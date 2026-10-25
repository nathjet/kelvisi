"""Calcule les prévisions de tous les points publics et les écrit pour l'application.

Lancé toutes les heures par GitHub Actions (voir .github/workflows/previsions.yml).

Usage : python outils/calculer_previsions.py [--sortie app/donnees] [--jours 3]

Écrit dans le dossier de sortie :
  resume.json        tous les points, résumé par jour (carte et liste « Où aller ? »)
  points/<id>.json   détail heure par heure d'un point (fiche du spot)
  parametres.json    constantes du modèle, lues par le moteur du navigateur
  temperatures.json  température de l'eau de la surface à 40 m autour de chaque point (si Copernicus)
  push.json          clé publique des notifications (alertes sur les favoris, si Supabase)

Variables d'environnement facultatives :
  OPEN_METEO_CLE                       clé Open-Meteo (usage commercial)
  SUPABASE_URL, SUPABASE_SERVICE_KEY   lecture des retours terrain pour corriger chaque point,
                                       envoi des alertes sur les favoris (voir outils/alertes.py)
  COPERNICUSMARINE_SERVICE_USERNAME,
  COPERNICUSMARINE_SERVICE_PASSWORD    correction par satellite (voir prevision/sources/copernicus.py)
                                       et température en profondeur (prevision/sources/temperature.py)

Les débits des rivières (Hub'Eau) sont lus sans clé. Toute source facultative
en panne est ignorée : les prévisions sont publiées sans elle.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

import numpy as np

RACINE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RACINE))

from prevision import charger_spots, parametres as P, prevoir  # noqa: E402
from prevision.donnees import Rapport  # noqa: E402
from prevision.pipeline import VERSION_MODELE  # noqa: E402
from prevision.sources import copernicus, hubeau, openmeteo, temperature  # noqa: E402
from prevision.spot import avec_reglage_voisin  # noqa: E402

JOURS_RETOURS = 90
# Le modèle de température ne change qu'une fois par jour : le fichier publié est repris tel quel
# pendant 6 h, et sert de secours (moins de 2 jours) si Copernicus ne répond pas.
AGE_TEMPERATURES_S = 6 * 3600
AGE_SECOURS_TEMPERATURES_S = 48 * 3600


def facade(spot) -> str:
    """Façade affichée : la Corse est distinguée du reste de la Méditerranée."""
    if spot.region == "mediterranee" and spot.lon > 8.4 and spot.lat < 43.1:
        return "corse"
    return spot.region


def description_spot(spot) -> dict:
    return {
        "id": spot.id, "nom": spot.nom, "lat": spot.lat, "lon": spot.lon,
        "region": spot.region, "facade": facade(spot),
        "orientation_deg": spot.orientation_deg, "ouverture_deg": spot.ouverture_deg,
        "profondeur_m": spot.profondeur_m, "fond": spot.fond, "notes": spot.notes,
        "rivieres": sorted({st.nom for st in spot.stations if st.nom}),
        "seuils": list(spot.params_region["seuils"]),
        # Valeurs calées sur le satellite, reprises par le navigateur pour les lieux proches
        "calage": ({"visibilite_calme_m": spot.visibilite_calme_m, "sensibilite_houle": spot.sensibilite_houle}
                   if spot.visibilite_calme_m is not None else None),
    }


def parametres_publics() -> dict:
    """Toutes les constantes du modèle, sous une forme lisible en JavaScript."""
    def convertir(v):
        if isinstance(v, dict):
            return {k: convertir(x) for k, x in v.items()}
        if isinstance(v, (tuple, list)):
            return [convertir(x) for x in v]
        return v
    return {nom: convertir(getattr(P, nom)) for nom in dir(P) if nom.isupper()}


BILAN: list[str] = []


def noter(ligne: str) -> None:
    """Affiche une ligne et la garde pour le résumé visible dans GitHub Actions."""
    print(ligne, flush=True)
    BILAN.append(ligne)


def publier_bilan() -> None:
    """Annotation GitHub (onglet Actions) reprenant le bilan du passage, sans aucune donnée personnelle."""
    if os.environ.get("GITHUB_ACTIONS") and BILAN:
        texte = "\n".join(BILAN)[:3800].replace("%", "%25").replace("\r", "").replace("\n", "%0A")
        print(f"::notice title=Bilan du calcul::{texte}", flush=True)


def ajouter_debits(spots, conditions, telecharger=hubeau.telecharger) -> dict[str, str]:
    """Ajoute aux conditions de chaque point les débits de ses rivières (Hub'Eau).

    Chaque station n'est téléchargée qu'une fois. Une station injoignable est
    ignorée : le point est alors calculé sans sa rivière, comme dans l'application.
    Retourne l'état de chaque station ("ok" ou le type d'erreur).
    """
    codes = sorted({st.code for spot in spots for st in spot.stations})
    if not codes:
        return {}
    depuis = min(int(c.temps[0]) for c in conditions) - 86400
    mesures, etat = {}, {}
    for code in codes:
        try:
            temps, debits = telecharger(code, depuis)
            if len(temps) == 0:
                raise ValueError("aucune mesure")
            mesures[code] = (temps, debits)
            etat[code] = "ok"
        except Exception as e:  # réseau, format inattendu : on continue sans cette rivière
            etat[code] = type(e).__name__
    for spot, cond in zip(spots, conditions):
        for st in spot.stations:
            if st.code in mesures:
                cond.debits[st.code] = hubeau.sur_grille_horaire(*mesures[st.code], np.asarray(cond.temps))
    return etat


def debits_actuels(spot, cond, maintenant: int) -> list[dict]:
    """Dernier débit mesuré de chaque rivière du point, comparé à son débit habituel."""
    resultat = []
    for st in spot.stations:
        serie = cond.debits.get(st.code)
        if serie is None:
            continue
        t = np.asarray(cond.temps)
        valides = np.isfinite(serie) & (t <= maintenant)
        if not valides.any():
            continue
        i = int(np.flatnonzero(valides)[-1])
        resultat.append({
            "nom": st.nom or st.code, "debit_m3s": round(float(serie[i]), 1),
            "debit_habituel_m3s": round(st.debit_reference_m3s, 1),
            "rapport": round(float(serie[i]) / st.debit_reference_m3s, 2) if st.debit_reference_m3s > 0 else None,
            "mesure_le": datetime.fromtimestamp(int(t[i]), timezone.utc).isoformat(),
        })
    return resultat


def resumer_retours(rapports: list[Rapport], maintenant: int) -> dict:
    recents = [r for r in rapports if maintenant - r.temps <= 7 * 86400]
    dernier = max(rapports, key=lambda r: r.temps, default=None)
    return {
        "nombre_7_jours": len(recents),
        "dernier": None if dernier is None else {
            "visibilite_m": dernier.visibilite_m,
            "date": datetime.fromtimestamp(dernier.temps, timezone.utc).isoformat(),
        },
    }


def completer_previsions(spot, cond, rapports: list[Rapport]) -> list[Rapport]:
    """Ajoute la visibilité prévue aux retours qui ne l'ont pas, quand la météo de ce moment est connue.

    Le calcul horaire récupère 5 jours de météo passée : un retour de moins de
    5 jours peut donc être comparé à ce que le modèle (sans correction) prévoyait.
    """
    manquants = [r for r in rapports if r.prevision_m is None and cond.temps[0] <= r.temps <= cond.temps[-1]]
    if not manquants:
        return rapports
    from prevision import modele

    vis = modele.calculer(spot, cond).visibilite_m
    resultat = []
    for r in rapports:
        if r.prevision_m is None and cond.temps[0] <= r.temps <= cond.temps[-1]:
            i = int(round((r.temps - cond.temps[0]) / 3600))
            r = Rapport(r.temps, r.visibilite_m, r.utilisateur, float(vis[min(i, len(vis) - 1)]))
        resultat.append(r)
    return resultat


def construire(spots, conditions, maintenant: int, rapports_par_spot: dict | None = None, jours: int = 3,
               satellites: dict | None = None) -> dict:
    """Prévisions de tous les points. Un point en erreur est signalé sans bloquer les autres."""
    rapports_par_spot = rapports_par_spot or {}
    satellites = satellites or {}
    resume_points, details, erreurs = [], {}, []
    for spot, cond in zip(spots, conditions):
        try:
            # Point pas encore calé : il reprend les valeurs de son voisin calé (moins de 25 km), comme un lieu libre
            calcul = avec_reglage_voisin(spot, spots)
            rapports = completer_previsions(calcul, cond, rapports_par_spot.get(spot.id, []))
            p = prevoir(calcul, cond, maintenant, satellite=satellites.get(spot.id), rapports=rapports, jours=jours)
        except Exception as e:  # un point défaillant ne doit pas empêcher la publication des autres
            erreurs.append({"id": spot.id, "erreur": f"{type(e).__name__}: {e}"})
            continue
        meta = description_spot(spot)
        p["spot"] = meta
        p["rivieres"] = debits_actuels(spot, cond, maintenant)
        details[spot.id] = p
        resume_points.append({
            **meta,
            "jours": [
                {k: j[k] for k in ("date", "visibilite_moyenne_m", "classe", "meilleur_creneau", "alerte",
                                   "explication", "tendance", "conseil_maree", "lever_soleil",
                                   "coucher_soleil", "marees")}
                for j in p["jours"]
            ],
            "calibrage": p["calibrage"],
            "satellite": p["satellite"],
            "retours": resumer_retours(rapports, maintenant),
        })
    resume = {
        "genere_le": datetime.fromtimestamp(maintenant, timezone.utc).isoformat(),
        "version_modele": VERSION_MODELE,
        "points": resume_points,
        "erreurs": erreurs,
        "sources": ["Open-Meteo"] + (["Copernicus Marine"] if satellites else [])
                   + (["retours terrain"] if rapports_par_spot else []),
    }
    return {"resume": resume, "details": details}


def ecrire(dossier: Path, sorties: dict) -> None:
    dossier.mkdir(parents=True, exist_ok=True)
    (dossier / "points").mkdir(exist_ok=True)

    def ecrire_json(chemin: Path, contenu) -> None:
        temporaire = chemin.with_suffix(".tmp")
        temporaire.write_text(json.dumps(contenu, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
        temporaire.replace(chemin)

    for ident, detail in sorties["details"].items():
        ecrire_json(dossier / "points" / f"{ident}.json", detail)
    ecrire_json(dossier / "resume.json", sorties["resume"])
    ecrire_json(dossier / "parametres.json", parametres_publics())
    if sorties.get("temperatures"):
        ecrire_json(dossier / "temperatures.json", sorties["temperatures"])
    if sorties.get("push"):
        ecrire_json(dossier / "push.json", sorties["push"])


def envoyer_alertes(url: str, cle: str, resume: dict, maintenant: int, traiter=None) -> dict | None:
    """Alertes sur les favoris (outils/alertes.py). Renvoie le contenu de push.json, ou None si indisponible."""
    import alertes

    traiter = traiter or alertes.traiter
    try:
        bilan = traiter(alertes.Base(url, cle), resume, datetime.fromtimestamp(maintenant, timezone.utc),
                        adresse_site() or "https://github.com/nathjet/kelvisi")
    except Exception as e:
        statut = getattr(getattr(e, "response", None), "status_code", None)
        noter("Alertes : tables absentes, relance supabase/schema.sql dans Supabase" if statut in (400, 404)
              else f"Alertes indisponibles ({type(e).__name__})")
        return None
    if bilan["hors_horaires"]:
        noter("Alertes : en attente (envoi entre 8 h et 21 h)")
    elif bilan["notifications"] or bilan["abonnements_supprimes"]:
        noter(f"Alertes : {bilan['notifications']} notifications envoyées à {bilan['comptes']} comptes"
              + (f", {bilan['abonnements_supprimes']} abonnements expirés supprimés" if bilan["abonnements_supprimes"] else ""))
    return {"cle_publique": bilan["cle_publique"]}


def adresse_site() -> str | None:
    """Adresse de l'application publiée (GitHub Pages), pour relire le fichier de températures déjà en ligne."""
    if os.environ.get("KELVISI_SITE"):
        return os.environ["KELVISI_SITE"].rstrip("/") + "/"
    depot = os.environ.get("GITHUB_REPOSITORY", "")
    if "/" not in depot:
        return None
    proprietaire, nom = depot.split("/", 1)
    return f"https://{proprietaire.lower()}.github.io/{nom}/"


