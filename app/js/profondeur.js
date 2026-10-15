// Profondeur et orientation d'un lieu. D'abord avec les modèles du Shom (relevés laser au mètre,
// modèles côtiers à 20 m, modèles de façade à 100 m), sinon avec EMODnet (maille d'environ 100 m).
// Sert à pré-remplir la fiche d'un lieu ; l'utilisateur peut toujours corriger.

import { grilleAutour, meilleureMesure, orientationDepuisGrille, profondeursAuPoint } from "./bathymetrie.js";

const URL = "https://rest.emodnet-bathymetry.eu/depth_sample";

// Profondeur moyenne (m, positive en mer) au point, ou null à terre ou en cas d'échec
export async function profondeurAuPoint(lat, lon, signal) {
  const geom = `POINT(${lon.toFixed(3)} ${lat.toFixed(3)})`;
  try {
    const r = await fetch(`${URL}?geom=${encodeURIComponent(geom)}`, { signal });
    if (!r.ok) return null;
    const d = await r.json();
    const v = Number(d.avg);
    return Number.isFinite(v) && v > 0 ? v : null;
  } catch (e) {
    if (e.name === "AbortError") throw e;
    return null;
  }
}

function deplacer(lat, lon, azimut, metres) {
  const rad = Math.PI / 180;
  return [
    lat + (metres * Math.cos(azimut * rad)) / 111320,
    lon + (metres * Math.sin(azimut * rad)) / (111320 * Math.cos(lat * rad)),
  ];
}

export async function estimerLieu(lat, lon, signal) {
  try {
    const [mesures, grille] = await Promise.all([profondeursAuPoint(lat, lon, { signal }), grilleAutour(lat, lon, { signal })]);
    let orientation = grille ? orientationDepuisGrille(grille) : null;
    const m = meilleureMesure(mesures);
    if (!orientation && m && !m.terre) {
      const e = await estimerLieuEmodnet(lat, lon, signal);
      if (e && e.orientation_deg !== null) orientation = { orientation_deg: e.orientation_deg, ouverture_deg: e.ouverture_deg };
    }
    if (orientation || (m && !m.terre)) {
      return {
        profondeur_m: m && !m.terre ? m.profondeur_m : null,
        orientation_deg: orientation ? orientation.orientation_deg : null,
        ouverture_deg: orientation ? orientation.ouverture_deg : 90,
        mesures,
        source: "shom",
      };
    }
  } catch (e) {
    if (e.name === "AbortError") throw e;
  }
  const ancien = await estimerLieuEmodnet(lat, lon, signal);
  return ancien && { ...ancien, mesures: [], source: "emodnet" };
}

// Direction vers le large : celle où le fond plonge le plus, sur un cercle de 1,5 km
async function estimerLieuEmodnet(lat, lon, signal) {
  const directions = [0, 45, 90, 135, 180, 225, 270, 315];
  const [centre, ...autour] = await Promise.all([
    profondeurAuPoint(lat, lon, signal),
    ...directions.map((az) => profondeurAuPoint(...deplacer(lat, lon, az, 1500), signal)),
  ]);
  const mer = directions.map((az, i) => ({ az, p: autour[i] })).filter((x) => x.p !== null);
  if (!mer.length && centre === null) return null;
  let sx = 0, sy = 0;
  for (const { az, p } of mer) {
    sx += Math.sin((az * Math.PI) / 180) * p;
    sy += Math.cos((az * Math.PI) / 180) * p;
  }
  const orientation = mer.length ? Math.round(((Math.atan2(sx, sy) * 180) / Math.PI + 360) % 360) : null;
  return {
    profondeur_m: centre,
    orientation_deg: orientation,
    ouverture_deg: Math.max(45, Math.min(180, mer.length * 22.5 + 22.5)),
  };
}
