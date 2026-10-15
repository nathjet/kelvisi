"""Diagnostic des services en ligne, lancé à la main depuis GitHub Actions (workflow « Diagnostic »).

Chaque test écrit une annotation lisible dans le résumé du lancement. Sert à
vérifier des services injoignables depuis l'espace de développement : Shom,
Géoplateforme, EMODnet, Copernicus Marine, Supabase.

Usage : python outils/diagnostic.py [shom] [geopf] [emodnet] [copernicus] [supabase]
"""

from __future__ import annotations

import os
import re
import sys
import traceback

import requests

ORIGINE = "https://nathjet.github.io"
POINT = (47.4892, -3.1565)  # Quiberon, côte sauvage


def annoter(titre: str, lignes) -> None:
    texte = "\n".join(str(x) for x in lignes)[:3800]
    texte = texte.replace("%", "%25").replace("\r", "").replace("\n", "%0A")
    print(f"::notice title={titre}::{texte}", flush=True)


def get(url, **kw):
    kw.setdefault("timeout", 60)
    entetes = kw.pop("headers", {})
    entetes.setdefault("Origin", ORIGINE)
    return requests.get(url, headers=entetes, **kw)


def cors(r) -> str:
    return r.headers.get("Access-Control-Allow-Origin", "absent")


def couches_wms(xml: str) -> list[str]:
    return re.findall(r"<Layer[^>]*>\s*<Name>([^<]+)</Name>", xml)


def shom():
    lignes = []
    for url in ["https://services.data.shom.fr/INSPIRE/wms/r", "https://services.data.shom.fr/INSPIRE/wms/v"]:
        try:
            r = get(url, params={"service": "WMS", "request": "GetCapabilities", "version": "1.3.0"})
            noms = couches_wms(r.text)
            interessantes = [n for n in noms if re.search(r"LITTO|MNT|HOMONIM|BATHY|SONDE|ISOBATH", n, re.I)]
            lignes += [f"{url} : HTTP {r.status_code}, CORS {cors(r)}, {len(noms)} couches, dont {len(interessantes)} bathy",
                       *interessantes[:60]]
        except Exception as e:
            lignes.append(f"{url} : {type(e).__name__} {e}")
    for url in ["https://services.data.shom.fr/INSPIRE/wmts", "https://services.data.shom.fr/clevisu/wmts"]:
        try:
            r = get(url, params={"service": "WMTS", "request": "GetCapabilities"})
            ids = re.findall(r"<ows:Identifier>([^<]+)</ows:Identifier>", r.text)
            bathy = [i for i in ids if re.search(r"LITTO|MNT|HOMONIM|BATHY", i, re.I)]
            lignes += [f"{url} : HTTP {r.status_code}, CORS {cors(r)}, {len(ids)} identifiants, bathy : {bathy[:30]}"]
        except Exception as e:
            lignes.append(f"{url} : {type(e).__name__} {e}")
    annoter("Shom", lignes)


def shom_point(couche: str, url="https://services.data.shom.fr/INSPIRE/wms/r"):
    """Valeur d'une couche au point, et image : formats acceptés et en-têtes CORS."""
    lat, lon = POINT
    d = 0.002
    lignes = []
    base = {"service": "WMS", "version": "1.3.0", "layers": couche, "crs": "EPSG:4326",
            "bbox": f"{lat - d},{lon - d},{lat + d},{lon + d}", "width": 101, "height": 101, "styles": ""}
    for fmt in ["text/plain", "application/json", "text/html", "application/vnd.ogc.gml"]:
        try:
            r = get(url, params={**base, "request": "GetFeatureInfo", "query_layers": couche, "info_format": fmt, "i": 50, "j": 50,
                                 "format": "image/png"})
            lignes.append(f"GetFeatureInfo {fmt} : HTTP {r.status_code}, CORS {cors(r)}, {r.text[:300]!r}")
        except Exception as e:
            lignes.append(f"GetFeatureInfo {fmt} : {type(e).__name__} {e}")
    for fmt in ["image/png", "image/x-bil;bits=32", "image/tiff", "image/geotiff"]:
        try:
            r = get(url, params={**base, "request": "GetMap", "format": fmt, "width": 5, "height": 5})
            extrait = ""
            if "bil" in fmt and r.ok:
                import numpy as np
                extrait = f" octets {r.content[:24].hex()} | uint8 {list(r.content[:20])} | >f4 {np.frombuffer(r.content, dtype='>f4')[:8].round(2).tolist()}"
            elif not r.ok:
                extrait = " " + r.text[:200]
            lignes.append(f"GetMap {fmt} : HTTP {r.status_code}, type {r.headers.get('Content-Type')}, {len(r.content)} octets, CORS {cors(r)}{extrait}")
        except Exception as e:
            lignes.append(f"GetMap {fmt} : {type(e).__name__} {e}")
    annoter(f"Shom point {couche}"[:60], lignes)


