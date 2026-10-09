#!/usr/bin/env python3
"""Invitations : envoi (relance) par courriel et alerte à l'inscription (09/10/2026).

Demandes de l'utilisateur : « réactive l'envoi des mails […] lance l'invitation pour les 12
rajouts » et « active de me prévenir par mail lorsqu'un agent utilise son lien d'inscription
et s'inscrit ».

Ce contrôle travaille sur un projet d'essai (créé puis effacé) et vérifie :
  1. l'application sait SI les envois sont ouverts (`envoi_actif`) ;
  2. on peut (re)envoyer UNE invitation, puis TOUTES celles en attente ;
  3. les boutons « Envoyer » sont bien là dans la fenêtre des membres (un par ligne, et pour
     tout envoyer d'un geste) ;
  4. quand quelqu'un active son lien d'inscription, un courriel part vers l'administrateur.

Les adresses d'essai sont en `.invalid` (domaine réservé) : **aucun courriel ne peut arriver
quelque part** ; on lit dans le journal d'envoi la trace de la tentative, ce qui prouve que le
mécanisme s'est bien déclenché.

    python3 tests/tester_invitations_envoi.py
    SYNERGIE_SITE=https://synergie.alpinevibe.fr python3 tests/tester_invitations_envoi.py
"""
import json
import os
import sys
import urllib.error
import urllib.request

from playwright.sync_api import sync_playwright

BASE = os.environ.get("SYNERGIE_SITE", "http://127.0.0.1:8077").rstrip("/")
CAPTURES = os.environ.get("CHECKUP_CAPTURES", "/home/ubuntu/captures")
JOURNAL = "/home/ubuntu/synergie/donnees/journal-alertes.log"
TITRE = "Essai — envoi des invitations"
ADMIN = "admin.essai@exemple.invalid"
COLLEAGUES = ["invite1@exemple.invalid", "invite2@exemple.invalid", "invite3@exemple.invalid"]

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


def journal(nombre=40):
    try:
        with open(JOURNAL, encoding="utf-8") as fichier:
            return fichier.readlines()[-nombre:]
    except OSError:
        return []


def taille_journal() -> int:
    """Position de la fin du journal d'envoi : ce qui est écrit APRÈS nous intéresse."""
    try:
        return os.path.getsize(JOURNAL)
    except OSError:
        return 0


def depuis(position: int) -> list[str]:
    """Les lignes écrites dans le journal depuis la position donnée."""
    try:
        with open(JOURNAL, encoding="utf-8") as fichier:
            fichier.seek(position)
            return [ligne.strip() for ligne in fichier if ligne.strip()]
    except OSError:
        return []


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


