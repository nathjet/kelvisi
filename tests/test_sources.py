from datetime import datetime

import numpy as np
import pytest

from prevision.sources import copernicus, hubeau, openmeteo

T0 = 1_791_590_400  # heure ronde


def reponse_marine(n=4, decalage=0):
    temps = [T0 + 3600 * (k + decalage) for k in range(n)]
    return {
        "latitude": 47.9, "longitude": -4.4,
        "hourly": {
            "time": temps,
            "wave_height": [1.0, 1.2, None, 1.5][:n],
            "wave_period": [8, 9, 9, 10][:n],
            "wave_direction": [270] * n,
            "ocean_current_velocity": [3.6, 7.2, 0.0, 1.8][:n],
            "ocean_current_direction": [0] * n,
            "sea_level_height_msl": [0.5, 1.0, 1.2, 0.8][:n],
            "sea_surface_temperature": [15.0] * n,
        },
    }


def reponse_meteo(n=4, decalage=0):
    temps = [T0 + 3600 * (k + decalage) for k in range(n)]
    return {
        "hourly": {
            "time": temps,
            "wind_speed_10m": [36.0, 18.0, 0.0, 9.0][:n],
            "wind_direction_10m": [90] * n,
            "wind_gusts_10m": [50.0] * n,
            "precipitation": [0.0, 1.0, 0.0, 0.2][:n],
            "cloud_cover": [10, 50, 100, 0][:n],
        },
    }


def test_conversion_open_meteo():
    c = openmeteo.convertir(reponse_marine(), reponse_meteo())
    assert len(c) == 4
    assert c["courant"][1] == pytest.approx(2.0)   # 7,2 km/h = 2 m/s
    assert c["vent"][0] == pytest.approx(10.0)     # 36 km/h = 10 m/s
    assert np.isnan(c["hauteur_vagues"][2])         # valeur manquante
    assert np.all(np.isnan(c["hauteur_houle"]))      # variable absente
    assert c.lat == 47.9


def test_alignement_des_deux_api():
    c = openmeteo.convertir(reponse_marine(n=4), reponse_meteo(n=4, decalage=1))
    assert len(c) == 3
    assert c.temps[0] == T0 + 3600
    assert c["pluie"][0] == 0.0 and c["hauteur_vagues"][0] == 1.2


def test_parametres_open_meteo():
    marine, meteo = openmeteo.parametres_requetes(47.9, -4.4, jours_passes=5, jours_prevision=7, cle="secret")
    assert "sea_level_height_msl" in marine["hourly"] and marine["cell_selection"] == "sea"
    assert "wind_gusts_10m" in meteo["hourly"]
    assert marine["past_days"] == 5 and meteo["timeformat"] == "unixtime"
    assert marine["apikey"] == "secret"


def test_conversion_hubeau():
    reponse = {"data": [
        {"date_obs": "2026-10-14T12:00:00Z", "resultat_obs": 25000.0},
        {"date_obs": "2026-10-14T10:00:00Z", "resultat_obs": 20000.0},
        {"date_obs": None, "resultat_obs": 1.0},
    ]}
    temps, debits = hubeau.convertir(reponse)
    assert list(debits) == [20.0, 25.0]
    assert temps[1] - temps[0] == 7200


def test_hubeau_sur_grille():
    temps = np.array([T0, T0 + 7200])
    grille = T0 - 3600 + 3600 * np.arange(5)
    valeurs = hubeau.sur_grille_horaire(temps, np.array([10.0, 20.0]), grille)
    assert np.isnan(valeurs[0]) and np.isnan(valeurs[4])
    assert valeurs[2] == pytest.approx(15.0)


def test_extraction_satellite():
    distances = np.array([50.0, 100.0, 200.0, 250.0, 2000.0])
    turbidite = np.array([2.0, 3.0, np.nan, 4.0, 50.0])
    chl = np.array([1.0, 2.0, 3.0, np.nan, 9.0])
    obs = copernicus.extraire_au_spot(T0, turbidite, chl, distances)
    assert obs.turbidite_fnu == pytest.approx(3.0)
    assert obs.chlorophylle_mg_m3 == pytest.approx(2.0)


def test_extraction_satellite_nuageuse():
    distances = np.array([50.0, 100.0, 200.0, 250.0])
    turbidite = np.array([np.nan, np.nan, np.nan, 4.0])
    assert copernicus.extraire_au_spot(T0, turbidite, None, distances) is None


