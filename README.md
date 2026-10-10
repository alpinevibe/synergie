# Synergie

**Travailler ensemble, décider ensemble.** Synergie est un **atelier collaboratif** : un
**projet** réunit une équipe autour de **groupes de travail**. Dans chaque groupe, on écrit
ce qui nous passe par la tête sur un **tableau blanc sans limites**, on dépose ses
**documents**, on discute et on **prend des décisions** — chacun voyant les modifications des
autres **en direct**.

Deux idées gouvernent l'application :

- **plusieurs projets** peuvent vivre côte à côte (un projet = une réorganisation, un
  service, un sujet) — chacun avec **ses groupes**, **ses membres** et **ses rôles** ;
- **chaque groupe a les mêmes outils** : tableau blanc, pages, documents, décisions, journal
  — et sa **discussion**, toujours visible dans une colonne à droite. Aucun outil « réservé » :
  l'outil ne complique pas la méthode.

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
| Comment inviter quelqu'un ? | L'administrateur **crée l'invitation** et reçoit un **lien personnel à copier** (projet ou groupe) ; chaque personne a **son** lien, qui ne sert qu'une fois. |
| Comment décider, ou simplement consulter ? | Un **vote** tranche une question (oui / non) ; un **sondage** éclaire la réflexion (plusieurs questions, plusieurs types de réponses). L'administrateur du groupe **ouvre** la consultation : chaque personne reçoit un **lien personnel**, **une personne = une réponse**, et le dépouillement reste **anonyme** (barres, moyenne, nuage de mots). |
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

**Comment obtient-on un identifiant ?** Un administrateur **crée une invitation** (pour le
projet, ou **directement pour un groupe**) : Synergie affiche un **lien personnel à copier**,
que l'administrateur transmet comme il veut (courriel, message). En ouvrant le lien, la
personne choisit son **prénom** et son **identifiant**, et rejoint le projet — et le groupe,
avec le rôle prévu. Le lien ne sert qu'une fois et vaut 30 jours.

### 2. Mes projets, puis un projet

L'accueil liste les **projets dont on est membre** (tuiles : nombre de groupes, nombre de
membres, rôle). En haut de l'écran, un **sélecteur** permet de passer d'un projet à l'autre ;
« + Nouveau projet » en crée un (on en devient administrateur). Le **cadre de travail** du
projet (le contexte, en quelques phrases) est un bloc replié : tout le monde le lit d'un
coup d'œil, personne ne le subit.

### 3. Les groupes de travail

Chaque groupe est une **tuile** : titre, description, compteurs, dernier mouvement. Un clic
ouvre le groupe : **la discussion à droite** (toujours visible, comme celle du projet) et, à
gauche, **les mêmes outils pour tous** :

| Outil | Ce qu'on y fait |
|---|---|
| **Tableau blanc** | notes libres, déplaçables, redimensionnables, mises en forme (6 couleurs de texte, 6 fonds), rangement automatique en colonnes, recherche |
| **Pages** | des pages de travail avec un traitement de texte simple (comptes rendus, procédures) |
| **Documents** | les fichiers de travail, téléchargeables par tous |
| **Votes et sondages** | **un vote** = une question, oui ou non (décision collective) ; **un sondage** = plusieurs questions, avec le type de réponse qui convient : choix unique, cases à cocher, liste déroulante, échelle de 1 à 5, un mot (nuage de mots). On choisit **qui l'on consulte** (le groupe ou tout le projet), les réponses restent **anonymes**, et **ce qui vous attend s'affiche en alerte à l'ouverture du projet** : on répond d'un clic, sans courriel |

| **Journal** | qui a fait quoi, quand — **réservé aux administrateurs du groupe** |

