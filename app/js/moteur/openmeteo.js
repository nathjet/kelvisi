// Récupération de la météo marine pour un point, directement depuis le navigateur.
// Même transformation que prevision/sources/openmeteo.py.

const URL_MARINE = "https://marine-api.open-meteo.com/v1/marine";
const URL_METEO = "https://api.open-meteo.com/v1/forecast";

const MARINE = {
  wave_height: "hauteur_vagues", wave_period: "periode_vagues", wave_direction: "direction_vagues",
  swell_wave_height: "hauteur_houle", swell_wave_period: "periode_houle", swell_wave_direction: "direction_houle",
  wind_wave_height: "hauteur_mer_vent", wind_wave_period: "periode_mer_vent", wind_wave_direction: "direction_mer_vent",
  ocean_current_velocity: "courant", ocean_current_direction: "direction_courant",
  sea_level_height_msl: "niveau_mer", sea_surface_temperature: "temperature_eau",
};
const METEO = {
  wind_speed_10m: "vent", wind_direction_10m: "direction_vent", wind_gusts_10m: "rafales",
  precipitation: "pluie", cloud_cover: "nebulosite",
};
const EN_KMH = new Set(["courant", "vent", "rafales"]);

function parametres(lat, lon, variables, joursPasses, joursPrevision, extra = {}) {
  return new URLSearchParams({
    latitude: lat.toFixed(4), longitude: lon.toFixed(4), timeformat: "unixtime", timezone: "GMT",
    past_days: String(joursPasses), forecast_days: String(joursPrevision),
    hourly: Object.keys(variables).join(","), ...extra,
  });
}

async function lire(url, signal) {
  for (let essai = 0; essai < 3; essai++) {
    const r = await fetch(url, { signal });
    if (r.ok) return r.json();
    if (r.status === 429 || r.status >= 500) {
      await new Promise((ok) => setTimeout(ok, 1500 * (essai + 1)));
      continue;
    }
    throw new Error(`Open-Meteo a répondu ${r.status}`);
  }
  throw new Error("Open-Meteo ne répond pas, réessaie dans un moment");
}

export function convertir(marine, meteo) {
  const tMarine = marine.hourly.time, tMeteo = meteo.hourly.time;
  const ensemble = new Set(tMeteo);
  const temps = tMarine.filter((t) => ensemble.has(t));
  if (temps.length < 2) throw new Error("Données météo incomplètes pour ce lieu");
  const series = {};
  for (const [reponse, table, tSrc] of [[marine, MARINE, tMarine], [meteo, METEO, tMeteo]]) {
    const index = new Map(tSrc.map((t, i) => [t, i]));
    for (const [nomApi, nom] of Object.entries(table)) {
      const brut = reponse.hourly[nomApi];
      if (!brut) continue;
      series[nom] = temps.map((t) => {
        const v = brut[index.get(t)];
        if (v === null || v === undefined) return null;
        return EN_KMH.has(nom) ? v / 3.6 : v;
      });
    }
  }
  return { temps, series, lat: marine.latitude, lon: marine.longitude };
}

// Coordonnées arrondies à 0,01° (environ 1 km) : la météo marine est calculée sur
// une maille de plusieurs kilomètres, inutile de transmettre la position exacte d'un spot.
export async function recupererConditions(lat, lon, { joursPasses = 5, joursPrevision = 4, signal } = {}) {
  const la = Math.round(lat * 100) / 100, lo = Math.round(lon * 100) / 100;
  const marine = await lire(`${URL_MARINE}?${parametres(la, lo, MARINE, joursPasses, joursPrevision, { cell_selection: "sea" })}`, signal);
  const meteo = await lire(`${URL_METEO}?${parametres(la, lo, METEO, joursPasses, joursPrevision)}`, signal);
  return convertir(marine, meteo);
}