def shom_couche(couche: str, url="https://services.data.shom.fr/INSPIRE/wms/r"):
    """Bloc XML de la couche dans GetCapabilities : interrogeable, styles, emprise, échelles."""
    r = get(url, params={"service": "WMS", "request": "GetCapabilities", "version": "1.3.0"})
    i = r.text.find(f"<Name>{couche}</Name>")
    debut = r.text.rfind("<Layer", 0, i)
    fin = r.text.find("</Layer>", i)
    bloc = re.sub(r"\s+", " ", r.text[debut:fin])
    annoter(f"Couche {couche}"[:60], [bloc[:3000]])


def wcs():
    lignes = []
    for url in ["https://services.data.shom.fr/INSPIRE/wcs", "https://services.data.shom.fr/wcs", "https://data.geopf.fr/wcs"]:
        for version in ["2.0.1", "1.0.0"]:
            try:
                r = get(url, params={"service": "WCS", "request": "GetCapabilities", "version": version})
                ids = re.findall(r"<(?:wcs:CoverageId|wcs:Identifier|name|CoverageId)>([^<]+)<", r.text)
                bathy = [i for i in ids if re.search(r"LITTO|MNT|HOMONIM|BATHY|ELEVATION", i, re.I)]
                lignes.append(f"{url} v{version} : HTTP {r.status_code}, CORS {cors(r)}, {len(ids)} couvertures, utiles {bathy[:25]} | {r.text[:160]!r}")
            except Exception as e:
                lignes.append(f"{url} v{version} : {type(e).__name__} {e}")
    annoter("WCS", lignes)


def geopf():
    lignes = []
    for url, params in [("https://data.geopf.fr/wmts", {"SERVICE": "WMTS", "REQUEST": "GetCapabilities"}),
                        ("https://data.geopf.fr/wms-r", {"SERVICE": "WMS", "REQUEST": "GetCapabilities", "VERSION": "1.3.0"})]:
        try:
            r = get(url, params=params)
            ids = re.findall(r"<(?:ows:Identifier|Name)>([^<]+)</(?:ows:Identifier|Name)>", r.text)
            bathy = sorted({i for i in ids if re.search(r"LITTO|BATHY|MNT|ELEVATION", i, re.I)})
            lignes.append(f"{url} : HTTP {r.status_code}, CORS {cors(r)}, {len(ids)} noms, utiles : {bathy[:40]}")
        except Exception as e:
            lignes.append(f"{url} : {type(e).__name__} {e}")
    try:
        r = get("https://data.geopf.fr/altimetrie/1.0/calcul/alti/rest/elevation.json",
                params={"lon": POINT[1], "lat": POINT[0], "resource": "ign_rge_alti_wld", "zonly": "true"})
        lignes.append(f"altimétrie IGN au point : HTTP {r.status_code}, CORS {cors(r)}, {r.text[:200]}")
    except Exception as e:
        lignes.append(f"altimétrie : {type(e).__name__} {e}")
    annoter("Geoplateforme", lignes)


def emodnet():
    lignes = []
    for url in [f"https://rest.emodnet-bathymetry.eu/depth_sample?geom=POINT({POINT[1]} {POINT[0]})",
                "https://tiles.emodnet-bathymetry.eu/latest/mean_atlas_land/web_mercator/8/125/89.png"]:
        try:
            r = get(url)
            lignes.append(f"{url} : HTTP {r.status_code}, CORS {cors(r)}, {r.text[:150] if 'json' in r.headers.get('Content-Type', '') else len(r.content)}")
        except Exception as e:
            lignes.append(f"{url} : {type(e).__name__} {e}")
    annoter("EMODnet", lignes)


