# Synergie

**Travailler ensemble, décider ensemble.** Synergie est un **atelier collaboratif** : un
**projet** réunit une équipe autour de **groupes de travail**. Dans chaque groupe, on écrit
ce qui nous passe par la tête sur un **tableau blanc sans limites**, on dépose ses
**documents**, on discute et on **prend des décisions** — chacun voyant les modifications des
autres **en direct**.

Deux idées gouvernent l'application :

- **plusieurs projets** peuvent vivre côte à côte (un projet = une réorganisation, un
  service, un sujet) — chacun avec **ses groupes**, **ses membres** et **ses rôles** ;
- **chaque groupe a les mêmes outils** : tableau blanc, pages, discussion, documents,
  décisions, journal. Aucun outil « réservé » : l'outil ne complique pas la méthode.

> La construction des cycles de planning (boîte à trames, fiches de poste, codes horaires) a
> **quitté Synergie le 08/10/2026** : elle devient l'application **Orbis**.

---

## À quoi ça sert

| Question | Réponse de Synergie |
|---|---|
| Où rassembler les idées d'une équipe sur un sujet ? | Un **groupe de travail** : chacun écrit sur le tableau blanc, sans hiérarchie et sans ordre imposé. |
| Comment réfléchir à plusieurs, en même temps ? | Le tableau est **partagé en direct** : les notes, leurs couleurs et leurs déplacements arrivent chez les autres immédiatement ; on voit **qui est en ligne** et **qui écrit sur quelle note**. |
| Qui a le droit de faire quoi ? | Les **rôles** : **administrateur** (membres, groupes, réglages), **membre participant** (écrit, dépose, propose et vote), **visiteur** (consulte seulement). Un rôle donné **dans un groupe** l'emporte sur celui du projet. |
| Où mettre les documents de travail ? | Dans le groupe, ou dans le projet (comptes rendus de réunion). Chacun les télécharge ; ils ne s'affichent jamais dans le navigateur, par sécurité. |
| Comment savoir ce qui a été tranché ? | Les **décisions** : proposées, puis **adoptées** ou **rejetées**, avec l'auteur et la date. Chacun vote une fois, **anonymement**. |
| Comment être prévenu sans y passer sa journée ? | Chacun choisit, **projet par projet et groupe par groupe**, s'il veut un courriel — ou rien. |
| Comment voter sans se déplacer ? | L'administrateur du groupe **ouvre le vote** : un **lien personnel** part par courriel à chaque votant (membres du groupe, ou tout le projet). **Une personne, une voix**, et les votes restent **anonymes** dans le dépouillement. |
| Et la traçabilité ? | Le **journal** de chaque groupe dit qui a fait quoi et quand ; rien ne s'efface. |

---

## Démarrage

```bash
./run.sh                       # http://127.0.0.1:8077
./run.sh --port 8080 --hote 0.0.0.0
```

En ligne : <https://synergie.alpinevibe.fr/>

---

## Le parcours

### 1. Entrer : son identifiant personnel

On entre avec son **identifiant personnel** — un identifiant ne se devine pas, personne ne
peut donc prendre l'identité d'un autre (c'était possible tant que le prénom suffisait).
Le **poste de travail** (navigateur, système, appareil) est enregistré automatiquement avec
le compte — un site web n'a pas le droit de lire l'identifiant de session Windows — et la
personne peut le **corriger** dans « Mon compte ».

**Comment obtient-on un identifiant ?** Un administrateur de projet invite par
**adresse de courriel** : la personne reçoit un **lien personnel**, y choisit son **prénom**
et son **identifiant**, et rejoint le projet. Le lien ne sert qu'une fois et vaut 30 jours.
Le courriel n'est jamais demandé à l'entrée : il sert à recevoir l'invitation et les alertes.

### 2. Mes projets, puis un projet

L'accueil liste les **projets dont on est membre** (tuiles : nombre de groupes, nombre de
membres, rôle). En haut de l'écran, un **sélecteur** permet de passer d'un projet à l'autre ;
« + Nouveau projet » en crée un (on en devient administrateur). Le **cadre de travail** du
projet (le contexte, en quelques phrases) est un bloc replié : tout le monde le lit d'un
coup d'œil, personne ne le subit.

