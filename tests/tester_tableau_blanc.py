#!/usr/bin/env python3
"""Le tableau blanc reste un TABLEAU BLANC (12/10/2026).

Demande de l'utilisateur : « je veux que tu gardes le concept de tableau blanc pour les
post-it … tu avais modifié la disposition pour mettre les post-it les uns en dessous des
autres et ça n'a pas de sens de fonctionner comme ça : faut que ça reste un tableau blanc. »

En « vue téléphone », l'application affichait en effet une LISTE de notes (post-it empilés)
à la place du tableau. Ce contrôle vérifie, sur téléphone comme sur ordinateur, que :

  1. le tableau s'affiche d'emblée (et non la liste) ;
  2. les notes restent POSÉES LIBREMENT : deux notes côte à côte le restent (elles ne sont
     pas empilées l'une sous l'autre) ;
  3. le bouton offert bascule vers la liste, puis revient au tableau, et son libellé dit
     ce qu'il fait ;
  4. le choix de la liste est gardé au rechargement — mais le tableau reste le défaut.

    python3 tests/tester_tableau_blanc.py
    SYNERGIE_SITE=http://127.0.0.1:8096 python3 tests/tester_tableau_blanc.py
"""
import json
import os
import sys
import urllib.error
import urllib.request

from playwright.sync_api import sync_playwright

BASE = os.environ.get("SYNERGIE_SITE", "http://127.0.0.1:8077").rstrip("/")
CAPTURES = os.environ.get("CHECKUP_CAPTURES", "/home/ubuntu/captures")
PROJET = "Essai — tableau blanc"
GROUPE = "Groupe essai tableau"
# Trois notes posées librement : deux côte à côte, une plus bas et à gauche.
NOTES = [("Post-it de gauche", 60, 60), ("Post-it de droite", 460, 60), ("Post-it du bas", 60, 360)]

RESULTATS = []


def verifie(titre, condition, detail=""):
    RESULTATS.append((titre, bool(condition)))
    print(("  ✅ " if condition else "  ❌ ") + titre + ((" — " + str(detail)) if detail else ""))


def menage(identifiants):
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    from menage_essai import effacer_comptes
    effacer_comptes(identifiants)


def rouvrir(page, url, attente=3000):
    """Rouvre l'application sur l'adresse donnée, comme on rouvrirait l'application installée.

    Un simple changement d'ancre ne recharge pas la page (et l'application réécrit l'ancre
    sur le projet) : on force donc un vrai rechargement de l'adresse voulue.
    """
    page.goto(url)
    page.reload(wait_until="load")
    page.wait_for_timeout(attente)


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


MESURE = """() => {
  const plateau = document.querySelector('#plateau');
  const liste = document.querySelector('#notes-liste');
  const bouton = document.querySelector('#btn-voir-tableau');
  const visible = (n) => !!n && n.getBoundingClientRect().height > 0
    && getComputedStyle(n).display !== 'none';
  const boites = [...document.querySelectorAll('#monde .note')].map((n) => {
    const b = n.getBoundingClientRect();
    return { gauche: Math.round(b.left), haut: Math.round(b.top) };
  });
  // Deux notes « côte à côte » : même hauteur, à plus de 100 px l'une de l'autre.
  let coteACote = 0;
  for (let i = 0; i < boites.length; i += 1) {
    for (let j = i + 1; j < boites.length; j += 1) {
      if (Math.abs(boites[i].haut - boites[j].haut) < 40
          && Math.abs(boites[i].gauche - boites[j].gauche) > 100) coteACote += 1;
    }
  }
  return {
    tableau: visible(plateau), liste: visible(liste),
    bouton: bouton ? bouton.textContent.trim() : '',
    bouton_visible: visible(bouton),
    notes: boites.length, cote_a_cote: coteACote,
    meme_colonne: boites.length > 1
      && new Set(boites.map((b) => b.gauche)).size === 1
  };
}"""


