// Relief sous-marin de la carte « Profondeurs ».
//
// Les cartes du Shom (relevés laser Litto3D, modèles côtiers à 5-20 m, modèles de façade à 100 m)
// sont relues pixel par pixel (couleur -> profondeur), puis redessinées : une teinte par tranche de
// profondeur, un trait à chaque isobathe (tous les 5 m jusqu'à 20 m, puis 30, 50, 100 m...) et un
// éclairage du relief venant du nord-ouest. Un tombant apparaît comme des traits serrés et une
// ombre marquée, un banc comme une tache claire au milieu d'une teinte plus foncée.
//
// Le relevé laser est déjà éclairé par le Shom : on garde son éclairage (rapport entre la couleur
// reçue et la couleur de la palette). Pour les modèles à 20 et 100 m, l'éclairage est calculé ici
// sur une surface lissée (B-spline cubique), sans marches d'escalier.
//
// Ce module ne touche pas au DOM : il sert aussi bien dans un Worker que dans la page.

import { SOURCES, WMS_SHOM, croise, tablePalette } from "./bathymetrie.js";

// Tranches de profondeur (m) et leur teinte, de la plus claire (0 à 2 m) à la plus foncée (> 500 m)
export const SEUILS = [2, 5, 10, 15, 20, 25, 30, 40, 50, 75, 100, 200, 500];
export const COULEURS = [
  [198, 236, 228], [174, 226, 223], [150, 214, 219], [120, 199, 214], [92, 180, 206], [72, 160, 196],
  [59, 141, 186], [50, 121, 173], [43, 102, 158], [37, 85, 142], [32, 69, 125], [27, 55, 108],
  [22, 42, 90], [17, 31, 72],
];
// Isobathes tracées, et celles tracées plus foncé
export const ISOBATHES = [5, 10, 15, 20, 30, 50, 100, 200, 500];
export const ISOBATHES_MAJEURES = [10, 20, 30, 50, 100];
const ENCRE = [14, 36, 66];
const OPACITE_TRAIT = 0.42;
const OPACITE_TRAIT_MAJEUR = 0.72;

// Éclairage : soleil au nord-ouest, 45° au-dessus de l'horizon, relief exagéré pour les modèles lissés
const AZIMUT = 315;
const HAUTEUR = 45;
const EXAGERATION = 6;
const OMBRE_MIN = 0.45;
const OMBRE_MAX = 1.45;
// Luminosité moyenne des relevés laser du Shom par rapport à leur palette (mesurée sur Bretagne,
// Pays basque, Languedoc et Provence : 0,70 à 0,82)
const LUMIERE_LASER = 0.75;

// Taille d'un pixel au sol (m) en dessous de laquelle chaque source est demandée
export const PIXEL_MAX_LASER_M = 15;
export const PIXEL_MAX_COTIER_M = 40;

const R = 6378137;
const MONDE = 2 * Math.PI * R;
const versLon = (mx) => (mx / R) * (180 / Math.PI);
const versLat = (my) => (2 * Math.atan(Math.exp(my / R)) - Math.PI / 2) * (180 / Math.PI);

// Emprise d'une tuile en mètres Mercator : [ouest, sud, est, nord]
export function empriseTuile(z, x, y) {
  const t = MONDE / 2 ** z;
  const ouest = -MONDE / 2 + x * t;
  const nord = MONDE / 2 - y * t;
  return [ouest, nord - t, ouest + t, nord];
}

function urlWms(couche, emprise, n) {
  let crs, bbox;
  if (couche.includes("_4326_")) {
    // Couche en coordonnées géographiques (WMS 1.3.0 : latitude d'abord). À l'échelle d'une tuile,
    // l'écart avec la projection Mercator est inférieur au pixel.
    crs = "EPSG:4326";
    bbox = [versLat(emprise[1]), versLon(emprise[0]), versLat(emprise[3]), versLon(emprise[2])].map((v) => v.toFixed(7));
  } else {
    crs = "EPSG:3857";
    bbox = emprise.map((v) => v.toFixed(2));
  }
  return `${WMS_SHOM}?SERVICE=WMS&VERSION=1.3.0&REQUEST=GetMap&LAYERS=${couche}&STYLES=&CRS=${crs}`
    + `&BBOX=${bbox.join(",")}&WIDTH=${n}&HEIGHT=${n}&FORMAT=image/png&TRANSPARENT=true`;
}

