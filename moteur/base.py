#!/usr/bin/env python3
"""SYNERGIE — la couche base de données, la même pour SQLite et pour PostgreSQL.

Le code du moteur écrit du SQL simple (des `?`, des `insert`, des `select`) et ne sait
pas sur quel moteur il tourne. C'est ici que la différence se règle :

  • **SQLite** (par défaut, `donnees/atelier.db`) — un fichier, aucun service à
    administrer : pratique pour l'essai local et pour les bancs de tests ;
  • **PostgreSQL** (`SYNERGIE_BASE=postgresql:///synergie`) — ce que la production
    utilise : plusieurs personnes qui écrivent **en même temps**, plusieurs ouvriers
    applicatifs, des transactions par ligne, des sauvegardes à chaud.

Ce que la couche traduit, et rien de plus :

  • les `?` de SQLite deviennent les `%s` de psycopg (le `%` d'un motif `like` est
    doublé, sinon psycopg le prendrait pour un gabarit) ;
  • `pragma table_info(x)` devient une lecture de `information_schema` — les modules
    s'en servent pour ajouter une colonne manquante, le résultat doit rester le même ;
  • les `PRAGMA` (mode WAL, clés étrangères) n'ont pas d'équivalent : ils sont ignorés ;
  • `insert or ignore` devient `insert ... on conflict do nothing` ;
  • `integer primary key autoincrement` (la table `journal`) devient une colonne
    d'identité PostgreSQL.

Ce que la couche garantit : la connexion est **refermée** à la sortie (l'incident du
08/10/2026 : 509 descripteurs ouverts, « Too many open files »), la transaction est
validée si tout s'est bien passé, annulée sinon. En PostgreSQL, les connexions viennent
d'un **pool** : ouvrir une connexion par requête épuiserait les 100 connexions du
serveur, et un pool réutilise un petit nombre de connexions entre les fils.
"""
from __future__ import annotations

import atexit
import os
import re
import sqlite3
import threading
from contextlib import contextmanager
from pathlib import Path

RACINE = Path(__file__).resolve().parent.parent
DONNEES = RACINE / "donnees"
#: Le fichier utilisé quand rien n'est configuré : un bac à sable d'essai, jamais les
#: données de production (celles-ci vivent dans PostgreSQL — voir `SYNERGIE_BASE`).
BASE_DEFAUT = DONNEES / "essai.db"
PREFIXES_POSTGRES = ("postgres://", "postgresql://")

#: Ce processus, pour que la diffusion temps réel ne se réentende pas lui-même.
PROCESSUS = f"{os.getpid()}-{os.urandom(3).hex()}"


class ErreurPortabilite(RuntimeError):
    """Une requête écrite pour SQLite n'a pas d'équivalent direct en PostgreSQL.

    Mieux vaut le dire clairement que laisser PostgreSQL répondre « collation inconnue » :
    le message doit indiquer quoi écrire à la place.
    """

_pool = None  # rempli au premier usage PostgreSQL
_verrou_pool = threading.Lock()

#: Les erreurs d'intégrité de chaque moteur (clé déjà prise, contrainte violée…), pour
#: que le moteur puisse écrire `except base.ERREUR_INTEGRITE` quel que soit le moteur.
ERREUR_INTEGRITE = (sqlite3.IntegrityError,)
#: Les erreurs de base en général (moteur absent, requête invalide…).
ERREUR_BASE = (sqlite3.Error,)
try:  # psycopg n'est là que si les données sont dans PostgreSQL
    import psycopg as _psycopg

    ERREUR_INTEGRITE += (_psycopg.errors.IntegrityError,)
    ERREUR_BASE += (_psycopg.Error,)
except Exception:  # noqa: BLE001 - psycopg absent : SQLite seul, sans conséquence
    pass


# ------------------------------------------------------------------ configuration
def source() -> str:
    """Où sont les données : un fichier SQLite, ou une base PostgreSQL."""
    return os.environ.get("SYNERGIE_BASE") or str(BASE_DEFAUT)


def est_postgres() -> bool:
    """Vrai si la configuration vise PostgreSQL (sinon SQLite)."""
    return source().startswith(PREFIXES_POSTGRES)


def nom_moteur() -> str:
    """« postgresql » ou « sqlite » : ce que les pages et les journaux affichent."""
    return "postgresql" if est_postgres() else "sqlite"


