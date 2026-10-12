#!/usr/bin/env python3
"""Notifications réglées sur son propre compte (12/10/2026).

Demande de l'utilisateur : « Je veux aussi dans synergie pouvoir gérer les notifications
liées à son propre compte. Se voir un mail lorsqu'il y a un nouveau message dans le chat, de
nouveaux documents, des modifications liées au projet, liées au groupe. »

Ce contrôle a deux parties :

  1. LE MOTEUR, sur une base d'essai à part (aucun courriel ne part, aucune donnée réelle
     touchée) : on vérifie que décocher une catégorie retire vraiment la personne des
     destinataires de cette catégorie-là, et d'elle seule ;
  2. L'ÉCRAN, dans un vrai navigateur et contre le service en marche : les quatre cases
     existent, elles sont cochées d'emblée, et décocher « chat » puis Enregistrer est
     réellement gardé (relu par l'API).

    python3 tests/tester_notifications.py
    SYNERGIE_SITE=https://synergie.alpinevibe.fr python3 tests/tester_notifications.py
"""
import json
import os
import sys
import tempfile
import urllib.error
import urllib.request

from playwright.sync_api import sync_playwright

RACINE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, RACINE)

BASE = os.environ.get("SYNERGIE_SITE", "http://127.0.0.1:8077").rstrip("/")
CAPTURES = os.environ.get("CHECKUP_CAPTURES", "/home/ubuntu/captures")
PERSONNE = "Essai notifications"

RESULTATS = []


def verifie(titre, condition, detail=""):
    RESULTATS.append((titre, bool(condition)))
    print(("  ✅ " if condition else "  ❌ ") + titre + ((" — " + str(detail)) if detail else ""))


def menage(identifiants):
    from tests.menage_essai import effacer_comptes
    effacer_comptes(identifiants)


def appel(chemin, corps=None, jeton=None, methode=None):
    donnees = json.dumps(corps).encode("utf-8") if corps is not None else None
    requete = urllib.request.Request(BASE + chemin, data=donnees,
                                     method=methode or ("POST" if donnees else "GET"))
    requete.add_header("Content-Type", "application/json")
    requete.add_header("User-Agent", "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
                                     "(KHTML, like Gecko) Chrome/124.0 Safari/537.36")
    if jeton:
        requete.add_header("X-Synergie-Jeton", jeton)
    with urllib.request.urlopen(requete, timeout=30) as reponse:
        return json.loads(reponse.read().decode("utf-8"))


