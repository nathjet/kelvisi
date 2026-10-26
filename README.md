# Kelvisi

Prévision de la visibilité sous l'eau, en mètres, heure par heure sur trois
jours, pour la chasse sous-marine sur les côtes françaises (Manche,
Atlantique, Méditerranée, Corse). Version bêta gratuite, avec un compte.

**Pour mettre l'application en ligne : voir [GUIDE.md](GUIDE.md).**

## Ce que fait l'application

- **Comptes obligatoires** (e-mail et mot de passe) : prénom, département,
  pratiques, tranche d'âge et accord e-mails à l'inscription ; spots privés
  et favoris synchronisés entre appareils et visibles par leur seul
  propriétaire ; page « Mon compte » (profil, mot de passe, export des
  données, suppression). Liste des clients exportable depuis Supabase.
- **Carte** des 97 points Kelvisi et des spots partagés par les utilisateurs,
  colorés selon la visibilité du jour choisi, sur un fond plan ou la vue
  aérienne IGN.
- **Carte des profondeurs** : les modèles du Shom (relevés laser Litto3D au
  mètre, modèles côtiers à 5-20 m, modèles de façade à 100 m) relus et
  redessinés en tranches de profondeur, avec un trait tous les 5 m et un relief
  éclairé du nord-ouest, pour repérer tombants, têtes de roche et bancs.
  EMODnet en vue lointaine.
- **Profondeur au point** lue sur les cartes du Shom (relevé laser, modèle
  côtier à 20 m, modèle de façade à 100 m), avec sa référence (niveau moyen
  ou plus basses mers) ; direction du large et abri d'un lieu calculés sur
  la carte de façade du Shom.
- **Recherche de lieux** (plage, pointe, commune) avec la Géoplateforme IGN,
  puis prévision calculée sur place pour ce lieu.
- **« Où aller ? »** : recherche d'une ville, d'une plage ou d'un spot par son
  nom, ou « Autour de moi », puis les spots du rayon choisi classés du plus
  clair au plus trouble.
- **Spots partagés** : un utilisateur peut proposer un de ses spots à tous ;
  il apparaît après validation par l'éditeur, sans le nom de son auteur.
- **Clic en mer** n'importe où : profondeur et orientation estimées
  automatiquement (Shom, sinon EMODnet), prévision du lieu, réglages modifiables.
- **Fiche d'un spot** : visibilité attendue, fourchette et confiance, meilleur
  créneau de jour, explication en une phrase, tendance, alerte de sécurité,
  heure par heure, houle au spot, vent (de terre ou de mer, en nœuds ou km/h),
  courant, marées, température de l'eau en surface et **au fond** (à la
  profondeur du spot, modèles IBI et MED de Copernicus Marine), pluie des 48
  dernières heures, débit des fleuves proches, lever et coucher du soleil,
  phase de la Lune et période de vives-eaux ou mortes-eaux.
- **Zones de pêche sous-marine** : bouton « Zones » de la carte (rouge :
  chasse interdite, orange : règles particulières) d'après les zones
  réglementaires du CACEM ; les fiches et la fiche rapide le signalent en haut,
  avec la règle et la référence du texte. Mise à jour mensuelle automatique.
- **Favoris** parmi les points Kelvisi, et **alerte** au choix sur un favori
  ou un spot privé, avec un seuil de visibilité en mètres choisi par
  l'utilisateur : notification du navigateur quand le meilleur créneau d'une
  journée l'atteint, une fois par jour et par spot, entre 8 h et 21 h. **Partage d'une prévision par lien**.
- **Mes spots** : favoris et spots privés, liés au compte et synchronisés
  entre appareils, visibles par leur seul propriétaire ; copie et import.
  Un lieu peut être proposé comme futur point Kelvisi par courriel.
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
- Les spots privés sont enregistrés dans le compte de leur propriétaire
  (Supabase), lisibles par lui seul.
- La carte des profondeurs est dessinée dans le navigateur, dans un worker
  (`app/js/relief-rendu.js`) : chaque image du Shom est relue couleur par
  couleur, puis redessinée.

## Le modèle

La visibilité horizontale vaut 4,8 / c, où c est l'atténuation de la lumière
dans l'eau (Davies-Colley). Le moteur additionne les sources d'atténuation :

