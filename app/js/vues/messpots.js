// Mes spots : points Kelvisi favoris et spots privés de cet appareil, avec export et import.

import { echapper, heure, metres, NOM_FACADE, facadePour } from "../format.js";
import { mesSpots, enregistrerSpot } from "../messpots.js";
import { favoris, ajouterFavoris } from "../favoris.js";
import { pointPublic } from "../donnees.js";
import { comptesActifs } from "../compte.js";

function ligneFavori(p, iJour) {
  const j = p.jours[Math.min(iJour, p.jours.length - 1)];
  const v = j.meilleur_creneau ? j.meilleur_creneau.visibilite_m : j.visibilite_moyenne_m;
  return `<li><a class="ligne-spot" href="#/spot/${encodeURIComponent(p.id)}"><span class="eau eau-${j.classe}"></span>
    <span><span class="nom">${echapper(p.nom)}</span><br><span class="infos">${NOM_FACADE[p.facade] || ""} · point Kelvisi</span></span>
    <span class="visi chiffres"><strong>${metres(v)} m</strong><span>${j.meilleur_creneau ? `de ${heure(j.meilleur_creneau.debut)} à ${heure(j.meilleur_creneau.fin)}` : '<span class="deconseille">déconseillé</span>'}</span></span></a></li>`;
}

export function afficherMesSpots(zone, ctx) {
  const spots = mesSpots();
  const iJour = ctx.etat.jour;
  const favs = favoris().map((id) => pointPublic(id)).filter(Boolean);
  zone.innerHTML = `
    <div class="entete-fiche"><h1 class="titre-vue">Mes spots</h1>
      <p>${comptesActifs() ? "Tes coins à toi : enregistrés dans ton compte, visibles par toi seul, sur tous tes appareils." : "Tes coins à toi. Ils restent sur cet appareil : Kelvisi ne les reçoit jamais."}</p></div>
    ${favs.length ? `<h2 class="titre-bloc">Points Kelvisi favoris</h2><ol class="liste" id="liste-favoris">${favs.map((p) => ligneFavori(p, iJour)).join("")}</ol>
      <h2 class="titre-bloc">Mes spots privés</h2>` : ""}
    ${spots.length ? `<ol class="liste">${spots.map((s) => {
      const pr = ctx.previsionsPrivees.get(s.id);
      const j = pr ? pr.jours[Math.min(iJour, pr.jours.length - 1)] : null;
      const v = j ? (j.meilleur_creneau ? j.meilleur_creneau.visibilite_m : j.visibilite_moyenne_m) : null;
      return `<li><a class="ligne-spot" href="#/prive/${s.id}"><span class="eau ${j ? `eau-${j.classe}` : ""}"></span>
        <span><span class="nom">${echapper(s.nom)}</span><br><span class="infos">${NOM_FACADE[facadePour(s.lat, s.lon)]} · ${Math.round(s.profondeur_m)} m</span></span>
        <span class="visi chiffres">${j ? `<strong>${metres(v)} m</strong><span>${j.meilleur_creneau ? `de ${heure(j.meilleur_creneau.debut)} à ${heure(j.meilleur_creneau.fin)}` : '<span class="deconseille">déconseillé</span>'}</span>` : "<strong>…</strong><span>calcul</span>"}</span></a></li>`;
    }).join("")}</ol>` : `<div class="vide"><p class="texte"><strong>Aucun spot enregistré.</strong></p>
      <p class="texte">Sur la carte, touche la mer à l'endroit où tu chasses, puis « Prévision ici ». Règle la profondeur et le fond, et enregistre.</p></div>`}
    <div class="rangee"><a class="bouton" href="#/carte">Ajouter un spot depuis la carte</a></div>
    <div class="bloc"><h2 class="titre-bloc">Changer d'appareil</h2>
      <p class="note">${comptesActifs() ? "Avec ton compte, tes spots et favoris te suivent : connecte-toi sur l'autre appareil. Tu peux aussi les copier ici pour les garder ou les partager." : "Sans compte, tes spots et favoris ne se synchronisent pas. Copie-les ici, puis colle-les dans Kelvisi sur l'autre appareil."}</p>
      <div class="rangee"><button type="button" class="bouton secondaire" id="exporter" ${spots.length || favs.length ? "" : "disabled"}>Copier mes spots</button></div>
      <label class="etiquette" for="import-texte">Coller des spots copiés</label>
      <textarea id="import-texte" rows="3" style="width:100%;border:1.5px solid var(--ligne);border-radius:10px;padding:8px;background:var(--surface)"></textarea>
      <div class="rangee"><button type="button" class="bouton secondaire" id="importer">Importer</button></div>
      <p class="confirmation" id="message-spots" hidden></p>
    </div>`;

  const message = zone.querySelector("#message-spots");
  const dire = (texte, erreur = false) => {
    message.textContent = texte;
    message.className = erreur ? "erreur" : "confirmation";
    message.hidden = false;
  };
  zone.querySelector("#exporter").addEventListener("click", async () => {
    const texte = JSON.stringify({ kelvisi: 1, spots: mesSpots(), favoris: favoris() });
    try {
      await navigator.clipboard.writeText(texte);
      const n = spots.length + favs.length;
      dire(`${n} spot${n > 1 ? "s" : ""} copié${n > 1 ? "s" : ""}. Colle le texte sur l'autre appareil.`);
    } catch (e) {
      const zoneTexte = zone.querySelector("#import-texte");
      zoneTexte.value = texte;
      zoneTexte.select();
      dire("Copie automatique impossible : le texte est sélectionné ci-dessus, copie-le à la main.");
    }
  });
  zone.querySelector("#importer").addEventListener("click", () => {
    try {
      const d = JSON.parse(zone.querySelector("#import-texte").value);
      const liste = Array.isArray(d) ? d : d.spots || [];
      const listeFavoris = Array.isArray(d.favoris) ? d.favoris : [];
      if (!Array.isArray(liste) || (!liste.length && !listeFavoris.length)) throw new Error();
      const existants = new Set(mesSpots().map((s) => s.id));
      let n = 0;
      for (const s of liste) {
        if (existants.has(s.id)) continue;
        enregistrerSpot(s);
        n++;
      }
      n += ajouterFavoris(listeFavoris);
      ctx.surSpotsModifies();
      afficherMesSpots(zone, ctx);
      const m = zone.querySelector("#message-spots");
      m.textContent = n ? `${n} spot${n > 1 ? "s" : ""} importé${n > 1 ? "s" : ""}.` : "Ces spots sont déjà sur cet appareil.";
      m.hidden = false;
    } catch (e) {
      dire("Texte non reconnu : colle exactement le texte copié depuis Kelvisi.", true);
    }
  });
}
