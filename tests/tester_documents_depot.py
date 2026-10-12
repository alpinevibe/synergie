#!/usr/bin/env python3
"""Dépôt de plusieurs documents, et par GLISSER-DÉPOSER (12/10/2026).

Demande de l'utilisateur : « permettre l'ajout de plusieurs documents en même temps et
permettre le drag and drop ».

Ce contrôle, fait dans un vrai navigateur contre le service, vérifie que :

  1. plusieurs fichiers choisis d'un coup partent bien tous (documents du groupe) ;
  2. si l'un d'eux est REFUSÉ, les autres partent quand même et le refus est annoncé ;
  3. des fichiers LÂCHÉS sur la zone sont déposés — et la zone s'allume au survol ;
  4. la même chose marche sur « Comptes rendus et documents » du PROJET ;
  5. une personne qui n'a pas le droit d'écrire (visiteur) ne peut PAS déposer :
     le dépôt est refusé et rien n'est enregistré.

    python3 tests/tester_documents_depot.py
    SYNERGIE_SITE=https://synergie.alpinevibe.fr python3 tests/tester_documents_depot.py
"""
import json
import os
import sys
import tempfile
import urllib.error
import urllib.request

from playwright.sync_api import sync_playwright

BASE = os.environ.get("SYNERGIE_SITE", "http://127.0.0.1:8077").rstrip("/")
CAPTURES = os.environ.get("CHECKUP_CAPTURES", "/home/ubuntu/captures")
PROJET = "Essai — dépôt de documents"
GROUPE = "Groupe essai dépôt"

RESULTATS = []


def verifie(titre, condition, detail=""):
    RESULTATS.append((titre, bool(condition)))
    print(("  ✅ " if condition else "  ❌ ") + titre + ((" — " + str(detail)) if detail else ""))


def menage(identifiants):
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    from menage_essai import effacer_comptes
    effacer_comptes(identifiants)


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


def fichiers(nombre, prefixe, dossier):
    """Fabrique de vrais fichiers d'essai, et rend leurs chemins."""
    chemins = []
    for rang in range(nombre):
        chemin = os.path.join(dossier, f"{prefixe}-{rang + 1}.txt")
        with open(chemin, "w", encoding="utf-8") as fichier:
            fichier.write(f"Document d'essai {rang + 1}\n" + "ligne\n" * 20)
        chemins.append(chemin)
    return chemins


def documents_du_groupe(groupe, jeton):
    return appel(f"/api/themes/{groupe['id']}", jeton=jeton).get("documents") or []


def documents_du_projet(projet, jeton):
    return appel(f"/api/projets/{projet['id']}/documents", jeton=jeton).get("documents") or []


LACHER = """([selecteur, noms]) => {
  const zone = document.querySelector(selecteur);
  if (!zone) return 'zone introuvable';
  const dt = new DataTransfer();
  noms.forEach((nom) => dt.items.add(new File(['contenu déposé à la souris'], nom,
    { type: 'text/plain' })));
  zone.dispatchEvent(new DragEvent('dragenter', { dataTransfer: dt, bubbles: true,
    cancelable: true }));
  zone.dispatchEvent(new DragEvent('dragover', { dataTransfer: dt, bubbles: true,
    cancelable: true }));
  const allumee = zone.classList.contains('depot-actif');
  zone.dispatchEvent(new DragEvent('drop', { dataTransfer: dt, bubbles: true,
    cancelable: true }));
  return allumee ? 'allumée' : 'éteinte';
}"""


