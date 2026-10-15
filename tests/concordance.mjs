// Exécute le moteur JavaScript sur des cas préparés par test_concordance_js.py.
// Usage : node tests/concordance.mjs cas.json > resultats.json
import { readFileSync } from "node:fs";
import { definirParametres, prevoir, calculer, preparerConditions } from "../app/js/moteur/moteur.js";

const cas = JSON.parse(readFileSync(process.argv[2], "utf8"));
definirParametres(cas.parametres);
const resultats = cas.cas.map((c) => {
  const options = { jours: c.jours, satellite: c.satellite, rapports: c.rapports };
  const sortie = prevoir(c.spot, c.conditions, c.maintenant, options);
  const brut = calculer(c.spot, preparerConditions(c.conditions), c.satellite);
  return { nom: c.nom, sortie, visibilite_modele: brut.visibilite_m };
});
process.stdout.write(JSON.stringify(resultats));
