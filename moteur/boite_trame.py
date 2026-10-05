#!/usr/bin/env python3
"""LA BOÎTE À TRAMES SIMPLE — calcul des besoins et génération des trames.

Deux fonctions publiques, qui correspondent aux deux routes de l'interface :

  * ``analyser(description)``  -> heures hebdomadaires, ETP nécessaires, ETP
    disponibles, comparaison, couverture de nuit.
  * ``generer(description)``   -> jusqu'à 3 trames, chacune étant un cycle de
    plusieurs semaines rejoué en boucle ; pour chaque personne, ses postes et ses
    repos, plus les compteurs et le verdict de conformité.

La génération utilise **OR-Tools CP-SAT**. Elle ne tient compte que des règles
**collectives** (couverture des postes, repos, nuits, quotité) : aucune règle
individuelle (récupération, congés, souhaits personnels) n'intervient.

Description attendue (le « corps » envoyé par la page) ::

    {
      "profession": "IDE",
      "effectif": {"temps_plein": 12, "partiel_80": 4,
                   "fixes_nuit": 3, "dispensees_nuit": 2},
      "postes": [ {"libelle": "Matin", "debut": "06:30", "fin": "14:30",
                   "personnes": 4, "jours": [1,1,1,1,1,0,0]}, ... ],
      "reglages": {"heures_legales_semaine": 35,
                   "coefficient_remplacement": 0.10,
                   "cycle_semaines": 4,
                   "jours_temps_plein": 5,
                   "jours_80": 4}
    }
"""
from __future__ import annotations

import math

from ortools.sat.python import cp_model

from .reglementation import (
    JOURS_COURTS,
    duree_poste,
    est_poste_nuit,
    minutes,
    verifier_trame,
)

JOURS = JOURS_COURTS
REPOS = "Repos"
MAX_TRAMES = 3
# Temps accordé au solveur par trame. Les configurations mêlant des journées de 7 h 30
# et de 12 h demandent plus de recherche qu'un horaire unique : sans cela, le
# solveur rend une première solution valable mais mal répartie (05/10/2026).
DUREE_SOLVEUR_S = 25.0
CYCLE_MIN, CYCLE_MAX = 2, 8

# Libellés des catégories de personnel (affichés tels quels, sans jargon).
PROFIL_TEMPS_PLEIN = "100 % (jour)"
PROFIL_QUATRE_VINGT = "80 % (jour)"
PROFIL_NUIT = "fixe de nuit"
PROFIL_DISPENSE = "dispensé de nuit"

# Réglages par défaut.
REGLAGES_DEFAUT = {
    "heures_legales_semaine": 35.0,       # heures légales hebdomadaires (Code du travail)
    "coefficient_remplacement": 0.10,     # marge pour les remplacements (FPH ~10 %)
    "cycle_semaines": 4,                  # durée du cycle proposé (2 à 6 en général)
    "jours_temps_plein": 5,               # jours travaillés par semaine à 100 %
    "jours_80": 4,                        # jours travaillés par semaine à 80 %
}

# Poids de l'objectif (recherche).
# Priorités (dans l'ordre) : couvrir chaque poste EXACTEMENT, puis approcher les heures
# légales de chacun, puis l'équité. Les écarts d'heures se comptent en MINUTES : 3 par
# minute représente 180 par heure, très en dessous de la mise en trop d'une personne, pour
# que la couverture reste exacte dans tous les cas.
_P_SOUS = 1_000_000       # ne jamais laisser un poste non couvert
_P_TROP = 20_000          # ne jamais mettre quelqu'un en trop
_P_HEURES_BAS = 3         # éviter de passer sous les heures légales
_P_HEURES_HAUT = 1        # limiter les heures au-delà (compensées en jours de réduction)
_P_EQUITE_HEURES = 2      # resserrer l'écart d'heures entre la personne qui travaille
                          # le plus et celle qui travaille le moins (par minute)
_P_EQUITE = 3             # répartir équitablement les week-ends travaillés
_P_EQUITE_TRAVAIL = 2     # répartir équitablement le nombre de jours travaillés
_P_PARTAGE = 25           # faire suivre la même trame au plus grand nombre


