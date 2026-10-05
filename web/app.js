/* Synergie — interface. Tout le calcul vit côté serveur ; ici, on décrit et on affiche. */
const JOURS = ["Lun", "Mar", "Mer", "Jeu", "Ven", "Sam", "Dim"];
const CODES_REPOS = ["RH", "DS"];
const SOUHAITS = ["CAJ", "CA", "RTT", "CEP", "FEJ", "FC", "JR", "repos", "M"];

let projet = null;
let tramesCourantes = null;
let regles = null;

const $ = (s) => document.querySelector(s);
const api = async (url, options) => {
  const r = await fetch(url, options);
  if (!r.ok) throw new Error((await r.text()).slice(0, 300));
  return r.json();
};
const jsonPost = (url, corps) => api(url, {
  method: "POST", headers: { "Content-Type": "application/json" },
  body: JSON.stringify(corps || {})
});

/* --- Onglets ----------------------------------------------------------------- */
document.querySelectorAll(".onglets button").forEach((b) => {
  b.onclick = () => {
    document.querySelectorAll(".onglets button").forEach((x) => x.classList.remove("actif"));
    b.classList.add("actif");
    ["projet", "boite", "avis", "synthese"].forEach((o) => {
      $("#onglet-" + o).hidden = o !== b.dataset.onglet;
    });
    // L'onglet « Boîte à trames » renvoie vers le nouvel outil (une seule page) :
    // plus rien à calculer ici.
  };
});

/* --- Projets ----------------------------------------------------------------- */
async function chargerProjets(selection) {
  const projets = await api("/api/projets");
  const choix = $("#choix-projet");
  choix.innerHTML = "";
  projets.forEach((p) => {
    const o = document.createElement("option");
    o.value = p.id; o.textContent = p.nom || p.id;
    choix.appendChild(o);
  });
  if (!projets.length) {
    await jsonPost("/api/demo");
    return chargerProjets();
  }
  choix.value = selection && projets.some((p) => p.id === selection) ? selection : projets[0].id;
  await chargerProjet(choix.value);
}

async function chargerProjet(id) {
  projet = await api("/api/projets/" + id);
  afficherProjet();
}

function afficherProjet() {
  $("#p-nom").value = projet.nom || "";
  $("#p-collectivite").value = projet.collectivite || "";
  $("#p-date").value = projet.date_debut || "";
  $("#p-duree").value = projet.duree_semaines || 6;
  $("#p-description").value = projet.description || "";
  afficherMetiers();
  afficherAgents();
  afficherAvis();
  majSelecteurs();
  $("#liste-trames").innerHTML = "";
  $("#synthese").innerHTML = "";
}

function majSelecteurs() {
  const sel = $("#a-agent");
  sel.innerHTML = "";
  (projet.agents || []).forEach((a) => {
    const o = document.createElement("option"); o.value = a.nom; o.textContent = a.nom;
    sel.appendChild(o);
  });
  if (!$("#a-jour").value) $("#a-jour").value = projet.date_debut || "";
  const t = $("#t-genre");
  t.innerHTML = '<option value="">Projet entier</option>';
  (projet.metiers || []).forEach((m) => {
    const o = document.createElement("option"); o.value = m.code;
    o.textContent = m.libelle || m.code;
    t.appendChild(o);
  });
}

function afficherMetiers() {
  const zone = $("#liste-metiers");
  zone.innerHTML = "";
  (projet.metiers || []).forEach((m, i) => {
    const d = document.createElement("div");
    d.className = "ligne-form";
    const code = `<label>Métier<input data-k="code" data-i="${i}" value="${m.code || ""}"></label>`;
    const lib = `<label>Libellé<input data-k="libelle" data-i="${i}" value="${m.libelle || ""}"></label>`;
    const poste = `<label>Poste (code)<input data-k="poste" data-i="${i}" value="${(m.codes_travail || ["M"])[0]}"></label>`;
    const heures = `<label>Heures/jour<input data-k="heures" data-i="${i}" type="number" step="0.5" value="${((m.postes || [{}])[0] || {}).heures || 7.5}"></label>`;
    const supp = `<button class="discret" data-supp-metier="${i}">✕</button>`;
    d.innerHTML = code + lib + poste + heures + supp;
    zone.appendChild(d);
    // cibles
    const c = document.createElement("div");
    c.className = "grille-form";
    JOURS.forEach((j) => {
      const val = ((m.cibles || {})[j] || {})[(m.codes_travail || ["M"])[0]] || 0;
      c.innerHTML += `<label>${j}<input data-cible="${i}" data-jour="${j}" type="number" min="0" value="${val}"></label>`;
    });
    zone.appendChild(c);
    zone.appendChild(document.createElement("hr"));
  });
}

