"""SYNERGIE — les fiches de poste, travaillées par tranche horaire et par code horaire.

Comment on travaille ici (l'organisation retenue, demandée le 05/10/2026) :

  1. D'ABORD LE VOCABULAIRE. On se met d'accord sur les CODES HORAIRES de la profession :
     ce que veut dire M03, S03, J13, N02…, à quelles heures, et à quoi cela correspond dans
     la journée. Le référentiel est partagé : c'est la base de tout le reste, et il reprend
     les couleurs du planning habituel (Hermes).
  2. ENSUITE LES FICHES. Une fiche de poste se lit PAR TRANCHE HORAIRE : pour chaque code
     horaire, quelles tâches sont prévues, combien de temps, à quelle fréquence, et par qui.
     Autrement dit une « fiche de tâches », pas un texte général.
  3. ON VALIDE. Chaque fiche a un état : à l'étude, proposée, validée (avec qui et quand).
     Une fiche ne se valide pas toute seule : elle passe par la discussion du thème.
  4. ON MESURE. Pour chaque code horaire, l'outil additionne les durées des tâches et
     affiche la charge : on voit tout de suite si une tranche est surchargée ou creuse, et
     si les tâches tiennent dans le temps de présence.
  5. ON PART DE L'EXISTANT. On duplique une fiche pour en créer une nouvelle version sans
     perdre l'ancienne.

Ce module ne fait que les données ; l'affichage est dans la page du thème.
"""
from __future__ import annotations

from .atelier import _identifiant, connexion, diffuser, journaliser, maintenant
from .boite_trame import CODES_HERMES

STATUTS = ("a_l_etude", "proposee", "validee")
LIBELLES_STATUTS = {"a_l_etude": "à l'étude", "proposee": "proposée", "validee": "validée"}

SCHEMA = """
create table if not exists codes_horaires (
    id text primary key, theme text not null, code text not null, libelle text default '',
    debut text default '', fin text default '', couleur text default '',
    definition text default '', ordre integer default 0, cree_le text, maj_le text,
    unique (theme, code));
create table if not exists fiches (
    id text primary key, theme text not null, profession text default '',
    intitule text default '', finalite text default '', statut text default 'a_l_etude',
    version integer default 1, validee_par text default '', validee_le text,
    auteur text default '', cree_le text, maj_le text);
create table if not exists fiche_taches (
    id text primary key, fiche text not null, ordre integer default 0, libelle text default '',
    code text default '', debut text default '', fin text default '',
    duree_min integer default 0, periodicite text default '', qui text default '',
    remarque text default '');
create index if not exists fiches_theme on fiches (theme);
create index if not exists taches_fiche on fiche_taches (fiche, ordre);
"""

# Les codes proposés au départ : ceux du planning habituel (couleurs d'Hermes).
CODES_DEPART = [
    ("M03", "Matin", "06:30", "14:00", "Le matin : soins, transmissions, tournées."),
    ("S03", "Après-midi", "13:30", "21:00", "L'après-midi : soins, entrées, transmissions."),
    ("J13", "Journée longue", "07:30", "19:30", "Journée de 12 h : recouvrement des équipes."),
    ("N02", "Nuit", "21:00", "07:30", "La nuit : surveillance, soins, urgences."),
    ("RH", "Repos hebdomadaire", "", "", "Jour de repos."),
    ("DS", "Disponibilité", "", "", "Présence sans affectation définie."),
    ("FEJ", "Férié", "", "", "Jour férié."),
    ("RTT", "Réduction du temps de travail", "", "", "Jour de récupération."),
]


def _minutes(hhmm: str) -> int:
    try:
        heures, minutes = str(hhmm or "").split(":")
        return int(heures) * 60 + int(minutes)
    except (ValueError, AttributeError):
        return 0


def duree(debut: str, fin: str) -> int:
    """Durée en minutes entre deux heures (une fin avant le début passe minuit)."""
    if not debut or not fin:
        return 0
    duree_ = _minutes(fin) - _minutes(debut)
    if duree_ <= 0:
        duree_ += 24 * 60
    return duree_


def initialiser() -> None:
    with connexion() as base:
        base.executescript(SCHEMA)