# ====================================================================================
# Normalisation de la description
# ====================================================================================
# --- Codes et couleurs des horaires, repris d'Hermes --------------------------------
# Ce sont EXACTEMENT les couleurs du planning d'Hermes : le matin est jaune, l'après-midi
# cyan, la nuit violet (texte blanc), une journée longue magenta, les repos verts, une
# journée sans affectation blanche. Le code d'un poste est déduit de son heure de début et
# de sa durée ; on peut le changer, la couleur suit le code choisi.
CODES_HERMES = {
    "M03": {"fond": "#ffff99", "texte": "#000000", "libelle": "Matin"},
    "S03": {"fond": "#00ffff", "texte": "#000000", "libelle": "Après-midi"},
    "J13": {"fond": "#ff00ff", "texte": "#000000", "libelle": "Journée longue"},
    "N02": {"fond": "#800080", "texte": "#ffffff", "libelle": "Nuit"},
    "RH":  {"fond": "#00ff00", "texte": "#000000", "libelle": "Repos hebdomadaire"},
    "DS":  {"fond": "#ffffff", "texte": "#000000", "libelle": "Disponibilité"},
    "FEJ": {"fond": "#ff99cc", "texte": "#000000", "libelle": "Férié"},
    "RTT": {"fond": "#ccffcc", "texte": "#000000", "libelle": "Réduction du temps de travail"},
}


def code_hermes_poste(poste: dict, seuil_journee_h: float = 10.0) -> str:
    """Déduit le code d'Hermes d'un poste : nuit, journée longue, matin ou après-midi."""
    if poste.get("est_nuit"):
        return "N02"
    if float(poste.get("duree") or 0) >= seuil_journee_h - 1e-9:
        return "J13"
    if int(poste.get("_debut_min") or 0) < 12 * 60:
        return "M03"
    return "S03"


def _entier(valeur, defaut=0) -> int:
    try:
        return max(0, int(valeur))
    except (TypeError, ValueError):
        return defaut


def _flottant(valeur, defaut=0.0) -> float:
    try:
        return float(valeur)
    except (TypeError, ValueError):
        return defaut


def _jours(valide) -> list[bool]:
    if isinstance(valide, (list, tuple)) and len(valide) == 7:
        return [bool(x) for x in valide]
    return [True] * 7


def normaliser(description: dict | None) -> dict:
    """Nettoie la description et applique les valeurs par défaut."""
    description = description or {}
    postes = []
    vus = set()
    for i, brut in enumerate(description.get("postes") or []):
        libelle = str(brut.get("libelle") or f"Poste {i + 1}").strip() or f"Poste {i + 1}"
        base = libelle
        n = 2
        while libelle in vus:                      # libellés uniques
            libelle = f"{base} ({n})"
            n += 1
        vus.add(libelle)
        poste = {
            "libelle": libelle,
            "debut": str(brut.get("debut") or "08:00"),
            "fin": str(brut.get("fin") or "16:00"),
            "personnes": _entier(brut.get("personnes")),
            "jours": _jours(brut.get("jours")),
        }
        poste["duree"] = duree_poste(poste)
        poste["est_nuit"] = est_poste_nuit(poste)
        poste["_debut_min"] = minutes(poste["debut"])
        poste["_duree_min"] = int(round(poste["duree"] * 60))
        # Code et couleurs d'Hermes : déduits du poste, ou choisis par la personne
        # (`code` dans la description). Un code inconnu retombe sur la disponibilité.
        code = str(brut.get("code") or "").strip().upper()
        poste["code"] = code if code in CODES_HERMES else code_hermes_poste(poste)
        poste["couleur_fond"] = CODES_HERMES[poste["code"]]["fond"]
        poste["couleur_texte"] = CODES_HERMES[poste["code"]]["texte"]
        postes.append(poste)

    effectif_brut = description.get("effectif") or {}
    effectif = {
        "temps_plein": _entier(effectif_brut.get("temps_plein")),
        "partiel_80": _entier(effectif_brut.get("partiel_80")),
        "fixes_nuit": _entier(effectif_brut.get("fixes_nuit")),
        "dispensees_nuit": _entier(effectif_brut.get("dispensees_nuit")),
    }

    reglages = dict(REGLAGES_DEFAUT)
    for cle, valeur in (description.get("reglages") or {}).items():
        if cle in reglages:
            reglages[cle] = valeur
    reglages["heures_legales_semaine"] = _flottant(reglages["heures_legales_semaine"], 35.0) or 35.0
    reglages["coefficient_remplacement"] = _flottant(reglages["coefficient_remplacement"], 0.10)
    reglages["cycle_semaines"] = max(CYCLE_MIN, min(CYCLE_MAX,
                                                    _entier(reglages["cycle_semaines"], 4)))
    reglages["jours_temps_plein"] = max(1, min(6, _entier(reglages["jours_temps_plein"], 5)))
    reglages["jours_80"] = max(1, min(6, _entier(reglages["jours_80"], 4)))

    return {
        "profession": str(description.get("profession") or "IDE").strip().upper(),
        "effectif": effectif,
        "postes": postes,
        "reglages": reglages,
    }


