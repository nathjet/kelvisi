// Carte : fond OpenFreeMap, vue aérienne IGN, profondeurs (EMODnet de loin, relief du Shom redessiné
// près des côtes), zones de pêche sous-marine interdite ou réglementée, repères des spots.

import { TAILLE_TUILE, URL_TUILES, installerRelief } from "./relief.js";
import { URL_ZONES } from "./zones.js";

const STYLE = "https://tiles.openfreemap.org/styles/positron";
const TUILES_IGN = "https://data.geopf.fr/wmts?SERVICE=WMTS&REQUEST=GetTile&VERSION=1.0.0&LAYER=ORTHOIMAGERY.ORTHOPHOTOS&STYLE=normal&FORMAT=image/jpeg&TILEMATRIXSET=PM&TILEMATRIX={z}&TILEROW={y}&TILECOL={x}";
const TUILES_EMODNET = "https://tiles.emodnet-bathymetry.eu/latest/mean_atlas_land/web_mercator/{z}/{x}/{y}.png";
const ZOOM_NOMBRES = 6.3;
// Relief du Shom à partir de ce zoom ; EMODnet (toute l'Europe, moins précis) en dessous
const ZOOM_RELIEF = 7;
// Zones couvertes par les modèles du Shom (Manche, Atlantique, Méditerranée, Corse)
const EMPRISE_SHOM = [-6.0, 40.7, 10.4, 52.9];
let reliefDisponible = false;

// Fond de secours si le fond OpenFreeMap ne répond pas : trait de côte simplifié (Natural Earth)
const STYLE_SECOURS = {
  version: 8,
  sources: { terre: { type: "geojson", data: new URL("../fond/terre.geojson", import.meta.url).href, attribution: "Trait de côte : Natural Earth" } },
  layers: [
    { id: "mer", type: "background", paint: { "background-color": "#cfe1e8" } },
    { id: "terre", type: "fill", source: "terre", paint: { "fill-color": "#e6ebe8", "fill-outline-color": "#9fb3bb" } },
  ],
};

let carte = null;
let secours = false;
const reperes = new Map();
let cible = null;
let rappels = { surPoint: () => {}, surMer: () => {} };
let couches = { aerien: false, profondeurs: false, zones: false };
// Zones de pêche sous-marine : rouge si interdite, orange si réglementée (les plus grandes ne sont pas dessinées)
const COULEUR_ZONE = ["match", ["get", "classe"], "interdite", "#cf3b32", "#e08a1e"];

export function carteDisponible() {
  return Boolean(window.maplibregl);
}

export function creerCarte(conteneur, options) {
  rappels = { ...rappels, ...options };
  if (!carteDisponible()) {
    conteneur.innerHTML = '<div class="carte-absente"><p>La carte n\'a pas pu se charger. Vérifie ta connexion, la liste « Où aller ? » reste disponible.</p></div>';
    return null;
  }
  if (!reliefDisponible) reliefDisponible = installerRelief(window.maplibregl);
  carte = new window.maplibregl.Map({
    container: conteneur,
    style: STYLE,
    // Toute la côte, d'Ouessant à la Corse, quelle que soit la taille de l'écran
    bounds: [[-5.3, 41.3], [9.6, 51.1]],
    fitBoundsOptions: { padding: { top: 120, bottom: 30, left: 16, right: 56 } },
    minZoom: 3.5,
    maxZoom: 17,
    attributionControl: { compact: true, customAttribution: "Prévisions Kelvisi d'après Open-Meteo" },
    cooperativeGestures: false,
  });
  // La zone de la carte change de taille avec la mise en page (onglets, panneau, rotation) :
  // sans ce suivi, le dessin serait étiré et les repères décalés.
  if ("ResizeObserver" in window) new window.ResizeObserver(() => carte.resize()).observe(conteneur);
  carte.addControl(new window.maplibregl.NavigationControl({ showCompass: false }), "top-right");
  carte.addControl(new window.maplibregl.GeolocateControl({ positionOptions: { enableHighAccuracy: false }, trackUserLocation: false }), "top-right");
  carte.addControl(new window.maplibregl.ScaleControl({ unit: "metric" }), "bottom-left");

  // Après chaque chargement de style (y compris le fond de secours), on remet nos couches
  let styleRecu = false;
  carte.on("style.load", () => {
    styleRecu = true;
    ajouterCouches();
    appliquerCouches();
  });
  const basculerSecours = () => {
    if (secours || styleRecu) return;
    secours = true;
    carte.setStyle(STYLE_SECOURS);
  };
  // Fond de secours seulement si le style du fond de carte n'arrive pas : une tuile lente ou en
  // erreur (vue aérienne, profondeurs) ne doit jamais faire perdre le fond de carte.
  setTimeout(basculerSecours, 10000);
  carte.on("error", (e) => {
    if (!styleRecu) basculerSecours();
    if (e && e.error) console.warn("Carte :", e.error.message || e.error);
  });
  carte.on("zoom", majDistance);
  carte.on("click", (e) => {
    const { lng, lat } = e.lngLat;
    rappels.surMer({ lat, lon: lng, enMer: estEnMer(e.point) });
  });
  majDistance();
  return carte;
}

