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

Fait le 17 octobre 2026 avec ton adresse Gmail. Quand tu auras une adresse
dédiée (par exemple `contact@kelvisi.fr`), remplace simplement `contact` de
la même façon : elle est publique, mieux vaut ne pas y laisser ton adresse
personnelle trop longtemps.

## 6. Comptes et base clients (Supabase)

Les comptes sont obligatoires : tant que Supabase n'est pas branché, l'appli
fonctionne sans compte ; dès que Claude a mis l'adresse et la clé publique
du projet dans `app/js/config.js`, l'écran d'inscription s'affiche pour tout
le monde. Fais donc les étapes a à d **avant** d'envoyer ces deux valeurs.

### a. Créer le projet

Sur supabase.com : nouveau projet `kelvisi`, région **Paris** (ou
Frankfurt). La page Confidentialité annonce un hébergement dans l'Union
européenne. Note le mot de passe de la base dans ton gestionnaire de mots de
passe.

### b. Créer les tables

**SQL Editor** > nouvelle requête > colle tout le fichier
`supabase/schema.sql` > **Run**. Le script crée les profils, les spots
privés, les favoris, les retours terrain, les règles d'accès (chacun ne voit
que ses données), la suppression de compte et ta liste de clients. Il peut
être relancé sans risque après une mise à jour. Il est testé automatiquement
sur une base PostgreSQL à chaque modification (workflow « Base de données »).

### c. Régler la connexion

Dans **Authentication** :

- **URL Configuration** : *Site URL* = `https://nathjet.github.io/kelvisi/`.
  Dans *Redirect URLs*, ajoute `https://nathjet.github.io/kelvisi/**`. Ce
  sont les adresses vers lesquelles renvoient les liens des e-mails.
- **Sign In / Providers** > **Email** : laisse *Email* activé, mets la
  longueur minimale du mot de passe à **8**.
  *Confirm email* : **désactive-le pour commencer** (voir e. ci-dessous),
  puis réactive-le dès que les e-mails passent par Brevo.

### d. Envoyer les clés

Dans **Project Settings** > **API Keys** :

- envoie à Claude l'adresse du projet (`https://xxxx.supabase.co`) et la clé
  **publishable** (`sb_publishable_…`), faite pour être publique ;
- mets la clé **secret** (`sb_secret_…`) uniquement dans les secrets GitHub
  (**Settings > Secrets and variables > Actions**) : `SUPABASE_SERVICE_KEY`,
  avec l'adresse du projet dans `SUPABASE_URL`. Elle sert au calcul horaire
  (lecture des retours terrain, effacement des comptes inactifs depuis 3 ans).

### e. Les e-mails (confirmation d'inscription, mot de passe oublié)

Le service d'e-mails intégré à Supabase n'envoie qu'aux membres de ton
équipe Supabase, et deux e-mails par heure au plus : tes utilisateurs ne
recevraient rien. D'où le réglage *Confirm email* désactivé au départ.
Conséquence en attendant : les inscriptions fonctionnent, mais « Mot de
passe oublié » n'enverra rien, et les adresses ne sont pas vérifiées.

Dès que tu as ton nom de domaine :

1. Crée un compte gratuit **Brevo** (300 e-mails par jour). Dans *Senders,
   Domains & Dedicated IPs*, ajoute ton domaine et les enregistrements DNS
   qu'il indique, puis crée l'expéditeur `contact@ton-domaine.fr`.
2. Dans Brevo, *Settings* > *SMTP & API* > onglet *SMTP* : génère une clé
   SMTP (pas une clé API).
3. Dans Supabase, **Authentication** > **Emails** > **SMTP Settings** :
   active *Enable custom SMTP* et saisis : expéditeur `contact@ton-domaine.fr`,
   nom `Kelvisi`, hôte `smtp-relay.brevo.com`, port `587`, identifiant = ton
   adresse de connexion Brevo, mot de passe = la clé SMTP.
4. **Authentication** > **Emails** > **Templates** : remplace les modèles
   « Confirm signup » et « Reset Password » par ceux du dossier
   `supabase/emails/` (objets indiqués en tête de chaque fichier).
5. Réactive *Confirm email* (étape c).

### f. Voir et exporter tes clients

**SQL Editor** > `select * from admin.clients;` > **Run**, puis **Export**
(CSV, à ouvrir dans Excel). Tu y trouves l'e-mail, le prénom, le
département, les pratiques, la tranche d'âge, l'accord e-mails (et sa date),
la date d'inscription, la dernière connexion, le nombre de spots et de
retours. **Tu ne vois jamais l'emplacement des spots privés.**

