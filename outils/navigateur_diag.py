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
        page.on("console", lambda m: erreurs.append(f"console {m.type}: {m.text}") if m.type in ("error", "warning") else None)
        page.on("requestfailed", lambda r: erreurs.append(f"échec {r.url[:120]} {r.failure}"))

        await page.goto(f"http://127.0.0.1:{PORT}/#/carte")
        await page.wait_for_timeout(9000)
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

        # Recherche de lieux (Géoplateforme)
        try:
            resultats["recherche"] = await page.evaluate(
                """async () => { const m = await import('./js/recherche.js'); return (await m.rechercherLieux('Quiberon')).slice(0, 3); }""")
        except Exception as e:
            resultats["recherche"] = f"erreur {e}"

        # Carte des profondeurs près de Quiberon, puis vue aérienne
        await page.click('[data-profondeurs]')
        await page.evaluate("""async () => { const c = await import('./js/carte.js'); c.voler(47.475, -3.16, 13); }""")
        await page.wait_for_timeout(7000)
        await page.screenshot(path=str(SORTIE / "nav_carte_profondeurs_quiberon.png"))
        await page.evaluate("""async () => { const c = await import('./js/carte.js'); c.voler(43.205, 5.36, 13); }""")
        await page.wait_for_timeout(7000)
        await page.screenshot(path=str(SORTIE / "nav_carte_profondeurs_marseille.png"))
        await page.click('[data-profondeurs]')
        await page.click('[data-fond="aerien"]')
        await page.wait_for_timeout(6000)
        await page.screenshot(path=str(SORTIE / "nav_carte_aerien_marseille.png"))

        # Fiche d'un lieu touché en mer
        await page.goto(f"http://127.0.0.1:{PORT}/#/point/47.47/-3.17")
        await page.wait_for_timeout(9000)
        await page.screenshot(path=str(SORTIE / "nav_fiche_lieu.png"), full_page=True)

        resultats["erreurs"] = erreurs[:40]
        await navigateur.close()

    (SORTIE / "navigateur.json").write_text(json.dumps(resultats, ensure_ascii=False, indent=1), encoding="utf-8")
    annoter("Navigateur", [f"{k} : {json.dumps(v, ensure_ascii=False)[:400]}" for k, v in resultats.items()])


if __name__ == "__main__":
    asyncio.run(main())
