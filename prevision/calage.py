"""Calage du modèle sur l'historique satellite.

Sans retours de chasseurs, le satellite sert de référence : pour chaque
point de référence, on compare la turbidité que le modèle aurait prévue
(à partir de la météo marine de l'époque) à celle mesurée par le satellite.

Trois niveaux de réglage :
- constantes communes (« À CALER » dans parametres.py) : force et durée du
  brassage, pluie, rivières, marée ;
- saison de chaque façade : à houle égale, l'eau est plus chargée en hiver ;
- deux valeurs propres à chaque point : sa visibilité habituelle par temps
  calme et sa sensibilité à la houle (un spot abrité ou sur un fond rocheux
  propre réagit moins qu'un spot ouvert près d'une plage).

Méthode : les constantes communes sont ajustées une à une (descente par
coordonnées en échelle logarithmique). À chaque essai, les deux valeurs de
chaque point sont recalculées au mieux par recherche sur grille, ce qui est
rapide car elles agissent linéairement sur la turbidité prévue.

Ce calage règle le « quand » et le « combien » de la turbidité. La conversion
turbidité en mètres de visibilité (C_PAR_FNU) ne peut pas être calée ainsi :
elle le sera avec les retours terrain de la bêta.
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
    "ALPHA_BRASSAGE": (0.0003, 0.1),
    "FACTEUR_TAU": (0.2, 6.0),
    "POIDS_LITTORAL": (0.001, 3.0),
    "DELTA_PLUIE": (0.01, 4.0),
    "EFFET_PHASE_MAREE": (0.005, 0.8),
    "GAMMA_FLUVIAL": (0.02, 8.0),
    "C_BRASSAGE_MAX": (1.0, 40.0),
}
BORNES_VISIBILITE_CALME = (0.8, 40.0)
DECALAGE_FNU = 0.2  # évite que les eaux très claires pèsent trop dans l'erreur logarithmique

# Grilles de recherche des deux valeurs propres à chaque point
GRILLE_FOND_FNU = np.concatenate([[0.0], np.geomspace(0.01, 15.0, 160)])
GRILLE_HOULE = np.geomspace(0.05, 20.0, 49)
# Rappel vers 1 de la sensibilité à la houle quand les images ne suffisent pas à la fixer
RAPPEL_HOULE = 0.01


@dataclass
class SerieCalage:
    """Un point de référence, sa météo passée et ses observations satellite."""

    spot: Spot
    conditions: Conditions
    observations: list[ObservationSatellite]


@dataclass
class ResultatCalage:
    reglages: dict[str, float]
    saisons: dict[str, dict]
    visibilites_calmes: dict[str, float]
    sensibilites_houle: dict[str, float]
    erreur_initiale: float          # écart type logarithmique avant calage (valeurs actuelles)
    erreur_finale: float            # après calage, sur les observations d'apprentissage
    erreur_test: float | None       # après calage, sur les observations mises de côté
    erreur_test_initiale: float | None
    observations: int
    details: dict[str, float] = field(default_factory=dict)  # erreur finale par point (apprentissage)


def turbidite_modele(spot: Spot, cond: Conditions, reglages: dict | None = None) -> np.ndarray:
    """Turbidité (FNU) que le modèle prévoit, hors plancton, heure par heure."""
    fond, brassage, autres = composantes_turbidite(spot, cond, reglages)
    return fond + brassage + autres


def composantes_turbidite(spot: Spot, cond: Conditions, reglages: dict | None = None):
    """Turbidité (FNU) séparée en : fond habituel, brassage par la houle, rivières et pluie."""
    c = modele.calculer(spot, cond, reglages=reglages).composantes
    return (c["fond_habituel"] / P.C_PAR_FNU, c["brassage"] / P.C_PAR_FNU,
            (c["rivieres"] + c["pluie"]) / P.C_PAR_FNU)


def fond_vers_visibilite(fond_fnu: float) -> float:
    """Turbidité de fond (FNU) vers visibilité par temps calme (m), comme dans le modèle."""
    return P.CONSTANTE_VISIBILITE / (P.C_EAU + P.C_PAR_FNU * fond_fnu)


def visibilite_vers_fond(visibilite_m: float) -> float:
    return max(P.CONSTANTE_VISIBILITE / visibilite_m - P.C_EAU, 0.0) / P.C_PAR_FNU


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


def separer(series: list[SerieCalage], part_apprentissage: float = 0.7):
    """Coupe chaque série dans le temps : le début pour caler, la fin pour vérifier."""
    apprentissage, test = [], []
    for s in series:
        obs = sorted(s.observations, key=lambda o: o.temps)
        k = int(round(len(obs) * part_apprentissage))
        apprentissage.append(replace(s, observations=obs[:k]))
        test.append(replace(s, observations=obs[k:]))
    return apprentissage, test


def _neutre(spot: Spot) -> Spot:
    """Le point avec une sensibilité à la houle de 1 : les composantes sont ensuite mises à l'échelle."""
    return replace(spot, sensibilite_houle=1.0)


