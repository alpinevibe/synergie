#!/usr/bin/env python3
"""Les AVIS et leur SYNTHÈSE — « tous les avis comptent, pour un résultat harmonieux ».

Aggregation des avis (souhaits) déposés par les professionnels, puis HARMONISATION :
on place chaque agent sur une ligne de la trame de son profil, et l'on cherche à honorer
les avis sans jamais dégrader la couverture du service (un avis ne passe jamais avant un
poste à couvrir).

  * « Indice de synergie » = part de la valeur des avis honorés (pondérée par le poids de
    chaque avis) : c'est l'indicateur d'harmonie du projet.
  * Tout avis non honoré est SIGNALÉ (jamais masqué) : c'est le point de discussion pour
    l'équipe.

Rappel des poids d'avis (règles génériques) : CAJ 3000 > FEJ 2000 > FC 1500 > RTT 1000.
"""
from __future__ import annotations

from datetime import date, timedelta

from .regles import poids_avis, regles_projet

JOURS = ["Lun", "Mar", "Mer", "Jeu", "Ven", "Sam", "Dim"]
CODES_ABSENCE = "CA CAJ CA25 FE FEJ FE25 RTT CEP JR JF MAT MAL AAJ FC HS".split()


def _date_debut(projet: dict) -> date:
    return date.fromisoformat(projet.get("date_debut") or date.today().isoformat())


def _cellule(trame: dict, jour: date, debut: date) -> tuple[int, int]:
    """Position (semaine, jour) d'une date dans la trame, modulo la période."""
    delta = (jour - debut).days
    semaine = (delta // 7) % int(trame["periode"])
    return semaine, delta % 7


def repartir_agents(trame: dict) -> dict:
    """Répartit les agents du profil sur les lignes de la trame (une ligne par agent)."""
    agents = list(trame.get("agents") or [])
    periode = int(trame["periode"])
    affectation = {}
    for i, nom in enumerate(agents):
        affectation[nom] = i % periode
    return affectation


def synthese(projet: dict, generation: dict) -> dict:
    """Produit le PLANNING PROJETÉ par agent + l'indice de synergie + les avis non honorés."""
    regles = regles_projet(projet.get("regles"))
    debut = _date_debut(projet)
    nb_semaines = int(projet.get("duree_semaines") or 6)
    avis = list(projet.get("avis") or [])

    # Index des trames par agent (via le métier et la quotité)
    trame_par_agent = {}
    for trame in generation.get("trames", []):
        for nom in trame.get("agents", []):
            trame_par_agent[nom] = trame

    lignes_agents = {nom: repartir_agents(t)[nom] for nom, t in trame_par_agent.items()}

    # --- Planning projeté -------------------------------------------------------------
    planning = {}
    for nom, trame in trame_par_agent.items():
        ligne = lignes_agents[nom]
        periode = int(trame["periode"])
        cases = {}
        for s in range(nb_semaines):
            for d in range(7):
                date_jour = debut + timedelta(days=7 * s + d)
                code = trame["semaines"][(s + ligne) % periode][d]
                cases[date_jour.isoformat()] = code
        planning[nom] = cases

    # --- Avis : honorés / non honorés --------------------------------------------------
    total_poids = 0
    gagnes = 0
    honores, refuses = [], []
    for a in avis:
        nom = a.get("agent")
        souhait = (a.get("souhait") or "").strip().upper()
        poids = poids_avis(souhait, regles)
        total_poids += poids
        if not nom or nom not in planning:
            refuses.append({**a, "poids": poids, "raison": "agent inconnu dans ce projet"})
            continue
        try:
            jour = date.fromisoformat(str(a.get("jour")))
        except Exception:
            refuses.append({**a, "poids": poids, "raison": "date illisible"})
            continue
        code_du_jour = planning[nom].get(jour.isoformat())
        if code_du_jour is None:
            refuses.append({**a, "poids": poids, "raison": "hors période du projet"})
            continue
        if code_du_jour == souhait:
            honores.append({**a, "poids": poids})
            gagnes += poids
        elif code_du_jour in ("RH", "DS") and souhait in CODES_ABSENCE:
            # le jour est déjà hors travail : l'absence est « posée » sans effet sur le
            # service — l'agent est bien en repos comme souhaité.
            honores.append({**a, "poids": poids, "note": "jour déjà en repos"})
            gagnes += poids
        else:
            refuse = _tenter_echange(projet, planning, trame_par_agent, lignes_agents,
                                     nom, jour, souhait, code_du_jour)
            if refuse is None:
                honores.append({**a, "poids": poids, "note": "obtenu par échange"})
                gagnes += poids
            else:
                refuses.append({**a, "poids": poids, "raison": refuse})

    indice = round(100.0 * gagnes / total_poids, 1) if total_poids else None
    return {
        "projet": projet.get("id"),
        "planning": planning,
        "lignes": lignes_agents,
        "avis": {
            "total": len(avis),
            "honores": len(honores),
            "non_honores": len(refuses),
            "indice_synergie": indice,
            "details_honores": honores,
            "details_refuses": refuses,
        },
        "couverture": [t.get("couverture", {}) for t in generation.get("trames", [])],
        "heures": [{"trame": t.get("code_trame"), **t.get("heures", {})}
                   for t in generation.get("trames", [])],
    }


def _tenter_echange(projet, planning, trame_par_agent, lignes_agents, nom, jour, souhait,
                    code_du_jour) -> str | None:
    """Cherche un collègue en repos ce jour-là, à qui l'on peut passer le poste.

    Retourne ``None`` si l'échange a été fait, sinon la raison du refus (texte).
    """
    if souhait not in CODES_ABSENCE and souhait not in ("RH", "DS"):
        return "code souhaité inconnu ou non posable sur une trame"
    trame = trame_par_agent.get(nom)
    if not trame:
        return "agent hors trame"
    metier = trame.get("metier")
    # collègues du même métier, en repos ce jour-là
    for collegue, cases in planning.items():
        if collegue == nom:
            continue
        t = trame_par_agent.get(collegue)
        if not t or t.get("metier") != metier:
            continue
        if cases.get(jour.isoformat()) in ("RH", "DS"):
            # échange : le collègue prend le poste, l'agent souhaité est libéré
            cases[jour.isoformat()] = code_du_jour
            planning[nom][jour.isoformat()] = souhait
            return None
    return "aucun collègue disponible pour reprendre le poste"
