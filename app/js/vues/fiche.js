// Fiche d'un spot : point public, spot privé ou lieu libre touché sur la carte.

import { detailPublic, pointPublic, previsionLieu } from "../donnees.js";
import { monSpot, enregistrerSpot, supprimerSpot } from "../messpots.js";
import { enregistrerRetour, partageActif, rapportsPourMoteur, retoursDuSpot } from "../retours.js";
import { estimerLieu } from "../profondeur.js";
import { profondeursAuPoint } from "../bathymetrie.js";
import { comptesActifs } from "../compte.js";
import { estFavori, basculerFavori } from "../favoris.js";
import { CONFIG } from "../config.js";
import {
  NOM_CLASSE, NOM_FACADE, NOM_FOND, SECTEURS_COURTS, de, echapper, facadePour, fleche, heure, jourCourt, jourLong,
  metres, regionPour, secteur, dateHeure, vitesseVent, lune, decrireMesure,
} from "../format.js";

const lieuxEstimes = new Map();

// --- Morceaux de fiche --------------------------------------------------------------------

const mm = (x) => String(Math.round(x * 10) / 10).replace(".", ",");
const debit = (x) => (x < 10 ? String(Math.round(x * 10) / 10).replace(".", ",") : String(Math.round(x)));

function heuresDuJour(prevision, date) {
  return prevision.heures.filter((h) => h.heure.slice(0, 10) === date);
}

function plage(prevision, jour) {
  const hs = heuresDuJour(prevision, jour.date);
  const cr = jour.meilleur_creneau;
  let choix = cr ? hs.filter((h) => h.heure >= cr.debut && h.heure < cr.fin) : hs.filter((h) => h.de_jour);
  if (!choix.length) choix = hs;
  if (!choix.length) return null;
  const pire = choix.reduce((a, h) => (h.confiance < a.confiance ? h : a), choix[0]);
  return {
    bas: Math.min(...choix.map((h) => h.fourchette_m[0])),
    haut: Math.max(...choix.map((h) => h.fourchette_m[1])),
    confiance: pire.confiance,
    texte: pire.confiance_texte,
  };
}

function couleur(classe) {
  return `var(--v-${classe})`;
}

function jauge(jour, pl, seuils) {
  if (!pl) return "";
  const max = seuils[2] >= 15 ? 30 : 15;
  const pas = max / 3;
  const v = jour.meilleur_creneau ? jour.meilleur_creneau.visibilite_m : jour.visibilite_moyenne_m;
  const pc = (x) => Math.max(0, Math.min(100, (x / max) * 100));
  const c = couleur(jour.classe);
  const grad = [];
  for (let k = 0; k <= max; k += pas) grad.push(`<span style="left:${pc(k)}%">${k} m</span>`);
  return `<div class="visee" role="img" aria-label="Portée de vue estimée entre ${metres(pl.bas)} et ${metres(pl.haut)} mètres">
    <div class="etiquette">Jusqu'où tu vois</div>
    <div class="piste">
      <span class="plein" style="left:0;width:${pc(pl.bas)}%;background:${c}"></span>
      <span class="flou" style="left:${pc(pl.bas)}%;width:${pc(pl.haut) - pc(pl.bas)}%;background:linear-gradient(90deg,${c},transparent)"></span>
      <span class="repere-visee" style="left:calc(${pc(v)}% - 1.5px)"></span>
    </div>
    <div class="graduations chiffres">${grad.join("")}</div>
  </div>`;
}

