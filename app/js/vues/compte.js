// Écrans du compte : accueil (inscription, connexion, mot de passe oublié), nouveau mot de passe,
// et page « Mon compte » (profil, accord e-mails, mot de passe, alertes, export, suppression).

import {
  PRATIQUES, TRANCHES_AGE, changerMotDePasse, connecter, deconnecter, inscrire, lireProfil, modifierProfil,
  motDePasseOublie, profilEnMemoire, renvoyerConfirmation, supprimerCompte, utilisateur, verifierDepartement,
  verifierMotDePasse,
} from "../compte.js";
import { effacerDonneesLocales, noterAlerte, synchroniser } from "../synchro.js";
import { NIVEAUX, alertes, choisirAlerte, desabonnerAppareil } from "../alertes.js";
import { pointPublic } from "../donnees.js";
import { mesSpots, monSpot } from "../messpots.js";
import { favoris } from "../favoris.js";
import { echapper, dateHeure } from "../format.js";
import { contenuPage } from "./infos.js";

const ecran = () => document.getElementById("ecran-compte");

// --- Morceaux de formulaire ------------------------------------------------------------------

function champsProfil(p = {}) {
  const pratiques = new Set(p.pratiques || []);
  return `
    <label class="champ"><span>Prénom</span><input name="prenom" type="text" autocomplete="given-name" maxlength="50" required value="${echapper(p.prenom || "")}"></label>
    <label class="champ"><span>Département</span><input name="departement" type="text" inputmode="text" autocomplete="off" maxlength="3" required
      placeholder="29, 2A, 974…" value="${echapper(p.departement || "")}"><small>Où tu habites. 99 si tu vis à l'étranger.</small></label>
    <fieldset class="champ"><legend>Ce que tu pratiques</legend>
      <div class="cases">${Object.entries(PRATIQUES).map(([v, t]) => `<label class="case"><input type="checkbox" name="pratiques" value="${v}" ${pratiques.has(v) ? "checked" : ""}> ${t}</label>`).join("")}</div>
    </fieldset>
    <label class="champ"><span>Âge</span><select name="tranche_age" required>
      <option value="">Choisir…</option>${TRANCHES_AGE.map((t) => `<option value="${t}" ${p.tranche_age === t ? "selected" : ""}>${t === "65+" ? "65 ans et plus" : `${t.replace("-", " à ")} ans`}</option>`).join("")}
    </select><small>Kelvisi est réservé aux 15 ans et plus.</small></label>
    <label class="case"><input type="checkbox" name="accord_emails" ${p.accord_emails ? "checked" : ""}>
      J'accepte de recevoir des e-mails de Kelvisi (nouveautés, offres). Je peux me désinscrire à tout moment.</label>`;
}

function lireProfilFormulaire(form) {
  const f = new FormData(form);
  return {
    prenom: String(f.get("prenom") || "").trim(),
    departement: String(f.get("departement") || "").trim().toUpperCase(),
    pratiques: f.getAll("pratiques").map(String),
    tranche_age: String(f.get("tranche_age") || ""),
    accord_emails: f.get("accord_emails") === "on",
  };
}

function verifierProfil(p) {
  if (!p.prenom) return "Indique ton prénom.";
  const d = verifierDepartement(p.departement);
  if (d) return d;
  if (!p.pratiques.length) return "Coche au moins une pratique.";
  if (!p.tranche_age) return "Indique ta tranche d'âge.";
  return null;
}

function champMotDePasse(nom = "mot_de_passe", libelle = "Mot de passe", nouveau = true) {
  return `<label class="champ"><span>${libelle}</span>
    <span class="avec-bouton"><input name="${nom}" type="password" autocomplete="${nouveau ? "new-password" : "current-password"}" required minlength="${nouveau ? 8 : 1}">
    <button type="button" class="lien" data-voir>Afficher</button></span>
    ${nouveau ? "<small>Au moins 8 caractères, avec des lettres et des chiffres.</small>" : ""}</label>`;
}

