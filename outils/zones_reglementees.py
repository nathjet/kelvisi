"""Zones où la pêche sous-marine est interdite ou réglementée, pour la carte de Kelvisi.

Source : zones réglementaires du CACEM (Centre d'appui au contrôle de l'environnement marin, ministère
de la Transition écologique), publiées chaque semaine sur data.gouv.fr sous Licence Ouverte 2.0. Le
fichier recense plus de 4 500 zones (arrêtés préfectoraux, décrets de réserves, cantonnements...), chacune
avec un résumé de la règle. Les tracés sont une interprétation du CACEM et ne remplacent pas les textes.

On garde les zones de métropole dont le résumé parle de pêche sous-marine, de pêche en général,
de prélèvement ou de plongée, et on les classe :
  interdite    la règle interdit la pêche sous-marine (directement, ou en interdisant toute pêche,
               tout prélèvement, ou toute plongée y compris en apnée)
  reglementee  la règle encadre la pêche sous-marine sans l'interdire partout (espèces, saisons,
               autorisation, réserve naturelle)
Les zones très étendues (règles générales d'une façade, par exemple le moratoire sur les mérous dans
toutes les eaux territoriales) et celles dont la date de fin est passée sont écartées. Les grandes zones
réglementées (plus de 150 km², par exemple l'aire du parc national des Calanques) sont gardées pour
les fiches mais pas dessinées sur la carte.

Le classement est fait d'après le texte du résumé : il peut se tromper. La carte le dit, et renvoie
toujours au texte officiel (référence affichée avec chaque zone).

Usage : python outils/zones_reglementees.py [--sortie app/zones/peche-sous-marine.geojson] [--revue revue.csv]
Dépendances (seulement pour ce script) : pip install geopandas pyogrio shapely requests
"""

from __future__ import annotations

import argparse
import json
import re
import unicodedata
from datetime import date
from pathlib import Path

SOURCE = "https://www.data.gouv.fr/api/1/datasets/r/dd48b545-a1d1-4710-9e56-415b895f5336"
PAGE_SOURCE = "https://www.data.gouv.fr/datasets/zones-reglementaires-cacem"
COUCHES_METROPOLE = ("MED", "NAMO", "SA", "MEMN")
SURFACE_MAX_KM2 = 1500.0     # au-delà, il s'agit d'une règle générale (toute une façade, tout un département)
GRANDE_KM2 = 150.0           # zone réglementée plus grande : pas dessinée (trop envahissante), mais signalée dans les fiches
TOLERANCE_DEG = {"interdite": 0.00012, "reglementee": 0.0002, "grande": 0.0006}  # simplification (12, 20 et 60 m)
DECIMALES = 5                # environ 1 m

ESPECES = (r"crustac|oursin|gorgone|merou|corail|langouste|homard|araignee|poulpe|nacre|datte|patelle|coquillage|palourde"
           r"|bivalve|coque|crevette|saumon|salmonide|alose|maigre|\bbar\b|anguille|civelle|ormeau|especes suivantes|certaines especes")
_SUIVI_ESPECE = rf"(?! (des|du|de la|de l'|d'|aux?|pour les|sur les|a la)\b ?(\w+[ ']){{0,3}}?({ESPECES}))"
_SUIVI_ENGIN = r"(?! (a pied|aux? (filets?|lignes?|casiers?|nasses?|palangres?|arts?)|a la (senne|ligne|traine|drague)|professionnelle seule|du |de la |des |de l'|d'))"

