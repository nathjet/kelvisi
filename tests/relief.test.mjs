// Relief sous-marin de la carte : choix des images du Shom, décodage, tranches, isobathes, éclairage.
// Les images du Shom sont remplacées par des images synthétiques peintes avec leurs palettes.
// Usage : node tests/relief.test.mjs

import assert from "node:assert/strict";
import { SOURCES, couleurPour } from "../app/js/bathymetrie.js";
import {
  COULEURS, ISOBATHES, SEUILS, decoderPixels, empriseTuile, planTuile, produireTuile, rendreRelief, tranchesLegende,
} from "../app/js/relief-rendu.js";

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

const R = 6378137;
const versMerc = (lat, lon) => [(R * lon * Math.PI) / 180, R * Math.log(Math.tan(Math.PI / 4 + (lat * Math.PI) / 360))];
function tuileDe(lat, lon, z) {
  const [mx, my] = versMerc(lat, lon);
  const t = (2 * Math.PI * R) / 2 ** z;
  return [z, Math.floor((mx + Math.PI * R) / t), Math.floor((Math.PI * R - my) / t)];
}
const couches = (plan) => plan.demandes.map((d) => d.couche);

await etape("images demandées selon le zoom : façade de loin, puis modèle côtier, puis relevé laser", async () => {
  const loin = planTuile(...tuileDe(47.47, -3.15, 8));
  assert.deepEqual(couches(loin), ["MNT_ATL100m_HOMONIM_PBMA_3857_WMSR"]);
  const moyen = planTuile(...tuileDe(47.47, -3.15, 11));
  assert.deepEqual(couches(moyen), ["MNT_COTIER_MORBIHAN_TANDEM_20m_PBMA_3857_WMSR", "MNT_ATL100m_HOMONIM_PBMA_3857_WMSR"]);
  const pres = planTuile(...tuileDe(47.47, -3.15, 13));
  assert.deepEqual(couches(pres), ["LITTO3D_BZH_2018_2021_PYR_3857_WMSR", "MNT_COTIER_MORBIHAN_TANDEM_20m_PBMA_3857_WMSR", "MNT_ATL100m_HOMONIM_PBMA_3857_WMSR"]);
  // Le modèle à 100 m n'est pas demandé en 512 pixels : sa résolution suffit
  const facade = pres.demandes.at(-1);
  assert.ok(facade.largeur < 120, `façade demandée en ${facade.largeur} px`);
  // Le relevé laser est demandé à la taille de la tuile, marge comprise
  assert.equal(pres.demandes[0].largeur, 512 + 2 * pres.marge);
  for (const d of pres.demandes) {
    const u = new URL(d.url);
    assert.equal(u.searchParams.get("LAYERS"), d.couche);
    assert.equal(Number(u.searchParams.get("WIDTH")), d.largeur);
  }
});

await etape("golfe du Lion : façade Méditerranée seulement ; large de l'Atlantique : rien à demander", async () => {
  assert.deepEqual(couches(planTuile(...tuileDe(43.27, 3.51, 9))), ["MNT_MED100m_GDL_CA_HOMONIM_PBMA_3857_WMSR"]);
  assert.deepEqual(planTuile(...tuileDe(45, -15, 8)).demandes, []);
  // Couche du golfe normand-breton, publiée en coordonnées géographiques : latitude d'abord
  const gnb = planTuile(...tuileDe(48.7, -1.9, 12)).demandes.find((d) => d.couche.includes("_4326_"));
  const bbox = new URL(gnb.url).searchParams.get("BBOX").split(",").map(Number);
  assert.equal(new URL(gnb.url).searchParams.get("CRS"), "EPSG:4326");
  assert.ok(bbox[0] > 48 && bbox[0] < 49.5 && bbox[1] < -1 && bbox[1] > -3, `bbox ${bbox}`);
});

