# Synergie

**Réorganiser un service, tous ensemble.** Synergie est une application **générique** de
réorganisation du temps de travail : elle décrit un service, génère ses **trames de
rotation** dans une *boîte à trames* réutilisable, recueille les **avis** de tous les
professionnels et rend un **résultat harmonieux** — les postes restent couverts, les
souhaits honorés quand c'est possible, les refus expliqués.

Le nom dit la méthode : un travail **collaboratif où tous les avis comptent** et forment
un résultat **harmonieux**.

---

## À quoi ça sert

| Question | Réponse de Synergie |
|---|---|
| Comment travailler à effectif constant ? | Le **générateur de trames** produit, par profil de temps de travail, une rotation de N semaines rejouée en boucle. |
| Et si un autre service veut faire pareil ? | Le modèle de projet est **générique** : rien n'est propre au soin. Un atelier, un service technique, une équipe de nuit se décrivent de la même façon. |
| Comment prendre en compte les souhaits de chacun ? | Les **avis** sont collectés, pesés (un congé annuel pèse plus qu'une récupération) et suivis jusqu'à la synthèse. |
| Comment garantir l'équité ? | Mêmes critères de temps de travail ⇒ **même trame, même code** ; la couverture est **identique chaque semaine** (aucune semaine chargée, aucune creuse). |
| Et si l'effectif ne suffit pas ? | La trame est **toujours produite** : le déficit est **signalé**, jamais masqué (suppléance à prévoir). |

---

## Démarrage

```bash
./run.sh                       # http://127.0.0.1:8077
./run.sh --port 8080 --hote 0.0.0.0
```

Tests (aucun réseau) :

```bash
/home/ubuntu/synergie-venv/bin/python tests/tester_synergie.py
```

Le projet d'exemple se crée d'un clic sur **« Exemple »** (bouton en haut à droite).

---

## Le parcours en quatre écrans

1. **Le service** — nom, collectivité, période ; métiers, postes et **couverture cible** ;
   population (quotité, nuit fixe, sans nuit). Le bouton *« Proposer la couverture »*
   répartit l'effectif en une cible cohérente (le week-end pèse moins, samedi et dimanche
   reçoivent la même cible).
2. **Boîte à trames** — le générateur produit les trames ; chacune porte un **code**
   (`TRM-<MÉTIER>-<quotité>-<n>S`) et rejoint le **catalogue**, réutilisable par un autre
   projet. Un bouton importe les trames du **générateur d'Hermes Planning**.
3. **Les avis** — chaque professionnel dépose son souhait (jour + code + motif).
4. **Résultat harmonieux** — *indice de synergie* (part des avis honorés), avis non
   honorés **avec leur raison**, contrôle des heures et **planning projeté** par agent.

---

## Les règles génériques (la « boîte à trames »)

Extraction générique des règles du moteur Hermes Planning (`data/regles_service.txt`),
surchargeables par projet (`projet.regles`) :

- **5 jours par semaine × quotité** : une semaine de week-end travaillé compte
  `arrondi(5 × quotité) + 1` jours, la suivante `− 1` (moyenne 5 × quotité) ⇒
  **heures travaillées ≥ heures légales** (35 h × quotité) ;
- **2 RH par semaine** en moyenne, et **1 DS par semaine** pour un temps partiel (jour hors
  quotité), **aucun DS** à temps plein ;
- **un week-end sur deux**, réparti entre **toutes** les lignes (samedi et dimanche
  forment une paire) ;
- **nuits tournantes** absentes d'une trame ; seuls les **agents fixes de nuit** suivent le
  cycle réglementaire de 14 jours (NN DS RH) ;
- un **avis** ne dégrade jamais la couverture : la sous-couverture coûte plus cher que la
  somme des avis (poids 10 000 contre 1 000 à 3 000) ;
- **un déficit n'empêche jamais la production** : il est signalé.

---

## Architecture

```
synergie/
├── serveur.py              API Flask + service de l'interface
├── run.sh                  lancement local
├── moteur/
│   ├── regles.py           règles génériques de temps de travail
│   ├── trames.py           générateur de trames (OR-Tools CP-SAT)
│   ├── boite.py            boîte à trames (catalogue) + pont Hermes Planning
│   ├── avis.py             collecte des avis + synthèse harmonieuse
│   └── projet.py           modèle de projet, stockage, couverture recommandée
├── web/                    interface (HTML/CSS/JS, sans dépendance)
├── donnees/                projets, boîte à trames, générations (JSON)
└── tests/tester_synergie.py
```

### Le modèle de la trame

Une trame = **N semaines** rejouées en boucle, N = **effectif du profil** (mêmes critères
de temps de travail), plafonné à 12. Chaque agent suit la trame **décalée d'une semaine** :
la couverture d'un jour de la semaine est donc toujours la même. Le moteur partage la
cible du métier entre ses profils **au prorata de leur capacité**.

---

## API

| Méthode | Route | Rôle |
|---|---|---|
| `GET` | `/api/sante` | état, disponibilité du pont Hermes |
| `GET` | `/api/regles` | règles génériques effectives |
| `GET/POST` | `/api/projets` | liste / création |
| `POST` | `/api/demo` | crée le projet d'exemple |
| `GET/PUT/DELETE` | `/api/projets/<id>` | lecture / mise à jour / suppression |
| `POST` | `/api/projets/<id>/cibles-recommandees` | couverture proposée d'après l'effectif |
| `GET/POST` | `/api/projets/<id>/trames` | lit / génère les trames |
| `POST/DELETE` | `/api/projets/<id>/avis` | ajoute / retire un avis |
| `GET` | `/api/projets/<id>/synthese` | indice de synergie, planning projeté |
| `GET` | `/api/boite` | catalogue des trames |
| `POST` | `/api/boite/importer-hermes` | importe les trames d'Hermes Planning |

---

## Lien avec Hermes Planning

Synergie **réutilise** les règles génériques d'Hermes Planning et sait **appeler son
générateur de grilles** (`engine_rotation.py`) pour importer ses trames dans la boîte
(`moteur/boite.py`). Elle en est néanmoins **indépendante** : elle fonctionne sans lui, et
sert des services qui n'ont rien de médical.

> Synergie ne remplace pas la production du **planning** d'Hermes (qui pose les nuits et
> les absences) : elle construit la **trame** et la **concertation** autour d'elle.
