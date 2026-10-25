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
from pathlib import Path as _Chemin

sys.path.insert(0, str(_Chemin(__file__).resolve().parent.parent))
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


SORTIE = os.environ.get("DIAG_SORTIE", "diag")


def legendes():
    """Télécharge légendes, capacités et images d'exemple des couches bathymétriques du Shom (dossier diag/)."""
    from pathlib import Path

    dossier = Path(SORTIE)
    dossier.mkdir(exist_ok=True)
    url = "https://services.data.shom.fr/INSPIRE/wms/r"
    r = get(url, params={"service": "WMS", "request": "GetCapabilities", "version": "1.3.0"})
    (dossier / "capacites_wms_r.xml").write_text(r.text, encoding="utf-8")
    lignes = []
    for bloc in re.findall(r"<Layer>(.*?)</Layer>", r.text, re.S):
        nom = re.search(r"<Name>([^<]+)</Name>", bloc)
        if not nom or not re.search(r"LITTO3D_(BZH|FINISTR|LR|NAQ|PACA)|MNT_(ATL|MED)|MNT_COTIER_(ARCACHON|DETROIT|GIRONDE|GNB|ILE_DE_RE|MORBIHAN|PERTUIS)", nom.group(1)):
            continue
        for style, legende in re.findall(r"<Style>\s*<Name>([^<]+)</Name>.*?xlink:href=\"([^\"]+)\"", bloc, re.S):
            try:
                img = get(legende.replace("&amp;", "&"))
                fichier = dossier / f"legende_{nom.group(1)}_{style}.png"
                fichier.write_bytes(img.content)
                lignes.append(f"{nom.group(1)} / {style} : {legende} ({len(img.content)} octets)")
            except Exception as e:
                lignes.append(f"{nom.group(1)} / {style} : {type(e).__name__}")
    exemples = {
        "quiberon": (47.47, -3.17, ["MNT_ATL100m_HOMONIM_PBMA_3857_WMSR", "LITTO3D_BZH_2018_2021_PYR_3857_WMSR", "MNT_COTIER_MORBIHAN_TANDEM_20m_PBMA_3857_WMSR"]),
        "marseille": (43.21, 5.35, ["MNT_MED100m_GDL_CA_HOMONIM_PBMA_3857_WMSR", "LITTO3D_PACA_2015_PYR_3857_WMSR"]),
    }
    for lieu, (lat, lon, couches) in exemples.items():
        for couche in couches:
            d = 0.03
            img = get(url, params={"service": "WMS", "version": "1.3.0", "request": "GetMap", "layers": couche, "styles": "",
                                   "crs": "EPSG:4326", "bbox": f"{lat - d},{lon - d * 1.5},{lat + d},{lon + d * 1.5}",
                                   "width": 512, "height": 512, "format": "image/png", "transparent": "true"})
            (dossier / f"exemple_{lieu}_{couche}.png").write_bytes(img.content)
            lignes.append(f"exemple {lieu} {couche} : HTTP {img.status_code} {len(img.content)} octets")
    # Profondeur EMODnet sur une grille, pour comparer avec les couleurs
    pts = []
    for lieu, (lat, lon, _) in exemples.items():
        for i in range(7):
            for j in range(7):
                la, lo = lat - 0.03 + i * 0.01, lon - 0.045 + j * 0.015
                try:
                    v = get(f"https://rest.emodnet-bathymetry.eu/depth_sample?geom=POINT({lo} {la})", timeout=20).json()
                    pts.append(f"{lieu},{la:.4f},{lo:.4f},{v.get('avg')}")
                except Exception:
                    pts.append(f"{lieu},{la:.4f},{lo:.4f},")
    (dossier / "emodnet_grille.csv").write_text("lieu,lat,lon,profondeur\n" + "\n".join(pts), encoding="utf-8")
    annoter("Legendes", lignes)


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

    from prevision.sources import copernicus as cop

    fin = datetime.now(timezone.utc)
    debut = fin - timedelta(days=8)
    lignes = []
    for nom, (lat, lon) in {"ibi": (47.6208, -3.4523), "nws": (48.46, -5.1268), "med": (43.1608, 5.6029)}.items():
        jeu = cop.JEUX[nom]
        try:
            ds = copernicusmarine.open_dataset(dataset_id=jeu, variables=["TUR", "CHL"], minimum_longitude=lon - 0.02, maximum_longitude=lon + 0.02,
                                               minimum_latitude=lat - 0.02, maximum_latitude=lat + 0.02,
                                               start_datetime=debut.strftime("%Y-%m-%dT00:00:00"), end_datetime=fin.strftime("%Y-%m-%dT23:59:59"))
            tur = ds["TUR"].load()
            valides = tur.notnull().sum(dim=[d for d in tur.dims if d != "time"]).values.tolist()
            dates = [str(x)[:10] for x in tur["time"].values]
            lignes.append(f"{nom} {jeu} : {dict(tur.sizes)} ; pixels valides par jour {list(zip(dates, valides))} ; turbidité médiane {float(tur.median()):.2f} FNU")
        except Exception as e:
            lignes.append(f"{nom} {jeu} : {type(e).__name__} {str(e)[:300]}")
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


