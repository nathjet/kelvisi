// Points Kelvisi favoris : une simple liste d'identifiants, gardée sur l'appareil.

import { lire, ecrire } from "./stockage.js";

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
  if (i >= 0) liste.splice(i, 1);
  else liste.push(id);
  ecrire(CLE, liste);
  return i < 0;
}

export function ajouterFavoris(ids) {
  const liste = favoris();
  let n = 0;
  for (const id of ids || []) {
    if (typeof id === "string" && id.length <= 64 && !liste.includes(id)) {
      liste.push(id);
      n++;
    }
  }
  ecrire(CLE, liste);
  return n;
}
