// Lecture des profondeurs du Shom : décodage des couleurs, choix des sources, direction du large.
// Les images du Shom sont remplacées par des images synthétiques peintes avec les mêmes palettes.
// Usage : node tests/bathymetrie.test.mjs

import assert from "node:assert/strict";
import {
  SOURCES, couleurPour, couvre, croise, decoderCouleur, definirLecteurImage, grilleAutour, meilleureMesure, orientationDepuisGrille,
  profondeursAuPoint,
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

// Fond synthétique : en Atlantique, la mer est à l'ouest de la longitude -3.15, de plus en plus profonde
// vers l'ouest ; en Méditerranée, au sud de la latitude 43.30.
const fond = (lat, lon) => {
  if (lon > 0) return lat < 43.3 ? Math.min(60, 4 + (43.3 - lat) * 400) : -8;
  return lon < -3.15 ? Math.min(60, 4 + (-3.15 - lon) * 400) : -8;
};
// Comme sur le vrai service : la façade Atlantique n'a rien en Méditerranée, et (pour le test) le
// relevé laser du Finistère n'a rien du tout
const vide = (source, lat, lon) => (source.couche.startsWith("MNT_ATL100m") && lon > 0 && lat < 44.6) || source.couche.startsWith("LITTO3D_FINISTR");
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
      if (vide(source, lat, lon)) continue;
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

await etape("golfe du Lion : la façade Méditerranée, sans demande inutile à la façade Atlantique", async () => {
  demandes.length = 0;
  const mesures = await profondeursAuPoint(43.275, 3.51);
  const facade = mesures.find((m) => m.type === "facade");
  assert.equal(facade?.source, "MNT de façade golfe du Lion - Côte d'Azur");
  assert.ok(Math.abs(facade.profondeur_m - 14) <= 1.5, `façade ${facade.profondeur_m}`);
  assert.ok(!demandes.some((u) => u.includes("MNT_ATL100m")), "façade Atlantique non demandée");
  const atl = SOURCES.find((s) => s.couche.startsWith("MNT_ATL100m"));
  assert.ok(!couvre(atl, 43.275, 3.51) && couvre(atl, 47.47, -3.17));
  assert.ok(croise(atl, [3.4, 43.2, 3.6, 43.4]) === false && croise(atl, [-3.2, 47.4, -3.1, 47.5]));
  // Direction du large lue sur la bonne carte : la mer est au sud
  const o = orientationDepuisGrille(await grilleAutour(43.29, 3.51));
  assert.ok(o.orientation_deg > 150 && o.orientation_deg < 210, `orientation ${o.orientation_deg}`);
});

await etape("deux sources du même type qui se chevauchent : la suivante prend le relais", async () => {
  // Dans le Finistère sud, le relevé du Finistère (vide ici) puis celui de la Bretagne
  const laser = (await profondeursAuPoint(47.8, -3.5)).find((m) => m.type === "laser");
  assert.equal(laser?.source, "Litto3D Bretagne");
});

console.log(`Bathymétrie\n${etapes.join("\n")}`);
process.exit(process.exitCode || 0);