def supabase_projet():
    """État du projet Supabase avec la clé publique de app/js/config.js : connexion par e-mail, confirmation, tables."""
    from pathlib import Path

    texte = (Path(__file__).resolve().parent.parent / "app" / "js" / "config.js").read_text(encoding="utf-8")
    url = re.search(r'supabaseUrl: "([^"]*)"', texte).group(1).rstrip("/")
    cle = re.search(r'supabaseCleAnon: "([^"]*)"', texte).group(1)
    lignes = [f"projet {url}"]
    entetes = {"apikey": cle}
    try:
        r = requests.get(f"{url}/auth/v1/settings", headers=entetes, timeout=30)
        d = r.json()
        lignes.append(f"auth/settings HTTP {r.status_code} : e-mail activé={d.get('external', {}).get('email')}, "
                      f"confirmation automatique (Confirm email désactivé)={d.get('mailer_autoconfirm')}, "
                      f"inscriptions fermées={d.get('disable_signup')}")
    except Exception as e:
        lignes.append(f"auth/settings : {type(e).__name__} {e}")
    for table in ["profils", "spots_prives", "favoris", "rapports"]:
        try:
            r = requests.get(f"{url}/rest/v1/{table}?select=*&limit=1", headers=entetes, timeout=30)
            lignes.append(f"table {table} : HTTP {r.status_code} {r.text[:160]}")
        except Exception as e:
            lignes.append(f"table {table} : {type(e).__name__} {e}")
    try:
        r = requests.post(f"{url}/rest/v1/rpc/supprimer_mon_compte", headers={**entetes, "Content-Type": "application/json"}, json={}, timeout=30)
        lignes.append(f"fonction supprimer_mon_compte (sans compte) : HTTP {r.status_code} {r.text[:160]}")
    except Exception as e:
        lignes.append(f"rpc : {type(e).__name__} {e}")
    annoter("Projet Supabase", lignes)


def secrets():
    """Présence des secrets attendus (jamais leur valeur) et nature de la clé Supabase."""
    lignes = []
    for nom in ["SUPABASE_URL", "SUPABASE_SERVICE_KEY", "COPERNICUSMARINE_SERVICE_USERNAME", "COPERNICUSMARINE_SERVICE_PASSWORD"]:
        v = os.environ.get(nom, "")
        nature = ""
        if v and nom == "SUPABASE_SERVICE_KEY":
            nature = " (clé secrète sb_secret)" if v.startswith("sb_secret_") else " (clé publique : il faut la clé secrète)" if v.startswith("sb_publishable_") else " (ancienne clé JWT)" if v.startswith("eyJ") else " (format inattendu)"
        if v and nom == "SUPABASE_URL":
            nature = " (adresse https://…supabase.co)" if re.match(r"^https://[a-z0-9]+\.supabase\.co/?$", v.strip()) else " (format inattendu : espace ou caractère en trop ?)"
        lignes.append(f"{nom} : {'présent' + nature if v else 'ABSENT'}")
    autres = [k.replace("CANDIDAT_", "") for k, v in os.environ.items() if k.startswith("CANDIDAT_") and v]
    lignes.append(f"secrets aux noms voisins trouvés : {autres or 'aucun'}")
    url, cle = os.environ.get("SUPABASE_URL", "").strip(), os.environ.get("SUPABASE_SERVICE_KEY", "").strip()
    if url and cle:
        entetes = {"apikey": cle} if cle.startswith("sb_") else {"apikey": cle, "Authorization": f"Bearer {cle}"}
        r = requests.get(url.rstrip("/") + "/rest/v1/rapports?select=id&limit=1", headers=entetes, timeout=30)
        lignes.append(f"lecture des retours avec la clé secrète : HTTP {r.status_code}")
    annoter("Secrets", lignes)


def supabase_parcours():
    """Vraie inscription d'essai sur le projet : profil, spot privé, favori, retour, puis suppression du compte."""
    import time
    from pathlib import Path

    texte = (Path(__file__).resolve().parent.parent / "app" / "js" / "config.js").read_text(encoding="utf-8")
    url = re.search(r'supabaseUrl: "([^"]*)"', texte).group(1).rstrip("/")
    cle = re.search(r'supabaseCleAnon: "([^"]*)"', texte).group(1)
    secrete = os.environ.get("SUPABASE_SERVICE_KEY", "").strip()
    pub = {"apikey": cle, "Content-Type": "application/json"}
    lignes = []
    email = f"diagnostic-{int(time.time())}@kelvisi-test.fr"
    try:
        r = requests.post(f"{url}/auth/v1/signup", headers=pub, timeout=30, json={
            "email": email, "password": "Essai-kelvisi-2026",
            "data": {"prenom": "Essai", "departement": "29", "pratiques": ["chasse"], "tranche_age": "25-34", "accord_emails": False}})
        d = r.json()
        lignes.append(f"inscription : HTTP {r.status_code}, session {'oui' if d.get('access_token') else 'non'} {'' if r.ok else r.text[:200]}")
        jeton = d.get("access_token")
        if not jeton:
            raise RuntimeError("pas de session après inscription")
        moi = d["user"]["id"]
        auth = {**pub, "Authorization": f"Bearer {jeton}"}
        r = requests.get(f"{url}/rest/v1/profils?id=eq.{moi}&select=prenom,departement,pratiques,tranche_age,accord_emails", headers=auth, timeout=30)
        lignes.append(f"profil créé : HTTP {r.status_code} {r.text[:200]}")
        r = requests.post(f"{url}/rest/v1/spots_prives?on_conflict=proprietaire,id", timeout=30,
                          headers={**auth, "Prefer": "resolution=merge-duplicates,return=minimal"},
                          json=[{"id": "prive-essai", "proprietaire": moi, "nom": "Essai", "lat": 47.49, "lon": -3.2, "region": "atlantique",
                                 "orientation_deg": 270, "ouverture_deg": 90, "profondeur_m": 8, "fond": "roche"}])
        lignes.append(f"spot privé enregistré : HTTP {r.status_code} {r.text[:150]}")
        r = requests.get(f"{url}/rest/v1/spots_prives?select=id,nom", headers=auth, timeout=30)
        lignes.append(f"spot privé relu : HTTP {r.status_code} {r.text[:150]}")
        r = requests.get(f"{url}/rest/v1/spots_prives?select=id", headers=pub, timeout=30)
        lignes.append(f"spot privé sans compte (doit être refusé) : HTTP {r.status_code}")
        r = requests.post(f"{url}/rest/v1/favoris?on_conflict=proprietaire,point_id", timeout=30,
                          headers={**auth, "Prefer": "resolution=ignore-duplicates,return=minimal"}, json=[{"proprietaire": moi, "point_id": "ref-groix"}])
        lignes.append(f"favori : HTTP {r.status_code} {r.text[:150]}")
        r = requests.post(f"{url}/rest/v1/rapports", timeout=30, headers={**auth, "Prefer": "return=minimal"},
                          json={"spot_id": "diagnostic-essai", "visibilite_m": 5, "observe_le": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()), "appareil": "diagnostic", "version": "1"})
        lignes.append(f"retour terrain : HTTP {r.status_code} {r.text[:150]}")
        r = requests.post(f"{url}/rest/v1/rpc/supprimer_mon_compte", headers=auth, json={}, timeout=30)
        lignes.append(f"suppression du compte : HTTP {r.status_code} {r.text[:150]}")
        r = requests.post(f"{url}/auth/v1/token?grant_type=password", headers=pub, timeout=30, json={"email": email, "password": "Essai-kelvisi-2026"})
        lignes.append(f"connexion après suppression (doit échouer) : HTTP {r.status_code}")
    except Exception as e:
        lignes.append(f"arrêt : {type(e).__name__} {e}")
    if secrete:
        h = {"apikey": secrete} if secrete.startswith("sb_") else {"apikey": secrete, "Authorization": f"Bearer {secrete}"}
        r = requests.delete(f"{url}/rest/v1/rapports?spot_id=eq.diagnostic-essai", headers=h, timeout=30)
        lignes.append(f"nettoyage du retour d'essai : HTTP {r.status_code}")
    annoter("Parcours Supabase", lignes)