def test_satellite_via_jeux_simules(monkeypatch):
    """Chaîne complète du satellite avec des jeux de données factices au format des produits HR."""
    xr = pytest.importorskip("xarray")
    from prevision import charger_spots
    from pathlib import Path

    spots = charger_spots(Path(__file__).resolve().parent.parent / "spots" / "points.json")
    groix = next(s for s in spots if s.id == "ref-groix")
    sete = next(s for s in spots if s.id == "ref-sete")
    ouessant = next(s for s in spots if s.id == "ref-ouessant")
    assert (copernicus.bassin(groix), copernicus.bassin(ouessant), copernicus.bassin(sete)) == ("ibi", "nws", "med")
    jours = np.array(["2026-10-12", "2026-10-13", "2026-10-14"], dtype="datetime64[ns]")
    demandes = []

    def ouvrir(dataset_id, variables, groupe, debut, fin):
        demandes.append((dataset_id, tuple(variables), tuple(s.id for s in groupe)))
        if "_med_" in dataset_id:
            raise ConnectionError("bassin indisponible")
        lats = np.arange(groix.lat - 0.01, groix.lat + 0.01001, 0.000926)[::-1]  # latitudes décroissantes, comme les produits L3
        lons = np.arange(groix.lon - 0.01, groix.lon + 0.01001, 0.00132)
        forme = (3, len(lats), len(lons))
        tur, chl = np.full(forme, 2.0), np.full(forme, 0.5)
        tur[2] = chl[2] = np.nan  # dernier jour couvert de nuages
        tur[1] *= 3
        chl[1] *= 3
        coords = {"time": jours, "latitude": lats, "longitude": lons}
        return xr.Dataset({"TUR": (("time", "latitude", "longitude"), tur), "CHL": (("time", "latitude", "longitude"), chl)}, coords=coords)

    glenan = next(s for s in spots if s.id == "ref-glenan")
    assert not glenan.satellite, "fond clair peu profond : satellite écarté"
    sat = copernicus.recuperer([groix, sete, ouessant, glenan], 1_791_590_400, ouvrir=ouvrir)
    assert all("ref-glenan" not in g for _, _, g in demandes), "les Glénan ne sont pas demandées au satellite"
    assert "ref-groix" in sat["observations"] and "med" in sat["erreurs"]
    assert "ref-ouessant" not in sat["observations"], "aucun pixel autour d'Ouessant dans l'image factice"
    obs = sat["observations"]["ref-groix"]
    assert obs.turbidite_fnu == pytest.approx(6.0) and obs.chlorophylle_mg_m3 == pytest.approx(1.5)
    assert obs.temps % 86400 == 10.5 * 3600 and obs.temps // 86400 == np.datetime64("2026-10-13", "D").astype(int)
    assert all(v == ("TUR", "CHL") for _, v, _ in demandes), "turbidité et chlorophylle lues ensemble"
    assert {d for d, _, _ in demandes} == set(copernicus.JEUX.values())


def test_satellite_desactive_sans_identifiants(monkeypatch):
    monkeypatch.delenv("COPERNICUSMARINE_SERVICE_USERNAME", raising=False)
    assert not copernicus.identifiants_presents()


def test_adresses_open_meteo():
    assert openmeteo.adresses(None)[0] == "https://marine-api.open-meteo.com/v1/marine"
    marine, meteo = openmeteo.adresses("cle-secrete")
    assert marine == "https://customer-marine-api.open-meteo.com/v1/marine"
    assert meteo == "https://customer-api.open-meteo.com/v1/forecast"


def test_rayon_satellite_elargi_pour_un_point_pres_des_terres():
    from dataclasses import replace

    from conftest import fabriquer_spot

    spot = fabriquer_spot(lat=47.34, lon=-3.25)
    lats = np.arange(spot.lat - 0.012, spot.lat + 0.0121, 0.000926)
    lons = np.arange(spot.lon - 0.015, spot.lon + 0.0151, 0.00132)
    d = copernicus.distances_m(spot.lat, spot.lon, lats, lons)
    tur = np.where(d > 350, 1.5, np.nan)[None, :, :]  # terres (pas de valeur) jusqu'à 350 m du point
    jours = np.array([T0 - T0 % 86400])
    assert copernicus.derniere_observation(spot, jours, lats, lons, tur, None) is None
    large = replace(spot, rayon_satellite_m=800)
    obs = copernicus.derniere_observation(large, jours, lats, lons, tur, None)
    assert obs is not None and obs.turbidite_fnu == pytest.approx(1.5)
    m_lat, m_lon = copernicus.marges(large)
    assert m_lat * 111_320 > 800 and m_lon * 111_320 * np.cos(np.radians(spot.lat)) > 800


# --- Température en profondeur (modèles physiques Copernicus) ---------------------------------