# Interdiction directe de la pêche sous-marine (et pas seulement de certaines espèces)
_DIRECT = re.compile(
    rf"(pratiquer|exercer|pratique de|interdiction de) (la )?(peche|chasse)( et la chasse)? sous-marines?{_SUIVI_ESPECE}"
    rf"|(peche|chasse)s? sous-marines?( de loisir| et [\w' ]{{1,60}}?)?( y)?( est| sont)?( strictement| egalement| formellement)? interdi(te|tes|ts|t|ction)\b(?! (pour|sur|aux?)\b)"
    rf"|zones? d'interdiction (de )?(la )?(peche|chasse) sous-marine{_SUIVI_ESPECE}"
    rf"|seule (est )?autorisee la peche (pratiquee )?(a l'aide de|au moyen de|aux|a la) (lignes?|palangres?)"
)
# Interdiction de toute pêche, de tout prélèvement ou de toute activité
_GENERAL = re.compile(
    rf"tout(e|es)? (les )?(forme|formes|type|types|mode|modes|methode|methodes|activite|activites) de peche( maritime)?{_SUIVI_ENGIN}"
    rf"|tout(e|es)? (les )?peches?\b{_SUIVI_ENGIN}"
    rf"|tout engin de peche"
    rf"|sous toutes ses formes"
    rf"|peches? (maritimes? )?(professionnelles? (et|ou) de loisirs?|de loisirs? (et|ou) professionnelles?|pro et de loisir){_SUIVI_ENGIN}"
    rf"|(pratiquer|exercer|exercice de) la peche de loisir|peche de loisir (est |sont )?interdite"
    rf"|tout prelevement|non[- ]prelevement"
    rf"|(^|[,:(] ?|\bla )peche (maritime )?(est |sont )?interdites?{_SUIVI_ESPECE}"
    rf"|(^|[,:] ?|\b(la|a la|et la) )peche(?=,| interdit| sont interdit| et (la )?(plongee|baignade|navigation|chasse|le mouillage))"
    rf"|(\bde |[,:] ?)pecher\b(?! (la|le|les|des|du|au|aux|a la|a l'|avec) )"
    rf"|toute activite (est |y est )?interdite|toutes? (les )?autres activites|toutes? activites? nautiques?"
    rf"|(pratiquer|pratique) des activites (sportives|nautiques|de loisirs?)"
    rf"|(^|[,:;] ?|\bet )(la )?(peche|chasse) sous-marines?(?= ?[,;]|$| et | sont| interdi)"
    rf"|y compris (la |de )?(peche|chasse) sous-marine"
    rf"|zones? d'interdiction de (la )?peche\b{_SUIVI_ENGIN}"
    rf"|toutes? (les )?activites maritimes|reserve integrale|zone tampon maritime"
)
# Pêche sous-marine limitée à certaines espèces (crustacés, oursins...) : réglementée, pas interdite
_PSM_ESPECES = re.compile(
    r"(peche|chasse) sous-marines?( de loisir)? (des|du|de la|de l'|d'|aux?) ([\w']+ ){0,2}(crustac|oursin|gorgone|merou|corail|langouste|homard)"
    r"|(peche|chasse) sous-marines?( de loisir)?( est| sont)? (interdite )?pour (les|certaines) especes"
)
_TOUTE_PECHE = re.compile(r"(pratiquer|exercer) la peche de loisir|toute peche|tout(e|es)? (les )?(forme|formes|type|types|activite|activites) de peche|sous toutes ses formes|toutes les especes|quel que soit le mode|non[- ]prelevement|tout prelevement")
_PERIODE = re.compile(r"\bdu (1er|\d{1,2}) [a-z]+ (inclus )?au (1er|\d{1,2}) [a-z]+|jusqu'au (1er|\d{1,2}) [a-z]+|\ba compter du\b|en periode")
# Plongée interdite, apnée comprise (une interdiction limitée au scaphandre ne gêne pas la chasse sous-marine)
_PLONGEE = re.compile(
    r"\bapnee\b|activites? (sous-marines?|subaquatiques?)"
    r"|(^|[,:;] ?|\b(la|et|et la|et de|a la|de la|ainsi que la|ou|ou la|ou de) )plongee([- ]sous-marine)?\b"
    r"(?! (en|avec) (bouteilles?|scaphandre)(?! (autonome )?(et|ou) (en )?apnee))"
)
_INTERDIT = re.compile(r"interdi(t|te|ts|tes|ction|re)\b|prohib")
_SAUF_PSM = re.compile(r"(sauf|exception|excepte|hormis|hors)[^.;]{0,60}(peche|chasse) sous-marine")
# Espèces visées par les chasseurs sous-marins : une règle qui les concerne rend la zone « réglementée »
ESPECES_CHASSE = r"crustac|oursin|gorgone|merou|corail|langouste|homard|araignee|poulpe|ormeau|\bbar\b|maigre|denti|corb\b"
_REGLEMENTEE = re.compile(
    rf"(peche|chasse) sous-marine|\bapnee\b|peche (maritime )?de loisir|pecheurs? de loisir|prelevement|cantonnement"
    rf"|{ESPECES_CHASSE}|porter atteinte[^.]{{0,40}}animaux|peche maritime[^.]{{0,60}}reglement"
)
# Autorisations de travaux, câbles, études, classement sanitaire des coquillages : pas une règle de pêche sous-marine
_HORS_SUJET = re.compile(r"\baot\b|cable|raccordement|campagne|etudes?\b|ouvrages?\b|bouee|mesures?\b|salubrite")
_SANITAIRE = re.compile(r"non classe|zone dite « a eclipse »|groupe [123] :|classement (saisonnier|sanitaire|de salubrite)")
# Interdiction qui vise des lieux génériques (ports, chenaux, abords des élevages) à l'intérieur d'un grand périmètre
_GENERIQUE = re.compile(r"a l'interieur des (ports|zones delimitees par les ouvrages portuaires)|ouvrages portuaires|avants? ports|"
                        r"a moins de \d+ ?m(etres)? (de|des) (tous |toutes )?(les )?(etablissements|plages|ports|installations|concessions)")


