/* LA BOÎTE À TRAMES — logique de la page unique.

   ROUTES APPELÉES (à brancher côté serveur) :
     POST /api/boite-trame/analyser  -> heures, ETP, comparaison, couverture de nuit
     POST /api/boite-trame/generer   -> jusqu'à 3 trames (grille + compteurs + verdict)

   Si ces routes ne répondent pas, la page calcule elle-même les heures et les ETP
   (secours) et affiche un message clair. Elle n'est jamais blanche. */

"use strict";

const JOURS_COURTS = ["L", "M", "M", "J", "V", "S", "D"];
const JOURS_LONGS = ["Lundi", "Mardi", "Mercredi", "Jeudi", "Vendredi", "Samedi", "Dimanche"];

/* Description d'exemple : elle est pré-remplie au chargement de la page. */
const EXEMPLE = {
  profession: "IDE",
  effectif: { temps_plein: 4, partiel_80: 1, fixes_nuit: 2, dispensees_nuit: 0 },
  postes: [
    { libelle: "Matin", debut: "07:00", fin: "14:00", personnes: 2,
      jours: [1, 1, 1, 1, 1, 1, 1] },
    { libelle: "Après-midi", debut: "14:00", fin: "21:00", personnes: 1,
      jours: [1, 1, 1, 1, 1, 1, 1] },
    { libelle: "Nuit", debut: "21:00", fin: "07:00", personnes: 1,
      jours: [1, 1, 1, 1, 1, 1, 1] },
  ],
  reglages: {
    heures_legales_semaine: 35,
    coefficient_remplacement: 0.10,
    cycle_semaines: 4,
    jours_temps_plein: 5,
    jours_80: 4,
  },
};

const $ = (selecteur) => document.querySelector(selecteur);

/* Codes et couleurs des horaires, EXACTEMENT ceux du planning d'Hermes : le matin est
   jaune, l'après-midi cyan, la nuit violet, une journée longue magenta, les repos verts.
   Le serveur renvoie la même table ; celle-ci sert à colorer la page avant l'échange. */
const CODES_HERMES = {
  M03: { fond: "#ffff99", texte: "#000000", libelle: "Matin" },
  S03: { fond: "#00ffff", texte: "#000000", libelle: "Après-midi" },
  J13: { fond: "#ff00ff", texte: "#000000", libelle: "Journée longue" },
  N02: { fond: "#800080", texte: "#ffffff", libelle: "Nuit" },
  RH:  { fond: "#00ff00", texte: "#000000", libelle: "Repos hebdomadaire" },
  DS:  { fond: "#ffffff", texte: "#000000", libelle: "Disponibilité" },
  FEJ: { fond: "#ff99cc", texte: "#000000", libelle: "Férié" },
  RTT: { fond: "#ccffcc", texte: "#000000", libelle: "Réduction du temps de travail" },
};

/** Le code qu'Hermes donnerait à ce poste : nuit, journée longue, matin ou après-midi. */
function codeHermes(poste) {
  if (poste.code) return poste.code;
  if (estPosteNuit(poste)) return "N02";
  if (dureePoste(poste) >= 10 - 1e-9) return "J13";
  return minutes(poste.debut) < 12 * 60 ? "M03" : "S03";
}

function esc(texte) {
  return String(texte == null ? "" : texte)
    .replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;");
}

function fr(nombre, decimales = 1) {
  const valeur = Number(nombre) || 0;
  return valeur.toLocaleString("fr-FR", {
    minimumFractionDigits: decimales, maximumFractionDigits: decimales,
  });
}

/* ==================================================================================
   Calculs élémentaires (identiques côté serveur)
   ================================================================================== */
function minutes(hhmm) {
  const parties = String(hhmm || "0:0").split(":");
  const h = parseInt(parties[0], 10) || 0;
  const m = parseInt(parties[1], 10) || 0;
  return h * 60 + m;
}

function dureePoste(poste) {
  let ecart = minutes(poste.fin) - minutes(poste.debut);
  if (ecart <= 0) ecart += 24 * 60;
  return ecart / 60;
}

