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
