#!/usr/bin/env python3
"""Plusieurs personnes écrivent en même temps : aucune écriture n'est perdue.

C'est la raison d'être de la bascule vers PostgreSQL (10/10/2026) : un atelier
collaboratif réunit une trentaine de personnes d'abord, plusieurs centaines ensuite,
et plusieurs navigateurs écrivent au même instant (notes déplacées, messages, votes).

Ce banc écrit **en parallèle** depuis plusieurs fils, puis recompte :

    SYNERGIE_BASE=postgresql:///synergie_essai python3 tests/tester_ecritures_simultanees.py

Sur SQLite, l'essai dit simplement qu'il est sans objet (un seul écrivain à la fois) :
il sort en 0. Tout ce que l'essai crée, il l'efface.
"""
from __future__ import annotations

import os
import sys
import threading

RACINE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, RACINE)

from moteur import atelier, equipe, projets  # noqa: E402

ECRIVAINS = 24
NOTES_PAR_ECRIVAIN = 3


def principal() -> int:
    if "postgres" not in os.environ.get("SYNERGIE_BASE", ""):
        print("essai sans objet : les écritures simultanées supposent PostgreSQL "
              "(SYNERGIE_BASE=postgresql:///synergie_essai)")
        return 0

    compte = equipe.creer_compte("Essai simultané")["compte"]
    projet = projets.creer_projet("Projet essai simultané", "banc d'écritures parallèles",
                                  auteur="Tests", admin=compte["id"], qui="Tests")
    groupe = atelier.creer_theme("Groupe essai simultané", "", projet=projet["id"],
                                 auteur="Tests")
    identifiant = groupe["id"]
    print(f"— {ECRIVAINS} écrivains en parallèle, {NOTES_PAR_ECRIVAIN} notes chacun —")

    erreurs: list[str] = []
    rendu: list[int] = []

    def ecrire(rang: int) -> None:
        try:
            for numero in range(NOTES_PAR_ECRIVAIN):
                atelier.creer_note(identifiant, {"texte": f"note {rang}-{numero}",
                                                 "auteur": f"Ecri vain {rang}"})
            rendu.append(rang)
        except Exception as erreur:  # noqa: BLE001 - on veut voir laquelle
            erreurs.append(f"écrivain {rang} : {erreur}")

    fils = [threading.Thread(target=ecrire, args=(rang,)) for rang in range(ECRIVAINS)]
    for fil in fils:
        fil.start()
    for fil in fils:
        fil.join(timeout=120)
    attendu = ECRIVAINS * NOTES_PAR_ECRIVAIN
    notes = atelier.lister_notes(identifiant)
    journal = [l for l in atelier.lister_journal(identifiant, 500)]

    print(f"  écrivains arrivés au bout : {len(rendu)}/{ECRIVAINS}")
    print(f"  notes écrites             : {len(notes)} (attendu {attendu})")
    print(f"  erreurs                   : {erreurs or 'aucune'}")

    # Ménage : l'essai ne laisse rien derrière lui.
    try:
        atelier.supprimer_theme(identifiant)
        projets.supprimer_projet(projet["id"])
        with atelier.connexion() as connexion:
            connexion.execute("delete from comptes where id = ?", (compte["id"],))
    except Exception as erreur:  # noqa: BLE001 - le ménage ne masque pas le résultat
        print(f"  (ménage incomplet : {erreur})")

    echecs = []
    if len(rendu) != ECRIVAINS:
        echecs.append(f"{ECRIVAINS - len(rendu)} écrivain(s) n'ont pas abouti")
    if len(notes) != attendu:
        echecs.append(f"{len(notes)} notes au lieu de {attendu} : des écritures ont été perdues")
    if erreurs:
        echecs.append("des écrivains ont échoué")
    if echecs:
        print("\nÉCHEC : " + " ; ".join(echecs))
        return 1
    print(f"\nCONFORME : {attendu} écritures simultanées, aucune perdue, aucune erreur.")
    return 0


if __name__ == "__main__":
    sys.exit(principal())
