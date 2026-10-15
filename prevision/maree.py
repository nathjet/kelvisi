"""Marée déduite de la série horaire du niveau de la mer.

Open-Meteo fournit un niveau de la mer (marée + effet de la pression) sur une
maille d'environ 8 km. On en tire les heures de pleine et basse mer, la phase
et l'intensité de la marée (vives-eaux ou mortes-eaux). Ces valeurs servent
au modèle ; les horaires officiels affichés viendront du Shom ou d'un calcul
harmonique dédié.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from . import parametres as P

ECART_MIN_H = 4  # deux extrêmes successifs sont séparés d'au moins 4 h


@dataclass
class Extreme:
    temps: float      # secondes Unix
    hauteur: float    # m
    type: str         # "PM" (pleine mer) ou "BM" (basse mer)


def extremes(temps, niveau) -> list[Extreme]:
    """Pleines et basses mers, affinées par interpolation parabolique."""
    t = np.asarray(temps, dtype=float)
    h = np.asarray(niveau, dtype=float)
    if np.count_nonzero(np.isfinite(h)) < 6:
        return []
    h = _boucher_trous(h)
    resultat: list[Extreme] = []
    for i in range(1, len(h) - 1):
        est_max = h[i] >= h[i - 1] and h[i] > h[i + 1]
        est_min = h[i] <= h[i - 1] and h[i] < h[i + 1]
        if not (est_max or est_min):
            continue
        # Sommet de la parabole passant par les trois points
        a = (h[i - 1] - 2 * h[i] + h[i + 1]) / 2
        b = (h[i + 1] - h[i - 1]) / 2
        dx = -b / (2 * a) if a != 0 else 0.0
        dx = float(np.clip(dx, -0.5, 0.5))
        sommet = h[i] + b * dx + a * dx**2
        e = Extreme(t[i] + dx * 3600, float(sommet), "PM" if est_max else "BM")
        if resultat and resultat[-1].type == e.type:
            # Deux extrêmes de même type : on garde le plus marqué
            precedent = resultat[-1]
            garder_nouveau = (e.hauteur > precedent.hauteur) if e.type == "PM" else (e.hauteur < precedent.hauteur)
            if garder_nouveau:
                resultat[-1] = e
            continue
        if resultat and (e.temps - resultat[-1].temps) < ECART_MIN_H * 3600:
            continue
        resultat.append(e)
    return resultat


def marnage_moyen(ext: list[Extreme]) -> float:
    """Écart moyen entre pleines et basses mers successives (m)."""
    if len(ext) < 2:
        return 0.0
    return float(np.mean([abs(a.hauteur - b.hauteur) for a, b in zip(ext, ext[1:])]))


def phase(temps, ext: list[Extreme]) -> np.ndarray:
    """Phase de la marée : +1 à la pleine mer, -1 à la basse mer.

    Interpolation en cosinus entre deux extrêmes ; 0 hors de la plage connue.
    """
    t = np.asarray(temps, dtype=float)
    k, dedans = _intervalle(t, ext)
    resultat = np.zeros(len(t))
    if not dedans.any():
        return resultat
    debuts = np.array([e.temps for e in ext])
    signes = np.array([1.0 if e.type == "PM" else -1.0 for e in ext])
    kk = k[dedans]
    x = (t[dedans] - debuts[kk]) / (debuts[kk + 1] - debuts[kk])
    resultat[dedans] = signes[kk] * np.cos(np.pi * x)
    return resultat


def rapport_marnage(temps, ext: list[Extreme]) -> np.ndarray:
    """Marnage local divisé par le marnage moyen (> 1 en vives-eaux)."""
    t = np.asarray(temps, dtype=float)
    moyen = marnage_moyen(ext)
    resultat = np.ones(len(t))
    if moyen < P.MARNAGE_MINIMUM_M:
        return resultat
    k, dedans = _intervalle(t, ext)
    hauteurs = np.array([e.hauteur for e in ext])
    kk = k[dedans]
    resultat[dedans] = np.abs(hauteurs[kk] - hauteurs[kk + 1]) / moyen
    return resultat


def _intervalle(t: np.ndarray, ext: list[Extreme]):
    """Pour chaque instant, indice de l'extrême qui le précède (et s'il est encadré)."""
    if len(ext) < 2:
        return np.zeros(len(t), dtype=int), np.zeros(len(t), dtype=bool)
    debuts = np.array([e.temps for e in ext])
    k = np.searchsorted(debuts, t, side="right") - 1
    dedans = (k >= 0) & (k < len(ext) - 1)
    return np.clip(k, 0, len(ext) - 2), dedans


def _boucher_trous(h: np.ndarray) -> np.ndarray:
    ok = np.isfinite(h)
    if ok.all():
        return h
    x = np.arange(len(h))
    return np.interp(x, x[ok], h[ok])
