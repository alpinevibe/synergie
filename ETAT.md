# Synergie — état du projet

**Repensé le 05/10/2026 : le cœur de Synergie n'est plus le planning, c'est le travail
collaboratif.** Le générateur de trames devient un outil parmi d'autres, rangé dans un thème.

## Ce qui existe et fonctionne

### L'atelier collaboratif (le cœur)
- **Thèmes de réflexion** : création, description, carte d'accueil avec compteurs
  (notes, décisions dont adoptées, documents) et dernier mouvement.
- **Tableau blanc sans limites** : notes écrites, déplacées, redimensionnées, mise en forme
  complète (taille, gras, italique, souligné, alignement, 6 couleurs de texte, 6 fonds),
  déplacement du fond, zoom (Ctrl + molette), rangement automatique en colonnes, repérage
  par mot.
- **Temps réel** (SSE) : tout ce qui se passe arrive chez les autres immédiatement — notes,
  mise en forme, déplacements, décisions, documents, **présence** (qui est en ligne) et
  **curseur d'écriture** (qui écrit sur quelle note).
- **Documents de travail** : dépôt multiple, mot d'accompagnement, téléchargement (toujours
  en pièce jointe, jamais affiché dans le navigateur).
- **Décisions** : proposées par une personne, adoptées / rejetées / en attente par une
  autre, avec auteur et date conservés.

### Le suivi du travail commun
- **Prénom demandé à l'ouverture** : rien ne se fait sans savoir qui agit.
- **Journal du thème** : qui a fait quoi, et quand (note écrite ou modifiée, décision
  proposée ou tranchée, document déposé, vote). Mis à jour en direct.
- **Votes anonymes sur les décisions** : POUR / CONTRE / NEUTRE, **une seule fois par
  personne**. Le nom n'est jamais enregistré — seul un calcul permet au serveur de
  reconnaître « cette personne a déjà voté » ; le journal note « un vote a été déposé »,
  jamais par qui. Chacun voit le décompte et sait s'il a déjà voté.
- **Post-its faciles à manier** : on les déplace en les tirant **n'importe où** (plus de
  petit point à viser) ; un **crayon** apparaît au survol pour modifier le texte, et le
  double-appui écrit directement. Le texte redevient inerte quand on a fini.

### Les outils (rangés dans un thème)
- **Boîte à trames — repensée, sur une seule page** (`boite-trame.html`) : on décrit la
  profession (AS, IDE…), l'effectif (temps plein, 80 %, fixes de nuit, dispensés de nuit)
  et les postes (libellé, début, fin, nombre de personnes, jours couverts) ; l'outil
  calcule les **heures hebdomadaires** et les **ETP nécessaires** (avec le coefficient de
  remplacement habituel dans la FPH, expliqué), les compare aux ETP disponibles, puis
  propose **jusqu'à 3 trames**, chacune vérifiée par un **contrôleur de réglementation**
  (amplitude ≤ 10 h, repos quotidien ≥ 11 h, 2 jours de repos par semaine dont un dimanche
  sur deux, 48 h maximum sur une semaine, 6 jours d'affilée au maximum, 5 nuits d'affilée,
  pause dès 6 h) avec ses **compteurs**. Le dépassement des 35 h par semaine n'est pas un
  manquement : dans la FPH il se compense sur l'année, et l'outil calcule le nombre de
  **jours de réduction** à prévoir. Seules les règles **collectives** sont prises en
  compte, aucune règle individuelle.
- **Avis et synthèse** : recueil des souhaits, résultat d'ensemble (`outils.html`).

### Technique
- Base **SQLite** (`donnees/atelier.db`, mode WAL) : plusieurs personnes écrivent en même
  temps ; un JSON se corromprait.
- Diffusion par **SSE** : aucune bibliothèque supplémentaire, Flask suffit.
- `proxy_buffering off` dans le vhost nginx (sinon le flux attend dans un tampon).
- `PUT`/`DELETE` autorisés **pour Synergie seulement** sur `/api/` (réglage de sécurité
  `nginx/00-securite-alpinevibe.conf`, étendu aux API par hôte).

## Tests

```bash
/home/ubuntu/synergie-venv/bin/python tests/tester_synergie.py
```
**53 contrôles, tous conformes** (dont 10 sur l'atelier : notes et mise en forme, décisions,
documents, diffusion et présence).

Vérifications en navigateur (Playwright, sur le site en ligne, avec deux participants) :
- notes et textes transmis en direct, mise en forme reçue à l'identique (taille, gras, fond),
- document déposé par l'un, vu et téléchargeable par l'autre,
- décision proposée par l'un, adoptée par l'autre avec son nom,
- présence affichée des deux côtés.

## En ligne

<https://synergie.alpinevibe.fr/> — service `synergie`, nginx + HTTPS.

## Pistes pour la suite

- **Historique** : revenir en arrière sur une note ou retrouver une version.
- **Zones et fils** : regrouper les notes par groupe (idées / questions / décisions).
- **Modèles de thème** : partir d'une trame de tableau pré-remplie.
- **Comptes** : aujourd'hui le nom est déclaré librement ; un compte nominatif (comme dans
  Flash et Check'up) rendrait la traçabilité des décisions plus solide.
- **Frise de décisions** : voir l'enchaînement des décisions dans le temps.
- **Images dans les notes** : coller une capture directement sur le tableau.

## Journal

- **05/10/2026 (soir)** — Prénom demandé à l'ouverture et **journal des actions** ; **votes
  anonymes** (une fois par personne) sur les décisions ; post-its déplaçables d'un simple
  glissement et modifiables au crayon ; **boîte à trames repensée** : une seule page, par
  profession, calcul des ETP avec le coefficient de remplacement FPH, 3 trames proposées et
  **contrôleur de réglementation** avec compteurs.
- **05/10/2026** — Synergie repensé : atelier collaboratif (thèmes, tableau blanc sans
  limites, documents, décisions) avec travail en direct à plusieurs ; le générateur de
  trames devient un outil du thème. Base SQLite, diffusion SSE, 53 tests conformes.
- **04/10/2026** — Premier jet : moteur générique de trames, boîte à trames, avis,
  synthèse, interface en quatre écrans, mise en ligne.
