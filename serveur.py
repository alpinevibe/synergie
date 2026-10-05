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
from moteur import boite_trame as m_boite_trame         # noqa: E402
from moteur import equipe as m_equipe                   # noqa: E402
from moteur import fiches as m_fiches                   # noqa: E402
from moteur import avis as m_avis                       # noqa: E402
from moteur import boite as m_boite                     # noqa: E402
from moteur import projet as m_projet                   # noqa: E402
from moteur import regles as m_regles                   # noqa: E402
from moteur import trames as m_trames                   # noqa: E402

WEB = os.path.join(RACINE, "web")
DOSSIER_GENERATIONS = os.path.join(RACINE, "donnees", "generations")
app = Flask(__name__, static_folder=None)


# --- Utilitaires --------------------------------------------------------------------
def _chemin_generation(identifiant: str) -> str:
    return os.path.join(DOSSIER_GENERATIONS, f"{m_projet._slug(identifiant)}.json")


def _lire_generation(identifiant: str) -> dict:
    chemin = _chemin_generation(identifiant)
    if os.path.exists(chemin):
        with open(chemin, encoding="utf-8") as f:
            return json.load(f)
    return {"projet": identifiant, "trames": []}


def _ecrire_generation(identifiant: str, generation: dict) -> None:
    os.makedirs(DOSSIER_GENERATIONS, exist_ok=True)
    with open(_chemin_generation(identifiant), "w", encoding="utf-8") as f:
        json.dump(generation, f, ensure_ascii=False, indent=2)


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
    return jsonify({"application": "Synergie", "version": "0.1.0",
                    "hermes": m_boite.hermes_disponible()})


@app.route("/api/regles")
def api_regles():
    return jsonify(m_regles.REGLES_DEFAUT)


@app.route("/api/projets", methods=["GET", "POST"])
def api_projets():
    if request.method == "POST":
        projet = m_projet.enregistrer(m_projet.normaliser(request.get_json(force=True) or {}))
        return jsonify(projet), 201
    return jsonify(m_projet.lister())


@app.route("/api/demo", methods=["POST"])
def api_demo():
    projet = m_projet.projet_demo()
    m_projet.enregistrer(projet)
    return jsonify(projet), 201


@app.route("/api/projets/<identifiant>", methods=["GET", "PUT", "DELETE"])
def api_projet(identifiant):
    if request.method == "DELETE":
        return jsonify({"supprime": m_projet.supprimer(identifiant)})
    if request.method == "PUT":
        projet = m_projet.normaliser(request.get_json(force=True) or {})
        projet["id"] = identifiant
        return jsonify(m_projet.enregistrer(projet))
    try:
        return jsonify(m_projet.charger(identifiant))
    except FileNotFoundError:
        return jsonify({"erreur": "projet introuvable"}), 404


@app.route("/api/projets/<identifiant>/cibles-recommandees", methods=["POST"])
def api_cibles(identifiant):
    projet = m_projet.charger(identifiant)
    regles = m_regles.regles_projet(projet.get("regles"))
    for metier in projet.get("metiers", []):
        metier["cibles"] = m_projet.cibles_recommandees(metier, projet.get("agents", []), regles)
    m_projet.enregistrer(projet)
    return jsonify(projet)


@app.route("/api/projets/<identifiant>/trames", methods=["GET", "POST"])
def api_trames(identifiant):
    if request.method == "GET":
        return jsonify(_lire_generation(identifiant))
    projet = m_projet.charger(identifiant)
    corps = request.get_json(silent=True) or {}
    generation = m_trames.generer_trames(
        projet,
        metier_code=corps.get("metier"),
        max_semaines=int(corps.get("max_semaines") or m_trames.MAX_SEMAINES_DEFAUT),
        duree_max_s=float(corps.get("duree_max_s") or m_trames.DUREE_SOLVEUR_S),
    )
    generation["nom_projet"] = projet.get("nom")
    _ecrire_generation(identifiant, generation)
    m_boite.ranger_generation(generation, projet=identifiant)
    return jsonify(generation)


