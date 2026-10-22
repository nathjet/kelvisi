"""Constantes du modèle de prévision.

Toutes les valeurs réglables sont regroupées ici. Celles marquées « Calé sur
le satellite » ont été ajustées sur l'historique satellite (outils/caler.py),
ainsi que la visibilité habituelle et la sensibilité à la houle de chaque
point de référence (spots/points.json). Celles marquées « À CALER » restent
des ordres de grandeur : elles seront ajustées avec les retours terrain.
"""

# --- Optique ---------------------------------------------------------------

# Portée visuelle horizontale d'une cible noire : V = 4,8 / c
# (c = coefficient d'atténuation du faisceau en m⁻¹, relation de Davies-Colley).
CONSTANTE_VISIBILITE = 4.8

# Atténuation de l'eau de mer très claire (m⁻¹).
C_EAU = 0.12

# Conversion turbidité satellite (FNU) en atténuation (m⁻¹). À CALER.
C_PAR_FNU = 0.7

# Atténuation due au phytoplancton : c = A * Chl^B (Chl en mg/m³).
# Ordre de grandeur des relations bio-optiques publiées. À CALER.
PLANCTON_A = 0.4
PLANCTON_B = 0.6

# --- Remise en suspension par la houle et le courant -------------------------

GRAVITE = 9.81

# Hauteur de vague maximale avant déferlement : H <= 0,78 * profondeur.
RAPPORT_DEFERLEMENT = 0.78

# Profondeur de la frange littorale (plages, petits fonds) dont le sable
# brassé dérive vers le spot (m).
PROFONDEUR_LITTORAL_M = 3.0

# Poids de la frange littorale par rapport au fond du spot. Calé sur le satellite (2022-01 à 2026-10).
POIDS_LITTORAL = 3.0

# Vitesse critique du sable de plage, souvent plus grossier (m/s).
U_CRITIQUE_LITTORAL = 0.25

# Part de la vitesse du courant (moyenne sur la colonne d'eau, maille de
# 8 km) qui s'exerce près du fond. Houle et courant se combinent en
# moyenne quadratique, car ils ne sont ni en phase ni dans le même axe.
COURANT_PRES_DU_FOND = 0.7

# Coefficient de production de turbidité (m⁻¹ par heure et par unité
# d'excès de cisaillement). Calé sur le satellite (2022-01 à 2026-10).
ALPHA_BRASSAGE = 0.00196

# Plafond doux de l'atténuation due au brassage (m⁻¹). Calé sur le satellite (2022-01 à 2026-10).
C_BRASSAGE_MAX = 25.36

# Par type de fond :
#   vitesse critique de remise en suspension au fond (m/s),
#   érodabilité (facteur multiplicatif),
#   temps de retour au calme (h) : durée pour que l'eau perde ~63 % de sa charge,
#   part de sable autour du spot par défaut (0 à 1).
FONDS = {
    "sable":   {"u_critique": 0.20, "erodabilite": 1.0, "tau_h": 18.0, "part_sable": 1.0},
    "vase":    {"u_critique": 0.12, "erodabilite": 1.5, "tau_h": 60.0, "part_sable": 1.0},
    "mixte":   {"u_critique": 0.20, "erodabilite": 0.7, "tau_h": 30.0, "part_sable": 0.5},
    "herbier": {"u_critique": 0.25, "erodabilite": 0.4, "tau_h": 24.0, "part_sable": 0.4},
    "roche":   {"u_critique": 0.22, "erodabilite": 0.5, "tau_h": 20.0, "part_sable": 0.3},
}

# Multiplicateur commun des temps de retour au calme. Calé sur le satellite (2022-01 à 2026-10).
FACTEUR_TAU = 1.414

# Atténuation résiduelle de la houle hors du secteur exposé (diffraction).
EXPOSITION_RESIDUELLE = 0.1

# --- Marée -------------------------------------------------------------------

# Effet de la phase de marée sur les composantes côtières :
# facteur = 1 - EFFET_PHASE_MAREE * sensibilité * phase (phase = +1 à la pleine mer).
# Calé sur le satellite (2022-01 à 2026-10) : effet faible à l'échelle des pixels.
EFFET_PHASE_MAREE = 0.2012

# Effet du marnage (vives-eaux) sur le brassage.
EFFET_MARNAGE = 0.3

# Marnage moyen en dessous duquel la marée est ignorée (m).
MARNAGE_MINIMUM_M = 0.5