function afficherAgents() {
  const zone = $("#liste-agents");
  zone.innerHTML = "";
  const metiers = projet.metiers || [];
  (projet.agents || []).forEach((a, i) => {
    const d = document.createElement("div");
    d.className = "ligne-form";
    d.innerHTML = `
      <label>Nom<input data-ka="nom" data-i="${i}" value="${a.nom || ""}"></label>
      <label>Métier<select data-ka="metier" data-i="${i}">
        ${metiers.map((m) => `<option ${m.code === a.metier ? "selected" : ""}>${m.code}</option>`).join("")}
      </select></label>
      <label>Quotité<select data-ka="quotite" data-i="${i}">
        ${[1, 0.9, 0.8, 0.5].map((q) => `<option value="${q}" ${Number(a.quotite) === q ? "selected" : ""}>${q * 100} %</option>`).join("")}
      </select></label>
      <label>Nuit<select data-ka="nuit_fixe" data-i="${i}">
        <option value="false" ${!a.nuit_fixe ? "selected" : ""}>jour</option>
        <option value="true" ${a.nuit_fixe ? "selected" : ""}>nuit fixe</option>
      </select></label>
      <label>&nbsp;<select data-ka="sans_nuit" data-i="${i}">
        <option value="false" ${!a.sans_nuit ? "selected" : ""}>nuit possible</option>
        <option value="true" ${a.sans_nuit ? "selected" : ""}>sans nuit</option>
      </select></label>
      <button class="discret" data-supp-agent="${i}">✕</button>`;
    zone.appendChild(d);
  });
}

function afficherAvis() {
  const zone = $("#liste-avis");
  zone.innerHTML = "";
  const avis = projet.avis || [];
  if (!avis.length) { zone.innerHTML = "<em>Aucun avis déposé.</em>"; return; }
  const t = document.createElement("table");
  t.innerHTML = "<tr><th class='jour'>Agent</th><th>Jour</th><th>Souhait</th><th class='jour'>Motif</th><th></th></tr>";
  avis.forEach((a, i) => {
    const tr = document.createElement("tr");
    tr.innerHTML = `<td class="jour">${a.agent}</td><td>${a.jour}</td>
      <td class="c-${a.souhait}">${a.souhait}</td><td class="jour">${a.motif || ""}</td>
      <td><button class="discret" data-supp-avis="${i}">✕</button></td>`;
    t.appendChild(tr);
  });
  zone.appendChild(t);
}

/* --- Lecture du formulaire ---------------------------------------------------- */
function lireFormulaire() {
  const p = { ...projet };
  p.nom = $("#p-nom").value; p.collectivite = $("#p-collectivite").value;
  p.date_debut = $("#p-date").value; p.duree_semaines = Number($("#p-duree").value) || 6;
  p.description = $("#p-description").value;
  p.metiers = (projet.metiers || []).map((m, i) => {
    const q = (k) => document.querySelector(`[data-k="${k}"][data-i="${i}"]`);
    const code = q("code").value.toUpperCase();
    const poste = q("poste").value.toUpperCase() || "M";
    const heures = Number(q("heures").value) || 7.5;
    const cibles = {};
    JOURS.forEach((j) => {
      const v = Number(document.querySelector(`[data-cible="${i}"][data-jour="${j}"]`).value) || 0;
      cibles[j] = v ? { [poste]: v } : {};
    });
    return { code, libelle: q("libelle").value, codes_travail: [poste],
             postes: [{ code: poste, libelle: "Journée", heures }], cibles };
  });
  p.agents = (projet.agents || []).map((a, i) => {
    const q = (k) => document.querySelector(`[data-ka="${k}"][data-i="${i}"]`).value;
    return { nom: q("nom"), metier: q("metier"), quotite: Number(q("quotite")),
             nuit_fixe: q("nuit_fixe") === "true", sans_nuit: q("sans_nuit") === "true" };
  });
  p.avis = projet.avis || [];
  return p;
}

/* --- Évènements --------------------------------------------------------------- */
document.querySelector("#choix-projet").onchange = (e) => chargerProjet(e.target.value);
$("#btn-demo").onclick = async () => { const p = await jsonPost("/api/demo"); await chargerProjets(p.id); };

$("#btn-ajouter-metier").onclick = () => {
  projet = lireFormulaire();
  projet.metiers.push({ code: "METIER" + (projet.metiers.length + 1), libelle: "Nouveau métier",
    codes_travail: ["M"], postes: [{ code: "M", heures: 7.5 }], cibles: {} });
  afficherMetiers(); majSelecteurs();
};

$("#btn-ajouter-agent").onclick = () => {
  projet = lireFormulaire();
  projet.agents.push({ nom: "Nouvel agent", metier: (projet.metiers[0] || {}).code,
    quotite: 1, nuit_fixe: false, sans_nuit: false });
  afficherAgents(); majSelecteurs();
};