@app.route("/api/projets/<identifiant>/avis", methods=["POST", "DELETE"])
def api_avis(identifiant):
    projet = m_projet.charger(identifiant)
    corps = request.get_json(force=True) or {}
    if request.method == "POST":
        if not corps.get("agent") or not corps.get("jour"):
            return jsonify({"erreur": "agent et jour sont obligatoires"}), 400
        projet.setdefault("avis", []).append({
            "agent": corps["agent"], "jour": corps["jour"],
            "souhait": (corps.get("souhait") or "").upper(),
            "motif": corps.get("motif", ""),
        })
    else:
        index = int(corps.get("index", -1))
        if 0 <= index < len(projet.get("avis", [])):
            projet["avis"].pop(index)
    m_projet.enregistrer(projet)
    return jsonify(projet)


@app.route("/api/projets/<identifiant>/synthese")
def api_synthese(identifiant):
    projet = m_projet.charger(identifiant)
    generation = _lire_generation(identifiant)
    if not generation.get("trames"):
        generation = m_trames.generer_trames(projet)
        _ecrire_generation(identifiant, generation)
        m_boite.ranger_generation(generation, projet=identifiant)
    return jsonify(m_avis.synthese(projet, generation))


@app.route("/api/boite")
def api_boite():
    trames = m_boite.lister()
    return jsonify({"trames": trames, "total": len(trames)})


@app.route("/api/boite/importer-hermes", methods=["POST"])
def api_importer_hermes():
    corps = request.get_json(silent=True) or {}
    pops = tuple(corps.get("populations") or ("IDE HTC", "AS HTC", "ASH"))
    return jsonify(m_boite.importer_hermes(pops, corps.get("semaines")))


# ====================================================================================
# ATELIER COLLABORATIF — thèmes de réflexion, tableau blanc, documents, décisions
# ====================================================================================
def _qui() -> str:
    """Le prénom de la personne qui agit : envoyé par la page dans l'en-tête
    « X-Synergie-Nom ». Il sert à journaliser les actions (demande du 05/10/2026)."""
    jeton = request.headers.get("X-Synergie-Jeton") or request.args.get("jeton")
    if jeton:
        compte = m_equipe.lire_compte(jeton)
        if compte and compte.get("prenom"):
            return compte["prenom"][:60]
    nom = (request.headers.get("X-Synergie-Nom") or "").strip()
    if not nom:
        corps = request.get_json(silent=True) or {}
        nom = (corps.get("auteur") or corps.get("qui") or "").strip()
    return nom[:60] or "Anonyme"


def _compte(requis: bool = False) -> dict | None:
    """Le compte de la personne qui agit, retrouvé grâce au jeton du navigateur."""
    jeton = request.headers.get("X-Synergie-Jeton") or request.args.get("jeton")
    compte = m_equipe.lire_compte(jeton) if jeton else None
    if compte is None and requis:
        abort(401, description="Compte inconnu : créez votre compte dans Synergie.")
    return compte


def _prevenir(identifiant: str, resume: str) -> None:
    """Prévient par courriel les responsables du thème qu'il vient de changer."""
    theme = m_atelier.lire_theme(identifiant)
    if theme:
        m_equipe.prevenit(identifiant, theme["titre"], resume, _qui())


def _theme(identifiant: str) -> dict:
    theme = m_atelier.lire_theme(identifiant)
    if not theme:
        abort(404, description="Thème inconnu")
    return theme


@app.route("/api/atelier/sante")
def api_atelier_sante():
    return jsonify(m_atelier.sante())


@app.route("/api/boite-trame/analyser", methods=["POST"])
def api_boite_trame_analyser():
    """Boîte à trames : ce que la description du service demande (heures, ETP, écart)."""
    try:
        return jsonify(m_boite_trame.analyser(request.get_json(silent=True) or {}))
    except Exception as erreur:                    # description incomplète : on le dit
        return jsonify({"erreur": str(erreur)}), 400


@app.route("/api/boite-trame/generer", methods=["POST"])
def api_boite_trame_generer():
    """Boîte à trames : jusqu'à 3 trames proposées, avec leur conformité."""
    maxi = request.args.get("trames", 3, type=int)
    try:
        return jsonify(m_boite_trame.generer(request.get_json(silent=True) or {}, maxi))
    except Exception as erreur:
        return jsonify({"erreur": str(erreur)}), 400