// Images du Shom à demander pour une tuile : chaque source à une résolution proche de la sienne
// (inutile de demander 512 pixels d'un modèle à 100 m), avec une marge pour lisser sans couture.
export function planTuile(z, x, y, taille = 512) {
  const marge = 2;
  const e = empriseTuile(z, x, y);
  const etendue = e[2] - e[0];
  const pas = etendue / taille;
  const geo = [versLon(e[0]), versLat(e[1]), versLon(e[2]), versLat(e[3])];
  const cosLat = Math.cos((((geo[1] + geo[3]) / 2) * Math.PI) / 180);
  const pasSol = pas * cosLat;
  const sortie = [e[0] - marge * pas, e[1] - marge * pas, e[2] + marge * pas, e[3] + marge * pas];
  const demandes = [];
  for (const s of SOURCES) {
    if (!croise(s, geo)) continue;
    if (s.type === "laser" && pasSol > PIXEL_MAX_LASER_M) continue;
    if (s.type === "cotier" && pasSol > PIXEL_MAX_COTIER_M) continue;
    let emprise, n;
    if (s.type === "laser") {
      emprise = sortie;
      n = taille + 2 * marge;
    } else {
      const cible = Math.max(pas, s.pas / cosLat / 1.5);
      const coeur = Math.max(4, Math.min(taille, Math.ceil(etendue / cible)));
      const p = etendue / coeur;
      emprise = [e[0] - 3 * p, e[1] - 3 * p, e[2] + 3 * p, e[3] + 3 * p];
      n = coeur + 6;
    }
    demandes.push({ couche: s.couche, type: s.type, palette: s.palette, max: s.max, emprise, largeur: n, hauteur: n, url: urlWms(s.couche, emprise, n) });
  }
  return { z, x, y, taille, marge, pasSol, sortie, demandes };
}

// --- Couleur -> profondeur ----------------------------------------------------------------------

const tablesRapides = new Map();
function tableRapide(nom) {
  if (tablesRapides.has(nom)) return tablesRapides.get(nom);
  const t = tablePalette(nom);
  const n = t.prof.length;
  const r = { ombre: t.ombre, n, prof: Float32Array.from(t.prof), coul: new Float32Array(3 * n), norm: new Float32Array(3 * n), norme: new Float32Array(n), cache: new Map() };
  for (let i = 0; i < n; i++) {
    const c = t.coul[i];
    const l = Math.hypot(c[0], c[1], c[2]) || 1;
    for (let j = 0; j < 3; j++) {
      r.coul[3 * i + j] = c[j];
      r.norm[3 * i + j] = c[j] / l;
    }
    r.norme[i] = l;
  }
  tablesRapides.set(nom, r);
  return r;
}

// Indice de la couleur de palette la plus proche, ou -1 si la couleur n'appartient pas à la palette
function chercher(t, r, g, b) {
  let meilleur = Infinity, k = -1;
  if (t.ombre) {
    // Relief éclairé : on compare les teintes, pas la luminosité
    const l = Math.hypot(r, g, b) || 1;
    const pr = r / l, pg = g / l, pb = b / l;
    for (let i = 0; i < t.n; i++) {
      const e = 1 - (pr * t.norm[3 * i] + pg * t.norm[3 * i + 1] + pb * t.norm[3 * i + 2]);
      if (e < meilleur) { meilleur = e; k = i; }
    }
    return meilleur * 1000 <= 25 ? k : -1;
  }
  for (let i = 0; i < t.n; i++) {
    const dr = r - t.coul[3 * i], dg = g - t.coul[3 * i + 1], db = b - t.coul[3 * i + 2];
    const e = dr * dr + dg * dg + db * db;
    if (e < meilleur) { meilleur = e; k = i; }
  }
  return meilleur <= 900 ? k : -1;
}

