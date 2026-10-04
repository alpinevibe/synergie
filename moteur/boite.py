#!/usr/bin/env python3
"""LA BOÎTE À TRAMES — catalogue réutilisable de trames, et pont vers Hermes Planning.

Deux usages :

1. **Catalogue** : toute trame produite est rangée dans ``donnees/boite/<code>.json`` et
   devient réutilisable par n'importe quel projet. Comme « mêmes critères de temps de
   travail = même trame = même code », deux services différents qui emploient le même
   profil (quotité, nuit) partagent la même trame.

2. **Pont Hermes** : Hermes Planning possède un générateur de grilles de rotation éprouvé
   (``engine_rotation.py``). Synergie sait l'appeler pour importer ses trames dans la
   boîte — le générateur de trames d'Hermes est ainsi réellement utilisé, tout en
   laissant Synergie autonome pour les services qui lui sont propres.
"""
from __future__ import annotations

import json
import os
import subprocess

RACINE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DOSSIER_BOITE = os.path.join(RACINE, "donnees", "boite")
HERMES = os.path.expanduser("~/hermes-planning")


# ------------------------------------------------------------------------------------
# Catalogue
# ------------------------------------------------------------------------------------
def lister() -> list[dict]:
    os.makedirs(DOSSIER_BOITE, exist_ok=True)
    trames = []
    for nom in sorted(os.listdir(DOSSIER_BOITE)):
        if nom.endswith(".json"):
            try:
                with open(os.path.join(DOSSIER_BOITE, nom), encoding="utf-8") as f:
                    trames.append(json.load(f))
            except Exception:                                      # pragma: no cover
                continue
    return trames


def ranger(trame: dict, origine: str = "Synergie", projet: str | None = None) -> dict:
    """Range une trame dans la boîte (une trame = un code ; on n'écrase pas)."""
    os.makedirs(DOSSIER_BOITE, exist_ok=True)
    entree = dict(trame)
    entree.setdefault("origine", origine)
    if projet:
        entree.setdefault("projets", [])
        if projet not in entree["projets"]:
            entree["projets"].append(projet)
    chemin = os.path.join(DOSSIER_BOITE, f"{entree['code_trame']}.json")
    with open(chemin, "w", encoding="utf-8") as f:
        json.dump(entree, f, ensure_ascii=False, indent=2)
    return entree


def ranger_generation(generation: dict, projet: str | None = None) -> list[dict]:
    return [ranger(t, origine="Synergie", projet=projet) for t in generation.get("trames", [])]


def chercher(code: str) -> dict | None:
    chemin = os.path.join(DOSSIER_BOITE, f"{code}.json")
    if os.path.exists(chemin):
        with open(chemin, encoding="utf-8") as f:
            return json.load(f)
    return None


# ------------------------------------------------------------------------------------
# Pont Hermes Planning (le générateur de trames y est déjà éprouvé)
# ------------------------------------------------------------------------------------
def hermes_disponible() -> bool:
    return os.path.isfile(os.path.join(HERMES, "engine_rotation.py")) and \
        os.path.isfile(os.path.join(HERMES, "venv", "bin", "python"))


_PONT = r"""
import json, sys
sys.path.insert(0, sys.argv[1])
import engine_rotation as er
sortie = {}
for pop in sys.argv[2].split(","):
    try:
        g = er.generer_grille_rotation(pop, int(sys.argv[3]) if len(sys.argv) > 3 else None)
        sortie[pop] = {"etat": g.get("etat"), "profils": [
            {"cle": p.get("cle"), "libelle": p.get("libelle"), "quotite": p.get("quotite"),
             "effectif": p.get("effectif"), "periode": p.get("periode"),
             "code": p.get("code"), "fixe": p.get("fixe"), "trame": p.get("trame")}
            for p in g.get("profils", [])]}
    except Exception as e:
        sortie[pop] = {"erreur": str(e)}
print(json.dumps(sortie, ensure_ascii=False))
"""


def importer_hermes(populations=("IDE HTC", "AS HTC", "ASH"), semaines: int | None = None) -> dict:
    """Importe les trames du générateur de grilles d'Hermes Planning dans la boîte."""
    if not hermes_disponible():
        return {"ok": False, "raison": "Hermes Planning introuvable"}
    python = os.path.join(HERMES, "venv", "bin", "python")
    cmd = [python, "-c", _PONT, HERMES, ",".join(populations)]
    if semaines:
        cmd.append(str(semaines))
    proc = subprocess.run(cmd, capture_output=True, text=True, timeout=900)
    if proc.returncode != 0:
        return {"ok": False, "raison": (proc.stderr or "échec du générateur Hermes").strip()[-500:]}
    donnees = json.loads(proc.stdout.strip().splitlines()[-1])
    rangees = []
    for pop, bloc in donnees.items():
        if "erreur" in bloc:
            continue
        for profil in bloc.get("profils", []):
            trame = profil.get("trame") or []
            if not trame:
                continue
            rangees.append(ranger({
                "code_trame": profil.get("code"),
                "metier": pop,
                "metier_libelle": pop,
                "quotite": profil.get("quotite"),
                "libelle": profil.get("libelle"),
                "nuit_fixe": bool(profil.get("fixe")),
                "effectif": profil.get("effectif"),
                "periode": profil.get("periode"),
                "semaines": trame,
                "couverture": {},
                "heures": {},
                "ecarts": [],
                "statut": "HERMES",
                "origine": "Hermes Planning",
            }, origine="Hermes Planning"))
    return {"ok": True, "importees": len(rangees),
            "codes": [t["code_trame"] for t in rangees]}
