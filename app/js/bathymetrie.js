// Profondeurs précises du Shom, lues sur les images de son service cartographique (licence ouverte).
//
// Le Shom publie ses modèles de fond (relevés laser Litto3D au mètre, modèles côtiers à 20 m,
// modèles de façade à 100 m) sous forme d'images colorées : chaque couleur correspond à une
// profondeur selon une palette publiée. On demande une toute petite image autour du point,
// puis on retrouve la profondeur à partir de la couleur. Vérifié sur des centaines de points
// contre EMODnet : écart de l'ordre du mètre sur les modèles à 20 et 100 m.

const WMS = "https://services.data.shom.fr/INSPIRE/wms/r";

// Palettes des légendes du Shom : (profondeur en m, positive sous l'eau ; négative = altitude à terre, couleur)
const PALETTES = {
  facade: { ombre: false, arrets: [[-50, [239, 236, 231]], [-20, [221, 220, 200]], [0, [169, 170, 128]], [15, [155, 46, 30]], [30, [248, 214, 22]], [40, [0, 128, 64]], [100, [97, 224, 224]], [125, [49, 208, 242]], [150, [3, 151, 222]], [1000, [14, 112, 192]], [3000, [9, 63, 206]]] },
  cotier: { ombre: false, arrets: [[-100, [213, 163, 117]], [-75, [202, 132, 115]], [-40, [159, 62, 62]], [-20, [248, 214, 22]], [-10, [0, 128, 64]], [-5, [98, 157, 108]], [0, [128, 255, 255]], [5, [131, 224, 252]], [10, [106, 181, 255]], [20, [0, 128, 255]], [40, [62, 62, 255]], [50, [0, 0, 176]], [85, [23, 5, 122]]] },
  litto_atl: { ombre: true, arrets: [[-250, [81, 40, 0]], [-25, [217, 108, 0]], [-20, [0, 128, 64]], [-10, [0, 255, 0]], [-5, [255, 255, 128]], [-0.5, [192, 192, 192]], [-0.1, [120, 120, 120]], [4.8, [128, 255, 255]], [5, [0, 255, 255]], [10, [0, 235, 232]], [15, [0, 128, 255]], [25, [0, 0, 223]]] },
  litto_med: { ombre: true, arrets: [[-250, [84, 43, 4]], [-25, [216, 109, 4]], [-20, [4, 130, 67]], [-10, [4, 255, 4]], [-5, [255, 255, 130]], [-0.5, [193, 193, 193]], [0, [122, 122, 122]], [2, [4, 255, 255]], [5, [4, 232, 232]], [20, [4, 130, 255]], [30, [4, 4, 224]]] },
};

