/* SYNERGIE — service worker.
   ---------------------------------------------------------------------------------
   Son seul rôle : rendre l'application INSTALLABLE (sur ordinateur comme sur
   téléphone) et lui permettre de s'ouvrir même avec une connexion capricieuse.

   Règles tenues ici :
     • seuls les fichiers de l'application (page, styles, script, icônes) sont gardés
       en réserve — jamais les données : l'API est TOUJOURS demandée au serveur, sinon
       on verrait un vote ou une note périmés ;
     • à chaque nouvelle version, la réserve est remplacée (CACHE_VERSION).
*/
const CACHE_VERSION = 3;
const RESERVE = `synergie-${CACHE_VERSION}`;
const FICHIERS = [
  '/', '/synergie.css', '/synergie.js', '/manifest.webmanifest',
  '/icone-192.png', '/icone-512.png', '/icone-maskable-512.png'
];

self.addEventListener('install', (evenement) => {
  evenement.waitUntil(
    caches.open(RESERVE).then((reserve) => reserve.addAll(FICHIERS)).then(() => self.skipWaiting())
  );
});

self.addEventListener('activate', (evenement) => {
  evenement.waitUntil(
    caches.keys()
      .then((noms) => Promise.all(noms.filter((nom) => nom !== RESERVE)
        .map((nom) => caches.delete(nom))))
      .then(() => self.clients.claim())
  );
});

self.addEventListener('fetch', (evenement) => {
  const requete = evenement.request;
  if (requete.method !== 'GET') return;
  const adresse = new URL(requete.url);
  if (adresse.origin !== self.location.origin) return;
  // Les données (API) et les flux temps réel ne sont JAMAIS mis en réserve.
  if (adresse.pathname.startsWith('/api/')) return;

  // Fichiers de l'application : le réseau d'abord (pour avoir la dernière version),
  // la réserve ensuite (pour fonctionner hors connexion).
  evenement.respondWith(
    fetch(requete)
      .then((reponse) => {
        const copie = reponse.clone();
        caches.open(RESERVE).then((reserve) => reserve.put(requete, copie)).catch(() => {});
        return reponse;
      })
      .catch(() => caches.match(requete).then((trouve) => trouve || caches.match('/')))
  );
});