function estPosteNuit(poste) {
  const debut = minutes(poste.debut);
  const fin = minutes(poste.fin);
  if (fin <= debut) return true;
  if (debut >= 20 * 60) return true;
  if (debut < 5 * 60) return true;
  return false;
}

/* Analyse faite dans la page (secours quand le serveur n'est pas branché). */
function analyserLocalement(description) {
  const legales = Number(description.reglages.heures_legales_semaine) || 35;
  const coef = Number(description.reglages.coefficient_remplacement) || 0;
  const detail = [];
  let total = 0;
  description.postes.forEach((poste) => {
    const jours = poste.jours.filter(Boolean).length;
    const heures = (poste.personnes || 0) * dureePoste(poste) * jours;
    total += heures;
    detail.push({
      libelle: poste.libelle, debut: poste.debut, fin: poste.fin,
      duree_heures: dureePoste(poste), personnes: poste.personnes,
      jours_par_semaine: jours, heures_par_semaine: heures,
      est_nuit: estPosteNuit(poste),
    });
  });
  const etpNecessaires = legales ? (total / legales) * (1 + coef) : 0;
  const eff = description.effectif;
  const etpDisponibles = (eff.temps_plein || 0) + 0.8 * (eff.partiel_80 || 0)
    + (eff.fixes_nuit || 0) + (eff.dispensees_nuit || 0);
  const ecart = etpDisponibles - etpNecessaires;
  let nuitNecessaires = 0;
  for (let wd = 0; wd < 7; wd += 1) {
    const besoin = description.postes
      .filter((p) => estPosteNuit(p) && p.jours[wd])
      .reduce((somme, p) => somme + (p.personnes || 0), 0);
    nuitNecessaires = Math.max(nuitNecessaires, besoin);
  }
  const nuitDisponibles = eff.fixes_nuit || 0;
  return {
    profession: description.profession,
    heures_semaine_necessaires: total,
    heures_legales_semaine: legales,
    coefficient_remplacement: coef,
    etp_necessaires: etpNecessaires,
    etp_disponibles: etpDisponibles,
    comparaison: {
      etat: Math.abs(ecart) < 0.05 ? "juste" : (ecart > 0 ? "surplus" : "manque"),
      ecart,
      phrase: Math.abs(ecart) < 0.05
        ? "L'effectif disponible correspond au besoin."
        : (ecart > 0
          ? `Il reste ${fr(ecart)} ETP disponible${ecart > 1 ? "s" : ""}`
          : `Il manque ${fr(-ecart)} ETP`),
    },    explication_coefficient: ("Le coefficient de remplacement ajoute une marge de personnel "
      + "pour assurer les remplacements (absences, congés, formations) : le besoin est "
      + "augmenté d'autant."),
    couverture_nuit: {
      necessaires: nuitNecessaires, disponibles: nuitDisponibles,
      phrase: nuitNecessaires
        ? (nuitDisponibles >= nuitNecessaires
          ? `Couverture de nuit assurée : ${nuitDisponibles} personne(s) fixe(s) de nuit pour ${nuitNecessaires} nécessaire(s).`
          : `Nuit non couverte : ${nuitDisponibles} personne(s) fixe(s) de nuit pour ${nuitNecessaires} nécessaire(s).`)
        : "Aucun poste de nuit décrit.",
    },
    detail_postes: detail,
    effectif: eff,
    reglages: description.reglages,
  };
}

/* ==================================================================================
   Formulaire : les postes
   ================================================================================== */
function joursHTML(jours) {
  return JOURS_COURTS.map((lettre, i) => (
    `<label class="jour"><input type="checkbox" data-jour="${i}" `
    + `${jours && jours[i] ? "checked" : ""}> ${lettre}</label>`
  )).join("");
}

