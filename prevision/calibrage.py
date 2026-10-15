"""Correction du modèle par les retours terrain.

Chaque rapport compare la visibilité constatée à celle qui avait été prévue.
On en tire un facteur multiplicatif propre au spot, prudent tant que les
rapports sont peu nombreux (on « rétrécit » vers 1).
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass

import numpy as np

from .donnees import Rapport

DEMI_VIE_JOURS = 30.0      # un rapport de plus d'un mois compte moitié moins
RETRECISSEMENT = 3.0       # équivaut à 3 rapports « neutres » ajoutés
FIABILITE_DEFAUT = 0.7
ECHELLE_ERREUR = 0.35      # écart logarithmique typique d'un rapport honnête
FENETRE_VOISINS_S = 3 * 3600


@dataclass
class Calibrage:
    facteur: float          # à multiplier par la visibilité du modèle
    nombre_effectif: float  # somme des poids des rapports utilisés
    dispersion: float       # écart type logarithmique des rapports


def fiabilite_utilisateurs(rapports: list[Rapport]) -> dict[str, float]:
    """Fiabilité de 0 à 1 par utilisateur, d'après l'accord avec les autres.

    Pour chaque rapport, on regarde les rapports d'autres utilisateurs sur le
    même spot à moins de 3 h d'écart. Un utilisateur qui s'écarte souvent de
    ses voisins (ou qui signale toujours une eau trouble) voit sa fiabilité
    baisser. Sans voisin pour comparer, la fiabilité reste à la valeur par défaut.
    """
    ecarts: dict[str, list[float]] = defaultdict(list)
    for r in rapports:
        voisins = [
            v.visibilite_m for v in rapports
            if v.utilisateur != r.utilisateur and abs(v.temps - r.temps) <= FENETRE_VOISINS_S and v.visibilite_m > 0
        ]
        if voisins and r.visibilite_m > 0:
            ecarts[r.utilisateur].append(abs(np.log(r.visibilite_m / np.median(voisins))))
    resultat = {}
    for utilisateur in {r.utilisateur for r in rapports}:
        e = ecarts.get(utilisateur)
        if not e:
            resultat[utilisateur] = FIABILITE_DEFAUT
        else:
            resultat[utilisateur] = float(1.0 / (1.0 + np.mean(e) / ECHELLE_ERREUR))
    return resultat


def calibrer(rapports: list[Rapport], maintenant: int, fiabilites: dict[str, float] | None = None) -> Calibrage:
    """Facteur de correction du spot à partir de ses rapports."""
    utilisables = [r for r in rapports if r.prevision_m and r.prevision_m > 0 and r.visibilite_m > 0 and r.temps <= maintenant]
    if not utilisables:
        return Calibrage(1.0, 0.0, 0.0)
    if fiabilites is None:
        fiabilites = fiabilite_utilisateurs(rapports)
    ecarts = np.array([np.log(r.visibilite_m / r.prevision_m) for r in utilisables])
    age_jours = np.array([(maintenant - r.temps) / 86400.0 for r in utilisables])
    poids = np.array([fiabilites.get(r.utilisateur, FIABILITE_DEFAUT) for r in utilisables]) * 0.5 ** (age_jours / DEMI_VIE_JOURS)
    somme = poids.sum()
    biais = float((poids * ecarts).sum() / (somme + RETRECISSEMENT))
    dispersion = float(np.sqrt((poids * (ecarts - biais) ** 2).sum() / somme)) if somme > 0 else 0.0
    return Calibrage(float(np.exp(biais)), float(somme), dispersion)
