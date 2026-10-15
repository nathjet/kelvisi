"""Position du soleil : hauteur, lever et coucher.

Algorithme basse précision de l'Astronomical Almanac (erreur de l'ordre de
0,01°, soit une minute environ sur l'heure du lever), suffisant ici.
"""

import numpy as np

HAUTEUR_LEVER_DEG = -0.833  # réfraction et demi-diamètre du soleil


def hauteur_soleil(lat_deg, lon_deg, temps_unix):
    """Hauteur du soleil au-dessus de l'horizon (degrés)."""
    t = np.asarray(temps_unix, dtype=float)
    n = t / 86400.0 + 2440587.5 - 2451545.0
    L = np.radians((280.460 + 0.9856474 * n) % 360)
    g = np.radians((357.528 + 0.9856003 * n) % 360)
    lam = L + np.radians(1.915) * np.sin(g) + np.radians(0.020) * np.sin(2 * g)
    eps = np.radians(23.439 - 0.0000004 * n)
    ascension = np.arctan2(np.cos(eps) * np.sin(lam), np.cos(lam))
    declinaison = np.arcsin(np.sin(eps) * np.sin(lam))
    gmst_h = (18.697374558 + 24.06570982441908 * n) % 24
    angle_horaire = np.radians(gmst_h * 15 + lon_deg) - ascension
    phi = np.radians(lat_deg)
    sin_h = np.sin(phi) * np.sin(declinaison) + np.cos(phi) * np.cos(declinaison) * np.cos(angle_horaire)
    return np.degrees(np.arcsin(np.clip(sin_h, -1, 1)))


def fait_jour(lat_deg, lon_deg, temps_unix):
    """Vrai entre le lever et le coucher du soleil."""
    return hauteur_soleil(lat_deg, lon_deg, temps_unix) > HAUTEUR_LEVER_DEG


def lever_coucher(lat_deg, lon_deg, debut_jour_unix):
    """Heures (Unix) du lever et du coucher pendant les 24 h qui suivent.

    Retourne (None, None) en cas de nuit ou de jour polaires.
    """
    pas = 60
    t = debut_jour_unix + np.arange(0, 86400 + pas, pas)
    jour = fait_jour(lat_deg, lon_deg, t)
    changements = np.nonzero(np.diff(jour.astype(int)))[0]
    lever = coucher = None
    for i in changements:
        if not jour[i] and jour[i + 1]:
            lever = lever or int(t[i + 1])
        elif jour[i] and not jour[i + 1]:
            coucher = coucher or int(t[i + 1])
    return lever, coucher