function ajouterPoste(poste) {
  poste = poste || { libelle: "", debut: "07:00", fin: "14:00", personnes: 1,
    jours: [1, 1, 1, 1, 1, 1, 1] };
  const bloc = document.createElement("div");
  bloc.className = "poste";
  bloc.innerHTML = `
    <div class="entete-poste">
      <strong>Poste</strong>
      <button type="button" class="petit danger" data-action="supprimer">Supprimer</button>
    </div>
    <div class="ligne-postes">
      <label>Code (couleur d'Hermes)<select data-champ="code">${
        Object.entries(CODES_HERMES).map(([code, info]) =>
          `<option value="${code}"${codeHermes(poste) === code ? " selected" : ""}>` +
          `${code} — ${esc(info.libelle)}</option>`).join("")}</select></label>
      <label>Libellé<input data-champ="libelle" value="${esc(poste.libelle)}"
        placeholder="Matin, Après-midi, Nuit…"></label>
      <label>Heure de début<input data-champ="debut" type="time" value="${esc(poste.debut)}"></label>
      <label>Heure de fin<input data-champ="fin" type="time" value="${esc(poste.fin)}"></label>
      <label>Nombre de personnes<input data-champ="personnes" type="number" min="0"
        value="${Number(poste.personnes) || 0}"></label>
    </div>
    <div class="jours"><span class="etiquette">Jours couverts :</span>${joursHTML(poste.jours)}</div>`;
  bloc.querySelector("[data-action=supprimer]").addEventListener("click", () => bloc.remove());
  $("#postes").appendChild(bloc);
}

function lecturePostes() {
  return Array.from(document.querySelectorAll("#postes .poste")).map((bloc) => {
    const champ = (nom) => bloc.querySelector(`[data-champ="${nom}"]`);
    const jours = Array.from(bloc.querySelectorAll("[data-jour]")).map((c) => (c.checked ? 1 : 0));
    return {
      libelle: champ("libelle").value.trim(),
      code: champ("code") ? champ("code").value : "",   // couleur d'Hermes choisie
      debut: champ("debut").value || "08:00",
      fin: champ("fin").value || "16:00",
      personnes: parseInt(champ("personnes").value, 10) || 0,
      jours,
    };
  });
}

function constructionDescription() {
  return {
    profession: $("#profession").value,
    effectif: {
      temps_plein: parseInt($("#eff-temps-plein").value, 10) || 0,
      partiel_80: parseInt($("#eff-80").value, 10) || 0,
      fixes_nuit: parseInt($("#eff-nuit").value, 10) || 0,
      dispensees_nuit: parseInt($("#eff-dispense").value, 10) || 0,
    },
    postes: lecturePostes(),
    reglages: {
      heures_legales_semaine: parseFloat($("#reg-heures").value) || 35,
      coefficient_remplacement: (parseFloat($("#reg-coef").value) || 0) / 100,
      cycle_semaines: parseInt($("#reg-cycle").value, 10) || 4,
      jours_temps_plein: parseInt($("#reg-jours-plein").value, 10) || 5,
      jours_80: parseInt($("#reg-jours-80").value, 10) || 4,
    },
  };
}

function preRemplir(description) {
  $("#profession").value = description.profession;
  $("#eff-temps-plein").value = description.effectif.temps_plein;
  $("#eff-80").value = description.effectif.partiel_80;
  $("#eff-nuit").value = description.effectif.fixes_nuit;
  $("#eff-dispense").value = description.effectif.dispensees_nuit;
  $("#reg-heures").value = description.reglages.heures_legales_semaine;
  $("#reg-coef").value = Math.round(description.reglages.coefficient_remplacement * 100);
  $("#reg-cycle").value = String(description.reglages.cycle_semaines);
  $("#reg-jours-plein").value = description.reglages.jours_temps_plein;
  $("#reg-jours-80").value = description.reglages.jours_80;
  $("#postes").innerHTML = "";
  description.postes.forEach(ajouterPoste);
}

/* ==================================================================================
   Messages
   ================================================================================== */