def copernicus_catalogue():
    """Catalogue complet des produits de couleur de l'eau (sans identifiants), dans diag/copernicus_catalogue.txt."""
    import copernicusmarine
    from pathlib import Path

    Path(SORTIE).mkdir(exist_ok=True)
    lignes = []
    cat = copernicusmarine.describe(contains=["OCEANCOLOUR"], disable_progress_bar=True)
    for p in cat.products:
        for ds in p.datasets:
            for v in ds.versions:
                for part in v.parts:
                    for svc in part.services:
                        variables = sorted({var.short_name for var in svc.variables})
                        coords = []
                        for var in svc.variables[:1]:
                            for c in var.coordinates:
                                if c.coordinate_id in ("time", "latitude", "longitude"):
                                    coords.append(f"{c.coordinate_id}[{getattr(c, 'minimum_value', None)}..{getattr(c, 'maximum_value', None)} pas {getattr(c, 'step', None)}]")
                        lignes.append(f"{p.product_id} | {ds.dataset_id} | {v.label} | {part.name} | {svc.service_name} | {variables} | {' '.join(coords)}")
    Path(SORTIE, "copernicus_catalogue.txt").write_text("\n".join(lignes), encoding="utf-8")
    hr = sorted({l.split(" | ")[1] for l in lignes if "_hr" in l.lower() or "-hr" in l.lower()})
    annoter("Catalogue Copernicus", [f"{len(lignes)} lignes", *hr[:40]])


def copernicus_identifiants():
    """Forme des identifiants Copernicus (jamais leur valeur) et essai de connexion, brut puis nettoyé."""
    import copernicusmarine

    u = os.environ.get("COPERNICUSMARINE_SERVICE_USERNAME", "")
    m = os.environ.get("COPERNICUSMARINE_SERVICE_PASSWORD", "")
    def forme(v, nom):
        return (f"{nom} : {len(v.strip())} caractères utiles, espaces ou retours à la ligne aux extrémités : "
                f"{'OUI' if v != v.strip() else 'non'}, contient @ : {'OUI' if '@' in v else 'non'}, "
                f"caractères non ASCII : {'OUI' if any(ord(c) > 127 for c in v) else 'non'}, "
                f"guillemets : {'OUI' if any(c in v for c in '\"\'«»') else 'non'}")
    lignes = [forme(u, "identifiant"), forme(m, "mot de passe") + f", 12 caractères ou plus : {'oui' if len(m.strip()) >= 12 else 'NON'}"]
    for nom, (uu, mm) in {"tel quel": (u, m), "nettoyé": (u.strip(), m.strip())}.items():
        try:
            ok = copernicusmarine.login(username=uu, password=mm, force_overwrite=True, check_credentials_valid=True)
            lignes.append(f"connexion {nom} : {'ACCEPTÉE' if ok else 'refusée'}")
        except Exception as e:
            lignes.append(f"connexion {nom} : {type(e).__name__} {str(e)[:200]}")
    annoter("Identifiants Copernicus", lignes)