La **discussion du groupe** occupe la **colonne de droite**, sous les yeux pendant qu'on
travaille sur le tableau ou les pages (elle n'est plus un onglet depuis le 09/10/2026) ;
**modération** : l'auteur peut retirer son message, un administrateur peut retirer n'importe
lequel (le journal garde la trace du retrait). Sur un écran étroit, elle passe simplement
sous le contenu.

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

Un **vote** est ouvert par un administrateur du groupe ; les **résultats** sont visibles par
tous **une fois la consultation close** (et à tout moment par les administrateurs).

**Une personne qui n'a pas encore répondu voit une ALERTE sur la page d'accueil du projet**
et répond d'un clic, sans courriel. Les **liens personnels** restent disponibles
(bouton « Liens ») pour transmettre à la main.

> **Les envois de courriel sont suspendus** (réglage `SYNERGIE_ENVOI=non` dans
> `/srv/bases/config/mail.conf`), le temps que les messageries professionnelles acceptent
> les messages de `contact@alpinevibe.fr` : tout passe par des **liens à copier**. Pour
> rouvrir les envois : mettre `SYNERGIE_ENVOI=oui` puis redémarrer le service.
**Seul un administrateur du projet crée des groupes** (et seul un administrateur du groupe
ouvre un vote).

### 6. Sur téléphone, et l'installation sur l'appareil (08/10/2026)

Synergie existe en **deux dispositions**, pas une seule rétrécie :

| | Ordinateur | Téléphone |
|---|---|---|
| Navigation | tout sur une page (tableau, groupes, discussion côte à côte) | **barre en bas**, à portée de pouce : Projet · Groupes · Discussion · Votes · Compte |
| Écran | plusieurs blocs visibles | **un écran = une chose** (les blocs se répartissent par onglet) |
| Tableau blanc | plateau à déplacer à la souris | **liste de notes** : on écrit au doigt, on change la couleur, on range, on supprime |

Le passage se fait **tout seul** dès qu'un téléphone est détecté (`data-vue="mobile"` sur
`body`, écoute de la largeur d'écran). On n'y perd rien : les votes et l'alerte d'accueil
sont sur l'onglet **Votes**, les documents sur **Projet**, le chat sur **Discussion**.

**Installer l'application** : Synergie se comporte comme une application (PWA —
`web/manifest.webmanifest` et `web/sw.js`). Sur téléphone, « Ajouter à l'écran d'accueil »
depuis le menu du navigateur ; sur ordinateur, le bouton **Installer** apparaît dans
l'entête (Chrome/Edge) et installe Synergie comme une fenêtre à part. En mode installé,
l'application **fonctionne même sans réseau** pour tout ce qui est déjà chargé (le service
worker ne met en cache que les fichiers de l'application, **jamais** `/api/` ni les flux).

---

## Architecture

```
serveur.py            API + interface (Flask) ; contrôle des rôles
moteur/atelier.py     groupes, notes, décisions, documents, journal, diffusion temps réel
moteur/equipe.py      comptes, discussions, pages, cadre de travail, alertes par courriel
moteur/projets.py     projets, membres, rôles, notifications
moteur/invitations.py invitations par courriel (liens personnels à usage unique)
moteur/consultations.py votes et sondages : questions, bulletins, réponses, dépouillement
moteur/base.py        la couche base : SQLite pour l'essai local, PostgreSQL en production
moteur/diffusion.py   diffusion temps réel entre ouvriers (NOTIFY PostgreSQL)
web/index.html        l'application (projets, groupes, outils)
web/synergie.js       logique de l'application et du temps réel
web/synergie.css      habillage (lisibilité, accessibilité)
donnees/documents/    fichiers déposés
scripts/migrer-v2-projets.py     migration vers les projets et les rôles (08/10/2026)
scripts/migrer-vers-postgres.py  reprise des données SQLite → PostgreSQL (10/10/2026)
```

### Où vivent les données

En production, **PostgreSQL** (base `synergie`) : plusieurs personnes écrivent **en même
temps** — l'atelier réunit une trentaine de personnes d'abord, plusieurs centaines ensuite —
et PostgreSQL gère les écritures concurrentes ligne par ligne, là où SQLite n'en accepte
qu'une à la fois. La connexion passe par la **socket locale en authentification par pair** :
aucun mot de passe à stocker, aucun port ouvert. Sauvegarde : le dump quotidien de la pile
(`dump-quotidien.sh`, 03 h 30 UTC) et la copie hors VPS.

Le **fichier SQLite** reste le moteur de l'essai local et des bancs de tests — rien à
installer pour travailler :

```bash
SYNERGIE_BASE=donnees/essai.db python3 tests/tester_synergie.py          # SQLite, local
SYNERGIE_BASE=postgresql:///synergie_essai python3 tests/tester_synergie.py   # PostgreSQL
```

`moteur/base.py` tient la différence (liaisons `?`, lignes lisibles par nom ou par position,
transactions, `pragma`) pour que le moteur de l'application écrive le **même SQL** dans les
deux cas. Le fichier d'avant la bascule (`donnees/atelier.db.avant-postgres`, 10/10/2026) est
conservé pour le retour arrière, et copié à part dans la pile de sauvegardes.

Le **temps réel** passe par `NOTIFY` PostgreSQL (`moteur/diffusion.py`) : chaque ouvrier
rediffuse chez lui ce que publient les autres, si bien que l'application peut être servie par
plusieurs processus — un navigateur attaché à l'un voit ce qu'écrit un participant passé par
l'autre (`tests/tester_diffusion.py` le vérifie). Un événement trop gros pour une
notification part en version courte « rafraîchir », et le navigateur redemande l'état.

