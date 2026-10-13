#!/usr/bin/env python3
"""Corriger le PRÉNOM d'un participant (13/10/2026).

Demande de l'utilisateur : « je veux avoir la possibilité de modifier le Prénom des
participants dans Synergie en tant qu'administrateur ».

Le prénom est le nom affiché partout dans Synergie (messages, présence, listes de membres,
alertes) : il devait donc pouvoir être corrigé — faute de frappe à l'inscription, changement
de nom — sans recréer le compte.

Ce contrôle vérifie :

  1. qu'un ADMINISTRATEUR du projet renomme un participant, et que le nouveau nom apparaît
     partout (liste des membres, compte de la personne) ;
  2. que la personne renommée **garde son accès** (même jeton, même identifiant personnel) ;
  3. qu'un simple membre ne peut PAS renommer quelqu'un d'autre ;
  4. que dans un GROUPE le renommage reste réservé à l'administrateur du projet ;
  5. qu'un prénom vide — ou trop long — est refusé avec un message clair ;
  6. qu'à l'écran, l'administrateur a bien le champ « Prénom affiché » et le bouton
     « Renommer » dans la fiche du membre.

    python3 tests/tester_renommer_membre.py
    SYNERGIE_SITE=https://synergie.alpinevibe.fr python3 tests/tester_renommer_membre.py
"""
import json
import os
import sys
import tempfile
import urllib.error
import urllib.request

from playwright.sync_api import sync_playwright

RACINE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, RACINE)

BASE = os.environ.get("SYNERGIE_SITE", "http://127.0.0.1:8077").rstrip("/")
CAPTURES = os.environ.get("CHECKUP_CAPTURES", "/home/ubuntu/captures")
PROJET = "Essai — prénom des participants"
GROUPE = "Groupe essai prénom"

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


def essai_appel(chemin, corps=None, jeton=None, methode=None):
    try:
        appel(chemin, corps, jeton, methode)
        return 200, ""
    except urllib.error.HTTPError as erreur:
        return erreur.code, erreur.read().decode("utf-8", "replace")[:200]


# =====================================================================================
# 1. LE MOTEUR (base d'essai isolée)
# =====================================================================================
def controler_le_moteur():
    fichier = tempfile.NamedTemporaryFile(suffix="-prenom.db", delete=False)
    fichier.close()
    ancienne = os.environ.get("SYNERGIE_BASE")
    os.environ["SYNERGIE_BASE"] = fichier.name
    for module in [m for m in list(sys.modules) if m.startswith("moteur")]:
        del sys.modules[module]
    from moteur import atelier, equipe

    atelier.initialiser()          # la table du journal (tracé du renommage)
    equipe.initialiser()
    compte = equipe.creer_compte("Faute de Frape", "faute@exemple.invalid")["compte"]
    avant = equipe.lire_compte(identifiant=compte["id"])
    from moteur import base as m_base
    with m_base.connexion() as b:
        jeton_avant = b.execute("select jeton from comptes where id = ?",
                                (compte["id"],)).fetchone()["jeton"]

    change = equipe.renommer_compte(compte["id"], "Prénom Corrigé", par="Patron")
    verifie("le prénom se corrige", change["prenom"] == "Prénom Corrigé", change["prenom"])
    with m_base.connexion() as b:
        jeton_apres = b.execute("select jeton from comptes where id = ?",
                                (compte["id"],)).fetchone()["jeton"]
    verifie("le jeton et l'identifiant personnel ne changent PAS (la personne garde son accès)",
            jeton_apres == jeton_avant and change["identifiant"] == avant["identifiant"])
    with m_base.connexion() as b:
        trace = b.execute("select action, details from journal where action = 'compte_renomme'"
                          " order by id desc limit 1").fetchone()
    verifie("l'ancien nom reste au journal (traçabilité)",
            bool(trace) and "Faute de Frape" in (trace["details"] or ""),
            dict(trace) if trace else "aucune trace")

    for mauvais, quoi in (("", "vide"), ("x" * 200, "trop long")):
        try:
            equipe.renommer_compte(compte["id"], mauvais)
            verifie(f"un prénom {quoi} est refusé", False, "accepté !")
        except ValueError as erreur:
            verifie(f"un prénom {quoi} est refusé, avec un message clair",
                    "prénom" in str(erreur).lower(), str(erreur))
    try:
        equipe.renommer_compte("cp-inexistant", "Personne")
        verifie("un compte inconnu est refusé", False, "accepté !")
    except KeyError:
        verifie("un compte inconnu est refusé", True)

    os.unlink(fichier.name)
    if ancienne is None:
        os.environ.pop("SYNERGIE_BASE", None)
    else:
        os.environ["SYNERGIE_BASE"] = ancienne


