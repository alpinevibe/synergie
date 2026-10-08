"""SYNERGIE — atelier collaboratif : thèmes de réflexion, tableau blanc, documents, décisions.

Le cœur de Synergie n'est plus le planning : c'est le TRAVAIL À PLUSIEURS. Un « thème de
réflexion » réunit une équipe autour d'un sujet ; dedans, chacun écrit ce qui lui passe par
la tête sur un tableau blanc sans limites (comme une feuille OneNote), dépose des documents
de travail, et ensemble on tranche des décisions. Tous les participants voient les
modifications des autres en direct.

Les données vivent dans une base SQLite (`donnees/atelier.db`) : plusieurs personnes
écrivent en même temps, un fichier JSON ne suffirait pas. Les documents déposés sont
rangés dans `donnees/documents/<thème>/`.

La diffusion temps réel passe par des files d'attente en mémoire : chaque navigateur
connecté en récupère une, et toute écriture est poussée à toutes les autres (SSE).
"""
from __future__ import annotations

import datetime as dt
import json
import os
import queue
import secrets
import shutil
import sqlite3
import threading
from pathlib import Path

RACINE = Path(__file__).resolve().parent.parent
DONNEES = RACINE / "donnees"
BASE = DONNEES / "atelier.db"
DOCUMENTS = DONNEES / "documents"

TAILLE_MAX_DOCUMENT = 40 * 1024 * 1024          # 40 Mo : suffisant pour un dossier de travail
COULEURS_FOND = ("#fff8d6", "#e7f2ff", "#e9f9ee", "#fdeceb", "#f0eaff", "#ffffff")
COULEURS_TEXTE = ("#1e2a3a", "#4a6cf7", "#17a673", "#c0392b", "#b26a00", "#7a3ea1")

# --- diffusion temps réel ------------------------------------------------------------
_ABONNES: dict[str, dict[int, dict]] = {}       # thème -> {n° de file -> {file, nom, vu}}
_VERROU = threading.Lock()
_COMPTEUR = [0]


def maintenant() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def _identifiant(prefixe: str) -> str:
    return f"{prefixe}-{secrets.token_urlsafe(8)}"


def connexion() -> sqlite3.Connection:
    DONNEES.mkdir(parents=True, exist_ok=True)
    base = sqlite3.connect(BASE, timeout=15)
    base.row_factory = sqlite3.Row
    base.execute("PRAGMA journal_mode=WAL")
    base.execute("PRAGMA foreign_keys=ON")
    return base


SCHEMA = """
create table if not exists themes (
    id text primary key, titre text not null, description text default '',
    couleur text default '#4a6cf7', projet text default '', auteur text default '',
    cree_le text not null, maj_le text not null);
create table if not exists notes (
    id text primary key, theme text not null, x real default 0, y real default 0,
    largeur real default 280, texte text default '', taille integer default 16,
    gras integer default 0, italique integer default 0, souligne integer default 0,
    couleur_texte text default '#1e2a3a', couleur_fond text default '#fff8d6',
    alignement text default 'gauche', ordre integer default 0, auteur text default '',
    cree_le text, maj_le text);
create table if not exists decisions (
    id text primary key, theme text not null, intitule text not null, detail text default '',
    statut text default 'proposee', auteur text default '', decide_par text default '',
    commentaire text default '', cree_le text, decide_le text);
create table if not exists documents (
    id text primary key, theme text not null, nom text not null, taille integer default 0,
    type text default '', fichier text default '', note text default '',
    auteur text default '', cree_le text);
create table if not exists journal (
    id integer primary key autoincrement, theme text, qui text default '', action text not null,
    cible text default '', details text default '', quand text not null);
-- Les votes sont ANONYMES : on ne garde jamais le nom, seulement une empreinte calculée avec
-- un secret du serveur (« cette personne a déjà voté »), et la valeur du vote à part.
create table if not exists votes (
    id text primary key, theme text not null, decision text not null,
    empreinte text not null, valeur text not null, quand text not null,
    unique (decision, empreinte));
create index if not exists notes_theme on notes (theme);
create index if not exists decisions_theme on decisions (theme);
create index if not exists documents_theme on documents (theme);
create index if not exists journal_theme on journal (theme);
create index if not exists votes_decision on votes (decision);
"""


