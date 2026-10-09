#!/usr/bin/env python3
"""Membres : affichage moderne, identique pour le PROJET et les GROUPES (09/10/2026).

Demande de l'utilisateur : « adopte un affichage du plus moderne des membres du projet. La case
cochée ne sert à rien. Je veux plutôt un affichage comme les membres d'un groupe WhatsApp et la
possibilité de changer leur rôle ou de les supprimer. Affichage identique pour le projet et les
groupes. »

Ce contrôle crée un projet d'essai (puis l'efface) et vérifie dans un vrai navigateur :
  1. chaque personne a sa PASTILLE d'initiales, son nom, son adresse — et son rôle ;
  2. plus aucune case à cocher ;
  3. un appui sur la ligne ouvre le choix du rôle (Administrateur / Membre participant /
     Visiteur) et le retrait de la personne ;
  4. changer le rôle fonctionne vraiment (vérifié en base par l'API) ;
  5. le GROUPE présente exactement le même affichage ;
  6. un membre qui n'administre pas voit la liste, sans pouvoir la modifier.

    python3 tests/tester_membres_affichage.py
    SYNERGIE_SITE=https://synergie.alpinevibe.fr python3 tests/tester_membres_affichage.py
"""
import json
import os
import sys
import urllib.error
import urllib.request

from playwright.sync_api import sync_playwright

BASE = os.environ.get("SYNERGIE_SITE", "http://127.0.0.1:8077").rstrip("/")
CAPTURES = os.environ.get("CHECKUP_CAPTURES", "/home/ubuntu/captures")
PROJET = "Essai — affichage des membres"
GROUPE = "Groupe d'essai"
PERSONNES = ["Aline Martin", "Bruno Petit", "Chloé Grand"]

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


MESURE = """(selecteur) => {
  const zone = document.querySelector(selecteur);
  if (!zone) return null;
  const lignes = [...zone.querySelectorAll('.membre')];
  return {
    nombre: lignes.length,
    cases: zone.querySelectorAll('input[type=checkbox]').length,
    menus: zone.querySelectorAll('select').length,
    pastilles: zone.querySelectorAll('.pastille-membre').length,
    chevrons: zone.querySelectorAll('.membre-chevron').length,
    premiere: lignes.length ? {
      pastille: (lignes[0].querySelector('.pastille-membre') || {}).textContent || '',
      nom: (lignes[0].querySelector('strong') || {}).textContent || '',
      detail: (lignes[0].querySelector('.membre-detail') || {}).textContent || '',
      role: (lignes[0].querySelector('.etiquette-role') || {}).textContent || ''
    } : null
  };
}"""


