// Points Kelvisi favoris : une simple liste d'identifiants, gardée sur l'appareil.

import { lire, ecrire } from "./stockage.js";
import { noterFavori } from "./synchro.js";
import { alertes, remplacerAlertes } from "./alertes.js";

const CLE = "kelvisi-favoris";

export function favoris() {
  const liste = lire(CLE, []);
  return Array.isArray(liste) ? liste.filter((x) => typeof x === "string") : [];
}

export function estFavori(id) {
  return favoris().includes(id);
}

// Ajoute ou retire ; renvoie vrai si le point est désormais favori
export function basculerFavori(id) {
  const liste = favoris();
  const i = liste.indexOf(id);
  if (i >= 0) {
    liste.splice(i, 1);
    // Retiré des favoris : son alerte disparaît avec lui (sur le compte aussi, la ligne étant supprimée)
    const a = alertes();
    if (a[id]) {
      delete a[id];
      remplacerAlertes(a);
    }
  } else liste.push(id);
  ecrire(CLE, liste);
  noterFavori(id, i < 0 ? "ajout" : "retrait");
  return i < 0;
}

export function ajouterFavoris(ids) {
  const liste = favoris();
  let n = 0;
  for (const id of ids || []) {
    if (typeof id === "string" && id.length <= 64 && !liste.includes(id)) {
      liste.push(id);
      noterFavori(id, "ajout");
      n++;
    }
  }
  ecrire(CLE, liste);
  return n;
}
