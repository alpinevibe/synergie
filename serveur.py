#!/usr/bin/env python3
"""SYNERGIE — serveur (API + interface).

Lancement :  ./run.sh          (ou)  python serveur.py --port 8077
"""
from __future__ import annotations

import argparse
import json
import os
import sys

from flask import Flask, jsonify, request, send_from_directory

RACINE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, RACINE)

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


def principal():
    analyseur = argparse.ArgumentParser(description="Synergie — serveur")
    analyseur.add_argument("--port", type=int, default=int(os.environ.get("SYNERGIE_PORT", 8077)))
    analyseur.add_argument("--hote", default="127.0.0.1")
    arguments = analyseur.parse_args()
    app.run(host=arguments.hote, port=arguments.port, debug=False)


if __name__ == "__main__":
    principal()