| Composante | Calcul |
| --- | --- |
| Eau claire | Constante |
| Fond habituel du spot | Visibilité typique par temps calme, calée sur le satellite pour chaque point de référence ; un lieu libre ou un spot privé reprend celle du point de référence le plus proche (moins de 25 km), sinon celle de la façade |
| Brassage | Vitesse de l'eau au fond sous les vagues (théorie linéaire), combinée au courant, comparée au seuil de remise en suspension du fond ; effet retard de 18 h (sable) à 60 h (vase) ; sable des petits fonds voisins ; sensibilité à la houle propre à chaque point (calée sur le satellite) |
| Rivières | Débit Hub'Eau rapporté au débit habituel (médiane depuis 2021), avec délai d'arrivée et poids propres à chaque point |
| Pluie | Cumul récent avec mémoire de 36 h |
| Saison | À houle égale, eau plus chargée en hiver en Manche et en Atlantique (facteur calé sur le satellite, maximum début janvier) |
| Plancton | Valeurs saisonnières par façade (la chlorophylle satellite, faussée par les sédiments près des côtes, n'est pas utilisée) |
| Satellite | La dernière image recale le modèle ; son poids diminue en 3 jours |

L'abri du spot (orientation, ouverture) filtre la houle. La marée module les
composantes côtières (eau plus claire autour de la pleine mer, vives-eaux
plus brassées) ; elle est ignorée en Méditerranée. La lumière donne la
visibilité ressentie. Les seuils de couleur sont propres à chaque façade.

Toutes les constantes sont dans `prevision/parametres.py`. Le brassage, la
pluie, les rivières, la marée, la saison et les valeurs de chaque point de
référence sont calés sur l'historique satellite (voir « Calage » ci-dessous).
Les valeurs encore marquées « À CALER » (conversion turbidité en mètres,
plancton) le seront avec les retours terrain de la bêta
(`prevision/calibrage.py`, appliqué automatiquement point par point).

### Calage sur le satellite

Le workflow « Calage » (`outils/historique.py`) rassemble pour les points Kelvisi
les images satellite depuis 2022 et la météo marine, la pluie et les débits
des mêmes jours, sur la branche `historique`. `outils/caler.py` recalcule
ensuite la turbidité que le modèle aurait prévue, la compare aux images, cale
les réglages sur le début de l'historique et vérifie le résultat sur la fin,
jamais vue pendant le calage (`--appliquer` écrit les valeurs retenues).
Rapport complet : `calage/resultat.json`.

Calage du 22 octobre 2026 (images de janvier 2022 à octobre 2026, 95 points,
14 804 images). La vérification porte sur la fin de chaque série (de mi-2025 à
octobre 2026), jamais vue pendant le calage ; erreur typique sur la turbidité :

| Prévision | 1 jour après une image | 2 à 3 jours | 4 à 7 jours |
| --- | --- | --- | --- |
| Eau identique à la dernière image | 33 % | 47 % | 73 % |
| Modèle calé, recalé sur la dernière image | 31 % | 36 % | 48 % |

Sans image récente, le modèle calé fait 46 % d'erreur typique, contre 63 %
pour une simple moyenne de chaque point. Ces chiffres sont plus élevés qu'au
calage précédent parce que la période de vérification, plus récente, est plus
difficile : sur une même période (l'année 2026 mise de côté), caler sur
2022-2025 plutôt que sur 2024-2025 fait passer l'erreur de 48,9 % à 48,5 %.
Les 51 points ajoutés en octobre ont leurs propres valeurs depuis le 19
octobre : leur erreur est passée de 95 % (valeurs reprises d'un voisin) à
42 %. Aux Glénan et à Palombaggia, le fond de sable clair peu profond
fausse la turbidité satellite : le satellite y est ignoré. À Ouessant,
Belle-Île, Campomoro, sur la côte Vermeille et aux Baleines, le masque des
terres du satellite s'arrête à 140-380 m du point : les pixels sont pris
dans un rayon de 800 m au lieu de 300 m.

## Organisation

```
app/                    application publiée (HTML, CSS, JavaScript, données)
  js/app.js             navigation, recherche, carte, fraîcheur des données
  js/carte.js           carte MapLibre, fonds, repères
  js/relief*.js         carte des profondeurs redessinée (worker)
  js/zones.js           zones de pêche sous-marine (carte, fiches)
  js/temperatures.js    température au fond, lue dans les profils publiés
  js/alertes.js         alertes sur les favoris (abonnement aux notifications)
  zones/                zones de pêche sous-marine (mises à jour chaque mois)
  js/vues/              fiche, Où aller ?, Mes spots, Infos
  js/moteur/            moteur JavaScript, Open-Meteo, EMODnet, recherche IGN
  js/config.js          réglages à compléter (éditeur, contact, Supabase)
  donnees/              prévisions publiées (régénérées toutes les heures)
  sw.js                 fonctionnement hors connexion
prevision/              moteur Python
  sources/              Open-Meteo, Hub'Eau, Copernicus (satellite, température en profondeur)
spots/points.json       les 97 points Kelvisi (et leurs rivières)
outils/
  calculer_previsions.py  calcul horaire de tous les points
  prevoir_spot.py         prévision d'un seul spot, en ligne de commande
  construire_apercu.py    version autonome de l'appli pour un aperçu
  zones_reglementees.py   zones du CACEM classées (interdite, réglementée)
  alertes.py, webpush.py  envoi des alertes (Web Push chiffré, clés VAPID)
supabase/schema.sql     tables (comptes, spots, favoris et alertes, retours) et leurs protections
.github/workflows/      calcul horaire et publication, zones chaque mois, tests de la base
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

## État au 25 octobre 2026

| Élément | État |
| --- | --- |
| Modèle, créneaux, explications, calibrage, classement | Codé, testé (174 tests Python), calé sur le satellite |
| Open-Meteo | Lancé sur l'API réelle : 97 points calculés sans erreur |
| Hub'Eau | Lancé sur l'API réelle : 6 stations lues, rattachées à 25 points |
| Interface | Testée automatiquement en mobile et grand écran |
| Carte, fonds en ligne, recherche IGN, profondeurs | Vérifiés dans un vrai navigateur sur les vrais services (workflow « Diagnostic ») |
| Copernicus | En service depuis le 16 octobre 2026 : produits côtiers d'environ 100 m, environ 6 points sur 10 recalés à chaque passage (selon les nuages) |
| Supabase | Projet en service : inscription, profil, spots privés, favoris, retours et suppression vérifiés sur le vrai projet |
| Comptes | Ouverts (obligatoires) ; e-mails de mot de passe oublié en attente d'un envoi d'e-mails propre (Brevo et nom de domaine) |
| Température au fond | Lancée sur le vrai service Copernicus (IBI, MED) : 97 points sur 97 |
| Zones de pêche sous-marine | Fichier tiré des zones du CACEM (418 interdites, 117 réglementées), mis à jour chaque mois |
| Alertes sur les favoris | Codées et testées ; en service dès que `supabase/schema.sql` est relancé |
| Paiement, fonctions de la version payante | Pas commencés |
| Photo jointe aux retours, statistiques d'audience | Pas commencées |

Limites connues :

- La conversion de la turbidité en mètres de visibilité n'est pas encore
  vérifiée sur le terrain : les retours de la bêta la régleront.
- Le satellite ne voit rien par temps couvert : environ la moitié des points
  ont une image de moins de 5 jours à un instant donné.
- Les horaires de marée viennent d'un modèle à maille de 8 km : indicatifs.
- La carte des profondeurs a une finesse inégale (relevé laser au mètre près
  des côtes de Bretagne, Nouvelle-Aquitaine, Occitanie et Provence, 100 m
  ailleurs), est lue sur la couleur des cartes du Shom (environ un mètre
  d'incertitude) et ne sert pas à naviguer.
- Les points Kelvisi sont des zones de prévision, pas des recommandations de
  spot : réserves et cantonnements sont à vérifier localement. D'après les
  zones du CACEM, six points sont dans une zone où la chasse est interdite
  (Camarat, Cavalaire, Calvi Revellata, Cap d'Agde, Cap Sicié, Esterel) :
  leur fiche l'affiche en rouge.
- Les zones de pêche sous-marine sont classées d'après le résumé de chaque
  règle : un classement peut être faux, et la liste ne couvre pas les règles
  générales (ports, abords des plages, arrêtés municipaux).
- La température au fond vient d'un modèle à maille de 3 à 4 km, en moyenne
  sur la journée : une thermocline marquée près de la côte peut lui échapper.

Données : Open-Meteo (CC BY 4.0), Hub'Eau (Licence Ouverte), IGN
Géoplateforme (Licence Ouverte), Shom (Licence Ouverte), EMODnet Bathymetry,
OpenFreeMap et OpenStreetMap (ODbL), Natural Earth, Copernicus Marine Service,
zones réglementaires du CACEM (Licence Ouverte 2.0).
