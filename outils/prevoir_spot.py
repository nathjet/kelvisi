"""Prévision réelle d'un spot à partir des données Open-Meteo du moment.

Usage :
    python outils/prevoir_spot.py --id exemple-anse-sable
    python outils/prevoir_spot.py --lat 47.9 --lon -4.4 --orientation 270 --profondeur 6 --fond sable

Nécessite un accès réseau à marine-api.open-meteo.com et api.open-meteo.com.
"""

import argparse
import json
import sys
import time
from pathlib import Path

RACINE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RACINE))

from prevision import Spot, charger_spots, prevoir  # noqa: E402
from prevision.sources import openmeteo  # noqa: E402


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--id", help="identifiant d'un spot du fichier de spots")
    p.add_argument("--spots", default=str(RACINE / "spots" / "exemples.json"))
    p.add_argument("--lat", type=float)
    p.add_argument("--lon", type=float)
    p.add_argument("--region", default="atlantique")
    p.add_argument("--orientation", type=float, default=270)
    p.add_argument("--ouverture", type=float, default=90)
    p.add_argument("--profondeur", type=float, default=8)
    p.add_argument("--fond", default="mixte")
    p.add_argument("--jours", type=int, default=3)
    p.add_argument("--json", action="store_true", help="affiche la sortie complète")
    args = p.parse_args()

    if args.id:
        spot = next((s for s in charger_spots(args.spots) if s.id == args.id), None)
        if spot is None:
            sys.exit(f"Spot introuvable : {args.id}")
    elif args.lat is not None and args.lon is not None:
        spot = Spot(id="point", nom="Point choisi", lat=args.lat, lon=args.lon, region=args.region,
                    orientation_deg=args.orientation, ouverture_deg=args.ouverture,
                    profondeur_m=args.profondeur, fond=args.fond)
    else:
        sys.exit("Indiquer --id ou --lat et --lon")

    try:
        conditions = openmeteo.recuperer(spot.lat, spot.lon, jours_passes=5, jours_prevision=max(args.jours + 1, 4))
    except Exception as erreur:  # réseau coupé, quota dépassé, réponse invalide
        sys.exit(f"Impossible de récupérer les données Open-Meteo : {type(erreur).__name__}. Vérifier l'accès réseau.")
    resultat = prevoir(spot, conditions, int(time.time()), jours=args.jours)

    if args.json:
        print(json.dumps(resultat, ensure_ascii=False, indent=2))
        return
    print(spot.nom)
    for j in resultat["jours"]:
        cr = j["meilleur_creneau"]
        creneau = "aucun créneau conseillé" if cr is None else f"{cr['debut'][11:16]}-{cr['fin'][11:16]} ({cr['visibilite_m']} m)"
        print(f"{j['date']}  {j['visibilite_moyenne_m']} m  {j['classe']}  {creneau}")
        print(f"   {j['explication']}")
        if j["alerte"]:
            print(f"   {j['alerte']}")


if __name__ == "__main__":
    main()