def lire_temperatures_publiees(site: str | None, session=None) -> dict | None:
    if not site:
        return None
    import requests

    try:
        r = (session or requests).get(f"{site}donnees/temperatures.json", timeout=20)
        return r.json() if r.ok else None
    except Exception:
        return None


def temperatures_du_passage(spots, maintenant: int, precedent: dict | None, recuperer=temperature.recuperer) -> tuple[dict | None, str]:
    """Profils de température à publier, et une ligne de bilan.

    Fichier déjà en ligne de moins de 6 h et complet : repris sans interroger Copernicus.
    Sinon recalcul ; les points d'un bassin en panne gardent leur ancien profil s'il a moins de 2 jours
    (ses dates restent celles d'origine, l'application n'affiche que le jour correspondant).
    """
    ids = {s.id for s in spots}
    if temperature.encore_valable(precedent, ids, maintenant, AGE_TEMPERATURES_S):
        return precedent, f"Température en profondeur : fichier de {precedent['genere_le'][11:16]} UTC repris ({len(precedent['points'])} points)"
    t0 = time.time()
    res = recuperer(spots, maintenant)
    points = dict(res["points"])
    repris = 0
    if temperature.encore_valable(precedent, set(), maintenant, AGE_SECOURS_TEMPERATURES_S, complet=False):
        for ident, profil in precedent["points"].items():
            if ident in ids and ident not in points:
                points[ident] = profil
                repris += 1
    bilan = (f"Température en profondeur : {len(res['points'])} points sur {len(spots)} en {time.time() - t0:.0f} s"
             + (f", {repris} anciens profils repris" if repris else "")
             + "".join(f" ; indisponible ({b}) : {e[:200]}" for b, e in res["erreurs"].items()))
    if not points:
        return None, bilan
    return {
        "genere_le": datetime.fromtimestamp(maintenant, timezone.utc).isoformat(),
        "complet": not res["erreurs"],
        "jeux": res["jeux"],
        "points": points,
    }, bilan


