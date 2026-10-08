#!/usr/bin/env python3
"""VOTES ET SONDAGES — consulter le groupe, et décider ensemble.

    Deux objets, deux usages (consigne du 08/10/2026) :

      • un VOTE est une **prise de décision collective** : UNE question, réponse **oui/non** ;
      • un SONDAGE est une **consultation collective** qui aide le groupe à réfléchir :
        PLUSIEURS questions, avec le type de réponse qui convient (choix unique, cases à
        cocher, liste déroulante, échelle, un mot pour un nuage de mots).

    Dans les deux cas :
      • on choisit QUI l'on consulte : les membres du groupe, ou tout le projet ;
      • chaque personne reçoit un **lien personnel** par courriel : **une personne, une
        réponse**, et le dépouillement reste **anonyme** (on ne garde qu'une empreinte).

Les tables vivent dans la même base SQLite que l'atelier (`donnees/atelier.db`).
"""
from __future__ import annotations

import json
import secrets
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path

RACINE = Path(__file__).resolve().parent.parent
DONNEES = RACINE / "donnees"
BASE = DONNEES / "atelier.db"

TYPES = ("vote", "sondage")
TYPES_QUESTION = ("oui_non", "unique", "multiple", "liste", "likert", "mot")
LIBELLES_QUESTION = {
    "oui_non": "Oui / Non",
    "unique": "Choix unique (une seule réponse)",
    "multiple": "Cases à cocher (plusieurs réponses)",
    "liste": "Liste déroulante",
    "likert": "Échelle de 1 à 5",
    "mot": "Un mot (nuage de mots)",
}
ECHELLE_MIN, ECHELLE_MAX = 1, 5


def maintenant() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _identifiant(prefixe: str) -> str:
    alphabet = "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789"
    return prefixe + "-" + "".join(secrets.choice(alphabet) for _ in range(11))


@contextmanager
def connexion():
    DONNEES.mkdir(parents=True, exist_ok=True)
    base = sqlite3.connect(BASE, timeout=15)
    base.row_factory = sqlite3.Row
    try:
        base.execute("PRAGMA journal_mode=WAL")
        yield base
        base.commit()
    except Exception:
        base.rollback()
        raise
    finally:
        base.close()


SCHEMA = """
create table if not exists consultations (
    id text primary key, theme text not null, type text not null default 'sondage',
    intitule text not null, detail text default '', scrutin text default 'groupe',
    statut text default 'brouillon', auteur text default '',
    cree_le text not null, ouverte_le text default '', close_le text default '');
create table if not exists questions (
    id text primary key, consultation text not null, ordre integer default 0,
    type text not null default 'unique', intitule text not null, options text default '[]',
    obligatoire integer default 1);
create table if not exists reponses (
    id text primary key, consultation text not null, question text not null,
    empreinte text not null, valeur text not null, cree_le text not null);
create table if not exists bulletins (
    id text primary key, consultation text not null, theme text not null,
    compte text default '', email text not null, jeton text not null unique,
    scrutin text default 'groupe', cree_le text not null, repondu_le text default '',
    valeur text default '');
create index if not exists questions_consultation on questions (consultation);
create index if not exists bulletins_consultation on bulletins (consultation);
create index if not exists reponses_consultation on reponses (consultation);
create index if not exists reponses_question on reponses (question);
"""


def initialiser() -> None:
    with connexion() as base:
        base.executescript(SCHEMA)


# ------------------------------------------------------------------ consultations
def _questions_public(consultation: str) -> list[dict]:
    with connexion() as base:
        lignes = base.execute(
            "select * from questions where consultation = ? order by ordre, id",
            (consultation,))
        questions = []
        for ligne in lignes:
            question = dict(ligne)
            question["options"] = json.loads(question.get("options") or "[]")
            question["libelle_type"] = LIBELLES_QUESTION.get(question["type"], question["type"])
            questions.append(question)
    return questions