def principal() -> int:
    try:
        patron = appel("/api/comptes", {"prenom": "Essai dépôt"})
        curieux = appel("/api/comptes", {"prenom": "Essai dépôt visiteur"})
    except urllib.error.URLError as erreur:
        print(f"Synergie injoignable sur {BASE} : {erreur}", file=sys.stderr)
        return 2
    jeton = patron["jeton"]
    projet = groupe = None
    dossier = tempfile.mkdtemp()
    try:
        projet = appel("/api/projets", {"nom": PROJET}, jeton=jeton)
        groupe = appel("/api/themes", {"titre": GROUPE, "projet": projet["id"]}, jeton=jeton)
        appel(f"/api/projets/{projet['id']}/membres",
              {"compte": curieux["compte"]["id"], "role": "visiteur"}, jeton=jeton)

        with sync_playwright() as p:
            nav = p.chromium.launch(args=["--no-sandbox"])
            ctx = nav.new_context(viewport={"width": 1280, "height": 900})
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
            page.click("#onglets-theme button[data-onglet=documents]")
            page.wait_for_timeout(1200)

            # 1. plusieurs fichiers choisis d'un coup
            page.set_input_files("#fichier-document", fichiers(3, "choisi", dossier))
            page.click("#btn-deposer")
            page.wait_for_timeout(4000)
            etat = page.text_content("#etat-depot") or ""
            n = len(documents_du_groupe(groupe, jeton))
            verifie("trois fichiers choisis d'un coup sont tous déposés",
                    n == 3 and "3 documents déposés" in etat, f"{n} · « {etat.strip()} »")

            # 2. un refus n'arrête pas les autres
            compteur = {"n": 0}

            def router(route):
                compteur["n"] += 1
                if compteur["n"] == 2:
                    route.fulfill(status=500, content_type="application/json",
                                  body=json.dumps({"erreur": "refus simulé"}))
                else:
                    route.continue_()

            page.route("**/api/themes/*/documents", router)
            page.set_input_files("#fichier-document", fichiers(3, "melange", dossier))
            page.click("#btn-deposer")
            page.wait_for_timeout(4000)
            page.unroute("**/api/themes/*/documents")
            etat = page.text_content("#etat-depot") or ""
            total = len(documents_du_groupe(groupe, jeton))
            verifie("un fichier refusé n'empêche pas les autres de partir",
                    total == 5 and "2 documents déposés" in etat and "efusé" in etat,
                    f"{total} · « {etat.strip()} »")

            # 3. le glisser-déposer, sur la zone des documents du groupe
            allumee = page.evaluate(LACHER, ["#onglet-documents", ["glisse-1.txt", "glisse-2.txt"]])
            verifie("la zone s'allume quand un fichier la survole", allumee == "allumée", allumee)
            page.wait_for_timeout(4000)
            noms = [d["nom"] for d in documents_du_groupe(groupe, jeton)]
            verifie("les fichiers lâchés sur la zone sont déposés",
                    "glisse-1.txt" in noms and "glisse-2.txt" in noms, noms)
            page.screenshot(path=f"{CAPTURES}/synergie-depot-documents.png", full_page=False)

            # 4. le glisser-déposer sur les documents du PROJET
            page.goto(f"{BASE}/#p={projet['id']}", wait_until="load")
            page.wait_for_timeout(2500)
            page.evaluate("""() => { const d = document.querySelector('#cadre-documents')
                && document.querySelector('#cadre-documents').closest('details');
                if (d) d.open = true; }""")
            page.wait_for_timeout(500)
            page.evaluate(LACHER, ["#cadre-documents", ["projet-glisse.txt"]])
            page.wait_for_timeout(4000)
            noms_projet = [d["nom"] for d in documents_du_projet(projet, jeton)]
            verifie("les fichiers lâchés sur le projet y sont déposés",
                    "projet-glisse.txt" in noms_projet, noms_projet)

            verifie("aucune erreur JavaScript dans ces écrans", not erreurs, erreurs[:2])
            ctx.close()

            # 5. un visiteur ne peut pas déposer
            ctx2 = nav.new_context(viewport={"width": 1280, "height": 900})
            ctx2.add_init_script(
                "localStorage.setItem('synergie.jeton', %s);"
                "localStorage.setItem('synergie.projet', %s);"
                % (json.dumps(curieux["jeton"]), json.dumps(projet["id"])))
            ctx2.add_cookies([{"name": "synergie", "value": curieux["jeton"], "url": BASE,
                               "httpOnly": True, "sameSite": "Lax"}])
            page2 = ctx2.new_page()
            page2.goto(f"{BASE}/#t={groupe['id']}", wait_until="load", timeout=45000)
            page2.wait_for_timeout(3000)
            page2.click("#onglets-theme button[data-onglet=documents]")
            page2.wait_for_timeout(1200)
            avant = len(documents_du_groupe(groupe, jeton))
            page2.evaluate(LACHER, ["#onglet-documents", ["interdit.txt"]])
            page2.wait_for_timeout(2500)
            apres = len(documents_du_groupe(groupe, jeton))
            verifie("un visiteur ne peut pas déposer (rien n'est enregistré)", apres == avant,
                    f"{avant} → {apres}")
            verifie("… et l'application le lui dit",
                    "ne permet pas" in (page2.text_content("#etat-depot") or "")
                    or page2.evaluate("() => !!document.querySelector('.toast')"),
                    (page2.text_content("#etat-depot") or "")[:80])
            ctx2.close()
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
        menage([patron["compte"]["id"], curieux["compte"]["id"]])
    echecs = sum(1 for _, ok in RESULTATS if not ok)
    print(f"\n{len(RESULTATS) - echecs}/{len(RESULTATS)} contrôles réussis")
    return 1 if echecs else 0


if __name__ == "__main__":
    sys.exit(principal())