# =====================================================================================
# 1. LE MOTEUR — sur une base d'essai, à l'écart des données réelles
# =====================================================================================
def controler_le_moteur() -> list[str]:
    """Rend les identifiants créés (pour les effacer ensuite)."""
    fichier = tempfile.NamedTemporaryFile(suffix="-notifications.db", delete=False)
    fichier.close()
    ancienne = os.environ.get("SYNERGIE_BASE")
    os.environ["SYNERGIE_BASE"] = fichier.name
    for module in [m for m in list(sys.modules) if m.startswith("moteur")]:
        del sys.modules[module]

    from moteur import atelier, equipe, projets

    atelier.initialiser()
    equipe.initialiser()
    projets.initialiser()

    un = equipe.creer_compte("Essai Notif Une", "essai-notif-1@exemple.invalid")["compte"]
    deux = equipe.creer_compte("Essai Notif Deux", "essai-notif-2@exemple.invalid")["compte"]
    projet = projets.creer_projet("Essai notifications", "", "Essai",
                                  admin=un["id"], qui="Essai")
    groupe = atelier.creer_theme("Groupe d'essai notifications", "", "", projet["id"], "Essai")
    for compte, role in ((un, "admin"), (deux, "membre")):
        projets.definir_membre_projet(projet["id"], compte["id"], role, True, "Essai")
        projets.definir_membre_theme(groupe["id"], compte["id"], role, True, "Essai")

    # Tout est reçu par défaut : rien n'a été décoché.
    verifie("tout est reçu par défaut (aucun réglage posé)",
            equipe.lire_categories(un["id"]) == {"chat": True, "documents": True,
                                                 "projet": True, "groupe": True},
            equipe.lire_categories(un["id"]))

    def adresses(theme_projet, categorie):
        m = projets.destinataires_theme(groupe["id"], projet["id"], categorie)
        return sorted(p["email"] for p in m)

    avant = adresses(groupe, "chat")
    verifie("le chat prévient bien les deux personnes au départ", len(avant) == 2, avant)

    # Je ne veux plus du chat : les autres catégories ne bougent pas.
    equipe.regler_categories(un["id"], {"chat": False})
    apres_chat = adresses(groupe, "chat")
    apres_documents = adresses(groupe, "documents")
    verifie("décocher « chat » retire cette personne des messages du chat",
            apres_chat == ["essai-notif-2@exemple.invalid"], apres_chat)
    verifie("décocher « chat » ne touche PAS les autres catégories",
            len(apres_documents) == 2, apres_documents)

    equipe.regler_categories(un["id"], {"documents": False})
    verifie("chaque catégorie se règle indépendamment",
            (adresses(groupe, "documents") == ["essai-notif-2@exemple.invalid"]
             and adresses(groupe, "projet") == ["essai-notif-1@exemple.invalid",
                                                "essai-notif-2@exemple.invalid"]),
            adresses(groupe, "documents"))

    # Les changements du PROJET passent par le projet (et non par un groupe).
    dest_projet = projets.destinataires_projet(projet["id"], "projet")
    verifie("les changements du projet atteignent les membres du projet",
            len(dest_projet) == 2, [d["email"] for d in dest_projet])

    # Une catégorie inventée ne doit rien filtrer (ni casser la requête).
    verifie("une catégorie inconnue ne filtre personne et ne casse rien",
            len(adresses(groupe, "nimportequoi")) == 2)

    # Le message d'alerte dit où régler tout cela.
    corps = equipe.pied_de_page()
    verifie("chaque alerte rappelle où régler ses notifications",
            "Mon compte" in corps and "Notifications" in corps)

    # Le réglage est bien relu après écriture (et non seulement en mémoire).
    verifie("le réglage est relu depuis la base",
            equipe.lire_categories(un["id"])["chat"] is False
            and equipe.lire_categories(deux["id"])["chat"] is True)

    os.unlink(fichier.name)
    if ancienne is None:
        os.environ.pop("SYNERGIE_BASE", None)
    else:
        os.environ["SYNERGIE_BASE"] = ancienne
    return []


# =====================================================================================
# 2. L'ÉCRAN — dans un vrai navigateur, contre le service en marche
# =====================================================================================
MESURE = """() => {
  const zone = document.querySelector('#c-categories');
  if (!zone) return null;
  const cases = [...zone.querySelectorAll('input[data-categorie]')];
  return {
    nombre: cases.length,
    libelles: cases.map((c) => (c.parentElement.textContent || '').trim()),
    cochees: cases.map((c) => c.checked),
    identifiants: cases.map((c) => c.dataset.categorie)
  };
}"""

# Les cases ne doivent JAMAIS rester sous la barre de boutons collée au bas de la fenêtre
# (défaut constaté le 12/10/2026 : la carte translucide laissait voir les cases au travers).
MESURE_RECOUVREMENT = """() => {
  const boite = document.querySelector('#vue-compte .boite-nom');
  const barre = document.querySelector('#vue-compte .barre-boutons');
  boite.scrollTop = boite.scrollHeight;            // on va au bas de la fenêtre
  const bb = barre.getBoundingClientRect();
  const fond = getComputedStyle(barre).backgroundColor;
  const opacite = (fond.match(/rgba?\\(([^)]+)\\)/) || [])[1];
  const parties = (opacite || '0').split(',');
  const alpha = parties.length === 4 ? parseFloat(parties[3]) : 1;
  const recouvertes = [...document.querySelectorAll('#c-categories label.case')]
    .filter((l) => l.getBoundingClientRect().bottom > bb.top + 1).length;
  return { recouvertes, alpha, hauteur_barre: Math.round(bb.height) };
}"""


