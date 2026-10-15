import pytest

from prevision.calibrage import calibrer, fiabilite_utilisateurs
from prevision.donnees import Rapport

MAINTENANT = 1_800_000_000


def rapports_coherents(n, rapport=2.0, age_jours=1.0):
    return [
        Rapport(temps=MAINTENANT - int(age_jours * 86400) - k * 3600, visibilite_m=4.0 * rapport,
                utilisateur=f"u{k}", prevision_m=4.0)
        for k in range(n)
    ]


def test_sans_rapport():
    c = calibrer([], MAINTENANT)
    assert c.facteur == 1.0 and c.nombre_effectif == 0.0


def test_prudence_avec_peu_de_rapports():
    peu = calibrer(rapports_coherents(2), MAINTENANT)
    beaucoup = calibrer(rapports_coherents(30), MAINTENANT)
    assert 1.0 < peu.facteur < beaucoup.facteur < 2.0
    assert beaucoup.facteur > 1.8


def test_les_vieux_rapports_comptent_moins():
    recents = calibrer(rapports_coherents(5, age_jours=1), MAINTENANT)
    anciens = calibrer(rapports_coherents(5, age_jours=120), MAINTENANT)
    assert recents.facteur > anciens.facteur > 1.0


def test_rapports_futurs_ignores():
    futurs = [Rapport(temps=MAINTENANT + 3600, visibilite_m=8, utilisateur="a", prevision_m=4)]
    assert calibrer(futurs, MAINTENANT).facteur == 1.0


def test_fiabilite_utilisateur_isole():
    t = MAINTENANT - 86400
    rapports = [
        Rapport(t, 6.0, "a"), Rapport(t + 600, 6.5, "b"), Rapport(t + 1200, 5.5, "c"),
        Rapport(t + 1800, 1.0, "menteur"),
    ]
    f = fiabilite_utilisateurs(rapports)
    assert f["menteur"] < 0.5 < f["a"]


def test_fiabilite_par_defaut_sans_voisin():
    f = fiabilite_utilisateurs([Rapport(MAINTENANT, 5.0, "seul")])
    assert f["seul"] == pytest.approx(0.7)
