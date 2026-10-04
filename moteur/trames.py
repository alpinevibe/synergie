#!/usr/bin/env python3
"""GÉNÉRATEUR DE TRAMES — moteur générique (OR-Tools CP-SAT).

C'est le cœur de la « boîte à trames » de Synergie : il reprend la LOGIQUE du générateur
de grilles de rotation d'Hermes Planning (``engine_rotation.py``), mais il est **générique** :
il ne connaît aucun métier — il reçoit en entrée un métier, ses cibles par jour et sa
population, et rend une TRAME de N semaines.

PRINCIPE (identique à Hermes, arbitrage du 21/09/2026)
-----------------------------------------------------
  * Une trame = N semaines rejouées en boucle ; N = EFFECTIF du profil de temps de travail
    (mêmes quotité / nuit), plafonné (12 par défaut). Deux professionnels ayant les MÊMES
    critères de temps de travail suivent la MÊME trame, décalée d'une semaine par ligne :
    la couverture est donc **identique chaque semaine** (aucune semaine chargée ni creuse).
  * Chaque semaine de la trame a un profil de jours travaillés : une semaine de week-end
    travaillé compte ``arrondi(5 × quotité) + 1`` jours, la suivante ``arrondi(5 × quotité) - 1``
    (moyenne 5 × quotité). C'est ce qui garantit « heures travaillées ≥ heures légales ».
  * Un temps partiel (quotité < 100 %) porte exactement ``1`` DS par semaine (jour hors
    quotité). Les repos RH complètent la semaine (2 par semaine en moyenne).
  * Un week-end travaillé = samedi ET dimanche ; au plus un week-end sur deux, réparti
    entre TOUTES les lignes.
  * Les nuits TOURNANTES n'entrent pas dans une trame. seuls les profils d'agents
    FIXES de nuit suivent le cycle de 14 jours du règlement (NN DS RH).
  * Un déficit de couverture n'empêche jamais la production : il est SIGNALÉ.
"""
from __future__ import annotations

import math

from ortools.sat.python import cp_model

from .regles import (
    heures_code,
    heures_legales,
    jours_travailles_semaine,
    ds_par_semaine,
)

JOURS = ["Lun", "Mar", "Mer", "Jeu", "Ven", "Sam", "Dim"]
MAX_SEMAINES_DEFAUT = 12
DUREE_SOLVEUR_S = 20.0


# ------------------------------------------------------------------------------------
# Groupes de temps de travail
# ------------------------------------------------------------------------------------
def _profil_agent(agent: dict) -> tuple:
    """Clé de regroupement : mêmes critères de temps de travail = même trame."""
    quotite = round(float(agent.get("quotite", 1.0)), 2)
    return (quotite, bool(agent.get("nuit_fixe", False)), bool(agent.get("sans_nuit", False)))


def _libelle_profil(quotite: float, nuit_fixe: bool, sans_nuit: bool) -> str:
    parts = [f"{int(round(quotite * 100))} %"]
    if nuit_fixe:
        parts.append("nuit fixe")
    elif sans_nuit:
        parts.append("sans nuit")
    return " — ".join(parts)


def profils_metier(metier: dict, agents: list[dict], max_semaines: int) -> list[dict]:
    """Regroupe les agents d'un métier en profils de temps de travail."""
    groupes: dict[tuple, list[dict]] = {}
    for a in agents:
        groupes.setdefault(_profil_agent(a), []).append(a)
    profils = []
    for (quotite, nuit_fixe, sans_nuit), membres in sorted(groupes.items()):
        profils.append({
            "cle": f"{metier['code']}-{int(round(quotite * 100))}"
                   + ("-NF" if nuit_fixe else ("-SN" if sans_nuit else "")),
            "metier": metier["code"],
            "metier_libelle": metier.get("libelle", metier["code"]),
            "quotite": quotite,
            "nuit_fixe": nuit_fixe,
            "sans_nuit": sans_nuit,
            "libelle": _libelle_profil(quotite, nuit_fixe, sans_nuit),
            "effectif": len(membres),
            "agents": [m.get("nom", "") for m in membres],
            "semaines_max": max_semaines,
        })
    return profils


# ------------------------------------------------------------------------------------
# Cycle fixe de nuit (règlement §§1-6) — 14 jours
# ------------------------------------------------------------------------------------
_CYCLE_NUIT_BASE = ["N", "N", "DS", "RH", "N", "N", "N", "DS", "RH", "N", "N", "DS", "RH", "RH"]
# les agents fixes de nuit suivent ce cycle, décalé de 7 jours l'un par rapport à l'autre
CYCLE_NUIT_FIXE = (
    list(_CYCLE_NUIT_BASE),
    _CYCLE_NUIT_BASE[7:] + _CYCLE_NUIT_BASE[:7],
)


