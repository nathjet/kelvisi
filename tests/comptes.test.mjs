// Test de bout en bout des comptes, dans un navigateur simulé (jsdom), avec un faux serveur Supabase
// qui applique les mêmes règles que supabase/schema.sql (chacun ne voit que ses données).
//
// Usage : node tests/comptes.test.mjs   (lance les parcours « parcours », « lien », « expire », « partage » et « alertes »)

import { readFileSync, existsSync } from "node:fs";
import { fileURLToPath, pathToFileURL } from "node:url";
import { dirname, join } from "node:path";
import { spawnSync } from "node:child_process";
import assert from "node:assert/strict";
import { JSDOM } from "jsdom";

const ICI = dirname(fileURLToPath(import.meta.url));
const APP = join(ICI, "..", "app");
const mode = process.argv[2];

if (!mode) {
  let echec = false;
  for (const m of ["parcours", "lien", "expire", "partage", "alertes"]) {
    const r = spawnSync(process.execPath, [fileURLToPath(import.meta.url), m], { encoding: "utf8" });
    process.stdout.write(r.stdout);
    process.stderr.write(r.stderr);
    if (r.status !== 0) echec = true;
  }
  process.exit(echec ? 1 : 0);
}

// --- Faux serveur Supabase ------------------------------------------------------------------------

const BASE = "https://supabase.test";
const serveur = { utilisateurs: [], profils: new Map(), spots: [], favoris: [], rapports: [], appels: [], abonnements: [],
  // Partage des spots installé sur la base (script SQL appliqué) : seulement dans le parcours « partage »
  partageActif: mode === "partage",
  // Alertes installées (script SQL appliqué, clés publiées dans donnees/push.json) : parcours « alertes »
  alertesActives: mode === "alertes" };
const CLE_PUSH = "BCVxsr7N_eNgVRqvHtD0zTZsEc6-VV-JvLexhqUzORcxaOzi6-AYWXvTBHm4bjyPjs7Vd8pZGH6SRpkNtoIAiw4";
const CARACTERISTIQUES = ["nom", "lat", "lon", "orientation_deg", "ouverture_deg", "profondeur_m", "fond"];
let compteur = 0;

function creerUtilisateur(email, motDePasse, meta = {}, confirme = false) {
  const u = { id: `0000000${++compteur}-aaaa-bbbb-cccc-dddddddddddd`, email, motDePasse, meta, confirme };
  serveur.utilisateurs.push(u);
  serveur.profils.set(u.id, {
    prenom: meta.prenom || null, departement: meta.departement || null, pratiques: meta.pratiques || [],
    tranche_age: meta.tranche_age || null, accord_emails: Boolean(meta.accord_emails), accord_emails_le: meta.accord_emails ? new Date().toISOString() : null,
    cree_le: new Date().toISOString(),
  });
  return u;
}

const jetons = (u) => ({
  access_token: `acc-${u.id}-${++compteur}`, refresh_token: `ref-${u.id}`, expires_in: 3600,
  expires_at: Math.floor(Date.now() / 1000) + 3600, token_type: "bearer", user: { id: u.id, email: u.email },
});

function utilisateurDuJeton(entetes) {
  const m = /^Bearer acc-(.+)-\d+$/.exec(entetes?.Authorization || "");
  return m ? serveur.utilisateurs.find((u) => u.id === m[1]) || null : null;
}

const reponse = (donnees, statut = 200) => ({
  ok: statut >= 200 && statut < 300, status: statut,
  text: async () => (donnees === undefined || donnees === null ? "" : JSON.stringify(donnees)),
  json: async () => donnees,
});

