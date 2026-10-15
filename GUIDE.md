# Mettre Kelvisi en ligne, pas à pas

Ce guide part de zéro et ne demande aucune connaissance en développement.
Compte une heure pour la partie obligatoire (étapes 1 à 5).

Résultat : l'application est publiée à l'adresse
`https://TON-PSEUDO.github.io/kelvisi/`, les prévisions se recalculent toutes
les heures toutes seules, et tout est gratuit tant que l'application l'est.

## Ce qu'il faut savoir avant de commencer

- **Aucun serveur à gérer.** GitHub héberge le site (GitHub Pages) et lance
  le calcul des prévisions toutes les heures (GitHub Actions).
- **Le dépôt doit être public** pour que tout soit gratuit : GitHub Pages
  n'est gratuit qu'avec un dépôt public, et le calcul horaire dépasserait le
  quota gratuit d'un dépôt privé (environ 2 900 minutes par mois pour 2 000
  offertes). Le pack étudiant GitHub (GitHub Pro gratuit) autorise Pages en
  privé, mais pas assez de minutes pour le calcul horaire.
  Rendre le code public ne donne pas grand-chose aux concurrents : le moteur
  de calcul est de toute façon envoyé à chaque navigateur qui ouvre l'appli.
  Ce qui fera la valeur de Kelvisi, ce sont le calage et les retours terrain,
  qui ne sont pas dans le dépôt.
- **Aucun mot de passe ni clé secrète ne va dans les fichiers.** Les clés
  secrètes vont uniquement dans les « secrets » GitHub (étape 6 et suivantes).
  Ne les colle jamais dans une conversation, un courriel ou un fichier.

## 1. Mettre le code sur GitHub

Deux façons de faire. La première est la plus simple.

### Option A : avec GitHub Desktop (conseillé)

1. Dézippe `kelvisi-v1.0.zip`. Tu obtiens un dossier `kelvisi`.
2. Installe GitHub Desktop (desktop.github.com) et connecte-toi avec ton
   compte GitHub.
3. Menu **File > Add local repository**, choisis le dossier `kelvisi`.
   GitHub Desktop propose de « créer un dépôt » : accepte (nom `kelvisi`).
4. Clique **Publish repository**. **Décoche** « Keep this code private ».
   Valide.

### Option B : demander à Claude de pousser le code

Connecte ton compte GitHub à Claude depuis les paramètres de Claude, puis
donne-moi le nom exact du dépôt (par exemple `ton-pseudo/kelvisi`). Je
pourrai alors envoyer le code et les futures corrections moi-même.

> Le téléversement par le site web de GitHub (« Add file > Upload files »)
> est déconseillé : il est limité à 100 fichiers par envoi et, sur Mac, le
> dossier caché `.github` (qui contient le calcul horaire) est facilement
> oublié. Sans lui, rien ne se met à jour.

## 2. Activer la publication du site

Sur la page du dépôt, dans GitHub :

1. **Settings** (onglet en haut à droite du dépôt) > **Pages** (menu de gauche).
2. Dans **Build and deployment**, champ **Source** : choisis **GitHub Actions**.

C'est tout pour cette étape.

## 3. Lancer le premier calcul

1. Onglet **Actions** du dépôt. Si GitHub demande d'autoriser les workflows,
   accepte.
2. Clique sur **Prévisions et publication** dans la liste de gauche, puis
   **Run workflow** > **Run workflow**.
3. Attends 5 à 10 minutes. Une coche verte signifie que c'est publié.
   Une croix rouge : clique dessus, puis sur l'étape en rouge, et copie-moi
   le message d'erreur (il ne contient aucun secret).

L'adresse du site s'affiche dans **Settings > Pages**. Ensuite, le calcul
tourne seul toutes les heures (à la 17e minute).

## 4. Vérifier sur ton téléphone

1. Ouvre l'adresse du site.
2. Vérifie : la carte s'affiche, les pastilles de couleur sont là, la
   recherche trouve « Quiberon », une fiche s'ouvre, l'onglet « Où aller ? »
   classe les spots.
3. Pour l'installer comme une appli :
   - iPhone (Safari) : bouton **Partager** > **Sur l'écran d'accueil** ;
   - Android (Chrome) : menu **⋮** > **Installer l'application** (ou
     « Ajouter à l'écran d'accueil »).

