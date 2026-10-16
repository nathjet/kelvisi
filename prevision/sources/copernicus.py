"""Connecteur Copernicus Marine : turbidité et chlorophylle satellite (Sentinel-2 et Sentinel-3, environ 100 m).

Étape FACULTATIVE du calcul horaire : elle ne tourne que si les identifiants
Copernicus Marine sont fournis (variables d'environnement
COPERNICUSMARINE_SERVICE_USERNAME et COPERNICUSMARINE_SERVICE_PASSWORD, lues
directement par la boîte à outils officielle `copernicusmarine`). Sans eux, ou
en cas d'erreur, les prévisions sont calculées sans satellite.

Jeux de données : produits côtiers haute résolution OCEANCOLOUR_NWS/IBI/MED_BGC_HR_L3_NRT
(identifiants relevés dans le catalogue réel en octobre 2026). Si l'un d'eux change, le
remplacer via les variables d'environnement KELVISI_SAT_NWS, KELVISI_SAT_IBI, KELVISI_SAT_MED
sans toucher au code. La turbidité y est fournie directement en FNU.

Mention obligatoire dans l'application quand le satellite est utilisé :
« Generated using E.U. Copernicus Marine Service Information ».
"""

from __future__ import annotations

import os

import numpy as np

from ..donnees import ObservationSatellite


def extraire_au_spot(temps_image: int, turbidite: np.ndarray, chlorophylle: np.ndarray | None,
                     distances_m: np.ndarray, rayon_m: float = 300.0, part_min: float = 0.3) -> ObservationSatellite | None:
    """Résume les pixels autour d'un spot en une observation.

    `turbidite`, `chlorophylle` et `distances_m` sont des tableaux de même
    forme (pixels de l'image). Les pixels sans valeur (nuage, terre) sont NaN.
    Retourne None si trop peu de pixels sont exploitables.
    """
    proches = distances_m <= rayon_m
    if not proches.any():
        return None
    tur = turbidite[proches]
    valides = np.isfinite(tur)
    if valides.mean() < part_min:
        return None
    chl = None
    if chlorophylle is not None:
        c = chlorophylle[proches]
        c = c[np.isfinite(c)]
        chl = float(np.median(c)) if len(c) else None
    return ObservationSatellite(temps=int(temps_image), turbidite_fnu=float(np.median(tur[valides])), chlorophylle_mg_m3=chl)


# Produits « haute résolution » côtiers (Sentinel-2 et Sentinel-3, environ 100 m, une image par jour
# quand le ciel est dégagé), qui donnent directement la turbidité en FNU et la chlorophylle.
# Vérifiés dans le catalogue Copernicus Marine en octobre 2026 (archives depuis 2020).
JEUX = {
    "nws": os.environ.get("KELVISI_SAT_NWS") or "cmems_obs_oc_nws_bgc_tur-spm-chl_nrt_l3-hr-mosaic_P1D-m",  # Manche, Bretagne nord (au nord de 48°)
    "ibi": os.environ.get("KELVISI_SAT_IBI") or "cmems_obs_oc_ibi_bgc_tur-spm-chl_nrt_l3-hr-mosaic_P1D-m",  # golfe de Gascogne (au sud de 48°)
    "med": os.environ.get("KELVISI_SAT_MED") or "cmems_obs_oc_med_bgc_tur-spm-chl_nrt_l3-hr-mosaic_P1D-m",  # Méditerranée et Corse
}
VARIABLE_TURBIDITE = "TUR"
VARIABLE_CHL = "CHL"
FNU_PAR_SPM = 1.0             # la turbidité est déjà en FNU : pas de conversion
HEURE_PASSAGE_UTC = 10.5      # Sentinel-2 et Sentinel-3 survolent la France vers 10 h 30 UTC
RAYON_M = 300.0               # trois pixels d'environ 100 m autour du point
MARGE_DEG = 0.01


def identifiants_presents() -> bool:
    return bool(os.environ.get("COPERNICUSMARINE_SERVICE_USERNAME") and os.environ.get("COPERNICUSMARINE_SERVICE_PASSWORD"))


def bassin(spot) -> str:
    if spot.region == "mediterranee":
        return "med"
    return "nws" if spot.lat >= 48.0 else "ibi"


