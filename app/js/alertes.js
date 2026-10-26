// Alertes sur les favoris et les spots privés : une notification quand la visibilité prévue atteint
// le seuil choisi par l'utilisateur, en mètres.
//
// Le seuil est gardé sur l'appareil et sur le compte (colonne « alerte_m » des favoris et des spots) ;
// l'appareil s'abonne aux notifications de son navigateur (Web Push), et le calcul horaire envoie
// les alertes (outils/alertes.py). La clé publique des notifications est dans donnees/push.json :
// sans ce fichier, les alertes ne sont pas encore en service.

import { lire, ecrire, supprimer } from "./stockage.js";
import { comptesActifs, requete, utilisateur } from "./compte.js";

const CLE = "kelvisi-alertes";
// Seuils proposés (mètres de visibilité sur le meilleur créneau du jour)
export const SEUILS_M = [2, 3, 4, 5, 6, 7, 8, 10, 12, 15, 18, 20, 25];
const seuilValide = (v) => Number.isFinite(v) && v >= 1 && v <= 40;
export const texteSeuil = (m) => `à partir de ${String(m).replace(".", ",")} m`;

let config = null;

export class ErreurAlerte extends Error {
  constructor(message, code) {
    super(message);
    this.code = code;
  }
}

// { identifiant du favori ou du spot: seuil en mètres }
export function alertes() {
  const a = lire(CLE, {});
  return a && typeof a === "object" && !Array.isArray(a) ? Object.fromEntries(Object.entries(a).filter(([, v]) => seuilValide(v))) : {};
}

export function seuilAlerte(id) {
  return alertes()[id] || null;
}

export function remplacerAlertes(table) {
  ecrire(CLE, table);
}

export function oublierAlertes() {
  supprimer(CLE);
}

// Clé publique des notifications ; null si les alertes ne sont pas encore en service (fichier absent,
// ou base qui ne connaît pas encore les seuils en mètres)
export function alertesDisponibles() {
  if (!config) {
    config = fetch("donnees/push.json", { cache: "no-cache" })
      .then((r) => (r.ok ? r.json() : null))
      .then((c) => (c && c.cle_publique && c.seuils_m ? c.cle_publique : null))
      .catch(() => null);
    config.then((c) => { if (!c) config = null; });
  }
  return config;
}

export function notificationsPossibles() {
  return "serviceWorker" in navigator && "PushManager" in window && "Notification" in window;
}

function surIphone() {
  return /iPhone|iPad|iPod/.test(navigator.userAgent || "");
}

function octets(b64) {
  const s = atob(b64.replace(/-/g, "+").replace(/_/g, "/") + "=".repeat((4 - (b64.length % 4)) % 4));
  return Uint8Array.from(s, (c) => c.charCodeAt(0));
}

function b64(tampon) {
  return btoa(String.fromCharCode(...new Uint8Array(tampon))).replace(/\+/g, "-").replace(/\//g, "_").replace(/=+$/, "");
}

// Abonne l'appareil (ou retrouve son abonnement) et l'enregistre sur le compte
export async function abonnerAppareil({ demander = true } = {}) {
  const cle = await alertesDisponibles();
  if (!cle) throw new ErreurAlerte("Les alertes ne sont pas encore en service.", "indisponible");
  if (!notificationsPossibles()) {
    throw new ErreurAlerte(surIphone()
      ? "Sur iPhone, ajoute d'abord Kelvisi à l'écran d'accueil (bouton Partager, puis « Sur l'écran d'accueil ») et ouvre-le depuis son icône."
      : "Ce navigateur ne sait pas recevoir de notifications.", "navigateur");
  }
  let permission = Notification.permission;
  if (permission === "default" && demander) permission = await Notification.requestPermission();
  if (permission !== "granted") {
    throw new ErreurAlerte("Les notifications sont bloquées pour Kelvisi : autorise-les dans les réglages du navigateur.", "refus");
  }
  const enregistrement = await navigator.serviceWorker.ready;
  let abonnement = await enregistrement.pushManager.getSubscription();
  if (abonnement && abonnement.options?.applicationServerKey && b64(abonnement.options.applicationServerKey) !== cle) {
    await abonnement.unsubscribe(); // clés de Kelvisi changées : nouvel abonnement
    abonnement = null;
  }
  if (!abonnement) abonnement = await enregistrement.pushManager.subscribe({ userVisibleOnly: true, applicationServerKey: octets(cle) });
  const u = utilisateur();
  await requete("abonnements_push?on_conflict=proprietaire,endpoint", {
    methode: "POST",
    prefer: "resolution=merge-duplicates,return=minimal",
    corps: [{ proprietaire: u.id, endpoint: abonnement.endpoint, p256dh: b64(abonnement.getKey("p256dh")), auth: b64(abonnement.getKey("auth")) }],
  });
  return abonnement;
}

// Active, modifie ou retire l'alerte d'un favori ou d'un spot (seuil null : plus d'alerte)
export async function choisirAlerte(id, seuil, noter) {
  if (seuil !== null && !seuilValide(seuil)) throw new ErreurAlerte("Choisis un seuil entre 1 et 40 m.", "seuil");
  if (seuil !== null) {
    if (!comptesActifs() || !utilisateur()) throw new ErreurAlerte("Connecte-toi pour recevoir des alertes.", "compte");
    await abonnerAppareil();
  }
  const a = alertes();
  if (seuil !== null) a[id] = seuil;
  else delete a[id];
  ecrire(CLE, a);
  noter(id, seuil ?? "aucune");
}

// Au démarrage : l'abonnement de l'appareil est renouvelé s'il a disparu (sans rien demander)
export async function verifierAbonnement() {
  if (!Object.keys(alertes()).length || !comptesActifs() || !utilisateur() || !notificationsPossibles()) return;
  if (Notification.permission !== "granted") return;
  try {
    await abonnerAppareil({ demander: false });
  } catch (e) {
    /* hors connexion ou alertes indisponibles : nouvel essai au prochain démarrage */
  }
}

// À la déconnexion : cet appareil ne reçoit plus les alertes du compte
export async function desabonnerAppareil() {
  if (!notificationsPossibles()) return;
  try {
    const enregistrement = await navigator.serviceWorker.getRegistration();
    const abonnement = await enregistrement?.pushManager.getSubscription();
    if (!abonnement) return;
    try {
      await requete(`abonnements_push?endpoint=eq.${encodeURIComponent(`"${abonnement.endpoint}"`)}`, { methode: "DELETE" });
    } finally {
      await abonnement.unsubscribe();
    }
  } catch (e) {
    /* sans réseau : l'abonnement expirera côté serveur au premier envoi refusé */
  }
}
