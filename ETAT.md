# Synergie — état du projet

## 9 octobre 2026 — les courriels sont rouverts : invitations et alerte d'inscription

Demandes de l'utilisateur : « réactive l'envoi des mails car ils ont été débloqués par mon
service informatique […] lance l'invitation pour les 12 rajouts » et « active de me prévenir
par mail lorsqu'un agent utilise son lien d'inscription et s'inscrit ».

- **Envois rouverts** : `SYNERGIE_ENVOI=oui` dans `/srv/bases/config/mail.conf` (fichier copié
  avant modification : `mail.conf.avant-synergie-20261009-123051`). Message d'essai expédié vers
  `pnicolas@chu-grenoble.fr` : accepté par `ssl0.ovh.net` (250, « queued »).
- **Les 12 invitations en attente ont été expédiées** (`scripts/envoyer-invitations.py`, qui
  attend que la file d'envoi soit vide) : 12 réponses `250` d'OVH, journal d'expédition dans
  `donnees/journal-alertes.log`. Chaque invitation retient désormais sa date d'envoi
  (`envoyee_le`, colonne ajoutée par migration) et l'affiche : « envoyée par courriel il y a … ».
- **Envoi depuis l'application** : deux points d'entrée nouveaux —
  `POST /api/projets/<id>/invitations/envoi` et `POST /api/themes/<id>/invitations/envoi`. La
  fenêtre des membres montre **un bouton « Envoyer » par invitation** et un bouton
  « **Envoyer les N invitations** » ; quand les envois sont suspendus, l'application le dit et
  n'affiche pas ces boutons (les liens restent à copier).
- **Alerte à l'inscription** (`moteur/equipe.py` → `prevenir_arrivee`) : quand quelqu'un ouvre
  son lien et s'inscrit, les **administrateurs du projet** (même sans abonnement aux
  changements ordinaires) et les personnes abonnées reçoivent un courriel : qui vient de
  rejoindre, avec quel rôle, et où voir les membres.
- **Contrôle de bout en bout** : `python3 tests/tester_invitations_envoi.py` → **11 contrôles,
  0 échec** (envois ouverts, envoi d'une invitation puis de toutes, boutons présents dans la
  fenêtre des membres, courriel à l'administrateur à l'activation d'un lien, connexion de la
  personne inscrite). Les adresses d'essai sont en `.invalid` : **rien ne peut partir quelque
  part** ; on lit dans le journal d'expédition la trace de la tentative.
- **Non-régression** : `tester_synergie.py` **92** (dont l'envoi par le moteur et l'alerte),
  `tester_chat_a_droite.py` **9/9**, `tester_membres_a_la_volee.py` **10/10**,
  `tester_fenetres.py` **10/10**. `CACHE_VERSION` du service worker → **5**.

## 9 octobre 2026 — le bouton « Fermer » des fenêtres reste visible

Défaut rapporté par l'utilisateur : « problème d'affichage de la fenêtre membre, je ne vois pas
le bouton fermé ».

- Une grande fenêtre (Membres, Cadre de travail, Compte, Liens) **débordait de l'écran** : sa
  barre de fermeture partait sous le bord, invisible. `web/synergie.css` la borne à `90svh` et
  la fait **défiler en interne**, avec la barre `.barre-boutons` **collée en bas** — on la voit
  sans rien chercher.
- Une **croix ✕** est ajoutée en haut de chaque grande fenêtre (`poserCroixDeFermeture`), dans
  le titre qui reste collé en haut pendant le défilement ; elle déclenche **le même bouton de
  fermeture** que celui du bas, pour un effet identique.
- **Contrôle automatisé ajouté** : `python3 tests/tester_fenetres.py` crée un projet d'essai
  avec sept membres et vérifie, dans un vrai navigateur, sur **1024 × 700 et 390 × 740**, que la
  fenêtre ne dépasse pas l'écran, que la barre « Fermer » et la croix restent visibles, et que
  la croix ferme bien la fenêtre — **10 contrôles, 0 échec**, essai effacé. Captures
  `captures/synergie-fenetre-membres-<largeur>x<hauteur>.png`.
- **Non-régression** : `tester_synergie.py` **88**, `tester_chat_a_droite.py` **9/9**,
  `tester_membres_a_la_volee.py` **10/10**. `CACHE_VERSION` du service worker → **4**.

## 9 octobre 2026 — ajouter plusieurs membres à la volée

Demande de l'utilisateur : « la possibilité d'ajouter plusieurs membres à la volée dans
Synergie ».

