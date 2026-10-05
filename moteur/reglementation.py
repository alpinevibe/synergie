#!/usr/bin/env python3
"""VÉRIFICATEUR DE RÉGLEMENTATION DU TEMPS DE TRAVAIL.

Ce module est **écrit en Python pur** (aucune dépendance) : il prend une trame
(un cycle de plusieurs semaines : pour chaque personne, pour chaque jour, le poste
de travail ou le repos) et rend :

  * un **verdict** : « conforme » ou « non conforme » ;
  * la **liste précise des manquements** (quelle personne, quel jour, quelle règle) ;
  * des **compteurs** utilisables par l'outil (heures travaillées, repos, week-ends,
    nuits, jours consécutifs, écart avec les heures légales…).

Toutes les valeurs de référence sont regroupées dans ``REGLE_DEFAUT`` ci-dessous :
chaque règle est écrite en clair, avec sa valeur par défaut et sa source
(Code du travail, ou accord de la Fonction Publique Hospitalière).

Convention des données d'entrée (trame) ::

    {
      "semaines": 4,
      "postes": [ {"libelle": "Matin", "debut": "06:30", "fin": "14:30"}, ... ],
      "agents": [
        {"nom": "Personne 1", "profil": "100 %", "quotite": 1.0,
         "jours": ["Matin", "Matin", "Repos", ...] }   # N semaines × 7 jours
      ]
    }

Le libellé « Repos » (ou « RH », « DS » ou une case vide) désigne un jour non
travaillé.
"""
from __future__ import annotations

# --- Vocabulaire commun --------------------------------------------------------------
JOURS_COURTS = ["Lun", "Mar", "Mer", "Jeu", "Ven", "Sam", "Dim"]
JOURS_LONGS = ["Lundi", "Mardi", "Mercredi", "Jeudi", "Vendredi", "Samedi", "Dimanche"]
LIBELLES_REPOS = {"repos", "rh", "ds", "", "repos hebdomadaire", "repos domicile",
                  "repos quotidien", "off", "congé", "conge"}

# --- Valeurs de référence des règles (par défaut) -----------------------------------
# Chaque règle : valeur par défaut + source. Modifiables via ``regles``.
REGLES_DEFAUT: dict = {
    # Amplitude journalière : la durée entre le début et la fin d'une journée de travail
    # ne peut pas dépasser 10 heures de travail effectif.
    #   Valeur : 10 h — Source : Code du travail, article L3121-18.
    "amplitude_max_h": 10.0,

    # Repos quotidien : entre la fin d'un poste et le début du suivant, une personne doit
    # bénéficier d'au moins 11 heures consécutives de repos.
    #   Valeur : 11 h — Source : Code du travail, article L3131-1.
    "repos_quotidien_min_h": 11.0,

    # Repos hebdomadaire : au moins 2 jours de repos par semaine (24 h + 11 h de repos
    # quotidien, soit deux jours pleins en pratique).
    #   Valeur : 2 jours — Source : Code du travail, articles L3131-1 et L3164-1.
    "repos_hebdo_min_jours": 2,

    # Repos dominical : au moins un dimanche complet de repos sur deux (règle hospitalière).
    #   Valeur : un dimanche sur deux — Source : Code du travail, article L3164-2 (FPH).
    "un_dimanche_sur_deux": 2,

    # Durée hebdomadaire moyenne : la moyenne des heures travaillées sur le cycle ne doit
    # pas dépasser les heures légales (35 h pour un temps plein).
    #   Valeur : 35 h — Source : Code du travail, article L3121-27.
    "duree_moyenne_max_h": 35.0,

    # Durée hebdomadaire maximale : aucune semaine ne peut dépasser 48 heures.
    #   Valeur : 48 h — Source : Code du travail, article L3121-20.
    "duree_max_semaine_h": 48.0,

    # Jours consécutifs travaillés : le repos hebdomadaire implique de ne jamais dépasser
    # 6 jours de travail d'affilée.
    #   Valeur : 6 jours — Source : Code du travail, article L3131-1.
    "max_jours_consecutifs": 6,

    # Pause : dès 6 heures de travail, une pause d'au moins 20 minutes est obligatoire.
    # Signalé comme **information** (pas comme manquement).
    #   Valeur : 6 h — Source : Code du travail, article L3121-16.
    "pause_seuil_h": 6.0,

    # Nuits consécutives : une personne ne doit pas enchaîner plus de 5 nuits d'affilée.
    #   Valeur : 5 nuits — Source : accord de la Fonction Publique Hospitalière.
    "max_nuits_consecutives": 5,
}


