// « Où aller ? » : les spots autour d'une ville, d'un lieu ou de ma position, du plus clair au plus trouble.

import { NOM_FACADE, distanceKm, echapper, facadePour, heure, jourCourt, metres, dateHeure } from "../format.js";
import { mesSpots } from "../messpots.js";
import { rechercherLieux } from "../recherche.js";
import { spotsCommunaute } from "../communaute.js";

const RAYONS = [15, 30, 60, 100, 200];

// Pour comparer des noms sans accents ni majuscules
const simplifier = (t) => String(t || "").normalize("NFD").replace(/[̀-ͯ]/g, "").toLowerCase();

function tousLesSpots(ctx) {
  const { etat, resume, previsionsPrivees } = ctx;
  const jourDe = (jours) => (jours ? jours[Math.min(etat.jour, jours.length - 1)] : null);
  const lignes = resume.points.map((p) => ({
    id: p.id, nom: p.nom, lat: p.lat, lon: p.lon, facade: p.facade, jour: jourDe(p.jours), type: "public", lien: `#/spot/${p.id}`,
  }));
  for (const s of mesSpots()) {
    lignes.push({ id: s.id, nom: s.nom, lat: s.lat, lon: s.lon, facade: facadePour(s.lat, s.lon), jour: jourDe(previsionsPrivees.get(s.id)?.jours),
      type: "prive", lien: `#/prive/${s.id}` });
  }
  for (const s of spotsCommunaute(mesSpots().map((x) => x.partage_id))) {
    lignes.push({ id: s.id, nom: s.nom, lat: s.lat, lon: s.lon, facade: facadePour(s.lat, s.lon), jour: jourDe(previsionsPrivees.get(s.id)?.jours),
      type: "communaute", lien: `#/partage/${encodeURIComponent(s.uuid)}` });
  }
  return lignes;
}

export function lignesClassees(ctx) {
  const { etat } = ctx;
  const o = etat.origine;
  return tousLesSpots(ctx)
    // Sans point de départ, les spots partagés (calculés à la demande) ne sont pas listés
    .filter((l) => o || l.type !== "communaute")
    .map((l) => ({
      ...l,
      distance: o ? distanceKm(o.lat, o.lon, l.lat, l.lon) : null,
      visi: l.jour ? (l.jour.meilleur_creneau ? l.jour.meilleur_creneau.visibilite_m : l.jour.visibilite_moyenne_m) : null,
    }))
    .filter((l) => l.distance === null || l.distance <= etat.rayon)
    .sort((a, b) =>
      ((a.jour ? 0 : 1) - (b.jour ? 0 : 1)) ||
      ((a.jour?.meilleur_creneau ? 0 : 1) - (b.jour?.meilleur_creneau ? 0 : 1)) ||
      ((b.visi ?? 0) - (a.visi ?? 0)) ||
      ((a.distance ?? 0) - (b.distance ?? 0)));
}

// Spots dont le nom contient le texte cherché
export function spotsParNom(ctx, texte) {
  const q = simplifier(texte.trim());
  if (q.length < 2) return [];
  return tousLesSpots(ctx)
    .filter((l) => simplifier(l.nom).includes(q))
    .sort((a, b) => simplifier(a.nom).indexOf(q) - simplifier(b.nom).indexOf(q))
    .slice(0, 5);
}

export function afficherListe(zone, ctx) {
  const { etat, resume } = ctx;
  const dates = resume.points[0] ? resume.points[0].jours.map((j) => j.date) : [];
  const lignes = lignesClassees(ctx);
  const o = etat.origine;
  zone.innerHTML = `
    <div class="entete-fiche"><h1 class="titre-vue">Où aller ?</h1>
      <p>Les spots autour d'une ville ou de toi, du plus clair au plus trouble. Prévisions mises à jour ${dateHeure(resume.genere_le)}.</p></div>
    <form class="recherche recherche-ou" id="ou-recherche" role="search" autocomplete="off">
      <input id="ou-texte" type="search" placeholder="Ville, plage ou spot" aria-label="Chercher une ville, une plage ou un spot" value="">
      <ul id="ou-resultats" class="resultats" hidden></ul>
    </form>
    <div class="rangee">
      <button type="button" class="puce" id="autour" aria-pressed="${o?.type === "position"}">Autour de moi</button>
      <label class="etiquette" for="rayon">Rayon</label>
      <select id="rayon" ${o ? "" : "disabled"}>${RAYONS.map((r) => `<option value="${r}" ${r === etat.rayon ? "selected" : ""}>${r} km</option>`).join("")}</select>
    </div>
    <p class="note" id="origine">${o ? `Autour de <strong>${echapper(o.nom)}</strong> · <button type="button" class="lien" id="sans-origine">Toute la France</button>` : "Toute la France : cherche une ville ou touche « Autour de moi » pour voir les spots proches."}</p>
    <div class="segments" id="liste-jours" role="group" aria-label="Jour">${dates.map((d, i) => `<button type="button" data-jour="${i}" aria-pressed="${i === etat.jour}">${jourCourt(d)}</button>`).join("")}</div>
    <p class="erreur" id="erreur-position" hidden></p>
    <ol class="liste">${lignes.length ? lignes.map((l) => ligne(l, etat)).join("") : `<li class="vide">Aucun spot dans ce rayon. Élargis la distance ou cherche une autre ville.</li>`}</ol>
    <p class="note">Les points Kelvisi sont des zones de prévision, pas des recommandations de spot : vérifie la réglementation locale avant de chasser (réserves, cantonnements, parcs).</p>`;

  zone.querySelector("#liste-jours").addEventListener("click", (e) => {
    const b = e.target.closest("button");
    if (!b) return;
    etat.jour = Number(b.dataset.jour);
    ctx.surJour();
    afficherListe(zone, ctx);
  });
  zone.querySelector("#rayon").addEventListener("change", (e) => {
    etat.rayon = Number(e.target.value);
    ctx.memoriser();
    choisirOrigine(zone, ctx, etat.origine);
  });
  const sans = zone.querySelector("#sans-origine");
  if (sans) sans.addEventListener("click", () => { etat.origine = null; afficherListe(zone, ctx); });
  zone.querySelector("#autour").addEventListener("click", () => {
    const err = zone.querySelector("#erreur-position");
    if (!navigator.geolocation) {
      err.textContent = "Ton navigateur ne donne pas accès à ta position. Cherche plutôt une ville.";
      err.hidden = false;
      return;
    }
    navigator.geolocation.getCurrentPosition(
      (pos) => choisirOrigine(zone, ctx, { type: "position", nom: "ma position", lat: pos.coords.latitude, lon: pos.coords.longitude }),
      () => {
        err.textContent = "Position indisponible (refusée ou introuvable). Cherche plutôt une ville.";
        err.hidden = false;
      },
      { enableHighAccuracy: false, timeout: 10000, maximumAge: 600000 },
    );
  });
  lierRecherche(zone, ctx);
}

