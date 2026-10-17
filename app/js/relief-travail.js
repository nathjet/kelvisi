// Worker du relief sous-marin : télécharge les images du Shom, les relit et dessine la tuile,
// sans ralentir la carte. Réponse { id, png } ou { id, erreur, interne }.

import { ErreurReseau, produireTuile } from "./relief-rendu.js";

const enCours = new Map();

self.addEventListener("message", async (e) => {
  const m = e.data;
  if (m.annuler !== undefined) {
    enCours.get(m.annuler)?.abort();
    return;
  }
  const controleur = new AbortController();
  enCours.set(m.id, controleur);
  try {
    const png = await produireTuile(m.tuile, controleur.signal);
    self.postMessage({ id: m.id, png }, [png]);
  } catch (err) {
    const annule = err && err.name === "AbortError";
    // interne : le navigateur ne sait pas dessiner dans un worker, la page prendra le relais
    self.postMessage({ id: m.id, erreur: annule ? "AbortError" : String((err && err.message) || err), interne: !annule && !(err instanceof ErreurReseau) });
  } finally {
    enCours.delete(m.id);
  }
});
