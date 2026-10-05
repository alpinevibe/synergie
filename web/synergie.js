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
  let journal = [];                      // journal des actions du thème
  let votes = {};                        // décompte des votes par décision
  let mesVotes = [];                     // décisions sur lesquelles j'ai déjà voté
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
    // Le jeton du compte accompagne chaque appel : le serveur sait ainsi qui agit (et
    // retrouve le courriel pour les alertes). Le prénom sert de secours.
    if (monJeton()) options.headers['X-Synergie-Jeton'] = monJeton();
    if (monNom()) options.headers['X-Synergie-Nom'] = monNom();
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
  let compte = null;                     // mon compte (prénom, courriel, notifications)

  function monJeton() { return localStorage.getItem('synergie.jeton') || ''; }
  function retenirJeton(valeur) {
    if (valeur) localStorage.setItem('synergie.jeton', valeur);
  }

  function monNom() {
    if (compte && compte.prenom) return compte.prenom;
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
  // Les onglets ne sont pas les mêmes selon le thème : « Rythme de travail » ouvre sur la
  // boîte à trames, « Fiches de poste » sur les fiches et les codes horaires.
  const ONGLETS = {
    libre: [['tableau', 'Tableau blanc'], ['pages', 'Pages'], ['chat', 'Discussion'],
            ['documents', 'Documents'], ['decisions', 'Décisions'], ['journal', 'Journal']],
    rythme: [['boite', 'Boîte à trames'], ['tableau', 'Tableau blanc'], ['pages', 'Pages'],
             ['chat', 'Discussion'], ['documents', 'Documents'], ['decisions', 'Décisions'],
             ['journal', 'Journal']],
    fiches: [['fiches', 'Fiches de poste'], ['codes', 'Codes horaires'],
             ['tableau', 'Tableau blanc'], ['pages', 'Pages'], ['chat', 'Discussion'],
             ['documents', 'Documents'], ['decisions', 'Décisions'], ['journal', 'Journal']]
  };

  function construireOnglets(type) {
    const barre = $('#onglets-theme');
    barre.innerHTML = '';
    const liste = ONGLETS[type] || ONGLETS.libre;
    liste.forEach(([cle, libelle], rang) => {
      const bouton = element('button', { texte: libelle });
      bouton.dataset.onglet = cle;
      if (rang === 0) bouton.classList.add('actif');
      bouton.addEventListener('click', () => montrerOnglet(cle));
      barre.append(bouton);
    });
    document.querySelectorAll('.onglet').forEach((onglet) => onglet.classList.add('cache'));
    montrerOnglet(liste[0][0]);
  }

  function montrerOnglet(cle) {
    document.querySelectorAll('#onglets-theme button').forEach((bouton) =>
      bouton.classList.toggle('actif', bouton.dataset.onglet === cle));
    document.querySelectorAll('.onglet').forEach((onglet) =>
      onglet.classList.toggle('cache', onglet.id !== 'onglet-' + cle));
    if (cle === 'chat') chargerChatTheme();
    if (cle === 'pages') chargerPages();
    if (cle === 'codes') chargerCodes();
    if (cle === 'fiches') chargerFiches();
    if (cle === 'journal') afficherJournal();
  }

  async function ouvrirTheme(identifiant, { pousser = true } = {}) {
    const donnees = await appel('/api/themes/' + encodeURIComponent(identifiant));
    theme = donnees.theme; notes = donnees.notes || []; decisions = donnees.decisions || [];
    documents = donnees.documents || []; participants = donnees.participants || [];
    journal = donnees.journal || []; votes = donnees.votes || {};
    mesVotes = donnees.mes_votes || [];
    $('#vue-accueil').classList.add('cache');
    $('#vue-theme').classList.remove('cache');
    $('#titre-theme').value = theme.titre || '';
    $('#description-theme').value = theme.description || '';
    afficherParticipants();
    dessinerNotes();
    afficherDocuments();
    afficherDecisions();
    afficherJournal();
    afficherResponsables();
    const fixe = Boolean(theme.fixe);
    $('#btn-supprimer-theme').classList.toggle('cache', fixe);
    $('#zone-responsables').classList.add('cache');
    construireOnglets(theme.type || 'libre');
    chargerChatTheme();
    brancherFlux();
    if (pousser && location.hash !== '#t=' + identifiant) {
      history.replaceState(null, '', '#t=' + identifiant);
    }
  }

  function fermerTheme() {
    if (flux) { flux.close(); flux = null; }
    theme = null; notes = []; decisions = []; documents = []; participants = [];
    journal = []; votes = {}; mesVotes = [];
    $('#vue-theme').classList.add('cache');
    $('#vue-accueil').classList.remove('cache');
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

  /** Après un changement de prénom : journal et « ai-je déjà voté » sont rafraîchis. */
  async function chargerJournalEtVotes() {
    if (!theme) return;
    try {
      const donnees = await appel('/api/themes/' + theme.id);
      journal = donnees.journal || []; votes = donnees.votes || {};
      mesVotes = donnees.mes_votes || [];
      afficherJournal(); afficherDecisions();
    } catch (erreur) { /* sans conséquence */ }
  }

  // ---- flux général : discussion générale et cadre de travail ----
  let fluxGeneral = null;
  function brancherFluxGeneral() {
    if (fluxGeneral) return;
    fluxGeneral = new EventSource('/api/evenements?nom=' + encodeURIComponent(monNom() || 'Anonyme'));
    fluxGeneral.onmessage = (message) => {
      try {
        const evenement = JSON.parse(message.data);
        if (evenement.type === 'message') chargerChatGeneral();
        if (evenement.type === 'cadre') chargerCadre();
      } catch (erreur) { /* événement illisible */ }
    };
    fluxGeneral.onerror = () => { /* le navigateur retente tout seul */ };
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
      case 'journal':
        journal.unshift(evenement.entree);
        if (journal.length > 300) journal.pop();
        afficherJournal();
        break;
      case 'vote':
        votes = Object.assign({}, votes, { [evenement.decision]: evenement.comptes });
        afficherDecisions();
        break;
      case 'message':
        if (evenement.message.theme === theme.id) chargerChatTheme();
        break;
      case 'responsables':
        theme.responsables = evenement.responsables || [];
        afficherResponsables();
        break;
      case 'page_creee':
      case 'page_maj':
      case 'page_supprimee':
        chargerPages();
        if (pageOuverte && evenement.page && pageOuverte.id === evenement.page.id
            && document.activeElement !== $('#page-contenu')) {
          $('#page-contenu').innerHTML = evenement.page.contenu || '';
          pageOuverte = evenement.page;
        }
        break;
      case 'code_horaire':
      case 'code_horaire_supprime':
        chargerCodes();
        break;
      case 'fiche_creee':
      case 'fiche_maj':
      case 'fiche_supprimee':
        chargerFiches();
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
    const auteur = element('span', { classe: 'note-auteur' });
    const crayon = element('button', { classe: 'crayon', texte: '✏️' });
    crayon.title = 'Modifier ce qui est écrit';
    const supprimer = element('button', { classe: 'note-suppr', texte: '×' });
    supprimer.title = 'Supprimer la note';
    poser(barre, auteur, crayon, supprimer);

    const texte = element('div', { classe: 'note-texte' });
    texte.spellcheck = false;
    const poigneeTaille = element('span', { classe: 'poignee-taille' });
    poigneeTaille.title = 'Redimensionner';
    poser(noeud, barre, texte, poigneeTaille);

    let enEdition = false;

    /** On écrit dans la note : le texte devient modifiable (demande du 05/10/2026). */
    function modifier(invitation) {
      enEdition = true;
      texte.contentEditable = 'true';
      noeud.classList.add('en-edition');
      selectionner(note.id);
      envoyerCurseur(note.id);
      texte.focus();
      if (invitation && textoVide(texte)) texte.textContent = '';
      // le curseur se place à la fin du texte existant
      const plage = document.createRange();
      plage.selectNodeContents(texte);
      plage.collapse(false);
      const choix = window.getSelection();
      choix.removeAllRanges();
      choix.addRange(plage);
    }

    /** On arrête d'écrire : la note redevient une note que l'on déplace. */
    function terminer() {
      if (!enEdition) return;
      enEdition = false;
      texte.contentEditable = 'false';
      noeud.classList.remove('en-edition');
      envoyerCurseur(null);
      const courante = notes.find((n) => n.id === note.id);
      if (courante) courante.texte = texte.textContent;
      sauver(note.id, { texte: texte.textContent });
    }

    crayon.addEventListener('click', (evenement) => {
      evenement.stopPropagation();
      if (enEdition) terminer(); else modifier();
    });
    texte.addEventListener('blur', terminer);
    texte.addEventListener('keydown', (evenement) => {
      if (evenement.key === 'Escape') { evenement.preventDefault(); texte.blur(); }
    });
    texte.addEventListener('input', () => {
      const courante = notes.find((n) => n.id === note.id);
      if (courante) courante.texte = texte.textContent;
      programmer(note.id, () => sauver(note.id, { texte: texte.textContent }, 'texte'), 700);
    });

    supprimer.addEventListener('click', (evenement) => {
      evenement.stopPropagation();
      if (!confirm('Supprimer cette note ?')) return;
      appel('/api/themes/' + theme.id + '/notes/' + note.id, { methode: 'DELETE' });
    });

    // ---- déplacer : en cliquant N'IMPORTE OÙ sur la note (hors crayon, croix et coin) ----
    noeud.addEventListener('pointerdown', (evenement) => {
      if (enEdition || evenement.target.closest('.crayon, .note-suppr, .poignee-taille')) return;
      evenement.preventDefault();
      selectionner(note.id);
      noeud.setPointerCapture(evenement.pointerId);
      const depart = { x: evenement.clientX, y: evenement.clientY, ox: note.x, oy: note.y };
      let bouge = false;
      const deplacer = (e) => {
        const dx = (e.clientX - depart.x) / vue.z, dy = (e.clientY - depart.y) / vue.z;
        if (!bouge && Math.abs(dx) + Math.abs(dy) < 3) return;   // simple appui : rien
        bouge = true;
        noeud.classList.add('deplacee');
        note.x = depart.ox + dx;
        note.y = depart.oy + dy;
        noeud.style.left = note.x + 'px';
        noeud.style.top = note.y + 'px';
        programmer('pos-' + note.id, () => sauver(note.id, { x: note.x, y: note.y }), 350);
      };
      const relacher = () => {
        noeud.removeEventListener('pointermove', deplacer);
        noeud.removeEventListener('pointerup', relacher);
        noeud.removeEventListener('pointercancel', relacher);
        noeud.classList.remove('deplacee');
        if (bouge) sauver(note.id, { x: note.x, y: note.y });
      };
      noeud.addEventListener('pointermove', deplacer);
      noeud.addEventListener('pointerup', relacher);
      noeud.addEventListener('pointercancel', relacher);
    });

    // un double-appui écrit directement dans la note
    noeud.addEventListener('dblclick', (evenement) => {
      evenement.stopPropagation();
      if (!enEdition) modifier();
    });

    // ---- redimensionner ----
    poigneeTaille.addEventListener('pointerdown', (evenement) => {
      evenement.preventDefault(); evenement.stopPropagation();
      poigneeTaille.setPointerCapture(evenement.pointerId);
      const depart = { x: evenement.clientX, largeur: note.largeur };
      const etirer = (e) => {
        note.largeur = Math.max(160, depart.largeur + (e.clientX - depart.x) / vue.z);
        noeud.style.width = note.largeur + 'px';
        programmer('larg-' + note.id, () => sauver(note.id, { largeur: note.largeur }), 350);
      };
      const relacher = () => {
        poigneeTaille.removeEventListener('pointermove', etirer);
        poigneeTaille.removeEventListener('pointerup', relacher);
        sauver(note.id, { largeur: note.largeur });
      };
      poigneeTaille.addEventListener('pointermove', etirer);
      poigneeTaille.addEventListener('pointerup', relacher);
    });

    return noeud;
  }

  function textoVide(noeud) { return !(noeud.textContent || '').trim(); }

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
    const crayon = document.querySelector(`.note[data-id="${note.id}"] .crayon`);
    if (crayon) crayon.click();          // la note neuve s'ouvre en écriture
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

        // ---- les votes : tout le monde vote une fois, et les votes sont anonymes ----
        const comptes = votes[decision.id] || { pour: 0, contre: 0, neutre: 0, total: 0 };
        poser(carte, element('div', { classe: 'votes' },
          element('span', { classe: 'etiquette', texte: 'Votes anonymes' }),
          element('span', { classe: 'compteur pour', texte: 'Pour ' + comptes.pour }),
          element('span', { classe: 'compteur contre', texte: 'Contre ' + comptes.contre }),
          element('span', { classe: 'compteur neutre', texte: 'Neutre ' + comptes.neutre }),
          element('span', { classe: 'meta', texte: comptes.total
            ? comptes.total + ' vote(s) — personne ne sait qui a voté quoi'
            : 'aucun vote pour le moment' })));
        if (mesVotes.includes(decision.id)) {
          carte.append(element('p', { classe: 'meta deja-vote',
            texte: '✓ Vous avez voté (votre vote reste anonyme).' }));
        } else {
          const barreVote = element('div', { classe: 'barre-boutons barre-vote' });
          [['pour', 'Pour'], ['contre', 'Contre'], ['neutre', 'Neutre']].forEach(([valeur, mot]) => {
            const bouton = element('button', { classe: 'petit', texte: mot });
            bouton.addEventListener('click', () => voter(decision, valeur));
            barreVote.append(bouton);
          });
          carte.append(barreVote);
        }
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

  /** Vote ANONYME : une seule fois par personne. Le serveur ne garde jamais le nom. */
  async function voter(decision, valeur) {
    try {
      const resultat = await appel(
        `/api/themes/${theme.id}/decisions/${decision.id}/votes`,
        { methode: 'POST', corps: { valeur } });
      if (resultat && resultat.ok) {
        mesVotes = mesVotes.concat([decision.id]);
        votes = Object.assign({}, votes, { [decision.id]: resultat.comptes });
        afficherDecisions();
      }
    } catch (erreur) {
      alert(erreur.message || 'Le vote n\'a pas pu être enregistré.');
    }
  }

  const ACTIONS = {
    theme_cree: 'a créé le thème', theme_modifie: 'a modifié le thème',
    note_creee: 'a écrit une note', note_modifiee: 'a modifié une note',
    note_deplacee: 'a déplacé une note', note_supprimee: 'a supprimé une note',
    decision_proposee: 'a proposé une décision', decision_modifiee: 'a modifié une décision',
    decision_tranchee: 'a tranché une décision', decision_supprimee: 'a supprimé une décision',
    vote: 'a voté', document_depose: 'a déposé un document',
    document_supprime: 'a supprimé un document', arrivee: 'est arrivé dans le thème'
  };

  function afficherJournal() {
    const zone = $('#liste-journal');
    if (!zone) return;
    zone.innerHTML = '';
    if (!journal.length) {
      zone.append(element('p', { classe: 'vide', texte: 'Aucune action enregistrée pour le moment.' }));
      return;
    }
    journal.forEach((entree) => {
      poser(zone, element('div', { classe: 'carte entree-journal' },
        element('span', { classe: 'qui', texte: entree.qui || 'Quelqu\'un' }),
        element('span', { classe: 'quoi', texte: ACTIONS[entree.action] || entree.action }),
        entree.details ? element('span', { classe: 'details', texte: '« ' + entree.details + ' »' }) : null,
        element('span', { classe: 'quand', texte: quand(entree.quand) })));
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

  // ================================================================ MON COMPTE
  // Chaque personne a un compte enregistré sur le serveur (prénom + courriel). Le jeton
  // gardé par le navigateur permet de le retrouver, et le courriel sert aux alertes.

  async function creerMonCompte() {
    const prenom = ($('#prenom').value || '').trim();
    if (!prenom) { $('#prenom').classList.add('manquant'); $('#prenom').focus(); return false; }
    const donnees = await appel('/api/comptes', { methode: 'POST', corps: {
      prenom,
      email: ($('#email-compte').value || '').trim(),
      notifier_tout: $('#notifier-tout').checked,
      jeton: monJeton() || null } });
    compte = donnees.compte;
    retenirJeton(donnees.jeton);
    retenirNom(compte.prenom);
    return true;
  }

  async function chargerMonCompte() {
    if (!monJeton()) return null;
    try {
      const donnees = await appel('/api/comptes/moi');
      compte = donnees.compte;
      compte.abonnements = donnees.abonnements || [];
      compte.responsable_de = donnees.responsable_de || [];
      if (compte && compte.prenom) retenirNom(compte.prenom);
      return compte;
    } catch (erreur) {
      localStorage.removeItem('synergie.jeton');       // jeton périmé : on redemandera
      return null;
    }
  }

  async function ouvrirMonCompte() {
    if (!compte) { demanderPrenom(); return; }
    $('#c-prenom').value = compte.prenom || '';
    $('#c-email').value = compte.email || '';
    $('#c-tout').checked = Boolean(compte.notifier_tout);
    await chargerListeAbonnements();
    $('#c-etat').textContent = compte.responsable_de && compte.responsable_de.length
      ? 'Vous êtes responsable de ' + compte.responsable_de.length + ' thème(s).'
      : '';
    $('#vue-compte').classList.remove('cache');
  }

  async function chargerListeAbonnements() {
    const zone = $('#c-abonnements');
    zone.innerHTML = '';
    let liste = themes;
    if (!liste.length) {
      const donnees = await appel('/api/themes');
      liste = donnees.themes || [];
    }
    const abonnes = new Set(compte.abonnements || []);
    liste.forEach((theme) => {
      const ligne = element('label', { classe: 'case' });
      const case_ = element('input', { attrs: { type: 'checkbox' } });
      case_.checked = abonnes.has(theme.id);
      case_.dataset.theme = theme.id;
      poser(ligne, case_, element('span', { texte: theme.titre }));
      zone.append(ligne);
    });
    if (!liste.length) zone.append(element('p', { classe: 'aide', texte: 'Aucun thème.' }));
  }

  async function enregistrerMonCompte() {
    const abonnements = [...document.querySelectorAll('#c-abonnements input:checked')]
      .map((c) => c.dataset.theme);
    try {
      const donnees = await appel('/api/comptes/moi', { methode: 'PUT', corps: {
        prenom: $('#c-prenom').value.trim(), email: $('#c-email').value.trim(),
        notifier_tout: $('#c-tout').checked, abonnements } });
      compte = Object.assign(compte, donnees.compte);
      compte.abonnements = donnees.abonnements;
      compte.responsable_de = donnees.responsable_de;
      retenirNom(compte.prenom);
      $('#c-etat').textContent = 'Enregistré.';
      if (theme) brancherFlux();
    } catch (erreur) {
      $('#c-etat').textContent = 'Enregistrement impossible : ' + erreur.message;
    }
  }

  // ================================================================ CADRE DE TRAVAIL
  async function chargerCadre() {
    try {
      const cadre = await appel('/api/cadre');
      if (document.activeElement !== $('#cadre-contexte')) {
        $('#cadre-contexte').value = cadre.contexte || '';
      }
      $('#cadre-etat').textContent = cadre.maj_le
        ? 'Dernière modification par ' + (cadre.maj_par || 'quelqu\'un') + ' ' + quand(cadre.maj_le)
        : '';
      const donnees = await appel('/api/cadre/documents');
      afficherComptesRendus(donnees.documents || []);
    } catch (erreur) { /* sans conséquence */ }
  }

  function afficherComptesRendus(documents) {
    const zone = $('#cadre-documents');
    zone.innerHTML = '';
    if (!documents.length) {
      zone.append(element('p', { classe: 'aide', texte: 'Aucun compte rendu déposé.' }));
      return;
    }
    documents.forEach((document) => {
      const ligne = element('div', { classe: 'carte document' });
      poser(ligne,
        element('a', { classe: 'nom', texte: document.nom,
          attrs: { href: `/api/cadre/documents/${document.id}/fichier` } }),
        element('span', { classe: 'meta', texte:
          `${poids(document.taille)} · déposé par ${document.auteur || 'quelqu\'un'} ${quand(document.cree_le)}` }),
        document.note ? element('span', { classe: 'note-doc', texte: document.note }) : null);
      const supprimer = element('button', { classe: 'discret danger petit', texte: 'Supprimer' });
      supprimer.addEventListener('click', async () => {
        if (!confirm('Supprimer ce document ?')) return;
        await appel(`/api/cadre/documents/${document.id}`, { methode: 'DELETE' });
        chargerCadre();
      });
      poser(ligne, supprimer);
      zone.append(ligne);
    });
  }

  async function enregistrerCadre() {
    $('#cadre-etat').textContent = 'Enregistrement…';
    await appel('/api/cadre', { methode: 'PUT', corps: { contexte: $('#cadre-contexte').value } });
    await chargerCadre();
  }

  async function deposerComptesRendus() {
    const champ = $('#cadre-fichier');
    if (!champ.files || !champ.files.length) {
      $('#cadre-depot-etat').textContent = 'Choisissez un fichier.';
      return;
    }
    for (const fichier of champ.files) {
      const donnees = new FormData();
      donnees.append('fichier', fichier);
      donnees.append('note', $('#cadre-note').value);
      donnees.append('auteur', monNom() || 'Anonyme');
      $('#cadre-depot-etat').textContent = 'Envoi de ' + fichier.name + '…';
      await appel('/api/cadre/documents', { methode: 'POST', donnees });
    }
    champ.value = ''; $('#cadre-note').value = '';
    $('#cadre-depot-etat').textContent = 'Document(s) déposé(s).';
    chargerCadre();
  }

  // ================================================================ DISCUSSIONS
  // Un chat général (tout le projet) et un chat par thème. Les messages arrivent en direct.

  function afficherFil(zone, messages, sujet) {
    const proche = zone.scrollHeight - zone.scrollTop - zone.clientHeight < 80;
    zone.innerHTML = '';
    if (!messages.length) {
      zone.append(element('p', { classe: 'aide', texte: 'Aucun message pour le moment.' }));
      return;
    }
    messages.forEach((message) => {
      const ligne = element('div', { classe: 'message' + (message.qui === monNom() ? ' moi' : '') });
      poser(ligne,
        element('span', { classe: 'qui', texte: message.qui || 'Quelqu\'un' }),
        element('span', { classe: 'texte', texte: message.texte }),
        element('span', { classe: 'quand', texte: quand(message.cree_le) }));
      zone.append(ligne);
    });
    if (proche) zone.scrollTop = zone.scrollHeight;
  }

  async function chargerChatGeneral() {
    try {
      const donnees = await appel('/api/messages');
      afficherFil($('#chat-general'), donnees.messages || []);
    } catch (erreur) { /* sans conséquence */ }
  }

  async function chargerChatTheme() {
    if (!theme) return;
    try {
      const donnees = await appel('/api/themes/' + theme.id + '/messages');
      afficherFil($('#fil-theme'), donnees.messages || []);
    } catch (erreur) { /* sans conséquence */ }
  }

  async function envoyerChat(themeId, champ, recharger) {
    const texte = (champ.value || '').trim();
    if (!texte) return;
    champ.value = '';
    const chemin = themeId ? `/api/themes/${themeId}/messages` : '/api/messages';
    try {
      await appel(chemin, { methode: 'POST', corps: { texte } });
      await recharger();
    } catch (erreur) { alert('Message non envoyé : ' + erreur.message); }
  }

  // ================================================================ PAGES DE TRAVAIL
  let pages = [];
  let pageOuverte = null;
  let minuteurPage = null;

  async function chargerPages() {
    if (!theme) return;
    const donnees = await appel('/api/themes/' + theme.id + '/pages');
    pages = donnees.pages || [];
    afficherPages();
  }

  function afficherPages() {
    const zone = $('#liste-pages');
    zone.innerHTML = '';
    if (!pages.length) {
      zone.append(element('p', { classe: 'aide',
        texte: 'Aucune page pour le moment. Créez-en une : c\'est une page blanche à remplir.' }));
      return;
    }
    pages.forEach((page) => {
      const carte = element('div', { classe: 'carte page-carte'
        + (pageOuverte && pageOuverte.id === page.id ? ' ouverte' : '') });
      poser(carte,
        element('h4', { texte: page.titre }),
        element('p', { classe: 'meta', texte:
          (page.auteur ? 'créée par ' + page.auteur + ' · ' : '') + quand(page.maj_le) }));
      carte.addEventListener('click', () => ouvrirPage(page.id));
      zone.append(carte);
    });
  }

  async function creerPage() {
    const titre = ($('#nouvelle-page-titre').value || '').trim() || 'Page sans titre';
    const page = await appel('/api/themes/' + theme.id + '/pages',
      { methode: 'POST', corps: { titre } });
    $('#nouvelle-page-titre').value = '';
    pages.unshift({ id: page.id, theme: page.theme, titre: page.titre, auteur: page.auteur,
                    cree_le: page.cree_le, maj_le: page.maj_le });
    afficherPages();
    ouvrirPage(page.id);
  }

  async function ouvrirPage(identifiant) {
    const page = await appel('/api/themes/' + theme.id + '/pages/' + identifiant);
    pageOuverte = page;
    $('#page-editeur').classList.remove('cache');
    $('#page-titre').value = page.titre;
    $('#page-contenu').innerHTML = page.contenu || '';
    $('#page-etat').textContent = 'Modifiée ' + quand(page.maj_le);
    afficherPages();
  }

  async function enregistrerPage(silencieux) {
    if (!pageOuverte) return;
    try {
      await appel('/api/themes/' + theme.id + '/pages/' + pageOuverte.id, { methode: 'PUT',
        corps: { titre: $('#page-titre').value.trim() || 'Page sans titre',
                 contenu: $('#page-contenu').innerHTML } });
      if (!silencieux) $('#page-etat').textContent = 'Enregistrée.';
      const dansListe = pages.find((p) => p.id === pageOuverte.id);
      if (dansListe) { dansListe.titre = $('#page-titre').value.trim(); }
      afficherPages();
    } catch (erreur) {
      $('#page-etat').textContent = 'Enregistrement impossible : ' + erreur.message;
    }
  }

  function programmerPage() {
    clearTimeout(minuteurPage);
    $('#page-etat').textContent = 'Modifications en cours…';
    minuteurPage = setTimeout(() => enregistrerPage(true), 1500);
  }

  function mettreEnForme(ordre) {
    const [commande, valeur] = ordre.split(':');
    document.execCommand(commande, false, valeur || null);
    $('#page-contenu').focus();
    programmerPage();
  }

  // ================================================================ CODES HORAIRES
  async function chargerCodes() {
    if (!theme) return;
    const donnees = await appel('/api/themes/' + theme.id + '/codes');
    afficherCodes(donnees.codes || []);
  }

  function afficherCodes(codes) {
    const zone = $('#liste-codes');
    zone.innerHTML = '';
    codes.forEach((code) => {
      const ligne = element('div', { classe: 'ligne-code' });
      const pastille = element('span', { classe: 'case-code',
        style: `background:${code.couleur || '#eef1f6'}` , texte: code.code });
      const champs = element('div', { classe: 'champs-code' });
      const saisies = {};
      [['libelle', 'Libellé', code.libelle], ['debut', 'Début', code.debut],
       ['fin', 'Fin', code.fin]].forEach(([cle, etiquette, valeur]) => {
        const champ = element('input', { classe: 'champ-court' });
        champ.value = valeur || '';
        champ.placeholder = etiquette;
        saisies[cle] = champ;
        champs.append(champ);
      });
      const definition = element('input', { classe: 'champ-long' });
      definition.value = code.definition || '';
      definition.placeholder = 'À quoi correspond ce code dans la journée ?';
      saisies.definition = definition;
      const duree = element('span', { classe: 'meta', texte: code.duree_min
        ? (code.duree_min / 60).toFixed(1).replace('.', ',') + ' h' : '—' });
      const enregistrer = element('button', { classe: 'discret petit', texte: 'Enregistrer' });
      enregistrer.addEventListener('click', async () => {
        await appel('/api/themes/' + theme.id + '/codes', { methode: 'POST', corps: {
          code: code.code, libelle: saisies.libelle.value, debut: saisies.debut.value,
          fin: saisies.fin.value, definition: saisies.definition.value,
          couleur: code.couleur, ordre: code.ordre } });
        chargerCodes();
      });
      const supprimer = element('button', { classe: 'discret danger petit', texte: 'Supprimer' });
      supprimer.addEventListener('click', async () => {
        if (!confirm('Supprimer le code ' + code.code + ' ?')) return;
        await appel('/api/themes/' + theme.id + '/codes/' + code.id, { methode: 'DELETE' });
        chargerCodes();
      });
      poser(zone, pastille, champs, definition, duree, enregistrer, supprimer);
      zone.append(element('div', { classe: 'separateur' }));
    });
    if (!codes.length) zone.append(element('p', { classe: 'aide', texte: 'Aucun code défini.' }));
  }

  async function ajouterCode() {
    const code = prompt('Nouveau code horaire (par exemple M03, S03, une lettre…)');
    if (!code) return;
    const libelle = prompt('Que veut dire ce code ? (par exemple « Matin »)') || '';
    const debut = prompt('Heure de début (par exemple 06:30) — laissez vide si sans objet') || '';
    const fin = prompt('Heure de fin (par exemple 14:00)') || '';
    await appel('/api/themes/' + theme.id + '/codes', { methode: 'POST',
      corps: { code, libelle, debut, fin } });
    chargerCodes();
  }

  // ================================================================ FICHES DE POSTE
  async function chargerFiches() {
    if (!theme) return;
    const donnees = await appel('/api/themes/' + theme.id + '/fiches');
    afficherFiches(donnees.fiches || []);
  }

  function afficherFiches(fiches) {
    const zone = $('#liste-fiches');
    zone.innerHTML = '';
    if (!fiches.length) {
      zone.append(element('p', { classe: 'aide', texte:
        'Aucune fiche pour le moment. Créez la première : elle se remplira tâche par tâche, tranche horaire par tranche horaire.' }));
      return;
    }
    fiches.forEach((fiche) => zone.append(carteFiche(fiche)));
  }

  function carteFiche(fiche) {
    const carte = element('div', { classe: 'carte fiche ' + fiche.statut });
    poser(carte,
      element('div', { classe: 'entete-fiche' },
        element('h3', { texte: fiche.intitule }),
        element('span', { classe: 'statut ' + fiche.statut, texte: fiche.statut_libelle })),
      element('p', { classe: 'meta', texte:
        (fiche.profession ? fiche.profession + ' · ' : '') + 'version ' + fiche.version +
        (fiche.auteur ? ' · ouverte par ' + fiche.auteur : '') + ' · ' + quand(fiche.maj_le) }));

    if (fiche.finalite) {
      carte.append(element('p', { classe: 'finalite', texte: fiche.finalite }));
    }

    // La charge par code horaire : combien de temps est prévu sur chaque tranche.
    if (fiche.charge_par_code && fiche.charge_par_code.length) {
      const charges = element('div', { classe: 'charges' });
      fiche.charge_par_code.forEach((charge) => {
        charges.append(element('span', { classe: 'charge', texte:
          charge.code + ' : ' + (charge.minutes / 60).toFixed(1).replace('.', ',') + ' h' }));
      });
      carte.append(element('p', { classe: 'etiquette', texte: 'Temps prévu par code horaire' }), charges);
    }

    // Le tableau des tâches, une ligne par tâche.
    const table = element('table', { classe: 'table-taches' });
    const entete = element('tr');
    ['Code', 'Tâche', 'Début', 'Fin', 'Durée', 'Fréquence', 'Qui', 'Remarque', ''].forEach((titre) => {
      entete.append(element('th', { texte: titre }));
    });
    table.append(entete);
    (fiche.taches || []).forEach((tache) => table.append(ligneTache(fiche, tache)));
    carte.append(table);

    const barre = element('div', { classe: 'barre-boutons' });
    const ajouter = element('button', { classe: 'discret petit', texte: '+ Ajouter une tâche' });
    ajouter.addEventListener('click', async () => {
      await appel(`/api/themes/${theme.id}/fiches/${fiche.id}/taches`, { methode: 'POST',
        corps: { libelle: 'Nouvelle tâche', code: (fiche.taches[0] || {}).code || '' } });
      chargerFiches();
    });
    const dupliquer = element('button', { classe: 'discret petit', texte: 'Dupliquer (nouvelle version)' });
    dupliquer.addEventListener('click', async () => {
      await appel(`/api/themes/${theme.id}/fiches/${fiche.id}/dupliquer`, { methode: 'POST' });
      chargerFiches();
    });
    const supprimer = element('button', { classe: 'discret danger petit', texte: 'Supprimer' });
    supprimer.addEventListener('click', async () => {
      if (!confirm('Supprimer cette fiche et ses tâches ?')) return;
      await appel(`/api/themes/${theme.id}/fiches/${fiche.id}`, { methode: 'DELETE' });
      chargerFiches();
    });
    poser(barre, ajouter, dupliquer, supprimer);
    carte.append(barre);

    // La validation : à l'étude → proposée → validée.
    const statuts = element('div', { classe: 'barre-boutons' });
    statuts.append(element('span', { classe: 'etiquette', texte: 'État de la fiche' }));
    [['a_l_etude', 'À l\'étude'], ['proposee', 'Proposer'], ['validee', 'Valider']].forEach(([valeur, mot]) => {
      const bouton = element('button', { classe: 'petit ' + (valeur === 'validee' ? 'principal' : ''),
        texte: mot });
      bouton.addEventListener('click', async () => {
        await appel(`/api/themes/${theme.id}/fiches/${fiche.id}`, { methode: 'PUT',
          corps: { statut: valeur } });
        chargerFiches();
      });
      statuts.append(bouton);
    });
    if (fiche.statut === 'validee' && fiche.validee_par) {
      statuts.append(element('span', { classe: 'meta', texte:
        'validée par ' + fiche.validee_par + ' ' + quand(fiche.validee_le) }));
    }
    carte.append(statuts);
    return carte;
  }

  function ligneTache(fiche, tache) {
    const ligne = element('tr');
    const champ = (cle, valeur, classe) => {
      const noeud = element('input', { classe: classe || 'champ-court' });
      noeud.value = valeur || '';
      noeud.dataset.cle = cle;
      return noeud;
    };
    const code = element('input', { classe: 'champ-code' });
    code.value = tache.code || '';
    code.title = 'Code horaire (M03, S03, J13, N02…)';
    const libelle = champ('libelle', tache.libelle, 'champ-long');
    const debut = champ('debut', tache.debut);
    const fin = champ('fin', tache.fin);
    const duree = element('span', { classe: 'meta', texte: tache.duree_min
      ? (tache.duree_min / 60).toFixed(1).replace('.', ',') + ' h' : '—' });
    const periodicite = champ('periodicite', tache.periodicite);
    const qui = champ('qui', tache.qui);
    const remarque = champ('remarque', tache.remarque, 'champ-long');
    const actions = element('td');
    const enregistrer = element('button', { classe: 'discret petit', texte: '✓' });
    enregistrer.title = 'Enregistrer cette tâche';
    enregistrer.addEventListener('click', async () => {
      await appel(`/api/themes/${theme.id}/fiches/${fiche.id}/taches/${tache.id}`, { methode: 'PUT',
        corps: { code: code.value, libelle: libelle.value, debut: debut.value, fin: fin.value,
                 periodicite: periodicite.value, qui: qui.value, remarque: remarque.value } });
      chargerFiches();
    });
    const supprimer = element('button', { classe: 'discret danger petit', texte: '×' });
    supprimer.title = 'Supprimer cette tâche';
    supprimer.addEventListener('click', async () => {
      await appel(`/api/themes/${theme.id}/fiches/${fiche.id}/taches/${tache.id}`,
        { methode: 'DELETE' });
      chargerFiches();
    });
    poser(actions, enregistrer, supprimer);
    [element('td', {}, code), element('td', {}, libelle), element('td', {}, debut),
     element('td', {}, fin), element('td', {}, duree), element('td', {}, periodicite),
     element('td', {}, qui), element('td', {}, remarque), actions].forEach((cellule) => {
      ligne.append(cellule);
    });
    return ligne;
  }

  async function creerFiche() {
    const intitule = ($('#fiche-intitule').value || '').trim();
    if (!intitule) { alert('Donnez un intitulé à la fiche.'); return; }
    await appel('/api/themes/' + theme.id + '/fiches', { methode: 'POST', corps: {
      profession: $('#fiche-profession').value, intitule } });
    $('#fiche-intitule').value = '';
    chargerFiches();
  }

  // ================================================================ RESPONSABLES
  async function ouvrirResponsables() {
    const zone = $('#liste-comptes');
    zone.innerHTML = '';
    $('#zone-responsables').classList.remove('cache');
    let comptes = [];
    try { comptes = (await appel('/api/comptes')).comptes || []; } catch (e) { comptes = []; }
    const actuels = new Set(((theme && theme.responsables) || []).map((r) => r.id));
    if (!comptes.length) {
      zone.append(element('p', { classe: 'aide', texte:
        'Personne n\'a encore créé son compte : chacun doit entrer son prénom et son courriel à l\'ouverture de Synergie.' }));
      return;
    }
    comptes.forEach((compte_) => {
      const ligne = element('label', { classe: 'case' });
      const case_ = element('input', { attrs: { type: 'checkbox' } });
      case_.checked = actuels.has(compte_.id);
      case_.dataset.compte = compte_.id;
      poser(ligne, case_, element('span', { texte:
        compte_.prenom + (compte_.email ? ' — ' + compte_.email : ' (sans courriel : aucune alerte)') }));
      zone.append(ligne);
    });
  }

  async function enregistrerResponsables() {
    const comptes = [...document.querySelectorAll('#liste-comptes input:checked')]
      .map((c) => c.dataset.compte);
    const donnees = await appel('/api/themes/' + theme.id + '/responsables',
      { methode: 'PUT', corps: { comptes } });
    theme.responsables = donnees.responsables || [];
    afficherResponsables();
    $('#zone-responsables').classList.add('cache');
  }

  function afficherResponsables() {
    const zone = $('#responsables');
    const liste = (theme && theme.responsables) || [];
    zone.textContent = liste.length ? liste.map((r) => r.prenom).join(' · ') : 'personne';
  }

  // ================================================================ OUTILS DE PAGE
  /** Ajoute des enfants en IGNORANT les vides : `append(null)` écrit « null » dans la page. */
  function poser(parent, ...enfants) {
    enfants.filter(Boolean).forEach((enfant) => parent.append(enfant));
    return parent;
  }

  function element(balise, { classe = '', texte = '', style = '', attrs = {} } = {}, ...enfants) {
    const noeud = document.createElement(balise);
    if (classe) noeud.className = classe;
    if (texte !== '') noeud.textContent = texte;
    if (style) noeud.setAttribute('style', style);
    Object.entries(attrs).forEach(([cle, valeur]) => noeud.setAttribute(cle, valeur));
    poser(noeud, ...enfants);
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
    $('#btn-compte').addEventListener('click', ouvrirMonCompte);
    $('#c-enregistrer').addEventListener('click', enregistrerMonCompte);
    $('#c-fermer').addEventListener('click', () => $('#vue-compte').classList.add('cache'));
    $('#c-essai').addEventListener('click', async () => {
      $('#c-etat').textContent = 'Envoi de l\'essai…';
      try {
        const resultat = await appel('/api/alertes/essai', { methode: 'POST', corps: {} });
        $('#c-etat').textContent = resultat.envoye
          ? 'Essai envoyé à ' + resultat.email + '.'
          : 'L\'envoi n\'a pas abouti (voir le journal des alertes).';
      } catch (erreur) { $('#c-etat').textContent = 'Essai impossible : ' + erreur.message; }
    });

    $('#cadre-enregistrer').addEventListener('click', enregistrerCadre);
    $('#cadre-deposer').addEventListener('click', deposerComptesRendus);
    $('#chat-general-form').addEventListener('submit', (evenement) => {
      evenement.preventDefault();
      envoyerChat('', $('#chat-general-texte'), chargerChatGeneral);
    });
    $('#chat-theme-form').addEventListener('submit', (evenement) => {
      evenement.preventDefault();
      envoyerChat(theme ? theme.id : null, $('#chat-theme-texte'), chargerChatTheme);
    });
    $('#btn-page').addEventListener('click', creerPage);
    $('#page-enregistrer').addEventListener('click', () => enregistrerPage(false));
    $('#page-titre').addEventListener('input', programmerPage);
    $('#page-contenu').addEventListener('input', programmerPage);
    $('#page-supprimer').addEventListener('click', async () => {
      if (!pageOuverte || !confirm('Supprimer cette page ?')) return;
      await appel('/api/themes/' + theme.id + '/pages/' + pageOuverte.id, { methode: 'DELETE' });
      pageOuverte = null;
      $('#page-editeur').classList.add('cache');
      chargerPages();
    });
    document.querySelectorAll('[data-edition]').forEach((bouton) => {
      bouton.addEventListener('click', () => mettreEnForme(bouton.dataset.edition));
    });
    $('#btn-code').addEventListener('click', ajouterCode);
    $('#btn-fiche').addEventListener('click', creerFiche);
    $('#btn-responsables').addEventListener('click', ouvrirResponsables);
    $('#responsables-enregistrer').addEventListener('click', enregistrerResponsables);
    $('#responsables-fermer').addEventListener('click', () =>
      $('#zone-responsables').classList.add('cache'));


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
  /** À l'ouverture : on demande le prénom (demande du 05/10/2026). Tant qu'il n'est pas
      donné, on n'entre pas dans l'atelier — car toute action est journalisée. */
  function demanderPrenom() {
    const voile = $('#accueil-nom');
    const champ = $('#prenom');
    voile.classList.remove('cache');
    setTimeout(() => champ.focus(), 200);

    async function valider() {
      try {
        const pret = await creerMonCompte();
        if (!pret) return;
      } catch (erreur) {
        $('#btn-prenom').textContent = 'Réessayer';
        alert('Compte non créé : ' + erreur.message);
        return;
      }
      voile.classList.add('cache');
      entrerDansLAtelier();
    }
    $('#btn-prenom').addEventListener('click', valider);
    [champ, $('#email-compte')].forEach((noeud) => noeud.addEventListener('keydown', (evenement) => {
      if (evenement.key === 'Enter') valider();
    }));
    champ.addEventListener('input', () => champ.classList.remove('manquant'));
  }

  async function entrerDansLAtelier() {
    await chargerThemes();
    chargerCadre();
    chargerChatGeneral();
    brancherFluxGeneral();
    const cible = (location.hash.match(/#t=(.+)/) || [])[1];
    if (cible) { try { await ouvrirTheme(cible, { pousser: false }); } catch (e) { /* inconnu */ } }
  }

  async function demarrer() {
    brancher();
    appliquerVue();
    await chargerMonCompte();                      // le compte d'abord
    if (!compte || !compte.prenom) { demanderPrenom(); return; }
    await entrerDansLAtelier();
  }

  document.addEventListener('DOMContentLoaded', demarrer);
})();