function filtreIn(url, champ) {
  const m = new RegExp(`${champ}=in\\.\\(([^)]*)\\)`).exec(decodeURIComponent(url));
  return m ? m[1].split(",").map((x) => x.replace(/"/g, "")) : [];
}

function supabase(url, options) {
  const methode = options.method || "GET";
  const corps = options.body ? JSON.parse(options.body) : null;
  const chemin = url.slice(BASE.length);
  serveur.appels.push(`${methode} ${chemin.split("?")[0]}`);
  assert.equal(options.headers.apikey, "sb_publishable_test", "clé publique envoyée");

  if (chemin.startsWith("/auth/v1/signup")) {
    if (serveur.utilisateurs.some((u) => u.email === corps.email)) return reponse({ id: "faux", email: corps.email });
    const u = creerUtilisateur(corps.email, corps.password, corps.data);
    return reponse({ id: u.id, email: u.email, confirmation_sent_at: new Date().toISOString() });
  }
  if (chemin.startsWith("/auth/v1/token?grant_type=password")) {
    const u = serveur.utilisateurs.find((x) => x.email === corps.email);
    if (!u || u.motDePasse !== corps.password) return reponse({ error_code: "invalid_credentials", msg: "Invalid login credentials" }, 400);
    if (!u.confirme) return reponse({ error_code: "email_not_confirmed", msg: "Email not confirmed" }, 400);
    return reponse(jetons(u));
  }
  if (chemin.startsWith("/auth/v1/token?grant_type=refresh_token")) {
    const u = serveur.utilisateurs.find((x) => `ref-${x.id}` === corps.refresh_token);
    return u ? reponse(jetons(u)) : reponse({ error_code: "refresh_token_not_found" }, 400);
  }
  if (chemin.startsWith("/auth/v1/recover") || chemin.startsWith("/auth/v1/resend")) return reponse({});
  if (chemin.startsWith("/auth/v1/logout")) return reponse(null, 204);

  const u = utilisateurDuJeton(options.headers);
  if (!u) return reponse({ code: "401", message: "JWT manquant" }, 401);

  if (chemin.startsWith("/auth/v1/user")) {
    if (methode === "PUT") u.motDePasse = corps.password;
    return reponse({ id: u.id, email: u.email });
  }
  if (chemin.startsWith("/rest/v1/profils")) {
    const p = serveur.profils.get(u.id);
    if (methode === "PATCH") Object.assign(p, corps, { accord_emails_le: corps.accord_emails ? new Date().toISOString() : null });
    return reponse([p]);
  }
  if (chemin.startsWith("/rest/v1/spots_prives")) {
    // Sans le script de partage, la base ne connaît pas la colonne « partage » : elle refuse la requête
    const colonneInconnue = reponse({ code: "PGRST204", message: "Could not find the 'partage' column of 'spots_prives'" }, 400);
    if (!serveur.alertesActives && /alerte/.test(decodeURIComponent(chemin) + JSON.stringify(corps || ""))) {
      return reponse({ code: "PGRST204", message: "Could not find the 'alerte' column of 'spots_prives'" }, 400);
    }
    if (methode === "PATCH") {
      assert.deepEqual(Object.keys(corps), ["alerte"], "seule l'alerte change par ce chemin");
      const ids = filtreIn(url, "id");
      for (const sp of serveur.spots) if (sp.proprietaire === u.id && ids.includes(sp.id)) sp.alerte = corps.alerte;
      return reponse(null, 204);
    }
    if (methode === "GET") {
      if (!serveur.partageActif && /partage/.test(decodeURIComponent(chemin))) return colonneInconnue;
      return reponse(serveur.spots.filter((s) => s.proprietaire === u.id).map(({ proprietaire, ...s }) => s));
    }
    if (methode === "POST") {
      if (!serveur.partageActif && corps.some((s) => "partage" in s)) return colonneInconnue;
      for (const s of corps) {
        assert.equal(s.proprietaire, u.id, "spot déposé au nom du compte");
        const ancien = serveur.spots.find((x) => x.proprietaire === u.id && x.id === s.id);
        if (serveur.partageActif) {
          // Mêmes règles que le déclencheur spots_partage de supabase/schema.sql
          const demande = s.partage ?? ancien?.partage ?? "prive";
          const inchange = ancien && CARACTERISTIQUES.every((c) => ancien[c] === s[c]);
          s.partage = demande === "prive" ? "prive"
            : ancien && ["publie", "refuse"].includes(ancien.partage) && inchange ? ancien.partage : "en_attente";
          s.partage_id = ancien?.partage_id || `uuid-${++compteur}`;
        }
        serveur.spots = serveur.spots.filter((x) => !(x.proprietaire === u.id && x.id === s.id));
        serveur.spots.push(s);
      }
      return reponse(null, 201);
    }
    if (methode === "DELETE") {
      const ids = filtreIn(url, "id");
      serveur.spots = serveur.spots.filter((x) => !(x.proprietaire === u.id && ids.includes(x.id)));
      return reponse(null, 204);
    }
  }
  if (chemin.startsWith("/rest/v1/favoris")) {
    if (!serveur.alertesActives && /alerte/.test(decodeURIComponent(chemin) + JSON.stringify(corps || ""))) {
      return reponse({ code: "PGRST204", message: "Could not find the 'alerte' column of 'favoris'" }, 400);
    }
    if (methode === "GET") {
      return reponse(serveur.favoris.filter((f) => f.proprietaire === u.id)
        .map((f) => (/alerte/.test(chemin) ? { point_id: f.point_id, alerte: f.alerte ?? null } : { point_id: f.point_id })));
    }
    if (methode === "PATCH") {
      assert.deepEqual(Object.keys(corps), ["alerte"], "seule l'alerte d'un favori est modifiable");
      assert.ok([null, "bonne", "excellente"].includes(corps.alerte), "niveau d'alerte valide");
      const ids = filtreIn(url, "point_id");
      for (const f of serveur.favoris) if (f.proprietaire === u.id && ids.includes(f.point_id)) f.alerte = corps.alerte;
      return reponse(null, 204);
    }
    if (methode === "POST") {
      for (const f of corps) if (!serveur.favoris.some((x) => x.proprietaire === u.id && x.point_id === f.point_id)) serveur.favoris.push(f);
      return reponse(null, 201);
    }
    if (methode === "DELETE") {
      const ids = filtreIn(url, "point_id");
      serveur.favoris = serveur.favoris.filter((x) => !(x.proprietaire === u.id && ids.includes(x.point_id)));
      return reponse(null, 204);
    }
  }
  if (chemin.startsWith("/rest/v1/abonnements_push")) {
    if (methode === "POST") {
      for (const a of corps) {
        assert.equal(a.proprietaire, u.id, "appareil abonné au nom du compte");
        assert.match(a.endpoint, /^https:\/\//);
        assert.ok(a.p256dh.length > 20 && a.auth.length >= 8, "clés de chiffrement de l'appareil");
        serveur.abonnements = serveur.abonnements.filter((x) => !(x.proprietaire === u.id && x.endpoint === a.endpoint));
        serveur.abonnements.push(a);
      }
      return reponse(null, 201);
    }
    if (methode === "DELETE") {
      const m = /endpoint=eq\.(.+)$/.exec(decodeURIComponent(chemin));
      const endpoint = m ? m[1].replace(/^"|"$/g, "") : null;
      serveur.abonnements = serveur.abonnements.filter((x) => !(x.proprietaire === u.id && x.endpoint === endpoint));
      return reponse(null, 204);
    }
  }
  if (chemin.startsWith("/rest/v1/rapports")) {
    serveur.rapports.push({ ...corps, utilisateur: u.id });
    return reponse(null, 201);
  }
  if (chemin.startsWith("/rest/v1/rpc/spots_communaute")) {
    if (!serveur.partageActif) return reponse({ code: "PGRST202", message: "Could not find the function public.spots_communaute" }, 404);
    return reponse(serveur.spots.filter((s) => s.partage === "publie").map((s) => ({
      id: s.partage_id, nom: s.nom, lat: s.lat, lon: s.lon, region: s.region, orientation_deg: s.orientation_deg,
      ouverture_deg: s.ouverture_deg, profondeur_m: s.profondeur_m, fond: s.fond, publie_le: s.maj_le,
    })));
  }
  if (chemin.startsWith("/rest/v1/rpc/supprimer_mon_compte")) {
    serveur.utilisateurs = serveur.utilisateurs.filter((x) => x.id !== u.id);
    serveur.spots = serveur.spots.filter((x) => x.proprietaire !== u.id);
    serveur.favoris = serveur.favoris.filter((x) => x.proprietaire !== u.id);
    serveur.abonnements = serveur.abonnements.filter((x) => x.proprietaire !== u.id);
    serveur.profils.delete(u.id);
    return reponse(null, 204);
  }
  return reponse({ message: `Route inconnue ${chemin}` }, 404);
}

// --- Autres services (météo, profondeur) -----------------------------------------------------------

const fixture = JSON.parse(readFileSync(join(ICI, "fixtures", "conditions_reelles_quiberon.json"), "utf8"));
const MARINE = {
  wave_height: "hauteur_vagues", wave_period: "periode_vagues", wave_direction: "direction_vagues",
  swell_wave_height: "hauteur_houle", swell_wave_period: "periode_houle", swell_wave_direction: "direction_houle",
  wind_wave_height: "hauteur_mer_vent", wind_wave_period: "periode_mer_vent", wind_wave_direction: "direction_mer_vent",
  ocean_current_velocity: "courant", ocean_current_direction: "direction_courant",
  sea_level_height_msl: "niveau_mer", sea_surface_temperature: "temperature_eau",
};
const METEO = { wind_speed_10m: "vent", wind_direction_10m: "direction_vent", wind_gusts_10m: "rafales", precipitation: "pluie", cloud_cover: "nebulosite" };
const KMH = new Set(["courant", "vent", "rafales"]);
const decalage = Math.floor(Date.now() / 1000 / 3600) * 3600 - 5 * 86400 - fixture.temps[0];
function reponseOpenMeteo(table) {
  const hourly = { time: fixture.temps.map((t) => t + decalage) };
  for (const [api, nom] of Object.entries(table)) hourly[api] = fixture.series[nom].map((v) => (v === null ? null : KMH.has(nom) ? v * 3.6 : v));
  return { latitude: fixture.lat, longitude: fixture.lon, hourly };
}

async function fauxFetch(entree, options = {}) {
  const url = String(entree);
  if (url.startsWith(BASE)) return supabase(url, options);
  if (url.startsWith("donnees/push.json")) return serveur.alertesActives ? reponse({ cle_publique: CLE_PUSH }) : reponse(null, 404);
  if (url.startsWith("donnees/")) {
    const chemin = join(APP, decodeURIComponent(url.split("?")[0]));
    return existsSync(chemin) ? reponse(JSON.parse(readFileSync(chemin, "utf8"))) : reponse(null, 404);
  }
  if (url.includes("marine-api.open-meteo.com")) return reponse(reponseOpenMeteo(MARINE));
  if (url.includes("api.open-meteo.com")) return reponse(reponseOpenMeteo(METEO));
  return reponse(null, 404);
}

class FausseCarte {
  constructor(o) { this.gest = {}; this.zoom = 5; this.conteneur = o.container; }
  on(ev, f) { (this.gest[ev] ||= []).push(f); }
  addControl() {}
  getZoom() { return this.zoom; }
  getContainer() { return this.conteneur; }
  getStyle() { return { layers: [] }; }
  isStyleLoaded() { return true; }
  setStyle() {}
  getSource() { return null; }
  addSource() {}
  addLayer() {}
  getLayer() { return null; }
  setLayoutProperty() {}
  queryRenderedFeatures() { return []; }
  flyTo() {}
  resize() {}
}
class FauxRepere {
  constructor({ element }) { this.element = element; element.classList.add("maplibregl-marker"); }
  setLngLat() { return this; }
  addTo(c) { c.conteneur.appendChild(this.element); return this; }
  remove() { this.element.remove(); }
}

// --- Navigateur simulé ------------------------------------------------------------------------------

const ADRESSES = {
  parcours: "https://kelvisi.test/",
  partage: "https://kelvisi.test/",
  alertes: "https://kelvisi.test/",
  lien: "https://kelvisi.test/#access_token=PLACEHOLDER&expires_in=3600&refresh_token=REFRESH&token_type=bearer&type=recovery",
  expire: "https://kelvisi.test/#error=access_denied&error_code=otp_expired&error_description=Email+link+is+invalid+or+has+expired",
};
let adresse = ADRESSES[mode];
if (mode === "lien") {
  const u = creerUtilisateur("oubli@exemple.fr", "ancienmdp1", { prenom: "Lou" }, true);
  adresse = adresse.replace("PLACEHOLDER", jetons(u).access_token).replace("REFRESH", `ref-${u.id}`);
}

const html = readFileSync(join(APP, "index.html"), "utf8").replace(/<script[^>]*><\/script>/g, "");
const dom = new JSDOM(html, { url: adresse, pretendToBeVisual: true });
const w = dom.window;
w.matchMedia = (q) => ({ matches: false, media: q, addEventListener() {}, removeEventListener() {} });
w.maplibregl = { Map: FausseCarte, Marker: FauxRepere, NavigationControl: class {}, GeolocateControl: class {}, ScaleControl: class {} };
w.fetch = fauxFetch;
w.scrollTo = () => {};
w.HTMLElement.prototype.scrollIntoView = () => {};
for (const nom of ["window", "document", "location", "localStorage", "history", "HTMLElement", "Event", "CustomEvent", "AbortController", "FormData"]) {
  globalThis[nom] = w[nom];
}
// Notifications du navigateur (Web Push) : permission et abonnement simulés
const push = { reponse: "granted", abonnement: null, demandes: 0 };
w.Notification = class { static permission = "default"; static async requestPermission() { push.demandes++; w.Notification.permission = push.reponse; return push.reponse; } };
w.PushManager = class {};
const enregistrementSw = {
  pushManager: {
    getSubscription: async () => push.abonnement,
    subscribe: async ({ userVisibleOnly, applicationServerKey }) => {
      assert.ok(userVisibleOnly, "notifications toujours visibles");
      assert.equal(applicationServerKey.length, 65, "clé publique de Kelvisi décodée");
      push.abonnement = {
        endpoint: "https://push.test/appareil-1", options: { applicationServerKey: applicationServerKey.buffer },
        getKey: (n) => new Uint8Array(n === "p256dh" ? 65 : 16).fill(7).buffer,
        unsubscribe: async () => { push.abonnement = null; return true; },
      };
      return push.abonnement;
    },
  },
};
Object.defineProperty(w.navigator, "serviceWorker", { configurable: true, value: {
  register: async () => enregistrementSw, ready: Promise.resolve(enregistrementSw), getRegistration: async () => enregistrementSw,
} });
globalThis.Notification = w.Notification;
Object.defineProperty(globalThis, "navigator", { value: w.navigator, configurable: true, writable: true });
globalThis.fetch = fauxFetch;
globalThis.requestAnimationFrame = (f) => setTimeout(f, 0);
w.requestAnimationFrame = globalThis.requestAnimationFrame;

const d = w.document;
const attendre = (ms = 30) => new Promise((ok) => setTimeout(ok, ms));
async function jusqua(condition, message, delai = 3000) {
  const debut = Date.now();
  while (Date.now() - debut < delai) {
    if (condition()) return;
    await attendre(20);
  }
  throw new Error(`Délai dépassé : ${message}`);
}
const ecran = () => d.getElementById("ecran-compte");
const panneau = () => d.getElementById("panneau");
const texte = (el) => (el ? el.textContent.replace(/\s+/g, " ").trim() : "");
function remplir(form, valeurs) {
  for (const [nom, v] of Object.entries(valeurs)) {
    const champs = form.querySelectorAll(`[name="${nom}"]`);
    if (Array.isArray(v)) champs.forEach((c) => { c.checked = v.includes(c.value); });
    else if (typeof v === "boolean") champs[0].checked = v;
    else champs[0].value = v;
  }
}
const soumettre = (form) => form.dispatchEvent(new w.Event("submit", { cancelable: true }));
const erreurs = [];
w.addEventListener("error", (e) => erreurs.push(e.message));
process.on("unhandledRejection", (e) => erreurs.push(String(e)));

const etapes = [];
async function etape(nom, f) {
  try {
    await f();
    etapes.push(`  ok  ${nom}`);
  } catch (e) {
    etapes.push(`  ÉCHEC ${nom} : ${e.message}`);
    process.exitCode = 1;
  }
}

// Supabase configuré avant le démarrage : les comptes sont obligatoires
const { CONFIG } = await import(pathToFileURL(join(APP, "js", "config.js")).href);
CONFIG.supabaseUrl = BASE;
CONFIG.supabaseCleAnon = "sb_publishable_test";
CONFIG.comptesOuverts = true;

if (mode === "parcours") {
  // Un spot et un favori créés avant l'existence des comptes : ils doivent rejoindre le compte
  w.localStorage.setItem("kelvisi-spots", JSON.stringify([{ id: "prive-ancien", nom: "Ma crique", lat: 47.49, lon: -3.2, region: "atlantique",
    orientation_deg: 270, ouverture_deg: 90, profondeur_m: 8, fond: "roche", prive: true, cree_le: new Date().toISOString() }]));
  w.localStorage.setItem("kelvisi-favoris", JSON.stringify(["ref-groix"]));
}

await import(pathToFileURL(join(APP, "js", "app.js")).href);

if (mode === "parcours") {
  await etape("écran d'inscription obligatoire au démarrage", async () => {
    await jusqua(() => !ecran().hidden && /Créer mon compte/.test(texte(ecran())), "écran de compte");
    assert.ok(d.body.classList.contains("compte-requis"));
    assert.ok(ecran().querySelector('input[name="accord_emails"]') && !ecran().querySelector('input[name="accord_emails"]').checked, "accord e-mails non coché par défaut");
  });

  await etape("inscription : contrôles du formulaire", async () => {
    const form = ecran().querySelector("form");
    const essai = async (valeurs, attendu) => {
      remplir(form, valeurs);
      soumettre(form);
      await jusqua(() => attendu.test(texte(ecran().querySelector("[data-message]"))), `message ${attendu}`);
    };
    await essai({ email: "nathan@exemple.fr", mot_de_passe: "court" }, /Mot de passe/);
    await essai({ mot_de_passe: "visibilite29", prenom: "Nathan", departement: "999" }, /département/i);
    await essai({ departement: "29" }, /pratique/);
    await essai({ pratiques: ["chasse", "apnee"] }, /tranche d'âge/);
    await essai({ tranche_age: "18-24" }, /conditions d'utilisation/);
    assert.equal(serveur.utilisateurs.length, 0, "rien envoyé tant que le formulaire est incomplet");
  });

  await etape("inscription envoyée, confirmation par e-mail demandée", async () => {
    const form = ecran().querySelector("form");
    remplir(form, { cgu: true, accord_emails: true });
    soumettre(form);
    await jusqua(() => /Vérifie ta boîte mail/.test(texte(ecran())), "écran de confirmation");
    assert.match(texte(ecran()), /nathan@exemple\.fr/);
    const u = serveur.utilisateurs[0];
    assert.deepEqual(u.meta, { prenom: "Nathan", departement: "29", pratiques: ["chasse", "apnee"], tranche_age: "18-24", accord_emails: true });
  });

  await etape("connexion refusée : mauvais mot de passe, puis adresse non confirmée", async () => {
    ecran().querySelector('[data-mode="connexion"]').click();
    let form = ecran().querySelector("form");
    assert.equal(form.querySelector('input[name="email"]').value, "nathan@exemple.fr", "e-mail repris");
    remplir(form, { mot_de_passe: "mauvais" });
    soumettre(form);
    await jusqua(() => /incorrect/.test(texte(ecran())), "mot de passe incorrect");
    form = ecran().querySelector("form");
    remplir(form, { mot_de_passe: "visibilite29" });
    soumettre(form);
    await jusqua(() => /Vérifie ta boîte mail/.test(texte(ecran())) && /Confirme d'abord/.test(texte(ecran())), "adresse à confirmer");
  });

  await etape("connexion après confirmation : spots et favoris d'avant versés au compte", async () => {
    serveur.utilisateurs[0].confirme = true;
    ecran().querySelector('[data-mode="connexion"]').click();
    const form = ecran().querySelector("form");
    remplir(form, { mot_de_passe: "visibilite29" });
    soumettre(form);
    await jusqua(() => ecran().hidden, "écran fermé");
    assert.ok(!d.body.classList.contains("compte-requis"));
    await jusqua(() => serveur.spots.length === 1 && serveur.favoris.length === 1, "synchronisation");
    assert.equal(serveur.spots[0].nom, "Ma crique");
    assert.equal(serveur.favoris[0].point_id, "ref-groix");
  });

  await etape("mon compte : profil lu et accord e-mails retiré", async () => {
    w.location.hash = "#/compte";
    await jusqua(() => panneau().querySelector('[data-form="profil"] input[name="prenom"]')?.value === "Nathan", "profil affiché");
    assert.match(texte(panneau()), /nathan@exemple\.fr/);
    const form = panneau().querySelector('[data-form="profil"]');
    remplir(form, { accord_emails: false, departement: "56" });
    soumettre(form);
    await jusqua(() => /Profil enregistré/.test(texte(panneau())), "profil enregistré");
    const p = serveur.profils.get(serveur.utilisateurs[0].id);
    assert.equal(p.accord_emails, false);
    assert.equal(p.departement, "56");
  });

  await etape("favori ajouté sur une fiche, enregistré dans le compte", async () => {
    w.location.hash = "#/spot/ref-quiberon";
    await jusqua(() => panneau().querySelector("#favori"), "fiche");
    panneau().querySelector("#favori").click();
    await jusqua(() => serveur.favoris.some((f) => f.point_id === "ref-quiberon"), "favori sur le serveur");
  });

  await etape("retour terrain déposé au nom du compte", async () => {
    panneau().querySelector("#retour-visi").value = "7";
    soumettre(panneau().querySelector("#form-retour"));
    await jusqua(() => serveur.rapports.length === 1, "retour reçu");
    assert.equal(serveur.rapports[0].spot_id, "ref-quiberon");
    assert.equal(serveur.rapports[0].utilisateur, serveur.utilisateurs[0].id);
  });

  await etape("suppression d'un spot privé, aussi sur le serveur", async () => {
    w.location.hash = "#/prive/prive-ancien";
    await jusqua(() => panneau().querySelector("#prive-supprimer"), "fiche du spot");
    assert.ok(!panneau().querySelector("#prive-partage"), "pas de partage tant que la base ne le connaît pas");
    assert.ok(serveur.spots.every((x) => !("partage" in x)), "aucun champ de partage envoyé");
    panneau().querySelector("#prive-supprimer").click();
    panneau().querySelector("#prive-oui").click();
    await jusqua(() => serveur.spots.length === 0, "spot supprimé du serveur");
  });

  await etape("déconnexion : écran de connexion et appareil vidé", async () => {
    w.location.hash = "#/compte";
    await jusqua(() => panneau().querySelector("[data-deconnexion]"), "page compte");
    panneau().querySelector("[data-deconnexion]").click();
    await jusqua(() => !ecran().hidden && /Me connecter/.test(texte(ecran())), "écran de connexion");
    for (const cle of ["kelvisi-session", "kelvisi-spots", "kelvisi-favoris", "kelvisi-profil"]) assert.equal(w.localStorage.getItem(cle), null, cle);
  });

  await etape("reconnexion : favoris retrouvés depuis le compte", async () => {
    const form = ecran().querySelector("form");
    remplir(form, { email: "nathan@exemple.fr", mot_de_passe: "visibilite29" });
    soumettre(form);
    await jusqua(() => ecran().hidden, "écran fermé");
    await jusqua(() => (JSON.parse(w.localStorage.getItem("kelvisi-favoris") || "[]")).length === 2, "favoris rapatriés");
  });

  await etape("suppression du compte", async () => {
    w.location.hash = "#/compte";
    await jusqua(() => panneau().querySelector("[data-supprimer]"), "page compte");
    panneau().querySelector("[data-supprimer]").click();
    panneau().querySelector("[data-oui]").click();
    await jusqua(() => !ecran().hidden, "écran de compte");
    assert.equal(serveur.utilisateurs.length, 0);
    assert.equal(serveur.favoris.length, 0);
    assert.equal(w.localStorage.getItem("kelvisi-session"), null);
  });
}

if (mode === "lien") {
  await etape("lien de nouveau mot de passe reçu par e-mail", async () => {
    await jusqua(() => !ecran().hidden && /Nouveau mot de passe/.test(texte(ecran())), "écran nouveau mot de passe");
    assert.equal(w.location.hash, "#/carte", "jetons retirés de l'adresse");
    const form = ecran().querySelector("form");
    remplir(form, { mot_de_passe: "court" });
    soumettre(form);
    await jusqua(() => /Mot de passe/.test(texte(ecran().querySelector("[data-message]"))), "mot de passe refusé");
    remplir(form, { mot_de_passe: "nouveaumdp7" });
    soumettre(form);
    await jusqua(() => ecran().hidden, "écran fermé");
    assert.equal(serveur.utilisateurs[0].motDePasse, "nouveaumdp7");
    await jusqua(() => /Mot de passe changé/.test(d.getElementById("bandeau").textContent), "annonce");
  });
}

if (mode === "partage") {
  const auteur = creerUtilisateur("auteur@exemple.fr", "partage2026", { prenom: "Auteur" }, true);
  serveur.spots.push({ id: "prive-x", proprietaire: auteur.id, nom: "Roche du large", lat: 47.47, lon: -3.18, region: "atlantique",
    orientation_deg: 260, ouverture_deg: 90, profondeur_m: 9, fond: "roche", partage: "publie", partage_id: "uuid-roche", maj_le: new Date().toISOString() });
  const moi = creerUtilisateur("moi@exemple.fr", "chasse2026", { prenom: "Moi" }, true);
  serveur.spots.push({ id: "prive-mien", proprietaire: moi.id, nom: "Ma crique", lat: 47.49, lon: -3.2, region: "atlantique",
    orientation_deg: 270, ouverture_deg: 90, profondeur_m: 8, fond: "roche", partage: "prive", partage_id: "uuid-mien", maj_le: new Date().toISOString() });

  await etape("connexion : spots partagés chargés", async () => {
    await jusqua(() => !ecran().hidden, "écran de compte");
    ecran().querySelector('[data-mode="connexion"]').click();
    const form = ecran().querySelector("form");
    remplir(form, { email: "moi@exemple.fr", mot_de_passe: "chasse2026" });
    soumettre(form);
    await jusqua(() => ecran().hidden, "écran fermé");
    await jusqua(() => d.querySelector('.repere.communaute[data-type="communaute"]'), "repère du spot partagé");
    assert.equal(d.querySelectorAll(".repere.communaute").length, 1);
  });

  await etape("fiche d'un spot partagé, anonyme, copiable", async () => {
    w.location.hash = "#/partage/uuid-roche";
    await jusqua(() => panneau().querySelector(".lecture"), "prévision calculée", 5000);
    assert.match(texte(panneau()), /Roche du large/);
    assert.match(texte(panneau()), /Spot partagé/);
    assert.doesNotMatch(texte(panneau()), /Auteur|auteur@exemple/, "aucun nom d'auteur");
    assert.match(panneau().querySelector("a.bouton[href^='mailto:']")?.getAttribute("href") || "", /Signalement/, "signalement possible");
    panneau().querySelector("#communaute-copier").click();
    await jusqua(() => /#\/prive\//.test(w.location.hash) && panneau().querySelector("#prive-partage"), "copie dans mes spots", 5000);
    await jusqua(() => serveur.spots.filter((x) => x.proprietaire === moi.id).length === 2, "copie synchronisée");
    const copie = serveur.spots.find((x) => x.proprietaire === moi.id && x.nom === "Roche du large");
    assert.equal(copie.partage, "prive", "la copie reste privée");
  });

  await etape("proposer son spot : en attente de validation", async () => {
    w.location.hash = "#/prive/prive-mien";
    await jusqua(() => /Ma crique/.test(texte(panneau().querySelector(".titre-vue"))) && panneau().querySelector("#prive-partage"), "bloc de partage", 5000);
    assert.match(texte(panneau()), /Visible par toi seul/);
    panneau().querySelector("#prive-partage").click();
    await jusqua(() => serveur.spots.find((x) => x.id === "prive-mien").partage === "en_attente", "proposition reçue");
    await jusqua(() => /en attente de validation/.test(texte(panneau())), "état affiché");
  });

  await etape("validé par Kelvisi : visible comme partagé, puis retiré", async () => {
    serveur.spots.find((x) => x.id === "prive-mien").partage = "publie";
    w.dispatchEvent(new w.Event("online"));
    await jusqua(() => JSON.parse(w.localStorage.getItem("kelvisi-spots")).find((x) => x.id === "prive-mien").partage === "publie", "état rapatrié");
    w.location.hash = "#/mes-spots";
    await attendre();
    w.location.hash = "#/prive/prive-mien";
    await jusqua(() => /Ma crique/.test(texte(panneau().querySelector(".titre-vue"))) && /Partagé : visible par tous, sans ton nom/.test(texte(panneau())), "partagé", 5000);
    panneau().querySelector("#prive-partage").click();
    await jusqua(() => serveur.spots.find((x) => x.id === "prive-mien").partage === "prive", "retiré");
  });

  await etape("« Où aller ? » autour d'une ville inclut le spot partagé", async () => {
    await import(pathToFileURL(join(APP, "js", "communaute.js")).href).then((m) => m.chargerCommunaute());
    w.location.hash = "#/liste";
    await jusqua(() => panneau().querySelector("#ou-texte"), "liste");
    assert.ok(![...panneau().querySelectorAll(".liste .marque-prive")].some((m) => m.textContent === "partagé"), "pas sans point de départ");
    const champ = panneau().querySelector("#ou-texte");
    champ.value = "roche";
    champ.dispatchEvent(new w.Event("input"));
    await jusqua(() => /Roche du large\s*Spot partagé/.test(texte(panneau().querySelector("#ou-resultats"))), "spot partagé trouvé par son nom");
  });
}

if (mode === "alertes") {
  const moi = creerUtilisateur("alerte@exemple.fr", "chasse2026", { prenom: "Moi" }, true);
  serveur.favoris.push({ proprietaire: moi.id, point_id: "ref-groix", alerte: null });

  await etape("connexion : favori sans alerte", async () => {
    await jusqua(() => !ecran().hidden, "écran de compte");
    ecran().querySelector('[data-mode="connexion"]').click();
    const form = ecran().querySelector("form");
    remplir(form, { email: "alerte@exemple.fr", mot_de_passe: "chasse2026" });
    soumettre(form);
    await jusqua(() => ecran().hidden && JSON.parse(w.localStorage.getItem("kelvisi-favoris") || "[]").includes("ref-groix"), "favori rapatrié");
    w.location.hash = "#/spot/ref-groix";
    await jusqua(() => panneau().querySelector("#alerte-favori:not([hidden])"), "case d'alerte");
    assert.ok(!panneau().querySelector("#alerte-case").checked);
    assert.match(texte(panneau().querySelector("#alerte-favori")), /M'alerter quand la visibilité y sera bonne/);
  });

  await etape("notifications refusées : message clair, rien d'enregistré", async () => {
    push.reponse = "denied";
    const caseAlerte = panneau().querySelector("#alerte-case");
    caseAlerte.checked = true;
    caseAlerte.dispatchEvent(new w.Event("change"));
    await jusqua(() => !panneau().querySelector("#alerte-erreur").hidden, "message");
    assert.match(panneau().querySelector("#alerte-erreur").textContent, /bloquées/);
    assert.ok(!panneau().querySelector("#alerte-case").checked);
    assert.equal(serveur.abonnements.length, 0);
    w.Notification.permission = "default";
  });

  await etape("alerte activée : appareil abonné, niveau enregistré sur le compte", async () => {
    push.reponse = "granted";
    const caseAlerte = panneau().querySelector("#alerte-case");
    caseAlerte.checked = true;
    caseAlerte.dispatchEvent(new w.Event("change"));
    await jusqua(() => serveur.favoris[0].alerte === "bonne", "alerte sur le serveur");
    assert.equal(serveur.abonnements.length, 1);
    assert.equal(serveur.abonnements[0].endpoint, "https://push.test/appareil-1");
    assert.ok(panneau().querySelector("#alerte-case").checked);
    assert.equal(panneau().querySelector('#alerte-niveau [aria-pressed="true"]').textContent, "Bonne ou mieux");
    panneau().querySelector('#alerte-niveau [data-v="excellente"]').click();
    await jusqua(() => serveur.favoris[0].alerte === "excellente", "niveau changé");
    assert.deepEqual(JSON.parse(w.localStorage.getItem("kelvisi-alertes")), { "ref-groix": "excellente" });
  });

  await etape("alerte sur un spot privé, enregistrée sur la ligne du spot", async () => {
    serveur.spots.push({ id: "prive-crique", proprietaire: moi.id, nom: "Ma crique", lat: 47.49, lon: -3.2, region: "atlantique",
      orientation_deg: 270, ouverture_deg: 90, profondeur_m: 8, fond: "roche", maj_le: new Date().toISOString() });
    w.location.hash = "#/mes-spots";
    await attendre(100);
    const { synchroniser } = await import(pathToFileURL(join(APP, "js", "synchro.js")).href);
    await synchroniser();
    w.location.hash = "#/prive/prive-crique";
    await jusqua(() => panneau().querySelector("#alerte-favori:not([hidden])"), "case d'alerte du spot privé");
    assert.match(texte(panneau().querySelector("#alerte-favori")), /sa position n'est jamais publiée/);
    const caseAlerte = panneau().querySelector("#alerte-case");
    caseAlerte.checked = true;
    caseAlerte.dispatchEvent(new w.Event("change"));
    await jusqua(() => serveur.spots.find((x) => x.id === "prive-crique").alerte === "bonne", "alerte du spot sur le serveur");
    assert.equal(serveur.favoris[0].alerte, "excellente", "l'alerte du favori n'a pas bougé");
    assert.ok(!JSON.parse(w.localStorage.getItem("kelvisi-spots")).some((x) => "alerte" in x), "l'alerte n'est pas rangée dans le spot");
  });

  await etape("mon compte : alertes listées et exportées", async () => {
    w.location.hash = "#/compte";
    await jusqua(() => /Mes alertes/.test(texte(panneau())), "bloc des alertes");
    assert.match(texte(panneau()), /Groix.*excellente seulement/);
    assert.match(texte(panneau()), /Ma crique.*bonne ou mieux/);
  });

  await etape("spot privé supprimé : son alerte disparaît", async () => {
    w.location.hash = "#/prive/prive-crique";
    await jusqua(() => panneau().querySelector("#prive-supprimer"), "fiche du spot");
    panneau().querySelector("#prive-supprimer").click();
    panneau().querySelector("#prive-oui").click();
    await jusqua(() => !serveur.spots.some((x) => x.id === "prive-crique"), "spot supprimé du serveur");
    assert.deepEqual(JSON.parse(w.localStorage.getItem("kelvisi-alertes")), { "ref-groix": "excellente" });
  });

  await etape("favori retiré : son alerte disparaît", async () => {
    w.location.hash = "#/spot/ref-groix";
    await jusqua(() => panneau().querySelector("#alerte-favori:not([hidden])"), "fiche");
    panneau().querySelector("#favori").click();
    await jusqua(() => panneau().querySelector("#alerte-favori").hidden, "case masquée");
    await jusqua(() => serveur.favoris.length === 0, "favori supprimé du serveur");
    assert.deepEqual(JSON.parse(w.localStorage.getItem("kelvisi-alertes") || "{}"), {});
  });

  await etape("déconnexion : l'appareil ne reçoit plus les alertes du compte", async () => {
    panneau().querySelector("#favori").click();
    await jusqua(() => panneau().querySelector("#alerte-favori:not([hidden])"), "case revenue");
    assert.ok(!panneau().querySelector("#alerte-case").checked, "pas d'alerte reprise d'office");
    w.location.hash = "#/compte";
    await jusqua(() => panneau().querySelector("[data-deconnexion]"), "page compte");
    panneau().querySelector("[data-deconnexion]").click();
    await jusqua(() => !ecran().hidden, "écran de connexion");
    assert.equal(serveur.abonnements.length, 0, "abonnement retiré du compte");
    assert.equal(push.abonnement, null, "abonnement du navigateur résilié");
    assert.equal(w.localStorage.getItem("kelvisi-alertes"), null);
  });
}

if (mode === "expire") {
  await etape("lien expiré : message clair et connexion proposée", async () => {
    await jusqua(() => !ecran().hidden && /expiré/.test(texte(ecran())), "message lien expiré");
    assert.match(texte(ecran()), /Me connecter/);
    assert.equal(w.location.hash, "#/carte");
  });
}

await etape("aucune erreur JavaScript", async () => {
  assert.deepEqual(erreurs, []);
});

console.log(`Comptes (${mode})\n${etapes.join("\n")}`);
process.exit(process.exitCode || 0);