SANS_SAISON = {r: {"amplitude": 0.0, "pic_jour": 15.0} for r in P.SAISON}
BORNES_AMPLITUDE_SAISON = (0.0, 1.5)


def profil_point(brassage: np.ndarray, autres: np.ndarray, log_obs: np.ndarray,
                 saison: np.ndarray | None = None) -> tuple[float, float, float]:
    """Meilleures turbidité de fond (FNU) et sensibilité à la houle d'un point, et l'erreur obtenue.

    `brassage` et `autres` sont les composantes prévues aux heures des images
    (sensibilité 1, sans saison), `log_obs` le logarithme des turbidités
    observées (+ décalage), `saison` le facteur saisonnier aux mêmes heures.
    """
    bornes_fond = (visibilite_vers_fond(BORNES_VISIBILITE_CALME[1]), visibilite_vers_fond(BORNES_VISIBILITE_CALME[0]))
    fonds = GRILLE_FOND_FNU[(GRILLE_FOND_FNU >= bornes_fond[0]) & (GRILLE_FOND_FNU <= bornes_fond[1])]
    prevu = fonds[:, None, None] + GRILLE_HOULE[None, :, None] * brassage[None, None, :] + autres[None, None, :]
    if saison is not None:
        prevu = prevu * saison[None, None, :]
    ecarts = np.log(prevu + DECALAGE_FNU) - log_obs[None, None, :]
    cout = np.mean(ecarts**2, axis=2) + RAPPEL_HOULE * np.log(GRILLE_HOULE)[None, :] ** 2
    i, j = np.unravel_index(int(np.argmin(cout)), cout.shape)
    return float(fonds[i]), float(GRILLE_HOULE[j]), float(np.mean(ecarts[i, j] ** 2))


def _erreurs(fond: float, houle: float, brassage, autres, log_obs) -> np.ndarray:
    return np.log(fond + houle * brassage + autres + DECALAGE_FNU) - log_obs


