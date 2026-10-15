"""Fiche technique d'un spot."""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from pathlib import Path

from . import parametres as P


@dataclass
class StationRiviere:
    """Station de débit Hub'Eau qui influence un spot."""

    code: str
    debit_reference_m3s: float          # débit habituel (médiane de la saison)
    poids: float = 1.0                  # influence sur le spot, de 0 à 1
    delai_h: float = 12.0               # trajet de l'eau trouble jusqu'au spot
    nom: str = ""                       # nom de la rivière, pour les explications


@dataclass
class Spot:
    """Caractéristiques fixes d'un spot.

    `orientation_deg` est la direction vers le large depuis le spot
    (0 = nord, 90 = est, 180 = sud, 270 = ouest).
    Les champs laissés à None prennent la valeur par défaut de la région
    ou du type de fond.
    """

    id: str
    nom: str
    lat: float
    lon: float
    region: str
    orientation_deg: float
    ouverture_deg: float = 90.0
    profondeur_m: float = 8.0
    fond: str = "mixte"
    part_sable_alentours: float | None = None
    visibilite_calme_m: float | None = None
    sensibilite_maree: float | None = None
    sensibilite_pluie: float = 0.3
    facteur_courant: float = 1.0
    stations: list[StationRiviere] = field(default_factory=list)
    prive: bool = False
    notes: str = ""

    def __post_init__(self):
        if self.region not in P.REGIONS:
            raise ValueError(f"Région inconnue : {self.region} (attendu : {', '.join(P.REGIONS)})")
        if self.fond not in P.FONDS:
            raise ValueError(f"Type de fond inconnu : {self.fond} (attendu : {', '.join(P.FONDS)})")
        if not -90 <= self.lat <= 90 or not -180 <= self.lon <= 180:
            raise ValueError("Coordonnées hors limites")
        if self.profondeur_m <= 0:
            raise ValueError("La profondeur doit être positive")
        if not 0 < self.ouverture_deg <= 180:
            raise ValueError("L'ouverture doit être comprise entre 0 et 180 degrés")
        self.orientation_deg = self.orientation_deg % 360.0
        self.stations = [s if isinstance(s, StationRiviere) else StationRiviere(**s) for s in self.stations]

    # --- Valeurs effectives (avec défauts) ---------------------------------

    @property
    def params_fond(self) -> dict:
        return P.FONDS[self.fond]

    @property
    def params_region(self) -> dict:
        return P.REGIONS[self.region]

    @property
    def part_sable(self) -> float:
        if self.part_sable_alentours is not None:
            return self.part_sable_alentours
        return self.params_fond["part_sable"]

    @property
    def visibilite_calme(self) -> float:
        if self.visibilite_calme_m is not None:
            return self.visibilite_calme_m
        return self.params_region["visibilite_calme_m"] * P.FACTEUR_CALME_FOND[self.fond]

    @property
    def sensibilite_maree_effective(self) -> float:
        if self.sensibilite_maree is not None:
            return self.sensibilite_maree
        return self.params_region["sensibilite_maree"]

    def vers_dict(self) -> dict:
        return asdict(self)


def charger_spots(chemin: str | Path) -> list[Spot]:
    """Lit une liste de spots depuis un fichier JSON."""
    donnees = json.loads(Path(chemin).read_text(encoding="utf-8"))
    return [Spot(**d) for d in donnees]