def principal() -> int:
    try:
        compte = appel("/api/comptes", {"prenom": "Essai envoi"})
    except urllib.error.URLError as erreur:
        print(f"Synergie injoignable sur {BASE} : {erreur}", file=sys.stderr)
        return 2
    jeton = compte["jeton"]
    projet = None
    invites = []
    try:
        projet = appel("/api/projets", {"nom": TITRE}, jeton=jeton)
        # L'administrateur du projet reçoit l'alerte d'inscription à SON adresse.
        appel("/api/comptes/moi", {"email": ADMIN}, jeton=jeton, methode="PUT")
        invitations = [appel(f"/api/projets/{projet['id']}/invitations",
                             {"email": adresse, "role": "membre"}, jeton=jeton)["invitation"]
                       for adresse in COLLEAGUES]

        # ---- 1 et 2 : les envois, par l'API ---------------------------------------------
        print("\nEnvoi des invitations :")
        taille_avant = taille_journal()
        fiche = appel(f"/api/projets/{projet['id']}/invitations", jeton=jeton)
        verifie("l'application dit si les envois sont ouverts", "envoi_actif" in fiche,
                {k: v for k, v in fiche.items() if k != "invitations"})
        verifie("les envois sont bien OUVERTS", fiche["envoi_actif"] is True, fiche["envoi_actif"])
        verifie("les trois invitations sont en attente",
                len([i for i in fiche["invitations"] if not i["utilise_le"]]) == 3)

        un = appel(f"/api/projets/{projet['id']}/invitations/envoi",
                   {"invitations": [invitations[0]["id"]]}, jeton=jeton)
        verifie("UNE invitation peut être envoyée seule", un["envoyes"] == 1, un)
        tous = appel(f"/api/projets/{projet['id']}/invitations/envoi", {}, jeton=jeton)
        verifie("le bouton global renvoie TOUTES les invitations en attente",
                tous["envoyes"] == 3 and sorted(tous["emails"]) == sorted(COLLEAGUES), tous)
        import time
        time.sleep(6)                                # le facteur expédie en arrière-plan
        expediees = depuis(taille_avant)
        verifie("chaque envoi est noté au journal d'expédition",
                sum(1 for ligne in expediees if any(a in ligne for a in COLLEAGUES)) >= 3,
                expediees[-3:])

        # ---- 3 : les boutons dans la fenêtre des membres --------------------------------
        print("\nBoutons dans la fenêtre des membres :")
        with sync_playwright() as p:
            nav = p.chromium.launch()
            ctx = nav.new_context(viewport={"width": 1100, "height": 800},
                                  ignore_https_errors=True)
            ctx.add_init_script(
                "localStorage.setItem('synergie.jeton', %s);"
                "localStorage.setItem('synergie.projet', %s);"
                "localStorage.setItem('synergie.nom', 'Essai envoi');"
                % (json.dumps(jeton), json.dumps(projet["id"])))
            ctx.add_cookies([{"name": "synergie", "value": jeton, "url": BASE,
                              "httpOnly": True, "sameSite": "Lax"}])
            page = ctx.new_page()
            erreurs = []
            page.on("pageerror", lambda e: erreurs.append(str(e)))
            page.goto(f"{BASE}/#p={projet['id']}", wait_until="load")
            page.wait_for_timeout(2500)
            page.click("#btn-membres")
            page.wait_for_timeout(1200)
            os.makedirs(CAPTURES, exist_ok=True)
            page.screenshot(path=os.path.join(CAPTURES, "synergie-invitations-envoi.png"))
            boutons = page.eval_on_selector_all(
                "#invitations-en-cours button", "n => n.map(b => b.textContent.trim())")
            verifie("chaque invitation a son bouton « Envoyer »",
                    boutons.count("Envoyer") == 3, boutons)
            verifie("un bouton envoie toutes les invitations d'un geste",
                    any("invitations" in b for b in boutons), boutons)
            verifie("aucune erreur JavaScript", not erreurs, erreurs[:2])
            ctx.close()
            nav.close()

        # ---- 4 : l'alerte quand quelqu'un s'inscrit -------------------------------------
        print("\nAlerte à l'inscription :")
        avant = taille_journal()
        appel(f"/api/invitations/{invitations[0]['jeton']}",
              {"prenom": "Invite", "identifiant": "invite.essai"})
        import time
        time.sleep(6)                                # le courriel part en arrière-plan
        nouvelles = depuis(avant)
        verifie("un courriel part vers l'administrateur quand quelqu'un s'inscrit",
                any(ADMIN in ligne for ligne in nouvelles),
                [ligne.strip()[:110] for ligne in nouvelles[-3:]])
        utilisateur = appel(f"/api/connexion", {"identifiant": "invite.essai"})
        verifie("la personne inscrite entre avec son identifiant",
                utilisateur["compte"]["prenom"] == "Invite")
        invites = [utilisateur["compte"]["id"]]
    finally:
        # Le PROJET d'abord (avec le jeton encore valable), les comptes ensuite : dans l'autre
        # ordre, le ménage se ferait avec un jeton devenu inutile et laisserait le projet.
        if projet:
            try:
                appel(f"/api/projets/{projet['id']}", jeton=jeton, methode="DELETE")
            except Exception:
                pass
        menage(compte["compte"]["id"], invites)

    echecs = sum(1 for _, ok in RESULTATS if not ok)
    print(f"\n{len(RESULTATS) - echecs}/{len(RESULTATS)} contrôles réussis")
    return 1 if echecs else 0


if __name__ == "__main__":
    sys.exit(principal())
