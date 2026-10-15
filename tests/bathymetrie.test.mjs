// Lecture des profondeurs du Shom : décodage des couleurs, choix des sources, direction du large.
// Les images du Shom sont remplacées par des images synthétiques peintes avec les mêmes palettes.
// Usage : node tests/bathymetrie.test.mjs

import assert from "node:assert/strict";
import {
  SOURCES, couleurPour, decoderCouleur, definirLecteurImage, grilleAutour, meilleureMesure, orientationDepuisGrille,
  profondeursAuPoint, urlTuilesShom,
} from "../app/js/bathymetrie.js";

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

// Fond synthétique : la mer est à l'ouest de la longitude -3.15, de plus en plus profonde vers l'ouest
const fond = (lat, lon) => (lon < -3.15 ? Math.min(60, 4 + (-3.15 - lon) * 400) : -8);
function image(url) {
  const q = new URL(url).searchParams;
  const [s, o, n, e] = q.get("BBOX").split(",").map(Number);
  const taille = Number(q.get("WIDTH"));
  const source = SOURCES.find((x) => x.couche === q.get("LAYERS"));
  const pixels = new Uint8ClampedArray(taille * taille * 4);
  for (let y = 0; y < taille; y++) {
    for (let x = 0; x < taille; x++) {
      const lat = n - ((y + 0.5) / taille) * (n - s);
      const lon = o + ((x + 0.5) / taille) * (e - o);
      // Décalage de référence : le laser mesure depuis le niveau moyen, 3 m au-dessus des plus basses mers
      let d = fond(lat, lon);
      if (source.reference === "moyen" && d > 0) d += 3;
      const c = couleurPour(Math.min(d, source.max), source.palette);
      // Relief éclairé : les palettes ombrées sont assombries
      const f = source.type === "laser" ? 0.8 : 1;
      pixels.set([Math.round(c[0] * f), Math.round(c[1] * f), Math.round(c[2] * f), 255], (y * taille + x) * 4);
    }
  }
  return { largeur: taille, hauteur: taille, pixels };
}
const demandes = [];
definirLecteurImage(async (url) => { demandes.push(url); return image(url); });

await etape("chaque palette se relit à la couleur près", async () => {
  for (const [palette, profondeurs] of [["facade", [3, 12, 22, 35, 70]], ["cotier", [2, 8, 15, 30, 45]], ["litto_atl", [6, 12, 20]], ["litto_med", [3, 10, 25]]]) {
    for (const p of profondeurs) {
      const { profondeur } = decoderCouleur(couleurPour(p, palette), palette);
      // Palettes Litto3D : entre 5 et 10 m les teintes se ressemblent, la lecture est à 1 m près
      const tolerance = palette.startsWith("litto") ? 1 : 0.6;
      assert.ok(Math.abs(profondeur - p) <= tolerance, `${palette} ${p} m relu ${profondeur} m`);
    }
  }
  // Une couleur de terre n'est jamais lue comme de l'eau
  assert.ok(decoderCouleur([0, 255, 0], "litto_atl").profondeur < 0, "vert Litto3D = terre");
});

await etape("profondeurs au point : laser, modèle côtier et façade, chacun avec sa référence", async () => {
  const mesures = await profondeursAuPoint(47.47, -3.17);
  assert.deepEqual(mesures.map((m) => m.type), ["laser", "cotier", "facade"]);
  const [laser, cotier, facade] = mesures;
  assert.equal(laser.reference, "moyen");
  assert.equal(cotier.reference, "pbma");
  assert.ok(Math.abs(cotier.profondeur_m - 12) <= 1, `côtier ${cotier.profondeur_m}`);
  assert.ok(Math.abs(facade.profondeur_m - 12) <= 1.5, `façade ${facade.profondeur_m}`);
  assert.ok(Math.abs(laser.profondeur_m - 15) <= 1.5, `laser ${laser.profondeur_m}`);
  assert.equal(meilleureMesure(mesures), laser);
});

await etape("au-delà de la portée du laser, la mesure suivante prend le relais", async () => {
  const mesures = await profondeursAuPoint(47.47, -3.25);
  assert.ok(mesures[0].au_moins, "laser saturé");
  assert.equal(meilleureMesure(mesures).type, "cotier");
  assert.ok(meilleureMesure(mesures).profondeur_m > 30);
});

await etape("à terre", async () => {
  const m = meilleureMesure(await profondeursAuPoint(47.47, -3.10));
  assert.ok(m.terre && m.profondeur_m === null);
});

await etape("hors des zones du Shom : aucune mesure, aucune requête", async () => {
  demandes.length = 0;
  assert.deepEqual(await profondeursAuPoint(36.0, -20.0), []);
  assert.equal(demandes.length, 0);
});

await etape("direction du large et ouverture tirées de la carte de façade", async () => {
  const g = await grilleAutour(47.47, -3.16);
  const o = orientationDepuisGrille(g);
  assert.ok(o.orientation_deg > 240 && o.orientation_deg < 300, `orientation ${o.orientation_deg}`);
  assert.ok(o.ouverture_deg >= 135 && o.ouverture_deg <= 180, `ouverture ${o.ouverture_deg}`);
});

await etape("tuiles de la carte : couches côtières et laser, laser au-dessus", async () => {
  const u = urlTuilesShom();
  assert.match(u, /\{bbox-epsg-3857\}/);
  const couches = new URL(u.replace("{bbox-epsg-3857}", "0,0,1,1")).searchParams.get("LAYERS").split(",");
  assert.ok(couches.indexOf("LITTO3D_BZH_2018_2021_PYR_3857_WMSR") > couches.indexOf("MNT_COTIER_MORBIHAN_TANDEM_20m_PBMA_3857_WMSR"));
  assert.ok(!couches.some((c) => c.startsWith("MNT_ATL100m")), "façade non affichée (EMODnet en dessous)");
});

console.log(`Bathymétrie\n${etapes.join("\n")}`);
process.exit(process.exitCode || 0);