def _codes_depart(theme: str) -> None:
    """Installe le référentiel de départ d'un thème, s'il est vide."""
    with connexion() as base:
        deja = base.execute("select count(*) from codes_horaires where theme = ?",
                            (theme,)).fetchone()[0]
        if deja:
            return
        moment = maintenant()
        for ordre, (code, libelle, debut, fin, definition) in enumerate(CODES_DEPART, start=1):
            base.execute(
                "insert or ignore into codes_horaires (id, theme, code, libelle, debut, fin,"
                " couleur, definition, ordre, cree_le, maj_le) values (?, ?, ?, ?, ?, ?, ?, ?,"
                " ?, ?, ?)",
                (_identifiant("ch"), theme, code, libelle, debut, fin,
                 CODES_HERMES.get(code, {}).get("fond", ""), definition, ordre, moment, moment))


# ====================================================================================
# Référentiel des codes horaires
# ====================================================================================
def lister_codes(theme: str) -> list[dict]:
    _codes_depart(theme)
    with connexion() as base:
        lignes = base.execute(
            "select * from codes_horaires where theme = ? order by ordre, code", (theme,)
        ).fetchall()
    codes = [dict(l) for l in lignes]
    for code in codes:
        code["duree_min"] = duree(code.get("debut", ""), code.get("fin", ""))
    return codes


def enregistrer_code(theme: str, champs: dict, qui: str = "") -> dict:
    code = str(champs.get("code") or "").strip().upper()
    if not code:
        raise ValueError("Le code est obligatoire (par exemple M03).")
    moment = maintenant()
    with connexion() as base:
        existant = base.execute("select * from codes_horaires where theme = ? and code = ?",
                                (theme, code)).fetchone()
        if existant:
            base.execute(
                "update codes_horaires set libelle = ?, debut = ?, fin = ?, definition = ?,"
                " couleur = ?, ordre = ?, maj_le = ? where id = ?",
                (champs.get("libelle", existant["libelle"]), champs.get("debut", existant["debut"]),
                 champs.get("fin", existant["fin"]), champs.get("definition", existant["definition"]),
                 champs.get("couleur") or existant["couleur"],
                 int(champs.get("ordre", existant["ordre"]) or 0), moment, existant["id"]))
            identifiant = existant["id"]
        else:
            identifiant = _identifiant("ch")
            base.execute(
                "insert into codes_horaires (id, theme, code, libelle, debut, fin, couleur,"
                " definition, ordre, cree_le, maj_le) values (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (identifiant, theme, code, champs.get("libelle", ""), champs.get("debut", ""),
                 champs.get("fin", ""),
                 champs.get("couleur") or CODES_HERMES.get(code, {}).get("fond", ""),
                 champs.get("definition", ""), int(champs.get("ordre") or 0), moment, moment))
        ligne = base.execute("select * from codes_horaires where id = ?", (identifiant,)).fetchone()
    journaliser(theme, qui or "Anonyme", "code_horaire", identifiant, code)
    resultat = dict(ligne)
    resultat["duree_min"] = duree(resultat.get("debut", ""), resultat.get("fin", ""))
    diffuser(theme, {"type": "code_horaire", "code": resultat})
    return resultat


def supprimer_code(theme: str, code_id: str, qui: str = "") -> None:
    with connexion() as base:
        ligne = base.execute("select code from codes_horaires where id = ? and theme = ?",
                             (code_id, theme)).fetchone()
        base.execute("delete from codes_horaires where id = ? and theme = ?", (code_id, theme))
    journaliser(theme, qui or "Anonyme", "code_horaire_supprime", code_id,
                ligne["code"] if ligne else "")
    diffuser(theme, {"type": "code_horaire_supprime", "id": code_id})


# ====================================================================================
# Fiches de poste et leurs tâches
# ====================================================================================
def _taches(fiche: str, base) -> list[dict]:
    lignes = base.execute("select * from fiche_taches where fiche = ? order by ordre, rowid",
                          (fiche,)).fetchall()
    taches = [dict(l) for l in lignes]
    for tache in taches:
        if not tache["duree_min"]:
            tache["duree_min"] = duree(tache.get("debut", ""), tache.get("fin", ""))
    return taches