def satellite_rayons():
    """Points sans image satellite : pixels d'eau disponibles selon le rayon autour du point (fichier diag/satellite_rayons.json)."""
    import json
    from pathlib import Path

    import copernicusmarine
    import numpy as np

    from prevision import charger_spots
    from prevision.sources import copernicus as cop

    Path(SORTIE).mkdir(exist_ok=True)
    spots = {s.id: s for s in charger_spots(Path(__file__).resolve().parent.parent / "spots" / "points.json")}
    ids = ["ref-ouessant", "ref-belle-ile", "ref-campomoro", "ref-cote-vermeille", "ref-baleines", "ref-quiberon"]
    rayons = [300, 500, 800, 1200, 2000]
    lignes, sortie = [], {}
    for pid in ids:
        s = spots[pid]
        m = 0.025
        try:
            ds = copernicusmarine.open_dataset(
                dataset_id=cop.JEUX[cop.bassin(s)], variables=["TUR"],
                minimum_longitude=s.lon - m * 1.5, maximum_longitude=s.lon + m * 1.5,
                minimum_latitude=s.lat - m, maximum_latitude=s.lat + m,
                start_datetime="2025-01-01T00:00:00", end_datetime="2026-10-15T23:59:59")
            tur = ds["TUR"].load()
            v = tur.values
            d = cop.distances_m(s.lat, s.lon, tur["latitude"].values, tur["longitude"].values)
            eau = np.isfinite(v).any(axis=0)  # pixel vu au moins une fois : de l'eau
            res = {}
            for r in rayons:
                disque = d <= r
                n_eau = int((eau & disque).sum())
                valides = np.isfinite(v[:, disque])
                part_tous = valides.mean(axis=1) if disque.any() else np.zeros(len(v))
                part_eau = valides[:, eau[disque]].mean(axis=1) if n_eau else np.zeros(len(v))
                jours_30_tous = int((part_tous >= 0.3).sum())
                jours_50_eau = int((part_eau >= 0.5).sum()) if n_eau else 0
                med = float(np.nanmedian(v[:, disque & eau])) if n_eau else None
                res[r] = {"pixels": int(disque.sum()), "pixels_eau": n_eau, "jours_30pct_tous": jours_30_tous,
                          "jours_50pct_eau": jours_50_eau, "turbidite_mediane": None if med is None else round(med, 2)}
            # Pixel d'eau le plus proche
            dist_eau = float(d[eau].min()) if eau.any() else None
            sortie[pid] = {"rayons": res, "eau_la_plus_proche_m": dist_eau, "jours": int(v.shape[0])}
            lignes.append(f"{pid} : eau la plus proche à {dist_eau if dist_eau is None else round(dist_eau)} m ; "
                          + " ; ".join(f"{r} m : {x['pixels_eau']}/{x['pixels']} px d'eau, {x['jours_30pct_tous']} j (règle actuelle), "
                                       f"{x['jours_50pct_eau']} j (50 % de l'eau), méd. {x['turbidite_mediane']}" for r, x in res.items()))
        except Exception as e:
            lignes.append(f"{pid} : {type(e).__name__} {str(e)[:200]}")
    Path(SORTIE, "satellite_rayons.json").write_text(json.dumps(sortie, indent=1), encoding="utf-8")
    annoter("Rayons satellite", lignes)


def placer_points():
    """Nouveaux points (spots/candidats.json) : profondeur EMODnet, direction du large, placement entre 6 et 15 m.

    Résultat dans diag/points_places.json (publié sur la branche « diagnostic »).
    """
    import json
    import math
    from concurrent.futures import ThreadPoolExecutor
    from pathlib import Path

    racine = Path(__file__).resolve().parent.parent
    candidats = json.loads((racine / "spots" / "candidats.json").read_text(encoding="utf-8"))
    Path(SORTIE).mkdir(exist_ok=True)
    http = requests.Session()

    def altitude(lat, lon):
        for _ in range(3):
            try:
                r = http.get("https://rest.emodnet-bathymetry.eu/depth_sample",
                             params={"geom": f"POINT({lon:.5f} {lat:.5f})"}, timeout=30)
                if r.status_code == 200:
                    v = r.json().get("avg")
                    return None if v is None else float(v)
            except Exception:
                pass
        return None

    # Convention vérifiée sur deux points connus : large de Quiberon (mer) et Rennes (terre)
    temoins = {"mer, large de Quiberon": altitude(47.45, -3.25), "terre, Rennes": altitude(48.11, -1.68)}
    signe = -1.0 if (temoins["mer, large de Quiberon"] or 0) < 0 else 1.0

    def profondeur(lat, lon):
        v = altitude(lat, lon)
        if v is None:
            return None
        d = signe * v
        return d if d > 0 else None

    def deplacer(lat, lon, azimut, metres):
        a = math.radians(azimut)
        return (lat + metres * math.cos(a) / 111_320.0, lon + metres * math.sin(a) / (111_320.0 * math.cos(math.radians(lat))))

    directions = [k * 22.5 for k in range(16)]

    def large_et_ouverture(lat, lon):
        rayons = {d: [profondeur(*deplacer(lat, lon, d, m)) for m in (800, 1500)] for d in directions}
        def score(d):
            return sum(rayons[(d + k * 22.5) % 360][1] or 0 for k in (-1, 0, 1))
        orientation = max(directions, key=score) if any(r[1] for r in rayons.values()) else None
        ouverture = max(45, min(180, 22.5 * sum(1 for d in directions if rayons[d][0] is not None)))
        return orientation, ouverture

    def traiter(c):
        lat, lon = c["lat"], c["lon"]
        p0 = profondeur(lat, lon)
        lat2, lon2, p2, deplace = lat, lon, p0, 0
        if p0 is None or not 5 <= p0 <= 18:
            # Le point d'eau le plus proche entre 5 et 18 m, dans toutes les directions, à 1,5 km au plus
            trouve = None
            for m in (150, 300, 500, 750, 1000, 1400):
                essais = []
                for d in directions:
                    la, lo = deplacer(lat, lon, d, m)
                    pr = profondeur(la, lo)
                    if pr is not None and 5 <= pr <= 18:
                        essais.append((abs(pr - 10), la, lo, pr))
                if essais:
                    trouve = min(essais)
                    deplace = m
                    break
            if trouve:
                _, lat2, lon2, p2 = trouve
        orientation, ouverture = large_et_ouverture(lat2, lon2)
        return {"id": c["id"], "nom": c["nom"], "depart": [lat, lon], "profondeur_depart": p0, "lat": round(lat2, 4), "lon": round(lon2, 4),
                "profondeur": p2, "deplace_m": deplace, "orientation_deg": orientation, "orientation_prevue": c.get("orientation_deg"),
                "ouverture_deg": ouverture}

    with ThreadPoolExecutor(max_workers=8) as pool:
        resultats = list(pool.map(traiter, candidats))
    Path(SORTIE, "points_places.json").write_text(json.dumps(resultats, ensure_ascii=False, indent=1), encoding="utf-8")
    annoter("EMODnet : convention", [f"{k} : {v}" for k, v in temoins.items()] + [f"profondeur = {signe:+.0f} × avg"])
    annoter("Placement des nouveaux points", [
        f"{r['id']} : {r['profondeur_depart']} m -> {r['profondeur']} m ({r['deplace_m']} m), large {r['orientation_deg']}° (prévu {r['orientation_prevue']}°), ouverture {r['ouverture_deg']}°"
        for r in resultats])


