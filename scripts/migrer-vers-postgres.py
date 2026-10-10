#!/usr/bin/env python3
"""SYNERGIE — reprise des données SQLite vers PostgreSQL.

Le schéma est celui que l'application crée elle-même (`initialiser()` de chaque module) :
la reprise n'entretient donc pas un second schéma qui dériverait du premier.

    # 1. on essaie sur la base d'essai
    SYNERGIE_BASE=postgresql:///synergie_essai \\
        scripts/migrer-vers-postgres.py --depuis donnees/atelier.db

    # 2. on vérifie sans rien écrire
    SYNERGIE_BASE=postgresql:///synergie scripts/migrer-vers-postgres.py --verifier

    # 3. la vraie reprise (le fichier SQLite n'est jamais modifié)
    SYNERGIE_BASE=postgresql:///synergie scripts/migrer-vers-postgres.py

Ce que le script fait, dans l'ordre : il refuse de travailler si la cible n'est pas
PostgreSQL, compare les tables déjà présentes (et s'arrête si elles ne sont pas vides,
sauf `--vider`), recopie les lignes table par table, remet les compteurs d'identité à
jour, puis compte les lignes des deux côtés et affiche l'écart. Un écart non nul fait
sortir en erreur : la reprise ne se déclare pas réussie toute seule.
"""
from __future__ import annotations

import argparse
import sqlite3
import sys
from pathlib import Path

RACINE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RACINE))

from moteur import atelier, base, consultations, equipe, invitations, projets  # noqa: E402

MODULES = (atelier, projets, invitations, consultations, equipe)
TABLES_SYSTEME = ("sqlite_sequence",)


def lire_source(chemin: Path) -> tuple[sqlite3.Connection, list[str]]:
    """Ouvre le fichier SQLite en lecture seule et liste ses tables."""
    if not chemin.is_file():
        sys.exit(f"fichier introuvable : {chemin}")
    source = sqlite3.connect(f"file:{chemin}?mode=ro", uri=True)
    source.row_factory = sqlite3.Row
    tables = [
        ligne["name"]
        for ligne in source.execute(
            "select name from sqlite_master where type = 'table' order by name")
        if ligne["name"] not in TABLES_SYSTEME and not ligne["name"].startswith("sqlite_")
    ]
    return source, tables


def colonnes_de(source: sqlite3.Connection, table: str) -> list[str]:
    return [ligne["name"] for ligne in source.execute(f'pragma table_info("{table}")')]


def compter_source(source: sqlite3.Connection, table: str) -> int:
    return source.execute(f'select count(*) from "{table}"').fetchone()[0]


def compter_cible(table: str) -> int:
    with base.connexion() as connexion:
        ligne = connexion.execute(f'select count(*) as n from "{table}"').fetchone()
        return ligne["n"] if ligne else 0


def creer_schema() -> None:
    """Le schéma, tel que l'application le crée au démarrage."""
    for module in MODULES:
        module.initialiser()


def tables_cible() -> set[str]:
    """Les tables que l'application connaît, dans la cible."""
    with base.connexion() as connexion:
        return {
            ligne["name"]
            for ligne in connexion.execute(
                "select table_name as name from information_schema.tables"
                " where table_schema = 'public' and table_type = 'BASE TABLE'")
        }


def vider_cible(tables: list[str]) -> None:
    with base.connexion() as connexion:
        for table in tables:
            connexion.execute(f'truncate table "{table}"')
    print(f"   {len(tables)} table(s) vidée(s) dans la cible")


def recopier(source: sqlite3.Connection, table: str) -> int:
    """Recopie une table entière ; renvoie le nombre de lignes écrites."""
    colonnes = colonnes_de(source, table)
    lignes = [tuple(ligne) for ligne in source.execute(f'select * from "{table}"')]
    if not lignes:
        return 0
    marques = ", ".join("?" for _ in colonnes)
    requete = f'insert into "{table}" ({", ".join(colonnes)}) values ({marques})'
    with base.connexion() as connexion:
        connexion.executemany(requete, lignes)
    return len(lignes)


def remettre_identites() -> None:
    """Les compteurs d'identité repartent après la dernière ligne recopiée."""
    with base.connexion() as connexion:
        for table, colonne in (("journal", "id"),):
            try:
                connexion.execute(
                    "select setval(pg_get_serial_sequence(?, ?),"
                    " greatest(coalesce((select max(" + colonne + ") from " + table + "), 0), 1))",
                    (table, colonne),
                )
                print(f"   compteur d'identité de {table} remis à jour")
            except Exception as erreur:  # noqa: BLE001 - table sans identité : sans objet
                print(f"   (compteur de {table} non remis : {erreur})")


def main(argv: list[str] | None = None) -> int:
    analyseur = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    analyseur.add_argument("--depuis", type=Path, default=RACINE / "donnees" / "atelier.db",
                           help="fichier SQLite source (lecture seule)")
    analyseur.add_argument("--verifier", action="store_true",
                           help="comparer les comptes sans rien écrire")
    analyseur.add_argument("--vider", action="store_true",
                           help="vider les tables de la cible avant de recopier")
    options = analyseur.parse_args(argv)

    if not base.est_postgres():
        return int(bool(sys.exit(
            "SYNERGIE_BASE doit viser PostgreSQL, par exemple :\n"
            "    SYNERGIE_BASE=postgresql:///synergie scripts/migrer-vers-postgres.py")))

    source, tables = lire_source(options.depuis)
    print(f"source : {options.depuis} ({len(tables)} tables)")
    print(f"cible  : {base.source()}")

    if not options.verifier:
        creer_schema()
        print("   schéma créé (ou déjà en place) dans la cible")

    presentes = tables_cible()
    reprises = [table for table in tables if table in presentes]
    heritees = [table for table in tables if table not in presentes]
    if heritees:
        print("   tables héritées — l'application ne les crée plus (reprises ailleurs),"
              " elles ne sont pas recopiées :")
        for table in heritees:
            print(f"      {table:<20} {compter_source(source, table):>7} ligne(s) conservées"
                  f" dans le fichier SQLite")
    tables = reprises

    restes = {table: compter_cible(table) for table in tables}
    if not options.verifier and any(restes.values()):
        remplies = {t: n for t, n in restes.items() if n}
        if not options.vider:
            source.close()
            return int(bool(sys.exit(
                f"la cible contient déjà des données ({remplies}) — utilisez --vider si c'est voulu")))
        vider_cible(tables)

    ecarts = {}
    if not options.verifier:
        for table in tables:
            nombre = recopier(source, table)
            if nombre:
                print(f"   {table:<20} {nombre} ligne(s)")
        remettre_identites()

    print("\n— contrôle des comptes —")
    for table in tables:
        attendu = compter_source(source, table)
        obtenu = compter_cible(table)
        etat = "ok" if attendu == obtenu else "ÉCART"
        if attendu != obtenu:
            ecarts[table] = (attendu, obtenu)
        print(f"   {table:<20} {attendu:>7} → {obtenu:>7}   {etat}")
    source.close()

    if ecarts:
        print(f"\nÉCHEC : {len(ecarts)} table(s) ne correspondent pas : {ecarts}", file=sys.stderr)
        return 1
    print(f"\nCONFORME : {len(tables)} tables recopiées à l'identique.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
