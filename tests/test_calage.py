"""Le calage doit retrouver des réglages connus à partir d'observations simulées."""

from dataclasses import replace

import numpy as np
import pytest

from prevision import modele
from prevision.calage import SerieCalage, caler, separer, turbidite_modele
from prevision.donnees import ObservationSatellite
from prevision.simulation import calme, saison_agitee

from conftest import fabriquer_spot

DEBUT = 1_767_225_600  # 1er janvier 2026
VERITE = {"ALPHA_BRASSAGE": 0.006, "FACTEUR_TAU": 1.6}


def series_simulees():
    rng = np.random.default_rng(7)
    points = [
        (fabriquer_spot(id="sable", fond="sable", profondeur_m=6), 5.0),
        (fabriquer_spot(id="roche", fond="roche", profondeur_m=12), 12.0),
    ]
    series = []
    for k, (spot, calme_vrai) in enumerate(points):
        cond = saison_agitee(DEBUT, jours=150, graine=k + 1)
        vraie = turbidite_modele(replace(spot, visibilite_calme_m=calme_vrai), cond, VERITE)
        obs = [
            ObservationSatellite(int(cond.temps[i]), float(vraie[i] * rng.lognormal(0, 0.15)))
            for i in range(11, len(cond), 24)
            if rng.random() < 0.4  # 60 % des jours nuageux
        ]
        series.append(SerieCalage(spot, cond, obs))
    return series


@pytest.fixture(scope="module")
def resultat():
    apprentissage, test = separer(series_simulees())
    return caler(apprentissage, test)


def test_l_erreur_baisse_jusqu_au_bruit_de_mesure(resultat):
    assert resultat.erreur_finale < 0.22          # bruit simulé : 0,15
    assert resultat.erreur_test < 0.5 * resultat.erreur_test_initiale


def test_retrouve_le_temps_de_retour_au_calme(resultat):
    assert resultat.reglages["FACTEUR_TAU"] == pytest.approx(1.6, rel=0.3)


def test_retrouve_la_visibilite_calme_de_chaque_point(resultat):
    assert resultat.visibilites_calmes["sable"] == pytest.approx(5.0, rel=0.2)
    assert resultat.visibilites_calmes["roche"] == pytest.approx(12.0, rel=0.2)


def test_separation_dans_le_temps():
    series = series_simulees()
    app, test = separer(series, part_apprentissage=0.7)
    for a, t in zip(app, test):
        assert max(o.temps for o in a.observations) < min(o.temps for o in t.observations)


def test_sans_observation():
    spot = fabriquer_spot()
    with pytest.raises(ValueError):
        caler([SerieCalage(spot, calme(DEBUT), [])])


def test_reglage_inconnu_refuse():
    with pytest.raises(ValueError):
        modele.calculer(fabriquer_spot(), calme(DEBUT), reglages={"N_EXISTE_PAS": 1})