// Pixels RGBA d'une image du Shom -> profondeur (m, négative à terre, NaN sans donnée) et, pour
// les relevés éclairés, luminosité relative du pixel
export function decoderPixels(pixels, largeur, hauteur, nomPalette) {
  const t = tableRapide(nomPalette);
  if (t.cache.size > 300000) t.cache.clear();
  const n = largeur * hauteur;
  const prof = new Float32Array(n);
  const lum = t.ombre ? new Float32Array(n) : null;
  for (let i = 0; i < n; i++) {
    const o = 4 * i;
    if (pixels[o + 3] < 200) {
      prof[i] = NaN;
      if (lum) lum[i] = NaN;
      continue;
    }
    const r = pixels[o], g = pixels[o + 1], b = pixels[o + 2];
    const cle = (r << 16) | (g << 8) | b;
    let k = t.cache.get(cle);
    if (k === undefined) {
      k = chercher(t, r, g, b);
      t.cache.set(cle, k);
    }
    if (k < 0) {
      prof[i] = NaN;
      if (lum) lum[i] = NaN;
      continue;
    }
    prof[i] = t.prof[k];
    if (lum) lum[i] = Math.hypot(r, g, b) / t.norme[k];
  }
  return { prof, lum, largeur, hauteur };
}

// --- Rééchantillonnage ----------------------------------------------------------------------------

// Poids et indices d'une B-spline cubique (lissante) le long d'un axe : pour chaque pixel de sortie,
// les 4 pixels source voisins.
function axeBSpline(nSortie, positionSource, nSource) {
  const idx = new Int32Array(4 * nSortie);
  const w = new Float32Array(4 * nSortie);
  for (let j = 0; j < nSortie; j++) {
    const u = positionSource(j);
    const x0 = Math.floor(u);
    const t = u - x0, t2 = t * t, t3 = t2 * t;
    const p = [(1 - t) ** 3 / 6, (3 * t3 - 6 * t2 + 4) / 6, (-3 * t3 + 3 * t2 + 3 * t + 1) / 6, t3 / 6];
    for (let k = 0; k < 4; k++) {
      idx[4 * j + k] = Math.min(nSource - 1, Math.max(0, x0 - 1 + k));
      w[4 * j + k] = p[k];
    }
  }
  return { idx, w };
}

function reechantillonner(grille, l, h, ax, ay, G) {
  const tmp = new Float32Array(h * G);
  for (let r = 0; r < h; r++) {
    const ligne = r * l;
    for (let j = 0; j < G; j++) {
      const q = 4 * j;
      tmp[r * G + j] = ax.w[q] * grille[ligne + ax.idx[q]] + ax.w[q + 1] * grille[ligne + ax.idx[q + 1]]
        + ax.w[q + 2] * grille[ligne + ax.idx[q + 2]] + ax.w[q + 3] * grille[ligne + ax.idx[q + 3]];
    }
  }
  const sortie = new Float32Array(G * G);
  for (let i = 0; i < G; i++) {
    const q = 4 * i;
    const a = ay.idx[q] * G, b = ay.idx[q + 1] * G, c = ay.idx[q + 2] * G, d = ay.idx[q + 3] * G;
    const wa = ay.w[q], wb = ay.w[q + 1], wc = ay.w[q + 2], wd = ay.w[q + 3];
    for (let j = 0; j < G; j++) sortie[i * G + j] = wa * tmp[a + j] + wb * tmp[b + j] + wc * tmp[c + j] + wd * tmp[d + j];
  }
  return sortie;
}

