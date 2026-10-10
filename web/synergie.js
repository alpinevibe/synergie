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
  let envoiCourriel = true;              // les envois de courriel sont-ils ouverts ?
  let cadreProjet = null;
  let invitationEnCours = null;        // invitation ouverte depuis un lien de courriel
  let jetonVote = null;                // lien de vote en cours (venu du courriel)
  let consultationRepondue = null;      // consultation à laquelle on répond depuis l'app              // cadre de travail du projet (lu en cliquant son nom)
  let membresTheme = [];
  let fluxGeneral = null;                // flux temps réel du projet
  let groupes = [];                      // groupes du projet
  let themes = [];                       // groupes du projet (même liste)
  let theme = null;                      // groupe ouvert
  let notes = [];                        // notes du tableau blanc
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
    chargerAttente();
    chargerCadre();
    chargerChatGeneral();
    brancherFluxGeneral();
    if (pousser && location.hash !== '#p=' + identifiant) {
      history.replaceState(null, '', '#p=' + identifiant);
    }
  }

  /** Ce qui attend la personne ici : votes et sondages sans réponse (consigne du 08/10). */
  async function chargerAttente() {
    const zone = $('#attente');
    if (!zone) return;
    zone.innerHTML = '';
    zone.classList.add('cache');
    if (!projet) return;
    let attentes = [];
    try { attentes = (await appel('/api/projets/' + projet.id + '/attente')).attentes || []; }
    catch (erreur) { return; }
    const pastille = $('#pastille-votes');
    if (pastille) {
      pastille.textContent = attentes.length;
      pastille.classList.toggle('cache', !attentes.length);
    }
    if (!attentes.length) return;
    const titre = element('p', { classe: 'alerte-titre', texte:
      attentes.length === 1 ? 'Une consultation vous attend'
        : attentes.length + ' consultations vous attendent' });
    zone.append(titre);
    attentes.forEach((attente) => {
      const ligne = element('div', { classe: 'alerte-ligne' });
      poser(ligne,
        element('span', { classe: 'alerte-type', texte:
          attente.type === 'vote' ? '🗳' : '📊' }),
        element('span', { classe: 'alerte-texte', texte:
          attente.intitule + ' — ' + attente.groupe }),
        (() => {
          const bouton = element('button', { classe: 'principal petit', texte: 'Répondre' });
          bouton.addEventListener('click', () => repondreDansApplication(attente.id));
          return bouton;
        })());
      zone.append(ligne);
    });
    zone.classList.remove('cache');
  }

  function libelleRole(role) {
    const trouve = roles.find((r) => r.cle === role);
    return trouve ? trouve.libelle : (role || '');
  }

  function estAdministrateurTheme() {
    // L'administrateur du PROJET administre tous ses groupes, quel que soit son rôle dans le
    // groupe (règle appliquée aussi côté serveur — sinon « Tout cocher » pouvait retirer
    // l'administration en se donnant un rôle de simple membre, constat du 09/10/2026).
    return roleProjet === 'admin' || roleTheme === 'admin';
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
        `${t.notes} note(s) · ${t.documents} document(s)` }));
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
  // La DISCUSSION n'est plus un onglet (demande de l'utilisateur, 09/10/2026) : elle vit
  // dans la colonne de droite, toujours visible, comme la discussion du projet.
  const ONGLETS = [
    ['tableau', 'Tableau blanc'], ['pages', 'Pages'],
    ['documents', 'Documents'], ['consultations', 'Votes et sondages'],
    ['journal', 'Journal']
  ];

  function construireOnglets() {
    const barre = $('#onglets-theme');
    barre.innerHTML = '';
    // Le JOURNAL est réservé aux administrateurs du groupe (consigne du 08/10/2026).
    const liste = ONGLETS.filter(([cle]) => cle !== 'journal' || estAdministrateurTheme());
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
    if (cle === 'pages') chargerPages();
    if (cle === 'consultations') chargerConsultations();
    if (cle === 'journal') afficherJournal();
  }

  async function ouvrirTheme(identifiant, { pousser = true } = {}) {
    const donnees = await appel('/api/themes/' + encodeURIComponent(identifiant));
    theme = donnees.theme; notes = donnees.notes || [];
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
    chargerConsultations();
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
    theme = null; notes = []; documents = []; participants = [];
    journal = []; votes = {}; mesVotes = []; membresTheme = []; roleTheme = null;
    if (projet) { ouvrirProjet(projet.id, { pousser: false }); }
    else { afficherVue('projets'); }
    history.replaceState(null, '', location.pathname);
  }

  // ================================================================ VERSION TÉLÉPHONE
  // Sur un téléphone, l'application change de navigation : une barre en bas, un écran
  // par chose à faire, et le tableau blanc sous forme de liste de notes.
  const mediaEtroit = window.matchMedia('(max-width: 900px)');
  let sectionMobile = 'projet';

  function estMobile() {
    return mediaEtroit.matches || /Android|iPhone|iPad|iPod|Windows Phone/i.test(navigator.userAgent);
  }

  /** Première mise en place : on choisit la version adaptée à l'appareil. */
  function afficherMode() { appliquerMode(); }

  function appliquerMode() {
    const mobile = estMobile();
    document.body.dataset.vue = mobile ? 'mobile' : 'bureau';
    const barre = $('#nav-mobile');
    if (barre) barre.classList.toggle('cache', !mobile);
    if (mobile) afficherSectionMobile(sectionMobile);
    if (theme) dessinerNotes();
  }

  function afficherSectionMobile(cle) {
    sectionMobile = cle || 'projet';
    document.body.dataset.section = sectionMobile;
    document.querySelectorAll('#nav-mobile button').forEach((bouton) =>
      bouton.classList.toggle('actif', bouton.dataset.section === sectionMobile));
    if (sectionMobile === 'votes') chargerConsultationsProjet();
    if (sectionMobile === 'compte') ouvrirMonCompte();
  }

  /** Le volet « Votes » du téléphone : tout ce qui est ouvert dans le projet. */
  async function chargerConsultationsProjet() {
    const zone = $('#consultations-projet');
    if (!zone || !projet) return;
    zone.innerHTML = '';
    let liste = [];
    try { liste = (await appel('/api/projets/' + projet.id + '/consultations')).consultations || []; }
    catch (erreur) { return; }
    if (!liste.length) {
      zone.append(element('p', { classe: 'vide',
        texte: 'Aucun vote ni sondage ouvert pour le moment.' }));
      return;
    }
    liste.forEach((consultation) => {
      const carte = element('div', { classe: 'carte consultation ' + consultation.statut });
      poser(carte,
        element('h4', { texte: (consultation.type === 'vote' ? '🗳 ' : '📊 ')
          + consultation.intitule }),
        consultation.detail ? element('p', { classe: 'aide', texte: consultation.detail }) : null,
        element('p', { classe: 'meta', texte: consultation.groupe + ' · ' + consultation.libelle_type
          + ' · ' + (consultation.statut === 'ouverte' ? 'ouvert' : consultation.statut) }));
      if (consultation.je_suis_consulte) {
        if (consultation.moi_repondu) {
          carte.append(element('p', { classe: 'meta deja-vote',
            texte: '✓ Vous avez répondu (merci !).' }));
        } else {
          const bouton = element('button', { classe: 'principal petit', texte: 'Répondre' });
          bouton.addEventListener('click', () => repondreDansApplication(consultation.id));
          carte.append(bouton);
        }
      } else {
        carte.append(element('p', { classe: 'aide fin',
          texte: 'Vous n\'êtes pas consulté(e) pour celle-ci.' }));
      }
      zone.append(carte);
    });
  }

  /** Bascule entre les trois vues : mes projets, un projet, un groupe. */
  function afficherVue(nom) {
    ['projets', 'projet', 'theme'].forEach((cle) => {
      $('#vue-' + cle).classList.toggle('cache', cle !== nom);
    });
    const barre = document.querySelector('header');
    if (barre) barre.classList.toggle('cache', nom === 'projets' && !estMobile());
    // Sur téléphone, la barre du bas ne sert que dans le projet (dans un groupe, on
    // revient par le bouton « ← Le projet »).
    const nav = $('#nav-mobile');
    if (nav) nav.classList.toggle('cache', !estMobile() || nom !== 'projet');
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
      afficherJournal();
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
        if (evenement.type === 'message_supprime') chargerChatGeneral();
        if (evenement.type === 'cadre') chargerCadre();
        if (evenement.type === 'rafraichir') { chargerChatGeneral(); chargerCadre(); }
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
      case 'message_supprime':
        chargerChatTheme();
        break;
      case 'consultation_creee':
      case 'consultation_maj':
      case 'consultation_supprimee':
        chargerConsultations();
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
          chargerConsultations();
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
      case 'rafraichir':
        // Événement trop gros pour la notification entre ouvriers, ou reprise après
        // connexion perdue : on redemande simplement l'état du groupe.
        if (theme) ouvrirTheme(theme.id, { pousser: false });
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

  // ---------------------------------------------------------------- ANNULER
  // Chaque modification du tableau pousse son INVERSE sur une pile : on peut revenir en
  // arrière (bouton « ↶ Annuler » ou Ctrl + Z), comme dans une page de texte.
  const annulations = [];
  const ANNULATIONS_MAX = 60;

  function noterAnnulation(description, action) {
    annulations.push({ description, action });
    if (annulations.length > ANNULATIONS_MAX) annulations.shift();
    majBoutonAnnuler();
  }

  function majBoutonAnnuler() {
    const bouton = $('#btn-annuler');
    if (!bouton) return;
    bouton.disabled = annulations.length === 0;
    bouton.title = annulations.length
      ? "Revenir en arrière : " + annulations[annulations.length - 1].description
      : 'Rien à annuler';
  }

  async function annuler() {
    const dernier = annulations.pop();
    majBoutonAnnuler();
    if (!dernier) { toast('Rien à annuler.'); return; }
    try {
      await dernier.action();
      toast('Annulé : ' + dernier.description);
    } catch (erreur) {
      toast('Annulation impossible : ' + erreur.message);
    }
  }

  /** Applique des changements à une note, en gardant de quoi revenir en arrière. */
  async function modifierNote(note, changements, description) {
    const avant = {};
    Object.keys(changements).forEach((cle) => { avant[cle] = note[cle]; });
    Object.assign(note, changements);
    poserNote(note);
    if (noteSelectionnee() === note) afficherBarreFormat();
    await sauver(note.id, changements);
    noterAnnulation(description, async () => {
      Object.assign(note, avant);
      poserNote(note);
      if (noteSelectionnee() === note) afficherBarreFormat();
      await sauver(note.id, avant, { annulable: false });
    });
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

    let texteAvant = '';

    /** On écrit dans la note : le texte devient modifiable (demande du 05/10/2026). */
    function modifier(invitation) {
      texteAvant = texte.textContent;
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
      if (texteAvant !== texte.textContent) {
        const ancien = texteAvant;
        noterAnnulation('texte de la note', async () => {
          const noeudNote = document.querySelector(`.note[data-id="${note.id}"] .note-texte`);
          if (noeudNote) noeudNote.textContent = ancien;
          const cible = notes.find((n) => n.id === note.id);
          if (cible) cible.texte = ancien;
          await sauver(note.id, { texte: ancien });
        });
      }
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

    supprimer.addEventListener('click', async (evenement) => {
      evenement.stopPropagation();
      if (!confirm('Supprimer cette note ?')) return;
      await supprimerNote(note);
      toast('Note supprimée.');
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
        if (bouge) {
          const avant = { x: depart.ox, y: depart.oy };
          const apres = { x: note.x, y: note.y };
          if (avant.x !== apres.x || avant.y !== apres.y) {
            sauver(note.id, apres);
            noterAnnulation('déplacement de la note', async () => {
              Object.assign(note, avant);
              poserNote(note);
              await sauver(note.id, avant);
            });
          }
        }
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
      const largeurAvant = note.largeur;
      const etirer = (e) => {
        note.largeur = Math.max(160, depart.largeur + (e.clientX - depart.x) / vue.z);
        noeud.style.width = note.largeur + 'px';
        programmer('larg-' + note.id, () => sauver(note.id, { largeur: note.largeur }), 350);
      };
      const relacher = () => {
        poigneeTaille.removeEventListener('pointermove', etirer);
        poigneeTaille.removeEventListener('pointerup', relacher);
        sauver(note.id, { largeur: note.largeur });
        if (Math.round(largeurAvant) !== Math.round(note.largeur)) {
          const avant = { largeur: largeurAvant };
          noterAnnulation('redimensionnement de la note', async () => {
            Object.assign(note, avant);
            poserNote(note);
            await sauver(note.id, avant);
          });
        }
      };
      poigneeTaille.addEventListener('pointermove', etirer);
      poigneeTaille.addEventListener('pointerup', relacher);
    });

    return noeud;
  }

  /** Supprime une note, en gardant tout pour pouvoir la remettre (annulation). */
  async function supprimerNote(note, { annulable = true } = {}) {
    const copie = { ...note };
    await appel('/api/themes/' + theme.id + '/notes/' + note.id, { methode: 'DELETE' });
    notes = notes.filter((n) => n.id !== note.id);
    retirerNote(note.id);
    if (selection === note.id) selectionner(null);
    if (annulable) {
      noterAnnulation('suppression de la note', async () => {
        const remise = await appel('/api/themes/' + theme.id + '/notes', { methode: 'POST',
          corps: { x: copie.x, y: copie.y, texte: copie.texte, taille: copie.taille,
                   gras: copie.gras, italique: copie.italique, souligne: copie.souligne,
                   couleur_texte: copie.couleur_texte, couleur_fond: copie.couleur_fond,
                   alignement: copie.alignement, largeur: copie.largeur,
                   auteur: copie.auteur || monNom() || 'Anonyme' } });
        notes.push(remise);
        poserNote(remise);
      });
    }
  }

  function textoVide(noeud) { return !(noeud.textContent || '').trim(); }

  /** La liste des notes : sur téléphone, c'est ainsi qu'on lit et qu'on écrit. */
  function carteNoteMobile(note) {
    const carte = element('div', { classe: 'carte-note' + (selection === note.id ? ' choisie' : '') });
    carte.style.background = note.couleur_fond || '#fff8d6';
    carte.style.color = note.couleur_texte || '#1e2a3a';
    carte.style.borderLeft = '5px solid ' + (note.couleur_texte || '#1e2a3a');
    carte.dataset.id = note.id;

    const texte = element('div', { classe: 'note-texte-mobile', texte: note.texte || '' });
    texte.setAttribute('role', 'textbox');
    texte.setAttribute('aria-label', 'Note');
    let avantEdition = note.texte || '';
    // Sur téléphone, on écrit en appuyant sur la note : le curseur se place à la fin.
    texte.addEventListener('click', () => {
      if (texte.contentEditable === 'true') return;
      avantEdition = texte.textContent || '';
      texte.contentEditable = 'true';
      texte.focus();
      const plage = document.createRange();
      plage.selectNodeContents(texte);
      plage.collapse(false);
      const choix = window.getSelection();
      choix.removeAllRanges();
      choix.addRange(plage);
      selectionner(note.id);
    });
    texte.addEventListener('blur', async () => {
      texte.contentEditable = 'false';
      const courante = notes.find((n) => n.id === note.id);
      if (courante) courante.texte = texte.textContent;
      if (avantEdition !== texte.textContent) {
        await sauver(note.id, { texte: texte.textContent });
        noterAnnulation('texte de la note', async () => {
          texte.textContent = avantEdition;
          const cible = notes.find((n) => n.id === note.id);
          if (cible) cible.texte = avantEdition;
          await sauver(note.id, { texte: avantEdition });
        });
      }
    });
    carte.append(texte);

    const meta = element('div', { classe: 'note-meta-mobile' });
    poser(meta,
      element('span', { texte: (note.auteur || 'quelqu\'un') + ' · ' + quand(note.maj_le) }),
      element('span', { classe: 'etiquette-role', texte: note.texte ? ''
        : 'note vide — appuyez pour écrire' }));
    carte.append(meta);

    const actions = element('div', { classe: 'actions-note' });
    const couleur = element('button', { classe: 'discret petit', texte: 'Couleur',
      attrs: { title: 'Changer la couleur du post-it' } });
    couleur.addEventListener('click', () => {
      const suite = ORDRE_FONDS[(ORDRE_FONDS.indexOf(note.couleur_fond) + 1) % ORDRE_FONDS.length];
      changerCouleur(note, 'couleur_fond', suite).then(() => afficherNotesMobile());
    });
    const haut = element('button', { classe: 'discret petit', texte: '↑',
      attrs: { title: 'Monter la note' } });
    haut.addEventListener('click', () => deplacerDansListe(note, -1));
    const bas = element('button', { classe: 'discret petit', texte: '↓',
      attrs: { title: 'Descendre la note' } });
    bas.addEventListener('click', () => deplacerDansListe(note, 1));
    const retirer = element('button', { classe: 'discret danger petit', texte: 'Supprimer' });
    retirer.addEventListener('click', async () => {
      if (!confirm('Supprimer cette note ?')) return;
      await supprimerNote(note);
      afficherNotesMobile();
      toast('Note supprimée.');
    });
    poser(actions, couleur, haut, bas, retirer);
    carte.append(actions);
    return carte;
  }

  /** Ranger une note dans la liste : on échange sa place avec sa voisine. */
  async function deplacerDansListe(note, sens) {
    const ordonnees = [...notes].sort((a, b) => (a.y - b.y) || (a.x - b.x));
    const rang = ordonnees.findIndex((n) => n.id === note.id);
    const voisine = ordonnees[rang + sens];
    if (!voisine) return;
    const y = note.y;
    note.y = voisine.y;
    voisine.y = y;
    await sauver(note.id, { y: note.y });
    await sauver(voisine.id, { y: voisine.y });
    afficherNotesMobile();
  }

  function afficherNotesMobile() {
    const zone = $('#notes-liste');
    if (!zone || !estMobile()) return;
    zone.innerHTML = '';
    const ordonnees = [...notes].sort((a, b) => (a.y - b.y) || (a.x - b.x));
    if (!ordonnees.length) {
      zone.append(element('p', { classe: 'vide',
        texte: 'Aucune note pour le moment : appuyez sur « + Note ».' }));
      return;
    }
    ordonnees.forEach((note) => zone.append(carteNoteMobile(note)));
    const bouton = $('#btn-voir-tableau');
    if (bouton) bouton.classList.remove('cache');
  }

  function dessinerNotes() {
    afficherNotesMobile();
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

  async function sauver(identifiant, champs, { annulable = true } = {}) {
    try {
      await appel('/api/themes/' + theme.id + '/notes/' + identifiant,
        { methode: 'PUT', corps: champs });
    } catch (erreur) { /* la note reste à l'écran, une nouvelle tentative suivra */ }
    return annulable;
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
    afficherNotesMobile();
    selectionner(note.id);
    noterAnnulation('création de la note', async () => { await supprimerNote(note, { annulable: false }); });
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
        await supprimerNote(note);
        return;
      default: break;
    }
    await modifierNote(note, changements, 'mise en forme de la note');
  }

  async function changerCouleur(note, champ, couleur) {
    await modifierNote(note, { [champ]: couleur },
      champ === 'couleur_fond' ? 'changement de couleur' : 'changement de couleur du texte');
  }

  /** Range les notes en colonnes, dans l'ordre de lecture : le tableau redevient lisible. */
  /** Ranger le tableau : UNE COLONNE PAR COULEUR de post-it (demande du 08/10/2026).
      Les notes de même fond se suivent, dans l'ordre où elles étaient ; la couleur de
      fond la plus fréquente n'est pas privilégiée — c'est l'ordre des couleurs de la
      palette qui décide, pour que le tableau soit toujours rangé pareil. */
  async function organiser() {
    if (!notes.length) return;
    const rang = (note) => {
      const place = ORDRE_FONDS.indexOf(note.couleur_fond);
      return place === -1 ? ORDRE_FONDS.length : place;
    };
    const triees = [...notes].sort((a, b) => (rang(a) - rang(b)) || (a.y - b.y) || (a.x - b.x));
    const colonne = 400, pas = 230, parColonne = 4;
    let x = 40;
    let y = 40;
    let couleur = null;
    for (const note of triees) {
      const teinte = note.couleur_fond || ORDRE_FONDS[0];
      if (couleur === null || teinte !== couleur) {
        // Nouvelle couleur : nouvelle colonne, en haut.
        if (couleur !== null) { x += colonne; y = 40; }
        couleur = teinte;
      } else if (y > 40 + (parColonne - 1) * pas) {
        // Colonne pleine : la même couleur continue dans la colonne suivante.
        x += colonne;
        y = 40;
      }
      note.x = x;
      note.y = y;
      y += pas;
      poserNote(note);
      await sauver(note.id, { x: note.x, y: note.y });
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

  // Les actions du journal, dites en français.
  const ACTIONS = {
    theme_cree: 'a créé le groupe', theme_modifie: 'a modifié le groupe',
    note_creee: 'a écrit une note', note_modifiee: 'a modifié une note',
    note_deplacee: 'a déplacé une note', note_supprimee: 'a supprimé une note',
    document_depose: 'a déposé un document', document_supprime: 'a supprimé un document',
    consultation_creee: 'a créé un vote ou un sondage',
    consultation_ouverte: 'a ouvert un vote ou un sondage',
    consultation_repondue: 'a répondu à une consultation',
    consultation_close: 'a clos une consultation',
    message_supprime: 'a retiré un message de la discussion',
    invitation: 'a invité quelqu\'un', invitation_activee: 'a activé son accès',
    projet_membre: 'a modifié les membres du projet', arrivee: 'est arrivé dans le groupe',
  };

  /** Le journal du groupe (qui a fait quoi) — visible des administrateurs seulement. */
  function afficherJournal() {
    const zone = $('#liste-journal');
    if (!zone) return;
    zone.innerHTML = '';
    if (!journal.length) {
      zone.append(element('p', { classe: 'vide',
        texte: 'Aucune action enregistrée pour le moment.' }));
      return;
    }
    journal.forEach((entree) => {
      poser(zone, element('div', { classe: 'carte entree-journal' },
        element('span', { classe: 'qui', texte: entree.qui || 'Quelqu\'un' }),
        element('span', { classe: 'quoi', texte: ACTIONS[entree.action] || entree.action }),
        entree.details ? element('span', { classe: 'details',
          texte: '« ' + entree.details + ' »' }) : null,
        element('span', { classe: 'quand', texte: quand(entree.quand) })));
    });
  }

  // ================================================================ VOTES ET SONDAGES
  // Un VOTE tranche une question (oui / non) ; un SONDAGE éclaire la réflexion (plusieurs
  // questions, plusieurs types de réponses). Dans les deux cas : on choisit qui l'on
  // consulte, chacun reçoit un lien personnel, et les réponses restent anonymes.

  let consultations = [];
  let consultationOuverte = null;       // celle qu'on modifie (sinon, on crée)
  let typeConsultation = 'sondage';     // « vote » ou « sondage » en cours de création
  let typesQuestion = [];

  async function chargerConsultations() {
    if (!theme) return;
    try {
      const donnees = await appel('/api/themes/' + theme.id + '/consultations');
      consultations = donnees.consultations || [];
      typesQuestion = donnees.types_question || [];
      afficherConsultations();
    } catch (erreur) { /* sans conséquence */ }
  }

  const STATUTS = { brouillon: 'brouillon', ouverte: 'ouvert', close: 'clos' };

  function afficherConsultations() {
    const zone = $('#liste-consultations');
    zone.innerHTML = '';
    if (!consultations.length) {
      zone.append(element('p', { classe: 'vide',
        texte: 'Aucun vote ni sondage pour le moment.' }));
      return;
    }
    consultations.forEach((consultation) => {
      const vote = consultation.type === 'vote';
      const carte = element('div', { classe: `carte consultation ${consultation.statut}` });
      poser(carte,
        element('h4', { texte: (vote ? '🗳 ' : '📊 ') + consultation.intitule }),
        consultation.detail ? element('p', { classe: 'aide', texte: consultation.detail }) : null,
        element('p', { classe: 'meta', texte:
          consultation.libelle_type + ' · ' + STATUTS[consultation.statut]
          + ' · ' + (consultation.scrutin === 'projet' ? 'tout le projet' : 'membres du groupe')
          + ` · ${consultation.repondu}/${consultation.bulletins} réponse(s)`
          + ` · ${consultation.questions} question(s)` }));

      // Les questions (aperçu)
      if (consultation.questions_detaillees) {
        const liste = element('ul', { classe: 'questions-apercu' });
        consultation.questions_detaillees.forEach((question) => {
          liste.append(element('li', { texte: question.intitule
            + ' — ' + question.libelle_type }));
        });
        carte.append(liste);
      }

      const barre = element('div', { classe: 'barre-boutons' });
      if (consultation.statut === 'brouillon' && estAdministrateurTheme()) {
        const ouvrir = element('button', { classe: 'principal petit',
          texte: 'Envoyer les liens' });
        ouvrir.addEventListener('click', () => ouvrirConsultation(consultation));
        const modifier = element('button', { classe: 'discret petit', texte: 'Modifier' });
        modifier.addEventListener('click', () => ouvrirFenetreConsultation(consultation));
        poser(barre, ouvrir, modifier);
      }
      if (consultation.statut === 'ouverte' && estAdministrateurTheme()) {
        const fermer = element('button', { classe: 'petit discret', texte: 'Clore' });
        fermer.addEventListener('click', async () => {
          if (!confirm('Clore la consultation ? Les réponses resteront visibles.')) return;
          await appel('/api/consultations/' + consultation.id + '/fermer', { methode: 'POST' });
          await chargerConsultations();
        });
        barre.append(fermer);
      }
      if (estAdministrateurTheme() && consultation.bulletins) {
        const liens = element('button', { classe: 'discret petit', texte: 'Liens' });
        liens.addEventListener('click', () => afficherLiens(consultation));
        barre.append(liens);
      }
      const resultats = element('button', { classe: 'discret petit', texte: 'Résultats' });
      resultats.addEventListener('click', () => afficherResultats(consultation, carte));
      barre.append(resultats);
      if (estAdministrateurTheme()) {
        const supprimer = element('button', { classe: 'discret danger petit', texte: 'Supprimer' });
        supprimer.addEventListener('click', async () => {
          if (!confirm('Supprimer cette consultation et ses réponses ?')) return;
          await appel('/api/consultations/' + consultation.id, { methode: 'DELETE' });
          await chargerConsultations();
        });
        barre.append(supprimer);
      }
      carte.append(barre);
      zone.append(carte);
    });
  }

  /** Le dépouillement : barres pour les choix, nuage pour les mots, moyenne pour l'échelle. */
  async function afficherResultats(consultation, carte) {
    const zone = carte.querySelector('.resultats') || element('div', { classe: 'resultats' });
    zone.innerHTML = '';
    const donnees = await appel('/api/consultations/' + consultation.id);
    const resultats = donnees.resultats || [];
    if (!resultats.length) {
      zone.append(element('p', { classe: 'aide', texte:
        'Les résultats apparaîtront ici (ils sont visibles par tous une fois la consultation close).' }));
      carte.append(zone);
      return;
    }
    resultats.forEach((question) => {
      const bloc = element('div', { classe: 'resultat' });
      bloc.append(element('p', { classe: 'resultat-titre', texte: question.intitule
        + ' (' + question.total + ' réponse(s))' }));
      if (question.type === 'mot') {
        const nuage = element('div', { classe: 'nuage' });
        (question.mots || []).forEach((mot) => {
          nuage.append(element('span', { classe: 'mot',
            style: `font-size:${Math.min(30, 13 + mot.nombre * 3)}px`,
            texte: mot.valeur + ' ' }));
        });
        bloc.append(nuage);
      } else if (question.type === 'likert') {
        bloc.append(element('p', { classe: 'meta',
          texte: 'Moyenne : ' + (question.moyenne === null ? '—' : question.moyenne + ' / 5') }));
        (question.repartition || []).forEach((note) => bloc.append(ligneResultat(note.valeur, note.nombre, question.total)));
      } else {
        (question.comptes || []).forEach((ligne) => bloc.append(ligneResultat(ligne.valeur, ligne.nombre, question.total)));
        if (!(question.comptes || []).length) {
          bloc.append(element('p', { classe: 'aide', texte: 'Aucune réponse pour le moment.' }));
        }
      }
      zone.append(bloc);
    });
    carte.append(zone);
  }

  /** Les liens personnels : de quoi consulter les gens même si le courriel ne part pas. */
  async function afficherLiens(consultation) {
    const donnees = await appel('/api/consultations/' + consultation.id + '/liens');
    const zone = $('#liste-liens');
    zone.innerHTML = '';
    donnees.liens.forEach((entree) => {
      const ligne = element('div', { classe: 'ligne-lien' });
      const champ = element('input', { attrs: { readonly: 'readonly', value: entree.lien } });
      const copier = element('button', { classe: 'discret petit', texte: 'Copier' });
      copier.addEventListener('click', async () => {
        try { await navigator.clipboard.writeText(entree.lien); toast('Lien copié.'); }
        catch (e) { champ.select(); document.execCommand('copy'); toast('Lien copié.'); }
      });
      poser(ligne,
        element('span', { classe: 'lien-personne', texte: entree.email
          + (entree.repondu ? ' ✓ a répondu' : '') }),
        champ, copier);
      zone.append(ligne);
    });
    if (!donnees.liens.length) {
      zone.append(element('p', { classe: 'vide', texte:
        "Aucun lien : ouvrez d’abord la consultation (les personnes visées ont besoin "
        + "d’une adresse de courriel)." }));
    }
    $('#liens-etat').textContent = '';
    $('#vue-liens').classList.remove('cache');

    $('#btn-copier-liens').onclick = async () => {
      const texteLiens = donnees.liens.map((e) => e.email + ' : ' + e.lien).join('\n');
      try { await navigator.clipboard.writeText(texteLiens); }
      catch (e) { /* le presse-papiers peut être refusé */ }
      $('#liens-etat').textContent = donnees.liens.length + ' lien(s) copié(s).';
    };
  }

  function ligneResultat(valeur, nombre, total) {
    const pourcent = total ? Math.round((nombre / total) * 100) : 0;
    const ligne = element('div', { classe: 'ligne-resultat' });
    poser(ligne,
      element('span', { classe: 'resultat-valeur', texte: valeur || '(vide)' }),
      element('span', { classe: 'resultat-barre' },
        element('span', { classe: 'resultat-remplie', style: `width:${pourcent}%` })),
      element('span', { classe: 'resultat-nombre', texte: nombre + (total ? ` (${pourcent} %)` : '') }));
    return ligne;
  }

  /** Créer (ou modifier) un vote ou un sondage. */
  function ouvrirFenetreConsultation(consultation = null, typeParDefaut = 'sondage') {
    consultationOuverte = consultation;
    const type = consultation ? consultation.type : typeParDefaut;
    typeConsultation = type;
    $('#titre-consultation').textContent = consultation
      ? 'Modifier ' + (type === 'vote' ? 'le vote' : 'le sondage')
      : (type === 'vote' ? 'Nouveau vote' : 'Nouveau sondage');
    $('#consultation-intitule').value = consultation ? consultation.intitule : '';
    $('#consultation-detail').value = consultation ? consultation.detail || '' : '';
    const questions = consultation && consultation.questions_detaillees
      ? consultation.questions_detaillees : [{ type: type === 'vote' ? 'oui_non' : 'unique',
                                               intitule: '', options: [] }];
    dessinerQuestions(questions, type);
    $('#consultation-erreur').textContent = '';
    $('#btn-ajouter-question').classList.toggle('cache', type === 'vote');
    $('#btn-consultation-ouvrir').textContent = consultation
      ? 'Enregistrer et envoyer les liens' : 'Enregistrer et envoyer les liens';
    $('#vue-consultation').classList.remove('cache');
    setTimeout(() => $('#consultation-intitule').focus(), 200);
  }

  function dessinerQuestions(questions, type) {
    const zone = $('#consultation-questions');
    zone.innerHTML = '';
    questions.forEach((question, rang) => zone.append(construireQuestion(question, type, rang)));
  }

  function construireQuestion(question, type, rang) {
    const bloc = element('div', { classe: 'question-editeur' });
    bloc.dataset.rang = rang;
    const vote = type === 'vote';

    const entete = element('div', { classe: 'ligne-question' });
    entete.append(element('span', { classe: 'etiquette', texte: vote ? 'Question' : `Question ${rang + 1}` }));
    const menu = element('select', { attrs: { 'aria-label': 'Type de réponse' } });
    typesQuestion.forEach((t) => {
      const option = element('option', { texte: t.libelle, attrs: { value: t.cle } });
      if (t.cle === (question.type || 'unique')) option.selected = true;
      menu.append(option);
    });
    menu.disabled = vote;
    if (!vote) entete.append(menu);
    bloc.append(entete);

    const intitule = element('input', { classe: 'champ-large',
      attrs: { placeholder: 'La question', maxlength: '200' } });
    intitule.value = question.intitule || '';
    bloc.append(intitule);

    const options = element('textarea', { classe: 'options-question',
      attrs: { rows: '3', placeholder: 'Une réponse possible par ligne' } });
    options.value = (question.options || []).join('\n');
    const blocOptions = element('div', {});
    blocOptions.append(element('span', { classe: 'aide fin', texte:
      'Réponses possibles (une par ligne) :' }), options);
    bloc.append(blocOptions);

    function majVisibilite() {
      if (vote) { blocOptions.classList.add('cache'); return; }
      const avecOptions = ['unique', 'multiple', 'liste'].includes(menu.value);
      blocOptions.classList.toggle('cache', !avecOptions);
    }
    menu.addEventListener('change', majVisibilite);
    majVisibilite();

    if (!vote) {
      const enlever = element('button', { classe: 'discret danger petit', texte: 'Retirer' });
      enlever.addEventListener('click', () => bloc.remove());
      bloc.append(enlever);
    }
    return bloc;
  }

  function lireQuestions() {
    const questions = [];
    document.querySelectorAll('#consultation-questions .question-editeur').forEach((bloc) => {
      const menu = bloc.querySelector('select');
      const champs = bloc.querySelectorAll('input, textarea');
      questions.push({
        type: menu ? menu.value : 'oui_non',
        intitule: (champs[0].value || '').trim(),
        options: (champs[1].value || '').split('\n').map((l) => l.trim()).filter(Boolean),
      });
    });
    return questions;
  }

  /** Crée (ou met à jour) la consultation, puis l'ouvre si on l'a demandé. */
  async function enregistrerConsultation({ ouvrirAussi = true } = {}) {
    const erreur = $('#consultation-erreur');
    erreur.textContent = '';
    const corps = {
      type: consultationOuverte ? consultationOuverte.type : typeConsultation,
      intitule: $('#consultation-intitule').value.trim(),
      detail: $('#consultation-detail').value.trim(),
      questions: lireQuestions(),
    };
    if (!corps.intitule) { erreur.textContent = 'Donnez un intitulé.'; return; }
    try {
      let consultation = consultationOuverte;
      if (consultationOuverte) {
        consultation = await appel('/api/consultations/' + consultationOuverte.id,
          { methode: 'PUT', corps: { intitule: corps.intitule, detail: corps.detail,
                                     questions: corps.questions } });
      } else {
        consultation = await appel('/api/themes/' + theme.id + '/consultations',
          { methode: 'POST', corps });
      }
      if (ouvrirAussi) {
        const scrutin = (document.querySelector('input[name="scrutin"]:checked') || {}).value
          || 'groupe';
        const envoi = await appel('/api/consultations/' + consultation.id + '/ouvrir',
          { methode: 'POST', corps: { scrutin } });
        toast((envoi.envoyes || []).length + ' lien(s) envoyé(s) par courriel.');
      } else {
        toast('Consultation enregistrée en brouillon.');
      }
      $('#vue-consultation').classList.add('cache');
      await chargerConsultations();
    } catch (e) {
      erreur.textContent = e.message;
    }
  }

  async function ouvrirConsultation(consultation) {
    const scrutin = prompt('Qui consulter ? Écrivez « groupe » ou « projet »', 'groupe');
    if (!scrutin) return;
    try {
      const envoi = await appel('/api/consultations/' + consultation.id + '/ouvrir',
        { methode: 'POST', corps: {
          scrutin: scrutin.trim().toLowerCase().startsWith('proj') ? 'projet' : 'groupe' } });
      toast((envoi.envoyes || []).length + ' lien(s) envoyé(s) par courriel.');
      await chargerConsultations();
    } catch (e) { toast(e.message); }
  }

  // ================================================================ MON COMPTE
  // Chaque personne a un compte enregistré sur le serveur (prénom + courriel). Le jeton
  // gardé par le navigateur permet de le retrouver, et le courriel sert aux alertes.

  /** Entrer avec son IDENTIFIANT personnel (demande du 08/10/2026) : l'identifiant
      n'est connu que de son titulaire, personne ne peut donc prendre sa place. */
  async function entrerAvecIdentifiant() {
    const erreur = $('#nom-erreur');
    const champ = $('#identifiant');
    const identifiant = (champ.value || '').trim();
    if (!identifiant) {
      erreur.textContent = 'Indiquez votre identifiant.';
      champ.classList.add('manquant');
      champ.focus();
      return false;
    }
    erreur.textContent = '';
    const donnees = await appel('/api/connexion', { methode: 'POST', corps: { identifiant } });
    compte = donnees.compte;
    retenirJeton(donnees.jeton);
    retenirNom(compte.prenom);
    localStorage.setItem('synergie.identifiant', identifiant);
    return true;
  }

  /** Le premier appareil : on garde la trace du poste de travail pour le compte. */
  async function signalerLePoste() {
    try {
      await appel('/api/comptes/moi', { methode: 'PUT', corps: {
        poste: localStorage.getItem('synergie.poste') || posteDetecte(),
        appareil: appareilDetecte() } });
    } catch (erreur) { /* sans conséquence */ }
  }

  // ---------------------------------------------------------------- INVITATION
  /** Le lien reçu par courriel : on choisit son prénom et son identifiant. */
  async function ouvrirInvitation(jeton) {
    try {
      const donnees = await appel('/api/invitations/' + encodeURIComponent(jeton));
      invitationEnCours = { jeton, ...donnees };
      $('#titre-invitation').textContent = donnees.projet
        ? 'Rejoindre « ' + donnees.projet.nom + ' »' : 'Activer mon accès';
      $('#invitation-projet').textContent = donnees.invitation.prenom
        ? 'Bonjour ' + donnees.invitation.prenom + ' !' : 'Bonjour !';
      $('#invitation-email').textContent = 'Votre adresse : ' + donnees.invitation.email
        + ' (' + (roles.find((r) => r.cle === donnees.invitation.role) || {}).libelle + ')';
      $('#invitation-prenom').value = donnees.invitation.prenom || '';
      afficherVue('invitation');
      $('#vue-invitation').classList.remove('cache');
      setTimeout(() => $('#invitation-identifiant').focus(), 200);
    } catch (erreur) {
      toast(erreur.message);
      history.replaceState(null, '', location.pathname);
      demarrer();
    }
  }

  async function activerInvitation() {
    const prenom = ($('#invitation-prenom').value || '').trim();
    const identifiant = ($('#invitation-identifiant').value || '').trim();
    const erreur = $('#invitation-erreur');
    if (!prenom) { erreur.textContent = 'Indiquez votre prénom.'; return; }
    if (!identifiant) { erreur.textContent = 'Choisissez votre identifiant personnel.'; return; }
    try {
      const donnees = await appel('/api/invitations/' + invitationEnCours.jeton,
        { methode: 'POST', corps: { prenom, identifiant } });
      compte = donnees.compte;
      retenirJeton(donnees.jeton);
      retenirNom(compte.prenom);
      localStorage.setItem('synergie.identifiant', identifiant);
      $('#vue-invitation').classList.add('cache');
      history.replaceState(null, '', location.pathname);
      toast('Bienvenue ' + prenom + ' !');
      await entrerDansLAtelier();
    } catch (e) {
      erreur.textContent = e.message;
    }
  }

  // ---------------------------------------------------------------- VOTE
  /** Le lien de vote reçu par courriel : une personne, une voix. */
  /** Répondre depuis l'application : la personne est déjà reconnue, pas besoin de lien. */
  async function repondreDansApplication(consultationId) {
    try {
      const donnees = await appel('/api/consultations/' + consultationId + '/repondre');
      consultationRepondue = consultationId;
      jetonVote = null;
      afficherQuestionnaire(donnees);
    } catch (erreur) {
      toast(erreur.message);
    }
  }

  /** Répondre à un vote (oui / non) ou à un sondage (plusieurs questions). */
  async function ouvrirVote(jeton) {
    try {
      const donnees = await appel('/api/votes/' + encodeURIComponent(jeton));
      jetonVote = jeton;
      consultationRepondue = null;
      afficherQuestionnaire(donnees);
    } catch (erreur) {
      toast(erreur.message);
      history.replaceState(null, '', location.pathname);
      demarrer();
    }
  }

  /** La fenêtre de réponse, commune au lien personnel et à la réponse depuis l'application. */
  function afficherQuestionnaire(donnees) {
    {
      const consultation = donnees.consultation || {};
      $('#titre-vote').textContent = (consultation.type === 'vote' ? 'Vote' : 'Sondage')
        + ' — ' + (donnees.groupe || '');
      $('#vote-groupe').textContent = donnees.scrutin === 'projet'
        ? 'Tous les membres du projet sont consultés.' : 'Les membres du groupe sont consultés.';
      $('#vote-question').textContent = consultation.intitule || '';
      $('#vote-detail').textContent = consultation.detail || '';
      const zone = $('#vote-questions');
      zone.innerHTML = '';
      (consultation.questions || []).forEach((question) =>
        zone.append(construireReponse(question, consultation.type)));

      const close = consultation.statut && consultation.statut !== 'ouverte';
      $('#btn-envoyer-reponses').disabled = Boolean(donnees.deja_repondu || close);
      $('#vote-etat').textContent = donnees.deja_repondu
        ? 'Vous avez déjà répondu : merci !'
        : (close ? 'Cette consultation est close : les réponses ne sont plus ouvertes.'
                 : 'Répondez, puis envoyez.');
      afficherVue('vote');
      $('#vue-vote').classList.remove('cache');
    }
  }

  /** Une question, dessinée selon son type (le type décide de la façon de répondre). */
  function construireReponse(question, typeConsultation) {
    const bloc = element('div', { classe: 'question-reponse' });
    bloc.dataset.question = question.id;
    bloc.append(element('p', { classe: 'vote-question', texte: question.intitule }));

    if (typeConsultation === 'vote' || question.type === 'oui_non') {
      const barre = element('div', { classe: 'barre-boutons' });
      [['oui', 'Oui'], ['non', 'Non']].forEach(([valeur, mot]) => {
        const bouton = element('button', { classe: 'petit', texte: mot });
        bouton.dataset.valeur = valeur;
        bouton.addEventListener('click', () => {
          barre.querySelectorAll('button').forEach((b) => b.classList.remove('actif'));
          bouton.classList.add('actif');
        });
        barre.append(bouton);
      });
      bloc.append(barre);
      return bloc;
    }
    if (question.type === 'unique' || question.type === 'liste') {
      const menu = element('select', { attrs: { 'aria-label': question.intitule } });
      menu.append(element('option', { texte: 'Choisissez…', attrs: { value: '' } }));
      (question.options || []).forEach((option) =>
        menu.append(element('option', { texte: option, attrs: { value: option } })));
      bloc.append(menu);
      return bloc;
    }
    if (question.type === 'multiple') {
      (question.options || []).forEach((option) => {
        const case_ = element('input', { attrs: { type: 'checkbox', value: option } });
        const ligne = element('label', { classe: 'case' });
        poser(ligne, case_, element('span', { texte: option }));
        bloc.append(ligne);
      });
      return bloc;
    }
    if (question.type === 'likert') {
      const barre = element('div', { classe: 'barre-boutons echelle' });
      [1, 2, 3, 4, 5].forEach((note) => {
        const bouton = element('button', { classe: 'petit', texte: String(note) });
        bouton.dataset.valeur = String(note);
        bouton.addEventListener('click', () => {
          barre.querySelectorAll('button').forEach((b) => b.classList.remove('actif'));
          bouton.classList.add('actif');
        });
        barre.append(bouton);
      });
      bloc.append(barre, element('p', { classe: 'aide fin',
        texte: '1 = pas du tout d\'accord · 5 = tout à fait d\'accord' }));
      return bloc;
    }
    if (question.type === 'mot') {
      bloc.append(element('input', { attrs: { placeholder: 'Un mot', maxlength: '40' } }));
      return bloc;
    }
    return bloc;
  }

  /** Ce qui a été répondu, question par question (les vides restent vides). */
  function lireReponses() {
    const reponses = {};
    document.querySelectorAll('#vote-questions .question-reponse').forEach((bloc) => {
      const question = bloc.dataset.question;
      const actif = bloc.querySelector('button.actif');
      const cases = [...bloc.querySelectorAll('input[type="checkbox"]:checked')];
      const menu = bloc.querySelector('select');
      const champ = bloc.querySelector('input:not([type="checkbox"])');
      if (actif) reponses[question] = [actif.dataset.valeur];
      else if (cases.length) reponses[question] = cases.map((c) => c.value);
      else if (menu) reponses[question] = menu.value ? [menu.value] : [];
      else if (champ) reponses[question] = champ.value.trim() ? [champ.value.trim()] : [];
    });
    return reponses;
  }

  async function envoyerReponses() {
    $('#vote-etat').textContent = 'Enregistrement…';
    const adresse = consultationRepondue
      ? '/api/consultations/' + consultationRepondue + '/repondre'
      : '/api/votes/' + jetonVote;
    try {
      await appel(adresse, { methode: 'POST', corps: { reponses: lireReponses() } });
      $('#btn-envoyer-reponses').disabled = true;
      $('#vote-etat').textContent = 'Vos réponses sont enregistrées. Merci !';
      toast('Réponses envoyées.');
      if (consultationRepondue) {
        await chargerAttente();
        await chargerConsultations();
      }
    } catch (erreur) {
      $('#vote-etat').textContent = erreur.message;
    }
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
    $('#c-identifiant').value = compte.identifiant || '';
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
        identifiant: $('#c-identifiant').value.trim(),
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

  /** Quitter proprement : le jeton du navigateur ne vaut plus rien, et l'on revient à
      l'entrée par identifiant personnel (demande de l'utilisateur, 09/10/2026 : il fallait
      pouvoir reprendre son identifiant sur un appareil où l'on s'était identifié autrement —
      sans cela, l'application restait collée au compte du navigateur). */
  async function seDeconnecter() {
    if (!confirm('Se déconnecter de Synergie sur cet appareil ?')) return;
    try {
      await appel('/api/deconnexion', { methode: 'POST' });
    } catch (erreur) {                          // réseau capricieux : on quitte quand même
      /* on efface de toute façon ce que garde le navigateur */
    }
    if (flux) { flux.close(); flux = null; }
    if (fluxGeneral) { fluxGeneral.close(); fluxGeneral = null; }
    ['synergie.jeton', 'synergie.projet', 'synergie.nom', 'synergie.identifiant']
      .forEach((cle) => localStorage.removeItem(cle));
    compte = null; projet = null; theme = null;
    membresProjet = []; membresTheme = [];
    $('#vue-compte').classList.add('cache');
    $('#liste-projets').innerHTML = '';
    afficherVue('projets');
    demanderPrenom();                           // l'écran d'entrée par identifiant
    toast('Vous êtes déconnecté(e) : entrez avec votre identifiant.');
  }

  // ================================================================ CADRE DE TRAVAIL
  /** Le cadre de travail : on le lit en cliquant le NOM DU PROJET (consigne du
      08/10/2026), il n'occupe plus la page. Seul l'administrateur du projet le modifie. */
  async function chargerCadre() {
    try {
      const cadre = await appel('/api/projets/' + projet.id + '/cadre');
      cadreProjet = cadre;
      afficherCadre();
      const donnees = await appel('/api/projets/' + projet.id + '/documents');
      afficherComptesRendus(donnees.documents || []);
    } catch (erreur) { /* sans conséquence */ }
  }

  /** Le cadre se lit en clair ; « Modifier » ne s'affiche que pour l'administrateur. */
  function afficherCadre({ enEdition = false } = {}) {
    const lecture = $('#cadre-lecture');
    const zone = $('#cadre-contexte');
    const texte = (cadreProjet && cadreProjet.contexte) || '';
    const administre = roleProjet === 'admin';
    lecture.textContent = texte || 'Le cadre de travail n\'est pas encore renseigné.';
    lecture.classList.toggle('cache', enEdition || !texte);
    zone.classList.toggle('cache', !enEdition);
    $('#cadre-modifier').classList.toggle('cache', !administre || enEdition || !texte);
    $('#cadre-enregistrer').classList.toggle('cache', !enEdition);
    $('#cadre-annuler').classList.toggle('cache', !enEdition);
    zone.value = texte;
    $('#cadre-etat').textContent = cadreProjet && cadreProjet.maj_le
      ? 'Dernière modification par ' + (cadreProjet.maj_par || 'quelqu\'un') + ' '
        + quand(cadreProjet.maj_le)
      : '';
  }

  async function ouvrirCadre() {
    if (!projet) return;
    await chargerCadre();
    afficherCadre();
    $('#vue-cadre').classList.remove('cache');
    $('#cadre-lecture').focus();
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
    if (roleProjet !== 'admin') { toast('Seul l\'administrateur du projet peut modifier le cadre.'); return; }
    $('#cadre-etat').textContent = 'Enregistrement…';
    await appel('/api/projets/' + projet.id + '/cadre',
      { methode: 'PUT', corps: { contexte: $('#cadre-contexte').value } });
    await chargerCadre();
    afficherCadre();
    toast('Cadre de travail enregistré.');
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

  /** Le fil d'une discussion. `moderation` : où retirer un message (auteur ou admin). */
  function afficherFil(zone, messages, sujet, { moderation = '', administre = false } = {}) {
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
      // MODÉRATION : l'auteur peut retirer son message ; un administrateur peut retirer
      // n'importe lequel (« posts non adaptés »).
      if (moderation && (administre || message.qui === monNom())) {
        const retirer = element('button', { classe: 'retirer-message', texte: 'Retirer' });
        retirer.title = administre && message.qui !== monNom()
          ? 'Retirer ce message (modération)' : 'Retirer mon message';
        retirer.addEventListener('click', async () => {
          if (!confirm('Retirer ce message de la discussion ?')) return;
          try {
            await appel(moderation + '/' + message.id, { methode: 'DELETE' });
            toast('Message retiré.');
          } catch (erreur) { toast(erreur.message); }
        });
        ligne.append(retirer);
      }
      zone.append(ligne);
    });
    if (proche) zone.scrollTop = zone.scrollHeight;
  }

  async function chargerChatGeneral() {
    try {
      const donnees = await appel('/api/projets/' + projet.id + '/messages');
      afficherFil($('#chat-general'), donnees.messages || [], '',
        { moderation: '/api/projets/' + projet.id + '/messages',
          administre: roleProjet === 'admin' });
    } catch (erreur) { /* sans conséquence */ }
  }

  async function chargerChatTheme() {
    if (!theme) return;
    try {
      const donnees = await appel('/api/themes/' + theme.id + '/messages');
      afficherFil($('#fil-theme'), donnees.messages || [], '',
        { moderation: '/api/themes/' + theme.id + '/messages',
          administre: estAdministrateurTheme() });
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
  /** La pastille d'une personne : ses initiales sur une couleur stable — comme la photo de
      profil d'un groupe de discussion, mais dessinée (demande de l'utilisateur, 09/10/2026). */
  function pastilleMembre(prenom) {
    const mots = (prenom || '?').trim().split(/\s+/).filter(Boolean);
    const initiales = ((mots[0] || '?')[0] + (mots[1] ? mots[1][0] : '')).toUpperCase();
    const teintes = ['#3a56c9', '#12907d', '#b0561b', '#7a3ea8', '#b3261e', '#0f6d8c', '#4a6cf7'];
    let somme = 0;
    for (const lettre of (prenom || '')) somme += lettre.codePointAt(0);
    return element('span', { classe: 'pastille-membre', texte: initiales,
      style: 'background:' + teintes[somme % teintes.length],
      attrs: { 'aria-hidden': 'true' } });
  }

  /** Un membre, à la manière d'un groupe de discussion : sa pastille, son nom, son rôle — et
      un appui sur la ligne ouvre de quoi CHANGER SON RÔLE ou LE RETIRER.

      Le même affichage sert au PROJET et aux GROUPES (demande de l'utilisateur, 09/10/2026) ;
      la case « me prévenir par courriel » a disparu : chacun règle ses alertes lui-même dans
      « Mon compte ». */
  function ligneMembre(membre, { portee, identifiant, administre = true }) {
    const quoi = portee === 'projet' ? 'du projet' : 'du groupe';
    const chemin = portee === 'projet'
      ? `/api/projets/${identifiant}/membres/${membre.compte}`
      : `/api/themes/${identifiant}/membres/${membre.compte}`;
    const rafraichir = async () => {
      if (portee === 'projet') await rafraichirProjet(); else await rafraichirMembresTheme();
    };

    const tete = element('button', { classe: 'membre-tete',
      attrs: { type: 'button', 'aria-expanded': 'false' } });
    poser(tete,
      pastilleMembre(membre.prenom),
      element('span', { classe: 'membre-identite' },
        element('strong', { texte: membre.prenom }),
        element('span', { classe: 'membre-detail', texte: membre.email || 'pas de courriel' })),
      element('span', { classe: 'etiquette-role', texte: membre.libelle_role || membre.role }));

    if (!administre) {                        // simple lecture : personne ne se modifie ici
      tete.disabled = true;
      return element('div', { classe: 'membre' }, tete);
    }
    tete.append(element('span', { classe: 'membre-chevron', texte: '⋯', attrs: { 'aria-hidden': 'true' } }));

    // --- ce que l'on peut faire : le rôle, puis le retrait ---------------------------------
    const choix = element('div', { classe: 'roles-choix' });
    roles.forEach((r) => {
      const pastille = element('button', { classe: 'role-choix' + (r.cle === membre.role ? ' actif' : ''),
        texte: r.libelle, attrs: { type: 'button', title: r.description || '' } });
      pastille.addEventListener('click', async () => {
        if (r.cle === membre.role) return;
        try {
          await appel(chemin, { methode: 'PUT', corps: { role: r.cle } });
          await rafraichir();
          toast(membre.prenom + ' est ' + r.libelle.toLowerCase() + ' ' + quoi + '.');
        } catch (erreur) { toast(erreur.message); }
      });
      choix.append(pastille);
    });
    const retirer = element('button', { classe: 'danger petit', texte: 'Retirer ' + quoi,
      attrs: { type: 'button' } });
    retirer.addEventListener('click', async () => {
      if (!confirm('Retirer ' + membre.prenom + ' ' + quoi + ' ?')) return;
      try {
        await appel(chemin, { methode: 'DELETE' });
        await rafraichir();
        toast(membre.prenom + ' ne fait plus partie ' + quoi + '.');
      } catch (erreur) { toast(erreur.message); }
    });
    const actions = element('div', { classe: 'membre-actions cache' },
      element('span', { classe: 'aide', texte: 'Rôle ' + quoi }),
      choix, retirer);

    tete.addEventListener('click', () => {
      const ouvert = !actions.classList.contains('cache');
      actions.classList.toggle('cache', ouvert);
      tete.setAttribute('aria-expanded', ouvert ? 'false' : 'true');
    });
    return element('div', { classe: 'membre' }, tete, actions);
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
    }
    if (administre) afficherInvitations();
    // Le MÊME affichage pour le projet et pour les groupes (demande de l'utilisateur,
    // 09/10/2026) ; seuls les administrateurs peuvent changer un rôle ou retirer quelqu'un.
    membresProjet.forEach((membre) => {
      zone.append(ligneMembre(membre, { portee: 'projet', identifiant: projet.id,
                                        administre }));
    });
  }

  async function ouvrirMembresProjet() {
    if (!projet) return;
    const menu = $('#membre-role');
    menu.innerHTML = '';
    roles.forEach((r) => {
      const option = element('option', { texte: r.libelle,
        attrs: { value: r.cle, title: r.description } });
      if (r.cle === 'membre') option.selected = true;
      menu.append(option);
    });
    if (!membresProjet.length) await rafraichirProjet(); else afficherMembresProjet();
    $('#vue-membres').classList.remove('cache');
  }

  /** Les adresses saisies : une par ligne, ou séparées par des virgules ou des points-virgules. */
  function adressesSaisies(champ) {
    const brut = (champ && champ.value) || '';
    return [...new Set(brut.split(/[\s,;]+/)
      .map((adresse) => adresse.trim().toLowerCase())
      .filter(Boolean))];
  }

  /** Ajouter PLUSIEURS personnes d'un coup : une invitation par adresse, en un seul geste.

      « À la volée » (demande de l'utilisateur, 09/10/2026) : on colle la liste des adresses et
      tout part d'un coup. Une adresse refusée est signalée, jamais silencieuse. */
  async function ajouterPlusieurs(chemin, champ, corps) {
    const adresses = adressesSaisies(champ);
    if (!adresses.length) { champ.focus(); return null; }
    const faites = [], refusees = [];
    for (const email of adresses) {
      try {
        faites.push(await appel(chemin, { methode: 'POST', corps: { ...corps, email } }));
      } catch (erreur) {
        refusees.push(email);
      }
    }
    if (faites.length) champ.value = '';
    return { faites, refusees };
  }

  /** Le compte rendu d'un ajout en série, en une phrase. */
  function direAjout(faites, refusees, suite) {
    const morceaux = [];
    if (faites.length) {
      morceaux.push(faites.length === 1 ? '1 personne ajoutée'
        : faites.length + ' personnes ajoutées');
    }
    if (refusees.length) {
      morceaux.push(refusees.length + ' adresse(s) refusée(s) : ' + refusees.join(', '));
    }
    if (!morceaux.length) { toast('Aucune adresse à ajouter.'); return; }
    toast(morceaux.join(' · ') + (suite ? ' — ' + suite : ''));
  }

  /** Ajouter PLUSIEURS personnes au PROJET : une adresse par ligne, un seul geste. */
  async function inviterAuProjet() {
    const resultat = await ajouterPlusieurs('/api/projets/' + projet.id + '/invitations',
      $('#membres-emails'), { role: $('#membre-role').value });
    if (!resultat) return;
    await rafraichirProjet();
    const aTransmettre = resultat.faites.filter((donnees) => !donnees.envoye).length;
    direAjout(resultat.faites, resultat.refusees,
      aTransmettre ? 'les liens personnels sont en dessous, à copier et transmettre.' : '');
  }

  /** Une invitation : son adresse, son rôle, et SON lien personnel à copier. */
  function ligneInvitation(invitation, message) {
    const ligne = element('div', { classe: 'invitation' });
    const infos = element('div', { classe: 'invitation-tete' });
    poser(infos,
      element('strong', { texte: invitation.email || invitation.prenom || 'invitation' }),
      element('span', { classe: 'etiquette-role', texte: invitation.libelle_role
        || (roles.find((r) => r.cle === (invitation.role_theme || invitation.role)) || {}).libelle
        || '' }),
      element('span', { classe: 'aide', texte: 'créé ' + quand(invitation.cree_le)
        + (invitation.theme ? ' · pour ce groupe' : '')
        + (invitation.envoyee_le ? ' · envoyée par courriel ' + quand(invitation.envoyee_le)
                                 : ' · pas encore envoyée') }));
    ligne.append(infos);
    if (message) ligne.append(element('p', { classe: 'aide fin', texte: message }));
    const champ = element('input', { classe: 'lien-invitation',
      attrs: { readonly: 'readonly', value: invitation.lien || '' } });
    const copier = element('button', { classe: 'discret petit', texte: 'Copier le lien' });
    copier.addEventListener('click', async () => {
      try { await navigator.clipboard.writeText(invitation.lien); toast('Lien copié.'); }
      catch (e) { champ.select(); document.execCommand('copy'); toast('Lien copié.'); }
    });
    poser(ligne, champ, copier);
    // Le courriel peut être EXPÉDIÉ (ou renvoyé) sans quitter la fenêtre : c'est ce qu'on veut
    // quand les envois viennent d'être rouverts (demande de l'utilisateur, 09/10/2026).
    if (envoiCourriel) {
      const envoyer = element('button', { classe: 'principal petit', texte: 'Envoyer' });
      envoyer.addEventListener('click', async () => {
        envoyer.disabled = true;
        try {
          const resultat = await appel(cheminEnvoiInvitations(), { methode: 'POST',
            corps: { invitations: [invitation.id] } });
          toast(resultat.envoyes
            ? 'Invitation envoyée à ' + invitation.email + '.'
            : 'Envoi impossible : le lien reste à copier ci-dessus.');
          if (!resultat.envoyes) envoyer.disabled = false;
        } catch (erreur) {
          toast(erreur.message);
          envoyer.disabled = false;
        }
      });
      ligne.append(envoyer);
    }
    return ligne;
  }

  /** Où envoyer les invitations : au projet, ou au groupe ouvert dans la fenêtre. */
  function cheminEnvoiInvitations() {
    return theme && !$('#zone-membres-theme').classList.contains('cache')
      ? '/api/themes/' + theme.id + '/invitations/envoi'
      : '/api/projets/' + projet.id + '/invitations/envoi';
  }

  /** Envoyer d'un geste toutes les invitations encore en attente. */
  async function envoyerInvitationsEnAttente(invitations) {
    const auGroupe = cheminEnvoiInvitations().includes('/themes/');
    try {
      const resultat = await appel(cheminEnvoiInvitations(), { methode: 'POST', corps: {} });
      toast(resultat.envoyes
        ? resultat.envoyes + ' invitation(s) envoyée(s) par courriel.'
        : 'Aucune invitation à envoyer : les liens restent à copier.');
      if (auGroupe) await afficherInvitationsTheme(); else await afficherInvitations();
    } catch (erreur) {
      toast(erreur.message);
    }
  }

  /** Les invitations en attente (celles dont le lien n'a pas encore été utilisé). */
  async function afficherInvitations() {
    const zone = $('#invitations-en-cours');
    if (!zone) return;
    zone.innerHTML = '';
    let invitations = [];
    try {
      const donnees = await appel('/api/projets/' + projet.id + '/invitations');
      invitations = donnees.invitations || [];
      envoiCourriel = donnees.envoi_actif !== false;
    } catch (erreur) { return; }
    const maintenant_ = new Date().toISOString().slice(0, 19) + 'Z';
    const attente = invitations.filter((i) => !i.utilise_le && i.expire_le > maintenant_
                                             && !i.theme);
    if (!attente.length) return;
    zone.append(element('p', { classe: 'aide',
      texte: attente.length + ' invitation(s) en attente — copiez le lien et transmettez-le :' }));
    attente.forEach((invitation) => zone.append(ligneInvitation(invitation)));
    zone.append(boutonCopierLiens(attente));
    if (envoiCourriel) {
      const envoyer = element('button', { classe: 'principal petit',
        texte: attente.length > 1 ? 'Envoyer les ' + attente.length + ' invitations'
                                  : 'Envoyer l\'invitation' });
      envoyer.addEventListener('click', () => envoyerInvitationsEnAttente(attente));
      zone.append(envoyer);
    } else {
      zone.append(element('p', { classe: 'aide fin', texte:
        'Envois de courriel suspendus : les liens ci-dessus restent à transmettre à la main '
        + '(ils seront envoyés dès que les envois seront rouverts).' }));
    }
  }

  /** Copier d'un geste les liens de plusieurs invitations (un par ligne). */
  function boutonCopierLiens(invitations) {
    const bouton = element('button', { classe: 'discret petit', attrs: { type: 'button' },
      texte: invitations.length > 1 ? 'Copier les ' + invitations.length + ' liens'
                                    : 'Copier le lien' });
    bouton.addEventListener('click', async () => {
      const liste = invitations.map((invitation) => (invitation.prenom
        ? invitation.prenom + ' : ' : '') + invitation.lien).join('\n');
      try {
        await navigator.clipboard.writeText(liste);
        toast(invitations.length + ' lien(s) copié(s) — il n\'y a plus qu\'à les transmettre.');
      } catch (erreur) {
        toast('Copie automatique impossible : copiez les liens un par un.');
      }
    });
    return bouton;
  }

  /** Inviter PLUSIEURS personnes dans CE GROUPE : un lien personnel par adresse. */
  async function inviterDansLeGroupe() {
    const resultat = await ajouterPlusieurs('/api/themes/' + theme.id + '/invitations',
      $('#invitation-theme-email'), { role: $('#invitation-theme-role').value });
    if (!resultat) return;
    await afficherInvitationsTheme();
    direAjout(resultat.faites, resultat.refusees,
      'les liens personnels sont en dessous, à copier et transmettre.');
  }

  async function afficherInvitationsTheme(recents = []) {
    const zone = $('#invitations-theme');
    if (!zone || !theme) return;
    zone.innerHTML = '';
    let invitations = [];
    try {
      const donnees = await appel('/api/themes/' + theme.id + '/invitations');
      invitations = donnees.invitations || [];
      envoiCourriel = donnees.envoi_actif !== false;
    } catch (erreur) { return; }
    const attente = invitations.filter((i) => !i.utilise_le);
    attente.forEach((invitation) => zone.append(ligneInvitation(invitation,
      'Ce lien ne sert qu\'une fois : en l\'ouvrant, la personne choisit son identifiant et '
      + 'rejoint ce groupe.')));
    if (attente.length) {
      zone.append(boutonCopierLiens(attente));
      if (envoiCourriel) {
        const envoyer = element('button', { classe: 'principal petit',
          texte: attente.length > 1 ? 'Envoyer les ' + attente.length + ' invitations'
                                    : 'Envoyer l\'invitation' });
        envoyer.addEventListener('click', () => envoyerInvitationsEnAttente(attente));
        zone.append(envoyer);
      }
    }
  }

  function afficherMembresTheme() {
    const zone = $('#liste-membres-theme');
    zone.innerHTML = '';
    const administre = estAdministrateurTheme();
    if (administre) {
      remplirMembresThemesDisponibles();
      afficherInvitationsTheme();
    } else {
      $('#inviter-theme').classList.add('cache');
      $('#inviter-theme-externe').classList.add('cache');
    }
    const menu = $('#membre-theme-role');
    if (menu.options.length !== roles.length) {
      menu.innerHTML = '';
      roles.forEach((r) => {
        const option = element('option', { texte: r.libelle,
          attrs: { value: r.cle, title: r.description } });
        if (r.cle === 'membre') option.selected = true;
        menu.append(option);
      });
    }
    if (!membresTheme.length) {
      zone.append(element('p', { classe: 'aide', texte:
        'Personne n\'a de rôle particulier ici : tous les membres du projet participent.' }));
      return;
    }
    membresTheme.forEach((membre) => {
      zone.append(ligneMembre(membre, { portee: 'theme', identifiant: theme.id, administre }));
    });
  }

  /** Ajouter au groupe PLUSIEURS membres du projet, avec un rôle propre au groupe. */
  async function inviterAuTheme() {
    const cases = [...document.querySelectorAll('#membre-theme-comptes input:checked')];
    if (!cases.length) { toast('Cochez au moins une personne.'); return; }
    const role = $('#membre-theme-role').value;
    const noms = cases.map((c) => c.dataset.nom || '');
    for (const cochee of cases) {
      await appel('/api/themes/' + theme.id + '/membres', { methode: 'POST', corps: {
        compte: cochee.value, role, notifier: true } });
    }
    await rafraichirMembresTheme();
    toast(cases.length === 1 ? noms[0] + ' a rejoint le groupe.'
      : cases.length + ' personnes ont rejoint le groupe.');
  }

  /** La liste des personnes du projet qui n'ont pas encore de rôle ici, à cocher.

      Plusieurs à la fois (demande de l'utilisateur, 09/10/2026) : on coche qui l'on veut, on
      choisit UN rôle, et tout est ajouté d'un coup. */
  function remplirMembresThemesDisponibles() {
    const zone = $('#membre-theme-comptes');
    if (!zone) return;
    const dejaLa = new Set(membresTheme.map((m) => m.compte));
    zone.innerHTML = '';
    const libres = membresProjet.filter((m) => !dejaLa.has(m.compte));
    libres.forEach((membre) => {
      const etiquette = element('label', { classe: 'choix-membre' });
      const coche = element('input', { attrs: { type: 'checkbox', value: membre.compte } });
      coche.dataset.nom = membre.prenom;
      etiquette.append(coche,
        element('span', { texte: membre.prenom }),
        element('span', { classe: 'aide',
          texte: membre.email || 'pas de courriel' }));
      zone.append(etiquette);
    });
    if (libres.length > 1) {                      // tout prendre d'un geste
      const tout = element('button', { classe: 'discret petit', texte: 'Tout cocher',
        attrs: { type: 'button' } });
      tout.addEventListener('click', () => {
        const cases = [...zone.querySelectorAll('input')];
        const aCocher = cases.some((c) => !c.checked);
        cases.forEach((c) => { c.checked = aCocher; });
        majBoutonAjoutTheme();
      });
      zone.append(tout);
    }
    const menuRoleExterne = $('#invitation-theme-role');
    if (menuRoleExterne && !menuRoleExterne.options.length) {
      roles.forEach((r) => {
        const option = element('option', { texte: r.libelle,
          attrs: { value: r.cle, title: r.description } });
        if (r.cle === 'membre') option.selected = true;
        menuRoleExterne.append(option);
      });
    }
    const possible = libres.length > 0;
    $('#inviter-theme').classList.toggle('cache', !possible);
    $('#inviter-theme-note').classList.toggle('cache', possible);
    if (!possible) {
      $('#inviter-theme-note').textContent = 'Tous les membres du projet ont déjà un rôle dans ce groupe.';
    }
    majBoutonAjoutTheme();
  }

  /** Le bouton dit combien de personnes seront ajoutées : « Ajouter au groupe (3) ». */
  function majBoutonAjoutTheme() {
    const bouton = $('#membre-theme-ajouter');
    const zone = $('#membre-theme-comptes');
    if (!bouton || !zone) return;
    const combien = zone.querySelectorAll('input:checked').length;
    bouton.textContent = combien ? 'Ajouter au groupe (' + combien + ')'
                                 : 'Ajouter au groupe';
    bouton.disabled = !combien;                   // rien de coché : on n'ajoute rien
  }

  /** Un ✕ en haut à droite de chaque grande fenêtre : on la ferme sans chercher le bouton du
      bas (défaut rapporté le 09/10/2026 : « je ne vois pas le bouton fermé »). Le ✕ déclenche
      le MÊME bouton de fermeture que celui du bas, pour garder exactement le même effet. */
  function poserCroixDeFermeture() {
    document.querySelectorAll('.boite-nom.large').forEach((boite) => {
      if (boite.querySelector('.croix-fermeture')) return;
      const titre = boite.querySelector('h2');
      if (!titre) return;
      const fermer = [...boite.querySelectorAll('button')].find((b) => /-fermer$/.test(b.id));
      const croix = element('button', { classe: 'croix-fermeture discret', texte: '✕',
        attrs: { type: 'button', 'aria-label': 'Fermer', title: 'Fermer' } });
      croix.addEventListener('click', () => {
        if (fermer) { fermer.click(); return; }
        const voile = boite.closest('.voile');
        if (voile) voile.classList.add('cache');
      });
      titre.append(croix);                        // dans le titre : il reste visible en défilant
    });
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
    brancherInstallation();
    poserCroixDeFermeture();
    // --- la barre de navigation du téléphone
    document.querySelectorAll('#nav-mobile button').forEach((bouton) => {
      bouton.addEventListener('click', () => {
        afficherSectionMobile(bouton.dataset.section);
        window.scrollTo({ top: 0, behavior: 'smooth' });
      });
    });
    mediaEtroit.addEventListener('change', appliquerMode);
    $('#btn-voir-tableau').addEventListener('click', () => {
      const tableau = document.body.dataset.tableau === 'oui';
      document.body.dataset.tableau = tableau ? 'non' : 'oui';
      $('#btn-voir-tableau').textContent = tableau ? 'Voir le tableau' : 'Revenir à la liste';
      if (!tableau) appliquerVue();
    });
    // Au clavier : Échap ferme la fenêtre ouverte et rend le focus au bouton qui l'a ouverte.
    document.addEventListener('keydown', (evenement) => {
      if (evenement.key !== 'Escape') return;
      const fenetre = ['#vue-compte', '#vue-membres', '#vue-cadre', '#vue-liens']
        .find((sel) => !$(sel).classList.contains('cache'));
      if (!fenetre) return;
      $(fenetre).classList.add('cache');
      const retour = fenetre === '#vue-compte' ? $('#btn-compte')
        : fenetre === '#vue-cadre' ? $('#btn-cadre') : $('#btn-membres');
      if (retour) retour.focus();
    });
    $('#btn-compte').addEventListener('click', ouvrirMonCompte);
    $('#c-enregistrer').addEventListener('click', enregistrerMonCompte);
    $('#c-deconnecter').addEventListener('click', seDeconnecter);
    $('#c-fermer').addEventListener('click', () => $('#vue-compte').classList.add('cache'));
    $('#c-essai').addEventListener('click', async () => {      $('#c-etat').textContent = 'Envoi de l\'essai…';
      try {
        const resultat = await appel('/api/alertes/essai', { methode: 'POST', corps: {} });
        $('#c-etat').textContent = resultat.envoye
          ? 'Essai envoyé à ' + resultat.email + '.'
          : 'L\'envoi n\'a pas abouti (voir le journal des alertes).';
      } catch (erreur) { $('#c-etat').textContent = 'Essai impossible : ' + erreur.message; }
    });

    $('#btn-invitation').addEventListener('click', activerInvitation);
    $('#invitation-identifiant').addEventListener('keydown', (e) => {
      if (e.key === 'Enter') activerInvitation();
    });
    document.querySelectorAll('[data-vote]').forEach((bouton) => {
      bouton.addEventListener('click', () => voter(bouton.dataset.vote));
    });
    $('#btn-cadre').addEventListener('click', ouvrirCadre);
    $('#btn-cadre-mobile').addEventListener('click', ouvrirCadre);
    $('#btn-membres-mobile').addEventListener('click', ouvrirMembresProjet);
    $('#cadre-fermer').addEventListener('click', () => $('#vue-cadre').classList.add('cache'));
    $('#cadre-modifier').addEventListener('click', () => afficherCadre({ enEdition: true }));
    $('#cadre-annuler').addEventListener('click', () => afficherCadre());
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
    $('#membre-theme-comptes').addEventListener('change', majBoutonAjoutTheme);
    $('#invitation-theme-creer').addEventListener('click', inviterDansLeGroupe);

    $('#btn-retour').addEventListener('click', fermerTheme);
    $('#btn-renommer-theme').addEventListener('click', enregistrerTheme);
    $('#btn-supprimer-theme').addEventListener('click', async () => {
      if (!confirm('Supprimer ce thème, ses notes, ses documents et ses décisions ?')) return;
      await appel('/api/themes/' + theme.id, { methode: 'DELETE' });
      fermerTheme();
    });


    // --- tableau blanc
    $('#btn-note').addEventListener('click', () => creerNote());
    $('#btn-annuler').addEventListener('click', annuler);
    // Ctrl + Z annule sur le tableau (dans une page de texte, le navigateur s'en occupe).
    document.addEventListener('keydown', (evenement) => {
      if (!(evenement.ctrlKey || evenement.metaKey) || evenement.key.toLowerCase() !== 'z') return;
      if (vue !== undefined && $('#onglet-tableau') && !$('#onglet-tableau').classList.contains('cache')
          && !evenement.target.isContentEditable) {
        evenement.preventDefault();
        annuler();
      }
    });
    $('#page-annuler').addEventListener('click', () => {
      $('#page-contenu').focus();
      document.execCommand('undo');
      programmerPage();
    });
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
    $('#btn-nouveau-vote').addEventListener('click', () =>
      ouvrirFenetreConsultation(null, 'vote'));
    $('#btn-nouveau-sondage').addEventListener('click', () =>
      ouvrirFenetreConsultation(null, 'sondage'));
    $('#btn-ajouter-question').addEventListener('click', () => {
      const type = consultationOuverte ? consultationOuverte.type : typeConsultation;
      $('#consultation-questions').append(construireQuestion({}, type,
        $('#consultation-questions').children.length));
    });
    $('#btn-consultation-brouillon').addEventListener('click', () =>
      enregistrerConsultation({ ouvrirAussi: false }));
    $('#btn-consultation-ouvrir').addEventListener('click', () =>
      enregistrerConsultation({ ouvrirAussi: true }));
    $('#btn-consultation-fermer').addEventListener('click', () =>
      $('#vue-consultation').classList.add('cache'));
    $('#btn-envoyer-reponses').addEventListener('click', envoyerReponses);
    $('#liens-fermer').addEventListener('click', () =>
      $('#vue-liens').classList.add('cache'));

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
    const champ = $('#identifiant');
    voile.classList.remove('cache');
    setTimeout(() => champ.focus(), 200);

    async function valider() {
      try {
        const pret = await entrerAvecIdentifiant();
        if (!pret) return;
      } catch (erreur) {
        $('#nom-erreur').textContent = erreur.message;
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

  /** On entre dans l'atelier : mes projets, puis le dernier projet ouvert (ou le seul).

      Le groupe visé par l'adresse (`#t=…`) est lu AVANT d'ouvrir le projet : ouvrir un
      projet réécrit l'adresse (`#p=…`), ce qui effaçait le groupe visé et faisait ouvrir
      le projet au lieu du groupe (constat du 09/10/2026, en corrigeant la discussion de
      groupe). Un lien de groupe ouvre donc bien le groupe, même sans projet mémorisé. */
  async function entrerDansLAtelier() {
    await chargerProjets();
    const groupe = (location.hash.match(/#t=(.+)/) || [])[1];
    const garde = localStorage.getItem('synergie.projet');
    let cible = (location.hash.match(/#p=(.+)/) || [])[1]
      || (projets.some((p) => p.id === garde) ? garde : '')
      || (projets.length === 1 ? projets[0].id : '');
    if (!cible && groupe) {                       // le groupe dit à quel projet il appartient
      try {
        const fiche = await appel('/api/themes/' + encodeURIComponent(groupe));
        cible = (fiche.theme || {}).projet || '';
      } catch (erreur) { cible = ''; }
    }
    if (!cible) { afficherVue('projets'); return; }
    await ouvrirProjet(cible);
    if (groupe) { try { await ouvrirTheme(groupe, { pousser: false }); } catch (e) { /* inconnu */ } }
  }

  async function demarrer() {
    brancher();
    afficherMode();
    afficherVue('projets');
    roles = [{ cle: 'admin', libelle: 'Administrateur' },
             { cle: 'membre', libelle: 'Membre participant' },
             { cle: 'visiteur', libelle: 'Visiteur' }];
    // Un lien reçu par courriel passe AVANT tout : invitation, puis vote.
    const invitation = (location.hash.match(/#invitation=([^&]+)/) || [])[1];
    if (invitation) { await ouvrirInvitation(invitation); return; }
    const vote = (location.hash.match(/#vote=([^&]+)/) || [])[1];
    if (vote) { await ouvrirVote(vote); return; }
    await chargerMonCompte();                      // le compte d'abord
    if (!compte || !compte.prenom) { demanderPrenom(); return; }
    await signalerLePoste();
    await entrerDansLAtelier();
  }

  // ---------------------------------------------------------------- INSTALLATION (PWA)
  // Synergie s'installe comme une application, sur ordinateur comme sur téléphone : le
  // navigateur prévient quand c'est possible, et on propose alors le bouton « Installer ».
  let invitationInstallation = null;

  window.addEventListener('beforeinstallprompt', (evenement) => {
    evenement.preventDefault();
    invitationInstallation = evenement;
    const bouton = $('#btn-installer');
    if (bouton) bouton.classList.remove('cache');
  });

  async function installerApplication() {
    if (!invitationInstallation) {
      toast('Utilisez le menu de votre navigateur : « Installer l\'application ».');
      return;
    }
    invitationInstallation.prompt();
    const choix = await invitationInstallation.userChoice;
    invitationInstallation = null;
    $('#btn-installer').classList.add('cache');
    toast(choix && choix.outcome === 'accepted' ? 'Synergie est installée !'
                                                : 'Installation annulée.');
  }

  function brancherInstallation() {
    const bouton = $('#btn-installer');
    if (bouton) bouton.addEventListener('click', installerApplication);
  }

  // Le service worker rend l'application installable et utilisable hors connexion.
  if ('serviceWorker' in navigator) {
    window.addEventListener('load', () => {
      navigator.serviceWorker.register('/sw.js').catch(() => {});
    });
  }

  document.addEventListener('DOMContentLoaded', demarrer);
})();
