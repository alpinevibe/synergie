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
import queue
import subprocess
import threading
import time

from .atelier import (DONNEES, _identifiant, connexion, diffuser, journaliser, maintenant)

CONFIG_MAIL = "/srv/bases/config/mail.conf"
CONFIG_MSMTP = "/srv/bases/config/synergie-msmtp.conf"
JOURNAL_MAIL = str(DONNEES / "journal-alertes.log")
DELAI_ENTRE_ALERTES = 600          # 10 minutes entre deux alertes pour le même thème

SCHEMA = """
create table if not exists comptes (
    id text primary key, prenom text not null, email text default '',
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


def creer_compte(prenom: str, email: str = "", notifier_tout: bool = False,
                 jeton: str | None = None) -> dict:
    """Crée (ou retrouve) le compte de quelqu'un, et rend son jeton personnel.

    Un même courriel ne crée pas deux comptes : on retrouve le sien. Le jeton est le
    « trousseau » gardé par le navigateur ; il n'est jamais montré à l'écran.
    """
    prenom = (prenom or "").strip()
    email = (email or "").strip().lower()
    if not prenom:
        raise ValueError("Le prénom est obligatoire.")
    moment = maintenant()
    with connexion() as base:
        ligne = None
        if email:
            ligne = base.execute("select * from comptes where email = ?", (email,)).fetchone()
        if not ligne and jeton:
            ligne = base.execute("select * from comptes where jeton = ?", (jeton,)).fetchone()
        if not ligne:
            ligne = base.execute("select * from comptes where prenom = ? and email = ''",
                                 (prenom,)).fetchone() if not email else None
        if ligne:
            base.execute("update comptes set prenom = ?, email = ?, jeton = ?, maj_le = ?,"
                         " notifier_tout = ? where id = ?",
                         (prenom, email or ligne["email"], jeton or ligne["jeton"] or _identifiant("jt"),
                          moment, 1 if notifier_tout else ligne["notifier_tout"], ligne["id"]))
            identifiant = ligne["id"]
        else:
            identifiant = _identifiant("cp")
            base.execute("insert into comptes (id, prenom, email, jeton, notifier_tout,"
                         " cree_le, maj_le) values (?, ?, ?, ?, ?, ?, ?)",
                         (identifiant, prenom, email, jeton or _identifiant("jt"),
                          1 if notifier_tout else 0, moment, moment))
        resultat = dict(base.execute("select * from comptes where id = ?",
                                     (identifiant,)).fetchone())
    return {"compte": _compte_public(resultat), "jeton": resultat["jeton"]}


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
        lignes = base.execute("select * from comptes order by prenom collate nocase").fetchall()
    return [_compte_public(l) for l in lignes]


def maj_compte(identifiant: str, champs: dict) -> dict | None:
    autorises = ("prenom", "email", "notifier_tout")
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
        ligne = base.execute("select * from comptes where prenom = ? collate nocase limit 1",
                             ((prenom or "").strip(),)).fetchone()
    return _compte_public(ligne) if ligne else None


# ====================================================================================
# Responsables d'un thème et abonnements
# ====================================================================================
def responsables(theme: str) -> list[dict]:
    with connexion() as base:
        lignes = base.execute(
            "select c.* from responsables r join comptes c on c.id = r.compte"
            " where r.theme = ? order by c.prenom collate nocase", (theme,)).fetchall()
    return [_compte_public(l) for l in lignes]


def definir_responsables(theme: str, comptes: list[str], qui: str = "") -> list[dict]:
    """Remplace la liste des responsables d'un thème (ce sont eux qui reçoivent les alertes)."""
    with connexion() as base:
        base.execute("delete from responsables where theme = ?", (theme,))
        for identifiant in comptes or []:
            base.execute("insert or ignore into responsables (theme, compte, cree_le)"
                         " values (?, ?, ?)", (theme, identifiant, maintenant()))
    journaliser(theme, qui or "Anonyme", "responsables", theme,
                f"{len(comptes or [])} responsable(s)")
    resultat = responsables(theme)
    diffuser(theme, {"type": "responsables", "responsables": resultat})
    return resultat


def abonnes_du_theme(theme: str) -> list[dict]:
    with connexion() as base:
        lignes = base.execute(
            "select c.* from abonnements a join comptes c on c.id = a.compte"
            " where a.theme = ?", (theme,)).fetchall()
    return [_compte_public(l) for l in lignes]


def abonner(theme: str, compte: str, actif: bool = True) -> None:
    with connexion() as base:
        if actif:
            base.execute("insert or ignore into abonnements (theme, compte, cree_le)"
                         " values (?, ?, ?)", (theme, compte, maintenant()))
        else:
            base.execute("delete from abonnements where theme = ? and compte = ?",
                         (theme, compte))


def abonnements_du_compte(compte: str) -> list[str]:
    with connexion() as base:
        return [l["theme"] for l in base.execute(
            "select theme from abonnements where compte = ?", (compte,)).fetchall()]


