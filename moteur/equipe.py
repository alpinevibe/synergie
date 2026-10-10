"""SYNERGIE — l'équipe : comptes, discussions, pages de travail, cadre général et alertes.

Ce module rassemble tout ce qui fait vivre l'équipe autour des thèmes :

  • les COMPTES : chacun crée son compte (prénom + courriel) ; il est enregistré dans la
    base du serveur, et un jeton gardé par le navigateur permet de retrouver son compte ;
  • les DISCUSSIONS : un chat général (sur tout le projet) et un chat par thème ;
  • les PAGES : des pages blanches avec un traitement de texte simple, par thème ;
  • le CADRE DE TRAVAIL : le contexte du projet en quelques phrases, et les comptes rendus
    de réunion déposés au même endroit ;
  • les RESPONSABLES d'un thème : ce sont eux qui reçoivent une ALERTE PAR COURRIEL quand
    leur thème change, et chacun peut régler ses notifications.

Les courriels partent par `msmtp` (déjà installé sur le serveur, configuré pour la boîte
contact@alpinevibe.fr). Les alertes sont regroupées : au plus une par thème toutes les
dix minutes, pour ne pas noyer les boîtes aux lettres.
"""
from __future__ import annotations

import json
import os
import re
import queue
import subprocess
import threading
import time

from .atelier import (DONNEES, _identifiant, connexion, diffuser, journaliser, maintenant)

CONFIG_MAIL = "/srv/bases/config/mail.conf"
CONFIG_MSMTP = "/srv/bases/config/synergie-msmtp.conf"
VALEUR_COFFRE = "/srv/coffre/valeur.sh"          # lecture des secrets (jamais affichés)
JOURNAL_MAIL = str(DONNEES / "journal-alertes.log")
DELAI_ENTRE_ALERTES = 600          # 10 minutes entre deux alertes pour le même thème

SCHEMA = """
create table if not exists comptes (
    id text primary key, prenom text not null, email text default '',
    poste text default '', appareil text default '', derniere_connexion text default '',
    identifiant text, identifiant_min text,
    jeton text unique, notifier_tout integer default 0, cree_le text, maj_le text);
create table if not exists responsables (
    theme text not null, compte text not null, cree_le text,
    primary key (theme, compte));
create table if not exists abonnements (
    theme text not null, compte text not null, cree_le text,
    primary key (theme, compte));
create table if not exists messages (
    id text primary key, theme text default '', qui text default '', texte text not null,
    cree_le text not null);
create index if not exists messages_theme on messages (theme, cree_le);
create table if not exists pages (
    id text primary key, theme text not null, titre text not null, contenu text default '',
    auteur text default '', cree_le text, maj_le text);
create index if not exists pages_theme on pages (theme);
create table if not exists cadre (
    id text primary key, contexte text default '', maj_le text, maj_par text default '');
"""


def initialiser() -> None:
    """Crée les tables de l'équipe (sans toucher au reste)."""
    with connexion() as base:
        base.executescript(SCHEMA)
        # Colonnes ajoutées le 08/10/2026 : le poste de travail et la dernière connexion.
        colonnes = {l[1] for l in base.execute("pragma table_info(comptes)")}
        for nom, definition in (("poste", "text default ''"),
                                ("appareil", "text default ''"),
                                ("derniere_connexion", "text default ''"),
                                ("identifiant", "text"),
                                ("identifiant_min", "text")):
            if nom not in colonnes:
                base.execute(f"alter table comptes add column {nom} {definition}")
        base.execute("insert or ignore into cadre (id, contexte, maj_le, maj_par)"
                     " values ('general', '', ?, '')", (maintenant(),))


# ====================================================================================
# Comptes
# ====================================================================================
def _compte_public(ligne) -> dict:
    compte = dict(ligne)
    compte.pop("jeton", None)
    compte["notifier_tout"] = bool(compte.get("notifier_tout"))
    return compte