def normaliser(texte) -> str:
    """Minuscules sans accents, apostrophes et tirets unifiés, espaces simples."""
    if texte is None or (isinstance(texte, float) and texte != texte):
        return ""
    t = unicodedata.normalize("NFKD", str(texte))
    t = "".join(c for c in t if not unicodedata.combining(c)).lower()
    t = t.replace("’", "'").replace("‘", "'").replace("–", "-").replace("—", "-")
    t = re.sub(r"sous[ -]?ma(rin|chin)", "sous-marin", t)
    t = re.sub(r"sous-marne", "sous-marine", t)
    t = re.sub(r"(peche|chasse) sous-marin\b", r"\1 sous-marine", t)
    return re.sub(r"\s+", " ", t).strip()


def phrases(texte: str) -> list[str]:
    return [p.strip() for p in re.split(r"[.\n!]|\s-\s|\s--\s", texte) if p.strip()]


def classer(layer_name="", poly_name="", resume="", themes="") -> str | None:
    """Classe une zone d'après son nom et le résumé de sa règle : "interdite", "reglementee" ou None."""
    noms = normaliser(f"{layer_name} : {poly_name}")
    texte = normaliser(resume)
    if _HORS_SUJET.search(noms) or _SANITAIRE.search(texte):
        return None
    for p in phrases(texte):
        if _SAUF_PSM.search(p):
            continue
        if _GENERIQUE.search(p) and (_DIRECT.search(p) or _GENERAL.search(p)):
            return "reglementee"
        if _DIRECT.search(p) and not _PSM_ESPECES.search(p):
            return "interdite"
        if not _INTERDIT.search(p):
            continue
        if _PLONGEE.search(p):
            return "interdite"
        if _GENERAL.search(p) and (_TOUTE_PECHE.search(p) or not re.search(ESPECES, p)):
            return "interdite"
    # Nom explicite (« Zone d'interdiction de la pêche sous-marine »), sauf si le résumé la limite à des espèces
    if re.search(r"interdiction (de )?(la )?(peche|chasse) sous-marine|(peche|chasse) sous-marine interdite|non[- ]prelevement", noms) \
            and not _PSM_ESPECES.search(texte):
        return "interdite"
    if _REGLEMENTEE.search(texte) or _REGLEMENTEE.search(noms) or "peche sous-marine" in normaliser(themes):
        return "reglementee"
    return None


def nom_zone(z) -> str:
    for champ in ("poly_name", "layer_name"):
        v = z.get(champ)
        if isinstance(v, str) and v.strip() and v.strip().lower() != "nan":
            return v.strip()[:120]
    return "Zone réglementée"


def resume_court(texte, longueur: int = 600) -> str:
    if not isinstance(texte, str):
        return ""
    t = re.sub(r"\s+", " ", texte).strip()
    return t if len(t) <= longueur else t[: longueur - 1].rsplit(" ", 1)[0] + "…"


def arrondir(coords, decimales: int = DECIMALES):
    if isinstance(coords, (list, tuple)) and coords and isinstance(coords[0], (int, float)):
        return [round(float(c), decimales) for c in coords]
    return [arrondir(c, decimales) for c in coords]


def construire(zones, aujourd_hui: date | None = None) -> tuple[dict, list[dict]]:
    """GeoJSON des zones retenues et lignes de revue (toutes les zones examinées avec leur classement).

    `zones` : GeoDataFrame en WGS84 avec les colonnes du CACEM et une colonne couche_gpkg.
    """
    from shapely.geometry import mapping

    aujourd_hui = aujourd_hui or date.today()
    surfaces = zones.to_crs(2154).geometry.area / 1e6
    par_contour, revue = {}, []
    for (_, z), surface in zip(zones.iterrows(), surfaces):
        classe = classer(z.get("layer_name"), z.get("poly_name"), z.get("resume"), z.get("themes"))
        motif = ""
        fin = str(z.get("date_fin") or "")[:10]
        if classe is None:
            motif = "sans rapport"
        elif fin and fin != "nan" and fin < aujourd_hui.isoformat():
            motif = f"terminée le {fin}"
        elif surface > SURFACE_MAX_KM2:
            motif = f"règle générale ({surface:.0f} km²)"
        elif z.geometry is None or z.geometry.is_empty:
            motif = "sans contour"
        revue.append({"id": z.get("id"), "couche": z.get("couche_gpkg"), "classe": classe or "", "retenue": not motif, "motif": motif,
                      "surface_km2": round(float(surface), 3), "nom": nom_zone(z), "resume": resume_court(z.get("resume"), 300)})
        if motif:
            continue
        grande = classe == "reglementee" and surface > GRANDE_KM2
        geometrie = z.geometry.simplify(TOLERANCE_DEG["grande" if grande else classe], preserve_topology=True)
        if geometrie.is_empty:
            continue
        g = mapping(geometrie)
        coordonnees = arrondir(g["coordinates"])
        cle = (g["type"], json.dumps(coordonnees, separators=(",", ":")))
        regle = {
            "classe": classe, "nom": nom_zone(z), "regle": resume_court(z.get("resume")),
            "reference": resume_court(z.get("ref_reg"), 300), "fin": fin if fin and fin != "nan" else None,
            "periode": bool(_PERIODE.search(normaliser(z.get("resume")))),
        }
        if cle in par_contour:  # même contour pour plusieurs règles : une seule zone qui les liste toutes
            e = par_contour[cle]
            if regle not in e["properties"]["regles"]:
                e["properties"]["regles"].append(regle)
            if classe == "interdite":
                e["properties"].update(classe="interdite", grande=False)
            continue
        par_contour[cle] = {"type": "Feature", "properties": {"classe": classe, "grande": grande, "regles": [regle]},
                            "geometry": {"type": g["type"], "coordinates": coordonnees}}
    entites = list(par_contour.values())
    for e in entites:  # règle d'interdiction en premier
        e["properties"]["regles"].sort(key=lambda r: r["classe"] != "interdite")
    # Les zones interdites sont dessinées au-dessus des zones réglementées
    entites.sort(key=lambda e: e["properties"]["classe"] == "interdite")
    collection = {
        "type": "FeatureCollection",
        "source": "Zones réglementaires du CACEM, data.gouv.fr (licence ouverte)",
        "page_source": PAGE_SOURCE,
        "mis_a_jour_le": aujourd_hui.isoformat(),
        "features": entites,
    }
    return collection, revue


