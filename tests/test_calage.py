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


# Constantes figées pendant ces tests, pour qu'ils ne dépendent pas du dernier calage réel
CONSTANTES_DU_TEST = {"POIDS_LITTORAL": 0.3, "C_BRASSAGE_MAX": 6.0, "DELTA_PLUIE": 0.35, "GAMMA_FLUVIAL": 0.6,
                      "EFFET_PHASE_MAREE": 0.25, "ALPHA_BRASSAGE": 0.003, "FACTEUR_TAU": 1.0,
                      "SAISON": {r: {"amplitude": 0.0, "pic_jour": 15.0} for r in ("manche", "atlantique", "mediterranee")}}


@pytest.fixture(scope="module", autouse=True)
def constantes_figees():
    from prevision import parametres as P

    with pytest.MonkeyPatch.context() as m:
        for nom, valeur in CONSTANTES_DU_TEST.items():
            m.setattr(P, nom, valeur)
        yield


@pytest.fixture(scope="module")
def resultat(constantes_figees):
    apprentissage, test = separer(series_simulees())
    return caler(apprentissage, test, saison=False)


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


def test_retrouve_la_sensibilite_a_la_houle():
    rng = np.random.default_rng(3)
    series = []
    for k, sensibilite in enumerate((0.5, 2.0)):
        spot = fabriquer_spot(id=f"s{k}", fond="sable", profondeur_m=6)
        cond = saison_agitee(DEBUT, jours=150, graine=k + 10)
        vraie = turbidite_modele(replace(spot, visibilite_calme_m=8.0, sensibilite_houle=sensibilite), cond)
        obs = [ObservationSatellite(int(cond.temps[i]), float(vraie[i] * rng.lognormal(0, 0.1)))
               for i in range(11, len(cond), 24) if rng.random() < 0.5]
        series.append(SerieCalage(spot, cond, obs))
    res = caler(series, parametres=("FACTEUR_TAU",), saison=False)
    assert res.sensibilites_houle["s1"] / res.sensibilites_houle["s0"] == pytest.approx(4.0, rel=0.3)