def principal() -> int:
    try:
        compte = appel("/api/comptes", {"prenom": "Essai tableau"})
    except urllib.error.URLError as erreur:
        print(f"Synergie injoignable sur {BASE} : {erreur}", file=sys.stderr)
        return 2
    jeton = compte["jeton"]
    projet, groupe = None, None
    try:
        projet = appel("/api/projets", {"nom": PROJET}, jeton=jeton)
        groupe = appel("/api/themes", {"titre": GROUPE, "projet": projet["id"]}, jeton=jeton)
        for texte, x, y in NOTES:
            appel(f"/api/themes/{groupe['id']}/notes",
                  {"texte": texte, "x": x, "y": y, "couleur_fond": "#fff3bf"}, jeton=jeton)

        with sync_playwright() as p:
            nav = p.chromium.launch(args=["--no-sandbox"])
            for etiquette, largeur in (("téléphone", 430), ("ordinateur", 1280)):
                ctx = nav.new_context(viewport={"width": largeur, "height": 900})
                ctx.add_init_script(
                    "localStorage.setItem('synergie.jeton', %s);"
                    "localStorage.setItem('synergie.projet', %s);"
                    % (json.dumps(jeton), json.dumps(projet["id"])))
                ctx.add_cookies([{"name": "synergie", "value": jeton, "url": BASE,
                                  "httpOnly": True, "sameSite": "Lax"}])
                page = ctx.new_page()
                erreurs = []
                page.on("pageerror", lambda e: erreurs.append(str(e)[:120]))
                page.goto(f"{BASE}/#t={groupe['id']}", wait_until="load", timeout=45000)
                page.wait_for_timeout(3000)
                vue = page.evaluate(MESURE)
                print(f"\n{etiquette} ({largeur} px) : {vue}")
                verifie(f"{etiquette} : le tableau blanc s'affiche d'emblée", vue["tableau"], vue)
                verifie(f"{etiquette} : les post-it ne sont PAS empilés en liste",
                        not vue["liste"], vue)
                verifie(f"{etiquette} : les notes restent posées librement (côte à côte)",
                        vue["cote_a_cote"] >= 1 and not vue["meme_colonne"], vue)
                if largeur == 430:
                    verifie("téléphone : le bouton propose de revenir à la liste",
                            "liste" in vue["bouton"].lower(), vue["bouton"])
                    page.screenshot(path=f"{CAPTURES}/synergie-tableau-telephone.png")
                    page.click("#btn-voir-tableau")
                    page.wait_for_timeout(1200)
                    apres = page.evaluate(MESURE)
                    verifie("le bouton bascule bien vers la liste, et le dit",
                            apres["liste"] and not apres["tableau"]
                            and "tableau" in apres["bouton"].lower(), apres)
                    page.click("#btn-voir-tableau")
                    page.wait_for_timeout(1200)
                    retour = page.evaluate(MESURE)
                    verifie("… et le retour au tableau fonctionne",
                            retour["tableau"] and not retour["liste"], retour)
                    # On choisit la liste, on ROUVRE l'application sur le même groupe :
                    # le choix est gardé.
                    page.click("#btn-voir-tableau")
                    page.wait_for_timeout(800)
                    rouvrir(page, f"{BASE}/#t={groupe['id']}")
                    garde = page.evaluate(MESURE)
                    verifie("le choix de la liste est gardé à la réouverture",
                            garde["liste"] and not garde["tableau"], garde)
                    # … puis on revient au tableau, comme le veut le cadre.
                    page.click("#btn-voir-tableau")
                    page.wait_for_timeout(800)
                    rouvrir(page, f"{BASE}/#t={groupe['id']}")
                    final = page.evaluate(MESURE)
                    verifie("de retour au tableau, il reste le tableau",
                            final["tableau"] and not final["liste"], final)
                verifie(f"{etiquette} : aucune erreur JavaScript", not erreurs, erreurs[:2])
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
        menage([compte["compte"]["id"]])
    echecs = sum(1 for _, ok in RESULTATS if not ok)
    print(f"\n{len(RESULTATS) - echecs}/{len(RESULTATS)} contrôles réussis")
    return 1 if echecs else 0


if __name__ == "__main__":
    sys.exit(principal())