// Modèle lissé : profondeur (0 à terre), part de mer (1 mer, 0 terre) et présence de données ;
// les pixels sans donnée reçoivent la valeur du pixel connu le plus proche, pour que le lissage
// ne crée pas de faux fonds au bord des zones couvertes.
function preparer(source) {
  const { prof, largeur: l, hauteur: h } = source;
  const n = l * h;
  const D = new Float32Array(n), M = new Float32Array(n), O = new Float32Array(n);
  const vu = new Uint8Array(n);
  const file = new Int32Array(n);
  let debut = 0, fin = 0;
  for (let i = 0; i < n; i++) {
    const p = prof[i];
    if (p === p) {
      O[i] = 1;
      M[i] = p > 0 ? 1 : 0;
      D[i] = p > 0 ? p : 0;
      vu[i] = 1;
      file[fin++] = i;
    }
  }
  if (!fin) return null;
  const visiter = (k, i) => {
    if (vu[k]) return;
    vu[k] = 1;
    D[k] = D[i];
    M[k] = M[i];
    file[fin++] = k;
  };
  while (debut < fin) {
    const i = file[debut++];
    const x = i % l;
    if (x > 0) visiter(i - 1, i);
    if (x < l - 1) visiter(i + 1, i);
    if (i >= l) visiter(i - l, i);
    if (i + l < n) visiter(i + l, i);
  }
  return { D, M, O };
}

// --- Dessin d'une tuile ---------------------------------------------------------------------------

