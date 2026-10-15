"""Connecteur Copernicus Marine : turbidité et chlorophylle satellite (Sentinel-3, 300 m).

Étape FACULTATIVE du calcul horaire : elle ne tourne que si les identifiants
Copernicus Marine sont fournis (variables d'environnement
COPERNICUSMARINE_SERVICE_USERNAME et COPERNICUSMARINE_SERVICE_PASSWORD, lues
directement par la boîte à outils officielle `copernicusmarine`). Sans eux, ou
en cas d'erreur, les prévisions sont calculées sans satellite.

NON TESTÉ sur le service réel : l'accès réseau à Copernicus n'était pas ouvert
pendant le développement. Les identifiants de jeux de données ci-dessous suivent
le catalogue (produits OCEANCOLOUR_ATL_BGC_L3_NRT_009_111 et
OCEANCOLOUR_MED_BGC_L3_NRT_009_141) ; si l'un d'eux a changé, le remplacer via
les variables d'environnement KELVISI_SAT_* sans toucher au code.

La turbidité est approchée par les matières en suspension (SPM, g/m³) :
dans les eaux côtières, 1 g/m³ correspond à peu près à 1 FNU (Nechad et al.).
Le coefficient FNU_PAR_SPM permet de l'ajuster après comparaison.

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


JEUX = {
    # bassin : (jeu « transparence » avec SPM, jeu « plancton » avec CHL)
    "atl": ((os.environ.get("KELVISI_SAT_ATL_TRANSP") or "cmems_obs-oc_atl_bgc-transp_nrt_l3-olci-300m_P1D"),
            (os.environ.get("KELVISI_SAT_ATL_PLANCTON") or "cmems_obs-oc_atl_bgc-plankton_nrt_l3-olci-300m_P1D")),
    "med": ((os.environ.get("KELVISI_SAT_MED_TRANSP") or "cmems_obs-oc_med_bgc-transp_nrt_l3-olci-300m_P1D"),
            (os.environ.get("KELVISI_SAT_MED_PLANCTON") or "cmems_obs-oc_med_bgc-plankton_nrt_l3-olci-300m_P1D")),
}
VARIABLE_TURBIDITE = (os.environ.get("KELVISI_SAT_VAR_TURBIDITE") or "SPM")
VARIABLE_CHL = (os.environ.get("KELVISI_SAT_VAR_CHL") or "CHL")
FNU_PAR_SPM = 1.0
HEURE_PASSAGE_UTC = 10.5      # Sentinel-3 survole la France vers 10 h 30 UTC
RAYON_M = 600.0               # deux pixels de 300 m autour du point
MARGE_DEG = 0.02


def identifiants_presents() -> bool:
    return bool(os.environ.get("COPERNICUSMARINE_SERVICE_USERNAME") and os.environ.get("COPERNICUSMARINE_SERVICE_PASSWORD"))


def bassin(spot) -> str:
    return "med" if spot.region == "mediterranee" else "atl"


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


def _ouvrir(dataset_id: str, variable: str, spots, debut: str, fin: str):
    import copernicusmarine  # installé seulement quand le satellite est activé

    return copernicusmarine.open_dataset(
        dataset_id=dataset_id, variables=[variable],
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
    for nom_bassin, (jeu_transp, jeu_plancton) in JEUX.items():
        groupe = [s for s in spots if bassin(s) == nom_bassin]
        if not groupe:
            continue
        try:
            tur = ouvrir(jeu_transp, VARIABLE_TURBIDITE, groupe, debut, fin)
            try:
                chl = ouvrir(jeu_plancton, VARIABLE_CHL, groupe, debut, fin)
            except Exception:
                chl = None
            for spot in groupe:
                obs = _au_spot(spot, tur, chl)
                if obs is not None:
                    resultat[spot.id] = obs
        except Exception as e:
            erreurs[nom_bassin] = f"{type(e).__name__}: {e}"
    return {"observations": resultat, "erreurs": erreurs}


def _au_spot(spot, tur, chl) -> ObservationSatellite | None:
    """Découpe autour du point puis cherche la dernière image valable."""
    zone = dict(latitude=slice(spot.lat - MARGE_DEG, spot.lat + MARGE_DEG),
                longitude=slice(spot.lon - MARGE_DEG, spot.lon + MARGE_DEG))
    t = tur[VARIABLE_TURBIDITE].sortby("latitude").sel(**zone).load()
    if t.size == 0:
        return None
    temps = t["time"].values.astype("datetime64[s]").astype(np.int64)
    temps_jours = temps - temps % 86400
    c = None
    if chl is not None:
        try:
            cz = chl[VARIABLE_CHL].sortby("latitude").sel(**zone)
            c = cz.reindex_like(t, method="nearest", tolerance=0.002).load().values
        except Exception:  # grilles incompatibles : turbidité seule
            c = None
    return derniere_observation(spot, temps_jours, t["latitude"].values, t["longitude"].values,
                                t.values * FNU_PAR_SPM, c)
