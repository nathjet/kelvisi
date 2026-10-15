// Recherche de lieux : communes, plages, pointes, îles… via la Géoplateforme de l'IGN.

const URL = "https://data.geopf.fr/geocodage/search";

const DANS_LA_ZONE = (lat, lon) => lat > 41 && lat < 51.6 && lon > -5.8 && lon < 9.9;

async function interroger(params, signal) {
  const r = await fetch(`${URL}?${new URLSearchParams(params)}`, { signal });
  if (!r.ok) throw new Error(`Recherche indisponible (${r.status})`);
  return (await r.json()).features || [];
}

export async function rechercherLieux(texte, signal) {
  const q = texte.trim();
  if (q.length < 3) return [];
  const [communes, lieux] = await Promise.allSettled([
    interroger({ q, index: "address", type: "municipality", limit: "5" }, signal),
    interroger({ q, index: "poi", limit: "8" }, signal),
  ]);
  if (communes.status === "rejected" && lieux.status === "rejected") throw communes.reason;
  const resultats = [];
  for (const f of lieux.status === "fulfilled" ? lieux.value : []) {
    const [lon, lat] = f.geometry.coordinates;
    const p = f.properties;
    const categories = Array.isArray(p.category) ? p.category : [p.category].filter(Boolean);
    resultats.push({
      nom: p.toponym || (Array.isArray(p.name) ? p.name[0] : p.name),
      detail: [categories[0], p.city || p.municipality].filter(Boolean).join(" · "),
      lat, lon, type: "lieu", score: p.score || 0,
    });
  }
  for (const f of communes.status === "fulfilled" ? communes.value : []) {
    const [lon, lat] = f.geometry.coordinates;
    const p = f.properties;
    resultats.push({ nom: p.name || p.label, detail: `commune · ${p.context || ""}`.trim(), lat, lon, type: "commune", score: p.score || 0 });
  }
  const vus = new Set();
  return resultats
    .filter((r) => r.nom && DANS_LA_ZONE(r.lat, r.lon))
    .sort((a, b) => b.score - a.score)
    .filter((r) => {
      const cle = `${r.nom}|${r.lat.toFixed(2)}|${r.lon.toFixed(2)}`;
      if (vus.has(cle)) return false;
      vus.add(cle);
      return true;
    })
    .slice(0, 8);
}
