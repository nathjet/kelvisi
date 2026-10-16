// Kelvisi : moteur de prévision, version navigateur.
// Traduction fidèle de prevision/ (Python). Toute modification du modèle doit être
// faite des deux côtés ; le test tests/test_concordance_js.py vérifie qu'ils donnent
// les mêmes résultats.
//
// Les constantes viennent de donnees/parametres.json (produit par le calcul Python) :
// appeler definirParametres(P) avant tout calcul.

let P = null;

export function definirParametres(parametres) {
  P = parametres;
}

export function parametres() {
  if (!P) throw new Error("Paramètres du modèle non chargés");
  return P;
}

// --- Outils numériques ---------------------------------------------------------

const estFini = Number.isFinite;
const nanVers = (x, v) => (estFini(x) ? x : v);
const pince = (x, a, b) => Math.min(Math.max(x, a), b);

// Arrondi « au pair » comme round() de Python
export function arrondiPair(x) {
  const r = Math.round(x);
  if (Math.abs(x - Math.trunc(x)) === 0.5) return 2 * Math.round(x / 2);
  return r;
}

// round(x, d) de Python : arrondi correct de la valeur binaire exacte, égalités au pair
export function arrondiDecimales(x, d) {
  if (!estFini(x)) return x;
  const exact = Math.abs(x).toFixed(Math.min(100, d + 40));
  const point = exact.indexOf(".");
  const suite = exact.slice(point + 1 + d);
  let texte = Math.abs(x).toFixed(d);
  if (/^50*$/.test(suite)) {
    // Égalité exacte : toFixed arrondit vers le haut, Python vers le chiffre pair
    const tronque = exact.slice(0, point + 1 + d).replace(/\.$/, "");
    const dernier = Number(tronque.replace(".", "").slice(-1));
    if (dernier % 2 === 0) texte = tronque;
  }
  const v = Number(texte);
  return x < 0 ? -v : v;
}

// Mise en forme f"{x:.Nf}" de Python, virgule décimale
export function formater(x, d) {
  return arrondiDecimales(x, d).toFixed(d).replace(".", ",");
}

function memoire(entree, tau) {
  const d = Math.exp(-1 / tau);
  const sortie = new Array(entree.length);
  let acc = 0;
  for (let i = 0; i < entree.length; i++) {
    acc = acc * d + entree[i];
    sortie[i] = acc;
  }
  return sortie;
}

function rechercheGauche(t, v) {
  let a = 0, b = t.length;
  while (a < b) {
    const m = (a + b) >> 1;
    if (t[m] < v) a = m + 1; else b = m;
  }
  return a;
}

function rechercheDroite(t, v) {
  let a = 0, b = t.length;
  while (a < b) {
    const m = (a + b) >> 1;
    if (t[m] <= v) a = m + 1; else b = m;
  }
  return a;
}

const moyenne = (xs) => xs.reduce((s, x) => s + x, 0) / xs.length;

// --- Fuseau horaire --------------------------------------------------------------

const formats = new Map();
function formatFuseau(fuseau) {
  if (!formats.has(fuseau)) {
    formats.set(fuseau, new Intl.DateTimeFormat("en-US", {
      timeZone: fuseau, hourCycle: "h23", year: "numeric", month: "2-digit", day: "2-digit",
      hour: "2-digit", minute: "2-digit", second: "2-digit",
    }));
  }
  return formats.get(fuseau);
}

function partiesLocales(t, fuseau) {
  const p = {};
  for (const x of formatFuseau(fuseau).formatToParts(new Date(t * 1000))) p[x.type] = x.value;
  return { an: +p.year, mois: +p.month, jour: +p.day, heure: +p.hour % 24, minute: +p.minute, seconde: +p.second };
}

function decalageS(t, fuseau) {
  const p = partiesLocales(t, fuseau);
  return Date.UTC(p.an, p.mois - 1, p.jour, p.heure, p.minute, p.seconde) / 1000 - t;
}

// Instant (s) de l'heure murale donnée dans le fuseau
function versInstant(an, mois, jour, heure, fuseau) {
  const mural = Date.UTC(an, mois - 1, jour, heure) / 1000;
  let t = mural - decalageS(mural, fuseau);
  t = mural - decalageS(t, fuseau);
  return t;
}

const deux = (n) => String(n).padStart(2, "0");

export function isoLocal(t, fuseau = "Europe/Paris") {
  const p = partiesLocales(t, fuseau);
  const dec = Math.round(decalageS(t, fuseau) / 60);
  const signe = dec >= 0 ? "+" : "-";
  const a = Math.abs(dec);
  return `${p.an}-${deux(p.mois)}-${deux(p.jour)}T${deux(p.heure)}:${deux(p.minute)}:${deux(p.seconde)}${signe}${deux(Math.floor(a / 60))}:${deux(a % 60)}`;
}

function minuitLocal(t, fuseau, plusJours = 0) {
  const p = partiesLocales(t, fuseau);
  const d = new Date(Date.UTC(p.an, p.mois - 1, p.jour + plusJours));
  return versInstant(d.getUTCFullYear(), d.getUTCMonth() + 1, d.getUTCDate(), 0, fuseau);
}

