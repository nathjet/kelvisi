"""Température de l'eau en profondeur : modèles physiques de Copernicus Marine (moyenne de chaque jour).

Étape FACULTATIVE du calcul, comme le satellite : elle ne tourne qu'avec les identifiants
Copernicus Marine. Sans eux, ou en cas d'erreur, la fiche n'affiche que la température de surface.

Modèles (identifiants relevés dans le catalogue réel en octobre 2026, remplaçables sans toucher
au code par les variables KELVISI_TEMP_IBI et KELVISI_TEMP_MED) :
  IBI  Atlantique et Manche, maille de 0,027° (environ 3 km), 16 niveaux entre 0,5 et 34 m, puis 40 m
  MED  Méditerranée et Corse, maille de 0,042° (environ 4 km), 13 niveaux entre 1 et 38 m

Pour chaque point, on construit un profil de la surface à 40 m : à chaque profondeur, la valeur de la
maille d'eau la plus proche (moins de 10 km) qui descend jusque-là. Près de la côte, les mailles du
modèle sont souvent moins profondes que le spot ; la mer voisine, à la même profondeur, a quasiment la
même température. Le navigateur lit ce profil à la profondeur du spot (ou du spot privé, d'après le
point Kelvisi le plus proche).
"""

from __future__ import annotations

import os
from datetime import datetime, timedelta, timezone

import numpy as np

JEUX = {
    "ibi": os.environ.get("KELVISI_TEMP_IBI") or "cmems_mod_ibi_phy_anfc_0.027deg-3D_P1D-m",
    "med": os.environ.get("KELVISI_TEMP_MED") or "cmems_mod_med_phy-tem_anfc_4.2km_P1D-m",
}
VARIABLE = "thetao"
PROFONDEUR_MAX_M = 41.0   # assez pour les spots privés les plus profonds (40 m)
RAYON_KM = 10.0           # mailles prises en compte autour du point
MARGE_DEG = 0.15          # découpe autour des points (un peu plus que le rayon)


def bassin(spot) -> str:
    return "med" if spot.region == "mediterranee" else "ibi"


def distances_km(lat0: float, lon0: float, lats: np.ndarray, lons: np.ndarray) -> np.ndarray:
    la, lo = np.meshgrid(lats, lons, indexing="ij")
    return np.hypot((la - lat0) * 111.32, (lo - lon0) * 111.32 * np.cos(np.radians(lat0)))


def profil_composite(lat: float, lon: float, lats: np.ndarray, lons: np.ndarray, profondeurs: np.ndarray,
                     valeurs: np.ndarray, rayon_km: float = RAYON_KM) -> dict | None:
    """Profil de température au voisinage d'un point.

    `valeurs` est de forme (jour, profondeur, lat, lon), NaN hors de l'eau. À chaque profondeur, on
    prend la maille la plus proche qui a de l'eau à ce niveau ; on s'arrête au premier niveau
    qu'aucune maille du voisinage n'atteint. Retourne None si aucune maille d'eau n'est assez proche.
    """
    d = distances_km(lat, lon, lats, lons)
    proches = d <= rayon_km
    niveaux, colonnes, ecarts = [], [], []
    for k in range(len(profondeurs)):
        eau = proches & np.all(np.isfinite(valeurs[:, k]), axis=0)
        if not eau.any():
            break
        i, j = np.unravel_index(np.argmin(np.where(eau, d, np.inf)), d.shape)
        niveaux.append(float(profondeurs[k]))
        colonnes.append(valeurs[:, k, i, j].astype(float))
        ecarts.append(float(d[i, j]))
    if not niveaux:
        return None
    par_jour = np.array(colonnes).T  # (jour, niveau)
    return {
        "profondeurs": [round(p, 1) for p in niveaux],
        "valeurs": [[round(float(x), 1) for x in ligne] for ligne in par_jour],
        "distance_km": round(ecarts[0], 1),
    }