# ====================================================================================
# Analyse : heures, ETP, comparaison
# ====================================================================================
def _fr(nombre, decimales=1) -> str:
    return f"{nombre:.{decimales}f}".replace(".", ",")


def analyser(description: dict) -> dict:
    """Calcule les heures nécessaires, les ETP nécessaires et disponibles."""
    d = normaliser(description)
    postes = d["postes"]
    reglages = d["reglages"]
    legales = float(reglages["heures_legales_semaine"])
    coef = float(reglages["coefficient_remplacement"])

    detail_postes = []
    heures_total = 0.0
    for poste in postes:
        jours_semaine = sum(1 for x in poste["jours"] if x)
        heures = poste["personnes"] * poste["duree"] * jours_semaine
        heures_total += heures
        detail_postes.append({
            "libelle": poste["libelle"],
            "debut": poste["debut"],
            "fin": poste["fin"],
            "code": poste["code"],
            "couleur_fond": poste["couleur_fond"],
            "couleur_texte": poste["couleur_texte"],
            "duree_heures": round(poste["duree"], 2),
            "personnes": poste["personnes"],
            "jours_par_semaine": jours_semaine,
            "heures_par_semaine": round(heures, 2),
            "est_nuit": bool(poste["est_nuit"]),
        })

    heures_total = round(heures_total, 2)
    etp_necessaires = round(heures_total / legales * (1 + coef), 2) if legales else 0.0

    eff = d["effectif"]
    etp_disponibles = round(
        eff["temps_plein"] * 1.0 + eff["partiel_80"] * 0.8
        + eff["fixes_nuit"] * 1.0 + eff["dispensees_nuit"] * 1.0, 2)

    ecart = round(etp_disponibles - etp_necessaires, 2)
    if abs(ecart) < 0.05:
        phrase = "L'effectif disponible correspond au besoin."
        etat = "juste"
    elif ecart > 0:
        phrase = f"Il reste {_fr(ecart)} ETP disponible" + ("s" if ecart > 1 else "")
        etat = "surplus"
    else:
        phrase = f"Il manque {_fr(-ecart)} ETP"
        etat = "manque"

    # Couverture de nuit : nombre de personnes nécessaires la nuit la plus chargée
    # contre le nombre de personnes fixes de nuit disponibles.
    nuit_necessaires = 0
    for wd in range(7):
        besoin = sum(p["personnes"] for p in postes
                     if p["est_nuit"] and p["jours"][wd])
        nuit_necessaires = max(nuit_necessaires, besoin)
    nuit_disponibles = eff["fixes_nuit"]
    if nuit_necessaires and nuit_disponibles >= nuit_necessaires:
        phrase_nuit = (f"Couverture de nuit assurée : {nuit_disponibles} personne(s) "
                       f"fixe(s) de nuit pour {nuit_necessaires} nécessaire(s).")
    elif nuit_necessaires:
        phrase_nuit = (f"Nuit non couverte : {nuit_disponibles} personne(s) fixe(s) de nuit "
                       f"pour {nuit_necessaires} nécessaire(s).")
    else:
        phrase_nuit = "Aucun poste de nuit décrit."

    return {
        "profession": d["profession"],
        "heures_semaine_necessaires": heures_total,
        "heures_legales_semaine": legales,
        "coefficient_remplacement": coef,
        "etp_necessaires": etp_necessaires,
        "etp_disponibles": etp_disponibles,
        "comparaison": {"etat": etat, "ecart": ecart, "phrase": phrase},
        "explication_coefficient": (
            "Le coefficient de remplacement ajoute une marge de personnel pour assurer les "
            "remplacements (absences, congés, formations) : le besoin est augmenté d'autant."),
        "couverture_nuit": {
            "necessaires": nuit_necessaires,
            "disponibles": nuit_disponibles,
            "phrase": phrase_nuit,
        },
        "detail_postes": detail_postes,
        # Ce qu'il faut savoir sur les postes décrits : au-delà de 10 h une dérogation est
        # nécessaire, au-delà de 12 h la journée n'est pas conforme. Autant le dire tout de
        # suite, dès l'analyse.
        "remarques": [
            f"Le poste « {p['libelle']} » dure {p['duree']:g} h : "
            + ("au-delà de 12 h, la journée n'est pas conforme à la réglementation."
               if p["duree"] > 12.0 + 1e-9 else
               "c'est possible, mais une dérogation est nécessaire au-delà de 10 h.")
            for p in postes if p["duree"] > 10.0 + 1e-9
        ],
        "effectif": eff,
        "reglages": reglages,
    }


