import numpy as np

from prevision import maree

PERIODE_H = 12.42


def serie(debut, jours=8, amplitude=2.0, modulation=0.3):
    h = np.arange(jours * 24, dtype=float)
    temps = debut + 3600 * np.arange(jours * 24)
    a = amplitude * (1 + modulation * np.cos(2 * np.pi * h / 354.0))
    return temps, a * np.cos(2 * np.pi * h / PERIODE_H)


def test_deux_pleines_mers_par_jour(debut):
    temps, niveau = serie(debut)
    ext = maree.extremes(temps, niveau)
    pm = [e for e in ext if e.type == "PM"]
    assert 14 <= len(pm) <= 16
    types = [e.type for e in ext]
    assert all(a != b for a, b in zip(types, types[1:]))  # alternance PM / BM


def test_heures_des_pleines_mers(debut):
    temps, niveau = serie(debut, modulation=0.0)
    ext = maree.extremes(temps, niveau)
    for e in ext:
        if e.type == "PM":
            h = (e.temps - debut) / 3600
            ecart = min(abs(h - k * PERIODE_H) for k in range(20))
            assert ecart < 0.25  # moins de 15 minutes


def test_phase(debut):
    temps, niveau = serie(debut, modulation=0.0)
    ext = maree.extremes(temps, niveau)
    phase = maree.phase(temps, ext)
    dedans = (temps > ext[0].temps) & (temps < ext[-1].temps)
    correlation = np.corrcoef(phase[dedans], niveau[dedans])[0, 1]
    assert correlation > 0.98
    assert phase.max() <= 1.0 and phase.min() >= -1.0


def test_vives_eaux_et_mortes_eaux(debut):
    temps, niveau = serie(debut, jours=15)
    ext = maree.extremes(temps, niveau)
    rapport = maree.rapport_marnage(temps, ext)
    assert rapport[:24].mean() > 1.1     # début de série : vives-eaux
    assert rapport[160:200].mean() < 0.9  # une semaine plus tard : mortes-eaux


def test_marnage_faible_ignore(debut):
    temps, niveau = serie(debut, amplitude=0.1)
    ext = maree.extremes(temps, niveau)
    assert np.all(maree.rapport_marnage(temps, ext) == 1.0)


def test_serie_vide_ou_trouee(debut):
    temps = debut + 3600 * np.arange(48)
    assert maree.extremes(temps, np.full(48, np.nan)) == []
    _, niveau = serie(debut, jours=2)
    niveau[10:14] = np.nan
    assert len(maree.extremes(temps, niveau)) >= 6