def caler(series: list[SerieCalage], test: list[SerieCalage] | None = None,
          parametres: tuple[str, ...] = tuple(BORNES), saison: bool = True, iterations_max: int = 30) -> ResultatCalage:
    """Ajuste les constantes communes, la saison de chaque façade, la visibilité calme et la
    sensibilité à la houle de chaque point."""
    inconnus = set(parametres) - set(BORNES)
    if inconnus:
        raise ValueError(f"Paramètres non calables : {', '.join(sorted(inconnus))}")

    reglages = {nom: float(getattr(P, nom)) for nom in parametres}
    saisons = {r: dict(P.SAISON[r]) for r in P.SAISON}
    donnees = []
    for s in series:
        idx, val = _indices_observations(s.conditions, s.observations)
        if len(idx):
            donnees.append((s, idx, np.log(val + DECALAGE_FNU), s.conditions.temps[idx]))
    n_obs = sum(len(d[1]) for d in donnees)
    if n_obs == 0:
        raise ValueError("Aucune observation satellite exploitable")
    regions = sorted({d[0].spot.region for d in donnees}) if saison else []

    memoire: dict = {}

    def composantes(k: int, regl: dict):
        """Brassage et autres apports aux heures des images, sans saison (gardés en mémoire)."""
        cle = (k, tuple(sorted(regl.items())))
        if cle not in memoire:
            s, idx, _, _ = donnees[k]
            _, b, a = composantes_turbidite(_neutre(s.spot), s.conditions, {**regl, "SAISON": SANS_SAISON})
            memoire[cle] = (b[idx], a[idx])
        return memoire[cle]

    def evaluer(regl, sais) -> tuple[float, list]:
        profils, total = [], 0.0
        for k, (s, idx, lo, t_obs) in enumerate(donnees):
            b, a = composantes(k, regl)
            fond, houle, mse = profil_point(b, a, lo, modele.facteur_saison(t_obs, sais[s.spot.region]))
            profils.append((fond, houle))
            total += mse * len(idx)
        return total / n_obs, profils

    # Erreur des réglages actuels, avec les valeurs actuelles de chaque point (sans profil)
    def erreur_actuelle(liste) -> float | None:
        ecarts = []
        for s in liste or []:
            idx, val = _indices_observations(s.conditions, s.observations)
            if len(idx):
                ecarts.append(np.log(turbidite_modele(s.spot, s.conditions)[idx] + DECALAGE_FNU) - np.log(val + DECALAGE_FNU))
        return float(np.sqrt(np.mean(np.concatenate(ecarts) ** 2))) if ecarts else None

    erreur_initiale = erreur_actuelle(series)
    erreur_test_initiale = erreur_actuelle(test)

    perte, profils = evaluer(reglages, saisons)
    pas = math.log(2.0)
    for _ in range(iterations_max):
        ameliore = False
        for nom in parametres:
            bas, haut = BORNES[nom]
            for sens in (1, -1):
                ancien = reglages[nom]
                candidat = min(max(ancien * math.exp(sens * pas), bas), haut)
                if candidat == ancien:
                    continue
                reglages[nom] = candidat
                essai, essai_profils = evaluer(reglages, saisons)
                if essai < perte - 1e-6:
                    perte, profils = essai, essai_profils
                    ameliore = True
                    break
                reglages[nom] = ancien
        # Saison de chaque façade : amplitude puis date du maximum (pas fixes, réduits avec `pas`)
        for r in regions:
            for champ, saut in (("amplitude", 0.3), ("pic_jour", 45.0)):
                for sens in (1, -1):
                    ancien = saisons[r][champ]
                    if champ == "amplitude":
                        candidat = min(max(ancien + sens * saut * pas / math.log(2.0), BORNES_AMPLITUDE_SAISON[0]), BORNES_AMPLITUDE_SAISON[1])
                    else:
                        candidat = (ancien + sens * saut * pas / math.log(2.0)) % 365.25
                    if candidat == ancien:
                        continue
                    saisons[r][champ] = candidat
                    essai, essai_profils = evaluer(reglages, saisons)
                    if essai < perte - 1e-6:
                        perte, profils = essai, essai_profils
                        ameliore = True
                        break
                    saisons[r][champ] = ancien
        if not ameliore:
            pas /= 2
            if pas < math.log(1.03):
                break

    # Normalisation : un point « moyen » (sensibilité 1) doit correspondre aux constantes communes,
    # car les lieux recherchés par les utilisateurs n'ont pas de sensibilité calée. Multiplier
    # ALPHA_BRASSAGE et C_BRASSAGE_MAX par m revient exactement à multiplier le brassage par m.
    m = float(np.median([h for _, h in profils]))
    if "ALPHA_BRASSAGE" in reglages and "C_BRASSAGE_MAX" in reglages:
        reglages["ALPHA_BRASSAGE"] *= m
        reglages["C_BRASSAGE_MAX"] *= m
    else:
        m = 1.0

    saisons = {r: {"amplitude": round(v["amplitude"], 3), "pic_jour": round(v["pic_jour"], 1)} for r, v in saisons.items()}
    visibilites, sensibilites, details = {}, {}, {}
    for (s, idx, lo, _), (fond, houle) in zip(donnees, profils):
        visibilites[s.spot.id] = round(fond_vers_visibilite(fond), 2)
        sensibilites[s.spot.id] = round(houle / m, 3)
    # Erreurs finales, recalculées avec la vraie formule du modèle et les valeurs arrondies
    def erreur_finale(liste) -> tuple[float | None, dict]:
        ecarts, par_point = [], {}
        for s in liste or []:
            if s.spot.id not in visibilites:
                continue
            idx, val = _indices_observations(s.conditions, s.observations)
            if not len(idx):
                continue
            spot = replace(s.spot, visibilite_calme_m=visibilites[s.spot.id], sensibilite_houle=sensibilites[s.spot.id])
            e = (np.log(turbidite_modele(spot, s.conditions, {**reglages, "SAISON": saisons})[idx] + DECALAGE_FNU)
                 - np.log(val + DECALAGE_FNU))
            ecarts.append(e)
            par_point[s.spot.id] = float(np.sqrt(np.mean(e**2)))
        return (float(np.sqrt(np.mean(np.concatenate(ecarts) ** 2))) if ecarts else None), par_point

    erreur_app, details = erreur_finale(series)
    erreur_test, _ = erreur_finale(test)
    return ResultatCalage(
        reglages={k: round(v, 5) for k, v in reglages.items()},
        saisons=saisons,
        visibilites_calmes=visibilites,
        sensibilites_houle=sensibilites,
        erreur_initiale=erreur_initiale,
        erreur_finale=erreur_app,
        erreur_test=erreur_test,
        erreur_test_initiale=erreur_test_initiale,
        observations=n_obs,
        details=details,
    )


def en_pourcentage(erreur_log: float) -> float:
    """Écart type logarithmique converti en erreur relative typique (%)."""
    return 100 * (math.exp(erreur_log) - 1)
