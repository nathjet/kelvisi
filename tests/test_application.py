"""Garde-fous sur les fichiers publiés de l'application."""

import re
from pathlib import Path

APP = Path(__file__).resolve().parent.parent / "app"


def test_hors_connexion_couvre_tous_les_modules():
    """Un module oublié dans sw.js casserait l'application hors connexion."""
    sw = (APP / "sw.js").read_text(encoding="utf-8")
    listes = set(re.findall(r'"([^"]+)"', sw))
    modules = {str(p.relative_to(APP)) for p in (APP / "js").rglob("*.js")}
    assert modules - listes == set()
    for chemin in listes:
        if "/" in chemin and not chemin.startswith(("http", "/", "donnees/")) and "." in chemin.rsplit("/", 1)[-1]:
            assert (APP / chemin).exists(), chemin


def test_aucune_cle_secrete_publiee():
    """La clé secrète Supabase ne doit jamais se retrouver dans le site."""
    for fichier in APP.rglob("*"):
        if fichier.suffix in {".js", ".html", ".json", ".webmanifest"} and "vendor" not in fichier.parts:
            texte = fichier.read_text(encoding="utf-8", errors="ignore")
            assert "sb_secret_" not in texte, fichier
            assert '"role":"service_role"' not in texte.replace(" ", ""), fichier


def test_fichiers_references_par_la_page():
    page = (APP / "index.html").read_text(encoding="utf-8")
    for chemin in re.findall(r'(?:src|href)="([^"#:]+)"', page):
        assert (APP / chemin).exists(), chemin
