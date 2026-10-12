#!/usr/bin/env python3
"""Les rôles dans les groupes (12/10/2026).

Deux règles demandées par l'utilisateur :

  1. « les membres d'un projet en qualité de membre sont d'emblée visiteurs » : appartenir au
     projet ne donne pas le droit d'écrire dans ses groupes — il faut y être NOMMÉ ;
  2. « seul l'administrateur d'un projet peut nommer un administrateur de groupe ».

Ce contrôle les éprouve à trois niveaux :

  • le MOTEUR, sur une base d'essai isolée (règle de rôle effectif et droit de nomination) ;
  • l'API, sur le service : un membre du projet ne peut pas écrire dans un groupe (403), puis
    peut quand on lui y donne un rôle ; un administrateur de groupe ne peut pas nommer
    d'administrateur (403) ; l'administrateur du projet le peut ;
  • l'ÉCRAN : la pastille de statut annonce bien « Visiteur » pour un membre du projet qui n'a
    pas de rôle dans le groupe.

    python3 tests/tester_roles_groupes.py
    SYNERGIE_SITE=http://127.0.0.1:8096 SYNERGIE_BASE=donnees/essai.db python3 tests/tester_roles_groupes.py
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
PROJET = "Essai — rôles des groupes"
GROUPE = "Groupe essai rôles"

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
    """Comme `appel`, mais rend (code, message d'erreur) au lieu de lever."""
    try:
        appel(chemin, corps, jeton, methode)
        return 200, ""
    except urllib.error.HTTPError as erreur:
        return erreur.code, erreur.read().decode("utf-8", "replace")[:200]


# =====================================================================================
# 1. LE MOTEUR (base d'essai isolée : aucune donnée réelle touchée)
# =====================================================================================
def controler_le_moteur():
    fichier = tempfile.NamedTemporaryFile(suffix="-roles.db", delete=False)
    fichier.close()
    ancienne = os.environ.get("SYNERGIE_BASE")
    os.environ["SYNERGIE_BASE"] = fichier.name
    for module in [m for m in list(sys.modules) if m.startswith("moteur")]:
        del sys.modules[module]
    from moteur import atelier, equipe, projets

    atelier.initialiser()
    equipe.initialiser()
    projets.initialiser()

    patron = equipe.creer_compte("Patron", "patron@exemple.invalid")["compte"]
    collegue = equipe.creer_compte("Collegue", "collegue@exemple.invalid")["compte"]
    lecteur = equipe.creer_compte("Lecteur", "lecteur@exemple.invalid")["compte"]
    projet = projets.creer_projet("Essai rôles", "", "Essai", admin=patron["id"], qui="Essai")
    groupe = atelier.creer_theme("Groupe essai", "", "", projet["id"], "Essai")
    projets.definir_membre_projet(projet["id"], collegue["id"], "membre", True, "Essai")
    projets.definir_membre_projet(projet["id"], lecteur["id"], "visiteur", False, "Essai")

    def role(compte):
        return projets.role_effectif(projet["id"], groupe["id"], compte["id"])

    verifie("l'administrateur du projet est administrateur de ses groupes",
            role(patron) == "admin", role(patron))
    verifie("un simple MEMBRE du projet est VISITEUR dans le groupe",
            role(collegue) == "visiteur", role(collegue))
    verifie("un visiteur du projet reste visiteur dans le groupe",
            role(lecteur) == "visiteur", role(lecteur))
    verifie("… et n'a donc pas le droit d'écrire dans le groupe",
            not projets.peut_ecrire(role(collegue)))

    projets.definir_membre_theme(groupe["id"], collegue["id"], "membre", None, "Essai")
    verifie("nommé dans le groupe, il peut y écrire",
            role(collegue) == "membre" and projets.peut_ecrire(role(collegue)), role(collegue))

    verifie("seul l'administrateur du projet peut nommer un administrateur de groupe",
            projets.peut_nommer_admin_de_groupe("admin")
            and not projets.peut_nommer_admin_de_groupe("membre")
            and not projets.peut_nommer_admin_de_groupe("visiteur")
            and not projets.peut_nommer_admin_de_groupe(None))

    os.unlink(fichier.name)
    if ancienne is None:
        os.environ.pop("SYNERGIE_BASE", None)
    else:
        os.environ["SYNERGIE_BASE"] = ancienne


# =====================================================================================
# 2. L'API ET L'ÉCRAN (contre le service)
# =====================================================================================
def controler_l_api() -> int:
    try:
        patron = appel("/api/comptes", {"prenom": "Essai rôles patron"})
        collegue = appel("/api/comptes", {"prenom": "Essai rôles collègue"})
        tiers = appel("/api/comptes", {"prenom": "Essai rôles tiers"})
        temoin = appel("/api/comptes", {"prenom": "Essai rôles témoin"})
    except urllib.error.URLError as erreur:
        print(f"Synergie injoignable sur {BASE} : {erreur}", file=sys.stderr)
        return 2
    projet = groupe = None
    try:
        projet = appel("/api/projets", {"nom": PROJET}, jeton=patron["jeton"])
        groupe = appel("/api/themes", {"titre": GROUPE, "projet": projet["id"]},
                       jeton=patron["jeton"])
        appel(f"/api/projets/{projet['id']}/membres",
              {"compte": collegue["compte"]["id"], "role": "membre"}, jeton=patron["jeton"])
        appel(f"/api/projets/{projet['id']}/membres",
              {"compte": tiers["compte"]["id"], "role": "membre"}, jeton=patron["jeton"])
        # Ce témoin reste membre du projet SANS rôle dans le groupe : sa pastille doit dire
        # « Visiteur » (aucun rôle ne lui a été donné ici).
        appel(f"/api/projets/{projet['id']}/membres",
              {"compte": temoin["compte"]["id"], "role": "membre"}, jeton=patron["jeton"])

        # 1) un membre du projet ne peut pas écrire dans un groupe où il n'a pas de rôle
        code, detail = essai_appel(f"/api/themes/{groupe['id']}/notes",
                                   {"texte": "essai", "x": 40, "y": 40},
                                   jeton=collegue["jeton"])
        verifie("un membre du projet ne peut PAS écrire dans un groupe sans y avoir de rôle",
                code == 403, f"{code} {detail[:80]}")

        lecture = appel(f"/api/themes/{groupe['id']}", jeton=collegue["jeton"])
        verifie("… mais il y voit tout (rôle annoncé : visiteur)",
                lecture.get("role") == "visiteur", lecture.get("role"))

        # 2) il écrit dès qu'on lui donne un rôle dans le groupe
        appel(f"/api/themes/{groupe['id']}/membres",
              {"compte": collegue["compte"]["id"], "role": "membre"}, jeton=patron["jeton"])
        code, detail = essai_appel(f"/api/themes/{groupe['id']}/notes",
                                   {"texte": "essai", "x": 40, "y": 40},
                                   jeton=collegue["jeton"])
        verifie("nommé MEMBRE dans le groupe, il peut y écrire", code in (200, 201),
                f"{code} {detail[:80]}")

        # 3) seul l'administrateur du projet nomme un administrateur de groupe
        code, detail = essai_appel(
            f"/api/themes/{groupe['id']}/membres",
            {"compte": tiers["compte"]["id"], "role": "admin"}, jeton=collegue["jeton"])
        verifie("un simple membre ne peut pas nommer d'administrateur", code == 403,
                f"{code} {detail[:90]}")

        code, detail = essai_appel(
            f"/api/themes/{groupe['id']}/membres/{tiers['compte']['id']}",
            {"role": "admin"}, jeton=collegue["jeton"], methode="PUT")
        verifie("… pas davantage en modifiant un rôle existant", code == 403,
                f"{code} {detail[:90]}")

        # L'administrateur du projet, lui, nomme : on le donne à « collegue ».
        code, detail = essai_appel(
            f"/api/themes/{groupe['id']}/membres/{collegue['compte']['id']}",
            {"role": "admin"}, jeton=patron["jeton"], methode="PUT")
        verifie("l'administrateur du projet, lui, nomme un administrateur de groupe",
                code == 200, f"{code} {detail[:90]}")

        # Devenu administrateur du groupe, il gère les participants… mais ne nomme pas.
        code, detail = essai_appel(
            f"/api/themes/{groupe['id']}/membres/{tiers['compte']['id']}",
            {"role": "membre"}, jeton=collegue["jeton"], methode="PUT")
        verifie("l'administrateur du groupe gère les participants (rôle membre)",
                code == 200, f"{code} {detail[:90]}")
        code, detail = essai_appel(
            f"/api/themes/{groupe['id']}/membres/{tiers['compte']['id']}",
            {"role": "admin"}, jeton=collegue["jeton"], methode="PUT")
        verifie("… mais il ne s'arroge pas le droit de nommer un administrateur",
                code == 403, f"{code} {detail[:90]}")
        code, detail = essai_appel(
            f"/api/themes/{groupe['id']}/membres/{collegue['compte']['id']}",
            {"role": "membre"}, jeton=collegue["jeton"], methode="PUT")
        verifie("… et ne peut pas retirer l'administration (lui-même compris)",
                code == 403, f"{code} {detail[:90]}")

        # 4) l'écran : la pastille annonce « Visiteur » pour un membre du projet sans rôle ici
        with sync_playwright() as p:
            nav = p.chromium.launch(args=["--no-sandbox"])
            ctx = nav.new_context(viewport={"width": 1280, "height": 900})
            ctx.add_init_script(
                "localStorage.setItem('synergie.jeton', %s);"
                "localStorage.setItem('synergie.projet', %s);"
                % (json.dumps(patron["jeton"]), json.dumps(projet["id"])))
            ctx.add_cookies([{"name": "synergie", "value": patron["jeton"], "url": BASE,
                              "httpOnly": True, "sameSite": "Lax"}])
            page = ctx.new_page()
            erreurs = []
            page.on("pageerror", lambda e: erreurs.append(str(e)[:120]))
            page.goto(f"{BASE}/#t={groupe['id']}", wait_until="load", timeout=45000)
            page.wait_for_timeout(3000)
            personnes = page.eval_on_selector_all(
                "#apercu-membres-theme .personne",
                """els => els.map(e => ({
                     nom: (e.querySelector('.nom-personne')||{}).textContent||'',
                     statut: (e.querySelector('.statut')||{}).textContent||''}))""")
            par_nom = {p["nom"]: p["statut"] for p in personnes}
            verifie("l'écran annonce « Visiteur » pour un membre du projet sans rôle ici",
                    par_nom.get("Essai rôles témoin") == "Visiteur", par_nom)
            verifie("les administrateurs du groupe sont annoncés « Admin »",
                    par_nom.get("Essai rôles patron") == "Admin"
                    and par_nom.get("Essai rôles collègue") == "Admin", par_nom)
            verifie("aucune erreur JavaScript dans l'écran du groupe", not erreurs, erreurs[:2])
            os.makedirs(CAPTURES, exist_ok=True)
            page.screenshot(path=f"{CAPTURES}/synergie-roles-groupe.png", full_page=False)
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
        menage([patron["compte"]["id"], collegue["compte"]["id"], tiers["compte"]["id"],
                temoin["compte"]["id"]])
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
