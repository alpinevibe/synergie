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

### Les outils (inchangés, rangés dans un thème)
- Générateur de **trames** (OR-Tools CP-SAT), **boîte à trames**, import **Hermes**,
  **avis** des professionnels, **synthèse** harmonieuse. Page dédiée : `outils.html`.

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

- **05/10/2026** — Synergie repensé : atelier collaboratif (thèmes, tableau blanc sans
  limites, documents, décisions) avec travail en direct à plusieurs ; le générateur de
  trames devient un outil du thème. Base SQLite, diffusion SSE, 53 tests conformes.
- **04/10/2026** — Premier jet : moteur générique de trames, boîte à trames, avis,
  synthèse, interface en quatre écrans, mise en ligne.