def principal() -> int:
    try:
        admin = appel("/api/comptes", {"prenom": "Essai affichage"})
    except urllib.error.URLError as erreur:
        print(f"Synergie injoignable sur {BASE} : {erreur}", file=sys.stderr)
        return 2
    jeton = admin["jeton"]
    projet = groupe = None
    crees = []
    simple = None
    try:
        projet = appel("/api/projets", {"nom": PROJET}, jeton=jeton)
        for personne in PERSONNES:
            appel(f"/api/projets/{projet['id']}/membres", {"prenom": personne, "role": "membre"},
                  jeton=jeton)
        groupe = appel("/api/themes", {"titre": GROUPE, "projet": projet["id"]}, jeton=jeton)
        fiche = appel(f"/api/projets/{projet['id']}", jeton=jeton)
        crees = [m["compte"] for m in fiche["membres"] if m["prenom"] in PERSONNES]
        appel(f"/api/themes/{groupe['id']}/membres",
              {"compte": crees[0], "role": "membre"}, jeton=jeton)
        # Un membre SANS droit d'administration, pour voir ce qu'il voit (son propre jeton).
        simple = appel("/api/comptes", {"prenom": "Membre simple"})
        appel(f"/api/projets/{projet['id']}/membres",
              {"compte": simple["compte"]["id"], "role": "membre"}, jeton=jeton)

        with sync_playwright() as p:
            nav = p.chromium.launch()

            def ouvrir(jeton_connexion, nom, route=None):
                ctx = nav.new_context(viewport={"width": 1100, "height": 850},
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

            # ---- le PROJET -----------------------------------------------------------------
            print("\nFenêtre des membres du projet :")
            ctx, page, erreurs = ouvrir(jeton, "Essai affichage")
            page.click("#btn-membres")
            page.wait_for_timeout(1000)
            m = page.evaluate(MESURE, "#membres-liste")
            verifie("chaque personne a sa pastille",
                    m["nombre"] >= 4 and m["pastilles"] == m["nombre"]
                    and m["chevrons"] == m["nombre"], m)
            verifie("plus AUCUNE case à cocher", m["cases"] == 0, m["cases"])
            verifie("plus aucun menu déroulant dans la liste", m["menus"] == 0, m["menus"])
            verifie("la première ligne montre initiales, nom, adresse et rôle",
                    m["premiere"] and len(m["premiere"]["pastille"]) == 2
                    and m["premiere"]["nom"] and m["premiere"]["detail"]
                    and m["premiere"]["role"], m["premiere"])
            os.makedirs(CAPTURES, exist_ok=True)
            page.screenshot(path=os.path.join(CAPTURES, "synergie-membres-moderne.png"))

            # un appui ouvre les actions (sur la ligne d'Aline Martin)
            page.click(f"#membres-liste .membre:has-text('{PERSONNES[0]}') .membre-tete")
            page.wait_for_timeout(400)
            actions = page.evaluate("""() => {
              const bloc = [...document.querySelectorAll('#membres-liste .membre-actions')]
                .find((b) => !b.classList.contains('cache'));
              return {ouverte: bloc && !bloc.classList.contains('cache'),
                      roles: bloc ? [...bloc.querySelectorAll('.role-choix')].map(b => b.textContent.trim()) : [],
                      retirer: bloc ? (bloc.querySelector('button.danger') || {}).textContent : ''};
            }""")
            verifie("l'appui ouvre le choix du rôle et le retrait",
                    actions["ouverte"] and len(actions["roles"]) == 3
                    and "Retirer du projet" in (actions["retirer"] or ""), actions)
            page.screenshot(path=os.path.join(CAPTURES, "synergie-membres-actions.png"))

            # changer un rôle : « Visiteur »
            avant = next(x for x in appel(f"/api/projets/{projet['id']}", jeton=jeton)["membres"]
                         if x["prenom"] == PERSONNES[0])
            page.click(f"#membres-liste .membre:has-text('{PERSONNES[0]}')"
                       f" .role-choix:has-text('Visiteur')")
            page.wait_for_timeout(1500)
            apres = next(x for x in appel(f"/api/projets/{projet['id']}", jeton=jeton)["membres"]
                         if x["prenom"] == PERSONNES[0])
            verifie("le rôle se change vraiment", avant["role"] == "membre"
                    and apres["role"] == "visiteur", f"{avant['role']} → {apres['role']}")

            # ---- le GROUPE -----------------------------------------------------------------
            print("\nFenêtre des membres du groupe (même affichage) :")
            ctx2, page2, erreurs2 = ouvrir(jeton, "Essai affichage",
                                           route=f"#t={groupe['id']}")
            page2.click("#btn-membres-theme")
            page2.wait_for_timeout(1000)
            g = page2.evaluate(MESURE, "#liste-membres-theme")
            verifie("le groupe présente le même affichage",
                    g["nombre"] == 1 and g["pastilles"] == 1 and g["cases"] == 0, g)
            page2.click("#liste-membres-theme .membre-tete")
            page2.wait_for_timeout(400)
            actions2 = page2.evaluate("""() => {
              const bloc = [...document.querySelectorAll('#liste-membres-theme .membre-actions')]
                .find((b) => !b.classList.contains('cache'));
              return {ouverte: bloc && !bloc.classList.contains('cache'),
                      roles: bloc ? [...bloc.querySelectorAll('.role-choix')].map(b => b.textContent.trim()) : [],
                      retirer: bloc ? (bloc.querySelector('button.danger') || {}).textContent : ''};
            }""")
            verifie("le groupe propose les mêmes actions",
                    actions2["ouverte"] and len(actions2["roles"]) == 3
                    and "Retirer du groupe" in (actions2["retirer"] or ""), actions2)
            verifie("aucune erreur JavaScript",
                    not erreurs and not erreurs2, (erreurs + erreurs2)[:2])

            # ---- un membre simple : la liste, sans les actions ------------------------------
            print("\nUn membre qui n'administre pas :")
            ctx3, page3, _ = ouvrir(simple["jeton"], "Membre simple")
            page3.click("#btn-membres")
            page3.wait_for_timeout(1000)
            s = page3.evaluate(MESURE, "#membres-liste")
            verifie("le membre voit la liste, sans pouvoir la modifier",
                    s and s["nombre"] >= 3 and s["chevrons"] == 0 and s["cases"] == 0, s)
            ctx.close(); ctx2.close(); ctx3.close()
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
