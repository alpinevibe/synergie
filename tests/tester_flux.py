#!/usr/bin/env python3
"""Le flux asynchrone tient-il plusieurs centaines de navigateurs ? (10/10/2026)

Trois choses sont vérifiées ici :

  1. **le nombre** : 150 navigateurs en direct sont servis par le service de flux, et le
     processus reste à une poignée de fils (c'est tout l'intérêt de l'asynchrone : avec le
     serveur applicatif, 150 connexions auraient demandé 150 fils) ;
  2. **la portée** : une note écrite par l'application (processus distinct) atteint **les
     150** navigateurs — c'est le `NOTIFY` PostgreSQL qui fait le lien ;
  3. **la présence** : les 150 apparaissent dans « qui est en ligne », et disparaissent
     quand ils ferment.

    SYNERGIE_BASE=postgresql:///synergie_essai python3 tests/tester_flux.py

L'essai efface derrière lui ce qu'il a créé. Sur SQLite, il est ignoré (le lien entre
ouvriers n'existe pas) et sort en 0.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import threading
import time
import urllib.error
import urllib.parse
import urllib.request

RACINE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, RACINE)

PORT_APP, PORT_FLUX = 8241, 8242
NAVIGATEURS = 150
UA = ("Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) "
      "Chrome/124.0 Safari/537.36")
COMPTE, PROJET, GROUPE = "Essai flux", "Projet essai flux", "Groupe essai flux"

RESULTATS: list[tuple[str, bool]] = []


def verifie(titre: str, condition, detail="") -> None:
    RESULTATS.append((titre, bool(condition)))
    print(("  ✅ " if condition else "  ❌ ") + titre + ((" — " + str(detail)) if detail else ""))


def appel(port: int, chemin: str, corps=None, jeton=None):
    donnees = json.dumps(corps).encode("utf-8") if corps is not None else None
    requete = urllib.request.Request(f"http://127.0.0.1:{port}{chemin}", data=donnees,
                                     method="POST" if donnees else "GET")
    requete.add_header("Content-Type", "application/json")
    requete.add_header("User-Agent", UA)
    if jeton:
        requete.add_header("X-Synergie-Jeton", jeton)
    with urllib.request.urlopen(requete, timeout=30) as reponse:
        return json.loads(reponse.read().decode("utf-8"))


def attendre_serveur(port: int, chemin: str, delai: float = 30.0) -> bool:
    fin = time.time() + delai
    while time.time() < fin:
        try:
            appel(port, chemin)
            return True
        except Exception:  # noqa: BLE001 - le serveur démarre encore
            time.sleep(0.4)
    return False


def navigateur(port: int, groupe: str, jeton: str, nom: str, recus: list,
               arret: threading.Event) -> None:
    """Une connexion en direct, comme celle d'un navigateur (elle ne rend pas la main)."""
    requete = urllib.request.Request(
        f"http://127.0.0.1:{port}/api/themes/{groupe}/evenements?nom={urllib.parse.quote(nom)}")
    requete.add_header("User-Agent", UA)
    requete.add_header("X-Synergie-Jeton", jeton)
    try:
        with urllib.request.urlopen(requete, timeout=60) as flux:
            for ligne in flux:
                if arret.is_set():
                    return
                texte = ligne.decode("utf-8").strip()
                if texte.startswith("data:"):
                    try:
                        evenement = json.loads(texte[5:].strip())
                    except ValueError:
                        continue
                    recus.append(evenement)
    except Exception as erreur:  # noqa: BLE001 - flux interrompu
        if not arret.is_set():
            recus.append({"type": "erreur", "detail": str(erreur)})


def fils_du_processus(pid: int) -> int:
    try:
        with open(f"/proc/{pid}/status") as fichier:
            for ligne in fichier:
                if ligne.startswith("Threads:"):
                    return int(ligne.split()[1])
    except OSError:
        pass
    return -1


def attendre_evenements(navigateurs: list[dict], type_voulu: str, delai: float = 30.0) -> int:
    """Combien de navigateurs ont reçu l'événement, au bout du délai accordé."""
    fin = time.time() + delai
    while time.time() < fin:
        combien = sum(1 for n in navigateurs
                      if any(e.get("type") == type_voulu for e in n["recus"]))
        if combien == len(navigateurs):
            return combien
        time.sleep(0.3)
    return sum(1 for n in navigateurs if any(e.get("type") == type_voulu for e in n["recus"]))


def menage(compte: str, projet: str, groupe: str) -> None:
    try:
        from moteur import atelier, projets
        atelier.supprimer_theme(groupe)
        projets.supprimer_projet(projet)
        with atelier.connexion() as connexion:
            connexion.execute("delete from comptes where id = ?", (compte,))
    except Exception as erreur:  # noqa: BLE001 - le ménage ne masque pas le résultat
        print(f"  (ménage incomplet : {erreur})")