function dateLocale(t, fuseau) {
  const p = partiesLocales(t, fuseau);
  return `${p.an}-${deux(p.mois)}-${deux(p.jour)}`;
}

// --- Spot -------------------------------------------------------------------------

export function spotEffectif(spot) {
  const fond = P.FONDS[spot.fond];
  const region = P.REGIONS[spot.region];
  if (!fond) throw new Error(`Type de fond inconnu : ${spot.fond}`);
  if (!region) throw new Error(`Région inconnue : ${spot.region}`);
  return {
    ...spot,
    ouverture_deg: spot.ouverture_deg ?? 90,
    sensibilite_pluie: spot.sensibilite_pluie ?? 0.3,
    sensibilite_houle: spot.sensibilite_houle ?? 1,
    facteur_courant: spot.facteur_courant ?? 1,
    fondP: fond,
    regionP: region,
    part_sable: spot.part_sable_alentours ?? fond.part_sable,
    visibilite_calme: spot.visibilite_calme_m ?? region.visibilite_calme_m * P.FACTEUR_CALME_FOND[spot.fond],
    sensibilite_maree_effective: spot.sensibilite_maree ?? region.sensibilite_maree,
  };
}

// --- Physique ------------------------------------------------------------------------

export function nombreOnde(T, h) {
  if (!(T > 0)) return NaN;
  const g = P.GRAVITE;
  const omega = (2 * Math.PI) / T;
  let k = (omega * omega) / (g * Math.sqrt(Math.tanh((omega * omega * h) / g)));
  for (let i = 0; i < 6; i++) {
    const th = Math.tanh(k * h);
    const f = g * k * th - omega * omega;
    const df = g * th + g * k * h * (1 - th * th);
    k = k - f / df;
  }
  return k;
}

export function vitesseOrbitaleFond(H, T, h) {
  H = pince(nanVers(H, 0), 0, P.RAPPORT_DEFERLEMENT * h);
  T = nanVers(T, 0);
  if (!(H > 0 && T > 0)) return 0;
  const kh = Math.min(nombreOnde(T, h) * h, 50);
  return (Math.PI * H) / (T * Math.sinh(kh));
}

export function ecartAngulaire(a, b) {
  const x = a - b + 180;
  return Math.abs((((x % 360) + 360) % 360) - 180);
}

export function exposition(direction, orientation, ouverture) {
  const d = nanVers(ecartAngulaire(direction, orientation), 180);
  const r = P.EXPOSITION_RESIDUELLE;
  if (d > ouverture) return r;
  const forme = Math.cos((Math.PI / 2) * pince(d / Math.max(ouverture, 1), 0, 1));
  return r + (1 - r) * forme;
}

export function ventDeTerre(direction, orientation) {
  return ecartAngulaire(direction, orientation) > 100;
}

// --- Marée -------------------------------------------------------------------------------

function boucherTrous(h) {
  const ok = h.map(estFini);
  if (ok.every(Boolean)) return h.slice();
  const xs = [], ys = [];
  h.forEach((v, i) => { if (ok[i]) { xs.push(i); ys.push(v); } });
  return h.map((v, i) => {
    if (ok[i]) return v;
    if (i <= xs[0]) return ys[0];
    if (i >= xs[xs.length - 1]) return ys[ys.length - 1];
    const j = rechercheDroite(xs, i) - 1;
    const f = (i - xs[j]) / (xs[j + 1] - xs[j]);
    return ys[j] + f * (ys[j + 1] - ys[j]);
  });
}

export function extremesMaree(t, niveau) {
  if (niveau.filter(estFini).length < 6) return [];
  const h = boucherTrous(niveau);
  const res = [];
  for (let i = 1; i < h.length - 1; i++) {
    const estMax = h[i] >= h[i - 1] && h[i] > h[i + 1];
    const estMin = h[i] <= h[i - 1] && h[i] < h[i + 1];
    if (!estMax && !estMin) continue;
    const a = (h[i - 1] - 2 * h[i] + h[i + 1]) / 2;
    const b = (h[i + 1] - h[i - 1]) / 2;
    const dx = pince(a !== 0 ? -b / (2 * a) : 0, -0.5, 0.5);
    const e = { temps: t[i] + dx * 3600, hauteur: h[i] + b * dx + a * dx * dx, type: estMax ? "PM" : "BM" };
    const dernier = res[res.length - 1];
    if (dernier && dernier.type === e.type) {
      const garder = e.type === "PM" ? e.hauteur > dernier.hauteur : e.hauteur < dernier.hauteur;
      if (garder) res[res.length - 1] = e;
      continue;
    }
    if (dernier && e.temps - dernier.temps < 4 * 3600) continue;
    res.push(e);
  }
  return res;
}

function marnageMoyen(ext) {
  if (ext.length < 2) return 0;
  const ecarts = [];
  for (let i = 0; i + 1 < ext.length; i++) ecarts.push(Math.abs(ext[i].hauteur - ext[i + 1].hauteur));
  return moyenne(ecarts);
}