ZONES_RELIEF = {
    "quiberon": (47.475, -3.145),
    "crozon": (48.255, -4.62),
    "glenan": (47.715, -3.99),
    "marseille": (43.205, 5.345),
    "agde": (43.275, 3.51),
    "biarritz": (43.48, -1.565),
    "bonifacio": (41.385, 9.165),
    "etretat": (49.71, 0.19),
}


def relief():
    """Images du Shom (et d'EMODnet) autour de quelques spots, à la résolution des données et en tuile de 256 px,
    pour mettre au point la carte du relief sous-marin sans réseau (dossier diag/relief/)."""
    import json
    import math
    import subprocess
    import time
    from pathlib import Path

    sortie = subprocess.run(["node", "--input-type=module", "-e",
                             "import { SOURCES } from './app/js/bathymetrie.js'; console.log(JSON.stringify(SOURCES));"],
                            capture_output=True, text=True)
    sources = json.loads(sortie.stdout)
    dossier = Path(SORTIE) / "relief"
    dossier.mkdir(parents=True, exist_ok=True)
    url = "https://services.data.shom.fr/INSPIRE/wms/r"
    R = 6378137.0
    lignes, index = [], []

    def merc(lat, lon):
        return R * math.radians(lon), R * math.log(math.tan(math.pi / 4 + math.radians(lat) / 2))

    def wms(couche, bbox, n, extra=None):
        p = {"SERVICE": "WMS", "VERSION": "1.3.0", "REQUEST": "GetMap", "LAYERS": couche, "STYLES": "",
             "CRS": "EPSG:3857", "BBOX": ",".join(f"{v:.2f}" for v in bbox), "WIDTH": n, "HEIGHT": n,
             "FORMAT": "image/png", "TRANSPARENT": "true", **(extra or {})}
        t = time.time()
        r = get(url, params=p)
        return r, round(time.time() - t, 2)

    for zone, (lat, lon) in ZONES_RELIEF.items():
        x, y = merc(lat, lon)
        cote_sol = 3000.0
        cote = cote_sol / math.cos(math.radians(lat))  # côté en mètres Mercator
        bbox = (x - cote / 2, y - cote / 2, x + cote / 2, y + cote / 2)
        for s in sources:
            z = s["zone"]
            if "_4326_" in s["couche"] or not (z[0] <= lon <= z[2] and z[1] <= lat <= z[3]):
                continue
            natif = max(16, min(1024, round(cote_sol / s["pas"])))
            for n in sorted({natif, 256}):
                try:
                    r, duree = wms(s["couche"], bbox, n)
                    nom = f"{zone}_{s['type']}_{n}.png"
                    if r.ok and r.headers.get("Content-Type", "").startswith("image/png"):
                        (dossier / nom).write_bytes(r.content)
                    index.append({"zone": zone, "couche": s["couche"], "type": s["type"], "palette": s["palette"], "pas": s["pas"],
                                  "taille": n, "fichier": nom, "bbox_3857": bbox, "http": r.status_code, "duree_s": duree,
                                  "octets": len(r.content), "type_mime": r.headers.get("Content-Type")})
                    lignes.append(f"{zone} {s['type']} {n} px : HTTP {r.status_code} {len(r.content)} o en {duree} s")
                except Exception as e:
                    lignes.append(f"{zone} {s['type']} {n} px : {type(e).__name__} {e}")

    # Le Shom accepte-t-il une palette fournie (SLD_BODY) ? On demande un dégradé gris simple.
    sld = ('<?xml version="1.0" encoding="UTF-8"?><StyledLayerDescriptor version="1.0.0" xmlns="http://www.opengis.net/sld" '
           'xmlns:ogc="http://www.opengis.net/ogc"><NamedLayer><Name>{couche}</Name><UserStyle><FeatureTypeStyle><Rule>'
           '<RasterSymbolizer><ColorMap type="ramp"><ColorMapEntry color="#000000" quantity="-10"/>'
           '<ColorMapEntry color="#FFFFFF" quantity="100"/></ColorMap></RasterSymbolizer></Rule></FeatureTypeStyle>'
           '</UserStyle></NamedLayer></StyledLayerDescriptor>')
    lat, lon = ZONES_RELIEF["quiberon"]
    x, y = merc(lat, lon)
    c = 1500 / math.cos(math.radians(lat))
    bbox = (x - c, y - c, x + c, y + c)
    for couche in ["MNT_ATL100m_HOMONIM_PBMA_3857_WMSR", "LITTO3D_BZH_2018_2021_PYR_3857_WMSR"]:
        try:
            r, duree = wms(couche, bbox, 64, {"SLD_BODY": sld.replace("{couche}", couche)})
            (dossier / f"sld_{couche}.png").write_bytes(r.content)
            lignes.append(f"SLD_BODY {couche} : HTTP {r.status_code} {r.headers.get('Content-Type')} {len(r.content)} o {r.text[:150] if not r.ok else ''}")
        except Exception as e:
            lignes.append(f"SLD_BODY {couche} : {type(e).__name__} {e}")

    # EMODnet : valeurs brutes (WCS) et palette fournie (WMS GeoServer)
    lat, lon = ZONES_RELIEF["quiberon"]
    for nom, u, p in [
        ("wcs_capacites", "https://ows.emodnet-bathymetry.eu/wcs", {"service": "WCS", "request": "GetCapabilities", "version": "2.0.1"}),
        ("wcs_tiff", "https://ows.emodnet-bathymetry.eu/wcs", {"service": "WCS", "request": "GetCoverage", "version": "2.0.1",
                                                                "coverageId": "emodnet__mean", "format": "image/tiff",
                                                                "subset": [f"Lat({lat - 0.03},{lat + 0.03})", f"Long({lon - 0.045},{lon + 0.045})"]}),
        ("wcs_arcgrid", "https://ows.emodnet-bathymetry.eu/wcs", {"service": "WCS", "request": "GetCoverage", "version": "2.0.1",
                                                                   "coverageId": "emodnet__mean", "format": "application/x-ogc-aaigrid",
                                                                   "subset": [f"Lat({lat - 0.03},{lat + 0.03})", f"Long({lon - 0.045},{lon + 0.045})"]}),
        ("wms_sld", "https://ows.emodnet-bathymetry.eu/wms", {"service": "WMS", "version": "1.1.1", "request": "GetMap", "layers": "emodnet:mean",
                                                              "styles": "", "srs": "EPSG:4326", "bbox": f"{lon - 0.045},{lat - 0.03},{lon + 0.045},{lat + 0.03}",
                                                              "width": 64, "height": 64, "format": "image/png",
                                                              "sld_body": sld.replace("{couche}", "emodnet:mean")}),
    ]:
        try:
            t = time.time()
            r = get(u, params=p)
            duree = round(time.time() - t, 2)
            ext = {"wcs_capacites": "xml", "wcs_tiff": "tif", "wcs_arcgrid": "asc", "wms_sld": "png"}[nom]
            (dossier / f"emodnet_{nom}.{ext}").write_bytes(r.content)
            extrait = r.text[:200] if ("xml" in r.headers.get("Content-Type", "") or "text" in r.headers.get("Content-Type", "")) else ""
            if nom == "wcs_capacites":
                extrait = str(re.findall(r"<wcs:CoverageId>([^<]+)<", r.text)[:20])
            lignes.append(f"EMODnet {nom} : HTTP {r.status_code}, {r.headers.get('Content-Type')}, {len(r.content)} o en {duree} s, CORS {cors(r)} {extrait}")
        except Exception as e:
            lignes.append(f"EMODnet {nom} : {type(e).__name__} {e}")

    (dossier / "index.json").write_text(json.dumps(index, indent=1), encoding="utf-8")
    annoter("Relief", lignes)