# ------------------------------------------------------------------------------------
# Résolution d'un profil
# ------------------------------------------------------------------------------------
def _codes_trame(metier: dict, regles: dict) -> list[str]:
    """Codes autorisés dans une trame de jour : postes de travail + RH + DS."""
    codes = list(metier.get("codes_travail", [])) or [c["code"] for c in metier.get("postes", [])]
    for c in regles.get("codes_repos", []):
        if c not in codes:
            codes.append(c)
    return codes


def resoudre_trame(profil: dict, metier: dict, regles: dict,
                   cibles: dict | None = None,
                   duree_max_s: float = DUREE_SOLVEUR_S) -> dict:
    """Construit la trame d'un profil de temps de travail.

    ``cibles`` : {jour_de_semaine: {code: nombre}} — postes à couvrir chaque jour. Par
    défaut, on lit les cibles du métier.
    """
    quotite = float(profil["quotite"])
    effectif = int(profil["effectif"])
    cibles = cibles or metier.get("cibles", {})
    max_sem = int(profil.get("semaines_max", MAX_SEMAINES_DEFAUT))
    periode = max(2, min(effectif, max_sem))

    # --- Agents fixes de nuit : cycle réglementaire, pas de solveur ------------------
    if profil.get("nuit_fixe"):
        return _trame_nuit_fixe(profil, regles)

    codes = _codes_trame(metier, regles)
    codes_repos = [c for c in regles.get("codes_repos", []) if c in codes]
    code_rh = codes_repos[0] if codes_repos else "RH"
    code_ds = codes_repos[1] if len(codes_repos) > 1 else "DS"
    codes_travail = [c for c in codes if c not in codes_repos]

    nb_jours_sem = jours_travailles_semaine(quotite, regles)          # 5 × quotité
    nb_ds = ds_par_semaine(quotite, regles)
    we_actif = any(cibles.get(JOURS[d], {}) for d in (5, 6))          # samedi/dimanche

    m = cp_model.CpModel()
    # b[w][d][code] = 1 si la semaine w de la trame porte « code » le jour d.
    b = {}
    for w in range(periode):
        for d in range(7):
            for c in codes:
                b[(w, d, c)] = m.NewBoolVar(f"b_{w}_{d}_{c}")
            m.AddExactlyOne(b[(w, d, c)] for c in codes)

    travail = {(w, d): [b[(w, d, c)] for c in codes_travail]
               for w in range(periode) for d in range(7)}
    est_travail = {(w, d): m.NewBoolVar(f"t_{w}_{d}")
                   for w in range(periode) for d in range(7)}
    for (w, d), vars_ in travail.items():
        m.Add(sum(vars_) == est_travail[(w, d)])

    # --- 1. Couverture : cible APPROCHÉE au mieux (jamais un refus, §76) --------------
    ecarts = []
    deficit, surplus = [], []
    for d in range(7):
        cible_jour = {c: int(n) for c, n in (cibles.get(JOURS[d]) or {}).items()}
        for c in codes_travail:
            vise = cible_jour.get(c, 0)
            realise = sum(b[(w, d, c)] for w in range(periode))
            borne = periode + vise
            sous = m.NewIntVar(0, borne, f"sous_{d}_{c}")
            trop = m.NewIntVar(0, borne, f"trop_{d}_{c}")
            m.Add(realise - vise == trop - sous)
            deficit.append(sous)
            surplus.append(trop)
        for c, n in cible_jour.items():
            if c not in codes_travail:
                ecarts.append(f"cible « {c} » ({JOURS[d]}) hors des postes du métier "
                              f"{metier['code']} : {n} poste(s) non couvert(s)")

    # --- 2. Week-end : samedi et dimanche ensemble, au plus un sur deux --------------
    we_sym = (sum((cibles.get("Sam") or {}).values()) ==
              sum((cibles.get("Dim") or {}).values()))
    if we_sym:
        for w in range(periode):
            m.Add(est_travail[(w, 5)] == est_travail[(w, 6)])
        for w in range(periode):
            m.Add(est_travail[(w, 5)] + est_travail[((w + 1) % periode, 5)] <= 1)

    # --- 3. Structure de chaque semaine : travaillés / DS / RH ------------------------
    #    5 × quotité jours, + 1 la semaine du week-end travaillé, − 1 la semaine qui suit.
    for w in range(periode):
        prec = (w - 1) % periode
        m.Add(sum(est_travail[(w, d)] for d in range(7)) ==
              nb_jours_sem + est_travail[(w, 5)] - est_travail[(prec, 5)])
        m.Add(sum(b[(w, d, code_ds)] for d in range(7)) == nb_ds)

    # --- 4. Pas de DS collé à un week-end travaillé, RH jamais tronqué ----------------
    for w in range(periode):
        we = est_travail[(w, 5)]
        m.Add(b[(w, 5, code_ds)] == 0)
        m.Add(b[(w, 6, code_ds)] == 0)
        # le DS se prend en semaine, pas le lendemain d'un week-end travaillé
        m.Add(b[(w, 0, code_ds)] + we <= 1)

    # --- 5. Repos hebdomadaires : au moins 2 RH par semaine en moyenne ----------------
    rh_min = int(regles.get("rh_min_semaine", 2))
    total_rh = sum(b[(w, d, code_rh)] for w in range(periode) for d in range(7))
    m.Add(total_rh >= rh_min * periode)

    # --- 6. Heures travaillées ≥ heures légales ---------------------------------------
    heures = {c: heures_code(c, regles) for c in codes}
    total = sum(int(round(heures[c] * 100)) * b[(w, d, c)]
                for w in range(periode) for d in range(7) for c in codes)
    m.Add(total >= int(round(heures_legales(quotite, periode, regles) * 100)))

    # --- 7. Quotité 100 % : aucun DS --------------------------------------------------
    if nb_ds == 0:
        for w in range(periode):
            m.Add(sum(b[(w, d, code_ds)] for d in range(7)) == 0)

    # --- 8. Objectif : « tous les postes couverts », le déficit coûte très cher -------
    p_sous = int(regles.get("poids_sous_couverture", 10000))
    m.Minimize(sum(p_sous * s for s in deficit) + sum(surplus))

    # --- Résolution -------------------------------------------------------------------
    solveur = cp_model.CpSolver()
    solveur.parameters.max_time_in_seconds = float(duree_max_s)
    solveur.parameters.num_search_workers = 4
    statut = solveur.Solve(m)
    if statut not in (cp_model.OPTIMAL, cp_model.FEASIBLE):
        return _trame_de_secours(profil, metier, regles, periode, codes, ecarts)

    semaines = [[_code_de(b, solveur, w, d, codes) for d in range(7)] for w in range(periode)]
    return _habiller_trame(profil, semaines, cibles, regles, codes_travail, ecarts,
                           statut=str(statut).split(".")[-1])