// sources : du plus précis au moins précis, chacune { type, max, prof, lum, largeur, hauteur, emprise }.
// sortie : emprise (m Mercator) de la grille dessinée, marge comprise. Renvoie les pixels RGBA de la
// tuile, marge retirée.
export function rendreRelief({ taille, marge, pasSol, sortie, sources }) {
  const G = taille + 2 * marge;
  const N = G * G;
  const pas = (sortie[2] - sortie[0]) / G;
  const D = new Float32Array(N).fill(NaN);     // profondeur retenue
  const Dl = new Float32Array(N).fill(NaN);    // profondeur des modèles lissés (pour l'éclairage)
  const S = new Float32Array(N).fill(NaN);     // éclairage du relevé laser
  const A = new Float32Array(N);               // opacité (adoucie le long des côtes des modèles)
  const terre = new Uint8Array(N);
  const pris = new Uint8Array(N);

  for (const src of sources) {
    const { largeur: l, hauteur: h, emprise: em } = src;
    const pasX = (em[2] - em[0]) / l, pasY = (em[3] - em[1]) / h;
    const posX = (j) => (sortie[0] + (j + 0.5) * pas - em[0]) / pasX - 0.5;
    const posY = (i) => (em[3] - (sortie[3] - (i + 0.5) * pas)) / pasY - 0.5;
    const limite = src.max - 0.5;
    if (src.type === "laser") {
      const xs = new Int32Array(G), ys = new Int32Array(G);
      for (let j = 0; j < G; j++) xs[j] = Math.min(l - 1, Math.max(0, Math.round(posX(j))));
      for (let i = 0; i < G; i++) ys[i] = Math.min(h - 1, Math.max(0, Math.round(posY(i))));
      for (let i = 0; i < G; i++) {
        for (let j = 0; j < G; j++) {
          const q = i * G + j;
          if (pris[q]) continue;
          const k = ys[i] * l + xs[j];
          const p = src.prof[k];
          if (!(p === p) || p >= limite) continue;
          pris[q] = 1;
          D[q] = p;
          terre[q] = p <= 0 ? 1 : 0;
          A[q] = 1;
          const lu = src.lum ? src.lum[k] : NaN;
          S[q] = lu === lu ? lu / LUMIERE_LASER : NaN;
        }
      }
      continue;
    }
    const prep = preparer(src);
    if (!prep) continue;
    const ax = axeBSpline(G, posX, l), ay = axeBSpline(G, posY, h);
    const Ds = reechantillonner(prep.D, l, h, ax, ay, G);
    const Ms = reechantillonner(prep.M, l, h, ax, ay, G);
    const Os = reechantillonner(prep.O, l, h, ax, ay, G);
    for (let q = 0; q < N; q++) {
      if (Os[q] < 0.5) continue;
      const d = Ds[q] > 0 ? Ds[q] : 0;
      if (d >= limite) continue;
      if (!(Dl[q] === Dl[q])) Dl[q] = d;
      if (pris[q]) continue;
      pris[q] = 1;
      D[q] = d;
      terre[q] = Ms[q] < 0.5 ? 1 : 0;
      // Côte des modèles à 20-100 m : approximative, on laisse transparaître le fond de carte
      A[q] = Math.min(1, Math.max(0, (Ms[q] - 0.5) / 0.35));
    }
  }

  // Tranche de profondeur de chaque pixel de mer (255 : terre ou sans donnée)
  const bande = new Uint8Array(N).fill(255);
  for (let q = 0; q < N; q++) {
    if (!pris[q] || terre[q]) continue;
    const d = D[q];
    let b = 0;
    while (b < SEUILS.length && d >= SEUILS[b]) b++;
    bande[q] = b;
  }
  // Médiane 3 x 3 des tranches : retire les pixels isolés dus au décodage des couleurs
  const nettoyee = new Uint8Array(bande);
  const compte = new Uint8Array(SEUILS.length + 1);
  for (let i = 1; i < G - 1; i++) {
    for (let j = 1; j < G - 1; j++) {
      const q = i * G + j;
      if (bande[q] === 255) continue;
      compte.fill(0);
      let n = 0;
      for (let di = -1; di <= 1; di++) {
        for (let dj = -1; dj <= 1; dj++) {
          const v = bande[q + di * G + dj];
          if (v !== 255) { compte[v]++; n++; }
        }
      }
      let cumul = 0, b = 0;
      while (b < compte.length && (cumul += compte[b]) * 2 <= n) b++;
      nettoyee[q] = Math.min(b, SEUILS.length);
    }
  }

  // Éclairage des modèles lissés
  const az = (AZIMUT * Math.PI) / 180, ha = (HAUTEUR * Math.PI) / 180;
  const lx = Math.sin(az) * Math.cos(ha), ly = Math.cos(az) * Math.cos(ha), lz = Math.sin(ha);
  const k = EXAGERATION / (2 * pasSol);
  const lignes = new Set(ISOBATHES), majeures = new Set(ISOBATHES_MAJEURES);
  const rgba = new Uint8ClampedArray(taille * taille * 4);
  for (let i = marge; i < marge + taille; i++) {
    for (let j = marge; j < marge + taille; j++) {
      const q = i * G + j;
      const b = nettoyee[q];
      const o = 4 * ((i - marge) * taille + (j - marge));
      if (b === 255) continue;
      let s = S[q];
      if (!(s === s)) {
        const c = Dl[q];
        if (c === c) {
          // altitude = - profondeur ; x vers l'est, y vers le nord (un voisin sans donnée compte comme le pixel)
          let e = Dl[q + 1], w = Dl[q - 1], n = Dl[q - G], su = Dl[q + G];
          if (!(e === e)) e = c;
          if (!(w === w)) w = c;
          if (!(n === n)) n = c;
          if (!(su === su)) su = c;
          const gx = -(e - w) * k;
          const gy = -(n - su) * k;
          s = (-gx * lx - gy * ly + lz) / Math.sqrt(gx * gx + gy * gy + 1) / lz;
        } else {
          s = 1;
        }
      }
      s = Math.min(OMBRE_MAX, Math.max(OMBRE_MIN, s));
      const base = COULEURS[b];
      let r, g, bl;
      if (s < 1) {
        r = base[0] * s; g = base[1] * s; bl = base[2] * s;
      } else {
        // Versant éclairé : éclairci, sans aller jusqu'au blanc (qui se confondrait avec la terre)
        const f = (s - 1) * 0.45;
        r = base[0] + (255 - base[0]) * f; g = base[1] + (255 - base[1]) * f; bl = base[2] + (255 - base[2]) * f;
      }
      // Isobathe entre ce pixel et son voisin de droite ou du dessous
      let trait = 0;
      for (let t = 0; t < 2; t++) {
        const v = nettoyee[t ? q + G : q + 1];
        if (v === 255 || v === b) continue;
        const seuil = SEUILS[Math.max(v, b) - 1];
        if (lignes.has(seuil)) trait = Math.max(trait, majeures.has(seuil) ? OPACITE_TRAIT_MAJEUR : OPACITE_TRAIT);
      }
      if (trait) {
        r = r * (1 - trait) + ENCRE[0] * trait;
        g = g * (1 - trait) + ENCRE[1] * trait;
        bl = bl * (1 - trait) + ENCRE[2] * trait;
      }
      rgba[o] = r;
      rgba[o + 1] = g;
      rgba[o + 2] = bl;
      rgba[o + 3] = Math.round(255 * A[q]);
    }
  }
  return rgba;
}

