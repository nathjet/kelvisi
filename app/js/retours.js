// Retours terrain : « j'y étais, j'avais X m ».
// Points publics : envoyés au serveur de retours (Supabase) s'il est configuré, sinon gardés ici.
// Spots privés : toujours gardés sur l'appareil, ils corrigent la prévision de ce spot.

import { CONFIG } from "./config.js";
import { lire, ecrire, appareil } from "./stockage.js";

const CLE = "kelvisi-retours";

export function partageActif() {
  return Boolean(CONFIG.supabaseUrl && CONFIG.supabaseCleAnon);
}

export function tousLesRetours() {
  return lire(CLE, []);
}

export function retoursDuSpot(spotId) {
  return tousLesRetours().filter((r) => r.spot_id === spotId);
}

// Format attendu par le moteur pour corriger un spot privé
export function rapportsPourMoteur(spotId) {
  return retoursDuSpot(spotId)
    .filter((r) => r.prevision_m > 0)
    .map((r) => ({ temps: Math.floor(Date.parse(r.observe_le) / 1000), visibilite_m: r.visibilite_m, utilisateur: "moi", prevision_m: r.prevision_m }));
}

// Clé « publishable » (sb_publishable_…) : en-tête apikey seul. Ancienne clé « anon » (JWT) : apikey et Authorization.
export function entetesSupabase(cle) {
  const entetes = { apikey: cle, "Content-Type": "application/json", Prefer: "return=minimal" };
  if (!cle.startsWith("sb_")) entetes.Authorization = `Bearer ${cle}`;
  return entetes;
}

async function envoyer(retour) {
  const r = await fetch(`${CONFIG.supabaseUrl.replace(/\/$/, "")}/rest/v1/rapports`, {
    method: "POST",
    headers: entetesSupabase(CONFIG.supabaseCleAnon),
    body: JSON.stringify({
      spot_id: retour.spot_id,
      visibilite_m: retour.visibilite_m,
      prevision_m: retour.prevision_m,
      observe_le: retour.observe_le,
      appareil: appareil(),
      version: "1",
    }),
  });
  if (!r.ok) throw new Error(`Envoi refusé (${r.status})`);
}

// Enregistre un retour ; renvoie « partage », « attente » (hors ligne, sera renvoyé) ou « local »
export async function enregistrerRetour({ spotId, prive, visibilite, observeLe, prevision }) {
  const retour = {
    spot_id: spotId,
    prive: Boolean(prive),
    visibilite_m: visibilite,
    observe_le: new Date(observeLe * 1000).toISOString(),
    prevision_m: prevision ?? null,
    envoye: false,
  };
  const liste = tousLesRetours();
  liste.push(retour);
  ecrire(CLE, liste.slice(-300));
  if (prive || !partageActif()) return "local";
  try {
    await envoyer(retour);
    marquerEnvoye(retour);
    return "partage";
  } catch (e) {
    return "attente";
  }
}

function marquerEnvoye(retour) {
  const liste = tousLesRetours();
  const r = liste.find((x) => x.spot_id === retour.spot_id && x.observe_le === retour.observe_le && !x.envoye);
  if (r) r.envoye = true;
  ecrire(CLE, liste);
}

// Renvoie les retours publics restés en attente (pas de réseau au moment de la saisie)
export async function renvoyerEnAttente() {
  if (!partageActif() || !navigator.onLine) return;
  const limite = Date.now() - 3 * 86400 * 1000; // le serveur refuse les retours de plus de 3 jours
  for (const r of tousLesRetours().filter((x) => !x.prive && !x.envoye && Date.parse(x.observe_le) > limite)) {
    try {
      await envoyer(r);
      marquerEnvoye(r);
    } catch (e) {
      return;
    }
  }
}

export function supprimerRetoursDuSpot(spotId) {
  ecrire(CLE, tousLesRetours().filter((r) => r.spot_id !== spotId));
}