function lierAffichageMotDePasse(zone) {
  zone.querySelectorAll("[data-voir]").forEach((b) => b.addEventListener("click", () => {
    const champ = b.parentElement.querySelector("input");
    const visible = champ.type === "text";
    champ.type = visible ? "password" : "text";
    b.textContent = visible ? "Afficher" : "Masquer";
  }));
}

function message(zone, texte, type = "erreur") {
  const m = zone.querySelector("[data-message]");
  m.textContent = texte;
  m.className = type === "erreur" ? "erreur" : "confirmation";
  m.hidden = !texte;
  if (texte) m.scrollIntoView?.({ block: "nearest" });
}

async function occupe(bouton, travail) {
  bouton.disabled = true;
  try {
    return await travail();
  } finally {
    bouton.disabled = false;
  }
}

// --- Écran d'accueil (obligatoire tant que l'on n'est pas connecté) -------------------------------

export function afficherEcranCompte(mode = "inscription", { info = "", email = "" } = {}) {
  const z = ecran();
  z.hidden = false;
  document.body.classList.add("compte-requis");
  const entete = `<div class="ecran-entete"><span class="marque">Kel<i>visi</i></span>
    <p>La visibilité sous l'eau, prévue heure par heure sur les côtes françaises.</p></div>`;
  const pied = `<p class="note pied-compte"><button type="button" class="lien" data-page="cgu">Conditions d'utilisation</button> ·
    <button type="button" class="lien" data-page="confidentialite">Confidentialité</button> ·
    <button type="button" class="lien" data-page="mentions">Mentions légales</button></p>`;
  const vues = {
    inscription: () => `
      <h1 class="titre-vue">Créer mon compte</h1>
      <p class="note">Gratuit pendant la bêta. Tes spots privés et tes favoris te suivent sur tous tes appareils.</p>
      <form class="formulaire" novalidate data-form="inscription">
        <label class="champ"><span>E-mail</span><input name="email" type="email" autocomplete="email" required value="${echapper(email)}"></label>
        ${champMotDePasse()}
        ${champsProfil()}
        <label class="case"><input type="checkbox" name="cgu" required> J'ai lu et j'accepte les
          <button type="button" class="lien" data-page="cgu">conditions d'utilisation</button> et la
          <button type="button" class="lien" data-page="confidentialite">politique de confidentialité</button>.</label>
        <p data-message hidden></p>
        <button type="submit" class="bouton">Créer mon compte</button>
      </form>
      <p class="texte">Déjà inscrit ? <button type="button" class="lien" data-mode="connexion">Me connecter</button></p>`,
    connexion: () => `
      <h1 class="titre-vue">Me connecter</h1>
      <form class="formulaire" novalidate data-form="connexion">
        <label class="champ"><span>E-mail</span><input name="email" type="email" autocomplete="email" required value="${echapper(email)}"></label>
        ${champMotDePasse("mot_de_passe", "Mot de passe", false)}
        <p data-message hidden></p>
        <div class="rangee"><button type="submit" class="bouton">Me connecter</button>
          <button type="button" class="lien" data-mode="oubli">Mot de passe oublié ?</button></div>
      </form>
      <p class="texte">Pas encore de compte ? <button type="button" class="lien" data-mode="inscription">Créer mon compte</button></p>`,
    oubli: () => `
      <h1 class="titre-vue">Mot de passe oublié</h1>
      <p class="note">Indique ton adresse : tu recevras un lien pour choisir un nouveau mot de passe.</p>
      <form class="formulaire" novalidate data-form="oubli">
        <label class="champ"><span>E-mail</span><input name="email" type="email" autocomplete="email" required value="${echapper(email)}"></label>
        <p data-message hidden></p>
        <button type="submit" class="bouton">Recevoir le lien</button>
      </form>
      <p class="texte"><button type="button" class="lien" data-mode="connexion">Retour à la connexion</button></p>`,
    confirmer: () => `
      <h1 class="titre-vue">Vérifie ta boîte mail</h1>
      <p class="texte">Un e-mail de confirmation vient d'être envoyé à <strong>${echapper(email)}</strong>. Clique sur le lien qu'il contient pour activer ton compte.</p>
      <p class="note">Rien reçu après quelques minutes ? Regarde dans les indésirables.</p>
      <p data-message hidden></p>
      <div class="rangee"><button type="button" class="bouton secondaire" data-renvoyer>Renvoyer l'e-mail</button>
        <button type="button" class="lien" data-mode="connexion">J'ai confirmé, me connecter</button></div>`,
    "nouveau-mot-de-passe": () => `
      <h1 class="titre-vue">Nouveau mot de passe</h1>
      <form class="formulaire" novalidate data-form="nouveau">
        ${champMotDePasse("mot_de_passe", "Nouveau mot de passe")}
        <p data-message hidden></p>
        <button type="submit" class="bouton">Enregistrer</button>
      </form>`,
  };
  z.innerHTML = `<div class="ecran-contenu">${entete}<div class="bloc" data-vue>${vues[mode]()}</div>${pied}</div>
    <div class="page-modale" hidden></div>`;
  if (info) message(z, info, /expir|plus valable|Impossible/.test(info) ? "erreur" : "ok");

  lierAffichageMotDePasse(z);
  z.querySelectorAll("[data-mode]").forEach((b) => b.addEventListener("click", () => {
    const champ = z.querySelector('input[name="email"]');
    afficherEcranCompte(b.dataset.mode, { email: champ ? champ.value : email });
  }));
  z.querySelectorAll("[data-page]").forEach((b) => b.addEventListener("click", () => ouvrirPage(z, b.dataset.page)));

  const form = z.querySelector("form");
  if (form) form.addEventListener("submit", (e) => { e.preventDefault(); soumettre(z, form); });
  const renvoi = z.querySelector("[data-renvoyer]");
  if (renvoi) renvoi.addEventListener("click", () => occupe(renvoi, async () => {
    try {
      await renvoyerConfirmation(email);
      message(z, "E-mail renvoyé.", "ok");
    } catch (err) {
      message(z, err.message);
    }
  }));
  z.querySelector("input")?.focus?.();
}