# --- Petites aides de calcul ---------------------------------------------------------
def minutes(hhmm: str) -> int:
    """« 06:30 » -> 390 minutes depuis minuit. Tolère « 6:30 » et « 6h30 »."""
    texte = str(hhmm).strip().lower().replace("h", ":")
    parties = texte.split(":")
    try:
        heures = int(parties[0]) if parties and parties[0] != "" else 0
        mins = int(parties[1]) if len(parties) > 1 and parties[1] != "" else 0
    except (ValueError, TypeError):
        return 0
    return heures * 60 + mins


def duree_poste(poste: dict) -> float:
    """Durée en heures d'un poste, en tenant compte d'un poste qui passe minuit.

    Exemple : 19:30 -> 07:30 = 12 heures ; 06:30 -> 14:30 = 8 heures.
    """
    debut = minutes(poste.get("debut", "08:00"))
    fin = minutes(poste.get("fin", "16:00"))
    ecart = fin - debut
    if ecart <= 0:            # le poste franchit minuit
        ecart += 24 * 60
    return round(ecart / 60.0, 4)


def est_poste_nuit(poste: dict) -> bool:
    """Vrai si le poste est un poste de nuit.

    Est considéré de nuit : tout poste qui franchit minuit, ou qui commence à
    20 h ou après, ou qui commence avant 5 h du matin.
    """
    debut = minutes(poste.get("debut", "08:00"))
    fin = minutes(poste.get("fin", "16:00"))
    if fin <= debut:                 # passe minuit
        return True
    if debut >= 20 * 60:             # commence à 20 h ou plus tard
        return True
    if debut < 5 * 60:               # commence avant 5 h du matin
        return True
    return False


def _est_repos(libelle: str) -> bool:
    return str(libelle or "").strip().lower() in LIBELLES_REPOS


def _libelle_jour(t: int) -> str:
    return f"{JOURS_COURTS[t % 7]} (semaine {t // 7 + 1})"


def _index_par_libelle(postes: list[dict]) -> dict:
    table = {}
    for poste in postes or []:
        libelle = str(poste.get("libelle", "")).strip()
        if libelle:
            table[libelle] = poste
    return table


# --- Cœur du vérificateur ------------------------------------------------------------
# Repères annuels pour la compensation des heures au-delà de 35 h par semaine :
#   • une personne travaille environ 46 semaines par an (52 semaines moins 5 semaines de
#     congés annuels et les jours fériés) ;
#   • un jour de réduction du temps de travail vaut 7 heures (35 h réparties sur 5 jours).
SEMAINES_TRAVAILLEES_AN = 46.0
HEURES_JOURNEE_REFERENCE = 7.0


