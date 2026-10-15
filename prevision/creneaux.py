"""Choix du meilleur créneau de la journée.

La chasse sous-marine est interdite entre le coucher et le lever du soleil :
seules les heures de jour sont proposées.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from . import parametres as P


@dataclass
class Creneau:
    debut: int              # secondes Unix (début de la première heure)
    fin: int                # secondes Unix (fin de la dernière heure)
    visibilite_moyenne: float
    visibilite_min: float
    visibilite_max: float
    score: float


def score_horaire(visibilite_ressentie, hauteur_vagues, rafales_ms, vent_ms, vent_de_terre, seuil_excellent):
    """Note de 0 à 1,5 par heure ; 0 si les conditions sont déconseillées."""
    vis = np.clip(np.nan_to_num(visibilite_ressentie, nan=0.0) / seuil_excellent, 0.0, 1.5)
    hs = np.nan_to_num(hauteur_vagues, nan=0.0)
    rafales_kn = np.nan_to_num(rafales_ms, nan=0.0) / P.NOEUD_EN_MS
    vent_kn = np.nan_to_num(vent_ms, nan=0.0) / P.NOEUD_EN_MS

    confort = np.where(
        hs <= P.HOULE_CONFORT_M,
        1.0,
        1.0 - 0.4 * (hs - P.HOULE_CONFORT_M) / (P.HOULE_DECONSEILLEE_M - P.HOULE_CONFORT_M),
    )
    confort = np.where((vent_kn > P.VENT_GENANT_KN) & ~np.asarray(vent_de_terre, dtype=bool), confort * 0.8, confort)
    deconseille = (hs > P.HOULE_DECONSEILLEE_M) | (rafales_kn > P.RAFALES_DECONSEILLEES_KN)
    return np.where(deconseille, 0.0, vis * confort), deconseille


def meilleur_creneau(temps, score, visibilite, de_jour) -> Creneau | None:
    """Plage d'heures consécutives (2 à 4 h) de jour avec la meilleure note moyenne."""
    t = np.asarray(temps)
    s = np.asarray(score, dtype=float)
    ok = np.asarray(de_jour, dtype=bool) & (s > 0)
    meilleur: Creneau | None = None
    meilleure_note = -1.0
    n = len(t)
    for debut in range(n):
        if not ok[debut]:
            continue
        for duree in range(P.DUREE_CRENEAU_MIN_H, P.DUREE_CRENEAU_MAX_H + 1):
            fin = debut + duree
            if fin > n or not ok[debut:fin].all():
                break
            note = s[debut:fin].mean() * (1 + 0.05 * (duree - P.DUREE_CRENEAU_MIN_H))
            if note > meilleure_note + 1e-9:
                v = visibilite[debut:fin]
                meilleure_note = note
                meilleur = Creneau(int(t[debut]), int(t[fin - 1]) + 3600, float(v.mean()), float(v.min()), float(v.max()), float(note))
    return meilleur
