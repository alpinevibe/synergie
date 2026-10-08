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
  let projets = [];                      // mes projets
  let projet = null;                     // projet ouvert
  let roleProjet = null;                 // mon rôle dans le projet (admin / membre / visiteur)
  let roleTheme = null;                  // mon rôle dans le groupe ouvert
  let roles = [];                        // les rôles possibles (libellés du serveur)
  let membresProjet = [];
  let membresTheme = [];
  let fluxGeneral = null;                // flux temps réel du projet
  let groupes = [];                      // groupes du projet
  let themes = [];                       // groupes du projet (même liste)
  let theme = null;                      // groupe ouvert
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

  // ================================================================ MES PROJETS
  /** Ce que le navigateur peut dire du poste de travail. Un site web n'a pas le droit de
      lire l'identifiant de session Windows : on enregistre donc ce qui est accessible
      (navigateur, appareil, écran, langue, fuseau) — la personne peut le corriger. */
  function posteDetecte() {
    const ua = navigator.userAgent;
    const systeme = /Windows/.test(ua) ? 'Windows' : /Mac OS/.test(ua) ? 'macOS'
      : /Android/.test(ua) ? 'Android' : /iPhone|iPad/.test(ua) ? 'iOS'
      : /Linux/.test(ua) ? 'Linux' : 'appareil inconnu';
    const navigateur = /Edg\//.test(ua) ? 'Edge' : /Chrome\//.test(ua) ? 'Chrome'
      : /Safari\//.test(ua) ? 'Safari' : /Firefox\//.test(ua) ? 'Firefox' : 'navigateur';
    return `${systeme} · ${navigateur}`;
  }

  function appareilDetecte() {
    return [navigator.userAgent, `${screen.width}×${screen.height}`,
            navigator.language, Intl.DateTimeFormat().resolvedOptions().timeZone].join(' | ');
  }

  async function chargerProjets() {
    const donnees = await appel('/api/projets');
    projets = donnees.projets || [];
    roles = donnees.roles || [];
    afficherProjets();
    const choix = $('#choix-projet');
    choix.innerHTML = '';
    projets.forEach((p) => {
      choix.append(element('option', { texte: p.nom, attrs: { value: p.id } }));
    });
    return projets;
  }

  function afficherProjets() {
    const zone = $('#liste-projets');
    zone.innerHTML = '';
    $('#bloc-nouveau-projet').classList.remove('cache');
    $('#projets-vide').classList.toggle('cache', projets.length > 0);
    projets.forEach((p) => {
      const carte = element('button', { classe: 'carte-theme',
        style: `--teinte:${p.couleur || '#4a6cf7'}` });
      poser(carte,
        element('h3', { texte: p.nom }),
        element('p', { classe: 'aide', texte: p.description || 'Pas encore de description.' }),
        element('p', { classe: 'compteurs', texte:
          `${p.groupes} groupe(s) · ${p.membres} membre(s)` }),
        element('span', { classe: 'etiquette-role', texte: p.libelle_role || p.role || '' }));
      carte.addEventListener('click', () => ouvrirProjet(p.id));
      zone.append(carte);
    });
  }

  /** Ouvre un projet : son cadre, ses groupes, ses membres, sa discussion. */
  async function ouvrirProjet(identifiant, { pousser = true } = {}) {
    const donnees = await appel('/api/projets/' + encodeURIComponent(identifiant));
    projet = donnees.projet;
    roleProjet = donnees.role;
    groupes = donnees.groupes || [];
    themes = groupes;
    membresProjet = donnees.membres || [];
    localStorage.setItem('synergie.projet', identifiant);
    if (fluxGeneral) { fluxGeneral.close(); fluxGeneral = null; }
    afficherVue('projet');
    $('#choix-projet').value = identifiant;
    $('#nom-projet').textContent = projet.nom;
    $('#description-projet').textContent = projet.description || '';
    $('#mon-role-projet').textContent = libelleRole(roleProjet);
    const administre = roleProjet === 'admin';
    $('#btn-renommer-projet').classList.toggle('cache', !administre);
    $('#btn-nouveau-theme').classList.toggle('cache', !administre);
    $('#nouveau-theme-bloc').classList.add('cache');
    afficherThemes();
    afficherMembresProjet();
    chargerCadre();
    chargerChatGeneral();
    brancherFluxGeneral();
    if (pousser && location.hash !== '#p=' + identifiant) {
      history.replaceState(null, '', '#p=' + identifiant);
    }
  }

  function libelleRole(role) {
    const trouve = roles.find((r) => r.cle === role);
    return trouve ? trouve.libelle : (role || '');
  }

  function estAdministrateurTheme() {
    return roleTheme === 'admin' || (roleTheme === null && roleProjet === 'admin');
  }

  // ================================================================ LES GROUPES DE TRAVAIL
  async function chargerThemes() {
    const donnees = await appel('/api/themes'
      + (projet ? '?projet=' + encodeURIComponent(projet.id) : ''));
    themes = donnees.themes || [];
    groupes = themes;
    afficherThemes();
  }

  /** Les groupes du projet : une tuile par groupe, avec ses compteurs. */
  function afficherThemes() {
    const zone = $('#liste-themes');
    zone.innerHTML = '';
    if (!themes.length) {
      zone.append(element('p', { classe: 'vide',
        texte: 'Aucun groupe pour le moment.' }));
      return;
    }
    themes.forEach((t) => {
      const carte = element('button', { classe: 'carte-theme',
        style: `--teinte:${t.couleur || '#4a6cf7'}` });
      const parties = [element('h3', { texte: t.titre })];
      if (t.description) parties.push(element('p', { classe: 'aide', texte: t.description }));
      parties.push(element('p', { classe: 'compteurs', texte:
        `${t.notes} note(s) · ${t.decisions} décision(s) · ${t.documents} document(s)` }));
      parties.push(element('p', { classe: 'quand', texte: quand(t.maj_le) }));
      poser(carte, ...parties);
      carte.addEventListener('click', () => ouvrirTheme(t.id));
      zone.append(carte);
    });
  }

  async function creerTheme() {
    const titre = ($('#nouveau-theme-titre').value || '').trim();
    if (!titre) { $('#nouveau-theme-titre').focus(); return; }
    await appel('/api/themes', { methode: 'POST', corps: {
      titre, description: $('#nouveau-theme-description').value.trim(),
      projet: projet ? projet.id : '' } });
    $('#nouveau-theme-titre').value = '';
    $('#nouveau-theme-description').value = '';
    $('#nouveau-theme-bloc').classList.add('cache');
    await chargerThemes();
  }

  // ================================================================ UN GROUPE DE TRAVAIL
  // TOUS les groupes ont les mêmes outils (consigne du 08/10/2026) : la boîte à trames et
  // les fiches de poste ont quitté Synergie (elles deviennent l'application Orbis).
  const ONGLETS = [
    ['tableau', 'Tableau blanc'], ['pages', 'Pages'], ['chat', 'Discussion'],
    ['documents', 'Documents'], ['decisions', 'Décisions'], ['journal', 'Journal']
  ];

  function construireOnglets() {
    const barre = $('#onglets-theme');
    barre.innerHTML = '';
    ONGLETS.forEach(([cle, libelle], rang) => {
      const bouton = element('button', { texte: libelle });
      bouton.dataset.onglet = cle;
      if (rang === 0) bouton.classList.add('actif');
      bouton.addEventListener('click', () => montrerOnglet(cle));
      barre.append(bouton);
    });
    document.querySelectorAll('.onglet').forEach((onglet) => onglet.classList.add('cache'));
    montrerOnglet(ONGLETS[0][0]);
  }

  function montrerOnglet(cle) {
    document.querySelectorAll('#onglets-theme button').forEach((bouton) =>
      bouton.classList.toggle('actif', bouton.dataset.onglet === cle));
    document.querySelectorAll('.onglet').forEach((onglet) =>
      onglet.classList.toggle('cache', onglet.id !== 'onglet-' + cle));
    if (cle === 'chat') chargerChatTheme();
    if (cle === 'pages') chargerPages();
    if (cle === 'journal') afficherJournal();
  }

  async function ouvrirTheme(identifiant, { pousser = true } = {}) {
    const donnees = await appel('/api/themes/' + encodeURIComponent(identifiant));
    theme = donnees.theme; notes = donnees.notes || []; decisions = donnees.decisions || [];
    documents = donnees.documents || []; participants = donnees.participants || [];
    journal = donnees.journal || []; votes = donnees.votes || {};
    mesVotes = donnees.mes_votes || [];
    membresTheme = donnees.membres || [];
    roleTheme = donnees.role || null;
    roles = donnees.roles || roles;
    afficherVue('theme');
    $('#titre-theme').textContent = theme.titre || '';
    $('#description-theme').textContent = theme.description || '';
    $('#mon-role-theme').textContent = libelleRole(roleTheme || roleProjet);
    $('#btn-membres-theme').classList.toggle('cache', !estAdministrateurTheme());
    $('#zone-membres-theme').classList.add('cache');
    afficherParticipants();
    dessinerNotes();
    afficherDocuments();
    afficherDecisions();
    afficherJournal();
    afficherMembresTheme();
    $('#btn-supprimer-theme').classList.toggle('cache', !estAdministrateurTheme());
    $('#btn-renommer-theme').classList.toggle('cache', !estAdministrateurTheme());
    construireOnglets();
    chargerChatTheme();
    brancherFlux();
    if (pousser && location.hash !== '#t=' + identifiant) {
      history.replaceState(null, '', '#t=' + identifiant);
    }
  }

  function fermerTheme() {
    if (flux) { flux.close(); flux = null; }
    theme = null; notes = []; decisions = []; documents = []; participants = [];
    journal = []; votes = {}; mesVotes = []; membresTheme = []; roleTheme = null;
    if (projet) { ouvrirProjet(projet.id, { pousser: false }); }
    else { afficherVue('projets'); }
    history.replaceState(null, '', location.pathname);
  }

  /** Bascule entre les trois vues : mes projets, un projet, un groupe. */
  function afficherVue(nom) {
    ['projets', 'projet', 'theme'].forEach((cle) => {
      $('#vue-' + cle).classList.toggle('cache', cle !== nom);
    });
    const barre = document.querySelector('header');
    if (barre) barre.classList.toggle('cache', nom === 'projets');
  }

  async function enregistrerTheme() {
    if (!theme || !estAdministrateurTheme()) return;
    const titre = prompt('Titre du groupe', theme.titre);
    if (!titre || !titre.trim()) return;
    const description = prompt('En une phrase (facultatif)', theme.description || '');
    await appel('/api/themes/' + theme.id, { methode: 'PUT',
      corps: { titre: titre.trim(), description: (description || '').trim() } });
    theme.titre = titre.trim();
    theme.description = (description || '').trim();
    $('#titre-theme').textContent = theme.titre;
    $('#description-theme').textContent = theme.description;
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

  // ---- flux du projet : sa discussion et son cadre de travail ----
  function brancherFluxGeneral() {
    if (fluxGeneral || !projet) return;
    fluxGeneral = new EventSource('/api/projets/' + projet.id + '/evenements?nom='
      + encodeURIComponent(monNom() || 'Anonyme'));
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
    const erreur = $('#nom-erreur');
    if (!prenom) {
      erreur.textContent = 'Indiquez votre prénom.';
      $('#prenom').classList.add('manquant');
      $('#prenom').focus();
      return false;
    }
    erreur.textContent = '';
    const donnees = await appel('/api/comptes', { methode: 'POST', corps: {
      prenom,
      poste: localStorage.getItem('synergie.poste') || posteDetecte(),
      appareil: appareilDetecte(),
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
      compte.notifications = donnees.notifications || { projets: [] };
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
    $('#c-poste').value = compte.poste || '';
    $('#c-email').value = compte.email || '';
    await chargerNotifications();
    $('#c-etat').textContent = compte.email
      ? 'Les alertes partent à ' + compte.email + '.'
      : 'Aucun courriel : vous ne recevrez pas d\'alerte.';
    $('#vue-compte').classList.remove('cache');
  }

  /** Mes projets et mes groupes, avec une case « me prévenir » pour chacun. */
  async function chargerNotifications() {
    const zone = $('#c-notifications');
    zone.innerHTML = '';
    const donnees = await appel('/api/comptes/moi');
    compte.notifications = donnees.notifications || { projets: [] };
    const liste = compte.notifications.projets || [];
    if (!liste.length) {
      zone.append(element('p', { classe: 'aide', texte: 'Vous ne participez à aucun projet.' }));
      return;
    }
    liste.forEach((p) => {
      const bloc = element('div', { classe: 'notif-projet' });
      const case_ = element('input', { attrs: { type: 'checkbox' } });
      case_.checked = Boolean(p.notifier);
      case_.dataset.projet = p.id;
      const ligne = element('label', { classe: 'case' });
      poser(ligne, case_, element('span', { texte: 'Tout le projet — ' + p.nom }));
      bloc.append(ligne);
      p.groupes.forEach((g) => {
        const sous = element('input', { attrs: { type: 'checkbox' } });
        sous.checked = Boolean(g.notifier);
        sous.dataset.theme = g.id;
        const l = element('label', { classe: 'case sous' });
        poser(l, sous, element('span', { texte: g.titre }));
        bloc.append(l);
      });
      zone.append(bloc);
    });
  }

  async function enregistrerMonCompte() {
    try {
      const donnees = await appel('/api/comptes/moi', { methode: 'PUT', corps: {
        prenom: $('#c-prenom').value.trim(),
        poste: $('#c-poste').value.trim(),
        email: $('#c-email').value.trim() } });
      compte = Object.assign(compte, donnees.compte);
      localStorage.setItem('synergie.poste', compte.poste || '');
      const projets_ = [];
      document.querySelectorAll('#c-notifications input[data-projet]').forEach((c) => {
        projets_.push({ id: c.dataset.projet, notifier: c.checked });
      });
      const groupes_ = [];
      document.querySelectorAll('#c-notifications input[data-theme]').forEach((c) => {
        groupes_.push({ id: c.dataset.theme, notifier: c.checked });
      });
      compte.notifications = await appel('/api/notifications',
        { methode: 'PUT', corps: { projets: projets_, groupes: groupes_ } });
      retenirNom(compte.prenom);
      $('#c-etat').textContent = 'Enregistré.';
      if (projet) brancherFlux();
    } catch (erreur) {
      $('#c-etat').textContent = 'Enregistrement impossible : ' + erreur.message;
    }
  }

  // ================================================================ CADRE DE TRAVAIL
  async function chargerCadre() {
    try {
      const cadre = await appel('/api/projets/' + projet.id + '/cadre');
      if (document.activeElement !== $('#cadre-contexte')) {
        $('#cadre-contexte').value = cadre.contexte || '';
      }
      $('#cadre-etat').textContent = cadre.maj_le
        ? 'Dernière modification par ' + (cadre.maj_par || 'quelqu\'un') + ' ' + quand(cadre.maj_le)
        : '';
      const donnees = await appel('/api/projets/' + projet.id + '/documents');
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
          attrs: { href: `/api/projets/${projet.id}/documents/${document.id}/fichier` } }),
        element('span', { classe: 'meta', texte:
          `${poids(document.taille)} · déposé par ${document.auteur || 'quelqu\'un'} ${quand(document.cree_le)}` }),
        document.note ? element('span', { classe: 'note-doc', texte: document.note }) : null);
      const supprimer = element('button', { classe: 'discret danger petit', texte: 'Supprimer' });
      supprimer.addEventListener('click', async () => {
        if (!confirm('Supprimer ce document ?')) return;
        await appel(`/api/projets/${projet.id}/documents/${document.id}`,
          { methode: 'DELETE' });
        chargerCadre();
      });
      poser(ligne, supprimer);
      zone.append(ligne);
    });
  }

  async function enregistrerCadre() {
    $('#cadre-etat').textContent = 'Enregistrement…';
    await appel('/api/projets/' + projet.id + '/cadre',
      { methode: 'PUT', corps: { contexte: $('#cadre-contexte').value } });
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
      await appel('/api/projets/' + projet.id + '/documents', { methode: 'POST', donnees });
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
      const donnees = await appel('/api/projets/' + projet.id + '/messages');
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
    const chemin = themeId ? `/api/themes/${themeId}/messages`
      : `/api/projets/${projet.id}/messages`;
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

  // ================================================================ RESPONSABLES
  // ================================================================ LES MEMBRES
  /** Un rôle : un menu déroulant avec les trois rôles possibles. */
  function menuRole(valeur, { projets_ = false } = {}) {
    const menu = element('select', { classe: 'role' });
    roles.forEach((r) => {
      const option = element('option', { texte: r.libelle, attrs: { value: r.cle,
        title: r.description } });
      if (r.cle === valeur) option.selected = true;
      menu.append(option);
    });
    menu.dataset.portee = projets_ ? 'projet' : 'theme';
    return menu;
  }

  /** Une ligne de membre : son nom, son rôle, ses alertes, et les actions. */
  function ligneMembre(membre, { portee, identifiant }) {
    const ligne = element('div', { classe: 'membre' });
    const infos = element('div', { classe: 'membre-nom' });
    poser(infos,
      element('strong', { texte: membre.prenom }),
      element('span', { classe: 'aide', texte: membre.poste ? ' · ' + membre.poste : '' }),
      membre.email ? element('span', { classe: 'aide', texte: ' · ' + membre.email })
        : element('span', { classe: 'aide', texte: ' · pas de courriel' }));
    const menu = menuRole(membre.role, { projets_: portee === 'projet' });
    menu.setAttribute('aria-label', 'Rôle de ' + membre.prenom);
    const alerte = element('input', { attrs: { type: 'checkbox', title: 'Me prévenir par courriel' } });
    alerte.checked = Boolean(membre.notifier);
    alerte.setAttribute('aria-label', 'Prévenir ' + membre.prenom + ' par courriel');
    const enlever = element('button', { classe: 'discret danger petit', texte: 'Retirer' });

    async function enregistrer() {
      const chemin = portee === 'projet'
        ? `/api/projets/${identifiant}/membres/${membre.compte}`
        : `/api/themes/${identifiant}/membres/${membre.compte}`;
      await appel(chemin, { methode: 'PUT', corps: { role: menu.value, notifier: alerte.checked } });
      if (portee === 'projet') { await rafraichirProjet(); } else { await rafraichirMembresTheme(); }
      toast('Rôle enregistré.');
    }
    menu.addEventListener('change', enregistrer);
    alerte.addEventListener('change', enregistrer);
    enlever.addEventListener('click', async () => {
      if (!confirm('Retirer ' + membre.prenom + ' ?')) return;
      const chemin = portee === 'projet'
        ? `/api/projets/${identifiant}/membres/${membre.compte}`
        : `/api/themes/${identifiant}/membres/${membre.compte}`;
      await appel(chemin, { methode: 'DELETE' });
      if (portee === 'projet') { await rafraichirProjet(); } else { await rafraichirMembresTheme(); }
      toast(membre.prenom + ' a été retiré.');
    });
    poser(ligne, infos, menu, alerte, enlever);
    return ligne;
  }

  async function rafraichirProjet() {
    if (!projet) return;
    const donnees = await appel('/api/projets/' + projet.id);
    membresProjet = donnees.membres || [];
    roleProjet = donnees.role || roleProjet;
    afficherMembresProjet();
  }

  async function rafraichirMembresTheme() {
    if (!theme) return;
    const donnees = await appel('/api/themes/' + theme.id + '/membres');
    membresTheme = donnees.membres || [];
    afficherMembresTheme();
  }

  function afficherMembresProjet() {
    const zone = $('#membres-liste');
    zone.innerHTML = '';
    const administre = roleProjet === 'admin';
    $('#membres-inviter').classList.toggle('cache', !administre);
    if (!membresProjet.length) {
      zone.append(element('p', { classe: 'vide', texte: 'Personne pour le moment.' }));
      return;
    }
    membresProjet.forEach((membre) => {
      if (administre) {
        zone.append(ligneMembre(membre, { portee: 'projet', identifiant: projet.id }));
      } else {
        const ligne = element('div', { classe: 'membre' });
        poser(ligne,
          element('strong', { texte: membre.prenom }),
          element('span', { classe: 'etiquette-role', texte: membre.libelle_role || membre.role }));
        zone.append(ligne);
      }
    });
  }

  async function ouvrirMembresProjet() {
    if (!projet) return;
    const menu = $('#membre-role');
    menu.innerHTML = '';
    roles.forEach((r) => menu.append(element('option', { texte: r.libelle,
      attrs: { value: r.cle, title: r.description } })));
    if (!membresProjet.length) await rafraichirProjet(); else afficherMembresProjet();
    $('#vue-membres').classList.remove('cache');
  }

  async function inviterAuProjet() {
    const prenom = ($('#membre-prenom').value || '').trim();
    if (!prenom) { $('#membre-prenom').focus(); return; }
    await appel('/api/projets/' + projet.id + '/membres', { methode: 'POST', corps: {
      prenom, role: $('#membre-role').value, notifier: true } });
    $('#membre-prenom').value = '';
    await rafraichirProjet();
    toast(prenom + ' a rejoint le projet.');
  }

  function afficherMembresTheme() {
    const zone = $('#liste-membres-theme');
    zone.innerHTML = '';
    const administre = estAdministrateurTheme();
    $('#inviter-theme').classList.toggle('cache', !administre);
    const menu = $('#membre-theme-role');
    if (menu.options.length !== roles.length) {
      menu.innerHTML = '';
      roles.forEach((r) => menu.append(element('option', { texte: r.libelle,
        attrs: { value: r.cle, title: r.description } })));
    }
    if (!membresTheme.length) {
      zone.append(element('p', { classe: 'aide', texte:
        'Personne n\'a de rôle particulier ici : tous les membres du projet participent.' }));
      return;
    }
    membresTheme.forEach((membre) => {
      if (administre) {
        zone.append(ligneMembre(membre, { portee: 'theme', identifiant: theme.id }));
      } else {
        const ligne = element('div', { classe: 'membre' });
        poser(ligne, element('strong', { texte: membre.prenom }),
          element('span', { classe: 'etiquette-role', texte: membre.libelle_role || membre.role }));
        zone.append(ligne);
      }
    });
  }

  async function inviterAuTheme() {
    const prenom = ($('#membre-theme-prenom').value || '').trim();
    if (!prenom) { $('#membre-theme-prenom').focus(); return; }
    await appel('/api/themes/' + theme.id + '/membres', { methode: 'POST', corps: {
      prenom, role: $('#membre-theme-role').value, notifier: true } });
    $('#membre-theme-prenom').value = '';
    await rafraichirMembresTheme();
    toast(prenom + ' a rejoint le groupe.');
  }

  /** Petit message en bas de l'écran (jamais de fenêtre qui bloque le travail). */
  function toast(texte) {
    const zone = $('#zone-toast');
    if (!zone) return;
    const bulle = element('div', { classe: 'toast', texte });
    zone.append(bulle);
    setTimeout(() => bulle.classList.add('visible'), 10);
    setTimeout(() => { bulle.classList.remove('visible'); setTimeout(() => bulle.remove(), 300); }, 2600);
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
    // Au clavier : Échap ferme la fenêtre ouverte et rend le focus au bouton qui l'a ouverte.
    document.addEventListener('keydown', (evenement) => {
      if (evenement.key !== 'Escape') return;
      const fenetre = ['#vue-compte', '#vue-membres'].find((sel) => !$(sel).classList.contains('cache'));
      if (!fenetre) return;
      $(fenetre).classList.add('cache');
      const retour = fenetre === '#vue-compte' ? $('#btn-compte') : $('#btn-membres');
      if (retour) retour.focus();
    });
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
    // --- les projets et les groupes
    $('#choix-projet').addEventListener('change', (e) => {
      if (e.target.value) ouvrirProjet(e.target.value);
    });
    $('#btn-projet').addEventListener('click', async () => {
      const nom = ($('#nouveau-projet-nom').value || '').trim();
      if (!nom) { $('#nouveau-projet-nom').focus(); return; }
      const cree = await appel('/api/projets', { methode: 'POST', corps: {
        nom, description: $('#nouveau-projet-description').value.trim() } });
      $('#nouveau-projet-nom').value = '';
      $('#nouveau-projet-description').value = '';
      await chargerProjets();
      ouvrirProjet(cree.id);
    });
    $('#btn-renommer-projet').addEventListener('click', async () => {
      const nom = prompt('Nom du projet', projet.nom);
      if (!nom || !nom.trim()) return;
      const description = prompt('En une phrase', projet.description || '');
      await appel('/api/projets/' + projet.id, { methode: 'PUT', corps: {
        nom: nom.trim(), description: (description || '').trim() } });
      await ouvrirProjet(projet.id, { pousser: false });
    });
    $('#btn-nouveau-theme').addEventListener('click', () => {
      $('#nouveau-theme-bloc').classList.remove('cache');
      $('#nouveau-theme-titre').focus();
    });
    $('#btn-theme-creer').addEventListener('click', creerTheme);
    $('#btn-theme-annuler').addEventListener('click', () =>
      $('#nouveau-theme-bloc').classList.add('cache'));

    // --- les membres (projet et groupe)
    $('#btn-membres').addEventListener('click', ouvrirMembresProjet);
    $('#membres-fermer').addEventListener('click', () =>
      $('#vue-membres').classList.add('cache'));
    $('#membre-ajouter').addEventListener('click', inviterAuProjet);
    $('#btn-membres-theme').addEventListener('click', () =>
      $('#zone-membres-theme').classList.toggle('cache'));
    $('#membres-theme-fermer').addEventListener('click', () =>
      $('#zone-membres-theme').classList.add('cache'));
    $('#membre-theme-ajouter').addEventListener('click', inviterAuTheme);

    $('#btn-retour').addEventListener('click', fermerTheme);
    $('#btn-renommer-theme').addEventListener('click', enregistrerTheme);
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
  /** À l'ouverture : on demande le PRÉNOM, et rien d'autre (consigne du 08/10/2026).
      Tant qu'il n'est pas donné, on n'entre pas : toute action est journalisée. */
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
        $('#nom-erreur').textContent = 'Connexion impossible : ' + erreur.message;
        return;
      }
      voile.classList.add('cache');
      entrerDansLAtelier();
      // Au clavier, on repart du début du contenu : la personne sait où elle est.
      const contenu = $('#vue-projet') || $('#vue-projets');
      if (contenu) { contenu.setAttribute('tabindex', '-1'); contenu.focus(); }
    }
    $('#btn-prenom').addEventListener('click', valider);
    champ.addEventListener('keydown', (evenement) => {
      if (evenement.key === 'Enter') valider();
    });
    champ.addEventListener('input', () => {
      champ.classList.remove('manquant');
      $('#nom-erreur').textContent = '';
    });
  }

  /** On entre dans l'atelier : mes projets, puis le dernier projet ouvert (ou le seul). */
  async function entrerDansLAtelier() {
    await chargerProjets();
    const garde = localStorage.getItem('synergie.projet');
    const cible = (location.hash.match(/#p=(.+)/) || [])[1]
      || (projets.some((p) => p.id === garde) ? garde : '')
      || (projets.length === 1 ? projets[0].id : '');
    if (!cible) { afficherVue('projets'); return; }
    await ouvrirProjet(cible);
    const groupe = (location.hash.match(/#t=(.+)/) || [])[1];
    if (groupe) { try { await ouvrirTheme(groupe, { pousser: false }); } catch (e) { /* inconnu */ } }
  }

  async function demarrer() {
    brancher();
    afficherVue('projets');
    await chargerMonCompte();                      // le compte d'abord
    if (!compte || !compte.prenom) { demanderPrenom(); return; }
    await entrerDansLAtelier();
  }

  document.addEventListener('DOMContentLoaded', demarrer);
})();
