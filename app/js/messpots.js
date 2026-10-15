// Spots privés : enregistrés uniquement sur cet appareil, jamais envoyés à Kelvisi.

import { lire, ecrire, identifiant } from "./stockage.js";
import { regionPour } from "./format.js";
import { supprimerRetoursDuSpot } from "./retours.js";
import { noterSpot } from "./synchro.js";

const CLE = "kelvisi-spots";
const FONDS = ["sable", "vase", "mixte", "herbier", "roche"];

export function mesSpots() {
  return lire(CLE, []);
}

export function monSpot(id) {
  return mesSpots().find((s) => s.id === id) || null;
}

export function normaliser(s) {
  const lat = Number(s.lat), lon = Number(s.lon);
  if (!(lat > -90 && lat < 90 && lon > -180 && lon < 180)) throw new Error("Position invalide");
  return {
    id: s.id || `prive-${identifiant()}`,
    nom: String(s.nom || "Mon spot").trim().slice(0, 60) || "Mon spot",
    lat: Math.round(lat * 1e5) / 1e5,
    lon: Math.round(lon * 1e5) / 1e5,
    region: regionPour(lat, lon),
    orientation_deg: ((Math.round(Number(s.orientation_deg) || 0) % 360) + 360) % 360,
    ouverture_deg: Math.min(180, Math.max(30, Number(s.ouverture_deg) || 90)),
    profondeur_m: Math.min(40, Math.max(1, Number(s.profondeur_m) || 8)),
    fond: FONDS.includes(s.fond) ? s.fond : "mixte",
    prive: true,
    cree_le: s.cree_le || new Date().toISOString(),
    maj_le: new Date().toISOString(),
  };
}

export function enregistrerSpot(s) {
  const spot = normaliser(s);
  const liste = mesSpots().filter((x) => x.id !== spot.id);
  liste.push(spot);
  if (!ecrire(CLE, liste)) throw new Error("Impossible d'enregistrer sur cet appareil (stockage plein ou bloqué)");
  noterSpot(spot.id, "maj");
  return spot;
}

export function supprimerSpot(id) {
  ecrire(CLE, mesSpots().filter((x) => x.id !== id));
  supprimerRetoursDuSpot(id);
  noterSpot(id, "suppr");
}
