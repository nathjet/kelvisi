"""Structures de données communes, indépendantes des sources."""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np

CHAMPS_HORAIRES = (
    # Vagues (hauteurs en m, périodes en s, directions de provenance en degrés)
    "hauteur_vagues", "periode_vagues", "direction_vagues",
    "hauteur_houle", "periode_houle", "direction_houle",
    "hauteur_mer_vent", "periode_mer_vent", "direction_mer_vent",
    # Courant (m/s, direction vers laquelle il porte) et niveau de la mer (m)
    "courant", "direction_courant", "niveau_mer",
    # Atmosphère
    "vent", "direction_vent", "rafales",   # m/s, degrés de provenance
    "pluie",                                 # mm sur l'heure
    "nebulosite",                            # % de ciel couvert
    "temperature_eau",                       # °C
)


@dataclass
class Conditions:
    """Séries horaires alignées sur `temps` (secondes Unix, UTC).

    Un champ absent est un tableau rempli de NaN. `debits` associe un code
    de station Hub'Eau à une série horaire de débits (m³/s).
    """

    temps: np.ndarray
    series: dict[str, np.ndarray] = field(default_factory=dict)
    debits: dict[str, np.ndarray] = field(default_factory=dict)
    lat: float | None = None
    lon: float | None = None

    def __post_init__(self):
        self.temps = np.asarray(self.temps, dtype=np.int64)
        n = len(self.temps)
        if n < 2:
            raise ValueError("Au moins deux heures de données sont nécessaires")
        if np.any(np.diff(self.temps) != 3600):
            raise ValueError("Les séries doivent être horaires et continues")
        for nom in CHAMPS_HORAIRES:
            valeurs = self.series.get(nom)
            if valeurs is None:
                self.series[nom] = np.full(n, np.nan)
            else:
                valeurs = np.asarray(valeurs, dtype=float)
                if len(valeurs) != n:
                    raise ValueError(f"Longueur incorrecte pour {nom}")
                self.series[nom] = valeurs
        for code, valeurs in list(self.debits.items()):
            valeurs = np.asarray(valeurs, dtype=float)
            if len(valeurs) != n:
                raise ValueError(f"Longueur incorrecte pour le débit {code}")
            self.debits[code] = valeurs

    def __getitem__(self, nom: str) -> np.ndarray:
        return self.series[nom]

    def __len__(self) -> int:
        return len(self.temps)

    def vers_dict(self) -> dict:
        """Forme JSON (valeurs manquantes à null), lisible aussi par le moteur JavaScript."""
        def liste(v):
            return [None if not np.isfinite(x) else float(x) for x in v]
        return {
            "temps": [int(x) for x in self.temps],
            "series": {k: liste(v) for k, v in self.series.items()},
            "debits": {k: liste(v) for k, v in self.debits.items()},
            "lat": self.lat, "lon": self.lon,
        }

    @classmethod
    def depuis_dict(cls, d: dict) -> "Conditions":
        def tableau(v):
            return np.array([np.nan if x is None else x for x in v], dtype=float)
        return cls(
            temps=np.asarray(d["temps"], dtype=np.int64),
            series={k: tableau(v) for k, v in d.get("series", {}).items()},
            debits={k: tableau(v) for k, v in d.get("debits", {}).items()},
            lat=d.get("lat"), lon=d.get("lon"),
        )

    def a_composantes(self) -> bool:
        """Vrai si la houle et la mer du vent sont fournies séparément."""
        return bool(np.any(np.isfinite(self["hauteur_houle"])) and np.any(np.isfinite(self["hauteur_mer_vent"])))


@dataclass
class ObservationSatellite:
    """Dernière observation satellite exploitable au droit du spot."""

    temps: int                          # secondes Unix (UTC) de l'image
    turbidite_fnu: float | None = None
    chlorophylle_mg_m3: float | None = None


@dataclass
class Rapport:
    """Retour terrain d'un utilisateur."""

    temps: int                  # secondes Unix (UTC)
    visibilite_m: float
    utilisateur: str
    prevision_m: float | None = None   # visibilité qui avait été prévue à ce moment