function majDistance() {
  if (!carte) return;
  carte.getContainer().classList.toggle("carte--loin", carte.getZoom() < ZOOM_NOMBRES);
}

function premiereCoucheTexte() {
  const style = carte.getStyle();
  const c = (style.layers || []).find((l) => l.type === "symbol");
  return c ? c.id : undefined;
}

function ajouterCouches() {
  if (!carte.getSource("ign-ortho")) {
    carte.addSource("ign-ortho", { type: "raster", tiles: [TUILES_IGN], tileSize: 256, maxzoom: 19, attribution: "Vue aérienne © IGN" });
    carte.addLayer({ id: "couche-aerien", type: "raster", source: "ign-ortho", layout: { visibility: "none" } }, premiereCoucheTexte());
  }
  if (!carte.getSource("emodnet")) {
    carte.addSource("emodnet", { type: "raster", tiles: [TUILES_EMODNET], tileSize: 256, maxzoom: 12, attribution: "Profondeurs EMODnet Bathymetry" });
    carte.addLayer({
      id: "couche-profondeurs", type: "raster", source: "emodnet", ...(reliefDisponible ? { maxzoom: ZOOM_RELIEF } : {}),
      paint: { "raster-opacity": 0.78 }, layout: { visibility: "none" },
    }, premiereCoucheTexte());
  }
  // Relief sous-marin : les modèles du Shom (laser Litto3D, modèles côtiers et de façade) relus et
  // redessinés en tranches de profondeur, isobathes et relief éclairé (voir relief-rendu.js).
  if (reliefDisponible && !carte.getSource("relief")) {
    carte.addSource("relief", {
      type: "raster", tiles: [URL_TUILES], tileSize: TAILLE_TUILE, minzoom: ZOOM_RELIEF - 1, maxzoom: 15, bounds: EMPRISE_SHOM,
      attribution: "Relief sous-marin d'après le Shom (Litto3D® Shom-IGN, MNT côtiers et de façade)",
    });
    carte.addLayer({
      id: "couche-relief", type: "raster", source: "relief", minzoom: ZOOM_RELIEF,
      paint: { "raster-fade-duration": 150 }, layout: { visibility: "none" },
    }, premiereCoucheTexte());
  }
}

// Ajoutées seulement quand on les affiche : le fichier des zones n'est pas téléchargé sinon
function ajouterZones() {
  if (carte.getSource("zones")) return;
  carte.addSource("zones", { type: "geojson", data: URL_ZONES, attribution: "Zones réglementaires : CACEM (data.gouv.fr)" });
  const dessinees = ["!=", ["get", "grande"], true];
  carte.addLayer({
    id: "couche-zones-fond", type: "fill", source: "zones", filter: dessinees,
    paint: { "fill-color": COULEUR_ZONE, "fill-opacity": ["match", ["get", "classe"], "interdite", 0.3, 0.14] },
  }, premiereCoucheTexte());
  carte.addLayer({
    id: "couche-zones-trait", type: "line", source: "zones", filter: dessinees,
    paint: { "line-color": COULEUR_ZONE, "line-width": ["match", ["get", "classe"], "interdite", 1.6, 1], "line-opacity": 0.9 },
  }, premiereCoucheTexte());
}

