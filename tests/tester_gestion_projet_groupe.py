#!/usr/bin/env python3
"""Gestion du projet et des groupes, et les personnes visibles (12/10/2026).

Demande de l'utilisateur :
  1. un bouton « Gestion du projet » (administrateur du projet seulement) pour régler le nom,
     la description du projet et les membres — et corriger l'affichage des membres, qui était
     superposé et tassé ;
  2. dans chaque groupe, un bouton « Gestion du groupe » (administrateur du groupe seulement)
     pour régler le nom, la description et les membres ;
  3. les personnes qui font partie du projet, et celles qui font partie d'un groupe, VISIBLES
     sur la page d'accueil, avec leur statut (Admin, membre, visiteur).

Ce contrôle crée un projet d'essai (puis l'efface) et vérifie dans un vrai navigateur, à
390 × 740 comme à 1280 × 900 :
  • l'administrateur voit « Gestion du projet » ; un simple membre ne le voit pas ;
  • la fenêtre règle vraiment le nom et la description (vérifié par l'API) ;
  • la fenêtre liste les personnes sans les superposer (chaque ligne garde sa hauteur) ;
  • l'administrateur du groupe voit « Gestion du groupe » et règle vraiment le groupe ;
  • le serveur REFUSE à un simple membre de renommer un groupe ;
  • les personnes du projet et du groupe sont visibles d'emblée, avec leur statut.

    python3 tests/tester_gestion_projet_groupe.py
    SYNERGIE_SITE=https://synergie.alpinevibe.fr python3 tests/tester_gestion_projet_groupe.py
"""
import json
import os

import sys
import urllib.error
import urllib.request

from playwright.sync_api import sync_playwright

BASE = os.environ.get("SYNERGIE_SITE", "http://127.0.0.1:8077").rstrip("/")
CAPTURES = os.environ.get("CHECKUP_CAPTURES", "/home/ubuntu/captures")
PROJET = "Essai — gestion du projet"
GROUPE = "Groupe d'essai gestion"
PERSONNES = [("Camille Martin", "membre"), ("Bruno Petit", "visiteur")]

RESULTATS = []


def verifie(titre, condition, detail=""):
    RESULTATS.append((titre, bool(condition)))
    print(("  ✅ " if condition else "  ❌ ") + titre + ((" — " + str(detail)) if detail else ""))


def appel(chemin, corps=None, jeton=None, methode=None):
    donnees = json.dumps(corps).encode("utf-8") if corps is not None else None
    requete = urllib.request.Request(BASE + chemin, data=donnees,
                                     method=methode or ("POST" if donnees else "GET"))
    requete.add_header("Content-Type", "application/json")
    requete.add_header("User-Agent", "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
                                     "(KHTML, like Gecko) Chrome/124.0 Safari/537.36")
    if jeton:
        requete.add_header("X-Synergie-Jeton", jeton)
    with urllib.request.urlopen(requete, timeout=30) as reponse:
        return json.loads(reponse.read().decode("utf-8"))


def essai_appel(chemin, corps=None, jeton=None, methode=None):
    """Un appel dont on attend l'échec (403) : on rend le code de retour."""
    try:
        appel(chemin, corps, jeton, methode)
        return 200
    except urllib.error.HTTPError as erreur:
        return erreur.code


def menage(identifiants):
    """Efface les comptes de l'essai — dans la VRAIE base du service (voir `menage_essai`)."""
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    from menage_essai import effacer_comptes
    effacer_comptes(identifiants)


# --- ce que l'on mesure dans la page -------------------------------------------------------
MESURE_GESTION = """() => {
  const bouton = document.querySelector('#btn-membres');
  const gestion = document.querySelector('#gestion-projet');
  return {
    libelle: bouton ? bouton.textContent.trim() : '',
    bouton_projet: !!document.querySelector('#btn-gestion-projet')
      && !document.querySelector('#btn-gestion-projet').classList.contains('cache'),
    titre: (document.querySelector('#titre-membres') || {}).textContent || '',
    gestion_visible: !!gestion && !gestion.classList.contains('cache'),
    champs: (gestion && !gestion.classList.contains('cache'))
      ? gestion.querySelectorAll('input').length : 0,
    fenetre: !document.querySelector('#vue-membres').classList.contains('cache')
  };
}"""