def _avec_compteurs(consultation: dict) -> dict:
    with connexion() as base:
        consultation["bulletins"] = base.execute(
            "select count(*) from bulletins where consultation = ?", (consultation["id"],)
        ).fetchone()[0]
        consultation["repondu"] = base.execute(
            "select count(*) from bulletins where consultation = ? and repondu_le <> ''",
            (consultation["id"],)).fetchone()[0]
        consultation["questions"] = base.execute(
            "select count(*) from questions where consultation = ?", (consultation["id"],)
        ).fetchone()[0]
    consultation["libelle_type"] = ("Vote (oui / non)" if consultation["type"] == "vote"
                                    else "Sondage")
    return consultation


def lister_consultations(theme: str) -> list[dict]:
    with connexion() as base:
        lignes = base.execute("select * from consultations where theme = ?"
                              " order by cree_le desc", (theme,))
        return [_avec_compteurs(dict(l)) for l in lignes]


def lire_consultation(identifiant: str) -> dict | None:
    with connexion() as base:
        ligne = base.execute("select * from consultations where id = ?",
                             (identifiant,)).fetchone()
        if not ligne:
            return None
        consultation = _avec_compteurs(dict(ligne))
        consultation["questions_detaillees"] = _questions_public(identifiant)
    return consultation


def _nettoyer_questions(questions: list[dict], type_consultation: str) -> list[dict]:
    """Prépare les questions reçues : on ne garde que ce qui a un sens."""
    propres = []
    for question in questions or []:
        intitule = (question.get("intitule") or "").strip()
        if not intitule:
            continue
        type_question = question.get("type") if question.get("type") in TYPES_QUESTION else "unique"
        if type_consultation == "vote":
            type_question = "oui_non"
        options = [str(o).strip() for o in (question.get("options") or []) if str(o).strip()]
        if type_question in ("unique", "multiple", "liste") and not options:
            options = ["Oui", "Non"] if type_question != "liste" else ["", "Oui", "Non"]
        if type_question in ("oui_non", "likert", "mot"):
            options = []
        propres.append({"type": type_question, "intitule": intitule, "options": options})
    return propres


def creer_consultation(theme: str, type_consultation: str, intitule: str,
                       detail: str = "", questions: list[dict] | None = None,
                       auteur: str = "") -> dict:
    type_consultation = type_consultation if type_consultation in TYPES else "sondage"
    titre = (intitule or "").strip()
    if not titre:
        raise ValueError("Donnez un intitulé à la consultation.")
    propres = _nettoyer_questions(questions or [], type_consultation)
    if type_consultation == "vote" and not propres:
        propres = [{"type": "oui_non", "intitule": titre, "options": []}]
    if not propres:
        raise ValueError("Ajoutez au moins une question.")
    consultation = {"id": _identifiant("cs"), "theme": theme, "type": type_consultation,
                    "intitule": titre, "detail": (detail or "").strip(),
                    "scrutin": "groupe", "statut": "brouillon", "auteur": auteur or "",
                    "cree_le": maintenant(), "ouverte_le": "", "close_le": ""}
    with connexion() as base:
        base.execute(
            "insert into consultations (id, theme, type, intitule, detail, scrutin, statut,"
            " auteur, cree_le, ouverte_le, close_le) values (:id, :theme, :type, :intitule,"
            " :detail, :scrutin, :statut, :auteur, :cree_le, :ouverte_le, :close_le)",
            consultation)
        for rang, question in enumerate(propres):
            base.execute(
                "insert into questions (id, consultation, ordre, type, intitule, options,"
                " obligatoire) values (?, ?, ?, ?, ?, ?, 1)",
                (_identifiant("qs"), consultation["id"], rang, question["type"],
                 question["intitule"], json.dumps(question["options"], ensure_ascii=False)))
    return lire_consultation(consultation["id"])