function intervalle(t, ext) {
  const debuts = ext.map((e) => e.temps);
  return t.map((x) => {
    if (ext.length < 2) return -1;
    const k = rechercheDroite(debuts, x) - 1;
    return k >= 0 && k < ext.length - 1 ? k : -1;
  });
}

function phaseMaree(t, ext) {
  return intervalle(t, ext).map((k, i) => {
    if (k < 0) return 0;
    const a = ext[k], b = ext[k + 1];
    const x = (t[i] - a.temps) / (b.temps - a.temps);
    return (a.type === "PM" ? 1 : -1) * Math.cos(Math.PI * x);
  });
}

function rapportMarnage(t, ext) {
  const moyen = marnageMoyen(ext);
  if (moyen < P.MARNAGE_MINIMUM_M) return t.map(() => 1);
  return intervalle(t, ext).map((k) => (k < 0 ? 1 : Math.abs(ext[k].hauteur - ext[k + 1].hauteur) / moyen));
}

// --- Soleil -------------------------------------------------------------------------------

const rad = Math.PI / 180;

export function hauteurSoleil(lat, lon, t) {
  const n = t / 86400 + 2440587.5 - 2451545.0;
  const L = (((280.46 + 0.9856474 * n) % 360) + 360) % 360 * rad;
  const g = (((357.528 + 0.9856003 * n) % 360) + 360) % 360 * rad;
  const lam = L + 1.915 * rad * Math.sin(g) + 0.02 * rad * Math.sin(2 * g);
  const eps = (23.439 - 0.0000004 * n) * rad;
  const ascension = Math.atan2(Math.cos(eps) * Math.sin(lam), Math.cos(lam));
  const declinaison = Math.asin(Math.sin(eps) * Math.sin(lam));
  const gmst = (((18.697374558 + 24.06570982441908 * n) % 24) + 24) % 24;
  const angle = (gmst * 15 + lon) * rad - ascension;
  const phi = lat * rad;
  const s = Math.sin(phi) * Math.sin(declinaison) + Math.cos(phi) * Math.cos(declinaison) * Math.cos(angle);
  return Math.asin(pince(s, -1, 1)) / rad;
}

export const faitJour = (lat, lon, t) => hauteurSoleil(lat, lon, t) > -0.833;

export function leverCoucher(lat, lon, debut) {
  let lever = null, coucher = null;
  let avant = faitJour(lat, lon, debut);
  for (let s = 60; s <= 86400; s += 60) {
    const maintenant = faitJour(lat, lon, debut + s);
    if (!avant && maintenant && lever === null) lever = debut + s;
    if (avant && !maintenant && coucher === null) coucher = debut + s;
    avant = maintenant;
  }
  return [lever, coucher];
}

// --- Conditions -----------------------------------------------------------------------------

export const CHAMPS = [
  "hauteur_vagues", "periode_vagues", "direction_vagues",
  "hauteur_houle", "periode_houle", "direction_houle",
  "hauteur_mer_vent", "periode_mer_vent", "direction_mer_vent",
  "courant", "direction_courant", "niveau_mer",
  "vent", "direction_vent", "rafales", "pluie", "nebulosite", "temperature_eau",
];

// { temps: [s...], series: { champ: [...] } } ; champs absents remplis de NaN
export function preparerConditions(brut) {
  const n = brut.temps.length;
  const series = {};
  for (const c of CHAMPS) {
    const v = brut.series?.[c];
    series[c] = v ? v.map((x) => (x === null || x === undefined ? NaN : x)) : new Array(n).fill(NaN);
  }
  return { temps: brut.temps.slice(), series, debits: brut.debits || {} };
}

function aComposantes(c) {
  return c.series.hauteur_houle.some(estFini) && c.series.hauteur_mer_vent.some(estFini);
}

function vitesseVagues(spot, c, profondeur) {
  const comp = (hs, ts, ds) => hs.map((h, i) =>
    vitesseOrbitaleFond(nanVers(h, 0) * exposition(ds[i], spot.orientation_deg, spot.ouverture_deg), ts[i], profondeur));
  const s = c.series;
  if (aComposantes(c)) {
    const u1 = comp(s.hauteur_houle, s.periode_houle, s.direction_houle);
    const u2 = comp(s.hauteur_mer_vent, s.periode_mer_vent, s.direction_mer_vent);
    return u1.map((u, i) => Math.sqrt(u * u + u2[i] * u2[i]));
  }
  return comp(s.hauteur_vagues, s.periode_vagues, s.direction_vagues);
}

export function hauteurAuSpot(spot, c) {
  const s = c.series;
  const ex = (h, d) => nanVers(h, 0) * exposition(d, spot.orientation_deg, spot.ouverture_deg);
  if (aComposantes(c)) {
    return s.hauteur_houle.map((h, i) => {
      const a = ex(h, s.direction_houle[i]);
      const b = ex(s.hauteur_mer_vent[i], s.direction_mer_vent[i]);
      return Math.sqrt(a * a + b * b);
    });
  }
  return s.hauteur_vagues.map((h, i) => (estFini(h) ? ex(h, s.direction_vagues[i]) : NaN));
}

// --- Modèle ----------------------------------------------------------------------------------