# ---------------------------------------------------------------------- les lignes
class Ligne:
    """Une ligne de résultat, lisible par nom (`ligne["titre"]`) **ou** par position (`ligne[1]`).

    `sqlite3.Row` faisait les deux ; les lignes de psycopg ne se lisent que par nom. Le
    moteur existant utilise les deux écritures : cette classe évite de réécrire 156 requêtes.
    """

    __slots__ = ("_valeurs", "_colonnes", "_index")

    def __init__(self, valeurs, colonnes) -> None:
        self._valeurs = tuple(valeurs)
        self._colonnes = tuple(colonnes)
        self._index = {nom: rang for rang, nom in enumerate(self._colonnes)}

    def __getitem__(self, cle):
        if isinstance(cle, int):
            return self._valeurs[cle]
        return self._valeurs[self._index[cle]]

    def __iter__(self):
        return iter(self._valeurs)

    def __len__(self) -> int:
        return len(self._valeurs)

    def __contains__(self, cle) -> bool:
        return cle in self._index

    def keys(self) -> list[str]:
        return list(self._colonnes)

    def get(self, cle, defaut=None):
        return self._valeurs[self._index[cle]] if cle in self._index else defaut

    def __repr__(self) -> str:  # pragma: no cover - confort de débogage
        return f"Ligne({dict(zip(self._colonnes, self._valeurs))!r})"


# ------------------------------------------------------------------------ traduction
_PRAGMA_TABLE = re.compile(r"^\s*pragma\s+table_info\s*\(\s*([A-Za-z_][\w]*)\s*\)\s*$", re.I)
_PRAGMA = re.compile(r"^\s*pragma\b", re.I)
_NOM = re.compile(r":([A-Za-z_]\w*)")
_AUTOINCREMENT = re.compile(r"integer\s+primary\s+key\s+autoincrement", re.I)
_INSERT_OR_IGNORE = re.compile(r"^\s*insert\s+or\s+ignore\s+into\b", re.I)


def _table_info(nom: str) -> str:
    """`pragma table_info(x)` en PostgreSQL : mêmes colonnes, même ordre qu'en SQLite."""
    return (
        "select ordinal_position - 1 as cid, column_name as name, data_type as type, "
        "case when is_nullable = 'NO' then 1 else 0 end as notnull, "
        "column_default as dflt_value, "
        "case when column_name in ("
        "  select kcu.column_name from information_schema.key_column_usage kcu "
        "  join information_schema.table_constraints tc "
        "    on tc.constraint_name = kcu.constraint_name and tc.table_schema = kcu.table_schema "
        "  where tc.table_name = '{nom}' and tc.constraint_type = 'PRIMARY KEY') "
        "then 1 else 0 end as pk "
        "from information_schema.columns where table_name = '{nom}' "
        "order by ordinal_position"
    ).format(nom=nom.replace("'", "''"))


def _lier(sql: str) -> str:
    """`?` → `%s`, `:nom` → `%(nom)s`, et `%` → `%%`, hors chaînes littérales.

    SQLite accepte les deux écritures de liaison — positionnelle (`?`) et nommée
    (`:nom`, liée à un dictionnaire). psycopg n'accepte que `%s` et `%(nom)s`, et
    réserve le pour cent : d'où les trois conversions, faites en une seule passe pour
    ne pas retoucher ce qui vient d'être écrit.
    """
    sortie, dans_chaine, i = [], False, 0
    while i < len(sql):
        caractere = sql[i]
        if caractere == "'":
            if dans_chaine and sql[i : i + 2] == "''":
                sortie.append("''")
                i += 2
                continue
            dans_chaine = not dans_chaine
            sortie.append(caractere)
        elif dans_chaine:
            sortie.append(caractere)
        elif caractere == "%":
            sortie.append("%%")  # y compris dans une chaîne : psycopg formate toute la requête
        elif caractere == "?":
            sortie.append("%s")
        elif caractere == ":":
            if sql[i : i + 2] == "::":  # transtypage PostgreSQL (::text), à laisser tel quel
                sortie.append("::")
                i += 2
                continue
            nom = _NOM.match(sql, i)
            if nom:
                sortie.append(f"%({nom.group(1)})s")
                i = nom.end()
                continue
            sortie.append(caractere)
        else:
            sortie.append(caractere)
        i += 1
    return "".join(sortie)