def _colonne_factice(lat0, lon0, pas=0.027):
    """Grille autour d'un point : la côte à l'ouest (pas d'eau), des mailles de plus en plus profondes vers l'est."""
    lats = np.arange(lat0 - 0.2, lat0 + 0.2001, pas)
    lons = np.arange(lon0 - 0.2, lon0 + 0.2001, pas)
    profs = np.array([0.5, 1.5, 2.6, 3.8, 5.1, 6.4, 7.9, 9.6, 11.4, 13.5, 15.8, 18.5, 21.6, 25.2, 29.4, 34.4, 40.3])
    fond = np.clip((lons - lon0) * 250 + 6, -1, 60)  # 6 m au droit du point, plus profond vers l'est
    v = np.full((2, len(profs), len(lats), len(lons)), np.nan)
    for k, p in enumerate(profs):
        for j, f in enumerate(fond):
            if p <= f:
                v[0, k, :, j] = 15.0 - 0.1 * p
                v[1, k, :, j] = 14.0 - 0.1 * p
    return lats, lons, profs, v


def test_profil_composite_va_chercher_la_profondeur_au_large():
    from prevision.sources import temperature

    lats, lons, profs, v = _colonne_factice(47.5, -3.2)
    p = temperature.profil_composite(47.5, -3.2, lats, lons, profs, v)
    assert p["profondeurs"][0] == 0.5 and p["profondeurs"][-1] == 34.4, "40 m n'est atteint qu'au-delà de 10 km"
    assert p["valeurs"][0][0] == pytest.approx(14.95, abs=0.06) and p["valeurs"][1][-1] == pytest.approx(10.6, abs=0.06)
    assert p["distance_km"] < 2.1
    t, lu = temperature.valeur_a(p["profondeurs"], p["valeurs"][0], 12)
    assert lu == 12 and t == pytest.approx(13.8, abs=0.06)
    t, lu = temperature.valeur_a(p["profondeurs"], p["valeurs"][0], 60)
    assert lu == 34.4, "au-delà du profil, on garde le niveau le plus profond"
    assert temperature.valeur_a([1.0, 3.2], [20.0, 19.0], 0.2) == (20.0, 1.0)


def test_profil_composite_sans_eau_proche():
    from prevision.sources import temperature

    lats, lons, profs, v = _colonne_factice(47.5, -3.2)
    assert temperature.profil_composite(47.5, -4.0, lats, lons, profs, v) is None


def test_temperatures_via_jeux_simules():
    xr = pytest.importorskip("xarray")
    from conftest import fabriquer_spot
    from prevision.sources import temperature

    groix = fabriquer_spot(id="groix", lat=47.62, lon=-3.45, profondeur_m=12)
    sete = fabriquer_spot(id="sete", lat=43.39, lon=3.70, region="mediterranee")
    demandes = []

    def ouvrir(jeu, groupe, debut, fin):
        demandes.append((jeu, tuple(s.id for s in groupe), debut, fin))
        if "med" in jeu:
            raise ConnectionError("bassin indisponible")
        lats, lons, profs, v = _colonne_factice(groix.lat, groix.lon)
        coords = {"time": np.array(["2026-10-25", "2026-10-26"], dtype="datetime64[ns]"), "depth": profs,
                  "latitude": lats[::-1], "longitude": lons}
        return xr.Dataset({"thetao": (("time", "depth", "latitude", "longitude"), v[:, :, ::-1, :])}, coords=coords)

    res = temperature.recuperer([groix, sete], 1_792_900_000, jours=4, ouvrir=ouvrir)
    assert set(res["points"]) == {"groix"} and "med" in res["erreurs"]
    p = res["points"]["groix"]
    assert p["dates"] == ["2026-10-25", "2026-10-26"] and p["profondeur_m"] == 12
    assert p["au_fond"] == [pytest.approx(13.8, abs=0.06), pytest.approx(12.8, abs=0.06)]
    assert demandes[0][2:] == ("2026-10-25T00:00:00", "2026-10-28T00:00:00")
    assert {d[0] for d in demandes} == set(temperature.JEUX.values())


def test_temperatures_reprises_si_recentes():
    from prevision.sources import temperature

    precedent = {"genere_le": "2026-10-25T06:00:00+00:00", "points": {"a": {}, "b": {}}}
    t = int(datetime.fromisoformat("2026-10-25T09:00:00+00:00").timestamp())
    assert temperature.encore_valable(precedent, {"a", "b"}, t, 6 * 3600)
    assert not temperature.encore_valable(precedent, {"a", "b", "c"}, t, 6 * 3600), "un point nouveau oblige à recalculer"
    assert not temperature.encore_valable(precedent, {"a"}, t + 4 * 3600, 6 * 3600)
    assert not temperature.encore_valable(None, {"a"}, t, 6 * 3600)
    assert not temperature.encore_valable({"points": {"a": {}}}, {"a"}, t, 6 * 3600)
    partiel = {**precedent, "complet": False}
    assert not temperature.encore_valable(partiel, {"a"}, t, 6 * 3600), "un bassin était en panne : on réessaie"
    assert temperature.encore_valable(partiel, set(), t, 48 * 3600, complet=False), "mais il sert de secours"