# --- Rivières et pluie -------------------------------------------------------

GAMMA_FLUVIAL = 0.6266     # m⁻¹ par unité d'anomalie de débit. Calé sur le satellite (2022-01 à 2026-10).
EXPOSANT_FLUVIAL = 0.7
TAU_FLUVIAL_H = 24.0       # persistance du panache

TAU_PLUIE_H = 36.0         # mémoire de la pluie
SEUIL_PLUIE_MM = 8.0       # cumul (avec mémoire) sans effet notable
DELTA_PLUIE = 0.1605       # m⁻¹ par tranche de 10 mm au-delà du seuil. Calé sur le satellite (2022-01 à 2026-10).

# --- Assimilation satellite --------------------------------------------------

# Durée pendant laquelle une image satellite continue de corriger le modèle.
TAU_ASSIMILATION_H = 72.0

# --- Régions -----------------------------------------------------------------

REGIONS = {
    "manche": {
        "visibilite_calme_m": 2.8,
        "visibilite_max_m": 20.0,
        "sensibilite_maree": 0.6,
        # Seuils de classe (m) : mauvaise < s1 <= moyenne < s2 <= bonne < s3 <= excellente
        "seuils": (2.0, 4.0, 7.0),
        # Plancton saisonnier (m⁻¹) de janvier à décembre, faute de satellite. À CALER.
        "plancton_mensuel": (0.05, 0.05, 0.12, 0.35, 0.35, 0.25, 0.2, 0.2, 0.15, 0.1, 0.05, 0.05),
    },
    "atlantique": {
        "visibilite_calme_m": 5.6,
        "visibilite_max_m": 25.0,
        "sensibilite_maree": 0.5,
        "seuils": (2.0, 4.0, 7.0),
        "plancton_mensuel": (0.05, 0.05, 0.12, 0.35, 0.35, 0.25, 0.2, 0.2, 0.15, 0.1, 0.05, 0.05),
    },
    "mediterranee": {
        "visibilite_calme_m": 12.3,
        "visibilite_max_m": 35.0,
        "sensibilite_maree": 0.0,
        "seuils": (4.0, 8.0, 15.0),
        "plancton_mensuel": (0.03, 0.08, 0.1, 0.08, 0.04, 0.03, 0.03, 0.03, 0.03, 0.03, 0.03, 0.03),
    },
}

# Saison : à houle égale, les eaux côtières sont plus chargées en hiver (fines particules
# qui restent en suspension, mer rarement calme longtemps, crues). Facteur multiplicatif
# sur la turbidité côtière : exp(amplitude · cos(2π (jour − pic_jour) / 365,25)),
# pic_jour compté depuis le 1er janvier. Calé sur le satellite (2022-01 à 2026-10).
SAISON = {
    "manche": {"amplitude": 0.412, "pic_jour": 6.6},
    "atlantique": {"amplitude": 0.543, "pic_jour": 9.4},
    "mediterranee": {"amplitude": 0.0, "pic_jour": 96.6},
}

# Effet du type de fond sur la visibilité par temps calme (eau de fond vaseux
# rarement très claire).
FACTEUR_CALME_FOND = {"sable": 0.9, "vase": 0.5, "mixte": 1.0, "herbier": 1.0, "roche": 1.1}

CLASSES = ("mauvaise", "moyenne", "bonne", "excellente")

# --- Lumière (visibilité ressentie) -------------------------------------------

FACTEUR_CIEL_COUVERT = 0.85    # ciel couvert à 100 %
FACTEUR_SOLEIL_BAS = 0.8       # soleil à l'horizon
HAUTEUR_SOLEIL_PLEINE_LUMIERE = 15.0  # degrés

# --- Incertitude -------------------------------------------------------------

INCERTITUDE_SANS_SATELLITE = 0.30
INCERTITUDE_AVEC_SATELLITE = 0.18
INCERTITUDE_PAR_JOUR = 0.05            # croissance avec l'échéance
INCERTITUDE_AGE_SATELLITE_PAR_JOUR = 0.03
INCERTITUDE_MAX = 0.7

# --- Sécurité et confort -----------------------------------------------------

HOULE_CONFORT_M = 1.2
HOULE_DECONSEILLEE_M = 2.5
RAFALES_DECONSEILLEES_KN = 30.0
VENT_GENANT_KN = 18.0
DUREE_CRENEAU_MIN_H = 2
DUREE_CRENEAU_MAX_H = 4

NOEUD_EN_MS = 0.514444
