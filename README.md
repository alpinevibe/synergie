# Synergie

**Travailler ensemble, décider ensemble.** Synergie est un **atelier collaboratif** : une
équipe ouvre un **thème de réflexion**, y écrit tout ce qui lui passe par la tête sur un
**tableau blanc sans limites**, y dépose ses **documents de travail**, et **prend ses
décisions** — chaque membre voyant les modifications des autres **en direct**.

Le nom dit la méthode : un travail **collaboratif où tous les avis comptent** et forment un
résultat **harmonieux**.

Le **générateur de trames** est un **outil** de cet atelier — utile, mais un outil parmi
d'autres : on y vient depuis un thème, quand le moment est venu de traduire les idées en
organisation concrète.

---

## À quoi ça sert

| Question | Réponse de Synergie |
|---|---|
| Où rassembler les idées d'une équipe sur un sujet ? | Un **thème de réflexion** : chacun écrit sur le tableau blanc, sans hiérarchie, sans ordre imposé. |
| Comment réfléchir à plusieurs, en même temps ? | Le tableau est **partagé en direct** : les notes, leurs couleurs, leurs tailles et leurs déplacements arrivent chez les autres immédiatement, et l'on voit **qui est en ligne** et **qui écrit sur quelle note**. |
| Où mettre les documents de travail ? | Dans le thème : comptes rendus, tableaux, plans, photos. Chacun les télécharge (jamais affichés dans le navigateur, par sécurité). |
| Comment savoir ce qui a été tranché ? | Les **décisions** : proposées, puis **adoptées** ou **rejetées**, avec l'auteur et la date. Les décisions adoptées se voient d'un coup d'œil. |
| Comment passer des idées à l'organisation ? | Les **outils** du thème : générateur de **trames de rotation**, **boîte à trames**, **avis** de tous les professionnels, **synthèse** harmonieuse. Un thème peut être relié à un projet. |
| Et si l'effectif ne suffit pas ? | La trame est **toujours produite** : le déficit est **signalé**, jamais masqué (suppléance à prévoir). |

---

## Démarrage

```bash
./run.sh                       # http://127.0.0.1:8077
./run.sh --port 8080 --hote 0.0.0.0
```

En ligne : <https://synergie.alpinevibe.fr/>

---

## Le parcours

### 1. Les thèmes de réflexion (l'accueil)

Chaque thème est une carte : son titre, son objet, le nombre de notes, de décisions (dont
celles adoptées) et de documents, et le moment du dernier mouvement. On ouvre un thème d'un
appui.

### 2. Le tableau blanc (dans un thème)

Une feuille **sans limites** :

- **double-clic** (ou « + Nouvelle note ») : une note naît à cet endroit ;
- on y **écrit** directement ;
- **mise en forme** : taille (A− / A+), **gras**, *italique*, souligné, alignement,
  **couleur du texte** et **couleur de fond** (six teintes pastel) ;
- on **fait glisser** la note par sa poignée, on la **redimensionne** par son coin ;
- on se **déplace** en tirant le fond, on **agrandit** avec Ctrl + molette, et le bouton
  « Ranger » remet les notes en colonnes quand le tableau devient fouillis ;
- un champ de **repérage** met en évidence les notes qui contiennent un mot.

### 3. Les documents de travail

On dépose un ou plusieurs fichiers, avec un mot pour dire à quoi ils servent. Ils sont
rangés dans `donnees/documents/<thème>/` et **toujours proposés au téléchargement**
(jamais affichés dans le navigateur : un fichier déposé ne doit pas pouvoir s'exécuter dans
l'application).

### 4. Les décisions

On propose une décision, on en discute sur le tableau, puis on la marque **adoptée**,
**rejetée** ou **en attente**. L'auteur de la proposition, l'auteur de la décision et la
date sont conservés.

### 5. Les outils (dont le générateur de trames)

Depuis le thème : le générateur de trames, la boîte à trames, les avis et la synthèse. Un
thème peut être **relié à un projet** pour que les deux se répondent.

---

## Le temps réel, comment ça marche

- chaque navigateur ouvre un flux d'événements (`/api/themes/<id>/evenements`, SSE) ;
- le serveur lui **pousse** tout ce qui se passe : note créée, modifiée, supprimée,
  déplacée, décision, document, présence ;
- la **présence** (qui est en ligne) et le **curseur d'écriture** (qui travaille sur quelle
  note) sont diffusés de la même façon ;