// Du plus précis au moins précis. zone : [ouest, sud, est, nord]. reference : « moyen » (niveau moyen
// de la mer, Litto3D) ou « pbma » (plus basses mers astronomiques, zéro des cartes marines).
export const SOURCES = [
  { couche: "LITTO3D_FINISTR_2014_PYR_3857_WMSR", nom: "Litto3D Finistère", type: "laser", palette: "litto_atl", zone: [-5.312, 47.581, -3.067, 48.779], pas: 2, reference: "moyen", max: 25 },
  { couche: "LITTO3D_BZH_2018_2021_PYR_3857_WMSR", nom: "Litto3D Bretagne", type: "laser", palette: "litto_atl", zone: [-3.869, 47.236, -1.373, 49.007], pas: 2, reference: "moyen", max: 25 },
  { couche: "LITTO3D_NAQ_2020_2022_PYR_3857_WMSR", nom: "Litto3D Nouvelle-Aquitaine", type: "laser", palette: "litto_atl", zone: [-1.802, 43.291, -0.825, 46.343], pas: 2, reference: "moyen", max: 25 },
  { couche: "LITTO3D_LR_2009_PYR_3857_WMSR", nom: "Litto3D Languedoc-Roussillon", type: "laser", palette: "litto_med", zone: [2.902, 42.423, 4.527, 43.762], pas: 2, reference: "moyen", max: 30 },
  { couche: "LITTO3D_PACA_2015_PYR_3857_WMSR", nom: "Litto3D Provence-Alpes-Côte d'Azur", type: "laser", palette: "litto_med", zone: [4.347, 42.975, 7.538, 43.859], pas: 2, reference: "moyen", max: 30 },
  { couche: "MNT_COTIER_ILE_DE_RE_5m_PBMA_3857_WMSR", nom: "MNT côtier de l'île de Ré", type: "cotier", palette: "cotier", zone: [-1.723, 46.125, -1.445, 46.318], pas: 5, reference: "pbma", max: 85 },
  { couche: "MNT_COTIER_MORBIHAN_TANDEM_20m_PBMA_3857_WMSR", nom: "MNT côtier du Morbihan", type: "cotier", palette: "cotier", zone: [-3.333, 47.2, -2.367, 47.725], pas: 20, reference: "pbma", max: 85 },
  { couche: "MNT_COTIER_GNB_PAPI_SM_20m_PBMA_4326_WMSR", nom: "MNT côtier du golfe normand-breton", type: "cotier", palette: "cotier", zone: [-2.15, 48.55, -1.3, 48.95], pas: 20, reference: "pbma", max: 85 },
  { couche: "MNT_COTIER_PERTUIS_HOMONIM_20m_PBMA_3857_WMSR", nom: "MNT côtier des Pertuis charentais", type: "cotier", palette: "cotier", zone: [-1.704, 45.746, -0.942, 46.454], pas: 20, reference: "pbma", max: 85 },
  { couche: "MNT_COTIER_GIRONDE_AVAL_20m_PBMA_3857_WMSR", nom: "MNT côtier de l'estuaire de la Gironde", type: "cotier", palette: "cotier", zone: [-1.509, 45.183, -0.649, 45.76], pas: 20, reference: "pbma", max: 85 },
  { couche: "MNT_COTIER_ARCACHON_HOMONIM_20m_PBMA_3857_WMSR", nom: "MNT côtier d'Arcachon", type: "cotier", palette: "cotier", zone: [-1.41, 44.43, -0.95, 45.19], pas: 20, reference: "pbma", max: 85 },
  { couche: "MNT_COTIER_DETROIT_PDC_20m_PBMA_WMSR_3857", nom: "MNT côtier du Pas-de-Calais", type: "cotier", palette: "cotier", zone: [0.834, 50.5, 2.544, 51.334], pas: 20, reference: "pbma", max: 85 },
  { couche: "MNT_ATL100m_HOMONIM_PBMA_3857_WMSR", nom: "MNT de façade Manche-Atlantique", type: "facade", palette: "facade", zone: [-6.0, 43.249, 5.851, 52.901], pas: 100, reference: "pbma", max: 3000 },
  { couche: "MNT_MED100m_GDL_CA_HOMONIM_PBMA_3857_WMSR", nom: "MNT de façade golfe du Lion - Côte d'Azur", type: "facade", palette: "facade", zone: [2.9, 41.7, 7.901, 44.401], pas: 100, reference: "pbma", max: 3000 },
  { couche: "MNT_MED100m_CORSE_HOMONIM_PBMA_3857_WMSR", nom: "MNT de façade de la Corse", type: "facade", palette: "facade", zone: [7.699, 40.7, 10.4, 43.7], pas: 100, reference: "pbma", max: 3000 },
];

// Couches affichées sur la carte « Profondeurs » au-dessus d'EMODnet, de la moins à la plus précise
export const COUCHES_CARTE = SOURCES.filter((s) => s.type !== "facade").map((s) => s.couche).reverse();

export function urlTuilesShom() {
  return `${WMS}?SERVICE=WMS&VERSION=1.3.0&REQUEST=GetMap&LAYERS=${COUCHES_CARTE.join(",")}&STYLES=&CRS=EPSG:3857`
    + "&BBOX={bbox-epsg-3857}&WIDTH=256&HEIGHT=256&FORMAT=image/png&TRANSPARENT=true";
}

const dans = (z, lat, lon) => lon >= z[0] && lon <= z[2] && lat >= z[1] && lat <= z[3];

// --- Couleur vers profondeur ------------------------------------------------------------------------

const tables = new Map();
function table(nom) {
  if (tables.has(nom)) return tables.get(nom);
  const { arrets, ombre } = PALETTES[nom];
  const prof = [], coul = [];
  for (let k = 0; k < arrets.length - 1; k++) {
    const [d0, c0] = arrets[k], [d1, c1] = arrets[k + 1];
    const n = 40;
    for (let i = 0; i < n; i++) {
      const t = i / n;
      prof.push(d0 + (d1 - d0) * t);
      coul.push([0, 1, 2].map((j) => c0[j] * (1 - t) + c1[j] * t));
    }
  }
  const [dn, cn] = arrets[arrets.length - 1];
  prof.push(dn);
  coul.push(cn.slice());
  // Palettes ombrées (relief éclairé) : on compare les teintes, pas la luminosité
  const norm = coul.map((c) => {
    const l = Math.hypot(...c) || 1;
    return c.map((x) => x / l);
  });
  const t = { prof, coul, norm, ombre };
  tables.set(nom, t);
  return t;
}

