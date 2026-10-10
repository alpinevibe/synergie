#!/usr/bin/env python3
"""La diffusion temps réel traverse-t-elle deux ouvriers ? (constat du 10/10/2026)

Deux serveurs Synergie, deux ports, **la même base** : un navigateur attaché au premier
doit voir ce qu'écrit une personne passée par le second. C'est ce que garantit
`moteur/diffusion.py` — un `NOTIFY` PostgreSQL entre ouvriers — sans lequel chaque
ouvrier ne parlerait qu'à ses propres navigateurs (et la montée en charge serait
impossible : on ne pourrait jamais servir l'application avec plusieurs processus).

    SYNERGIE_BASE=postgresql:///synergie_essai python3 tests/tester_diffusion.py

Sur SQLite, l'essai est ignoré (un seul écrivain, donc rien à traverser) : il sort en 0.
L'essai efface derrière lui le compte et le projet qu'il a créés.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import threading
import time
import urllib.error
import urllib.request

RACINE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, RACINE)

PORT_A, PORT_B = 8231, 8232
UA = ("Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) "
      "Chrome/124.0 Safari/537.36")
COMPTE, PROJET, GROUPE = "Essai diffusion", "Projet essai diffusion", "Groupe essai diffusion"
MESSAGE = "Note écrite par l'ouvrier B."

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


def lancer(port: int) -> subprocess.Popen:
    """Un serveur Synergie (waitress) sur le port demandé, sur la base configurée."""
    return subprocess.Popen(
        [sys.executable, os.path.join(RACINE, "serveur.py"),
         "--hote", "127.0.0.1", "--port", str(port), "--fils", "8"],
        cwd=RACINE, env=dict(os.environ), stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
        text=True,
    )


def attendre(port: int, delai: float = 30.0) -> bool:
    fin = time.time() + delai
    while time.time() < fin:
        try:
            appel(port, "/api/sante")
            return True
        except Exception:  # noqa: BLE001 - le serveur démarre encore
            time.sleep(0.4)
    return False


def ecouter(port: int, groupe: str, jeton: str, recus: list, arret: threading.Event) -> None:
    """Lit le flux temps réel du groupe sur ce serveur, et garde les événements."""
    requete = urllib.request.Request(
        f"http://127.0.0.1:{port}/api/themes/{groupe}/evenements?nom=Essai")
    requete.add_header("User-Agent", UA)
    requete.add_header("X-Synergie-Jeton", jeton)  # le flux est réservé aux membres
    try:
        with urllib.request.urlopen(requete, timeout=40) as flux:
            for ligne in flux:
                if arret.is_set():
                    return
                texte = ligne.decode("utf-8").strip()
                if texte.startswith("data:"):
                    try:
                        recus.append(json.loads(texte[5:].strip()))
                    except ValueError:
                        pass
    except Exception as erreur:  # noqa: BLE001 - flux interrompu
        recus.append({"type": "erreur", "detail": str(erreur)})


def attendre_evenement(recus: list, type_voulu: str, delai: float = 15.0) -> dict | None:
    fin = time.time() + delai
    while time.time() < fin:
        for evenement in list(recus):
            if evenement.get("type") == type_voulu:
                return evenement
        time.sleep(0.2)
    return None


def menage(compte: str, projet: str, groupe: str) -> None:
    """Efface ce que l'essai a créé (l'essai ne doit laisser aucune trace)."""
    try:
        from moteur import atelier, equipe, projets
        with atelier.connexion() as connexion:
            for table, colonne in (("notes", "theme"), ("messages", "theme"),
                                   ("journal", "theme"), ("theme_membres", "theme")):
                connexion.execute(f"delete from {table} where {colonne} = ?", (groupe,))
            connexion.execute("delete from themes where id = ?", (groupe,))
            connexion.execute("delete from projet_membres where projet = ?", (projet,))
            connexion.execute("delete from projets where id = ?", (projet,))
        with atelier.connexion() as connexion:
            connexion.execute("delete from comptes where id = ?", (compte,))
    except Exception as erreur:  # noqa: BLE001 - le ménage ne doit pas masquer le résultat
        print(f"  (ménage impossible : {erreur})")


def principal() -> int:
    if not os.environ.get("SYNERGIE_BASE", "").startswith("postgres"):
        print("essai ignoré : la diffusion entre ouvriers suppose PostgreSQL "
              "(SYNERGIE_BASE=postgresql:///synergie_essai)")
        return 0

    print("— démarrage de deux ouvriers sur la même base —")
    serveurs = [lancer(PORT_A), lancer(PORT_B)]
    try:
        if not all(attendre(port) for port in (PORT_A, PORT_B)):
            for serveur in serveurs:
                serveur.terminate()
            print("serveurs non démarrés :\n" + (serveurs[0].stdout.read() or ""), file=sys.stderr)
            return 2
        verifie("les deux ouvriers répondent", True, f"ports {PORT_A} et {PORT_B}")

        compte = appel(PORT_A, "/api/comptes", {"prenom": COMPTE})
        jeton = compte["jeton"]
        projet = appel(PORT_A, "/api/projets", {"nom": PROJET}, jeton=jeton)
        groupe = appel(PORT_A, "/api/themes", {"titre": GROUPE, "projet": projet["id"]}, jeton=jeton)
        verifie("un compte, un projet et un groupe d'essai sont créés", bool(groupe["id"]),
                groupe.get("id"))
        identifiant = groupe["id"]

        recus_a, recus_b = [], []
        arret = threading.Event()
        fils = [
            threading.Thread(target=ecouter,
                             args=(PORT_A, identifiant, jeton, recus_a, arret), daemon=True),
            threading.Thread(target=ecouter,
                             args=(PORT_B, identifiant, jeton, recus_b, arret), daemon=True),
        ]
        for fil in fils:
            fil.start()
        time.sleep(2.5)  # le temps que les deux navigateurs soient abonnés
        verifie("les deux navigateurs sont abonnés",
                bool(attendre_evenement(recus_a, "bonjour", 5)) and
                bool(attendre_evenement(recus_b, "bonjour", 5)))

        # La note est écrite par l'ouvrier B : l'ouvrier A ne peut la voir que par NOTIFY.
        appel(PORT_B, f"/api/themes/{identifiant}/notes", {"texte": MESSAGE}, jeton=jeton)
        recu_a = attendre_evenement(recus_a, "note_creee")
        recu_b = attendre_evenement(recus_b, "note_creee")
        verifie("l'ouvrier qui a reçu l'écriture la diffuse chez lui",
                recu_b is not None and recu_b.get("note", {}).get("texte") == MESSAGE)
        verifie("l'AUTRE ouvrier la diffuse aussi (NOTIFY)",
                recu_a is not None and recu_a.get("note", {}).get("texte") == MESSAGE,
                "sans la notification, ce navigateur ne verrait rien")
        verifie("l'événement n'arrive qu'une fois par ouvrier",
                len([e for e in recus_a if e.get("type") == "note_creee"]) == 1 and
                len([e for e in recus_b if e.get("type") == "note_creee"]) == 1)

        arret.set()
        menage(compte["compte"]["id"], projet["id"], identifiant)
    finally:
        for serveur in serveurs:
            serveur.terminate()
        for serveur in serveurs:
            try:
                serveur.wait(timeout=10)
            except subprocess.TimeoutExpired:  # pragma: no cover - arrêt forcé
                serveur.kill()

    echecs = [titre for titre, ok in RESULTATS if not ok]
    print("\n" + "=" * 60)
    print(f"{len(RESULTATS) - len(echecs)} contrôle(s) réussi(s), {len(echecs)} échec(s).")
    if echecs:
        print("ÉCHEC : " + " ; ".join(echecs))
        return 1
    print("CONFORME : la diffusion traverse les ouvriers.")
    return 0


if __name__ == "__main__":
    sys.exit(principal())
