// Spots partagés par les utilisateurs : proposés depuis « Mon spot », visibles de tous une fois
// validés par Kelvisi, sans le nom de leur auteur. Ils sont calculés dans le navigateur, comme
// un lieu libre. Tant que la base n'a pas la fonction de partage (script SQL pas encore appliqué),
// tout reste masqué et les spots privés se synchronisent comme avant.

import { lire, ecrire } from "./stockage.js";
import { comptesActifs, requete, utilisateur } from "./compte.js";

const CLE = "kelvisi-communaute";
const PREFIXE = "communaute-";

let disponible = null;       // null : pas encore vérifié ; true / false ensuite
let verification = null;
let spots = lire(CLE, { spots: [] }).spots || [];

export const idCommunaute = (uuid) => `${PREFIXE}${uuid}`;
export const estCommunaute = (id) => String(id || "").startsWith(PREFIXE);

// Le partage est-il en service sur la base ? (une seule vérification réussie par session)
export function partageDisponible() {
  if (disponible !== null) return Promise.resolve(disponible);
  if (!comptesActifs() || !utilisateur()) return Promise.resolve(false);
  if (!verification) {
    verification = chargerCommunaute().finally(() => { verification = null; });
  }
  return verification.then(() => Boolean(disponible));
}

export function partageConnu() {
  return disponible === true;
}

// Liste des spots validés ; garde la dernière liste reçue pour le hors ligne
export async function chargerCommunaute() {
  if (!comptesActifs() || !utilisateur()) return spots;
  try {
    const lignes = await requete("rpc/spots_communaute", { methode: "POST", corps: {} });
    disponible = true;
    spots = (lignes || []).map((s) => ({
      id: idCommunaute(s.id), uuid: s.id, nom: s.nom, lat: s.lat, lon: s.lon, region: s.region,
      orientation_deg: s.orientation_deg, ouverture_deg: s.ouverture_deg, profondeur_m: s.profondeur_m, fond: s.fond,
      publie_le: s.publie_le, communaute: true,
    }));
    ecrire(CLE, { spots, recu_le: new Date().toISOString() });
    document.dispatchEvent(new CustomEvent("kelvisi-communaute"));
  } catch (e) {
    // Fonction absente de la base : le partage n'est pas encore installé
    if (e.code === "PGRST202" || e.code === "404" || e.code === "42883") disponible = false;
  }
  return spots;
}

// Spots partagés, sans ceux de l'utilisateur lui-même (il les voit déjà comme « mes spots »)
export function spotsCommunaute(mesIdsPublics = []) {
  const miens = new Set(mesIdsPublics.filter(Boolean));
  return spots.filter((s) => !miens.has(s.uuid));
}

export function spotCommunaute(id) {
  return spots.find((s) => s.id === id) || null;
}

export function oublierCommunaute() {
  spots = [];
  disponible = null;
  ecrire(CLE, { spots: [] });
}

// État de partage d'un spot privé, pour l'affichage
export const ETATS_PARTAGE = {
  prive: { titre: "Visible par toi seul", action: "Proposer ce spot à tous" },
  en_attente: { titre: "Proposé : en attente de validation par Kelvisi", action: "Annuler la proposition" },
  publie: { titre: "Partagé : visible par tous, sans ton nom", action: "Ne plus le partager" },
  refuse: { titre: "Non retenu par Kelvisi pour le partage", action: "Le garder privé" },
};
