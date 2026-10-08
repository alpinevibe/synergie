#!/usr/bin/env python3
"""SYNERGIE — serveur (API + interface).

Lancement :  ./run.sh          (ou)  python serveur.py --port 8077
"""
from __future__ import annotations

import argparse
import json
import os
import queue
import sys

from flask import (Flask, Response, abort, jsonify, request, send_file,
                   send_from_directory)

RACINE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, RACINE)

from moteur import atelier as m_atelier                 # noqa: E402
from moteur import consultations as m_consultations     # noqa: E402
from moteur import equipe as m_equipe                   # noqa: E402
from moteur import invitations as m_invitations         # noqa: E402
from moteur import projets as m_projets                 # noqa: E402

WEB = os.path.join(RACINE, "web")
app = Flask(__name__, static_folder=None)


# --- Interface ----------------------------------------------------------------------
@app.route("/")
def accueil():
    return send_from_directory(WEB, "index.html")


@app.route("/<path:chemin>")
def statique(chemin):
    return send_from_directory(WEB, chemin)


# --- API ----------------------------------------------------------------------------
@app.route("/api/sante")
def sante():
    return jsonify({"application": "Synergie", "version": "2.0.0"})




# ====================================================================================
# ATELIER COLLABORATIF — thèmes de réflexion, tableau blanc, documents, décisions
# ====================================================================================
def _qui() -> str:
    """Le prénom de la personne qui agit : envoyé par la page dans l'en-tête
    « X-Synergie-Nom ». Il sert à journaliser les actions (demande du 05/10/2026)."""
    jeton = _jeton()
    if jeton:
        compte = m_equipe.lire_compte(jeton)
        if compte and compte.get("prenom"):
            return compte["prenom"][:60]
    nom = (request.headers.get("X-Synergie-Nom") or "").strip()
    if not nom:
        corps = request.get_json(silent=True) or {}
        nom = (corps.get("auteur") or corps.get("qui") or "").strip()
    return nom[:60] or "Anonyme"


def _jeton() -> str:
    """Le trousseau du navigateur : en-tête des appels ordinaires, COOKIE pour le flux
    temps réel (un « EventSource » ne peut pas porter d'en-tête personnalisé)."""
    return (request.headers.get("X-Synergie-Jeton")
            or request.args.get("jeton")
            or request.cookies.get("synergie")
            or "")


def _compte(requis: bool = False) -> dict | None:
    """Le compte de la personne qui agit, retrouvé grâce au jeton du navigateur."""
    jeton = _jeton()
    compte = m_equipe.lire_compte(jeton) if jeton else None
    if compte is None and requis:
        abort(401, description="Compte inconnu : créez votre compte dans Synergie.")
    return compte


def _avec_cookie(reponse, jeton: str):
    """Pose le jeton en COOKIE : c'est ce qui authentifie le flux temps réel (un
    « EventSource » ne peut pas porter d'en-tête personnalisé)."""
    if jeton:
        reponse.set_cookie("synergie", jeton, httponly=True, samesite="Lax",
                           max_age=60 * 60 * 24 * 365)
    return reponse


def _prevenir(identifiant: str, resume: str) -> None:
    """Prévient par courriel les personnes qui suivent ce groupe — ou tout le projet."""
    theme = m_atelier.lire_theme(identifiant)
    if theme:
        m_equipe.prevenit(identifiant, theme["titre"], resume, _qui(),
                          theme.get("projet") or "")


def _theme(identifiant: str, ecriture: bool = False) -> dict:
    """Le groupe demandé, après vérification des droits de la personne qui agit.

    Lecture : il faut être membre du projet (ou du groupe). Écriture : il faut être
    « membre participant » ou « administrateur » — un visiteur ne modifie rien.
    """
    theme = m_atelier.lire_theme(identifiant)
    if not theme:
        abort(404, description="Groupe inconnu.")
    compte = _compte(requis=True)
    role = m_projets.role_effectif(theme.get("projet") or "", identifiant, compte["id"])
    if role is None:
        abort(403, description="Vous n'avez pas accès à ce groupe de travail.")
    if ecriture and not m_projets.peut_ecrire(role):
        abort(403, description="Votre rôle de visiteur ne permet pas de modifier ce groupe.")
    request.role_theme = role
    return theme


def _projet(identifiant: str, ecriture: bool = False) -> dict:
    """Le projet demandé, après vérification des droits."""
    projet = m_projets.lire_projet(identifiant)
    if not projet:
        abort(404, description="Projet inconnu.")
    compte = _compte(requis=True)
    role = m_projets.role_du_projet(identifiant, compte["id"])
    if role is None:
        abort(403, description="Vous n'êtes pas membre de ce projet.")
    if ecriture and not m_projets.peut_administrer(role):
        abort(403, description="Seul un administrateur du projet peut faire cette action.")
    request.role_projet = role
    return projet


def _compte_a_ajouter(corps: dict) -> dict:
    """La personne à inviter : un compte existant, ou un compte créé à la volée."""
    corps = corps or {}
    if corps.get("compte"):
        for compte in m_equipe.lister_comptes():
            if compte["id"] == corps["compte"]:
                return compte
        abort(404, description="Compte inconnu.")
    prenom = (corps.get("prenom") or "").strip()
    if not prenom:
        abort(400, description="Indiquez le prénom de la personne à inviter.")
    return m_equipe.creer_compte(prenom, (corps.get("email") or "").strip())["compte"]