export function calculer(spotBrut, c, satellite = null) {
  const spot = spotEffectif(spotBrut);
  const t = c.temps;
  const n = t.length;
  const fond = spot.fondP;
  const region = spot.regionP;
  const s = c.series;

  const uVagues = vitesseVagues(spot, c, spot.profondeur_m);
  const uLittoral = vitesseVagues(spot, c, Math.min(P.PROFONDEUR_LITTORAL_M, spot.profondeur_m));
  const courant = s.courant.map((x) => nanVers(x, 0) * spot.facteur_courant * P.COURANT_PRES_DU_FOND);
  const uFond = uVagues.map((u, i) => Math.sqrt(u * u + courant[i] * courant[i]));
  const uBord = uLittoral.map((u, i) => Math.sqrt(u * u + courant[i] * courant[i]));

  const ext = extremesMaree(t, s.niveau_mer);
  const marnage = marnageMoyen(ext);
  const mareeActive = marnage >= P.MARNAGE_MINIMUM_M && spot.sensibilite_maree_effective > 0;
  const phase = mareeActive ? phaseMaree(t, ext) : new Array(n).fill(0);
  const rapport = mareeActive ? rapportMarnage(t, ext) : new Array(n).fill(1);
  const sens = mareeActive ? spot.sensibilite_maree_effective : 0;

  const source = uFond.map((u, i) => {
    const local = Math.max(0, (u / fond.u_critique) ** 2 - 1) * fond.erodabilite;
    const bord = Math.max(0, (uBord[i] / P.U_CRITIQUE_LITTORAL) ** 2 - 1) * spot.part_sable * P.POIDS_LITTORAL;
    const vivesEaux = 1 + P.EFFET_MARNAGE * sens * (rapport[i] - 1);
    return P.ALPHA_BRASSAGE * (local + bord) * Math.max(vivesEaux, 0.5);
  });
  const charge = memoire(source, fond.tau_h * P.FACTEUR_TAU);
  const cBrassage = charge.map((x) => spot.sensibilite_houle * P.C_BRASSAGE_MAX * (1 - Math.exp(-x / P.C_BRASSAGE_MAX)));

  // Les rivières ne sont prises en compte que pour les points publics (calcul Python)
  const cFluvial = new Array(n).fill(0);

  const cumul = memoire(s.pluie.map((x) => nanVers(x, 0)), P.TAU_PLUIE_H);
  const cPluie = cumul.map((x) => P.DELTA_PLUIE * spot.sensibilite_pluie * Math.max(0, x - P.SEUIL_PLUIE_MM) / 10);

  const poidsSat = (tsat) => t.map((x) => Math.exp(-Math.abs(x - tsat) / 3600 / P.TAU_ASSIMILATION_H));
  // Plancton saisonnier par façade (la chlorophylle satellite, faussée par les sédiments près des côtes, n'est pas utilisée)
  const cPlancton = t.map((x) => region.plancton_mensuel[new Date(x * 1000).getUTCMonth()]);

  const cBase = Math.max(P.CONSTANTE_VISIBILITE / spot.visibilite_calme - P.C_EAU, 0);
  // Paramètres d'une version précédente (en cache) : pas d'effet de saison
  const saisonP = (P.SAISON || {})[spot.region] || { amplitude: 0, pic_jour: 15 };
  const saison = t.map((x) => Math.exp(saisonP.amplitude * Math.cos(2 * Math.PI * (((x / 86400) % 365.25) - saisonP.pic_jour) / 365.25)));
  const facteurMaree = phase.map((ph) => 1 - P.EFFET_PHASE_MAREE * sens * ph);
  const cModele = t.map((_, i) => P.C_EAU + saison[i] * (cBase + facteurMaree[i] * (cBrassage[i] + cFluvial[i] + cPluie[i])) + cPlancton[i]);

  let correction = new Array(n).fill(0);
  let satelliteUtilise = false;
  if (satellite && satellite.turbidite_fnu != null) {
    let iSat = 0;
    for (let i = 1; i < n; i++) if (Math.abs(t[i] - satellite.temps) < Math.abs(t[iSat] - satellite.temps)) iSat = i;
    if (Math.abs(t[iSat] - satellite.temps) <= 3 * 3600) {
      const cObs = P.C_EAU + P.C_PAR_FNU * Math.max(satellite.turbidite_fnu, 0);
      const ecart = cObs - (cModele[iSat] - cPlancton[iSat]);
      correction = poidsSat(satellite.temps).map((w) => ecart * w);
      satelliteUtilise = true;
    }
  }

  const cTotal = cModele.map((x, i) => Math.max(x + correction[i], P.C_EAU + 0.02));
  const visibilite = cTotal.map((x) => Math.min(P.CONSTANTE_VISIBILITE / x, region.visibilite_max_m));
  const hauteur = t.map((x) => hauteurSoleil(spot.lat, spot.lon, x));
  const lumiere = hauteur.map((h, i) => {
    const fSoleil = P.FACTEUR_SOLEIL_BAS + (1 - P.FACTEUR_SOLEIL_BAS) * pince(h / P.HAUTEUR_SOLEIL_PLEINE_LUMIERE, 0, 1);
    const couvert = pince(nanVers(s.nebulosite[i], 50) / 100, 0, 1);
    return fSoleil * (1 - (1 - P.FACTEUR_CIEL_COUVERT) * couvert);
  });

  return {
    temps: t,
    visibilite_m: visibilite,
    visibilite_ressentie_m: visibilite.map((v, i) => v * lumiere[i]),
    composantes: {
      eau: new Array(n).fill(P.C_EAU),
      fond_habituel: saison.map((f) => f * cBase),
      brassage: cBrassage.map((x, i) => saison[i] * facteurMaree[i] * x),
      rivieres: cFluvial.map((x, i) => saison[i] * facteurMaree[i] * x),
      pluie: cPluie.map((x, i) => saison[i] * facteurMaree[i] * x),
      plancton: cPlancton,
      satellite: correction,
    },
    diagnostics: { phase_maree: phase, rapport_marnage: rapport, cumul_pluie: cumul, hauteur_soleil: hauteur },
    extremes_maree: ext,
    satellite_utilise: satelliteUtilise,
    spot,
  };
}