function graphique(prevision, jour) {
  const hs = heuresDuJour(prevision, jour.date);
  if (!hs.length) return "";
  const W = 640, H = 230, g = 34, d = 10, haut = 18, bas = 30;
  const maxV = Math.max(...hs.map((h) => h.fourchette_m[1]));
  const pasY = maxV > 20 ? 10 : 5;
  const ymax = Math.max(pasY, Math.ceil(maxV / pasY) * pasY);
  const largeur = (W - g - d) / 24;
  const x = (i) => g + i * largeur;
  const y = (v) => haut + (H - haut - bas) * (1 - v / ymax);
  const cr = jour.meilleur_creneau;
  const parts = [];
  for (let t = 0; t <= ymax; t += pasY) {
    parts.push(`<line x1="${g}" x2="${W - d}" y1="${y(t)}" y2="${y(t)}" style="stroke:var(--ligne)" stroke-width="1"/>`);
    parts.push(`<text x="${g - 6}" y="${y(t) + 4}" text-anchor="end" font-size="11" style="fill:var(--discret)">${t}</text>`);
  }
  parts.push(`<text x="${g}" y="11" font-size="11" style="fill:var(--discret)">mètres</text>`);
  for (const h of hs) {
    const i = parseInt(h.heure.slice(11, 13), 10);
    const cx = x(i) + largeur / 2;
    if (!h.de_jour) parts.push(`<rect x="${x(i)}" y="${haut}" width="${largeur}" height="${H - haut - bas}" style="fill:var(--nuit)"/>`);
    parts.push(`<line x1="${cx}" x2="${cx}" y1="${y(h.fourchette_m[1])}" y2="${y(h.fourchette_m[0])}" style="stroke:var(--discret)" stroke-width="1" opacity="0.6"/>`);
    parts.push(`<rect x="${x(i) + 2}" y="${y(h.visibilite_m)}" width="${largeur - 4}" height="${Math.max(1, y(0) - y(h.visibilite_m))}" rx="2" style="fill:${couleur(h.classe)}" opacity="${h.de_jour ? 1 : 0.45}"><title>${heure(h.heure)} : ${metres(h.visibilite_m)} m (${metres(h.fourchette_m[0])} à ${metres(h.fourchette_m[1])} m)</title></rect>`);
    if (cr && h.heure >= cr.debut && h.heure < cr.fin) parts.push(`<rect x="${x(i)}" y="${y(0) + 3}" width="${largeur}" height="5" style="fill:var(--bouee)"/>`);
    if (i % 3 === 0) parts.push(`<text x="${x(i)}" y="${H - 8}" font-size="11" style="fill:var(--discret)">${i} h</text>`);
  }
  return `<div class="graphique"><svg viewBox="0 0 ${W} ${H}" role="img" aria-label="Visibilité heure par heure, ${jourLong(jour.date)}">${parts.join("")}</svg></div>
    <div class="legende"><span><i style="background:var(--v-mauvaise)"></i>Mauvaise</span><span><i style="background:var(--v-moyenne)"></i>Moyenne</span>
    <span><i style="background:var(--v-bonne)"></i>Bonne</span><span><i style="background:var(--v-excellente)"></i>Excellente</span>
    <span><i style="background:var(--nuit)"></i>Nuit, chasse interdite</span><span><i style="background:var(--bouee)"></i>Meilleur créneau</span></div>`;
}

function conditions(prevision, jour, meta) {
  const hs = heuresDuJour(prevision, jour.date);
  if (!hs.length) return "";
  const cr = jour.meilleur_creneau;
  const h = (cr && hs.find((x) => x.heure === cr.debut)) || hs[Math.min(12, hs.length - 1)];
  const moment = `à ${heure(h.heure)}`;
  const houle = h.houle, vent = h.vent;
  const cartes = [];
  cartes.push(`<div class="condition"><span class="etiquette">Houle au spot</span><span class="valeur chiffres">${houle.hauteur_au_spot_m !== null ? `${metres(houle.hauteur_au_spot_m)} m` : "?"}</span>
    <span class="sous">${houle.direction_deg !== null ? fleche(houle.direction_deg) : ""}au large ${houle.hauteur_m !== null ? String(houle.hauteur_m).replace(".", ",") : "?"} m ${houle.direction_deg !== null ? de(secteur(houle.direction_deg)) : ""}${houle.periode_s !== null ? `, ${houle.periode_s} s` : ""} · ${moment}</span></div>`);
  cartes.push(`<div class="condition"><span class="etiquette">Vent</span><span class="valeur chiffres">${vitesseVent(vent.vitesse_kn)}</span>
    <span class="sous">${vent.direction_deg !== null ? fleche(vent.direction_deg) + secteur(vent.direction_deg) + ", " : ""}rafales ${vitesseVent(vent.rafales_kn)}${vent.de_terre === null ? "" : vent.de_terre ? " · vent de terre" : " · vent de mer"}</span></div>`);
  if (jour.marees && jour.marees.length) {
    cartes.push(`<div class="condition"><span class="etiquette">Marée</span><ul class="marees chiffres">${jour.marees
      .map((e) => `<li><strong>${e.type === "PM" ? "Pleine mer" : "Basse mer"}</strong> ${heure(e.heure)}</li>`).join("")}</ul>
      <span class="sous">Horaires indicatifs (modèle à maille de 8 km)</span></div>`);
  }
  if (jour.lever_soleil && jour.coucher_soleil) {
    cartes.push(`<div class="condition"><span class="etiquette">Soleil</span><span class="valeur chiffres">${heure(jour.lever_soleil)} à ${heure(jour.coucher_soleil)}</span><span class="sous">Créneaux proposés dans cette plage</span></div>`);
  }
  if (h.temperature_eau_c !== null && h.temperature_eau_c !== undefined) {
    cartes.push(`<div class="condition"><span class="etiquette">Eau</span><span class="valeur chiffres">${String(h.temperature_eau_c).replace(".", ",")} °C</span><span class="sous">en surface</span></div>`);
  }
  if (h.courant_ms !== null && h.courant_ms !== undefined) {
    const kn = h.courant_ms / 0.514444;
    cartes.push(`<div class="condition"><span class="etiquette">Courant</span><span class="valeur chiffres">${kn.toFixed(1).replace(".", ",")} nœud${kn >= 2 ? "s" : ""}</span><span class="sous">${moment}, modèle à maille de 8 km</span></div>`);
  }
  const pluieJour = hs.reduce((a, x) => a + (x.pluie_mm || 0), 0);
  if (prevision.pluie_48h_mm !== undefined) {
    cartes.push(`<div class="condition"><span class="etiquette">Pluie</span><span class="valeur chiffres">${mm(prevision.pluie_48h_mm)} mm</span>
      <span class="sous">tombés ces dernières 48 h · ${mm(pluieJour)} mm prévus ${jour.date === prevision.heures[0]?.heure.slice(0, 10) ? "d'ici ce soir" : "ce jour-là"}</span></div>`);
  }
  for (const r of prevision.rivieres || []) {
    const etat = r.rapport === null ? "" : r.rapport < 0.7 ? "basses eaux" : r.rapport < 1.5 ? "débit habituel" : r.rapport < 3 ? "débit élevé" : "en crue";
    cartes.push(`<div class="condition"><span class="etiquette">${echapper(r.nom)}</span><span class="valeur chiffres">${debit(r.debit_m3s)} m³/s</span>
      <span class="sous">${etat}${etat ? " · " : ""}habituellement ${debit(r.debit_habituel_m3s)} m³/s</span></div>`);
  }
  const l = lune(jour.date);
  cartes.push(`<div class="condition"><span class="etiquette">Lune</span><span class="valeur">${l.phase}</span>
    <span class="sous">${meta?.region === "mediterranee" ? "marée faible en Méditerranée" : `période de ${l.maree.startsWith("coef") ? "transition, " + l.maree : l.maree}`}</span></div>`);
  return `<div class="conditions">${cartes.join("")}</div>`;
}

