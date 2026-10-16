import numpy as np
import pytest

from prevision import modele, parametres as P
from prevision.donnees import Conditions, ObservationSatellite
from prevision.simulation import calme, coup_de_houle

from conftest import fabriquer_spot


def vis(spot, cond, satellite=None):
    return modele.calculer(spot, cond, satellite).visibilite_m


def test_mer_calme_proche_de_la_visibilite_habituelle(debut):
    spot = fabriquer_spot(region="mediterranee", fond="roche", profondeur_m=10)
    v = vis(spot, calme(debut))
    assert v[48:].min() > 0.6 * spot.visibilite_calme
    assert v.max() <= P.REGIONS["mediterranee"]["visibilite_max_m"]


def test_la_tempete_trouble_l_eau(debut, spot_sable):
    v = vis(spot_sable, coup_de_houle(debut))
    assert v[66] < 0.5 * v[40]


def test_effet_retard_et_retour_au_calme(debut, spot_sable):
    cond = coup_de_houle(debut)
    v = vis(spot_sable, cond)
    # Houle retombée à 1,2 m mais eau encore chargée
    assert v[96] < 0.6 * v[40]
    # Retour progressif au calme, jour après jour
    moyennes = [v[a:a + 24].mean() for a in (120, 144, 168)]
    assert moyennes[0] < moyennes[1] < moyennes[2]


def test_le_sable_se_decante_plus_vite_que_la_vase(debut):
    cond = coup_de_houle(debut)
    sable = fabriquer_spot(fond="sable", visibilite_calme_m=8)
    vase = fabriquer_spot(fond="vase", visibilite_calme_m=8)
    assert vis(sable, cond)[150] > vis(vase, cond)[150]


def test_un_spot_profond_est_moins_touche(debut):
    cond = coup_de_houle(debut)
    peu_profond = fabriquer_spot(profondeur_m=4, part_sable_alentours=0.0)
    profond = fabriquer_spot(profondeur_m=15, part_sable_alentours=0.0)
    assert vis(profond, cond).min() > vis(peu_profond, cond).min()


def test_un_spot_abrite_est_moins_touche(debut):
    cond = coup_de_houle(debut, direction_houle=270)
    expose = fabriquer_spot(orientation_deg=270)
    abrite = fabriquer_spot(orientation_deg=90)
    assert vis(abrite, cond).min() > 2 * vis(expose, cond).min()


def test_crue_de_riviere_et_delai(debut):
    base = calme(debut, jours=6)
    debit = np.full(len(base), 10.0)
    debit[60:90] = 60.0
    cond = Conditions(temps=base.temps, series=dict(base.series), debits={"X001": debit})
    sans = fabriquer_spot(region="mediterranee")
    immediat = fabriquer_spot(region="mediterranee", stations=[{"code": "X001", "debit_reference_m3s": 10.0, "delai_h": 0}])
    retarde = fabriquer_spot(region="mediterranee", stations=[{"code": "X001", "debit_reference_m3s": 10.0, "delai_h": 24}])
    v_sans, v_imm, v_ret = vis(sans, cond), vis(immediat, cond), vis(retarde, cond)
    assert v_imm[80] < 0.8 * v_sans[80]
    assert v_ret[70] > v_imm[70]           # l'eau trouble n'est pas encore arrivée
    assert v_ret[100] < v_sans[100]        # puis elle arrive


def test_fortes_pluies(debut, spot_sable):
    base = calme(debut)
    pluie = np.zeros(len(base))
    pluie[40:50] = 4.0  # 40 mm en 10 h
    series = dict(base.series)
    series["pluie"] = pluie
    cond = Conditions(temps=base.temps, series=series)
    assert vis(spot_sable, cond)[55] < 0.97 * vis(spot_sable, base)[55]