// --- Production d'une tuile (réseau, images) --------------------------------------------------------

function toile(l, h) {
  if (typeof OffscreenCanvas !== "undefined") return new OffscreenCanvas(l, h);
  const c = document.createElement("canvas");
  c.width = l;
  c.height = h;
  return c;
}

export class ErreurReseau extends Error {}

export const OUTILS = {
  async lireImage(url, signal) {
    let r;
    try {
      r = await fetch(url, { signal });
    } catch (e) {
      if (e.name === "AbortError") throw e;
      throw new ErreurReseau(`Shom injoignable : ${e.message}`);
    }
    if (!r.ok) throw new ErreurReseau(`Shom : HTTP ${r.status}`);
    const image = await createImageBitmap(await r.blob(), { premultiplyAlpha: "none", colorSpaceConversion: "none" });
    const t = toile(image.width, image.height);
    const ctx = t.getContext("2d", { willReadFrequently: true });
    ctx.drawImage(image, 0, 0);
    if (image.close) image.close();
    return { largeur: t.width, hauteur: t.height, pixels: ctx.getImageData(0, 0, t.width, t.height).data };
  },
  async encoderPng(rgba, l, h) {
    const t = toile(l, h);
    t.getContext("2d").putImageData(new ImageData(rgba, l, h), 0, 0);
    const blob = t.convertToBlob ? await t.convertToBlob({ type: "image/png" }) : await new Promise((ok) => t.toBlob(ok, "image/png"));
    return blob.arrayBuffer();
  },
};

// Tuile { z, x, y, taille } -> image PNG (ArrayBuffer)
export async function produireTuile({ z, x, y, taille = 512 }, signal, outils = OUTILS) {
  const plan = planTuile(z, x, y, taille);
  if (!plan.demandes.length) return outils.encoderPng(new Uint8ClampedArray(4), 1, 1);
  let echecs = 0, derniere = null;
  const images = await Promise.all(plan.demandes.map(async (d) => {
    try {
      return { d, img: await outils.lireImage(d.url, signal) };
    } catch (e) {
      if (e.name === "AbortError") throw e;
      echecs++;
      derniere = e;
      return null;
    }
  }));
  if (echecs === images.length) throw derniere;
  const sources = images.filter(Boolean).map(({ d, img }) => ({ ...d, ...decoderPixels(img.pixels, img.largeur, img.hauteur, d.palette) }));
  const rgba = rendreRelief({ taille, marge: plan.marge, pasSol: plan.pasSol, sortie: plan.sortie, sources });
  return outils.encoderPng(rgba, taille, taille);
}

// Légende : une case par tranche jusqu'à 100 m (les tranches plus profondes réunies)
export function tranchesLegende() {
  const t = [];
  const derniere = SEUILS.indexOf(100) + 1;
  for (let b = 0; b <= derniere; b++) {
    t.push({ de: b ? SEUILS[b - 1] : 0, a: b < derniere ? SEUILS[b] : null, couleur: COULEURS[b] });
  }
  return t;
}