// Profondeur (m) et écart de couleur pour un pixel [r, g, b]
export function decoderCouleur(rgb, nomPalette) {
  const t = table(nomPalette);
  let meilleur = Infinity, iMeilleur = 0;
  if (t.ombre) {
    const l = Math.hypot(...rgb) || 1;
    const p = rgb.map((x) => x / l);
    for (let i = 0; i < t.norm.length; i++) {
      const n = t.norm[i];
      const e = 1 - (p[0] * n[0] + p[1] * n[1] + p[2] * n[2]);
      if (e < meilleur) { meilleur = e; iMeilleur = i; }
    }
    return { profondeur: t.prof[iMeilleur], ecart: meilleur * 1000 };
  }
  for (let i = 0; i < t.coul.length; i++) {
    const c = t.coul[i];
    const e = Math.hypot(rgb[0] - c[0], rgb[1] - c[1], rgb[2] - c[2]);
    if (e < meilleur) { meilleur = e; iMeilleur = i; }
  }
  return { profondeur: t.prof[iMeilleur], ecart: meilleur };
}

// --- Lecture des images ---------------------------------------------------------------------------

// Renvoie { largeur, hauteur, pixels (RGBA) } ; remplaçable pour les tests
let lecteur = async (url, signal) => {
  const r = await fetch(url, { signal });
  if (!r.ok) throw new Error(`Image Shom indisponible (${r.status})`);
  const image = await createImageBitmap(await r.blob());
  const toile = typeof OffscreenCanvas !== "undefined" ? new OffscreenCanvas(image.width, image.height) : Object.assign(document.createElement("canvas"), { width: image.width, height: image.height });
  const ctx = toile.getContext("2d", { willReadFrequently: true });
  ctx.drawImage(image, 0, 0);
  return { largeur: image.width, hauteur: image.height, pixels: ctx.getImageData(0, 0, image.width, image.height).data };
};

export function definirLecteurImage(f) {
  lecteur = f;
}

function urlImage(couche, lat, lon, demiCoteM, taille) {
  const dLat = demiCoteM / 111320;
  const dLon = demiCoteM / (111320 * Math.cos((lat * Math.PI) / 180));
  // WMS 1.3.0 en EPSG:4326 : emprise dans l'ordre latitude, longitude
  const bbox = [lat - dLat, lon - dLon, lat + dLat, lon + dLon].map((x) => x.toFixed(6)).join(",");
  return `${WMS}?SERVICE=WMS&VERSION=1.3.0&REQUEST=GetMap&LAYERS=${couche}&STYLES=&CRS=EPSG:4326&BBOX=${bbox}&WIDTH=${taille}&HEIGHT=${taille}&FORMAT=image/png&TRANSPARENT=true`;
}

function mediane(v) {
  const s = [...v].sort((a, b) => a - b);
  const m = Math.floor(s.length / 2);
  return s.length % 2 ? s[m] : (s[m - 1] + s[m]) / 2;
}

// Lit une source autour du point : profondeur médiane des pixels centraux, ou null si pas de donnée
async function lireSource(source, lat, lon, signal) {
  const taille = 7;
  const img = await lecteur(urlImage(source.couche, lat, lon, (source.pas * taille) / 2, taille), signal);
  const c = Math.floor(img.largeur / 2), r = Math.floor(img.hauteur / 2);
  const valeurs = [];
  const seuil = PALETTES[source.palette].ombre ? 25 : 30;
  for (let y = r - 1; y <= r + 1; y++) {
    for (let x = c - 1; x <= c + 1; x++) {
      const i = (y * img.largeur + x) * 4;
      const p = img.pixels;
      if (p[i + 3] < 200) continue;
      const { profondeur, ecart } = decoderCouleur([p[i], p[i + 1], p[i + 2]], source.palette);
      if (ecart <= seuil) valeurs.push(profondeur);
    }
  }
  if (valeurs.length < 3) return null;
  return mediane(valeurs);
}

const memoire = new Map();

