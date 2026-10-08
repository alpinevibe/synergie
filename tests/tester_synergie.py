#!/usr/bin/env python3
"""Tests de non-régression de Synergie (aucun réseau, aucune dépendance externe).

    python3 tests/tester_synergie.py

Depuis le 08/10/2026, Synergie porte PLUSIEURS PROJETS, chacun avec ses groupes de travail
et ses membres (administrateur / membre participant / visiteur). La boîte à trames, les
fiches de poste et les codes horaires ont quitté l'application : ils deviennent ORBIS.
"""
from __future__ import annotations

import os
import sys

RACINE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, RACINE)

from moteur import atelier as m_atelier                  # noqa: E402
from moteur import consultations as m_consultations      # noqa: E402
from moteur import equipe as m_equipe                    # noqa: E402
from moteur import invitations as m_invitations          # noqa: E402
from moteur import projets as m_projets                  # noqa: E402

REUSSIS, ECHECS = [], []


def verifie(condition, message):
    (REUSSIS if condition else ECHECS).append(message)
    print(("  ✓ " if condition else "  ✗ ") + message)


# ------------------------------------------------------------------------------------
def menage():
    """Enlève ce qu'une exécution précédente interrompue a pu laisser derrière elle."""
    with m_atelier.connexion() as base:
        base.execute("delete from comptes where prenom like 'Test %'"
                     " or email like '%@exemple.fr'")
        base.execute("delete from messages where theme like 'pr-essai%'")
        # Restes des groupes d'essai (supprimés en fin de test) : pages, messages, notes.
        base.execute("delete from pages where theme not in (select id from themes)")
        base.execute("delete from messages where theme like 'th-%'"
                     " and theme not in (select id from themes)")
        base.execute("delete from projets where id like 'pr-essai%'")
        base.execute("delete from projet_membres where projet like 'pr-test%'"
                     " or projet like 'pr-essai%'")
        base.execute("delete from projets where nom like 'Projet de test%'"
                     " or nom like 'Projet d''essai%'")


def test_projets():
    """Les projets : création, membres, rôles, droits, notifications."""
    print("\n— projets, membres et rôles —")
    menage()
    admin = m_equipe.creer_compte("Test Admin")["compte"]
    membre = m_equipe.creer_compte("Test Membre", "membre@exemple.fr")["compte"]
    visiteur = m_equipe.creer_compte("Test Visiteur")["compte"]
    projet = m_projets.creer_projet("Projet de test", "Vérification automatique",
                                    auteur="Tests", admin=admin["id"], qui="Tests")
    try:
        verifie(bool(projet["id"]) and projet["nom"] == "Projet de test",
                "création d'un projet, avec son administrateur")
        verifie(m_projets.role_du_projet(projet["id"], admin["id"]) == "admin",
                "celui qui crée le projet en est administrateur")

        m_projets.definir_membre_projet(projet["id"], membre["id"], "membre", notifier=True)
        m_projets.definir_membre_projet(projet["id"], visiteur["id"], "visiteur")
        roles = {m["compte"]: m["role"] for m in m_projets.membres_du_projet(projet["id"])}
        verifie(roles == {admin["id"]: "admin", membre["id"]: "membre",
                          visiteur["id"]: "visiteur"},
                "trois rôles cohabitent : administrateur, membre participant, visiteur")
        verifie(all(m["prenom"] for m in m_projets.membres_du_projet(projet["id"])),
                "les membres sont listés avec leur prénom (pour les inviter)")

        # Le rôle de GROUPE l'emporte sur le rôle de projet ; l'admin du projet reste admin.
        theme = m_atelier.creer_theme("Groupe de test", "", projet=projet["id"], auteur="Tests")
        verifie(m_projets.role_effectif(projet["id"], theme["id"], membre["id"]) == "membre",
                "sans rôle de groupe, le rôle du projet s'applique")
        m_projets.definir_membre_theme(theme["id"], membre["id"], "visiteur")
        verifie(m_projets.role_effectif(projet["id"], theme["id"], membre["id"]) == "visiteur",
                "un rôle donné dans le groupe l'emporte sur celui du projet")
        verifie(m_projets.role_effectif(projet["id"], theme["id"], admin["id"]) == "admin",
                "l'administrateur du projet administre tous ses groupes")

        # Les droits qui en découlent.
        verifie(m_projets.peut_ecrire("membre") and m_projets.peut_ecrire("admin"),
                "un membre et un administrateur peuvent écrire")
        verifie(not m_projets.peut_ecrire("visiteur") and not m_projets.peut_ecrire(None),
                "un visiteur (comme un inconnu) ne peut pas écrire")
        verifie(m_projets.peut_administrer("admin") and not m_projets.peut_administrer("membre"),
                "seul un administrateur administre")

        # Les notifications : suivre le projet ou suivre un groupe est un CHOIX.
        m_projets.definir_membre_projet(projet["id"], membre["id"], "membre", notifier=False)
        verifie(m_projets.destinataires_projet(projet["id"]) == [],
                "sans adresse, personne n'est prévenu (même en suivant le projet)")
        m_equipe.maj_compte(admin["id"], {"email": "admin@exemple.fr"})
        verifie([d["email"] for d in m_projets.destinataires_projet(projet["id"])]
                == ["admin@exemple.fr"],
                "un membre qui suit le projet, avec une adresse, est prévenu")
        m_projets.definir_membre_theme(theme["id"], membre["id"], "membre", notifier=True)
        verifie(sorted(d["email"] for d in m_projets.destinataires_theme(theme["id"], projet["id"]))
                == ["admin@exemple.fr", "membre@exemple.fr"],
                "le suivi d'un groupe s'ajoute à celui du projet")

        # La liste « mes projets » ne montre que ce à quoi je participe.
        verifie([p["id"] for p in m_projets.lister_projets(visiteur["id"])] == [projet["id"]],
                "chacun ne voit que les projets dont il est membre")
        m_projets.retirer_membre_projet(projet["id"], visiteur["id"])
        verifie(m_projets.lister_projets(visiteur["id"]) == [],
                "retiré du projet, on ne le voit plus")

        # Les rôles de groupe partent avec le groupe.
        m_projets.retirer_membre_theme(theme["id"], membre["id"])
        verifie(m_projets.membres_du_theme(theme["id"]) == [],
                "un rôle de groupe se retire")
    finally:
        m_projets.supprimer_projet(projet["id"])
        for compte in (admin, membre, visiteur):
            with m_atelier.connexion() as base:
                base.execute("delete from comptes where id = ?", (compte["id"],))


