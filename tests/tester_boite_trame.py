#!/usr/bin/env python3
"""TESTS DE L'OUTIL « BOÎTE À TRAMES » ET DU VÉRIFICATEUR DE RÉGLEMENTATION.

Lancement :  /home/ubuntu/synergie-venv/bin/python tests/tester_boite_trame.py

Ces tests vérifient, sans serveur ni interface :
  1. le calcul des heures hebdomadaires et des ETP sur un exemple calculé à la main ;
  2. qu'une trame générée couvre EXACTEMENT les besoins de chaque poste chaque jour ;
  3. que le vérificateur DÉTECTE un cas non conforme fabriqué à la main (deux postes
     enchaînés avec moins de 11 h de repos) et ne signale RIEN sur un cas conforme ;
  4. que les personnes fixes de nuit ne se voient JAMAIS attribuer un poste de jour.
"""
from __future__ import annotations

import os
import sys

RACINE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if RACINE not in sys.path:
    sys.path.insert(0, RACINE)

from moteur import boite_trame as bt          # noqa: E402
from moteur import reglementation as reg      # noqa: E402


# ====================================================================================
# 1. Calcul des heures et des ETP (exemple vérifiable à la main)
# ====================================================================================
def test_heures_et_etp():
    """Exemple calculé à la main :

    Postes décrits :
      * Matin (07:00-14:00 = 7 h), 3 personnes, 5 jours/semaine -> 3 × 7 × 5   = 105 h
      * Après-midi (14:00-21:00 = 7 h), 2 personnes, 5 jours/semaine -> 2 × 7 × 5 = 70 h
      * Nuit (21:00-07:00 = 10 h), 1 personne, 7 jours/semaine -> 1 × 10 × 7   =  70 h
    Total des heures hebdomadaires nécessaires                        = 245 h

    ETP nécessaires = 245 / 35 × (1 + 0,10) = 7 × 1,10 = 7,70
    ETP disponibles = 10 personnes à 100 %            = 10,00
    Écart           = 10,00 − 7,70 = 2,30 (il reste 2,3 ETP)
    """
    description = {
        "profession": "IDE",
        "effectif": {"temps_plein": 10, "partiel_80": 0,
                     "fixes_nuit": 0, "dispensees_nuit": 0},
        "postes": [
            {"libelle": "Matin", "debut": "07:00", "fin": "14:00",
             "personnes": 3, "jours": [1, 1, 1, 1, 1, 0, 0]},
            {"libelle": "Après-midi", "debut": "14:00", "fin": "21:00",
             "personnes": 2, "jours": [1, 1, 1, 1, 1, 0, 0]},
            {"libelle": "Nuit", "debut": "21:00", "fin": "07:00",
             "personnes": 1, "jours": [1, 1, 1, 1, 1, 1, 1]},
        ],
        "reglages": {"heures_legales_semaine": 35,
                     "coefficient_remplacement": 0.10,
                     "cycle_semaines": 4,
                     "jours_temps_plein": 5, "jours_80": 4},
    }
    analyse = bt.analyser(description)

    assert abs(analyse["heures_semaine_necessaires"] - 245.0) < 1e-6, \
        f"heures attendues 245, obtenu {analyse['heures_semaine_necessaires']}"
    assert abs(analyse["etp_necessaires"] - 7.70) < 1e-6, \
        f"ETP nécessaires attendus 7,70, obtenu {analyse['etp_necessaires']}"
    assert abs(analyse["etp_disponibles"] - 10.0) < 1e-6, \
        f"ETP disponibles attendus 10, obtenu {analyse['etp_disponibles']}"
    assert abs(analyse["comparaison"]["ecart"] - 2.30) < 1e-6, \
        f"écart attendu 2,30, obtenu {analyse['comparaison']['ecart']}"
    assert analyse["comparaison"]["etat"] == "surplus"
    assert analyse["couverture_nuit"]["necessaires"] == 1


# ====================================================================================
# 2. La trame générée couvre exactement les besoins de chaque poste chaque jour
# ====================================================================================
def _exemple_equilibre():
    """Service où environ 10 postes de jour et 7 nuits sont à couvrir chaque semaine."""
    return {
        "profession": "AS",
        "effectif": {"temps_plein": 2, "partiel_80": 0,
                     "fixes_nuit": 2, "dispensees_nuit": 0},
        "postes": [
            {"libelle": "Matin", "debut": "07:00", "fin": "14:00",
             "personnes": 1, "jours": [1, 1, 1, 1, 1, 0, 0]},
            {"libelle": "Après-midi", "debut": "14:00", "fin": "21:00",
             "personnes": 1, "jours": [1, 1, 1, 1, 1, 0, 0]},
            {"libelle": "Nuit", "debut": "21:00", "fin": "07:00",
             "personnes": 1, "jours": [1, 1, 1, 1, 1, 1, 1]},
        ],
        "reglages": {"heures_legales_semaine": 35,
                     "coefficient_remplacement": 0.10,
                     "cycle_semaines": 2,
                     "jours_temps_plein": 5, "jours_80": 4},
    }


