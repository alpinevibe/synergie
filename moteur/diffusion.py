#!/usr/bin/env python3
"""SYNERGIE — la diffusion temps réel entre processus.

Chaque navigateur connecté reçoit les événements par une file en mémoire
(`moteur/atelier.py`) : cela suffit tant qu'un seul processus sert l'application. Dès
qu'il y en a plusieurs — « waitress » avec plusieurs ouvriers, ou plusieurs machines —
un navigateur attaché à l'ouvrier A ne verrait plus ce qui se passe chez l'ouvrier B.

`publier` fait donc deux choses : la diffusion locale (comme avant) **et** un `NOTIFY`
PostgreSQL. Chaque processus écoute le canal et rediffuse chez lui ce que les autres
ont publié — les navigateurs, eux, ne changent pas : ils restent en Server-Sent Events
sur leur propre serveur. Aucun courtier à administrer, rien de plus à sauvegarder :
PostgreSQL est déjà là.

Deux précautions :

  • l'émetteur ne se réentend pas : chaque processus porte un identifiant (`base.PROCESSUS`) ;
  • un `NOTIFY` porte au plus 8 000 octets. Un événement trop gros part en version courte
    « rafraîchir », et le navigateur redemande l'état du groupe : mieux vaut une requête
    de plus qu'un message perdu.
"""
from __future__ import annotations

import json
import sys
import threading
import time

from . import base

#: Le canal d'écoute, et la taille au-delà de laquelle on prévient sans le contenu.
CANAL = "synergie"
LIMITE = 7000

_demarre = False
_verrou = threading.Lock()


def publier(theme: str, evenement: dict) -> None:
    """Prévient les autres processus qu'un événement vient d'être diffusé."""
    if not base.est_postgres():
        return
    charge = {"origine": base.PROCESSUS, "theme": theme, "evenement": evenement}
    texte = json.dumps(charge, ensure_ascii=False)
    if len(texte.encode("utf-8")) > LIMITE:
        charge["evenement"] = {"type": "rafraichir"}
        texte = json.dumps(charge, ensure_ascii=False)
    try:
        with base.connexion() as connexion:
            connexion.execute("select pg_notify(?, ?)", (CANAL, texte))
    except Exception as erreur:  # noqa: BLE001 - la diffusion locale a déjà eu lieu
        print(f"diffusion : notification impossible ({erreur})", file=sys.stderr, flush=True)


def _ecouter(diffuser_local) -> None:
    """Écoute le canal ; rediffuse chez nous ce que publient les autres processus."""
    import psycopg

    while True:
        try:
            # Une connexion bien à elle : elle reste ouverte des jours, elle n'est pas
            # rendue au pool entre deux notifications.
            with psycopg.connect(base.source(), autocommit=True) as connexion:
                connexion.execute(f"listen {CANAL}")
                print(f"diffusion : à l'écoute du canal « {CANAL} »", file=sys.stderr, flush=True)
                for notification in connexion.notifies():
                    try:
                        charge = json.loads(notification.payload)
                    except ValueError:
                        continue
                    if charge.get("origine") == base.PROCESSUS:
                        continue  # c'est nous qui l'avons publié : déjà diffusé sur place
                    diffuser_local(charge.get("theme") or "", charge.get("evenement") or {})
        except Exception as erreur:  # noqa: BLE001 - PostgreSQL indisponible : on retente
            print(f"diffusion : écoute interrompue ({erreur}), nouvelle tentative dans 2 s",
                  file=sys.stderr, flush=True)
            time.sleep(2)


def demarrer(diffuser_local) -> bool:
    """Lance l'écoute du canal, une seule fois par processus. Vrai si l'écoute tourne."""
    global _demarre
    if not base.est_postgres():
        return False
    with _verrou:
        if _demarre:
            return True
        threading.Thread(target=_ecouter, args=(diffuser_local,),
                         name="diffusion", daemon=True).start()
        _demarre = True
    return True