// Heure et prévision correspondant au moment choisi dans le formulaire de retour
function momentDuRetour(prevision, quand) {
  const toutes = [...(prevision.historique || []), ...prevision.heures];
  const maintenant = Date.now() / 1000;
  // Dates du jour et de la veille à l'heure de Paris, d'après l'horloge (pas d'après les prévisions)
  const jourParis = (ms) => new Date(ms).toLocaleDateString("fr-CA", { timeZone: CONFIG.fuseau || "Europe/Paris" });
  const aujourdHui = jourParis(Date.now());
  const veille = jourParis(Date.now() - 86400000);
  let cible = null;
  if (quand === "matin") cible = toutes.find((h) => h.heure.startsWith(`${aujourdHui}T09:`));
  if (quand === "hier") cible = toutes.find((h) => veille && h.heure.startsWith(`${veille}T15:`));
  if (cible) {
    const t = Date.parse(cible.heure) / 1000;
    if (t <= maintenant) return { temps: t, prevision: cible.visibilite_m };
  }
  if (quand === "hier") return { temps: maintenant - 86400, prevision: null };
  if (quand === "matin") return { temps: maintenant - 3 * 3600, prevision: null };
  const proche = toutes.reduce((a, h) => (Math.abs(Date.parse(h.heure) / 1000 - maintenant) < Math.abs(Date.parse(a.heure) / 1000 - maintenant) ? h : a), toutes[0]);
  return { temps: maintenant, prevision: proche ? proche.visibilite_m : null };
}

function formulaireRetour(type, id) {
  if (type === "point") {
    return `<div class="bloc"><h2 class="titre-bloc">Tu y étais ?</h2><p class="note">Enregistre ce lieu dans tes spots pour noter la visibilité de tes sorties : tes retours corrigeront sa prévision.</p></div>`;
  }
  const mes = retoursDuSpot(id).slice(-3).reverse();
  const explication = type === "prive"
    ? "Tes retours restent sur ton appareil et corrigent la prévision de ce spot."
    : partageActif()
      ? "Ton retour est partagé de façon anonyme et sert à corriger la prévision de ce point pour tout le monde."
      : "Le partage des retours n'est pas encore activé : ton retour reste sur ton appareil.";
  return `<div class="bloc"><h2 class="titre-bloc">Tu y étais ?</h2>
    <p class="note">${explication}</p>
    <form class="formulaire" id="form-retour">
      <div class="rangee"><label class="etiquette" for="retour-visi">Visibilité constatée</label>
        <input id="retour-visi" type="range" min="0" max="30" step="0.5" value="5"><output id="retour-sortie" for="retour-visi" class="chiffres">5 m</output></div>
      <div class="rangee"><label class="etiquette" for="retour-quand">Quand</label>
        <select id="retour-quand"><option value="maintenant">À l'instant</option><option value="matin">Ce matin</option><option value="hier">Hier après-midi</option></select></div>
      <button class="bouton" type="submit">Envoyer mon retour</button>
      <p class="confirmation" id="retour-ok" hidden></p>
    </form>
    ${mes.length ? `<div><span class="etiquette">Mes derniers retours ici</span><ul class="marees chiffres">${mes.map((r) => `<li>${metres(r.visibilite_m)} m · ${dateHeure(r.observe_le)}</li>`).join("")}</ul></div>` : ""}
  </div>`;
}