def test_couverture_exacte():
    description = _exemple_equilibre()
    generation = bt.generer(description, max_trames=1, duree_max_s=8.0)
    assert generation["nb_trames"] >= 1, "aucune trame n'a été produite"
    trame = generation["trames"][0]
    semaines = trame["semaines"]
    agents = trame["agents"]

    for poste in description["postes"]:
        libelle = poste["libelle"]
        for wd in range(7):
            cible = poste["personnes"] if poste["jours"][wd] else 0
            for w in range(semaines):
                t = w * 7 + wd
                presents = sum(1 for a in agents if a["jours"][t] == libelle)
                assert presents == cible, (
                    f"{libelle} {reg.JOURS_COURTS[wd]} semaine {w + 1} : "
                    f"{presents} présent(s), attendu {cible}")


# ====================================================================================
# 3. Le vérificateur détecte un cas non conforme, et valide un cas conforme
# ====================================================================================
def test_verificateur_detecte_repos_insuffisant():
    """Deux postes enchaînés avec moins de 11 h de repos : Nuit (21:00-07:00) puis
    Matin (07:00-14:00) le lendemain -> repos nul, donc non conforme."""
    trame = {
        "semaines": 2,
        "postes": [
            {"libelle": "Matin", "debut": "07:00", "fin": "14:00"},
            {"libelle": "Nuit", "debut": "21:00", "fin": "07:00"},
        ],
        "agents": [{
            "nom": "Personne 1", "profil": "100 %", "quotite": 1.0,
            # Nuit le lundi, Matin le mardi -> repos insuffisant
            "jours": ["Nuit", "Matin", "Repos", "Repos", "Repos", "Repos", "Repos",
                      "Repos", "Repos", "Repos", "Repos", "Repos", "Repos", "Repos"],
        }],
    }
    verdict = reg.verifier_trame(trame)
    assert verdict["conforme"] is False, "le vérificateur aurait dû refuser cette trame"
    regles = [m["regle"] for m in verdict["manquements"]]
    assert any("repos quotidien" in r for r in regles), \
        f"manquement « repos quotidien » attendu, obtenu {regles}"


def test_verificateur_valide_trame_conforme():
    """Une trame simple et conforme : 5 matins de 7 h par semaine, week-end reposé.

    5 × 7 h = 35 h (durée hebdomadaire moyenne respectée), 2 jours de repos par semaine,
    amplitudes de 7 h, aucun enchaînement trop serré, aucun dimanche travaillé.
    """
    semaine = ["Matin"] * 5 + ["Repos", "Repos"]
    trame = {
        "semaines": 2,
        "postes": [{"libelle": "Matin", "debut": "07:00", "fin": "14:00"}],
        "agents": [{
            "nom": "Personne 1", "profil": "100 %", "quotite": 1.0,
            "jours": semaine + semaine,
        }],
    }
    verdict = reg.verifier_trame(trame)
    assert verdict["conforme"] is True, \
        f"trame jugée non conforme à tort : {verdict['manquements']}"
    assert verdict["manquements"] == []
    assert verdict["compteurs"]["par_personne"][0]["heures_semaine"] == 35.0


# ====================================================================================
# 4. Les personnes fixes de nuit ne prennent jamais un poste de jour
# ====================================================================================
def test_fixes_de_nuit_jamais_de_jour():
    generation = bt.generer(_exemple_equilibre(), max_trames=1, duree_max_s=8.0)
    trame = generation["trames"][0]
    postes_de_nuit = {p["libelle"] for p in trame["postes"]
                      if reg.est_poste_nuit(p)}
    postes_de_jour = {p["libelle"] for p in trame["postes"]} - postes_de_nuit
    assert postes_de_jour, "le test a besoin d'au moins un poste de jour"

    verifiers = 0
    for agent in trame["agents"]:
        if "nuit" not in agent["profil"].lower():
            continue
        verifiers += 1
        for libelle in agent["jours"]:
            if libelle == reg.LIBELLES_REPOS or libelle == "Repos":
                continue
            assert libelle in postes_de_nuit, (
                f"{agent['nom']} (fixe de nuit) a reçu le poste de jour « {libelle} »")
    assert verifiers > 0, "aucune personne fixe de nuit dans la trame générée"


