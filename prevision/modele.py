"""Cœur du modèle : de la météo marine à la visibilité en mètres.

Principe : la visibilité horizontale vaut 4,8 / c, où c est l'atténuation
de la lumière dans l'eau (m⁻¹). On additionne les sources d'atténuation :

    c = eau claire + fond habituel du spot
        + brassage (houle et courant, avec effet retard)
        + rivières en crue + pluie récente
        + plancton
        + correction satellite

Les composantes côtières (brassage, rivières, pluie) sont modulées par la
phase de la marée : l'eau du large qui arrive à la pleine mer est plus claire.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from . import maree, parametres as P, physique, soleil
from .donnees import Conditions, ObservationSatellite
from .spot import Spot


@dataclass
class ResultatModele:
    temps: np.ndarray
    visibilite_m: np.ndarray            # clarté de l'eau
    visibilite_ressentie_m: np.ndarray  # avec l'effet de la lumière
    composantes: dict[str, np.ndarray]  # contributions à l'atténuation (m⁻¹)
    diagnostics: dict[str, np.ndarray]  # grandeurs intermédiaires utiles aux explications
    extremes_maree: list[maree.Extreme]
    satellite_utilise: bool


def calculer(spot: Spot, cond: Conditions, satellite: ObservationSatellite | None = None,
             reglages: dict | None = None) -> ResultatModele:
    """`reglages` remplace certaines constantes de parametres.py (utilisé pour le calage)."""
    R = Reglages(reglages)
    t = cond.temps
    n = len(cond)
    fond = spot.params_fond
    region = spot.params_region

    # --- 1. Vitesse de l'eau au fond -----------------------------------------
    u_vagues = _vitesse_vagues(spot, cond, spot.profondeur_m)
    u_littoral = _vitesse_vagues(spot, cond, min(P.PROFONDEUR_LITTORAL_M, spot.profondeur_m))
    courant = np.nan_to_num(cond["courant"], nan=0.0) * spot.facteur_courant * R.COURANT_PRES_DU_FOND
    u_fond = np.sqrt(u_vagues**2 + courant**2)
    u_bord = np.sqrt(u_littoral**2 + courant**2)

    # --- 2. Marée ---------------------------------------------------------------
    ext = _extremes_en_cache(cond)
    marnage = maree.marnage_moyen(ext)
    maree_active = marnage >= P.MARNAGE_MINIMUM_M and spot.sensibilite_maree_effective > 0
    if maree_active:
        phase = maree.phase(t, ext)
        rapport = maree.rapport_marnage(t, ext)
    else:
        phase = np.zeros(n)
        rapport = np.ones(n)
    sens_maree = spot.sensibilite_maree_effective if maree_active else 0.0

    # --- 3. Brassage avec effet retard ------------------------------------------
    exces_local = np.maximum(0.0, (u_fond / fond["u_critique"]) ** 2 - 1) * fond["erodabilite"]
    exces_bord = np.maximum(0.0, (u_bord / R.U_CRITIQUE_LITTORAL) ** 2 - 1) * spot.part_sable * R.POIDS_LITTORAL
    effet_vives_eaux = 1 + R.EFFET_MARNAGE * sens_maree * (rapport - 1)
    source = R.ALPHA_BRASSAGE * (exces_local + exces_bord) * np.maximum(effet_vives_eaux, 0.5)
    charge = _memoire(source, fond["tau_h"] * R.FACTEUR_TAU)
    c_brassage = spot.sensibilite_houle * R.C_BRASSAGE_MAX * (1 - np.exp(-charge / R.C_BRASSAGE_MAX))

    # --- 4. Rivières --------------------------------------------------------------
    c_fluvial = np.zeros(n)
    for station in spot.stations:
        debit = cond.debits.get(station.code)
        if debit is None or station.debit_reference_m3s <= 0:
            continue
        debit = _prolonger(debit)
        retard = int(round(station.delai_h))
        if retard > 0:
            debit = np.concatenate([np.full(retard, debit[0]), debit[:-retard]])
        anomalie = np.maximum(0.0, debit / station.debit_reference_m3s - 1)
        apport = R.GAMMA_FLUVIAL * station.poids * anomalie**P.EXPOSANT_FLUVIAL
        c_fluvial += _lisser(apport, P.TAU_FLUVIAL_H)

    # --- 5. Pluie récente ---------------------------------------------------------
    pluie = np.nan_to_num(cond["pluie"], nan=0.0)
    cumul = _memoire(pluie, P.TAU_PLUIE_H)
    c_pluie = R.DELTA_PLUIE * spot.sensibilite_pluie * np.maximum(0.0, cumul - R.SEUIL_PLUIE_MM) / 10

    # --- 6. Plancton --------------------------------------------------------------
    # Valeurs saisonnières par façade. La chlorophylle satellite n'est pas utilisée : près des
    # côtes, les sédiments la faussent (le calage d'octobre 2026 la trouve maximale en hiver,
    # à l'inverse des vraies floraisons de printemps), et la turbidité satellite tient déjà
    # compte des particules, plancton compris.
    mois = _mois(t)
    c_plancton = np.array(region["plancton_mensuel"])[mois - 1]

    # --- 7. Fond habituel du spot et saison ---------------------------------------------
    c_base = np.full(n, max(P.CONSTANTE_VISIBILITE / spot.visibilite_calme - P.C_EAU, 0.0))
    saison = facteur_saison(t, R.SAISON[spot.region])

    # --- 8. Assemblage ----------------------------------------------------------------
    facteur_maree = 1 - R.EFFET_PHASE_MAREE * sens_maree * phase
    cotier = facteur_maree * (c_brassage + c_fluvial + c_pluie)
    c_modele = P.C_EAU + saison * (c_base + cotier) + c_plancton

    # --- 9. Correction par la dernière image satellite --------------------------------
    correction = np.zeros(n)
    satellite_utilise = False
    if satellite is not None and satellite.turbidite_fnu is not None:
        i_sat = int(np.argmin(np.abs(t - satellite.temps)))
        if abs(int(t[i_sat]) - satellite.temps) <= 3 * 3600:
            c_obs = P.C_EAU + P.C_PAR_FNU * max(satellite.turbidite_fnu, 0.0)
            # La turbidité satellite inclut déjà le plancton : on la compare au modèle hors plancton
            ecart = c_obs - (c_modele[i_sat] - c_plancton[i_sat])
            correction = ecart * _poids_satellite(t, satellite.temps)
            satellite_utilise = True

    c_total = np.maximum(c_modele + correction, P.C_EAU + 0.02)
    visibilite = np.minimum(P.CONSTANTE_VISIBILITE / c_total, region["visibilite_max_m"])

    # --- 10. Lumière ------------------------------------------------------------------
    hauteur = soleil.hauteur_soleil(spot.lat, spot.lon, t)
    lumiere = _facteur_lumiere(hauteur, cond["nebulosite"])
    ressentie = visibilite * lumiere

    composantes = {
        "eau": np.full(n, P.C_EAU),
        "fond_habituel": saison * c_base,
        "brassage": saison * facteur_maree * c_brassage,
        "rivieres": saison * facteur_maree * c_fluvial,
        "pluie": saison * facteur_maree * c_pluie,
        "plancton": c_plancton,
        "satellite": correction,
    }
    diagnostics = {
        "vitesse_fond": u_fond,
        "phase_maree": phase,
        "rapport_marnage": rapport,
        "cumul_pluie": cumul,
        "hauteur_soleil": hauteur,
        "facteur_lumiere": lumiere,
        "attenuation": c_total,
    }
    return ResultatModele(t, visibilite, ressentie, composantes, diagnostics, ext, satellite_utilise)


def hauteur_au_spot(spot: Spot, cond: Conditions) -> np.ndarray:
    """Hauteur de vagues estimée au spot, une fois l'abri pris en compte (m)."""

    def exposee(hauteur, direction):
        expo = physique.exposition(direction, spot.orientation_deg, spot.ouverture_deg)
        return np.nan_to_num(hauteur, nan=0.0) * expo

    if cond.a_composantes():
        houle = exposee(cond["hauteur_houle"], cond["direction_houle"])
        mer = exposee(cond["hauteur_mer_vent"], cond["direction_mer_vent"])
        hauteur = np.sqrt(houle**2 + mer**2)
    else:
        hauteur = exposee(cond["hauteur_vagues"], cond["direction_vagues"])
    return np.where(np.isfinite(cond["hauteur_vagues"]) | cond.a_composantes(), hauteur, np.nan)