// --- Créneaux -----------------------------------------------------------------------------------

function scoreHoraire(ressentie, hs, rafales, vent, deTerre, seuilExcellent) {
  const score = [], deconseille = [];
  for (let i = 0; i < ressentie.length; i++) {
    const vis = pince(nanVers(ressentie[i], 0) / seuilExcellent, 0, 1.5);
    const h = nanVers(hs[i], 0);
    const rafKn = nanVers(rafales[i], 0) / P.NOEUD_EN_MS;
    const ventKn = nanVers(vent[i], 0) / P.NOEUD_EN_MS;
    let confort = h <= P.HOULE_CONFORT_M ? 1
      : 1 - (0.4 * (h - P.HOULE_CONFORT_M)) / (P.HOULE_DECONSEILLEE_M - P.HOULE_CONFORT_M);
    if (ventKn > P.VENT_GENANT_KN && !deTerre[i]) confort *= 0.8;
    const dec = h > P.HOULE_DECONSEILLEE_M || rafKn > P.RAFALES_DECONSEILLEES_KN;
    deconseille.push(dec);
    score.push(dec ? 0 : vis * confort);
  }
  return { score, deconseille };
}

function meilleurCreneau(t, score, visibilite, deJour) {
  let meilleur = null, note = -1;
  for (let debut = 0; debut < t.length; debut++) {
    if (!(deJour[debut] && score[debut] > 0)) continue;
    for (let duree = P.DUREE_CRENEAU_MIN_H; duree <= P.DUREE_CRENEAU_MAX_H; duree++) {
      const fin = debut + duree;
      if (fin > t.length) break;
      let ok = true;
      for (let k = debut; k < fin; k++) if (!(deJour[k] && score[k] > 0)) { ok = false; break; }
      if (!ok) break;
      const n = moyenne(score.slice(debut, fin)) * (1 + 0.05 * (duree - P.DUREE_CRENEAU_MIN_H));
      if (n > note + 1e-9) {
        const v = visibilite.slice(debut, fin);
        note = n;
        meilleur = { debut: t[debut], fin: t[fin - 1] + 3600, visibilite_moyenne: moyenne(v) };
      }
    }
  }
  return meilleur;
}

// --- Explications ------------------------------------------------------------------------------

const SECTEURS = ["nord", "nord-est", "est", "sud-est", "sud", "sud-ouest", "ouest", "nord-ouest"];

export function secteur(deg) {
  if (!estFini(deg)) return "secteur inconnu";
  return SECTEURS[Math.floor(((((deg % 360) + 360) % 360) + 22.5) / 45) % 8];
}

const de = (mot) => (/^[aeiouy]/.test(mot) ? `d'${mot}` : `de ${mot}`);

