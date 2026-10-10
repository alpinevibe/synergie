#!/usr/bin/env python3
"""SYNERGIE — le service de flux : le temps réel servi **en asynchrone**.

Chaque navigateur en direct occupe une connexion. Servi par le serveur applicatif (WSGI),
chaque connexion coûtait un **fil** : une soixantaine au maximum, et le fil restait occupé
tout le temps où la personne regardait la page. Ici le même travail est fait par des tâches
asynchrones : plusieurs centaines de navigateurs tiennent dans un seul processus, et le
serveur applicatif ne s'occupe plus que des écritures.

Ce que le service fait :

  • il **vérifie le jeton et les droits** du groupe (les mêmes règles que l'application,
    par le moteur partagé `moteur/`) ;
  • il tient « qui est en ligne » dans la table `presences`, en base — donc le même
    renseignement partout, quel que soit l'ouvrier qui sert le navigateur ;
  • il **écoute le canal PostgreSQL `synergie`** et rediffuse aux navigateurs d'ici : c'est
    le seul lien nécessaire entre l'application qui écrit et le flux qui parle. Rien à
    installer de plus, et plusieurs ouvriers de flux pourraient tourner côte à côte.

Lancer :

    SYNERGIE_BASE=postgresql:///synergie python3 -m uvicorn flux:app \\
        --host 127.0.0.1 --port 8078

nginx envoie ici `/api/themes/<id>/evenements` et `/api/projets/<id>/evenements`
(`deploy/nginx-synergie.conf`). Sans nginx (essai local), le serveur applicatif sait encore
servir ces deux routes : le service de flux est un complément, pas un prérequis.
"""
from __future__ import annotations

import asyncio
import json
import os
import sys
import uuid
from contextlib import asynccontextmanager
from pathlib import Path

RACINE = Path(__file__).resolve().parent
sys.path.insert(0, str(RACINE))

from moteur import atelier, base, diffusion, equipe, projets  # noqa: E402

from starlette.applications import Starlette  # noqa: E402
from starlette.responses import JSONResponse, StreamingResponse  # noqa: E402
from starlette.routing import Route  # noqa: E402

#: Les files d'attente des navigateurs, par groupe (ou par projet pour le flux général).
ABONNES: dict[str, set[asyncio.Queue]] = {}
#: Le nombre de connexions servies depuis le démarrage (affiché par /sante).
CONNEXIONS = {"total": 0, "ouvertes": 0}

SOUFFLE = 15          # secondes entre deux battements de cœur
#: Un événement plus gros que la limite d'une notification est publié sans son contenu.
LIMITE_NOTIFICATION = diffusion.LIMITE


def _donnee(evenement: dict) -> str:
    return "data: " + json.dumps(evenement, ensure_ascii=False) + "\n\n"


def _jeton(requete) -> str | None:
    """Le jeton du navigateur : en-tête (tests, scripts) ou cookie (EventSource)."""
    valeur = requete.headers.get("x-synergie-jeton")
    if valeur:
        return valeur.strip()
    return requete.cookies.get("synergie")


def _droits(genre: str, identifiant: str, compte: dict) -> bool:
    """Les mêmes règles que l'application : membre du groupe, ou du projet."""
    if genre == "projets":
        projet = projets.lire_projet(identifiant)
        if not projet:
            return False
        return projets.role_du_projet(identifiant, compte["id"]) is not None
    theme = atelier.lire_theme(identifiant)
    if not theme:
        return False
    role = projets.role_effectif(theme.get("projet") or "", identifiant, compte["id"])
    return role is not None


async def _publier(identifiant: str, evenement: dict) -> None:
    """Diffuse chez les navigateurs d'ici **et** prévient les autres ouvriers."""
    _diffuser_local(identifiant, evenement)
    await asyncio.to_thread(diffusion.publier, identifiant, evenement)


def _diffuser_local(identifiant: str, evenement: dict) -> None:
    for file in list(ABONNES.get(identifiant) or ()):
        try:
            file.put_nowait(evenement)
        except asyncio.QueueFull:
            # Un navigateur trop lent à lire (téléphone en veille) : on préfère perdre un
            # événement plutôt que de faire attendre les autres. Il redemandera l'état.
            continue


def _partir(identifiant: str, numero: str, file: asyncio.Queue) -> None:
    """Le départ d'un navigateur : à faire **sans `await`**.

    Quand la page se ferme, uvicorn annule la tâche du flux ; le `finally` s'exécute alors
    dans une tâche déjà annulée, où le moindre `await` est refusé — une personne partie
    restait donc affichée « en ligne » (constaté le 10/10/2026 avec 150 connexions). Le
    ménage se fait ici en direct : quelques millisecondes, et jamais d'exception qui remonte.
    Idempotent : un départ peut être constaté deux fois (flux annulé, handler repris).
    """
    files = ABONNES.get(identifiant)
    if files is None or file not in files:
        return
    files.discard(file)
    CONNEXIONS["ouvertes"] -= 1
    try:
        atelier.presence_retirer(identifiant, numero)
        diffusion.publier(identifiant, {
            "type": "presence", "participants": atelier.participants(identifiant)})
    except Exception as erreur:  # noqa: BLE001 - un départ ne doit jamais lever
        print(f"flux : ménage du départ impossible ({erreur})", file=sys.stderr, flush=True)