def traduire(sql: str) -> str | None:
    """Traduit une requête écrite pour SQLite vers PostgreSQL (`None` = à ignorer)."""
    if not est_postgres():
        return sql
    table = _PRAGMA_TABLE.match(sql)
    if table:
        return _table_info(table.group(1))
    if _PRAGMA.match(sql):  # mode WAL, clés étrangères : sans objet ici
        return None
    texte = sql
    if re.search(r"\bcollate\s+nocase\b", texte, re.I):
        raise ErreurPortabilite(
            "« collate nocase » n'existe pas en PostgreSQL : écrire lower(...) dans la "
            f"requête, qui reste identique dans les deux moteurs — {texte.strip()[:120]}"
        )
    if _INSERT_OR_IGNORE.match(texte):
        texte = _INSERT_OR_IGNORE.sub("insert into", texte, count=1).rstrip()
        if not texte.endswith(";"):
            texte += " on conflict do nothing"
        else:
            texte = texte[:-1].rstrip() + " on conflict do nothing;"
    texte = _AUTOINCREMENT.sub("bigint generated by default as identity primary key", texte)
    return _lier(texte)


def decouper(script: str) -> list[str]:
    """Sépare un script SQL en instructions (le `;` d'une chaîne ne compte pas)."""
    instructions, courante, dans_chaine, i = [], [], False, 0
    while i < len(script):
        caractere = script[i]
        if dans_chaine:
            courante.append(caractere)
            if caractere == "'":
                if script[i : i + 2] == "''":
                    courante.append("'")
                    i += 2
                    continue
                dans_chaine = False
        elif caractere == "'":
            dans_chaine = True
            courante.append(caractere)
        elif script[i : i + 2] == "--":  # commentaire jusqu'à la fin de la ligne
            fin = script.find("\n", i)
            i = len(script) if fin == -1 else fin
            continue
        elif caractere == ";":
            texte = "".join(courante).strip()
            if texte:
                instructions.append(texte)
            courante = []
        else:
            courante.append(caractere)
        i += 1
    texte = "".join(courante).strip()
    if texte:
        instructions.append(texte)
    return instructions


# --------------------------------------------------------------------- les connexions
class Resultat:
    """Le curseur, avec des lignes que l'on peut lire par nom ou par position."""

    def __init__(self, curseur) -> None:
        self._curseur = curseur
        self._colonnes = None

    def _preparer(self, brut):
        if brut is None:
            return None
        if self._colonnes is None:
            self._colonnes = [d[0] for d in (self._curseur.description or [])]
        return Ligne(brut, self._colonnes)

    def fetchone(self):
        return self._preparer(self._curseur.fetchone())

    def fetchall(self) -> list:
        return [self._preparer(ligne) for ligne in self._curseur.fetchall()]

    def fetchmany(self, taille: int = 1) -> list:
        return [self._preparer(ligne) for ligne in self._curseur.fetchmany(taille)]

    def __iter__(self):
        for ligne in self._curseur:
            yield self._preparer(ligne)

    @property
    def rowcount(self) -> int:
        return self._curseur.rowcount

    @property
    def lastrowid(self):
        return getattr(self._curseur, "lastrowid", None)


def _connexion_postgres() -> "ConnexionPostgres":
    """Une connexion PostgreSQL, prise dans le pool.

    Le pool se crée **une seule fois**, sous verrou : sans cela, cent cinquante connexions
    qui arrivent en même temps (le service de flux) en créaient plusieurs, et une connexion
    prise dans l'un ne pouvait plus être rendue à l'autre — « can't return connection to
    pool », constaté le 10/10/2026 sous charge.
    """
    global _pool
    if _pool is None:
        with _verrou_pool:
            if _pool is None:
                from psycopg_pool import ConnectionPool

                _pool = ConnectionPool(
                    os.environ.get("SYNERGIE_BASE", ""),
                    min_size=1,
                    max_size=int(os.environ.get("SYNERGIE_CONNEXIONS", "12")),
                    timeout=15,
                    max_idle=300,
                    kwargs={"autocommit": False},
                    # Une connexion rendue au pool est vérifiée avant d'être réutilisée :
                    # sans cela, un redémarrage de PostgreSQL laissait l'application avec des
                    # connexions mortes (« the connection is lost »), jusqu'à son redémarrage
                    # à elle — constaté le 10/10/2026, avec une fausse alerte à la clé.
                    check=ConnectionPool.check_connection,
                    name="synergie",
                )
    pool = _pool
    return ConnexionPostgres(pool.getconn(), pool)