- **Au projet** (`web/index.html`, `web/synergie.js`) : le panneau des membres remplace le champ
  « une adresse » par une **zone de plusieurs adresses** (une par ligne, ou séparées par des
  virgules), un rôle commun et un bouton « Ajouter ces personnes ». Les invitations sont créées
  d'affilée ; celles qui sont refusées sont **nommées** dans le compte rendu, jamais tues. Un
  bouton « **Copier les N liens** » (`boutonCopierLiens`) met toute la liste dans le
  presse-papiers.
- **Au groupe** : les personnes du projet s'affichent **à cocher** (`.choix-membres`, bouton
  « Tout cocher »), le bouton indique combien seront ajoutées — « Ajouter au groupe (4) » — et
  toutes entrent d'un coup avec le même rôle. Le bloc « personnes qui ne sont pas encore dans le
  projet » accepte lui aussi plusieurs adresses.
- **Défaut corrigé** (`moteur/projets.py`) : `role_effectif` laissait le rôle de GROUPE écraser
  celui du PROJET, si bien qu'un administrateur qui se donnait un rôle de simple membre dans un
  groupe perdait l'administration de ce groupe — avec « Tout cocher », l'ajout s'arrêtait sur
  « interdit ». L'administrateur du projet administre désormais **toujours** ses groupes
  (`estAdministrateurTheme()` côté navigateur suit la même règle).
- **Défauts de ménage corrigés** (constatés en éprouvant la nouveauté) : `supprimer_theme`
  laissait derrière lui les **pages**, les **membres du groupe**, le **journal** et les
  **invitations** ; `supprimer_projet` laissait les **invitations** du projet et de ses groupes
  (liens encore valables pour un projet disparu).
- **Contrôle de bout en bout** : `python3 tests/tester_membres_a_la_volee.py` — compte, projet,
  trois membres et un groupe d'essai créés puis **effacés** : trois adresses collées d'un coup,
  trois invitations vérifiées par l'API, bouton de copie collective, trois personnes cochées
  (« Tout cocher ») et ajoutées au groupe d'un seul geste → **10 contrôles, 0 échec**.
  Captures `captures/synergie-membres-projet.png` et `synergie-membres-groupe.png`.
- **Non-régression** : `python3 tests/tester_synergie.py` → **88 tests, 0 échec** (dont quatre
  nouveaux : plusieurs membres d'un coup, administrateur jamais rétrogradé, et le ménage d'un
  groupe et d'un projet) ; `python3 tests/tester_chat_a_droite.py` → **9/9**.

## 9 octobre 2026 — la discussion du groupe passe à droite

Demande de l'utilisateur : « retire l'onglet discussion dans les groupes et mets la fenêtre de
chat sur la droite ».

- **L'onglet « Discussion » disparaît** de la barre d'onglets d'un groupe (`web/synergie.js`) :
  il ne reste que **Tableau blanc · Pages · Documents · Votes et sondages · Journal**.
- **La discussion du groupe occupe la colonne de droite**, toujours visible — la même mise en
  page que la discussion du projet (`web/index.html` : `aside.theme-chat` dans
  `.theme-grille` ; `web/synergie.css` : colonne de 340 px, collante en haut, qui défile
  seule). Sur un écran étroit (moins de 1100 px) et sur téléphone, elle repasse **sous** le
  contenu, sans jamais disparaître.
- **Défaut corrigé au passage** : un lien direct vers un groupe (`#t=…`) ouvrait le projet au
  lieu du groupe — ouvrir un projet réécrit l'adresse (`#p=…`) et effaçait le groupe visé. Le
  groupe est désormais lu **avant** l'ouverture du projet, et un lien de groupe retrouve son
  projet tout seul, même sur un navigateur neuf.
- **Contrôle de bout en bout** : `python3 tests/tester_chat_a_droite.py` crée un compte, un
  projet et un groupe d'essai, écrit un message, puis vérifie dans un **vrai navigateur**
  (1440 × 900 et 900 × 900) que l'onglet a disparu, que la discussion est **à droite** des
  onglets, qu'elle passe sous le contenu sur écran étroit et que le message s'y affiche —
  **9 contrôles, 0 échec**, puis efface l'essai. Captures
  `captures/synergie-chat-droite-<largeur>x<hauteur>.png`.
- **Non-régression** : `python3 tests/tester_synergie.py` → **83 tests, 0 échec**.
  `CACHE_VERSION` du service worker passe à **2**.

## 8 octobre 2026 (nuit) — plus tendance, et une vraie version téléphone

1. **Les couleurs de fond ont été retravaillées** : la page n'est plus d'un blanc/bleu uni
   mais d'un **fond à dégradés doux** (trois halos — bleu, vert d'eau, violet — posés sur un
   dégradé diagonal clair). Les cartes, l'entête, les tuiles de groupe et les boutons
   principaux suivent la même famille (dégradés d'accent bleu-violet-vert d'eau), avec un
   léger **effet de verre** (les cartes laissent transparaître le fond). Rien d'excessif : les
   textes gardent un contraste franc (AA), et l'ensemble reste calme.

