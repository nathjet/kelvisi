"""Scénarios météo simulés, pour les tests et les démonstrations.

Ces séries sont inventées : elles servent à vérifier que le modèle réagit
dans le bon sens, pas à prévoir une situation réelle.
"""

from __future__ import annotations

import numpy as np

from .donnees import Conditions

KN = 0.514444


def _rampe(h, points):
    """Interpolation linéaire d'une série définie par des points (heure, valeur)."""
    x, y = zip(*points)
    return np.interp(h, x, y)


def coup_de_houle(debut_unix: int, jours: int = 8, hauteur_max: float = 3.0, pluie_totale_mm: float = 12.0,
                  direction_houle: float = 270.0, marnage: float = 4.4) -> Conditions:
    """Deux jours calmes, une tempête d'ouest le 3e jour, puis retour au calme.

    Heures depuis le début :
      0-48   calme (houle 0,5 m, vent de terre faible)
      48-60  la houle monte jusqu'à `hauteur_max`, vent d'ouest fort, pluie
      60-78  pic puis début de baisse
      78-120 décroissance, le vent tourne au nord-est
      120-   calme
    """
    n = jours * 24
    h = np.arange(n, dtype=float)
    temps = debut_unix + 3600 * np.arange(n)

    houle = _rampe(h, [(0, 0.5), (48, 0.6), (60, hauteur_max), (72, hauteur_max), (96, 1.2), (120, 0.6), (n, 0.5)])
    periode = _rampe(h, [(0, 9), (48, 10), (60, 13), (72, 13), (120, 10), (n, 9)])
    mer_vent = _rampe(h, [(0, 0.2), (48, 0.3), (56, 1.0), (72, 0.8), (84, 0.3), (n, 0.2)])
    periode_vent = _rampe(h, [(0, 3), (56, 5), (84, 3), (n, 3)])
    vent_kn = _rampe(h, [(0, 8), (48, 10), (56, 25), (72, 20), (84, 10), (n, 8)])
    direction_vent = np.where(h < 48, 90.0, np.where(h < 84, 270.0, 45.0))
    rafales_kn = vent_kn * 1.4

    hauteur_totale = np.sqrt(houle**2 + mer_vent**2)
    pluie = np.zeros(n)
    fenetre = (h >= 50) & (h < 66)
    if fenetre.any():
        pluie[fenetre] = pluie_totale_mm / fenetre.sum()

    # Marée semi-diurne avec cycle vives-eaux / mortes-eaux
    amplitude = marnage / 2 * (1 + 0.3 * np.cos(2 * np.pi * h / 354.0))
    niveau = amplitude * np.cos(2 * np.pi * h / 12.42)
    courant = 0.25 * (amplitude / (marnage / 2)) * np.abs(np.sin(2 * np.pi * h / 12.42))

    nebulosite = _rampe(h, [(0, 30), (48, 40), (54, 100), (72, 100), (90, 60), (120, 30), (n, 30)])

    series = {
        "hauteur_vagues": hauteur_totale,
        "periode_vagues": periode,
        "direction_vagues": np.full(n, direction_houle),
        "hauteur_houle": houle,
        "periode_houle": periode,
        "direction_houle": np.full(n, direction_houle),
        "hauteur_mer_vent": mer_vent,
        "periode_mer_vent": periode_vent,
        "direction_mer_vent": direction_vent,
        "courant": courant,
        "direction_courant": np.zeros(n),
        "niveau_mer": niveau,
        "vent": vent_kn * KN,
        "direction_vent": direction_vent,
        "rafales": rafales_kn * KN,
        "pluie": pluie,
        "nebulosite": nebulosite,
        "temperature_eau": np.full(n, 15.0),
    }
    return Conditions(temps=temps, series=series)


def saison_agitee(debut_unix: int, jours: int = 90, graine: int = 1, marnage: float = 4.0) -> Conditions:
    """Plusieurs mois avec des coups de houle et des pluies tirés au hasard.

    Sert à tester le calage : la même graine donne toujours la même saison.
    """
    rng = np.random.default_rng(graine)
    n = jours * 24
    h = np.arange(n, dtype=float)
    temps = debut_unix + 3600 * np.arange(n)

    houle = np.full(n, 0.5)
    periode = np.full(n, 9.0)
    vent_kn = np.full(n, 8.0)
    pluie = np.zeros(n)
    t_evt = rng.uniform(48, 9 * 24)
    while t_evt < n - 24:
        pic = rng.uniform(1.0, 4.0)
        largeur = rng.uniform(12, 48)
        bosse = np.exp(-(((h - t_evt) / largeur) ** 2))
        houle += pic * bosse
        periode = np.maximum(periode, 9 + 5 * bosse * pic / 4)
        vent_kn += rng.uniform(8, 20) * bosse
        if rng.random() < 0.6:
            pluie += rng.uniform(0.3, 1.5) * (np.abs(h - t_evt) < largeur / 2)
        t_evt += rng.uniform(4 * 24, 12 * 24)

    amplitude = marnage / 2 * (1 + 0.3 * np.cos(2 * np.pi * h / 354.0))
    niveau = amplitude * np.cos(2 * np.pi * h / 12.42)
    courant = 0.2 * (amplitude / (marnage / 2)) * np.abs(np.sin(2 * np.pi * h / 12.42)) if marnage > 0 else np.zeros(n)

    series = {
        "hauteur_vagues": houle,
        "periode_vagues": periode,
        "direction_vagues": np.full(n, 280.0),
        "courant": courant,
        "niveau_mer": niveau,
        "vent": vent_kn * KN,
        "direction_vent": np.full(n, 260.0),
        "rafales": vent_kn * 1.4 * KN,
        "pluie": pluie,
        "nebulosite": np.full(n, 60.0),
        "temperature_eau": np.full(n, 14.0),
    }
    return Conditions(temps=temps, series=series)


def calme(debut_unix: int, jours: int = 6, hauteur: float = 0.4, marnage: float = 0.0) -> Conditions:
    """Mer calme et constante, sans pluie."""
    n = jours * 24
    h = np.arange(n, dtype=float)
    temps = debut_unix + 3600 * np.arange(n)
    niveau = marnage / 2 * np.cos(2 * np.pi * h / 12.42)
    series = {
        "hauteur_vagues": np.full(n, hauteur),
        "periode_vagues": np.full(n, 8.0),
        "direction_vagues": np.full(n, 270.0),
        "courant": np.full(n, 0.05),
        "niveau_mer": niveau,
        "vent": np.full(n, 5 * KN),
        "direction_vent": np.full(n, 90.0),
        "rafales": np.full(n, 8 * KN),
        "pluie": np.zeros(n),
        "nebulosite": np.full(n, 20.0),
        "temperature_eau": np.full(n, 16.0),
    }
    return Conditions(temps=temps, series=series)
