"""Vérifie l'application dans un vrai navigateur (Chromium), avec l'accès à internet de GitHub Actions.

Captures d'écran de la carte (plan, profondeurs, vue aérienne), lecture des profondeurs du Shom
dans la page, recherche de lieux. Résultats dans diag/ (publiés sur la branche « diagnostic »).

Usage : python outils/navigateur_diag.py
"""

from __future__ import annotations

import asyncio
import functools
import http.server
import json
import threading
from pathlib import Path

RACINE = Path(__file__).resolve().parent.parent
SORTIE = RACINE / "diag"
PORT = 8123

POINTS = {
    "quiberon": (47.47, -3.17),
    "groix_sud": (47.62, -3.45),
    "marseille_calanques": (43.21, 5.35),
    "biarritz": (43.4862, -1.571),
    "etretat": (49.7152, 0.1901),
    "ajaccio": (41.8785, 8.5893),
    "cap_ferrat": (43.6725, 7.33),
}


def serveur():
    gestion = functools.partial(http.server.SimpleHTTPRequestHandler, directory=str(RACINE / "app"))
    httpd = http.server.ThreadingHTTPServer(("127.0.0.1", PORT), gestion)
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    return httpd


def annoter(titre, lignes):
    texte = "\n".join(str(x) for x in lignes)[:3800].replace("%", "%25").replace("\n", "%0A")
    print(f"::notice title={titre}::{texte}", flush=True)


