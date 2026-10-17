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


def shom_tuiles():
    """Tuiles 256 px en EPSG:3857 pour chaque couche côtière, puis la composition utilisée par la carte."""
    import subprocess, json as js
    sortie = subprocess.run(["node", "--input-type=module", "-e",
                             "import { COUCHES_CARTE } from './app/js/bathymetrie.js'; console.log(JSON.stringify(COUCHES_CARTE.map((c) => c.couche)));"],
                            capture_output=True, text=True)
    couches = js.loads(sortie.stdout)
    url = "https://services.data.shom.fr/INSPIRE/wms/r"
    # tuile z12 au-dessus de Marseille et de Quiberon (EPSG:3857)
    emprises = {"marseille": "596000,5340000,606000,5350000", "quiberon": "-352000,6015000,-342000,6025000"}
    lignes = []
    def essai(nom_couches, emprise, styles=""):
        r = get(url, params={"SERVICE": "WMS", "VERSION": "1.3.0", "REQUEST": "GetMap", "LAYERS": nom_couches, "STYLES": styles,
                             "CRS": "EPSG:3857", "BBOX": emprise, "WIDTH": 256, "HEIGHT": 256, "FORMAT": "image/png", "TRANSPARENT": "true"})
        return f"HTTP {r.status_code} {r.headers.get('Content-Type')} {len(r.content)} o {r.text[:120] if r.status_code != 200 else ''}"
    for c in couches:
        lignes.append(f"{c} : {essai(c, emprises['marseille'])}")
    lignes.append(f"composition ({len(couches)}) : {essai(','.join(couches), emprises['marseille'])}")
    lignes.append(f"composition styles vides : {essai(','.join(couches), emprises['marseille'], ','.join([''] * len(couches)))}")
    for n in (2, 3, 4, 6, 8):
        lignes.append(f"{n} premières : {essai(','.join(couches[:n]), emprises['quiberon'])}")
    lignes.append(f"litto seules : {essai(','.join(c for c in couches if c.startswith('LITTO')), emprises['marseille'])}")
    annoter("Tuiles Shom", lignes)


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
