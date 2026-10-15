import pytest

from prevision.classement import classer, distance_km


def prevision(nom, lat, lon, visibilite, creneau=True):
    return {
        "spot": {"id": nom, "nom": nom, "lat": lat, "lon": lon},
        "jours": [{
            "visibilite_moyenne_m": visibilite,
            "classe": "bonne",
            "meilleur_creneau": {"visibilite_m": visibilite} if creneau else None,
            "alerte": None if creneau else "Sortie déconseillée : rafales jusqu'à 35 nœuds.",
        }],
    }


def test_distance_brest_rennes():
    assert distance_km(48.39, -4.49, 48.11, -1.68) == pytest.approx(210, abs=10)


def test_classement():
    previsions = [
        prevision("proche-trouble", 47.91, -4.40, 2.0),
        prevision("clair", 47.95, -4.45, 8.0),
        prevision("clair-mais-dangereux", 47.92, -4.41, 12.0, creneau=False),
        prevision("trop-loin", 43.3, 5.4, 20.0),
    ]
    resultat = classer(previsions, 47.9, -4.4, rayon_km=30)
    assert [r["spot"]["id"] for r in resultat] == ["clair", "proche-trouble", "clair-mais-dangereux"]