### 3. Les groupes de travail

Chaque groupe est une **tuile** : titre, description, compteurs, dernier mouvement. Un clic
ouvre le groupe, avec **les mêmes six outils pour tous** :

| Outil | Ce qu'on y fait |
|---|---|
| **Tableau blanc** | notes libres, déplaçables, redimensionnables, mises en forme (6 couleurs de texte, 6 fonds), rangement automatique en colonnes, recherche |
| **Pages** | des pages de travail avec un traitement de texte simple (comptes rendus, procédures) |
| **Discussion** | le fil du groupe |
| **Documents** | les fichiers de travail, téléchargeables par tous |
| **Décisions** | proposer, discuter, voter (anonyme), adopter ou rejeter |
| **Journal** | qui a fait quoi, quand — **réservé aux administrateurs du groupe** |

Le **cadre de travail** du projet se lit en cliquant le **nom du projet**, en haut : tout le
monde le lit, seul l'administrateur le modifie. Sur le tableau blanc, **↶ Annuler** (ou
Ctrl + Z) revient en arrière, et **Ranger** range les post-it **en colonnes par couleur**.

### 4. Les membres et les rôles

Le bouton **Membres** (au projet) liste les personnes avec leur rôle, une case « me prévenir
par courriel », le formulaire d'**invitation par adresse** et les invitations en attente.
Dans un groupe, le bouton **Membres** donne un rôle **propre au groupe**, choisi **parmi les
membres du projet** : utile pour ouvrir un groupe à quelqu'un qui n'a rien à faire ailleurs,
ou pour n'y laisser qu'un droit de lecture.

### 5. Ce que chacun peut faire

| Rôle | Ce qu'il peut faire |
|---|---|
| **Administrateur du projet** | tout : membres, invitations, groupes, cadre de travail, rôles |
| **Membre du projet** | écrire dans la discussion du projet, participer aux groupes, lire — **sauf le journal des groupes** |
| **Visiteur du projet** | voir la discussion et les groupes, **sans rien modifier** ni voir le journal |
| **Rôle dans un groupe** | l'emporte sur le rôle du projet : administrateur, membre participant ou visiteur |

**Seul un administrateur du projet crée des groupes** (et seul un administrateur du groupe
ouvre un vote).

---

## Architecture

```
serveur.py            API + interface (Flask) ; contrôle des rôles
moteur/atelier.py     groupes, notes, décisions, documents, journal, diffusion temps réel
moteur/equipe.py      comptes, discussions, pages, cadre de travail, alertes par courriel
moteur/projets.py     projets, membres, rôles, notifications
moteur/invitations.py invitations par courriel (liens personnels) et bulletins de vote
web/index.html        l'application (projets, groupes, outils)
web/synergie.js       logique de l'application et du temps réel
web/synergie.css      habillage (lisibilité, accessibilité)
donnees/atelier.db    base SQLite (projets, membres, groupes, notes, documents, comptes)
donnees/documents/    fichiers déposés
scripts/migrer-v2-projets.py   migration vers les projets et les rôles (08/10/2026)
```

### Pourquoi SQLite ici ?

Plusieurs personnes écrivent **en même temps** : un fichier JSON se corromprait. SQLite en
mode WAL encaisse les écritures concurrentes sans configuration, tient dans un fichier, et
se sauvegarde comme n'importe quel fichier.

---

## API

Toutes les routes exigent le **jeton du navigateur** (`X-Synergie-Jeton`, ou le cookie
`synergie`) : `_compte(requis=True)`. Les droits se lisent dans les rôles (`moteur/projets.py`).

### Projets et membres