function afficherMessage(texte, estErreur) {
  const zone = $("#message");
  if (!texte) { zone.hidden = true; zone.textContent = ""; return; }
  zone.hidden = false;
  zone.textContent = texte;
  zone.className = "message" + (estErreur ? " erreur" : "");
}

/* ==================================================================================
   Appels au serveur
   ================================================================================== */
async function poster(chemin, corps) {
  const reponse = await fetch(chemin, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(corps),
  });
  if (!reponse.ok) throw new Error(`réponse ${reponse.status}`);
  return reponse.json();
}

/* ==================================================================================
   Affichage : « ce que ça donne »
   ================================================================================== */
function blocResultat(valeur, etiquette, classe) {
  return `<div class="bloc-resultat">
      <div class="valeur ${classe || ""}">${valeur}</div>
      <div class="etiquette">${esc(etiquette)}</div>
    </div>`;
}

function renderResultats(analyse, local) {
  const lignes = analyse.detail_postes.map((p) => `
    <tr>
      <td>${esc(p.libelle)}${p.est_nuit ? " 🌙" : ""}</td>
      <td>${esc(p.debut)} – ${esc(p.fin)}</td>
      <td class="nombre">${fr(p.duree_heures)} h</td>
      <td class="nombre">${p.personnes}</td>
      <td class="nombre">${p.jours_par_semaine}</td>
      <td class="nombre">${fr(p.heures_par_semaine)} h</td>
    </tr>`).join("");

  const classeEcart = analyse.comparaison.etat === "surplus" ? "ecart-surplus"
    : (analyse.comparaison.etat === "manque" ? "ecart-manque" : "");
  $("#resultats").innerHTML = `
    <div class="cartes-resultat">
      ${blocResultat(`${fr(analyse.heures_semaine_necessaires)} h`, "Heures nécessaires par semaine")}
      ${blocResultat(fr(analyse.etp_necessaires, 2), "ETP nécessaires")}
      ${blocResultat(fr(analyse.etp_disponibles, 2), "ETP disponibles")}
      ${blocResultat(`${analyse.comparaison.ecart >= 0 ? "+" : "−"}${fr(Math.abs(analyse.comparaison.ecart), 2)}`,
        "Écart", classeEcart)}
    </div>
    <p class="phrase-forte ${classeEcart}">${esc(analyse.comparaison.phrase)}</p>
    <p class="aide">${esc(analyse.explication_coefficient)}</p>
    <p class="aide"><strong>${esc(analyse.couverture_nuit.phrase)}</strong></p>
    <h3>Détail par poste</h3>
    <div class="roll"><table>
      <thead><tr><th>Poste</th><th>Horaires</th><th>Durée</th><th>Personnes</th>
        <th>Jours/sem.</th><th>Heures/sem.</th></tr></thead>
      <tbody>${lignes}</tbody>
    </table></div>
    ${local ? '<p class="aide">Heures et ETP calculés directement dans la page.</p>' : ""}`;
}

/* ==================================================================================
   Affichage : les trames
   ================================================================================== */
function couleursTrame(trame) {
  if (trame.couleurs) return trame.couleurs;
  const table = { Repos: { fond: CODES_HERMES.RH.fond, texte: CODES_HERMES.RH.texte,
                           code: "RH" } };
  (trame.postes || []).forEach((poste) => {
    const code = codeHermes(poste);
    table[poste.libelle] = { fond: CODES_HERMES[code].fond, texte: CODES_HERMES[code].texte,
                             code };
  });
  return table;
}

/** Une case de la grille, peinte comme dans Hermes : le CODE sur sa couleur. */
function cellule(libelle, trame) {
  const table = couleursTrame(trame);
  const nom = libelle || "Repos";
  const info = table[nom] || table.Repos;
  const poste = (trame.postes || []).find((p) => p.libelle === nom);
  const titre = poste ? `${poste.libelle} — ${poste.debut} à ${poste.fin}`
                      : "Repos hebdomadaire";
  return `<span class="cellule" style="background:${info.fond};color:${info.texte}" ` +
         `title="${esc(titre)}">${esc(info.code || nom)}</span>`;
}

