// Chargement des prévisions : points publics (calculés chaque heure) et lieux libres ou spots
// privés (calculés dans le navigateur avec la météo Open-Meteo du moment).

import { definirParametres, prevoir } from "./moteur/moteur.js";
import { recupererConditions } from "./moteur/openmeteo.js";
import { lire, ecrire } from "./stockage.js";
import { CONFIG } from "./config.js";
import { distanceKm } from "./format.js";

const DUREE_CACHE_METEO_S = 3600;
// Distance maximale pour reprendre les valeurs calées d'un point de référence (km)
const RAYON_REFERENCE_KM = 25;

let resume = null;
const details = new Map();

async function lireJson(url) {
  const r = await fetch(url, { cache: "no-cache" });
  if (!r.ok) throw new Error(`Fichier introuvable : ${url}`);
  return r.json();
}

export async function demarrer() {
  const [p, r] = await Promise.all([lireJson("donnees/parametres.json"), lireJson("donnees/resume.json")]);
  definirParametres(p);
  resume = r;
  return resume;
}

export function resumeCharge() {
  return resume;
}

export function pointPublic(id) {
  return resume?.points.find((p) => p.id === id) || null;
}

export async function detailPublic(id) {
  if (!details.has(id)) details.set(id, lireJson(`donnees/points/${encodeURIComponent(id)}.json`));
  try {
    return await details.get(id);
  } catch (e) {
    details.delete(id);
    throw e;
  }
}

// Météo d'un lieu : gardée une heure sur l'appareil, et réutilisée hors connexion
async function conditionsLieu(lat, lon, { forcer = false, signal } = {}) {
  const cle = `kelvisi-meteo-${lat.toFixed(2)}-${lon.toFixed(2)}`;
  const memo = lire(cle, null);
  const maintenant = Date.now() / 1000;
  if (!forcer && memo && maintenant - memo.recu_le < DUREE_CACHE_METEO_S) return { ...memo, horsLigne: false };
  try {
    const conditions = await recupererConditions(lat, lon, { signal });
    const entree = { recu_le: maintenant, conditions };
    if (!ecrire(cle, entree)) {
      // Stockage plein : on vide les anciennes météos puis on réessaie
      nettoyerCacheMeteo();
      ecrire(cle, entree);
    }
    return { ...entree, horsLigne: false };
  } catch (e) {
    if (e.name === "AbortError") throw e;
    if (memo) return { ...memo, horsLigne: true, erreur: e };
    throw e;
  }
}

function nettoyerCacheMeteo() {
  try {
    const cles = Object.keys(localStorage).filter((k) => k.startsWith("kelvisi-meteo-"));
    cles.forEach((k) => localStorage.removeItem(k));
  } catch (e) {
    /* rien à faire */
  }
}

// Point de référence le plus proche (même façade) dont la visibilité habituelle et la réaction
// à la houle ont été calées sur le satellite, à moins de RAYON_REFERENCE_KM.
export function referenceProche(lat, lon, region) {
  let meilleur = null;
  for (const p of resume?.points || []) {
    if (!p.calage || p.region !== region) continue;
    const d = distanceKm(lat, lon, p.lat, p.lon);
    if (d <= RAYON_REFERENCE_KM && (!meilleur || d < meilleur.distance_km)) meilleur = { id: p.id, nom: p.nom, distance_km: d, ...p.calage };
  }
  return meilleur;
}

// Prévision d'un lieu décrit comme un spot (lat, lon, region, orientation_deg, ouverture_deg, profondeur_m, fond)
export async function previsionLieu(spot, { rapports = [], forcer = false, signal } = {}) {
  const { conditions, recu_le, horsLigne } = await conditionsLieu(spot.lat, spot.lon, { forcer, signal });
  const maintenant = Math.floor(Date.now() / 1000);
  const reference = spot.visibilite_calme_m == null ? referenceProche(spot.lat, spot.lon, spot.region) : null;
  const calcule = reference
    ? { ...spot, visibilite_calme_m: reference.visibilite_calme_m, sensibilite_houle: reference.sensibilite_houle }
    : spot;
  const prevision = prevoir(calcule, conditions, Math.max(maintenant, conditions.temps[0]), { rapports, jours: 3, fuseau: CONFIG.fuseau });
  prevision.reference = reference ? { nom: reference.nom, distance_km: Math.round(reference.distance_km) } : null;
  return { prevision, recu_le, horsLigne };
}
