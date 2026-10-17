"""Historique pour le calage : satellite, vagues, courant, marée, pluie et débits sur plusieurs années.

Lancé par le workflow « Calage » de GitHub Actions (ces services ne sont pas
joignables depuis l'espace de développement). Les fichiers sont rangés dans
historique/ et publiés sur la branche « historique ». Chaque lancement reprend
là où le précédent s'est arrêté : Open-Meteo limite le nombre d'appels par
jour, la collecte complète peut donc demander plusieurs lancements.

Usage :
  python outils/historique.py sonder
  python outils/historique.py collecter [--budget 4000] [--debut 2022-01-01]
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import numpy as np

RACINE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RACINE))

from prevision import charger_spots  # noqa: E402
from prevision.sources import copernicus, hubeau, openmeteo  # noqa: E402

DOSSIER = RACINE / "historique"
DEBUT = "2022-01-01"  # courants et marée Open-Meteo (SMOC) archivés depuis janvier 2022

URL_ARCHIVE_METEO = "https://archive-api.open-meteo.com/v1/archive"

# Seules les grandeurs utilisées par le calcul de la turbidité
VARIABLES_MARINE = {
    "swell_wave_height": "hauteur_houle", "swell_wave_period": "periode_houle", "swell_wave_direction": "direction_houle",
    "wind_wave_height": "hauteur_mer_vent", "wind_wave_period": "periode_mer_vent", "wind_wave_direction": "direction_mer_vent",
    "ocean_current_velocity": "courant", "sea_level_height_msl": "niveau_mer",
}  # 8 grandeurs : moins de 10, chaque tranche de 2 semaines compte pour un seul appel
VARIABLES_PLUIE = {"precipitation": "pluie"}
LOT = 10  # points par requête Open-Meteo


def annoter(titre: str, lignes) -> None:
    texte = "\n".join(str(x) for x in lignes)[:3800].replace("%", "%25").replace("\r", "").replace("\n", "%0A")
    print(f"::notice title={titre}::{texte}", flush=True)


def poids_open_meteo(n_variables: int, jours: int, n_points: int) -> float:
    """Nombre d'appels décomptés par Open-Meteo (au-delà de 10 variables ou de 2 semaines, appels fractionnaires)."""
    return max(1.0, n_variables / 10) * max(1.0, jours / 14) * n_points


def cle_open_meteo() -> str | None:
    return os.environ.get("OPEN_METEO_CLE") or None


def url_marine() -> str:
    return openmeteo.adresses(cle_open_meteo())[0]


def url_archive() -> str:
    return URL_ARCHIVE_METEO.replace("https://", "https://customer-") if cle_open_meteo() else URL_ARCHIVE_METEO


def requete_open_meteo(http, url: str, points, variables: dict, debut: str, fin: str, modele: str | None = None):
    """Une requête groupée ; retourne la liste des réponses (une par point)."""
    params = {
        "latitude": ",".join(f"{s.lat:.4f}" for s in points),
        "longitude": ",".join(f"{s.lon:.4f}" for s in points),
        "hourly": ",".join(variables), "timeformat": "unixtime", "timezone": "GMT",
        "start_date": debut, "end_date": fin,
    }
    if "marine" in url:
        params["cell_selection"] = "sea"
    if modele:
        params["models"] = modele
    if cle_open_meteo():
        params["apikey"] = cle_open_meteo()
    r = openmeteo._get_avec_reessais(http, url, params, essais=3)
    d = r.json()
    return d if isinstance(d, list) else [d]


def vers_series(reponse: dict, variables: dict) -> tuple[np.ndarray, dict]:
    temps = np.asarray(reponse["hourly"]["time"], dtype=np.int64)
    series = {}
    for nom_api, nom in variables.items():
        brut = reponse["hourly"].get(nom_api)
        if brut is None:
            continue
        v = np.array([np.nan if x is None else x for x in brut], dtype=np.float32)
        if nom == "courant":
            v = v / np.float32(3.6)  # km/h vers m/s
        series[nom] = v
    return temps, series


# --- Sonde : ce que chaque service fournit réellement ----------------------------------------