Pour une newsletter, n'envoie qu'aux lignes où `accord_emails` vaut `true`
(c'est la loi : l'accord doit être donné avant l'envoi), avec un lien de
désinscription dans chaque e-mail. Un utilisateur peut retirer son accord
dans « Mon compte ».

### g. Valider les spots partagés

Les utilisateurs peuvent proposer un de leurs spots à tous. Il n'apparaît
qu'après ta validation, sans le nom de son auteur.

**À faire une fois** (17 octobre 2026) : **SQL Editor** > nouvelle requête >
colle tout le fichier `supabase/schema.sql` > **Run**. Tant que ce n'est pas
fait, le bouton de partage reste caché et tout fonctionne comme avant.

**Quand un spot est proposé** : le cadre **Bilan du calcul** (onglet
**Actions** de GitHub, passage « Prévisions et publication ») affiche
« Spots proposés au partage, en attente de ta validation : N ».

1. **SQL Editor** > `select * from admin.spots_a_valider;` > **Run**. Pour
   chaque spot : son nom, sa position, un lien `carte` à ouvrir pour voir où
   il est, et l'adresse de la personne qui le propose.
2. Vérifie qu'il n'est pas dans une réserve ou une zone interdite à la
   chasse, et que son nom est correct.
3. **Table Editor** > `spots_prives` > filtre `partage` égal à `en_attente`,
   puis dans la colonne `partage` remplace la valeur par `publie` (accepté)
   ou `refuse`. Le spot apparaît (ou non) chez les autres en quelques
   minutes.

Pour retirer un spot déjà publié, mets `refuse` de la même façon. Si son
auteur le modifie, il repasse tout seul en attente de validation.

À savoir : un projet Supabase gratuit se met en pause après une semaine sans
activité. Le calcul horaire lit la base toutes les heures, ce qui suffit en
principe à le garder actif.

## 7. Satellite Copernicus (en service)

Le satellite recale la prévision sur la turbidité réellement observée
(produits côtiers Sentinel-2 et Sentinel-3, environ 100 m, une image par jour
quand il n'y a pas de nuages). Il tourne depuis le 16 octobre 2026. En cas de
souci, les prévisions sont publiées sans satellite : rien ne bloque.

- Identifiants : deux secrets GitHub, `COPERNICUSMARINE_SERVICE_USERNAME`
  (nom d'utilisateur ou e-mail) et `COPERNICUSMARINE_SERVICE_PASSWORD`. Il
  faut un compte créé directement sur Copernicus Marine : un compte ouvert
  avec « Login with CDSE » n'a pas de mot de passe Copernicus Marine et
  l'outil le refuse.
- Contrôle : dans **Actions**, ouvre un passage de « Prévisions et
  publication ». Le cadre **Bilan du calcul** indique par exemple
  « Satellite : 27 points sur 46 avec une image exploitable ». Par temps
  couvert, ce nombre baisse : c'est normal.
- Si le bilan indique « satellite indisponible » avec un nom de jeu de
  données introuvable, envoie-moi le message : il suffira de corriger le nom
  dans **Settings > Secrets and variables > Actions > Variables**
  (`KELVISI_SAT_NWS`, `KELVISI_SAT_IBI`, `KELVISI_SAT_MED`), sans toucher au
  code.
- Si tu changes le mot de passe de ton compte Copernicus Marine, mets aussi à
  jour le secret, sinon le satellite s'arrête (sans bloquer le reste).

La page « Sources » affiche automatiquement la mention obligatoire
« Generated using E.U. Copernicus Marine Service Information ».

### Recaler le modèle

Les réglages du modèle sont calés sur l'historique satellite (voir le README,
section « Calage sur le satellite »). Pour refaire le calage avec des données
plus récentes :

1. **Actions > Calage > Run workflow**, étape `collecter`. Chaque lancement
   ajoute des années d'historique ; Open-Meteo gratuit limite le nombre
   d'appels par jour, d'où un budget de 2 000 à 4 000 appels par lancement et
   au plus un ou deux lancements par jour.
2. Puis, sur un ordinateur avec le dépôt : récupérer la branche `historique`
   dans un dossier `historique/` et lancer
   `python outils/caler.py --appliquer` (compter
   une dizaine de minutes). Les valeurs retenues sont écrites dans
   `prevision/parametres.py` et `spots/points.json`, le rapport dans
   `calage/resultat.json`.

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
- **Hébergement** : GitHub Pages n'est pas autorisé pour faire tourner une
  activité commerciale. Avant de faire payer, il faut déplacer le site
  (Cloudflare Pages, Netlify ou un hébergeur français), ce qui prend une heure.
- **Supabase** : la formule gratuite est permise, mais pour des clients
  payants la formule Pro (environ 25 $ par mois) apporte les sauvegardes et
  évite la mise en pause.
- **Paiement** : rien n'est codé pour l'instant. Ce sera la prochaine grosse
  étape.

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
| Calcul des prévisions avec la vraie météo Open-Meteo (97 points) | Lancé avec succès sur les vraies données |
| Débits des rivières Hub'Eau (Seine, Loire, Vilaine, Adour, Rhône, Var) | Lancé avec succès sur les vraies données |
| Interface (navigation, fiches, recherche, spots privés, retours) | Testée automatiquement, version mobile et ordinateur |
| Même résultat entre le calcul du navigateur et celui du serveur | Vérifié automatiquement |
| Carte dans un vrai navigateur (Chromium, téléphone et ordinateur) | Vérifiée : repères bien placés, fiche rapide, fiches |
| Fonds de carte en ligne (OpenFreeMap, vue aérienne IGN), carte des profondeurs redessinée | Vérifiés dans un vrai navigateur sur les vrais services (workflow « Diagnostic ») |
| Recherche de lieux (IGN) et profondeur au point (Shom, EMODnet) | Vérifiées de la même façon |
| Satellite Copernicus | En service sur le vrai service : 27 points sur 46 recalés au premier passage (16 octobre 2026) |
| Calage du modèle sur le satellite | Fait sur janvier 2024 à octobre 2026 (95 points, 11 007 images) et vérifié sur une période mise de côté ; 2022 et 2023 en cours de collecte |
| Comptes (inscription, connexion, mot de passe oublié, profil, synchronisation, suppression) | Testés de bout en bout avec un faux serveur ; schéma testé sur un vrai PostgreSQL ; à vérifier sur ton projet après l'étape 6 |
| Profondeurs du Shom lues au point et direction du large | Vérifiées dans Chromium sur les vraies cartes du Shom (Bretagne, Provence, Pays basque, Normandie, Corse) |
| Conversion turbidité en mètres, plancton (« À CALER ») | Ordres de grandeur de la littérature ; seront ajustés avec les retours de la bêta |