await etape("décodage : profondeur relue, terre négative, éclairage du relevé laser", async () => {
  const valeurs = [3, 12, 22, 35, -5];
  const px = new Uint8ClampedArray(valeurs.length * 4);
  valeurs.forEach((p, i) => px.set([...couleurPour(p, "facade"), 255], 4 * i));
  const { prof } = decoderPixels(px, valeurs.length, 1, "facade");
  valeurs.forEach((p, i) => assert.ok(Math.abs(prof[i] - p) <= 0.6, `${p} relu ${prof[i]}`));
  // Relevé laser assombri par le relief : même profondeur, luminosité 0,6
  const c = couleurPour(18, "litto_atl").map((x) => Math.round(x * 0.6));
  const laser = decoderPixels(new Uint8ClampedArray([...c, 255, 0, 0, 0, 0]), 2, 1, "litto_atl");
  assert.ok(Math.abs(laser.prof[0] - 18) <= 1, `laser ${laser.prof[0]}`);
  assert.ok(Math.abs(laser.lum[0] - 0.6) < 0.05, `luminosité ${laser.lum[0]}`);
  assert.ok(Number.isNaN(laser.prof[1]), "pixel transparent : sans donnée");
  // Une couleur étrangère à la palette n'est pas lue
  assert.ok(Number.isNaN(decoderPixels(new Uint8ClampedArray([255, 0, 255, 255]), 1, 1, "cotier").prof[0]));
});

// Grille synthétique : profondeur fonction de la colonne (pente d'ouest en est), terre à l'ouest
function grille(n, f) {
  const prof = new Float32Array(n * n);
  for (let i = 0; i < n; i++) for (let j = 0; j < n; j++) prof[i * n + j] = f(i / (n - 1), j / (n - 1));
  return prof;
}
const EMPRISE = [0, 0, 3000, 3000];
function rendu(sources, taille = 128) {
  const marge = 2, pas = (EMPRISE[2] - EMPRISE[0]) / taille;
  const sortie = [EMPRISE[0] - marge * pas, EMPRISE[1] - marge * pas, EMPRISE[2] + marge * pas, EMPRISE[3] + marge * pas];
  return { rgba: rendreRelief({ taille, marge, pasSol: pas, sortie, sources }), taille };
}
const pixel = ({ rgba, taille }, i, j) => Array.from(rgba.slice(4 * (i * taille + j), 4 * (i * taille + j) + 4));

await etape("tranches, isobathes tous les 5 m et terre transparente", async () => {
  // Façade à 100 m : terre sur le premier dixième, puis de 0 à 40 m d'ouest en est
  const n = 31;
  const prof = grille(n, (_, x) => (x < 0.1 ? -5 : ((x - 0.1) / 0.9) * 40));
  const r = rendu([{ type: "facade", max: 3000, prof, lum: null, largeur: n, hauteur: n, emprise: EMPRISE }]);
  assert.equal(pixel(r, 64, 2)[3], 0, "terre transparente");
  assert.equal(pixel(r, 64, 120)[3], 255, "mer opaque");
  // Plus c'est profond, plus c'est foncé
  const clair = pixel(r, 64, 30), fonce = pixel(r, 64, 115);
  assert.ok(clair[0] + clair[1] + clair[2] > fonce[0] + fonce[1] + fonce[2] + 100, `${clair} / ${fonce}`);
  // Un trait (pixel plus foncé que ses voisins) au passage de chaque isobathe tracée, pas à 25 m ni 40 m
  const ligne = Array.from({ length: r.taille }, (_, j) => pixel(r, 64, j));
  const luminosite = (p) => p[0] + p[1] + p[2];
  const traits = [];
  for (let j = 1; j < r.taille - 1; j++) {
    if (ligne[j][3] && ligne[j - 1][3] && ligne[j + 1][3] && luminosite(ligne[j]) < luminosite(ligne[j - 1]) - 60 && luminosite(ligne[j]) < luminosite(ligne[j + 1]) - 30) traits.push(j);
  }
  const profondeurA = (j) => (((j + 0.5) / r.taille - 0.1) / 0.9) * 40;
  const vues = traits.map((j) => Math.round(profondeurA(j)));
  for (const iso of [5, 10, 15, 20, 30]) assert.ok(vues.some((v) => Math.abs(v - iso) <= 1), `isobathe ${iso} m absente (${vues})`);
  assert.ok(!vues.some((v) => Math.abs(v - 25) <= 0.5), `trait à 25 m (${vues})`);
  assert.ok(ISOBATHES.includes(10) && !ISOBATHES.includes(25));
});

await etape("relevé laser prioritaire, modèle de secours au-delà de sa portée", async () => {
  const n = 31;
  const facade = { type: "facade", max: 3000, prof: grille(n, () => 8), lum: null, largeur: n, hauteur: n, emprise: EMPRISE };
  // Laser : 12 m sur la moitié nord, saturé (au-delà de sa portée de 25 m) au sud
  const m = 132;
  const laser = { type: "laser", max: 25, prof: grille(m, (y) => (y < 0.5 ? 12 : 25)), lum: new Float32Array(m * m).fill(0.75), largeur: m, hauteur: m, emprise: EMPRISE };
  const r = rendu([laser, facade]);
  const bande = (d) => SEUILS.filter((s) => d >= s).length;
  assert.deepEqual(pixel(r, 20, 64).slice(0, 3), COULEURS[bande(12)], "nord : 12 m du laser, éclairage neutre");
  assert.deepEqual(pixel(r, 110, 64).slice(0, 3), COULEURS[bande(8)], "sud : 8 m de la façade");
});