# Thèmes retirés le 08/10/2026 : « Rythme de travail » (boîte à trames) et « Fiches de
# poste » partent dans l'application Orbis. Synergie ne garde que les GROUPES DE TRAVAIL
# issus d'une lettre de cadrage, tous outillés de la même façon.
THEMES_RETIRES = ("th-rythme-de-travail", "th-fiches-de-poste")


def initialiser() -> None:
    """Crée la base, le dossier des documents et les tables (atelier, équipe, projets)."""
    from . import projets as m_projets          # import local : aucun cycle à l'import
    DONNEES.mkdir(parents=True, exist_ok=True)
    DOCUMENTS.mkdir(parents=True, exist_ok=True)
    m_projets.initialiser()                     # les tables des projets d'abord
    with connexion() as base:
        base.executescript(SCHEMA)
        # Colonnes ajoutées après coup : on les crée seulement si elles manquent.
        colonnes = {l[1] for l in base.execute("pragma table_info(themes)")}
        for nom, definition in (("type", "text default 'libre'"),
                                ("fixe", "integer default 0"),
                                ("ordre", "integer default 100")):
            if nom not in colonnes:
                base.execute(f"alter table themes add column {nom} {definition}")
        # Migration : les deux thèmes fixes (et leurs notes, décisions, documents) quittent
        # Synergie. Les données correspondantes ont été exportées avant (donnees à part).
        marques = ",".join("?" for _ in THEMES_RETIRES)
        base.execute(f"delete from notes where theme in ({marques})", THEMES_RETIRES)
        base.execute(f"delete from decisions where theme in ({marques})", THEMES_RETIRES)
        base.execute(f"delete from documents where theme in ({marques})", THEMES_RETIRES)
        base.execute(f"delete from theme_membres where theme in ({marques})", THEMES_RETIRES)
        base.execute(f"delete from themes where id in ({marques})", THEMES_RETIRES)


# --- journal des actions -------------------------------------------------------------
# « Toutes les actions doivent être journalisées » (demande du 05/10/2026) : qui a fait
# quoi, quand, dans quel thème. Le journal se consulte dans le thème et sert de mémoire
# des décisions collectives.

ACTIONS_LISIBLES = {
    "theme_cree": "a créé le thème",
    "theme_modifie": "a modifié le thème",
    "note_creee": "a écrit une note",
    "note_modifiee": "a modifié une note",
    "note_deplacee": "a déplacé une note",
    "note_supprimee": "a supprimé une note",
    "decision_proposee": "a proposé une décision",
    "decision_modifiee": "a modifié une décision",
    "decision_tranchee": "a tranché une décision",
    "decision_supprimee": "a supprimé une décision",
    "vote": "a voté",
    "document_depose": "a déposé un document",
    "document_supprime": "a supprimé un document",
    "arrivee": "est arrivé dans le thème",
}


def journaliser(theme: str, qui: str, action: str, cible: str = "", details: str = "",
                diffuser_aussi: bool = True, silence: int = 0) -> dict | None:
    """Écrit une ligne de journal. `silence` (en secondes) évite de répéter la même action
    de la même personne sur la même cible : un déplacement de note envoie plusieurs
    positions, on ne veut pas dix lignes."""
    moment = maintenant()
    with connexion() as base:
        if silence:
            deja = base.execute(
                "select quand from journal where theme = ? and qui = ? and action = ?"
                " and cible = ? order by id desc limit 1",
                (theme, qui, action, cible)).fetchone()
            if deja and _secondes_depuis(deja["quand"]) < silence:
                return None
        base.execute("insert into journal (theme, qui, action, cible, details, quand)"
                     " values (?, ?, ?, ?, ?, ?)",
                     (theme, qui, action, cible, details, moment))
        ligne = base.execute("select * from journal order by id desc limit 1").fetchone()
    entree = dict(ligne)
    if diffuser_aussi:
        diffuser(theme, {"type": "journal", "entree": entree})
    return entree