def distances_m(lat0: float, lon0: float, lats: np.ndarray, lons: np.ndarray) -> np.ndarray:
    """Distances (m) entre un point et une grille lat/lon (approximation locale plane)."""
    la, lo = np.meshgrid(lats, lons, indexing="ij")
    dy = (la - lat0) * 111_320.0
    dx = (lo - lon0) * 111_320.0 * np.cos(np.radians(lat0))
    return np.hypot(dx, dy)


def derniere_observation(spot, temps_jours: np.ndarray, lats: np.ndarray, lons: np.ndarray,
                         turbidite: np.ndarray, chlorophylle: np.ndarray | None) -> ObservationSatellite | None:
    """Dernière image exploitable au droit du spot.

    `turbidite` et `chlorophylle` sont de forme (jour, lat, lon), en FNU et mg/m³.
    `temps_jours` donne le début de chaque jour (secondes Unix UTC).
    """
    d = distances_m(spot.lat, spot.lon, lats, lons)
    for k in range(len(temps_jours) - 1, -1, -1):
        obs = extraire_au_spot(int(temps_jours[k] + HEURE_PASSAGE_UTC * 3600), turbidite[k],
                               None if chlorophylle is None else chlorophylle[k], d, rayon_m=RAYON_M)
        if obs is not None:
            return obs
    return None


def _ouvrir(dataset_id: str, variables: list[str], spots, debut: str, fin: str):
    import copernicusmarine  # installé seulement quand le satellite est activé

    return copernicusmarine.open_dataset(
        dataset_id=dataset_id, variables=variables,
        minimum_longitude=min(s.lon for s in spots) - MARGE_DEG, maximum_longitude=max(s.lon for s in spots) + MARGE_DEG,
        minimum_latitude=min(s.lat for s in spots) - MARGE_DEG, maximum_latitude=max(s.lat for s in spots) + MARGE_DEG,
        start_datetime=debut, end_datetime=fin,
    )


def recuperer(spots, maintenant: int, jours: int = 5, ouvrir=_ouvrir) -> dict:
    """Dernière observation satellite de chaque point des `jours` derniers jours.

    Retourne {id du point: ObservationSatellite}. Les points sans image
    exploitable (nuages, côte trop proche) sont absents. Une erreur sur un
    bassin n'empêche pas l'autre.
    """
    from datetime import datetime, timezone

    debut = datetime.fromtimestamp(maintenant - jours * 86400, timezone.utc).strftime("%Y-%m-%dT00:00:00")
    fin = datetime.fromtimestamp(maintenant, timezone.utc).strftime("%Y-%m-%dT23:59:59")
    resultat, erreurs = {}, {}
    for nom_bassin, jeu in JEUX.items():
        # Points où un fond clair peu profond fausse la mesure : satellite ignoré
        groupe = [s for s in spots if bassin(s) == nom_bassin and getattr(s, "satellite", True)]
        if not groupe:
            continue
        try:
            ds = ouvrir(jeu, [VARIABLE_TURBIDITE, VARIABLE_CHL], groupe, debut, fin)
            for spot in groupe:
                obs = _au_spot(spot, ds)
                if obs is not None:
                    resultat[spot.id] = obs
        except Exception as e:
            erreurs[nom_bassin] = f"{type(e).__name__}: {e}"
    return {"observations": resultat, "erreurs": erreurs}


def _au_spot(spot, ds) -> ObservationSatellite | None:
    """Découpe autour du point puis cherche la dernière image valable."""
    zone = dict(latitude=slice(spot.lat - MARGE_DEG, spot.lat + MARGE_DEG),
                longitude=slice(spot.lon - MARGE_DEG, spot.lon + MARGE_DEG))
    ds = ds.sortby("latitude")
    t = ds[VARIABLE_TURBIDITE].sel(**zone).load()
    if t.size == 0:
        return None
    temps = t["time"].values.astype("datetime64[s]").astype(np.int64)
    temps_jours = temps - temps % 86400
    c = ds[VARIABLE_CHL].sel(**zone).load().values if VARIABLE_CHL in ds else None
    return derniere_observation(spot, temps_jours, t["latitude"].values, t["longitude"].values,
                                t.values * FNU_PAR_SPM, c)