def _code_de(b, solveur, w, d, codes) -> str:
    for c in codes:
        if solveur.Value(b[(w, d, c)]) == 1:
            return c
    return codes[-1]


# ------------------------------------------------------------------------------------
# Trame fixe de nuit
# ------------------------------------------------------------------------------------
def _trame_nuit_fixe(profil: dict, regles: dict) -> dict:
    effectif = int(profil["effectif"])
    semaines = []
    for i in range(effectif):
        cycle = CYCLE_NUIT_FIXE[i % len(CYCLE_NUIT_FIXE)]
        semaines.append(list(cycle))
    return _habiller_trame(profil, semaines, {}, regles,
                           codes_travail=["N"], ecarts=[], statut="CYCLE_FIXE")


# ------------------------------------------------------------------------------------
# Repli (aucune trame ne se refuse) et habillage
# ------------------------------------------------------------------------------------
def _trame_de_secours(profil, metier, regles, periode, codes, ecarts) -> dict:
    """Repli : trame régulière minimale (semaine travaillée / semaine de repos)."""
    quotite = float(profil["quotite"])
    nb_jours = jours_travailles_semaine(quotite, regles)
    nb_ds = ds_par_semaine(quotite, regles)
    codes_repos = list(regles.get("codes_repos", ["RH", "DS"]))
    code_rh = codes_repos[0] if codes_repos else "RH"
    code_ds = codes_repos[1] if len(codes_repos) > 1 else "DS"
    code_travail = next((c for c in codes if c not in codes_repos), "M")
    semaines = []
    for w in range(periode):
        we = w % 2 == 1
        ligne = [code_rh] * 7
        for d in range(nb_jours):
            ligne[d % 5] = code_travail
        for k in range(nb_ds):
            ligne[4 - k] = code_ds
        if we:
            ligne[5] = code_travail
            ligne[6] = code_travail
        semaines.append(ligne)
    ecarts = list(ecarts) + [
        "MODÈLE INFAISABLE pour ce profil : trame de REPLI appliquée (cibles non "
        "entièrement tenues) — déficit à couvrir par suppléance."]
    return _habiller_trame(profil, semaines, metier.get("cibles", {}), regles,
                           codes_travail=[code_travail], ecarts=ecarts, statut="REPLI")


