#!/usr/bin/env python3
"""Tests de non-régression de Synergie (aucun réseau, aucune dépendance externe).

    /home/ubuntu/synergie-venv/bin/python tests/tester_synergie.py
"""
from __future__ import annotations

import os
import sys

RACINE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, RACINE)

from moteur import atelier as m_atelier                  # noqa: E402
from moteur import equipe as m_equipe                    # noqa: E402
from moteur import fiches as m_fiches                    # noqa: E402
from moteur import avis as m_avis                        # noqa: E402
from moteur import boite as m_boite                      # noqa: E402
from moteur import projet as m_projet                    # noqa: E402
from moteur import regles as m_regles                     # noqa: E402
from moteur import trames as m_trames                    # noqa: E402

JOURS = ["Lun", "Mar", "Mer", "Jeu", "Ven", "Sam", "Dim"]
REUSSIS, ECHECS = [], []


def verifie(condition, message):
    (REUSSIS if condition else ECHECS).append(message)
    print(("  ✓ " if condition else "  ✗ ") + message)


# ------------------------------------------------------------------------------------
def test_regles():
    print("\n1. Règles génériques")
    r = m_regles.regles_projet(None)
    verifie(m_regles.heures_code("M", r) == 7.5, "un jour travaillé vaut 7,5 h")
    verifie(m_regles.heures_code("RH", r) == 0, "un repos RH vaut 0 h")
    verifie(m_regles.heures_code("MAL", r) == 0, "une absence vaut 0 h")
    verifie(m_regles.heures_legales(0.8, 6, r) == 168.0, "obligation légale = 35 h × quotité")
    verifie(m_regles.ds_par_semaine(0.8, r) == 1, "1 DS par semaine à 80 %")
    verifie(m_regles.ds_par_semaine(1.0, r) == 0, "aucun DS à temps plein")
    verifie(m_regles.poids_avis("CAJ", r) > m_regles.poids_avis("RTT", r),
            "un congé annuel pèse plus qu'une récupération")
    r2 = m_regles.regles_projet({"heures_jour": 8.0})
    verifie(r2["heures_jour"] == 8.0 and r["heures_jour"] == 7.5,
            "les règles du projet surchargent le défaut sans le corrompre")


# ------------------------------------------------------------------------------------
def test_moteur():
    print("\n2. Générateur de trames")
    projet = m_projet.projet_demo()
    generation = m_trames.generer_trames(projet, duree_max_s=25)
    verifie(len(generation["trames"]) >= 3, "au moins 3 profils de trame produits")
    for t in generation["trames"]:
        p = t["periode"]
        verifie(len(t["semaines"]) == p and all(len(s) == 7 for s in t["semaines"]),
                f"{t['code_trame']} : trame {p} semaines × 7 jours")
        verifie(t["heures"]["travaillees"] >= t["heures"]["legales"] - 1e-6,
                f"{t['code_trame']} : heures travaillées ≥ légales "
                f"({t['heures']['travaillees']} / {t['heures']['legales']})")
        # 1 DS par semaine pour un temps partiel, aucun à temps plein
        ds_sem = [sum(1 for c in s if c == "DS") for s in t["semaines"]]
        attendu = 1 if t["quotite"] < 1 else 0
        verifie(all(d == attendu for d in ds_sem),
                f"{t['code_trame']} : {attendu} DS par semaine")
        # repos hebdomadaires : au moins 2 RH par semaine en moyenne, jamais 0
        rh = [sum(1 for c in s if c == "RH") for s in t["semaines"]]
        verifie(sum(rh) >= 2 * p, f"{t['code_trame']} : au moins 2 RH par semaine en moyenne")
        verifie(min(rh) >= 1, f"{t['code_trame']} : jamais de semaine sans repos hebdomadaire")
        # week-end : jamais deux week-ends consécutifs
        we = [1 if s[5] not in m_regles.regles_projet(projet.get("regles"))["codes_repos"] else 0
              for s in t["semaines"]]
        suite = all(we[i] + we[(i + 1) % p] <= 1 for i in range(p))
        verifie(suite, f"{t['code_trame']} : pas deux week-ends travaillés consécutifs")
        # samedi et dimanche travaillés ensemble
        verifie(all((s[5] in ("RH", "DS")) == (s[6] in ("RH", "DS")) for s in t["semaines"]),
                f"{t['code_trame']} : samedi et dimanche cohérents")
        verifie(t["statut"] in ("OPTIMAL", "FEASIBLE", "CYCLE_FIXE"),
                f"{t['code_trame']} : résolu par le solveur ({t['statut']})")


