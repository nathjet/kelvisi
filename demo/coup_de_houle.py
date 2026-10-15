"""Démonstration : trois spots fictifs face au même coup de houle d'ouest.

Usage : python demo/coup_de_houle.py
Écrit aussi demo/coup_de_houle.csv (visibilité toutes les 3 heures).
"""

import csv
import sys
from datetime import datetime, timezone
from pathlib import Path

RACINE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RACINE))

from prevision import charger_spots, prevoir  # noqa: E402
from prevision.simulation import coup_de_houle  # noqa: E402

DEBUT = int(datetime(2026, 10, 10, tzinfo=timezone.utc).timestamp())
MAINTENANT = DEBUT + 86400  # on prévoit à partir du 11 octobre, la veille de la tempête


def main():
    spots = charger_spots(RACINE / "spots" / "exemples.json")
    conditions = coup_de_houle(DEBUT, jours=8)
    previsions = {s.id: prevoir(s, conditions, MAINTENANT, jours=6) for s in spots}

    for spot in spots:
        p = previsions[spot.id]
        print(f"\n=== {spot.nom}")
        for j in p["jours"]:
            cr = j["meilleur_creneau"]
            creneau = "aucun créneau conseillé" if cr is None else f"{cr['debut'][11:16]}-{cr['fin'][11:16]} ({cr['visibilite_m']} m)"
            print(f"{j['date']}  {j['visibilite_moyenne_m']:>4} m  {j['classe']:<10}  tendance {str(j['tendance']):<13}  {creneau}")
            print(f"            {j['explication']}")

    chemin = RACINE / "demo" / "coup_de_houle.csv"
    with chemin.open("w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["heure", "houle_m"] + [s.id for s in spots])
        heures = previsions[spots[0].id]["heures"]
        for k in range(0, len(heures), 3):
            ligne = [heures[k]["heure"], heures[k]["houle"]["hauteur_m"]]
            ligne += [previsions[s.id]["heures"][k]["visibilite_m"] for s in spots]
            w.writerow(ligne)
    print(f"\nSérie écrite dans {chemin}")


if __name__ == "__main__":
    main()