function choisirOrigine(zone, ctx, origine) {
  ctx.etat.origine = origine;
  afficherListe(zone, ctx);
  // Les spots partagés proches sont calculés dans le navigateur, puis la liste se met à jour
  if (origine && ctx.calculerProches) ctx.calculerProches(origine, ctx.etat.rayon);
}

function lierRecherche(zone, ctx) {
  const form = zone.querySelector("#ou-recherche");
  const champ = zone.querySelector("#ou-texte");
  const liste = zone.querySelector("#ou-resultats");
  let minuterie = null, controleur = null, choix = [];
  const montrer = (html) => { liste.innerHTML = html; liste.hidden = false; };

  const rendreChoix = (lieuxEnCours) => {
    if (!choix.length && !lieuxEnCours) { montrer('<li class="message">Aucun spot ni lieu trouvé.</li>'); return; }
    montrer(choix.map((c, i) => `<li><button type="button" data-i="${i}"><span>${echapper(c.nom)}</span><span class="detail">${echapper(c.detail)}</span></button></li>`).join("")
      + (lieuxEnCours ? '<li class="message">Recherche des villes…</li>' : ""));
  };

  async function chercher() {
    const q = champ.value.trim();
    if (q.length < 2) { liste.hidden = true; return; }
    const spots = spotsParNom(ctx, q).map((l) => ({
      nom: l.nom, lien: l.lien, lat: l.lat, lon: l.lon,
      detail: `${{ public: "Point Kelvisi", prive: "Mon spot", communaute: "Spot partagé" }[l.type]}${NOM_FACADE[l.facade] ? ` · ${NOM_FACADE[l.facade]}` : ""}`,
    }));
    choix = spots;
    if (q.length < 3) { rendreChoix(false); return; }
    rendreChoix(true);
    if (controleur) controleur.abort();
    controleur = new AbortController();
    try {
      const lieux = await rechercherLieux(q, controleur.signal);
      choix = [...spots, ...lieux.slice(0, 6).map((r) => ({ ...r, origine: true }))];
      rendreChoix(false);
    } catch (e) {
      if (e.name === "AbortError") return;
      rendreChoix(false);
      if (!spots.length) montrer('<li class="message">Recherche des villes indisponible pour le moment. Vérifie ta connexion.</li>');
    }
  }

  const choisir = (c) => {
    liste.hidden = true;
    if (c.origine) choisirOrigine(zone, ctx, { type: "lieu", nom: c.nom, lat: c.lat, lon: c.lon });
    else ctx.allerA(c.lien);
  };

  champ.addEventListener("input", () => {
    clearTimeout(minuterie);
    minuterie = setTimeout(chercher, 300);
  });
  champ.addEventListener("keydown", (e) => { if (e.key === "Escape") liste.hidden = true; });
  form.addEventListener("submit", (e) => {
    e.preventDefault();
    if (choix.length && !liste.hidden) choisir(choix[0]);
    else chercher();
  });
  liste.addEventListener("click", (e) => {
    const b = e.target.closest("button[data-i]");
    if (b) choisir(choix[Number(b.dataset.i)]);
  });
}

function ligne(l, etat) {
  const infos = [NOM_FACADE[l.facade], l.distance !== null ? `${Math.round(l.distance)} km` : null].filter(Boolean).join(" · ");
  let droite;
  if (!l.jour) droite = `<strong>…</strong><span>calcul</span>`;
  else {
    const cr = l.jour.meilleur_creneau;
    droite = `<strong>${metres(l.visi)} m</strong><span>${cr ? `de ${heure(cr.debut)} à ${heure(cr.fin)}` : '<span class="deconseille">déconseillé</span>'}</span>`;
  }
  const marque = { prive: '<span class="marque-prive">mon spot</span>', communaute: '<span class="marque-prive">partagé</span>' }[l.type] || "";
  return `<li><a class="ligne-spot" href="${l.lien}" ${etat.selection === l.id ? 'aria-current="true"' : ""}>
    <span class="eau ${l.jour ? `eau-${l.jour.classe}` : ""}"></span>
    <span><span class="nom">${echapper(l.nom)}</span>${marque}<br><span class="infos">${infos}</span></span>
    <span class="visi chiffres">${droite}</span></a></li>`;
}
