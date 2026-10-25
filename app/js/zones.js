// Zones où la pêche sous-marine est interdite ou réglementée, d'après les zones réglementaires du CACEM
// (outils/zones_reglementees.py). Le fichier complet n'est téléchargé que si la couche est affichée ou
// si un lieu tombe dans l'emprise d'une zone (petit index des emprises).

import { echapper } from "./format.js";

export const URL_ZONES = new URL("../zones/peche-sous-marine.geojson", import.meta.url).href;
const URL_INDEX = new URL("../zones/peche-sous-marine-index.json", import.meta.url).href;

let index = null;
let zones = null;

function memoriser(url, garder) {
  const p = fetch(url).then((r) => {
    if (!r.ok) throw new Error(`Zones indisponibles (${r.status})`);
    return r.json();
  });
  p.catch(() => garder(null));
  return p;
}

export function chargerZones() {
  if (!zones) zones = memoriser(URL_ZONES, (v) => { zones = v; });
  return zones;
}

function chargerIndex() {
  if (!index) index = memoriser(URL_INDEX, (v) => { index = v; });
  return index;
}

// Point dans un anneau (lancer de rayon), coordonnées [lon, lat]
export function dansAnneau(lon, lat, anneau) {
  let dedans = false;
  for (let i = 0, j = anneau.length - 1; i < anneau.length; j = i++) {
    const [xi, yi] = anneau[i];
    const [xj, yj] = anneau[j];
    if ((yi > lat) !== (yj > lat) && lon < ((xj - xi) * (lat - yi)) / (yj - yi) + xi) dedans = !dedans;
  }
  return dedans;
}

export function dansGeometrie(lon, lat, g) {
  const polygone = (anneaux) => dansAnneau(lon, lat, anneaux[0]) && !anneaux.slice(1).some((t) => dansAnneau(lon, lat, t));
  if (g?.type === "Polygon") return polygone(g.coordinates);
  if (g?.type === "MultiPolygon") return g.coordinates.some(polygone);
  return false;
}

// Zones qui contiennent le lieu, celles où la chasse est interdite d'abord : [{ classe, regles: [...] }]
export async function zonesAuPoint(lat, lon) {
  const idx = await chargerIndex();
  const candidats = [];
  idx.boites.forEach((b, i) => {
    if (lon >= b[0] && lat >= b[1] && lon <= b[2] && lat <= b[3]) candidats.push(i);
  });
  if (!candidats.length) return [];
  const collection = await chargerZones();
  return candidats
    .map((i) => collection.features[i])
    .filter((f) => f && dansGeometrie(lon, lat, f.geometry))
    .map((f) => f.properties)
    .sort((a, b) => (a.classe === "interdite" ? 0 : 1) - (b.classe === "interdite" ? 0 : 1));
}

function regleHtml(r) {
  return `<li><strong>${echapper(r.nom)}</strong>${r.periode ? " (selon la période de l'année)" : ""} : ${echapper(r.regle || "voir le texte officiel")}
    ${r.reference ? `<br><span class="note">Texte : ${echapper(r.reference)}</span>` : ""}</li>`;
}

// Encart d'une fiche : rouge si la chasse est interdite, plus discret si elle est seulement réglementée
export function encartZones(liste, { court = false } = {}) {
  if (!liste?.length) return "";
  const interdite = liste.some((z) => z.classe === "interdite");
  const regles = liste.flatMap((z) => z.regles.filter((r) => !interdite || r.classe === "interdite"));
  const titre = interdite ? "Chasse sous-marine interdite ici" : "Règles particulières ici";
  if (court) {
    return `<div class="encart ${interdite ? "zone-interdite" : "info"}"><strong>${titre}</strong> : ${echapper(regles[0].nom)}${regles.length > 1 ? ` et ${regles.length - 1} autre${regles.length > 2 ? "s" : ""} règle${regles.length > 2 ? "s" : ""}` : ""}.</div>`;
  }
  return `<div class="encart ${interdite ? "zone-interdite" : "info"}"><strong>${titre}</strong>
    <ul class="regles-zone">${regles.slice(0, 4).map(regleHtml).join("")}</ul>
    <p class="note">D'après les zones réglementaires recensées par l'État (CACEM). Tracés indicatifs et liste incomplète : seul le texte officiel fait foi.</p></div>`;
}