function appliquerCouches() {
  if (!carte || !carte.getLayer("couche-aerien")) return;
  if (couches.zones) ajouterZones();
  for (const id of ["couche-zones-fond", "couche-zones-trait"]) {
    if (carte.getLayer(id)) carte.setLayoutProperty(id, "visibility", couches.zones ? "visible" : "none");
  }
  carte.setLayoutProperty("couche-aerien", "visibility", couches.aerien ? "visible" : "none");
  carte.setLayoutProperty("couche-profondeurs", "visibility", couches.profondeurs ? "visible" : "none");
  if (carte.getLayer("couche-relief")) carte.setLayoutProperty("couche-relief", "visibility", couches.profondeurs ? "visible" : "none");
}

export function definirCouches(nouvelles) {
  couches = { ...couches, ...nouvelles };
  appliquerCouches();
}

export function couchesActives() {
  return { ...couches };
}

function estEnMer(point) {
  try {
    const objets = carte.queryRenderedFeatures(point);
    if (objets.some((o) => o.layer.id === "terre")) return false;
    if (!objets.length || secours) return true;
    return objets.some((o) => o.sourceLayer === "water" || /water|ocean|sea/i.test(o.layer.id));
  } catch (e) {
    return true;
  }
}

// points : [{ id, nom, lat, lon, visi, classe, prive }]
export function afficherReperes(points, idChoisi) {
  if (!carte) return;
  const vus = new Set();
  for (const p of points) {
    vus.add(p.id);
    let r = reperes.get(p.id);
    if (!r) {
      const el = document.createElement("button");
      el.type = "button";
      el.addEventListener("click", (e) => {
        e.stopPropagation();
        rappels.surPoint(el.dataset.id, el.dataset.type);
      });
      r = { el, marqueur: new window.maplibregl.Marker({ element: el }).setLngLat([p.lon, p.lat]).addTo(carte) };
      reperes.set(p.id, r);
    }
    r.marqueur.setLngLat([p.lon, p.lat]);
    const el = r.el;
    el.dataset.id = p.id;
    el.dataset.prive = p.prive ? "1" : "0";
    el.dataset.type = p.type || (p.prive ? "prive" : "public");
    // Garder les classes posées par MapLibre (positionnement absolu du repère), sinon les repères se décalent
    const classesCarte = [...el.classList].filter((c) => c.startsWith("maplibregl-"));
    el.className = [...classesCarte, "repere", p.classe, p.prive ? "prive" : "", p.type === "communaute" ? "communaute" : "",
      p.id === idChoisi ? "choisi" : ""].filter(Boolean).join(" ");
    el.textContent = p.visi === null || p.visi === undefined ? "·" : String(p.visi).replace(".", ",");
    el.setAttribute("aria-label", `${p.nom} : ${p.visi === null || p.visi === undefined ? "prévision à calculer" : `${String(p.visi).replace(".", ",")} m`}`);
  }
  for (const [id, r] of reperes) {
    if (!vus.has(id)) {
      r.marqueur.remove();
      reperes.delete(id);
    }
  }
}

export function montrerCible(lat, lon) {
  if (!carte) return;
  if (!cible) {
    const el = document.createElement("div");
    el.className = "cible";
    cible = new window.maplibregl.Marker({ element: el });
  }
  cible.setLngLat([lon, lat]).addTo(carte);
}

export function cacherCible() {
  if (cible) cible.remove();
}

export function voler(lat, lon, zoom) {
  if (!carte) return;
  carte.flyTo({ center: [lon, lat], zoom: zoom ?? Math.max(carte.getZoom(), 10), speed: 1.4 });
}

export function redimensionner() {
  if (carte) requestAnimationFrame(() => carte.resize());
}