def creer_compte(prenom: str, email: str = "", poste: str = "", appareil: str = "",
                 jeton: str | None = None) -> dict:
    """Crée (ou retrouve) le compte de quelqu'un, et rend son jeton personnel.

    On ne demande que le PRÉNOM (consigne du 08/10/2026) : le courriel n'est demandé que
    plus tard, si la personne veut recevoir des alertes. On garde aussi le POSTE d'où la
    personne se connecte (navigateur, appareil) pour savoir qui agit d'où — un navigateur
    ne peut pas lire l'identifiant de session Windows, on enregistre donc ce qu'il expose.

    Le jeton est le « trousseau » gardé par le navigateur ; il n'est jamais montré.
    """
    prenom = (prenom or "").strip()
    email = (email or "").strip().lower()
    poste = (poste or "").strip()[:120]
    appareil = (appareil or "").strip()[:300]
    if not prenom:
        raise ValueError("Le prénom est obligatoire.")
    moment = maintenant()
    with connexion() as base:
        ligne = None
        if jeton:
            ligne = base.execute("select * from comptes where jeton = ?", (jeton,)).fetchone()
        if not ligne and email:
            ligne = base.execute("select * from comptes where email = ?", (email,)).fetchone()
        if not ligne and poste:
            # Même poste, même prénom : c'est la même personne qui revient.
            ligne = base.execute("select * from comptes where prenom = ? and poste = ?",
                                 (prenom, poste)).fetchone()
        # PAS de repli par le prénom : sans cela, n'importe qui pourrait se faire passer
        # pour quelqu'un d'autre en tapant son prénom (constat du 08/10/2026).
        if ligne:
            base.execute(
                "update comptes set prenom = ?, email = ?, poste = ?, appareil = ?, jeton = ?,"
                " maj_le = ?, derniere_connexion = ? where id = ?",
                (prenom, email or ligne["email"], poste or ligne["poste"],
                 appareil or ligne["appareil"],
                 jeton or ligne["jeton"] or _identifiant("jt"), moment, moment, ligne["id"]))
            identifiant = ligne["id"]
        else:
            identifiant = _identifiant("cp")
            base.execute("insert into comptes (id, prenom, email, poste, appareil, jeton,"
                         " notifier_tout, cree_le, maj_le, derniere_connexion)"
                         " values (?, ?, ?, ?, ?, ?, 0, ?, ?, ?)",
                         (identifiant, prenom, email, poste, appareil,
                          jeton or _identifiant("jt"), moment, moment, moment))
        resultat = dict(base.execute("select * from comptes where id = ?",
                                     (identifiant,)).fetchone())
    return {"compte": _compte_public(resultat), "jeton": resultat["jeton"]}


IDENTIFIANT_MINIMUM = 6


def identifiant_valide(identifiant: str) -> bool:
    return bool(re.fullmatch(r"[A-Za-z0-9._-]{6,60}", (identifiant or "").strip()))


def definir_identifiant(compte_id: str, identifiant: str) -> dict:
    """Pose (ou change) l'identifiant personnel d'un compte. Il doit être unique."""
    propre = (identifiant or "").strip()
    if not identifiant_valide(propre):
        raise ValueError("L'identifiant doit faire au moins "
                         f"{IDENTIFIANT_MINIMUM} caractères (lettres, chiffres, . _ -).")
    with connexion() as base:
        autre = base.execute("select id from comptes where identifiant_min = ? and id <> ?",
                             (propre.lower(), compte_id)).fetchone()
        if autre:
            raise ValueError("Cet identifiant est déjà utilisé : entrez avec lui, "
                             "ou choisissez-en un autre.")
        base.execute("update comptes set identifiant = ?, identifiant_min = ?, maj_le = ?"
                     " where id = ?", (propre, propre.lower(), maintenant(), compte_id))
    return lire_compte(identifiant=compte_id)