function reglages(spot, type) {
  const dirs = [0, 45, 90, 135, 180, 225, 270, 315];
  const proche = dirs.reduce((a, d) => (Math.abs(((spot.orientation_deg - d + 540) % 360) - 180) < Math.abs(((spot.orientation_deg - a + 540) % 360) - 180) ? d : a), 0);
  const ouvertures = [[45, "Étroite"], [90, "Moyenne"], [135, "Large"], [180, "Île, cap"]];
  const ouv = ouvertures.reduce((a, o) => (Math.abs(o[0] - spot.ouverture_deg) < Math.abs(a[0] - spot.ouverture_deg) ? o : a), ouvertures[1])[0];
  const fonds = ["sable", "roche", "mixte", "herbier", "vase"];
  return `<div class="bloc"><h2 class="titre-bloc">${type === "point" ? "Réglages du lieu (estimés)" : "Réglages du spot"}</h2>
    <p class="note">${type === "point" ? `Estimés d'après ${spot.source_estimation === "shom" ? "les cartes des fonds du Shom" : "la carte des profondeurs EMODnet"}. Corrige-les si tu connais l'endroit : la prévision se recalcule aussitôt.` : "Modifie-les si l'endroit ne correspond pas : la prévision se recalcule aussitôt."}</p>
    <div class="formulaire" id="reglages">
      <div><span class="etiquette">Direction du large</span><div class="boussole" id="regl-orientation">${dirs.map((d, i) => `<button type="button" data-v="${d}" aria-pressed="${d === proche}">${SECTEURS_COURTS[i]}</button>`).join("")}</div></div>
      <div><span class="etiquette">Ouverture sur la mer</span><div class="segments" id="regl-ouverture">${ouvertures.map(([v, n]) => `<button type="button" data-v="${v}" aria-pressed="${v === ouv}">${n}</button>`).join("")}</div></div>
      <div class="rangee"><label class="etiquette" for="regl-profondeur">Profondeur où tu chasses</label>
        <input id="regl-profondeur" type="number" min="1" max="40" step="1" value="${Math.round(spot.profondeur_m)}" inputmode="numeric"> m</div>
      <div><span class="etiquette">Fond</span><div class="segments" id="regl-fond">${fonds.map((f) => `<button type="button" data-v="${f}" aria-pressed="${f === spot.fond}">${NOM_FOND[f]}</button>`).join("")}</div></div>
      ${type === "point" ? `<div class="rangee"><label class="etiquette" for="regl-nom">Nom</label><input id="regl-nom" type="text" maxlength="60" placeholder="Mon spot" value=""></div>
        <button class="bouton" type="button" id="regl-enregistrer">Enregistrer dans mes spots</button>
        <p class="note">${comptesActifs() ? "Tes spots privés ne sont visibles que par toi." : "Tes spots restent sur ton appareil. Kelvisi ne les reçoit jamais."}</p>` : ""}
    </div>
  </div>`;
}

function actionsPrive(spot) {
  return `<div class="bloc"><h2 class="titre-bloc">Ce spot</h2>
    <div class="rangee"><label class="etiquette" for="prive-nom">Nom</label><input id="prive-nom" type="text" maxlength="60" value="${echapper(spot.nom)}"></div>
    <div class="rangee"><button class="bouton secondaire" type="button" id="prive-renommer">Renommer</button>
      <button class="bouton danger" type="button" id="prive-supprimer">Supprimer ce spot</button></div>
    <div class="rangee" id="prive-confirmer" hidden><span>Supprimer « ${echapper(spot.nom)} » et ses retours ?</span>
      <button class="bouton danger" type="button" id="prive-oui">Oui, supprimer</button><button class="bouton secondaire" type="button" id="prive-non">Annuler</button></div>
  </div>`;
}

// --- Vue ------------------------------------------------------------------------------------

