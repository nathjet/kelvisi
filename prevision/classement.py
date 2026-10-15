"""« Où aller aujourd'hui ? » : classement des spots autour de l'utilisateur."""

from __future__ import annotations

import math

RAYON_TERRE_KM = 6371.0


def distance_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Distance à vol d'oiseau (formule de haversine)."""
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp = p2 - p1
    dl = math.radians(lon2 - lon1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * RAYON_TERRE_KM * math.asin(math.sqrt(a))


def classer(previsions: list[dict], lat: float, lon: float, rayon_km: float, indice_jour: int = 0) -> list[dict]:
    """Spots du rayon choisi, du plus clair au plus trouble pour le jour demandé.

    `previsions` : sorties de `prevoir`. Un spot sans créneau conseillé ce
    jour-là passe en fin de liste. À visibilité égale, le plus proche d'abord.
    """
    resultat = []
    for p in previsions:
        d = distance_km(lat, lon, p["spot"]["lat"], p["spot"]["lon"])
        if d > rayon_km or indice_jour >= len(p["jours"]):
            continue
        jour = p["jours"][indice_jour]
        creneau = jour["meilleur_creneau"]
        resultat.append({
            "spot": p["spot"],
            "distance_km": round(d, 1),
            "visibilite_m": creneau["visibilite_m"] if creneau else jour["visibilite_moyenne_m"],
            "classe": jour["classe"],
            "meilleur_creneau": creneau,
            "alerte": jour.get("alerte"),
        })
    resultat.sort(key=lambda r: (r["meilleur_creneau"] is None, -r["visibilite_m"], r["distance_km"]))
    return resultat