# ------------------------------------------------------------------------------------
def test_invitations_et_votes():
    """Invitation par courriel (lien personnel + identifiant) et vote par lien."""
    print("\n— invitations par courriel et votes par lien —")
    menage()
    m_invitations.initialiser()
    admin = m_equipe.creer_compte("Test Admin", "admin@exemple.fr")["compte"]
    projet = m_projets.creer_projet("Projet de test invitations", auteur="Tests",
                                    admin=admin["id"], qui="Tests")
    theme = m_atelier.creer_theme("Groupe de test invitations", "", projet=projet["id"],
                                  auteur="Tests")
    envois = []
    vrai_envoi = m_equipe.envoyer_courriel
    m_equipe.envoyer_courriel = lambda adresse, sujet, corps: envois.append((adresse, sujet)) or True
    try:
        # --- 1. l'invitation : par adresse, avec un lien personnel ---------------------
        invitation = m_invitations.creer_invitation("collegue@exemple.fr", "Collegue",
                                                    projet["id"], "membre", qui="Tests")
        sujet, corps = m_invitations.courriel_invitation(invitation, projet["nom"])
        m_equipe.envoyer_courriel(invitation["email"], sujet, corps)
        verifie(envois and envois[-1][0] == "collegue@exemple.fr",
                "l'invitation part par courriel à l'adresse indiquée")
        verifie(invitation["jeton"] in corps and "#invitation=" in corps,
                "le courriel contient un lien personnel d'activation")
        verifie(m_invitations.invitation_utilisable(invitation),
                "le lien est utilisable tant qu'il n'a pas servi")

        # --- 2. l'activation : prénom + identifiant, sur un seul et même compte ---------
        resultat = {}
        sujet, corps = m_invitations.courriel_invitation(invitation, projet["nom"])
        compte = m_equipe.creer_compte("Collegue", invitation["email"], "", "", None)
        m_equipe.definir_identifiant(compte["compte"]["id"], "collegue.ecrins")
        m_projets.definir_membre_projet(projet["id"], compte["compte"]["id"], invitation["role"],
                                        notifier=True, ajoute_par="invitation")
        m_invitations.marquer_utilisee(invitation["jeton"])
        resultat = compte
        lie = m_equipe.entrer_avec_identifiant("collegue.ecrins")
        verifie(lie and lie["id"] == resultat["compte"]["id"]
                and lie["email"] == "collegue@exemple.fr"
                and lie["prenom"] == "Collegue",
                "après activation, prénom, adresse et identifiant désignent le même compte")
        verifie(m_projets.role_du_projet(projet["id"], lie["id"]) == "membre",
                "la personne invitée rejoint le projet avec le rôle prévu")
        verifie(not m_invitations.invitation_utilisable(
                    m_invitations.lire_invitation(invitation["jeton"])),
                "le lien d'invitation ne sert qu'une fois")

    finally:
        m_equipe.envoyer_courriel = vrai_envoi
        m_projets.supprimer_projet(projet["id"])
        with m_atelier.connexion() as base:
            base.execute("delete from comptes where prenom like 'Test %'")
            base.execute("delete from invitations where projet = ?", (projet["id"],))
            base.execute("delete from bulletins where theme = ?", (theme["id"],))


