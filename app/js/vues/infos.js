// Pages d'information : fonctionnement, sécurité, sources, mentions légales, confidentialité.

import { CONFIG } from "../config.js";
import { echapper, dateHeure, CLE_UNITE_VENT } from "../format.js";
import { comptesActifs, utilisateur, profilEnMemoire } from "../compte.js";
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
        <li>Les images satellite de la turbidité (Copernicus Marine), quand le ciel est dégagé : la dernière image recale la prévision, et son effet s'efface en trois jours.</li>
        <li>La lumière, pour la visibilité ressentie (ciel couvert, soleil bas).</li>
      </ul>
      <h2>Lire la prévision</h2>
      <ul>
        <li>Le grand chiffre est la visibilité attendue sur le meilleur créneau du jour.</li>
        <li>La fourchette et la confiance disent à quel point l'estimation est sûre. La confiance baisse avec l'échéance.</li>
        <li>Les couleurs vont de « mauvaise » à « excellente ». Les seuils ne sont pas les mêmes en Méditerranée, où l'eau est plus claire.</li>
        <li>Seuls les créneaux entre le lever et le coucher du soleil sont proposés : la chasse de nuit est interdite.</li>
        <li>« Eau au fond » donne la température prévue à la profondeur du spot, en moyenne sur la journée (modèles de Copernicus Marine). Pour un spot à toi, elle vient du point Kelvisi le plus proche.</li>
      </ul>
      <h2>Lire la carte des profondeurs</h2>
      <ul>
        <li>Plus la teinte est foncée, plus c'est profond (échelle sous les boutons de la carte).</li>
        <li>Un trait tous les 5 m jusqu'à 20 m, puis à 30, 50 et 100 m ; les traits plus foncés marquent 10, 20, 30, 50 et 100 m.</li>
        <li>Le relief est éclairé du nord-ouest : des traits serrés et une ombre marquée signalent un tombant, une tache claire au milieu d'une teinte foncée un haut-fond ou un banc.</li>
        <li>Près des côtes de Bretagne, de Nouvelle-Aquitaine, d'Occitanie et de Provence, le relevé laser du Shom montre chaque tête de roche. Ailleurs, le modèle à 100 m ne montre que les grandes formes.</li>
        <li>Touche la mer pour lire la profondeur exacte du point.</li>
      </ul>
      <h2>Limites de cette version bêta</h2>
      <ul>
        <li>Le modèle est calé sur environ 15 000 images satellite de 2022 à 2026. Le passage de la turbidité aux mètres de visibilité reste à vérifier avec vos retours terrain.</li>
        <li>Par temps couvert, le satellite ne voit rien : la prévision repose alors sur le modèle seul, moins précis.</li>
        <li>Les horaires de marée et le courant viennent d'un modèle à maille de 8 km : ce sont des indications, pas des horaires officiels.</li>
        <li>Les profondeurs viennent des cartes du Shom, lues sur leurs couleurs : compte environ un mètre d'incertitude. Elles sont mesurées sous le niveau moyen de la mer pour le relevé laser, sous les plus basses mers ailleurs, d'où un écart de quelques mètres en limite des relevés laser en Manche et en Atlantique. Elles ne servent pas à naviguer.</li>
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
        <li>Le bouton « Zones » de la carte montre en rouge les zones où la chasse sous-marine est interdite et en orange celles qui ont des règles particulières, d'après les zones réglementaires recensées par l'État (CACEM). Les fiches le signalent aussi. La liste n'est pas complète (ports, abords des plages en été, arrêtés municipaux) et les tracés sont indicatifs : seul le texte officiel fait foi.</li>
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
        <li>Profondeurs près des côtes : <a href="https://data.shom.fr" target="_blank" rel="noopener">Shom</a> (Licence Ouverte) : Litto3D® Shom-IGN, MNT côtiers et MNT de façade (projet Homonim).</li>
        <li>Profondeurs en vue lointaine et hors des zones du Shom : <a href="https://emodnet.ec.europa.eu/en/bathymetry" target="_blank" rel="noopener">EMODnet Bathymetry</a>, réseau européen d'observation marine.</li>
        <li>Zones de pêche sous-marine interdite ou réglementée : <a href="https://www.data.gouv.fr/datasets/zones-reglementaires-cacem" target="_blank" rel="noopener">zones réglementaires du CACEM</a>, ministère de la Transition écologique (Licence Ouverte 2.0), reprises chaque mois.</li>
        <li>Température de l'eau en profondeur : modèles IBI et MED de Copernicus Marine.</li>
        <li>Comptes et données des utilisateurs : Supabase, serveurs dans l'Union européenne.</li>
        <li>Fond de carte de secours : trait de côte Natural Earth (domaine public).</li>
        <li>Carte interactive : MapLibre GL JS (licence BSD).</li>
        <li>Polices : Archivo et Atkinson Hyperlegible (licence SIL Open Font).</li>
      </ul>
      ${ctx?.resume?.sources?.includes("Copernicus Marine") ? "<p>Images satellite et température en profondeur : Generated using E.U. Copernicus Marine Service Information.</p>" : ""}
      <p>Le modèle de prévision de Kelvisi est un travail original. Ses résultats ne sont pas des données officielles.</p>`,
  },
  confidentialite: {
    titre: "Confidentialité",
    resume: "Ton compte, tes données, tes droits",
    contenu: () => comptesActifs() ? `
      <p>Kelvisi est édité par ${aCompleter(CONFIG.editeur, "nom de l'éditeur")}, responsable du traitement de tes données. Pas de publicité, pas de revente de données, pas de mesure d'audience.</p>
      <h2>Les données de ton compte</h2>
      <ul>
        <li><strong>Ce que tu donnes à l'inscription</strong> : adresse e-mail, mot de passe (stocké chiffré, personne ne peut le lire), prénom, département, pratiques, tranche d'âge, et ton choix de recevoir ou non des e-mails de Kelvisi.</li>
        <li><strong>Ce que tu enregistres</strong> : tes spots privés, tes favoris (avec l'alerte choisie) et tes retours terrain.</li>
        <li><strong>Si tu actives une alerte</strong> : l'adresse de notification de chaque appareil où tu l'autorises (fournie par le service de ton navigateur : Google, Mozilla ou Apple) et la liste des alertes déjà envoyées, gardée 30 jours.</li>
        <li><strong>Ce qui est noté automatiquement</strong> : dates d'inscription et de dernière connexion.</li>
      </ul>
      <h2>À quoi elles servent</h2>
      <ul>
        <li>Faire fonctionner ton compte, retrouver tes spots sur tous tes appareils et t'envoyer les alertes que tu as demandées (exécution des conditions d'utilisation).</li>
        <li>Corriger les prévisions grâce aux retours terrain, et mieux connaître les utilisateurs de Kelvisi pour améliorer le service, de façon statistique (intérêt légitime).</li>
        <li>T'envoyer des nouvelles et des offres de Kelvisi, <strong>seulement si tu l'as accepté</strong> (consentement). Tu peux retirer ton accord à tout moment dans « Mon compte » ou par le lien de désinscription de chaque e-mail.</li>
      </ul>
      <h2>Qui y a accès</h2>
      <ul>
        <li>Tes spots privés ne sont visibles que par toi. Ni les autres utilisateurs ni l'application ne peuvent les lire.</li>
        <li>Si tu proposes un spot au partage, l'éditeur le voit avec ton adresse e-mail pour le vérifier. Une fois validé, les autres utilisateurs voient sa position, son nom et ses réglages, jamais qui l'a partagé. Tu peux le retirer à tout moment.</li>
        <li>L'éditeur de Kelvisi voit la liste des comptes (e-mail, profil, nombre de spots et de retours), mais pas l'emplacement de tes spots privés.</li>
        <li>Hébergement de la base : Supabase, serveurs situés dans l'Union européenne. Envoi des e-mails : prestataire d'envoi d'e-mails. Aucune donnée n'est vendue ni cédée.</li>
      </ul>
      <h2>Combien de temps</h2>
      <p>Tant que ton compte existe. Un compte sans connexion pendant trois ans est supprimé avec ses données. Les retours terrain sont gardés trois ans au plus ; à la suppression d'un compte, ils restent sans lien avec toi.</p>
      <h2>Ce qui reste sur ton appareil</h2>
      <ul>
        <li>Ta session de connexion, une copie de tes spots et favoris pour l'usage hors connexion, tes préférences d'affichage. Tout est effacé quand tu te déconnectes.</li>
        <li>Ta position, si tu utilises « Autour de moi » : elle sert seulement à trier les spots et n'est envoyée nulle part.</li>
      </ul>
      <h2>Ce qui est envoyé à des services tiers</h2>
      <ul>
        <li>Pour calculer la prévision d'un lieu ou d'un spot privé : sa position arrondie à environ 1 km, envoyée à Open-Meteo.</li>
        <li>Pour la profondeur d'un lieu : sa position, envoyée au Shom et à EMODnet.</li>
        <li>Le texte tapé dans la recherche, envoyé à la Géoplateforme de l'IGN. Les tuiles de carte, chargées depuis OpenFreeMap, l'IGN, le Shom et EMODnet.</li>
        <li>Les alertes passent par le service de notification de ton navigateur (Google, Mozilla ou Apple). Leur contenu est chiffré : ce service ne peut pas le lire. L'abonnement de l'appareil est effacé quand tu t'y déconnectes.</li>
      </ul>
      <p>Ces services reçoivent aussi, comme tout site web, ton adresse IP. Kelvisi ne leur transmet rien d'autre.</p>
      <h2>Tes droits</h2>
      <p>Tu peux à tout moment consulter et corriger ton profil, télécharger tes données et supprimer ton compte depuis « Mon compte ». Pour toute autre demande (accès, opposition, limitation) : ${aCompleter(CONFIG.contact, "adresse de contact")}. Tu peux aussi saisir la CNIL (cnil.fr).</p>
      <p>Kelvisi est réservé aux personnes de 15 ans et plus.</p>` : `
      <p>Kelvisi fonctionne sans publicité et sans mesure d'audience. Tes spots privés, tes retours et tes préférences restent dans ce navigateur.</p>
      <ul>
        <li>Pour calculer la prévision d'un lieu ou d'un spot privé : sa position arrondie à environ 1 km, envoyée à Open-Meteo.</li>
        <li>Pour la profondeur d'un lieu : sa position, envoyée au Shom et à EMODnet. Le texte tapé dans la recherche, envoyé à la Géoplateforme de l'IGN.</li>
      </ul>
      <p>Pour toute question : ${aCompleter(CONFIG.contact, "adresse de contact")}.</p>`,
  },
  cgu: {
    titre: "Conditions d'utilisation",
    resume: "Les règles du jeu de la bêta",
    contenu: () => `
      <p>Kelvisi est proposé gratuitement, en version bêta. En créant un compte et en utilisant le service, tu acceptes ces conditions.</p>
      <h2>Ton compte</h2>
      <p>Le compte est personnel et réservé aux personnes de 15 ans et plus. Donne des informations exactes et garde ton mot de passe pour toi. Tu peux supprimer ton compte à tout moment depuis « Mon compte ». Un compte utilisé pour nuire au service (faux retours en série, tentative d'accès aux données d'autrui) peut être fermé.</p>
      <h2>Une prévision, pas une garantie</h2>
      <p>Les visibilités annoncées sont des estimations calculées à partir de modèles météorologiques. Elles peuvent se tromper. Elles ne remplacent ni l'observation sur place, ni les bulletins officiels, ni ton jugement. La carte des profondeurs ne doit pas servir à la navigation.</p>
      <h2>Ta sécurité et la réglementation</h2>
      <p>Tu restes seul responsable de ta décision d'aller à l'eau, de ta sécurité et du respect de la réglementation (zones interdites, tailles, quotas, déclarations). Kelvisi ne peut être tenu responsable d'un dommage lié à l'utilisation des prévisions.</p>
      <h2>Retours terrain</h2>
      <p>Merci de signaler la visibilité que tu as réellement constatée. Les retours manifestement faux peuvent être écartés.</p>
      <h2>Spots partagés</h2>
      <p>Ne propose que des spots que tu as le droit de faire connaître et où la pratique est autorisée. Kelvisi vérifie chaque spot avant de le rendre visible et peut refuser ou retirer un spot (zone réglementée, doublon, nom inapproprié), sans avoir à se justifier. Un spot partagé reste lié à ton compte : il disparaît si tu le retires ou si tu supprimes ton compte. Kelvisi ne garantit pas qu'un spot partagé est autorisé ou sûr : vérifie toujours sur place.</p>
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
      <p>Écris à : ${CONFIG.contact ? `<a href="mailto:${encodeURIComponent(CONFIG.contact)}?subject=${encodeURIComponent("Avis sur Kelvisi")}"><strong style="user-select:all">${echapper(CONFIG.contact)}</strong></a>` : aCompleter("", "adresse de contact")}</p>
      <p>Pour une prévision qui se trompe, le plus utile est d'utiliser « Tu y étais ? » sur la fiche du spot : ton retour corrige directement le modèle.</p>`,
  },
};

// Contenu d'une page (titre compris), aussi affiché depuis l'écran de connexion
export function contenuPage(page, ctx) {
  const p = PAGES[page];
  return p ? `<h1 class="titre-vue">${p.titre}</h1>${p.contenu(ctx)}` : "";
}

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
  const u = comptesActifs() ? utilisateur() : null;
  const prenom = profilEnMemoire()?.prenom;
  zone.innerHTML = `<div class="entete-fiche"><h1 class="titre-vue">Infos</h1>
      <p>Kelvisi prévoit la visibilité sous l'eau sur les côtes françaises. Version bêta${r ? `, prévisions mises à jour ${dateHeure(r.genere_le)}` : ""}.</p></div>
    ${u ? `<ul class="menu-infos"><li><a href="#/compte">Mon compte<span>${echapper(prenom ? `${prenom} · ${u.email}` : u.email)}</span></a></li></ul>` : ""}
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