def maj_consultation(identifiant: str, champs: dict) -> dict | None:
    consultation = lire_consultation(identifiant)
    if not consultation:
        return None
    valeurs = {}
    for cle in ("intitule", "detail"):
        if cle in champs:
            valeurs[cle] = (champs[cle] or "").strip()
    with connexion() as base:
        if valeurs:
            base.execute("update consultations set intitule = ?, detail = ? where id = ?",
                         (valeurs.get("intitule", consultation["intitule"]),
                          valeurs.get("detail", consultation["detail"]), identifiant))
        if "questions" in champs and consultation["statut"] == "brouillon":
            propres = _nettoyer_questions(champs["questions"] or [], consultation["type"])
            base.execute("delete from questions where consultation = ?", (identifiant,))
            for rang, question in enumerate(propres):
                base.execute(
                    "insert into questions (id, consultation, ordre, type, intitule, options,"
                    " obligatoire) values (?, ?, ?, ?, ?, ?, 1)",
                    (_identifiant("qs"), identifiant, rang, question["type"],
                     question["intitule"], json.dumps(question["options"], ensure_ascii=False)))
    return lire_consultation(identifiant)


def supprimer_consultation(identifiant: str) -> bool:
    with connexion() as base:
        base.execute("delete from reponses where consultation = ?", (identifiant,))
        base.execute("delete from questions where consultation = ?", (identifiant,))
        base.execute("delete from bulletins where consultation = ?", (identifiant,))
        base.execute("delete from consultations where id = ?", (identifiant,))
    return True


def ouvrir_consultation(identifiant: str, scrutin: str = "groupe") -> dict | None:
    """Ouvre la consultation : à partir de là, les liens personnels peuvent être utilisés."""
    with connexion() as base:
        base.execute("update consultations set scrutin = ?, statut = 'ouverte', ouverte_le = ?"
                     " where id = ?",
                     ("projet" if scrutin == "projet" else "groupe", maintenant(), identifiant))
    return lire_consultation(identifiant)


def fermer_consultation(identifiant: str) -> dict | None:
    with connexion() as base:
        base.execute("update consultations set statut = 'close', close_le = ? where id = ?",
                     (maintenant(), identifiant))
    return lire_consultation(identifiant)


# ------------------------------------------------------------------ bulletins
def creer_bulletin(consultation: str, theme: str, compte: str, email: str,
                   scrutin: str) -> dict:
    """Un bulletin = UNE réponse possible, envoyée à une adresse : une personne, une voix."""
    bulletin = {"id": _identifiant("bu"),
                "consultation": consultation, "theme": theme, "compte": compte,
                "email": (email or "").strip().lower(), "jeton": _identifiant("bul"),
                "scrutin": scrutin or "groupe", "cree_le": maintenant(), "repondu_le": "",
                "valeur": ""}
    with connexion() as base:
        base.execute(
            "insert into bulletins (id, consultation, theme, compte, email, jeton, scrutin,"
            " cree_le, repondu_le, valeur) values (:id, :consultation, :theme, :compte,"
            " :email, :jeton, :scrutin, :cree_le, :repondu_le, :valeur)", bulletin)
    return bulletin


def lire_bulletin(jeton: str) -> dict | None:
    with connexion() as base:
        ligne = base.execute("select * from bulletins where jeton = ?", (jeton,)).fetchone()
    return dict(ligne) if ligne else None


def lister_bulletins(consultation: str) -> list[dict]:
    with connexion() as base:
        lignes = base.execute("select * from bulletins where consultation = ? order by cree_le",
                              (consultation,))
        return [dict(l) for l in lignes]