def _fiche_complete(ligne, base) -> dict:
    fiche = dict(ligne)
    fiche["taches"] = _taches(fiche["id"], base)
    fiche["statut_libelle"] = LIBELLES_STATUTS.get(fiche["statut"], fiche["statut"])
    # Charge par code horaire : la somme des durées des tâches, et le temps de présence.
    par_code: dict[str, dict] = {}
    for tache in fiche["taches"]:
        casier = par_code.setdefault(tache["code"] or "—",
                                     {"code": tache["code"] or "—", "minutes": 0, "taches": 0})
        casier["minutes"] += int(tache["duree_min"] or 0)
        casier["taches"] += 1
    fiche["charge_par_code"] = sorted(par_code.values(), key=lambda c: -c["minutes"])
    fiche["minutes_totales"] = sum(c["minutes"] for c in par_code.values())
    return fiche


def lister_fiches(theme: str) -> list[dict]:
    with connexion() as base:
        lignes = base.execute("select * from fiches where theme = ? order by profession,"
                              " intitule collate nocase", (theme,)).fetchall()
        fiches = [_fiche_complete(l, base) for l in lignes]
    return fiches


def lire_fiche(theme: str, fiche_id: str) -> dict | None:
    with connexion() as base:
        ligne = base.execute("select * from fiches where id = ? and theme = ?",
                             (fiche_id, theme)).fetchone()
        if not ligne:
            return None
        return _fiche_complete(ligne, base)


def creer_fiche(theme: str, champs: dict, qui: str = "") -> dict:
    moment = maintenant()
    fiche = {"id": _identifiant("fp"), "theme": theme,
             "profession": (champs.get("profession") or "").strip(),
             "intitule": (champs.get("intitule") or "Fiche de poste").strip(),
             "finalite": (champs.get("finalite") or "").strip(),
             "statut": "a_l_etude", "version": 1, "auteur": qui or "",
             "cree_le": moment, "maj_le": moment}
    with connexion() as base:
        base.execute(
            "insert into fiches (id, theme, profession, intitule, finalite, statut, version,"
            " validee_par, validee_le, auteur, cree_le, maj_le) values (:id, :theme,"
            " :profession, :intitule, :finalite, :statut, :version, '', NULL, :auteur,"
            " :cree_le, :maj_le)", fiche)
    journaliser(theme, qui or "Anonyme", "fiche_creee", fiche["id"], fiche["intitule"])
    resultat = lire_fiche(theme, fiche["id"])
    diffuser(theme, {"type": "fiche_creee", "fiche": resultat})
    return resultat


def maj_fiche(theme: str, fiche_id: str, champs: dict, qui: str = "") -> dict | None:
    autorises = ("profession", "intitule", "finalite")
    valeurs = {c: champs[c] for c in autorises if c in champs}
    if champs.get("statut") in STATUTS:
        valeurs["statut"] = champs["statut"]
        if champs["statut"] == "validee":
            valeurs["validee_par"] = qui or "Anonyme"
            valeurs["validee_le"] = maintenant()
    if not valeurs:
        return lire_fiche(theme, fiche_id)
    valeurs["maj_le"] = maintenant()
    colonnes = ", ".join(f"{c} = :{c}" for c in valeurs)
    valeurs.update({"id": fiche_id, "theme": theme})
    with connexion() as base:
        base.execute(f"update fiches set {colonnes} where id = :id and theme = :theme", valeurs)
    fiche = lire_fiche(theme, fiche_id)
    if not fiche:
        return None
    action = "fiche_validee" if champs.get("statut") == "validee" else "fiche_modifiee"
    journaliser(theme, qui or "Anonyme", action, fiche_id,
                fiche["intitule"] + " — " + fiche["statut_libelle"], silence=30)
    diffuser(theme, {"type": "fiche_maj", "fiche": fiche})
    return fiche


def dupliquer_fiche(theme: str, fiche_id: str, qui: str = "") -> dict:
    """« On part de l'existant » : la copie devient une nouvelle version à travailler."""
    originale = lire_fiche(theme, fiche_id)
    if not originale:
        raise ValueError("Fiche inconnue")
    copie = creer_fiche(theme, {"profession": originale["profession"],
                                "intitule": originale["intitule"] + " (nouvelle version)",
                                "finalite": originale["finalite"]}, qui)
    with connexion() as base:
        base.execute("update fiches set version = ? where id = ?",
                     (int(originale["version"]) + 1, copie["id"]))
        for tache in originale["taches"]:
            _ajouter_ligne(base, copie["id"], tache, tache["ordre"])
    resultat = lire_fiche(theme, copie["id"])
    journaliser(theme, qui or "Anonyme", "fiche_dupliquee", copie["id"], resultat["intitule"])
    diffuser(theme, {"type": "fiche_creee", "fiche": resultat})
    return resultat