| Méthode | Chemin | Rôle |
|---|---|---|
| GET / POST | `/api/projets` | mes projets / créer un projet |
| GET / PUT / DELETE | `/api/projets/<id>` | lire (avec groupes et membres) / modifier / supprimer |
| POST | `/api/projets/<id>/membres` | inviter (prénom + rôle + alertes) |
| PUT / DELETE | `/api/projets/<id>/membres/<compte>` | changer le rôle / retirer |
| GET / PUT | `/api/projets/<id>/cadre` | le cadre de travail du projet |
| GET / POST | `/api/projets/<id>/documents` | comptes rendus de réunion |
| GET / POST | `/api/projets/<id>/messages` | la discussion du projet |
| GET | `/api/projets/<id>/evenements` | **flux temps réel** du projet (SSE) |

### Groupes de travail

| Méthode | Chemin | Rôle |
|---|---|---|
| GET / POST | `/api/themes` | les groupes de mes projets / créer (administrateur du projet) |
| GET / PUT / DELETE | `/api/themes/<id>` | lire / modifier / supprimer (administrateur) |
| GET / POST | `/api/themes/<id>/membres` | les membres du groupe / inviter |
| PUT / DELETE | `/api/themes/<id>/membres/<compte>` | changer le rôle / retirer |
| POST | `/api/themes/<id>/notes` | créer une note |
| PUT / DELETE | `/api/themes/<id>/notes/<note>` | modifier / supprimer une note |
| POST | `/api/themes/<id>/decisions` | proposer une décision |
| PUT / DELETE | `/api/themes/<id>/decisions/<decision>` | statut / supprimer |
| POST | `/api/themes/<id>/decisions/<decision>/votes` | voter (anonyme) |
| POST | `/api/themes/<id>/documents` | déposer un document |
| GET | `/api/themes/<id>/documents/<doc>/fichier` | télécharger un document |
| POST | `/api/themes/<id>/curseurs` | « j'écris sur cette note » (relayé, non enregistré) |
| GET | `/api/themes/<id>/evenements` | **flux temps réel** du groupe (SSE) |

### Comptes et alertes

| Méthode | Chemin | Rôle |
|---|---|---|
| POST | `/api/comptes` | premier rattachement (prénom, poste détecté) → jeton + cookie |
| POST | `/api/connexion` | **entrer avec son identifiant personnel** → jeton + cookie |
| GET / POST | `/api/projets/<id>/invitations` | les invitations du projet / **inviter par adresse** |
| GET / POST | `/api/invitations/<jeton>` | ouvrir le lien reçu / **activer son compte** (prénom + identifiant) |
| POST | `/api/themes/<id>/decisions/<d>/scrutin` | **ouvrir le vote** (membres du groupe ou tout le projet) |
| GET / POST | `/api/votes/<jeton>` | le lien de vote : lire la question / **voter une fois** |
| GET / PUT | `/api/comptes/moi` | mon compte, mes projets, mes rôles |
| PUT | `/api/notifications` | mes alertes (projet et groupes) |
| POST | `/api/alertes/essai` | essai d'envoi de courriel |

**Un visiteur ne modifie rien** : toute route d'écriture répond `403` avec un message clair.

---

## Tests

```bash
/home/ubuntu/synergie-venv/bin/python tests/tester_synergie.py
```

60 contrôles, sans réseau : projets, membres, rôles et droits, notifications, invitations
par courriel (lien personnel, activation, identifiant unique), votes par lien (une personne,
une voix), atelier (groupes, notes et mise en forme, décisions, documents, votes anonymes,
diffusion temps réel) et équipe (comptes, discussions, pages, cadre de travail, alertes).

---

## Mise en ligne

```bash
bash deploy/installer.sh        # service systemd + nginx + HTTPS
```

Le flux temps réel a besoin de `proxy_buffering off` dans le vhost : sans cela, les
événements attendent dans un tampon et rien n'arrive. Les méthodes `PUT` et `DELETE` sont
autorisées sur `/api/` pour Synergie uniquement (voir `nginx/00-securite-alpinevibe.conf`).

Le service tourne depuis `/home/ubuntu/synergie` :

```bash
sudo systemctl restart synergie.service
sudo systemctl status synergie.service
```