@app.route("/api/atelier/sante")
def api_atelier_sante():
    return jsonify(m_atelier.sante())


# ====================================================================================
# PROJETS — un projet rassemble des groupes de travail, et des membres avec un rôle
# ====================================================================================
@app.route("/api/projets", methods=["GET", "POST"])
def api_projets():
    """GET : les projets dont je suis membre. POST : créer un projet (j'en suis l'admin)."""
    compte = _compte(requis=True)
    if request.method == "POST":
        corps = request.get_json(silent=True) or {}
        nom = (corps.get("nom") or "").strip()
        if not nom:
            return jsonify({"erreur": "Le nom du projet est obligatoire."}), 400
        projet = m_projets.creer_projet(nom, corps.get("description", ""), compte["prenom"],
                                        admin=compte["id"], qui=compte["prenom"])
        m_atelier.journaliser("", compte["prenom"], "projet_cree", projet["id"], nom,
                              diffuser_aussi=False)
        return jsonify(projet), 201
    projets = m_projets.lister_projets(compte["id"])
    for projet in projets:
        projet["role"] = projet.get("role") or "membre"
        projet["libelle_role"] = m_projets.LIBELLES_ROLES.get(projet["role"], projet["role"])
    return jsonify({"projets": projets,
                    "roles": [{"cle": r, "libelle": m_projets.LIBELLES_ROLES[r],
                               "description": m_projets.DESCRIPTIONS_ROLES[r]}
                              for r in m_projets.ROLES]})


@app.route("/api/projets/<identifiant>", methods=["GET", "PUT", "DELETE"])
def api_projet(identifiant):
    if request.method == "DELETE":
        _projet(identifiant, ecriture=True)
        m_projets.supprimer_projet(identifiant)
        return jsonify({"ok": True})
    if request.method == "PUT":
        _projet(identifiant, ecriture=True)
        return jsonify(m_projets.maj_projet(identifiant, request.get_json(silent=True) or {},
                                            _qui()))
    projet = _projet(identifiant)
    compte = _compte(requis=True)
    return jsonify({
        "projet": projet,
        "role": m_projets.role_du_projet(identifiant, compte["id"]),
        "groupes": m_atelier.lister_themes(projet=identifiant),
        "membres": m_projets.membres_du_projet(identifiant),
        "roles": [{"cle": r, "libelle": m_projets.LIBELLES_ROLES[r],
                   "description": m_projets.DESCRIPTIONS_ROLES[r]} for r in m_projets.ROLES],
    })


@app.route("/api/projets/<identifiant>/membres", methods=["POST"])
def api_projet_membre(identifiant):
    """Inviter ou régler une personne du projet : rôle et notifications."""
    _projet(identifiant, ecriture=True)
    corps = request.get_json(silent=True) or {}
    compte = _compte_a_ajouter(corps)
    role = corps.get("role") or "membre"
    if role not in m_projets.ROLES:
        return jsonify({"erreur": "Rôle inconnu."}), 400
    membre = m_projets.definir_membre_projet(
        identifiant, compte["id"], role,
        bool(corps.get("notifier")),
        ajoute_par=_qui())
    m_atelier.journaliser("", _qui(), "projet_membre", identifiant,
                          f"{compte['prenom']} · {m_projets.LIBELLES_ROLES[role]}",
                          diffuser_aussi=False)
    return jsonify(membre), 201


@app.route("/api/projets/<identifiant>/membres/<membre>", methods=["PUT", "DELETE"])
def api_projet_membre_un(identifiant, membre):
    _projet(identifiant, ecriture=True)
    try:
        if request.method == "DELETE":
            m_projets.retirer_membre_projet(identifiant, membre)
            return jsonify({"ok": True})
        corps = request.get_json(silent=True) or {}
        role = corps.get("role")
        if role is not None and role not in m_projets.ROLES:
            return jsonify({"erreur": "Rôle inconnu."}), 400
        notifier = corps.get("notifier")
        return jsonify(m_projets.definir_membre_projet(
            identifiant, membre, role, None if notifier is None else bool(notifier),
            ajoute_par=_qui()))
    except ValueError as erreur:                   # dernier administrateur : on refuse
        return jsonify({"erreur": str(erreur)}), 400


# ====================================================================================
# GROUPES DE TRAVAIL — un groupe appartient à un projet
# ====================================================================================
@app.route("/api/themes", methods=["GET", "POST"])
def api_themes():
    """GET : les groupes des projets dont je suis membre (ou d'un projet donné).
    POST : créer un groupe — il faut administrer le projet."""
    compte = _compte(requis=True)
    if request.method == "POST":
        corps = request.get_json(silent=True) or {}
        titre = (corps.get("titre") or "").strip()
        if not titre:
            return jsonify({"erreur": "Le titre est obligatoire."}), 400
        projet = (corps.get("projet") or "").strip()
        if not projet:
            return jsonify({"erreur": "Choisissez le projet du groupe."}), 400
        _projet(projet, ecriture=True)
        theme = m_atelier.creer_theme(titre, corps.get("description", ""),
                                      corps.get("couleur", ""), projet, _qui())
        return jsonify(theme), 201
    demande = (request.args.get("projet") or "").strip()
    if demande:
        _projet(demande)
        groupes = m_atelier.lister_themes(projet=demande)
    else:
        identifiants = []
        for projet in m_projets.lister_projets(compte["id"]):
            identifiants.extend(t["id"] for t in m_atelier.lister_themes(projet=projet["id"]))
        groupes = m_atelier.lister_themes(identifiants=identifiants)
    return jsonify({"themes": groupes})