def test_satellite_eau_trouble(debut, spot_sable):
    cond = calme(debut, jours=10)
    t_obs = int(cond.temps[48])
    res = modele.calculer(spot_sable, cond, ObservationSatellite(temps=t_obs, turbidite_fnu=5.0))
    attendu = P.CONSTANTE_VISIBILITE / (P.C_EAU + P.C_PAR_FNU * 5.0 + res.composantes["plancton"][48])
    assert res.satellite_utilise
    assert res.visibilite_m[48] == pytest.approx(attendu, rel=0.01)
    # L'image vieillit : son effet s'efface en quelques jours
    assert res.visibilite_m[48 + 7 * 24] > 2 * res.visibilite_m[48]


def test_satellite_eau_claire(debut, spot_sable):
    cond = coup_de_houle(debut)
    t_obs = int(cond.temps[100])
    avec = vis(spot_sable, cond, ObservationSatellite(temps=t_obs, turbidite_fnu=0.3))
    assert avec[100] > vis(spot_sable, cond)[100]


def test_image_satellite_trop_ancienne_ignoree(debut, spot_sable):
    cond = calme(debut)
    res = modele.calculer(spot_sable, cond, ObservationSatellite(temps=int(cond.temps[0]) - 10 * 86400, turbidite_fnu=5.0))
    assert not res.satellite_utilise


def test_chlorophylle_satellite_ignoree(debut, spot_sable):
    # Près des côtes, la chlorophylle satellite est faussée par les sédiments : elle ne change rien
    cond = calme(debut)
    t_obs = int(cond.temps[24])
    bloom = vis(spot_sable, cond, ObservationSatellite(temps=t_obs, chlorophylle_mg_m3=15.0))
    assert np.allclose(bloom, vis(spot_sable, cond))


def test_eaux_plus_chargees_en_hiver(spot_sable):
    from datetime import datetime, timezone

    saison = {**P.SAISON, "atlantique": {"amplitude": 0.5, "pic_jour": 15.0}}
    janvier = calme(int(datetime(2026, 1, 15, tzinfo=timezone.utc).timestamp()))
    juillet = calme(int(datetime(2026, 7, 16, tzinfo=timezone.utc).timestamp()))
    def fond(cond, reglages):
        return modele.calculer(spot_sable, cond, reglages=reglages).composantes["fond_habituel"]

    assert fond(janvier, {"SAISON": saison}).mean() == pytest.approx(np.exp(0.5) * fond(juillet, {"SAISON": saison}).mean() * np.exp(0.5), rel=0.01)
    # Amplitude nulle : aucun effet
    sans = {r: {"amplitude": 0.0, "pic_jour": 15.0} for r in P.SAISON}
    assert np.allclose(fond(janvier, {"SAISON": sans}), fond(juillet, {"SAISON": sans}))


def test_sensibilite_a_la_houle(debut):
    cond = coup_de_houle(debut)
    sensible = modele.calculer(fabriquer_spot(sensibilite_houle=3.0), cond).composantes["brassage"]
    abrite = modele.calculer(fabriquer_spot(sensibilite_houle=0.3), cond).composantes["brassage"]
    assert sensible.max() > 5 * abrite.max()


def test_mediterranee_sans_effet_de_maree(debut):
    cond = coup_de_houle(debut, marnage=0.3)
    spot = fabriquer_spot(region="mediterranee")
    res = modele.calculer(spot, cond)
    assert np.all(res.diagnostics["phase_maree"] == 0)


def test_maree_module_la_visibilite(debut, spot_sable):
    cond = coup_de_houle(debut, marnage=5.0)
    res = modele.calculer(spot_sable, cond)
    phase = res.diagnostics["phase_maree"]
    v = res.visibilite_m
    pm = (phase > 0.9) & (np.arange(len(v)) > 130)
    bm = (phase < -0.9) & (np.arange(len(v)) > 130)
    assert v[pm].mean() > v[bm].mean()


def test_hauteur_au_spot(debut):
    cond = coup_de_houle(debut, direction_houle=270)
    expose = modele.hauteur_au_spot(fabriquer_spot(orientation_deg=270), cond)
    abrite = modele.hauteur_au_spot(fabriquer_spot(orientation_deg=90), cond)
    assert expose[66] > 2.5
    assert abrite[66] < 0.5
