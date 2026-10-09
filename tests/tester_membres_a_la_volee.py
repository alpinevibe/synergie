#!/usr/bin/env python3
"""Ajouter PLUSIEURS membres à la volée dans Synergie (09/10/2026).

Demande de l'utilisateur : « la possibilité d'ajouter plusieurs membres à la volée dans
Synergie ».

Ce contrôle travaille sur une VRAIE session (compte, projet, trois membres et un groupe
d'essai, créés puis effacés) et un VRAI navigateur :
  1. au projet : on colle TROIS adresses d'un coup, un seul clic → trois invitations ;
  2. les trois liens personnels sont là, avec le bouton « Copier les 3 liens » ;
  3. au groupe : les trois personnes du projet se cochent d'un geste (« Tout cocher ») ;
  4. le bouton annonce « Ajouter au groupe (3) » et les ajoute toutes d'un coup ;
  5. les trois ont bien un rôle dans le groupe.

    python3 tests/tester_membres_a_la_volee.py
    SYNERGIE_SITE=https://synergie.alpinevibe.fr python3 tests/tester_membres_a_la_volee.py
"""
import json
import os
import sys
import urllib.error
import urllib.request

from playwright.sync_api import sync_playwright

BASE = os.environ.get("SYNERGIE_SITE", "http://127.0.0.1:8077").rstrip("/")
CAPTURES = os.environ.get("CHECKUP_CAPTURES", "/home/ubuntu/captures")
TITRE_PROJET = "Essai — plusieurs membres à la volée"
TITRE_GROUPE = "Groupe d'essai"
# Domaine réservé (RFC 2606) : aucune invitation ne peut partir pour de vrai.
ADRESSES = ["camille.essai@exemple.invalid", "sofia.essai@exemple.invalid",
            "nadia.essai@exemple.invalid"]
PERSONNES = ["Camille", "Sofia", "Nadia"]

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
    # Le site public refuse les requêtes qui ne ressemblent pas à un navigateur.
    requete.add_header("User-Agent", "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
                                     "(KHTML, like Gecko) Chrome/124.0 Safari/537.36")
    if jeton:
        requete.add_header("X-Synergie-Jeton", jeton)
    with urllib.request.urlopen(requete, timeout=30) as reponse:
        return json.loads(reponse.read().decode("utf-8"))


def menage(compte_id: str, autres: list[str]) -> None:
    """Efface tout ce que ce contrôle a créé : aucune trace dans l'application."""
    try:
        sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
        from moteur import atelier                  # noqa: E402 (même base que l'application)
        with atelier.connexion() as base:
            for identifiant in [compte_id, *autres]:
                for table in ("projet_membres", "theme_membres", "abonnements",
                              "responsables"):
                    base.execute(f"delete from {table} where compte = ?", (identifiant,))
                base.execute("delete from comptes where id = ?", (identifiant,))
    except Exception as erreur:                     # le ménage ne doit jamais tout casser
        print(f"  (ménage impossible : {erreur})")


