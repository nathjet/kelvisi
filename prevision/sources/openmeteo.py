"""Connecteur Open-Meteo : vagues, courant, niveau de la mer, vent, pluie, nuages.

Deux appels : l'API marine et l'API météo, tous deux en temps Unix (UTC).
Mention obligatoire dans l'application : données Open-Meteo.
Usage commercial : clé payante à ajouter (paramètre `apikey`).
"""

from __future__ import annotations

import numpy as np

from ..donnees import Conditions

URL_MARINE = "https://marine-api.open-meteo.com/v1/marine"
URL_METEO = "https://api.open-meteo.com/v1/forecast"


def adresses(cle: str | None) -> tuple[str, str]:
    """Adresses des deux API : les abonnés commerciaux passent par les serveurs « customer- »."""
    if cle:
        return (URL_MARINE.replace("https://", "https://customer-"), URL_METEO.replace("https://", "https://customer-"))
    return URL_MARINE, URL_METEO

VARIABLES_MARINE = {
    "wave_height": "hauteur_vagues",
    "wave_period": "periode_vagues",
    "wave_direction": "direction_vagues",
    "swell_wave_height": "hauteur_houle",
    "swell_wave_period": "periode_houle",
    "swell_wave_direction": "direction_houle",
    "wind_wave_height": "hauteur_mer_vent",
    "wind_wave_period": "periode_mer_vent",
    "wind_wave_direction": "direction_mer_vent",
    "ocean_current_velocity": "courant",
    "ocean_current_direction": "direction_courant",
    "sea_level_height_msl": "niveau_mer",
    "sea_surface_temperature": "temperature_eau",
}

VARIABLES_METEO = {
    "wind_speed_10m": "vent",
    "wind_direction_10m": "direction_vent",
    "wind_gusts_10m": "rafales",
    "precipitation": "pluie",
    "cloud_cover": "nebulosite",
}

# Open-Meteo renvoie les vitesses en km/h par défaut : conversion en m/s
EN_KMH = {"courant", "vent", "rafales"}


def parametres_requetes(lat: float, lon: float, jours_passes: int = 5, jours_prevision: int = 7, cle: str | None = None):
    """Paramètres des deux requêtes (séparés pour pouvoir les tester)."""
    commun = {
        "latitude": round(lat, 4),
        "longitude": round(lon, 4),
        "timeformat": "unixtime",
        "timezone": "GMT",
        "past_days": jours_passes,
        "forecast_days": jours_prevision,
    }
    if cle:
        commun["apikey"] = cle
    marine = {**commun, "hourly": ",".join(VARIABLES_MARINE), "cell_selection": "sea"}
    meteo = {**commun, "hourly": ",".join(VARIABLES_METEO)}
    return marine, meteo


def convertir(reponse_marine: dict, reponse_meteo: dict) -> Conditions:
    """Transforme les deux réponses JSON en séries horaires alignées."""
    t_marine = np.asarray(reponse_marine["hourly"]["time"], dtype=np.int64)
    t_meteo = np.asarray(reponse_meteo["hourly"]["time"], dtype=np.int64)
    temps = np.intersect1d(t_marine, t_meteo)
    if len(temps) < 2:
        raise ValueError("Les réponses marine et météo ne se recouvrent pas")

    series: dict[str, np.ndarray] = {}
    for reponse, table, t_src in ((reponse_marine, VARIABLES_MARINE, t_marine), (reponse_meteo, VARIABLES_METEO, t_meteo)):
        index = np.searchsorted(t_src, temps)
        for nom_api, nom in table.items():
            brut = reponse["hourly"].get(nom_api)
            if brut is None:
                continue
            valeurs = np.array([np.nan if v is None else v for v in brut], dtype=float)[index]
            if nom in EN_KMH:
                valeurs = valeurs / 3.6
            series[nom] = valeurs

    # Open-Meteo donne la direction vers laquelle porte le courant ; on la garde telle quelle.
    return Conditions(
        temps=temps,
        series=series,
        lat=reponse_marine.get("latitude"),
        lon=reponse_marine.get("longitude"),
    )


TAILLE_LOT = 10  # points par requête groupée


def recuperer_plusieurs(points: list[tuple[float, float]], jours_passes: int = 5, jours_prevision: int = 7,
                        cle: str | None = None, session=None, pause_s: float = 1.0) -> list[Conditions]:
    """Conditions de plusieurs points, en requêtes groupées (une par lot et par API).

    Open-Meteo accepte des listes de coordonnées séparées par des virgules et
    renvoie alors une liste de réponses dans le même ordre.
    """
    import time

    import requests

    http = session or requests.Session()
    resultat: list[Conditions] = []
    for debut in range(0, len(points), TAILLE_LOT):
        lot = points[debut: debut + TAILLE_LOT]
        p_marine, p_meteo = parametres_requetes(0.0, 0.0, jours_passes, jours_prevision, cle)
        for p in (p_marine, p_meteo):
            p["latitude"] = ",".join(f"{lat:.4f}" for lat, _ in lot)
            p["longitude"] = ",".join(f"{lon:.4f}" for _, lon in lot)
        reponses = []
        url_marine, url_meteo = adresses(cle)
        for url, params in ((url_marine, p_marine), (url_meteo, p_meteo)):
            r = _get_avec_reessais(http, url, params)
            donnees = r.json()
            reponses.append(donnees if isinstance(donnees, list) else [donnees])
        for marine, meteo in zip(*reponses):
            resultat.append(convertir(marine, meteo))
        if debut + TAILLE_LOT < len(points):
            time.sleep(pause_s)
    return resultat


def _get_avec_reessais(http, url, params, essais: int = 6):
    """GET avec nouvelles tentatives espacées si l'API limite le débit (code 429) ou échoue."""
    import time

    import requests

    attente = 10.0
    for k in range(essais):
        try:
            r = http.get(url, params=params, timeout=60)
        except requests.exceptions.RequestException:
            # Coupure réseau passagère : on retente, sauf au dernier essai
            if k == essais - 1:
                raise
            time.sleep(attente)
            attente = min(attente * 2, 120.0)
            continue
        if r.status_code == 200:
            return r
        if k < essais - 1 and (r.status_code == 429 or r.status_code >= 500):
            time.sleep(attente)
            attente = min(attente * 2, 120.0)
            continue
        r.raise_for_status()
    return r


def recuperer(lat: float, lon: float, jours_passes: int = 5, jours_prevision: int = 7, cle: str | None = None, session=None) -> Conditions:
    """Interroge Open-Meteo et retourne les conditions du point."""
    import requests

    http = session or requests.Session()
    p_marine, p_meteo = parametres_requetes(lat, lon, jours_passes, jours_prevision, cle)
    url_marine, url_meteo = adresses(cle)
    r_marine = http.get(url_marine, params=p_marine, timeout=30)
    r_marine.raise_for_status()
    r_meteo = http.get(url_meteo, params=p_meteo, timeout=30)
    r_meteo.raise_for_status()
    return convertir(r_marine.json(), r_meteo.json())
