"""Connecteur Hub'Eau Hydrométrie (API v2) : débits des rivières en temps réel.

Débits fournis en l/s, convertis ici en m³/s. Licence Ouverte.
Pas de prévision de débit : au-delà de la dernière mesure, le modèle garde
la dernière valeur connue.

Vérifié sur l'API réelle (octobre 2026) : champs `date_obs` et `resultat_obs`,
filtre `date_debut_obs`, pas de temps horaire avec `timestep=60` (l'ordre des
mesures renvoyées n'est pas garanti, d'où le tri). Le débit de référence de
chaque station (champ `debit_reference_m3s` des points) est la médiane des
débits moyens journaliers depuis 2021 (opération `obs_elab`, code QmnJ),
voir `debit_reference`.
"""

from __future__ import annotations

from datetime import datetime, timezone

import numpy as np

URL_OBSERVATIONS = "https://hubeau.eaufrance.fr/api/v2/hydrometrie/observations_tr"
URL_ELABOREES = "https://hubeau.eaufrance.fr/api/v2/hydrometrie/obs_elab"


def parametres_requete(code_station: str, depuis: int | None = None, taille: int = 5000) -> dict:
    params = {"code_entite": code_station, "grandeur_hydro": "Q", "size": taille, "timestep": 60,
              "fields": "date_obs,resultat_obs"}
    if depuis is not None:
        params["date_debut_obs"] = datetime.fromtimestamp(depuis, timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    return params


def convertir(reponse: dict) -> tuple[np.ndarray, np.ndarray]:
    """Retourne (temps Unix, débit m³/s), triés par date."""
    temps, debits = [], []
    for obs in reponse.get("data", []):
        date = obs.get("date_obs")
        valeur = obs.get("resultat_obs")
        if date is None or valeur is None:
            continue
        temps.append(int(datetime.fromisoformat(date.replace("Z", "+00:00")).timestamp()))
        debits.append(float(valeur) / 1000.0)
    ordre = np.argsort(temps)
    return np.asarray(temps, dtype=np.int64)[ordre], np.asarray(debits, dtype=float)[ordre]


def sur_grille_horaire(temps_obs: np.ndarray, debits: np.ndarray, grille: np.ndarray) -> np.ndarray:
    """Interpole les mesures sur la grille horaire du modèle.

    Avant la première mesure et après la dernière, la série reste à NaN :
    le modèle prolonge lui-même la dernière valeur connue.
    """
    resultat = np.full(len(grille), np.nan)
    if len(temps_obs) == 0:
        return resultat
    dedans = (grille >= temps_obs[0]) & (grille <= temps_obs[-1])
    resultat[dedans] = np.interp(grille[dedans], temps_obs, debits)
    return resultat


def telecharger(code_station: str, depuis: int | None = None, session=None) -> tuple[np.ndarray, np.ndarray]:
    """Mesures horaires brutes (temps Unix, m³/s) de la station depuis `depuis`."""
    import requests

    http = session or requests.Session()
    r = http.get(URL_OBSERVATIONS, params=parametres_requete(code_station, depuis), timeout=30)
    r.raise_for_status()
    return convertir(r.json())


def recuperer(code_station: str, grille: np.ndarray, session=None) -> np.ndarray:
    """Débits horaires (m³/s) de la station sur la grille du modèle."""
    temps, debits = telecharger(code_station, int(grille[0]) - 86400, session)
    return sur_grille_horaire(temps, debits, grille)


def debit_reference(code_station: str, depuis: str = "2021-01-01", session=None) -> float | None:
    """Médiane des débits moyens journaliers (m³/s) : sert à fixer `debit_reference_m3s`."""
    import requests

    http = session or requests.Session()
    r = http.get(URL_ELABOREES, params={
        "code_entite": code_station, "grandeur_hydro_elab": "QmnJ", "date_debut_obs_elab": depuis,
        "size": 20000, "fields": "date_obs_elab,resultat_obs_elab"}, timeout=60)
    r.raise_for_status()
    valeurs = [o["resultat_obs_elab"] / 1000.0 for o in r.json().get("data", []) if o.get("resultat_obs_elab") is not None]
    return float(np.median(valeurs)) if valeurs else None
