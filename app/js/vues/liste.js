// « Où aller ? » : les spots classés du plus clair au plus trouble pour le jour choisi.

import { NOM_FACADE, distanceKm, echapper, facadePour, heure, jourCourt, metres, dateHeure } from "../format.js";
import { mesSpots } from "../messpots.js";

const FACADES = [["toutes", "Toutes"], ["manche", "Manche"], ["atlantique", "Atlantique"], ["mediterranee", "Méditerranée"], ["corse", "Corse"]];
const RAYONS = [30, 60, 100, 200];

export function lignesClassees(ctx) {
  const { etat, resume, previsionsPrivees } = ctx;
  const lignes = [];
  for (const p of resume.points) {
    const j = p.jours[Math.min(etat.jour, p.jours.length - 1)];
    lignes.push({ id: p.id, nom: p.nom, lat: p.lat, lon: p.lon, facade: p.facade, jour: j, prive: false, lien: `#/spot/${p.id}` });
  }
  for (const s of mesSpots()) {
    const pr = previsionsPrivees.get(s.id);
    const j = pr ? pr.jours[Math.min(etat.jour, pr.jours.length - 1)] : null;
    lignes.push({ id: s.id, nom: s.nom, lat: s.lat, lon: s.lon, facade: facadePour(s.lat, s.lon), jour: j, prive: true, lien: `#/prive/${s.id}` });
  }
  const o = etat.origine;
  return lignes
    .map((l) => ({
      ...l,
      distance: o ? distanceKm(o.lat, o.lon, l.lat, l.lon) : null,
      visi: l.jour ? (l.jour.meilleur_creneau ? l.jour.meilleur_creneau.visibilite_m : l.jour.visibilite_moyenne_m) : null,
    }))
    .filter((l) => etat.facade === "toutes" || l.facade === etat.facade)
    .filter((l) => l.distance === null || l.distance <= etat.rayon)
    .sort((a, b) =>
      ((a.jour ? 0 : 1) - (b.jour ? 0 : 1)) ||
      ((a.jour?.meilleur_creneau ? 0 : 1) - (b.jour?.meilleur_creneau ? 0 : 1)) ||
      ((b.visi ?? 0) - (a.visi ?? 0)) ||
      ((a.distance ?? 0) - (b.distance ?? 0)));
}

export function afficherListe(zone, ctx) {
  const { etat, resume } = ctx;
  const dates = resume.points[0] ? resume.points[0].jours.map((j) => j.date) : [];
  const lignes = lignesClassees(ctx);
  const o = etat.origine;
  zone.innerHTML = `
    <div class="entete-fiche"><h1 class="titre-vue">Où aller ?</h1>
      <p>Spots classés du plus clair au plus trouble. Prévisions mises à jour ${dateHeure(resume.genere_le)}.</p></div>
    <div class="segments" id="liste-jours" role="group" aria-label="Jour">${dates.map((d, i) => `<button type="button" data-jour="${i}" aria-pressed="${i === etat.jour}">${jourCourt(d)}</button>`).join("")}</div>
    <div class="segments" id="liste-facades" role="group" aria-label="Façade">${FACADES.map(([id, nom]) => `<button type="button" data-facade="${id}" aria-pressed="${id === etat.facade}">${nom}</button>`).join("")}</div>
    <div class="rangee">
      <button type="button" class="puce" id="autour" aria-pressed="${o?.type === "position"}">Autour de moi</button>
      ${o ? `<span class="note">Depuis : <strong>${echapper(o.nom)}</strong></span> <button type="button" class="lien" id="sans-origine">Toute la France</button>` : ""}
      <label class="etiquette" for="rayon">Rayon</label>
      <select id="rayon" ${o ? "" : "disabled"}>${RAYONS.map((r) => `<option value="${r}" ${r === etat.rayon ? "selected" : ""}>${r} km</option>`).join("")}</select>
    </div>
    <p class="erreur" id="erreur-position" hidden></p>
    <ol class="liste">${lignes.length ? lignes.map((l) => ligne(l, etat)).join("") : `<li class="vide">Aucun spot dans ce rayon. Élargis la distance ou change de façade.</li>`}</ol>
    <p class="note">Les points Kelvisi sont des zones de prévision, pas des recommandations de spot : vérifie la réglementation locale avant de chasser (réserves, cantonnements, parcs).</p>`;

  zone.querySelector("#liste-jours").addEventListener("click", (e) => {
    const b = e.target.closest("button");
    if (!b) return;
    etat.jour = Number(b.dataset.jour);
    ctx.surJour();
    afficherListe(zone, ctx);
  });
  zone.querySelector("#liste-facades").addEventListener("click", (e) => {
    const b = e.target.closest("button");
    if (!b) return;
    etat.facade = b.dataset.facade;
    ctx.memoriser();
    afficherListe(zone, ctx);
  });
  zone.querySelector("#rayon").addEventListener("change", (e) => {
    etat.rayon = Number(e.target.value);
    ctx.memoriser();
    afficherListe(zone, ctx);
  });
  const sans = zone.querySelector("#sans-origine");
  if (sans) sans.addEventListener("click", () => { etat.origine = null; afficherListe(zone, ctx); });
  zone.querySelector("#autour").addEventListener("click", () => {
    const err = zone.querySelector("#erreur-position");
    if (!navigator.geolocation) {
      err.textContent = "Ton navigateur ne donne pas accès à ta position. Cherche plutôt un lieu.";
      err.hidden = false;
      return;
    }
    navigator.geolocation.getCurrentPosition(
      (pos) => {
        etat.origine = { type: "position", nom: "ma position", lat: pos.coords.latitude, lon: pos.coords.longitude };
        afficherListe(zone, ctx);
      },
      () => {
        err.textContent = "Position indisponible (refusée ou introuvable). Cherche plutôt un lieu dans la barre de recherche.";
        err.hidden = false;
      },
      { enableHighAccuracy: false, timeout: 10000, maximumAge: 600000 },
    );
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
  return `<li><a class="ligne-spot" href="${l.lien}" ${etat.selection === l.id ? 'aria-current="true"' : ""}>
    <span class="eau ${l.jour ? `eau-${l.jour.classe}` : ""}"></span>
    <span><span class="nom">${echapper(l.nom)}</span>${l.prive ? '<span class="marque-prive">mon spot</span>' : ""}<br><span class="infos">${infos}</span></span>
    <span class="visi chiffres">${droite}</span></a></li>`;
}