@app.route("/api/themes", methods=["GET", "POST"])
def api_themes():
    if request.method == "POST":
        corps = request.get_json(silent=True) or {}
        titre = (corps.get("titre") or "").strip()
        if not titre:
            return jsonify({"erreur": "Le titre est obligatoire."}), 400
        theme = m_atelier.creer_theme(titre, corps.get("description", ""),
                                      corps.get("couleur", ""), corps.get("projet", ""),
                                      _qui())
        return jsonify(theme), 201
    return jsonify({"themes": m_atelier.lister_themes()})


@app.route("/api/themes/<identifiant>", methods=["GET", "PUT", "DELETE"])
def api_theme(identifiant):
    if request.method == "DELETE":
        _theme(identifiant)
        m_atelier.supprimer_theme(identifiant)
        return jsonify({"ok": True})
    if request.method == "PUT":
        _theme(identifiant)
        return jsonify(m_atelier.maj_theme(identifiant, request.get_json(silent=True) or {},
                                           _qui()))
    contenu = m_atelier.resume(identifiant, _qui())
    contenu["responsables"] = m_equipe.responsables(identifiant)
    return jsonify(contenu)


@app.route("/api/themes/<identifiant>/notes", methods=["POST"])
def api_note_creer(identifiant):
    _theme(identifiant)
    corps = request.get_json(silent=True) or {}
    corps["auteur"] = corps.get("auteur") or _qui()
    return jsonify(m_atelier.creer_note(identifiant, corps)), 201


@app.route("/api/themes/<identifiant>/notes/<note>", methods=["PUT", "DELETE"])
def api_note(identifiant, note):
    _theme(identifiant)
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
    _theme(identifiant)
    corps = request.get_json(silent=True) or {}
    if not (corps.get("intitule") or "").strip():
        return jsonify({"erreur": "L'intitulé est obligatoire."}), 400
    return jsonify(m_atelier.creer_decision(identifiant, corps.get("intitule"),
                                            corps.get("detail", ""),
                                            corps.get("auteur") or _qui())), 201


@app.route("/api/themes/<identifiant>/decisions/<decision>", methods=["PUT", "DELETE"])
def api_decision(identifiant, decision):
    _theme(identifiant)
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
    _theme(identifiant)
    corps = request.get_json(silent=True) or {}
    try:
        resultat = m_atelier.voter(identifiant, decision, _qui(), corps.get("valeur", ""))
    except ValueError as erreur:
        return jsonify({"erreur": str(erreur)}), 400
    return jsonify(resultat), (200 if resultat.get("ok") else 409)


@app.route("/api/themes/<identifiant>/documents", methods=["POST"])
def api_document_ajouter(identifiant):
    _theme(identifiant)
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
    _theme(identifiant)
    m_atelier.supprimer_document(identifiant, document, _qui())
    return jsonify({"ok": True})


@app.route("/api/themes/<identifiant>/curseurs", methods=["POST"])
def api_curseurs(identifiant):
    """« Qui travaille sur quelle note » : relayé aux autres, sans être enregistré."""
    _theme(identifiant)
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
@app.route("/api/comptes", methods=["GET", "POST"])
def api_comptes():
    """POST : créer (ou retrouver) son compte avec prénom et courriel → rend un jeton.
    GET : la liste des comptes (pour désigner les responsables d'un thème)."""
    if request.method == "POST":
        corps = request.get_json(silent=True) or {}
        try:
            resultat = m_equipe.creer_compte(corps.get("prenom", ""), corps.get("email", ""),
                                             bool(corps.get("notifier_tout")),
                                             corps.get("jeton"))
        except ValueError as erreur:
            return jsonify({"erreur": str(erreur)}), 400
        return jsonify(resultat), 201
    return jsonify({"comptes": m_equipe.lister_comptes()})


@app.route("/api/comptes/moi", methods=["GET", "PUT"])
def api_mon_compte():
    compte = _compte(requis=True)
    if request.method == "PUT":
        corps = request.get_json(silent=True) or {}
        compte = m_equipe.maj_compte(compte["id"], corps) or compte
        if "abonnements" in corps:
            for identifiant in m_atelier.lister_themes():
                m_equipe.abonner(identifiant["id"], compte["id"],
                                 identifiant["id"] in (corps.get("abonnements") or []))
    themes_responsable = [t["id"] for t in m_atelier.lister_themes()
                          if any(r["id"] == compte["id"] for r in m_equipe.responsables(t["id"]))]
    return jsonify({"compte": compte,
                    "abonnements": m_equipe.abonnements_du_compte(compte["id"]),
                    "responsable_de": themes_responsable})


