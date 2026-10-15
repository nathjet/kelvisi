"""Assemble une prévision complète pour un spot, prête à envoyer à l'application."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

import numpy as np

from . import calibrage as cal, creneaux, explication, modele, parametres as P, physique, soleil
from .donnees import Conditions, ObservationSatellite, Rapport
from .spot import Spot

VERSION_MODELE = "0.4.0"


def classe(visibilite: float, spot: Spot) -> str:
    s1, s2, s3 = spot.params_region["seuils"]
    if visibilite < s1:
        return P.CLASSES[0]
    if visibilite < s2:
        return P.CLASSES[1]
    if visibilite < s3:
        return P.CLASSES[2]
    return P.CLASSES[3]


def arrondir(visibilite: float) -> float:
    """0,5 m près sous 10 m, au mètre au-delà."""
    if visibilite < 10:
        return round(visibilite * 2) / 2
    return float(round(visibilite))


def niveau_confiance(incertitude: float) -> tuple[int, str]:
    score = int(round(100 * np.exp(-1.6 * incertitude)))
    if score >= 65:
        return score, "élevée"
    if score >= 40:
        return score, "moyenne"
    return score, "faible"


def prevoir(
    spot: Spot,
    cond: Conditions,
    maintenant: int,
    satellite: ObservationSatellite | None = None,
    rapports: list[Rapport] | None = None,
    jours: int = 3,
    fuseau: str = "Europe/Paris",
) -> dict:
    """Prévision heure par heure et résumé par jour, au format JSON.

    `cond` doit couvrir quelques jours avant `maintenant` : ces jours servent
    à l'effet retard (une houle d'avant-hier trouble encore l'eau aujourd'hui).
    """
    tz = ZoneInfo(fuseau)
    res = modele.calculer(spot, cond, satellite)
    t = cond.temps

    calib = cal.calibrer(rapports or [], maintenant)
    visibilite = res.visibilite_m * calib.facteur
    ressentie = res.visibilite_ressentie_m * calib.facteur
    vis_max = spot.params_region["visibilite_max_m"]
    visibilite = np.minimum(visibilite, vis_max)
    ressentie = np.minimum(ressentie, vis_max)

    i0 = int(np.searchsorted(t, maintenant - (maintenant % 3600)))
    if i0 >= len(t):
        raise ValueError("Les données s'arrêtent avant l'heure demandée")
    fin_locale = datetime.fromtimestamp(t[i0], tz).replace(hour=0, minute=0, second=0) + timedelta(days=jours)
    i1 = min(len(t), int(np.searchsorted(t, fin_locale.timestamp())))

    # --- Incertitude --------------------------------------------------------------
    if res.satellite_utilise and satellite is not None:
        age_sat_j = max(0.0, (maintenant - satellite.temps) / 86400.0)
        base = P.INCERTITUDE_AVEC_SATELLITE + P.INCERTITUDE_AGE_SATELLITE_PAR_JOUR * age_sat_j
    else:
        age_sat_j = None
        base = P.INCERTITUDE_SANS_SATELLITE
    if calib.nombre_effectif >= 5 and calib.dispersion < 0.3:
        base *= 0.8
    echeance_j = np.maximum(0.0, (t - maintenant) / 86400.0)
    incertitude = np.minimum(base + P.INCERTITUDE_PAR_JOUR * echeance_j, P.INCERTITUDE_MAX)

    # --- Sécurité, confort, jour ------------------------------------------------------
    # Une heure n'est proposée que si le soleil est levé à son début et à sa fin
    de_jour = soleil.fait_jour(spot.lat, spot.lon, t) & soleil.fait_jour(spot.lat, spot.lon, t + 3600)
    de_terre = physique.vent_de_terre(cond["direction_vent"], spot.orientation_deg)
    houle_spot = modele.hauteur_au_spot(spot, cond)
    score, deconseille = creneaux.score_horaire(
        ressentie, houle_spot, cond["rafales"], cond["vent"], de_terre, spot.params_region["seuils"][2]
    )

    # --- Heures --------------------------------------------------------------------
    heures = []
    for i in range(i0, i1):
        v = float(visibilite[i])
        conf, conf_txt = niveau_confiance(float(incertitude[i]))
        u = float(incertitude[i])
        heures.append({
            "heure": datetime.fromtimestamp(int(t[i]), tz).isoformat(),
            "visibilite_m": arrondir(v),
            "fourchette_m": [arrondir(v * np.exp(-u)), arrondir(v * np.exp(u))],
            "visibilite_ressentie_m": arrondir(float(ressentie[i])),
            "classe": classe(v, spot),
            "confiance": conf,
            "confiance_texte": conf_txt,
            "de_jour": bool(de_jour[i]),
            "deconseille": bool(deconseille[i]),
            "houle": {**_vagues(cond, i), "hauteur_au_spot_m": _nombre(houle_spot[i], 1)},
            "vent": _vent(cond, i, bool(de_terre[i])),
            "courant_ms": _nombre(cond["courant"][i], 2),
            "niveau_mer_m": _nombre(cond["niveau_mer"][i], 2),
            "pluie_mm": _nombre(cond["pluie"][i], 1),
            "nebulosite_pct": _nombre(cond["nebulosite"][i], 0),
            "temperature_eau_c": _nombre(cond["temperature_eau"][i], 1),
        })

    # --- Jours --------------------------------------------------------------------
    jours_sortie = []
    debut_jour = datetime.fromtimestamp(t[i0], tz).replace(hour=0, minute=0, second=0, microsecond=0)
    moyennes = []
    for d in range(jours):
        j0 = debut_jour + timedelta(days=d)
        j1 = j0 + timedelta(days=1)
        a = int(np.searchsorted(t, j0.timestamp()))
        b = int(np.searchsorted(t, j1.timestamp()))
        a = max(a, i0)
        if a >= b:
            break
        jour_mask = de_jour[a:b]
        vis_jour = visibilite[a:b][jour_mask]
        moyenne = float(vis_jour.mean()) if len(vis_jour) else float(visibilite[a:b].mean())
        moyennes.append(moyenne)
        cr = creneaux.meilleur_creneau(t[a:b], score[a:b], visibilite[a:b], jour_mask)
        if cr is not None:
            i_ref = int(np.searchsorted(t, (cr.debut + cr.fin) // 2, side="right")) - 1
        else:
            i_ref = a + (b - a) // 2
        i_ref = int(np.clip(i_ref, a, b - 1))
        phrases = explication.expliquer(spot, cond, res, i_ref)
        lever, coucher = soleil.lever_coucher(spot.lat, spot.lon, int(j0.timestamp()))
        marees = [
            {"type": e.type, "heure": datetime.fromtimestamp(int(e.temps), tz).isoformat(), "hauteur_m": round(e.hauteur, 2)}
            for e in res.extremes_maree
            if j0.timestamp() <= e.temps < j1.timestamp()
        ]
        jours_sortie.append({
            "date": j0.date().isoformat(),
            "alerte": _alerte(cond, houle_spot, deconseille, np.arange(a, b)[jour_mask]),
            "visibilite_moyenne_m": arrondir(moyenne),
            "classe": classe(moyenne, spot),
            "meilleur_creneau": None if cr is None else {
                "debut": datetime.fromtimestamp(cr.debut, tz).isoformat(),
                "fin": datetime.fromtimestamp(cr.fin, tz).isoformat(),
                "visibilite_m": arrondir(cr.visibilite_moyenne),
            },
            "explication": " ".join(phrases),
            "conseil_maree": explication.conseil_maree(res, spot),
            "deconseille_toute_la_journee": bool(deconseille[a:b][jour_mask].all()) if jour_mask.any() else False,
            "lever_soleil": None if lever is None else datetime.fromtimestamp(lever, tz).isoformat(),
            "coucher_soleil": None if coucher is None else datetime.fromtimestamp(coucher, tz).isoformat(),
            "marees": marees if spot.sensibilite_maree_effective > 0 else [],
        })
    for d, jour in enumerate(jours_sortie):
        if d + 1 < len(moyennes):
            jour["tendance"] = explication.tendance(moyennes[d], moyennes[d + 1])
        else:
            jour["tendance"] = None

    return {
        "spot": {"id": spot.id, "nom": spot.nom, "lat": spot.lat, "lon": spot.lon},
        "genere_le": datetime.fromtimestamp(maintenant, timezone.utc).isoformat(),
        "version_modele": VERSION_MODELE,
        "satellite": {
            "utilise": res.satellite_utilise,
            "age_jours": None if age_sat_j is None else round(age_sat_j, 1),
        },
        "calibrage": {"facteur": round(calib.facteur, 3), "rapports": round(calib.nombre_effectif, 1)},
        "jours": jours_sortie,
        "heures": heures,
        # Visibilité prévue pendant les 48 h écoulées : sert à comparer avec les retours terrain
        "historique": [
            {"heure": datetime.fromtimestamp(int(t[i]), tz).isoformat(), "visibilite_m": arrondir(float(visibilite[i]))}
            for i in range(max(0, i0 - 48), i0)
        ],
        # Pluie tombée pendant les 48 h écoulées (somme dans l'ordre, comme le moteur du navigateur)
        "pluie_48h_mm": _pluie_passee(cond, i0),
        "avertissement": "Prévision indicative : elle ne remplace pas l'observation sur place.",
    }


def _alerte(cond: Conditions, houle_spot: np.ndarray, deconseille: np.ndarray, heures_jour: np.ndarray) -> str | None:
    """Message de sécurité si des heures de jour sont déconseillées."""
    if len(heures_jour) == 0 or not deconseille[heures_jour].any():
        return None
    raisons = []
    houle_max = np.nanmax(houle_spot[heures_jour], initial=0.0)
    rafales_max = np.nanmax(cond["rafales"][heures_jour], initial=0.0) / P.NOEUD_EN_MS
    if houle_max > P.HOULE_DECONSEILLEE_M:
        raisons.append(f"houle jusqu'à {houle_max:.1f} m au spot".replace(".", ","))
    if rafales_max > P.RAFALES_DECONSEILLEES_KN:
        raisons.append(f"rafales jusqu'à {rafales_max:.0f} nœuds")
    debut = "Sortie déconseillée" if deconseille[heures_jour].all() else "Sortie déconseillée à certaines heures"
    if not raisons:
        return f"{debut}."
    return f"{debut} : {' et '.join(raisons)}."


def _pluie_passee(cond: Conditions, i0: int) -> float:
    total = 0.0
    for x in cond["pluie"][max(0, i0 - 48): i0]:
        if np.isfinite(x):
            total += float(x)
    return round(total, 1)


def _nombre(x, decimales):
    return None if not np.isfinite(x) else round(float(x), decimales)


def _vagues(cond: Conditions, i: int) -> dict:
    return {
        "hauteur_m": _nombre(cond["hauteur_vagues"][i], 1),
        "periode_s": _nombre(cond["periode_vagues"][i], 0),
        "direction_deg": _nombre(cond["direction_vagues"][i], 0),
    }


def _vent(cond: Conditions, i: int, de_terre: bool) -> dict:
    vitesse = cond["vent"][i]
    rafales = cond["rafales"][i]
    return {
        "vitesse_kn": None if not np.isfinite(vitesse) else round(float(vitesse / P.NOEUD_EN_MS)),
        "rafales_kn": None if not np.isfinite(rafales) else round(float(rafales / P.NOEUD_EN_MS)),
        "direction_deg": _nombre(cond["direction_vent"][i], 0),
        "de_terre": de_terre if np.isfinite(cond["direction_vent"][i]) else None,
    }
