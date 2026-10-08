#!/usr/bin/env python3
"""PROJETS de Synergie — un projet rassemble des groupes de travail.

    Un PROJET porte un nom, une description et des MEMBRES, chacun avec un RÔLE :

      • admin    : administre le projet — membres, groupes, réglages ;
      • membre   : participe : il écrit dans les groupes du projet ;
      • visiteur : consulte seulement, il ne modifie rien.

    Chaque GROUPE (thème de réflexion) a en plus ses propres membres, avec les mêmes rôles.
    Le rôle donné dans un GROUPE l'emporte sur le rôle de projet ; l'administrateur du
    projet est administrateur de tous ses groupes.

Les notifications se règlent séparément, au projet et au groupe : « prévenez-moi des
nouveautés » — l'adresse de courriel est demandée à ce moment-là, jamais à l'entrée.
"""
from __future__ import annotations

import secrets
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

RACINE = Path(__file__).resolve().parent.parent
DONNEES = RACINE / "donnees"
BASE = DONNEES / "atelier.db"

ROLES = ("admin", "membre", "visiteur")
LIBELLES_ROLES = {
    "admin": "Administrateur",
    "membre": "Membre participant",
    "visiteur": "Visiteur",
}
DESCRIPTIONS_ROLES = {
    "admin": "Administre le projet et ses groupes : membres, rôles, groupes.",
    "membre": "Écrit, dépose des documents, propose et vote des décisions.",
    "visiteur": "Consulte tout, sans rien modifier.",
}


def maintenant() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _identifiant(prefixe: str) -> str:
    alphabet = "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789"
    return prefixe + "-" + "".join(secrets.choice(alphabet) for _ in range(11))


def connexion() -> sqlite3.Connection:
    DONNEES.mkdir(parents=True, exist_ok=True)
    base = sqlite3.connect(BASE, timeout=15)
    base.row_factory = sqlite3.Row
    base.execute("PRAGMA journal_mode=WAL")
    base.execute("PRAGMA foreign_keys=ON")
    return base


SCHEMA = """
create table if not exists projets (
    id text primary key, nom text not null, description text default '',
    auteur text default '', cree_le text not null, maj_le text not null);
create table if not exists projet_membres (
    projet text not null, compte text not null, role text not null default 'membre',
    notifier integer default 0, ajoute_par text default '',
    cree_le text not null, maj_le text not null, primary key (projet, compte));
create table if not exists theme_membres (
    theme text not null, compte text not null, role text not null default 'membre',
    notifier integer default 0, ajoute_par text default '',
    cree_le text not null, maj_le text not null, primary key (theme, compte));
create index if not exists projet_membres_projet on projet_membres (projet);
create index if not exists theme_membres_theme on theme_membres (theme);
"""


def initialiser() -> None:
    with connexion() as base:
        base.executescript(SCHEMA)


def role_valide(role: str) -> str:
    return role if role in ROLES else "membre"


# ------------------------------------------------------------------ projets
def _projet_depuis(ligne: sqlite3.Row) -> dict:
    return dict(ligne)


def lister_projets(compte: str | None = None) -> list[dict]:
    """Les projets visibles : tous ceux dont on est membre (ou tous, pour l'accueil)."""
    with connexion() as base:
        if compte:
            lignes = base.execute(
                "select p.*, m.role, m.notifier from projets p"
                " join projet_membres m on m.projet = p.id"
                " where m.compte = ? order by p.maj_le desc, p.nom collate nocase", (compte,))
            projets = [dict(l) for l in lignes]
            for projet in projets:
                projet["groupes"] = base.execute(
                    "select count(*) from themes where projet = ?", (projet["id"],)
                ).fetchone()[0]
                projet["membres"] = base.execute(
                    "select count(*) from projet_membres where projet = ?", (projet["id"],)
                ).fetchone()[0]
            return projets
        lignes = base.execute("select * from projets order by maj_le desc, nom collate nocase")
        return [_projet_depuis(l) for l in lignes]


def lire_projet(identifiant: str) -> dict | None:
    with connexion() as base:
        ligne = base.execute("select * from projets where id = ?", (identifiant,)).fetchone()
    return dict(ligne) if ligne else None


def creer_projet(nom: str, description: str = "", auteur: str = "",
                 admin: str = "", qui: str = "") -> dict:
    moment = maintenant()
    projet = {"id": _identifiant("pr"), "nom": (nom or "Projet sans nom").strip(),
              "description": (description or "").strip(), "auteur": auteur or "",
              "cree_le": moment, "maj_le": moment}
    with connexion() as base:
        base.execute(
            "insert into projets (id, nom, description, auteur, cree_le, maj_le)"
            " values (:id, :nom, :description, :auteur, :cree_le, :maj_le)", projet)
    if admin:
        definir_membre_projet(projet["id"], admin, "admin", notifier=True,
                              ajoute_par=qui or auteur, silence=True)
    return projet