def enregistrer_reponses(jeton: str, reponses: dict) -> dict:
    """Enregistre les réponses d'un bulletin. Un bulletin ne sert QU'UNE fois.

    `reponses` : {identifiant de question: valeur} — la valeur est une chaîne, ou une
    liste pour les questions à réponses multiples.
    """
    from .atelier import _empreinte                     # anonymat : une empreinte, pas un nom

    bulletin = lire_bulletin(jeton)
    if not bulletin:
        raise ValueError("Ce lien de consultation n'existe pas.")
    if bulletin.get("repondu_le"):
        raise ValueError("Vous avez déjà répondu : une personne, une réponse.")
    consultation = lire_consultation(bulletin["consultation"])
    if not consultation:
        raise ValueError("Cette consultation n'existe plus.")
    if consultation["statut"] != "ouverte":
        raise ValueError("Cette consultation n'est pas ouverte.")

    empreinte = _empreinte(bulletin["consultation"], bulletin["compte"])
    moment = maintenant()
    enregistrements = []
    for question in consultation["questions_detaillees"]:
        if question["id"] not in reponses:
            if question.get("obligatoire"):
                raise ValueError("Il manque une réponse à : " + question["intitule"])
            continue
        valeur = reponses[question["id"]]
        valeurs = valeur if isinstance(valeur, list) else [valeur]
        for choix in valeurs:
            propre = str(choix or "").strip()[:300]
            if propre:
                enregistrements.append((_identifiant("rp"), bulletin["consultation"],
                                        question["id"], empreinte, propre, moment))
    with connexion() as base:
        base.executemany("insert into reponses (id, consultation, question, empreinte,"
                         " valeur, cree_le) values (?, ?, ?, ?, ?, ?)", enregistrements)
        base.execute("update bulletins set repondu_le = ?, valeur = ? where jeton = ?",
                     (moment, "repondu", jeton))
    return {"ok": True, "reponses": len(enregistrements)}


# ------------------------------------------------------------------ résultats
def resultats(identifiant: str) -> list[dict]:
    """Le dépouillement, question par question — jamais nominatif."""
    consultation = lire_consultation(identifiant)
    if not consultation:
        return []
    sortie = []
    for question in consultation["questions_detaillees"]:
        with connexion() as base:
            lignes = base.execute(
                "select valeur, count(*) as nombre from reponses where question = ?"
                " group by valeur order by nombre desc", (question["id"],)).fetchall()
        comptes = [{"valeur": l["valeur"], "nombre": l["nombre"]} for l in lignes]
        total = sum(c["nombre"] for c in comptes)
        detail = {"id": question["id"], "intitule": question["intitule"],
                  "type": question["type"], "libelle_type": question["libelle_type"],
                  "options": question["options"], "total": total}
        if question["type"] == "mot":
            detail["mots"] = comptes[:200]
        elif question["type"] == "likert":
            valeurs = []
            with connexion() as base:
                for ligne in base.execute("select valeur from reponses where question = ?",
                                          (question["id"],)):
                    try:
                        valeurs.append(float(ligne["valeur"]))
                    except ValueError:
                        continue
            detail["moyenne"] = round(sum(valeurs) / len(valeurs), 2) if valeurs else None
            detail["repartition"] = [
                {"valeur": str(note),
                 "nombre": len([v for v in valeurs if round(v) == note])}
                for note in range(ECHELLE_MIN, ECHELLE_MAX + 1)]
        else:
            detail["comptes"] = comptes
        sortie.append(detail)
    return sortie


def courriel_consultation(bulletin: dict, consultation: dict, nom_groupe: str) -> tuple[str, str]:
    from . import equipe as m_equipe

    lien = f"{m_equipe.adresse_site()}/#vote={bulletin['jeton']}"
    qui = ("les membres du groupe" if bulletin["scrutin"] == "groupe"
           else "tous les membres du projet")
    quoi = "Un vote est ouvert" if consultation["type"] == "vote" else "Un sondage est ouvert"
    sujet = f"[Synergie] {consultation['libelle_type']} : {consultation['intitule'][:70]}"
    corps = (
        f"Bonjour,\n\n{quoi} dans le groupe « {nom_groupe} » :\n\n"
        f"    {consultation['intitule']}\n"
        + (f"\n{consultation['detail']}\n" if consultation.get("detail") else "")
        + f"\nVous êtes invité(e) à répondre comme {qui}.\n\n"
        f"Pour répondre, ouvrez ce lien :\n{lien}\n\n"
        "Ce lien est personnel : il ne permet QU'UNE réponse, et les réponses restent\n"
        "anonymes dans le dépouillement.\n\nÀ bientôt sur Synergie.\n")
    return sujet, corps