def _secondes_depuis(moment: str) -> float:
    try:
        alors = dt.datetime.fromisoformat(str(moment).replace("Z", "+00:00"))
    except ValueError:
        return 1e9
    return (dt.datetime.now(dt.timezone.utc) - alors).total_seconds()


def lister_journal(theme: str, limite: int = 300) -> list[dict]:
    with connexion() as base:
        lignes = base.execute(
            "select * from journal where theme = ? order by id desc limit ?",
            (theme, limite)).fetchall()
    return [dict(l) for l in lignes]


# --- votes (anonymes, une fois par personne) -----------------------------------------
SECRET_VOTES = os.environ.get("SYNERGIE_SECRET_VOTES") or "synergie-votes"


def _empreinte(decision: str, nom: str) -> str:
    """Une empreinte qui permet de reconnaître « déjà voté » SANS jamais écrire le nom."""
    import hashlib
    propre = " ".join((nom or "").strip().lower().split())
    return hashlib.sha256(f"{decision}|{propre}|{SECRET_VOTES}".encode()).hexdigest()


def voter(theme: str, decision: str, nom: str, valeur: str) -> dict:
    """Enregistre un vote (pour, contre, neutre). Une seule fois par personne."""
    if valeur not in ("pour", "contre", "neutre"):
        raise ValueError("Vote inconnu")
    if not (nom or "").strip():
        raise ValueError("Il faut indiquer votre prénom pour voter")
    empreinte = _empreinte(decision, nom)
    try:
        with connexion() as base:
            base.execute("insert into votes (id, theme, decision, empreinte, valeur, quand)"
                         " values (?, ?, ?, ?, ?, ?)",
                         (_identifiant("vt"), theme, decision, empreinte, valeur, maintenant()))
    except sqlite3.IntegrityError:
        return {"ok": False, "deja": True,
                "erreur": "Vous avez déjà voté sur cette décision."}
    # Le vote est journalisé SANS le nom : le journal dit qu'un vote a été déposé, jamais
    # par qui — c'est la condition de l'anonymat demandé le 05/10/2026.
    journaliser(theme, "(vote anonyme)", "vote", decision, "", silence=0)
    resultat = {"ok": True, "decision": decision, "comptes": comptes_votes(theme)[decision]}
    diffuser(theme, {"type": "vote", "decision": decision, "comptes": resultat["comptes"]})
    return resultat


def comptes_votes(theme: str) -> dict[str, dict]:
    """Décompte par décision : pour / contre / neutre / total. Jamais qui a voté."""
    with connexion() as base:
        lignes = base.execute(
            "select decision, valeur, count(*) as nombre from votes where theme = ?"
            " group by decision, valeur", (theme,)).fetchall()
    comptes: dict[str, dict] = {}
    for ligne in lignes:
        casier = comptes.setdefault(ligne["decision"], {"pour": 0, "contre": 0, "neutre": 0,
                                                        "total": 0})
        casier[ligne["valeur"]] = ligne["nombre"]
        casier["total"] += ligne["nombre"]
    return comptes


def decisions_votees(theme: str, nom: str) -> list[str]:
    """Les décisions sur lesquelles CETTE personne a déjà voté (sans dire comment)."""
    if not (nom or "").strip():
        return []
    with connexion() as base:
        lignes = base.execute("select decision, empreinte from votes where theme = ?",
                              (theme,)).fetchall()
    return [l["decision"] for l in lignes if l["empreinte"] == _empreinte(l["decision"], nom)]


def supprimer_votes(theme: str, decision: str) -> None:
    with connexion() as base:
        base.execute("delete from votes where theme = ? and decision = ?", (theme, decision))


# --- thèmes --------------------------------------------------------------------------
def _theme_depuis(ligne: sqlite3.Row, comptes: dict | None = None) -> dict:
    theme = dict(ligne)
    if comptes:
        theme.update(comptes)
    return theme


