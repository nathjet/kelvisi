"""Calage du modèle sur l'historique satellite (dossier historique/, voir outils/historique.py).

Pour chaque point de référence, le modèle recalcule la turbidité heure par heure
avec la météo marine de l'époque, sans satellite, et on la compare aux images
satellite des mêmes jours. Le calage ajuste les constantes « À CALER » et la
visibilité habituelle de chaque point sur la première partie de l'historique,
puis vérifie le résultat sur la dernière partie, jamais vue pendant le calage.

Usage : python outils/caler.py [--historique historique] [--sortie calage/resultat.json]
"""

from __future__ import annotations

import argparse
import json
import math
import sys
import time
from collections import defaultdict
from dataclasses import replace
from datetime import date, datetime, timezone
from pathlib import Path

import numpy as np

RACINE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RACINE))

from prevision import charger_spots, parametres as P  # noqa: E402
from prevision import modele  # noqa: E402
from prevision.calage import (BORNES, BORNES_VISIBILITE_CALME, DECALAGE_FNU, GRILLE_FOND_FNU, SANS_SAISON,  # noqa: E402
                              SerieCalage, _indices_observations, _neutre, caler, composantes_turbidite,
                              en_pourcentage, fond_vers_visibilite, separer, turbidite_modele, visibilite_vers_fond)
from prevision.donnees import Conditions, ObservationSatellite  # noqa: E402

PRECHAUFFAGE_H = 10 * 24  # le modèle a de la mémoire : on ignore les images des 10 premiers jours


def _concatener(fichiers: list[Path]) -> tuple[np.ndarray, dict[str, np.ndarray]]:
    temps, series = [], defaultdict(list)
    for f in sorted(fichiers):
        d = np.load(f)
        temps.append(d["temps"])
        for k in d.files:
            if k != "temps":
                series[k].append(d[k].astype(float))
    if not temps:
        return np.array([], dtype=np.int64), {}
    t = np.concatenate(temps).astype(np.int64)
    ordre = np.argsort(t)
    return t[ordre], {k: np.concatenate(v)[ordre] for k, v in series.items()}


def _sur_grille(grille: np.ndarray, temps: np.ndarray, valeurs: np.ndarray) -> np.ndarray:
    sortie = np.full(len(grille), np.nan)
    i = np.searchsorted(grille, temps)
    ok = (i < len(grille)) & (grille[np.minimum(i, len(grille) - 1)] == temps)
    sortie[i[ok]] = valeurs[ok]
    return sortie


def charger_debits(dossier: Path) -> dict[str, tuple[np.ndarray, np.ndarray]]:
    """Débits moyens journaliers, placés à midi UTC de chaque jour."""
    debits = {}
    for f in (dossier / "debits").glob("*.json"):
        d = json.loads(f.read_text())
        if not d["jours"]:
            continue
        t = np.array([int(datetime.fromisoformat(j[:10]).replace(tzinfo=timezone.utc).timestamp()) + 12 * 3600
                      for j, _ in d["jours"]], dtype=np.int64)
        q = np.array([v for _, v in d["jours"]], dtype=float)
        debits[d["code"]] = (t, q)
    return debits