function expliquer(spot, c, res, i) {
  const comp = Object.fromEntries(Object.entries(res.composantes).map(([k, v]) => [k, v[i]]));
  const phrases = [];
  const cand = ["brassage", "rivieres", "pluie", "plancton", "satellite"];
  let principal = cand[0];
  for (const k of cand) if (comp[k] > comp[principal]) principal = k;
  const valeur = comp[principal];
  const s = c.series;
  const hs = s.hauteur_vagues;
  const SEUIL = 0.15;

  if (valeur < SEUIL && comp.satellite > -SEUIL) {
    const fenetre = hs.slice(Math.max(0, i - 48), i + 1).filter(estFini);
    const maxH = fenetre.length ? Math.max(0, ...fenetre) : 0;
    if (maxH >= 1.5 && exposition(s.direction_vagues[i], spot.orientation_deg, spot.ouverture_deg) < 0.4) {
      phrases.push(`Spot abrité de la houle ${de(secteur(s.direction_vagues[i]))} : eau claire pour le secteur.`);
    } else {
      phrases.push("Mer calme et sans apport d'eau trouble : eau claire pour ce spot.");
    }
  } else if (principal === "brassage") {
    phrases.push(phraseBrassage(spot, c, i, comp.brassage));
  } else if (principal === "rivieres") {
    phrases.push("Rivière en crue à proximité : apport d'eau trouble.");
  } else if (principal === "pluie") {
    phrases.push(`Fortes pluies récentes (environ ${formater(res.diagnostics.cumul_pluie[i], 0)} mm) : ruissellement vers la côte.`);
  } else if (principal === "plancton") {
    phrases.push("Présence de plancton, fréquente en cette saison.");
  } else if (principal === "satellite") {
    phrases.push("La dernière image satellite montre une eau plus trouble que prévu.");
  }
  if (comp.satellite < -SEUIL) phrases.push("La dernière image satellite montre une eau plus claire que prévu.");

  const vent = s.vent[i];
  if (estFini(vent)) {
    const kn = vent / P.NOEUD_EN_MS;
    const terre = ventDeTerre(s.direction_vent[i], spot.orientation_deg);
    if (terre && kn >= 15) phrases.push(`Vent de terre fort (${formater(kn, 0)} nœuds) : attention à la dérive vers le large.`);
    else if (terre && kn >= 5) phrases.push("Vent de terre : surface plutôt calme.");
    else if (!terre && kn >= P.VENT_GENANT_KN) phrases.push(`Vent de mer soutenu (${formater(kn, 0)} nœuds).`);
  }
  return phrases.slice(0, 2);
}

// Au-delà de 0,5 m⁻¹ de brassage, l'eau est dite « chargée », en dessous « un peu chargée »
const SEUIL_CHARGEE = 0.5;

function phraseBrassage(spot, c, i, brassage) {
  const s = c.series;
  const h = estFini(s.hauteur_vagues[i]) ? s.hauteur_vagues[i] : 0;
  const cour = estFini(s.courant[i]) ? s.courant[i] : 0;
  const etat = brassage >= SEUIL_CHARGEE ? "chargée" : "un peu chargée";
  if (h >= 1 && exposition(s.direction_vagues[i], spot.orientation_deg, spot.ouverture_deg) >= 0.3) {
    const p = s.periode_vagues[i];
    const txt = estFini(p) ? `, période ${formater(p, 0)} s` : "";
    return `Houle de ${formater(h, 1)} m${txt} qui brasse le fond : eau ${etat}.`;
  }
  const debut = Math.max(0, i - 72);
  const fenetre = s.hauteur_vagues.slice(debut, i + 1).map((x) => nanVers(x, 0));
  const max = Math.max(...fenetre);
  if (fenetre.length && max >= 1) {
    const j = debut + fenetre.indexOf(max);
    const heures = i - j;
    if (heures <= 12) return `La houle retombe, mais l'eau reste ${etat} après le pic de ${formater(max, 1)} m de ces dernières heures.`;
    const quand = heures <= 36 ? "d'hier" : "des jours précédents";
    return `La mer s'est calmée, mais l'eau reste ${etat} après la houle de ${formater(max, 1)} m ${quand}.`;
  }
  if (cour >= 0.5) return "Forts courants qui remettent le sable en suspension.";
  return "Fond légèrement brassé par la houle : eau un peu chargée.";
}

function conseilMaree(res, spot) {
  if (spot.sensibilite_maree_effective >= 0.3 && res.diagnostics.phase_maree.some((x) => x !== 0)) {
    return "Visibilité généralement meilleure autour de la pleine mer.";
  }
  return null;
}

function tendance(avant, apres) {
  if (avant <= 0) return "stable";
  const r = apres / avant;
  if (r >= 1.15) return "amélioration";
  if (r <= 0.87) return "dégradation";
  return "stable";
}

// --- Calibrage par les retours terrain ---------------------------------------------------------

export function fiabiliteUtilisateurs(rapports) {
  const ecarts = {};
  for (const r of rapports) {
    const voisins = rapports
      .filter((v) => v.utilisateur !== r.utilisateur && Math.abs(v.temps - r.temps) <= 3 * 3600 && v.visibilite_m > 0)
      .map((v) => v.visibilite_m)
      .sort((a, b) => a - b);
    if (voisins.length && r.visibilite_m > 0) {
      const m = voisins.length % 2 ? voisins[(voisins.length - 1) / 2]
        : (voisins[voisins.length / 2 - 1] + voisins[voisins.length / 2]) / 2;
      (ecarts[r.utilisateur] ||= []).push(Math.abs(Math.log(r.visibilite_m / m)));
    }
  }
  const res = {};
  for (const r of rapports) {
    const e = ecarts[r.utilisateur];
    res[r.utilisateur] = e ? 1 / (1 + moyenne(e) / 0.35) : 0.7;
  }
  return res;
}

