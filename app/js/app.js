// Kelvisi : point d'entrée de l'application (navigation, carte, recherche, état partagé).

import { demarrer, pointPublic, previsionLieu } from "./donnees.js";
import { afficherReperes, cacherCible, creerCarte, definirCouches, montrerCible, redimensionner, voler } from "./carte.js";
import { rechercherLieux } from "./recherche.js";
import { afficherListe } from "./vues/liste.js";
import { afficherFiche } from "./vues/fiche.js";
import { afficherMesSpots } from "./vues/messpots.js";
import { afficherInfos } from "./vues/infos.js";
import { mesSpots } from "./messpots.js";
import { chargerCommunaute, idCommunaute, oublierCommunaute, spotCommunaute, spotsCommunaute } from "./communaute.js";
import { rapportsPourMoteur, renvoyerEnAttente } from "./retours.js";
import { lire, ecrire } from "./stockage.js";
import { comptesActifs, lireProfil, session, traiterLienRecu } from "./compte.js";
import { effacerDonneesLocales, synchroniser } from "./synchro.js";
import { afficherEcranCompte, afficherMonCompte, masquerEcranCompte } from "./vues/compte.js";
import { NOM_CLASSE, dateHeure, decrireMesure, distanceKm, echapper, heure, jourCourt, metres, ventDansTexte } from "./format.js";
import { meilleureMesure, profondeursAuPoint } from "./bathymetrie.js";
import { encartZones, zonesAuPoint } from "./zones.js";
import { verifierAbonnement } from "./alertes.js";
import { tranchesLegende } from "./relief-rendu.js";

const large = window.matchMedia("(min-width: 960px)");
const panneau = document.getElementById("panneau");
const ficheRapide = document.getElementById("fiche-rapide");
const bandeau = document.getElementById("bandeau");

const prefs = lire("kelvisi-reglages", {});
const etat = {
  jour: 0,
  rayon: [15, 30, 60, 100, 200].includes(prefs.rayon) ? prefs.rayon : 60,
  origine: null,
  selection: null,
  route: null,
};
const previsionsPrivees = new Map();
const pile = [];

const ctx = {
  etat,
  resume: null,
  previsionsPrivees,
  jeton: null,
  allerA,
  revenir,
  memoriser,
  surJour: () => { majJoursCarte(); majReperes(); },
  surSpotsModifies: () => { calculerMesSpots(); majReperes(); },
  calculerProches: (origine, rayon) => calculerCommunauteProches(origine, rayon),
  voirSurCarte: (lat, lon, id) => {
    etat.selection = id;
    if (!large.matches) allerA("#/carte");
    voler(lat, lon, 11);
    majReperes();
  },
};

function memoriser() {
  ecrire("kelvisi-reglages", { ...lire("kelvisi-reglages", {}), rayon: etat.rayon });
}

// --- Navigation -----------------------------------------------------------------------------

function allerA(hash) {
  if (location.hash === hash) naviguer();
  else location.hash = hash;
}

function revenir() {
  pile.pop();
  const precedent = pile.pop();
  allerA(precedent || (large.matches ? "#/liste" : "#/carte"));
}

