// Comptes Kelvisi : inscription, connexion, session, profil (Supabase Auth, par son API REST).
//
// La session est gardée sur l'appareil. Hors connexion, une session expirée reste utilisable :
// on ne bloque jamais quelqu'un en mer parce que son jeton n'a pas pu être renouvelé.

import { CONFIG } from "./config.js";
import { lire, ecrire, supprimer } from "./stockage.js";

const CLE_SESSION = "kelvisi-session";
const MARGE_S = 60;

export const PRATIQUES = { chasse: "Chasse sous-marine", apnee: "Apnée", plongee: "Plongée bouteille", photo: "Photo sous-marine", randonnee: "Randonnée palmée" };
export const TRANCHES_AGE = ["15-17", "18-24", "25-34", "35-44", "45-54", "55-64", "65+"];

export function comptesActifs() {
  return Boolean(CONFIG.supabaseUrl && CONFIG.supabaseCleAnon && CONFIG.comptesOuverts);
}

export function session() {
  const s = lire(CLE_SESSION, null);
  return s && s.access_token && s.user ? s : null;
}

export function utilisateur() {
  return session()?.user || null;
}

function base() {
  return CONFIG.supabaseUrl.replace(/\/$/, "");
}

// Adresse où les liens reçus par e-mail ramènent (confirmation, nouveau mot de passe)
export function adresseRetour() {
  return location.href.split("#")[0].split("?")[0];
}

function entetes(jeton) {
  const e = { apikey: CONFIG.supabaseCleAnon, "Content-Type": "application/json" };
  if (jeton) e.Authorization = `Bearer ${jeton}`;
  else if (!CONFIG.supabaseCleAnon.startsWith("sb_")) e.Authorization = `Bearer ${CONFIG.supabaseCleAnon}`;
  return e;
}

export class ErreurCompte extends Error {
  constructor(message, code) {
    super(message);
    this.code = code;
  }
}

// Messages de Supabase traduits pour l'utilisateur
function traduire(statut, corps) {
  const code = corps?.error_code || corps?.code || corps?.error || "";
  const texte = `${corps?.msg || corps?.message || corps?.error_description || ""}`;
  const t = (m) => new ErreurCompte(m, code || String(statut));
  if (code === "invalid_credentials" || /invalid login credentials/i.test(texte)) return t("E-mail ou mot de passe incorrect.");
  if (code === "email_not_confirmed" || /email not confirmed/i.test(texte)) return new ErreurCompte("Confirme d'abord ton adresse : clique sur le lien reçu par e-mail.", "email_not_confirmed");
  if (code === "user_already_exists" || /already registered/i.test(texte)) return t("Un compte existe déjà avec cette adresse. Connecte-toi.");
  if (code === "weak_password" || /password/i.test(texte) && /(least|weak|short)/i.test(texte)) return t("Mot de passe trop faible : au moins 8 caractères, avec lettres et chiffres.");
  if (code === "email_address_invalid" || /invalid.*email|email.*invalid/i.test(texte)) return t("Adresse e-mail invalide.");
  if (code === "over_email_send_rate_limit" || statut === 429) return t("Trop de tentatives. Patiente quelques minutes puis réessaie.");
  if (code === "same_password") return t("Choisis un mot de passe différent de l'ancien.");
  if (code === "signup_disabled") return t("Les inscriptions sont fermées pour le moment.");
  if (statut >= 500) return t("Le service des comptes ne répond pas. Réessaie dans un moment.");
  return t(texte || `Erreur ${statut}`);
}

async function appel(chemin, { methode = "POST", corps, jeton } = {}) {
  let r;
  try {
    r = await fetch(`${base()}${chemin}`, {
      method: methode,
      headers: entetes(jeton),
      body: corps === undefined ? undefined : JSON.stringify(corps),
    });
  } catch (e) {
    throw new ErreurCompte("Pas de connexion internet.", "reseau");
  }
  const texte = await r.text();
  let donnees = null;
  try {
    donnees = texte ? JSON.parse(texte) : null;
  } catch (e) {
    donnees = null;
  }
  if (!r.ok) throw traduire(r.status, donnees);
  return donnees;
}

function memoriserSession(d, annoncer = true) {
  const s = {
    access_token: d.access_token,
    refresh_token: d.refresh_token,
    expires_at: d.expires_at || Math.floor(Date.now() / 1000) + (Number(d.expires_in) || 3600),
    user: { id: d.user.id, email: d.user.email },
  };
  ecrire(CLE_SESSION, s);
  if (annoncer) document.dispatchEvent(new CustomEvent("kelvisi-compte", { detail: { connecte: true } }));
  return s;
}

function oublierSession() {
  supprimer(CLE_SESSION);
  document.dispatchEvent(new CustomEvent("kelvisi-compte", { detail: { connecte: false } }));
}

// --- Inscription, connexion, mot de passe --------------------------------------------------------

export async function inscrire({ email, motDePasse, prenom, departement, pratiques, trancheAge, accordEmails }) {
  const d = await appel(`/auth/v1/signup?redirect_to=${encodeURIComponent(adresseRetour())}`, {
    corps: {
      email: email.trim(),
      password: motDePasse,
      data: {
        prenom: prenom.trim(),
        departement: departement.trim().toUpperCase(),
        pratiques,
        tranche_age: trancheAge,
        accord_emails: Boolean(accordEmails),
      },
    },
  });
  // Confirmation par e-mail activée : pas de session tant que le lien n'a pas été suivi
  if (d && d.access_token) {
    memoriserSession(d);
    return "connecte";
  }
  return "a_confirmer";
}

export async function connecter(email, motDePasse) {
  const d = await appel("/auth/v1/token?grant_type=password", { corps: { email: email.trim(), password: motDePasse } });
  return memoriserSession(d);
}