# ====================================================================================
# Construction des personnes et des postes autorisés
# ====================================================================================
def _construire_personnes(description: dict) -> tuple[list[dict], list[dict]]:
    d = normaliser(description)
    postes = d["postes"]
    reglages = d["reglages"]
    eff = d["effectif"]

    index_jour = [i for i, p in enumerate(postes) if not p["est_nuit"]]
    index_nuit = [i for i, p in enumerate(postes) if p["est_nuit"]]

    # Durée de référence d'une nuit : le nombre de nuits par semaine vise les heures légales.
    legales = float(reglages["heures_legales_semaine"])
    if index_nuit:
        duree_nuit = sum(postes[i]["duree"] for i in index_nuit) / len(index_nuit)
        cible_nuit = max(1, min(5, int(math.ceil(legales / duree_nuit))))
    else:
        cible_nuit = 0

    # La cible n'est PAS un nombre de jours mais un nombre d'HEURES par semaine (les
    # heures légales, au prorata de la quotité). C'est ce qui permet de mélanger des
    # journées de 7 h 30 et de 12 h : cinq journées courtes ou trois longues reviennent au
    # même. Le nombre de jours affiché n'est qu'une conséquence, donné à titre indicatif.
    def cible_heures(quotite):
        return legales * quotite * 60.0

    personnes = []
    for _ in range(eff["temps_plein"]):
        personnes.append({"profil": PROFIL_TEMPS_PLEIN, "quotite": 1.0,
                          "categorie": "jour", "postes": list(index_jour),
                          "cible_heures_min": cible_heures(1.0)})
    for _ in range(eff["partiel_80"]):
        personnes.append({"profil": PROFIL_QUATRE_VINGT, "quotite": 0.8,
                          "categorie": "jour", "postes": list(index_jour),
                          "cible_heures_min": cible_heures(0.8)})
    for _ in range(eff["fixes_nuit"]):
        personnes.append({"profil": PROFIL_NUIT, "quotite": 1.0,
                          "categorie": "nuit", "postes": list(index_nuit),
                          "cible_heures_min": cible_heures(1.0)})
    for _ in range(eff["dispensees_nuit"]):
        personnes.append({"profil": PROFIL_DISPENSE, "quotite": 1.0,
                          "categorie": "jour", "postes": list(index_jour),
                          "cible_heures_min": cible_heures(1.0)})

    for i, personne in enumerate(personnes):
        personne["nom"] = f"Personne {i + 1}"
    return personnes, postes


def _repos_insuffisant(precedent: dict, suivant: dict, minimum_h: float) -> bool:
    """Vrai si le repos entre ces deux postes (jours consécutifs) est insuffisant."""
    fin = precedent["_debut_min"] + precedent["_duree_min"]
    debut = suivant["_debut_min"] + 24 * 60
    return (debut - fin) < minimum_h * 60