def lister_themes(projet: str | None = None, identifiants: list[str] | None = None) -> list[dict]:
    """Les groupes de travail, éventuellement d'un seul projet ou d'une liste donnée."""
    requete = "select * from themes"
    valeurs: list = []
    conditions = []
    if projet is not None:
        conditions.append("projet = ?")
        valeurs.append(projet)
    if identifiants is not None:
        if not identifiants:
            return []
        conditions.append("id in (" + ",".join("?" for _ in identifiants) + ")")
        valeurs.extend(identifiants)
    if conditions:
        requete += " where " + " and ".join(conditions)
    requete += " order by ordre, maj_le desc, titre collate nocase"
    with connexion() as base:
        themes = [dict(l) for l in base.execute(requete, valeurs)]
        for theme in themes:
            theme["notes"] = base.execute(
                "select count(*) from notes where theme = ?", (theme["id"],)).fetchone()[0]
            theme["decisions"] = base.execute(
                "select count(*) from decisions where theme = ?", (theme["id"],)).fetchone()[0]
            theme["documents"] = base.execute(
                "select count(*) from documents where theme = ?", (theme["id"],)).fetchone()[0]
            theme["adoptees"] = base.execute(
                "select count(*) from decisions where theme = ? and statut = 'adoptee'",
                (theme["id"],)).fetchone()[0]
            theme["membres"] = base.execute(
                "select count(*) from theme_membres where theme = ?", (theme["id"],)
            ).fetchone()[0]
    return themes


def creer_theme(titre: str, description: str = "", couleur: str = "", projet: str = "",
                auteur: str = "", type_theme: str = "libre") -> dict:
    moment = maintenant()
    theme = {
        "id": _identifiant("th"), "titre": (titre or "Thème sans titre").strip(),
        "description": (description or "").strip(), "couleur": couleur or "#4a6cf7",
        "projet": projet or "", "auteur": auteur or "", "cree_le": moment, "maj_le": moment,
        "type": type_theme or "libre", "fixe": 0, "ordre": 100,
    }
    with connexion() as base:
        base.execute("insert into themes (id, titre, description, couleur, projet, auteur,"
                     " cree_le, maj_le, type, fixe, ordre) values (:id, :titre, :description,"
                     " :couleur, :projet, :auteur, :cree_le, :maj_le, :type, :fixe, :ordre)",
                     theme)
    journaliser(theme["id"], auteur or "Anonyme", "theme_cree", theme["id"], theme["titre"])
    return theme


def lire_theme(identifiant: str) -> dict | None:
    with connexion() as base:
        ligne = base.execute("select * from themes where id = ?", (identifiant,)).fetchone()
    return dict(ligne) if ligne else None


def maj_theme(identifiant: str, champs: dict, qui: str = "") -> dict | None:
    autorises = ("titre", "description", "couleur", "projet")
    valeurs = {c: champs[c] for c in autorises if c in champs}
    if not valeurs:
        return lire_theme(identifiant)
    valeurs["maj_le"] = maintenant()
    colonnes = ", ".join(f"{c} = :{c}" for c in valeurs)
    valeurs["id"] = identifiant
    with connexion() as base:
        base.execute(f"update themes set {colonnes} where id = :id", valeurs)
    journaliser(identifiant, qui or "Anonyme", "theme_modifie", identifiant,
                ", ".join(sorted(valeurs)))
    return lire_theme(identifiant)


def supprimer_theme(identifiant: str) -> bool:
    """Supprime un thème et tout son contenu. Les thèmes FIXES (Rythme de travail,
    Fiches de poste) ne se suppriment pas : la fonction refuse et rend False."""
    theme = lire_theme(identifiant)
    if not theme:
        return False
    if theme.get("fixe"):
        return False
    with connexion() as base:
        # Les bulletins de vote partent avec les décisions du groupe (sinon ils
        # s'accumuleraient sans fin, sans pouvoir être rattachés à quoi que ce soit).
        base.execute("delete from bulletins where theme = ?", (identifiant,))
        base.execute("delete from votes where decision in"
                     " (select id from decisions where theme = ?)", (identifiant,))
        for table in ("notes", "decisions", "documents"):
            base.execute(f"delete from {table} where theme = ?", (identifiant,))
        base.execute("delete from themes where id = ?", (identifiant,))
    dossier = DOCUMENTS / identifiant
    if dossier.is_dir():
        shutil.rmtree(dossier, ignore_errors=True)
    diffuser(identifiant, {"type": "theme_supprime"})
    return True