Le service est rendu par **waitress** (pool de fils, `SYNERGIE_FILS`, 64 par défaut), et non
plus par le serveur de développement de Flask : chaque navigateur en temps réel occupe un fil,
et le serveur de développement n'en tient qu'une poignée.

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
| DELETE | `/api/projets/<id>/messages/<message>` | **retirer un message** (auteur ou administrateur) |
| DELETE | `/api/themes/<id>/messages/<message>` | **retirer un message d'un groupe** (auteur ou administrateur) |
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
| GET / POST | `/api/projets/<id>/invitations` | les invitations du projet (avec leur **lien**) / en créer une |
| GET / POST | `/api/themes/<id>/invitations` | les invitations **du groupe** / inviter directement dans le groupe |
| GET | `/api/projets/<id>/attente` | **ce qui attend la personne** (votes sans réponse) |
| GET / POST | `/api/consultations/<id>/repondre` | répondre **depuis l'application** (sans lien) |
| GET / POST | `/api/invitations/<jeton>` | ouvrir le lien reçu / **activer son compte** (prénom + identifiant) |
| GET / POST | `/api/themes/<id>/consultations` | les votes et sondages du groupe / en créer un |
| GET / PUT / DELETE | `/api/consultations/<id>` | lire (avec le dépouillement) / modifier / supprimer |
| POST | `/api/consultations/<id>/ouvrir` | **envoyer les liens** (membres du groupe, ou tout le projet) |
| POST | `/api/consultations/<id>/fermer` | clore la consultation |
| GET | `/api/consultations/<id>/resultats` | le dépouillement, question par question |
| GET / POST | `/api/votes/<jeton>` | le lien personnel : lire les questions / **répondre une fois** |
| GET / PUT | `/api/comptes/moi` | mon compte, mes projets, mes rôles |
| PUT | `/api/notifications` | mes alertes (projet et groupes) |
| POST | `/api/alertes/essai` | essai d'envoi de courriel |

**Un visiteur ne modifie rien** : toute route d'écriture répond `403` avec un message clair.

---

## Tests

```bash
# le moteur, sans réseau (SQLite par défaut : donnees/essai.db)
/home/ubuntu/synergie-venv/bin/python tests/tester_synergie.py

# le même banc, sur PostgreSQL (base d'essai dédiée)
SYNERGIE_BASE=postgresql:///synergie_essai /home/ubuntu/synergie-venv/bin/python tests/tester_synergie.py

# deux ouvriers sur la même base : la diffusion doit traverser l'un vers l'autre
SYNERGIE_BASE=postgresql:///synergie_essai /home/ubuntu/synergie-venv/bin/python tests/tester_diffusion.py

# 24 écrivains en parallèle : aucune écriture perdue
SYNERGIE_BASE=postgresql:///synergie_essai /home/ubuntu/synergie-venv/bin/python tests/tester_ecritures_simultanees.py
```

96 contrôles, sans réseau : projets, membres, rôles et droits, notifications, invitations
par courriel (lien personnel, activation, identifiant unique), votes et sondages (questions
de tous types, liens personnels, une réponse par personne, dépouillement anonyme), atelier
(groupes, notes et mise en forme, documents, diffusion temps réel) et équipe (comptes,
discussions, pages, cadre de travail, alertes).

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

## Ajouter plusieurs membres à la volée (9 octobre 2026)

Demande de l'utilisateur : « la possibilité d'ajouter plusieurs membres à la volée dans
Synergie ».

- **Au projet** — le panneau « Membres du projet » accepte désormais **plusieurs adresses d'un
  seul geste** : on les colle ou on les tape (une par ligne, ou séparées par des virgules),
  on choisit **un rôle pour toutes**, et un clic crée toutes les invitations. Un bouton
  « **Copier les N liens** » met la liste complète dans le presse-papiers, prête à transmettre.
- **Au groupe** — les personnes du projet s'affichent **à cocher** (avec « Tout cocher »), et
  le bouton annonce combien seront ajoutées : « Ajouter au groupe (4) ». Toutes rejoignent le
  groupe d'un coup, avec le même rôle. Le champ « Inviter des personnes qui ne sont pas encore
  dans le projet » accepte lui aussi **plusieurs adresses**.
- **Garantie** : l'administrateur du projet **reste administrateur de ses groupes**, même s'il
  s'y inscrit comme simple membre (auparavant, cocher tout le monde — lui compris — lui retirait
  l'administration et l'application répondait « interdit » pour le reste).

Vérifications : `python3 tests/tester_membres_a_la_volee.py` → **10 contrôles, 0 échec**
(trois adresses collées d'un coup, trois invitations vérifiées en base, bouton de copie
collective, trois personnes cochées et ajoutées au groupe d'un seul geste — dans un vrai
navigateur, essai entièrement effacé) ; `python3 tests/tester_synergie.py` → **88 tests,
0 échec**.

Version **CACHE_VERSION 3** du service worker.

## Le bouton « Fermer » reste visible (9 octobre 2026)

