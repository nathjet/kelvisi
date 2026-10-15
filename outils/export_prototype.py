"""Construit le prototype de l'appli à partir du moteur.

Calcule une prévision sur 3 jours pour les 14 points de référence, à partir
d'une situation météo SIMULÉE (fin de coup de houle d'ouest sur l'Atlantique
et la Manche, petite houle d'est en Méditerranée), puis injecte le résultat
dans prototype/kelvisi.html.

Usage : python outils/export_prototype.py [sortie.html]
"""

import json
import sys
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

RACINE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RACINE))

from prevision import charger_spots, prevoir  # noqa: E402
from prevision.simulation import coup_de_houle  # noqa: E402

MAINTENANT = int(datetime(2026, 10, 15, tzinfo=ZoneInfo("Europe/Paris")).timestamp())
DECALAGE_H = 78  # « maintenant » tombe pendant la décrue de la houle simulée

SCENARIOS = {
    "manche": dict(hauteur_max=2.6, direction_houle=290, marnage=7.0),
    "atlantique": dict(hauteur_max=3.2, direction_houle=280, marnage=4.5),
    "mediterranee": dict(hauteur_max=1.4, direction_houle=95, marnage=0.3),
}


def construire() -> dict:
    debut = MAINTENANT - DECALAGE_H * 3600
    spots = charger_spots(RACINE / "spots" / "reference.json")
    conditions = {region: coup_de_houle(debut, jours=8, **params) for region, params in SCENARIOS.items()}
    previsions = []
    for spot in spots:
        p = prevoir(spot, conditions[spot.region], MAINTENANT, jours=3)
        p["spot"].update({"region": spot.region, "profondeur_m": spot.profondeur_m, "fond": spot.fond,
                          "orientation_deg": spot.orientation_deg, "notes": spot.notes,
                          "seuils": list(spot.params_region["seuils"])})
        for h in p["heures"]:
            for cle in ("courant_ms", "pluie_mm", "nebulosite_pct", "visibilite_ressentie_m"):
                h.pop(cle, None)
        previsions.append(p)
    return {"genere_le": MAINTENANT, "simulation": True, "previsions": previsions}


def main():
    sortie = Path(sys.argv[1]) if len(sys.argv) > 1 else RACINE / "prototype" / "dist" / "kelvisi.html"
    modele = (RACINE / "prototype" / "kelvisi.html").read_text(encoding="utf-8")
    donnees = json.dumps(construire(), ensure_ascii=False, separators=(",", ":")).replace("</", "<\\/")
    if "/*DONNEES*/null" not in modele:
        sys.exit("Repère /*DONNEES*/null introuvable dans le modèle")
    sortie.parent.mkdir(parents=True, exist_ok=True)
    sortie.write_text(modele.replace("/*DONNEES*/null", donnees), encoding="utf-8")
    print(f"{sortie} ({sortie.stat().st_size // 1024} Ko)")


if __name__ == "__main__":
    main()
