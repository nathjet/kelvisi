"""Classement des zones réglementaires du CACEM (outils/zones_reglementees.py), sur des résumés réels."""

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "outils"))

from zones_reglementees import arrondir, classer, normaliser  # noqa: E402

INTERDITES = [
    ("Pêche sous-marine, Zone d'interdiction", "", "Zone d'interdiction de la pêche sous-marine de la pointe Prime à la pointe Béarlieu (Porquerolles)"),
    ("Pêche sous-marine, Zone d'interdiction", "Anse des Cuivres (commune de Marseille)", "La pêche sous-marine est interdite toute l'année"),
    ("Activités réglementées", "", "Zone de non prélèvement (ZNP) : pêches professionnelle et de loisir interdites - Riou, Podestat et Pointe du Vaisseau (Article 11.2)"),
    ("Cantonnement", "", "La pêche maritime sous toutes ses formes est interdite"),
    ("Cantonnement pêche", "", "Cantonnement de Propriano : pêche interdite à la seule exception de la pêche à pied et de la pêche à la ligne depuis le rivage"),
    ("Activité nautique", "Cantonnement Calvi", "Cantonnement Calvi - plongée sous-marine en scaphandre autonome et en apnée interdite (sauf autorisation individuelle)"),
    ("Réglementation", "", "Il est interdit :  d'exercer la pêche et la chasse sous-marine, de chasser"),
    ("Pêche de loisir", "", "Pêche autorisée du 1er septembre au 30 juin, chasse sous marine interdite - Zone D"),
    ("Ouest île d'Oléron : zone réglementée", "", "Mouillage, dragage, forage, pêche, plongée sous-marine interdits"),
    ("ZMEL", "Pont de la Corde (aval)", "Pêche : interdit de ramasser des moules sur les équipements. Pêche sous-marin et engin dormants INTERDICTION."),
    ("Cantonnements pêche", "", "Cantonnement entre la pointe d'Arradon et la pointe nord de l'île aux Moines : Toute pêche, y compris la pêche sous-marine est interdite, à l'exception de celle pratiquée au moyen de lignes ou palangres"),
    ("APHN", "", "Sont interdits dans l’ensemble de l’APHN : activités de pêche maritime embarquée, sauf pêche à la ligne ; pêche sous-marine ; piétinement des formations récifales"),
    ("APB", "Zone d'interdiction permanente", "Du 1er aout au 29 février inclus : sont interdits l'accostage; la chasse y compris la chasse sous-marine; usage du feu"),
    ("Cantonnement à crustacés", "", "Seule est autorisée la pêche pratiquée à l'aide de lignes - La récolte des végétaux est interdite"),
    ("Réglementation", "", "Il est interdit : de pratiquer la pêche à pied professionnelle à l'exception de la pêche à la coque, de pratiquer la pêche de loisir, de chasser"),
    ("règlement de police des pêches du GPMM", "GPMM", "règlement de police des pêches du GPMM - zone d'interdiction de la pêche"),
    ("Pêche sous-marine, Zone d'interdiction", "Pêche sous-marine interdite dans les Alpes-Maritimes",
     "En dehors de ces zones, la pêche maritime est autorisée du 1er novembre au 1er mars, uniquement en semaine (sauf pour les oursins)"),
    ("APB", "", "du 15 avril au 31 août interdiction d'accès aux partie émergées; interdiction de navigation et mouillage des navires engins nautiques, de baignade et de plongée sous-marine"),
]

REGLEMENTEES = [
    ("Pêche sous-marine, Zone d'interdiction", "Zone d'interdiction de la pêche sous-marine",
     "La pêche sous-marine de loisir des crustacés et des gorgones est interdite toute l'année dans la bande littorale des 300 mètres"),
    ("Pêche sous-marine, Zone d'interdiction", "", "Zone d'interdiction de la pêche sous-marine des crustacés au large de Leucate sur la roche de Leucate"),
    ("Pêche de loisir des différentes espèces de mérous", "", "Pêche sous-marine interdite pour les espèces suivantes : mérou brun (Epinephelus marginatus), badèche"),
    ("Zone de protection renforcée", "", "Plateau des Lavezzi - pêche de loisir soumise à déclaration et à autorisation nominative et réglementée"),
    ("Cantonnements pêche", "Cantonnement du Plateau de la Recherche",
     "Pêche interdite à l'exception de la pêche aux lignes et aux palangres, la pêche sous-marine de poissons - Récolte des végétaux marins interdite"),
    ("Cantonnement, réserve à crustacés", "Réserve à crustacés de Doëlan", "La pêche des crustacés à l’aide de toutes méthodes de pêche, y compris de pêche sous-machine, est interdite"),
    ("Pêche des oursins", "Luri", "La pêche des oursins violets, quel que soit son mode de capture, est interdite dans cette zone."),
    ("Pêche pro et loisir du bar", "", "Toute forme de pêche du bar, tant professionnelle que de loisir, est interdite chaque année du 1er mars au 31 mai"),
]

SANS_RAPPORT = [
    ("Activités nautiques", "", "Pointe du Vaisseau - Mouillage interdit sauf sur dispositif de plongée"),
    ("Activité nautiques", "", "Coeur marin (600 m) / VNM et engins tractés interdits / Plongée en scaphandre autonome interdite sauf autorisation délivrée"),
    ("Chasse", "", "Chasse interdite"),
    ("Pêche palourdes", "", "La pêche de la palourde, tant à titre professionnel qu'à titre de loisir, est interdite à compter du 1er novembre 2016"),
    ("Arrêté ministériel", "Crevette, Adour", "Pendant la période d'interdiction, les pêcheurs professionnels sont autorisés à pêcher la crevette, limitée à un kilogramme par jour de pêche et par bateau."),
    ("Pêche engins", "Zone nord de Houat", "La pêche professionnelle et de loisir aux filets, palangres et nasses et casiers est interdite"),
    ("Chenaux d'accès", "", "Interdiction de pêche (arts trainants, pose d'engins de pêche mouillés ou dérivants)"),
    ("AOT DPM études université de Corse", "", "AOT DPM pour des études de microhabitats sous-marins de protection juvéniles de crustacés"),
    ("ARP Natura 2000", "ARP", "Zone d’interdiction de la pêche à la senne danoise"),
]


@pytest.mark.parametrize("couche,nom,resume", INTERDITES)
def test_zones_interdites(couche, nom, resume):
    assert classer(couche, nom, resume) == "interdite"


@pytest.mark.parametrize("couche,nom,resume", REGLEMENTEES)
def test_zones_reglementees(couche, nom, resume):
    assert classer(couche, nom, resume) == "reglementee"


@pytest.mark.parametrize("couche,nom,resume", SANS_RAPPORT)
def test_zones_sans_rapport(couche, nom, resume):
    assert classer(couche, nom, resume) is None


def test_theme_peche_sous_marine_suffit_pour_reglementee():
    assert classer("Mouillage", "", "Zone de mouillage organisée", '{"Pêche de loisir (autre que PAP)": ["Pêche sous-marine"]}') == "reglementee"


def test_normalisation():
    assert normaliser("Pêche  SOUS MARINE\n’") == "peche sous-marine '"
    assert normaliser(None) == "" and normaliser(float("nan")) == ""
    assert arrondir([[1.123456789, 2.987654321]]) == [[1.12346, 2.98765]]