def entetes_supabase(cle: str) -> dict:
    """Clé secrète (sb_secret_…) : en-tête apikey seul. Ancienne clé service_role (JWT) : apikey et Authorization."""
    return {"apikey": cle} if cle.startswith("sb_") else {"apikey": cle, "Authorization": f"Bearer {cle}"}


def lire_retours_supabase(url: str, cle: str, maintenant: int, session=None) -> dict[str, list[Rapport]]:
    """Retours terrain des 90 derniers jours, regroupés par point."""
    import requests

    http = session or requests.Session()
    depuis = datetime.fromtimestamp(maintenant - JOURS_RETOURS * 86400, timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    r = http.get(
        f"{url.rstrip('/')}/rest/v1/rapports",
        params={"select": "spot_id,visibilite_m,prevision_m,observe_le,appareil,utilisateur", "observe_le": f"gte.{depuis}",
                "order": "observe_le.asc", "limit": "10000"},
        headers=entetes_supabase(cle),
        timeout=30,
    )
    r.raise_for_status()
    par_spot: dict[str, list[Rapport]] = defaultdict(list)
    for ligne in r.json():
        try:
            t = int(datetime.fromisoformat(ligne["observe_le"].replace("Z", "+00:00")).timestamp())
            par_spot[ligne["spot_id"]].append(Rapport(
                temps=t, visibilite_m=float(ligne["visibilite_m"]),
                utilisateur=str(ligne.get("utilisateur") or ligne.get("appareil") or "anonyme"),
                prevision_m=None if ligne.get("prevision_m") is None else float(ligne["prevision_m"]),
            ))
        except (KeyError, TypeError, ValueError):
            continue
    return dict(par_spot)


def spots_a_valider(url: str, cle: str, session=None) -> int | None:
    """Nombre de spots proposés au partage qui attendent la validation de l'éditeur (None si le partage n'est pas installé)."""
    import requests

    http = session or requests
    r = http.get(f"{url.rstrip('/')}/rest/v1/spots_prives", params={"select": "partage_id", "partage": "eq.en_attente"},
                 headers={**entetes_supabase(cle), "Prefer": "count=exact", "Range": "0-0"}, timeout=30)
    if r.status_code in (400, 404):  # colonne absente : script SQL du partage pas encore appliqué
        return None
    r.raise_for_status()
    total = r.headers.get("Content-Range", "*/0").split("/")[-1]
    return int(total) if total.isdigit() else 0


def purger_comptes_inactifs(url: str, cle: str, session=None) -> int | None:
    """Supprime les comptes sans connexion depuis 3 ans (fonction SQL de supabase/schema.sql)."""
    import requests

    http = session or requests.Session()
    r = http.post(f"{url.rstrip('/')}/rest/v1/rpc/purger_comptes_inactifs", json={},
                  headers={**entetes_supabase(cle), "Content-Type": "application/json"}, timeout=30)
    r.raise_for_status()
    return r.json()


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--sortie", default=str(RACINE / "app" / "donnees"))
    p.add_argument("--spots", default=str(RACINE / "spots" / "points.json"))
    p.add_argument("--jours", type=int, default=3)
    args = p.parse_args()

    debut = time.time()
    maintenant = int(time.time())
    spots = charger_spots(args.spots)
    conditions = openmeteo.recuperer_plusieurs(
        [(s.lat, s.lon) for s in spots], jours_passes=5, jours_prevision=args.jours + 1,
        cle=os.environ.get("OPEN_METEO_CLE") or None, pause_s=3.0,
    )

    etat_rivieres = ajouter_debits(spots, conditions)
    if etat_rivieres:
        en_panne = [c for c, e in etat_rivieres.items() if e != "ok"]
        noter(f"Rivières : {len(etat_rivieres) - len(en_panne)} stations lues"
              + (f", indisponibles : {', '.join(en_panne)}" if en_panne else ""))

    satellites = {}
    if copernicus.identifiants_presents():
        t0 = time.time()
        try:
            sat = copernicus.recuperer(spots, maintenant)
            satellites = sat["observations"]
            ages = sorted((maintenant - o.temps) / 86400 for o in satellites.values())
            noter(f"Satellite : {len(satellites)} points sur {len(spots)} avec une image exploitable"
                  + (f" (la plus récente il y a {ages[0]:.1f} j, la plus ancienne {ages[-1]:.1f} j)" if ages else "")
                  + f", en {time.time() - t0:.0f} s")
            for b, e in sat["erreurs"].items():
                noter(f"  satellite indisponible ({b}) : {str(e)[:300]}")
        except Exception as e:
            noter(f"Satellite indisponible ({type(e).__name__}) : prévisions sans satellite")
    else:
        noter("Satellite : identifiants Copernicus absents, étape sautée")

    temperatures = None
    if copernicus.identifiants_presents():
        try:
            temperatures, ligne = temperatures_du_passage(spots, maintenant, lire_temperatures_publiees(adresse_site()))
            noter(ligne)
        except Exception as e:
            noter(f"Température en profondeur indisponible ({type(e).__name__})")

    rapports = {}
    url, cle = os.environ.get("SUPABASE_URL"), os.environ.get("SUPABASE_SERVICE_KEY")
    if url and cle:
        try:
            rapports = lire_retours_supabase(url, cle, maintenant)
            noter(f"Retours terrain lus : {sum(len(v) for v in rapports.values())}")
        except Exception as e:
            noter(f"Retours terrain indisponibles ({type(e).__name__}) : prévisions sans correction")
        try:
            n = spots_a_valider(url, cle)
            if n:
                noter(f"Spots proposés au partage, en attente de ta validation : {n} (Supabase > Table Editor > spots_prives)")
        except Exception as e:
            noter(f"Spots à valider : lecture impossible ({type(e).__name__})")
        # Une fois par jour : effacement des comptes inactifs depuis 3 ans (durée annoncée aux utilisateurs)
        if datetime.fromtimestamp(maintenant, timezone.utc).hour == 3:
            try:
                n = purger_comptes_inactifs(url, cle)
                noter(f"Comptes inactifs supprimés : {n}")
            except Exception as e:
                noter(f"Purge des comptes inactifs impossible ({type(e).__name__})")

    sorties = construire(spots, conditions, maintenant, rapports, args.jours, satellites)
    resume = sorties["resume"]
    if temperatures:
        sorties["temperatures"] = temperatures
        if "Copernicus Marine" not in resume["sources"]:
            resume["sources"].insert(1, "Copernicus Marine")
    if url and cle and resume["points"]:
        sorties["push"] = envoyer_alertes(url, cle, resume, maintenant)
    if any(e == "ok" for e in etat_rivieres.values()):
        resume["sources"].insert(1, "Hub'Eau")
    ecrire(Path(args.sortie), sorties)
    noter(f"{len(resume['points'])} points calculés en {time.time() - debut:.0f} s, {len(resume['erreurs'])} en erreur")
    for e in resume["erreurs"]:
        noter(f"  {e['id']} : {e['erreur']}")
    publier_bilan()
    if not resume["points"]:
        sys.exit("Aucun point calculé : publication annulée")


if __name__ == "__main__":
    main()