# --- Outils ------------------------------------------------------------------------


class Reglages:
    """Constantes de parametres.py, dont certaines peuvent être remplacées."""

    def __init__(self, remplacements: dict | None = None):
        inconnus = set(remplacements or {}) - set(dir(P))
        if inconnus:
            raise ValueError(f"Réglages inconnus : {', '.join(sorted(inconnus))}")
        self._remplacements = dict(remplacements or {})

    def __getattr__(self, nom: str):
        if nom.startswith("_"):
            raise AttributeError(nom)
        return self._remplacements.get(nom, getattr(P, nom))


def facteur_saison(t: np.ndarray, saison: dict) -> np.ndarray:
    """Eaux côtières plus chargées en hiver : exp(amplitude · cos(2π (jour − pic) / 365,25))."""
    jour = (np.asarray(t, dtype=float) / 86400.0) % 365.25   # jour de l'année (approché à un jour près)
    return np.exp(saison["amplitude"] * np.cos(2 * np.pi * (jour - saison["pic_jour"]) / 365.25))


def _extremes_en_cache(cond: Conditions) -> list[maree.Extreme]:
    """Pleines et basses mers, calculées une seule fois par jeu de conditions."""
    cle = id(cond["niveau_mer"])
    cache = cond.__dict__.setdefault("_cache", {})
    if cache.get("maree_cle") != cle:
        cache["maree_cle"] = cle
        cache["maree"] = maree.extremes(cond.temps, cond["niveau_mer"])
    return cache["maree"]