async def evenements(requete):
    """Le flux temps réel d'un groupe (ou d'un projet) : Server-Sent Events."""
    genre = requete.url.path.split("/")[2]      # « themes » ou « projets »
    identifiant = requete.path_params["identifiant"]
    nom = requete.query_params.get("nom") or "Anonyme"

    compte = await asyncio.to_thread(equipe.lire_compte, _jeton(requete))
    if compte is None:
        return JSONResponse({"erreur": "Compte inconnu : créez votre compte dans Synergie."},
                            status_code=401)
    if not await asyncio.to_thread(_droits, genre, identifiant, compte):
        return JSONResponse({"erreur": "Vous n'avez pas accès à ce groupe de travail."},
                            status_code=403)

    file: asyncio.Queue = asyncio.Queue(maxsize=1000)
    ABONNES.setdefault(identifiant, set()).add(file)
    numero = f"flux-{uuid.uuid4().hex[:8]}"
    try:
        await asyncio.to_thread(atelier.presence_nettoyer, identifiant)
        await asyncio.to_thread(atelier.presence_marquer, identifiant, numero, nom)
        presences = await asyncio.to_thread(atelier.participants, identifiant)
        await _publier(identifiant, {"type": "presence", "participants": presences})
    except BaseException:
        _partir(identifiant, numero, file)   # une file abandonnée ne doit pas rester
        raise
    CONNEXIONS["total"] += 1
    CONNEXIONS["ouvertes"] += 1

    async def flux():
        try:
            yield "retry: 3000\n\n"
            yield _donnee({"type": "bonjour", "participants": presences})
            while True:
                try:
                    evenement = await asyncio.wait_for(file.get(), timeout=SOUFFLE)
                except asyncio.TimeoutError:
                    # Le souffle est aussi le battement de cœur de la présence.
                    await asyncio.to_thread(atelier.presence_marquer, identifiant, numero, nom)
                    yield ": souffle\n\n"
                    continue
                yield _donnee(evenement)
        finally:
            _partir(identifiant, numero, file)

    return StreamingResponse(flux(), media_type="text/event-stream", headers={
        "Cache-Control": "no-cache",
        "X-Accel-Buffering": "no",   # nginx : ne pas mettre le flux dans un tampon
        "Connection": "keep-alive",
    })


async def sante(_requete):
    return JSONResponse({
        "service": "synergie-flux",
        "moteur": base.nom_moteur(),
        "abonnes": sum(len(files) for files in ABONNES.values()),
        "connexions_ouvertes": CONNEXIONS["ouvertes"],
        "connexions_servies": CONNEXIONS["total"],
    })


async def ecouter_canal() -> None:
    """Écoute le canal `synergie` : ce que les autres processus publient arrive ici."""
    import psycopg

    while True:
        try:
            connexion = await psycopg.AsyncConnection.connect(base.source(), autocommit=True)
            async with connexion:
                await connexion.execute(f"listen {diffusion.CANAL}")
                print(f"flux : à l'écoute du canal « {diffusion.CANAL} »", file=sys.stderr, flush=True)
                async for notification in connexion.notifies():
                    try:
                        charge = json.loads(notification.payload)
                    except ValueError:
                        continue
                    if charge.get("origine") == base.PROCESSUS:
                        continue      # déjà diffusé ici même
                    _diffuser_local(charge.get("theme") or "", charge.get("evenement") or {})
        except Exception as erreur:  # noqa: BLE001 - PostgreSQL indisponible : on retente
            print(f"flux : écoute interrompue ({erreur}), nouvelle tentative dans 2 s",
                  file=sys.stderr, flush=True)
            await asyncio.sleep(2)


async def demarrer() -> None:
    """Installe l'écoute du canal PostgreSQL (une tâche de fond, pour la vie du processus)."""
    asyncio.create_task(ecouter_canal())
    print(f"flux : {base.nom_moteur()} — {base.source()}", file=sys.stderr, flush=True)


@asynccontextmanager
async def cycle(_app):
    """Le cycle de vie du service : l'écoute du canal démarre avec le service."""
    await demarrer()
    yield


app = Starlette(routes=[
    Route("/sante", sante),
    Route("/api/themes/{identifiant}/evenements", evenements),
    Route("/api/projets/{identifiant}/evenements", evenements),
], lifespan=cycle)


if __name__ == "__main__":  # pragma: no cover - confort : lancement direct
    import uvicorn

    uvicorn.run(app, host=os.environ.get("SYNERGIE_FLUX_HOTE", "127.0.0.1"),
                port=int(os.environ.get("SYNERGIE_FLUX_PORT", "8078")))
