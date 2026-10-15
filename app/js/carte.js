// Carte : fond OpenFreeMap, vue aérienne IGN, profondeurs (EMODnet, et près des côtes Shom), repères des spots.

import { COUCHES_CARTE, urlTuileShom } from "./bathymetrie.js";

const STYLE = "https://tiles.openfreemap.org/styles/positron";
const TUILES_IGN = "https://data.geopf.fr/wmts?SERVICE=WMTS&REQUEST=GetTile&VERSION=1.0.0&LAYER=ORTHOIMAGERY.ORTHOPHOTOS&STYLE=normal&FORMAT=image/jpeg&TILEMATRIXSET=PM&TILEMATRIX={z}&TILEROW={y}&TILECOL={x}";
const TUILES_EMODNET = "https://tiles.emodnet-bathymetry.eu/latest/mean_atlas_land/web_mercator/{z}/{x}/{y}.png";
const ZOOM_NOMBRES = 6.3;

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
let couches = { aerien: false, profondeurs: false };

export function carteDisponible() {
  return Boolean(window.maplibregl);
}

export function creerCarte(conteneur, options) {
  rappels = { ...rappels, ...options };
  if (!carteDisponible()) {
    conteneur.innerHTML = '<div class="carte-absente"><p>La carte n\'a pas pu se charger. Vérifie ta connexion, la liste « Où aller ? » reste disponible.</p></div>';
    return null;
  }
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
    carte.addLayer({ id: "couche-profondeurs", type: "raster", source: "emodnet", paint: { "raster-opacity": 0.78 }, layout: { visibility: "none" } }, premiereCoucheTexte());
  }
  // Près des côtes : relevés laser Litto3D (au mètre) et modèles côtiers du Shom, à partir du zoom 10.
  // Une source par couche, limitée à sa zone : aucune tuile n'est demandée ailleurs.
  COUCHES_CARTE.forEach((c, i) => {
    if (carte.getSource(`shom-${i}`)) return;
    carte.addSource(`shom-${i}`, {
      type: "raster", tiles: [urlTuileShom(c.couche)], tileSize: 256, minzoom: 10, maxzoom: 18, bounds: c.zone,
      attribution: "Profondeurs côtières © Shom, Litto3D® Shom-IGN",
    });
    carte.addLayer({ id: `couche-shom-${i}`, type: "raster", source: `shom-${i}`, minzoom: 10, paint: { "raster-opacity": 0.9 }, layout: { visibility: "none" } }, premiereCoucheTexte());
  });
}

function appliquerCouches() {
  if (!carte || !carte.getLayer("couche-aerien")) return;
  carte.setLayoutProperty("couche-aerien", "visibility", couches.aerien ? "visible" : "none");
  carte.setLayoutProperty("couche-profondeurs", "visibility", couches.profondeurs ? "visible" : "none");
  COUCHES_CARTE.forEach((_, i) => {
    if (carte.getLayer(`couche-shom-${i}`)) carte.setLayoutProperty(`couche-shom-${i}`, "visibility", couches.profondeurs ? "visible" : "none");
  });
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
        rappels.surPoint(el.dataset.id, el.dataset.prive === "1");
      });
      r = { el, marqueur: new window.maplibregl.Marker({ element: el }).setLngLat([p.lon, p.lat]).addTo(carte) };
      reperes.set(p.id, r);
    }
    r.marqueur.setLngLat([p.lon, p.lat]);
    const el = r.el;
    el.dataset.id = p.id;
    el.dataset.prive = p.prive ? "1" : "0";
    // Garder les classes posées par MapLibre (positionnement absolu du repère), sinon les repères se décalent
    const classesCarte = [...el.classList].filter((c) => c.startsWith("maplibregl-"));
    el.className = [...classesCarte, "repere", p.classe, p.prive ? "prive" : "", p.id === idChoisi ? "choisi" : ""].filter(Boolean).join(" ");
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