def _mois(t: np.ndarray) -> np.ndarray:
    """Mois (1 à 12) de chaque instant, en UTC."""
    jours = np.asarray(t, dtype="int64") // 86400
    return np.asarray(jours.astype("datetime64[D]").astype("datetime64[M]").astype(int) % 12 + 1)


def _vitesse_vagues(spot: Spot, cond: Conditions, profondeur: float) -> np.ndarray:
    """Vitesse au fond due aux vagues, avec l'abri du spot."""

    def composante(hauteur, periode, direction):
        expo = physique.exposition(direction, spot.orientation_deg, spot.ouverture_deg)
        return physique.vitesse_orbitale_fond(np.nan_to_num(hauteur, nan=0.0) * expo, periode, profondeur)

    if cond.a_composantes():
        u_houle = composante(cond["hauteur_houle"], cond["periode_houle"], cond["direction_houle"])
        u_mer = composante(cond["hauteur_mer_vent"], cond["periode_mer_vent"], cond["direction_mer_vent"])
        return np.sqrt(u_houle**2 + u_mer**2)
    return composante(cond["hauteur_vagues"], cond["periode_vagues"], cond["direction_vagues"])


def _memoire(entree: np.ndarray, tau_h: float) -> np.ndarray:
    """Accumulation avec oubli exponentiel : x[i] = x[i-1]·e^(-1/τ) + entrée[i]."""
    # Calcul vectorisé par blocs (identique à la boucle, mais bien plus rapide
    # sur plusieurs années de données horaires, utile pour le calage).
    d = np.exp(-1.0 / tau_h)
    x = np.asarray(entree, dtype=float)
    n = len(x)
    bloc = max(16, min(256, int(30 * tau_h)))  # évite les débordements de d^-j
    j = np.arange(bloc)
    puissances = d**j
    inverses = d ** (-j)
    sortie = np.empty(n)
    acc = 0.0
    for debut in range(0, n, bloc):
        morceau = x[debut: debut + bloc]
        m = len(morceau)
        y = puissances[:m] * np.cumsum(morceau * inverses[:m]) + acc * puissances[:m] * d
        sortie[debut: debut + m] = y
        acc = y[-1]
    return sortie


def _lisser(entree: np.ndarray, tau_h: float) -> np.ndarray:
    """Moyenne glissante exponentielle (même niveau que l'entrée en régime établi)."""
    return _memoire(entree, tau_h) * (1 - np.exp(-1.0 / tau_h))


def _prolonger(serie: np.ndarray) -> np.ndarray:
    """Comble les trous ; après la dernière mesure, garde la dernière valeur connue."""
    s = np.asarray(serie, dtype=float)
    ok = np.isfinite(s)
    if not ok.any():
        return np.zeros(len(s))
    x = np.arange(len(s))
    return np.interp(x, x[ok], s[ok])


def _poids_satellite(t: np.ndarray, t_sat: int) -> np.ndarray:
    """Poids de l'observation satellite : 1 à la date de l'image, décroissant de part et d'autre."""
    age_h = np.abs(t - t_sat) / 3600.0
    return np.exp(-age_h / P.TAU_ASSIMILATION_H)


def _facteur_lumiere(hauteur_soleil: np.ndarray, nebulosite: np.ndarray) -> np.ndarray:
    soleil_bas = np.clip(hauteur_soleil / P.HAUTEUR_SOLEIL_PLEINE_LUMIERE, 0.0, 1.0)
    f_soleil = P.FACTEUR_SOLEIL_BAS + (1 - P.FACTEUR_SOLEIL_BAS) * soleil_bas
    couvert = np.clip(np.nan_to_num(nebulosite, nan=50.0) / 100.0, 0.0, 1.0)
    f_ciel = 1 - (1 - P.FACTEUR_CIEL_COUVERT) * couvert
    return f_soleil * f_ciel
