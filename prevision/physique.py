"""Physique des vagues : vitesse de l'eau au fond et exposition d'un spot."""

import numpy as np

from . import parametres as P


def nombre_onde(periode_s, profondeur_m):
    """Nombre d'onde k (rad/m) qui vérifie ω² = g k tanh(k h).

    Départ par l'approximation d'Eckart, puis quelques itérations de Newton.
    Fonctionne sur des tableaux numpy. Retourne NaN si la période est nulle.
    """
    T = np.asarray(periode_s, dtype=float)
    h = np.asarray(profondeur_m, dtype=float)
    with np.errstate(divide="ignore", invalid="ignore"):
        omega = 2 * np.pi / T
        k = omega**2 / (P.GRAVITE * np.sqrt(np.tanh(omega**2 * h / P.GRAVITE)))
        for _ in range(6):
            th = np.tanh(k * h)
            f = P.GRAVITE * k * th - omega**2
            df = P.GRAVITE * th + P.GRAVITE * k * h * (1 - th**2)
            k = k - f / df
    return np.where(T > 0, k, np.nan)


def vitesse_orbitale_fond(hauteur_m, periode_s, profondeur_m):
    """Amplitude de la vitesse de l'eau au fond sous les vagues (m/s).

    Théorie linéaire : Ub = π H / (T sinh(k h)). La hauteur est limitée par
    le déferlement (H <= 0,78 h). Plus le fond est profond et la période
    courte, plus la vitesse au fond est faible.
    """
    H = np.nan_to_num(np.asarray(hauteur_m, dtype=float), nan=0.0)
    T = np.nan_to_num(np.asarray(periode_s, dtype=float), nan=0.0)
    h = float(profondeur_m)
    H = np.clip(H, 0.0, P.RAPPORT_DEFERLEMENT * h)
    valide = (H > 0) & (T > 0)
    T_sur = np.where(valide, T, 1.0)
    k = nombre_onde(T_sur, h)
    with np.errstate(over="ignore"):
        kh = np.minimum(k * h, 50.0)
        ub = np.pi * H / (T_sur * np.sinh(kh))
    return np.where(valide, ub, 0.0)


def ecart_angulaire(a_deg, b_deg):
    """Écart le plus court entre deux directions, de 0 à 180 degrés."""
    d = np.abs((np.asarray(a_deg, dtype=float) - b_deg + 180.0) % 360.0 - 180.0)
    return d


def exposition(direction_provenance_deg, orientation_deg, ouverture_deg):
    """Part de la houle qui atteint le spot (0 à 1).

    `direction_provenance_deg` : d'où vient la houle (convention météo).
    `orientation_deg` : direction vers le large depuis le spot.
    `ouverture_deg` : demi-angle du secteur d'où la houle arrive librement.
    Une houle venant pile du large vaut 1 ; hors secteur, il reste une part
    résiduelle (diffraction autour des pointes).
    """
    d = ecart_angulaire(direction_provenance_deg, orientation_deg)
    d = np.nan_to_num(d, nan=180.0)
    dans_secteur = d <= ouverture_deg
    forme = np.cos(np.pi / 2 * np.clip(d / max(ouverture_deg, 1.0), 0.0, 1.0))
    r = P.EXPOSITION_RESIDUELLE
    return np.where(dans_secteur, r + (1 - r) * forme, r)


def vent_de_terre(direction_vent_deg, orientation_deg):
    """Vrai si le vent souffle de la terre vers la mer pour ce spot."""
    return ecart_angulaire(direction_vent_deg, orientation_deg) > 100.0