class ConnexionPostgres:
    """Une connexion PostgreSQL qui se lit comme une connexion SQLite."""

    def __init__(self, brute, pool=None) -> None:
        self._brute = brute
        self._pool = pool

    def execute(self, sql: str, parametres=()) -> Resultat:
        requete = traduire(sql)
        if requete is None:  # PRAGMA : rien à faire
            return Resultat(_CurseurVide())
        curseur = self._brute.cursor()
        if parametres:
            # Un dictionnaire (paramètres nommés) est passé tel quel, une suite devient un tuple.
            curseur.execute(requete, parametres if isinstance(parametres, dict) else tuple(parametres))
        else:
            curseur.execute(requete)
        return Resultat(curseur)

    def executemany(self, sql: str, lignes) -> Resultat:
        requete = traduire(sql)
        if requete is None:
            return Resultat(_CurseurVide())
        lignes = list(lignes)
        if not lignes:
            return Resultat(_CurseurVide())
        prevoir = lignes if isinstance(lignes[0], dict) else [tuple(ligne) for ligne in lignes]
        curseur = self._brute.cursor()
        curseur.executemany(requete, prevoir)
        return Resultat(curseur)

    def executescript(self, script: str) -> None:
        """Le `executescript` de sqlite3 : plusieurs instructions d'un coup."""
        for instruction in decouper(script):
            self.execute(instruction)

    def commit(self) -> None:
        self._brute.commit()

    def rollback(self) -> None:
        self._brute.rollback()

    def close(self) -> None:
        """Remet la connexion au pool **d'où elle vient** (le pool la réinitialise)."""
        try:
            self._brute.rollback()
        except Exception:  # noqa: BLE001 - connexion déjà fermée : sans importance
            pass
        if self._pool is not None:
            self._pool.putconn(self._brute)
        else:
            self._brute.close()


class _CurseurVide:
    """Ce que renvoie une instruction ignorée (un PRAGMA) : rien, sans erreur."""

    description = None
    rowcount = 0
    lastrowid = None

    def fetchone(self):
        return None

    def fetchall(self):
        return []

    def fetchmany(self, taille: int = 1):
        return []

    def __iter__(self):
        return iter(())


@contextmanager
def connexion():
    """Une connexion, REFERMÉE à la sortie, avec la même sémantique dans les deux moteurs.

    Sans la fermeture explicite, chaque appel laissait un descripteur ouvert : le
    service a fini par en avoir 509 et saturer la limite système (« Too many open
    files », constat du 08/10/2026).
    """
    if est_postgres():
        base = _connexion_postgres()
        try:
            yield base
            base.commit()
        except Exception:
            base.rollback()
            raise
        finally:
            base.close()
        return

    DONNEES.mkdir(parents=True, exist_ok=True)
    base = sqlite3.connect(source(), timeout=15)
    base.row_factory = lambda curseur, ligne: Ligne(ligne, [d[0] for d in curseur.description])
    try:
        base.execute("PRAGMA journal_mode=WAL")
        base.execute("PRAGMA foreign_keys=ON")
        yield base
        base.commit()
    except Exception:
        base.rollback()
        raise
    finally:
        base.close()


def fermer_pool() -> None:
    """Ferme le pool PostgreSQL (arrêt propre, bancs de tests)."""
    global _pool
    if _pool is not None:
        try:
            _pool.close()
        except Exception:  # noqa: BLE001 - à l'arrêt, une erreur ne doit rien empêcher
            pass
        _pool = None


CLE_INSTALLATION = 7_251_001  # un numéro bien à nous : le verrou d'installation du schéma


@contextmanager
def verrou_installation():
    """Sérialise la création du schéma entre processus (PostgreSQL seulement).

    Deux ouvriers qui démarrent en même temps créaient le schéma et nettoyaient les
    mêmes tables ensemble : PostgreSQL a détecté un interblocage (« deadlock detected »),
    constaté le 10/10/2026 en lançant deux serveurs sur la même base. Le verrou est pris
    sur une connexion à part, et **rendu** explicitement à la sortie.
    """
    if not est_postgres():
        yield
        return
    import psycopg

    connexion_verrou = psycopg.connect(source(), autocommit=True)
    try:
        connexion_verrou.execute("select pg_advisory_lock(%s)", (CLE_INSTALLATION,))
        yield
    finally:
        try:
            connexion_verrou.execute("select pg_advisory_unlock(%s)", (CLE_INSTALLATION,))
        finally:
            connexion_verrou.close()


#: Sans cela, l'interpréteur se plaint à l'arrêt : le thread du pool est joint trop tard.
atexit.register(fermer_pool)
