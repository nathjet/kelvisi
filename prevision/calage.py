"""Calage du modèle sur l'historique satellite.

Sans retours de chasseurs, le satellite sert de référence : pour chaque
point de référence, on compare la turbidité que le modèle aurait prévue
(à partir de la météo marine de l'époque) à celle mesurée par le satellite.
On ajuste ensuite les constantes « À CALER » et la visibilité habituelle de
chaque point pour réduire l'écart.

Ce calage règle le « quand » et le « combien » de la turbidité (effet de la
houle, durée du retour au calme, pluie, marée). La conversion turbidité en
mètres de visibilité (C_PAR_FNU) ne peut pas être calée ainsi : elle le sera
avec les retours terrain de la bêta.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field, replace

import numpy as np

from . import modele, parametres as P
from .donnees import Conditions, ObservationSatellite
from .spot import Spot

# Constantes ajustées et bornes autorisées
BORNES = {
    "ALPHA_BRASSAGE": (0.0003, 0.05),
    "FACTEUR_TAU": (0.25, 4.0),
    "POIDS_LITTORAL": (0.02, 2.0),
    "DELTA_PLUIE": (0.02, 3.0),
    "EFFET_PHASE_MAREE": (0.02, 0.6),
}
BORNES_VISIBILITE_CALME = (1.5, 40.0)
DECALAGE_FNU = 0.2  # évite que les eaux très claires pèsent trop dans l'erreur logarithmique


@dataclass
class SerieCalage:
    """Un point de référence, sa météo passée et ses observations satellite."""

    spot: Spot
    conditions: Conditions
    observations: list[ObservationSatellite]


@dataclass
class ResultatCalage:
    reglages: dict[str, float]
    visibilites_calmes: dict[str, float]
    erreur_initiale: float          # écart type logarithmique avant calage
    erreur_finale: float            # après calage, sur les observations d'apprentissage
    erreur_test: float | None       # après calage, sur les observations mises de côté
    erreur_test_initiale: float | None
    observations: int
    details: dict[str, float] = field(default_factory=dict)  # erreur finale par point


def turbidite_modele(spot: Spot, cond: Conditions, reglages: dict | None = None) -> np.ndarray:
    """Turbidité (FNU) que le modèle prévoit, hors plancton, heure par heure."""
    res = modele.calculer(spot, cond, reglages=reglages)
    c = res.composantes
    particules = c["fond_habituel"] + c["brassage"] + c["rivieres"] + c["pluie"]
    return particules / P.C_PAR_FNU


def _indices_observations(cond: Conditions, observations: list[ObservationSatellite]):
    indices, valeurs = [], []
    for obs in observations:
        if obs.turbidite_fnu is None:
            continue
        i = int(np.argmin(np.abs(cond.temps - obs.temps)))
        if abs(int(cond.temps[i]) - obs.temps) <= 3600:
            indices.append(i)
            valeurs.append(obs.turbidite_fnu)
    return np.array(indices, dtype=int), np.array(valeurs, dtype=float)


def _ecarts(spot: Spot, cond: Conditions, indices: np.ndarray, valeurs: np.ndarray, reglages: dict) -> np.ndarray:
    if len(indices) == 0:
        return np.array([])
    tur = turbidite_modele(spot, cond, reglages)[indices]
    return np.log(tur + DECALAGE_FNU) - np.log(valeurs + DECALAGE_FNU)


def separer(series: list[SerieCalage], part_apprentissage: float = 0.7):
    """Coupe chaque série dans le temps : le début pour caler, la fin pour vérifier."""
    apprentissage, test = [], []
    for s in series:
        obs = sorted(s.observations, key=lambda o: o.temps)
        k = int(round(len(obs) * part_apprentissage))
        apprentissage.append(replace(s, observations=obs[:k]))
        test.append(replace(s, observations=obs[k:]))
    return apprentissage, test


def caler(series: list[SerieCalage], test: list[SerieCalage] | None = None,
          parametres: tuple[str, ...] = tuple(BORNES), iterations_max: int = 40) -> ResultatCalage:
    """Ajuste les constantes globales et la visibilité calme de chaque point.

    Méthode : descente coordonnée par coordonnée, en échelle logarithmique,
    avec un pas qui diminue quand plus rien ne s'améliore. Simple, robuste,
    sans dépendance supplémentaire.
    """
    inconnus = set(parametres) - set(BORNES)
    if inconnus:
        raise ValueError(f"Paramètres non calables : {', '.join(sorted(inconnus))}")

    reglages = {nom: float(getattr(P, nom)) for nom in parametres}
    calmes = {s.spot.id: float(s.spot.visibilite_calme) for s in series}
    donnees = [(s, *_indices_observations(s.conditions, s.observations)) for s in series]
    n_obs = sum(len(d[1]) for d in donnees)
    if n_obs == 0:
        raise ValueError("Aucune observation satellite exploitable")

    def ecarts_serie(k: int) -> np.ndarray:
        s, idx, val = donnees[k]
        spot = replace(s.spot, visibilite_calme_m=calmes[s.spot.id])
        return _ecarts(spot, s.conditions, idx, val, reglages)

    cache = [ecarts_serie(k) for k in range(len(donnees))]

    def perte(c=None) -> float:
        tous = np.concatenate(c if c is not None else cache)
        return float(np.mean(tous**2))

    erreur_initiale = math.sqrt(perte())
    erreur_test_initiale = _erreur(test, reglages, calmes) if test else None

    pas = math.log(2.0)
    for _ in range(iterations_max):
        ameliore = False
        # Constantes globales : toutes les séries sont recalculées
        for nom in parametres:
            bas, haut = BORNES[nom]
            for sens in (1, -1):
                ancien = reglages[nom]
                candidat = min(max(ancien * math.exp(sens * pas), bas), haut)
                if candidat == ancien:
                    continue
                reglages[nom] = candidat
                nouveau_cache = [ecarts_serie(k) for k in range(len(donnees))]
                if perte(nouveau_cache) < perte() - 1e-9:
                    cache = nouveau_cache
                    ameliore = True
                    break
                reglages[nom] = ancien
        # Visibilité calme de chaque point : seule sa série est recalculée
        for k, (s, _, _) in enumerate(donnees):
            sid = s.spot.id
            bas, haut = BORNES_VISIBILITE_CALME
            for sens in (1, -1):
                ancien = calmes[sid]
                candidat = min(max(ancien * math.exp(sens * pas), bas), haut)
                if candidat == ancien:
                    continue
                calmes[sid] = candidat
                essai = list(cache)
                essai[k] = ecarts_serie(k)
                if perte(essai) < perte() - 1e-9:
                    cache = essai
                    ameliore = True
                    break
                calmes[sid] = ancien
        if not ameliore:
            pas /= 2
            if pas < math.log(1.02):
                break

    details = {s.spot.id: float(np.sqrt(np.mean(cache[k] ** 2))) if len(cache[k]) else float("nan")
               for k, (s, _, _) in enumerate(donnees)}
    return ResultatCalage(
        reglages={k: round(v, 5) for k, v in reglages.items()},
        visibilites_calmes={k: round(v, 2) for k, v in calmes.items()},
        erreur_initiale=erreur_initiale,
        erreur_finale=math.sqrt(perte()),
        erreur_test=_erreur(test, reglages, calmes) if test else None,
        erreur_test_initiale=erreur_test_initiale,
        observations=n_obs,
        details=details,
    )


def _erreur(series: list[SerieCalage], reglages: dict, calmes: dict) -> float | None:
    ecarts = []
    for s in series:
        idx, val = _indices_observations(s.conditions, s.observations)
        spot = replace(s.spot, visibilite_calme_m=calmes.get(s.spot.id, s.spot.visibilite_calme))
        ecarts.append(_ecarts(spot, s.conditions, idx, val, reglages))
    tous = np.concatenate(ecarts) if ecarts else np.array([])
    return float(np.sqrt(np.mean(tous**2))) if len(tous) else None


def en_pourcentage(erreur_log: float) -> float:
    """Écart type logarithmique converti en erreur relative typique (%)."""
    return 100 * (math.exp(erreur_log) - 1)
