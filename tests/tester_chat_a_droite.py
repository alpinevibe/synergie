#!/usr/bin/env python3
"""La discussion d'un GROUPE n'est plus un onglet : elle est en colonne de droite (09/10/2026).

Demande de l'utilisateur : « dans synergie : retire l'onglet discussion dans les groupes et
mets la fenêtre de chat sur la droite ».

Ce contrôle travaille sur une VRAIE session (compte, projet et groupe d'essai créés puis
effacés) et un VRAI navigateur :
  1. l'onglet « Discussion » a disparu de la barre d'onglets du groupe ;
  2. les autres onglets sont toujours là (Tableau blanc, Pages, Documents, Votes, Journal) ;
  3. la discussion est visible à DROITE des onglets sur un écran large ;
  4. sur un écran étroit, elle passe simplement SOUS le contenu, toujours visible ;
  5. les messages du groupe s'y affichent.

    python3 tests/tester_chat_a_droite.py
    SYNERGIE_SITE=http://127.0.0.1:8077 python3 tests/tester_chat_a_droite.py
"""
import json
import os
import sys
import urllib.error
import urllib.request

from playwright.sync_api import sync_playwright

BASE = os.environ.get("SYNERGIE_SITE", "http://127.0.0.1:8077").rstrip("/")
CAPTURES = os.environ.get("CHECKUP_CAPTURES", "/home/ubuntu/captures")
TITRE_PROJET = "Essai — discussion à droite"
TITRE_GROUPE = "Groupe d'essai"
MESSAGE = "Bonjour depuis l'essai automatique."

RESULTATS = []


def verifie(titre, condition, detail=""):
    RESULTATS.append((titre, bool(condition)))
    print(("  ✅ " if condition else "  ❌ ") + titre + ((" — " + str(detail)) if detail else ""))


def appel(chemin, corps=None, jeton=None, methode=None):
    """Appel à l'API de Synergie (en-tête d'authentification, comme l'application)."""
    donnees = json.dumps(corps).encode("utf-8") if corps is not None else None
    requete = urllib.request.Request(BASE + chemin, data=donnees,
                                     method=methode or ("POST" if donnees else "GET"))
    requete.add_header("Content-Type", "application/json")
    if jeton:
        requete.add_header("X-Synergie-Jeton", jeton)
    with urllib.request.urlopen(requete, timeout=30) as reponse:
        return json.loads(reponse.read().decode("utf-8"))


MESURE = """() => {
  const boite = (selecteur) => {
    const n = document.querySelector(selecteur);
    if (!n || !n.offsetParent && getComputedStyle(n).position !== 'fixed') return null;
    const b = n.getBoundingClientRect();
    if (b.width < 2 || b.height < 2) return null;
    return { gauche: Math.round(b.left), droite: Math.round(b.right),
             haut: Math.round(b.top), bas: Math.round(b.bottom) };
  };
  return {
    onglets: [...document.querySelectorAll('#onglets-theme button')].map((b) => b.textContent.trim()),
    discussion: boite('.theme-chat'),
    contenu: boite('.theme-principal'),
    fil: (document.querySelector('#fil-theme') || {}).innerText || '',
    largeur: window.innerWidth
  };
}"""


def principal() -> int:
    try:
        compte = appel("/api/comptes", {"prenom": "Essai chat"})
    except urllib.error.URLError as erreur:
        print(f"Synergie injoignable sur {BASE} : {erreur}", file=sys.stderr)
        return 2
    jeton = compte["jeton"]
    projet = appel("/api/projets", {"nom": TITRE_PROJET}, jeton=jeton)
    groupe = appel("/api/themes", {"titre": TITRE_GROUPE, "projet": projet["id"]}, jeton=jeton)
    message = appel(f"/api/themes/{groupe['id']}/messages", {"texte": MESSAGE}, jeton=jeton)

    try:
        with sync_playwright() as p:
            nav = p.chromium.launch()
            for largeur, hauteur, colonne in ((1440, 900, True), (900, 900, False)):
                print(f"\nÉcran {largeur} × {hauteur} :")
                ctx = nav.new_context(viewport={"width": largeur, "height": hauteur},
                                      device_scale_factor=1, ignore_https_errors=True)
                ctx.add_init_script(
                    "localStorage.setItem('synergie.jeton', %s);"
                    "localStorage.setItem('synergie.projet', %s);"
                    "localStorage.setItem('synergie.nom', 'Essai chat');"
                    % (json.dumps(jeton), json.dumps(projet["id"])))
                ctx.add_cookies([{"name": "synergie", "value": jeton,
                                  "url": BASE, "httpOnly": True, "sameSite": "Lax"}])
                page = ctx.new_page()
                erreurs = []
                page.on("pageerror", lambda e: erreurs.append(str(e)))
                page.goto(f"{BASE}/#t={groupe['id']}", wait_until="load")
                page.wait_for_timeout(3000)
                m = page.evaluate(MESURE)
                os.makedirs(CAPTURES, exist_ok=True)
                page.screenshot(path=os.path.join(
                    CAPTURES, f"synergie-chat-droite-{largeur}x{hauteur}.png"), full_page=True)

                if largeur == 1440:
                    verifie("l'onglet « Discussion » a disparu",
                            "Discussion" not in m["onglets"], m["onglets"])
                    verifie("les autres onglets du groupe sont là",
                            m["onglets"] == ["Tableau blanc", "Pages", "Documents",
                                             "Votes et sondages", "Journal"],
                            m["onglets"])
                    verifie("le message du groupe s'affiche dans la discussion",
                            MESSAGE in m["fil"], m["fil"][:80])
                verifie("la discussion est visible", m["discussion"] is not None)
                if m["discussion"] and m["contenu"]:
                    if colonne:
                        verifie("la discussion est à DROITE des onglets",
                                m["discussion"]["gauche"] >= m["contenu"]["droite"] - 2,
                                f"discussion à {m['discussion']['gauche']} px, "
                                f"contenu jusqu'à {m['contenu']['droite']} px")
                    else:
                        verifie("sur écran étroit, la discussion passe SOUS le contenu",
                                m["discussion"]["haut"] >= m["contenu"]["bas"] - 2,
                                f"discussion à {m['discussion']['haut']} px, "
                                f"contenu jusqu'à {m['contenu']['bas']} px")
                verifie("aucune erreur JavaScript", not erreurs, erreurs[:2])
                ctx.close()
            nav.close()
    finally:
        for chemin in (f"/api/themes/{groupe['id']}", f"/api/projets/{projet['id']}"):
            try:
                appel(chemin, jeton=jeton, methode="DELETE")
            except Exception:                       # le ménage ne doit jamais tout casser
                pass

    echecs = sum(1 for _, ok in RESULTATS if not ok)
    print(f"\n{len(RESULTATS) - echecs}/{len(RESULTATS)} contrôles réussis")
    return 1 if echecs else 0


if __name__ == "__main__":
    sys.exit(principal())