def controler_l_ecran() -> int:
    try:
        compte = appel("/api/comptes", {"prenom": PERSONNE, "email": ""})
    except urllib.error.URLError as erreur:
        print(f"Synergie injoignable sur {BASE} : {erreur}", file=sys.stderr)
        return 2
    jeton = compte["jeton"]
    identifiant = compte["compte"]["id"]
    projet = None
    try:
        projet = appel("/api/projets", {"nom": "Essai — notifications"}, jeton=jeton)
        with sync_playwright() as p:
            nav = p.chromium.launch(args=["--no-sandbox"])
            ctx = nav.new_context(viewport={"width": 1280, "height": 900})
            ctx.add_init_script(
                "localStorage.setItem('synergie.jeton', %s);"
                "localStorage.setItem('synergie.projet', %s);"
                % (json.dumps(jeton), json.dumps(projet["id"])))
            ctx.add_cookies([{"name": "synergie", "value": jeton, "url": BASE,
                              "httpOnly": True, "sameSite": "Lax"}])
            page = ctx.new_page()
            erreurs = []
            page.on("pageerror", lambda e: erreurs.append(str(e)[:120]))
            page.on("console", lambda m: erreurs.append("console: " + m.text[:120])
                    if m.type == "error" else None)
            page.goto(f"{BASE}/#p={projet['id']}", wait_until="load", timeout=45000)
            page.wait_for_timeout(2500)
            page.click("#btn-compte")            # « Mon compte », dans l'entête
            page.wait_for_timeout(1500)

            vue = page.evaluate(MESURE)
            verifie("les quatre catégories sont proposées dans « Mon compte »",
                    vue and vue["nombre"] == 4, vue and vue["nombre"])
            verifie("elles sont cochées d'emblée (on reçoit tout par défaut)",
                    vue and all(vue["cochees"]), vue and vue["cochees"])
            verifie("elles portent les bonnes catégories",
                    vue and sorted(vue["identifiants"]) == ["chat", "documents",
                                                            "groupe", "projet"],
                    vue and vue["identifiants"])
            verifie("chacune est nommée en français",
                    vue and all("chat" in l.lower() or "document" in l.lower()
                                or "projet" in l.lower() or "groupe" in l.lower()
                                for l in vue["libelles"]), vue and vue["libelles"])
            os.makedirs(CAPTURES, exist_ok=True)
            page.screenshot(path=f"{CAPTURES}/synergie-notifications.png", full_page=False)

            recouvrement = page.evaluate(MESURE_RECOUVREMENT)
            page.wait_for_timeout(300)
            verifie("aucune case ne reste cachée sous la barre de boutons",
                    recouvrement and recouvrement["recouvertes"] == 0, recouvrement)
            verifie("la barre de boutons est opaque (on ne voit rien au travers)",
                    recouvrement and recouvrement["alpha"] == 1, recouvrement)
            verifie("la barre de boutons reste courte (elle ne mange pas la fenêtre)",
                    recouvrement and recouvrement["hauteur_barre"] <= 120, recouvrement)
            page.screenshot(path=f"{CAPTURES}/synergie-notifications-bas.png", full_page=False)

            # Décocher « chat », enregistrer, et relire par l'API.
            page.evaluate("""() => {
              const c = document.querySelector('#c-categories input[data-categorie="chat"]');
              c.checked = false;
              document.querySelector('#c-enregistrer').click();
            }""")
            page.wait_for_timeout(2500)
            relu = appel("/api/comptes/moi", jeton=jeton)
            categories = (relu.get("notifications") or {}).get("categories") or {}
            verifie("décocher « chat » puis Enregistrer est réellement gardé",
                    categories.get("chat") is False, categories)
            verifie("les autres catégories restent cochées",
                    all(categories.get(c) for c in ("documents", "projet", "groupe")),
                    categories)

            # On remet tout : l'essai ne doit rien laisser déréglé.
            appel("/api/notifications", {"categories": {"chat": True, "documents": True,
                                                        "projet": True, "groupe": True}},
                  jeton=jeton, methode="PUT")
            relu = appel("/api/comptes/moi", jeton=jeton)
            verifie("on peut tout remettre (l'essai ne laisse rien déréglé)",
                    all(((relu.get("notifications") or {}).get("categories") or {}).values()),
                    ((relu.get("notifications") or {}).get("categories")))
            verifie("aucune erreur JavaScript dans l'écran", not erreurs, erreurs[:2])
            ctx.close()
            nav.close()
    finally:
        if projet:
            try:
                appel(f"/api/projets/{projet['id']}", jeton=jeton, methode="DELETE")
            except Exception:
                pass
        menage([identifiant])
    return 0


def principal() -> int:
    print("1. Le moteur (base d'essai, aucun courriel envoyé)")
    controler_le_moteur()
    print("\n2. L'écran « Mon compte », dans un vrai navigateur")
    code = controler_l_ecran()
    if code:
        return code
    echecs = sum(1 for _, ok in RESULTATS if not ok)
    print(f"\n{len(RESULTATS) - echecs}/{len(RESULTATS)} contrôles réussis")
    return 1 if echecs else 0


if __name__ == "__main__":
    sys.exit(principal())