/** La légende des couleurs, sous la grille : ce que veut dire chaque code. */
function legende(trame) {
  const table = couleursTrame(trame);
  const morceaux = [];
  (trame.postes || []).forEach((poste) => {
    const info = table[poste.libelle];
    morceaux.push(`<span class="case-legende" style="background:${info.fond};` +
      `color:${info.texte}">${esc(info.code)}</span> ${esc(poste.libelle)} ` +
      `<small>${esc(poste.debut)} – ${esc(poste.fin)}</small>`);
  });
  morceaux.push(`<span class="case-legende" style="background:${CODES_HERMES.RH.fond};` +
    `color:${CODES_HERMES.RH.texte}">RH</span> Repos hebdomadaire`);
  return `<div class="legende">${morceaux.join("")}</div>`;
}

function tableauSemaine(trame, semaine) {
  const entete = JOURS_LONGS.map((j) => `<th>${j.slice(0, 3)}</th>`).join("");
  const lignes = trame.agents.map((agent) => {
    const cellules = agent.semaines[semaine]
      .map((libelle) => `<td>${cellule(libelle, trame)}</td>`).join("");
    return `<tr><td class="nom">${esc(agent.nom)} <small>(${esc(agent.profil)})</small></td>${cellules}</tr>`;
  }).join("");
  return `<div class="roll">
      <table class="trame-table">
        <thead><tr><th class="nom">Semaine ${semaine + 1}</th>${entete}</tr></thead>
        <tbody>${lignes}</tbody>
      </table>
    </div>`;
}

function renderCompteurs(trame) {
  const g = trame.compteurs;
  const lignes = g.par_personne.map((p) => `
    <tr>
      <td>${esc(p.nom)}</td>
      <td class="nombre">${fr(p.heures_semaine)} h</td>
      <td class="nombre">${fr(p.heures_cycle)} h</td>
      <td class="nombre">${p.jours_repos}</td>
      <td class="nombre">${p.weekends_travailles}</td>
      <td class="nombre">${p.nuits}</td>
      <td class="nombre">${p.max_jours_consecutifs}</td>
      <td class="nombre ${p.ecart_heures > 0 ? "ecart-surplus" : ""}">${p.ecart_heures >= 0 ? "+" : "−"}${fr(Math.abs(p.ecart_heures))} h</td>
    </tr>`).join("");
  return `
    <div class="compteurs">
      <p>Heures travaillées par semaine et par personne (moyenne) :
        <strong>${fr(g.heures_semaine_moyenne)} h</strong> ·
        Total du cycle : <strong>${fr(g.heures_cycle_total)} h</strong> ·
        Week-ends travaillés (tous) : <strong>${g.weekends_travailles_total}</strong> ·
        Nuits (toutes) : <strong>${g.nuits_total}</strong>.</p>
    </div>
    <div class="roll"><table>
      <thead><tr><th>Personne</th><th>Heures/sem.</th><th>Heures/cycle</th><th>Jours repos</th>
        <th>Week-ends</th><th>Nuits</th><th>Jours d'affilée max</th><th>Écart légal</th></tr></thead>
      <tbody>${lignes}</tbody>
    </table></div>`;
}

function renderVerdict(trame) {
  const verdict = trame.verdict;
  const badge = verdict.conforme
    ? '<span class="verdict conforme">Conforme à la réglementation</span>'
    : '<span class="verdict non-conforme">Non conforme — à revoir</span>';
  let details = "";
  if (verdict.manquements && verdict.manquements.length) {
    details = `<p class="aide">Points à corriger :</p><ul class="manquements">`
      + verdict.manquements.map((m) => (
        `<li><strong>${esc(m.personne)}</strong> — ${esc(m.jour)} — ${esc(m.regle)} : ${esc(m.detail)}</li>`
      )).join("") + "</ul>";
  }
  let infos = "";
  if (verdict.informations && verdict.informations.length) {
    infos = `<p class="aide">Informations : ${esc(verdict.informations[0].detail)}</p>`;
  }
  return badge + details + infos;
}