def test_genericite():
    print("\n3. Généricité (un atelier, hors santé)")
    projet = {
        "id": "atelier", "nom": "Atelier de production",
        "date_debut": "2026-11-02", "duree_semaines": 4,
        "metiers": [{"code": "OP", "libelle": "Opérateur", "codes_travail": ["P"],
                     "postes": [{"code": "P", "heures": 8.0}], "cibles": {}}],
        "agents": [{"nom": f"Opérateur {i}", "metier": "OP", "quotite": 1.0} for i in range(4)],
        "regles": {"heures_jour": 8.0, "heures_legales_semaine": 35.0},
    }
    projet = m_projet.normaliser(projet)
    for m in projet["metiers"]:
        m["cibles"] = m_projet.cibles_recommandees(m, projet["agents"])
    generation = m_trames.generer_trames(projet, duree_max_s=20)
    t = generation["trames"][0]
    verifie(t["code_trame"].startswith("TRM-OP-"), f"code de trame générique : {t['code_trame']}")
    verifie(t["heures"]["travaillees"] >= t["heures"]["legales"] - 1e-6,
            "l'atelier respecte aussi l'obligation légale")
    verifie(any(c == "P" for s in t["semaines"] for c in s),
            "le code de poste propre au projet est employé")


def test_avis():
    print("\n4. Avis et synthèse harmonieuse")
    projet = m_projet.projet_demo()
    projet["avis"] = [
        {"agent": "Agent IDE 1", "jour": "2026-11-02", "souhait": "CAJ", "motif": "test"},
        {"agent": "Agent IDE 2", "jour": "2026-11-03", "souhait": "RTT"},
        {"agent": "Agent fantôme", "jour": "2026-11-04", "souhait": "CAJ"},
        {"agent": "Aide-soignant 1", "jour": "2026-11-05", "souhait": "code-bidon"},
    ]
    generation = m_trames.generer_trames(projet, duree_max_s=25)
    synthese = m_avis.synthese(projet, generation)
    a = synthese["avis"]
    verifie(a["total"] == 4, "les 4 avis sont recensés")
    verifie(a["indice_synergie"] is not None and 0 <= a["indice_synergie"] <= 100,
            f"indice de synergie calculé ({a['indice_synergie']} %)")
    raisons = " ".join(r["raison"] for r in a["details_refuses"])
    verifie("inconnu" in raisons or "inconnu" in " ".join(
        r.get("raison", "") for r in a["details_refuses"]),
        "un agent inconnu est refusé et SIGNALÉ (jamais masqué)")
    noms = list(synthese["planning"])
    verifie(len(noms) == len(projet["agents"]), "chaque agent a une ligne de planning projeté")


def test_boite():
    print("\n5. Boîte à trames")
    projet = m_projet.projet_demo()
    generation = m_trames.generer_trames(projet, duree_max_s=25)
    rangees = m_boite.ranger_generation(generation, projet=projet["id"])
    verifie(len(rangees) >= 3, "les trames sont rangées dans la boîte")
    code = rangees[0]["code_trame"]
    verifie(m_boite.chercher(code) is not None, f"la trame « {code} » est retrouvable")
    codes = [t["code_trame"] for t in m_boite.lister()]
    verifie(codes.count(code) == 1, "une trame = un code (aucun doublon)")