# ====================================================================================
# Résolution CP-SAT d'un cycle
# ====================================================================================
def _resoudre(description: dict, semaines: int, seed: int,
              duree_max_s: float) -> dict | None:
    d = normaliser(description)
    postes = d["postes"]
    reglages = d["reglages"]
    personnes, _ = _construire_personnes(d)
    if not personnes:
        return None

    nb_personnes = len(personnes)
    T = semaines * 7          # nombre total de jours du cycle

    m = cp_model.CpModel()
    x = {}
    for a, personne in enumerate(personnes):
        for t in range(T):
            for pi in personne["postes"]:
                x[(a, t, pi)] = m.NewBoolVar(f"x_{a}_{t}_{pi}")
            # une seule chose par jour (un poste, ou rien = repos)
            if personne["postes"]:
                m.Add(sum(x[(a, t, pi)] for pi in personne["postes"]) <= 1)

    # --- Couverture : chaque jour, chaque poste au nombre demandé (souple, pénalisée)
    sous, trop = [], []
    for pi, poste in enumerate(postes):
        for wd in range(7):
            cible = poste["personnes"] if poste["jours"][wd] else 0
            for w in range(semaines):
                t = w * 7 + wd
                realises = [x[(a, t, pi)] for a in range(nb_personnes)
                            if pi in personnes[a]["postes"]]
                realise = sum(realises) if realises else 0
                s = m.NewIntVar(0, nb_personnes + 1, f"sous_{pi}_{t}")
                tr = m.NewIntVar(0, nb_personnes + 1, f"trop_{pi}_{t}")
                m.Add(realise - cible == tr - s)
                sous.append(s)
                trop.append(tr)

    # --- Heures travaillées par semaine : on vise les heures légales ------------------
    # Aucun nombre de jours n'est imposé : c'est la somme des heures qui compte. Une
    # personne travaille ainsi 5 journées de 7 h, ou 3 journées de 12 h, ou un mélange des
    # deux — n'importe quelle configuration est acceptée.
    heures_bas, heures_haut = [], []
    for a, personne in enumerate(personnes):
        if not personne["postes"]:
            continue
        cible = int(round(personne["cible_heures_min"]))
        for w in range(semaines):
            heures = sum(postes[pi]["_duree_min"] * x[(a, t, pi)]
                         for t in range(w * 7, w * 7 + 7) for pi in personne["postes"])
            haut = m.NewIntVar(0, max(0, 48 * 60 - cible), f"haut_{a}_{w}")
            bas = m.NewIntVar(0, cible, f"bas_{a}_{w}")
            m.Add(heures - cible == haut - bas)
            heures_haut.append(haut)
            heures_bas.append(bas)

    # --- Jamais plus de 48 h sur une semaine (Code du travail, art. L3121-20) --------
    for a, personne in enumerate(personnes):
        if not personne["postes"]:
            continue
        limite_min = 48 * 60
        for w in range(semaines):
            heures = sum(postes[pi]["_duree_min"] * x[(a, t, pi)]
                         for t in range(w * 7, w * 7 + 7)
                         for pi in personne["postes"])
            m.Add(heures <= limite_min)

    # --- Au moins 2 jours de repos par semaine (donc au plus 5 jours travaillés) ------
    for a, personne in enumerate(personnes):
        if not personne["postes"]:
            continue
        for w in range(semaines):
            travail = [x[(a, t, pi)] for t in range(w * 7, w * 7 + 7)
                       for pi in personne["postes"]]
            m.Add(sum(travail) <= 5)

    # --- Repos quotidien ≥ 11 h : interdire les enchaînements trop serrés -----------
    minimum = float(reglages.get("repos_quotidien_min_h", 11.0))
    for a, personne in enumerate(personnes):
        for t in range(T):
            tsv = (t + 1) % T
            for pi in personne["postes"]:
                for pj in personne["postes"]:
                    if _repos_insuffisant(postes[pi], postes[pj], minimum):
                        m.Add(x[(a, t, pi)] + x[(a, tsv, pj)] <= 1)

    # --- Jamais plus de 6 jours consécutifs -----------------------------------------
    for a, personne in enumerate(personnes):
        if not personne["postes"]:
            continue
        for depart in range(T):
            fenetre = [x[(a, (depart + k) % T, pi)]
                       for k in range(7) for pi in personne["postes"]]
            m.Add(sum(fenetre) <= 6)

    # --- Nuits consécutives ≤ 5 -----------------------------------------------------
    for a, personne in enumerate(personnes):
        nuits = [pi for pi in personne["postes"] if postes[pi]["est_nuit"]]
        if not nuits:
            continue
        for depart in range(T):
            fenetre = [x[(a, (depart + k) % T, pi)] for k in range(6) for pi in nuits]
            m.Add(sum(fenetre) <= 5)

    # --- Au moins un dimanche complet de repos sur deux -----------------------------
    for a, personne in enumerate(personnes):
        if not personne["postes"]:
            continue
        for w in range(semaines):
            dim1 = sum(x[(a, w * 7 + 6, pi)] for pi in personne["postes"])
            dim2 = sum(x[(a, ((w + 1) % semaines) * 7 + 6, pi)]
                       for pi in personne["postes"])
            m.Add(dim1 + dim2 <= 1)

    # --- Équité des week-ends travaillés --------------------------------------------
    weekends = []
    for a, personne in enumerate(personnes):
        if not personne["postes"]:
            weekends.append(m.NewConstant(0))
            continue
        total = sum(x[(a, w * 7 + j, pi)]
                    for w in range(semaines) for j in (5, 6)
                    for pi in personne["postes"])
        var = m.NewIntVar(0, 2 * semaines, f"we_{a}")
        m.Add(var == total)
        weekends.append(var)
    we_min = m.NewIntVar(0, 2 * semaines, "we_min")
    we_max = m.NewIntVar(0, 2 * semaines, "we_max")
    for var in weekends:
        m.Add(var >= we_min)
        m.Add(var <= we_max)

    # --- Équité des HEURES travaillées ----------------------------------------------
    # Sans cela, un horaire varié (7 h 30 et 12 h mêlés) laisse les heures très inégales
    # d'une personne à l'autre. On resserre l'écart entre celle qui travaille le plus et
    # celle qui travaille le moins, sur tout le cycle.
    heures_personne = []
    for a, personne in enumerate(personnes):
        if not personne["postes"]:
            continue
        total = sum(postes[pi]["_duree_min"] * x[(a, t, pi)]
                    for t in range(T) for pi in personne["postes"])
        heures_personne.append(total)
    if len(heures_personne) > 1:
        h_max = m.NewIntVar(0, 48 * 60 * semaines, "hmax")
        h_min = m.NewIntVar(0, 48 * 60 * semaines, "hmin")
        for total in heures_personne:
            m.Add(total <= h_max)
            m.Add(total >= h_min)
        ecart_heures = h_max - h_min
    else:
        ecart_heures = m.NewConstant(0)

    # --- Équité du nombre total de jours travaillés ---------------------------------
    totals = []
    for a, personne in enumerate(personnes):
        total = (sum(x[(a, t, pi)] for t in range(T) for pi in personne["postes"])
                 if personne["postes"] else 0)
        var = m.NewIntVar(0, T, f"tot_{a}")
        m.Add(var == total)
        totals.append(var)
    tot_min = m.NewIntVar(0, T, "tot_min")
    tot_max = m.NewIntVar(0, T, "tot_max")
    for var in totals:
        m.Add(var >= tot_min)
        m.Add(var <= tot_max)

    # --- Lisibilité : faire partager la même trame au plus grand nombre --------------
    #     Les personnes d'un même profil (même quotité, même nuit) sont comparées à la
    #     première d'entre elles : on récompense celles qui suivent exactement la même
    #     suite de postes et de repos.
    plafond = max(1, len(postes))
    valeurs = {}
    for a, personne in enumerate(personnes):
        for t in range(T):
            valeurs[(a, t)] = m.NewIntVar(0, plafond, f"val_{a}_{t}")
            if personne["postes"]:
                m.Add(valeurs[(a, t)] == sum((pi + 1) * x[(a, t, pi)]
                                             for pi in personne["postes"]))
            else:
                m.Add(valeurs[(a, t)] == 0)
    partages = []
    reference = {}
    for a, personne in enumerate(personnes):
        ref = reference.setdefault(personne["profil"], a)
        if ref == a:
            continue
        identique = m.NewBoolVar(f"eq_{a}")
        for t in range(T):
            m.Add(valeurs[(a, t)] - valeurs[(ref, t)] <= plafond * (1 - identique))
            m.Add(valeurs[(ref, t)] - valeurs[(a, t)] <= plafond * (1 - identique))
        partages.append(identique)

    # --- Objectif -------------------------------------------------------------------
    m.Minimize(_P_SOUS * sum(sous) + _P_TROP * sum(trop)
               + _P_HEURES_BAS * sum(heures_bas) + _P_HEURES_HAUT * sum(heures_haut)
               + _P_EQUITE_HEURES * ecart_heures
               + _P_EQUITE * (we_max - we_min)
               + _P_EQUITE_TRAVAIL * (tot_max - tot_min)
               - _P_PARTAGE * sum(partages))

    solveur = cp_model.CpSolver()
    solveur.parameters.max_time_in_seconds = float(duree_max_s)
    solveur.parameters.num_search_workers = 4
    solveur.parameters.random_seed = int(seed)
    statut = solveur.Solve(m)
    if statut not in (cp_model.OPTIMAL, cp_model.FEASIBLE):
        return None

    # --- Lecture de la solution -----------------------------------------------------
    jours_par_personne = []
    for a, personne in enumerate(personnes):
        ligne = []
        for t in range(T):
            valeur = REPOS
            for pi in personne["postes"]:
                if solveur.Value(x[(a, t, pi)]) == 1:
                    valeur = postes[pi]["libelle"]
                    break
            ligne.append(valeur)
        jours_par_personne.append(ligne)

    return _habiller(d, personnes, jours_par_personne, semaines, statut=str(statut).split(".")[-1])