export async function renvoyerConfirmation(email) {
  await appel(`/auth/v1/resend?redirect_to=${encodeURIComponent(adresseRetour())}`, { corps: { type: "signup", email: email.trim() } });
}

export async function motDePasseOublie(email) {
  await appel(`/auth/v1/recover?redirect_to=${encodeURIComponent(adresseRetour())}`, { corps: { email: email.trim() } });
}

export async function changerMotDePasse(nouveau) {
  const j = await jeton();
  if (!j) throw new ErreurCompte("Connexion internet nécessaire pour changer de mot de passe.", "reseau");
  await appel("/auth/v1/user", { methode: "PUT", corps: { password: nouveau }, jeton: j });
}

export async function deconnecter() {
  const s = session();
  if (s) {
    try {
      await appel("/auth/v1/logout", { jeton: s.access_token });
    } catch (e) {
      /* la session est oubliée sur l'appareil quoi qu'il arrive */
    }
  }
  oublierSession();
}

// Jeton valide pour appeler l'API, renouvelé si besoin. Null si non connecté ou hors connexion.
let renouvellement = null;
export async function jeton() {
  const s = session();
  if (!s) return null;
  if (s.expires_at - MARGE_S > Date.now() / 1000) return s.access_token;
  if (!renouvellement) {
    renouvellement = (async () => {
      try {
        const d = await appel("/auth/v1/token?grant_type=refresh_token", { corps: { refresh_token: s.refresh_token } });
        return memoriserSession(d, false).access_token;
      } catch (e) {
        // Jeton de renouvellement refusé (compte supprimé, session révoquée) : il faut se reconnecter
        if (e.code !== "reseau" && !/^5\d\d$/.test(e.code)) oublierSession();
        return null;
      } finally {
        setTimeout(() => { renouvellement = null; }, 0);
      }
    })();
  }
  return renouvellement;
}

// --- Liens reçus par e-mail --------------------------------------------------------------------

// À appeler au démarrage, avant la navigation : lit les jetons laissés dans l'adresse par
// un lien de confirmation ou de nouveau mot de passe. Renvoie { type } ou { erreur } ou null.
export async function traiterLienRecu() {
  const h = location.hash.replace(/^#/, "");
  if (!/(^|&)(access_token|error)=/.test(h)) return null;
  const p = new URLSearchParams(h);
  history.replaceState(null, "", `${location.pathname}${location.search}#/carte`);
  if (p.get("error")) {
    const expire = /expired/i.test(p.get("error_code") || "") || /expired/i.test(p.get("error_description") || "");
    return { erreur: expire ? "Ce lien a expiré. Demande un nouvel e-mail." : "Ce lien n'est plus valable." };
  }
  const accessToken = p.get("access_token");
  try {
    const user = await appel("/auth/v1/user", { methode: "GET", jeton: accessToken });
    memoriserSession({
      access_token: accessToken,
      refresh_token: p.get("refresh_token"),
      expires_at: Number(p.get("expires_at")) || undefined,
      expires_in: p.get("expires_in"),
      user,
    });
    return { type: p.get("type") || "signup" };
  } catch (e) {
    return { erreur: "Impossible de valider ce lien. Réessaie de te connecter." };
  }
}

// --- Données du compte (API REST de la base, protégée par les règles d'accès) --------------------

export async function requete(chemin, { methode = "GET", corps, prefer } = {}) {
  const j = await jeton();
  if (!j) throw new ErreurCompte("Connexion nécessaire.", "reseau");
  const e = entetes(j);
  if (prefer) e.Prefer = prefer;
  let r;
  try {
    r = await fetch(`${base()}/rest/v1/${chemin}`, { method: methode, headers: e, body: corps === undefined ? undefined : JSON.stringify(corps) });
  } catch (err) {
    throw new ErreurCompte("Pas de connexion internet.", "reseau");
  }
  const texte = await r.text();
  const d = texte ? JSON.parse(texte) : null;
  if (!r.ok) throw new ErreurCompte(d?.message || `Erreur ${r.status}`, d?.code || String(r.status));
  return d;
}

export async function lireProfil() {
  const u = utilisateur();
  if (!u) return null;
  const lignes = await requete(`profils?id=eq.${u.id}&select=prenom,departement,pratiques,tranche_age,accord_emails,accord_emails_le,cree_le`);
  const profil = lignes?.[0] || null;
  if (profil) ecrire("kelvisi-profil", profil);
  return profil;
}

export function profilEnMemoire() {
  return lire("kelvisi-profil", null);
}

export async function modifierProfil(champs) {
  const u = utilisateur();
  const lignes = await requete(`profils?id=eq.${u.id}`, { methode: "PATCH", corps: champs, prefer: "return=representation" });
  if (lignes?.[0]) ecrire("kelvisi-profil", lignes[0]);
  return lignes?.[0];
}

export async function supprimerCompte() {
  await requete("rpc/supprimer_mon_compte", { methode: "POST", corps: {} });
  oublierSession();
}

// --- Vérifications des formulaires ------------------------------------------------------------

export function verifierMotDePasse(m) {
  if (m.length < 8) return "Au moins 8 caractères.";
  if (!/[A-Za-z]/.test(m) || !/\d/.test(m)) return "Mélange des lettres et des chiffres.";
  return null;
}

export function verifierDepartement(d) {
  const v = d.trim().toUpperCase();
  return /^(0[1-9]|[1-8][0-9]|9[0-5]|2A|2B|97[1-6]|99)$/.test(v) ? null : "Numéro de département, par exemple 29, 2A ou 974 (99 si tu vis à l'étranger).";
}
