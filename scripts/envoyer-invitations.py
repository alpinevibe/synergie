#!/usr/bin/env python3
"""Renvoyer par courriel les invitations en attente d'un projet (ou d'un seul groupe).

Pourquoi cet outil : quand les envois de Synergie ont été suspendus (réglage
`SYNERGIE_ENVOI=non` dans `/srv/bases/config/mail.conf`), les invitations créées pendant la
suspension ont gardé leur Lien personnel. Les rouvrir ne les envoie pas rétroactivement : ce
script les expédie — une par une — puis attend que la file d'envoi soit vide (sinon le message
partirait avec le processus).

    python3 scripts/envoyer-invitations.py <projet> [--groupe <groupe>]
    python3 scripts/envoyer-invitations.py --essai adresse@exemple.fr   (message d'essai)
"""
from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

RACINE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RACINE))

from moteur import atelier as m_atelier                       # noqa: E402
from moteur import equipe as m_equipe                         # noqa: E402
from moteur import invitations as m_invitations               # noqa: E402
from moteur import projets as m_projets                       # noqa: E402


def invitations_en_attente(projet: str, groupe: str = "") -> list[dict]:
    """Les invitations utilisables (ni utilisées, ni expirées) d'un projet ou d'un groupe."""
    if not projet:
        projet = os.environ.get("SYNERGIE_PROJET", "")
    liste = m_invitations.lister_invitations(projet)
    gardees = []
    for invitation in liste:
        if groupe and invitation.get("theme") != groupe:
            continue
        if not groupe and invitation.get("theme"):
            continue                              # les invitations de groupe ont leur envoi
        if invitation.get("utilise_le"):
            continue
        if m_invitations.invitation_utilisable(invitation):
            gardees.append(invitation)
    return gardees


def envoyer(projet: str, groupe: str = "", *,
            simulation: bool = False) -> tuple[int, list[str]]:
    """Met les invitations en attente dans la file d'envoi ; rend (nombre, adresses)."""
    invitations = invitations_en_attente(projet, groupe)
    if not invitations:
        return 0, []
    if not m_equipe.envoi_actif() and not simulation:
        print("Envois SUSPENDUS (SYNERGIE_ENVOI) : rien n'a été expédié.")
        return 0, [i["email"] for i in invitations]
    nom_projet = (m_projets.lire_projet(projet) or {}).get("nom") or "votre projet"
    for invitation in invitations:
        titre_groupe = ""
        if invitation.get("theme"):
            titre_groupe = (m_atelier.lire_theme(invitation["theme"]) or {}).get("titre") or ""
        print(f"  → {invitation['email']}"
              + (f" (groupe « {titre_groupe} »)" if titre_groupe else ""))
        if not simulation:
            m_invitations.envoyer_invitation(invitation, nom_projet, titre_groupe)
    return len(invitations), [i["email"] for i in invitations]


def principal() -> int:
    analyseur = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    analyseur.add_argument("projet", nargs="?", default="", help="identifiant du projet")
    analyseur.add_argument("--groupe", default="", help="n'envoyer que ce groupe")
    analyseur.add_argument("--essai", default="", help="envoyer un message d'essai à cette adresse")
    analyseur.add_argument("--simulation", action="store_true", help="montrer, sans envoyer")
    options = analyseur.parse_args()

    if options.essai:
        m_equipe.demarrer_le_facteur()
        reussi = m_equipe.test_alerte(options.essai)
        print(f"Message d'essai à {options.essai} : {'expédié' if reussi else 'ÉCHEC'}")
        return 0 if reussi else 1

    nombre, adresses = envoyer(options.projet, options.groupe, simulation=options.simulation)
    if options.simulation or not nombre:
        print(f"{nombre} invitation(s) en attente : {', '.join(adresses) or 'aucune'}")
        return 0
    m_equipe.demarrer_le_facteur()                 # le facteur expédie en arrière-plan
    m_equipe._FILE.join()                          # on attend que la file soit vide
    print(f"{nombre} invitation(s) expédiée(s) — voir {m_equipe.JOURNAL_MAIL}")
    return 0


if __name__ == "__main__":
    sys.exit(principal())
