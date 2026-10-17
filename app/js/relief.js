// Tuiles du relief sous-marin pour MapLibre : protocole « kelvisi-relief:// », calcul dans un
// worker (dans la page si le navigateur ne le permet pas), dernières tuiles gardées en mémoire.

import { produireTuile } from "./relief-rendu.js";

export const PROTOCOLE = "kelvisi-relief";
export const URL_TUILES = `${PROTOCOLE}://{z}/{x}/{y}`;
export const TAILLE_TUILE = 512;

const MEMOIRE_MAX = 96;
const memoire = new Map();
const attentes = new Map();
let travailleur; // undefined : pas encore lancé ; null : indisponible
let numero = 0;

const erreurAnnulation = () => new DOMException("Tuile abandonnée", "AbortError");

function arreterTravailleur() {
  if (travailleur) travailleur.terminate();
  travailleur = null;
  const enAttente = [...attentes.values()];
  attentes.clear();
  for (const a of enAttente) a.repli();
}

function lancerTravailleur() {
  if (travailleur !== undefined) return travailleur;
  travailleur = null;
  if (typeof Worker === "undefined" || typeof OffscreenCanvas === "undefined") return null;
  try {
    const w = new Worker(new URL("./relief-travail.js", import.meta.url), { type: "module" });
    w.addEventListener("message", (e) => {
      const a = attentes.get(e.data.id);
      if (!a) return;
      attentes.delete(e.data.id);
      if (e.data.png) a.ok(e.data.png);
      else if (e.data.interne) {
        // Dessin impossible dans le worker sur ce navigateur : tout passe par la page
        a.repli();
        arreterTravailleur();
      } else a.ko(e.data.erreur);
    });
    w.addEventListener("error", arreterTravailleur);
    travailleur = w;
  } catch (e) {
    travailleur = null;
  }
  return travailleur;
}

function calculer(tuile, signal) {
  const w = lancerTravailleur();
  if (!w) return produireTuile(tuile, signal);
  return new Promise((ok, ko) => {
    const id = ++numero;
    const annuler = () => {
      attentes.delete(id);
      w.postMessage({ annuler: id });
      ko(erreurAnnulation());
    };
    const fin = () => signal && signal.removeEventListener("abort", annuler);
    attentes.set(id, {
      ok: (png) => { fin(); ok(png); },
      ko: (message) => { fin(); ko(message === "AbortError" ? erreurAnnulation() : new Error(message)); },
      repli: () => { fin(); produireTuile(tuile, signal).then(ok, ko); },
    });
    if (signal) signal.addEventListener("abort", annuler, { once: true });
    w.postMessage({ id, tuile });
  });
}

export async function tuileRelief(z, x, y, signal) {
  const cle = `${z}/${x}/${y}`;
  if (memoire.has(cle)) {
    const png = memoire.get(cle);
    memoire.delete(cle);
    memoire.set(cle, png);
    return png.slice(0);
  }
  const png = await calculer({ z, x, y, taille: TAILLE_TUILE }, signal);
  memoire.set(cle, png);
  if (memoire.size > MEMOIRE_MAX) memoire.delete(memoire.keys().next().value);
  return png.slice(0);
}

export function installerRelief(maplibregl) {
  if (!maplibregl || typeof maplibregl.addProtocol !== "function") return false;
  maplibregl.addProtocol(PROTOCOLE, async (parametres, controleur) => {
    const m = /^[a-z-]+:\/\/(\d+)\/(\d+)\/(\d+)/.exec(parametres.url);
    if (!m) throw new Error(`Tuile de relief inconnue : ${parametres.url}`);
    const data = await tuileRelief(Number(m[1]), Number(m[2]), Number(m[3]), controleur && controleur.signal);
    return { data };
  });
  return true;
}