# ====================================================================================
# Habillage : structure affichable + vérification réglementaire
# ====================================================================================
def _habiller(d: dict, personnes: list[dict], jours: list[list[str]],
              semaines: int, statut: str) -> dict:
    postes = d["postes"]
    agents = []
    for personne, ligne in zip(personnes, jours):
        agents.append({
            "nom": personne["nom"],
            "profil": personne["profil"],
            "quotite": personne["quotite"],
            "jours": list(ligne),
            "semaines": [ligne[w * 7:(w + 1) * 7] for w in range(semaines)],
        })

    # Couverture réalisée (la plus faible des semaines) contre la cible.
    couverture = []
    for pi, poste in enumerate(postes):
        couverture.append({"libelle": poste["libelle"], "jours": {}})
        for wd in range(7):
            comptes = []
            for w in range(semaines):
                t = w * 7 + wd
                comptes.append(sum(1 for ligne in jours
                                   if ligne[t] == poste["libelle"]))
            couverture[-1]["jours"][JOURS[wd]] = {
                "realise": min(comptes) if comptes else 0,
                "cible": poste["personnes"] if poste["jours"][wd] else 0,
            }

    trame = {
        "semaines": semaines,
        "postes": [{"libelle": p["libelle"], "debut": p["debut"], "fin": p["fin"],
                    "code": p["code"], "couleur_fond": p["couleur_fond"],
                    "couleur_texte": p["couleur_texte"], "duree": p["duree"]}
                   for p in postes],
        # Couleurs pour la grille : un libellé de poste → sa couleur, plus les repos
        # (verts, comme « RH » dans Hermes).
        "couleurs": dict({p["libelle"]: {"fond": p["couleur_fond"],
                                         "texte": p["couleur_texte"], "code": p["code"]}
                          for p in postes},
                         Repos={"fond": CODES_HERMES["RH"]["fond"],
                                "texte": CODES_HERMES["RH"]["texte"], "code": "RH"}),
        "codes_hermes": CODES_HERMES,
        "agents": agents,
    }
    verdict = verifier_trame(trame)

    # Remarques utiles (postes longs, personnel sans poste affecté…).
    remarques = []
    for poste in postes:
        if poste["duree"] > 12.0 + 1e-9:
            remarques.append(f"Le poste « {poste['libelle']} » dure {poste['duree']:g} h : "
                             "au-delà de 12 h, la journée n'est pas conforme à la "
                             "réglementation.")
        elif poste["duree"] > 10.0 + 1e-9:
            remarques.append(f"Le poste « {poste['libelle']} » dure {poste['duree']:g} h : "
                             "c'est possible, mais une dérogation est nécessaire au-delà "
                             "de 10 h.")
    for personne in personnes:
        if not personne["postes"]:
            remarques.append(f"Les personnes « {personne['profil']} » n'ont aucun poste à "
                             "assurer dans cette description.")

    # Regroupement des personnes qui suivent exactement la même trame (lisibilité).
    groupes = {}
    for a, agent in enumerate(agents):
        groupes.setdefault(tuple(agent["jours"]), []).append(agent["nom"])

    return {
        "semaines": semaines,
        "statut_solveur": statut,
        # Les postes portent leur CODE et leurs COULEURS d'Hermes : la page n'a plus qu'à
        # peindre la grille comme le planning habituel.
        "postes": [{"libelle": p["libelle"], "debut": p["debut"], "fin": p["fin"],
                    "code": p["code"], "couleur_fond": p["couleur_fond"],
                    "couleur_texte": p["couleur_texte"], "duree": p["duree"]}
                   for p in postes],
        "couleurs": dict({p["libelle"]: {"fond": p["couleur_fond"],
                                         "texte": p["couleur_texte"], "code": p["code"]}
                          for p in postes},
                         Repos={"fond": CODES_HERMES["RH"]["fond"],
                                "texte": CODES_HERMES["RH"]["texte"], "code": "RH"}),
        "codes_hermes": CODES_HERMES,
        "agents": agents,
        "couverture": couverture,
        "verdict": {
            "conforme": verdict["conforme"],
            "manquements": verdict["manquements"],
            "informations": verdict["informations"],
        },
        "compteurs": verdict["compteurs"],
        "remarques": remarques,
        "groupes": [noms for noms in groupes.values() if len(noms) > 1],
    }