await etape("éclairage du nord-ouest : un versant tourné vers le nord-ouest est plus clair", async () => {
  const n = 41;
  // Un haut-fond conique de 5 m au centre, 30 m autour
  const prof = grille(n, (y, x) => Math.min(30, 5 + 60 * Math.hypot(x - 0.5, y - 0.5)));
  const r = rendu([{ type: "facade", max: 3000, prof, lum: null, largeur: n, hauteur: n, emprise: EMPRISE }]);
  const lum = (p) => p[0] + p[1] + p[2];
  // même profondeur, versant nord-ouest et versant sud-est
  const no = pixel(r, 64 - 18, 64 - 18), se = pixel(r, 64 + 18, 64 + 18);
  assert.ok(lum(no) > lum(se) + 60, `nord-ouest ${no} / sud-est ${se}`);
});

await etape("tuile complète : images manquantes tolérées, toutes manquantes = erreur", async () => {
  const [z, x, y] = tuileDe(47.47, -3.15, 13);
  const plan = planTuile(z, x, y);
  // Faux Shom : chaque couche peinte avec sa palette, mer à l'ouest de -3.15 ; le modèle côtier ne répond pas
  const outils = {
    async lireImage(url) {
      const q = new URL(url).searchParams;
      const couche = q.get("LAYERS");
      if (couche.startsWith("MNT_COTIER")) throw Object.assign(new Error("HTTP 503"), { name: "Error" });
      const s = SOURCES.find((x) => x.couche === couche);
      const [o, , e] = q.get("BBOX").split(",").map(Number);
      const l = Number(q.get("WIDTH"));
      const pixels = new Uint8ClampedArray(l * l * 4);
      for (let i = 0; i < l; i++) {
        for (let j = 0; j < l; j++) {
          const lon = ((o + ((j + 0.5) / l) * (e - o)) / R) * (180 / Math.PI);
          const d = lon < -3.15 ? Math.min(s.max, 4 + (-3.15 - lon) * 400) : -6;
          pixels.set([...couleurPour(d, s.palette), 255], 4 * (i * l + j));
        }
      }
      return { largeur: l, hauteur: l, pixels };
    },
    async encoderPng(rgba, l, h) { return { rgba, l, h }; },
  };
  const t = await produireTuile({ z, x, y, taille: 512 }, undefined, outils);
  assert.equal(t.l, 512);
  const e = empriseTuile(z, x, y);
  // Colonne du trait de côte (longitude -3.15), tracé par le relevé laser
  const cote = Math.round(((versMerc(47.47, -3.15)[0] - e[0]) / (e[2] - e[0])) * 512);
  assert.ok(cote > 45 && cote < 500, `côte en colonne ${cote}`);
  assert.equal(t.rgba[4 * (256 * 512 + cote + 3) + 3], 0, "à terre (est)");
  assert.equal(t.rgba[4 * (256 * 512 + cote - 40) + 3], 255, "en mer (ouest)");
  assert.equal(plan.demandes.length, 3);
  const enPanne = { ...outils, async lireImage() { throw new Error("hors ligne"); } };
  await assert.rejects(produireTuile({ z, x, y, taille: 512 }, undefined, enPanne), /hors ligne/);
  // Loin de toute donnée : tuile vide sans aucune demande
  let demandes = 0;
  const vide = await produireTuile({ z: 8, x: tuileDe(45, -15, 8)[1], y: tuileDe(45, -15, 8)[2] }, undefined, { ...outils, async lireImage() { demandes++; } });
  assert.equal(vide.l, 1);
  assert.equal(demandes, 0);
});

await etape("légende : 12 cases de 0 à plus de 100 m, mêmes couleurs que la carte", async () => {
  const t = tranchesLegende();
  assert.equal(t.length, 12);
  assert.deepEqual([t[0].de, t[0].a], [0, 2]);
  assert.deepEqual([t.at(-1).de, t.at(-1).a], [100, null]);
  assert.deepEqual(t[3].couleur, COULEURS[3]);
});

console.log(`Relief\n${etapes.join("\n")}`);
process.exit(process.exitCode || 0);
