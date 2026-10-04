#!/usr/bin/env python3
"""PROJETS de réorganisation — modèle, stockage, et aide à la couverture cible.

Un « projet » décrit un SERVICE à réorganiser. Il est volontairement GÉNÉRIQUE : rien
n'y est propre au soin. Un service de soins, un atelier, un service technique se
décrivent avec les mêmes champs.

    {
      "id": "hdj", "nom": "Hôpital de jour",
      "description": "...", "collectivite": "...",
      "date_debut": "2026-11-02", "duree_semaines": 6,
      "metiers": [
        {"code": "IDE", "libelle": "Infirmier(ère)",
         "postes": [{"code": "M", "libelle": "Journée", "heures": 7.5}],
         "cibles": {"Lun": {"M": 5}, ...}}
      ],
      "agents": [{"nom": "...", "metier": "IDE", "quotite": 1.0,
                  "nuit_fixe": false, "sans_nuit": false}],
      "avis":   [{"agent": "...", "jour": "2026-11-03", "souhait": "CAJ", "motif": "..."}],
      "regles": {...}                      # surcharges des règles génériques
    }
"""
from __future__ import annotations

import json
import os
import re

JOURS = ["Lun", "Mar", "Mer", "Jeu", "Ven", "Sam", "Dim"]
RACINE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DOSSIER_PROJETS = os.path.join(RACINE, "donnees", "projets")


# ------------------------------------------------------------------------------------
# Stockage
# ------------------------------------------------------------------------------------
def _slug(texte: str) -> str:
    s = re.sub(r"[^a-z0-9]+", "-", str(texte).lower()).strip("-")
    return s or "projet"


def lister() -> list[dict]:
    os.makedirs(DOSSIER_PROJETS, exist_ok=True)
    projets = []
    for nom in sorted(os.listdir(DOSSIER_PROJETS)):
        if nom.endswith(".json"):
            try:
                projets.append(charger(nom[:-5]))
            except Exception:                                      # pragma: no cover
                continue
    return projets


def charger(identifiant: str) -> dict:
    chemin = os.path.join(DOSSIER_PROJETS, f"{_slug(identifiant)}.json")
    with open(chemin, encoding="utf-8") as f:
        return json.load(f)


def enregistrer(projet: dict) -> dict:
    os.makedirs(DOSSIER_PROJETS, exist_ok=True)
    if not projet.get("id"):
        projet["id"] = _slug(projet.get("nom", "projet"))
    chemin = os.path.join(DOSSIER_PROJETS, f"{_slug(projet['id'])}.json")
    with open(chemin, "w", encoding="utf-8") as f:
        json.dump(projet, f, ensure_ascii=False, indent=2)
    return projet


def supprimer(identifiant: str) -> bool:
    chemin = os.path.join(DOSSIER_PROJETS, f"{_slug(identifiant)}.json")
    if os.path.exists(chemin):
        os.remove(chemin)
        return True
    return False


# ------------------------------------------------------------------------------------
# Normalisation
# ------------------------------------------------------------------------------------
def normaliser(projet: dict) -> dict:
    """Complète un projet : identifiants, cibles manquantes, métiers des agents."""
    projet = dict(projet or {})
    projet.setdefault("jours", JOURS)
    for metier in projet.get("metiers", []):
        metier.setdefault("libelle", metier.get("code", "?"))
        metier.setdefault("cibles", {})
        if not metier.get("codes_travail"):
            metier["codes_travail"] = [p["code"] for p in metier.get("postes", [])] or ["M"]
        for jour in JOURS:
            metier["cibles"].setdefault(jour, {})
    projet.setdefault("agents", [])
    projet.setdefault("avis", [])
    return projet


# ------------------------------------------------------------------------------------
# Aide à la couverture cible
# ------------------------------------------------------------------------------------
POIDS_JOUR = {"Lun": 1.0, "Mar": 1.0, "Mer": 1.0, "Jeu": 1.0, "Ven": 1.0,
              "Sam": 0.45, "Dim": 0.45}


