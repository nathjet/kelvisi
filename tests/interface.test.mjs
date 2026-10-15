// Test de bout en bout de l'interface, dans un navigateur simulé (jsdom).
// La carte (WebGL) et les services en ligne sont remplacés par des doublures ;
// les prévisions des points publics sont celles de app/donnees.
//
// Usage : npm test   (lance les parcours « grand écran » et « téléphone »)

import { readFileSync, existsSync } from "node:fs";
import { fileURLToPath, pathToFileURL } from "node:url";
import { dirname, join } from "node:path";
import { spawnSync } from "node:child_process";
import assert from "node:assert/strict";
import { JSDOM } from "jsdom";

const ICI = dirname(fileURLToPath(import.meta.url));
const APP = join(ICI, "..", "app");
const mode = process.argv[2];

if (!mode) {
  let echec = false;
  for (const m of ["grand", "telephone"]) {
    const r = spawnSync(process.execPath, [fileURLToPath(import.meta.url), m], { encoding: "utf8" });
    process.stdout.write(r.stdout);
    process.stderr.write(r.stderr);
    if (r.status !== 0) echec = true;
  }
  process.exit(echec ? 1 : 0);
}

// --- Doublures des services ------------------------------------------------------------------

const fixture = JSON.parse(readFileSync(join(ICI, "fixtures", "conditions_reelles_quiberon.json"), "utf8"));
const MARINE = {
  wave_height: "hauteur_vagues", wave_period: "periode_vagues", wave_direction: "direction_vagues",
  swell_wave_height: "hauteur_houle", swell_wave_period: "periode_houle", swell_wave_direction: "direction_houle",
  wind_wave_height: "hauteur_mer_vent", wind_wave_period: "periode_mer_vent", wind_wave_direction: "direction_mer_vent",
  ocean_current_velocity: "courant", ocean_current_direction: "direction_courant",
  sea_level_height_msl: "niveau_mer", sea_surface_temperature: "temperature_eau",
};
const METEO = { wind_speed_10m: "vent", wind_direction_10m: "direction_vent", wind_gusts_10m: "rafales", precipitation: "pluie", cloud_cover: "nebulosite" };
const KMH = new Set(["courant", "vent", "rafales"]);
// La météo simulée commence 5 jours avant « maintenant » : on décale la fixture
const decalage = Math.floor(Date.now() / 1000 / 3600) * 3600 - 5 * 86400 - fixture.temps[0];
function reponseOpenMeteo(table) {
  const hourly = { time: fixture.temps.map((t) => t + decalage) };
  for (const [api, nom] of Object.entries(table)) {
    hourly[api] = fixture.series[nom].map((v) => (v === null ? null : KMH.has(nom) ? v * 3.6 : v));
  }
  return { latitude: fixture.lat, longitude: fixture.lon, hourly };
}

const appels = [];
const envois = [];
async function fauxFetch(entree, options = {}) {
  const url = String(entree);
  appels.push(url);
  const json = (d, statut = 200) => ({ ok: statut === 200, status: statut, json: async () => d });
  if (url.includes("supabase.test/rest/v1/rapports")) {
    envois.push(JSON.parse(options.body));
    return { ok: true, status: 201, json: async () => null };
  }
  if (url.startsWith("donnees/")) {
    const chemin = join(APP, decodeURIComponent(url.split("?")[0]));
    if (!existsSync(chemin)) return json(null, 404);
    return json(JSON.parse(readFileSync(chemin, "utf8")));
  }
  if (url.includes("marine-api.open-meteo.com")) return json(reponseOpenMeteo(MARINE));
  if (url.includes("api.open-meteo.com")) return json(reponseOpenMeteo(METEO));
  if (url.includes("rest.emodnet-bathymetry.eu")) {
    const m = decodeURIComponent(url).match(/POINT\(([-\d.]+) ([-\d.]+)\)/);
    const lon = Number(m[1]);
    // La mer est à l'ouest de -3.16 : le large est donc vers l'ouest
    return json({ avg: lon < -3.16 ? 4 + (-3.16 - lon) * 300 : -12 });
  }
  if (url.includes("data.geopf.fr/geocodage")) {
    const poi = url.includes("index=poi");
    return json({
      type: "FeatureCollection",
      features: poi
        ? [{ geometry: { type: "Point", coordinates: [-3.155, 47.49] }, properties: { toponym: "Pointe du Conguel", category: ["cap"], score: 0.9, _type: "poi" } }]
        : [{ geometry: { type: "Point", coordinates: [-3.12, 47.48] }, properties: { name: "Quiberon", context: "56, Morbihan, Bretagne", score: 0.95, _type: "address" } }],
    });
  }
  throw new Error(`Appel réseau inattendu : ${url}`);
}

