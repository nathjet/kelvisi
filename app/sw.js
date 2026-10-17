// Service worker : l'appli s'ouvre même sans réseau, avec les dernières prévisions reçues.
// La version est remplacée à chaque publication (voir .github/workflows/previsions.yml).

const VERSION = "kelvisi-__VERSION__";
const COQUILLE = [
  "./",
  "index.html",
  "styles.css",
  "manifest.webmanifest",
  "vendor/maplibre-gl.js",
  "vendor/maplibre-gl.css",
  "js/app.js",
  "js/bathymetrie.js",
  "js/carte.js",
  "js/compte.js",
  "js/config.js",
  "js/donnees.js",
  "js/favoris.js",
  "js/format.js",
  "js/messpots.js",
  "js/profondeur.js",
  "js/recherche.js",
  "js/relief.js",
  "js/relief-rendu.js",
  "js/relief-travail.js",
  "js/retours.js",
  "js/stockage.js",
  "js/synchro.js",
  "js/communaute.js",
  "js/moteur/moteur.js",
  "js/moteur/openmeteo.js",
  "js/vues/compte.js",
  "js/vues/fiche.js",
  "js/vues/infos.js",
  "js/vues/liste.js",
  "js/vues/messpots.js",
  "polices/archivo-latin-wdth-normal.woff2",
  "polices/atkinson-hyperlegible-latin-400-normal.woff2",
  "polices/atkinson-hyperlegible-latin-700-normal.woff2",
  "icones/icone-192.png",
  "icones/favicon-32.png",
  "fond/terre.geojson",
];

self.addEventListener("install", (e) => {
  e.waitUntil(caches.open(VERSION).then((c) => c.addAll(COQUILLE)).then(() => self.skipWaiting()));
});

self.addEventListener("activate", (e) => {
  e.waitUntil(
    caches.keys()
      .then((cles) => Promise.all(cles.filter((k) => k !== VERSION).map((k) => caches.delete(k))))
      .then(() => self.clients.claim()),
  );
});

self.addEventListener("fetch", (e) => {
  const url = new URL(e.request.url);
  if (e.request.method !== "GET" || url.origin !== self.location.origin) return;

  // Prévisions : réseau d'abord, dernière version connue si hors ligne
  if (url.pathname.includes("/donnees/")) {
    e.respondWith(
      fetch(e.request)
        .then((r) => {
          if (r.ok) {
            const copie = r.clone();
            caches.open(VERSION).then((c) => c.put(e.request, copie));
          }
          return r;
        })
        .catch(() => caches.match(e.request, { ignoreSearch: true })),
    );
    return;
  }

  // Application : cache d'abord, réseau sinon
  e.respondWith(
    caches.match(e.request, { ignoreSearch: true }).then((r) => r || fetch(e.request).then((rep) => {
      if (rep.ok) {
        const copie = rep.clone();
        caches.open(VERSION).then((c) => c.put(e.request, copie));
      }
      return rep;
    })),
  );
});