2. **Une version téléphone pensée pour le pouce** — pas l'interface d'ordinateur réduite :
   - une **barre de navigation en bas** de l'écran (Projet · Groupes · Discussion · Votes ·
     Compte), cibles d'au moins 58 px ;
   - **un écran = une chose** : les blocs de la page se répartissent par onglet, on ne fait
     plus défiler une longue page ;
   - le **tableau blanc devient une liste de notes** : une note par carte, on écrit
     directement dedans, on change la couleur, on range, on supprime ; un bouton « Voir le
     tableau » rend le plateau vrai (68 vh) pour qui le veut ;
   - champs à `16px` (plus de zoom involontaire), onglets qui défilent latéralement, entête
     compacte qui ne déborde jamais (un entête trop large force le navigateur à dézoomer) ;
   - les outils de zoom/recentrage restent, mais seulement en mode tableau.

   Le mode s'active **tout seul** dès qu'un téléphone est détecté ; la vue d'ordinateur est
   inchangée.

3. **Application installable** (PWA) sur ordinateur **et** téléphone : `manifest.webmanifest`,
   quatre icônes (192, 512, maskable 512, 180 pour iOS), un service worker qui met en cache
   les fichiers de l'application — **jamais** `/api/` ni les flux — et un bouton **Installer**
   dans l'entête (Chrome/Edge). Sur téléphone : « Ajouter à l'écran d'accueil ».

   Vérifié au navigateur : bureau 5/5, téléphone (iPhone émulé 390×844) barre du bas, 4
   tuiles, **17 notes en liste**, écriture au doigt, section Votes — **aucune erreur JS**,
   aucun débordement horizontal. 83 tests moteur verts.

## 8 octobre 2026 — modération des discussions

- **Retirer un message non adapté** : dans les discussions (projet et groupes), l'**auteur**
  peut retirer son message et un **administrateur** peut retirer n'importe lequel — c'est la
  modération. Le retrait est **journalisé** (« untel a retiré un message de untel ») et
  diffusé en direct : le message disparaît chez tout le monde sans recharger la page.
