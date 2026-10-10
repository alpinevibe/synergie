#!/usr/bin/env python3
"""Le temps réel arrive-t-il vraiment au navigateur, sans rechargement ? (10/10/2026)

C'est l'épreuve de bout en bout de la chaîne : un navigateur ouvert sur le site public →
nginx → **service de flux asynchrone** (127.0.0.1:8078) → canal `NOTIFY` PostgreSQL →
application qui écrit. Un seul maillon manquant et la personne ne voit rien.

    SYNERGIE_SITE=https://synergie.alpinevibe.fr \\
        /home/ubuntu/.venv-scan/bin/python tests/tester_temps_reel.py

Deux écritures sont éprouvées : une **note** sur le tableau blanc et un **message** dans la
discussion du groupe. Dans les deux cas, la page ne doit pas être rechargée : c'est le flux
qui apporte la nouveauté. L'essai efface derrière lui le compte et le projet créés.
"""
from __future__ import annotations

import json
import os
import sys
import time
import urllib.error
import urllib.request

RACINE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, RACINE)

SITE = os.environ.get("SYNERGIE_SITE", "http://127.0.0.1:8077").rstrip("/")
UA = ("Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) "
      "Chrome/124.0 Safari/537.36")
COMPTE, PROJET, GROUPE = "Essai temps réel", "Projet essai temps réel", "Groupe essai temps réel"
TEXTE_NOTE = "Note arrivée en direct (essai)."
TEXTE_MESSAGE = "Message arrivé en direct (essai)."

RESULTATS: list[tuple[str, bool]] = []


def verifie(titre: str, condition, detail="") -> None:
    RESULTATS.append((titre, bool(condition)))
    print(("  ✅ " if condition else "  ❌ ") + titre + ((" — " + str(detail)) if detail else ""))


def appel(chemin: str, corps=None, jeton=None):
    donnees = json.dumps(corps).encode("utf-8") if corps is not None else None
    requete = urllib.request.Request(SITE + chemin, data=donnees,
                                     method="POST" if donnees else "GET")
    requete.add_header("Content-Type", "application/json")
    requete.add_header("User-Agent", UA)
    if jeton:
        requete.add_header("X-Synergie-Jeton", jeton)
    with urllib.request.urlopen(requete, timeout=30) as reponse:
        return json.loads(reponse.read().decode("utf-8"))


def principal() -> int:
    try:
        compte = appel("/api/comptes", {"prenom": COMPTE})
    except urllib.error.URLError as erreur:
        print(f"Synergie injoignable sur {SITE} : {erreur}", file=sys.stderr)
        return 2
    jeton = compte["jeton"]
    projet = appel("/api/projets", {"nom": PROJET}, jeton=jeton)
    groupe = appel("/api/themes", {"titre": GROUPE, "projet": projet["id"]}, jeton=jeton)
    identifiant = groupe["id"]
    print(f"— navigateur ouvert sur {SITE} (groupe {identifiant}) —")

    from playwright.sync_api import sync_playwright

    with sync_playwright() as p:
        navigateur = p.chromium.launch()
        contexte = navigateur.new_context(viewport={"width": 1280, "height": 900},
                                          ignore_https_errors=True)
        contexte.add_init_script(
            "localStorage.setItem('synergie.jeton', %s);"
            "localStorage.setItem('synergie.projet', %s);"
            "localStorage.setItem('synergie.nom', 'Essai temps réel');"
            % (json.dumps(jeton), json.dumps(projet["id"])))
        contexte.add_cookies([{"name": "synergie", "value": jeton, "url": SITE,
                               "httpOnly": True, "sameSite": "Lax"}])
        page = contexte.new_page()
        erreurs: list[str] = []
        page.on("pageerror", lambda e: erreurs.append(str(e)))
        page.goto(f"{SITE}/#t={identifiant}", wait_until="load")
        page.wait_for_timeout(4000)          # le tableau et le flux s'installent
        verifie("la page est ouverte sur le groupe",
                len(page.locator("#monde, .plateau, .theme-principal").all()) > 0)

        # 1. une note écrite par quelqu'un d'autre (ici, l'API) doit apparaître seule
        appel(f"/api/themes/{identifiant}/notes", {"texte": TEXTE_NOTE, "x": 120, "y": 140},
              jeton=jeton)
        apparue = False
        for _ in range(20):
            page.wait_for_timeout(500)
            if TEXTE_NOTE in page.inner_text("body"):
                apparue = True
                break
        verifie("la note s'affiche sans rechargement", apparue,
                "rien reçu en 10 s" if not apparue else "")

        # 2. un message de discussion, idem
        appel(f"/api/themes/{identifiant}/messages", {"texte": TEXTE_MESSAGE}, jeton=jeton)
        vu = False
        for _ in range(20):
            page.wait_for_timeout(500)
            if TEXTE_MESSAGE in page.inner_text("body"):
                vu = True
                break
        verifie("le message s'affiche sans rechargement", vu,
                "rien reçu en 10 s" if not vu else "")

        # 3. un déplacement en cours (geste) : la note doit bouger chez les autres
        notes = appel(f"/api/themes/{identifiant}", None, jeton=jeton)["notes"]
        if notes:
            avant = page.evaluate(
                """(id) => { const n = document.querySelector('.note[data-id="' + id + '"]');
                            return n ? n.style.left : null; }""", notes[0]["id"])
            appel(f"/api/themes/{identifiant}/gestes",
                  {"id": notes[0]["id"], "x": 642, "y": 318}, jeton=jeton)
            bouge = False
            for _ in range(16):
                page.wait_for_timeout(500)
                apres = page.evaluate(
                    """(id) => { const n = document.querySelector('.note[data-id="' + id + '"]');
                                return n ? n.style.left : null; }""", notes[0]["id"])
                if apres and apres != avant:
                    bouge = True
                    break
            verifie("un geste en cours déplace la note chez les autres", bouge,
                    "" if bouge else f"position inchangée ({avant})")

        verifie("aucune erreur JavaScript", not erreurs, erreurs[:2])
        page.screenshot(path="/home/ubuntu/captures/synergie-temps-reel.png", full_page=False)
        contexte.close()
        navigateur.close()

    # Ménage (par l'API, comme le ferait un administrateur) : le groupe emporte sa
    # discussion et ses notes, le projet emporte ses groupes.
    for chemin in (f"/api/themes/{identifiant}", f"/api/projets/{projet['id']}"):
        try:
            requete = urllib.request.Request(SITE + chemin, method="DELETE")
            requete.add_header("User-Agent", UA)
            requete.add_header("X-Synergie-Jeton", jeton)
            with urllib.request.urlopen(requete, timeout=30):
                pass
        except Exception as erreur:  # noqa: BLE001 - le ménage ne masque pas le résultat
            print(f"  (ménage de {chemin} incomplet : {erreur})")

    echecs = [titre for titre, ok in RESULTATS if not ok]
    print("\n" + "=" * 60)
    print(f"{len(RESULTATS) - len(echecs)} contrôle(s) réussi(s), {len(echecs)} échec(s).")
    if echecs:
        print("ÉCHEC : " + " ; ".join(echecs))
        return 1
    print("CONFORME : le temps réel arrive au navigateur par le service de flux.")
    return 0


if __name__ == "__main__":
    sys.exit(principal())
