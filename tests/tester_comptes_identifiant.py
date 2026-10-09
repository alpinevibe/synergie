#!/usr/bin/env python3
"""Mon compte : identifiant personnel et déconnexion (09/10/2026).

Défaut rapporté par l'utilisateur : « dans l'application synergie, je n'arrive pas à me
connecter avec mon identifiant ».

Deux causes, corrigées ici :
  1. quand l'identifiant saisi était déjà utilisé, le serveur répondait **500** (panne) au lieu
     d'un message clair — l'écran « Mon compte » restait muet ;
  2. l'application n'avait **aucune déconnexion** : un appareil restait collé au compte du
     navigateur, impossible de reprendre son identifiant personnel.

Ce contrôle travaille sur deux comptes d'essai (créés puis effacés) et un vrai navigateur :
  1. poser un identifiant personnel : « Enregistré. » ;
  2. reprendre un identifiant déjà utilisé : message clair, PAS de panne ;
  3. se déconnecter : retour à l'écran d'entrée, plus rien en mémoire ;
  4. entrer de nouveau avec l'identifiant : on retrouve ses projets.

    python3 tests/tester_comptes_identifiant.py
    SYNERGIE_SITE=https://synergie.alpinevibe.fr python3 tests/tester_comptes_identifiant.py
"""
import json
import os
import sys
import urllib.error
import urllib.request

from playwright.sync_api import sync_playwright

BASE = os.environ.get("SYNERGIE_SITE", "http://127.0.0.1:8077").rstrip("/")
CAPTURES = os.environ.get("CHECKUP_CAPTURES", "/home/ubuntu/captures")
IDENTIFIANT = "essai.compte.1"
IDENTIFIANT_PRIS = "essai.compte.2"

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


def menage(identifiants):
    try:
        sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
        from moteur import atelier
        with atelier.connexion() as base:
            for identifiant in identifiants:
                for table in ("projet_membres", "theme_membres", "abonnements", "responsables"):
                    base.execute(f"delete from {table} where compte = ?", (identifiant,))
                base.execute("delete from comptes where id = ?", (identifiant,))
    except Exception as erreur:
        print(f"  (ménage impossible : {erreur})")


MESURE = """() => ({
  entree_visible: !document.getElementById('accueil-nom').classList.contains('cache'),
  compte_visible: !document.getElementById('vue-compte').classList.contains('cache'),
  etat: (document.getElementById('c-etat') || {}).textContent || '',
  erreur_entree: (document.getElementById('nom-erreur') || {}).textContent || '',
  jeton: localStorage.getItem('synergie.jeton') || '',
  vue: [...document.querySelectorAll('main')].filter((m) => !m.classList.contains('cache'))
         .map((m) => m.id)[0] || ''
})"""


def principal() -> int:
    try:
        premier = appel("/api/comptes", {"prenom": "Essai compte 1"})
        second = appel("/api/comptes", {"prenom": "Essai compte 2"})
        appel("/api/comptes/moi", {"identifiant": IDENTIFIANT_PRIS}, jeton=second["jeton"],
              methode="PUT")
    except urllib.error.URLError as erreur:
        print(f"Synergie injoignable sur {BASE} : {erreur}", file=sys.stderr)
        return 2
    identifiants = [premier["compte"]["id"], second["compte"]["id"]]
    projet = None
    try:
        projet = appel("/api/projets", {"nom": "Essai — compte et identifiant"},
                       jeton=premier["jeton"])

        with sync_playwright() as p:
            nav = p.chromium.launch()
            ctx = nav.new_context(viewport={"width": 1100, "height": 800},
                                  ignore_https_errors=True)
            ctx.add_init_script(
                "localStorage.setItem('synergie.jeton', %s);"
                "localStorage.setItem('synergie.projet', %s);"
                "localStorage.setItem('synergie.nom', 'Essai compte 1');"
                % (json.dumps(premier["jeton"]), json.dumps(projet["id"])))
            ctx.add_cookies([{"name": "synergie", "value": premier["jeton"], "url": BASE,
                              "httpOnly": True, "sameSite": "Lax"}])
            page = ctx.new_page()
            erreurs = []
            page.on("pageerror", lambda e: erreurs.append(str(e)))
            page.on("dialog", lambda dialogue: dialogue.accept())     # « Se déconnecter ? » : oui
            page.goto(f"{BASE}/#p={projet['id']}", wait_until="load")
            page.wait_for_timeout(2500)

            # ---- 1 : poser son identifiant personnel -------------------------------------
            print("\nPoser son identifiant personnel :")
            page.click("#btn-compte")            # « Mon compte », dans l'entête
            page.wait_for_timeout(800)
            page.fill("#c-identifiant", IDENTIFIANT)
            page.click("#c-enregistrer")
            page.wait_for_timeout(1500)
            m = page.evaluate(MESURE)
            verifie("l'identifiant personnel s'enregistre", "Enregistré" in m["etat"], m["etat"])

            # ---- 2 : un identifiant déjà utilisé, message clair et pas de panne ----------
            print("\nReprendre un identifiant déjà utilisé :")
            page.fill("#c-identifiant", IDENTIFIANT_PRIS)
            page.click("#c-enregistrer")
            page.wait_for_timeout(1500)
            m = page.evaluate(MESURE)
            verifie("le refus est expliqué clairement",
                    "déjà utilisé" in m["etat"], m["etat"])
            verifie("aucune panne serveur n'apparaît", "500" not in m["etat"]
                    and "INTERNAL" not in m["etat"], m["etat"])
            os.makedirs(CAPTURES, exist_ok=True)
            page.screenshot(path=os.path.join(CAPTURES, "synergie-compte-identifiant.png"))

            # ---- 3 : se déconnecter ------------------------------------------------------
            print("\nSe déconnecter :")
            page.click("#c-deconnecter")
            page.wait_for_timeout(2000)
            m = page.evaluate(MESURE)
            verifie("l'écran d'entrée par identifiant revient", m["entree_visible"] is True)
            verifie("plus aucun jeton en mémoire", m["jeton"] == "", m["jeton"][:8])

            # ---- 4 : entrer de nouveau avec son identifiant ------------------------------
            print("\nEntrer de nouveau avec son identifiant :")
            page.fill("#identifiant", IDENTIFIANT)
            page.click("#btn-prenom")
            page.wait_for_timeout(2500)
            m = page.evaluate(MESURE)
            verifie("l'entrée avec l'identifiant personnel fonctionne",
                    m["entree_visible"] is False, m["erreur_entree"])
            verifie("on retrouve ses projets", m["vue"] in ("vue-projets", "vue-projet"), m["vue"])
            verifie("aucune erreur JavaScript", not erreurs, erreurs[:2])
            ctx.close()
            nav.close()
    finally:
        if projet:
            # Le jeton du début ne vaut plus rien : l'essai s'est DÉCONNECTÉ (c'est le but).
            # On reprend un jeton neuf avec l'identifiant posé pendant l'essai.
            jeton_propre = premier["jeton"]
            try:
                jeton_propre = appel("/api/connexion", {"identifiant": IDENTIFIANT})["jeton"]
            except Exception:
                pass
            try:
                appel(f"/api/projets/{projet['id']}", jeton=jeton_propre, methode="DELETE")
            except Exception:
                pass
        menage(identifiants)

    echecs = sum(1 for _, ok in RESULTATS if not ok)
    print(f"\n{len(RESULTATS) - echecs}/{len(RESULTATS)} contrôles réussis")
    return 1 if echecs else 0


if __name__ == "__main__":
    sys.exit(principal())