export function masquerEcranCompte() {
  const z = ecran();
  z.hidden = true;
  z.innerHTML = "";
  document.body.classList.remove("compte-requis");
}

function ouvrirPage(z, page) {
  const modale = z.querySelector(".page-modale");
  modale.innerHTML = `<div class="ecran-contenu"><button type="button" class="retour" data-fermer>← Retour</button>
    <article class="page-infos bloc">${contenuPage(page)}</article></div>`;
  modale.hidden = false;
  modale.scrollTop = 0;
  modale.querySelector("[data-fermer]").addEventListener("click", () => { modale.hidden = true; modale.innerHTML = ""; });
}

async function soumettre(z, form) {
  const bouton = form.querySelector('button[type="submit"]');
  const f = new FormData(form);
  const email = String(f.get("email") || "").trim();
  const mdp = String(f.get("mot_de_passe") || "");
  message(z, "");
  await occupe(bouton, async () => {
    try {
      switch (form.dataset.form) {
        case "inscription": {
          if (!/^[^@\s]+@[^@\s]+\.[^@\s]+$/.test(email)) return message(z, "Adresse e-mail invalide.");
          const m = verifierMotDePasse(mdp);
          if (m) return message(z, `Mot de passe : ${m}`);
          const p = lireProfilFormulaire(form);
          const erreur = verifierProfil(p);
          if (erreur) return message(z, erreur);
          if (!form.querySelector('input[name="cgu"]').checked) return message(z, "Accepte les conditions d'utilisation pour créer ton compte.");
          const etat = await inscrire({
            email, motDePasse: mdp, prenom: p.prenom, departement: p.departement, pratiques: p.pratiques,
            trancheAge: p.tranche_age, accordEmails: p.accord_emails,
          });
          if (etat === "a_confirmer") afficherEcranCompte("confirmer", { email });
          return undefined;
        }
        case "connexion":
          if (!email || !mdp) return message(z, "Indique ton e-mail et ton mot de passe.");
          await connecter(email, mdp);
          return undefined;
        case "oubli":
          if (!/^[^@\s]+@[^@\s]+\.[^@\s]+$/.test(email)) return message(z, "Adresse e-mail invalide.");
          await motDePasseOublie(email);
          return message(z, "Si un compte existe avec cette adresse, un e-mail vient de partir. Pense aux indésirables.", "ok");
        case "nouveau": {
          const m = verifierMotDePasse(mdp);
          if (m) return message(z, `Mot de passe : ${m}`);
          await changerMotDePasse(mdp);
          masquerEcranCompte();
          document.dispatchEvent(new CustomEvent("kelvisi-compte", { detail: { connecte: true } }));
          document.dispatchEvent(new CustomEvent("kelvisi-message", { detail: "Mot de passe changé." }));
          return undefined;
        }
        default:
          return undefined;
      }
    } catch (err) {
      if (err.code === "email_not_confirmed") {
        afficherEcranCompte("confirmer", { email, info: err.message });
        return undefined;
      }
      return message(z, err.message);
    }
  });
}

