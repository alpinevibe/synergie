#!/usr/bin/env python3
"""Met la discussion du groupe en colonne de droite (09/10/2026).

Demande de l'utilisateur : « retire l'onglet discussion dans les groupes et mets la fenêtre
de chat sur la droite ».

Le script réorganise la vue d'un groupe dans web/index.html :
  • les onglets (Tableau blanc, Pages, Documents, Votes, Journal) forment la colonne
    principale ;
  • la discussion du groupe devient une colonne de droite, toujours visible — la même mise en
    page que la discussion de projet (`.projet-chat`).
"""
import sys
from pathlib import Path

RACINE = Path(__file__).resolve().parent.parent
FICHIER = RACINE / "web" / "index.html"

NAV = '  <nav class="onglets" id="onglets-theme" aria-label="Outils du groupe"></nav>\n'

CHAT_ONGLE = '''  <!-- ---- la discussion du groupe ---- -->
  <section id="onglet-chat" class="onglet cache" aria-label="Discussion du groupe">
    <div class="carte">
      <div id="fil-theme" class="fil" aria-live="polite"></div>
      <form id="chat-theme-form" class="ligne-chat">
        <label class="sr-only" for="chat-theme-texte">Écrire un message</label>
        <input id="chat-theme-texte" placeholder="Écrire un message…" autocomplete="off">
        <button class="principal petit" type="submit">Envoyer</button>
      </form>
    </div>
  </section>

'''

CHAT_COLONNE = '''    <!-- Colonne de droite : la discussion du groupe, toujours visible -->
    <aside class="carte theme-chat" aria-label="Discussion du groupe">
      <h3>Discussion du groupe</h3>
      <div id="fil-theme" class="fil" aria-live="polite"></div>
      <form id="chat-theme-form" class="ligne-chat">
        <label class="sr-only" for="chat-theme-texte">Écrire un message</label>
        <input id="chat-theme-texte" placeholder="Écrire un message…" autocomplete="off">
        <button class="principal petit" type="submit">Envoyer</button>
      </form>
    </aside>
'''


def principal() -> int:
    texte = FICHIER.read_text(encoding="utf-8")
    if "theme-grille" in texte:
        print("déjà réorganisé : rien à faire")
        return 0
    if NAV not in texte or CHAT_ONGLE not in texte:
        print("vue du groupe introuvable : réorganisation abandonnée", file=sys.stderr)
        return 1

    debut = texte.index(NAV) + len(NAV)
    fin = texte.index("</main>", debut)                 # fin de la vue d'un groupe
    onglets = texte[debut:fin].replace(CHAT_ONGLE, "").strip("\n")

    # Les onglets rentrent d'un cran dans la colonne principale.
    onglets = "\n".join(("    " + ligne) if ligne.strip() else ligne
                        for ligne in onglets.splitlines())

    nouveau = (
        '  <div class="theme-grille">\n'
        + "    <!-- Colonne principale : les outils du groupe (onglets) -->\n"
        + '    <div class="theme-principal">\n'
        + onglets + "\n"
        + "    </div>\n\n"
        + CHAT_COLONNE
        + "  </div>\n"
    )
    FICHIER.write_text(texte[:debut] + nouveau + texte[fin:], encoding="utf-8")
    print("vue du groupe réorganisée : discussion en colonne de droite")
    return 0


if __name__ == "__main__":
    sys.exit(principal())