- **Ménage** : la présence de « Camille » (jeu d'essai) a été retirée — ses messages, sa page
  et ses 79 lignes de journal — ainsi que 266 lignes de journal orphelines laissées par les
  groupes d'essai supprimés au fil des mises au point. Les quatre groupes de travail et leurs
  contenus sont intacts.

## 8 octobre 2026 (soirée) — liens à copier, alerte d'accueil, envois suspendus

1. **Les envois de courriel sont SUSPENDUS** (`SYNERGIE_ENVOI=non` dans
   `/srv/bases/config/mail.conf`) : nos messages partent bien (Laposte les reçoit) mais la
   messagerie du CHU les bloque. Rien n'est perdu : tout passe par des **liens à copier**.
   Le domaine est authentifié (SPF, DKIM `ovhmo-selector-1/-2`, DMARC `p=none`) ; il reste
   à obtenir l'accord du CHU ou à passer par un service d'envoi dédié.
2. **ALERTE sur la page d'accueil du projet** : à l'ouverture, une personne voit **ce qui
   l'attend** — les votes et sondages ouverts auxquels elle n'a pas répondu — et **répond
   d'un clic**, sans courriel. L'alerte disparaît dès qu'elle a répondu.
3. **Invitations par LIEN PERSONNEL À COPIER** : pour le **projet** comme pour **un
   groupe** (avec son propre rôle dans le groupe), Synergie affiche un lien propre à chaque
   personne, à copier et à transmettre par le canal de son choix. Le lien ne sert qu'une
   fois, vaut 30 jours, et l'activation inscrit la personne au projet **et** au groupe.

Tests : **80 contrôles verts**. Vérifié au navigateur : alerte d'accueil, réponse sans
courriel, création des liens d'invitation (projet et groupe), activation d'une invitation de
groupe (projet + rôle de groupe).

## 8 octobre 2026 (fin de journée) — votes et sondages, et une panne réparée

1. **La panne d'abord.** Le service laissait fuir une **connexion à la base par appel** :
   au bout de quelques heures, 509 connexions restaient ouvertes et la limite système
   (« Too many open files ») bloquait tout — d'où « la création d'une note ne marche plus »
   et « la suppression d'une décision ne marche pas ». Chaque connexion est maintenant
   **refermée** à la sortie (les quatre moteurs), la limite de descripteurs du service est
   relevée, et les deux gestes remarchent.
2. **Les décisions deviennent « Votes et sondages ».** Dans un groupe, on crée :
   - un **VOTE** : UNE question, réponse **oui / non** — une prise de décision collective ;
   - un **SONDAGE** : PLUSIEURS questions, avec le type de réponse qui convient — **choix
     unique**, **cases à cocher**, **liste déroulante**, **échelle de 1 à 5**, **un mot**
     (nuage de mots) : une consultation collective pour aider le groupe à réfléchir.
   On choisit **qui l'on consulte** (les membres du groupe, ou tout le projet) ; chaque
   personne reçoit un **lien personnel par courriel** : **une personne, une réponse**, et le
   dépouillement reste **anonyme** (barres, moyenne, nuage de mots).
3. Au passage : supprimer un groupe ou un projet emporte désormais **tout** son contenu
   (consultations, questions, réponses, bulletins), et le compte-rendu de l'onglet affiche
   des compteurs sans mélanger les unités.

Tests : **72 contrôles verts**. Vérifié dans un vrai navigateur : création d'un sondage
(échelle + nuage), réponse par lien personnel, dépouillement (moyenne 4/5, nuage « clair »).

## 8 octobre 2026 (après-midi) — identité, invitations, votes et confort d'usage

Sept améliorations demandées par le cadre, appliquées le jour même :

1. **Annuler** sur le tableau blanc (bouton ↶ et Ctrl + Z) : création, suppression, texte,
   déplacement, redimensionnement, couleurs et mise en forme ; la touche annule aussi dans
   les pages de travail.
2. **Ranger** range désormais les post-it **en colonnes par couleur** (une teinte par
   colonne, l'ordre de la palette décide).
3. **Suppression des post-it** : les boutons d'une note (✏️ et ×) sont **toujours visibles**
   et larges — sur un écran tactile, un bouton qui n'apparaît qu'au survol était introuvable.
4. **Invitations par courriel et identifiant personnel** : l'administrateur invite par
   **adresse** ; la personne reçoit un **lien personnel**, y choisit son **prénom** et son
   **identifiant**, puis entre **avec cet identifiant seulement**. Le repli par prénom est
   supprimé (on ne peut plus se faire passer pour quelqu'un). Le **journal d'un groupe** est
   réservé à ses **administrateurs** ; les membres du projet écrivent dans la discussion du
   projet et visitent les groupes ; les visiteurs lisent sans modifier.
5. **Votes par lien personnel** : l'administrateur du groupe ouvre le vote « aux membres du
   groupe » ou « à tout le projet » ; chaque votant reçoit un lien par courriel, **une
   personne = une voix**, et le dépouillement reste **anonyme** (empreinte, jamais de nom).
6. **Cadre de travail** : il ne tient plus de place sur la page — il s'ouvre en cliquant le
   **nom du projet** dans l'entête, en **lecture seule**, modifiable par l'**administrateur**
   du projet.
7. **Création de groupes réservée à l'administrateur du projet** (bouton visible pour lui
   seul, et vérifié côté serveur).

Tests : **60 contrôles verts**. Vérifié dans un vrai navigateur (connexion par identifiant,
activation d'une invitation, vote par lien, journal masqué pour un membre) : aucune erreur.

## 8 octobre 2026 — Synergie devient multi-projets, et s'allège

Demandes du cadre, appliquées le jour même :

1. **Plusieurs projets** : un projet rassemble des groupes de travail ; on **invite** des
   personnes par leur prénom, avec un rôle au projet (**administrateur**, **membre
   participant**, **visiteur**) et, si besoin, un rôle **différent dans chaque groupe**.
   Le rôle de groupe l'emporte ; l'administrateur du projet administre tous ses groupes.
2. **Seuls les groupes issus d'une lettre de cadrage** restent (« Rythme de travail » et
   « Fiches de poste » sont retirés) : **tous les groupes ont désormais les mêmes outils**
   (tableau blanc, pages, discussion, documents, décisions, journal).
3. **Interface repensée** : moins de texte à l'écran (aides en infobulle, blocs repliés),
   une action principale par écran, contrastes renforcés, contours de focus visibles,
   libellés associés aux champs, cibles de 40 px.
4. **Entrée par le prénom seul** : le **poste de travail** (navigateur, appareil) est
   enregistré automatiquement et modifiable ; le **courriel** n'est demandé que pour
   **activer les alertes**, projet par projet et groupe par groupe.
5. La **boîte à trames**, les **fiches de poste** et les **codes horaires** quittent
   Synergie : ils deviennent l'application **Orbis** (`alpinevibe/orbis`), dont le moteur et
   les données ont été extraits le même jour.

Migration : `scripts/migrer-v2-projets.py` (projet « Projet horaires diversifiés HTC
Écrins », les 4 groupes rattachés, administrateurs désignés). Tests : 45 contrôles verts.

---

**Repensé le 05/10/2026 : le cœur de Synergie n'est plus le planning, c'est le travail
collaboratif.** Le générateur de trames devient un outil parmi d'autres, rangé dans un thème.

## Deux thèmes toujours présents
- **Rythme de travail** (fixe, non supprimable) : s'ouvre directement sur la **boîte à
  trames**.
- **Fiches de poste** (fixe, non supprimable) : s'ouvre sur les **fiches de poste** et le
  **référentiel des codes horaires**.

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

### L'équipe (05/10/2026)
- **Comptes** : prénom + courriel, enregistrés dans la base du serveur, retrouvés par un
  jeton gardé par le navigateur.
- **Discussions** : un **chat général** et un **chat par thème**, en direct.
- **Cadre de travail** (menu général) : le **contexte** du projet en quelques phrases et les
  **comptes rendus de réunion**.
- **Pages de travail** : pages blanches avec **traitement de texte simple**, enregistrées
  automatiquement.
- **Responsables par thème** : ils reçoivent une **alerte par courriel** quand le thème
  change ; chacun **règle ses notifications** (thèmes suivis ou tout). Alertes regroupées
  (au plus une par thème toutes les 10 minutes). Envoi par msmtp — **un essai a été envoyé
  avec succès** le 05/10/2026.

### Les fiches de poste (thème « Fiches de poste »)
Organisation retenue : **1)** le vocabulaire d'abord (référentiel des **codes horaires**,
couleurs d'Hermes, installé au départ : M03, S03, J13, N02, RH, DS, FEJ, RTT) ; **2)** les
**fiches** se lisent **par tranche horaire** (libellé, code, début, fin, durée, fréquence,
qui, remarque) ; **3)** chaque fiche a un état **à l'étude → proposée → validée** (qui,
quand) ; **4)** la **charge par code** est calculée et affichée ; **5)** on **duplique** une
fiche pour créer une nouvelle version, sans perdre l'ancienne.

