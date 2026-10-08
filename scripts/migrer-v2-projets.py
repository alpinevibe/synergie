#!/usr/bin/env python3
"""Migration du 08/10/2026 — Synergie passe aux PROJETS, aux rôles et aux groupes uniques.

Ce que fait la migration, une seule fois (elle peut être relancée sans dommage) :

  1. les groupes « Groupe n — … » (issus des lettres de cadrage) sont rattachés au projet
     « Projet horaires diversifiés HTC Écrins » ;
  2. Pierre y est administrateur (alertes activées) ; Camille y est membre ;
  3. le cadre de travail général et la discussion générale deviennent ceux du projet ;
  4. les documents rangés jusqu'ici « dans le vide » sont rattachés au projet.

Usage :  python3 scripts/migrer-v2-projets.py [--essai]
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

RACINE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RACINE))

from moteur import atelier as m_atelier                 # noqa: E402
from moteur import equipe as m_equipe                   # noqa: E402
from moteur import projets as m_projets                 # noqa: E402

NOM_PROJET = "Projet horaires diversifiés HTC Écrins"
ADMINS = ("Pierre",)
MEMBRES = ("Camille",)


def principal():
    analyseur = argparse.ArgumentParser(description=__doc__)
    analyseur.add_argument("--essai", action="store_true", help="montrer sans rien écrire")
    options = analyseur.parse_args()

    m_atelier.initialiser()
    m_equipe.initialiser()
    m_projets.initialiser()

    # 1. Le projet (créé une seule fois : on le retrouve par son nom).
    projet = next((p for p in m_projets.lister_projets() if p["nom"] == NOM_PROJET), None)
    if projet:
        print(f"projet déjà présent : {projet['id']} — {projet['nom']}")
    elif options.essai:
        print(f"[essai] création du projet « {NOM_PROJET} »")
        projet = {"id": "pr-essai"}
    else:
        projet = m_projets.creer_projet(
            NOM_PROJET,
            "Réorganisation du service autour des horaires diversifiés : quatre groupes de "
            "travail, chacun avec sa lettre de cadrage.", auteur="Pierre", admin="",
            qui="Pierre")
        print(f"projet créé : {projet['id']} — {projet['nom']}")

    # 2. Les groupes issus d'une lettre de cadrage.
    groupes = [t for t in m_atelier.lister_themes()
               if (t.get("titre") or "").startswith("Groupe ")]
    print(f"{len(groupes)} groupe(s) de travail : "
          + ", ".join(t["titre"] for t in groupes))
    if not options.essai:
        with m_atelier.connexion() as base:
            for theme in groupes:
                base.execute("update themes set projet = ? where id = ?",
                             (projet["id"], theme["id"]))

    # 3. Les personnes : administrateurs et membres (retrouvés par leur prénom).
    #    Une même personne peut avoir PLUSIEURS comptes (un par appareil ou par adresse) :
    #    on les ajoute tous, sinon elle perdrait l'accès depuis son autre navigateur.
    comptes = m_equipe.lister_comptes()
    for prenom in ADMINS:
        trouves = [c for c in comptes if c["prenom"].lower() == prenom.lower()]
        if not trouves:
            print(f"  ⚠ administrateur « {prenom} » : compte introuvable")
        for compte in trouves:
            if not options.essai:
                m_projets.definir_membre_projet(projet["id"], compte["id"], "admin",
                                                notifier=True, ajoute_par="migration")
            print(f"  administrateur : {compte['prenom']} ({compte['id']})")
    for prenom in MEMBRES:
        for compte in [c for c in comptes if c["prenom"].lower() == prenom.lower()]:
            if not options.essai:
                m_projets.definir_membre_projet(projet["id"], compte["id"], "membre",
                                                notifier=False, ajoute_par="migration")
            print(f"  membre : {compte['prenom']} ({compte['id']})")

    # 4. Le cadre général et la discussion générale deviennent ceux du projet.
    if not options.essai:
        with m_atelier.connexion() as base:
            ancien = base.execute("select contexte from cadre where id = 'general'").fetchone()
            base.execute("update messages set theme = ? where theme = ''", (projet["id"],))
            base.execute("update documents set theme = ? where theme = ''", (projet["id"],))
            # Ménage : les contenus des GROUPES retirés (boîte à trames, fiches de poste)
            # n'ont plus de thème — on les enlève plutôt que de garder des lignes
            # orphelines. ATTENTION : les discussions et documents du PROJET portent
            # l'identifiant du projet (pr-…), ils ne sont donc jamais concernés.
            for table in ("notes", "decisions", "documents", "messages", "pages", "journal"):
                base.execute(f"delete from {table} where theme like 'th-%' and theme not in"
                             " (select id from themes)")
        if ancien and ancien["contexte"]:
            cadre = m_equipe.lire_cadre(projet["id"])
            if not (cadre.get("contexte") or "").strip():
                m_equipe.maj_cadre(ancien["contexte"], "migration", projet["id"])
                print("  cadre de travail repris dans le projet")
        print("  discussion et comptes rendus rattachés au projet")

    print("\nÉtat final :")
    for p in m_projets.lister_projets():
        membres = m_projets.membres_du_projet(p["id"])
        print(f"  {p['nom']} ({p['id']}) — {len(m_atelier.lister_themes(projet=p['id']))} groupe(s), "
              + ", ".join(f"{m['prenom']} ({m['role']})" for m in membres))
    return 0


if __name__ == "__main__":
    raise SystemExit(principal())