// --- Doublure de la carte ----------------------------------------------------------------------

let carte = null;
class FausseCarte {
  constructor(o) { this.o = o; this.gest = {}; this.zoom = o.zoom ?? 5; this.conteneur = o.container; carte = this; }
  on(ev, f) { (this.gest[ev] ||= []).push(f); }
  emettre(ev, e) { (this.gest[ev] || []).forEach((f) => f(e)); }
  addControl() {}
  getZoom() { return this.zoom; }
  getContainer() { return this.conteneur; }
  getStyle() { return { layers: [{ id: "water", type: "fill" }, { id: "place", type: "symbol" }] }; }
  isStyleLoaded() { return true; }
  setStyle(s) { this.style = s; }
  getSource(id) { return this.sources?.[id]; }
  addSource(id, s) { (this.sources ||= {})[id] = s; }
  addLayer(c) { (this.couches ||= {})[c.id] = { ...c }; }
  getLayer(id) { return this.couches?.[id]; }
  setLayoutProperty(id, p, v) { this.couches[id].visibilite = v; }
  queryRenderedFeatures() { return [{ sourceLayer: "water", layer: { id: "water" } }]; }
  flyTo(o) { this.centre = o.center; this.zoom = o.zoom; }
  resize() {}
}
class FauxRepere {
  constructor({ element }) { this.element = element; element.classList.add("maplibregl-marker"); }
  setLngLat(l) { this.l = l; return this; }
  addTo(c) { c.conteneur.appendChild(this.element); return this; }
  remove() { this.element.remove(); }
}

// --- Navigateur simulé ----------------------------------------------------------------------------

const grand = mode === "grand";
const html = readFileSync(join(APP, "index.html"), "utf8").replace(/<script[^>]*><\/script>/g, "");
const dom = new JSDOM(html, { url: "https://kelvisi.test/", pretendToBeVisual: true });
const w = dom.window;
w.matchMedia = (q) => ({ matches: grand && /min-width/.test(q), media: q, addEventListener() {}, removeEventListener() {} });
w.maplibregl = { Map: FausseCarte, Marker: FauxRepere, NavigationControl: class {}, GeolocateControl: class {}, ScaleControl: class {} };
w.fetch = fauxFetch;
w.scrollTo = () => {};
w.navigator.geolocation = { getCurrentPosition: (ok) => ok({ coords: { latitude: 47.48, longitude: -3.12 } }) };
const copies = [];
Object.defineProperty(w.navigator, "clipboard", { value: { writeText: async (t) => { copies.push(t); } }, configurable: true });
for (const nom of ["window", "document", "location", "localStorage", "history", "HTMLElement", "Event", "CustomEvent", "AbortController", "requestAnimationFrame"]) {
  globalThis[nom] = w[nom];
}
Object.defineProperty(globalThis, "navigator", { value: w.navigator, configurable: true, writable: true });
globalThis.fetch = fauxFetch;
globalThis.window.requestAnimationFrame ||= (f) => setTimeout(f, 0);
globalThis.requestAnimationFrame = globalThis.window.requestAnimationFrame;

const d = w.document;
const attendre = (ms = 30) => new Promise((ok) => setTimeout(ok, ms));
async function jusqua(condition, message, delai = 3000) {
  const debut = Date.now();
  while (Date.now() - debut < delai) {
    if (condition()) return;
    await attendre(20);
  }
  throw new Error(`Délai dépassé : ${message}`);
}
async function aller(hash) {
  w.location.hash = hash;
  await attendre(40);
}
const panneau = () => d.getElementById("panneau");
const texte = (el) => el.textContent.replace(/\s+/g, " ").trim();
const erreurs = [];
w.addEventListener("error", (e) => erreurs.push(e.message));
process.on("unhandledRejection", (e) => erreurs.push(String(e)));

const etapes = [];
async function etape(nom, f) {
  try {
    await f();
    etapes.push(`  ok  ${nom}`);
  } catch (e) {
    etapes.push(`  ÉCHEC ${nom} : ${e.message}`);
    process.exitCode = 1;
  }
}

await import(pathToFileURL(join(APP, "js", "app.js")).href);
const resume = JSON.parse(readFileSync(join(APP, "donnees", "resume.json"), "utf8"));

