// Accès prudent au stockage du navigateur : il peut être absent ou plein (navigation privée).

export function lire(cle, defaut) {
  try {
    const v = localStorage.getItem(cle);
    return v === null ? defaut : JSON.parse(v);
  } catch (e) {
    return defaut;
  }
}

export function ecrire(cle, valeur) {
  try {
    localStorage.setItem(cle, JSON.stringify(valeur));
    return true;
  } catch (e) {
    return false;
  }
}

export function supprimer(cle) {
  try {
    localStorage.removeItem(cle);
  } catch (e) {
    /* rien à faire */
  }
}

export function identifiant() {
  const a = new Uint8Array(9);
  crypto.getRandomValues(a);
  return Array.from(a, (x) => x.toString(36).padStart(2, "0")).join("").slice(0, 12);
}

// Identifiant aléatoire de l'appareil, sans lien avec la personne : il sert seulement
// à estimer la fiabilité des retours terrain envoyés depuis cet appareil.
export function appareil() {
  let id = lire("kelvisi-appareil", null);
  if (!id) {
    id = identifiant();
    ecrire("kelvisi-appareil", id);
  }
  return id;
}