@app.route("/api/themes/<identifiant>", methods=["GET", "PUT", "DELETE"])
def api_theme(identifiant):
    if request.method == "DELETE":
        _theme(identifiant)
        projet = m_atelier.lire_theme(identifiant).get("projet") or ""
        if not m_projets.peut_administrer(
                m_projets.role_effectif(projet, identifiant, (_compte(requis=True) or {})["id"])):
            abort(403, description="Seul un administrateur peut supprimer un groupe.")
        m_atelier.supprimer_theme(identifiant)
        return jsonify({"ok": True})
    if request.method == "PUT":
        _theme(identifiant, ecriture=True)
        return jsonify(m_atelier.maj_theme(identifiant, request.get_json(silent=True) or {},
                                           _qui()))
    theme = _theme(identifiant)
    contenu = m_atelier.resume(identifiant, _qui())
    # Le JOURNAL d'un groupe est réservé à ses administrateurs (consigne du 08/10/2026) :
    # les membres du projet et les visiteurs voient tout le reste, pas le journal.
    if not m_projets.peut_administrer(getattr(request, "role_theme", None)):
        contenu["journal"] = []
    contenu["membres"] = m_projets.membres_du_theme(identifiant)
    contenu["role"] = getattr(request, "role_theme", None)
    contenu["role_projet"] = m_projets.role_du_projet(
        theme.get("projet") or "", (_compte(requis=True) or {})["id"])
    contenu["roles"] = [{"cle": r, "libelle": m_projets.LIBELLES_ROLES[r],
                         "description": m_projets.DESCRIPTIONS_ROLES[r]}
                        for r in m_projets.ROLES]
    return jsonify(contenu)


@app.route("/api/themes/<identifiant>/membres", methods=["GET", "POST"])
def api_theme_membres(identifiant):
    """Qui participe à ce groupe, et avec quel rôle."""
    if request.method == "GET":
        _theme(identifiant)
        return jsonify({"membres": m_projets.membres_du_theme(identifiant)})
    theme = _theme(identifiant)
    projet = theme.get("projet") or ""
    if not m_projets.peut_administrer(
            m_projets.role_effectif(projet, identifiant, (_compte(requis=True) or {})["id"])):
        abort(403, description="Seul un administrateur du groupe peut inviter.")
    corps = request.get_json(silent=True) or {}
    compte = _compte_a_ajouter(corps)
    role = corps.get("role") or "membre"
    if role not in m_projets.ROLES:
        return jsonify({"erreur": "Rôle inconnu."}), 400
    membre = m_projets.definir_membre_theme(identifiant, compte["id"], role,
                                            bool(corps.get("notifier")), ajoute_par=_qui())
    return jsonify(membre), 201


@app.route("/api/themes/<identifiant>/membres/<membre>", methods=["PUT", "DELETE"])
def api_theme_membre_un(identifiant, membre):
    theme = _theme(identifiant)
    projet = theme.get("projet") or ""
    if not m_projets.peut_administrer(
            m_projets.role_effectif(projet, identifiant, (_compte(requis=True) or {})["id"])):
        abort(403, description="Seul un administrateur du groupe peut modifier les rôles.")
    if request.method == "DELETE":
        m_projets.retirer_membre_theme(identifiant, membre)
        return jsonify({"ok": True})
    corps = request.get_json(silent=True) or {}
    role = corps.get("role")
    if role is not None and role not in m_projets.ROLES:
        return jsonify({"erreur": "Rôle inconnu."}), 400
    notifier = corps.get("notifier")
    return jsonify(m_projets.definir_membre_theme(
        identifiant, membre, role, None if notifier is None else bool(notifier),
        ajoute_par=_qui()))


@app.route("/api/themes/<identifiant>/notes", methods=["POST"])
def api_note_creer(identifiant):
    _theme(identifiant, ecriture=True)
    corps = request.get_json(silent=True) or {}
    corps["auteur"] = corps.get("auteur") or _qui()
    return jsonify(m_atelier.creer_note(identifiant, corps)), 201


@app.route("/api/themes/<identifiant>/notes/<note>", methods=["PUT", "DELETE"])
def api_note(identifiant, note):
    _theme(identifiant, ecriture=True)
    if request.method == "DELETE":
        m_atelier.supprimer_note(identifiant, note, _qui())
        return jsonify({"ok": True})
    resultat = m_atelier.maj_note(identifiant, note, request.get_json(silent=True) or {},
                                  _qui())
    if resultat is None:
        return jsonify({"erreur": "Note inconnue"}), 404
    return jsonify(resultat)


@app.route("/api/themes/<identifiant>/decisions", methods=["POST"])
def api_decision_creer(identifiant):
    _theme(identifiant, ecriture=True)
    corps = request.get_json(silent=True) or {}
    if not (corps.get("intitule") or "").strip():
        return jsonify({"erreur": "L'intitulé est obligatoire."}), 400
    return jsonify(m_atelier.creer_decision(identifiant, corps.get("intitule"),
                                            corps.get("detail", ""),
                                            corps.get("auteur") or _qui())), 201