# ====================================================================================
# Exécution
# ====================================================================================
# ====================================================================================
# 5. Amplitude de 12 h et horaires VARIÉS (7 h 30 et 12 h mêlés)
# ====================================================================================
def _exemple_horaires_varies():
    """Service mêlant des journées de 7 h 30 et des journées de 12 h, de jour comme de
    nuit : c'est le cas que l'utilisateur veut pouvoir tester (05/10/2026)."""
    return {
        "profession": "IDE",
        "effectif": {"temps_plein": 6, "partiel_80": 0,
                     "fixes_nuit": 2, "dispensees_nuit": 0},
        "postes": [
            {"libelle": "Matin 7h30", "debut": "06:30", "fin": "14:00",
             "personnes": 2, "jours": [1, 1, 1, 1, 1, 1, 1]},
            {"libelle": "Journée 12h", "debut": "07:30", "fin": "19:30",
             "personnes": 1, "jours": [1, 1, 1, 1, 1, 1, 1]},
            {"libelle": "Nuit 12h", "debut": "19:30", "fin": "07:30",
             "personnes": 1, "jours": [1, 1, 1, 1, 1, 1, 1]},
        ],
        "reglages": {"heures_legales_semaine": 35, "coefficient_remplacement": 0.10,
                     "cycle_semaines": 2},
    }


def test_amplitude_12h_acceptee():
    """Une journée de 12 h est possible (dérogation signalée), une journée de 13 h non."""
    description = _exemple_horaires_varies()
    postes = {p["libelle"]: p for p in bt.normaliser(description)["postes"]}
    assert postes["Journée 12h"]["duree"] == 12.0
    assert postes["Journée 12h"]["code"] == "J13", "une journée longue doit être codée J13"
    assert postes["Matin 7h30"]["code"] == "M03", "un matin doit être codé M03"
    assert postes["Nuit 12h"]["code"] == "N02", "une nuit doit être codée N02"
    assert postes["Matin 7h30"]["couleur_fond"] == "#ffff99", "couleur du matin (Hermes)"
    assert postes["Nuit 12h"]["couleur_fond"] == "#800080", "couleur de la nuit (Hermes)"

    trame = {"semaines": 1,
             "postes": [{"libelle": "Journée 12h", "debut": "07:30", "fin": "19:30"}],
             "agents": [
                 {"nom": "A", "quotite": 1.0,
                  "jours": ["Journée 12h"] + ["Repos"] * 6}]}
    verdict = reg.verifier_trame(trame)
    assert verdict["conforme"], "12 h ne doit pas être un manquement"
    assert any("dérogation" in i["regle"] for i in verdict["informations"]), \
        "au-delà de 10 h, la dérogation doit être signalée"

    trame["postes"] = [{"libelle": "Journée 13h", "debut": "07:00", "fin": "20:00"}]
    trame["agents"][0]["jours"] = ["Journée 13h"] + ["Repos"] * 6
    verdict = reg.verifier_trame(trame)
    assert not verdict["conforme"], "13 h doit être refusé (au-delà de 12 h)"


def test_horaires_varies_couverture_et_conformite():
    """Avec des 7 h 30 et des 12 h mêlés, la trame couvre exactement et reste conforme."""
    description = _exemple_horaires_varies()
    generation = bt.generer(description, max_trames=1, duree_max_s=25.0)
    assert generation["nb_trames"] >= 1, "aucune trame produite avec des horaires variés"
    trame = generation["trames"][0]
    assert trame["verdict"]["conforme"], \
        f"trame non conforme : {trame['verdict']['manquements'][:3]}"
    for poste in description["postes"]:
        for wd in range(7):
            cible = poste["personnes"]
            for w in range(trame["semaines"]):
                presents = sum(1 for a in trame["agents"]
                               if a["jours"][w * 7 + wd] == poste["libelle"])
                assert presents == cible, (f"{poste['libelle']} jour {wd + 1} semaine "
                                           f"{w + 1} : {presents} au lieu de {cible}")
    # Les couleurs d'Hermes voyagent avec la trame, pour peindre la grille.
    assert trame["couleurs"]["Matin 7h30"]["code"] == "M03"
    assert trame["couleurs"]["Repos"]["fond"] == "#00ff00"


def principal():
    tests = [
        test_heures_et_etp,
        test_couverture_exacte,
        test_verificateur_detecte_repos_insuffisant,
        test_verificateur_valide_trame_conforme,
        test_fixes_de_nuit_jamais_de_jour,
        test_amplitude_12h_acceptee,
        test_horaires_varies_couverture_et_conformite,
    ]
    tout_ok = True
    for test in tests:
        try:
            test()
            print(f"OK    — {test.__name__}")
        except AssertionError as erreur:
            tout_ok = False
            print(f"ÉCHEC — {test.__name__} : {erreur}")
        except Exception as erreur:                      # pragma: no cover
            tout_ok = False
            print(f"ERREUR — {test.__name__} : {erreur!r}")
    print("TOUS LES TESTS SONT OK" if tout_ok else "CERTAINS TESTS ONT ÉCHOUÉ")
    return 0 if tout_ok else 1


if __name__ == "__main__":
    sys.exit(principal())