def temperature_fond():
    """Prévisions de température en profondeur (Copernicus Marine, modèles physiques IBI, NWS, MED) :
    jeux disponibles, profondeurs, valeurs et temps d'extraction pour quelques points (diag/temperature.json)."""
    import json
    import time
    from datetime import datetime, timedelta, timezone
    from pathlib import Path

    import copernicusmarine
    import numpy as np

    Path(SORTIE).mkdir(exist_ok=True)
    lignes, sortie = [], {"jeux": [], "essais": []}
    for produit in ["IBI_ANALYSISFORECAST_PHY_005_001", "NWSHELF_ANALYSISFORECAST_PHY_004_013", "MEDSEA_ANALYSISFORECAST_PHY_006_013"]:
        try:
            cat = copernicusmarine.describe(product_id=produit, disable_progress_bar=True)
        except TypeError:
            cat = copernicusmarine.describe(contains=[produit], disable_progress_bar=True)
        except Exception as e:
            lignes.append(f"{produit} : {type(e).__name__} {str(e)[:200]}")
            continue
        for p in cat.products:
            for ds in p.datasets:
                variables, profondeur = set(), ""
                for v in ds.versions[:1]:
                    for part in v.parts[:1]:
                        for svc in part.services[:1]:
                            for var in svc.variables:
                                variables.add(var.short_name)
                                for c in var.coordinates:
                                    if c.coordinate_id in ("depth", "elevation") and not profondeur:
                                        vals = getattr(c, "values", None)
                                        profondeur = f"{c.coordinate_id} {list(vals)[:12] if vals else (getattr(c, 'minimum_value', None), getattr(c, 'maximum_value', None))}"
                sortie["jeux"].append({"produit": p.product_id, "jeu": ds.dataset_id, "variables": sorted(variables), "profondeur": profondeur})
                if "thetao" in variables:
                    lignes.append(f"{ds.dataset_id} : {profondeur[:160]}")

    maintenant = datetime.now(timezone.utc)
    points = {"quiberon": (47.47, -3.17, 12), "glenan": (47.72, -4.0, 8), "etretat": (49.71, 0.19, 10), "biarritz": (43.48, -1.57, 10),
              "marseille": (43.21, 5.35, 15), "bonifacio": (41.38, 9.17, 12)}
    candidats = [j for j in sortie["jeux"] if "thetao" in j["variables"] and "P1D" in j["jeu"] and ("3D" in j["jeu"] or "tem" in j["jeu"])]
    for j in candidats:
        med = "med" in j["jeu"].lower()
        zone = (2.9, 41.3, 9.7, 43.8) if med else (-5.5, 43.3, 2.6, 51.2)
        try:
            t0 = time.time()
            ds = copernicusmarine.open_dataset(
                dataset_id=j["jeu"], variables=["thetao"], minimum_longitude=zone[0], maximum_longitude=zone[2],
                minimum_latitude=zone[1], maximum_latitude=zone[3], minimum_depth=0, maximum_depth=40,
                start_datetime=(maintenant - timedelta(days=1)).strftime("%Y-%m-%dT00:00:00"),
                end_datetime=(maintenant + timedelta(days=5)).strftime("%Y-%m-%dT00:00:00"))
            ouvert = time.time() - t0
            th = ds["thetao"]
            res = {"jeu": j["jeu"], "dims": {k: int(v) for k, v in th.sizes.items()}, "temps": [str(x)[:10] for x in th["time"].values],
                   "profondeurs": [round(float(x), 2) for x in th["depth"].values], "ouverture_s": round(ouvert, 1), "points": {}}
            for nom, (lat, lon, prof) in points.items():
                if (lon > 2.8) != med:
                    continue
                t1 = time.time()
                autour = th.sel(latitude=slice(lat - 0.08, lat + 0.08), longitude=slice(lon - 0.12, lon + 0.12)).load()
                v = autour.values  # temps, profondeur, lat, lon
                la, lo = autour["latitude"].values, autour["longitude"].values
                d2 = (la[:, None] - lat) ** 2 + ((lo[None, :] - lon) * np.cos(np.radians(lat))) ** 2
                profs = autour["depth"].values
                k = int(np.argmin(np.abs(profs - prof)))
                valide = np.isfinite(v[0, k])
                if not valide.any():
                    res["points"][nom] = "aucune maille d'eau à cette profondeur"
                    continue
                i, jj = np.unravel_index(np.argmin(np.where(valide, d2, np.inf)), d2.shape)
                profil = v[0, :, i, jj]
                res["points"][nom] = {"maille": [round(float(la[i]), 4), round(float(lo[jj]), 4)], "distance_km": round(float(np.sqrt(d2[i, jj])) * 111.2, 2),
                                      "profondeur_m": round(float(profs[k]), 1), "par_jour": [round(float(x), 2) for x in v[:, k, i, jj]],
                                      "profil_jour1": {round(float(p), 1): (None if not np.isfinite(x) else round(float(x), 2)) for p, x in zip(profs, profil)},
                                      "extraction_s": round(time.time() - t1, 1)}
            sortie["essais"].append(res)
            lignes.append(f"{j['jeu']} : {res['dims']}, ouvert en {res['ouverture_s']} s ; " + " ; ".join(
                f"{n} {p['par_jour'][:3] if isinstance(p, dict) else p}" for n, p in res["points"].items()))
        except Exception as e:
            lignes.append(f"{j['jeu']} : {type(e).__name__} {str(e)[:300]}")
    Path(SORTIE, "temperature.json").write_text(json.dumps(sortie, ensure_ascii=False, indent=1), encoding="utf-8")
    annoter("Température en profondeur", lignes)