// Profondeur au point selon chaque source disponible, de la plus précise à la moins précise
// (au plus une par type : laser, côtier, façade). Chaque mesure :
// { profondeur_m, terre, au_moins, source, type, precision_m, reference }.
export async function profondeursAuPoint(lat, lon, { signal } = {}) {
  const cle = `${lat.toFixed(5)},${lon.toFixed(5)}`;
  if (memoire.has(cle)) return memoire.get(cle);
  const choisies = [];
  const types = new Set();
  for (const s of SOURCES) {
    if (types.has(s.type) || !dans(s.zone, lat, lon)) continue;
    types.add(s.type);
    choisies.push(s);
  }
  const lectures = await Promise.all(choisies.map(async (s) => {
    try {
      return { s, p: await lireSource(s, lat, lon, signal) };
    } catch (e) {
      if (e.name === "AbortError") throw e;
      return { s, p: null };
    }
  }));
  const mesures = lectures.filter((l) => l.p !== null).map(({ s, p }) => ({
    source: s.nom, type: s.type, precision_m: s.pas, reference: s.reference,
    terre: p <= 0,
    au_moins: p > 0 && p >= s.max - 0.5,
    profondeur_m: p <= 0 ? null : p >= s.max - 0.5 ? s.max : Math.round(p * 2) / 2,
  }));
  memoire.set(cle, mesures);
  return mesures;
}

// La mesure la plus précise qui donne une valeur exploitable (un relevé laser saturé cède la place)
export function meilleureMesure(mesures) {
  if (!mesures || !mesures.length) return null;
  return mesures.find((m) => m.terre || !m.au_moins) || mesures[0];
}

export async function profondeurPrecise(lat, lon, options) {
  return meilleureMesure(await profondeursAuPoint(lat, lon, options));
}

// Couleur de la palette pour une profondeur donnée (sert aux tests)
export function couleurPour(profondeur, nomPalette) {
  const t = table(nomPalette);
  let i = 0;
  while (i < t.prof.length - 1 && t.prof[i + 1] <= profondeur) i++;
  return t.coul[i].map(Math.round);
}

// Direction du large et ouverture du lieu, d'après la grille de profondeurs autour du point
export function orientationDepuisGrille({ grille, rayonM, taille }) {
  const c = (taille - 1) / 2;
  const pas = (2 * rayonM) / taille;
  let sx = 0, sy = 0, ouverts = 0;
  for (let az = 0; az < 360; az += 22.5) {
    const r = (az * Math.PI) / 180;
    const valeurs = [];
    let terre = false;
    for (let d = 250; d <= Math.min(2400, rayonM - pas); d += 250) {
      const x = Math.round(c + (Math.sin(r) * d) / pas);
      const y = Math.round(c - (Math.cos(r) * d) / pas);
      const v = grille[y]?.[x];
      if (v === null || v === undefined) continue;
      if (v === 0) {
        if (d <= 1500) terre = true;
        break;
      }
      valeurs.push(v);
    }
    if (terre || valeurs.length < 3) continue;
    const moyenne = valeurs.reduce((a, b) => a + b, 0) / valeurs.length;
    sx += Math.sin(r) * moyenne;
    sy += Math.cos(r) * moyenne;
    ouverts++;
  }
  if (!ouverts) return null;
  return {
    orientation_deg: Math.round(((Math.atan2(sx, sy) * 180) / Math.PI + 360) % 360),
    ouverture_deg: Math.max(45, Math.min(180, ouverts * 22.5)),
  };
}

// Carte des profondeurs (modèle de façade à 100 m) autour d'un point : grille de profondeurs,
// null à terre ou sans donnée. Sert à trouver la direction du large et l'abri du lieu.
export async function grilleAutour(lat, lon, { rayonM = 2500, taille = 51, signal } = {}) {
  const source = SOURCES.find((s) => s.type === "facade" && dans(s.zone, lat, lon));
  if (!source) return null;
  const img = await lecteur(urlImage(source.couche, lat, lon, rayonM, taille), signal);
  const grille = [];
  for (let y = 0; y < img.hauteur; y++) {
    const ligne = [];
    for (let x = 0; x < img.largeur; x++) {
      const i = (y * img.largeur + x) * 4;
      const p = img.pixels;
      if (p[i + 3] < 200) { ligne.push(null); continue; }
      const { profondeur, ecart } = decoderCouleur([p[i], p[i + 1], p[i + 2]], source.palette);
      ligne.push(ecart <= 30 && profondeur > 0 ? profondeur : (ecart <= 30 ? 0 : null));
    }
    grille.push(ligne);
  }
  return { grille, rayonM, taille: img.largeur };
}