def verifier_trame(trame: dict, regles: dict | None = None) -> dict:
    """Contrôle une trame et rend verdict + manquements + compteurs."""
    r = dict(REGLES_DEFAUT)
    r.update(regles or {})

    postes_par_libelle = _index_par_libelle(trame.get("postes") or [])
    agents = trame.get("agents") or []
    semaines = int(trame.get("semaines") or (len(agents[0].get("jours", [])) // 7 if agents else 0))
    T = semaines * 7

    manquements: list[dict] = []
    informations: list[dict] = []
    compteurs_personnes: list[dict] = []

    def manque(personne, jour, regle, detail):
        manquements.append({"personne": personne, "jour": jour, "regle": regle,
                            "detail": detail})

    total_heures_toutes = 0.0
    total_nuits = 0
    total_we = 0

    for agent in agents:
        nom = agent.get("nom", "?")
        profil = agent.get("profil", "")
        quotite = float(agent.get("quotite", 1.0) or 1.0)
        jours = list(agent.get("jours") or [])[:T]
        if len(jours) < T:
            jours += [""] * (T - len(jours))

        # Séquences de postes jour par jour.
        seq: list[dict | None] = []
        for libelle in jours:
            if _est_repos(libelle):
                seq.append(None)
            else:
                seq.append(postes_par_libelle.get(str(libelle).strip()))

        # --- compteurs de base -----------------------------------------------------
        heures_cycle = round(sum(duree_poste(p) for p in seq if p), 2)
        heures_semaine = round(heures_cycle / semaines, 2) if semaines else 0.0
        jours_travailles = sum(1 for p in seq if p)
        jours_repos = T - jours_travailles
        nuits = sum(1 for p in seq if p and est_poste_nuit(p))
        total_heures_toutes += heures_cycle
        total_nuits += nuits

        # --- règle 1 : amplitude journalière ≤ 10 h (L3121-18) ---------------------
        for t, poste in enumerate(seq):
            if poste is None:
                continue
            duree = duree_poste(poste)
            if duree > float(r["amplitude_max_h"]) + 1e-9:
                manque(nom, _libelle_jour(t), "amplitude journalière",
                       f"{poste.get('libelle')} dure {duree:g} h "
                       f"(maximum {r['amplitude_max_h']:g} h)")

        # --- règle 2 : repos quotidien ≥ 11 h (L3131-1) -----------------------------
        for t, poste in enumerate(seq):
            if poste is None:
                continue
            tsv = (t + 1) % T
            suivant = seq[tsv]
            if suivant is None:
                continue
            fin_min = t * 24 * 60 + minutes(poste.get("debut", "08:00")) + \
                int(round(duree_poste(poste) * 60))
            debut_min = (t + 1) * 24 * 60 + minutes(suivant.get("debut", "08:00"))
            repos_h = (debut_min - fin_min) / 60.0
            if repos_h < float(r["repos_quotidien_min_h"]) - 1e-9:
                manque(nom, _libelle_jour(t), "repos quotidien",
                       f"{poste.get('libelle')} puis {suivant.get('libelle')} : seulement "
                       f"{max(0.0, repos_h):.1f} h de repos "
                       f"(minimum {r['repos_quotidien_min_h']:g} h)")

        # --- règle 3 : 2 jours de repos par semaine (L3131-1) -----------------------
        for w in range(semaines):
            bloc = seq[w * 7:(w + 1) * 7]
            repos_semaine = sum(1 for p in bloc if p is None)
            if repos_semaine < int(r["repos_hebdo_min_jours"]):
                manque(nom, f"semaine {w + 1}", "repos hebdomadaire",
                       f"seulement {repos_semaine} jour(s) de repos "
                       f"(minimum {r['repos_hebdo_min_jours']})")

        # --- règle 4 : au moins un dimanche complet sur deux (L3164-2) --------------
        pas = int(r["un_dimanche_sur_deux"])
        for w in range(semaines):
            dim_courant = seq[w * 7 + 6]
            dim_suivant = seq[((w + 1) % semaines) * 7 + 6]
            if dim_courant is not None and dim_suivant is not None:
                manque(nom, f"semaine {w + 1} et {((w + 1) % semaines) + 1}",
                       "repos dominical",
                       f"deux dimanches travaillés consécutifs "
                       f"(au moins un dimanche complet de repos tous les {pas})")

        # --- règle 5 : durée hebdomadaire moyenne ----------------------------------
        # La durée légale est de 35 h par semaine (L3121-27). Mais dans la fonction
        # publique hospitalière, les postes font souvent plus de 7 h : la semaine dépasse
        # alors 35 h et l'excédent est COMPENSÉ SUR L'ANNÉE par des jours de réduction du
        # temps de travail. Un dépassement n'est donc PAS un manquement : c'est une
        # INFORMATION, et l'outil calcule le nombre de jours à prévoir dans l'année.
        #   Référence annuelle : 1607 h (soit 35 h sur ~46 semaines travaillées, congés
        #   annuels et jours fériés déduits) — Source : Code du travail, article L3121-27
        #   et statut de la fonction publique hospitalière.
        limite_moyenne = float(r["duree_moyenne_max_h"]) * quotite
        if heures_semaine > limite_moyenne + 1e-9:
            surplus_semaine = heures_semaine - limite_moyenne
            surplus_annuel = surplus_semaine * SEMAINES_TRAVAILLEES_AN
            jours_reduction = surplus_annuel / HEURES_JOURNEE_REFERENCE
            informations.append({
                "personne": nom, "regle": "durée hebdomadaire moyenne",
                "detail": f"{heures_semaine:g} h par semaine au lieu de "
                          f"{limite_moyenne:g} h : le surplus ("
                          f"{surplus_semaine:g} h par semaine, soit environ "
                          f"{surplus_annuel:.0f} h par an) est à compenser par des jours de "
                          f"réduction du temps de travail — comptez environ "
                          f"{jours_reduction:.1f} jour(s) de 7 h par an."})

        # --- règle 6 : jamais plus de 48 h sur une semaine (L3121-20) ----------------
        for w in range(semaines):
            h_semaine = round(sum(duree_poste(p) for p in seq[w * 7:(w + 1) * 7] if p), 2)
            if h_semaine > float(r["duree_max_semaine_h"]) + 1e-9:
                manque(nom, f"semaine {w + 1}", "durée hebdomadaire maximale",
                       f"{h_semaine:g} h sur la semaine "
                       f"(maximum {r['duree_max_semaine_h']:g} h)")

        # --- règle 7 : jamais plus de 6 jours consécutifs (L3131-1) ------------------
        max_consecutifs = 0
        if T:
            for depart in range(T):
                serie = 0
                k = 0
                while k < T and seq[(depart + k) % T] is not None:
                    serie += 1
                    k += 1
                max_consecutifs = max(max_consecutifs, serie)
        if max_consecutifs > int(r["max_jours_consecutifs"]):
            manque(nom, "cycle", "jours consécutifs",
                   f"{max_consecutifs} jours travaillés d'affilée "
                   f"(maximum {r['max_jours_consecutifs']})")

        # --- règle 8 : nuits consécutives ≤ 5 (FPH) ---------------------------------
        max_nuits_suite = 0
        if T:
            for depart in range(T):
                serie = 0
                k = 0
                while k < T and seq[(depart + k) % T] is not None and \
                        est_poste_nuit(seq[(depart + k) % T]):
                    serie += 1
                    k += 1
                max_nuits_suite = max(max_nuits_suite, serie)
        if max_nuits_suite > int(r["max_nuits_consecutives"]):
            manque(nom, "cycle", "nuits consécutives",
                   f"{max_nuits_suite} nuits d'affilée "
                   f"(maximum {r['max_nuits_consecutives']})")

        # --- règle 9 : pause dès 6 h de travail (L3121-16) — INFORMATION ------------
        postes_longs = sorted({p.get("libelle") for p in seq
                               if p and duree_poste(p) >= float(r["pause_seuil_h"]) - 1e-9})
        if postes_longs:
            informations.append({
                "personne": nom, "regle": "pause obligatoire",
                "detail": "Une pause d'au moins 20 minutes est obligatoire dès 6 h de "
                          f"travail (art. L3121-16) pour : {', '.join(postes_longs)}."})

        # --- week-ends travaillés (samedi ET dimanche) ------------------------------
        weekends = 0
        for w in range(semaines):
            sam = seq[w * 7 + 5]
            dim = seq[w * 7 + 6]
            if sam is not None and dim is not None:
                weekends += 1
        total_we += weekends

        # --- écart avec les heures légales ------------------------------------------
        heures_legales = round(float(r["duree_moyenne_max_h"]) * quotite * semaines, 2)
        ecart = round(heures_cycle - heures_legales, 2)

        compteurs_personnes.append({
            "nom": nom,
            "profil": profil,
            "quotite": quotite,
            "heures_cycle": heures_cycle,
            "heures_semaine": heures_semaine,
            "heures_legales_cycle": heures_legales,
            "ecart_heures": ecart,
            "jours_travailles": jours_travailles,
            "jours_repos": jours_repos,
            "weekends_travailles": weekends,
            "nuits": nuits,
            "max_jours_consecutifs": max_consecutifs,
            "max_nuits_consecutives": max_nuits_suite,
        })

    nb_personnes = len(agents)
    compteurs = {
        "semaines": semaines,
        "nb_personnes": nb_personnes,
        "heures_semaine_moyenne": round(total_heures_toutes / semaines / nb_personnes, 2)
        if semaines and nb_personnes else 0.0,
        "heures_cycle_total": round(total_heures_toutes, 2),
        "nuits_total": total_nuits,
        "weekends_travailles_total": total_we,
        "par_personne": compteurs_personnes,
    }

    return {
        "conforme": len(manquements) == 0,
        "manquements": manquements,
        "informations": informations,
        "compteurs": compteurs,
        "regles": {cle: r[cle] for cle in REGLES_DEFAUT},
    }
