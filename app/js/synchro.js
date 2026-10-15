// Synchronisation des spots privés et des favoris avec le compte.
//
// L'appareil garde une copie de travail (utilisable hors connexion). Chaque modification est
// notée dans une file d'attente, envoyée au serveur dès que possible ; ensuite la copie locale
// est remplacée par l'état du serveur, qui fait foi entre plusieurs appareils.

import { lire, ecrire, supprimer } from "./stockage.js";
import { comptesActifs, requete, utilisateur } from "./compte.js";

const CLE_SPOTS = "kelvisi-spots";
const CLE_FAVORIS = "kelvisi-favoris";
const CLE_ATTENTE = "kelvisi-synchro-attente";
const CLE_PROPRIETAIRE = "kelvisi-synchro-compte";
const CHAMPS_SPOT = ["id", "nom", "lat", "lon", "region", "orientation_deg", "ouverture_deg", "profondeur_m", "fond", "cree_le", "maj_le"];

function attente() {
  const a = lire(CLE_ATTENTE, null);
  return { spots: { ...(a?.spots || {}) }, favoris: { ...(a?.favoris || {}) } };
}

export function noterSpot(id, operation) {
  if (!comptesActifs()) return;
  const a = attente();
  a.spots[id] = operation; // « maj » ou « suppr »
  ecrire(CLE_ATTENTE, a);
  planifier();
}

export function noterFavori(id, operation) {
  if (!comptesActifs()) return;
  const a = attente();
  a.favoris[id] = operation; // « ajout » ou « retrait »
  ecrire(CLE_ATTENTE, a);
  planifier();
}

export function enAttente() {
  const a = attente();
  return Object.keys(a.spots).length + Object.keys(a.favoris).length;
}

let minuterie = null;
function planifier() {
  if (!comptesActifs() || !utilisateur()) return;
  clearTimeout(minuterie);
  minuterie = setTimeout(() => { synchroniser().catch(() => {}); }, 300);
}

const liste = (ids) => `(${ids.map((i) => `"${String(i).replace(/"/g, "")}"`).join(",")})`;

let enCours = null;
export function synchroniser() {
  if (!enCours) enCours = executer().finally(() => { enCours = null; });
  return enCours;
}

async function executer() {
  const u = utilisateur();
  if (!comptesActifs() || !u) return { ok: false, raison: "deconnecte" };

  // Données locales d'un autre compte (session expirée sans déconnexion) : on ne les mélange pas
  const proprietaire = lire(CLE_PROPRIETAIRE, null);
  if (proprietaire && proprietaire !== u.id) {
    effacerDonneesLocales();
  } else if (!proprietaire) {
    // Premier passage sur cet appareil : les spots et favoris créés avant le compte y sont versés
    const a = attente();
    for (const s of lire(CLE_SPOTS, [])) a.spots[s.id] ||= "maj";
    for (const f of lire(CLE_FAVORIS, [])) a.favoris[f] ||= "ajout";
    ecrire(CLE_ATTENTE, a);
  }
  ecrire(CLE_PROPRIETAIRE, u.id);

  const a = attente();
  try {
    const locaux = new Map(lire(CLE_SPOTS, []).map((s) => [s.id, s]));
    const aEnvoyer = Object.entries(a.spots).filter(([id, op]) => op === "maj" && locaux.has(id)).map(([id]) => locaux.get(id));
    const aSupprimer = Object.entries(a.spots).filter(([, op]) => op === "suppr").map(([id]) => id);
    if (aEnvoyer.length) {
      await requete("spots_prives?on_conflict=proprietaire,id", {
        methode: "POST",
        prefer: "resolution=merge-duplicates,return=minimal",
        corps: aEnvoyer.map((s) => ({ ...Object.fromEntries(CHAMPS_SPOT.map((c) => [c, s[c]])), proprietaire: u.id, maj_le: s.maj_le || new Date().toISOString() })),
      });
    }
    if (aSupprimer.length) await requete(`spots_prives?id=in.${encodeURIComponent(liste(aSupprimer))}`, { methode: "DELETE" });

    const ajouts = Object.entries(a.favoris).filter(([, op]) => op === "ajout").map(([id]) => id);
    const retraits = Object.entries(a.favoris).filter(([, op]) => op === "retrait").map(([id]) => id);
    if (ajouts.length) {
      await requete("favoris?on_conflict=proprietaire,point_id", {
        methode: "POST",
        prefer: "resolution=ignore-duplicates,return=minimal",
        corps: ajouts.map((point_id) => ({ proprietaire: u.id, point_id })),
      });
    }
    if (retraits.length) await requete(`favoris?point_id=in.${encodeURIComponent(liste(retraits))}`, { methode: "DELETE" });

    // Ce qui a été envoyé sort de la file ; une modification faite pendant l'envoi y reste
    const apres = attente();
    for (const [id, op] of Object.entries(a.spots)) if (apres.spots[id] === op) delete apres.spots[id];
    for (const [id, op] of Object.entries(a.favoris)) if (apres.favoris[id] === op) delete apres.favoris[id];
    ecrire(CLE_ATTENTE, apres);

    const [spots, favoris] = await Promise.all([
      requete(`spots_prives?select=${CHAMPS_SPOT.join(",")}&order=cree_le.asc`),
      requete("favoris?select=point_id&order=cree_le.asc"),
    ]);
    // Les modifications encore en attente gardent leur version locale
    const reste = attente();
    const encoreLocaux = new Map(lire(CLE_SPOTS, []).map((s) => [s.id, s]));
    const fusion = spots.filter((s) => reste.spots[s.id] !== "suppr").map((s) => ({ ...s, prive: true }));
    for (const [id, op] of Object.entries(reste.spots)) {
      if (op === "maj" && encoreLocaux.has(id)) {
        const i = fusion.findIndex((s) => s.id === id);
        if (i >= 0) fusion[i] = encoreLocaux.get(id);
        else fusion.push(encoreLocaux.get(id));
      }
    }
    const favs = favoris.map((f) => f.point_id).filter((id) => reste.favoris[id] !== "retrait");
    for (const [id, op] of Object.entries(reste.favoris)) if (op === "ajout" && !favs.includes(id)) favs.push(id);
    ecrire(CLE_SPOTS, fusion);
    ecrire(CLE_FAVORIS, favs);
    document.dispatchEvent(new CustomEvent("kelvisi-synchro"));
    return { ok: true };
  } catch (e) {
    return { ok: false, raison: e.code === "reseau" ? "reseau" : "erreur", erreur: e };
  }
}

// À la déconnexion ou au changement de compte : rien ne reste sur l'appareil
export function effacerDonneesLocales() {
  for (const cle of [CLE_SPOTS, CLE_FAVORIS, CLE_ATTENTE, CLE_PROPRIETAIRE, "kelvisi-retours", "kelvisi-profil"]) supprimer(cle);
}