async def main():
    from playwright.async_api import async_playwright

    SORTIE.mkdir(exist_ok=True)
    serveur()
    resultats = {}
    async with async_playwright() as p:
        navigateur = await p.chromium.launch()
        ctx = await navigateur.new_context(viewport={"width": 390, "height": 844}, device_scale_factor=2, is_mobile=True, has_touch=True)
        page = await ctx.new_page()
        erreurs = []
        page.on("pageerror", lambda e: erreurs.append(str(e)))
        page.on("console", lambda m: erreurs.append(f"console {m.type}: {m.text}") if m.type in ("error", "warning") and "GPU stall" not in m.text else None)
        page.on("requestfailed", lambda r: erreurs.append(f"échec {r.url[:160]} {r.failure}") if "ERR_ABORTED" not in (r.failure or "") else None)
        shom = []
        page.on("response", lambda r: shom.append(f"{r.status} {r.headers.get('content-type')} {r.url[:200]}") if "data.shom.fr" in r.url and "GetMap" in r.url and "WIDTH=256" in r.url else None)

        await page.goto(f"http://127.0.0.1:{PORT}/#/carte")
        await page.wait_for_timeout(4000)

        # Comptes ouverts : vraie inscription d'essai par l'écran d'accueil (compte supprimé à la fin)
        compte_essai = False
        if await page.is_visible("#ecran-compte"):
            import time
            await page.screenshot(path=str(SORTIE / "nav_compte_inscription.png"))
            ecran = page.locator("#ecran-compte")
            await ecran.locator('input[name="email"]').fill(f"diagnostic-nav-{int(time.time())}@kelvisi-test.fr")
            await ecran.locator('input[name="mot_de_passe"]').fill("Essai-kelvisi-2026")
            await ecran.locator('input[name="prenom"]').fill("Essai")
            await ecran.locator('input[name="departement"]').fill("56")
            await ecran.locator('input[name="pratiques"][value="chasse"]').check()
            await ecran.locator('select[name="tranche_age"]').select_option("25-34")
            await ecran.locator('input[name="cgu"]').check()
            await ecran.locator('button[type="submit"]').click()
            try:
                await page.wait_for_selector("#ecran-compte", state="hidden", timeout=15000)
                resultats["inscription"] = "réussie, écran fermé"
                compte_essai = True
            except Exception:
                resultats["inscription"] = "écran toujours affiché : " + (await ecran.inner_text())[:300]
                await page.screenshot(path=str(SORTIE / "nav_compte_echec.png"))

        await page.wait_for_timeout(6000)
        await page.screenshot(path=str(SORTIE / "nav_carte_plan.png"))

        # Profondeurs du Shom lues dans la page (vraies images, vrai décodage)
        for nom, (lat, lon) in POINTS.items():
            try:
                resultats[nom] = await page.evaluate(
                    """async ([lat, lon]) => { const m = await import('./js/bathymetrie.js'); return await m.profondeursAuPoint(lat, lon); }""",
                    [lat, lon])
            except Exception as e:
                resultats[nom] = f"erreur {e}"
            try:
                resultats[nom + "_lieu"] = await page.evaluate(
                    """async ([lat, lon]) => { const m = await import('./js/profondeur.js'); const r = await m.estimerLieu(lat, lon); return r && { ...r, mesures: undefined }; }""",
                    [lat, lon])
            except Exception as e:
                resultats[nom + "_lieu"] = f"erreur {e}"

        # Nouveaux points : profondeur et direction du large estimées comme pour un lieu libre (Shom d'abord)
        a_estimer = RACINE / "spots" / "candidats_places.json"
        if a_estimer.exists():
            estimations = []
            for c in json.loads(a_estimer.read_text(encoding="utf-8")):
                try:
                    e = await page.evaluate(
                        """async ([lat, lon]) => { const m = await import('./js/profondeur.js'); const r = await m.estimerLieu(lat, lon);
                           return r && { profondeur_m: r.profondeur_m, orientation_deg: r.orientation_deg, ouverture_deg: r.ouverture_deg, source: r.source,
                                         terre: (r.mesures || []).some((x) => x.terre) }; }""", [c["lat"], c["lon"]])
                except Exception as ex:
                    e = {"erreur": str(ex)[:200]}
                estimations.append({**c, "estimation": e})
            (SORTIE / "estimations.json").write_text(json.dumps(estimations, ensure_ascii=False, indent=1), encoding="utf-8")
            resultats["estimations"] = f"{len(estimations)} points estimés"

        # Recherche de lieux (Géoplateforme)
        try:
            resultats["recherche"] = await page.evaluate(
                """async () => { const m = await import('./js/recherche.js'); return (await m.rechercherLieux('Quiberon')).slice(0, 3); }""")
        except Exception as e:
            resultats["recherche"] = f"erreur {e}"

        # Carte des profondeurs près de Quiberon, puis vue aérienne
        await page.click('[data-profondeurs]')
        await page.evaluate("""async () => { const c = await import('./js/carte.js'); c.voler(47.53, -3.14, 13.5); }""")
        await page.wait_for_timeout(12000)
        await page.screenshot(path=str(SORTIE / "nav_carte_profondeurs_quiberon.png"))
        await page.evaluate("""async () => { const c = await import('./js/carte.js'); c.voler(43.205, 5.36, 13.5); }""")
        await page.wait_for_timeout(12000)
        await page.screenshot(path=str(SORTIE / "nav_carte_profondeurs_marseille.png"))
        await page.click('[data-profondeurs]')
        await page.click('[data-fond="aerien"]')
        await page.wait_for_timeout(6000)
        await page.screenshot(path=str(SORTIE / "nav_carte_aerien_marseille.png"))

        # Fiche d'un lieu touché en mer
        await page.goto(f"http://127.0.0.1:{PORT}/#/point/47.47/-3.17")
        await page.wait_for_timeout(9000)
        await page.screenshot(path=str(SORTIE / "nav_fiche_lieu.png"), full_page=True)

        if compte_essai:
            await page.goto(f"http://127.0.0.1:{PORT}/#/compte")
            await page.wait_for_timeout(3000)
            await page.screenshot(path=str(SORTIE / "nav_mon_compte.png"))
            await page.click("[data-supprimer]")
            await page.click("[data-oui]")
            try:
                await page.wait_for_selector("#ecran-compte", state="visible", timeout=15000)
                resultats["suppression_compte"] = "réussie, retour à l'écran d'accueil"
            except Exception:
                resultats["suppression_compte"] = "échec"

        resultats["erreurs"] = erreurs[:40]
        resultats["tuiles_shom"] = shom[:12]
        await navigateur.close()

    (SORTIE / "navigateur.json").write_text(json.dumps(resultats, ensure_ascii=False, indent=1), encoding="utf-8")
    annoter("Navigateur", [f"{k} : {json.dumps(v, ensure_ascii=False)[:400]}" for k, v in resultats.items()])


if __name__ == "__main__":
    asyncio.run(main())
