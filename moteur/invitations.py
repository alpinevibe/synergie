#!/usr/bin/env python3
"""INVITATIONS — on invite par ADRESSE DE COURRIEL, et la personne active son compte.

    Comment ça marche (consigne du 08/10/2026) :

      1. l'administrateur du projet saisit l'ADRESSE de la personne et son rôle ;
      2. Synergie envoie un courriel contenant un LIEN PERSONNEL (à usage unique) ;
      3. en ouvrant le lien, la personne choisit son PRÉNOM et son IDENTIFIANT personnel :
         le prénom, l'adresse et l'identifiant sont alors associés au même compte ;
      4. ensuite, on entre dans Synergie avec son **identifiant** seulement — un identifiant
         personnel ne se devine pas, personne ne peut donc prendre l'identité d'un autre.

Un lien d'invitation est valable 30 jours et ne sert qu'une fois.
"""
from __future__ import annotations

import secrets
import sqlite3
from datetime import datetime, timedelta, timezone
from pathlib import Path

RACINE = Path(__file__).resolve().parent.parent
DONNEES = RACINE / "donnees"
BASE = DONNEES / "atelier.db"

DUREE_JOURS = 30


def maintenant() -> datetime:
    return datetime.now(timezone.utc)


def _iso(moment: datetime) -> str:
    return moment.strftime("%Y-%m-%dT%H:%M:%SZ")


def _identifiant(prefixe: str) -> str:
    alphabet = "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789"
    return prefixe + "-" + "".join(secrets.choice(alphabet) for _ in range(22))


def connexion() -> sqlite3.Connection:
    DONNEES.mkdir(parents=True, exist_ok=True)
    base = sqlite3.connect(BASE, timeout=15)
    base.row_factory = sqlite3.Row
    base.execute("PRAGMA journal_mode=WAL")
    return base


SCHEMA = """
create table if not exists invitations (
    id text primary key, email text not null, prenom text default '',
    projet text not null, role text default 'membre', jeton text not null unique,
    note text default '', cree_le text not null, expire_le text not null,
    utilise_le text default '', cree_par text default '');
create table if not exists bulletins (
    id text primary key, decision text not null, theme text not null, compte text default '',
    email text not null, jeton text not null unique, scrutin text default 'groupe',
    cree_le text not null, vote_le text default '', valeur text default '');
create index if not exists invitations_projet on invitations (projet);
create index if not exists bulletins_decision on bulletins (decision);
"""


def initialiser() -> None:
    with connexion() as base:
        base.executescript(SCHEMA)


def _ligne(table: str, cle: str, valeur: str) -> dict | None:
    with connexion() as base:
        ligne = base.execute(f"select * from {table} where {cle} = ?", (valeur,)).fetchone()
    return dict(ligne) if ligne else None


# ------------------------------------------------------------------ invitations
def creer_invitation(email: str, prenom: str, projet: str, role: str,
                     note: str = "", qui: str = "") -> dict:
    """Prépare une invitation (elle est envoyée par l'appelant, qui sait quelle adresse)."""
    adresse = (email or "").strip().lower()
    if "@" not in adresse or "." not in adresse.split("@")[-1]:
        raise ValueError("Indiquez une adresse de courriel valide.")
    moment = maintenant()
    invitation = {
        "id": _identifiant("iv"), "email": adresse, "prenom": (prenom or "").strip()[:40],
        "projet": projet, "role": role or "membre", "jeton": _identifiant("inv"),
        "note": (note or "").strip()[:200], "cree_le": _iso(moment),
        "expire_le": _iso(moment + timedelta(days=DUREE_JOURS)), "utilise_le": "",
        "cree_par": qui or "",
    }
    with connexion() as base:
        # Une invitation en attente pour la même adresse et le même projet est remplacée.
        base.execute("delete from invitations where email = ? and projet = ? and utilise_le = ''",
                     (adresse, projet))
        base.execute(
            "insert into invitations (id, email, prenom, projet, role, jeton, note, cree_le,"
            " expire_le, utilise_le, cree_par) values (:id, :email, :prenom, :projet, :role,"
            " :jeton, :note, :cree_le, :expire_le, :utilise_le, :cree_par)", invitation)
    return invitation


def lire_invitation(jeton: str) -> dict | None:
    return _ligne("invitations", "jeton", jeton)


def invitation_utilisable(invitation: dict | None) -> bool:
    if not invitation or invitation.get("utilise_le"):
        return False
    expire = invitation.get("expire_le") or ""
    return expire > _iso(maintenant())