def temperature_points():
    """Profils de température de tous les points Kelvisi avec le module réel (prevision/sources/temperature.py)."""
    import json
    import time
    from pathlib import Path

    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
    from prevision import charger_spots
    from prevision.sources import temperature

    spots = charger_spots(str(Path(__file__).resolve().parent.parent / "spots" / "points.json"))
    t0 = time.time()
    res = temperature.recuperer(spots, int(time.time()))
    duree = time.time() - t0
    Path(SORTIE).mkdir(exist_ok=True)
    Path(SORTIE, "temperatures_points.json").write_text(json.dumps(res, ensure_ascii=False), encoding="utf-8")
    pts = res["points"]
    manquants = [s.id for s in spots if s.id not in pts]
    lignes = [f"{len(pts)} points sur {len(spots)} en {duree:.0f} s, jeux {res['jeux']}, erreurs {res['erreurs']}",
              f"sans profil : {manquants}",
              f"taille JSON : {len(json.dumps(pts, separators=(',', ':'))) / 1000:.0f} ko"]
    dist = sorted(p["distance_km"] for p in pts.values())
    if dist:
        lignes.append(f"distance de la maille de surface : médiane {dist[len(dist) // 2]} km, max {dist[-1]} km")
    courts = [(i, p["profondeurs"][-1], s.profondeur_m) for s in spots for i, p in [(s.id, pts.get(s.id))] if p and p["profondeurs"][-1] < s.profondeur_m]
    lignes.append(f"profil moins profond que le spot : {courts}")
    for i, p in list(pts.items())[::8]:
        lignes.append(f"{i} : surface {p['valeurs'][0][0]} °C, {p['profondeur_m']} m {p['au_fond']} (profil jusqu'à {p['profondeurs'][-1]} m, {p['distance_km']} km)")
    annoter("Température des points", lignes)