def entrer_avec_identifiant(identifiant: str) -> dict | None:
    """Retrouve le compte correspondant à un identifiant personnel (connexion)."""
    propre = (identifiant or "").strip().lower()
    if not propre:
        return None
    with connexion() as base:
        ligne = base.execute("select * from comptes where identifiant_min = ?",
                             (propre,)).fetchone()
        if ligne:
            base.execute("update comptes set derniere_connexion = ?, maj_le = ? where id = ?",
                         (maintenant(), maintenant(), ligne["id"]))
    return _compte_public(ligne) if ligne else None


def oublier_jeton(compte_id: str) -> None:
    """Rend inutilisable le jeton gardé par le navigateur (déconnexion).

    On en donne un NOUVEAU plutôt que de le vider : la colonne est unique, deux comptes ne
    peuvent pas partager la même valeur — et l'ancien jeton cesse aussitôt de valoir.
    """
    with connexion() as base:
        base.execute("update comptes set jeton = ?, maj_le = ? where id = ?",
                     (_identifiant("jt"), maintenant(), compte_id))


def jeton_de(compte_id: str) -> str:
    with connexion() as base:
        ligne = base.execute("select jeton from comptes where id = ?", (compte_id,)).fetchone()
    return ligne["jeton"] if ligne else ""


def adresse_site() -> str:
    """L'adresse publique de Synergie (pour les liens envoyés par courriel)."""
    return os.environ.get("SYNERGIE_ADRESSE", "https://synergie.alpinevibe.fr")


def envoyer_courriel(destinataire: str, sujet: str, corps: str) -> bool:
    """Met un courriel dans la file d'envoi : c'est le facteur qui l'envoie, en fond."""
    if not (destinataire or "").strip():
        return False
    _FILE.put((destinataire.strip(), sujet, corps))
    return True


def lire_compte(jeton: str | None = None, identifiant: str | None = None) -> dict | None:
    if not jeton and not identifiant:
        return None
    with connexion() as base:
        ligne = (base.execute("select * from comptes where jeton = ?", (jeton,)).fetchone()
                 if jeton else
                 base.execute("select * from comptes where id = ?", (identifiant,)).fetchone())
    return _compte_public(ligne) if ligne else None


def lister_comptes() -> list[dict]:
    with connexion() as base:
        lignes = base.execute("select * from comptes order by lower(prenom)").fetchall()
    return [_compte_public(l) for l in lignes]


def maj_compte(identifiant: str, champs: dict) -> dict | None:
    # L'identifiant personnel se pose à part : il est unique et vérifié.
    if "identifiant" in champs:
        nouveau = (champs.pop("identifiant") or "").strip()
        if nouveau and nouveau != (lire_compte(identifiant=identifiant) or {}).get("identifiant"):
            definir_identifiant(identifiant, nouveau)
    autorises = ("prenom", "email", "poste")
    valeurs = {c: champs[c] for c in autorises if c in champs}
    if not valeurs:
        return lire_compte(identifiant=identifiant)
    if "email" in valeurs:
        valeurs["email"] = (valeurs["email"] or "").strip().lower()
    if "notifier_tout" in valeurs:
        valeurs["notifier_tout"] = 1 if valeurs["notifier_tout"] else 0
    valeurs["maj_le"] = maintenant()
    colonnes = ", ".join(f"{c} = :{c}" for c in valeurs)
    valeurs["id"] = identifiant
    with connexion() as base:
        base.execute(f"update comptes set {colonnes} where id = :id", valeurs)
    return lire_compte(identifiant=identifiant)


def trouver_par_prenom(prenom: str) -> dict | None:
    with connexion() as base:
        ligne = base.execute("select * from comptes where lower(prenom) = lower(?) limit 1",
                             ((prenom or "").strip(),)).fetchone()
    return _compte_public(ligne) if ligne else None


# Les « responsables » et « abonnements » du 05/10/2026 sont remplacés par les RÔLES et
# les notifications portées par les projets et les groupes (moteur/projets.py, 08/10/2026).


# ====================================================================================
# Discussions (chat général et chat par thème)
# ====================================================================================
def lister_messages(theme: str = "", limite: int = 200) -> list[dict]:
    with connexion() as base:
        lignes = base.execute(
            "select * from messages where theme = ? order by cree_le desc, id desc limit ?",
            (theme or "", limite)).fetchall()
    return [dict(l) for l in reversed(lignes)]