# --- notes du tableau blanc ----------------------------------------------------------
CHAMPS_NOTE = ("x", "y", "largeur", "texte", "taille", "gras", "italique", "souligne",
               "couleur_texte", "couleur_fond", "alignement", "ordre", "auteur")


def _note_depuis(ligne: sqlite3.Row) -> dict:
    note = dict(ligne)
    for champ in ("gras", "italique", "souligne"):
        note[champ] = bool(note.get(champ))
    return note


def lister_notes(theme: str) -> list[dict]:
    with connexion() as base:
        lignes = base.execute(
            "select * from notes where theme = ? order by ordre, cree_le", (theme,)).fetchall()
    return [_note_depuis(l) for l in lignes]


def creer_note(theme: str, champs: dict) -> dict:
    moment = maintenant()
    note = {
        "id": _identifiant("nt"), "theme": theme,
        "x": float(champs.get("x") or 0), "y": float(champs.get("y") or 0),
        "largeur": float(champs.get("largeur") or 280),
        "texte": str(champs.get("texte") or ""),
        "taille": int(champs.get("taille") or 16),
        "gras": 1 if champs.get("gras") else 0,
        "italique": 1 if champs.get("italique") else 0,
        "souligne": 1 if champs.get("souligne") else 0,
        "couleur_texte": champs.get("couleur_texte") or COULEURS_TEXTE[0],
        "couleur_fond": champs.get("couleur_fond") or COULEURS_FOND[0],
        "alignement": champs.get("alignement") or "gauche",
        "ordre": int(champs.get("ordre") or 0), "auteur": champs.get("auteur") or "",
        "cree_le": moment, "maj_le": moment,
    }
    with connexion() as base:
        base.execute(
            "insert into notes (id, theme, x, y, largeur, texte, taille, gras, italique,"
            " souligne, couleur_texte, couleur_fond, alignement, ordre, auteur, cree_le, maj_le)"
            " values (:id, :theme, :x, :y, :largeur, :texte, :taille, :gras, :italique,"
            " :souligne, :couleur_texte, :couleur_fond, :alignement, :ordre, :auteur,"
            " :cree_le, :maj_le)", note)
    note = _note_depuis_dict(note)
    journaliser(theme, note["auteur"] or "Anonyme", "note_creee", note["id"],
                (note["texte"] or "")[:120])
    diffuser(theme, {"type": "note_creee", "note": note})
    return note


def _note_depuis_dict(note: dict) -> dict:
    for champ in ("gras", "italique", "souligne"):
        note[champ] = bool(note.get(champ))
    return note


def maj_note(theme: str, note_id: str, champs: dict, qui: str = "") -> dict | None:
    valeurs = {c: champs[c] for c in CHAMPS_NOTE if c in champs}
    if not valeurs:
        return None
    for booleen in ("gras", "italique", "souligne"):
        if booleen in valeurs:
            valeurs[booleen] = 1 if valeurs[booleen] else 0
    valeurs["maj_le"] = maintenant()
    colonnes = ", ".join(f"{c} = :{c}" for c in valeurs)
    valeurs["id"] = note_id
    valeurs["theme"] = theme
    with connexion() as base:
        base.execute(f"update notes set {colonnes} where id = :id and theme = :theme", valeurs)
        base.execute("update themes set maj_le = ? where id = ?", (valeurs["maj_le"], theme))
        ligne = base.execute("select * from notes where id = ?", (note_id,)).fetchone()
    if not ligne:
        return None
    note = _note_depuis(ligne)
    # Un déplacement envoie plusieurs positions d'affilée : on ne journalise qu'une fois
    # par minute, sinon le journal deviendrait illisible.
    if set(valeurs) <= {"x", "y"}:
        journaliser(theme, qui or note["auteur"] or "Anonyme", "note_deplacee", note_id,
                    silence=60)
    else:
        journaliser(theme, qui or note["auteur"] or "Anonyme", "note_modifiee", note_id,
                    (note["texte"] or "")[:120], silence=30)
    diffuser(theme, {"type": "note_maj", "note": note})
    return note


