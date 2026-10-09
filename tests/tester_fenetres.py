#!/usr/bin/env python3
"""Les grandes fenêtres de Synergie ne cachent plus leur bouton de fermeture (09/10/2026).

Demande de l'utilisateur : « problème d'affichage de la fenêtre membre, je ne vois pas le bouton
fermé ».

Ce contrôle crée un projet d'essai avec une longue liste de membres, puis vérifie dans un vrai
navigateur, sur un écran d'ordinateur ET sur un téléphone, que :
  1. la fenêtre ne dépasse jamais l'écran ;
  2. la barre « Fermer » reste visible en bas, sans rien faire défiler ;
  3. la croix ✕ est visible en haut, et elle ferme bien la fenêtre.

    python3 tests/tester_fenetres.py
    SYNERGIE_SITE=https://synergie.alpinevibe.fr python3 tests/tester_fenetres.py
"""
import json
import os
import sys
import urllib.error
import urllib.request

from playwright.sync_api import sync_playwright

BASE = os.environ.get("SYNERGIE_SITE", "http://127.0.0.1:8077").rstrip("/")
CAPTURES = os.environ.get("CHECKUP_CAPTURES", "/home/ubuntu/captures")
TITRE = "Essai — fenêtres"
MEMBRES = ["Aline", "Bruno", "Chloé", "Damien", "Élodie", "Farid", "Gaëlle"]
ECRANS = [(1024, 700), (390, 740)]

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


def menage(compte_id, autres):
    try:
        sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
        from moteur import atelier
        with atelier.connexion() as base:
            for identifiant in [compte_id, *autres]:
                for table in ("projet_membres", "theme_membres", "abonnements", "responsables"):
                    base.execute(f"delete from {table} where compte = ?", (identifiant,))
                base.execute("delete from comptes where id = ?", (identifiant,))
    except Exception as erreur:
        print(f"  (ménage impossible : {erreur})")


MESURE = """() => {
  const boite = (s) => { const n = document.querySelector(s); if (!n) return null;
    const b = n.getBoundingClientRect();
    return { haut: Math.round(b.top), bas: Math.round(b.bottom), h: Math.round(b.height) }; };
  const croix = document.querySelector('#vue-membres .croix-fermeture');
  const style = croix ? getComputedStyle(croix) : null;
  return {
    vis: window.innerHeight,
    fenetre: boite('#vue-membres .boite-nom'),
    barre: boite('#vue-membres .barre-boutons'),
    croix: croix ? boite('#vue-membres .croix-fermeture') : null,
    croix_visible: !!(croix && style.display !== 'none' && style.visibility !== 'hidden'
                      && Number(style.opacity) > 0)
  };
}"""


def principal() -> int:
    try:
        compte = appel("/api/comptes", {"prenom": "Essai fenetres"})
    except urllib.error.URLError as erreur:
        print(f"Synergie injoignable sur {BASE} : {erreur}", file=sys.stderr)
        return 2
    jeton = compte["jeton"]
    projet, crees = None, []
    try:
        projet = appel("/api/projets", {"nom": TITRE}, jeton=jeton)
        for prenom in MEMBRES:
            appel(f"/api/projets/{projet['id']}/membres", {"prenom": prenom, "role": "membre"},
                  jeton=jeton)
        crees = [m["compte"] for m in appel(f"/api/projets/{projet['id']}",
                                            jeton=jeton)["membres"]
                 if m["prenom"] in MEMBRES]

        with sync_playwright() as p:
            nav = p.chromium.launch()
            for largeur, hauteur in ECRANS:
                print(f"\nÉcran {largeur} × {hauteur} :")
                ctx = nav.new_context(viewport={"width": largeur, "height": hauteur},
                                      device_scale_factor=1, ignore_https_errors=True)
                ctx.add_init_script(
                    "localStorage.setItem('synergie.jeton', %s);"
                    "localStorage.setItem('synergie.projet', %s);"
                    "localStorage.setItem('synergie.nom', 'Essai fenetres');"
                    % (json.dumps(jeton), json.dumps(projet["id"])))
                ctx.add_cookies([{"name": "synergie", "value": jeton, "url": BASE,
                                  "httpOnly": True, "sameSite": "Lax"}])
                page = ctx.new_page()
                erreurs = []
                page.on("pageerror", lambda e: erreurs.append(str(e)))
                page.goto(f"{BASE}/#p={projet['id']}", wait_until="load")
                page.wait_for_timeout(2500)
                # Sur téléphone, la barre de l'entête est remplacée par un bouton dédié.
                page.click("#btn-membres" if page.is_visible("#btn-membres")
                           else "#btn-membres-mobile")
                page.wait_for_timeout(700)
                m = page.evaluate(MESURE)
                os.makedirs(CAPTURES, exist_ok=True)
                page.screenshot(path=os.path.join(
                    CAPTURES, f"synergie-fenetre-membres-{largeur}x{hauteur}.png"))

                verifie("la fenêtre ne dépasse pas l'écran",
                        m["fenetre"] and m["fenetre"]["bas"] <= m["vis"] + 1,
                        f"{m['fenetre']} pour un écran de {m['vis']}")
                verifie("la barre « Fermer » est visible en bas, sans rien faire défiler",
                        m["barre"] and m["barre"]["haut"] >= 0
                        and m["barre"]["bas"] <= m["vis"] + 1,
                        f"{m['barre']} pour un écran de {m['vis']}")
                verifie("la croix ✕ est visible en haut",
                        m["croix"] and m["croix_visible"] and m["croix"]["haut"] >= 0
                        and m["croix"]["bas"] <= m["vis"] + 1, m["croix"])
                # la croix ferme bien la fenêtre
                page.click("#vue-membres .croix-fermeture")
                page.wait_for_timeout(400)
                fermee = page.eval_on_selector("#vue-membres", "n => n.classList.contains('cache')")
                verifie("la croix ✕ ferme la fenêtre", fermee is True)
                verifie("aucune erreur JavaScript", not erreurs, erreurs[:2])
                ctx.close()
            nav.close()
    finally:
        if projet:
            try:
                appel(f"/api/projets/{projet['id']}", jeton=jeton, methode="DELETE")
            except Exception:
                pass
        menage(compte["compte"]["id"], crees)

    echecs = sum(1 for _, ok in RESULTATS if not ok)
    print(f"\n{len(RESULTATS) - echecs}/{len(RESULTATS)} contrôles réussis")
    return 1 if echecs else 0


if __name__ == "__main__":
    sys.exit(principal())