@app.route("/api/themes/<identifiant>/decisions/<decision>", methods=["PUT", "DELETE"])
def api_decision(identifiant, decision):
    _theme(identifiant, ecriture=True)
    if request.method == "DELETE":
        m_atelier.supprimer_decision(identifiant, decision, _qui())
        return jsonify({"ok": True})
    resultat = m_atelier.maj_decision(identifiant, decision,
                                      request.get_json(silent=True) or {}, _qui())
    if resultat is None:
        return jsonify({"erreur": "Décision inconnue"}), 404
    return jsonify(resultat)


@app.route("/api/themes/<identifiant>/decisions/<decision>/votes", methods=["POST"])
def api_voter(identifiant, decision):
    """Vote ANONYME sur une décision : une seule fois par personne. Le nom n'est jamais
    enregistré — seul le serveur peut reconnaître « cette personne a déjà voté »."""
    _theme(identifiant, ecriture=True)
    corps = request.get_json(silent=True) or {}
    try:
        resultat = m_atelier.voter(identifiant, decision, _qui(), corps.get("valeur", ""))
    except ValueError as erreur:
        return jsonify({"erreur": str(erreur)}), 400
    return jsonify(resultat), (200 if resultat.get("ok") else 409)


@app.route("/api/themes/<identifiant>/documents", methods=["POST"])
def api_document_ajouter(identifiant):
    _theme(identifiant, ecriture=True)
    depot = request.files.get("fichier")
    if not depot or not depot.filename:
        return jsonify({"erreur": "Aucun fichier reçu."}), 400
    try:
        document = m_atelier.ajouter_document(
            identifiant, depot.filename, depot.read(), depot.mimetype or "",
            request.form.get("note", ""), request.form.get("auteur") or _qui())
    except ValueError as erreur:
        return jsonify({"erreur": str(erreur)}), 413
    return jsonify(document), 201


@app.route("/api/themes/<identifiant>/documents/<document>/fichier")
def api_document_fichier(identifiant, document):
    trouve = m_atelier.chemin_document(identifiant, document)
    if not trouve:
        abort(404, description="Document inconnu")
    nom, chemin = trouve
    # Toujours proposé en TÉLÉCHARGEMENT, jamais affiché dans le navigateur : un fichier
    # déposé par un participant ne doit pas pouvoir s'exécuter dans l'application.
    return send_file(chemin, as_attachment=True, download_name=nom,
                     mimetype="application/octet-stream")


@app.route("/api/themes/<identifiant>/documents/<document>", methods=["DELETE"])
def api_document_supprimer(identifiant, document):
    _theme(identifiant, ecriture=True)
    m_atelier.supprimer_document(identifiant, document, _qui())
    return jsonify({"ok": True})


@app.route("/api/themes/<identifiant>/curseurs", methods=["POST"])
def api_curseurs(identifiant):
    """« Qui travaille sur quelle note » : relayé aux autres, sans être enregistré."""
    _theme(identifiant, ecriture=True)
    corps = request.get_json(silent=True) or {}
    m_atelier.diffuser(identifiant, {
        "type": "curseur", "qui": corps.get("qui", ""), "note": corps.get("note")})
    return jsonify({"ok": True})


@app.route("/api/themes/<identifiant>/evenements")
def api_evenements(identifiant):
    """Flux temps réel (Server-Sent Events) : tout ce qui se passe dans le thème arrive ici
    sans que le navigateur ait à redemander quoi que ce soit."""
    _theme(identifiant)
    nom = request.args.get("nom") or "Anonyme"
    numero, file = m_atelier.abonner(identifiant, nom)

    def flux():
        try:
            yield "retry: 3000\n\n"
            yield ("data: " + json.dumps(
                {"type": "bonjour", "participants": m_atelier.participants(identifiant)},
                ensure_ascii=False) + "\n\n")
            while True:
                try:
                    evenement = file.get(timeout=15)
                except queue.Empty:
                    yield ": souffle\n\n"          # garde la connexion ouverte
                    continue
                yield "data: " + json.dumps(evenement, ensure_ascii=False) + "\n\n"
        finally:
            m_atelier.desabonner(identifiant, numero)

    return Response(flux(), mimetype="text/event-stream",
                    headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no",
                             "Connexion": "keep-alive"})


# ====================================================================================
# L'ÉQUIPE : comptes, discussions, pages de travail, cadre général, fiches de poste
# ====================================================================================
def _mes_notifications(compte_id: str) -> dict:
    """Ce que je suis : mes projets et mes groupes, avec mes rôles et mes alertes."""
    projets = []
    for projet in m_projets.lister_projets(compte_id):
        miens = [m for m in m_projets.membres_du_projet(projet["id"])
                 if m["compte"] == compte_id]
        groupes = []
        for theme in m_atelier.lister_themes(projet=projet["id"]):
            siens = [m for m in m_projets.membres_du_theme(theme["id"])
                     if m["compte"] == compte_id]
            groupes.append({"id": theme["id"], "titre": theme["titre"],
                            "role": siens[0]["role"] if siens else projet["role"],
                            "role_propre": bool(siens),
                            "notifier": bool(siens[0]["notifier"]) if siens else False})
        projets.append({"id": projet["id"], "nom": projet["nom"], "role": projet["role"],
                        "notifier": bool(miens[0]["notifier"]) if miens else False,
                        "groupes": groupes})
    return {"projets": projets}