export function calibrer(rapports, maintenant, fiabilites = null) {
  const ok = rapports.filter((r) => r.prevision_m > 0 && r.visibilite_m > 0 && r.temps <= maintenant);
  if (!ok.length) return { facteur: 1, nombre_effectif: 0, dispersion: 0 };
  fiabilites = fiabilites || fiabiliteUtilisateurs(rapports);
  const ecarts = ok.map((r) => Math.log(r.visibilite_m / r.prevision_m));
  const poids = ok.map((r) => (fiabilites[r.utilisateur] ?? 0.7) * 0.5 ** ((maintenant - r.temps) / 86400 / 30));
  const somme = poids.reduce((a, b) => a + b, 0);
  const biais = poids.reduce((a, w, i) => a + w * ecarts[i], 0) / (somme + 3);
  const dispersion = somme > 0 ? Math.sqrt(poids.reduce((a, w, i) => a + w * (ecarts[i] - biais) ** 2, 0) / somme) : 0;
  return { facteur: Math.exp(biais), nombre_effectif: somme, dispersion };
}

// --- Prévision complète ------------------------------------------------------------------------

export const VERSION_MODELE = "0.4.0";

export function classe(v, spot) {
  const [s1, s2, s3] = (spot.regionP || P.REGIONS[spot.region]).seuils;
  if (v < s1) return P.CLASSES[0];
  if (v < s2) return P.CLASSES[1];
  if (v < s3) return P.CLASSES[2];
  return P.CLASSES[3];
}

export function arrondir(v) {
  return v < 10 ? arrondiPair(v * 2) / 2 : arrondiPair(v);
}

function niveauConfiance(u) {
  const score = arrondiPair(100 * Math.exp(-1.6 * u));
  return [score, score >= 65 ? "élevée" : score >= 40 ? "moyenne" : "faible"];
}

const nombre = (x, d) => (estFini(x) ? arrondiDecimales(x, d) : null);