await etape("démarrage et repères sur la carte", async () => {
  await jusqua(() => d.querySelectorAll(".repere").length >= resume.points.length, "repères");
  assert.equal(d.querySelectorAll(".repere").length, resume.points.length);
  assert.equal(d.querySelectorAll(".repere.maplibregl-marker").length, resume.points.length, "repères positionnés par la carte");
  assert.match(d.getElementById("fraicheur").textContent, /Prévisions/);
  if (grand) assert.match(texte(panneau()), /Où aller \?/);
  else assert.ok(d.body.classList.contains("route-carte"));
});

await etape("liste « Où aller ? » triée et filtrée", async () => {
  await aller("#/liste");
  const lignes = [...panneau().querySelectorAll(".ligne-spot")];
  assert.equal(lignes.length, resume.points.length);
  const visis = lignes.map((l) => parseFloat(l.querySelector(".visi strong").textContent.replace(",", ".")));
  assert.ok(visis.every((v, i) => i === 0 || v <= visis[i - 1] + 1e-9), "tri décroissant");
  panneau().querySelector('[data-facade="manche"]').click();
  await attendre();
  const manche = resume.points.filter((p) => p.facade === "manche").length;
  assert.equal(panneau().querySelectorAll(".ligne-spot").length, manche);
  panneau().querySelector("#autour").click();
  await attendre();
  assert.match(texte(panneau()), /Depuis : ma position/);
  panneau().querySelector('[data-facade="toutes"]').click();
  await attendre();
  const n = panneau().querySelectorAll(".ligne-spot").length;
  assert.ok(n > 0 && n < resume.points.length, "rayon de 100 km autour de Quiberon");
  panneau().querySelector("#sans-origine").click();
  await attendre();
});

await etape("fiche d'un point public", async () => {
  await aller("#/spot/ref-quiberon");
  await jusqua(() => panneau().querySelector(".lecture"), "fiche");
  assert.match(texte(panneau()), /Quiberon, côte sauvage/);
  assert.ok(panneau().querySelector(".graphique svg rect"), "graphique");
  assert.ok(panneau().querySelectorAll(".condition").length >= 3, "conditions");
  panneau().querySelector('#jours-fiche button[data-jour="2"]').click();
  await attendre();
  assert.equal(panneau().querySelector('#jours-fiche button[aria-pressed="true"]').dataset.jour, "2");
  panneau().querySelector('#jours-fiche button[data-jour="0"]').click();
  await attendre();
});