@app.route("/api/themes/<identifiant>/responsables", methods=["GET", "PUT"])
def api_responsables(identifiant):
    _theme(identifiant)
    if request.method == "PUT":
        corps = request.get_json(silent=True) or {}
        resultat = m_equipe.definir_responsables(identifiant, corps.get("comptes") or [], _qui())
        _prevenir(identifiant, "Les responsables du thème ont changé.")
        return jsonify({"responsables": resultat})
    return jsonify({"responsables": m_equipe.responsables(identifiant)})


@app.route("/api/messages")
def api_messages_generaux():
    """Le chat général du projet (celui qui n'est rattaché à aucun thème)."""
    return jsonify({"messages": m_equipe.lister_messages("")})


@app.route("/api/messages", methods=["POST"])
def api_message_general():
    corps = request.get_json(silent=True) or {}
    try:
        message = m_equipe.envoyer_message("", _qui(), corps.get("texte", ""))
    except ValueError as erreur:
        return jsonify({"erreur": str(erreur)}), 400
    return jsonify(message), 201


@app.route("/api/themes/<identifiant>/messages", methods=["GET", "POST"])
def api_messages(identifiant):
    _theme(identifiant)
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
    _theme(identifiant)
    m_equipe.supprimer_message(identifiant, message)
    return jsonify({"ok": True})


@app.route("/api/themes/<identifiant>/pages", methods=["GET", "POST"])
def api_pages(identifiant):
    _theme(identifiant)
    if request.method == "POST":
        corps = request.get_json(silent=True) or {}
        page = m_equipe.creer_page(identifiant, corps.get("titre", ""),
                                   corps.get("contenu", ""), _qui())
        _prevenir(identifiant, f"Nouvelle page : {page['titre']}")
        return jsonify(page), 201
    return jsonify({"pages": m_equipe.lister_pages(identifiant)})


@app.route("/api/themes/<identifiant>/pages/<page>", methods=["GET", "PUT", "DELETE"])
def api_page(identifiant, page):
    _theme(identifiant)
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


@app.route("/api/cadre", methods=["GET", "PUT"])
def api_cadre():
    """Le cadre de travail : le contexte du projet, en quelques phrases."""
    if request.method == "PUT":
        corps = request.get_json(silent=True) or {}
        return jsonify(m_equipe.maj_cadre(corps.get("contexte", ""), _qui()))
    return jsonify(m_equipe.lire_cadre())


@app.route("/api/cadre/documents", methods=["GET", "POST"])
def api_cadre_documents():
    """Les comptes rendus de réunion déposés dans le cadre de travail."""
    if request.method == "POST":
        depot = request.files.get("fichier")
        if not depot or not depot.filename:
            return jsonify({"erreur": "Aucun fichier reçu."}), 400
        try:
            document = m_atelier.ajouter_document("", depot.filename, depot.read(),
                                                  depot.mimetype or "",
                                                  request.form.get("note", ""),
                                                  request.form.get("auteur") or _qui())
        except ValueError as erreur:
            return jsonify({"erreur": str(erreur)}), 413
        return jsonify(document), 201
    return jsonify({"documents": m_atelier.lister_documents("")})


@app.route("/api/cadre/documents/<document>", methods=["DELETE"])
def api_cadre_document_supprimer(document):
    m_atelier.supprimer_document("", document, _qui())
    return jsonify({"ok": True})


@app.route("/api/cadre/documents/<document>/fichier")
def api_cadre_document_fichier(document):
    trouve = m_atelier.chemin_document("", document)
    if not trouve:
        abort(404, description="Document inconnu")
    nom, chemin = trouve
    return send_file(chemin, as_attachment=True, download_name=nom,
                     mimetype="application/octet-stream")