Une grande fenêtre (Membres, Cadre de travail, Compte, Liens) pouvait **dépasser l'écran** :
son bouton « Fermer », tout en bas, partait sous le bord et devenait introuvable.

Désormais ces fenêtres ne dépassent plus l'écran : elles défilent en interne et leur **barre
« Fermer » reste collée en bas**, toujours visible. Une **croix ✕** est aussi posée en haut de
chaque grande fenêtre, qui reste en place pendant le défilement — elle ferme la fenêtre comme
le bouton du bas.

Vérifications : `python3 tests/tester_fenetres.py` → **10 contrôles, 0 échec** (projet d'essai
de sept membres, écran d'ordinateur 1024 × 700 et écran de téléphone 390 × 740 : fenêtre
contenue dans l'écran, barre « Fermer » et croix visibles, croix qui ferme bien).

Version **CACHE_VERSION 4** du service worker.

## Invitations par courriel et alerte à l'inscription (9 octobre 2026)

Les envois de Synergie sont **ouverts** : les invitations **partent par courriel** (réglage
`SYNERGIE_ENVOI` dans `/srv/bases/config/mail.conf`). Quand les envois sont suspendus,
l'application le dit et laisse les liens à copier ; rouvrir les envois n'expédie pas
rétroactivement les invitations déjà créées — l'outil `scripts/envoyer-invitations.py` le fait
(il attend que la file d'envoi soit vide), et la fenêtre des membres offre désormais un bouton
**« Envoyer »** par invitation et un bouton **« Envoyer les N invitations »**. Chaque invitation
affiche sa date d'envoi.

Quand quelqu'un ouvre son lien personnel et **s'inscrit**, les **administrateurs du projet**
reçoivent un courriel : qui vient de rejoindre, avec quel rôle. C'est automatique et ne demande
aucun réglage.

Vérifications : `python3 tests/tester_invitations_envoi.py` → **11 contrôles, 0 échec** (envoi
d'une invitation, envoi global, boutons dans l'application, courriel à l'administrateur à
l'inscription, connexion de la personne inscrite ; adresses d'essai en `.invalid`, donc aucun
courriel réellement envoyé pendant les tests).

Version **CACHE_VERSION 5** du service worker.

## Se connecter avec son identifiant, et se déconnecter (9 octobre 2026)

L'écran « Mon compte » laisse poser son **identifiant personnel** (au moins 6 caractères). Il
est vérifié : s'il est **déjà utilisé**, l'application le dit clairement (« entrez avec lui, ou
choisissez-en un autre ») — auparavant elle répondait par une panne technique, incompréhensible.

Un bouton **« Se déconnecter »** a été ajouté au même endroit : il invalide le jeton gardé par
le navigateur et ramène à l'écran d'entrée par identifiant. C'était indispensable pour reprendre
son identifiant personnel sur un appareil où l'on s'était identifié autrement (un téléphone
partagé, par exemple).

Vérifications : `python3 tests/tester_comptes_identifiant.py` → **8 contrôles, 0 échec** (poser
son identifiant ; refus clair d'un identifiant déjà pris, sans panne ; déconnexion ; entrée de
nouveau avec l'identifiant et retour à ses projets).

Version **CACHE_VERSION 6** du service worker.

## L'entête du téléphone s'allège (9 octobre 2026)

Sur téléphone, « Mon compte » ne s'affiche plus en haut de l'écran : il est déjà dans la
**barre du bas**. L'entête ne garde que l'essentiel — la marque et le **choix du projet** ;
les personnes, l'installation et le compte vivent dans la barre du bas et les boutons de
l'écran. Sur ordinateur, rien ne change.

Vérifications : `python3 tests/tester_entete_mobile.py` → **6 contrôles, 0 échec** (téléphone :
« Mon compte » absent de l'entête, onglet « Compte » présent et fonctionnel ; ordinateur :
bouton toujours dans l'entête).

Version **CACHE_VERSION 7** du service worker.

## Les membres, comme dans un groupe de discussion (9 octobre 2026)

Le panneau « Membres » (du projet comme d'un groupe — **même affichage**) présente désormais une
**liste de personnes** : une **pastille d'initiales** colorée, le nom, l'adresse et le rôle. Plus
de case à cocher ni de menu déroulant dans la liste.

**Un appui sur une ligne** ouvre les actions : changer le rôle (**Administrateur · Membre
participant · Visiteur**, un appui suffit) ou **retirer** la personne. Un membre qui n'administre
pas voit la même liste, sans les actions. Chacun règle ses alertes par courriel lui-même, dans
« Mon compte ».

Vérifications : `python3 tests/tester_membres_affichage.py` → **10 contrôles, 0 échec** (pastilles
et rôles, aucune case à cocher, actions à l'appui, changement de rôle vraiment enregistré,
affichage identique dans un groupe, lecture seule pour un membre simple).

Version **CACHE_VERSION 8** du service worker.