def maj_projet(identifiant: str, champs: dict, qui: str = "") -> dict | None:
    autorises = ("nom", "description")
    valeurs = {c: champs[c] for c in autorises if c in champs}
    if not valeurs:
        return lire_projet(identifiant)
    valeurs["maj_le"] = maintenant()
    valeurs["id"] = identifiant
    with connexion() as base:
        colonnes = ", ".join(f"{c} = :{c}" for c in valeurs if c != "id")
        base.execute(f"update projets set {colonnes} where id = :id", valeurs)
    return lire_projet(identifiant)


def supprimer_projet(identifiant: str, supprimer_groupes: bool = True) -> bool:
    """Supprime un projet. Avec ses groupes, TOUT leur contenu part aussi (notes,
    décisions, votes, bulletins, documents, pages, discussions) — on ne laisse jamais de
    contenu orphelin derrière soi. Avec `supprimer_groupes=False`, les groupes sont
    seulement détachés du projet et gardent leur contenu."""
    with connexion() as base:
        base.execute("delete from projet_membres where projet = ?", (identifiant,))
        if supprimer_groupes:
            groupes = [l["id"] for l in base.execute("select id from themes where projet = ?",
                                                     (identifiant,))]
            for theme in groupes:
                base.execute("delete from bulletins where theme = ?", (theme,))
                base.execute("delete from votes where decision in"
                             " (select id from decisions where theme = ?)", (theme,))
                for table in ("notes", "decisions", "documents", "pages", "messages",
                              "theme_membres", "journal"):
                    base.execute(f"delete from {table} where theme = ?", (theme,))
                base.execute("delete from themes where id = ?", (theme,))
        else:
            base.execute("update themes set projet = '' where projet = ?", (identifiant,))
        # La discussion et les comptes rendus DU projet lui-même.
        base.execute("delete from messages where theme = ?", (identifiant,))
        base.execute("delete from documents where theme = ?", (identifiant,))
        base.execute("delete from projets where id = ?", (identifiant,))
    return True


# ------------------------------------------------------------------ membres
def _avec_compte(base: sqlite3.Connection, ligne: sqlite3.Row) -> dict:
    membre = dict(ligne)
    compte = base.execute("select id, prenom, email, poste from comptes where id = ?",
                          (membre["compte"],)).fetchone()
    membre["prenom"] = compte["prenom"] if compte else "(compte supprimé)"
    membre["email"] = (compte["email"] if compte else "") or ""
    membre["poste"] = (compte["poste"] if compte else "") or ""
    membre["libelle_role"] = LIBELLES_ROLES.get(membre["role"], membre["role"])
    return membre


def membres_du_projet(projet: str) -> list[dict]:
    with connexion() as base:
        lignes = base.execute(
            "select * from projet_membres where projet = ?"
            " order by case role when 'admin' then 0 when 'membre' then 1 else 2 end,"
            " cree_le", (projet,))
        return [_avec_compte(base, l) for l in lignes]


def membres_du_theme(theme: str) -> list[dict]:
    with connexion() as base:
        lignes = base.execute(
            "select * from theme_membres where theme = ?"
            " order by case role when 'admin' then 0 when 'membre' then 1 else 2 end,"
            " cree_le", (theme,))
        return [_avec_compte(base, l) for l in lignes]


def _poser_membre(table: str, cle: str, valeur: str, compte: str, role: str | None,
                  notifier: bool | None, ajoute_par: str, silence: bool = False) -> dict:
    moment = maintenant()
    with connexion() as base:
        ligne = base.execute(f"select * from {table} where {cle} = ? and compte = ?",
                             (valeur, compte)).fetchone()
        # Un projet ne peut jamais perdre son dernier administrateur : la rétrogradation
        # est refusée (sinon plus personne ne peut gérer les membres ni les groupes).
        if (ligne and table == "projet_membres" and ligne["role"] == "admin"
                and role is not None and role != "admin"):
            autres = base.execute(
                "select count(*) from projet_membres where projet = ? and role = 'admin'"
                " and compte <> ?", (valeur, compte)).fetchone()[0]
            if not autres:
                raise ValueError("Un projet doit garder au moins un administrateur.")
        if ligne:
            # L'ordre des paramètres suit EXACTEMENT celui des « ? » de la requête : les
            # valeurs à poser d'abord, la clé et le compte ensuite (pour le WHERE).
            champs, valeurs = [], []
            if role is not None:
                champs.append("role = ?")
                valeurs.append(role_valide(role))
            if notifier is not None:
                champs.append("notifier = ?")
                valeurs.append(1 if notifier else 0)
            champs.append("maj_le = ?")
            valeurs.append(moment)
            valeurs.extend([valeur, compte])
            base.execute(f"update {table} set {', '.join(champs)}"
                         f" where {cle} = ? and compte = ?", valeurs)
        else:
            base.execute(
                f"insert into {table} ({cle}, compte, role, notifier, ajoute_par, cree_le,"
                f" maj_le) values (?, ?, ?, ?, ?, ?, ?)",
                (valeur, compte, role_valide(role or "membre"),
                 1 if notifier else 0, ajoute_par or "", moment, moment))
        ligne = base.execute(f"select * from {table} where {cle} = ? and compte = ?",
                             (valeur, compte)).fetchone()
        return _avec_compte(base, ligne)