def principal() -> int:
    try:
        compte = appel("/api/comptes", {"prenom": "Essai membres"})
    except urllib.error.URLError as erreur:
        print(f"Synergie injoignable sur {BASE} : {erreur}", file=sys.stderr)
        return 2
    jeton = compte["jeton"]
    projet, groupe, crees = None, None, []
    try:
        projet = appel("/api/projets", {"nom": TITRE_PROJET}, jeton=jeton)
        # Trois personnes entrent dans le projet (leur compte est créé à la volée).
        for personne in PERSONNES:
            appel(f"/api/projets/{projet['id']}/membres",
                  {"prenom": personne, "role": "membre"}, jeton=jeton)
        groupe = appel("/api/themes", {"titre": TITRE_GROUPE, "projet": projet["id"]},
                       jeton=jeton)
        crees = [m["compte"] for m in appel(f"/api/projets/{projet['id']}",
                                            jeton=jeton)["membres"]
                 if m["prenom"] in PERSONNES]

        with sync_playwright() as p:
            nav = p.chromium.launch()
            erreurs = []

            def ouvrir(url):
                """Une page NEUVE à chaque fois : changer seulement l'ancre ne recharge pas
                l'application (le navigateur garde la page)."""
                ctx = nav.new_context(viewport={"width": 1440, "height": 950},
                                      device_scale_factor=1, ignore_https_errors=True)
                ctx.add_init_script(
                    "localStorage.setItem('synergie.jeton', %s);"
                    "localStorage.setItem('synergie.projet', %s);"
                    "localStorage.setItem('synergie.nom', 'Essai membres');"
                    % (json.dumps(jeton), json.dumps(projet["id"])))
                ctx.add_cookies([{"name": "synergie", "value": jeton, "url": BASE,
                                  "httpOnly": True, "sameSite": "Lax"}])
                page = ctx.new_page()
                page.on("pageerror", lambda e: erreurs.append(str(e)))
                page.goto(url, wait_until="load")
                page.wait_for_timeout(2500)
                return page

            os.makedirs(CAPTURES, exist_ok=True)

            # ---- 1 et 2 : plusieurs adresses d'un coup, au PROJET ------------------------
            print("\nAu projet — trois adresses collées d'un coup :")
            page = ouvrir(f"{BASE}/#p={projet['id']}")
            page.click("#btn-membres")
            page.wait_for_timeout(600)
            page.fill("#membres-emails", ", ".join(ADRESSES[:2]) + "\n" + ADRESSES[2])
            page.click("#membre-ajouter")
            page.wait_for_timeout(2500)
            page.screenshot(path=os.path.join(CAPTURES, "synergie-membres-projet.png"),
                            full_page=True)
            liens = page.eval_on_selector_all("#invitations-en-cours .invitation",
                                              "n => n.length")
            verifie("les trois invitations sont créées d'un seul clic", liens == 3, liens)
            reste = page.eval_on_selector("#membres-emails", "n => n.value")
            verifie("le champ des adresses se vide après l'ajout", reste.strip() == "", reste)
            invitations = appel(f"/api/projets/{projet['id']}/invitations",
                                jeton=jeton)["invitations"]
            en_attente = [i for i in invitations if not i["utilise_le"]]
            verifie("l'application connaît bien les trois invitations",
                    len(en_attente) == 3, [i["email"] for i in en_attente])
            copier = page.eval_on_selector_all(
                "#invitations-en-cours button",
                "n => n.map(b => b.textContent.trim())")
            verifie("le bouton propose de copier les trois liens d'un coup",
                    any("3 liens" in t for t in copier), copier)

            # ---- 3, 4 et 5 : plusieurs personnes d'un coup, au GROUPE -------------------
            print("\nAu groupe — trois personnes cochées d'un coup :")
            page = ouvrir(f"{BASE}/#t={groupe['id']}")
            page.click("#btn-membres-theme")
            page.wait_for_timeout(600)
            cases = page.eval_on_selector_all("#membre-theme-comptes input", "n => n.length")
            verifie("les personnes du projet se proposent au groupe", cases >= 3, cases)
            verifie("le bouton n'ajoute rien tant que personne n'est coché",
                    page.eval_on_selector("#membre-theme-ajouter", "n => n.disabled") is True)
            page.click("#membre-theme-comptes button.discret")          # « Tout cocher »
            page.wait_for_timeout(300)
            libelle = page.eval_on_selector("#membre-theme-ajouter", "n => n.textContent.trim()")
            verifie(f"le bouton annonce les {cases} personnes cochées", f"({cases})" in libelle,
                    libelle)
            page.click("#membre-theme-ajouter")
            page.wait_for_timeout(2500)
            page.screenshot(path=os.path.join(CAPTURES, "synergie-membres-groupe.png"),
                            full_page=True)
            ajoutes = page.eval_on_selector_all("#liste-membres-theme .membre", "n => n.length")
            verifie("toutes les personnes cochées sont dans le groupe", ajoutes == cases, ajoutes)
            membres = appel(f"/api/themes/{groupe['id']}/membres", jeton=jeton)["membres"]
            verifie("l'application connaît bien tous les membres du groupe",
                    len(membres) == cases, [m["prenom"] for m in membres])
            verifie("aucune erreur JavaScript", not erreurs, erreurs[:2])
            nav.close()
    finally:
        if groupe:
            try:
                appel(f"/api/themes/{groupe['id']}", jeton=jeton, methode="DELETE")
            except Exception:                       # le ménage ne doit jamais tout casser
                pass
        if projet:
            try:
                appel(f"/api/projets/{projet['id']}", jeton=jeton, methode="DELETE")
            except Exception:
                pass
        menage(compte["compte"]["id"], crees)       # les comptes d'essai s'en vont aussi

    echecs = sum(1 for _, ok in RESULTATS if not ok)
    print(f"\n{len(RESULTATS) - echecs}/{len(RESULTATS)} contrôles réussis")
    return 1 if echecs else 0


if __name__ == "__main__":
    sys.exit(principal())