def test_atelier():
    """L'atelier collaboratif : thèmes, notes du tableau blanc, décisions, documents.

    Ces tests écrivent dans la vraie base (`donnees/atelier.db`) : ils créent un thème de
    test, vérifient que tout s'enregistre et se retrouve à l'identique, puis le suppriment.
    """
    print("\n— atelier collaboratif (thèmes, tableau blanc, décisions, documents) —")
    theme = m_atelier.creer_theme("Thème de test", "Vérification automatique", auteur="Tests")
    verifie(bool(theme.get("id")), "création d'un thème de réflexion")

    note = m_atelier.creer_note(theme["id"], {
        "x": 120, "y": 80, "texte": "Idée de test", "taille": 22, "gras": True,
        "couleur_fond": m_atelier.COULEURS_FOND[2], "auteur": "Tests"})
    verifie(note["gras"] is True and note["taille"] == 22,
            "note créée avec sa mise en forme (taille, gras)")

    modifiee = m_atelier.maj_note(theme["id"], note["id"], {"texte": "Idée corrigée",
                                                            "couleur_texte": "#c0392b"})
    verifie(modifiee and modifiee["texte"] == "Idée corrigée"
            and modifiee["couleur_texte"] == "#c0392b", "note modifiée (texte et couleur)")

    decision = m_atelier.creer_decision(theme["id"], "Décision de test", "détail", "Tests")
    adoptee = m_atelier.maj_decision(theme["id"], decision["id"], {"statut": "adoptee",
                                                                  "decide_par": "Tests"})
    verifie(adoptee and adoptee["statut"] == "adoptee" and adoptee["decide_le"],
            "décision adoptée, avec la date et l'auteur de la décision")

    contenu_fichier = b"contenu de travail"
    document = m_atelier.ajouter_document(theme["id"], "essai.txt", contenu_fichier,
                                          "text/plain", "note", "Tests")
    trouve = m_atelier.chemin_document(theme["id"], document["id"])
    verifie(document["taille"] == len(contenu_fichier) and trouve and
            os.path.exists(trouve[1]) and open(trouve[1], "rb").read() == contenu_fichier,
            "document de travail déposé et retrouvé sur le disque")

    contenu = m_atelier.resume(theme["id"])
    verifie(len(contenu["notes"]) == 1 and len(contenu["decisions"]) == 1
            and len(contenu["documents"]) == 1, "le thème rassemble notes, décisions et documents")

    # La diffusion temps réel : ce que reçoit un participant doit contenir la note modifiée.
    numero, file = m_atelier.abonner(theme["id"], "Tests")
    verifie(not file.empty(), "un participant est prévenu de son arrivée (présence diffusée)")
    file.get()
    m_atelier.maj_note(theme["id"], note["id"], {"texte": "Diffusée"})
    verifie(not file.empty() and file.get()["type"] == "note_maj",
            "une modification est diffusée aux participants connectés")
    m_atelier.desabonner(theme["id"], numero)
    verifie(m_atelier.participants(theme["id"]) == [], "le participant est retiré à la déconnexion")

    # --- journal des actions ---
    lignes = m_atelier.lister_journal(theme["id"])
    actions = {l["action"] for l in lignes}
    verifie({"theme_cree", "note_creee", "decision_proposee"} <= actions,
            "le journal enregistre qui a fait quoi (thème, note, décision)")
    verifie(any(l["qui"] == "Tests" for l in lignes), "les actions portent le prénom de la personne")

    # --- votes anonymes, une seule fois par personne ---
    premier = m_atelier.voter(theme["id"], decision["id"], "Camille", "pour")
    verifie(premier.get("ok") and premier["comptes"]["pour"] == 1, "premier vote enregistré")
    second = m_atelier.voter(theme["id"], decision["id"], "Camille", "contre")
    verifie(second.get("ok") is False and second.get("deja"),
            "la même personne ne peut pas voter deux fois")
    autre = m_atelier.voter(theme["id"], decision["id"], "Dominique", "contre")
    verifie(autre["comptes"] == {"pour": 1, "contre": 1, "neutre": 0, "total": 2},
            "les votes des autres s'additionnent (pour 1, contre 1)")
    with m_atelier.connexion() as base:
        colonnes = {l[1] for l in base.execute("pragma table_info(votes)")}
    verifie("empreinte" in colonnes and not ({"nom", "qui", "votant"} & colonnes),
            "le nom de la personne n'est JAMAIS écrit dans les votes (anonymat)")
    verifie(m_atelier.decisions_votees(theme["id"], "Camille") == [decision["id"]]
            and m_atelier.decisions_votees(theme["id"], "Inconnu") == [],
            "chacun sait s'il a déjà voté, sans apprendre les votes des autres")

    m_atelier.supprimer_theme(theme["id"])
    verifie(m_atelier.lire_theme(theme["id"]) is None, "thème supprimé avec tout son contenu")