def sonder() -> None:
    import requests

    spots = charger_spots(RACINE / "spots" / "points.json")
    quiberon = next(s for s in spots if s.id == "ref-quiberon")
    lignes = [f"clé Open-Meteo commerciale : {'présente' if cle_open_meteo() else 'absente (limite gratuite : 10 000 appels par jour)'}"]
    http = requests.Session()

    for libelle, debut, fin, modele in [
        ("marine 2021-11", "2021-11-01", "2021-11-03", None),
        ("marine 2022-01", "2022-01-01", "2022-01-03", None),
        ("marine 2024-06", "2024-06-01", "2024-06-03", None),
        ("marine 2022-01 meteofrance", "2022-01-01", "2022-01-03", "meteofrance_wave,meteofrance_currents"),
    ]:
        try:
            rep = requete_open_meteo(http, url_marine(), [quiberon], VARIABLES_MARINE, debut, fin, modele)[0]
            t, s = vers_series(rep, VARIABLES_MARINE)
            remplis = {k: int(np.isfinite(v).sum()) for k, v in s.items()}
            lignes.append(f"{libelle} : {len(t)} h ; valeurs présentes {remplis} ; clés {sorted(rep.get('hourly', {}))[:14]}")
        except Exception as e:
            lignes.append(f"{libelle} : {type(e).__name__} {str(e)[:300]}")

    try:
        rep = requete_open_meteo(http, url_archive(), [quiberon], VARIABLES_PLUIE, "2022-01-01", "2022-01-31")[0]
        t, s = vers_series(rep, VARIABLES_PLUIE)
        lignes.append(f"pluie archive 2022-01 : {len(t)} h, cumul {np.nansum(s['pluie']):.0f} mm, manquants {int(np.isnan(s['pluie']).sum())}")
        fin = (date.today() - timedelta(days=3)).isoformat()
        rep = requete_open_meteo(http, url_archive(), [quiberon], VARIABLES_PLUIE, (date.today() - timedelta(days=12)).isoformat(), fin)[0]
        t, s = vers_series(rep, VARIABLES_PLUIE)
        lignes.append(f"pluie archive récente jusqu'au {fin} : {len(t)} h, manquants {int(np.isnan(s['pluie']).sum())}")
    except Exception as e:
        lignes.append(f"pluie archive : {type(e).__name__} {str(e)[:300]}")

    try:
        r = http.get(hubeau.URL_ELABOREES, params={
            "code_entite": "M530001010", "grandeur_hydro_elab": "QmnJ", "date_debut_obs_elab": "2022-01-01",
            "size": 20000, "fields": "date_obs_elab,resultat_obs_elab"}, timeout=60)
        d = r.json().get("data", [])
        lignes.append(f"Hub'Eau Loire débits journaliers depuis 2022 : HTTP {r.status_code}, {len(d)} jours, "
                      f"du {min(o['date_obs_elab'] for o in d)} au {max(o['date_obs_elab'] for o in d)}")
    except Exception as e:
        lignes.append(f"Hub'Eau : {type(e).__name__} {str(e)[:200]}")

    if copernicus.identifiants_presents():
        t0 = time.time()
        try:
            serie = satellite_du_point(quiberon, DEBUT, date.today().isoformat())
            lignes.append(f"satellite Quiberon depuis {DEBUT} : {len(serie)} jours exploitables en {time.time() - t0:.0f} s ; "
                          f"premiers {serie[:2]} ; derniers {serie[-2:]}")
        except Exception as e:
            lignes.append(f"satellite : {type(e).__name__} {str(e)[:300]}")
    annoter("Sonde historique", lignes)


# --- Satellite ----------------------------------------------------------------------------------