document.addEventListener("click", async (e) => {
  const t = e.target;
  if (t.dataset.suppMetier !== undefined) {
    projet = lireFormulaire(); projet.metiers.splice(+t.dataset.suppMetier, 1);
    afficherMetiers(); majSelecteurs();
  }
  if (t.dataset.suppAgent !== undefined) {
    projet = lireFormulaire(); projet.agents.splice(+t.dataset.suppAgent, 1);
    afficherAgents(); majSelecteurs();
  }
  if (t.dataset.suppAvis !== undefined) {
    await api(`/api/projets/${projet.id}/avis`, {
      method: "DELETE", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ index: +t.dataset.suppAvis }) });
    await chargerProjet(projet.id);
  }
});

$("#btn-enregistrer").onclick = async () => {
  const p = lireFormulaire();
  await api("/api/projets/" + projet.id, { method: "PUT",
    headers: { "Content-Type": "application/json" }, body: JSON.stringify(p) });
  $("#etat-projet").textContent = "Projet enregistré ✓";
  await chargerProjets(projet.id);
  setTimeout(() => ($("#etat-projet").textContent = ""), 2500);
};

$("#btn-cibles").onclick = async () => {
  await api("/api/projets/" + projet.id, { method: "PUT",
    headers: { "Content-Type": "application/json" }, body: JSON.stringify(lireFormulaire()) });
  projet = await jsonPost(`/api/projets/${projet.id}/cibles-recommandees`);
  afficherProjet();
  $("#etat-projet").textContent = "Couverture proposée d'après l'effectif ✓";
};

$("#btn-generer").onclick = async () => {
  $("#etat-boite").textContent = "Calcul en cours…";
  const metier = $("#t-genre").value;
  try {
    tramesCourantes = await jsonPost(`/api/projets/${projet.id}/trames`, { metier });
    afficherTrames(tramesCourantes);
    $("#etat-boite").textContent = `${tramesCourantes.trames.length} trame(s) générée(s) ✓`;
    chargerCatalogue();
  } catch (e) { $("#etat-boite").textContent = "Erreur : " + e.message; }
};

$("#btn-hermes").onclick = async () => {
  $("#etat-boite").textContent = "Appel du générateur Hermes…";
  const r = await jsonPost("/api/boite/importer-hermes");
  $("#etat-boite").textContent = r.ok ? `${r.importees} trame(s) Hermes importée(s) ✓`
    : "Hermes indisponible : " + (r.raison || "");
  chargerCatalogue();
};

$("#btn-ajouter-avis").onclick = async () => {
  await jsonPost(`/api/projets/${projet.id}/avis`, {
    agent: $("#a-agent").value, jour: $("#a-jour").value,
    souhait: $("#a-souhait").value, motif: $("#a-motif").value });
  $("#etat-avis").textContent = "Avis enregistré ✓";
  await chargerProjet(projet.id);
  setTimeout(() => ($("#etat-avis").textContent = ""), 2000);
};

$("#btn-synthese").onclick = async () => {
  $("#synthese").innerHTML = "<em>Calcul…</em>";
  const s = await api(`/api/projets/${projet.id}/synthese`);
  afficherSynthese(s);
};

/* --- Affichage des trames ----------------------------------------------------- */
function cellule(code) {
  return `<td class="c-${code}">${code}</td>`;
}

function afficherTrames(g) {
  const zone = $("#liste-trames");
  zone.innerHTML = "";
  (g.trames || []).forEach((t) => {
    const bloc = document.createElement("div");
    bloc.className = "trame-bloc";
    const h = t.heures || {};
    const ratio = h.ratio ? `${Math.round(h.ratio * 100)} %` : "—";
    let table = "<table><tr><th class='jour'>Semaine</th>" +
      JOURS.map((j) => `<th>${j}</th>`).join("") + "</tr>";
    (t.semaines || []).forEach((sem, i) => {
      table += `<tr><td class="jour">S${i + 1}</td>` + sem.map(cellule).join("") + "</tr>";
    });
    table += "</table>";

    let couv = "<table style='margin-top:10px'><tr><th class='jour'>Couverture</th>" +
      JOURS.map((j) => `<th>${j}</th>`).join("") + "</tr>";
    const codes = new Set();
    JOURS.forEach((j) => Object.keys(t.couverture?.[j] || {}).forEach((c) => codes.add(c)));
    [...codes].forEach((c) => {
      couv += `<tr><td class="jour">${c} (réalisé / cible)</td>` + JOURS.map((j) => {
        const v = (t.couverture?.[j] || {})[c];
        if (!v) return "<td>—</td>";
        const [r, cible] = v;
        const cls = r < cible ? "rouge" : (r > cible ? "jaune" : "vert");
        return `<td class="${cls}">${r} / ${cible}</td>`;
      }).join("") + "</tr>";
    });
    couv += "</table>";

    bloc.innerHTML = `
      <h3>${t.metier_libelle} · ${t.libelle} <span class="code">${t.code_trame}</span></h3>
      <div class="meta">${t.effectif} agent(s) · trame de ${t.periode} semaine(s) ·
        heures ${h.travaillees || "—"} / ${h.legales || "—"} (${ratio}) ·
        <span class="${h.ratio >= 1 ? "vert" : "rouge"}">${h.ratio >= 1 ? "conforme" : "sous l'obligation légale"}</span>
        · solveur : ${t.statut}</div>
      ${t.ecarts && t.ecarts.length ? `<p class="rouge">⚠ ${t.ecarts.join("<br>⚠ ")}</p>` : ""}
      ${table}${couv}
      <p class="aide" style="margin-top:10px">Ligne <em>i</em> = trame décalée de <em>i</em>
        semaine(s) : chaque agent suit sa ligne, la couverture est identique chaque semaine.</p>`;
    zone.appendChild(bloc);
  });
}