def cibles_recommandees(metier: dict, agents: list[dict], regles: dict | None = None) -> dict:
    """Répartit la capacité de travail d'un métier en une couverture cible COHÉRENTE.

    Capacité hebdomadaire = Σ (5 × quotité) jours travaillés. On la répartit exactement
    (méthode du plus fort reste) : le week-end pèse moins (un agent ne travaille qu'un
    week-end sur deux), et samedi / dimanche reçoivent la MÊME cible (un week-end se
    travaille par paire). La cible totale ÉGALE donc la capacité : le moteur peut la tenir
    sans déficit. Sert de PROPOSITION : le service reste libre de sa cible.
    """
    metier_agents = [a for a in agents if a.get("metier") == metier["code"]]
    jours_plein = float((regles or {}).get("jours_par_semaine_temps_plein", 5))
    capacite = sum(jours_plein * float(a.get("quotite", 1.0)) for a in metier_agents)
    code = (metier.get("codes_travail") or ["M"])[0]
    total = int(round(capacite))
    if total <= 0:
        return {}

    # Répartition au plus juste sur les 7 jours (samedi/dimanche comptés ensemble)
    poids = [1.0, 1.0, 1.0, 1.0, 1.0, 0.9, 0.9]          # Sam+Dim = 1,8 (≈ 2 jours pour 2 semaines)
    somme = sum(poids)
    exact = [total * p / somme for p in poids]
    base = [int(x) for x in exact]
    reste = total - sum(base)
    for i in sorted(range(7), key=lambda i: exact[i] - base[i], reverse=True)[:reste]:
        base[i] += 1
    # samedi et dimanche à la même valeur (paire de week-end)
    we = int(round((base[5] + base[6]) / 2))
    # on retire au(x) jour(s) de semaine le plus chargé(s) ce que l'arrondi ajoute
    ajust = (we - base[5]) + (we - base[6])
    ordre = sorted(range(5), key=lambda i: -base[i])
    i = 0
    while ajust > 0 and base[ordre[i % 5]] > 0:
        base[ordre[i % 5]] -= 1
        ajust -= 1
        i += 1
    base[5] = base[6] = we

    cibles = {}
    for jour, n in zip(JOURS, base):
        cibles[jour] = {code: int(n)} if n > 0 else {}
    return cibles


def ajouter_agent(projet: dict, agent: dict) -> dict:
    projet.setdefault("agents", []).append(agent)
    return projet


# ------------------------------------------------------------------------------------
# Projet de démonstration (illustre la GÉNÉRICITÉ : rien de médical)
# ------------------------------------------------------------------------------------
def projet_demo() -> dict:
    """Un projet d'exemple : un service de soins ET un atelier de production."""
    agents_soins = (
        [{"nom": f"Agent IDE {i+1}", "metier": "IDE", "quotite": 1.0} for i in range(5)]
        + [{"nom": f"Agent IDE {i+1} (80 %)", "metier": "IDE", "quotite": 0.8} for i in range(2)]
        + [{"nom": f"Aide-soignant {i+1}", "metier": "AS", "quotite": 1.0} for i in range(4)]
    )
    projet = {
        "id": "demo-soins",
        "nom": "Service de soins — réorganisation",
        "description": "Exemple généré par Synergie : deux métiers, temps plein et 80 %.",
        "collectivite": "Exemple",
        "date_debut": "2026-11-02",
        "duree_semaines": 6,
        "metiers": [
            {"code": "IDE", "libelle": "Infirmier(ère)",
             "postes": [{"code": "M", "libelle": "Journée", "heures": 7.5}],
             "codes_travail": ["M"], "cibles": {}},
            {"code": "AS", "libelle": "Aide-soignant(e)",
             "postes": [{"code": "M", "libelle": "Journée", "heures": 7.5}],
             "codes_travail": ["M"], "cibles": {}},
        ],
        "agents": agents_soins,
        "avis": [
            {"agent": "Agent IDE 1", "jour": "2026-11-05", "souhait": "CAJ",
             "motif": "rendez-vous familial"},
            {"agent": "Aide-soignant 2", "jour": "2026-11-11", "souhait": "RTT"},
        ],
    }
    for metier in projet["metiers"]:
        metier["cibles"] = cibles_recommandees(metier, agents_soins)
    return normaliser(projet)