@app.route("/api/comptes", methods=["GET", "POST"])
def api_comptes():
    """POST : créer (ou retrouver) son compte — seul le PRÉNOM est demandé → rend un jeton.
    GET : la liste des comptes connus, pour inviter quelqu'un dans un projet."""
    if request.method == "POST":
        corps = request.get_json(silent=True) or {}
        try:
            resultat = m_equipe.creer_compte(corps.get("prenom", ""), corps.get("email", ""),
                                             corps.get("poste", ""), corps.get("appareil", ""),
                                             corps.get("jeton"))
        except ValueError as erreur:
            return jsonify({"erreur": str(erreur)}), 400
        return _avec_cookie(jsonify(resultat), resultat["jeton"]), 201
    _compte(requis=True)
    return jsonify({"comptes": m_equipe.lister_comptes()})


@app.route("/api/comptes/moi", methods=["GET", "PUT"])
def api_mon_compte():
    """Mon compte : prénom, poste de travail, courriel d'alerte (facultatif) et ce que je suis."""
    compte = _compte(requis=True)
    if request.method == "PUT":
        corps = request.get_json(silent=True) or {}
        compte = m_equipe.maj_compte(compte["id"], corps) or compte
    return jsonify({"compte": compte, "notifications": _mes_notifications(compte["id"])})


# ====================================================================================
# INVITATIONS — on invite par ADRESSE : la personne active son compte, puis entre avec
# son IDENTIFIANT personnel (personne ne peut prendre l'identité d'un autre).
# ====================================================================================
@app.route("/api/projets/<identifiant>/invitations", methods=["GET", "POST"])
def api_invitations(identifiant):
    projet = _projet(identifiant, ecriture=True)
    if request.method == "GET":
        return jsonify({"invitations": m_invitations.lister_invitations(identifiant)})
    corps = request.get_json(silent=True) or {}
    role = corps.get("role") or "membre"
    if role not in m_projets.ROLES:
        return jsonify({"erreur": "Rôle inconnu."}), 400
    try:
        invitation = m_invitations.creer_invitation(
            corps.get("email", ""), corps.get("prenom", ""), identifiant, role,
            corps.get("note", ""), _qui())
    except ValueError as erreur:
        return jsonify({"erreur": str(erreur)}), 400
    sujet, texte = m_invitations.courriel_invitation(invitation, projet["nom"])
    envoye = m_equipe.envoyer_courriel(invitation["email"], sujet, texte)
    m_atelier.journaliser("", _qui(), "invitation", identifiant,
                          f"{invitation['email']} · {m_projets.LIBELLES_ROLES[role]}",
                          diffuser_aussi=False)
    return jsonify({"invitation": invitation, "envoye": envoye}), 201


@app.route("/api/invitations/<jeton>", methods=["GET", "POST"])
def api_invitation(jeton):
    """Le lien reçu par courriel : on lit l'invitation, puis on active son compte."""
    invitation = m_invitations.lire_invitation(jeton)
    if not m_invitations.invitation_utilisable(invitation):
        return jsonify({"erreur": "Ce lien d'invitation n'est plus valable. Demandez-en un "
                                  "nouveau à l'administrateur du projet."}), 410
    projet = m_projets.lire_projet(invitation["projet"])
    if request.method == "GET":
        return jsonify({"invitation": {"email": invitation["email"],
                                       "prenom": invitation["prenom"],
                                       "role": invitation["role"]},
                        "projet": {"id": projet["id"], "nom": projet["nom"]} if projet else None})
    corps = request.get_json(silent=True) or {}
    prenom = (corps.get("prenom") or invitation["prenom"] or "").strip()
    identifiant_ = (corps.get("identifiant") or "").strip()
    if not prenom:
        return jsonify({"erreur": "Indiquez votre prénom."}), 400
    try:
        resultat = m_equipe.creer_compte(prenom, invitation["email"], "", "", None)
        m_equipe.definir_identifiant(resultat["compte"]["id"], identifiant_)
    except ValueError as erreur:
        return jsonify({"erreur": str(erreur)}), 400
    m_projets.definir_membre_projet(invitation["projet"], resultat["compte"]["id"],
                                    invitation["role"], notifier=True,
                                    ajoute_par="invitation")
    m_invitations.marquer_utilisee(jeton)
    m_atelier.journaliser("", prenom, "invitation_activee", invitation["projet"],
                          invitation["email"], diffuser_aussi=False)
    return _avec_cookie(
        jsonify({"compte": resultat["compte"], "jeton": resultat["jeton"],
                 "projet": {"id": projet["id"], "nom": projet["nom"]} if projet else None}),
        resultat["jeton"])


@app.route("/api/connexion", methods=["POST"])
def api_connexion():
    """Entrer avec son IDENTIFIANT personnel (demande du 08/10/2026)."""
    corps = request.get_json(silent=True) or {}
    compte = m_equipe.entrer_avec_identifiant(corps.get("identifiant", ""))
    if not compte:
        return jsonify({"erreur": "Identifiant inconnu. Vérifiez la saisie, ou demandez une "
                                  "invitation à l'administrateur du projet."}), 404
    jeton = m_equipe.jeton_de(compte["id"])
    return _avec_cookie(jsonify({"compte": compte, "jeton": jeton}), jeton)


# ====================================================================================
# VOTES ET SONDAGES — on choisit QUI l'on consulte, chaque personne reçoit son lien
# ====================================================================================
def _consultation(identifiant: str, ecriture: bool = False) -> dict:
    consultation = m_consultations.lire_consultation(identifiant)
    if not consultation:
        abort(404, description="Consultation inconnue.")
    theme = _theme(consultation["theme"], ecriture=ecriture)
    consultation["groupe"] = theme["titre"]
    consultation["projet"] = theme.get("projet") or ""
    return consultation


