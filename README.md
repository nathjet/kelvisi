# Kelvisi

Prévision de la visibilité sous l'eau, en mètres, heure par heure sur trois
jours, pour la chasse sous-marine sur les côtes françaises (Manche,
Atlantique, Méditerranée, Corse). Version bêta, gratuite, sans compte.

**Pour mettre l'application en ligne : voir [GUIDE.md](GUIDE.md).**

## Ce que fait l'application

- **Comptes obligatoires** (e-mail et mot de passe) : prénom, département,
  pratiques, tranche d'âge et accord e-mails à l'inscription ; spots privés
  et favoris synchronisés entre appareils et visibles par leur seul
  propriétaire ; page « Mon compte » (profil, mot de passe, export des
  données, suppression). Liste des clients exportable depuis Supabase.
- **Carte** des 46 points Kelvisi, colorés selon la visibilité du jour choisi,
  avec trois fonds : plan, vue aérienne IGN, profondeurs (Shom près des
  côtes, dont les relevés laser Litto3D au mètre ; EMODnet au large).
- **Profondeur au point** lue sur les cartes du Shom (relevé laser, modèle
  côtier à 20 m, modèle de façade à 100 m), avec sa référence (niveau moyen
  ou plus basses mers) ; direction du large et abri d'un lieu calculés sur
  la carte de façade du Shom.
- **Recherche de lieux** (plage, pointe, commune) avec la Géoplateforme IGN,
  puis prévision calculée sur place pour ce lieu.
- **Clic en mer** n'importe où : profondeur et orientation estimées
  automatiquement (EMODnet), prévision du lieu, réglages modifiables.
- **Fiche d'un spot** : visibilité attendue, fourchette et confiance, meilleur
  créneau de jour, explication en une phrase, tendance, alerte de sécurité,
  heure par heure, houle au spot, vent (de terre ou de mer, en nœuds ou km/h),
  courant, marées, température de l'eau, pluie des 48 dernières heures, débit
  des fleuves proches, lever et coucher du soleil, phase de la Lune et période
  de vives-eaux ou mortes-eaux.
- **Favoris** parmi les points Kelvisi, et **partage d'une prévision par lien**.
- **Où aller ?** : classement des points par façade ou autour de soi
  (géolocalisation, rayon réglable), sur trois jours.
- **Mes spots** : favoris et spots privés, enregistrés sur l'appareil
  seulement ; copie et import pour changer de téléphone. Un lieu peut être
  proposé comme futur point Kelvisi par courriel.
- **Tu y étais ?** : retour terrain en deux gestes. Il corrige la prévision du
  spot (sur l'appareil pour un spot privé, pour tout le monde sur un point
  Kelvisi si le partage Supabase est activé).
- **Hors connexion** : la dernière prévision reste consultable (application
  installable, PWA).
- Pages Infos : fonctionnement, sécurité et réglementation, sources,
  confidentialité, conditions d'utilisation, mentions légales.

## Architecture

Aucun serveur à maintenir.

```
GitHub Actions, toutes les heures
  Open-Meteo (houle, vent, courant, marée, pluie)  ─┐
  Hub'Eau (débits Seine, Loire, Vilaine, Adour,     ├─> moteur Python ─> app/donnees/*.json
           Rhône, Var)                              │
  Copernicus Marine (satellite, facultatif)         │
  Supabase (comptes, retours terrain)              ─┘
                     │
                     v
GitHub Pages : site statique app/  ──>  téléphone ou ordinateur
                                        moteur JavaScript pour les lieux
                                        recherchés et les spots privés
```

- Les points publics sont calculés par le moteur Python et publiés en JSON.
- Les lieux recherchés et les spots privés sont calculés dans le navigateur
  par une copie JavaScript du moteur (`app/js/moteur/moteur.js`), avec la
  météo Open-Meteo du moment. Un test vérifie que les deux moteurs donnent
  exactement le même résultat.
- Les spots privés ne quittent jamais l'appareil.

## Le modèle

La visibilité horizontale vaut 4,8 / c, où c est l'atténuation de la lumière
dans l'eau (Davies-Colley). Le moteur additionne les sources d'atténuation :

| Composante | Calcul |
| --- | --- |
| Eau claire | Constante |
| Fond habituel du spot | Déduit de la visibilité typique par temps calme (région et type de fond) |
| Brassage | Vitesse de l'eau au fond sous les vagues (théorie linéaire), combinée au courant, comparée au seuil de remise en suspension du fond ; effet retard de 18 h (sable) à 60 h (vase) ; sable des petits fonds voisins |
| Rivières | Débit Hub'Eau rapporté au débit habituel (médiane depuis 2021), avec délai d'arrivée et poids propres à chaque point |
| Pluie | Cumul récent avec mémoire de 36 h |
| Plancton | Chlorophylle satellite si disponible, sinon valeurs saisonnières par façade |
| Satellite | La dernière image recale le modèle ; son poids diminue en 3 jours |

