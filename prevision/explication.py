"""Phrases qui expliquent la prévision à l'utilisateur."""

from __future__ import annotations

import numpy as np

from . import parametres as P, physique
from .donnees import Conditions
from .modele import ResultatModele
from .spot import Spot

SEUIL_NOTABLE = 0.15  # m⁻¹ : en dessous, une composante ne mérite pas d'être citée
SEUIL_CHARGEE = 0.5   # m⁻¹ de brassage : au-delà, l'eau est dite « chargée », en dessous « un peu chargée »


def _fmt(x: float, decimales: int = 1) -> str:
    return f"{x:.{decimales}f}".replace(".", ",")


def expliquer(spot: Spot, cond: Conditions, res: ResultatModele, i: int) -> list[str]:
    """Une à deux phrases sur ce qui fait la visibilité à l'heure i."""
    comp = {k: float(v[i]) for k, v in res.composantes.items()}
    phrases: list[str] = []

    candidats = {k: comp[k] for k in ("brassage", "rivieres", "pluie", "plancton", "satellite")}
    principal = max(candidats, key=candidats.get)
    valeur = candidats[principal]

    hs = cond["hauteur_vagues"]
    direction = cond["direction_vagues"]

    if valeur < SEUIL_NOTABLE and comp["satellite"] > -SEUIL_NOTABLE:
        if np.nanmax(hs[max(0, i - 48): i + 1], initial=0.0) >= 1.5 and _expo(spot, direction[i]) < 0.4:
            phrases.append(f"Spot abrité de la houle {_de(secteur(direction[i]))} : eau claire pour le secteur.")
        else:
            phrases.append("Mer calme et sans apport d'eau trouble : eau claire pour ce spot.")
    elif principal == "brassage":
        phrases.append(_phrase_brassage(spot, cond, res, i))
    elif principal == "rivieres":
        noms = [st.nom for st in spot.stations if st.nom]
        riviere = f" ({', '.join(noms)})" if noms else ""
        phrases.append(f"Rivière en crue à proximité{riviere} : apport d'eau trouble.")
    elif principal == "pluie":
        cumul = res.diagnostics["cumul_pluie"][i]
        phrases.append(f"Fortes pluies récentes (environ {cumul:.0f} mm) : ruissellement vers la côte.")
    elif principal == "plancton":
        phrases.append("Présence de plancton, fréquente en cette saison.")
    elif principal == "satellite":
        phrases.append("La dernière image satellite montre une eau plus trouble que prévu.")

    if comp["satellite"] < -SEUIL_NOTABLE:
        phrases.append("La dernière image satellite montre une eau plus claire que prévu.")

    vent = cond["vent"][i]
    if np.isfinite(vent):
        vent_kn = vent / P.NOEUD_EN_MS
        de_terre = bool(physique.vent_de_terre(cond["direction_vent"][i], spot.orientation_deg))
        if de_terre and vent_kn >= 15:
            phrases.append(f"Vent de terre fort ({vent_kn:.0f} nœuds) : attention à la dérive vers le large.")
        elif de_terre and vent_kn >= 5:
            phrases.append("Vent de terre : surface plutôt calme.")
        elif not de_terre and vent_kn >= P.VENT_GENANT_KN:
            phrases.append(f"Vent de mer soutenu ({vent_kn:.0f} nœuds).")

    return phrases[:2]


def conseil_maree(res: ResultatModele, spot: Spot) -> str | None:
    """Rappel sur la marée quand elle compte pour ce spot."""
    if spot.sensibilite_maree_effective >= 0.3 and np.any(res.diagnostics["phase_maree"] != 0):
        return "Visibilité généralement meilleure autour de la pleine mer."
    return None


def tendance(visibilite_avant: float, visibilite_apres: float) -> str:
    if visibilite_avant <= 0:
        return "stable"
    r = visibilite_apres / visibilite_avant
    if r >= 1.15:
        return "amélioration"
    if r <= 0.87:
        return "dégradation"
    return "stable"


SECTEURS = ("nord", "nord-est", "est", "sud-est", "sud", "sud-ouest", "ouest", "nord-ouest")


def secteur(direction_deg: float) -> str:
    """Nom du secteur (8 directions) d'où vient le vent ou la houle."""
    if not np.isfinite(direction_deg):
        return "secteur inconnu"
    return SECTEURS[int(((direction_deg % 360) + 22.5) // 45) % 8]


def _de(mot: str) -> str:
    return f"d'{mot}" if mot[0] in "aeiouy" else f"de {mot}"


def _expo(spot: Spot, direction: float) -> float:
    return float(physique.exposition(direction, spot.orientation_deg, spot.ouverture_deg))


def _phrase_brassage(spot: Spot, cond: Conditions, res: ResultatModele, i: int) -> str:
    hs = cond["hauteur_vagues"]
    periode = cond["periode_vagues"]
    h_now = hs[i] if np.isfinite(hs[i]) else 0.0
    courant = cond["courant"][i] if np.isfinite(cond["courant"][i]) else 0.0
    etat = "chargée" if float(res.composantes["brassage"][i]) >= SEUIL_CHARGEE else "un peu chargée"

    if h_now >= 1.0 and _expo(spot, cond["direction_vagues"][i]) >= 0.3:
        t_txt = f", période {periode[i]:.0f} s" if np.isfinite(periode[i]) else ""
        return f"Houle de {_fmt(h_now)} m{t_txt} qui brasse le fond : eau {etat}."

    debut = max(0, i - 72)
    fenetre = np.nan_to_num(hs[debut: i + 1], nan=0.0)
    if len(fenetre) and fenetre.max() >= 1.0:
        j = debut + int(np.argmax(fenetre))
        heures = (i - j)
        quand = "ces dernières heures" if heures <= 12 else ("d'hier" if heures <= 36 else "des jours précédents")
        if quand == "ces dernières heures":
            return f"La houle retombe, mais l'eau reste {etat} après le pic de {_fmt(fenetre.max())} m de ces dernières heures."
        return f"La mer s'est calmée, mais l'eau reste {etat} après la houle de {_fmt(fenetre.max())} m {quand}."

    if courant >= 0.5:
        return "Forts courants qui remettent le sable en suspension."
    return "Fond légèrement brassé par la houle : eau un peu chargée."
