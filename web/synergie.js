/* SYNERGIE — atelier collaboratif.
   ---------------------------------------------------------------------------------
   Le cœur de l'application, c'est le travail à plusieurs : des thèmes de réflexion, un
   tableau blanc SANS LIMITES où chacun écrit ce qui lui passe par la tête (mise en forme,
   couleurs, tailles), des documents de travail, et des décisions prises ensemble.

   Tout le monde voit les modifications des autres en direct : le serveur pousse chaque
   changement par un flux d'événements (SSE), et cette page l'écoute.

   Le générateur de trames n'est qu'un OUTIL, rangé dans l'onglet « Outils » du thème. */
(function () {
  'use strict';

  // ---------------------------------------------------------------- état de la page
  let themes = [];
  let theme = null;                      // thème ouvert
  let notes = [];                        // notes du tableau blanc
  let decisions = [];
  let documents = [];
  let participants = [];
  let selection = null;                  // note en cours d'édition
  let flux = null;                       // flux temps réel
  let vue = { x: 40, y: 40, z: 1 };      // déplacement et zoom du tableau
  let minuteurs = {};                    // temporisations d'enregistrement
  const $ = (selecteur) => document.querySelector(selecteur);

  const COULEURS_TEXTE = ['#1e2a3a', '#4a6cf7', '#17a673', '#c0392b', '#b26a00', '#7a3ea1'];
  const COULEURS_FOND = ['#fff8d6', '#e7f2ff', '#e9f9ee', '#fdeceb', '#f0eaff', '#ffffff'];
  const ORDRE_FONDS = ['#fff8d6', '#e7f2ff', '#e9f9ee', '#fdeceb', '#f0eaff', '#ffffff'];

  // ---------------------------------------------------------------- appels au serveur
  async function appel(chemin, { methode = 'GET', corps = null, donnees = null } = {}) {
    const options = { method: methode, headers: {} };
    if (corps !== null) {
      options.headers['Content-Type'] = 'application/json';
      options.body = JSON.stringify(corps);
    }
    if (donnees) options.body = donnees;
    const reponse = await fetch(chemin, options);
    if (!reponse.ok) {
      let detail = reponse.statusText;
      try { detail = (await reponse.json()).erreur || detail; } catch (e) { /* sans corps */ }
      throw new Error(detail);
    }
    return reponse.status === 204 ? null : reponse.json();
  }

  // ---------------------------------------------------------------- mon nom
  function monNom() {
    return (localStorage.getItem('synergie.nom') || '').trim();
  }
  function retenirNom(valeur) {
    localStorage.setItem('synergie.nom', (valeur || '').trim());
  }

  // ================================================================ LISTE DES THÈMES
  async function chargerThemes() {
    const donnees = await appel('/api/themes');
    themes = donnees.themes || [];
    afficherThemes();
  }

  function afficherThemes() {
    const zone = $('#liste-themes');
    zone.innerHTML = '';
    if (!themes.length) {
      zone.append(element('p', { classe: 'vide',
        texte: 'Aucun thème pour le moment. Créez le premier : c\'est le point de départ du travail commun.' }));
      return;
    }
    themes.forEach((t) => {
      const carte = element('div', { classe: 'carte-theme', style: `--teinte:${t.couleur || '#4a6cf7'}` });
      carte.append(
        element('h3', { texte: t.titre }),
        element('p', { classe: 'aide', texte: t.description || 'Pas encore de description.' }),
        element('p', { classe: 'compteurs', texte:
          `${t.notes} note(s) · ${t.decisions} décision(s) dont ${t.adoptees} adoptée(s) · ${t.documents} document(s)` }),
        element('p', { classe: 'quand', texte: 'Dernier mouvement : ' + quand(t.maj_le) })
      );
      carte.addEventListener('click', () => ouvrirTheme(t.id));
      zone.append(carte);
    });
  }

  // ================================================================ UN THÈME
  async function ouvrirTheme(identifiant, { pousser = true } = {}) {
    const donnees = await appel('/api/themes/' + encodeURIComponent(identifiant));
    theme = donnees.theme; notes = donnees.notes || []; decisions = donnees.decisions || [];
    documents = donnees.documents || []; participants = donnees.participants || [];
    $('#vue-themes').classList.add('cache');
    $('#vue-theme').classList.remove('cache');
    $('#titre-theme').value = theme.titre || '';
    $('#description-theme').value = theme.description || '';
    afficherParticipants();
    dessinerNotes();
    afficherDocuments();
    afficherDecisions();
    afficherOutils();
    brancherFlux();
    if (pousser && location.hash !== '#t=' + identifiant) {
      history.replaceState(null, '', '#t=' + identifiant);
    }
  }

  function fermerTheme() {
    if (flux) { flux.close(); flux = null; }
    theme = null; notes = []; decisions = []; documents = []; participants = [];
    $('#vue-theme').classList.add('cache');
    $('#vue-themes').classList.remove('cache');
    history.replaceState(null, '', location.pathname);
    chargerThemes();
  }

  async function enregistrerTheme() {
    if (!theme) return;
    try {
      await appel('/api/themes/' + theme.id, { methode: 'PUT',
        corps: { titre: $('#titre-theme').value.trim() || 'Thème sans titre',
                 description: $('#description-theme').value.trim() } });
      theme.titre = $('#titre-theme').value.trim();
    } catch (erreur) { alert('Enregistrement impossible : ' + erreur.message); }
  }

  // ================================================================ TEMPS RÉEL
  function brancherFlux() {
    if (flux) flux.close();
    if (!theme) return;
    flux = new EventSource('/api/themes/' + encodeURIComponent(theme.id) +
      '/evenements?nom=' + encodeURIComponent(monNom() || 'Anonyme'));
    flux.onmessage = (message) => {
      try { traiter(JSON.parse(message.data)); } catch (e) { /* événement illisible */ }
    };
    flux.onerror = () => { /* le navigateur retente tout seul */ };
  }

  function traiter(evenement) {
    switch (evenement.type) {
      case 'bonjour':
      case 'presence':
        participants = evenement.participants || [];
        afficherParticipants();
        break;
      case 'note_creee':
      case 'note_maj': {
        const note = evenement.note;
        const index = notes.findIndex((n) => n.id === note.id);
        if (index === -1) notes.push(note); else notes[index] = note;
        poserNote(note, { forcer: false });
        break;
      }
      case 'note_supprimee':
        notes = notes.filter((n) => n.id !== evenement.id);
        retirerNote(evenement.id);
        break;
      case 'decision_creee':
      case 'decision_maj': {
        const index = decisions.findIndex((d) => d.id === evenement.decision.id);
        if (index === -1) decisions.unshift(evenement.decision);
        else decisions[index] = evenement.decision;
        afficherDecisions();
        break;
      }
      case 'decision_supprimee':
        decisions = decisions.filter((d) => d.id !== evenement.id);
        afficherDecisions();
        break;
      case 'document_ajoute':
        documents.unshift(evenement.document);
        afficherDocuments();
        break;
      case 'document_supprime':
        documents = documents.filter((d) => d.id !== evenement.id);
        afficherDocuments();
        break;
      case 'curseur':
        signalerCurseur(evenement.qui, evenement.note);
        break;
      case 'theme_supprime':
        fermerTheme();
        break;
      default: break;
    }
  }

  function afficherParticipants() {
    const zone = $('#participants');
    if (!participants.length) { zone.textContent = 'personne pour le moment'; return; }
    zone.textContent = participants.join(' · ');
  }

  // Un liseré coloré sur la note que quelqu'un d'autre est en train d'écrire.
  const COULEURS_PRESENCE = ['#4a6cf7', '#17a673', '#c0392b', '#b26a00', '#7a3ea1', '#0f766e'];
  function signalerCurseur(qui, noteId) {
    document.querySelectorAll('.note.editee-par').forEach((n) => {
      n.classList.remove('editee-par'); n.removeAttribute('data-qui');
    });
    if (!noteId || !qui || qui === monNom()) return;
    const noeud = document.querySelector(`.note[data-id="${noteId}"]`);
    if (noeud) {
      const rang = (qui.charCodeAt(0) + qui.length) % COULEURS_PRESENCE.length;
      noeud.classList.add('editee-par');
      noeud.dataset.qui = qui;
      noeud.style.setProperty('--presence', COULEURS_PRESENCE[rang]);
    }
  }

  // ================================================================ TABLEAU BLANC
  function appliquerVue() {
    const monde = $('#monde');
    monde.style.transform = `translate(${vue.x}px, ${vue.y}px) scale(${vue.z})`;
    $('#zoom-valeur').textContent = Math.round(vue.z * 100) + ' %';
  }

  function styleNote(note) {
    return [
      `left:${note.x}px`, `top:${note.y}px`, `width:${note.largeur}px`,
      `z-index:${10 + (note.ordre || 0)}`,
      `--teinte:${note.couleur_fond || '#fff8d6'}`,
      `color:${note.couleur_texte || '#1e2a3a'}`,
      `font-size:${note.taille || 16}px`,
      `font-weight:${note.gras ? 700 : 400}`,
      `font-style:${note.italique ? 'italic' : 'normal'}`,
      `text-decoration:${note.souligne ? 'underline' : 'none'}`,
      `text-align:${note.alignement || 'gauche'}`
    ].join(';');
  }

  /** Pose (ou met à jour) une note dans le tableau. `forcer` écrase le texte en cours. */
  function poserNote(note, { forcer = true } = {}) {
    let noeud = document.querySelector(`.note[data-id="${note.id}"]`);
    if (!noeud) {
      noeud = construireNote(note);
      $('#monde').append(noeud);
    }
    noeud.setAttribute('style', styleNote(note));
    const zoneTexte = noeud.querySelector('.note-texte');
    const enEdition = document.activeElement === zoneTexte;
    if (forcer || !enEdition) zoneTexte.textContent = note.texte || '';
    noeud.querySelector('.note-auteur').textContent = note.auteur ? note.auteur : '';
  }

  function retirerNote(identifiant) {
    const noeud = document.querySelector(`.note[data-id="${identifiant}"]`);
    if (noeud) noeud.remove();
  }

  function construireNote(note) {
    const noeud = element('div', { classe: 'note' });
    noeud.dataset.id = note.id;
    const barre = element('div', { classe: 'note-barre' });
    const poignee = element('span', { classe: 'poignee', texte: '⠿' });
    poignee.title = 'Faire glisser la note';
    const auteur = element('span', { classe: 'note-auteur' });
    const supprimer = element('button', { classe: 'note-suppr', texte: '×' });
    supprimer.title = 'Supprimer la note';
    barre.append(poignee, auteur, supprimer);
    const texte = element('div', { classe: 'note-texte' });
    texte.contentEditable = 'true';
    texte.spellcheck = false;
    const poigneeTaille = element('span', { classe: 'poignee-taille' });
    noeud.append(barre, texte, poigneeTaille);

    // écrire
    texte.addEventListener('focus', () => {
      selectionner(note.id);
      envoyerCurseur(note.id);
    });
    texte.addEventListener('blur', () => envoyerCurseur(null));
    texte.addEventListener('input', () => {
      const courante = notes.find((n) => n.id === note.id);
      if (courante) courante.texte = texte.textContent;
      programmer(note.id, () => sauver(note.id, { texte: texte.textContent }, 'texte'), 700);
    });
    texte.addEventListener('pointerdown', (evenement) => evenement.stopPropagation());

    supprimer.addEventListener('click', (evenement) => {
      evenement.stopPropagation();
      if (!confirm('Supprimer cette note ?')) return;
      appel('/api/themes/' + theme.id + '/notes/' + note.id, { methode: 'DELETE' });
    });

    // déplacer (on suit la souris et on enregistre au relâchement)
    poignee.addEventListener('pointerdown', (evenement) => {
      evenement.preventDefault();
      poignee.setPointerCapture(evenement.pointerId);
      const depart = { x: evenement.clientX, y: evenement.clientY,
                       ox: note.x, oy: note.y };
      const bouger = (e) => {
        note.x = depart.ox + (e.clientX - depart.x) / vue.z;
        note.y = depart.oy + (e.clientY - depart.y) / vue.z;
        noeud.style.left = note.x + 'px';
        noeud.style.top = note.y + 'px';
        programmer('pos-' + note.id, () => sauver(note.id, { x: note.x, y: note.y }), 350);
      };
      const relacher = () => {
        poignee.removeEventListener('pointermove', bouger);
        poignee.removeEventListener('pointerup', relacher);
        sauver(note.id, { x: note.x, y: note.y });
      };
      poignee.addEventListener('pointermove', bouger);
      poignee.addEventListener('pointerup', relacher);
    });

    // redimensionner
    poigneeTaille.addEventListener('pointerdown', (evenement) => {
      evenement.preventDefault(); evenement.stopPropagation();
      poigneeTaille.setPointerCapture(evenement.pointerId);
      const depart = { x: evenement.clientX, largeur: note.largeur };
      const bouger = (e) => {
        note.largeur = Math.max(160, depart.largeur + (e.clientX - depart.x) / vue.z);
        noeud.style.width = note.largeur + 'px';
        programmer('larg-' + note.id, () => sauver(note.id, { largeur: note.largeur }), 350);
      };
      const relacher = () => {
        poigneeTaille.removeEventListener('pointermove', bouger);
        poigneeTaille.removeEventListener('pointerup', relacher);
        sauver(note.id, { largeur: note.largeur });
      };
      poigneeTaille.addEventListener('pointermove', bouger);
      poigneeTaille.addEventListener('pointerup', relacher);
    });

    noeud.addEventListener('pointerdown', () => selectionner(note.id));
    return noeud;
  }

  function dessinerNotes() {
    $('#monde').innerHTML = '';
    notes.forEach((note) => poserNote(note));
    appliquerVue();
    if (selection && notes.some((n) => n.id === selection)) afficherBarreFormat();
    else { selection = null; $('#barre-format').classList.add('cache'); }
  }

  /** Enregistre un changement (avec une temporisation pour ne pas écrire à chaque touche). */
  function programmer(cle, action, delai) {
    clearTimeout(minuteurs[cle]);
    minuteurs[cle] = setTimeout(action, delai);
  }

  async function sauver(identifiant, champs) {
    try {
      await appel('/api/themes/' + theme.id + '/notes/' + identifiant,
        { methode: 'PUT', corps: champs });
    } catch (erreur) { /* la note reste à l'écran, une nouvelle tentative suivra */ }
  }

  function envoyerCurseur(noteId) {
    if (!theme) return;
    programmer('curseur', () => {
      appel('/api/themes/' + theme.id + '/curseurs',
        { methode: 'POST', corps: { qui: monNom() || 'Anonyme', note: noteId } }).catch(() => {});
    }, 120);
  }

  function selectionner(identifiant) {
    selection = identifiant;
    document.querySelectorAll('.note').forEach((n) =>
      n.classList.toggle('choisie', n.dataset.id === identifiant));
    afficherBarreFormat();
  }

  function noteSelectionnee() { return notes.find((n) => n.id === selection) || null; }

  function afficherBarreFormat() {
    const note = noteSelectionnee();
    const barre = $('#barre-format');
    if (!note) { barre.classList.add('cache'); return; }
    barre.classList.remove('cache');
    barre.querySelectorAll('[data-format]').forEach((bouton) => {
      const cle = bouton.dataset.format;
      bouton.classList.toggle('actif',
        (cle === 'gras' && note.gras) || (cle === 'italique' && note.italique) ||
        (cle === 'souligne' && note.souligne) || (cle === note.alignement));
    });
  }

  /** Une place libre, à partir d'un point : deux personnes qui créent une note au même
      moment ne doivent PAS se superposer — les notes s'écartent en cascade. */
  function placeLibre(x, y) {
    let essai = 0;
    while (essai < 40 && notes.some((n) => Math.abs(n.x - x) < 34 && Math.abs(n.y - y) < 34)) {
      x += 30; y += 30; essai += 1;
    }
    return { x, y };
  }

  async function creerNote(champs = {}) {
    const place = placeLibre(Math.round((-vue.x + 60) / vue.z), Math.round((-vue.y + 90) / vue.z));
    const note = await appel('/api/themes/' + theme.id + '/notes', { methode: 'POST',
      corps: Object.assign({
        x: place.x, y: place.y,
        auteur: monNom() || 'Anonyme', couleur_fond: prochaineCouleur()
      }, champs) });
    notes.push(note);
    poserNote(note);
    selectionner(note.id);
    const texte = document.querySelector(`.note[data-id="${note.id}"] .note-texte`);
    if (texte) { texte.focus(); }
    return note;
  }

  function prochaineCouleur() {
    return ORDRE_FONDS[notes.length % ORDRE_FONDS.length];
  }

  async function appliquerFormat(cle) {
    const note = noteSelectionnee();
    if (!note) return;
    const changements = {};
    switch (cle) {
      case 'taille-plus': changements.taille = Math.min(64, (note.taille || 16) + 3); break;
      case 'taille-moins': changements.taille = Math.max(10, (note.taille || 16) - 3); break;
      case 'gras': changements.gras = !note.gras; break;
      case 'italique': changements.italique = !note.italique; break;
      case 'souligne': changements.souligne = !note.souligne; break;
      case 'gauche': case 'centre': case 'droite':
        changements.alignement = cle; break;
      case 'dupliquer': {
        await creerNote({ x: note.x + 40, y: note.y + 40, texte: note.texte,
          taille: note.taille, gras: note.gras, italique: note.italique,
          souligne: note.souligne, couleur_texte: note.couleur_texte,
          couleur_fond: note.couleur_fond, alignement: note.alignement });
        return;
      }
      case 'devant': {
        const maximum = Math.max(0, ...notes.map((n) => n.ordre || 0));
        changements.ordre = maximum + 1; break;
      }
      case 'supprimer':
        if (!confirm('Supprimer cette note ?')) return;
        await appel('/api/themes/' + theme.id + '/notes/' + note.id, { methode: 'DELETE' });
        return;
      default: break;
    }
    Object.assign(note, changements);
    poserNote(note);
    afficherBarreFormat();
    await sauver(note.id, changements);
  }

  async function changerCouleur(note, champ, couleur) {
    note[champ] = couleur;
    poserNote(note);
    await sauver(note.id, { [champ]: couleur });
  }

  /** Range les notes en colonnes, dans l'ordre de lecture : le tableau redevient lisible. */
  async function organiser() {
    if (!notes.length) return;
    const triees = [...notes].sort((a, b) => (a.y - b.y) || (a.x - b.x));
    const colonne = 330, pas = 230, hauteurPage = 900;
    let index = 0;
    for (const note of triees) {
      const c = Math.floor(index / Math.ceil(hauteurPage / pas));
      const r = index % Math.ceil(hauteurPage / pas);
      note.x = 40 + c * colonne;
      note.y = 40 + r * pas;
      poserNote(note);
      await sauver(note.id, { x: note.x, y: note.y });
      index += 1;
    }
    vue = { x: 40, y: 40, z: 1 };
    appliquerVue();
  }

  // ================================================================ DOCUMENTS
  function poids(octets) {
    if (octets < 1024) return octets + ' o';
    if (octets < 1024 * 1024) return Math.round(octets / 1024) + ' Ko';
    return (octets / (1024 * 1024)).toFixed(1) + ' Mo';
  }

  function afficherDocuments() {
    const zone = $('#liste-documents');
    zone.innerHTML = '';
    if (!documents.length) {
      zone.append(element('p', { classe: 'vide',
        texte: 'Aucun document pour ce thème.' }));
      return;
    }
    documents.forEach((document) => {
      const ligne = element('div', { classe: 'carte document' });
      poser(ligne,
        element('a', { classe: 'nom', texte: document.nom,
          attrs: { href: `/api/themes/${theme.id}/documents/${document.id}/fichier` } }),
        element('span', { classe: 'meta',
          texte: `${poids(document.taille)} · déposé par ${document.auteur || 'quelqu\'un'} ${quand(document.cree_le)}` }),
        document.note ? element('span', { classe: 'note-doc', texte: document.note }) : null
      );
      const supprimer = element('button', { classe: 'discret danger petit', texte: 'Supprimer' });
      supprimer.addEventListener('click', async () => {
        if (!confirm('Supprimer ce document ?')) return;
        await appel(`/api/themes/${theme.id}/documents/${document.id}`, { methode: 'DELETE' });
      });
      poser(ligne, supprimer);
      zone.append(ligne);
    });
  }

  async function deposerDocuments() {
    const champ = $('#fichier-document');
    if (!champ.files || !champ.files.length) { $('#etat-depot').textContent = 'Choisissez un fichier.'; return; }
    const etat = $('#etat-depot');
    let envoyes = 0;
    for (const fichier of champ.files) {
      const donnees = new FormData();
      donnees.append('fichier', fichier);
      donnees.append('note', $('#note-document').value);
      donnees.append('auteur', monNom() || 'Anonyme');
      etat.textContent = `Envoi de ${fichier.name}…`;
      try {
        await appel(`/api/themes/${theme.id}/documents`, { methode: 'POST', donnees });
        envoyes += 1;
      } catch (erreur) {
        etat.textContent = 'Envoi impossible : ' + erreur.message;
        return;
      }
    }
    champ.value = ''; $('#note-document').value = '';
    etat.textContent = envoyes > 1 ? `${envoyes} documents déposés.` : 'Document déposé.';
  }

  // ================================================================ DÉCISIONS
  function afficherDecisions() {
    const zone = $('#liste-decisions');
    zone.innerHTML = '';
    if (!decisions.length) {
      zone.append(element('p', { classe: 'vide', texte: 'Aucune décision pour ce thème.' }));
      return;
    }
    const ordre = { proposee: 0, 'en attente': 1, adoptee: 2, rejetee: 3 };
    [...decisions].sort((a, b) => (ordre[a.statut] || 0) - (ordre[b.statut] || 0))
      .forEach((decision) => {
        const carte = element('div', { classe: `carte decision ${decision.statut}` });
        poser(carte,
          element('h4', { texte: decision.intitule }),
          decision.detail ? element('p', { classe: 'aide', texte: decision.detail }) : null,
          element('p', { classe: 'meta', texte:
            `Proposée par ${decision.auteur || 'quelqu\'un'} ${quand(decision.cree_le)}` +
            (decision.decide_le ? ` · ${libelle(decision.statut)} ${quand(decision.decide_le)}${decision.decide_par ? ' par ' + decision.decide_par : ''}` : '') })
        );
        const boutons = element('div', { classe: 'barre-boutons' });
        [['adoptee', 'Adopter'], ['rejetee', 'Rejeter'], ['en attente', 'En attente']].forEach(([statut, texte]) => {
          const bouton = element('button', { classe: 'petit ' + (statut === 'adoptee' ? 'principal' : 'discret'),
            texte });
          bouton.addEventListener('click', () => changerStatut(decision, statut));
          boutons.append(bouton);
        });
        const supprimer = element('button', { classe: 'petit discret danger', texte: 'Supprimer' });
        supprimer.addEventListener('click', async () => {
          if (!confirm('Supprimer cette décision ?')) return;
          await appel(`/api/themes/${theme.id}/decisions/${decision.id}`, { methode: 'DELETE' });
        });
        boutons.append(supprimer);
        poser(carte, boutons);
        zone.append(carte);
      });
  }

  function libelle(statut) {
    return { proposee: 'proposée', adoptee: 'adoptée', rejetee: 'rejetée', 'en attente': 'en attente' }[statut] || statut;
  }

  async function changerStatut(decision, statut) {
    await appel(`/api/themes/${theme.id}/decisions/${decision.id}`, { methode: 'PUT',
      corps: { statut, decide_par: monNom() || 'Anonyme' } });
  }

  async function proposerDecision() {
    const intitule = $('#intitule-decision').value.trim();
    if (!intitule) { alert('Écrivez la décision en une phrase.'); return; }
    await appel(`/api/themes/${theme.id}/decisions`, { methode: 'POST',
      corps: { intitule, detail: $('#detail-decision').value.trim(), auteur: monNom() || 'Anonyme' } });
    $('#intitule-decision').value = ''; $('#detail-decision').value = '';
  }

  // ================================================================ OUTILS
  async function afficherOutils() {
    const zone = $('#outils-lies');
    zone.innerHTML = '';
    let projets = [];
    try { projets = (await appel('/api/projets')).projets || []; } catch (e) { projets = []; }
    if (!projets.length) {
      zone.append(element('p', { classe: 'aide', texte:
        'Aucun projet de trames pour le moment : créez-en un dans les outils, puis revenez le relier à ce thème.' }));
    } else {
      const choix = element('select', { classe: 'champ-large' });
      choix.append(element('option', { texte: '— relier ce thème à un projet —', attrs: { value: '' } }));
      projets.forEach((projet) => choix.append(element('option', {
        texte: projet.nom || projet.identifiant, attrs: { value: projet.identifiant } })));
      if (theme && theme.projet) choix.value = theme.projet;
      choix.addEventListener('change', async () => {
        await appel('/api/themes/' + theme.id, { methode: 'PUT', corps: { projet: choix.value } });
        theme.projet = choix.value;
        afficherOutils();
      });
      zone.append(element('p', { classe: 'aide', texte:
        'Le thème peut s\'appuyer sur un projet de trames : c\'est un outil au service de la réflexion.' }), choix);
      const projet = projets.find((p) => p.identifiant === (theme && theme.projet));
      if (projet) {
        zone.append(element('p', { classe: 'meta', texte:
          `Projet relié : ${projet.nom} · ${(projet.metiers || []).length} métier(s) · ` +
          `${(projet.agents || []).length} agent(s)` }));
      }
    }
  }

  // ================================================================ OUTILS DE PAGE
  /** Ajoute des enfants en IGNORANT les vides : `append(null)` écrit « null » dans la page. */
  function poser(parent, ...enfants) {
    enfants.filter(Boolean).forEach((enfant) => parent.append(enfant));
    return parent;
  }

  function element(balise, { classe = '', texte = '', style = '', attrs = {} } = {}) {
    const noeud = document.createElement(balise);
    if (classe) noeud.className = classe;
    if (texte !== '') noeud.textContent = texte;
    if (style) noeud.setAttribute('style', style);
    Object.entries(attrs).forEach(([cle, valeur]) => noeud.setAttribute(cle, valeur));
    return noeud;
  }

  function quand(iso) {
    if (!iso) return '';
    const moment = new Date(iso);
    const minutes = Math.round((Date.now() - moment.getTime()) / 60000);
    if (minutes < 1) return "à l'instant";
    if (minutes < 60) return `il y a ${minutes} min`;
    const heures = Math.round(minutes / 60);
    if (heures < 24) return `il y a ${heures} h`;
    const jours = Math.round(heures / 24);
    return jours === 1 ? 'hier' : `il y a ${jours} jours`;
  }

  // ================================================================ BRANCHEMENTS
  function brancher() {
    $('#mon-nom').value = monNom();
    $('#mon-nom').addEventListener('change', (e) => {
      retenirNom(e.target.value);
      if (theme) brancherFlux();          // on se présente à nouveau aux autres
    });

    $('#btn-nouveau-theme').addEventListener('click', async () => {
      const titre = prompt('Quel est le sujet de réflexion ?');
      if (!titre || !titre.trim()) return;
      const cree = await appel('/api/themes', { methode: 'POST',
        corps: { titre: titre.trim(), auteur: monNom() || 'Anonyme' } });
      await chargerThemes();
      ouvrirTheme(cree.id);
    });

    $('#btn-retour').addEventListener('click', fermerTheme);
    $('#titre-theme').addEventListener('change', enregistrerTheme);
    $('#description-theme').addEventListener('change', enregistrerTheme);
    $('#btn-supprimer-theme').addEventListener('click', async () => {
      if (!confirm('Supprimer ce thème, ses notes, ses documents et ses décisions ?')) return;
      await appel('/api/themes/' + theme.id, { methode: 'DELETE' });
      fermerTheme();
    });

    document.querySelectorAll('.onglets button').forEach((bouton) => {
      bouton.addEventListener('click', () => {
        document.querySelectorAll('.onglets button').forEach((b) => b.classList.toggle('actif', b === bouton));
        document.querySelectorAll('.onglet').forEach((onglet) =>
          onglet.classList.toggle('cache', onglet.id !== 'onglet-' + bouton.dataset.onglet));
      });
    });

    // --- tableau blanc
    $('#btn-note').addEventListener('click', () => creerNote());
    $('#zoom-plus').addEventListener('click', () => { vue.z = Math.min(2.5, vue.z * 1.2); appliquerVue(); });
    $('#zoom-moins').addEventListener('click', () => { vue.z = Math.max(0.3, vue.z / 1.2); appliquerVue(); });
    $('#btn-recentrer').addEventListener('click', () => { vue = { x: 40, y: 40, z: 1 }; appliquerVue(); });
    $('#btn-organiser').addEventListener('click', organiser);

    $('#recherche-notes').addEventListener('input', (e) => {
      const mot = (e.target.value || '').toLowerCase();
      document.querySelectorAll('.note').forEach((noeud) => {
        const note = notes.find((n) => n.id === noeud.dataset.id);
        const dedans = note && (note.texte || '').toLowerCase().includes(mot);
        noeud.classList.toggle('trouvee', Boolean(mot) && dedans);
        noeud.classList.toggle('estompee', Boolean(mot) && !dedans);
      });
    });

    // déplacement du fond + zoom à la molette
    const plateau = $('#plateau');
    plateau.addEventListener('pointerdown', (evenement) => {
      if (evenement.target !== plateau && evenement.target.id !== 'monde') return;
      selectionner(null);
      plateau.setPointerCapture(evenement.pointerId);
      const depart = { x: evenement.clientX, y: evenement.clientY, vx: vue.x, vy: vue.y };
      const bouger = (e) => {
        vue.x = depart.vx + (e.clientX - depart.x);
        vue.y = depart.vy + (e.clientY - depart.y);
        appliquerVue();
      };
      const relacher = () => {
        plateau.removeEventListener('pointermove', bouger);
        plateau.removeEventListener('pointerup', relacher);
      };
      plateau.addEventListener('pointermove', bouger);
      plateau.addEventListener('pointerup', relacher);
    });
    plateau.addEventListener('wheel', (evenement) => {
      evenement.preventDefault();
      if (evenement.ctrlKey || evenement.metaKey) {
        const avant = vue.z;
        vue.z = Math.min(2.5, Math.max(0.3, vue.z * (evenement.deltaY < 0 ? 1.1 : 0.9)));
        const boite = plateau.getBoundingClientRect();
        const x = evenement.clientX - boite.left, y = evenement.clientY - boite.top;
        vue.x = x - (x - vue.x) * (vue.z / avant);
        vue.y = y - (y - vue.y) * (vue.z / avant);
      } else {
        vue.x -= evenement.deltaX; vue.y -= evenement.deltaY;
      }
      appliquerVue();
    }, { passive: false });

    // --- barre de mise en forme
    const pastillesTexte = $('#couleurs-texte');
    COULEURS_TEXTE.forEach((couleur) => {
      const pastille = element('button', { classe: 'pastille', style: `background:${couleur}` });
      pastille.title = 'Couleur du texte';
      pastille.addEventListener('click', () => {
        const note = noteSelectionnee();
        if (note) changerCouleur(note, 'couleur_texte', couleur);
      });
      pastillesTexte.append(pastille);
    });
    const pastillesFond = $('#couleurs-fond');
    COULEURS_FOND.forEach((couleur) => {
      const pastille = element('button', { classe: 'pastille', style: `background:${couleur}` });
      pastille.title = 'Couleur de fond';
      pastille.addEventListener('click', () => {
        const note = noteSelectionnee();
        if (note) changerCouleur(note, 'couleur_fond', couleur);
      });
      pastillesFond.append(pastille);
    });
    document.querySelectorAll('#barre-format [data-format]').forEach((bouton) => {
      bouton.addEventListener('click', () => appliquerFormat(bouton.dataset.format));
    });

    // --- documents et décisions
    $('#btn-deposer').addEventListener('click', deposerDocuments);
    $('#btn-decision').addEventListener('click', proposerDecision);

    // double-clic sur le fond : une note là où l'on a cliqué
    $('#plateau').addEventListener('dblclick', (evenement) => {
      if (evenement.target !== plateau && evenement.target.id !== 'monde') return;
      const boite = plateau.getBoundingClientRect();
      const place = placeLibre(Math.round((evenement.clientX - boite.left - vue.x) / vue.z),
                               Math.round((evenement.clientY - boite.top - vue.y) / vue.z));
      creerNote(place);
    });

    document.addEventListener('keydown', (evenement) => {
      if (evenement.key === 'Escape') selectionner(null);
    });
  }

  // ================================================================ DÉMARRAGE
  async function demarrer() {
    brancher();
    appliquerVue();
    await chargerThemes();
    const cible = (location.hash.match(/#t=(.+)/) || [])[1];
    if (cible) { try { await ouvrirTheme(cible, { pousser: false }); } catch (e) { /* thème inconnu */ } }
  }

  document.addEventListener('DOMContentLoaded', demarrer);
})();