def satellite_du_point(spot, debut: str, fin: str) -> list[list]:
    """Toutes les images exploitables au point : [temps, turbidité FNU, chlorophylle, part de pixels valides]."""
    import copernicusmarine

    jeu = copernicus.JEUX[copernicus.bassin(spot)]
    m_lat, m_lon = copernicus.marges(spot)
    ds = copernicusmarine.open_dataset(
        dataset_id=jeu, variables=[copernicus.VARIABLE_TURBIDITE, copernicus.VARIABLE_CHL],
        minimum_longitude=spot.lon - m_lon, maximum_longitude=spot.lon + m_lon,
        minimum_latitude=spot.lat - m_lat, maximum_latitude=spot.lat + m_lat,
        start_datetime=f"{debut}T00:00:00", end_datetime=f"{fin}T23:59:59",
    )
    tur = ds[copernicus.VARIABLE_TURBIDITE].load()
    chl = ds[copernicus.VARIABLE_CHL].load()
    lats, lons = tur["latitude"].values, tur["longitude"].values
    d = copernicus.distances_m(spot.lat, spot.lon, lats, lons)
    proches = d <= copernicus.rayon(spot)
    temps = tur["time"].values.astype("datetime64[s]").astype(np.int64)
    sortie = []
    for k in range(len(temps)):
        obs = copernicus.extraire_au_spot(int(temps[k] - temps[k] % 86400 + copernicus.HEURE_PASSAGE_UTC * 3600),
                                          tur.values[k], chl.values[k], d, rayon_m=copernicus.rayon(spot))
        if obs is None:
            continue
        part = float(np.isfinite(tur.values[k][proches]).mean()) if proches.any() else 0.0
        sortie.append([obs.temps, round(obs.turbidite_fnu, 4),
                       None if obs.chlorophylle_mg_m3 is None else round(obs.chlorophylle_mg_m3, 4), round(part, 2)])
    return sortie


# --- Collecte ---------------------------------------------------------------------------------


def annees(debut: str, fin: date) -> list[tuple[str, str, str]]:
    """Tranches annuelles (étiquette, début, fin) de `debut` à `fin`."""
    d0 = date.fromisoformat(debut)
    tranches = []
    for a in range(d0.year, fin.year + 1):
        a_debut = max(d0, date(a, 1, 1))
        a_fin = min(fin, date(a, 12, 31))
        if a_debut <= a_fin:
            tranches.append((str(a), a_debut.isoformat(), a_fin.isoformat()))
    return tranches


def enregistrer_npz(chemin: Path, temps: np.ndarray, series: dict) -> None:
    chemin.parent.mkdir(parents=True, exist_ok=True)
    np.savez_compressed(chemin, temps=temps, **series)