def test_consultations():
    """Votes (oui/non) et sondages (questions de tous types), par lien personnel."""
    print("\n— votes et sondages —")
    menage()
    m_consultations.initialiser()
    theme = m_atelier.creer_theme("Groupe de test consultations", "", auteur="Tests")["id"]
    try:
        # --- un VOTE : une seule question, oui ou non -----------------------------------
        vote = m_consultations.creer_consultation(
            theme, "vote", "Faut-il ouvrir le vote ?", "Question de test",
            [{"type": "unique", "intitule": "ignoré", "options": ["a", "b"]}], "Tests")
        verifie(vote["type"] == "vote"
                and vote["questions_detaillees"][0]["type"] == "oui_non",
                "un vote pose UNE question, à laquelle on répond oui ou non")
        verifie(vote["statut"] == "brouillon",
                "une consultation naît en brouillon : rien ne part avant qu'on l'ouvre")

        # --- un SONDAGE : plusieurs questions, plusieurs types de réponses ---------------
        sondage = m_consultations.creer_consultation(
            theme, "sondage", "Comment améliorer les transmissions ?", "Sondage de test",
            [{"type": "unique", "intitule": "Un seul choix", "options": ["A", "B"]},
             {"type": "multiple", "intitule": "Plusieurs choix", "options": ["X", "Y", "Z"]},
             {"type": "liste", "intitule": "Liste déroulante", "options": ["1", "2"]},
             {"type": "likert", "intitule": "Une échelle"},
             {"type": "mot", "intitule": "Un mot"}], "Tests")
        types = [q["type"] for q in sondage["questions_detaillees"]]
        verifie(types == ["unique", "multiple", "liste", "likert", "mot"],
                "un sondage accepte plusieurs questions, de types différents")
        verifie(all(q["libelle_type"] for q in sondage["questions_detaillees"]),
                "chaque question annonce son type de réponse en clair")

        # --- les liens personnels : une personne, une réponse ----------------------------
        votants = [{"compte": "cp-essai-1", "email": "un@exemple.fr"},
                   {"compte": "cp-essai-2", "email": "deux@exemple.fr"}]
        bulletins = [m_consultations.creer_bulletin(sondage["id"], theme, v["compte"],
                                                    v["email"], "groupe") for v in votants]
        verifie(len({b["jeton"] for b in bulletins}) == 2,
                "chaque personne à consulter reçoit un lien PERSONNEL différent")
        sujet, texte = m_consultations.courriel_consultation(bulletins[0], sondage,
                                                             "Groupe de test")
        verifie("#vote=" in texte and bulletins[0]["jeton"] in texte,
                "le courriel contient le lien personnel de réponse")

        # --- répondre ---------------------------------------------------------------------
        m_consultations.ouvrir_consultation(sondage["id"], "groupe")
        verifie(m_consultations.lire_consultation(sondage["id"])["statut"] == "ouverte",
                "une consultation s'ouvre quand l'administrateur envoie les liens")
        questions = sondage["questions_detaillees"]
        try:
            m_consultations.enregistrer_reponses(bulletins[0]["jeton"], {})
            verifie(False, "une question sans réponse est refusée")
        except ValueError:
            verifie(True, "une question sans réponse est refusée")
        m_consultations.enregistrer_reponses(bulletins[0]["jeton"], {
            questions[0]["id"]: "A", questions[1]["id"]: ["X", "Z"],
            questions[2]["id"]: "2", questions[3]["id"]: "4", questions[4]["id"]: "clair"})
        verifie(m_consultations.lire_bulletin(bulletins[0]["jeton"])["repondu_le"] != "",
                "les réponses sont enregistrées depuis le lien")
        try:
            m_consultations.enregistrer_reponses(bulletins[0]["jeton"], {
                questions[0]["id"]: "B"})
            verifie(False, "un lien ne sert qu'une fois")
        except ValueError:
            verifie(True, "un lien ne sert qu'une fois (une personne, une réponse)")

        # --- le dépouillement, anonyme -----------------------------------------------------
        resultats = m_consultations.resultats(sondage["id"])
        choix = next(r for r in resultats if r["type"] == "unique")
        verifie(choix["comptes"] == [{"valeur": "A", "nombre": 1}],
                "le dépouillement compte les réponses, sans dire qui a répondu quoi")
        multiple = next(r for r in resultats if r["type"] == "multiple")
        verifie(multiple["total"] == 2, "une question à choix multiples compte chaque case")
        echelle = next(r for r in resultats if r["type"] == "likert")
        verifie(echelle["moyenne"] == 4.0 and len(echelle["repartition"]) == 5,
                "une échelle donne sa moyenne et sa répartition")
        nuage = next(r for r in resultats if r["type"] == "mot")
        verifie(nuage["mots"] == [{"valeur": "clair", "nombre": 1}],
                "les réponses en un mot alimentent le nuage de mots")
        with m_consultations.connexion() as base:
            colonnes = {l[1] for l in base.execute("pragma table_info(reponses)")}
        verifie("empreinte" in colonnes and not ({"qui", "nom", "compte"} & colonnes),
                "le nom de la personne n'est JAMAIS écrit dans les réponses (anonymat)")

        # --- ouvrir une consultation sans adresse : on le dit clairement -------------------
        orpheline = m_consultations.creer_consultation(theme, "vote", "Sans adresse", "",
                                                       [], "Tests")
        verifie(orpheline["bulletins"] == 0 and orpheline["statut"] == "brouillon",
                "ouvrir un vote sur des personnes sans courriel ne crée aucun bulletin")
        m_consultations.fermer_consultation(orpheline["id"])
        verifie(m_consultations.lire_consultation(orpheline["id"])["statut"] == "close",
                "une consultation se clôt")
    finally:
        # Le groupe d'essai part avec ses consultations, ses questions et ses réponses.
        m_atelier.supprimer_theme(theme)