def _votants(theme: dict, scrutin: str) -> list[dict]:
    """Qui l'on consulte : les membres du groupe, ou tous les membres du projet."""
    projet = theme.get("projet") or ""
    if scrutin == "projet":
        personnes = m_projets.membres_du_projet(projet)
    else:
        personnes = m_projets.membres_du_theme(theme["id"])
        if not personnes:
            personnes = m_projets.membres_du_projet(projet)
    return [{"compte": p["compte"], "email": p["email"]} for p in personnes if p["email"]]


@app.route("/api/themes/<identifiant>/consultations", methods=["GET", "POST"])
def api_consultations(identifiant):
    """Les votes et sondages du groupe ; on en crée un (brouillon, non envoyé)."""
    _theme(identifiant)
    if request.method == "POST":
        _theme(identifiant, ecriture=True)
        corps = request.get_json(silent=True) or {}
        try:
            consultation = m_consultations.creer_consultation(
                identifiant, corps.get("type", "sondage"), corps.get("intitule", ""),
                corps.get("detail", ""), corps.get("questions") or [], _qui())
        except ValueError as erreur:
            return jsonify({"erreur": str(erreur)}), 400
        m_atelier.journaliser(identifiant, _qui(), "consultation_creee", consultation["id"],
                              consultation["intitule"])
        return jsonify(consultation), 201
    return jsonify({"consultations": m_consultations.lister_consultations(identifiant),
                    "types_question": [{"cle": t, "libelle": m_consultations.LIBELLES_QUESTION[t]}
                                       for t in m_consultations.TYPES_QUESTION]})


@app.route("/api/consultations/<identifiant>", methods=["GET", "PUT", "DELETE"])
def api_consultation(identifiant):
    if request.method == "DELETE":
        consultation = _consultation(identifiant, ecriture=True)
        if not m_projets.peut_administrer(getattr(request, "role_theme", None)):
            return jsonify({"erreur": "Seul un administrateur peut supprimer."}), 403
        m_consultations.supprimer_consultation(identifiant)
        return jsonify({"ok": True})
    if request.method == "PUT":
        _consultation(identifiant, ecriture=True)
        return jsonify(m_consultations.maj_consultation(identifiant,
                                                        request.get_json(silent=True) or {}))
    consultation = _consultation(identifiant)
    consultation["resultats"] = (m_consultations.resultats(identifiant)
                                 if consultation["statut"] == "close"
                                 or m_projets.peut_administrer(
                                     getattr(request, "role_theme", None)) else [])
    return jsonify(consultation)


@app.route("/api/consultations/<identifiant>/resultats")
def api_resultats(identifiant):
    consultation = _consultation(identifiant)
    return jsonify({"resultats": m_consultations.resultats(identifiant)})


@app.route("/api/consultations/<identifiant>/ouvrir", methods=["POST"])
def api_ouvrir_consultation(identifiant):
    """Envoie un lien personnel à chaque personne à consulter."""
    consultation = _consultation(identifiant, ecriture=True)
    if not m_projets.peut_administrer(getattr(request, "role_theme", None)):
        return jsonify({"erreur": "Seul un administrateur du groupe peut ouvrir un vote."}), 403
    if consultation["statut"] != "brouillon":
        return jsonify({"erreur": "Cette consultation est déjà ouverte (ou fermée)."}), 400
    corps = request.get_json(silent=True) or {}
    scrutin = "projet" if corps.get("scrutin") == "projet" else "groupe"
    theme = m_atelier.lire_theme(consultation["theme"])
    votants = _votants(theme, scrutin)
    if not votants:
        return jsonify({"erreur": "Personne à consulter : les personnes visées n'ont pas "
                                  "d'adresse de courriel."}), 400
    envoyes = []
    for votant in votants:
        bulletin = m_consultations.creer_bulletin(identifiant, consultation["theme"],
                                                  votant["compte"], votant["email"], scrutin)
        sujet, texte = m_consultations.courriel_consultation(bulletin, consultation,
                                                             theme["titre"])
        m_equipe.envoyer_courriel(bulletin["email"], sujet, texte)
        envoyes.append(bulletin["email"])
    m_consultations.ouvrir_consultation(identifiant, scrutin)
    m_atelier.journaliser(consultation["theme"], _qui(), "consultation_ouverte", identifiant,
                          f"{scrutin} · {len(envoyes)} lien(s)")
    return jsonify({"scrutin": scrutin, "envoyes": envoyes,
                    "consultation": m_consultations.lire_consultation(identifiant)}), 201


@app.route("/api/consultations/<identifiant>/liens")
def api_liens_consultation(identifiant):
    """Les liens personnels, pour les transmettre à la main si le courriel ne passe pas."""
    consultation = _consultation(identifiant)
    if not m_projets.peut_administrer(getattr(request, "role_theme", None)):
        return jsonify({"erreur": "Les liens sont réservés aux administrateurs du groupe."}), 403
    liens = []
    for bulletin in m_consultations.lister_bulletins(identifiant):
        liens.append({"email": bulletin["email"], "compte": bulletin["compte"],
                      "repondu": bool(bulletin["repondu_le"]),
                      "lien": f"{m_equipe.adresse_site()}/#vote={bulletin['jeton']}"})
    return jsonify({"consultation": consultation, "liens": liens})