## 5. Compléter les mentions légales

Les pages « Mentions légales », « Confidentialité » et « Donner mon avis »
affichent `[… à compléter]` tant que ces deux informations manquent.

1. Dans le dépôt, ouvre le fichier `app/js/config.js` et clique sur le
   crayon (**Edit this file**).
2. Remplis :
   ```js
   editeur: "Nathan …",               // ton nom (ou celui de ta société plus tard)
   contact: "contact@ton-domaine.fr", // une adresse où l'on peut te joindre
   ```
3. **Commit changes**. Le site se republie tout seul en quelques minutes.

Conseil : crée une adresse dédiée (par exemple `kelvisi.contact@…`) plutôt
que ton adresse personnelle, puisqu'elle sera publique.

## 6. Partager les retours terrain (facultatif, conseillé pour la bêta)

Sans cette étape, l'appli fonctionne, mais chaque retour « Tu y étais ? »
reste sur le téléphone de la personne. Avec elle, les retours sur les points
Kelvisi sont mis en commun et corrigent la prévision de tout le monde.

1. Crée un compte gratuit sur supabase.com, puis un projet :
   - nom : `kelvisi` ;
   - région : **une région européenne** (Paris ou Francfort), car la page
     Confidentialité annonce un hébergement dans l'Union européenne ;
   - note le mot de passe de base de données dans ton gestionnaire de mots
     de passe (on ne s'en sert pas ici).
2. Dans le projet : **SQL Editor** > nouvelle requête > colle tout le contenu
   du fichier `supabase/schema.sql` > **Run**. Cela crée la table des retours
   avec les bonnes protections (dépôt anonyme possible, lecture publique
   impossible).
3. Dans **Settings > API Keys**, repère :
   - l'adresse du projet (`https://xxxx.supabase.co`, aussi visible dans
     **Settings > Data API** ou sur la page d'accueil du projet) ;
   - la clé **publishable** (`sb_publishable_…`) : elle est faite pour être
     publique ;
   - la clé **secret** (`sb_secret_…`) : elle ne doit **jamais** être publiée.
4. Dans `app/js/config.js` (comme à l'étape 5), remplis :
   ```js
   supabaseUrl: "https://xxxx.supabase.co",
   supabaseCleAnon: "sb_publishable_…",
   ```
5. Dans GitHub : **Settings > Secrets and variables > Actions >
   New repository secret**, crée deux secrets :
   - `SUPABASE_URL` : l'adresse du projet ;
   - `SUPABASE_SERVICE_KEY` : la clé **secret**.

Le calcul horaire lit alors les retours des 90 derniers jours et corrige
chaque point. Le journal du calcul (onglet Actions) affiche
« Retours terrain lus : N ».

À savoir : un projet Supabase gratuit se met en pause après une semaine sans
activité. La lecture horaire devrait suffire à le garder actif ; s'il se met
quand même en pause, un bouton dans Supabase le relance.

Les anciennes clés `anon` et `service_role` fonctionnent aussi, mais Supabase
annonce leur arrêt pour fin 2026 : prends les nouvelles.

## 7. Activer le satellite Copernicus (facultatif, non testé)

Le satellite recale la prévision sur la turbidité réellement observée
(Sentinel-3, 300 m, une image par jour quand il n'y a pas de nuages).
**Cette partie n'a pas pu être essayée sur le vrai service** : l'accès à
Copernicus était fermé pendant le développement. Elle est conçue pour ne
jamais bloquer le reste : en cas de souci, les prévisions sont publiées sans
satellite.

1. Dans GitHub, **Settings > Secrets and variables > Actions**, crée deux
   secrets avec les identifiants de ton compte Copernicus Marine :
   - `COPERNICUSMARINE_SERVICE_USERNAME`
   - `COPERNICUSMARINE_SERVICE_PASSWORD`
2. Relance le calcul (étape 3) et ouvre le journal de l'étape « Calculer les
   prévisions ». Tu dois lire « Satellite : N points avec une image
   exploitable ».
3. Si le journal indique « satellite indisponible » avec un nom de jeu de
   données introuvable, envoie-moi le message : il suffira de corriger le nom
   dans **Settings > Secrets and variables > Actions > Variables**
   (`KELVISI_SAT_ATL_TRANSP`, etc.), sans toucher au code.

Quand le satellite fonctionne, la page « Sources » affiche automatiquement la
mention obligatoire « Generated using E.U. Copernicus Marine Service
Information ».

## 8. Plus tard : nom de domaine

Quand tu auras réservé `kelvisi.fr` (ou autre) :

1. **Settings > Pages > Custom domain** : saisis le domaine, enregistre.
2. Chez ton registraire, ajoute les enregistrements DNS indiqués par la page
   d'aide GitHub « Managing a custom domain for your GitHub Pages site »
   (quatre adresses `A` pour le domaine nu, ou un `CNAME` vers
   `ton-pseudo.github.io` pour `www`).
3. Coche **Enforce HTTPS** dès que GitHub le propose.

Les spots privés et réglages sont stockés par adresse de site : en changeant
d'adresse, les testeurs repartent de zéro (ils peuvent copier leurs spots
depuis « Mes spots » avant le changement et les réimporter après).

## 9. Avant de rendre l'appli payante

- **Open-Meteo** est gratuit pour un usage non commercial seulement. Pour une
  version payante, il faut un abonnement Open-Meteo. Le calcul horaire est
  prêt : ajoute la clé dans le secret `OPEN_METEO_CLE`. Les calculs faits
  dans le navigateur (lieux recherchés, spots privés) appellent Open-Meteo
  directement : il faudra soit passer ces appels par un petit relais, soit
  accepter que la clé soit visible.
- **Mentions légales** : une activité payante impose d'indiquer l'éditeur
  complet (statut, SIRET). La micro-entreprise suffit pour commencer.
- **Paiement** : rien n'est codé pour l'instant (pas de comptes). Ce sera la
  prochaine grosse étape.

## Entretien courant

- **GitHub coupe le calcul horaire après 60 jours sans modification du
  dépôt.** Il prévient par courriel. Pour le relancer : onglet Actions >
  bouton **Enable workflow**, ou n'importe quelle petite modification du
  dépôt (par exemple corriger une note de spot).
- **Ajouter ou corriger un point Kelvisi** : fichier `spots/points.json`.
  Chaque point a un identifiant, un nom, une position (à 500 m environ du
  bord, côté mer), une région (`manche`, `atlantique`, `mediterranee`),
  l'orientation vers le large en degrés (0 = nord, 90 = est…), l'ouverture,
  la profondeur, le fond (`roche`, `mixte`, `sable`, `vase`) et une note. Le
  plus sûr est de m'envoyer la liste des changements.
- **Une prévision paraît fausse** : les retours « Tu y étais ? » la corrigent
  automatiquement. Si elle reste fausse, c'est souvent l'orientation ou la
  profondeur du point qui est mal réglée.

## Ce qui est vérifié et ce qui ne l'est pas

| Élément | État |
| --- | --- |
| Calcul des prévisions avec la vraie météo Open-Meteo (46 points) | Lancé avec succès sur les vraies données |
| Débits des rivières Hub'Eau (Seine, Loire, Vilaine, Adour, Rhône, Var) | Lancé avec succès sur les vraies données |
| Interface (navigation, fiches, recherche, spots privés, retours) | Testée automatiquement, version mobile et ordinateur |
| Même résultat entre le calcul du navigateur et celui du serveur | Vérifié automatiquement |
| Carte dans un vrai navigateur (Chromium, téléphone et ordinateur) | Vérifiée avec le fond de secours : repères bien placés, fiche rapide, fiches |
| Fonds de carte en ligne (OpenFreeMap, vue aérienne IGN, profondeurs EMODnet) | À vérifier à l'étape 4 : ces serveurs n'étaient pas joignables pendant le développement |
| Recherche de lieux (IGN) et profondeur au point (EMODnet) depuis un téléphone | À vérifier à l'étape 4, pour la même raison |
| Satellite Copernicus | Codé, testé sur données simulées, jamais lancé sur le vrai service |
| Partage des retours (Supabase) | Testé avec un faux serveur ; à vérifier après l'étape 6 en envoyant un retour |
| Réglages du modèle (« À CALER ») | Ordres de grandeur de la littérature ; seront ajustés avec le satellite et les retours de la bêta |