def zones_cacem():
    """Zones réglementaires du CACEM (data.gouv.fr) : structure du fichier (toutes les couches) et zones de
    métropole qui parlent de pêche sous-marine ou d'interdiction de pêche (diag/zones/)."""
    import json
    import re as _re
    import subprocess
    import time
    from pathlib import Path

    subprocess.run([sys.executable, "-m", "pip", "install", "-q", "geopandas", "pyogrio", "shapely"], check=True)
    import geopandas as gpd
    import pandas as pd
    import pyogrio

    dossier = Path(SORTIE) / "zones"
    dossier.mkdir(parents=True, exist_ok=True)
    gpkg = Path("/tmp/zones_cacem.gpkg")
    lignes = []
    try:
        t0 = time.time()
        with requests.get("https://www.data.gouv.fr/api/1/datasets/r/dd48b545-a1d1-4710-9e56-415b895f5336", stream=True, timeout=600) as r:
            r.raise_for_status()
            with open(gpkg, "wb") as f:
                for morceau in r.iter_content(1 << 20):
                    f.write(morceau)
        lignes.append(f"téléchargé {gpkg.stat().st_size / 1e6:.0f} Mo en {time.time() - t0:.0f} s")
        couches = pyogrio.list_layers(gpkg)
        (dossier / "couches.txt").write_text("\n".join(f"{c[0]}\t{c[1]}" for c in couches), encoding="utf-8")
        lignes.append(f"{len(couches)} couches : {[c[0] for c in couches][:40]}")
        morceaux = []
        for nom, _ in couches:
            try:
                a = pyogrio.read_dataframe(gpkg, layer=nom, read_geometry=False)
            except Exception as e:
                lignes.append(f"couche {nom} illisible : {type(e).__name__}")
                continue
            a.insert(0, "couche_gpkg", nom)
            morceaux.append(a)
        attributs = pd.concat(morceaux, ignore_index=True)
        lignes.append(f"{len(attributs)} zones ; colonnes {list(attributs.columns)}")
        for col in ("couche_gpkg", "plan", "facade", "type", "layer_name", "thematique", "thematiques", "tags"):
            if col in attributs:
                (dossier / f"valeurs_{col}.txt").write_text(attributs[col].astype("string").fillna("").value_counts().to_string(), encoding="utf-8")
        champs = [c for c in ("layer_name", "ref_reg", "resume", "obs", "poly_name", "type", "thematique", "tags") if c in attributs]
        texte = attributs[champs].astype("string").fillna("").agg(" | ".join, axis=1)
        motif = _re.compile(r"sous[- ]marin|chasse|harpon|toute (forme de )?p[êe]che|tout pr[ée]l[èe]vement|non[- ]pr[ée]l[èe]vement|interdiction de (la )?p[êe]che|cantonnement|r[ée]serve int[ée]grale|protection (forte|renforc)", _re.I)
        garde = texte.str.contains(motif)
        lignes.append(f"{int(garde.sum())} zones citent la pêche sous-marine ou une interdiction de pêche")
        sel = attributs[garde]
        (dossier / "zones_retenues.csv").write_text(sel.to_csv(index=False), encoding="utf-8")
        geos = []
        for nom in sel["couche_gpkg"].unique():
            g = gpd.read_file(gpkg, layer=nom)
            g.insert(0, "couche_gpkg", nom)
            g = g.loc[garde[attributs["couche_gpkg"] == nom].values]
            if g.crs is not None:
                g = g.to_crs(4326)
            geos.append(g)
        if geos:
            geo = gpd.GeoDataFrame(pd.concat(geos, ignore_index=True), crs=4326)
            b = geo.geometry.bounds
            geo = geo[(b["minx"] > -6) & (b["maxx"] < 10) & (b["miny"] > 41) & (b["maxy"] < 51.5)]
            geo["geometry"] = geo.geometry.simplify(0.0002, preserve_topology=True)
            geo.to_file(dossier / "zones_retenues.geojson", driver="GeoJSON")
            lignes.append(f"GeoJSON : {(dossier / 'zones_retenues.geojson').stat().st_size / 1e6:.1f} Mo, {len(geo)} zones en métropole")
            for _, z in geo.head(30).iterrows():
                lignes.append(" · ".join(str(z.get(c, ""))[:80] for c in ("couche_gpkg", "layer_name", "type", "ref_reg") if c in z))
    finally:
        annoter("Zones CACEM", lignes)


def zones_kelvisi():
    """Fichier des zones de pêche sous-marine produit par outils/zones_reglementees.py, avec la liste de revue
    et les points Kelvisi situés dans une zone (diag/zones/)."""
    import csv
    import json
    import subprocess
    from pathlib import Path

    subprocess.run([sys.executable, "-m", "pip", "install", "-q", "geopandas", "pyogrio", "shapely"], check=True)
    from shapely.geometry import Point, shape

    racine = Path(__file__).resolve().parent.parent
    dossier = Path(SORTIE) / "zones"
    dossier.mkdir(parents=True, exist_ok=True)
    r = subprocess.run([sys.executable, str(racine / "outils" / "zones_reglementees.py"), "--sortie", str(dossier / "peche-sous-marine.geojson"),
                        "--revue", str(dossier / "revue.csv")], capture_output=True, text=True)
    lignes = [r.stdout.strip(), r.stderr.strip()[-1500:]]
    if r.returncode:
        annoter("Zones Kelvisi", lignes)
        return
    revue = list(csv.DictReader(open(dossier / "revue.csv", encoding="utf-8")))
    ecartees = [z for z in revue if z["classe"] and z["retenue"] == "False"]
    lignes.append(f"{len(revue)} zones examinées ; écartées : " + "; ".join(f"{z['nom'][:50]} ({z['motif']})" for z in ecartees)[:1500])
    zones = json.load(open(dossier / "peche-sous-marine.geojson", encoding="utf-8"))
    formes = [(shape(f["geometry"]), f["properties"]) for f in zones["features"]]
    points = json.load(open(racine / "spots" / "points.json", encoding="utf-8"))
    dedans = []
    for pt in points:
        for g, prop in formes:
            if g.contains(Point(pt["lon"], pt["lat"])):
                dedans.append(f"{pt['id']} dans « {prop['nom'][:60]} » ({prop['classe']})")
    lignes.append(f"points Kelvisi dans une zone : {dedans or 'aucun'}")
    annoter("Zones Kelvisi", lignes)


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