# =====================================================================================
# 2. L'API ET L'ÉCRAN
# =====================================================================================
def controler_l_api() -> int:
    try:
        patron = appel("/api/comptes", {"prenom": "Essai prénom patron"})
        membre = appel("/api/comptes", {"prenom": "Essai prénom fautif"})
        tiers = appel("/api/comptes", {"prenom": "Essai prénom tiers"})
    except urllib.error.URLError as erreur:
        print(f"Synergie injoignable sur {BASE} : {erreur}", file=sys.stderr)
        return 2
    projet = groupe = None
    try:
        projet = appel("/api/projets", {"nom": PROJET}, jeton=patron["jeton"])
        groupe = appel("/api/themes", {"titre": GROUPE, "projet": projet["id"]},
                       jeton=patron["jeton"])
        for compte, role in ((membre, "membre"), (tiers, "membre")):
            appel(f"/api/projets/{projet['id']}/membres",
                  {"compte": compte["compte"]["id"], "role": role}, jeton=patron["jeton"])
            appel(f"/api/themes/{groupe['id']}/membres",
                  {"compte": compte["compte"]["id"], "role": "membre"}, jeton=patron["jeton"])

        membre_id = membre["compte"]["id"]
        chemin_projet = f"/api/projets/{projet['id']}/membres/{membre_id}"
        chemin_groupe = f"/api/themes/{groupe['id']}/membres/{membre_id}"

        # 3) un simple membre ne renomme personne
        code, detail = essai_appel(chemin_projet, {"prenom": "Nom Pirate"},
                                   jeton=membre["jeton"], methode="PUT")
        verifie("un simple membre ne peut pas renommer un participant", code == 403,
                f"{code} {detail[:60]}")

        # 5) un prénom vide ne renomme personne (l'interface le refuse avant l'envoi)
        essai_appel(chemin_projet, {"prenom": "   "}, jeton=patron["jeton"], methode="PUT")
        avant_vide = {m["compte"]: m["prenom"]
                      for m in appel(f"/api/projets/{projet['id']}",
                                     jeton=patron["jeton"])["membres"]}
        verifie("un prénom vide ne renomme personne (et ne casse rien)",
                avant_vide.get(membre_id) != "", avant_vide.get(membre_id))

        # 1) l'administrateur du projet renomme
        code, detail = essai_appel(chemin_projet, {"prenom": "Camille Martin"},
                                   jeton=patron["jeton"], methode="PUT")
        verifie("l'administrateur du projet renomme un participant", code == 200,
                f"{code} {detail[:60]}")
        membres = appel(f"/api/projets/{projet['id']}", jeton=patron["jeton"])["membres"]
        noms = {m["compte"]: m["prenom"] for m in membres}
        verifie("le nouveau prénom apparaît dans la liste des membres",
                noms.get(membre_id) == "Camille Martin", noms.get(membre_id))

        # 2) la personne renommée garde son accès
        moi = appel("/api/comptes/moi", jeton=membre["jeton"])
        verifie("la personne renommée garde son accès, avec son nouveau nom",
                (moi.get("compte") or {}).get("prenom") == "Camille Martin",
                (moi.get("compte") or {}).get("prenom"))

        # 4) dans un groupe, seul l'administrateur du projet renomme
        appel(f"/api/themes/{groupe['id']}/membres/{tiers['compte']['id']}",
              {"role": "admin"}, jeton=patron["jeton"], methode="PUT")
        code, detail = essai_appel(chemin_groupe, {"prenom": "Nom du Groupe"},
                                   jeton=tiers["jeton"], methode="PUT")
        verifie("dans un groupe, l'administrateur du groupe ne renomme pas", code == 403,
                f"{code} {detail[:70]}")
        code, detail = essai_appel(chemin_groupe, {"prenom": "Camille Martin-Groupe"},
                                   jeton=patron["jeton"], methode="PUT")
        verifie("… l'administrateur du projet, lui, renomme depuis un groupe", code == 200,
                f"{code} {detail[:70]}")

        # 6) l'écran : le champ de renommage n'apparaît que pour l'administrateur
        with sync_playwright() as p:
            nav = p.chromium.launch(args=["--no-sandbox"])
            for etiquette, compte, attendu in (("administrateur", patron, True),
                                               ("simple membre", membre, False)):
                ctx = nav.new_context(viewport={"width": 1280, "height": 900})
                ctx.add_init_script(
                    "localStorage.setItem('synergie.jeton', %s);"
                    "localStorage.setItem('synergie.projet', %s);"
                    % (json.dumps(compte["jeton"]), json.dumps(projet["id"])))
                ctx.add_cookies([{"name": "synergie", "value": compte["jeton"], "url": BASE,
                                  "httpOnly": True, "sameSite": "Lax"}])
                page = ctx.new_page()
                erreurs = []
                page.on("pageerror", lambda e: erreurs.append(str(e)[:120]))
                page.goto(f"{BASE}/#p={projet['id']}", wait_until="load", timeout=45000)
                page.wait_for_timeout(3000)
                page.click("#btn-membres")
                page.wait_for_timeout(1200)
                if attendu:
                    # La fiche ne s'ouvre que pour qui peut agir : un simple membre voit la
                    # liste en lecture, sans champ de renommage.
                    page.click("#membres-liste .membre:has-text('Camille Martin') .membre-tete")
                    page.wait_for_timeout(700)
                vu = page.evaluate("""() => {
                  const bloc = [...document.querySelectorAll('#membres-liste .membre')]
                    .find((m) => (m.textContent || '').includes('Camille Martin'));
                  if (!bloc) return {trouve: false};
                  const champ = bloc.querySelector('.renommer-membre input');
                  const bouton = bloc.querySelector('.renommer-membre button');
                  return {trouve: true, champ: !!champ, bouton: !!bouton,
                          valeur: champ ? champ.value : null};
                }""")
                verifie(f"écran {etiquette} : le champ « Prénom affiché » est "
                        + ("proposé" if attendu else "absent"),
                        vu.get("champ") is attendu, vu)
                if attendu:
                    page.fill("#membres-liste .membre:has-text('Camille Martin') "
                              ".renommer-membre input", "Camille Martin-Dupont")
                    page.click("#membres-liste .membre:has-text('Camille Martin') "
                               ".renommer-membre button")
                    page.wait_for_timeout(2500)
                    apres = appel(f"/api/projets/{projet['id']}",
                                  jeton=patron["jeton"])["membres"]
                    noms = {m["compte"]: m["prenom"] for m in apres}
                    verifie("écran administrateur : renommer depuis la fiche change le nom",
                            noms.get(membre_id) == "Camille Martin-Dupont", noms.get(membre_id))
                    page.screenshot(path=f"{CAPTURES}/synergie-renommer-membre.png",
                                    full_page=False)
                verifie(f"écran {etiquette} : aucune erreur JavaScript", not erreurs, erreurs[:2])
                ctx.close()
            nav.close()
    finally:
        if groupe:
            try:
                appel(f"/api/themes/{groupe['id']}", jeton=patron["jeton"], methode="DELETE")
            except Exception:
                pass
        if projet:
            try:
                appel(f"/api/projets/{projet['id']}", jeton=patron["jeton"], methode="DELETE")
            except Exception:
                pass
        menage([patron["compte"]["id"], membre["compte"]["id"], tiers["compte"]["id"]])
    return 0


def principal() -> int:
    print("1. Le moteur (base d'essai isolée)")
    controler_le_moteur()
    print("\n2. L'API et l'écran, contre le service")
    code = controler_l_api()
    if code:
        return code
    echecs = sum(1 for _, ok in RESULTATS if not ok)
    print(f"\n{len(RESULTATS) - echecs}/{len(RESULTATS)} contrôles réussis")
    return 1 if echecs else 0


if __name__ == "__main__":
    sys.exit(principal())