def envoyer_message(theme: str, qui: str, texte: str) -> dict:
    texte = (texte or "").strip()
    if not texte:
        raise ValueError("Le message est vide.")
    message = {"id": _identifiant("ms"), "theme": theme or "", "qui": qui or "Anonyme",
               "texte": texte[:4000], "cree_le": maintenant()}
    with connexion() as base:
        base.execute("insert into messages (id, theme, qui, texte, cree_le)"
                     " values (:id, :theme, :qui, :texte, :cree_le)", message)
    diffuser(theme or "", {"type": "message", "message": message})
    return message


def supprimer_message(theme: str, message_id: str, qui: str = "") -> bool:
    """Retire un message du fil (modération). Le journal garde la trace du retrait."""
    with connexion() as base:
        ligne = base.execute("select qui from messages where id = ? and theme = ?",
                             (message_id, theme or "")).fetchone()
        if not ligne:
            return False
        base.execute("delete from messages where id = ? and theme = ?",
                     (message_id, theme or ""))
    diffuser(theme or "", {"type": "message_supprime", "id": message_id})
    journaliser(theme or "", qui or "Anonyme", "message_supprime", message_id,
                f"message de {ligne['qui'] or 'quelqu\'un'}")
    return True


# ====================================================================================
# Pages blanches (traitement de texte simple)
# ====================================================================================
def lister_pages(theme: str) -> list[dict]:
    with connexion() as base:
        lignes = base.execute(
            "select id, theme, titre, auteur, cree_le, maj_le from pages where theme = ?"
            " order by maj_le desc", (theme,)).fetchall()
    return [dict(l) for l in lignes]


def lire_page(theme: str, page_id: str) -> dict | None:
    with connexion() as base:
        ligne = base.execute("select * from pages where id = ? and theme = ?",
                             (page_id, theme)).fetchone()
    return dict(ligne) if ligne else None


def creer_page(theme: str, titre: str, contenu: str = "", auteur: str = "") -> dict:
    moment = maintenant()
    page = {"id": _identifiant("pg"), "theme": theme,
            "titre": (titre or "Page sans titre").strip(), "contenu": contenu or "",
            "auteur": auteur or "", "cree_le": moment, "maj_le": moment}
    with connexion() as base:
        base.execute("insert into pages (id, theme, titre, contenu, auteur, cree_le, maj_le)"
                     " values (:id, :theme, :titre, :contenu, :auteur, :cree_le, :maj_le)",
                     page)
    journaliser(theme, auteur or "Anonyme", "page_creee", page["id"], page["titre"])
    diffuser(theme, {"type": "page_creee", "page": _page_sans_contenu(page)})
    return page


def _page_sans_contenu(page: dict) -> dict:
    return {c: v for c, v in page.items() if c != "contenu"}


def maj_page(theme: str, page_id: str, champs: dict, qui: str = "") -> dict | None:
    autorises = ("titre", "contenu")
    valeurs = {c: champs[c] for c in autorises if c in champs}
    if not valeurs:
        return lire_page(theme, page_id)
    valeurs["maj_le"] = maintenant()
    colonnes = ", ".join(f"{c} = :{c}" for c in valeurs)
    valeurs.update({"id": page_id, "theme": theme})
    with connexion() as base:
        base.execute(f"update pages set {colonnes} where id = :id and theme = :theme", valeurs)
    page = lire_page(theme, page_id)
    if not page:
        return None
    if "titre" in champs:
        journaliser(theme, qui or "Anonyme", "page_renommee", page_id, page["titre"])
    else:
        journaliser(theme, qui or "Anonyme", "page_modifiee", page_id, page["titre"], silence=60)
    # On diffuse la page ENTIÈRE : les autres navigateurs doivent voir le texte arriver.
    diffuser(theme, {"type": "page_maj", "page": page})
    return page


