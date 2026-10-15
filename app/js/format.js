// Mise en forme des nombres, heures et directions, en français.

import { lire } from "./stockage.js";

export const NOM_FACADE = { manche: "Manche", atlantique: "Atlantique", mediterranee: "Méditerranée", corse: "Corse" };
export const NOM_CLASSE = { mauvaise: "Mauvaise", moyenne: "Moyenne", bonne: "Bonne", excellente: "Excellente" };
export const NOM_FOND = { sable: "sable", vase: "vase", mixte: "fond mixte", herbier: "herbier", roche: "roche" };
const SECTEURS = ["nord", "nord-est", "est", "sud-est", "sud", "sud-ouest", "ouest", "nord-ouest"];
export const SECTEURS_COURTS = ["N", "NE", "E", "SE", "S", "SO", "O", "NO"];

export function metres(x) {
  if (x === null || x === undefined || !Number.isFinite(x)) return "?";
  const v = x < 10 ? Math.round(x * 2) / 2 : Math.round(x);
  return String(v).replace(".", ",");
}

export function heure(iso) {
  if (!iso) return "?";
  const h = parseInt(iso.slice(11, 13), 10);
  const mn = iso.slice(14, 16);
  return `${h} h${mn !== "00" ? " " + mn : ""}`;
}

function dateUTC(date) {
  const [a, m, j] = date.slice(0, 10).split("-").map(Number);
  return new Date(Date.UTC(a, m - 1, j, 12));
}

export function jourCourt(date) {
  return new Intl.DateTimeFormat("fr-FR", { weekday: "short", day: "numeric", timeZone: "UTC" }).format(dateUTC(date));
}

export function jourLong(date) {
  return new Intl.DateTimeFormat("fr-FR", { weekday: "long", day: "numeric", month: "long", timeZone: "UTC" }).format(dateUTC(date));
}

export function dateHeure(iso, fuseau = "Europe/Paris") {
  if (!iso) return "";
  return new Intl.DateTimeFormat("fr-FR", { weekday: "short", day: "numeric", month: "short", hour: "2-digit", minute: "2-digit", timeZone: fuseau })
    .format(new Date(iso));
}

export function secteur(deg) {
  if (deg === null || deg === undefined || !Number.isFinite(deg)) return "";
  return SECTEURS[Math.floor((((deg % 360) + 360) % 360 + 22.5) / 45) % 8];
}

export function de(mot) {
  return /^[aeiouy]/.test(mot) ? `d'${mot}` : `de ${mot}`;
}

// Flèche vers où va le vent ou la houle (provenance + 180°)
export function fleche(deg) {
  if (deg === null || deg === undefined) return "";
  const r = (deg + 180) % 360;
  return `<svg class="fleche" viewBox="0 0 16 16" aria-hidden="true"><g transform="rotate(${r} 8 8)"><path d="M8 1 L12 9 L8.9 8 L8.9 15 L7.1 15 L7.1 8 L4 9 Z" fill="currentColor"/></g></svg>`;
}

export function echapper(t) {
  return String(t ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
}

export function distanceKm(lat1, lon1, lat2, lon2) {
  const r = Math.PI / 180;
  const dp = (lat2 - lat1) * r, dl = (lon2 - lon1) * r;
  const a = Math.sin(dp / 2) ** 2 + Math.cos(lat1 * r) * Math.cos(lat2 * r) * Math.sin(dl / 2) ** 2;
  return 2 * 6371 * Math.asin(Math.sqrt(a));
}

// Façade d'un lieu quelconque, d'après sa position
export function regionPour(lat, lon) {
  if (lon > 2.9 && lat < 43.95) return "mediterranee";
  if (lat >= 48.45 && lon > -4.78) return "manche";
  return "atlantique";
}

export function facadePour(lat, lon) {
  const r = regionPour(lat, lon);
  if (r === "mediterranee" && lon > 8.4 && lat < 43.1) return "corse";
  return r;
}

// Vent en nœuds par défaut, ou en km/h selon le réglage de l'onglet Infos
export const CLE_UNITE_VENT = "kelvisi-unite-vent";

export function vitesseVent(kn) {
  if (kn === null || kn === undefined || !Number.isFinite(kn)) return "?";
  if (lire(CLE_UNITE_VENT, "kn") === "kmh") return `${Math.round(kn * 1.852)} km/h`;
  return `${Math.round(kn)} nœud${Math.round(kn) >= 2 ? "s" : ""}`;
}

// Phase de la Lune à une date (midi UTC), et période de marée qui en découle en Manche et Atlantique.
// Les vives-eaux arrivent environ un jour et demi après la nouvelle et la pleine lune.
const NOUVELLE_LUNE_REF = Date.UTC(2000, 0, 6, 18, 14) / 86400000;
const LUNAISON = 29.530588853;
const PHASES = ["Nouvelle lune", "Premier croissant", "Premier quartier", "Gibbeuse croissante",
  "Pleine lune", "Gibbeuse décroissante", "Dernier quartier", "Dernier croissant"];

export function lune(date) {
  const jour = Date.parse(`${date.slice(0, 10)}T12:00:00Z`) / 86400000;
  const age = (((jour - NOUVELLE_LUNE_REF) % LUNAISON) + LUNAISON) % LUNAISON;
  const phase = PHASES[Math.floor((age / LUNAISON) * 8 + 0.5) % 8];
  const demi = LUNAISON / 2;
  const depuisVives = (((age - 1.5) % demi) + demi) % demi;
  let maree;
  if (depuisVives <= 2 || depuisVives >= demi - 2) maree = "vives-eaux";
  else if (Math.abs(depuisVives - demi / 2) <= 2) maree = "mortes-eaux";
  else maree = depuisVives < demi / 2 ? "coefficients en baisse" : "coefficients en hausse";
  return { age, phase, maree };
}
