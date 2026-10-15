"""Le moteur JavaScript (app/js/moteur/moteur.js) doit donner les mêmes prévisions que Python.

Le navigateur calcule lui-même les lieux recherchés et les spots privés : une
divergence entre les deux versions donnerait deux réponses différentes au même
endroit. Ce test compare toutes les sorties, champ par champ.
"""

import json
import shutil
import subprocess
from dataclasses import asdict
from pathlib import Path

import numpy as np
import pytest

from prevision import modele, prevoir
from prevision.donnees import Conditions, ObservationSatellite, Rapport
from prevision.simulation import calme, coup_de_houle, saison_agitee

from conftest import fabriquer_spot

RACINE = Path(__file__).resolve().parent.parent
FIXTURES = Path(__file__).resolve().parent / "fixtures"
NODE = shutil.which("node")

pytestmark = pytest.mark.skipif(NODE is None, reason="Node.js absent")


def dict_spot(spot) -> dict:
    d = asdict(spot)
    d.pop("stations")
    return d


def preparer_cas():
    sys_path_outils = RACINE / "outils"
    import sys
    sys.path.insert(0, str(sys_path_outils))
    from calculer_previsions import parametres_publics  # noqa: E402

    debut = 1_760_054_400  # 10 octobre 2025, 00:00 UTC
    cas = []

    def ajouter(nom, spot, cond: Conditions, maintenant, jours=3, satellite=None, rapports=()):
        cas.append({
            "nom": nom, "spot": dict_spot(spot), "conditions": cond.vers_dict(), "maintenant": maintenant,
            "jours": jours, "satellite": None if satellite is None else asdict(satellite),
            "rapports": [asdict(r) for r in rapports],
            "_objets": (spot, cond, satellite, list(rapports)),
        })

    ajouter("tempête, sable", fabriquer_spot(), coup_de_houle(debut), debut + 86400 + 1234)
    ajouter("tempête, roche profonde", fabriquer_spot(fond="roche", profondeur_m=14), coup_de_houle(debut), debut + 2 * 86400)
    ajouter("abri", fabriquer_spot(orientation_deg=100, ouverture_deg=50, fond="mixte"), coup_de_houle(debut), debut + 86400)
    ajouter("vase", fabriquer_spot(fond="vase", sensibilite_pluie=0.8), coup_de_houle(debut, pluie_totale_mm=40), debut + 86400)
    ajouter("méditerranée", fabriquer_spot(region="mediterranee", fond="herbier", orientation_deg=180),
            coup_de_houle(debut, marnage=0.3, direction_houle=160), debut + 86400)
    ajouter("manche, marée", fabriquer_spot(region="manche", sensibilite_maree=0.9), saison_agitee(debut, jours=12, graine=3, marnage=8), debut + 5 * 86400, jours=4)
    ajouter("calme", fabriquer_spot(), calme(debut, jours=6, marnage=3.0), debut + 2 * 86400)
    sat = ObservationSatellite(temps=debut + 86400 + 11 * 3600, turbidite_fnu=4.0, chlorophylle_mg_m3=3.0)
    ajouter("satellite", fabriquer_spot(), coup_de_houle(debut), debut + 2 * 86400, satellite=sat)
    rapports = [Rapport(debut + 86400 - k * 7200, visibilite_m=4.0 + (k % 3), utilisateur=f"u{k % 4}", prevision_m=3.0) for k in range(9)]
    ajouter("retours", fabriquer_spot(), coup_de_houle(debut), debut + 86400, rapports=rapports)

    for fichier, region, orientation, fond, prof in (
        ("quiberon", "atlantique", 260, "mixte", 6),
        ("granville", "manche", 270, "mixte", 6),
        ("centuri", "mediterranee", 270, "roche", 12),
    ):
        cond = Conditions.depuis_dict(json.loads((FIXTURES / f"conditions_reelles_{fichier}.json").read_text()))
        spot = fabriquer_spot(id=fichier, lat=cond.lat, lon=cond.lon, region=region, orientation_deg=orientation,
                              fond=fond, profondeur_m=prof)
        ajouter(f"réel {fichier}", spot, cond, int(cond.temps[5 * 24 + 7]) + 600)

    return {"parametres": parametres_publics(), "cas": cas}


def nettoyer(o):
    """Sortie Python au format JSON pour comparer (NaN exclus par construction)."""
    return json.loads(json.dumps(o, ensure_ascii=False))


@pytest.fixture(scope="module")
def resultats(tmp_path_factory):
    donnees = preparer_cas()
    objets = [c.pop("_objets") for c in donnees["cas"]]
    chemin = tmp_path_factory.mktemp("concordance") / "cas.json"
    chemin.write_text(json.dumps(donnees, ensure_ascii=False), encoding="utf-8")
    sortie = subprocess.run([NODE, str(RACINE / "tests" / "concordance.mjs"), str(chemin)],
                            capture_output=True, text=True, timeout=120)
    assert sortie.returncode == 0, sortie.stderr
    js = json.loads(sortie.stdout)
    return list(zip(donnees["cas"], objets, js))


def test_visibilite_brute_identique(resultats):
    for cas, (spot, cond, sat, _), js in resultats:
        py = modele.calculer(spot, cond, sat).visibilite_m
        assert np.allclose(py, js["visibilite_modele"], rtol=1e-9, atol=1e-12), cas["nom"]


def test_sortie_complete_identique(resultats):
    for cas, (spot, cond, sat, rapports), js in resultats:
        py = nettoyer(prevoir(spot, cond, cas["maintenant"], satellite=sat, rapports=rapports, jours=cas["jours"]))
        sortie_js = js["sortie"]
        sortie_js.pop("_brut")
        for cle in ("jours", "heures", "historique", "calibrage", "satellite", "spot", "genere_le", "version_modele"):
            assert sortie_js[cle] == py[cle], f"{cas['nom']} : écart sur « {cle} »"