def charger_series(dossier: Path, spots) -> tuple[list[SerieCalage], dict]:
    """Une série de calage par point ayant de la météo et des images satellite."""
    debits = charger_debits(dossier)
    series, infos = [], {}
    for spot in spots:
        t_m, marine = _concatener(list((dossier / "marine").glob(f"{spot.id}_*.npz")))
        t_p, pluie = _concatener(list((dossier / "pluie").glob(f"{spot.id}_*.npz")))
        f_sat = dossier / "satellite" / f"{spot.id}.json"
        if not spot.satellite:
            infos[spot.id] = "satellite écarté : fond clair peu profond"
            continue
        if len(t_m) == 0 or len(t_p) == 0 or not f_sat.exists():
            infos[spot.id] = "données incomplètes"
            continue
        debut, fin = max(t_m[0], t_p[0]), min(t_m[-1], t_p[-1])
        grille = np.arange(debut, fin + 1, 3600, dtype=np.int64)
        valeurs = {k: _sur_grille(grille, t_m, v) for k, v in marine.items()}
        valeurs["pluie"] = _sur_grille(grille, t_p, pluie["pluie"])
        debits_horaires = {}
        for st in spot.stations:
            if st.code in debits:
                t_q, q = debits[st.code]
                h = np.interp(grille, t_q, q, left=np.nan, right=np.nan)
                debits_horaires[st.code] = h
        cond = Conditions(temps=grille, series=valeurs, debits=debits_horaires, lat=spot.lat, lon=spot.lon)
        niveau = valeurs.get("niveau_mer", np.full(len(grille), np.nan))
        # Pendant un trou dans le niveau de la mer, la phase de la marée serait inventée : images écartées
        trou_maree = ~np.isfinite(niveau) if np.isfinite(niveau).any() else np.zeros(len(grille), dtype=bool)
        brutes = json.loads(f_sat.read_text())["obs"]
        obs = [ObservationSatellite(int(t), float(tur), None if chl is None else float(chl))
               for t, tur, chl, _ in brutes
               if grille[0] + PRECHAUFFAGE_H * 3600 <= t <= grille[-1] and tur is not None and np.isfinite(tur)
               and not trou_maree[min(int((t - grille[0]) // 3600), len(grille) - 1)]]
        infos[spot.id] = {
            "heures": len(grille), "du": _jour(grille[0]), "au": _jour(grille[-1]), "images": len(obs),
            "maree_presente": round(float(np.isfinite(niveau).mean()), 3),
            "vagues_presentes": round(float(np.isfinite(valeurs.get("hauteur_houle", niveau * np.nan)).mean()), 3),
        }
        if obs:
            series.append(SerieCalage(spot, cond, obs))
    return series, infos


def _jour(t: int) -> str:
    return datetime.fromtimestamp(int(t), timezone.utc).date().isoformat()


def erreur_climatologie(apprentissage: list[SerieCalage], test: list[SerieCalage]) -> float:
    """Référence naïve : chaque point prévu à sa turbidité médiane, sans tenir compte de la météo."""
    ecarts = []
    for a, t in zip(apprentissage, test):
        if not a.observations or not t.observations:
            continue
        mediane = float(np.median([o.turbidite_fnu for o in a.observations]))
        v = np.array([o.turbidite_fnu for o in t.observations])
        ecarts.append(np.log(mediane + DECALAGE_FNU) - np.log(v + DECALAGE_FNU))
    tous = np.concatenate(ecarts)
    return float(np.sqrt(np.mean(tous**2)))


def evaluation_operationnelle(series: list[SerieCalage], test: list[SerieCalage], reglages: dict,
                              calmes: dict, houles: dict, taus=(48.0, 72.0, 120.0)) -> dict:
    """Erreur des prévisions telles que l'application les fait, sur la période de test.

    Pour chaque image de test, on se place juste avant : la dernière image connue
    date de 12 h à 7 jours. On compare :
      - persistance : on suppose l'eau identique à la dernière image ;
      - modèle seul : sans satellite ;
      - modèle recalé sur la dernière image, correction additive (formule actuelle)
        ou multiplicative, avec un poids qui décroît selon TAU (h).
    """
    ecarts = defaultdict(list)
    for s_app, s_test in zip(series, test):
        if s_app.spot.id not in calmes or not s_test.observations:
            continue
        spot = replace(s_app.spot, visibilite_calme_m=calmes[s_app.spot.id], sensibilite_houle=houles[s_app.spot.id])
        tur = turbidite_modele(spot, s_app.conditions, reglages)
        t = s_app.conditions.temps
        toutes = sorted(s_app.observations + s_test.observations, key=lambda o: o.temps)
        temps_obs = np.array([o.temps for o in toutes])
        for o in s_test.observations:
            avant = np.where((temps_obs <= o.temps - 12 * 3600) & (temps_obs >= o.temps - 7 * 86400))[0]
            if not len(avant):
                continue
            prec = toutes[int(avant[-1])]
            age_h = (o.temps - prec.temps) / 3600.0
            i_now = int(np.argmin(np.abs(t - o.temps)))
            i_prec = int(np.argmin(np.abs(t - prec.temps)))
            vu = math.log(o.turbidite_fnu + DECALAGE_FNU)
            classe = "1 jour" if age_h < 36 else ("2-3 jours" if age_h < 84 else "4-7 jours")
            m_now, m_prec = tur[i_now], tur[i_prec]
            ecarts[("persistance", classe)].append(math.log(prec.turbidite_fnu + DECALAGE_FNU) - vu)
            ecarts[("modele_seul", classe)].append(math.log(m_now + DECALAGE_FNU) - vu)
            for tau in taus:
                w = math.exp(-age_h / tau)
                add = max(m_now + w * (prec.turbidite_fnu - m_prec), 0.0)
                ecarts[(f"additif_{tau:.0f}h", classe)].append(math.log(add + DECALAGE_FNU) - vu)
                mul = math.log(m_now + DECALAGE_FNU) + w * (math.log(prec.turbidite_fnu + DECALAGE_FNU) - math.log(m_prec + DECALAGE_FNU))
                ecarts[(f"multiplicatif_{tau:.0f}h", classe)].append(mul - vu)
    resultat = defaultdict(dict)
    for (methode, classe), e in ecarts.items():
        e = np.array(e)
        resultat[methode][classe] = {"erreur_pct": round(en_pourcentage(float(np.sqrt(np.mean(e**2)))), 1), "images": len(e)}
    return dict(resultat)


def visibilite_sans_sensibilite(s: SerieCalage, reglages: dict, saisons: dict) -> float:
    """Visibilité calme qui convient le mieux au point quand sa sensibilité à la houle vaut 1."""
    idx, val = _indices_observations(s.conditions, s.observations)
    _, b, a = composantes_turbidite(_neutre(s.spot), s.conditions, {**reglages, "SAISON": SANS_SAISON})
    saison = modele.facteur_saison(s.conditions.temps[idx], saisons[s.spot.region])
    bas, haut = visibilite_vers_fond(BORNES_VISIBILITE_CALME[1]), visibilite_vers_fond(BORNES_VISIBILITE_CALME[0])
    fonds = GRILLE_FOND_FNU[(GRILLE_FOND_FNU >= bas) & (GRILLE_FOND_FNU <= haut)]
    prevu = saison[None, :] * (fonds[:, None] + b[idx][None, :] + a[idx][None, :])
    cout = np.mean((np.log(prevu + DECALAGE_FNU) - np.log(val + DECALAGE_FNU)[None, :]) ** 2, axis=1)
    return fond_vers_visibilite(float(fonds[int(np.argmin(cout))]))


def climatologie_plancton(series: list[SerieCalage]) -> dict[str, list[float | None]]:
    """Atténuation mensuelle due au plancton (m⁻¹) par région, d'après la chlorophylle satellite médiane."""
    chl = defaultdict(lambda: defaultdict(list))
    for s in series:
        for o in s.observations:
            if o.chlorophylle_mg_m3 is not None and np.isfinite(o.chlorophylle_mg_m3):
                mois = datetime.fromtimestamp(o.temps, timezone.utc).month
                chl[s.spot.region][mois].append(o.chlorophylle_mg_m3)
    resultat = {}
    for region, par_mois in chl.items():
        resultat[region] = [
            {"chl_mediane": round(float(np.median(par_mois[m])), 3), "images": len(par_mois[m]),
             "attenuation": round(P.PLANCTON_A * float(np.median(par_mois[m])) ** P.PLANCTON_B, 3)}
            if len(par_mois[m]) >= 10 else None
            for m in range(1, 13)
        ]
    return resultat


def regions_par_defaut(series: list[SerieCalage], res) -> dict:
    """Visibilité calme par défaut de chaque région, pour les lieux sans valeurs calées (sensibilité 1)."""
    par_region = defaultdict(list)
    for s in series:
        if s.spot.id in res.visibilites_calmes:
            par_region[s.spot.region].append(visibilite_sans_sensibilite(s, res.reglages, res.saisons) / P.FACTEUR_CALME_FOND[s.spot.fond])
    return {r: {"actuelle": P.REGIONS[r]["visibilite_calme_m"], "calee": round(float(np.median(v)), 1),
                "quartiles": [round(float(np.percentile(v, 25)), 1), round(float(np.percentile(v, 75)), 1)],
                "points": len(v)}
            for r, v in par_region.items()}


def _chiffres(v: float, n: int = 4) -> str:
    texte = f"{v:.{n}g}"
    return texte if any(c in texte for c in ".e") else texte + ".0"


def appliquer(res, regions: dict, periode: str, parametres: Path, points: Path) -> None:
    """Écrit les valeurs retenues dans prevision/parametres.py et spots/points.json."""
    import re

    lignes = parametres.read_text(encoding="utf-8").split("\n")
    for nom, valeur in res.reglages.items():
        k = next(i for i, l in enumerate(lignes) if re.match(rf"^{nom}\s*=", l))
        lignes[k] = re.sub(rf"^({nom}\s*=\s*)[0-9.eE+-]+", lambda m: m.group(1) + _chiffres(valeur), lignes[k])
        lignes[k] = lignes[k].replace("À CALER.", f"Calé sur le satellite ({periode}).")
        j = k - 1
        while j >= 0 and lignes[j].startswith("#"):
            lignes[j] = lignes[j].replace("À CALER.", f"Calé sur le satellite ({periode}).")
            j -= 1
    texte = "\n".join(lignes)
    bloc = "SAISON = {\n" + "".join(
        f'    "{r}": {{"amplitude": {_chiffres(v["amplitude"], 3)}, "pic_jour": {_chiffres(v["pic_jour"], 4)}}},\n'
        for r, v in res.saisons.items()) + "}"
    texte = re.sub(r"SAISON = \{\n.*?\n\}", lambda m: bloc, texte, count=1, flags=re.S)
    texte = texte.replace("sur la turbidité côtière : exp(amplitude · cos(2π (jour − pic_jour) / 365,25)),\n# pic_jour compté depuis le 1er janvier.",
                          f"sur la turbidité côtière : exp(amplitude · cos(2π (jour − pic_jour) / 365,25)),\n# pic_jour compté depuis le 1er janvier. Calé sur le satellite ({periode}).")
    for r, v in regions.items():
        texte = re.sub(rf'("{r}": \{{\n\s*"visibilite_calme_m": )[0-9.]+', lambda m: m.group(1) + f"{v['calee']:.1f}", texte, count=1)
    parametres.write_text(texte, encoding="utf-8")

    donnees = json.loads(points.read_text(encoding="utf-8"))
    for d in donnees:
        if d["id"] in res.visibilites_calmes:
            d["visibilite_calme_m"] = round(res.visibilites_calmes[d["id"]], 1)
            d["sensibilite_houle"] = round(res.sensibilites_houle[d["id"]], 2)
        else:
            d.pop("visibilite_calme_m", None)
            d.pop("sensibilite_houle", None)
    points.write_text(json.dumps(donnees, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--historique", default=str(RACINE / "historique"))
    p.add_argument("--sortie", default=str(RACINE / "calage" / "resultat.json"))
    p.add_argument("--parametres", default=",".join(BORNES))
    p.add_argument("--appliquer", action="store_true", help="écrire les valeurs retenues dans parametres.py et points.json")
    a = p.parse_args()
    calables = tuple(a.parametres.split(","))

    t0 = time.time()
    spots = charger_spots(RACINE / "spots" / "points.json")
    series, infos = charger_series(Path(a.historique), spots)
    print(f"{len(series)} points, {sum(len(s.observations) for s in series)} images, chargés en {time.time() - t0:.0f} s", flush=True)
    periode = {"du": min(v["du"] for v in infos.values() if isinstance(v, dict)),
               "au": max(v["au"] for v in infos.values() if isinstance(v, dict))}

    # 1. Validation : calage sur le début de l'historique, vérification sur la fin (jamais vue)
    apprentissage, test = separer(series)
    climato = erreur_climatologie(apprentissage, test)
    t1 = time.time()
    val = caler(apprentissage, test, parametres=calables)
    print(f"calage de validation en {time.time() - t1:.0f} s", flush=True)
    operationnel = evaluation_operationnelle(apprentissage, test, {**val.reglages, "SAISON": val.saisons},
                                             val.visibilites_calmes, val.sensibilites_houle)

    # 2. Valeurs retenues : calage sur tout l'historique
    t1 = time.time()
    res = caler(series, parametres=calables)
    print(f"calage final en {time.time() - t1:.0f} s", flush=True)
    regions = regions_par_defaut(series, res)

    sortie = {
        "date": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "periode": periode,
        "points": len(res.visibilites_calmes),
        "images": res.observations,
        "validation": {
            "images_apprentissage": val.observations,
            "images_test": sum(len(s.observations) for s in test),
            "erreur_typique_sans_satellite_pct": {
                "climatologie": round(en_pourcentage(climato), 1),
                "modele_avant_calage": round(en_pourcentage(val.erreur_test_initiale), 1),
                "modele_apres_calage": round(en_pourcentage(val.erreur_test), 1),
            },
            "erreur_typique_avec_satellite_pct": operationnel,
            "reglages": val.reglages,
            "saisons": val.saisons,
        },
        "reglages": {k: {"avant": float(getattr(P, k)), "apres": v} for k, v in res.reglages.items()},
        "saisons": res.saisons,
        "erreur_typique_apprentissage_pct": {"avant": round(en_pourcentage(res.erreur_initiale), 1),
                                             "apres": round(en_pourcentage(res.erreur_finale), 1)},
        "points_cales": {s.spot.id: {"visibilite_calme_avant": round(float(s.spot.visibilite_calme), 2),
                                     "visibilite_calme": res.visibilites_calmes[s.spot.id],
                                     "sensibilite_houle": res.sensibilites_houle[s.spot.id],
                                     "erreur_pct": round(en_pourcentage(res.details[s.spot.id]), 1),
                                     "images": len(s.observations)}
                         for s in series if s.spot.id in res.visibilites_calmes},
        "regions": regions,
        "plancton_satellite_non_utilise": climatologie_plancton(series),
        "donnees": infos,
    }
    Path(a.sortie).parent.mkdir(parents=True, exist_ok=True)
    Path(a.sortie).write_text(json.dumps(sortie, ensure_ascii=False, indent=1), encoding="utf-8")
    print(json.dumps({k: sortie[k] for k in ("periode", "points", "images", "validation", "reglages", "saisons", "regions")},
                     ensure_ascii=False, indent=1))
    if a.appliquer:
        appliquer(res, regions, f"{periode['du'][:7]} à {periode['au'][:7]}",
                  RACINE / "prevision" / "parametres.py", RACINE / "spots" / "points.json")
        print("valeurs écrites dans prevision/parametres.py et spots/points.json")


if __name__ == "__main__":
    main()
