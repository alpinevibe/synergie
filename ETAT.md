# Synergie — état du projet

**Version 0.1** · 04/10/2026 · dépôt <https://github.com/alpinevibe/synergie> ·
en ligne sur **<https://synergie.alpinevibe.fr/>**

## Ce qui est fait (premier jet)

| Brique | État |
|---|---|
| **Règles génériques** de temps de travail (extraction des règles Hermes) | ✅ `moteur/regles.py`, surchargeables par projet |
| **Générateur de trames** (OR-Tools CP-SAT) | ✅ `moteur/trames.py` — 5 × quotité jours, 1 DS/semaine à 80 %, 2 RH/semaine, week-end 1 sur 2, heures ≥ légales, cycle fixe de nuit |
| **Boîte à trames** (catalogue, mêmes critères = même code) | ✅ `moteur/boite.py` |
| **Pont Hermes Planning** (appel réel du générateur de grilles d'Hermes) | ✅ 8 trames importées (IDE/AS/ASH, dont fixes de nuit) |
| **Avis** (collecte) et **synthèse harmonieuse** (échange de poste, indice de synergie) | ✅ `moteur/avis.py` |
| **Projets génériques** (modèle, stockage, couverture recommandée) | ✅ `moteur/projet.py` |
| **Interface web** en 4 écrans | ✅ `web/` |
| **API** JSON | ✅ `serveur.py` |
| **Tests** de non-régression | ✅ `tests/tester_synergie.py` — **43/43** |
| **Déploiement** service systemd + HTTPS | ✅ `deploy/installer.sh`, certbot |

## Ce qui reste à faire (à corriger avec le cadre)

1. **Le concept en pièce jointe n'est pas arrivé** (le bot Github n'accepte que le texte et
   le vocal). Le premier jet suit la consigne écrite ; à ajuster dès réception du concept.
2. **Nuits tournantes** : aujourd'hui seuls les agents **fixes de nuit** figurent dans une
   trame (comme dans les grilles Hermes). Si Synergie doit aussi proposer le roulement de
   nuit, c'est un ajout à faire.
3. **Multi-postes par métier** : l'interface gère un poste (code) par métier ; le moteur
   accepte déjà plusieurs codes — reste à exposer dans l'écran *Le service*.
4. **Codes d'absence dans la trame** (CAJ, RTT, formation) : ils sont gérés par les **avis**
   et la synthèse, pas posés d'office dans la trame (choix d'Hermes : aucun jour hors
   travail gratuit). À confirmer selon le concept.
5. **Authentification** : l'application est publique (comme les autres applis du VPS).
   Mettre `auth-maison` si un accès restreint est souhaité.
6. **Export Excel** de la trame / du planning projeté (format Chronos) : non fait.
7. **Multi-projets / comparaison** de variantes : non fait.

## Commandes utiles

```bash
cd ~/synergie
./run.sh                                   # serveur local (port 8077)
/home/ubuntu/synergie-venv/bin/python tests/tester_synergie.py
sudo systemctl status|restart synergie
bash deploy/installer.sh                   # (re)déploie service + vhost
```

## Journal

- **04/10/2026** — premier jet complet : moteur, boîte à trames, pont Hermes, avis,
  synthèse, interface, tests (43/43), mise en ligne HTTPS.