def valeur_a(profondeurs: list[float], valeurs: list[float], profondeur_m: float) -> tuple[float, float]:
    """Température à une profondeur, par interpolation linéaire dans le profil.

    Retourne (température, profondeur réellement lue) : au-delà du niveau le plus profond
    disponible, on garde ce dernier.
    """
    p = min(max(float(profondeur_m), profondeurs[0]), profondeurs[-1])
    return float(np.interp(p, profondeurs, valeurs)), p


def _ouvrir(dataset_id: str, spots, debut: str, fin: str):
    import copernicusmarine  # installé seulement quand les identifiants Copernicus sont fournis

    return copernicusmarine.open_dataset(
        dataset_id=dataset_id, variables=[VARIABLE],
        minimum_longitude=min(s.lon for s in spots) - MARGE_DEG, maximum_longitude=max(s.lon for s in spots) + MARGE_DEG,
        minimum_latitude=min(s.lat for s in spots) - MARGE_DEG, maximum_latitude=max(s.lat for s in spots) + MARGE_DEG,
        minimum_depth=0, maximum_depth=PROFONDEUR_MAX_M, start_datetime=debut, end_datetime=fin,
    )


def recuperer(spots, maintenant: int, jours: int = 4, ouvrir=_ouvrir) -> dict:
    """Profils de température des points pour les `jours` prochains jours (à partir d'aujourd'hui).

    Retourne {"points": {id: profil}, "erreurs": {bassin: message}, "jeux": [...]}. Chaque profil
    contient lat, lon, profondeurs, dates, valeurs (une liste par jour) et au_fond (température à la
    profondeur du point, une par jour). Une erreur sur un bassin n'empêche pas l'autre.
    """
    jour0 = datetime.fromtimestamp(maintenant, timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)
    debut = jour0.strftime("%Y-%m-%dT00:00:00")
    fin = (jour0 + timedelta(days=jours - 1)).strftime("%Y-%m-%dT00:00:00")
    points, erreurs, jeux = {}, {}, []
    for nom, jeu in JEUX.items():
        groupe = [s for s in spots if bassin(s) == nom]
        if not groupe:
            continue
        try:
            ds = ouvrir(jeu, groupe, debut, fin)
            th = ds[VARIABLE].sortby("latitude").load()
            lats, lons = th["latitude"].values, th["longitude"].values
            profs = th["depth"].values
            dates = [str(t)[:10] for t in th["time"].values]
            valeurs = th.transpose("time", "depth", "latitude", "longitude").values
            jeux.append(jeu)
            for spot in groupe:
                profil = profil_composite(spot.lat, spot.lon, lats, lons, profs, valeurs)
                if profil is None:
                    continue
                au_fond = [valeur_a(profil["profondeurs"], v, spot.profondeur_m) for v in profil["valeurs"]]
                points[spot.id] = {
                    "lat": spot.lat, "lon": spot.lon, "region": spot.region, "dates": dates, **profil,
                    "profondeur_m": round(au_fond[0][1], 1), "au_fond": [round(t, 1) for t, _ in au_fond],
                }
        except Exception as e:
            erreurs[nom] = f"{type(e).__name__}: {str(e)[:300]}"
    return {"points": points, "erreurs": erreurs, "jeux": jeux}


def encore_valable(precedent: dict | None, ids: set[str], maintenant: int, age_max_s: int, complet: bool = True) -> bool:
    """Le fichier déjà publié peut-il être repris (assez récent, mêmes points, et sans bassin en panne si `complet`) ?"""
    if not precedent or not precedent.get("points"):
        return False
    if complet and precedent.get("complet") is False:
        return False
    try:
        genere = datetime.fromisoformat(precedent["genere_le"]).timestamp()
    except (KeyError, TypeError, ValueError):
        return False
    return 0 <= maintenant - genere <= age_max_s and ids <= set(precedent["points"])
