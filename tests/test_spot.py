from pathlib import Path

import pytest

from prevision import charger_spots, parametres as P

from conftest import fabriquer_spot

RACINE = Path(__file__).resolve().parent.parent


def test_valeurs_par_defaut():
    spot = fabriquer_spot(region="mediterranee", fond="roche")
    assert spot.visibilite_calme == pytest.approx(P.REGIONS["mediterranee"]["visibilite_calme_m"] * P.FACTEUR_CALME_FOND["roche"])
    assert spot.sensibilite_houle == 1.0 and spot.satellite
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
    assert len(points) == 97
    assert len({p.id for p in points}) == len(points)
    assert {p.region for p in points} == {"manche", "atlantique", "mediterranee"}
    # Tous en France métropolitaine, Corse comprise
    assert all(41 < p.lat < 51.5 and -5.5 < p.lon < 9.7 for p in points)
    # Région cohérente avec celle que le navigateur déduit de la position (même règle que format.js)
    def region(lat, lon):
        if lon > 2.9 and lat < 43.95:
            return "mediterranee"
        return "manche" if lat >= 48.45 and lon > -4.78 else "atlantique"
    assert all(p.region == region(p.lat, p.lon) for p in points), [p.id for p in points if p.region != region(p.lat, p.lon)]
    # Deux points ne se recouvrent pas
    from prevision.spot import _distance_km
    proches = [(a.id, b.id) for i, a in enumerate(points) for b in points[i + 1:] if _distance_km(a, b) < 3]
    assert not proches, proches


def test_fichier_d_exemples():
    spots = charger_spots(RACINE / "spots" / "exemples.json")
    assert len(spots) == 3
    assert {s.fond for s in spots} == {"sable", "roche", "mixte"}


def test_point_non_cale_reprend_son_voisin():
    from prevision.spot import avec_reglage_voisin

    cale = fabriquer_spot(id="cale", lat=47.50, lon=-3.20, visibilite_calme_m=6.5, sensibilite_houle=0.5)
    proche = fabriquer_spot(id="proche", lat=47.60, lon=-3.25)
    loin = fabriquer_spot(id="loin", lat=48.40, lon=-3.20)
    autre_region = fabriquer_spot(id="mer", lat=47.55, lon=-3.22, region="manche")
    spots = [cale, proche, loin, autre_region]
    assert avec_reglage_voisin(proche, spots).visibilite_calme_m == 6.5
    assert avec_reglage_voisin(proche, spots).sensibilite_houle == 0.5
    assert avec_reglage_voisin(loin, spots) is loin, "trop loin : valeurs de la région"
    assert avec_reglage_voisin(autre_region, spots) is autre_region, "autre région"
    assert avec_reglage_voisin(cale, spots) is cale, "déjà calé"
