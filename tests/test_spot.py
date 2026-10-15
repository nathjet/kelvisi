from pathlib import Path

import pytest

from prevision import charger_spots, parametres as P

from conftest import fabriquer_spot

RACINE = Path(__file__).resolve().parent.parent


def test_valeurs_par_defaut():
    spot = fabriquer_spot(region="mediterranee", fond="roche")
    assert spot.visibilite_calme == pytest.approx(20.0 * P.FACTEUR_CALME_FOND["roche"])
    assert spot.sensibilite_maree_effective == 0.0
    assert spot.part_sable == P.FONDS["roche"]["part_sable"]


def test_valeurs_imposees():
    spot = fabriquer_spot(visibilite_calme_m=5, sensibilite_maree=0.9, part_sable_alentours=0.2, orientation_deg=-90)
    assert spot.visibilite_calme == 5
    assert spot.sensibilite_maree_effective == 0.9
    assert spot.part_sable == 0.2
    assert spot.orientation_deg == 270


@pytest.mark.parametrize("modif", [
    {"region": "pacifique"}, {"fond": "corail"}, {"lat": 95}, {"profondeur_m": 0}, {"ouverture_deg": 0},
])
def test_valeurs_refusees(modif):
    with pytest.raises(ValueError):
        fabriquer_spot(**modif)


def test_points_publics():
    points = charger_spots(RACINE / "spots" / "points.json")
    assert len(points) == 46
    assert len({p.id for p in points}) == 46
    assert {p.region for p in points} == {"manche", "atlantique", "mediterranee"}
    # Tous en France métropolitaine, Corse comprise
    assert all(41 < p.lat < 51.5 and -5.5 < p.lon < 9.7 for p in points)


def test_fichier_d_exemples():
    spots = charger_spots(RACINE / "spots" / "exemples.json")
    assert len(spots) == 3
    assert {s.fond for s in spots} == {"sable", "roche", "mixte"}