# ====================================================================================
# Génération de plusieurs trames
# ====================================================================================
def _cycles_candidats(cycle_demande: int) -> list[int]:
    candidats = [cycle_demande, cycle_demande - 1, cycle_demande + 1,
                 cycle_demande - 2, cycle_demande + 2]
    vus, resultat = set(), []
    for c in candidats:
        c = max(CYCLE_MIN, min(CYCLE_MAX, c))
        if c not in vus:
            vus.add(c)
            resultat.append(c)
    return resultat


def generer(description: dict, max_trames: int = MAX_TRAMES,
            duree_max_s: float = DUREE_SOLVEUR_S) -> dict:
    """Génère jusqu'à ``max_trames`` trames différentes (2 à 3 en pratique)."""
    d = normaliser(description)
    analyse = analyser(d)
    cycle = int(d["reglages"]["cycle_semaines"])

    trames = []
    signatures = set()
    tentatives = [(c, 1) for c in _cycles_candidats(cycle)]
    if max_trames > 1:                       # seconds tirages pour varier les trames
        tentatives += [(c, 7) for c in _cycles_candidats(cycle)]

    for cycle_candidat, seed in tentatives:
        if len(trames) >= max(1, min(MAX_TRAMES, int(max_trames))):
            break
        trame = _resoudre(d, cycle_candidat, seed, duree_max_s)
        if trame is None:
            continue
        signature = tuple(tuple(agent["jours"]) for agent in trame["agents"])
        if signature in signatures:
            continue
        signatures.add(signature)
        trame["numero"] = len(trames) + 1
        trame["titre"] = f"Trame {len(trames) + 1} — cycle de {cycle_candidat} semaines"
        trames.append(trame)

    return {
        "profession": d["profession"],
        "analyse": analyse,
        "trames": trames,
        "nb_trames": len(trames),
    }