### Les outils (rangés dans un thème)
- **Boîte à trames — repensée, sur une seule page** (`boite-trame.html`) : on décrit la
  profession (AS, IDE…), l'effectif (temps plein, 80 %, fixes de nuit, dispensés de nuit)
  et les postes (libellé, début, fin, nombre de personnes, jours couverts) ; l'outil
  calcule les **heures hebdomadaires** et les **ETP nécessaires** (avec le coefficient de
  remplacement habituel dans la FPH, expliqué), les compare aux ETP disponibles, puis
  propose **jusqu'à 3 trames**, chacune vérifiée par un **contrôleur de réglementation**
  (amplitude ≤ 12 h — au-delà de 10 h une dérogation est signalée —, repos quotidien
  ≥ 11 h, 2 jours de repos par semaine dont un dimanche sur deux, 48 h maximum sur une
  semaine, 6 jours d'affilée au maximum, 5 nuits d'affilée, pause dès 6 h) avec ses
  **compteurs**.
- **Horaires variés** : la cible d'une personne est un nombre d'HEURES par semaine, pas un
  nombre de jours — on peut donc mêler des journées de 7 h 30 et de 12 h (cinq courtes ou
  trois longues reviennent au même), et n'importe quelle configuration est acceptée.
- **Couleurs d'Hermes** : chaque poste reçoit le code et la couleur du planning habituel
  (M03 matin jaune, S03 après-midi cyan, J13 journée longue magenta, N02 nuit violet,
  RH repos vert) ; les cases de la grille portent le code sur sa couleur, avec une légende,
  et le code de chaque poste peut être choisi dans la page. Le dépassement des 35 h par semaine n'est pas un
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

- **05/10/2026 (nuit)** — Deux thèmes fixes (Rythme de travail, Fiches de poste) ; comptes
  (prénom + courriel) en base ; chat général et chat par thème ; cadre de travail (contexte
  et comptes rendus de réunion) ; pages de travail avec traitement de texte simple ;
  responsables par thème avec alertes par courriel et réglage des notifications ; fiches de
  poste par tranche horaire avec référentiel des codes horaires, charge par code,
  duplication et validation.
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
