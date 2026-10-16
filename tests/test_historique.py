"""Collecte de l'historique et chargement pour le calage (sans réseau : fichiers fabriqués)."""

import json
import sys
from datetime import date
from pathlib import Path

import numpy as np

RACINE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RACINE / "outils"))

from caler import charger_series, climatologie_plancton, erreur_climatologie  # noqa: E402
from historique import annees, poids_open_meteo, vers_series  # noqa: E402
from prevision.calage import separer  # noqa: E402
from prevision.spot import StationRiviere  # noqa: E402

from conftest import fabriquer_spot  # noqa: E402

T2025 = 1_735_689_600  # 1er janvier 2025, 0 h UTC


def test_tranches_annuelles():
    assert annees("2025-03-01", date(2026, 2, 10)) == [("2025", "2025-03-01", "2025-12-31"), ("2026", "2026-01-01", "2026-02-10")]


def test_poids_des_requetes_open_meteo():
    assert poids_open_meteo(8, 14, 1) == 1          # moins de 10 grandeurs, 2 semaines : un appel
    assert poids_open_meteo(15, 14, 1) == 1.5       # exemple de la documentation Open-Meteo
    assert round(poids_open_meteo(8, 365, 10)) == 261


def test_conversion_reponse_marine():
    rep = {"hourly": {"time": [T2025, T2025 + 3600], "ocean_current_velocity": [3.6, None], "swell_wave_height": [1.0, 1.2]}}
    t, s = vers_series(rep, {"ocean_current_velocity": "courant", "swell_wave_height": "hauteur_houle"})
    assert list(t) == [T2025, T2025 + 3600]
    assert s["courant"][0] == 1.0 and np.isnan(s["courant"][1])  # km/h vers m/s, valeur manquante conservée


def fabriquer_historique(dossier: Path, spot, jours=60):
    n = jours * 24
    temps = T2025 + 3600 * np.arange(n)
    h = np.arange(n)
    houle = 0.8 + 1.5 * (np.sin(h / 50.0) > 0.7)
    (dossier / "marine").mkdir(parents=True)
    (dossier / "pluie").mkdir()
    (dossier / "satellite").mkdir()
    (dossier / "debits").mkdir()
    # Deux fichiers annuels fictifs qui se suivent
    moitie = n // 2
    for k, (a, b) in enumerate([(0, moitie), (moitie, n)]):
        np.savez_compressed(dossier / "marine" / f"{spot.id}_{2025 + k}.npz", temps=temps[a:b],
                            hauteur_houle=houle[a:b].astype(np.float32), periode_houle=np.full(b - a, 11, np.float32),
                            direction_houle=np.full(b - a, 270, np.float32), hauteur_mer_vent=np.full(b - a, 0.3, np.float32),
                            periode_mer_vent=np.full(b - a, 4, np.float32), direction_mer_vent=np.full(b - a, 270, np.float32),
                            courant=np.full(b - a, 0.2, np.float32),
                            niveau_mer=(2 * np.cos(2 * np.pi * h[a:b] / 12.42)).astype(np.float32))
    np.savez_compressed(dossier / "pluie" / f"{spot.id}_2025.npz", temps=temps[: n - 48], pluie=np.zeros(n - 48, np.float32))
    obs = [[int(T2025 + d * 86400 + 37800), 1.0 + 0.1 * d, 0.5, 1.0] for d in range(jours)]
    (dossier / "satellite" / f"{spot.id}.json").write_text(json.dumps({"id": spot.id, "obs": obs}))
    (dossier / "debits" / "X1.json").write_text(json.dumps({"code": "X1", "jusqu_au": "2025-03-01",
                                                             "jours": [["2025-01-01", 10.0], ["2025-03-01", 70.0]]}))