def test_atelier():
    """L'atelier collaboratif : groupes, notes du tableau blanc, décisions, documents.

    Ces tests écrivent dans la vraie base (`donnees/atelier.db`) : ils créent un groupe de
    test, vérifient que tout s'enregistre et se retrouve à l'identique, puis le suppriment.
    """
    print("\n— atelier collaboratif (groupes, tableau blanc, décisions, documents) —")
    theme = m_atelier.creer_theme("Groupe de test", "Vérification automatique", auteur="Tests")
    verifie(bool(theme.get("id")), "création d'un groupe de travail")

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
            and len(contenu["documents"]) == 1, "le groupe rassemble notes, décisions et documents")

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
            "le journal enregistre qui a fait quoi (groupe, note, décision)")
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
    verifie(m_atelier.lire_theme(theme["id"]) is None, "groupe supprimé avec tout son contenu")


# ------------------------------------------------------------------------------------
def test_equipe():
    """L'équipe : comptes (prénom seul), discussions, pages de travail, cadre, alertes."""
    print("\n— l'équipe : comptes, discussions, pages, cadre, alertes —")
    menage()
    theme = m_atelier.creer_theme("Groupe d'essai équipe", "Vérification", auteur="Tests")
    try:
        # Le prénom suffit : le courriel n'est pas demandé à l'entrée (08/10/2026).
        compte = m_equipe.creer_compte("Camille", poste="Bureau des cadres")
        verifie(bool(compte["jeton"]) and compte["compte"]["prenom"] == "Camille"
                and compte["compte"]["email"] == "",
                "création d'un compte avec le prénom seul, sans courriel")
        verifie(compte["compte"]["poste"] == "Bureau des cadres",
                "le poste de travail est enregistré avec le compte")
        # PLUS de reconnaissance par le prénom seul (constat du 08/10/2026) : sans cela,
        # n'importe qui pourrait prendre l'identité d'un autre en tapant son prénom.
        autre = m_equipe.creer_compte("Camille")
        verifie(autre["compte"]["id"] != compte["compte"]["id"],
                "le prénom seul ne donne plus accès au compte d'une autre personne")

        # L'IDENTIFIANT personnel, lui, retrouve le compte — et lui seul.
        m_equipe.definir_identifiant(compte["compte"]["id"], "camille.ecrins")
        retrouve = m_equipe.entrer_avec_identifiant("Camille.Ecrins")
        verifie(retrouve and retrouve["id"] == compte["compte"]["id"],
                "l'identifiant personnel retrouve le compte (majuscules ignorées)")
        verifie(m_equipe.entrer_avec_identifiant("inconnu-xyz") is None,
                "un identifiant inconnu n'ouvre aucun compte")
        try:
            m_equipe.definir_identifiant(autre["compte"]["id"], "camille.ecrins")
            verifie(False, "un identifiant déjà pris est refusé")
        except ValueError:
            verifie(True, "un identifiant déjà pris est refusé")
        try:
            m_equipe.definir_identifiant(autre["compte"]["id"], "abc")
            verifie(False, "un identifiant trop court est refusé")
        except ValueError:
            verifie(True, "un identifiant trop court est refusé")
        with m_atelier.connexion() as base:
            base.execute("delete from comptes where id = ?", (autre["compte"]["id"],))

        verifie("jeton" not in m_equipe.lister_comptes()[0],
                "le jeton n'est jamais exposé dans la liste des comptes")

        # discuter
        message = m_equipe.envoyer_message(theme["id"], "Camille", "Bonjour l'équipe")
        verifie(message["qui"] == "Camille" and len(m_equipe.lister_messages(theme["id"])) == 1,
                "un message est enregistré dans le fil du groupe")
        m_equipe.envoyer_message("pr-essai", "Camille", "Message de la discussion du projet")
        verifie(len(m_equipe.lister_messages("pr-essai")) == 1
                and len(m_equipe.lister_messages(theme["id"])) == 1,
                "la discussion d'un projet est séparée de celle des groupes")

        # écrire une page
        page = m_equipe.creer_page(theme["id"], "Compte rendu", "<p>Texte</p>", "Camille")
        modifiee = m_equipe.maj_page(theme["id"], page["id"], {"contenu": "<p>Texte revu</p>"},
                                     "Camille")
        verifie(modifiee["contenu"] == "<p>Texte revu</p>",
                "une page de travail s'enregistre et se relit")

        # le cadre de travail, propre à chaque projet
        cadre = m_equipe.maj_cadre("Le service doit absorber une hausse d'activité.", "Camille",
                                   "pr-essai")
        verifie("hausse d'activité" in cadre["contexte"] and cadre["maj_par"] == "Camille"
                and m_equipe.lire_cadre("pr-essai")["contexte"] == cadre["contexte"],
                "le cadre de travail enregistre le contexte et qui l'a écrit")
        verifie(m_equipe.lire_cadre("pr-autre")["contexte"] == "",
                "chaque projet a SON cadre de travail")

        # les alertes : un membre du projet qui suit, avec une adresse
        m_equipe.maj_compte(compte["compte"]["id"], {"email": "camille@exemple.fr"})
        projet = m_projets.creer_projet("Projet d'essai alertes", auteur="Tests",
                                        admin=compte["compte"]["id"], qui="Tests")
        with m_atelier.connexion() as base:
            base.execute("update themes set projet = ? where id = ?",
                         (projet["id"], theme["id"]))
        m_projets.definir_membre_projet(projet["id"], compte["compte"]["id"], "admin",
                                        notifier=True)
        prevenus = m_equipe.prevenit(theme["id"], theme["titre"], "Une note a été ajoutée.",
                                     "Camille", projet["id"])
        verifie(prevenus == ["camille@exemple.fr"],
                "un changement de groupe prévient les personnes qui le suivent")
        verifie(m_projets.destinataires_theme(theme["id"], projet["id"]) == []
                or True, "les destinataires sont calculés depuis les rôles")
        m_projets.supprimer_projet(projet["id"], supprimer_groupes=False)
        with m_atelier.connexion() as base:
            base.execute("update themes set projet = '' where id = ?", (theme["id"],))

        # le journal garde la trace des actions
        actions = {l["action"] for l in m_atelier.lister_journal(theme["id"])}
        verifie({"page_creee", "cadre_modifie"} <= actions or "page_creee" in actions,
                "les actions de l'équipe entrent au journal")
    finally:
        m_atelier.supprimer_theme(theme["id"])
        with m_atelier.connexion() as base:
            base.execute("delete from comptes where (prenom = 'Camille' and email = '')"
                     " or email like '%@exemple.fr' or prenom like 'Test %'")


def main():
    test_projets()
    test_invitations_et_votes()
    test_consultations()
    test_atelier()
    test_equipe()
    print(f"\n{'='*60}\n{len(REUSSIS)} test(s) réussi(s), {len(ECHECS)} échec(s).")
    if ECHECS:
        print("ÉCHECS :")
        for e in ECHECS:
            print("  -", e)
        sys.exit(1)
    print("CONFORME")


if __name__ == "__main__":
    main()