def supprimer_page(theme: str, page_id: str, qui: str = "") -> None:
    with connexion() as base:
        base.execute("delete from pages where id = ? and theme = ?", (page_id, theme))
    journaliser(theme, qui or "Anonyme", "page_supprimee", page_id)
    diffuser(theme, {"type": "page_supprimee", "id": page_id})


# ====================================================================================
# Cadre de travail (contexte du projet)
# ====================================================================================
def lire_cadre(projet: str = "") -> dict:
    """Le cadre de travail — un par PROJET (identifié par l'identifiant du projet)."""
    identifiant = projet or "general"
    with connexion() as base:
        ligne = base.execute("select * from cadre where id = ?", (identifiant,)).fetchone()
    return dict(ligne) if ligne else {"id": identifiant, "contexte": "", "maj_le": None,
                                      "maj_par": ""}


def maj_cadre(contexte: str, qui: str = "", projet: str = "") -> dict:
    identifiant = projet or "general"
    moment = maintenant()
    with connexion() as base:
        base.execute("insert or ignore into cadre (id, contexte, maj_le, maj_par)"
                     " values (?, '', ?, '')", (identifiant, moment))
        base.execute("update cadre set contexte = ?, maj_le = ?, maj_par = ? where id = ?",
                     (contexte or "", moment, qui or "Anonyme", identifiant))
    cadre = lire_cadre(projet)
    journaliser("", qui or "Anonyme", "cadre_modifie", "general", "")
    diffuser("", {"type": "cadre", "cadre": cadre})
    return cadre


# ====================================================================================
# Alertes par courriel
# ====================================================================================
_FILE = queue.Queue()
_DERNIERE = {}
_VERROU = threading.Lock()


def _config_mail() -> dict | None:
    """Lit la configuration d'envoi déjà utilisée par le serveur (une seule boîte à régler)."""
    try:
        with open(CONFIG_MAIL, encoding="utf-8") as fichier:
            valeurs = {}
            for ligne in fichier:
                ligne = ligne.strip()
                if not ligne or ligne.startswith("#") or "=" not in ligne:
                    continue
                cle, valeur = ligne.split("=", 1)
                valeurs[cle.strip()] = valeur.strip()
        return valeurs
    except OSError:
        return None


def _mot_de_passe_du_coffre() -> str:
    """Le mot de passe SMTP, lu dans le coffre à secrets — jamais affiché ni recopié.

    Il n'est PAS dans mail.conf : msmtp le demande au coffre à chaque connexion
    (« passwordeval »), donc aucun mot de passe n'existe en clair sur le disque.
    """
    try:
        resultat = subprocess.run([VALEUR_COFFRE, "smtp_mot_de_passe"],
                                  capture_output=True, timeout=30)
    except (OSError, subprocess.TimeoutExpired):
        return ""
    if resultat.returncode != 0:
        return ""
    return resultat.stdout.decode().strip()


def _ecrire_config_msmtp(config: dict) -> str:
    """Fabrique la configuration msmtp de Synergie à partir de celle du serveur."""
    mode = config.get("SMTP_TLS", "starttls")
    authentification = "on" if _mot_de_passe_du_coffre() else "off"
    lignes = ["defaults", f"auth {authentification}",
              f"tls {'off' if mode == 'off' else 'on'}",
              "tls_starttls " + ("off" if mode in ("off", "ssl") else "on"),
              f"logfile {JOURNAL_MAIL}", "account synergie",
              f"host {config.get('SMTP_HOTE', '')}", f"port {config.get('SMTP_PORT', '587')}",
              f"user {config.get('SMTP_UTILISATEUR', '')}",
              f"from {config.get('EXPEDITEUR', 'contact@alpinevibe.fr')}"]
    if authentification == "on":
        # « passwordeval » : msmtp exécute la commande et prend sa sortie comme mot de
        # passe. Le secret reste au coffre (chiffré au repos) : ce fichier n'en contient
        # aucun, et le changer ne demande aucune retouche du code.
        lignes.append(f"passwordeval {VALEUR_COFFRE} smtp_mot_de_passe")
    lignes.append("account default : synergie")
    os.makedirs(os.path.dirname(CONFIG_MSMTP), exist_ok=True)
    with open(CONFIG_MSMTP, "w", encoding="utf-8") as fichier:
        fichier.write("\n".join(lignes) + "\n")
    os.chmod(CONFIG_MSMTP, 0o600)
    return CONFIG_MSMTP