export function prevoir(spotBrut, conditions, maintenant, options = {}) {
  const { satellite = null, rapports = [], jours = 3, fuseau = "Europe/Paris" } = options;
  const c = preparerConditions(conditions);
  const res = calculer(spotBrut, c, satellite);
  const spot = res.spot;
  const t = c.temps;
  const s = c.series;
  const n = t.length;

  const calib = calibrer(rapports, maintenant);
  const vMax = spot.regionP.visibilite_max_m;
  const visibilite = res.visibilite_m.map((v) => Math.min(v * calib.facteur, vMax));
  const ressentie = res.visibilite_ressentie_m.map((v) => Math.min(v * calib.facteur, vMax));

  const i0 = rechercheGauche(t, maintenant - (maintenant % 3600));
  if (i0 >= n) throw new Error("Les données s'arrêtent avant l'heure demandée");
  const finLocale = minuitLocal(t[i0], fuseau, jours);
  const i1 = Math.min(n, rechercheGauche(t, finLocale));

  let base, ageSatJ = null;
  if (res.satellite_utilise && satellite) {
    ageSatJ = Math.max(0, (maintenant - satellite.temps) / 86400);
    base = P.INCERTITUDE_AVEC_SATELLITE + P.INCERTITUDE_AGE_SATELLITE_PAR_JOUR * ageSatJ;
  } else {
    base = P.INCERTITUDE_SANS_SATELLITE;
  }
  if (calib.nombre_effectif >= 5 && calib.dispersion < 0.3) base *= 0.8;
  const incertitude = t.map((x) => Math.min(base + P.INCERTITUDE_PAR_JOUR * Math.max(0, (x - maintenant) / 86400), P.INCERTITUDE_MAX));

  const deJour = t.map((x) => faitJour(spot.lat, spot.lon, x) && faitJour(spot.lat, spot.lon, x + 3600));
  const deTerre = s.direction_vent.map((d) => ventDeTerre(d, spot.orientation_deg));
  const houleSpot = hauteurAuSpot(spot, c);
  const { score, deconseille } = scoreHoraire(ressentie, houleSpot, s.rafales, s.vent, deTerre, spot.regionP.seuils[2]);

  const heures = [];
  for (let i = i0; i < i1; i++) {
    const v = visibilite[i], u = incertitude[i];
    const [conf, confTxt] = niveauConfiance(u);
    heures.push({
      heure: isoLocal(t[i], fuseau),
      visibilite_m: arrondir(v),
      fourchette_m: [arrondir(v * Math.exp(-u)), arrondir(v * Math.exp(u))],
      visibilite_ressentie_m: arrondir(ressentie[i]),
      classe: classe(v, spot),
      confiance: conf,
      confiance_texte: confTxt,
      de_jour: deJour[i],
      deconseille: deconseille[i],
      houle: {
        hauteur_m: nombre(s.hauteur_vagues[i], 1),
        periode_s: nombre(s.periode_vagues[i], 0),
        direction_deg: nombre(s.direction_vagues[i], 0),
        hauteur_au_spot_m: nombre(houleSpot[i], 1),
      },
      vent: {
        vitesse_kn: estFini(s.vent[i]) ? arrondiPair(s.vent[i] / P.NOEUD_EN_MS) : null,
        rafales_kn: estFini(s.rafales[i]) ? arrondiPair(s.rafales[i] / P.NOEUD_EN_MS) : null,
        direction_deg: nombre(s.direction_vent[i], 0),
        de_terre: estFini(s.direction_vent[i]) ? deTerre[i] : null,
      },
      courant_ms: nombre(s.courant[i], 2),
      niveau_mer_m: nombre(s.niveau_mer[i], 2),
      pluie_mm: nombre(s.pluie[i], 1),
      nebulosite_pct: nombre(s.nebulosite[i], 0),
      temperature_eau_c: nombre(s.temperature_eau[i], 1),
    });
  }

  const joursSortie = [];
  const moyennes = [];
  for (let d = 0; d < jours; d++) {
    const j0 = minuitLocal(t[i0], fuseau, d);
    const j1 = minuitLocal(t[i0], fuseau, d + 1);
    let a = rechercheGauche(t, j0);
    const b = rechercheGauche(t, j1);
    a = Math.max(a, i0);
    if (a >= b) break;
    const idx = [];
    for (let k = a; k < b; k++) idx.push(k);
    const masque = idx.map((k) => deJour[k]);
    const visJour = idx.filter((k) => deJour[k]).map((k) => visibilite[k]);
    const moy = visJour.length ? moyenne(visJour) : moyenne(idx.map((k) => visibilite[k]));
    moyennes.push(moy);
    const cr = meilleurCreneau(idx.map((k) => t[k]), idx.map((k) => score[k]), idx.map((k) => visibilite[k]), masque);
    let iRef = cr ? rechercheDroite(t, Math.floor((cr.debut + cr.fin) / 2)) - 1 : a + Math.floor((b - a) / 2);
    iRef = pince(iRef, a, b - 1);
    const phrases = expliquer(spot, c, res, iRef);
    const [lever, coucher] = leverCoucher(spot.lat, spot.lon, j0);
    const marees = res.extremes_maree
      .filter((e) => e.temps >= j0 && e.temps < j1)
      .map((e) => ({ type: e.type, heure: isoLocal(Math.trunc(e.temps), fuseau), hauteur_m: arrondiDecimales(e.hauteur, 2) }));
    const heuresJour = idx.filter((k) => deJour[k]);
    joursSortie.push({
      date: dateLocale(j0, fuseau),
      alerte: alerte(s, houleSpot, deconseille, heuresJour),
      visibilite_moyenne_m: arrondir(moy),
      classe: classe(moy, spot),
      meilleur_creneau: cr ? { debut: isoLocal(cr.debut, fuseau), fin: isoLocal(cr.fin, fuseau), visibilite_m: arrondir(cr.visibilite_moyenne) } : null,
      explication: phrases.join(" "),
      conseil_maree: conseilMaree(res, spot),
      deconseille_toute_la_journee: heuresJour.length ? heuresJour.every((k) => deconseille[k]) : false,
      lever_soleil: lever === null ? null : isoLocal(lever, fuseau),
      coucher_soleil: coucher === null ? null : isoLocal(coucher, fuseau),
      marees: spot.sensibilite_maree_effective > 0 ? marees : [],
    });
  }
  joursSortie.forEach((jour, d) => {
    jour.tendance = d + 1 < moyennes.length ? tendance(moyennes[d], moyennes[d + 1]) : null;
  });

  return {
    spot: { id: spot.id, nom: spot.nom, lat: spot.lat, lon: spot.lon },
    genere_le: new Date(maintenant * 1000).toISOString().replace(".000Z", "+00:00"),
    version_modele: VERSION_MODELE,
    satellite: { utilise: res.satellite_utilise, age_jours: ageSatJ === null ? null : arrondiDecimales(ageSatJ, 1) },
    calibrage: { facteur: arrondiDecimales(calib.facteur, 3), rapports: arrondiDecimales(calib.nombre_effectif, 1) },
    jours: joursSortie,
    heures,
    historique: Array.from({ length: i0 - Math.max(0, i0 - 48) }, (_, k) => {
      const i = Math.max(0, i0 - 48) + k;
      return { heure: isoLocal(t[i], fuseau), visibilite_m: arrondir(visibilite[i]) };
    }),
    // Pluie tombée pendant les 48 h écoulées
    pluie_48h_mm: arrondiDecimales(s.pluie.slice(Math.max(0, i0 - 48), i0).reduce((a, x) => (estFini(x) ? a + x : a), 0), 1),
    avertissement: "Prévision indicative : elle ne remplace pas l'observation sur place.",
    _brut: { visibilite: visibilite.slice(i0, i1) },
  };
}

function alerte(s, houleSpot, deconseille, heuresJour) {
  if (!heuresJour.length || !heuresJour.some((k) => deconseille[k])) return null;
  const raisons = [];
  const hMax = Math.max(0, ...heuresJour.map((k) => houleSpot[k]).filter(estFini));
  const rMax = Math.max(0, ...heuresJour.map((k) => s.rafales[k]).filter(estFini)) / P.NOEUD_EN_MS;
  if (hMax > P.HOULE_DECONSEILLEE_M) raisons.push(`houle jusqu'à ${formater(hMax, 1)} m au spot`);
  if (rMax > P.RAFALES_DECONSEILLEES_KN) raisons.push(`rafales jusqu'à ${formater(rMax, 0)} nœuds`);
  const debut = heuresJour.every((k) => deconseille[k]) ? "Sortie déconseillée" : "Sortie déconseillée à certaines heures";
  return raisons.length ? `${debut} : ${raisons.join(" et ")}.` : `${debut}.`;
}