@app.route("/api/consultations/<identifiant>/fermer", methods=["POST"])
def api_fermer_consultation(identifiant):
    consultation = _consultation(identifiant, ecriture=True)
    if not m_projets.peut_administrer(getattr(request, "role_theme", None)):
        return jsonify({"erreur": "Seul un administrateur peut clore la consultation."}), 403
    m_consultations.fermer_consultation(identifiant)
    m_atelier.journaliser(consultation["theme"], _qui(), "consultation_close", identifiant)
    return jsonify(m_consultations.lire_consultation(identifiant))


@app.route("/api/votes/<jeton>", methods=["GET", "POST"])
def api_vote(jeton):
    """Le lien personnel reçu par courriel : on répond UNE fois."""
    bulletin = m_consultations.lire_bulletin(jeton)
    if not bulletin:
        return jsonify({"erreur": "Ce lien n'existe pas."}), 404
    consultation = m_consultations.lire_consultation(bulletin["consultation"])
    if not consultation:
        return jsonify({"erreur": "Cette consultation n'existe plus."}), 404
    theme = m_atelier.lire_theme(consultation["theme"])
    if request.method == "GET":
        return jsonify({"consultation": {
            "intitule": consultation["intitule"], "detail": consultation["detail"],
            "type": consultation["type"], "statut": consultation["statut"],
            "questions": consultation["questions_detaillees"]},
            "groupe": theme["titre"] if theme else "",
            "scrutin": bulletin["scrutin"],
            "deja_repondu": bool(bulletin["repondu_le"])})
    corps = request.get_json(silent=True) or {}
    try:
        resultat = m_consultations.enregistrer_reponses(jeton, corps.get("reponses") or {})
    except ValueError as erreur:
        return jsonify({"erreur": str(erreur)}), 400
    m_atelier.journaliser(consultation["theme"], "un participant", "consultation_repondue",
                          consultation["id"], consultation["intitule"])
    return jsonify(resultat)


@app.route("/api/notifications", methods=["PUT"])
def api_notifications():
    """Régler mes alertes : par projet entier, ou groupe par groupe."""
    compte = _compte(requis=True)
    corps = request.get_json(silent=True) or {}
    for projet in corps.get("projets") or []:
        if m_projets.role_du_projet(projet.get("id") or "", compte["id"]) is None:
            continue
        m_projets.definir_membre_projet(projet["id"], compte["id"],
                                        notifier=bool(projet.get("notifier")))
    for theme in corps.get("groupes") or []:
        theme_lu = m_atelier.lire_theme(theme.get("id") or "")
        if not theme_lu:
            continue
        projet = theme_lu.get("projet") or ""
        role = m_projets.role_effectif(projet, theme["id"], compte["id"])
        if role is None:
            continue
        # On ne touche PAS au rôle : on garde celui du groupe, ou celui du projet à défaut
        # (créer une ligne de groupe avec le rôle « membre » rétrograderait un administrateur).
        siens = [m for m in m_projets.membres_du_theme(theme["id"]) if m["compte"] == compte["id"]]
        m_projets.definir_membre_theme(theme["id"], compte["id"],
                                       siens[0]["role"] if siens else role,
                                       bool(theme.get("notifier")))
    return jsonify(_mes_notifications(compte["id"]))


@app.route("/api/projets/<identifiant>/messages", methods=["GET", "POST"])
def api_messages_projet(identifiant):
    """La discussion du projet (celle qui n'est rattachée à aucun groupe)."""
    _projet(identifiant)
    if request.method == "POST":
        corps = request.get_json(silent=True) or {}
        try:
            message = m_equipe.envoyer_message(identifiant, _qui(), corps.get("texte", ""))
        except ValueError as erreur:
            return jsonify({"erreur": str(erreur)}), 400
        _prevenir(identifiant, f"Nouveau message de {_qui()} : " + corps.get("texte", "")[:120])
        return jsonify(message), 201
    return jsonify({"messages": m_equipe.lister_messages(identifiant)})


@app.route("/api/projets/<identifiant>/messages/<message>", methods=["DELETE"])
def api_message_projet_supprimer(identifiant, message):
    _projet(identifiant)
    m_equipe.supprimer_message(identifiant, message)
    return jsonify({"ok": True})


@app.route("/api/themes/<identifiant>/messages", methods=["GET", "POST"])
def api_messages(identifiant):
    _theme(identifiant, ecriture=request.method == "POST")
    if request.method == "POST":
        corps = request.get_json(silent=True) or {}
        try:
            message = m_equipe.envoyer_message(identifiant, _qui(), corps.get("texte", ""))
        except ValueError as erreur:
            return jsonify({"erreur": str(erreur)}), 400
        _prevenir(identifiant, f"Nouveau message de {_qui()} : " + corps.get("texte", "")[:120])
        return jsonify(message), 201
    return jsonify({"messages": m_equipe.lister_messages(identifiant)})


@app.route("/api/themes/<identifiant>/messages/<message>", methods=["DELETE"])
def api_message_supprimer(identifiant, message):
    _theme(identifiant, ecriture=True)
    m_equipe.supprimer_message(identifiant, message)
    return jsonify({"ok": True})