# Les lignes de la liste des personnes : leurs positions. Deux lignes ne doivent JAMAIS se
# chevaucher (défaut rapporté le 12/10/2026 : les membres étaient superposés et tassés).
MESURE_CHEVAUCHEMENT = """(selecteur) => {
  const lignes = [...document.querySelectorAll(selecteur + ' .membre')];
  const boites = lignes.map((n) => n.getBoundingClientRect());
  let chevauche = 0;
  let tasse = 0;
  for (let i = 1; i < boites.length; i += 1) {
    if (boites[i].top < boites[i - 1].bottom - 1) chevauche += 1;
    const contenu = lignes[i - 1].querySelector('.membre-tete');
    if (contenu && boites[i - 1].height + 1 < contenu.getBoundingClientRect().height) tasse += 1;
  }
  return { nombre: lignes.length, chevauche, tasse };
}"""

# Les personnes visibles sur la page, avec leur statut.
MESURE_APERCU = """(selecteur) => {
  const zone = document.querySelector(selecteur);
  if (!zone) return null;
  const personnes = [...zone.querySelectorAll('.personne')].map((n) => ({
    nom: (n.querySelector('.nom-personne') || {}).textContent || '',
    statut: (n.querySelector('.statut') || {}).textContent || '',
    pastille: ((n.querySelector('.pastille-membre') || {}).textContent || '').trim()
  }));
  const boites = [...zone.querySelectorAll('.personne')].map((n) => n.getBoundingClientRect());
  let chevauche = 0;
  for (let i = 1; i < boites.length; i += 1) {
    const memeLigne = boites[i].top < boites[i - 1].bottom - 1
      && boites[i].left < boites[i - 1].right - 1;
    if (memeLigne) chevauche += 1;
  }
  const conteneur = zone.closest('.panneau-membres');
  return { personnes, chevauche,
    visible: !!conteneur && conteneur.getBoundingClientRect().height > 0 };
}"""


