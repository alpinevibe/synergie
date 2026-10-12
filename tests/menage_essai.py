#!/usr/bin/env python3
"""Synergie — effacer les comptes d'un essai, DANS LA VRAIE BASE DU SERVICE.

Le banc de contrôle tourne avec son propre interpréteur (celui qui porte `playwright`),
lequel ne sait pas toujours parler à PostgreSQL : les ménages écrits à même le moteur
effaçaient donc une base SQLite vide, et **chaque essai laissait ses comptes derrière lui**
(constat du 12/10/2026 : plus de trente comptes « Essai … » s'étaient accumulés en production,
jusqu'à empêcher un contrôle de repasser).

Ici, l'adresse de la base est lue dans l'unité systemd du service (ou dans `SYNERGIE_BASE`), et
l'effacement est confié à l'interpréteur de l'application — le seul qui ait le pilote.
"""
from __future__ import annotations

import os
import subprocess
import sys

RACINE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
UNITE_SERVICE = "/etc/systemd/system/synergie.service"

_CODE = (
    "import sys\n"
    "from moteur import atelier\n"
    "with atelier.connexion() as base:\n"
    "    for identifiant in sys.argv[1:]:\n"
    "        for table in ('projet_membres', 'theme_membres', 'abonnements',\n"
    "                      'responsables'):\n"
    "            base.execute(f'delete from {table} where compte = ?', (identifiant,))\n"
    "        base.execute('delete from comptes where id = ?', (identifiant,))\n"
)


def base_de_donnees() -> str:
    """L'adresse de la base, telle que le service l'utilise."""
    if os.environ.get("SYNERGIE_BASE"):
        return os.environ["SYNERGIE_BASE"]
    try:
        with open(UNITE_SERVICE, encoding="utf-8") as unite:
            for ligne in unite:
                ligne = ligne.strip()
                if ligne.startswith("Environment=SYNERGIE_BASE="):
                    return ligne.split("=", 2)[2].strip()
    except OSError:
        pass
    return ""


def effacer_comptes(identifiants) -> None:
    """Efface les comptes donnés (et leurs places dans les projets et les groupes)."""
    identifiants = [i for i in identifiants if i]
    if not identifiants:
        return
    python = os.environ.get("SYNERGIE_PYTHON", "/home/ubuntu/synergie-venv/bin/python")
    environnement = dict(os.environ, PYTHONPATH=RACINE)
    base = base_de_donnees()
    if base:
        environnement["SYNERGIE_BASE"] = base
    for interpreteur in (python, sys.executable):
        try:
            fait = subprocess.run([interpreteur, "-c", _CODE, *identifiants],
                                  cwd=RACINE, env=environnement, capture_output=True,
                                  text=True, timeout=60)
        except OSError:
            continue
        if fait.returncode == 0:
            return
        print(f"  (ménage impossible avec {interpreteur} : "
              f"{(fait.stderr or '').strip().splitlines()[-1:]} )")