function lireRoute() {
  const morceaux = (location.hash || "").replace(/^#\/?/, "").split("/").filter(Boolean).map(decodeURIComponent);
  const [nom, a, b] = morceaux;
  switch (nom) {
    case "liste": return { nom: "liste" };
    case "spot": return { nom: "fiche", cible: { type: "public", id: a } };
    case "prive": return { nom: "fiche", cible: { type: "prive", id: a } };
    case "partage": return { nom: "fiche", cible: { type: "communaute", id: idCommunaute(a) } };
    case "point": {
      const lat = Number(a), lon = Number(b);
      if (Number.isFinite(lat) && Number.isFinite(lon)) return { nom: "fiche", cible: { type: "point", lat, lon } };
      return { nom: "carte" };
    }
    case "mes-spots": return { nom: "mes-spots" };
    case "infos": return { nom: "infos", page: a };
    case "compte": return { nom: "compte" };
    case "carte": return { nom: "carte" };
    default: return { nom: large.matches ? "liste" : "carte" };
  }
}

function naviguer() {
  if (!ctx.resume) return;
  const route = lireRoute();
  etat.route = route;
  if (pile[pile.length - 1] !== location.hash) pile.push(location.hash);
  if (pile.length > 30) pile.shift();

  // Un seul onglet actif : la fiche d'un point Kelvisi dépend de « Où aller ? », celle d'un lieu libre de la carte
  const onglet = route.nom === "fiche" ? { prive: "mes-spots", point: "carte", public: "liste", communaute: "carte" }[route.cible.type]
    : route.nom === "compte" ? "infos" : route.nom;
  document.querySelectorAll(".onglets a").forEach((a) => {
    if (a.dataset.onglet === onglet) a.setAttribute("aria-current", "page");
    else a.removeAttribute("aria-current");
  });
  document.body.classList.toggle("route-carte", route.nom === "carte");
  if (route.nom !== "carte") fermerFicheRapide();
  if (route.nom === "carte") redimensionner();

  ctx.jeton = null;
  switch (route.nom) {
    case "carte":
      if (large.matches) afficherListe(panneau, ctx);
      break;
    case "liste":
      afficherListe(panneau, ctx);
      if (etat.origine) calculerCommunauteProches(etat.origine, etat.rayon);
      break;
    case "mes-spots":
      afficherMesSpots(panneau, ctx);
      break;
    case "infos":
      afficherInfos(panneau, route.page, ctx);
      break;
    case "compte":
      afficherMonCompte(panneau, ctx);
      break;
    case "fiche": {
      const c = route.cible;
      etat.selection = c.type === "point" ? null : c.id;
      if (c.type === "point") montrerCible(c.lat, c.lon);
      else cacherCible();
      afficherFiche(panneau, c, ctx);
      break;
    }
  }
  if (route.nom !== "fiche" || route.cible.type !== "point") cacherCible();
  if (route.nom === "fiche" && route.cible.type === "point") montrerCible(route.cible.lat, route.cible.lon);
  panneau.scrollTop = 0;
  majReperes();
}

// --- Carte ------------------------------------------------------------------------------------

function pointsCarte() {
  const r = ctx.resume;
  const points = r.points.map((p) => {
    const j = p.jours[Math.min(etat.jour, p.jours.length - 1)];
    const visi = j.meilleur_creneau ? j.meilleur_creneau.visibilite_m : j.visibilite_moyenne_m;
    return { id: p.id, nom: p.nom, lat: p.lat, lon: p.lon, visi, classe: j.classe, prive: false };
  });
  const visiDuJour = (pr) => {
    const j = pr ? pr.jours[Math.min(etat.jour, pr.jours.length - 1)] : null;
    return { visi: j ? (j.meilleur_creneau ? j.meilleur_creneau.visibilite_m : j.visibilite_moyenne_m) : null, classe: j ? j.classe : "" };
  };
  for (const s of mesSpots()) {
    points.push({ id: s.id, nom: s.nom, lat: s.lat, lon: s.lon, prive: true, type: "prive", ...visiDuJour(previsionsPrivees.get(s.id)) });
  }
  for (const s of spotsCommunaute(mesSpots().map((x) => x.partage_id))) {
    points.push({ id: s.id, nom: s.nom, lat: s.lat, lon: s.lon, prive: false, type: "communaute", ...visiDuJour(previsionsPrivees.get(s.id)) });
  }
  return points;
}

function majReperes() {
  if (ctx.resume) afficherReperes(pointsCarte(), etat.selection);
}

function majJoursCarte() {
  const zone = document.getElementById("jours-carte");
  const dates = ctx.resume.points[0] ? ctx.resume.points[0].jours.map((j) => j.date) : [];
  zone.innerHTML = dates.map((d, i) => `<button type="button" data-jour="${i}" aria-pressed="${i === etat.jour}">${jourCourt(d)}</button>`).join("");
}

function fermerFicheRapide() {
  ficheRapide.hidden = true;
  ficheRapide.innerHTML = "";
}

function ouvrirFicheRapide(html, lier) {
  ficheRapide.innerHTML = `<div class="haut"><div>${html.titre}</div><button type="button" class="fermer" aria-label="Fermer">×</button></div>${html.corps}`;
  ficheRapide.hidden = false;
  ficheRapide.querySelector(".fermer").addEventListener("click", () => { fermerFicheRapide(); cacherCible(); });
  if (lier) lier(ficheRapide);
}

function pointsProches(lat, lon, n = 3) {
  return ctx.resume.points
    .map((p) => ({ p, d: distanceKm(lat, lon, p.lat, p.lon) }))
    .sort((a, b) => a.d - b.d)
    .slice(0, n);
}

function listeProches(lat, lon) {
  const proches = pointsProches(lat, lon);
  return `<div><span class="etiquette">Points Kelvisi les plus proches</span><ul>${proches.map(({ p, d }) => {
    const j = p.jours[Math.min(etat.jour, p.jours.length - 1)];
    const v = j.meilleur_creneau ? j.meilleur_creneau.visibilite_m : j.visibilite_moyenne_m;
    return `<li><button type="button" data-aller="#/spot/${p.id}"><span>${echapper(p.nom)} <span class="note">${Math.round(d)} km</span></span><strong class="chiffres">${metres(v)} m</strong></button></li>`;
  }).join("")}</ul></div>`;
}

function lierAllers(zone) {
  zone.querySelectorAll("[data-aller]").forEach((b) => b.addEventListener("click", () => allerA(b.dataset.aller)));
}

function surPoint(id, type) {
  etat.selection = id;
  majReperes();
  const lienCommunaute = () => `#/partage/${encodeURIComponent(spotCommunaute(id)?.uuid || "")}`;
  if (large.matches) {
    allerA(type === "prive" ? `#/prive/${id}` : type === "communaute" ? lienCommunaute() : `#/spot/${id}`);
    return;
  }
  if (type === "communaute") {
    const s = spotCommunaute(id);
    const pr = previsionsPrivees.get(id);
    const j = pr ? pr.jours[Math.min(etat.jour, pr.jours.length - 1)] : null;
    ouvrirFicheRapide({ titre: `<strong>${echapper(s ? s.nom : "Spot partagé")}</strong><br><span class="note">Spot partagé</span>`, corps: resumeJour(j, lienCommunaute()) }, lierAllers);
    return;
  }
  const prive = type === "prive";
  if (prive) {
    const s = mesSpots().find((x) => x.id === id);
    const pr = previsionsPrivees.get(id);
    const j = pr ? pr.jours[Math.min(etat.jour, pr.jours.length - 1)] : null;
    ouvrirFicheRapide({ titre: `<strong>${echapper(s ? s.nom : "Mon spot")}</strong><br><span class="note">Mon spot</span>`, corps: resumeJour(j, `#/prive/${id}`) }, lierAllers);
    return;
  }
  const p = pointPublic(id);
  const j = p.jours[Math.min(etat.jour, p.jours.length - 1)];
  ouvrirFicheRapide({ titre: `<strong>${echapper(p.nom)}</strong><br><span class="note">${jourCourt(j.date)}</span>`, corps: resumeJour(j, `#/spot/${id}`) }, lierAllers);
}

function resumeJour(j, lien) {
  if (!j) return `<p class="note">Prévision en cours de calcul…</p><button type="button" class="bouton" data-aller="${lien}">Ouvrir la fiche</button>`;
  const v = j.meilleur_creneau ? j.meilleur_creneau.visibilite_m : j.visibilite_moyenne_m;
  return `<div class="rangee"><span class="gros chiffres">${metres(v)} m</span><span class="classe" style="background:var(--v-${j.classe})">${NOM_CLASSE[j.classe]}</span></div>
    <p class="note">${j.meilleur_creneau ? `Meilleur créneau de ${heure(j.meilleur_creneau.debut)} à ${heure(j.meilleur_creneau.fin)}.` : "Aucun créneau conseillé."} ${echapper(ventDansTexte(j.explication))}</p>
    ${j.alerte ? `<p class="encart alerte">${echapper(ventDansTexte(j.alerte))}</p>` : ""}
    <button type="button" class="bouton" data-aller="${lien}">Voir la prévision</button>`;
}

function surMer({ lat, lon, enMer }) {
  montrerCible(lat, lon);
  const coord = `${lat.toFixed(5)}/${lon.toFixed(5)}`;
  if (large.matches && enMer) {
    allerA(`#/point/${coord}`);
    return;
  }
  ouvrirFicheRapide({
    titre: `<strong>${enMer ? "Prévision à cet endroit ?" : "Ce point semble à terre"}</strong>`,
    corps: `${enMer ? '<p class="note">Kelvisi estime la profondeur et l\'orientation du lieu, puis calcule la visibilité.</p>' : '<p class="note">Touche la mer, près de la côte, là où tu veux chasser.</p>'}
      <div data-zones-rapide hidden></div>
      <p class="profondeur-rapide" data-profondeur hidden></p>
      <div class="rangee"><button type="button" class="bouton" data-aller="#/point/${coord}">${enMer ? "Calculer la prévision" : "Calculer quand même"}</button></div>
      ${listeProches(lat, lon)}`,
  }, lierAllers);
  afficherProfondeurRapide(lat, lon);
  afficherZonesRapide(lat, lon);
}

// Zone de pêche sous-marine interdite ou réglementée à cet endroit, ajoutée à la fiche rapide
async function afficherZonesRapide(lat, lon) {
  try {
    const liste = await zonesAuPoint(lat, lon);
    const zone = ficheRapide.querySelector("[data-zones-rapide]");
    if (!liste.length || !zone) return;
    zone.innerHTML = encartZones(liste, { court: true });
    zone.hidden = false;
  } catch (e) {
    /* fichier des zones indisponible : rien à signaler */
  }
}

// Profondeur lue sur les cartes du Shom, ajoutée à la fiche rapide dès qu'elle arrive
async function afficherProfondeurRapide(lat, lon) {
  try {
    const m = meilleureMesure(await profondeursAuPoint(lat, lon));
    const zone = ficheRapide.querySelector("[data-profondeur]");
    if (!m || !zone) return;
    const d = decrireMesure(m);
    zone.innerHTML = `<strong class="chiffres">Profondeur : ${d.valeur}</strong><br><span class="note">${echapper(d.reference)}${d.reference ? " · " : ""}${echapper(d.source)}</span>`;
    zone.hidden = false;
  } catch (e) {
    /* sans réseau : la fiche rapide reste sans profondeur */
  }
}

// --- Recherche ----------------------------------------------------------------------------------

function initialiserRecherche() {
  const form = document.getElementById("recherche");
  const champ = document.getElementById("recherche-texte");
  const liste = document.getElementById("recherche-resultats");
  let minuterie = null, controleur = null, resultats = [];

  const montrer = (html) => { liste.innerHTML = html; liste.hidden = false; };
  const cacher = () => { liste.hidden = true; };

  async function chercher() {
    const q = champ.value.trim();
    if (q.length < 3) { cacher(); return; }
    if (controleur) controleur.abort();
    controleur = new AbortController();
    montrer('<li class="message">Recherche…</li>');
    try {
      resultats = await rechercherLieux(q, controleur.signal);
      if (!resultats.length) { montrer('<li class="message">Aucun lieu trouvé sur les côtes françaises.</li>'); return; }
      montrer(resultats.map((r, i) => `<li><button type="button" data-i="${i}"><span>${echapper(r.nom)}</span><span class="detail">${echapper(r.detail)}</span></button></li>`).join(""));
    } catch (e) {
      if (e.name !== "AbortError") montrer('<li class="message">Recherche indisponible pour le moment. Vérifie ta connexion.</li>');
    }
  }

  champ.addEventListener("input", () => {
    clearTimeout(minuterie);
    minuterie = setTimeout(chercher, 350);
  });
  form.addEventListener("submit", (e) => {
    e.preventDefault();
    if (resultats.length && !liste.hidden) choisir(resultats[0]);
    else chercher();
  });
  liste.addEventListener("click", (e) => {
    const b = e.target.closest("button[data-i]");
    if (b) choisir(resultats[Number(b.dataset.i)]);
  });
  document.addEventListener("click", (e) => { if (!form.contains(e.target)) cacher(); });
  champ.addEventListener("keydown", (e) => { if (e.key === "Escape") cacher(); });

  function choisir(r) {
    cacher();
    champ.blur();
    etat.origine = { type: "lieu", nom: r.nom, lat: r.lat, lon: r.lon };
    if (!large.matches && etat.route?.nom !== "carte") allerA("#/carte");
    voler(r.lat, r.lon, r.type === "commune" ? 11 : 12.5);
    montrerCible(r.lat, r.lon);
    const coord = `${r.lat.toFixed(5)}/${r.lon.toFixed(5)}`;
    ouvrirFicheRapide({
      titre: `<strong>${echapper(r.nom)}</strong><br><span class="note">${echapper(r.detail)}</span>`,
      corps: `<p class="note">Touche la mer sur la carte à l'endroit précis où tu veux chasser, ou calcule la prévision pour ce lieu.</p>
        <div class="rangee"><button type="button" class="bouton" data-aller="#/point/${coord}">Prévision ici</button>
        <button type="button" class="bouton secondaire" data-aller="#/liste">Où aller depuis ici ?</button></div>
        ${listeProches(r.lat, r.lon)}`,
    }, lierAllers);
    if (large.matches && etat.route?.nom === "liste") afficherListe(panneau, ctx);
    calculerCommunauteProches(etat.origine, etat.rayon);
  }
}

// --- Spots privés -------------------------------------------------------------------------------

let calculEnCours = false;
async function calculerMesSpots() {
  if (calculEnCours) return;
  calculEnCours = true;
  try {
    for (const s of mesSpots()) {
      try {
        const { prevision } = await previsionLieu(s, { rapports: rapportsPourMoteur(s.id) });
        previsionsPrivees.set(s.id, prevision);
      } catch (e) {
        /* sans réseau ni météo en mémoire : le spot reste « à calculer » */
      }
      majReperes();
      const r = etat.route?.nom;
      if (r === "liste" || r === "mes-spots" || (r === "carte" && large.matches)) {
        const y = panneau.scrollTop;
        if (r === "mes-spots") afficherMesSpots(panneau, ctx);
        else afficherListe(panneau, ctx);
        panneau.scrollTop = y;
      }
    }
  } finally {
    calculEnCours = false;
  }
}

// Spots partagés proches d'un point de départ : calculés dans le navigateur (10 au plus à la fois)
let prochesEnCours = false;
async function calculerCommunauteProches(origine, rayon) {
  if (prochesEnCours || !origine) return;
  prochesEnCours = true;
  try {
    const aCalculer = spotsCommunaute(mesSpots().map((x) => x.partage_id))
      .map((s) => ({ s, d: distanceKm(origine.lat, origine.lon, s.lat, s.lon) }))
      .filter(({ s, d }) => d <= rayon && !previsionsPrivees.has(s.id))
      .sort((a, b) => a.d - b.d)
      .slice(0, 10);
    for (const { s } of aCalculer) {
      try {
        const { prevision } = await previsionLieu(s, { rapports: rapportsPourMoteur(s.id) });
        previsionsPrivees.set(s.id, prevision);
      } catch (e) {
        /* sans réseau : le spot reste « à calculer » */
      }
    }
    if (aCalculer.length) {
      majReperes();
      if (etat.route?.nom === "liste" || (etat.route?.nom === "carte" && large.matches)) {
        const y = panneau.scrollTop;
        afficherListe(panneau, ctx);
        panneau.scrollTop = y;
      }
    }
  } finally {
    prochesEnCours = false;
  }
}

// --- Fraîcheur et connexion ---------------------------------------------------------------------

function majFraicheur() {
  const r = ctx.resume;
  const age = (Date.now() - Date.parse(r.genere_le)) / 3600000;
  document.getElementById("fraicheur").textContent = `Prévisions ${dateHeure(r.genere_le)}`;
  let message = "";
  if (window.KELVISI_APERCU) message = `Aperçu : prévisions réelles calculées ${dateHeure(r.genere_le)}, carte simplifiée. La recherche et les lieux libres fonctionnent sur le site en ligne.`;
  else if (!navigator.onLine) message = `Hors ligne : prévisions du ${dateHeure(r.genere_le)}.`;
  else if (age > 3) message = `Les prévisions n'ont pas été mises à jour depuis ${Math.round(age)} heures.`;
  bandeau.textContent = message;
  bandeau.hidden = !message;
}

// --- Comptes -------------------------------------------------------------------------------------

let minuterieAnnonce = null;
function annoncer(texte) {
  bandeau.textContent = texte;
  bandeau.hidden = false;
  clearTimeout(minuterieAnnonce);
  minuterieAnnonce = setTimeout(majFraicheur, 6000);
}

async function surConnexion() {
  masquerEcranCompte();
  await chargerCommunaute().catch(() => {});
  const r = await synchroniser();
  if (r && !r.ok && r.raison === "erreur") annoncer("Tes spots n'ont pas pu être synchronisés. Nouvel essai au prochain démarrage.");
  lireProfil().catch(() => {});
  verifierAbonnement();
}

function lierComptes(lien) {
  document.addEventListener("kelvisi-compte", (e) => {
    if (e.detail.connecte) {
      surConnexion();
      return;
    }
    effacerDonneesLocales();
    oublierCommunaute();
    previsionsPrivees.clear();
    majReperes();
    afficherEcranCompte("connexion");
    allerA(large.matches ? "#/liste" : "#/carte");
  });
  document.addEventListener("kelvisi-communaute", () => majReperes());
  document.addEventListener("kelvisi-synchro", () => {
    calculerMesSpots();
    majReperes();
    if (etat.route?.nom === "mes-spots") afficherMesSpots(panneau, ctx);
  });
  document.addEventListener("kelvisi-message", (e) => annoncer(e.detail));
  window.addEventListener("online", () => { if (session()) synchroniser().catch(() => {}); });

  if (lien?.type === "recovery") afficherEcranCompte("nouveau-mot-de-passe");
  else if (!session()) afficherEcranCompte(lien?.erreur ? "connexion" : "inscription", { info: lien?.erreur || "" });
  else {
    surConnexion();
    if (lien?.type === "signup") annoncer("Adresse confirmée : ton compte est actif. Bienvenue !");
  }
}

// --- Démarrage ----------------------------------------------------------------------------------

// Échelle des teintes de la carte des profondeurs (mêmes couleurs que le relief dessiné)
function remplirEchelleProfondeurs() {
  const el = document.getElementById("echelle-profondeurs");
  if (!el || el.childElementCount) return;
  const tranches = tranchesLegende();
  const graduees = new Set([0, 5, 10, 20, 30, 50, 100]);
  el.innerHTML = tranches.map((t) => `<i style="background:rgb(${t.couleur.join(",")})" title="${t.a === null ? `plus de ${t.de} m` : `${t.de} à ${t.a} m`}"></i>`).join("")
    + tranches.map((t, k) => (graduees.has(t.de) ? `<b style="left:${((100 * k) / tranches.length).toFixed(2)}%">${t.de === 100 ? "100 m" : t.de}</b>` : "")).join("");
}

function lierOutilsCarte() {
  remplirEchelleProfondeurs();
  const fond = document.getElementById("fond-carte");
  const couches = { aerien: Boolean(prefs.aerien), profondeurs: Boolean(prefs.profondeurs), zones: Boolean(prefs.zones) };
  const appliquer = () => {
    fond.querySelector('[data-fond="plan"]').setAttribute("aria-pressed", String(!couches.aerien));
    fond.querySelector('[data-fond="aerien"]').setAttribute("aria-pressed", String(couches.aerien));
    fond.querySelector("[data-profondeurs]").setAttribute("aria-pressed", String(couches.profondeurs));
    fond.querySelector("[data-zones]").setAttribute("aria-pressed", String(couches.zones));
    document.getElementById("legende-profondeurs").hidden = !couches.profondeurs;
    document.getElementById("legende-zones").hidden = !couches.zones;
    definirCouches(couches);
    ecrire("kelvisi-reglages", { ...lire("kelvisi-reglages", {}), aerien: couches.aerien, profondeurs: couches.profondeurs, zones: couches.zones });
  };
  fond.addEventListener("click", (e) => {
    const b = e.target.closest("button");
    if (!b) return;
    if (b.dataset.fond) couches.aerien = b.dataset.fond === "aerien";
    if (b.hasAttribute("data-profondeurs")) couches.profondeurs = !couches.profondeurs;
    if (b.hasAttribute("data-zones")) couches.zones = !couches.zones;
    appliquer();
  });
  document.getElementById("jours-carte").addEventListener("click", (e) => {
    const b = e.target.closest("button");
    if (!b) return;
    etat.jour = Number(b.dataset.jour);
    majJoursCarte();
    majReperes();
    if (large.matches && (etat.route?.nom === "liste" || etat.route?.nom === "carte")) afficherListe(panneau, ctx);
  });
  appliquer();
}

async function lancer() {
  // Lien reçu par e-mail (confirmation, nouveau mot de passe) : lu avant toute navigation
  const comptes = comptesActifs() && !window.KELVISI_APERCU;
  const lien = comptes ? await traiterLienRecu() : null;
  try {
    ctx.resume = await demarrer();
  } catch (e) {
    panneau.innerHTML = `<p class="erreur">Impossible de charger les prévisions.</p><p class="note">Vérifie ta connexion puis réessaie.</p>
      <button type="button" class="bouton" id="reessayer">Réessayer</button>`;
    document.getElementById("reessayer").addEventListener("click", () => location.reload());
    document.body.classList.remove("route-carte");
    return;
  }
  creerCarte(document.getElementById("carte"), { surPoint, surMer });
  lierOutilsCarte();
  majJoursCarte();
  initialiserRecherche();
  majFraicheur();
  window.addEventListener("online", () => { majFraicheur(); renvoyerEnAttente(); });
  window.addEventListener("offline", majFraicheur);
  window.addEventListener("hashchange", naviguer);
  large.addEventListener("change", () => { naviguer(); redimensionner(); });
  naviguer();
  if (comptes) lierComptes(lien);
  calculerMesSpots();
  renvoyerEnAttente();
  setInterval(majFraicheur, 10 * 60 * 1000);
}

if ("serviceWorker" in navigator && (location.protocol === "https:" || location.hostname === "localhost")) {
  navigator.serviceWorker.register("sw.js").catch(() => { /* l'appli fonctionne sans */ });
}

lancer();