await etape("favori, partage et conditions d'un point public", async () => {
  assert.match(texte(panneau()), /Lune/);
  assert.match(texte(panneau()), /Urgence en mer : 196/);
  assert.ok(panneau().querySelector('a[href="tel:196"]'), "appel du 196 en un geste");
  panneau().querySelector("#favori").click();
  assert.deepEqual(JSON.parse(w.localStorage.getItem("kelvisi-favoris")), ["ref-quiberon"]);
  assert.match(panneau().querySelector("#favori").textContent, /Dans mes favoris/);
  panneau().querySelector("#partager").click();
  await jusqua(() => !panneau().querySelector("#message-partage").hidden, "message de partage");
  assert.match(copies.at(-1), /Quiberon, côte sauvage : .* m de visibilité prévue .*#\/spot\/ref-quiberon$/);
});

await etape("retour terrain sur un point public (partage désactivé)", async () => {
  const curseur = panneau().querySelector("#retour-visi");
  curseur.value = "6.5";
  curseur.dispatchEvent(new w.Event("input"));
  panneau().querySelector("#form-retour").dispatchEvent(new w.Event("submit", { cancelable: true }));
  await jusqua(() => !panneau().querySelector("#retour-ok").hidden, "confirmation");
  assert.match(panneau().querySelector("#retour-ok").textContent, /gardé sur ton appareil/);
  const retours = JSON.parse(w.localStorage.getItem("kelvisi-retours"));
  assert.equal(retours.length, 1);
  assert.equal(retours[0].visibilite_m, 6.5);
  assert.ok(retours[0].prevision_m > 0, "prévision du moment jointe au retour");
});

await etape("retour partagé quand le serveur de retours est configuré", async () => {
  const { CONFIG } = await import(pathToFileURL(join(APP, "js", "config.js")).href);
  CONFIG.supabaseUrl = "https://supabase.test";
  CONFIG.supabaseCleAnon = "cle-publique";
  await aller("#/spot/ref-penmarch");
  await jusqua(() => /Penmarc'h/.test(texte(panneau())) && panneau().querySelector("#form-retour"), "fiche");
  assert.match(texte(panneau()), /partagé de façon anonyme/);
  panneau().querySelector("#retour-quand").value = "hier";
  panneau().querySelector("#form-retour").dispatchEvent(new w.Event("submit", { cancelable: true }));
  await jusqua(() => !panneau().querySelector("#retour-ok").hidden, "confirmation");
  assert.match(panneau().querySelector("#retour-ok").textContent, /aide à corriger/);
  assert.equal(envois.length, 1);
  const e = envois[0];
  assert.equal(e.spot_id, "ref-penmarch");
  assert.equal(e.visibilite_m, 5);
  assert.ok(e.appareil && e.appareil.length >= 8, "identifiant d'appareil");
  // « Hier après-midi » : la veille à 15 h (heure de Paris), quelle que soit l'heure du test
  const observe = new Date(e.observe_le);
  const jourParis = (d) => d.toLocaleDateString("fr-CA", { timeZone: "Europe/Paris" });
  const heureParis = observe.toLocaleTimeString("fr-FR", { timeZone: "Europe/Paris", hour: "2-digit" });
  const veille = jourParis(new Date(Date.now() - 86400 * 1000));
  assert.ok(
    (jourParis(observe) === veille && /^15/.test(heureParis)) || Math.abs(Date.now() - observe - 86400 * 1000) < 3600 * 1000,
    `retour daté d'hier après-midi (${e.observe_le})`,
  );
  CONFIG.supabaseUrl = "";
  CONFIG.supabaseCleAnon = "";
});

await etape("clic en mer puis prévision d'un lieu libre", async () => {
  await aller(grand ? "#/liste" : "#/carte");
  carte.emettre("click", { lngLat: { lng: -3.2, lat: 47.49 }, point: { x: 1, y: 1 } });
  await attendre();
  if (!grand) {
    assert.ok(!d.getElementById("fiche-rapide").hidden, "fiche rapide");
    d.querySelector("#fiche-rapide [data-aller^='#/point/']").click();
    await attendre();
  }
  await jusqua(() => panneau().querySelector(".lecture"), "fiche du lieu", 5000);
  assert.match(texte(panneau()), /Réglages du lieu/);
  assert.ok(appels.some((u) => u.includes("marine-api.open-meteo.com") && u.includes("latitude=47.49")), "coordonnées arrondies envoyées");
  const ouest = panneau().querySelector('#regl-orientation button[aria-pressed="true"]');
  assert.equal(ouest.textContent, "O", "orientation estimée vers l'ouest");
  assert.match(texte(panneau()), /Pluie\s*[\d,]+ mm\s*tombés ces dernières 48 h/);
  assert.match(texte(panneau()), /Lune/);
  assert.ok(panneau().querySelector("#partager"), "lieu libre partageable");
  assert.ok(!panneau().querySelector("#favori"), "pas de favori pour un lieu libre");
});

await etape("réglage puis enregistrement du lieu comme spot privé", async () => {
  panneau().querySelector('#regl-fond button[data-v="sable"]').click();
  await jusqua(() => panneau().querySelector('#regl-fond button[data-v="sable"][aria-pressed="true"]'), "fond sable");
  panneau().querySelector("#regl-nom").value = "Ma crique";
  panneau().querySelector("#regl-enregistrer").click();
  await jusqua(() => /#\/prive\//.test(w.location.hash) && /Ma crique/.test(texte(panneau())) && panneau().querySelector(".lecture"), "fiche du spot privé", 5000);
  assert.match(texte(panneau()), /Ma crique/);
  const spots = JSON.parse(w.localStorage.getItem("kelvisi-spots"));
  assert.equal(spots.length, 1);
  assert.equal(spots[0].fond, "sable");
});

await etape("retour sur un spot privé : il corrige la prévision", async () => {
  const curseur = panneau().querySelector("#retour-visi");
  curseur.value = "12";
  panneau().querySelector("#form-retour").dispatchEvent(new w.Event("submit", { cancelable: true }));
  await jusqua(() => /corrige la prévision/.test(panneau().querySelector("#retour-ok")?.textContent || ""), "confirmation");
  await jusqua(() => /corrigée/.test(texte(panneau())), "mention de la correction", 5000);
});

await etape("mes spots, copie et import", async () => {
  await aller("#/mes-spots");
  await jusqua(() => panneau().querySelectorAll('.ligne-spot[href^="#/prive/"]').length === 1, "liste des spots");
  assert.equal(panneau().querySelectorAll("#liste-favoris .ligne-spot").length, 1, "favori listé");
  assert.match(texte(panneau().querySelector("#liste-favoris")), /Quiberon/);
  panneau().querySelector("#exporter").click();
  await attendre();
  assert.match(panneau().querySelector("#message-spots").textContent, /2 spots copiés/);
  assert.deepEqual(JSON.parse(copies.at(-1)).favoris, ["ref-quiberon"]);
  const autre = { kelvisi: 1, spots: [{ id: "prive-test", nom: "Autre", lat: 43.2, lon: 5.4, orientation_deg: 180, ouverture_deg: 90, profondeur_m: 10, fond: "roche" }] };
  panneau().querySelector("#import-texte").value = JSON.stringify(autre);
  panneau().querySelector("#importer").click();
  await attendre();
  assert.equal(JSON.parse(w.localStorage.getItem("kelvisi-spots")).length, 2);
  assert.ok(d.querySelectorAll(".repere.prive").length === 2, "spots privés sur la carte");
  panneau().querySelector("#import-texte").value = JSON.stringify({ kelvisi: 1, spots: [], favoris: ["ref-groix"] });
  panneau().querySelector("#importer").click();
  await attendre();
  assert.deepEqual(JSON.parse(w.localStorage.getItem("kelvisi-favoris")), ["ref-quiberon", "ref-groix"]);
});

await etape("suppression d'un spot privé avec confirmation", async () => {
  await aller("#/prive/prive-test");
  await jusqua(() => panneau().querySelector("#prive-supprimer"), "fiche");
  panneau().querySelector("#prive-supprimer").click();
  assert.ok(!panneau().querySelector("#prive-confirmer").hidden);
  panneau().querySelector("#prive-oui").click();
  await jusqua(() => w.location.hash === "#/mes-spots", "retour à mes spots");
  assert.equal(JSON.parse(w.localStorage.getItem("kelvisi-spots")).length, 1);
});

await etape("recherche d'un lieu", async () => {
  const champ = d.getElementById("recherche-texte");
  champ.value = "quiberon";
  champ.dispatchEvent(new w.Event("input"));
  await jusqua(() => d.querySelectorAll("#recherche-resultats button").length === 2, "résultats", 3000);
  d.querySelector("#recherche-resultats button").click();
  await attendre();
  assert.ok(!d.getElementById("fiche-rapide").hidden, "fiche du lieu");
  assert.match(texte(d.getElementById("fiche-rapide")), /Points Kelvisi les plus proches/);
  assert.deepEqual(carte.centre.map((x) => Math.round(x * 10) / 10), [-3.1, 47.5]);
});

await etape("couches de la carte", async () => {
  d.querySelector('#fond-carte [data-fond="aerien"]').click();
  d.querySelector("#fond-carte [data-profondeurs]").click();
  carte.emettre("style.load");
  assert.equal(carte.couches["couche-aerien"].visibilite, "visible");
  assert.equal(carte.couches["couche-profondeurs"].visibilite, "visible");
  assert.ok(!d.getElementById("legende-profondeurs").hidden);
});

await etape("pages d'information", async () => {
  for (const page of ["comment", "securite", "sources", "confidentialite", "cgu", "mentions", "avis"]) {
    await aller(`#/infos/${page}`);
    assert.ok(panneau().querySelector(".page-infos h1"), page);
  }
  assert.match(texte(panneau()), /adresse de contact à compléter/);
});

await etape("unité du vent", async () => {
  await aller("#/infos");
  panneau().querySelector('#unite-vent button[data-unite="kmh"]').click();
  await aller("#/spot/ref-quiberon");
  await jusqua(() => panneau().querySelector(".lecture"), "fiche");
  assert.match(texte(panneau().querySelector(".conditions")), /\d+ km\/h/);
  assert.doesNotMatch(texte(panneau().querySelector(".conditions")), /Vent\s*\d+ nœud/);
  w.localStorage.removeItem("kelvisi-unite-vent");
});

await etape("aucune erreur JavaScript", async () => {
  assert.deepEqual(erreurs, []);
});

console.log(`Interface (${grand ? "grand écran" : "téléphone"})\n${etapes.join("\n")}`);
process.exit(process.exitCode || 0);