def copernicus():
    if not os.environ.get("COPERNICUSMARINE_SERVICE_USERNAME"):
        annoter("Copernicus", ["Secrets COPERNICUSMARINE_SERVICE_USERNAME / PASSWORD absents"])
        return
    import copernicusmarine

    lignes = []
    for motif in ["OCEANCOLOUR_ATL_BGC_L3_NRT", "OCEANCOLOUR_MED_BGC_L3_NRT", "HR_L3_NRT", "OCEANCOLOUR_IBI", "HROC"]:
        try:
            cat = copernicusmarine.describe(contains=[motif], disable_progress_bar=True)
            for p in cat.products:
                for ds in p.datasets:
                    variables = set()
                    for v in ds.versions:
                        for part in v.parts:
                            for svc in part.services:
                                for var in svc.variables:
                                    variables.add(var.short_name)
                    lignes.append(f"{p.product_id} | {ds.dataset_id} | {sorted(variables)[:12]}")
        except Exception as e:
            lignes.append(f"describe {motif} : {type(e).__name__} {str(e)[:200]}")
    annoter("Copernicus catalogue", lignes[:70])

    from datetime import datetime, timedelta, timezone

    fin = datetime.now(timezone.utc)
    debut = fin - timedelta(days=6)
    lat, lon = POINT
    essais = [(os.environ.get("KELVISI_SAT_ATL_TRANSP") or "cmems_obs-oc_atl_bgc-transp_nrt_l3-olci-300m_P1D", "SPM"),
              (os.environ.get("KELVISI_SAT_ATL_PLANCTON") or "cmems_obs-oc_atl_bgc-plankton_nrt_l3-olci-300m_P1D", "CHL")]
    lignes = []
    for jeu, var in essais:
        try:
            ds = copernicusmarine.open_dataset(dataset_id=jeu, variables=[var], minimum_longitude=lon - 0.05, maximum_longitude=lon + 0.05,
                                               minimum_latitude=lat - 0.05, maximum_latitude=lat + 0.05,
                                               start_datetime=debut.strftime("%Y-%m-%dT00:00:00"), end_datetime=fin.strftime("%Y-%m-%dT23:59:59"))
            da = ds[var].load()
            valides = da.notnull().sum(dim=[d for d in da.dims if d != "time"]).values.tolist()
            lignes.append(f"{jeu} {var} : dims {dict(da.sizes)}, pixels valides par jour {valides}, médiane {float(da.median()):.3f}")
        except Exception as e:
            lignes.append(f"{jeu} {var} : {type(e).__name__} {str(e)[:300]}")
    annoter("Copernicus donnees", lignes)


def supabase():
    url, cle = os.environ.get("SUPABASE_URL"), os.environ.get("SUPABASE_SERVICE_KEY")
    if not url or not cle:
        annoter("Supabase", ["Secrets SUPABASE_URL / SUPABASE_SERVICE_KEY absents"])
        return
    lignes = []
    entetes = {"apikey": cle} if cle.startswith("sb_") else {"apikey": cle, "Authorization": f"Bearer {cle}"}
    for chemin in ["/auth/v1/settings", "/rest/v1/profils?select=id&limit=1", "/rest/v1/rapports?select=id&limit=1",
                   "/rest/v1/spots_prives?select=id&limit=1", "/rest/v1/favoris?select=point_id&limit=1"]:
        try:
            r = requests.get(url.rstrip("/") + chemin, headers=entetes, timeout=30)
            lignes.append(f"{chemin} : HTTP {r.status_code} {r.text[:300]}")
        except Exception as e:
            lignes.append(f"{chemin} : {type(e).__name__} {e}")
    annoter("Supabase", lignes)


def main():
    choix = sys.argv[1:] or ["shom", "geopf", "emodnet", "copernicus", "supabase"]
    for nom in choix:
        try:
            if ":" in nom:  # shom_point:COUCHE
                fonction, argument = nom.split(":", 1)
                globals()[fonction](argument)
            else:
                globals()[nom]()
        except Exception:
            annoter(f"Erreur {nom}", [traceback.format_exc()[-1500:]])


if __name__ == "__main__":
    main()
