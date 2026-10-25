// Température de l'eau au fond : lecture des profils publiés (app/js/temperatures.js).
import assert from "node:assert/strict";
import { lireProfil, temperatureAuFond } from "../app/js/temperatures.js";

const profil = { lat: 47.49, lon: -3.16, region: "atlantique", dates: ["2026-10-25", "2026-10-26"],
  profondeurs: [0.5, 5.1, 9.6, 15.8], valeurs: [[16, 15.6, 15.2, 14.6], [15, 14.8, 14.6, 14.4]] };
const donnees = { points: { "ref-quiberon": profil, "ref-sete": { ...profil, lat: 43.39, lon: 3.7, region: "mediterranee" } } };

assert.deepEqual(lireProfil(profil.profondeurs, profil.valeurs[0], 12), { temperature: 15, profondeur: 12 });
assert.deepEqual(lireProfil(profil.profondeurs, profil.valeurs[0], 0), { temperature: 16, profondeur: 0.5 });
assert.deepEqual(lireProfil(profil.profondeurs, profil.valeurs[0], 30), { temperature: 14.6, profondeur: 15.8 }, "au-delà du profil : niveau le plus profond");
assert.deepEqual(lireProfil([1], [20.4], 8), { temperature: 20.4, profondeur: 1 });

const point = temperatureAuFond(donnees, { id: "ref-quiberon", lat: 47.49, lon: -3.16, region: "atlantique", profondeur_m: 9.6 }, "2026-10-26");
assert.deepEqual(point, { temperature: 14.6, profondeur: 9.6, profondeur_demandee: 9.6, reference: null });

const prive = temperatureAuFond(donnees, { id: "prive-1", lat: 47.55, lon: -3.2, region: "atlantique", profondeur_m: 20 }, "2026-10-25", { "ref-quiberon": "Quiberon" });
assert.equal(prive.temperature, 14.6);
assert.equal(prive.profondeur, 15.8);
assert.deepEqual(prive.reference, { nom: "Quiberon", distance_km: 7 });

assert.equal(temperatureAuFond(donnees, { id: "x", lat: 48.4, lon: -4.8, region: "atlantique", profondeur_m: 8 }, "2026-10-25"), null, "trop loin");
assert.equal(temperatureAuFond(donnees, { id: "x", lat: 43.4, lon: 3.6, region: "atlantique", profondeur_m: 8 }, "2026-10-25"), null, "autre façade");
assert.equal(temperatureAuFond(donnees, { id: "ref-quiberon", lat: 47.49, lon: -3.16, region: "atlantique", profondeur_m: 8 }, "2026-10-29"), null, "jour hors prévision");
assert.equal(temperatureAuFond(null, { id: "ref-quiberon", profondeur_m: 8 }, "2026-10-25"), null);
console.log("Température au fond : 10 vérifications réussies");