function renderTrame(trame) {
  const semaines = [];
  for (let w = 0; w < trame.semaines; w += 1) semaines.push(tableauSemaine(trame, w));
  let groupes = "";
  if (trame.groupes && trame.groupes.length) {
    groupes = trame.groupes.map((g) => (
      `<p class="groupes">Ces personnes suivent exactement la même trame : ${esc(g.join(", "))}.</p>`
    )).join("");
  }
  let remarques = "";
  if (trame.remarques && trame.remarques.length) {
    remarques = `<div class="remarques">${trame.remarques.map((r) => `<p>${esc(r)}</p>`).join("")}</div>`;
  }
  return `<div class="trame">
      <h3>${esc(trame.titre || `Trame ${trame.numero}`)}</h3>
      <p>${renderVerdict(trame)}</p>
      ${groupes}
      ${remarques}
      ${semaines.join("")}
      ${legende(trame)}
      ${renderCompteurs(trame)}
    </div>`;
}

function renderTrames(generation) {
  if (!generation.trames || !generation.trames.length) {
    $("#trames").innerHTML = `<p class="aide">Aucune trame n'a pu être proposée avec ces
      éléments. Vérifiez que les postes et l'effectif sont bien renseignés.</p>`;
    return;
  }
  const intro = `<p class="aide">${generation.trames.length} trame(s) proposée(s). Chaque trame
    est un cycle rejoué en boucle : à la fin du cycle, on repart au début.</p>`;
  $("#trames").innerHTML = intro + generation.trames.map(renderTrame).join("");
}

/* ==================================================================================
   Actions des boutons
   ================================================================================== */
async function calculer() {
  const description = constructionDescription();
  if (!description.postes.length) {
    afficherMessage("Ajoutez au moins un poste de travail.", true);
    return;
  }
  afficherMessage("Calcul en cours…", false);
  try {
    const analyse = await poster("/api/boite-trame/analyser", description);
    renderResultats(analyse, false);
    afficherMessage("", false);
  } catch (erreur) {
    const analyse = analyserLocalement(description);
    renderResultats(analyse, true);
    afficherMessage("Le serveur de calcul n'est pas encore branché : les heures et les ETP "
      + "sont calculés directement dans la page. Pour générer les trames, il faudra brancher "
      + "le serveur.", false);
  }
}

async function generer() {
  const description = constructionDescription();
  if (!description.postes.length) {
    afficherMessage("Ajoutez au moins un poste de travail.", true);
    return;
  }
  afficherMessage("Génération des trames en cours… (cela peut prendre quelques secondes)", false);
  $("#trames").innerHTML = '<p class="aide">Recherche des meilleures trames…</p>';
  try {
    const generation = await poster("/api/boite-trame/generer", description);
    if (generation.analyse) renderResultats(generation.analyse, false);
    renderTrames(generation);
    afficherMessage("", false);
  } catch (erreur) {
    renderTrames({ trames: [] });
    afficherMessage("La génération des trames n'est pas disponible pour le moment : la "
      + "fonction serveur n'est pas encore branchée. Le calcul des heures et des ETP, lui, "
      + "fonctionne (bouton Calculer).", true);
  }
}

/* ==================================================================================
   Démarrage : on pré-remplit l'exemple pour que la page ne soit jamais vide.
   ================================================================================== */
function demarrer() {
  preRemplir(EXEMPLE);
  $("#btn-ajouter-poste").addEventListener("click", () => ajouterPoste());
  $("#btn-calculer").addEventListener("click", calculer);
  $("#btn-generer").addEventListener("click", generer);
  $("#resultats").innerHTML = '<p class="aide">La description d\'exemple est déjà remplie. '
    + "Appuyez sur <strong>Calculer</strong> pour voir les besoins, puis sur "
    + "<strong>Générer les trames</strong> pour obtenir des propositions.</p>";
}

document.addEventListener("DOMContentLoaded", demarrer);