// --- Page « Mon compte » --------------------------------------------------------------------------

// Favoris sous alerte, avec un bouton pour toutes les retirer
function blocAlertes() {
  const liste = Object.entries(alertes());
  if (!liste.length) return "";
  return `<div class="bloc"><h2 class="titre-bloc">Mes alertes</h2>
    <ul class="marees">${liste.map(([id, niveau]) => `<li><strong>${echapper(pointPublic(id)?.nom || monSpot(id)?.nom || id)}</strong> · ${NIVEAUX[niveau].toLowerCase()}</li>`).join("")}</ul>
    <p class="note">Change-les depuis la fiche de chaque favori ou spot. Les notifications arrivent sur les appareils où tu les as autorisées.</p>
    <div class="rangee"><button type="button" class="bouton secondaire" data-alertes-retirer>Désactiver toutes mes alertes</button></div></div>`;
}

export function afficherMonCompte(zone, ctx) {
  const u = utilisateur();
  if (!u) {
    zone.innerHTML = `<button type="button" class="retour" data-retour>← Infos</button>
      <div class="vide"><p class="texte">Tu n'es pas connecté.</p></div>`;
    zone.querySelector("[data-retour]").addEventListener("click", () => ctx.allerA("#/infos"));
    return;
  }
  const rendre = (profil, horsLigne = false) => {
    zone.innerHTML = `<button type="button" class="retour" data-retour>← Infos</button>
      <div class="entete-fiche"><h1 class="titre-vue">Mon compte</h1>
        <p>${echapper(u.email)}${profil?.cree_le ? ` · inscrit le ${new Intl.DateTimeFormat("fr-FR", { day: "numeric", month: "long", year: "numeric", timeZone: "Europe/Paris" }).format(new Date(profil.cree_le))}` : ""}</p></div>
      ${horsLigne ? '<p class="encart info">Hors connexion : les modifications seront possibles au retour du réseau.</p>' : ""}
      <form class="bloc formulaire" novalidate data-form="profil">
        <h2 class="titre-bloc">Mon profil</h2>
        ${champsProfil(profil || {})}
        ${profil?.accord_emails && profil.accord_emails_le ? `<p class="note">Accord e-mails donné ${dateHeure(profil.accord_emails_le)}.</p>` : ""}
        <p data-message hidden></p>
        <button type="submit" class="bouton" ${horsLigne ? "disabled" : ""}>Enregistrer</button>
      </form>
      <form class="bloc formulaire" novalidate data-form="mdp">
        <h2 class="titre-bloc">Mot de passe</h2>
        ${champMotDePasse("mot_de_passe", "Nouveau mot de passe")}
        <p data-message hidden></p>
        <button type="submit" class="bouton secondaire" ${horsLigne ? "disabled" : ""}>Changer mon mot de passe</button>
      </form>
      ${blocAlertes()}
      <div class="bloc">
        <h2 class="titre-bloc">Mes données</h2>
        <p class="note">Tes spots privés ne sont visibles que par toi. Tu peux télécharger tout ce que Kelvisi garde sur ton compte.</p>
        <div class="rangee"><button type="button" class="bouton secondaire" data-exporter>Télécharger mes données</button>
          <button type="button" class="bouton secondaire" data-deconnexion>Me déconnecter</button></div>
        <div class="rangee"><button type="button" class="lien danger" data-supprimer>Supprimer mon compte</button></div>
        <div class="encart alerte" data-confirmer hidden>
          <span>Supprimer définitivement ton compte, tes spots privés, tes favoris et ton profil ? Tes retours terrain restent, sans lien avec toi.</span>
          <div class="rangee"><button type="button" class="bouton danger" data-oui>Oui, supprimer</button>
            <button type="button" class="bouton secondaire" data-non>Annuler</button></div>
        </div>
        <p data-message-donnees class="erreur" hidden></p>
      </div>`;
    zone.querySelector("[data-retour]").addEventListener("click", () => ctx.allerA("#/infos"));
    lierAffichageMotDePasse(zone);

    const formProfil = zone.querySelector('[data-form="profil"]');
    formProfil.addEventListener("submit", (e) => {
      e.preventDefault();
      const p = lireProfilFormulaire(formProfil);
      const erreur = verifierProfil(p);
      if (erreur) return message(formProfil, erreur);
      return occupe(formProfil.querySelector('button[type="submit"]'), async () => {
        try {
          await modifierProfil(p);
          message(formProfil, "Profil enregistré.", "ok");
        } catch (err) {
          message(formProfil, err.message);
        }
      });
    });
    const formMdp = zone.querySelector('[data-form="mdp"]');
    formMdp.addEventListener("submit", (e) => {
      e.preventDefault();
      const mdp = String(new FormData(formMdp).get("mot_de_passe") || "");
      const m = verifierMotDePasse(mdp);
      if (m) return message(formMdp, `Mot de passe : ${m}`);
      return occupe(formMdp.querySelector('button[type="submit"]'), async () => {
        try {
          await changerMotDePasse(mdp);
          formMdp.reset();
          message(formMdp, "Mot de passe changé.", "ok");
        } catch (err) {
          message(formMdp, err.message);
        }
      });
    });

    zone.querySelector("[data-exporter]").addEventListener("click", () => {
      const donnees = { compte: { email: u.email }, profil: profilEnMemoire(), spots_prives: mesSpots(), favoris: favoris(), alertes: alertes(), exporte_le: new Date().toISOString() };
      const lien = document.createElement("a");
      lien.href = URL.createObjectURL(new Blob([JSON.stringify(donnees, null, 2)], { type: "application/json" }));
      lien.download = "kelvisi-mes-donnees.json";
      document.body.appendChild(lien);
      lien.click();
      lien.remove();
    });
    zone.querySelector("[data-deconnexion]").addEventListener("click", async () => {
      await desabonnerAppareil();
      await deconnecter();
    });
    const toutes = zone.querySelector("[data-alertes-retirer]");
    if (toutes) toutes.addEventListener("click", (e) => occupe(e.currentTarget, async () => {
      for (const id of Object.keys(alertes())) await choisirAlerte(id, null, noterAlerte);
      rendre(profilEnMemoire(), horsLigne);
    }));
    const confirmer = zone.querySelector("[data-confirmer]");
    zone.querySelector("[data-supprimer]").addEventListener("click", () => { confirmer.hidden = false; });
    zone.querySelector("[data-non]").addEventListener("click", () => { confirmer.hidden = true; });
    zone.querySelector("[data-oui]").addEventListener("click", (e) => occupe(e.currentTarget, async () => {
      try {
        await desabonnerAppareil();
        await supprimerCompte();
        effacerDonneesLocales();
      } catch (err) {
        const m = zone.querySelector("[data-message-donnees]");
        m.textContent = `Suppression impossible : ${err.message}`;
        m.hidden = false;
      }
    }));
  };

  rendre(profilEnMemoire(), false);
  lireProfil()
    .then((p) => { if (location.hash === "#/compte") rendre(p, false); })
    .catch(() => { if (location.hash === "#/compte") rendre(profilEnMemoire(), true); });
  synchroniser().catch(() => {});
}