def supprimer_note(theme: str, note_id: str, qui: str = "") -> None:
    with connexion() as base:
        base.execute("delete from notes where id = ? and theme = ?", (note_id, theme))
    journaliser(theme, qui or "Anonyme", "note_supprimee", note_id)
    diffuser(theme, {"type": "note_supprimee", "id": note_id})


# --- décisions -----------------------------------------------------------------------
def lister_decisions(theme: str) -> list[dict]:
    with connexion() as base:
        lignes = base.execute(
            "select * from decisions where theme = ? order by cree_le desc", (theme,)).fetchall()
    return [dict(l) for l in lignes]


def creer_decision(theme: str, intitule: str, detail: str = "", auteur: str = "") -> dict:
    decision = {
        "id": _identifiant("dc"), "theme": theme, "intitule": (intitule or "Décision").strip(),
        "detail": (detail or "").strip(), "statut": "proposee", "auteur": auteur or "",
        "decide_par": "", "commentaire": "", "cree_le": maintenant(), "decide_le": None,
    }
    with connexion() as base:
        base.execute(
            "insert into decisions (id, theme, intitule, detail, statut, auteur, decide_par,"
            " commentaire, cree_le, decide_le) values (:id, :theme, :intitule, :detail,"
            " :statut, :auteur, :decide_par, :commentaire, :cree_le, :decide_le)", decision)
    journaliser(theme, auteur or "Anonyme", "decision_proposee", decision["id"],
                decision["intitule"])
    diffuser(theme, {"type": "decision_creee", "decision": decision})
    return decision


def maj_decision(theme: str, decision_id: str, champs: dict, qui: str = "") -> dict | None:
    autorises = ("intitule", "detail", "commentaire")
    valeurs = {c: champs[c] for c in autorises if c in champs}
    if champs.get("statut") in ("proposee", "adoptee", "rejetee", "en attente"):
        valeurs["statut"] = champs["statut"]
        valeurs["decide_le"] = maintenant() if valeurs["statut"] != "proposee" else None
        valeurs["decide_par"] = champs.get("decide_par") or ""
    if not valeurs:
        return None
    colonnes = ", ".join(f"{c} = :{c}" for c in valeurs)
    valeurs.update({"id": decision_id, "theme": theme})
    with connexion() as base:
        base.execute(f"update decisions set {colonnes} where id = :id and theme = :theme",
                     valeurs)
        ligne = base.execute("select * from decisions where id = ?", (decision_id,)).fetchone()
    if not ligne:
        return None
    decision = dict(ligne)
    action = "decision_tranchee" if "statut" in valeurs else "decision_modifiee"
    journaliser(theme, qui or decision["decide_par"] or "Anonyme", action, decision_id,
                decision["intitule"] + (" — " + decision["statut"]
                                        if action == "decision_tranchee" else ""))
    diffuser(theme, {"type": "decision_maj", "decision": decision})
    return decision


def supprimer_decision(theme: str, decision_id: str, qui: str = "") -> None:
    with connexion() as base:
        base.execute("delete from decisions where id = ? and theme = ?", (decision_id, theme))
    supprimer_votes(theme, decision_id)
    journaliser(theme, qui or "Anonyme", "decision_supprimee", decision_id)
    diffuser(theme, {"type": "decision_supprimee", "id": decision_id})


# --- documents de travail ------------------------------------------------------------
def lister_documents(theme: str) -> list[dict]:
    with connexion() as base:
        lignes = base.execute(
            "select id, theme, nom, taille, type, note, auteur, cree_le from documents"
            " where theme = ? order by cree_le desc", (theme,)).fetchall()
    return [dict(l) for l in lignes]