def principal() -> int:
    if "postgres" not in os.environ.get("SYNERGIE_BASE", ""):
        print("essai ignoré : le flux entre ouvriers suppose PostgreSQL "
              "(SYNERGIE_BASE=postgresql:///synergie_essai)")
        return 0

    import urllib.parse  # noqa: E402 - utilisé par les navigateurs d'essai

    print("— démarrage du serveur applicatif et du service de flux —")
    app = subprocess.Popen(
        [sys.executable, os.path.join(RACINE, "serveur.py"), "--hote", "127.0.0.1",
         "--port", str(PORT_APP), "--fils", "8"],
        cwd=RACINE, env=dict(os.environ), stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
    flux = subprocess.Popen(
        [sys.executable, "-m", "uvicorn", "flux:app", "--host", "127.0.0.1",
         "--port", str(PORT_FLUX), "--log-level", "warning"],
        cwd=RACINE, env=dict(os.environ), stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
    processus = [app, flux]
    arret = threading.Event()
    try:
        if not (attendre_serveur(PORT_APP, "/api/sante") and attendre_serveur(PORT_FLUX, "/sante")):
            print("serveurs non démarrés", file=sys.stderr)
            return 2

        compte = appel(PORT_APP, "/api/comptes", {"prenom": COMPTE})
        jeton = compte["jeton"]
        projet = appel(PORT_APP, "/api/projets", {"nom": PROJET}, jeton=jeton)
        groupe = appel(PORT_APP, "/api/themes", {"titre": GROUPE, "projet": projet["id"]}, jeton=jeton)
        identifiant = groupe["id"]

        print(f"— {NAVIGATEURS} navigateurs en direct sur le service de flux —")
        navigateurs = [{"recus": [], "nom": f"Essai {rang}"} for rang in range(NAVIGATEURS)]
        for rang, entree in enumerate(navigateurs):
            entree["fils"] = threading.Thread(
                target=navigateur,
                args=(PORT_FLUX, identifiant, jeton, entree["nom"], entree["recus"], arret),
                daemon=True)
        for entree in navigateurs:
            entree["fils"].start()
        time.sleep(6)   # le temps que les connexions s'installent et reçoivent « bonjour »

        bonjours = attendre_evenements(navigateurs, "bonjour", 30)
        verifie(f"les {NAVIGATEURS} navigateurs sont servis", bonjours == NAVIGATEURS,
                f"{bonjours}/{NAVIGATEURS}")
        if bonjours != NAVIGATEURS:
            for entree in navigateurs:
                if not any(e.get("type") == "bonjour" for e in entree["recus"]):
                    print(f"    {entree['nom']} : {entree['recus'][:1]}")
        sante = appel(PORT_FLUX, "/sante")
        print(f"  état du flux : {sante}")
        verifie("le service en compte autant qu'il en a ouvert",
                sante.get("connexions_ouvertes") == NAVIGATEURS, sante.get("connexions_ouvertes"))
        fils = fils_du_processus(flux.pid)
        verifie("le flux reste à une poignée de fils (asynchrone)",
                0 < fils <= 40, f"{fils} fils pour {NAVIGATEURS} connexions")

        # La note est écrite par l'APPLICATION : seul le NOTIFY relie les deux processus.
        appel(PORT_APP, f"/api/themes/{identifiant}/notes", {"texte": "Bonjour à tous"},
              jeton=jeton)
        atteints = attendre_evenements(navigateurs, "note_creee", 30)
        verifie("une écriture de l'application atteint les 150 navigateurs",
                atteints == NAVIGATEURS, f"{atteints}/{NAVIGATEURS}")

        # Présence : les 150 noms sont dans « qui est en ligne » (relu par l'application).
        resume = appel(PORT_APP, f"/api/themes/{identifiant}", jeton=jeton)
        presents = resume.get("participants") or []
        verifie("les 150 apparaissent dans « qui est en ligne »", len(presents) == NAVIGATEURS,
                f"{len(presents)} présent(s)")

        # Les gestes ne doivent pas écrire en base : un curseur, lui, doit passer.
        avant = appel(PORT_APP, f"/api/themes/{identifiant}", jeton=jeton)
        note = avant["notes"][0]
        appel(PORT_APP, f"/api/themes/{identifiant}/gestes",
              {"id": note["id"], "x": 1234, "y": 567}, jeton=jeton)
        gestes = attendre_evenements(navigateurs, "note_geste", 15)
        verifie("un geste (déplacement en cours) est relayé sans écriture",
                gestes == NAVIGATEURS, f"{gestes}/{NAVIGATEURS}")
        apres = appel(PORT_APP, f"/api/themes/{identifiant}", jeton=jeton)
        verifie("le geste n'a rien écrit en base",
                apres["notes"][0]["x"] == note["x"] and apres["notes"][0]["y"] == note["y"],
                f"x={apres['notes'][0]['x']} (attendu {note['x']})")

        # Fermeture : les présences doivent se vider (le souffle du flux les fait disparaître
        # dans les 15 secondes qui suivent la coupure).
        arret.set()
        presents = None
        for _ in range(24):
            time.sleep(2)
            resume = appel(PORT_APP, f"/api/themes/{identifiant}", jeton=jeton)
            presents = resume.get("participants") or []
            if not presents:
                break
        verifie("après fermeture, plus personne n'est en ligne", not presents,
                f"{len(presents or [])} restant(s)")

        menage(compte["compte"]["id"], projet["id"], identifiant)
    finally:
        for processus_ in processus:
            processus_.terminate()
        for processus_ in processus:
            try:
                processus_.wait(timeout=10)
            except subprocess.TimeoutExpired:  # pragma: no cover - arrêt forcé
                processus_.kill()

    echecs = [titre for titre, ok in RESULTATS if not ok]
    print("\n" + "=" * 60)
    print(f"{len(RESULTATS) - len(echecs)} contrôle(s) réussi(s), {len(echecs)} échec(s).")
    if echecs:
        print("ÉCHEC : " + " ; ".join(echecs))
        return 1
    print("CONFORME : le flux asynchrone tient la charge, et la présence suit.")
    return 0


if __name__ == "__main__":
    sys.exit(principal())