def _habiller_trame(profil, semaines, cibles, regles, codes_travail, ecarts, statut) -> dict:
    periode = len(semaines)
    quotite = float(profil["quotite"])
    # Décodage éventuel en cas de repli
    codes_repos = set(regles.get("codes_repos", []))
    couverture = {}
    for d, jour in enumerate(JOURS):
        couverture[jour] = {}
        for c in set(list(cibles.get(jour, {}).keys()) + list(codes_travail)):
            vise = int((cibles.get(jour, {}) or {}).get(c, 0))
            realise = sum(1 for w in range(periode)
                          if semaines[w][d] == c and c not in codes_repos)
            if vise or realise:
                couverture[jour][c] = [realise, vise]
    heures_trav = sum(heures_code(semaines[w][d], regles)
                      for w in range(periode) for d in range(7))
    heures_leg = heures_legales(quotite, periode, regles)
    # rotations : ligne i = trame décalée de i semaines
    lignes = [[semaines[(k + i) % periode] for k in range(periode)]
              for i in range(periode)]
    return {
        "cle": profil["cle"],
        "metier": profil["metier"],
        "metier_libelle": profil.get("metier_libelle", profil["metier"]),
        "quotite": quotite,
        "libelle": profil["libelle"],
        "nuit_fixe": bool(profil.get("nuit_fixe")),
        "effectif": int(profil["effectif"]),
        "agents": profil.get("agents", []),
        "periode": periode,
        "semaines": semaines,
        "lignes": lignes,
        "couverture": couverture,
        "ecarts": ecarts,
        "statut": statut,
        "heures": {
            "travaillees": round(heures_trav, 1),
            "legales": round(heures_leg, 1),
            "ratio": round(heures_trav / heures_leg, 3) if heures_leg else None,
        },
        "code_trame": code_trame(profil["metier"], quotite, periode, profil.get("nuit_fixe")),
    }


def code_trame(metier: str, quotite: float, periode: int, nuit_fixe: bool = False) -> str:
    """Code de trame : mêmes critères de temps de travail = même trame = même code."""
    q = int(round(float(quotite) * 100))
    return f"TRM-{str(metier).upper()}-{q:03d}" + ("-NF" if nuit_fixe else "") + f"-{periode}S"


def generer_trames(projet: dict, metier_code: str | None = None,
                   max_semaines: int = MAX_SEMAINES_DEFAUT,
                   duree_max_s: float = DUREE_SOLVEUR_S) -> dict:
    """Génère la boîte à trames d'un projet (un ou tous les métiers)."""
    regles = _regles(projet)
    resultats = []
    for metier in projet.get("metiers", []):
        if metier_code and metier["code"] != metier_code:
            continue
        agents = [a for a in projet.get("agents", []) if a.get("metier") == metier["code"]]
        profils = profils_metier(metier, agents, max_semaines)
        parts = repartir_cibles(metier.get("cibles", {}), profils, regles)
        for profil, cibles_part in zip(profils, parts):
            resultats.append(resoudre_trame(profil, metier, regles, cibles=cibles_part,
                                            duree_max_s=duree_max_s))
    return {
        "projet": projet.get("id"),
        "genere_le": __import__("datetime").datetime.now().isoformat(timespec="seconds"),
        "trames": resultats,
    }


def repartir_cibles(cibles: dict, profils: list[dict], regles: dict) -> list[dict]:
    """Partage la cible d'un métier entre ses profils de temps de travail.

    Chaque profil (quotité, nuit) ne couvre que SA part du service : la part est
    proportionnelle à sa capacité (effectif × jours travaillés par semaine), au plus
    juste (méthode du plus fort reste). Sans ce partage, chaque profil rejouerait la
    cible entière et le service serait sur-couvert.
    """
    JOURS_LOCAL = ["Lun", "Mar", "Mer", "Jeu", "Ven", "Sam", "Dim"]
    capacites = [p["effectif"] * jours_travailles_semaine(p["quotite"], regles)
                 for p in profils]
    total = sum(capacites) or 1
    parts = [{j: {} for j in JOURS_LOCAL} for _ in profils]
    for jour in JOURS_LOCAL:
        for code, n in (cibles.get(jour) or {}).items():
            exact = [int(n) * c / total for c in capacites]
            base = [int(x) for x in exact]
            reste = int(n) - sum(base)
            ordre = sorted(range(len(profils)), key=lambda i: exact[i] - base[i], reverse=True)
            for k in range(max(0, reste)):
                base[ordre[k % len(profils)]] += 1
            for i, valeur in enumerate(base):
                if valeur:
                    parts[i][jour][code] = valeur
    return parts


def _regles(projet: dict) -> dict:
    from .regles import regles_projet
    return regles_projet(projet.get("regles"))