@app.route("/api/evenements")
def api_evenements_generaux():
    """Flux temps réel du chat général et du cadre de travail."""
    nom = request.args.get("nom") or "Anonyme"
    numero, file = m_atelier.abonner("", nom)

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
            m_atelier.desabonner("", numero)

    return Response(flux(), mimetype="text/event-stream",
                    headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})


@app.route("/api/themes/<identifiant>/codes")
def api_codes(identifiant):
    _theme(identifiant)
    return jsonify({"codes": m_fiches.lister_codes(identifiant)})


@app.route("/api/themes/<identifiant>/codes", methods=["POST"])
def api_code_enregistrer(identifiant):
    _theme(identifiant)
    try:
        return jsonify(m_fiches.enregistrer_code(identifiant,
                                                 request.get_json(silent=True) or {}, _qui()))
    except ValueError as erreur:
        return jsonify({"erreur": str(erreur)}), 400


@app.route("/api/themes/<identifiant>/codes/<code>", methods=["DELETE"])
def api_code_supprimer(identifiant, code):
    _theme(identifiant)
    m_fiches.supprimer_code(identifiant, code, _qui())
    return jsonify({"ok": True})


@app.route("/api/themes/<identifiant>/fiches", methods=["GET", "POST"])
def api_fiches(identifiant):
    _theme(identifiant)
    if request.method == "POST":
        corps = request.get_json(silent=True) or {}
        fiche = m_fiches.creer_fiche(identifiant, corps, _qui())
        _prevenir(identifiant, f"Nouvelle fiche de poste : {fiche['intitule']}")
        return jsonify(fiche), 201
    return jsonify({"fiches": m_fiches.lister_fiches(identifiant)})


@app.route("/api/themes/<identifiant>/fiches/<fiche>", methods=["GET", "PUT", "DELETE"])
def api_fiche(identifiant, fiche):
    _theme(identifiant)
    if request.method == "DELETE":
        m_fiches.supprimer_fiche(identifiant, fiche, _qui())
        return jsonify({"ok": True})
    if request.method == "PUT":
        resultat = m_fiches.maj_fiche(identifiant, fiche, request.get_json(silent=True) or {},
                                      _qui())
        if resultat is None:
            return jsonify({"erreur": "Fiche inconnue"}), 404
        _prevenir(identifiant, f"Fiche de poste modifiée : {resultat['intitule']}"
                               f" ({resultat['statut_libelle']})")
        return jsonify(resultat)
    resultat = m_fiches.lire_fiche(identifiant, fiche)
    if resultat is None:
        return jsonify({"erreur": "Fiche inconnue"}), 404
    return jsonify(resultat)


@app.route("/api/themes/<identifiant>/fiches/<fiche>/dupliquer", methods=["POST"])
def api_fiche_dupliquer(identifiant, fiche):
    _theme(identifiant)
    try:
        return jsonify(m_fiches.dupliquer_fiche(identifiant, fiche, _qui())), 201
    except ValueError as erreur:
        return jsonify({"erreur": str(erreur)}), 404


@app.route("/api/themes/<identifiant>/fiches/<fiche>/taches", methods=["POST"])
def api_tache_ajouter(identifiant, fiche):
    _theme(identifiant)
    return jsonify(m_fiches.ajouter_tache(identifiant, fiche,
                                          request.get_json(silent=True) or {}, _qui())), 201


@app.route("/api/themes/<identifiant>/fiches/<fiche>/taches/<tache>", methods=["PUT", "DELETE"])
def api_tache(identifiant, fiche, tache):
    _theme(identifiant)
    if request.method == "DELETE":
        return jsonify(m_fiches.supprimer_tache(identifiant, fiche, tache, _qui()))
    return jsonify(m_fiches.maj_tache(identifiant, fiche, tache,
                                      request.get_json(silent=True) or {}, _qui()))


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
    m_fiches.initialiser()
    m_equipe.initialiser()
    m_equipe.demarrer_le_facteur()          # les alertes partent en arrière-plan
    # `threaded=True` : indispensable — une connexion temps réel occupe un fil, et les autres
    # participants doivent pouvoir continuer d'écrire pendant ce temps.
    app.run(host=arguments.hote, port=arguments.port, debug=False, threaded=True)


if __name__ == "__main__":
    principal()