def test_chargement_des_series(tmp_path):
    spot = fabriquer_spot(id="essai", stations=[StationRiviere(code="X1", debit_reference_m3s=20.0)])
    fabriquer_historique(tmp_path, spot)
    series, infos = charger_series(tmp_path, [spot, fabriquer_spot(id="sans-donnees")])
    assert len(series) == 1 and infos["sans-donnees"] == "données incomplètes"
    s = series[0]
    # Grille horaire continue, limitée à la période couverte par la marine ET la pluie
    assert np.all(np.diff(s.conditions.temps) == 3600)
    assert s.conditions.temps[-1] == T2025 + 3600 * (60 * 24 - 49)
    # Les images des 10 premiers jours (préchauffage du modèle) et celles hors période sont écartées
    assert min(o.temps for o in s.observations) >= T2025 + 10 * 86400
    assert max(o.temps for o in s.observations) <= s.conditions.temps[-1]
    # Débit journalier interpolé heure par heure
    q = s.conditions.debits["X1"]
    assert 10.0 < q[len(q) // 2] < 70.0
    assert infos["essai"]["maree_presente"] == 1.0


def test_references_et_plancton(tmp_path):
    spot = fabriquer_spot(id="essai")
    fabriquer_historique(tmp_path, spot)
    series, _ = charger_series(tmp_path, [spot])
    app, test = separer(series)
    assert erreur_climatologie(app, test) > 0
    plancton = climatologie_plancton(series)
    assert plancton["atlantique"][0]["chl_mediane"] == 0.5   # janvier : assez d'images
    assert plancton["atlantique"][5] is None                 # juin : aucune image


def test_appliquer_ecrit_les_valeurs(tmp_path):
    from types import SimpleNamespace

    from caler import appliquer

    racine = Path(__file__).resolve().parent.parent
    parametres = tmp_path / "parametres.py"
    parametres.write_text((racine / "prevision" / "parametres.py").read_text(encoding="utf-8"), encoding="utf-8")
    avant = {}
    exec(compile(parametres.read_text(encoding="utf-8"), str(parametres), "exec"), avant)
    points = tmp_path / "points.json"
    donnees = json.loads((racine / "spots" / "points.json").read_text(encoding="utf-8"))[:3]
    donnees[2]["visibilite_calme_m"] = 9.0  # valeur d'un ancien calage : retirée si le point n'est plus calé
    points.write_text(json.dumps(donnees, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    res = SimpleNamespace(
        reglages={"ALPHA_BRASSAGE": 0.00157, "FACTEUR_TAU": 1.41421, "GAMMA_FLUVIAL": 0.81255},
        saisons={"manche": {"amplitude": 0.487, "pic_jour": 363.4}, "atlantique": {"amplitude": 0.5, "pic_jour": 4.0},
                 "mediterranee": {"amplitude": 0.0, "pic_jour": 15.0}},
        visibilites_calmes={donnees[0]["id"]: 3.456}, sensibilites_houle={donnees[0]["id"]: 2.345},
    )
    appliquer(res, {"manche": {"calee": 2.9}, "mediterranee": {"calee": 12.1}}, "2025-01 à 2026-10", parametres, points)

    espace = {}
    exec(compile(parametres.read_text(encoding="utf-8"), str(parametres), "exec"), espace)
    assert espace["ALPHA_BRASSAGE"] == 0.00157 and espace["FACTEUR_TAU"] == 1.414
    assert abs(espace["GAMMA_FLUVIAL"] - 0.81255) < 1e-3
    assert espace["SAISON"]["manche"] == {"amplitude": 0.487, "pic_jour": 363.4}
    assert espace["REGIONS"]["manche"]["visibilite_calme_m"] == 2.9
    assert espace["REGIONS"]["atlantique"]["visibilite_calme_m"] == avant["REGIONS"]["atlantique"]["visibilite_calme_m"]  # inchangée
    assert espace["REGIONS"]["mediterranee"]["visibilite_calme_m"] == 12.1
    assert "Calé sur le satellite (2025-01 à 2026-10)" in parametres.read_text(encoding="utf-8")
    pts = json.loads(points.read_text(encoding="utf-8"))
    assert pts[0]["visibilite_calme_m"] == 3.5 and pts[0]["sensibilite_houle"] == 2.35
    assert "visibilite_calme_m" not in pts[2] and "sensibilite_houle" not in pts[1]