def index_emprises(collection: dict) -> dict:
    """Emprise [ouest, sud, est, nord] de chaque zone, dans l'ordre du fichier, arrondie vers l'extérieur."""
    import math

    def points(c):
        if isinstance(c[0], (int, float)):
            yield c
        else:
            for x in c:
                yield from points(x)

    boites = []
    for e in collection["features"]:
        xs, ys = zip(*points(e["geometry"]["coordinates"]))
        boites.append([math.floor(min(xs) * 1e4) / 1e4, math.floor(min(ys) * 1e4) / 1e4, math.ceil(max(xs) * 1e4) / 1e4, math.ceil(max(ys) * 1e4) / 1e4])
    return {"mis_a_jour_le": collection["mis_a_jour_le"], "boites": boites}


def lire_cacem(chemin: Path):
    import geopandas as gpd
    import pandas as pd
    import pyogrio

    morceaux = []
    for nom, _ in pyogrio.list_layers(chemin):
        if nom not in COUCHES_METROPOLE:
            continue
        g = gpd.read_file(chemin, layer=nom)
        g.insert(0, "couche_gpkg", nom)
        morceaux.append(g.to_crs(4326) if g.crs is not None else g.set_crs(4326))
    return gpd.GeoDataFrame(pd.concat(morceaux, ignore_index=True), crs=4326)


def telecharger(chemin: Path) -> None:
    import requests

    with requests.get(SOURCE, stream=True, timeout=600) as r:
        r.raise_for_status()
        with open(chemin, "wb") as f:
            for morceau in r.iter_content(1 << 20):
                f.write(morceau)


def main():
    racine = Path(__file__).resolve().parent.parent
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--sortie", default=str(racine / "app" / "zones" / "peche-sous-marine.geojson"))
    p.add_argument("--revue", default=None, help="fichier CSV listant chaque zone examinée et son classement")
    p.add_argument("--gpkg", default="/tmp/zones_cacem.gpkg")
    args = p.parse_args()

    gpkg = Path(args.gpkg)
    if not gpkg.exists():
        telecharger(gpkg)
    collection, revue = construire(lire_cacem(gpkg))
    if args.revue:
        import csv

        with open(args.revue, "w", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=list(revue[0]))
            w.writeheader()
            w.writerows(revue)
    sortie = Path(args.sortie)
    sortie.parent.mkdir(parents=True, exist_ok=True)
    try:
        ancien = json.loads(sortie.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        ancien = None
    if ancien and ancien.get("features") == collection["features"]:
        print("Aucune zone n'a changé : fichier inchangé")
        return
    sortie.write_text(json.dumps(collection, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    # Petit index des emprises : l'application ne télécharge le fichier complet que si un lieu tombe dans l'une d'elles
    sortie.with_name(sortie.stem + "-index.json").write_text(json.dumps(index_emprises(collection), separators=(",", ":")), encoding="utf-8")
    n = {c: sum(1 for e in collection["features"] if e["properties"]["classe"] == c) for c in ("interdite", "reglementee")}
    print(f"{n['interdite']} zones interdites, {n['reglementee']} réglementées, {sortie.stat().st_size / 1000:.0f} ko")


if __name__ == "__main__":
    main()