def marquer_utilisee(jeton: str) -> None:
    with connexion() as base:
        base.execute("update invitations set utilise_le = ? where jeton = ?",
                     (_iso(maintenant()), jeton))


def lister_invitations(projet: str) -> list[dict]:
    with connexion() as base:
        lignes = base.execute(
            "select * from invitations where projet = ? order by cree_le desc", (projet,))
        return [dict(l) for l in lignes]


def courriel_invitation(invitation: dict, nom_projet: str) -> tuple[str, str]:
    """Le texte du courriel d'invitation (objet, corps)."""
    from . import equipe as m_equipe

    lien = f"{m_equipe.adresse_site()}/#invitation={invitation['jeton']}"
    sujet = f"[Synergie] Vous êtes invité(e) à rejoindre « {nom_projet} »"
    corps = (
        f"Bonjour,\n\n"
        f"Vous êtes invité(e) à rejoindre le projet « {nom_projet} » dans Synergie.\n\n"
        f"Pour activer votre accès, ouvrez ce lien :\n{lien}\n\n"
        "Vous y choisirez votre prénom et votre identifiant personnel. Ensuite, vous vous\n"
        "connecterez avec cet identifiant : gardez-le pour vous, il vous identifie.\n\n"
        f"Ce lien est personnel et valable {DUREE_JOURS} jours ; il ne sert qu'une fois.\n\n"
        "À bientôt sur Synergie.\n")
    return sujet, corps


# ------------------------------------------------------------------ bulletins de vote
def creer_bulletin(decision: str, theme: str, compte: str, email: str, scrutin: str) -> dict:
    """Un bulletin = un VOTE possible, envoyé à une adresse : une personne, une voix."""
    bulletin = {
        "id": _identifiant("bu"), "decision": decision, "theme": theme, "compte": compte,
        "email": (email or "").strip().lower(), "jeton": _identifiant("bul"),
        "scrutin": scrutin or "groupe", "cree_le": _iso(maintenant()), "vote_le": "",
        "valeur": "",
    }
    with connexion() as base:
        base.execute(
            "insert into bulletins (id, decision, theme, compte, email, jeton, scrutin,"
            " cree_le, vote_le, valeur) values (:id, :decision, :theme, :compte, :email,"
            " :jeton, :scrutin, :cree_le, :vote_le, :valeur)", bulletin)
    return bulletin


def lire_bulletin(jeton: str) -> dict | None:
    return _ligne("bulletins", "jeton", jeton)


def lister_bulletins(decision: str) -> list[dict]:
    with connexion() as base:
        lignes = base.execute("select * from bulletins where decision = ? order by cree_le",
                              (decision,))
        return [dict(l) for l in lignes]


def enregistrer_vote(jeton: str, valeur: str) -> dict:
    """Enregistre le vote d'un bulletin. Un bulletin ne sert QU'UNE fois."""
    bulletin = lire_bulletin(jeton)
    if not bulletin:
        raise ValueError("Ce lien de vote n'existe pas.")
    if bulletin["vote_le"]:
        raise ValueError("Ce vote a déjà été enregistré : une personne, une voix.")
    with connexion() as base:
        base.execute("update bulletins set vote_le = ?, valeur = ? where jeton = ?",
                     (_iso(maintenant()), valeur, jeton))
    return lire_bulletin(jeton) or bulletin


def courriel_vote(bulletin: dict, intitule: str, detail: str, nom_groupe: str,
                  scrutin: str) -> tuple[str, str]:
    from . import equipe as m_equipe

    lien = f"{m_equipe.adresse_site()}/#vote={bulletin['jeton']}"
    qui = ("les membres du groupe" if scrutin == "groupe"
           else "tous les membres du projet")
    sujet = f"[Synergie] Vote : {intitule[:70]}"
    corps = (
        f"Bonjour,\n\nUn vote est ouvert dans le groupe « {nom_groupe} » :\n\n"
        f"    {intitule}\n" + (f"\n{detail}\n" if detail else "") + "\n"
        f"Vous êtes invité(e) à voter comme {qui}.\n\n"
        f"Pour voter, ouvrez ce lien :\n{lien}\n\n"
        "Ce lien est personnel : il ne permet qu'UN seul vote, et les votes restent\n"
        "anonymes dans le dépouillement.\n\nÀ bientôt sur Synergie.\n")
    return sujet, corps