def principal() -> int:
    try:
        admin = appel("/api/comptes", {"prenom": "Essai gestion"})
    except urllib.error.URLError as erreur:
        print(f"Synergie injoignable sur {BASE} : {erreur}", file=sys.stderr)
        return 2
    jeton = admin["jeton"]
    projet, groupe, crees, simple = None, None, [], None
    camille_jeton = None
    try:
        projet = appel("/api/projets", {"nom": PROJET, "description": "Départ"},
                       jeton=jeton)
        # Les personnes de l'essai : leur compte d'abord (on garde leur jeton pour entrer
        # avec leur propre identité), puis leur place dans le projet.
        comptes_personnes = {}
        for prenom, role in PERSONNES:
            cree = appel("/api/comptes", {"prenom": prenom})
            comptes_personnes[prenom] = cree
            appel(f"/api/projets/{projet['id']}/membres",
                  {"compte": cree["compte"]["id"], "role": role}, jeton=jeton)
        crees = [c["compte"]["id"] for c in comptes_personnes.values()]
        camille_jeton = comptes_personnes["Camille Martin"]["jeton"]
        groupe = appel("/api/themes", {"titre": GROUPE, "description": "Départ groupe",
                                       "projet": projet["id"]}, jeton=jeton)
        fiche = appel(f"/api/projets/{projet['id']}", jeton=jeton)
        crees = [m["compte"] for m in fiche["membres"] if m["prenom"] in
                 [p for p, _ in PERSONNES]] + crees
        # Un simple membre, sans aucun droit d'administration.
        simple = appel("/api/comptes", {"prenom": "Essai gestion simple"})
        appel(f"/api/projets/{projet['id']}/membres",
              {"compte": simple["compte"]["id"], "role": "membre"}, jeton=jeton)

        with sync_playwright() as p:
            nav = p.chromium.launch()

            def ouvrir(jeton_connexion, nom, route=None, largeur=1280, hauteur=900):
                ctx = nav.new_context(viewport={"width": largeur, "height": hauteur},
                                      ignore_https_errors=True)
                ctx.add_init_script(
                    "localStorage.setItem('synergie.jeton', %s);"
                    "localStorage.setItem('synergie.projet', %s);"
                    "localStorage.setItem('synergie.nom', %s);"
                    % (json.dumps(jeton_connexion), json.dumps(projet["id"]), json.dumps(nom)))
                page = ctx.new_page()
                erreurs = []
                page.on("pageerror", lambda e: erreurs.append(str(e)))
                page.goto(f"{BASE}/{route or '#p=' + projet['id']}", wait_until="load")
                page.wait_for_timeout(2500)
                return ctx, page, erreurs

            os.makedirs(CAPTURES, exist_ok=True)

            # ============================================================ 1. LE PROJET
            print("\n« Gestion du projet » — l'administrateur du projet :")
            ctx, page, erreurs = ouvrir(jeton, "Essai gestion")
            avant = page.evaluate(MESURE_APERCU, "#apercu-membres-projet")
            verifie("les personnes du projet sont visibles sur la page d'accueil",
                    bool(avant and avant["visible"] and len(avant["personnes"]) >= 4),
                    avant and [x["nom"] for x in avant["personnes"]])
            statuts = {x["nom"]: x["statut"] for x in (avant or {}).get("personnes", [])}
            verifie("chaque personne porte son statut (Admin, Membre, Visiteur)",
                    statuts.get("Essai gestion") == "Admin"
                    and statuts.get("Camille Martin") == "Membre"
                    and statuts.get("Bruno Petit") == "Visiteur", statuts)
            verifie("les personnes visibles ne se chevauchent pas",
                    avant and avant["chevauche"] == 0, avant and avant["chevauche"])
            page.screenshot(path=os.path.join(CAPTURES, "synergie-accueil-membres.png"),
                            full_page=True)

            m = page.evaluate(MESURE_GESTION)
            verifie("l'administrateur a le bouton « Gestion du projet »",
                    "Gestion du projet" in m["libelle"] and m["bouton_projet"]
                    and m["titre"].startswith("Gestion du projet"), m)

            page.click("#btn-membres")
            page.wait_for_timeout(800)
            m = page.evaluate(MESURE_GESTION)
            verifie("la fenêtre s'appelle « Gestion du projet » et porte le nom, la "
                    "description et les personnes",
                    m["titre"].startswith("Gestion du projet") and m["gestion_visible"]
                    and m["champs"] == 2 and m["fenetre"], m)

            # la fenêtre liste les personnes SANS les superposer
            liste = page.evaluate(MESURE_CHEVAUCHEMENT, "#membres-liste")
            verifie("la liste des personnes n'est plus superposée ni tassée",
                    liste["nombre"] >= 4 and liste["chevauche"] == 0 and liste["tasse"] == 0,
                    liste)

            # régler le nom et la description du projet
            page.fill("#gestion-projet-nom", PROJET + " (à jour)")
            page.fill("#gestion-projet-description", "Description mise à jour")
            page.click("#gestion-projet-enregistrer")
            page.wait_for_timeout(1500)
            apres = appel(f"/api/projets/{projet['id']}", jeton=jeton)["projet"]
            verifie("le nom et la description du projet sont vraiment enregistrés",
                    apres["nom"] == PROJET + " (à jour)"
                    and apres["description"] == "Description mise à jour",
                    f"{apres['nom']} / {apres['description']}")
            verifie("le nom du projet se voit aussitôt sur la page",
                    page.eval_on_selector("#nom-projet", "n => n.textContent")
                    == PROJET + " (à jour)")
            page.screenshot(path=os.path.join(CAPTURES, "synergie-gestion-projet.png"))
            verifie("aucune erreur JavaScript (administrateur du projet)", not erreurs, erreurs[:2])
            ctx.close()

            # ============================================================ 2. LE GROUPE
            print("\n« Gestion du groupe » — l'administrateur du groupe :")
            ctx, page, erreurs = ouvrir(jeton, "Essai gestion", route=f"#t={groupe['id']}")
            apercu = page.evaluate(MESURE_APERCU, "#apercu-membres-theme")
            verifie("les personnes du groupe sont visibles sur la page du groupe",
                    apercu and apercu["visible"] and len(apercu["personnes"]) >= 4
                    and apercu["chevauche"] == 0,
                    apercu and [f"{x['nom']} ({x['statut']})" for x in apercu["personnes"]])
            statuts_groupe = {x["nom"]: x["statut"] for x in (apercu or {}).get("personnes", [])}
            verifie("le statut est indiqué dans le groupe aussi",
                    statuts_groupe.get("Essai gestion") == "Admin"
                    and statuts_groupe.get("Camille Martin") == "Membre"
                    and statuts_groupe.get("Bruno Petit") == "Visiteur", statuts_groupe)
            page.screenshot(path=os.path.join(CAPTURES, "synergie-accueil-groupe-membres.png"),
                            full_page=True)

            bouton = page.eval_on_selector("#btn-gestion-groupe",
                                           "n => n.textContent.trim()")
            visible = page.eval_on_selector(
                "#btn-gestion-groupe", "n => !n.classList.contains('cache')")
            verifie("l'administrateur a le bouton « Gestion du groupe »",
                    visible and bouton == "Gestion du groupe", f"{bouton} / {visible}")

            page.click("#btn-gestion-groupe")
            page.wait_for_timeout(600)
            gestion_groupe = page.evaluate("""() => {
              const zone = document.querySelector('#gestion-groupe');
              return { visible: !zone.classList.contains('cache'),
                       titre: document.querySelector('#gestion-groupe-titre').value,
                       description: document.querySelector('#gestion-groupe-description').value,
                       a_ajouter: document.querySelectorAll('#membre-theme-comptes .choix-membre').length,
                       liste: document.querySelectorAll('#liste-membres-theme .membre').length };
            }""")
            verifie("« Gestion du groupe » ouvre le nom, la description et les membres",
                    gestion_groupe["visible"] and gestion_groupe["titre"] == GROUPE
                    and gestion_groupe["a_ajouter"] >= 1, gestion_groupe)
            page.screenshot(path=os.path.join(CAPTURES, "synergie-gestion-groupe.png"))

            page.fill("#gestion-groupe-titre", GROUPE + " (à jour)")
            page.fill("#gestion-groupe-description", "Description du groupe mise à jour")
            page.click("#gestion-groupe-enregistrer")
            page.wait_for_timeout(1500)
            apres_groupe = appel(f"/api/themes/{groupe['id']}", jeton=jeton)["theme"]
            verifie("le nom et la description du groupe sont vraiment enregistrés",
                    apres_groupe["titre"] == GROUPE + " (à jour)"
                    and apres_groupe["description"] == "Description du groupe mise à jour",
                    f"{apres_groupe['titre']} / {apres_groupe['description']}")
            page.screenshot(path=os.path.join(CAPTURES, "synergie-gestion-groupe-fait.png"))
            verifie("aucune erreur JavaScript (groupe)", not erreurs, erreurs[:2])
            ctx.close()

            # ============================================================ 3. LE MEMBRE SIMPLE
            print("\nUn simple membre : il lit, il ne gère pas.")
            ctx, page, erreurs = ouvrir(simple["jeton"], "Essai gestion simple")
            m2 = page.evaluate(MESURE_GESTION)
            verifie("le simple membre n'a PAS « Gestion du projet »",
                    m2["libelle"] == "Membres" and not m2["bouton_projet"]
                    and not m2["gestion_visible"] and m2["champs"] == 0
                    and m2["titre"].startswith("Membres du projet"), m2)
            verifie("le simple membre voit quand même les personnes du projet",
                    (page.evaluate(MESURE_APERCU, "#apercu-membres-projet") or {})
                    .get("visible") is True)
            page.click("#btn-membres")
            page.wait_for_timeout(800)
            liste2 = page.evaluate(MESURE_CHEVAUCHEMENT, "#membres-liste")
            verifie("il voit la liste, toujours sans chevauchement",
                    liste2["chevauche"] == 0 and liste2["tasse"] == 0, liste2)
            page.click("#membres-fermer")
            page.wait_for_timeout(300)

            # le membre simple ne peut pas renommer un groupe, ni par l'écran, ni par l'API.
            bouton_groupe = page.evaluate("""() => {
              const n = document.querySelector('#btn-gestion-groupe');
              return n ? !n.classList.contains('cache') : false;
            }""")
            verifie("il n'a PAS « Gestion du groupe » dans un groupe",
                    bouton_groupe is False, bouton_groupe)
            code = essai_appel(f"/api/themes/{groupe['id']}",
                               {"titre": "Détournement"}, simple["jeton"], methode="PUT")
            verifie("le serveur refuse à un simple membre de renommer un groupe",
                    code == 403, code)
            # et le nom du groupe n'a pas bougé
            verifie("le nom du groupe est resté intact",
                    appel(f"/api/themes/{groupe['id']}", jeton=jeton)["theme"]["titre"]
                    == GROUPE + " (à jour)")
            verifie("aucune erreur JavaScript (membre simple)", not erreurs, erreurs[:2])
            ctx.close()

            # ============================================================ 4. LE TÉLÉPHONE
            print("\nSur téléphone (390 × 740) :")
            ctx, page, erreurs = ouvrir(simple["jeton"], "Essai gestion simple",
                                        largeur=390, hauteur=740)
            apercu_mobile = page.evaluate(MESURE_APERCU, "#apercu-membres-projet")
            verifie("les personnes du projet restent visibles sur téléphone",
                    apercu_mobile and apercu_mobile["visible"]
                    and len(apercu_mobile["personnes"]) >= 4
                    and apercu_mobile["chevauche"] == 0, apercu_mobile and apercu_mobile["chevauche"])
            page.click("#btn-membres-mobile")
            page.wait_for_timeout(800)
            liste3 = page.evaluate(MESURE_CHEVAUCHEMENT, "#membres-liste")
            verifie("la liste des personnes ne se tasse pas non plus sur téléphone",
                    liste3["chevauche"] == 0 and liste3["tasse"] == 0, liste3)
            page.screenshot(path=os.path.join(CAPTURES, "synergie-membres-telephone.png"))
            verifie("aucune erreur JavaScript (téléphone)", not erreurs, erreurs[:2])
            ctx.close()

            # ---- un membre qui est ADMINISTRATEUR DU GROUPE (sans être admin du projet) ------
            print("\nUn administrateur de groupe qui n'administre pas le projet :")
            ctx, page, erreurs = ouvrir(jeton, "Essai gestion")
            page.click("#btn-membres")
            page.wait_for_timeout(800)
            page.click(f"#membres-liste .membre:has-text('Camille Martin') .membre-tete")
            page.wait_for_timeout(400)
            page.click(f"#membres-liste .membre:has-text('Camille Martin')"
                       f" .role-choix:has-text('Visiteur')")
            page.wait_for_timeout(1200)
            page.click("#membres-fermer")
            ctx.close()
            # Camille devient ADMINISTRATRICE DU GROUPE, tout en restant visiteuse du projet.
            camille = next(m for m in appel(f"/api/projets/{projet['id']}", jeton=jeton)["membres"]
                           if m["prenom"] == "Camille Martin")
            appel(f"/api/themes/{groupe['id']}/membres",
                  {"compte": camille["compte"], "role": "admin"}, jeton=jeton)
            # Camille entre avec son propre jeton.
            ctx, page, erreurs = ouvrir(camille_jeton, "Camille Martin",
                                        route=f"#t={groupe['id']}")
            bouton_camille = page.evaluate("""() => {
              const n = document.querySelector('#btn-gestion-groupe');
              return n ? !n.classList.contains('cache') : false;
            }""")
            verifie("l'administratrice du groupe a bien « Gestion du groupe »",
                    bouton_camille is True, bouton_camille)
            verifie("elle n'a PAS « Gestion du projet » (elle n'administre que le groupe)",
                    page.evaluate("""() => {
                      const n = document.querySelector('#btn-membres');
                      return n ? n.textContent.trim() : '';
                    }""") == "Membres")
            verifie("aucune erreur JavaScript (administratrice du groupe)",
                    not erreurs, erreurs[:2])
            ctx.close()

            nav.close()
    finally:
        if groupe:
            try:
                appel(f"/api/themes/{groupe['id']}", jeton=jeton, methode="DELETE")
            except Exception:
                pass
        if projet:
            try:
                appel(f"/api/projets/{projet['id']}", jeton=jeton, methode="DELETE")
            except Exception:
                pass
        menage([admin["compte"]["id"], *crees,
                (simple or {}).get("compte", {}).get("id", "")])

    echecs = sum(1 for _, ok in RESULTATS if not ok)
    print(f"\n{len(RESULTATS) - echecs}/{len(RESULTATS)} contrôles réussis")
    return 1 if echecs else 0


if __name__ == "__main__":
    sys.exit(principal())