def _message(destinataire: str, sujet: str, corps: str, expediteur: str) -> bytes:
    """Un courriel complet : expéditeur lisible, Date, Message-ID, sujet encodé, texte UTF-8.

    Sans ces en-têtes, les filtres anti-spam se méfient — le message part sans erreur mais
    n'arrive pas (constat du 08/10/2026 : les envois d'OVH étaient acceptés, rien dans les
    boîtes).
    """
    from email import policy
    from email.message import EmailMessage
    from email.utils import formataddr, formatdate, make_msgid

    domaine = expediteur.split("@")[-1] if "@" in expediteur else "alpinevibe.fr"
    message = EmailMessage()
    message["From"] = formataddr(("Synergie", expediteur))
    message["To"] = destinataire
    message["Subject"] = sujet
    message["Date"] = formatdate(localtime=True)
    message["Message-ID"] = make_msgid(domain=domaine)
    message["Reply-To"] = expediteur
    message["X-Mailer"] = "Synergie"
    message.set_content(corps, charset="utf-8")
    # Les fins de ligne doivent être CRLF (le protocole SMTP l'exige) : avec des « \n »
    # seuls, le message part sans erreur mais n'arrive pas (constat du 08/10/2026).
    return message.as_bytes(policy=policy.SMTP)


def envoi_actif() -> bool:
    """Les envois de courriel sont-ils ouverts ?

    Réglage « SYNERGIE_ENVOI » dans la configuration d'envoi (`mail.conf`) : « non »
    suspend TOUS les envois de Synergie (demande du 08/10/2026, le temps que la
    messagerie du CHU accepte nos messages). Rien n'est perdu : les liens personnels
    restent disponibles dans l'application (« Liens »), à transmettre à la main.
    """
    config = _config_mail() or {}
    return str(config.get("SYNERGIE_ENVOI", "oui")).strip().lower() not in (
        "non", "no", "0", "false", "off")


def _envoyer(destinataire: str, sujet: str, corps: str) -> bool:
    config = _config_mail()
    if not config or not config.get("SMTP_HOTE"):
        _noter("configuration d'envoi absente : alerte non partie")
        return False
    if not envoi_actif():
        _noter(f"envois suspendus : message pour {destinataire} non envoyé "
               "(les liens restent disponibles dans Synergie)")
        return False
    try:
        fichier = _ecrire_config_msmtp(config)
        message = _message(destinataire, sujet, corps,
                           config.get("EXPEDITEUR", "contact@alpinevibe.fr"))
        resultat = subprocess.run(["msmtp", "--file", fichier, destinataire],
                                  input=message, capture_output=True, timeout=30)
        if resultat.returncode != 0:
            _noter(f"échec d'envoi à {destinataire} : "
                   f"{resultat.stderr.decode('utf-8', 'replace')[:200]}")
            return False
        _noter(f"alerte envoyée à {destinataire}")
        return True
    except Exception as erreur:                        # pragma: no cover - dépend du réseau
        _noter(f"échec d'envoi à {destinataire} : {erreur}")
        return False


def _noter(texte: str) -> None:
    try:
        with open(JOURNAL_MAIL, "a", encoding="utf-8") as fichier:
            fichier.write(f"{maintenant()}  {texte}\n")
    except OSError:
        pass