export async function afficherFiche(zone, cible, ctx) {
  const jeton = (ctx.jeton = {});
  zone.innerHTML = `<button type="button" class="retour" data-retour>← Retour</button><p class="chargement">Calcul de la prévision…</p>`;
  lierRetour(zone, ctx);
  let meta, prevision, spot = null, info = "";
  try {
    if (cible.type === "public") {
      meta = pointPublic(cible.id);
      if (!meta) throw new Error("Ce point n'existe plus.");
      prevision = await detailPublic(cible.id);
    } else if (cible.type === "prive") {
      spot = monSpot(cible.id);
      if (!spot) throw new Error("Ce spot n'est plus enregistré sur cet appareil.");
      const r = await previsionLieu(spot, { rapports: rapportsPourMoteur(spot.id) });
      prevision = r.prevision;
      if (r.horsLigne) info = `Hors ligne : prévision calculée avec la météo reçue ${dateHeure(new Date(r.recu_le * 1000).toISOString())}.`;
      meta = spotVersMeta(spot);
    } else {
      spot = await estimationLieu(cible.lat, cible.lon);
      if (jeton !== ctx.jeton) return;
      const r = await previsionLieu(spot);
      prevision = r.prevision;
      if (r.horsLigne) info = `Hors ligne : prévision calculée avec la météo reçue ${dateHeure(new Date(r.recu_le * 1000).toISOString())}.`;
      meta = spotVersMeta(spot);
    }
  } catch (e) {
    if (jeton !== ctx.jeton) return;
    zone.innerHTML = `<button type="button" class="retour" data-retour>← Retour</button><p class="erreur">${echapper(e.message || "Prévision indisponible.")}</p>
      <p class="note">Vérifie ta connexion puis réessaie.</p><button type="button" class="bouton secondaire" id="reessayer">Réessayer</button>`;
    lierRetour(zone, ctx);
    zone.querySelector("#reessayer").addEventListener("click", () => afficherFiche(zone, cible, ctx));
    return;
  }
  if (jeton !== ctx.jeton) return;
  rendre(zone, cible, ctx, { meta, prevision, spot, info });
}

function spotVersMeta(spot) {
  return {
    ...spot,
    facade: facadePour(spot.lat, spot.lon),
    seuils: { manche: [2, 4, 7], atlantique: [2, 4, 7], mediterranee: [4, 8, 15] }[spot.region],
  };
}

async function estimationLieu(lat, lon) {
  const cle = `${lat.toFixed(4)},${lon.toFixed(4)}`;
  if (lieuxEstimes.has(cle)) return lieuxEstimes.get(cle);
  let est = null;
  try {
    est = await estimerLieu(lat, lon);
  } catch (e) {
    est = null;
  }
  const spot = {
    id: `point-${cle}`,
    nom: "Lieu choisi sur la carte",
    lat, lon,
    region: regionPour(lat, lon),
    orientation_deg: est?.orientation_deg ?? 270,
    ouverture_deg: est?.ouverture_deg ?? 90,
    profondeur_m: Math.min(30, Math.max(2, Math.round(est?.profondeur_m ?? 8))),
    fond: "mixte",
    estime: Boolean(est && est.orientation_deg !== null),
    source_estimation: est?.source || null,
  };
  lieuxEstimes.set(cle, spot);
  return spot;
}

function lierRetour(zone, ctx) {
  const b = zone.querySelector("[data-retour]");
  if (b) b.addEventListener("click", () => ctx.revenir());
}

// Lien vers la fiche, utilisable par quelqu'un d'autre (jamais pour un spot privé)
export function lienPartage(cible, meta) {
  const base = location.href.split("#")[0];
  return cible.type === "public" ? `${base}#/spot/${encodeURIComponent(meta.id)}` : `${base}#/point/${meta.lat.toFixed(4)}/${meta.lon.toFixed(4)}`;
}

async function partager(zone, cible, meta, jour, v) {
  const url = lienPartage(cible, meta);
  const texte = `${meta.nom} : ${metres(v)} m de visibilité prévue ${jourLong(jour.date)}, selon Kelvisi.`;
  const message = zone.querySelector("#message-partage");
  try {
    if (navigator.share) {
      await navigator.share({ title: "Kelvisi", text: texte, url });
      return;
    }
    await navigator.clipboard.writeText(`${texte} ${url}`);
    message.textContent = "Lien copié : colle-le dans un message.";
  } catch (e) {
    if (e && e.name === "AbortError") return;
    message.textContent = `Copie impossible, voici le lien : ${url}`;
  }
  message.hidden = false;
}

function lienProposition(meta, spot) {
  const s = spot || meta;
  const corps = [
    `Je propose ce lieu comme point Kelvisi.`, ``,
    `Position : ${s.lat.toFixed(5)}, ${s.lon.toFixed(5)}`,
    `Orientation vers le large : ${Math.round(s.orientation_deg)}°, ouverture ${Math.round(s.ouverture_deg)}°`,
    `Profondeur : ${Math.round(s.profondeur_m)} m, fond : ${s.fond}`, ``,
    `Nom usuel du lieu :`, `Réserve ou zone interdite à proximité :`,
  ].join("\n");
  return `mailto:${encodeURIComponent(CONFIG.contact)}?subject=${encodeURIComponent("Proposition de point Kelvisi")}&body=${encodeURIComponent(corps)}`;
}

