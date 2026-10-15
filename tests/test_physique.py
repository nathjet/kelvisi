import numpy as np
import pytest

from prevision import physique, soleil
from datetime import datetime
from zoneinfo import ZoneInfo


@pytest.mark.parametrize("periode", [4, 8, 12, 18])
@pytest.mark.parametrize("profondeur", [2, 6, 15, 60])
def test_relation_de_dispersion(periode, profondeur):
    k = physique.nombre_onde(periode, profondeur)
    omega = 2 * np.pi / periode
    assert 9.81 * k * np.tanh(k * profondeur) == pytest.approx(omega**2, rel=1e-9)


def test_vitesse_au_fond_diminue_avec_la_profondeur():
    vitesses = [float(physique.vitesse_orbitale_fond(2.0, 10.0, h)) for h in (3, 6, 12, 30)]
    assert vitesses == sorted(vitesses, reverse=True)


def test_vitesse_au_fond_augmente_avec_hauteur_et_periode():
    assert physique.vitesse_orbitale_fond(2.0, 10.0, 8) > physique.vitesse_orbitale_fond(1.0, 10.0, 8)
    assert physique.vitesse_orbitale_fond(1.5, 14.0, 8) > physique.vitesse_orbitale_fond(1.5, 7.0, 8)


def test_vitesse_nulle_sans_vague_et_grand_fond():
    assert physique.vitesse_orbitale_fond(0.0, 10.0, 6) == 0.0
    assert physique.vitesse_orbitale_fond(np.nan, np.nan, 6) == 0.0
    assert physique.vitesse_orbitale_fond(1.0, 5.0, 200) < 1e-4


def test_deferlement_limite_la_hauteur():
    a = physique.vitesse_orbitale_fond(10.0, 10.0, 3)
    b = physique.vitesse_orbitale_fond(0.78 * 3, 10.0, 3)
    assert a == pytest.approx(b)


def test_exposition():
    assert physique.exposition(270, 270, 90) == pytest.approx(1.0)
    assert physique.exposition(90, 270, 90) == pytest.approx(0.1)
    assert physique.exposition(240, 270, 90) == pytest.approx(physique.exposition(300, 270, 90))
    assert 0.1 < physique.exposition(225, 270, 90) < 1.0
    assert physique.exposition(np.nan, 270, 90) == pytest.approx(0.1)


def test_vent_de_terre():
    assert physique.vent_de_terre(90, 270)       # vent d'est sur une côte tournée vers l'ouest
    assert not physique.vent_de_terre(260, 270)  # vent d'ouest : vent de mer


def test_lever_coucher_rennes():
    tz = ZoneInfo("Europe/Paris")
    debut = int(datetime(2026, 10, 14, tzinfo=tz).timestamp())
    lever, coucher = soleil.lever_coucher(48.11, -1.68, debut)
    lever_local = datetime.fromtimestamp(lever, tz)
    coucher_local = datetime.fromtimestamp(coucher, tz)
    # Calcul de référence : 08 h 25 et 19 h 20 (heure d'été)
    assert (lever_local.hour, lever_local.minute) in {(8, m) for m in range(20, 31)}
    assert (coucher_local.hour, coucher_local.minute) in {(19, m) for m in range(15, 26)}


def test_jours_plus_longs_en_ete():
    tz = ZoneInfo("Europe/Paris")
    def duree(mois, jour):
        debut = int(datetime(2026, mois, jour, tzinfo=tz).timestamp())
        lever, coucher = soleil.lever_coucher(47.9, -4.4, debut)
        return coucher - lever
    assert duree(6, 21) > duree(12, 21) + 6 * 3600
