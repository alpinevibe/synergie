#!/usr/bin/env python3
"""RÈGLES GÉNÉRIQUES DE TEMPS DE TRAVAIL (« boîte à trames »).

Ces règles sont l'EXTRACTION GÉNÉRIQUE des règles du moteur Hermes Planning : elles ne
parlent d'aucun métier en particulier (pas d'« IDE », d'« AS » ni d'« ASH ») et peuvent
donc servir à n'importe quel service pour un projet de réorganisation.

Toutes les valeurs sont surchargeables par projet (c.f. ``projet.regles``), ce qui permet
d'adapter Synergie à un autre service sans toucher au code.
"""
from __future__ import annotations

import copy

# --- Jeu de règles par défaut (règles génériques Hermes) ----------------------------
REGLES_DEFAUT: dict = {
    # Durée d'une journée de travail de référence (heures).
    "heures_jour": 7.5,

    # Un agent travaille 5 jours par semaine × sa quotité : c'est ce qui garantit
    # « heures travaillées ≥ heures légales » (règle dure du 21/09/2026).
    "jours_par_semaine_temps_plein": 5,
    "heures_legales_semaine": 35.0,

    # Repos hebdomadaires : plancher 2 RH/semaine, plafond 3 (+ fériés), le 3e RH étant
    # le repos compensateur d'un week-end travaillé (au plus un par quinzaine).
    "rh_min_semaine": 2,
    "rh_max_semaine": 3,
    "rh_max_quinzaine": 5,

    # Temps partiel : une quotité < 100 % se traduit par des jours « DS » (jour hors
    # quotité) — à 80 %, exactement 1 DS par semaine (règle dure du 21/09/2026).
    "ds_par_semaine_temps_partiel": 1,

    # Week-ends : un week-end sur deux travaillé, réparti entre TOUTES les lignes.
    "weekend_un_sur_deux": True,
    "one_weekend_per_line_by_quinzaine": 1,

    # Jours hors travail facultatifs posés dans une trame (jamais d'office).
    "rtt_max_par_ligne": 2,
    "fej_max_par_ligne": 1,
    "fej_seuil_semaines": 10,

    # Les NUITS TOURNANTES n'apparaissent JAMAIS dans une trame : seul le cycle fixe
    # des agents de nuit (14 jours) figure, le cas échéant.
    "nuits_tournantes_dans_trame": False,
    "cycle_nuit_fixe_jours": 14,

    # Codes de repos (tout le reste est un jour travaillé ou une absence).
    "codes_repos": ["RH", "DS"],

    # Familles de codes usuels (libellés génériques, surchargeables par projet).
    "codes_absence": [
        "CA", "CAJ", "CA25", "FE", "FEJ", "FE25", "RTT", "CEP", "JR", "JF",
        "MAT", "MAL", "AAJ", "FC", "HS",
    ],
    "codes_formation": ["J01", "J02", "J03", "J04", "J05", "J13", "MT3", "FCM", "FCS"],

    # Heures comptées par code (un jour travaillé vaut « heures_jour », une nuit vaut
    # 10 h par défaut, une absence ou un repos vaut 0 h).
    "heures_par_code": {"N": 10.0, "N02": 10.0},

    # Pondération des avis (souhaits) — « tous les avis comptent », mais certains pèsent
    # plus lourd : congés annuels > fériés > formation > récupération > poste souhaité.
    "poids_avis": {
        "CAJ": 3000, "CA": 3000, "CA25": 3000,
        "FEJ": 2000, "FE": 2000, "FE25": 2000,
        "FC": 1500, "FCM": 1500, "FCS": 1500,
        "RTT": 1000, "CEP": 1000, "JR": 1000,
        "poste": 1000,
        "repos": 1000,
    },

    # Un avis ne doit JAMAIS dégrader la couverture du service : la pénalité de
    # sous-couverture est supérieure à la somme des poids d'avis.
    "poids_sous_couverture": 10000,

    # Repli de la couverture : le déficit n'empêche jamais la production d'une trame,
    # il se matérialise par une ligne de suppléance (SSP).
    "code_suppleance": "SSP",
}

# --- Aides -------------------------------------------------------------------------
def regles_projet(regles_projet: dict | None) -> dict:
    """Retourne les règles effectives = défaut, écrasées par les surcharges du projet."""
    r = copy.deepcopy(REGLES_DEFAUT)
    for cle, valeur in (regles_projet or {}).items():
        if isinstance(valeur, dict) and isinstance(r.get(cle), dict):
            r[cle].update(valeur)
        else:
            r[cle] = copy.deepcopy(valeur)
    return r


def heures_code(code: str, regles: dict) -> float:
    """Heures de travail comptées par un code (0 pour un repos ou une absence)."""
    if code is None:
        return 0.0
    code = str(code).strip().upper()
    if code in regles.get("codes_repos", []):
        return 0.0
    if code in regles.get("codes_absence", []) or code in regles.get("codes_formation", []):
        return 0.0
    special = regles.get("heures_par_code", {})
    if code in special:
        return float(special[code])
    return float(regles.get("heures_jour", 7.5))


def heures_legales(quotite: float, nb_semaines: int, regles: dict) -> float:
    """Obligation légale sur la période : 35 h × quotité × nombre de semaines."""
    return float(regles.get("heures_legales_semaine", 35.0)) * float(quotite) * int(nb_semaines)


def jours_travailles_semaine(quotite: float, regles: dict) -> int:
    """Nombre de jours travaillés visés dans une semaine (5 × quotité, arrondi)."""
    brut = float(regles.get("jours_par_semaine_temps_plein", 5)) * float(quotite)
    return max(1, int(round(brut)))


def ds_par_semaine(quotite: float, regles: dict) -> int:
    """Jours « DS » (hors quotité) par semaine pour un temps partiel."""
    if float(quotite) >= 0.999:
        return 0
    return int(regles.get("ds_par_semaine_temps_partiel", 1))


def poids_avis(code_souhaite: str, regles: dict) -> int:
    """Poids d'un avis selon le code souhaité (« tous les avis comptent »)."""
    if not code_souhaite:
        return 0
    code = str(code_souhaite).strip().upper()
    table = regles.get("poids_avis", {})
    if code in table:
        return int(table[code])
    if code in regles.get("codes_repos", []):
        return int(table.get("repos", 1000))
    return int(table.get("poste", 1000))
