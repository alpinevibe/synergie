#!/usr/bin/env python3
"""Entête du téléphone : « Mon compte » n'y est plus (09/10/2026).

Demande de l'utilisateur : « dans l'affichage téléphone, n'affiche pas mon compte en haut de
l'écran puisqu'il est déjà dans le menu ».

Ce contrôle ouvre l'application dans un vrai navigateur, sur un écran de téléphone et sur un
écran d'ordinateur, et vérifie que :
  1. sur téléphone, « Mon compte » n'est PAS en haut (l'entête ne le montre plus) ;
  2. l'onglet « Compte » de la barre du bas ouvre bien « Mon compte » ;
  3. sur ordinateur, le bouton « Mon compte » reste à sa place dans l'entête.

    python3 tests/tester_entete_mobile.py
    SYNERGIE_SITE=https://synergie.alpinevibe.fr python3 tests/tester_entete_mobile.py
"""
import json
import os
import sys
import urllib.error
import urllib.request

from playwright.sync_api import sync_playwright

BASE = os.environ.get("SYNERGIE_SITE", "http://127.0.0.1:8077").rstrip("/")
CAPTURES = os.environ.get("CHECKUP_CAPTURES", "/home/ubuntu/captures")

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


def principal() -> int:
    try:
        compte = appel("/api/comptes", {"prenom": "Essai entete"})
    except urllib.error.URLError as erreur:
        print(f"Synergie injoignable sur {BASE} : {erreur}", file=sys.stderr)
        return 2
    jeton = compte["jeton"]
    projet = None
    try:
        projet = appel("/api/projets", {"nom": "Essai — entête téléphone"}, jeton=jeton)
        with sync_playwright() as p:
            nav = p.chromium.launch()

            # ---- 1 et 2 : sur téléphone -------------------------------------------------
            print("\nSur téléphone (390 × 740) :")
            ctx = nav.new_context(viewport={"width": 390, "height": 740}, ignore_https_errors=True)
            ctx.add_init_script(
                "localStorage.setItem('synergie.jeton', %s);"
                "localStorage.setItem('synergie.projet', %s);"
                "localStorage.setItem('synergie.nom', 'Essai entete');"
                % (json.dumps(jeton), json.dumps(projet["id"])))
            page = ctx.new_page()
            erreurs = []
            page.on("pageerror", lambda e: erreurs.append(str(e)))
            page.goto(f"{BASE}/#p={projet['id']}", wait_until="load")
            page.wait_for_timeout(2500)
            verifie("l'application se présente en version téléphone",
                    page.evaluate("document.body.dataset.vue") == "mobile")
            verifie("« Mon compte » n'est plus en haut de l'écran",
                    page.is_visible("#btn-compte") is False)
            verifie("la barre du bas propose bien « Compte »",
                    page.is_visible("#nav-mobile button[data-section=compte]") is True)
            os.makedirs(CAPTURES, exist_ok=True)
            page.screenshot(path=os.path.join(CAPTURES, "synergie-entete-telephone.png"))
            page.click("#nav-mobile button[data-section=compte]")
            page.wait_for_timeout(1200)
            verifie("l'onglet « Compte » ouvre bien « Mon compte »",
                    page.is_visible("#vue-compte .boite-nom") is True)
            verifie("aucune erreur JavaScript", not erreurs, erreurs[:2])
            ctx.close()

            # ---- 3 : sur ordinateur ------------------------------------------------------
            print("\nSur ordinateur (1100 × 800) :")
            ctx = nav.new_context(viewport={"width": 1100, "height": 800}, ignore_https_errors=True)
            ctx.add_init_script(
                "localStorage.setItem('synergie.jeton', %s);"
                "localStorage.setItem('synergie.projet', %s);"
                "localStorage.setItem('synergie.nom', 'Essai entete');"
                % (json.dumps(jeton), json.dumps(projet["id"])))
            page = ctx.new_page()
            page.goto(f"{BASE}/#p={projet['id']}", wait_until="load")
            page.wait_for_timeout(2500)
            verifie("sur ordinateur, « Mon compte » reste dans l'entête",
                    page.is_visible("#btn-compte") is True)
            ctx.close()
            nav.close()
    finally:
        if projet:
            try:
                appel(f"/api/projets/{projet['id']}", jeton=jeton, methode="DELETE")
            except Exception:
                pass
        menage([compte["compte"]["id"]])

    echecs = sum(1 for _, ok in RESULTATS if not ok)
    print(f"\n{len(RESULTATS) - echecs}/{len(RESULTATS)} contrôles réussis")
    return 1 if echecs else 0


if __name__ == "__main__":
    sys.exit(principal())