function rendre(zone, cible, ctx, { meta, prevision, spot, info }) {
  const nbJours = prevision.jours.length;
  const iJour = Math.min(ctx.etat.jour, nbJours - 1);
  const jour = prevision.jours[iJour];
  const pl = plage(prevision, jour);
  const v = jour.meilleur_creneau ? jour.meilleur_creneau.visibilite_m : jour.visibilite_moyenne_m;
  const cr = jour.meilleur_creneau;
  const tendance = { "amélioration": "L'eau s'éclaircit le lendemain.", "dégradation": "L'eau se trouble le lendemain.", "stable": "Peu de changement le lendemain." }[jour.tendance] || "";
  const sousTitre = [
    NOM_FACADE[meta.facade] || "",
    NOM_FOND[meta.fond] || "",
    meta.profondeur_m ? `${metres(meta.profondeur_m)} m de fond` : "",
    cible.type === "prive" ? "Mon spot" : cible.type === "point" ? "Lieu libre" : "Point Kelvisi",
  ].filter(Boolean).join(" · ");
  const retours = cible.type === "public" && meta.retours?.nombre_7_jours
    ? `<p class="note">${meta.retours.nombre_7_jours} retour${meta.retours.nombre_7_jours > 1 ? "s" : ""} terrain ces 7 derniers jours${meta.retours.dernier ? `, dernier : ${metres(meta.retours.dernier.visibilite_m)} m (${dateHeure(meta.retours.dernier.date)})` : ""}.</p>` : "";
  const corrige = prevision.calibrage && prevision.calibrage.rapports > 0
    ? `<p class="note">Prévision corrigée d'après ${prevision.calibrage.rapports >= 2 ? "les retours terrain" : "un retour terrain"} (facteur ${String(prevision.calibrage.facteur).replace(".", ",")}).</p>` : "";
  const reference = prevision.reference
    ? `<p class="note">Eau habituelle et réaction à la houle reprises du point Kelvisi ${echapper(prevision.reference.nom)}, à ${prevision.reference.distance_km} km (calées sur le satellite).</p>` : "";
  const sat = prevision.satellite?.utilise
    ? `<p class="note">Recalée sur l'image satellite ${prevision.satellite.age_jours < 1 ? "du jour" : `d'il y a ${Math.round(prevision.satellite.age_jours)} jour${Math.round(prevision.satellite.age_jours) > 1 ? "s" : ""}`} (Copernicus Marine).</p>` : "";

  zone.innerHTML = `
    <button type="button" class="retour" data-retour>← Retour</button>
    ${info ? `<p class="encart info">${echapper(info)}</p>` : ""}
    <div class="bloc">
      <div class="entete-fiche"><h1 class="titre-vue">${echapper(meta.nom)}</h1><p>${sousTitre}</p></div>
      <div class="segments" id="jours-fiche" role="group" aria-label="Jour">${prevision.jours.map((j, i) => `<button type="button" data-jour="${i}" aria-pressed="${i === iJour}">${jourCourt(j.date)}</button>`).join("")}</div>
      <div class="lecture"><div class="nombre chiffres">${metres(v)}<small>m</small></div>
        <div class="details"><span class="classe" style="background:${couleur(jour.classe)}">${NOM_CLASSE[jour.classe]}</span>
        ${pl ? `<span class="fourchette chiffres">entre ${metres(pl.bas)} et ${metres(pl.haut)} m · confiance ${pl.texte} (${pl.confiance} %)</span>` : ""}</div></div>
      ${jauge(jour, pl, meta.seuils)}
      <p class="explication">${echapper(jour.explication)}</p>
      ${jour.alerte ? `<div class="encart alerte">${echapper(jour.alerte)}</div>` : ""}
      ${cr ? `<div class="encart creneau"><strong class="etiquette">Meilleur créneau</strong><span class="grand chiffres">de ${heure(cr.debut)} à ${heure(cr.fin)}</span><span>${metres(cr.visibilite_m)} m en moyenne sur le créneau</span></div>`
        : `<div class="encart alerte">Aucun créneau conseillé ce jour-là.</div>`}
      ${jour.conseil_maree || tendance ? `<p class="note">${[jour.conseil_maree, tendance].filter(Boolean).join(" ")}</p>` : ""}
      ${retours}${corrige}${sat}${reference}
      ${meta.notes ? `<p class="encart info">${echapper(meta.notes)}</p>` : ""}
      ${meta.rivieres?.length ? `<p class="note">Débit suivi en temps réel : ${meta.rivieres.map(echapper).join(", ")} (Hub'Eau).</p>` : ""}
      ${cible.type === "point" && spot && !spot.estime ? `<p class="encart info">Profondeur et orientation non trouvées pour ce lieu : vérifie les réglages plus bas.</p>` : ""}
      <div class="rangee"><button type="button" class="bouton secondaire" id="voir-carte">Voir sur la carte</button>
        ${cible.type === "public" ? `<button type="button" class="bouton secondaire" id="favori" aria-pressed="${estFavori(meta.id)}">${estFavori(meta.id) ? "★ Dans mes favoris" : "☆ Ajouter aux favoris"}</button>` : ""}
        ${cible.type !== "prive" ? `<button type="button" class="bouton secondaire" id="partager">Partager</button>` : ""}</div>
      <p class="confirmation" id="message-partage" hidden></p>
    </div>
    <div class="bloc"><h2 class="titre-bloc">Heure par heure</h2>${graphique(prevision, jour)}</div>
    <div class="bloc"><h2 class="titre-bloc">Conditions</h2>${conditions(prevision, jour, meta)}</div>
    <div class="bloc" id="bloc-profondeur" hidden></div>
    ${cible.type !== "public" && spot ? reglages(spot, cible.type) : ""}
    ${formulaireRetour(cible.type, meta.id)}
    ${cible.type === "prive" && spot ? actionsPrive(spot) : ""}
    ${cible.type !== "public" && CONFIG.contact ? `<p class="note"><a href="${lienProposition(meta, spot)}">Proposer ce lieu comme point Kelvisi</a> (tu choisis ce que tu envoies).</p>` : ""}
    <p class="note">Prévision indicative : elle ne remplace pas l'observation sur place. Urgence en mer : <a href="tel:196">196</a>.</p>`;

  lierRetour(zone, ctx);
  zone.querySelector("#jours-fiche").addEventListener("click", (e) => {
    const b = e.target.closest("button");
    if (!b) return;
    ctx.etat.jour = Number(b.dataset.jour);
    ctx.surJour();
    rendre(zone, cible, ctx, { meta, prevision, spot, info });
  });
  zone.querySelector("#voir-carte").addEventListener("click", () => ctx.voirSurCarte(meta.lat, meta.lon, meta.id));
  const fav = zone.querySelector("#favori");
  if (fav) fav.addEventListener("click", () => {
    const oui = basculerFavori(meta.id);
    fav.setAttribute("aria-pressed", String(oui));
    fav.textContent = oui ? "★ Dans mes favoris" : "☆ Ajouter aux favoris";
  });
  const bp = zone.querySelector("#partager");
  if (bp) bp.addEventListener("click", () => partager(zone, cible, meta, jour, v));
  lierFormulaireRetour(zone, cible, ctx, meta, prevision);
  remplirProfondeur(zone, cible, ctx, meta, prevision, jour, spot);
  if (cible.type !== "public" && spot) lierReglages(zone, cible, ctx, spot);
  if (cible.type === "prive" && spot) lierActionsPrive(zone, ctx, spot);
}

// Profondeur au point d'après le Shom : rempli dès que les mesures arrivent (souvent déjà en mémoire)
async function remplirProfondeur(zone, cible, ctx, meta, prevision, jour, spot) {
  const bloc = zone.querySelector("#bloc-profondeur");
  if (!bloc || !Number.isFinite(meta.lat)) return;
  let mesures;
  try {
    mesures = await profondeursAuPoint(meta.lat, meta.lon);
  } catch (e) {
    return;
  }
  if (!mesures.length || !bloc.isConnected) return;
  const niveaux = heuresDuJour(prevision, jour.date).map((h) => h.niveau_mer_m).filter((x) => Number.isFinite(x));
  const demiMarnage = niveaux.length ? (Math.max(...niveaux) - Math.min(...niveaux)) / 2 : 0;
  const laser = mesures.find((m) => m.type === "laser" && !m.terre && !m.au_moins);
  const utilisable = mesures.find((m) => !m.terre && !m.au_moins);
  bloc.innerHTML = `<h2 class="titre-bloc">Profondeur au point</h2>
    <div class="conditions">${mesures.map((m, i) => {
      const d = decrireMesure(m);
      return `<div class="condition${i === 0 ? " principale" : ""}"><span class="etiquette">${m.type === "laser" ? "Relevé laser" : m.type === "cotier" ? "Carte côtière" : "Carte du large"}</span>
        <span class="valeur chiffres">${d.valeur}</span><span class="sous">${echapper(d.reference)}${d.reference ? " · " : ""}${echapper(d.source)}</span></div>`;
    }).join("")}</div>
    ${laser && demiMarnage >= 0.3 ? `<p class="note">Ce jour-là, la mer descend jusqu'à environ ${metres(demiMarnage)} m sous son niveau moyen : à basse mer, compte autant de moins.</p>` : ""}
    ${mesures.some((m) => m.reference === "pbma" && !m.terre) ? '<p class="note">« Plus basses mers » : c\'est la profondeur minimale, celle des cartes marines. La marée ajoute de l\'eau par-dessus.</p>' : ""}
    ${spot && cible.type !== "public" && utilisable && Math.abs(utilisable.profondeur_m - spot.profondeur_m) >= 1 && utilisable.profondeur_m <= 40
      ? `<div class="rangee"><button type="button" class="bouton secondaire" id="utiliser-profondeur">Régler la prévision sur ${metres(utilisable.profondeur_m)} m</button></div>` : ""}
    <p class="note">Données Shom (licence ouverte) lues sur leurs cartes. Ne pas naviguer avec.</p>`;
  bloc.hidden = false;
  const b = bloc.querySelector("#utiliser-profondeur");
  if (b) b.addEventListener("click", () => {
    const champ = zone.querySelector("#regl-profondeur");
    if (!champ) return;
    champ.value = Math.round(utilisable.profondeur_m);
    champ.dispatchEvent(new Event("change"));
  });
}

function lierFormulaireRetour(zone, cible, ctx, meta, prevision) {
  const form = zone.querySelector("#form-retour");
  if (!form) return;
  const curseur = zone.querySelector("#retour-visi");
  const sortie = zone.querySelector("#retour-sortie");
  curseur.addEventListener("input", () => { sortie.textContent = `${metres(Number(curseur.value))} m`; });
  form.addEventListener("submit", async (e) => {
    e.preventDefault();
    const bouton = form.querySelector("button[type=submit]");
    bouton.disabled = true;
    const quand = zone.querySelector("#retour-quand").value;
    const m = momentDuRetour(prevision, quand);
    const resultat = await enregistrerRetour({
      spotId: meta.id, prive: cible.type === "prive", visibilite: Number(curseur.value), observeLe: m.temps, prevision: m.prevision,
    });
    const ok = zone.querySelector("#retour-ok");
    ok.textContent = {
      partage: "Merci : ton retour aide à corriger la prévision de ce point.",
      attente: "Pas de réseau : ton retour sera envoyé à la prochaine connexion.",
      local: cible.type === "prive" ? "Retour enregistré : il corrige la prévision de ton spot." : "Retour gardé sur ton appareil. Merci.",
    }[resultat];
    ok.hidden = false;
    bouton.disabled = false;
    if (cible.type === "prive") setTimeout(() => afficherFiche(zone, cible, ctx), 900);
  });
}

function lierReglages(zone, cible, ctx, spot) {
  const recalculer = async () => {
    if (cible.type === "prive") enregistrerSpot(spot);
    const r = await previsionLieu(spot, { rapports: cible.type === "prive" ? rapportsPourMoteur(spot.id) : [] });
    const y = zone.scrollTop;
    rendre(zone, cible, ctx, { meta: spotVersMeta(spot), prevision: r.prevision, spot, info: "" });
    zone.scrollTop = y;
    ctx.surSpotsModifies();
  };
  const groupe = (id, champ, conv) => {
    zone.querySelector(id).addEventListener("click", (e) => {
      const b = e.target.closest("button");
      if (!b) return;
      spot[champ] = conv(b.dataset.v);
      if (cible.type === "point") spot.estime = true;
      recalculer();
    });
  };
  groupe("#regl-orientation", "orientation_deg", Number);
  groupe("#regl-ouverture", "ouverture_deg", Number);
  groupe("#regl-fond", "fond", String);
  const prof = zone.querySelector("#regl-profondeur");
  prof.addEventListener("change", () => {
    const v = Number(prof.value);
    if (!(v >= 1 && v <= 40)) { prof.value = Math.round(spot.profondeur_m); return; }
    spot.profondeur_m = v;
    recalculer();
  });
  const enregistrer = zone.querySelector("#regl-enregistrer");
  if (enregistrer) {
    enregistrer.addEventListener("click", () => {
      try {
        const nom = zone.querySelector("#regl-nom").value.trim() || "Mon spot";
        const nouveau = enregistrerSpot({ ...spot, id: undefined, nom });
        ctx.surSpotsModifies();
        ctx.allerA(`#/prive/${nouveau.id}`);
      } catch (e) {
        enregistrer.insertAdjacentHTML("afterend", `<p class="erreur">${echapper(e.message)}</p>`);
      }
    });
  }
}

function lierActionsPrive(zone, ctx, spot) {
  zone.querySelector("#prive-renommer").addEventListener("click", () => {
    spot.nom = zone.querySelector("#prive-nom").value.trim() || spot.nom;
    enregistrerSpot(spot);
    ctx.surSpotsModifies();
    zone.querySelector(".titre-vue").textContent = spot.nom;
  });
  const confirmer = zone.querySelector("#prive-confirmer");
  zone.querySelector("#prive-supprimer").addEventListener("click", () => { confirmer.hidden = false; });
  zone.querySelector("#prive-non").addEventListener("click", () => { confirmer.hidden = true; });
  zone.querySelector("#prive-oui").addEventListener("click", () => {
    supprimerSpot(spot.id);
    ctx.surSpotsModifies();
    ctx.allerA("#/mes-spots");
  });
}