@app.route("/api/themes/<identifiant>/pages", methods=["GET", "POST"])
def api_pages(identifiant):
    _theme(identifiant, ecriture=request.method == "POST")
    if request.method == "POST":
        corps = request.get_json(silent=True) or {}
        page = m_equipe.creer_page(identifiant, corps.get("titre", ""),
                                   corps.get("contenu", ""), _qui())
        _prevenir(identifiant, f"Nouvelle page : {page['titre']}")
        return jsonify(page), 201
    return jsonify({"pages": m_equipe.lister_pages(identifiant)})


@app.route("/api/themes/<identifiant>/pages/<page>", methods=["GET", "PUT", "DELETE"])
def api_page(identifiant, page):
    _theme(identifiant, ecriture=request.method in ("PUT", "DELETE"))
    if request.method == "DELETE":
        m_equipe.supprimer_page(identifiant, page, _qui())
        return jsonify({"ok": True})
    if request.method == "PUT":
        resultat = m_equipe.maj_page(identifiant, page, request.get_json(silent=True) or {},
                                     _qui())
        if resultat is None:
            return jsonify({"erreur": "Page inconnue"}), 404
        _prevenir(identifiant, f"Page modifiée : {resultat['titre']}")
        return jsonify(resultat)
    resultat = m_equipe.lire_page(identifiant, page)
    if resultat is None:
        return jsonify({"erreur": "Page inconnue"}), 404
    return jsonify(resultat)


@app.route("/api/projets/<identifiant>/cadre", methods=["GET", "PUT"])
def api_cadre(identifiant):
    """Le cadre de travail DU PROJET : son contexte, en quelques phrases."""
    _projet(identifiant)
    if request.method == "PUT":
        _projet(identifiant, ecriture=True)
        corps = request.get_json(silent=True) or {}
        return jsonify(m_equipe.maj_cadre(corps.get("contexte", ""), _qui(), identifiant))
    return jsonify(m_equipe.lire_cadre(identifiant))


@app.route("/api/projets/<identifiant>/documents", methods=["GET", "POST"])
def api_cadre_documents(identifiant):
    """Les comptes rendus de réunion du projet (documents rangés sous le projet)."""
    _projet(identifiant)
    if request.method == "POST":
        _projet(identifiant, ecriture=True)
        depot = request.files.get("fichier")
        if not depot or not depot.filename:
            return jsonify({"erreur": "Aucun fichier reçu."}), 400
        try:
            document = m_atelier.ajouter_document(identifiant, depot.filename, depot.read(),
                                                  depot.mimetype or "",
                                                  request.form.get("note", ""),
                                                  request.form.get("auteur") or _qui())
        except ValueError as erreur:
            return jsonify({"erreur": str(erreur)}), 413
        return jsonify(document), 201
    return jsonify({"documents": m_atelier.lister_documents(identifiant)})


@app.route("/api/projets/<identifiant>/documents/<document>", methods=["DELETE"])
def api_cadre_document_supprimer(identifiant, document):
    _projet(identifiant, ecriture=True)
    m_atelier.supprimer_document(identifiant, document, _qui())
    return jsonify({"ok": True})


@app.route("/api/projets/<identifiant>/documents/<document>/fichier")
def api_cadre_document_fichier(identifiant, document):
    _projet(identifiant)
    trouve = m_atelier.chemin_document(identifiant, document)
    if not trouve:
        abort(404, description="Document inconnu")
    nom, chemin = trouve
    return send_file(chemin, as_attachment=True, download_name=nom,
                     mimetype="application/octet-stream")


@app.route("/api/projets/<identifiant>/evenements")
def api_evenements_generaux(identifiant):
    """Flux temps réel de la discussion et du cadre DU PROJET."""
    _projet(identifiant)
    nom = request.args.get("nom") or "Anonyme"
    numero, file = m_atelier.abonner(identifiant, nom)

    def flux():
        try:
            yield "retry: 3000\n\n"
            while True:
                try:
                    evenement = file.get(timeout=15)
                except queue.Empty:
                    yield ": souffle\n\n"
                    continue
                yield "data: " + json.dumps(evenement, ensure_ascii=False) + "\n\n"
        finally:
            m_atelier.desabonner(identifiant, numero)

    return Response(flux(), mimetype="text/event-stream",
                    headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})



@app.route("/api/alertes/essai", methods=["POST"])
def api_alerte_essai():
    """Vérifie que les alertes par courriel partent bien."""
    corps = request.get_json(silent=True) or {}
    destinataire = (corps.get("email") or "").strip()
    if not destinataire:
        compte = _compte()
        destinataire = (compte or {}).get("email") or ""
    if not destinataire:
        return jsonify({"erreur": "Aucune adresse de courriel."}), 400
    return jsonify({"envoye": m_equipe.test_alerte(destinataire), "email": destinataire})


def principal():
    analyseur = argparse.ArgumentParser(description="Synergie — serveur")
    analyseur.add_argument("--port", type=int, default=int(os.environ.get("SYNERGIE_PORT", 8077)))
    analyseur.add_argument("--hote", default="127.0.0.1")
    arguments = analyseur.parse_args()
    m_atelier.initialiser()
    m_projets.initialiser()
    m_invitations.initialiser()
    m_consultations.initialiser()
    m_equipe.initialiser()
    m_equipe.demarrer_le_facteur()          # les alertes partent en arrière-plan
    # `threaded=True` : indispensable — une connexion temps réel occupe un fil, et les autres
    # participants doivent pouvoir continuer d'écrire pendant ce temps.
    app.run(host=arguments.hote, port=arguments.port, debug=False, threaded=True)


if __name__ == "__main__":
    principal()