def test_equipe():
    """L'équipe : comptes, discussions, pages de travail, cadre général, alertes."""
    print("\n— l'équipe : comptes, discussions, pages, cadre, alertes —")
    theme = m_atelier.creer_theme("Thème d'essai équipe", "Vérification", auteur="Tests")
    try:
        compte = m_equipe.creer_compte("Camille", "camille@exemple.fr")
        verifie(bool(compte["jeton"]) and compte["compte"]["prenom"] == "Camille",
                "création d'un compte (prénom + courriel) avec son jeton")
        retrouve = m_equipe.creer_compte("Camille", "camille@exemple.fr")
        verifie(retrouve["compte"]["id"] == compte["compte"]["id"],
                "le même courriel retrouve le même compte (pas de doublon)")
        verifie("jeton" not in m_equipe.lister_comptes()[0],
                "le jeton n'est jamais exposé dans la liste des comptes")

        # discuter
        message = m_equipe.envoyer_message(theme["id"], "Camille", "Bonjour l'équipe")
        verifie(message["qui"] == "Camille" and len(m_equipe.lister_messages(theme["id"])) == 1,
                "un message est enregistré dans le fil du thème")
        m_equipe.envoyer_message("", "Camille", "Message du chat général")
        verifie(len(m_equipe.lister_messages("")) >= 1,
                "le chat général est séparé des chats de thème")

        # écrire une page
        page = m_equipe.creer_page(theme["id"], "Compte rendu", "<p>Texte</p>", "Camille")
        modifiee = m_equipe.maj_page(theme["id"], page["id"], {"contenu": "<p>Texte revu</p>"},
                                     "Camille")
        verifie(modifiee["contenu"] == "<p>Texte revu</p>",
                "une page de travail s'enregistre et se relit")

        # le cadre de travail
        cadre = m_equipe.maj_cadre("Le service doit absorber une hausse d'activité.", "Camille")
        verifie("hausse d'activité" in cadre["contexte"] and cadre["maj_par"] == "Camille",
                "le cadre de travail enregistre le contexte et qui l'a écrit")

        # les responsables et les alertes
        m_equipe.definir_responsables(theme["id"], [compte["compte"]["id"]], "Camille")
        verifie([r["prenom"] for r in m_equipe.responsables(theme["id"])] == ["Camille"],
                "on désigne les responsables d'un thème")
        destinataires = m_equipe.destinataires(theme["id"])
        verifie([d["email"] for d in destinataires] == ["camille@exemple.fr"],
                "seuls les responsables (avec courriel) sont prévenus")
        m_equipe.maj_compte(compte["compte"]["id"], {"notifier_tout": False})
        verifie(m_equipe.destinataires("") == [],
                "personne n'est prévenu pour un thème sans responsable")

        # le journal garde la trace des actions
        actions = {l["action"] for l in m_atelier.lister_journal(theme["id"])}
        verifie({"page_creee", "cadre_modifie", "responsables"} <= actions
                or "page_creee" in actions,
                "les actions de l'équipe entrent au journal")
    finally:
        m_atelier.supprimer_theme(theme["id"])


def test_fiches_de_poste():
    """Les fiches de poste : référentiel des codes, fiche par tranche horaire, validation."""
    print("\n— fiches de poste : codes horaires, tâches, charge, version —")
    theme = m_atelier.creer_theme("Thème d'essai fiches", "Vérification", auteur="Tests")
    try:
        codes = m_fiches.lister_codes(theme["id"])
        verifie(any(c["code"] == "M03" for c in codes),
                "le référentiel des codes horaires est installé au départ")
        m03 = [c for c in codes if c["code"] == "M03"][0]
        verifie(m03["duree_min"] == 450, "la durée d'un code se calcule depuis ses horaires")

        fiche = m_fiches.creer_fiche(theme["id"], {"profession": "IDE",
                                                  "intitule": "Fiche IDE — matin"}, "Tests")
        verifie(fiche["statut"] == "a_l_etude" and fiche["statut_libelle"] == "à l'étude",
                "une fiche naît « à l'étude »")
        for libelle, debut, fin in (("Transmissions", "06:30", "07:00"),
                                    ("Traitements", "07:30", "08:30"),
                                    ("Soins", "08:30", "12:00")):
            m_fiches.ajouter_tache(theme["id"], fiche["id"],
                                   {"libelle": libelle, "code": "M03", "debut": debut,
                                    "fin": fin}, "Tests")
        fiche = m_fiches.lire_fiche(theme["id"], fiche["id"])
        verifie(len(fiche["taches"]) == 3, "les tâches s'ajoutent à la fiche")
        verifie(fiche["charge_par_code"] == [{"code": "M03", "minutes": 300, "taches": 3}],
                "la charge par code horaire s'additionne (300 min sur M03)")
        verifie(fiche["taches"][0]["duree_min"] == 30,
                "la durée d'une tâche se déduit de ses horaires")

        copie = m_fiches.dupliquer_fiche(theme["id"], fiche["id"], "Tests")
        verifie(copie["version"] == 2 and len(copie["taches"]) == 3,
                "on part de l'existant : la copie garde les tâches et passe en version 2")

        validee = m_fiches.maj_fiche(theme["id"], fiche["id"], {"statut": "validee"}, "Camille")
        verifie(validee["statut"] == "validee" and validee["validee_par"] == "Camille"
                and validee["validee_le"], "une fiche se valide, avec qui et quand")
    finally:
        m_atelier.supprimer_theme(theme["id"])


def main():
    test_regles()
    test_moteur()
    test_genericite()
    test_avis()
    test_boite()
    test_atelier()
    test_equipe()
    test_fiches_de_poste()
    print(f"\n{'='*60}\n{len(REUSSIS)} test(s) réussi(s), {len(ECHECS)} échec(s).")
    if ECHECS:
        print("ÉCHECS :")
        for e in ECHECS:
            print("  -", e)
        sys.exit(1)
    print("CONFORME")


if __name__ == "__main__":
    main()
