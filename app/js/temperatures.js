// Température de l'eau en profondeur : profils calculés chaque heure autour des points Kelvisi
// (modèles physiques de Copernicus Marine, moyenne de chaque jour, de la surface à 40 m).
// Un spot privé ou un lieu libre reprend le profil du point Kelvisi le plus proche (moins de 25 km,
// même façade), lu à sa propre profondeur.

import { distanceKm } from "./format.js";

const RAYON_KM = 25;
let chargement = null;

export function chargerTemperatures() {
  if (!chargement) {
    chargement = fetch("donnees/temperatures.json", { cache: "no-cache" })
      .then((r) => (r.ok ? r.json() : null))
      .catch(() => null)
      .then((t) => {
        if (!t || !t.points) chargement = null; // réessayé à la prochaine fiche
        return t && t.points ? t : null;
      });
  }
  return chargement;
}

// Température à une profondeur, par interpolation dans le profil (au-delà du profil : niveau le plus profond)
export function lireProfil(profondeurs, valeurs, profondeur) {
  const p = Math.min(Math.max(profondeur, profondeurs[0]), profondeurs[profondeurs.length - 1]);
  let i = 0;
  while (i < profondeurs.length - 2 && profondeurs[i + 1] < p) i++;
  const [p0, p1] = [profondeurs[i], profondeurs[Math.min(i + 1, profondeurs.length - 1)]];
  const [t0, t1] = [valeurs[i], valeurs[Math.min(i + 1, valeurs.length - 1)]];
  const t = p1 === p0 ? t0 : t0 + ((t1 - t0) * (p - p0)) / (p1 - p0);
  return { temperature: Math.round(t * 10) / 10, profondeur: Math.round(p * 10) / 10 };
}

const memeBassin = (a, b) => (a === "mediterranee") === (b === "mediterranee");

// { temperature, profondeur (lue), profondeur_demandee, reference: { nom, distance_km } | null } ou null
export function temperatureAuFond(donnees, lieu, date, noms = {}) {
  if (!donnees?.points || !Number.isFinite(lieu?.profondeur_m)) return null;
  let profil = donnees.points[lieu.id];
  let reference = null;
  if (!profil) {
    let meilleur = null;
    for (const [id, p] of Object.entries(donnees.points)) {
      if (!memeBassin(p.region, lieu.region)) continue;
      const d = distanceKm(lieu.lat, lieu.lon, p.lat, p.lon);
      if (d <= RAYON_KM && (!meilleur || d < meilleur.d)) meilleur = { id, p, d };
    }
    if (!meilleur) return null;
    profil = meilleur.p;
    reference = { nom: noms[meilleur.id] || "voisin", distance_km: Math.round(meilleur.d) };
  }
  const i = profil.dates.indexOf(date);
  if (i < 0 || !profil.valeurs[i]) return null;
  const lu = lireProfil(profil.profondeurs, profil.valeurs[i], lieu.profondeur_m);
  return { ...lu, profondeur_demandee: lieu.profondeur_m, reference };
}