L'abri du spot (orientation, ouverture) filtre la houle. La marée module les
composantes côtières (eau plus claire autour de la pleine mer, vives-eaux
plus brassées) ; elle est ignorée en Méditerranée. La lumière donne la
visibilité ressentie. Les seuils de couleur sont propres à chaque façade.

Toutes les constantes sont dans `prevision/parametres.py`. Celles marquées
« À CALER » sont des ordres de grandeur à ajuster : d'abord sur l'historique
satellite (`prevision/calage.py`, validé sur données simulées), puis sur les
retours terrain de la bêta (`prevision/calibrage.py`, appliqué
automatiquement point par point).

## Organisation

```
app/                    application publiée (HTML, CSS, JavaScript, données)
  js/app.js             navigation, recherche, carte, fraîcheur des données
  js/carte.js           carte MapLibre, fonds, repères
  js/vues/              fiche, Où aller ?, Mes spots, Infos
  js/moteur/            moteur JavaScript, Open-Meteo, EMODnet, recherche IGN
  js/config.js          réglages à compléter (éditeur, contact, Supabase)
  donnees/              prévisions publiées (régénérées toutes les heures)
  sw.js                 fonctionnement hors connexion
prevision/              moteur Python
  sources/              Open-Meteo, Hub'Eau, Copernicus
spots/points.json       les 46 points Kelvisi (et leurs rivières)
outils/
  calculer_previsions.py  calcul horaire de tous les points
  prevoir_spot.py         prévision d'un seul spot, en ligne de commande
  construire_apercu.py    version autonome de l'appli pour un aperçu
supabase/schema.sql     table des retours terrain et ses protections
.github/workflows/      calcul horaire et publication
tests/                  tests du moteur, des sources et de l'interface
prototype/, demo/       maquette et démonstration des premières étapes
```

## Lancer en local

```
pip install -r requirements.txt
python -m pytest -q                                  # tests du moteur (Node requis pour la concordance)
npm ci && npm test                                   # tests de l'interface
python outils/calculer_previsions.py                 # prévisions réelles (réseau requis)
python -m http.server -d app 8000                    # puis http://localhost:8000
```

## État au 15 octobre 2026

| Élément | État |
| --- | --- |
| Modèle, créneaux, explications, calibrage, classement | Codé, testé (104 tests Python) |
| Open-Meteo | Lancé sur l'API réelle : 46 points calculés sans erreur |
| Hub'Eau | Lancé sur l'API réelle : 6 stations lues, rattachées à 11 points |
| Interface | Testée automatiquement en mobile et grand écran (32 étapes) |
| Carte | Vérifiée dans Chromium (mobile et ordinateur) avec le fond de secours |
| Fonds en ligne, recherche IGN, profondeurs EMODnet | Code prêt ; services non joignables depuis l'espace de développement, à vérifier en ligne |
| Copernicus | En service depuis le 16 octobre 2026 : produits côtiers d'environ 100 m, environ 6 points sur 10 recalés à chaque passage (selon les nuages) |
| Supabase | Projet en service : inscription, profil, spots privés, favoris, retours et suppression vérifiés sur le vrai projet |
| Comptes | Ouverts (obligatoires) ; e-mails de mot de passe oublié en attente d'un envoi d'e-mails propre (Brevo et nom de domaine) |
| Paiement, fonctions de la version payante | Pas commencés |
| Photo jointe aux retours, statistiques d'audience | Pas commencées |

Limites connues :

- Par mer calme, sans satellite, la prévision plafonne à la visibilité
  habituelle du secteur (19 m en Méditerranée) : seul le satellite verra les
  variations fines.
- Les horaires de marée viennent d'un modèle à maille de 8 km : indicatifs.
- La carte des profondeurs (environ 100 m de résolution) ne sert pas à
  naviguer.
- Les points Kelvisi sont des zones de prévision, pas des recommandations de
  spot : réserves et cantonnements sont à vérifier localement.

Données : Open-Meteo (CC BY 4.0), Hub'Eau (Licence Ouverte), IGN
Géoplateforme (Licence Ouverte), EMODnet Bathymetry, OpenFreeMap et
OpenStreetMap (ODbL), Natural Earth, Copernicus Marine Service.