def collecter(budget: float, debut: str, refaire_satellite: tuple[str, ...] = ()) -> None:
    import requests

    spots = charger_spots(RACINE / "spots" / "points.json")
    http = requests.Session()
    lignes = [f"clé Open-Meteo commerciale : {'présente' if cle_open_meteo() else 'absente'} ; budget de ce lancement {budget:.0f} appels"]
    fin_marine = date.today() - timedelta(days=2)
    fin_pluie = date.today() - timedelta(days=6)  # l'archive météo (ERA5) a quelques jours de retard
    depense = 0.0
    arret = None

    # 1. Débits journaliers (Hub'Eau, sans limite)
    codes = sorted({st.code for s in spots for st in s.stations})
    for code in codes:
        chemin = DOSSIER / "debits" / f"{code}.json"
        if chemin.exists() and json.loads(chemin.read_text())["jusqu_au"] >= (date.today() - timedelta(days=3)).isoformat():
            continue
        try:
            r = http.get(hubeau.URL_ELABOREES, params={
                "code_entite": code, "grandeur_hydro_elab": "QmnJ", "date_debut_obs_elab": debut,
                "size": 20000, "fields": "date_obs_elab,resultat_obs_elab"}, timeout=90)
            r.raise_for_status()
            jours = sorted((o["date_obs_elab"], o["resultat_obs_elab"] / 1000.0) for o in r.json().get("data", [])
                           if o.get("resultat_obs_elab") is not None)
            chemin.parent.mkdir(parents=True, exist_ok=True)
            chemin.write_text(json.dumps({"code": code, "jusqu_au": date.today().isoformat(), "jours": jours}))
            lignes.append(f"débits {code} : {len(jours)} jours")
        except Exception as e:
            lignes.append(f"débits {code} : {type(e).__name__} {str(e)[:150]}")

    # 2. Satellite (Copernicus Marine, sans limite d'appels)
    if copernicus.identifiants_presents():
        t0 = time.time()
        faits = 0
        for s in spots:
            chemin = DOSSIER / "satellite" / f"{s.id}.json"
            if chemin.exists() and s.id not in refaire_satellite:
                continue
            try:
                obs = satellite_du_point(s, debut, date.today().isoformat())
                chemin.parent.mkdir(parents=True, exist_ok=True)
                chemin.write_text(json.dumps({"id": s.id, "jeu": copernicus.JEUX[copernicus.bassin(s)], "obs": obs}))
                faits += 1
            except Exception as e:
                lignes.append(f"satellite {s.id} : {type(e).__name__} {str(e)[:150]}")
        lignes.append(f"satellite : {faits} points téléchargés en {time.time() - t0:.0f} s")

    # 3. Vagues, courant, marée et pluie (Open-Meteo, budget limité), des années récentes aux plus anciennes,
    #    pour que chaque lancement fournisse des années complètes utilisables tout de suite.
    sources = {"marine": (url_marine(), VARIABLES_MARINE, fin_marine), "pluie": (url_archive(), VARIABLES_PLUIE, fin_pluie)}
    taches = [(nom, etiquette, a_debut, a_fin)
              for etiquette, _, _ in reversed(annees(debut, fin_marine))
              for nom in sources
              for e2, a_debut, a_fin in annees(debut, sources[nom][2]) if e2 == etiquette]
    for nom, etiquette, a_debut, a_fin in taches:
        url, variables, _ = sources[nom]
        manquants = [s for s in spots if not (DOSSIER / nom / f"{s.id}_{etiquette}.npz").exists()]
        for k in range(0, len(manquants), LOT):
            lot = manquants[k:k + LOT]
            jours = (date.fromisoformat(a_fin) - date.fromisoformat(a_debut)).days + 1
            cout = poids_open_meteo(len(variables), jours, len(lot))
            if depense + cout > budget:
                arret = arret or f"budget atteint avant {nom} {etiquette}"
                break
            try:
                reponses = requete_open_meteo(http, url, lot, variables, a_debut, a_fin)
            except Exception as e:
                arret = f"{nom} {etiquette} : {type(e).__name__} {str(e)[:200]}"
                break
            depense += cout
            for s, rep in zip(lot, reponses):
                temps, series = vers_series(rep, variables)
                enregistrer_npz(DOSSIER / nom / f"{s.id}_{etiquette}.npz", temps, series)
            time.sleep(2.0)
        if arret:
            break

    attendus = {nom: len(spots) * len(annees(debut, fin)) for nom, fin in (("marine", fin_marine), ("pluie", fin_pluie))}
    presents = {nom: len(list((DOSSIER / nom).glob("*.npz"))) if (DOSSIER / nom).exists() else 0 for nom in attendus}
    complet = all(presents[n] >= attendus[n] for n in attendus) and len(list((DOSSIER / "satellite").glob("*.json"))) >= len(spots)
    lignes.append(f"appels Open-Meteo décomptés ce lancement : {depense:.0f}")
    lignes.append(f"fichiers : marine {presents['marine']}/{attendus['marine']}, pluie {presents['pluie']}/{attendus['pluie']}, "
                  f"satellite {len(list((DOSSIER / 'satellite').glob('*.json')))}/{len(spots)}")
    if arret:
        lignes.append(f"arrêt : {arret}")
    lignes.append("COLLECTE COMPLÈTE" if complet else "collecte incomplète : relancer plus tard")
    (DOSSIER / "etat.json").write_text(json.dumps({"complet": complet, "debut": debut, "maj": datetime.now(timezone.utc).isoformat(),
                                                  "presents": presents, "attendus": attendus}, indent=1))
    annoter("Collecte de l'historique", lignes)


def main():
    p = argparse.ArgumentParser()
    p.add_argument("etape", choices=["sonder", "collecter"])
    p.add_argument("--budget", type=float, default=4000)
    p.add_argument("--debut", default=DEBUT)
    p.add_argument("--refaire-satellite", default="", help="points dont les images sont à télécharger de nouveau (séparés par des virgules)")
    a = p.parse_args()
    DOSSIER.mkdir(exist_ok=True)
    if a.etape == "sonder":
        sonder()
    else:
        collecter(a.budget, a.debut, tuple(x for x in a.refaire_satellite.split(",") if x))


if __name__ == "__main__":
    main()
