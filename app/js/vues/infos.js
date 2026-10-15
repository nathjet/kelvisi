// Pages d'information : fonctionnement, sécurité, sources, mentions légales, confidentialité.

import { CONFIG } from "../config.js";
import { partageActif } from "../retours.js";
import { echapper, dateHeure, CLE_UNITE_VENT } from "../format.js";
import { lire, ecrire } from "../stockage.js";

const aCompleter = (v, libelle) => (v ? echapper(v) : `<span class="a-completer">[${libelle} à compléter]</span>`);

const PAGES = {
  comment: {
    titre: "Comment ça marche",
    resume: "D'où vient le chiffre de visi, et ses limites",
    contenu: () => `
      <p>Kelvisi estime la distance à laquelle tu verras sous l'eau, en mètres, heure par heure sur trois jours.</p>
      <h2>Ce que le modèle prend en compte</h2>
      <ul>
        <li>La houle et la mer du vent : plus elles sont fortes et longues, plus elles remettent le sable en suspension, surtout par petits fonds.</li>
        <li>L'abri du spot : une houle qui vient de derrière une pointe touche peu le spot.</li>
        <li>L'effet retard : après un coup de mer, l'eau reste chargée un à trois jours selon le fond (le sable se dépose plus vite que la vase).</li>
        <li>La marée : en Manche et en Atlantique, l'eau est souvent plus claire autour de la pleine mer, et les vives-eaux brassent davantage.</li>
        <li>Les fortes pluies, qui apportent de l'eau trouble, et le plancton selon la saison.</li>
        <li>Les crues des grands fleuves (Seine, Loire, Vilaine, Adour, Rhône, Var), mesurées en temps réel, pour les points Kelvisi proches de leur embouchure.</li>
        <li>La lumière, pour la visibilité ressentie (ciel couvert, soleil bas).</li>
      </ul>
      <h2>Lire la prévision</h2>
      <ul>
        <li>Le grand chiffre est la visibilité attendue sur le meilleur créneau du jour.</li>
        <li>La fourchette et la confiance disent à quel point l'estimation est sûre. La confiance baisse avec l'échéance.</li>
        <li>Les couleurs vont de « mauvaise » à « excellente ». Les seuils ne sont pas les mêmes en Méditerranée, où l'eau est plus claire.</li>
        <li>Seuls les créneaux entre le lever et le coucher du soleil sont proposés : la chasse de nuit est interdite.</li>
      </ul>
      <h2>Limites de cette version bêta</h2>
      <ul>
        <li>Les réglages du modèle sont des ordres de grandeur. Ils seront ajustés avec les observations satellite puis avec vos retours terrain.</li>
        <li>Par mer calme, la prévision plafonne à la visibilité habituelle du secteur : elle ne voit pas encore les variations fines qu'apportera le satellite.</li>
        <li>Les horaires de marée et le courant viennent d'un modèle à maille de 8 km : ce sont des indications, pas des horaires officiels.</li>
        <li>La carte des profondeurs (EMODnet, environ 100 m de résolution) donne la forme générale du fond. Elle peut rater une roche isolée et ne sert pas à naviguer.</li>
      </ul>
      <p>Chaque retour « Tu y étais ? » aide à corriger la prévision du point concerné.</p>`,
  },
  securite: {
    titre: "Sécurité et réglementation",
    resume: "Numéros d'urgence et règles de base",
    contenu: () => `
      <p>En cas d'urgence en mer, appelle le <a class="numero" href="tel:196">196</a> (CROSS) ou le canal 16 en VHF.</p>
      <h2>Avant d'y aller</h2>
      <ul>
        <li>Ne chasse jamais seul : un binôme qui te surveille en surface reste la meilleure sécurité.</li>
        <li>Signale ta présence avec une bouée, et dis à un proche où tu vas et quand tu rentres.</li>
        <li>Par vent de terre fort, attention à la dérive vers le large. Par forte houle ou forts courants, renonce.</li>
        <li>La prévision de Kelvisi est indicative : l'observation sur place a toujours le dernier mot.</li>
      </ul>
      <h2>Règles de base de la chasse sous-marine</h2>
      <ul>
        <li>Âge minimum : 16 ans.</li>
        <li>Chasse interdite entre le coucher et le lever du soleil, et avec un appareil respiratoire (bouteille).</li>
        <li>Tailles minimales de capture, quotas et zones interdites (réserves, cantonnements, parcs) : ils varient selon les secteurs et changent chaque année.</li>
        <li>Depuis 2026, chaque pêcheur de loisir doit s'enregistrer et déclarer ses captures d'espèces sensibles (bar, lieu jaune, thon rouge, dorade rose) avec l'application RecFishing. Certains parcs de Méditerranée utilisent Catchmachine.</li>
      </ul>
      <p>Règles officielles et à jour : <a href="https://www.mer.gouv.fr/peche-de-loisir-en-mer" target="_blank" rel="noopener">pêche de loisir en mer (ministère de la Mer)</a>. Vérifie aussi les arrêtés de ta direction interrégionale de la mer.</p>
      <p>Les points Kelvisi sont des zones de prévision, pas des recommandations de spot.</p>`,
  },
  sources: {
    titre: "Sources et licences",
    resume: "Données et outils utilisés",
    contenu: (ctx) => `
      <ul>
        <li>Météo marine et atmosphérique : <a href="https://open-meteo.com" target="_blank" rel="noopener">Open-Meteo.com</a> (licence CC BY 4.0), à partir des modèles de Météo-France, du DWD et de l'ECMWF.</li>
        <li>Débits des rivières : <a href="https://hubeau.eaufrance.fr" target="_blank" rel="noopener">Hub'Eau</a>, réseau Vigicrues et services de l'État (Licence Ouverte).</li>
        <li>Fond de carte : <a href="https://openfreemap.org" target="_blank" rel="noopener">OpenFreeMap</a>, © OpenMapTiles, © contributeurs OpenStreetMap.</li>
        <li>Vue aérienne et recherche de lieux : Géoplateforme de l'IGN (Licence Ouverte).</li>
        <li>Profondeurs : <a href="https://emodnet.ec.europa.eu/en/bathymetry" target="_blank" rel="noopener">EMODnet Bathymetry</a>, réseau européen d'observation marine.</li>
        <li>Fond de carte de secours : trait de côte Natural Earth (domaine public).</li>
        <li>Carte interactive : MapLibre GL JS (licence BSD).</li>
        <li>Polices : Archivo et Atkinson Hyperlegible (licence SIL Open Font).</li>
      </ul>
      ${ctx?.resume?.sources?.includes("Copernicus Marine") ? "<p>Images satellite : Generated using E.U. Copernicus Marine Service Information.</p>" : ""}
      <p>Le modèle de prévision de Kelvisi est un travail original. Ses résultats ne sont pas des données officielles.</p>`,
  },
  confidentialite: {
    titre: "Confidentialité",
    resume: "Ce qui reste sur ton appareil, ce qui en sort",
    contenu: () => `
      <p>Kelvisi fonctionne sans compte, sans publicité et sans mesure d'audience.</p>
      <h2>Ce qui reste sur ton appareil</h2>
      <ul>
        <li>Tes spots privés et leurs réglages, tes retours sur ces spots, tes préférences d'affichage. Ils sont stockés dans ton navigateur et effacés si tu vides ses données.</li>
        <li>Ta position, si tu utilises « Autour de moi » : elle sert seulement à trier les spots et n'est envoyée nulle part.</li>
      </ul>
      <h2>Ce qui est envoyé à des services tiers</h2>
      <ul>
        <li>Pour calculer la prévision d'un lieu ou d'un spot privé : sa position arrondie à environ 1 km, envoyée à Open-Meteo.</li>
        <li>Pour estimer la profondeur d'un lieu : sa position arrondie à environ 100 m, envoyée à EMODnet.</li>
        <li>Le texte tapé dans la recherche, envoyé à la Géoplateforme de l'IGN.</li>
        <li>Les tuiles de carte, chargées depuis OpenFreeMap, l'IGN et EMODnet.</li>
      </ul>
      <p>Ces services reçoivent aussi, comme tout site web, ton adresse IP. Kelvisi ne leur transmet rien d'autre.</p>
      <h2>Retours terrain sur les points Kelvisi</h2>
      ${partageActif()
        ? "<p>Quand tu envoies un retour sur un point Kelvisi, sont enregistrés : le point, la visibilité, le moment, et un identifiant aléatoire propre à cet appareil (il ne permet pas de te reconnaître). Ces retours, hébergés dans l'Union européenne, servent uniquement à corriger les prévisions. Ils sont conservés trois ans au plus.</p>"
        : "<p>Le partage des retours n'est pas activé : tous tes retours restent sur ton appareil.</p>"}
      <h2>Tes droits</h2>
      <p>Pour toute question ou demande sur tes données : ${aCompleter(CONFIG.contact, "adresse de contact")}.</p>`,
  },
  cgu: {
    titre: "Conditions d'utilisation",
    resume: "Les règles du jeu de la bêta",
    contenu: () => `
      <p>Kelvisi est proposé gratuitement, en version bêta. En l'utilisant, tu acceptes ces conditions.</p>
      <h2>Une prévision, pas une garantie</h2>
      <p>Les visibilités annoncées sont des estimations calculées à partir de modèles météorologiques. Elles peuvent se tromper. Elles ne remplacent ni l'observation sur place, ni les bulletins officiels, ni ton jugement. La carte des profondeurs ne doit pas servir à la navigation.</p>
      <h2>Ta sécurité et la réglementation</h2>
      <p>Tu restes seul responsable de ta décision d'aller à l'eau, de ta sécurité et du respect de la réglementation (zones interdites, tailles, quotas, déclarations). Kelvisi ne peut être tenu responsable d'un dommage lié à l'utilisation des prévisions.</p>
      <h2>Retours terrain</h2>
      <p>Merci de signaler la visibilité que tu as réellement constatée. Les retours manifestement faux peuvent être écartés.</p>
      <h2>Évolution du service</h2>
      <p>Le service peut évoluer, être interrompu ou devenir en partie payant. Les fonctions gratuites de la bêta seront annoncées avant tout changement.</p>`,
  },
  mentions: {
    titre: "Mentions légales",
    resume: "Éditeur et hébergeur",
    contenu: () => `
      <h2>Éditeur</h2>
      <p>${aCompleter(CONFIG.editeur, "nom de l'éditeur")}<br>Contact : ${aCompleter(CONFIG.contact, "adresse de contact")}</p>
      <h2>Hébergeur</h2>
      <p>GitHub, Inc. (GitHub Pages), 88 Colin P Kelly Jr Street, San Francisco, CA 94107, États-Unis.</p>
      <h2>Propriété intellectuelle</h2>
      <p>Le nom Kelvisi, les textes et le modèle de prévision appartiennent à l'éditeur. Les données et outils de tiers restent soumis à leurs licences (voir « Sources et licences »).</p>`,
  },
  avis: {
    titre: "Donner mon avis",
    resume: "Un bug, une idée, un spot qui se trompe",
    contenu: () => `
      <p>Kelvisi est en bêta : tes retours décident de la suite. Un bug, une prévision à côté, une fonction qui manque ?</p>
      <p>Écris à : <strong style="user-select:all">${aCompleter(CONFIG.contact, "adresse de contact")}</strong></p>
      <p>Pour une prévision qui se trompe, le plus utile est d'utiliser « Tu y étais ? » sur la fiche du spot : ton retour corrige directement le modèle.</p>`,
  },
};