def definir_membre_projet(projet: str, compte: str, role: str | None = None,
                          notifier: bool | None = None, ajoute_par: str = "",
                          silence: bool = False) -> dict:
    return _poser_membre("projet_membres", "projet", projet, compte, role, notifier,
                         ajoute_par, silence)


def definir_membre_theme(theme: str, compte: str, role: str | None = None,
                         notifier: bool | None = None, ajoute_par: str = "",
                         silence: bool = False) -> dict:
    return _poser_membre("theme_membres", "theme", theme, compte, role, notifier,
                         ajoute_par, silence)


def retirer_membre_projet(projet: str, compte: str) -> None:
    """Retire un membre — mais JAMAIS le dernier administrateur du projet."""
    with connexion() as base:
        ligne = base.execute("select role from projet_membres where projet = ? and compte = ?",
                             (projet, compte)).fetchone()
        if ligne and ligne["role"] == "admin":
            autres = base.execute(
                "select count(*) from projet_membres where projet = ? and role = 'admin'"
                " and compte <> ?", (projet, compte)).fetchone()[0]
            if not autres:
                raise ValueError("Un projet doit garder au moins un administrateur.")
        base.execute("delete from projet_membres where projet = ? and compte = ?",
                     (projet, compte))


def retirer_membre_theme(theme: str, compte: str) -> None:
    with connexion() as base:
        base.execute("delete from theme_membres where theme = ? and compte = ?",
                     (theme, compte))


def role_du_projet(projet: str, compte: str | None) -> str | None:
    if not compte:
        return None
    with connexion() as base:
        ligne = base.execute("select role from projet_membres where projet = ? and compte = ?",
                             (projet, compte)).fetchone()
    return ligne["role"] if ligne else None


def role_effectif(projet: str, theme: str | None, compte: str | None) -> str | None:
    """Le rôle qui s'applique : celui du GROUPE s'il existe, sinon celui du PROJET.

    L'administrateur du projet administre tous ses groupes.
    """
    if not compte:
        return None
    if theme:
        with connexion() as base:
            ligne = base.execute("select role from theme_membres where theme = ? and compte = ?",
                                 (theme, compte)).fetchone()
        if ligne:
            return ligne["role"]
    role = role_du_projet(projet, compte)
    return "admin" if role == "admin" else role


def peut_ecrire(role: str | None) -> bool:
    return role in ("admin", "membre")


def peut_administrer(role: str | None) -> bool:
    return role == "admin"


# ------------------------------------------------------------------ notifications
def destinataires_projet(projet: str) -> list[dict]:
    """Les membres du projet qui veulent être prévenus ET ont une adresse : qui, quoi."""
    with connexion() as base:
        lignes = base.execute(
            "select c.id, c.prenom, c.email, m.role from projet_membres m"
            " join comptes c on c.id = m.compte"
            " where m.projet = ? and m.notifier = 1 and c.email is not null and c.email <> ''",
            (projet,))
        return [dict(l) for l in lignes]


def destinataires_theme(theme: str, projet: str = "") -> list[dict]:
    """Les personnes à prévenir d'un changement de groupe : abonnés au groupe et au projet."""
    with connexion() as base:
        lignes = base.execute(
            "select c.id, c.prenom, c.email, 'groupe' as niveau from theme_membres m"
            " join comptes c on c.id = m.compte"
            " where m.theme = ? and m.notifier = 1 and c.email is not null and c.email <> ''",
            (theme,))
        trouves = {l["id"]: dict(l) for l in lignes}
        if projet:
            lignes = base.execute(
                "select c.id, c.prenom, c.email, 'projet' as niveau from projet_membres m"
                " join comptes c on c.id = m.compte"
                " where m.projet = ? and m.notifier = 1 and c.email is not null and c.email <> ''",
                (projet,))
            for ligne in lignes:
                trouves.setdefault(ligne["id"], dict(ligne))
    return list(trouves.values())
