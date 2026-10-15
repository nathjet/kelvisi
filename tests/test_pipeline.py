import json
from datetime import datetime

import numpy as np
import pytest

from prevision import parametres as P, prevoir
from prevision.donnees import Conditions, Rapport
from prevision.pipeline import arrondir, classe
from prevision.simulation import calme, coup_de_houle

from conftest import fabriquer_spot


def test_sortie_json_complete(debut, spot_sable):
    p = prevoir(spot_sable, coup_de_houle(debut), debut + 86400, jours=3)
    texte = json.dumps(p, ensure_ascii=False)
    assert "NaN" not in texte
    assert len(p["jours"]) == 3
    assert len(p["heures"]) >= 48
    for jour in p["jours"]:
        assert jour["explication"]


def test_fourchette_et_arrondis(debut, spot_sable):
    p = prevoir(spot_sable, coup_de_houle(debut), debut + 86400, jours=3)
    for h in p["heures"]:
        bas, haut = h["fourchette_m"]
        assert bas <= h["visibilite_m"] <= haut
        assert (h["visibilite_m"] * 2) % 1 == 0
        assert 0 <= h["confiance"] <= 100


def test_la_confiance_baisse_avec_l_echeance(debut, spot_sable):
    p = prevoir(spot_sable, calme(debut, jours=6), debut + 86400, jours=3)
    assert p["heures"][0]["confiance"] > p["heures"][-1]["confiance"]


def test_creneaux_uniquement_de_jour(debut, spot_sable):
    p = prevoir(spot_sable, calme(debut, jours=6), debut + 86400, jours=3)
    for jour in p["jours"]:
        cr = jour["meilleur_creneau"]
        assert cr is not None
        assert datetime.fromisoformat(cr["debut"]) >= datetime.fromisoformat(jour["lever_soleil"])
        assert datetime.fromisoformat(cr["fin"]) <= datetime.fromisoformat(jour["coucher_soleil"])


def test_tempete_sortie_deconseillee(debut, spot_sable):
    p = prevoir(spot_sable, coup_de_houle(debut), debut + 86400, jours=3)
    jour_tempete = p["jours"][1]
    assert jour_tempete["alerte"] is not None
    assert jour_tempete["meilleur_creneau"] is None
    assert p["jours"][0]["alerte"] is None


def test_classes():
    spot = fabriquer_spot(region="atlantique")
    assert classe(1.0, spot) == "mauvaise"
    assert classe(3.0, spot) == "moyenne"
    assert classe(5.0, spot) == "bonne"
    assert classe(9.0, spot) == "excellente"
    med = fabriquer_spot(region="mediterranee")
    assert classe(5.0, med) == "moyenne"


def test_arrondir():
    assert arrondir(3.26) == 3.5
    assert arrondir(3.2) == 3.0
    assert arrondir(12.4) == 12.0


def test_maintenant_hors_donnees(debut, spot_sable):
    with pytest.raises(ValueError):
        prevoir(spot_sable, calme(debut, jours=2), debut + 5 * 86400)


def test_les_retours_terrain_corrigent_le_spot(debut, spot_sable):
    cond = calme(debut, jours=6)
    maintenant = debut + 3 * 86400
    sans = prevoir(spot_sable, cond, maintenant, jours=1)
    v0 = sans["heures"][12]["visibilite_m"]
    rapports = [
        Rapport(temps=maintenant - k * 3600 * 20, visibilite_m=1.5 * v0, utilisateur=f"u{k % 4}", prevision_m=v0)
        for k in range(1, 12)
    ]
    avec = prevoir(spot_sable, cond, maintenant, rapports=rapports, jours=1)
    assert avec["heures"][12]["visibilite_m"] > v0
    assert avec["calibrage"]["facteur"] > 1.2


def test_vent_de_terre_dans_la_sortie(debut, spot_sable):
    p = prevoir(spot_sable, calme(debut), debut + 86400, jours=1)
    assert p["heures"][0]["vent"]["de_terre"] is True  # vent d'est, côte tournée vers l'ouest


def test_donnees_manquantes_tolerees(debut, spot_sable):
    base = calme(debut)
    series = {k: v.copy() for k, v in base.series.items()}
    series["hauteur_vagues"][50:60] = np.nan
    series["nebulosite"][:] = np.nan
    p = prevoir(spot_sable, Conditions(temps=base.temps, series=series), debut + 86400, jours=2)
    assert all(h["visibilite_m"] > 0 for h in p["heures"])
    assert P.CLASSES  # sanity