def prevenit(theme: str, titre_theme: str, resume: str, qui: str = "",
             projet: str = "") -> list[str]:
    """Prévient les personnes qui suivent ce groupe — ou tout le projet — qu'il a changé.

    Un seul envoi par personne et par groupe toutes les dix minutes : quand plusieurs
    personnes travaillent en même temps, la boîte aux lettres ne se remplit pas.
    """
    from . import projets as m_projets
    destinataires_ = m_projets.destinataires_theme(theme, projet)
    if not destinataires_:
        return []
    adresse_site = os.environ.get("SYNERGIE_ADRESSE", "https://synergie.alpinevibe.fr")
    lien = f"{adresse_site}/#t={theme}" if theme else f"{adresse_site}/"
    sujet = f"[Synergie] {titre_theme or 'Thème'} : du nouveau"
    auteur = qui or "quelqu'un"
    corps = (f"{titre_theme or 'Un groupe de travail'} : du nouveau, par {auteur}.\n\n"
             f"{resume}\n\nOuvrir : {lien}\n\n"
             "Vous recevez ce message parce que vous suivez ce groupe — ou tout le projet. "
             "Vous pouvez régler vos notifications dans Synergie : « Mon compte », puis "
             "« Notifications ».")
    enveloppes = []
    for compte in destinataires_:
        with _VERROU:
            derniere = _DERNIERE.get((theme, compte["id"]), 0)
            if time.time() - derniere < DELAI_ENTRE_ALERTES:
                continue
            _DERNIERE[(theme, compte["id"])] = time.time()
        enveloppes.append((compte["email"], sujet, corps))
    for enveloppe in enveloppes:
        _FILE.put(enveloppe)
    return [e[0] for e in enveloppes]


def _facteur():                                        # pragma: no cover - fil de fond
    while True:
        destinataire, sujet, corps = _FILE.get()
        try:
            _envoyer(destinataire, sujet, corps)
        finally:
            _FILE.task_done()


def demarrer_le_facteur() -> None:
    """Un seul fil d'envoi : les requêtes web ne doivent pas attendre le courriel."""
    fil = threading.Thread(target=_facteur, daemon=True)
    fil.start()


def test_alerte(destinataire: str) -> bool:
    """Envoie un message d'essai (sert à vérifier que les alertes partent bien)."""
    return _envoyer(destinataire, "[Synergie] essai d'alerte",
                    "Ceci est un essai : si vous recevez ce message, les alertes de Synergie "
                    "fonctionnent.")


def prevenir_arrivee(invitation: dict, compte: dict, nom_projet: str,
                     prenom: str, nom_groupe: str = "") -> list[str]:
    """Prévient les administrateurs qu'une personne vient d'utiliser son lien d'inscription.

    Demande de l'utilisateur (09/10/2026) : « active de me prévenir par mail lorsqu'un agent
    utilise son lien d'inscription et s'inscrit ». On écrit aux ADMINISTRATEURS du projet —
    même s'ils ne suivent pas les changements ordinaires — et aux personnes abonnées. Rend la
    liste des adresses prévenues (vide si personne n'a d'adresse).
    """
    from . import projets as m_projets

    projet_id = invitation.get("projet") or ""
    destinataires = list(m_projets.administrateurs_projet(projet_id))
    connus = {d["id"] for d in destinataires}
    for personne in m_projets.destinataires_projet(projet_id):
        if personne["id"] not in connus:
            destinataires.append(personne)
    if not destinataires:
        return []
    role = m_projets.LIBELLES_ROLES.get(invitation.get("role") or "membre", "Membre participant")
    sujet = f"[Synergie] {prenom} vient de rejoindre « {nom_projet} »"
    corps = (f"Bonjour,\n\n"
             f"{prenom} ({invitation.get('email', '')}) vient d'utiliser son lien d'inscription : "
             f"son accès est actif.\n\n"
             f"Rôle reçu : {role}"
             + (f"\nGroupe : {nom_groupe}" if nom_groupe else "") + "\n\n"
             f"Voir les membres et les rôles : {adresse_site()}/#p={projet_id}\n\n"
             "Vous recevez ce message parce que vous administrez ce projet dans Synergie.\n")
    for personne in destinataires:
        envoyer_courriel(personne["email"], sujet, corps)
    return [personne["email"] for personne in destinataires]