/* --- Catalogue ---------------------------------------------------------------- */
async function chargerCatalogue() {
  const r = await api("/api/boite");
  const zone = $("#catalogue");
  if (!r.total) { zone.innerHTML = "<em>Aucune trame dans la boîte pour l'instant.</em>"; return; }
  let t = "<table><tr><th class='jour'>Code</th><th>Métier</th><th>Quotité</th><th>Période</th><th>Effectif</th><th>Origine</th></tr>";
  r.trames.forEach((x) => {
    t += `<tr><td class="jour">${x.code_trame}</td><td>${x.metier_libelle || x.metier}</td>
      <td>${Math.round((x.quotite || 1) * 100)} %</td><td>${x.periode} sem.</td>
      <td>${x.effectif || "—"}</td><td>${x.origine || "—"}</td></tr>`;
  });
  zone.innerHTML = t + "</table>";
}

/* --- Synthèse ----------------------------------------------------------------- */
function afficherSynthese(s) {
  const a = s.avis || {};
  const zone = $("#synthese");
  let html = `<div class="carte"><h2>Indice de synergie</h2>
    <div class="indice">
      <div class="valeur">${a.indice_synergie === null ? "—" : a.indice_synergie + " %"}</div>
      <div class="barre"><span style="width:${a.indice_synergie || 0}%"></span></div>
    </div>
    <p class="aide">${a.honores} avis honoré(s) sur ${a.total} · ${a.non_honores} à rediscuter.
      La part d'avis refusés est le point de départ de la concertation.</p></div>`;

  if ((a.details_refuses || []).length) {
    html += `<div class="carte"><h2>Avis non honorés</h2><table>
      <tr><th class='jour'>Agent</th><th>Jour</th><th>Souhait</th><th class='jour'>Raison</th></tr>` +
      a.details_refuses.map((r) => `<tr><td class="jour">${r.agent}</td><td>${r.jour}</td>
        <td class="c-${r.souhait}">${r.souhait}</td><td class="jour rouge">${r.raison}</td></tr>`).join("") +
      "</table></div>";
  }

  if ((s.heures || []).length) {
    html += `<div class="carte"><h2>Heures et conformité</h2><table>
      <tr><th class='jour'>Trame</th><th>Travail</th><th>Légal</th><th>Ratio</th></tr>` +
      s.heures.map((h) => `<tr><td class="jour">${h.trame}</td><td>${h.travaillees} h</td>
        <td>${h.legales} h</td><td class="${h.ratio >= 1 ? "vert" : "rouge"}">
        ${Math.round((h.ratio || 0) * 100)} %</td></tr>`).join("") + "</table></div>";
  }

  // planning projeté (par agent)
  const noms = Object.keys(s.planning || {});
  if (noms.length) {
    html += `<div class="carte"><h2>Planning projeté</h2>`;
    noms.forEach((nom) => {
      const cases = s.planning[nom];
      const dates = Object.keys(cases).sort();
      let t = `<div class="trame-bloc"><h3>${nom} <span class="code">ligne ${
        (s.lignes[nom] || 0) + 1}</span></h3><table><tr><th class='jour'>Jour</th>`;
      dates.slice(0, 28).forEach((d) => (t += `<th>${d.slice(8)}/${d.slice(5, 7)}</th>`));
      t += "</tr><tr><td class='jour'>Code</td>";
      dates.slice(0, 28).forEach((d) => (t += cellule(cases[d])));
      t += "</tr></table></div>";
      html += t;
    });
    html += "</div>";
  }
  zone.innerHTML = html;
}

/* --- Démarrage ---------------------------------------------------------------- */
(async function demarrer() {
  regles = await api("/api/regles");
  $("#a-souhait").innerHTML = SOUHAITS.map((s) => `<option>${s}</option>`).join("");
  await chargerProjets();
})();