- l'écriture en cours est **regroupée** avant envoi (moins d'une seconde) : on ne noie ni le
  réseau ni la base.

Aucune bibliothèque n'est nécessaire : le serveur est en Flask, la diffusion se fait par
SSE, et la page écoute avec `EventSource`.

---

## Architecture

```
serveur.py            API + interface (Flask)
moteur/atelier.py     atelier collaboratif : thèmes, notes, décisions, documents, diffusion
moteur/trames.py      générateur de trames (OR-Tools CP-SAT)   ← OUTIL
moteur/boite.py       boîte à trames réutilisable              ← OUTIL
moteur/avis.py        recueil et pesée des avis                ← OUTIL
moteur/projet.py      modèle de projet générique               ← OUTIL
moteur/regles.py      règles génériques de temps de travail    ← OUTIL
web/index.html        l'atelier (thèmes, tableau blanc, documents, décisions, outils)
web/synergie.js       logique de l'atelier et du temps réel
web/synergie.css      habillage de l'atelier
web/outils.html       la page des outils (trames, boîte, avis, synthèse)
web/app.js            logique des outils
donnees/atelier.db    base SQLite (thèmes, notes, décisions, documents)
donnees/documents/    fichiers déposés
```

### Pourquoi SQLite ici ?

Plusieurs personnes écrivent **en même temps** : un fichier JSON se corromprait. SQLite en
mode WAL encaisse les écritures concurrentes sans configuration, tient dans un fichier, et
se sauvegarde comme n'importe quel fichier.

---

## API

### Atelier

| Méthode | Chemin | Rôle |
|---|---|---|
| GET / POST | `/api/themes` | lister / créer un thème |
| GET / PUT / DELETE | `/api/themes/<id>` | lire le thème complet / le modifier / le supprimer |
| POST | `/api/themes/<id>/notes` | créer une note |
| PUT / DELETE | `/api/themes/<id>/notes/<note>` | modifier / supprimer une note |
| POST | `/api/themes/<id>/decisions` | proposer une décision |
| PUT / DELETE | `/api/themes/<id>/decisions/<decision>` | statut (adoptée, rejetée, en attente) / supprimer |
| POST | `/api/themes/<id>/documents` | déposer un document |
| GET | `/api/themes/<id>/documents/<doc>/fichier` | télécharger un document |
| DELETE | `/api/themes/<id>/documents/<doc>` | supprimer un document |
| POST | `/api/themes/<id>/curseurs` | « j'écris sur cette note » (relayé) |
| GET | `/api/themes/<id>/evenements` | **flux temps réel** (SSE) |

### Outils

| Méthode | Chemin | Rôle |
|---|---|---|
| GET | `/api/sante` | état du service |
| GET / POST | `/api/projets` | lister / créer un projet |
| GET / PUT / DELETE | `/api/projets/<id>` | lire / modifier / supprimer un projet |
| POST | `/api/projets/<id>/cibles-recommandees` | couverture conseillée d'après l'effectif |
| GET / POST | `/api/projets/<id>/trames` | lire / générer les trames |
| POST / DELETE | `/api/projets/<id>/avis` | ajouter / retirer un avis |
| GET | `/api/projets/<id>/synthese` | synthèse harmonieuse |
| GET | `/api/boite` · POST `/api/boite/importer-hermes` | boîte à trames |

---

## Tests

```bash
/home/ubuntu/synergie-venv/bin/python tests/tester_synergie.py
```

53 contrôles : règles génériques, moteur de trames, généricité, avis, boîte à trames, et
l'atelier (thèmes, notes et leur mise en forme, décisions, documents, diffusion temps réel).

---

## Mise en ligne

```bash
bash deploy/installer.sh        # service systemd + nginx + HTTPS
```

Le flux temps réel a besoin de `proxy_buffering off` dans le vhost : sans cela, les
événements attendent dans un tampon et rien n'arrive. Les méthodes `PUT` et `DELETE` sont
autorisées sur `/api/` pour Synergie uniquement (voir `nginx/00-securite-alpinevibe.conf`).