def destinataires(theme: str) -> list[dict]:
    """Qui doit être prévenu quand ce thème change : ses responsables, plus ceux qui ont
    demandé à suivre tous les thèmes. Chaque compte n'apparaît qu'une fois, et seulement
    s'il a une adresse de courriel."""
    vus, liste = set(), []
    for compte in responsables(theme) + abonnes_du_theme(theme):
        if compte["id"] in vus:
            continue
        vus.add(compte["id"])
        if compte.get("email"):
            liste.append(compte)
    with connexion() as base:
        lignes = base.execute("select * from comptes where notifier_tout = 1").fetchall()
    for ligne in lignes:
        compte = _compte_public(ligne)
        if compte["id"] in vus or not compte.get("email"):
            continue
        vus.add(compte["id"])
        liste.append(compte)
    return liste


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


def supprimer_message(theme: str, message_id: str) -> None:
    with connexion() as base:
        base.execute("delete from messages where id = ? and theme = ?",
                     (message_id, theme or ""))
    diffuser(theme or "", {"type": "message_supprime", "id": message_id})


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
def lire_cadre() -> dict:
    with connexion() as base:
        ligne = base.execute("select * from cadre where id = 'general'").fetchone()
    return dict(ligne) if ligne else {"id": "general", "contexte": "", "maj_le": None,
                                      "maj_par": ""}


def maj_cadre(contexte: str, qui: str = "") -> dict:
    moment = maintenant()
    with connexion() as base:
        base.execute("update cadre set contexte = ?, maj_le = ?, maj_par = ? where id = 'general'",
                     (contexte or "", moment, qui or "Anonyme"))
    cadre = lire_cadre()
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


def _ecrire_config_msmtp(config: dict) -> str:
    """Fabrique la configuration msmtp de Synergie à partir de celle du serveur."""
    mode = config.get("SMTP_TLS", "starttls")
    authentification = "on" if config.get("SMTP_MOTDEPASSE") else "off"
    lignes = ["defaults", f"auth {authentification}",
              f"tls {'off' if mode == 'off' else 'on'}",
              "tls_starttls " + ("off" if mode in ("off", "ssl") else "on"),
              f"logfile {JOURNAL_MAIL}", "account synergie",
              f"host {config.get('SMTP_HOTE', '')}", f"port {config.get('SMTP_PORT', '587')}",
              f"user {config.get('SMTP_UTILISATEUR', '')}",
              f"from {config.get('EXPEDITEUR', 'contact@alpinevibe.fr')}"]
    if authentification == "on":
        lignes.append(f"password {config.get('SMTP_MOTDEPASSE')}")
    lignes.append("account default : synergie")
    os.makedirs(os.path.dirname(CONFIG_MSMTP), exist_ok=True)
    with open(CONFIG_MSMTP, "w", encoding="utf-8") as fichier:
        fichier.write("\n".join(lignes) + "\n")
    os.chmod(CONFIG_MSMTP, 0o600)
    return CONFIG_MSMTP


def _envoyer(destinataire: str, sujet: str, corps: str) -> bool:
    config = _config_mail()
    if not config or not config.get("SMTP_HOTE"):
        _noter("configuration d'envoi absente : alerte non partie")
        return False
    try:
        fichier = _ecrire_config_msmtp(config)
        message = (f"To: {destinataire}\nFrom: {config.get('EXPEDITEUR', 'contact@alpinevibe.fr')}\n"
                   f"Subject: {sujet}\nContent-Type: text/plain; charset=utf-8\n\n{corps}\n")
        resultat = subprocess.run(["msmtp", "--file", fichier, destinataire],
                                  input=message.encode("utf-8"), capture_output=True,
                                  timeout=30)
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


def prevenit(theme: str, titre_theme: str, resume: str, qui: str = "") -> list[str]:
    """Prévient les responsables du thème (et les abonnés) qu'il vient de changer.

    Les alertes sont REGROUPÉES : une seule par thème toutes les dix minutes, pour ne pas
    remplir les boîtes aux lettres quand plusieurs personnes travaillent en même temps.
    """
    destinataires_ = destinataires(theme)
    if not destinataires_:
        return []
    adresse_site = os.environ.get("SYNERGIE_ADRESSE", "https://synergie.alpinevibe.fr")
    lien = f"{adresse_site}/#t={theme}" if theme else f"{adresse_site}/"
    sujet = f"[Synergie] {titre_theme or 'Thème'} : du nouveau"
    auteur = qui or "quelqu'un"
    corps = (f"{titre_theme or 'Un thème'} vient d'être modifié par {auteur}.\n\n"
             f"{resume}\n\nOuvrir : {lien}\n\n"
             "Vous recevez ce message parce que vous êtes responsable de ce thème ou que "
             "vous avez demandé à suivre les nouveautés. Vous pouvez régler vos "
             "notifications dans Synergie, onglet « Mon compte ».")
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
