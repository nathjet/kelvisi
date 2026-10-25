// Zones de pêche sous-marine : point dans un polygone (trous, multipolygones) et encarts des fiches.
import assert from "node:assert/strict";
import { dansGeometrie, encartZones } from "../app/js/zones.js";

const anneau = (o, s, e, n) => [[o, s], [e, s], [e, n], [o, n], [o, s]];
const troue = { type: "Polygon", coordinates: [anneau(0, 0, 10, 10), anneau(4, 4, 6, 6)] };
assert.ok(dansGeometrie(1, 1, troue));
assert.ok(!dansGeometrie(5, 5, troue), "dans le trou");
assert.ok(!dansGeometrie(11, 5, troue));
const multi = { type: "MultiPolygon", coordinates: [[anneau(0, 0, 1, 1)], [anneau(5, 5, 6, 6)]] };
assert.ok(dansGeometrie(5.5, 5.5, multi) && !dansGeometrie(3, 3, multi));
assert.ok(!dansGeometrie(0.5, 0.5, null));
// Côte découpée (polygone concave)
const crique = { type: "Polygon", coordinates: [[[0, 0], [4, 0], [4, 4], [2, 1], [0, 4], [0, 0]]] };
assert.ok(dansGeometrie(1, 0.5, crique) && !dansGeometrie(2, 3, crique));

const interdite = { classe: "interdite", regles: [{ classe: "interdite", nom: "Cantonnement <A>", regle: "Toute pêche interdite", reference: "Arrêté 1", periode: false },
  { classe: "reglementee", nom: "Parc", regle: "Déclaration", reference: "", periode: false }] };
const reglementee = { classe: "reglementee", regles: [{ classe: "reglementee", nom: "Oursins", regle: "Licence", reference: "Arrêté 2", periode: true }] };
const html = encartZones([interdite, reglementee]);
assert.match(html, /zone-interdite/);
assert.match(html, /Chasse sous-marine interdite ici/);
assert.match(html, /Cantonnement &lt;A&gt;/, "texte échappé");
assert.doesNotMatch(html, /Oursins|Parc/, "seules les règles d'interdiction quand la chasse est interdite");
assert.match(encartZones([reglementee]), /Règles particulières ici[\s\S]*selon la période de l'année/);
assert.match(encartZones([interdite], { court: true }), /interdite ici<\/strong> : Cantonnement &lt;A&gt;\./);
assert.equal(encartZones([]), "");
console.log("Zones : 13 vérifications réussies");
