"""Prépare un aperçu de l'application publiable comme page Claude (artifact).

L'aperçu embarque les prévisions déjà calculées. Les services en ligne (fond
de carte, recherche, météo des lieux libres) n'y sont pas joignables : la
carte passe sur son fond de secours et un bandeau le signale.

Usage : python outils/construire_apercu.py DOSSIER_DE_SORTIE
"""

import re
import shutil
import sys
from pathlib import Path

RACINE = Path(__file__).resolve().parent.parent
APP = RACINE / "app"


def main():
    sortie = Path(sys.argv[1])
    if sortie.exists():
        shutil.rmtree(sortie)
    shutil.copytree(APP, sortie, ignore=shutil.ignore_patterns("sw.js", "manifest.webmanifest", ".nojekyll", "*.txt"))
    html = (APP / "index.html").read_text(encoding="utf-8")
    titre = re.search(r"<title>.*?</title>", html).group(0)
    liens = "\n".join(re.findall(r'<link rel="(?:stylesheet|icon)"[^>]*>', html))
    corps = re.search(r"<body[^>]*>(.*)</body>", html, re.S).group(1)
    corps = re.sub(r"<noscript>.*?</noscript>", "", corps, flags=re.S)
    page = f"""{titre}
{liens}
<script>window.KELVISI_APERCU = true; document.body.classList.add("route-carte");</script>
<script src="vendor/maplibre-gl.js"></script>
{corps}
<script type="module" src="js/app.js"></script>
"""
    (sortie / "index.html").write_text(page, encoding="utf-8")
    fichiers = sorted(str(f.relative_to(sortie)) for f in sortie.rglob("*") if f.is_file() and f.name != "index.html")
    print(len(fichiers), "fichiers")
    (sortie / "fichiers.txt").write_text("\n".join(fichiers), encoding="utf-8")


if __name__ == "__main__":
    main()