def supprimer_fiche(theme: str, fiche_id: str, qui: str = "") -> None:
    with connexion() as base:
        base.execute("delete from fiche_taches where fiche = ?", (fiche_id,))
        base.execute("delete from fiches where id = ? and theme = ?", (fiche_id, theme))
    journaliser(theme, qui or "Anonyme", "fiche_supprimee", fiche_id)
    diffuser(theme, {"type": "fiche_supprimee", "id": fiche_id})


def _ajouter_ligne(base, fiche_id: str, tache: dict, ordre: int) -> str:
    identifiant = _identifiant("ft")
    base.execute(
        "insert into fiche_taches (id, fiche, ordre, libelle, code, debut, fin, duree_min,"
        " periodicite, qui, remarque) values (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (identifiant, fiche_id, ordre, tache.get("libelle", ""), tache.get("code", ""),
         tache.get("debut", ""), tache.get("fin", ""),
         int(tache.get("duree_min") or duree(tache.get("debut", ""), tache.get("fin", ""))),
         tache.get("periodicite", ""), tache.get("qui", ""), tache.get("remarque", "")))
    return identifiant


def ajouter_tache(theme: str, fiche_id: str, champs: dict, qui: str = "") -> dict | None:
    with connexion() as base:
        ordre = base.execute("select coalesce(max(ordre), 0) + 1 from fiche_taches"
                             " where fiche = ?", (fiche_id,)).fetchone()[0]
        _ajouter_ligne(base, fiche_id, champs, int(ordre))
    journaliser(theme, qui or "Anonyme", "tache_ajoutee", fiche_id, champs.get("libelle", ""),
                silence=20)
    fiche = lire_fiche(theme, fiche_id)
    if fiche:
        diffuser(theme, {"type": "fiche_maj", "fiche": fiche})
    return fiche


def maj_tache(theme: str, fiche_id: str, tache_id: str, champs: dict,
              qui: str = "") -> dict | None:
    autorises = ("libelle", "code", "debut", "fin", "duree_min", "periodicite", "qui",
                 "remarque", "ordre")
    valeurs = {c: champs[c] for c in autorises if c in champs}
    if not valeurs:
        return lire_fiche(theme, fiche_id)
    if "duree_min" in valeurs:
        valeurs["duree_min"] = int(valeurs["duree_min"] or 0)
    if "ordre" in valeurs:
        valeurs["ordre"] = int(valeurs["ordre"] or 0)
    if not valeurs.get("duree_min") and ("debut" in valeurs or "fin" in valeurs):
        with connexion() as base:
            ancienne = base.execute("select debut, fin from fiche_taches where id = ?",
                                    (tache_id,)).fetchone()
        debut = valeurs.get("debut", ancienne["debut"] if ancienne else "")
        fin = valeurs.get("fin", ancienne["fin"] if ancienne else "")
        valeurs["duree_min"] = duree(debut, fin)
    colonnes = ", ".join(f"{c} = :{c}" for c in valeurs)
    valeurs["id"] = tache_id
    with connexion() as base:
        base.execute(f"update fiche_taches set {colonnes} where id = :id", valeurs)
    journaliser(theme, qui or "Anonyme", "tache_modifiee", fiche_id,
                champs.get("libelle", ""), silence=30)
    fiche = lire_fiche(theme, fiche_id)
    if fiche:
        diffuser(theme, {"type": "fiche_maj", "fiche": fiche})
    return fiche


def supprimer_tache(theme: str, fiche_id: str, tache_id: str, qui: str = "") -> dict | None:
    with connexion() as base:
        base.execute("delete from fiche_taches where id = ?", (tache_id,))
    journaliser(theme, qui or "Anonyme", "tache_supprimee", fiche_id)
    fiche = lire_fiche(theme, fiche_id)
    if fiche:
        diffuser(theme, {"type": "fiche_maj", "fiche": fiche})
    return fiche