def ajouter_document(theme: str, nom: str, contenu: bytes, type_fichier: str = "",
                     note: str = "", auteur: str = "") -> dict:
    """Enregistre un document de travail déposé par un participant."""
    if len(contenu) > TAILLE_MAX_DOCUMENT:
        raise ValueError(f"Document trop volumineux (maximum "
                         f"{TAILLE_MAX_DOCUMENT // (1024 * 1024)} Mo).")
    dossier = DOCUMENTS / theme
    dossier.mkdir(parents=True, exist_ok=True)
    identifiant = _identifiant("doc")
    nom_propre = os.path.basename(nom or "document")
    (dossier / f"{identifiant}__{nom_propre}").write_bytes(contenu)
    document = {
        "id": identifiant, "theme": theme, "nom": nom_propre, "taille": len(contenu),
        "type": type_fichier or "", "fichier": f"{identifiant}__{nom_propre}",
        "note": note or "", "auteur": auteur or "", "cree_le": maintenant(),
    }
    with connexion() as base:
        base.execute(
            "insert into documents (id, theme, nom, taille, type, fichier, note, auteur,"
            " cree_le) values (:id, :theme, :nom, :taille, :type, :fichier, :note, :auteur,"
            " :cree_le)", document)
    public = {c: v for c, v in document.items() if c != "fichier"}
    journaliser(theme, auteur or "Anonyme", "document_depose", public["id"], public["nom"])
    diffuser(theme, {"type": "document_ajoute", "document": public})
    return public


def chemin_document(theme: str, document_id: str) -> tuple[str, str] | None:
    with connexion() as base:
        ligne = base.execute(
            "select nom, fichier from documents where id = ? and theme = ?",
            (document_id, theme)).fetchone()
    if not ligne:
        return None
    return ligne["nom"], str(DOCUMENTS / theme / ligne["fichier"])


def supprimer_document(theme: str, document_id: str, qui: str = "") -> None:
    with connexion() as base:
        ligne = base.execute("select fichier from documents where id = ? and theme = ?",
                             (document_id, theme)).fetchone()
        base.execute("delete from documents where id = ? and theme = ?", (document_id, theme))
    if ligne:
        (DOCUMENTS / theme / ligne["fichier"]).unlink(missing_ok=True)
    journaliser(theme, qui or "Anonyme", "document_supprime", document_id)
    diffuser(theme, {"type": "document_supprime", "id": document_id})


# --- présence et diffusion temps réel ------------------------------------------------
def abonner(theme: str, nom: str) -> tuple[int, queue.Queue]:
    """Une file d'attente par navigateur connecté : il y reçoit tout ce qui se passe."""
    file: queue.Queue = queue.Queue()
    with _VERROU:
        _COMPTEUR[0] += 1
        numero = _COMPTEUR[0]
        _ABONNES.setdefault(theme, {})[numero] = {
            "file": file, "nom": nom or "Anonyme", "arrive": maintenant()}
    diffuser(theme, {"type": "presence", "participants": participants(theme)})
    return numero, file


def desabonner(theme: str, numero: int) -> None:
    with _VERROU:
        (_ABONNES.get(theme) or {}).pop(numero, None)
    diffuser(theme, {"type": "presence", "participants": participants(theme)})


def participants(theme: str) -> list[str]:
    with _VERROU:
        noms = [a["nom"] for a in (_ABONNES.get(theme) or {}).values()]
    vus, uniques = set(), []
    for nom in noms:
        if nom not in vus:
            vus.add(nom)
            uniques.append(nom)
    return uniques


def diffuser(theme: str, evenement: dict) -> None:
    """Pousse un événement à tous les navigateurs connectés sur ce thème."""
    with _VERROU:
        abonnes = list((_ABONNES.get(theme) or {}).values())
    for abonne in abonnes:
        abonne["file"].put(evenement)


def resume(theme: str, qui: str = "") -> dict:
    """Tout le contenu d'un thème, en une seule réponse."""
    theme_complet = lire_theme(theme)
    if not theme_complet:
        return {}
    return {
        "theme": theme_complet,
        "notes": lister_notes(theme),
        "decisions": lister_decisions(theme),
        "documents": lister_documents(theme),
        "participants": participants(theme),
        "journal": lister_journal(theme, 200),
        "votes": comptes_votes(theme),
        "mes_votes": decisions_votees(theme, qui),
    }


def sante() -> dict:
    try:
        with connexion() as base:
            base.execute("select 1").fetchone()
        return {"ok": True, "base": str(BASE), "themes": len(lister_themes())}
    except Exception as erreur:                     # pragma: no cover - dépend du disque
        return {"ok": False, "erreur": str(erreur)}
