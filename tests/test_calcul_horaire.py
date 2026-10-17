"""Calcul horaire de tous les points (sans réseau : conditions simulées)."""

import json
import sys
from pathlib import Path

import pytest

RACINE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RACINE / "outils"))

from calculer_previsions import (  # noqa: E402
    ajouter_debits, completer_previsions, construire, ecrire, facade, lire_retours_supabase, parametres_publics, spots_a_valider,
)
from prevision import charger_spots  # noqa: E402
from prevision.donnees import Rapport  # noqa: E402
from prevision.simulation import coup_de_houle  # noqa: E402

DEBUT = 1_760_054_400


@pytest.fixture(scope="module")
def spots():
    return charger_spots(RACINE / "spots" / "points.json")[:6]


def test_construire_et_ecrire(tmp_path, spots):
    conditions = [coup_de_houle(DEBUT) for _ in spots]
    sorties = construire(spots, conditions, DEBUT + 86400)
    ecrire(tmp_path, sorties)
    resume = json.loads((tmp_path / "resume.json").read_text())
    assert len(resume["points"]) == len(spots)
    assert resume["erreurs"] == []
    point = resume["points"][0]
    assert {"id", "nom", "lat", "lon", "facade", "seuils", "jours", "retours"} <= set(point)
    assert len(point["jours"]) == 3
    detail = json.loads((tmp_path / "points" / f"{point['id']}.json").read_text())
    assert len(detail["heures"]) >= 48 and len(detail["historique"]) == 24
    parametres = json.loads((tmp_path / "parametres.json").read_text())
    assert parametres["CONSTANTE_VISIBILITE"] == 4.8 and "atlantique" in parametres["REGIONS"]


def test_un_point_en_erreur_n_empeche_pas_les_autres(spots):
    conditions = [coup_de_houle(DEBUT) for _ in spots]
    conditions[1] = coup_de_houle(DEBUT, jours=2)  # s'arrête avant l'heure demandée
    sorties = construire(spots, conditions, DEBUT + 4 * 86400)
    assert len(sorties["resume"]["erreurs"]) >= 1
    assert spots[1].id in {e["id"] for e in sorties["resume"]["erreurs"]}


def test_facade_corse():
    tous = charger_spots(RACINE / "spots" / "points.json")
    facades = {s.id: facade(s) for s in tous}
    assert facades["ref-centuri"] == "corse" and facades["ref-cap-antibes"] == "mediterranee"


def test_previsions_ajoutees_aux_retours(spots):
    cond = coup_de_houle(DEBUT)
    rapports = [Rapport(DEBUT + 30 * 3600, 3.0, "a"), Rapport(DEBUT - 86400 * 10, 3.0, "b")]
    complets = completer_previsions(spots[0], cond, rapports)
    assert complets[0].prevision_m is not None and complets[0].prevision_m > 0
    assert complets[1].prevision_m is None  # hors de la période connue


def test_parametres_publics_serialisables():
    json.dumps(parametres_publics())


def test_lecture_supabase():
    class Reponse:
        def raise_for_status(self):
            pass

        def json(self):
            return [
                {"spot_id": "ref-quiberon", "visibilite_m": 4, "prevision_m": None, "observe_le": "2026-10-14T10:00:00+00:00", "appareil": "x"},
                {"spot_id": "ref-quiberon", "visibilite_m": "oops", "observe_le": "2026-10-14T10:00:00+00:00"},
            ]

    class Session:
        def get(self, url, params, headers, timeout):
            assert url.endswith("/rest/v1/rapports") and headers["apikey"] == "cle"
            return Reponse()

    retours = lire_retours_supabase("https://exemple.supabase.co", "cle", 1_792_000_000, session=Session())
    assert len(retours["ref-quiberon"]) == 1


def test_spots_a_valider():
    class Reponse:
        def __init__(self, statut, plage=None):
            self.status_code = statut
            self.headers = {"Content-Range": plage} if plage else {}

        def raise_for_status(self):
            assert self.status_code < 400

    class Session:
        def __init__(self, reponse):
            self.reponse = reponse

        def get(self, url, params, headers, timeout):
            assert url.endswith("/rest/v1/spots_prives") and params["partage"] == "eq.en_attente"
            assert headers["Prefer"] == "count=exact"
            return self.reponse

    assert spots_a_valider("https://x.supabase.co", "sb_secret_x", session=Session(Reponse(206, "0-0/3"))) == 3
    assert spots_a_valider("https://x.supabase.co", "sb_secret_x", session=Session(Reponse(200, "*/0"))) == 0
    # Partage pas encore installé sur la base : rien à signaler
    assert spots_a_valider("https://x.supabase.co", "sb_secret_x", session=Session(Reponse(400))) is None


def test_rivieres_en_crue_et_station_en_panne():
    tous = charger_spots(RACINE / "spots" / "points.json")
    croisic = next(s for s in tous if s.id == "ref-le-croisic")
    assert {st.nom for st in croisic.stations} == {"Loire", "Vilaine"}
    from prevision.simulation import calme
    from prevision import modele
    import numpy as np

    sans = calme(DEBUT)
    avec = calme(DEBUT)
    appels = []

    def faux_telecharger(code, depuis):
        appels.append(code)
        if code == "J790061002":
            raise ConnectionError("Hub'Eau indisponible")
        temps = np.arange(depuis, depuis + 12 * 86400, 3600)
        return temps, np.full(len(temps), 4 * 497.1)  # Loire à quatre fois son débit habituel

    etat = ajouter_debits([croisic], [avec], telecharger=faux_telecharger)
    assert etat == {"J790061002": "ConnectionError", "M530001010": "ok"}
    assert appels.count("M530001010") == 1
    assert "M530001010" in avec.debits and "J790061002" not in avec.debits
    v_sans = modele.calculer(croisic, sans).visibilite_m
    v_avec = modele.calculer(croisic, avec).visibilite_m
    assert np.nanmean(v_avec[72:]) < 0.8 * np.nanmean(v_sans[72:])

    sorties = construire([croisic], [avec], DEBUT + 3 * 86400)
    loire = sorties["details"]["ref-le-croisic"]["rivieres"]
    assert loire == [{"nom": "Loire", "debit_m3s": 1988.4, "debit_habituel_m3s": 497.1, "rapport": 4.0,
                      "mesure_le": loire[0]["mesure_le"]}]
    point = sorties["resume"]["points"][0]
    assert point["rivieres"] == ["Loire", "Vilaine"]
    assert any("Loire" in j["explication"] for j in point["jours"])


def test_aucune_riviere():
    assert ajouter_debits([], []) == {}


def test_satellite_transmis(spots):
    from prevision.donnees import ObservationSatellite

    conditions = [coup_de_houle(DEBUT) for _ in spots[:2]]
    maintenant = DEBUT + 3 * 86400
    trouble = ObservationSatellite(temps=maintenant - 6 * 3600, turbidite_fnu=15.0)
    sorties = construire(spots[:2], conditions, maintenant, satellites={spots[0].id: trouble})
    a, b = sorties["resume"]["points"]
    assert a["satellite"]["utilise"] and not b["satellite"]["utilise"]
    assert "Copernicus Marine" in sorties["resume"]["sources"]


def test_entetes_supabase():
    from calculer_previsions import entetes_supabase

    assert entetes_supabase("sb_secret_abc") == {"apikey": "sb_secret_abc"}
    assert entetes_supabase("eyJhbGciOi.x.y")["Authorization"] == "Bearer eyJhbGciOi.x.y"