export function afficherInfos(zone, page, ctx) {
  if (page && PAGES[page]) {
    const p = PAGES[page];
    zone.innerHTML = `<button type="button" class="retour" data-retour>← Infos</button>
      <article class="page-infos"><h1 class="titre-vue">${p.titre}</h1>${p.contenu(ctx)}</article>`;
    zone.querySelector("[data-retour]").addEventListener("click", () => ctx.allerA("#/infos"));
    return;
  }
  const r = ctx.resume;
  const unite = lire(CLE_UNITE_VENT, "kn");
  zone.innerHTML = `<div class="entete-fiche"><h1 class="titre-vue">Infos</h1>
      <p>Kelvisi prévoit la visibilité sous l'eau sur les côtes françaises. Version bêta${r ? `, prévisions mises à jour ${dateHeure(r.genere_le)}` : ""}.</p></div>
    <ul class="menu-infos">${Object.entries(PAGES).map(([id, p]) => `<li><a href="#/infos/${id}">${p.titre}<span>${p.resume}</span></a></li>`).join("")}</ul>
    <div class="bloc"><h2 class="titre-bloc">Unité du vent</h2>
      <div class="segments" id="unite-vent" role="group" aria-label="Unité du vent">
        <button type="button" data-unite="kn" aria-pressed="${unite === "kn"}">Nœuds</button>
        <button type="button" data-unite="kmh" aria-pressed="${unite === "kmh"}">km/h</button></div></div>
    <p class="note">Urgence en mer : <a class="numero" href="tel:196">196</a>.</p>`;
  zone.querySelector("#unite-vent").addEventListener("click", (e) => {
    const b = e.target.closest("button");
    if (!b) return;
    ecrire(CLE_UNITE_VENT, b.dataset.unite);
    zone.querySelectorAll("#unite-vent button").forEach((x) => x.setAttribute("aria-pressed", String(x === b)));
  });
}
