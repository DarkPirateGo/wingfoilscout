/* Wingfoilscout — der Service Worker fürs iPhone (seit 2.5.3).

   Gemeldet am 11.10.2026: Ist das iPhone eingerichtet, gibt der Mac aber
   nicht frei (seit dem Start kein „QR-Code zeigen“), öffnet das Symbol auf
   dem Home-Bildschirm einen schwarzen Bildschirm. Ohne Freigabe kommt nichts
   beim Mac an, der Mac kann also keine Seite schicken — der Hinweis muss
   schon auf dem iPhone liegen. Diesen Hinweis legt dieser Service Worker beim
   ersten Besuch ab (GET /handy/hinweis, mit dem Schlüssel im Cookie) und
   zeigt ihn, wenn eine Seite nicht ankommt.

   Er tut absichtlich wenig:
   - Seitenaufrufe (Navigationen) gehen unverändert ans Netz. Nur wenn keine
     Antwort kommt — die Verbindung scheitert oder nach FRIST_MS ist noch
     nichts da —, zeigt er den abgelegten Hinweis. Jede Antwort des Macs, auch
     „Kein Zugang“ oder „Nur noch verschlüsselt“, kommt so an, wie sie ist.
   - Abgelegt wird nur der Hinweis, keine Seite mit Daten.
   - Nach dem Sprachumschalter (POST /sprache) holt er den Hinweis neu, in
     der neuen Sprache.
   Alles andere (Daten, Bilder, Formulare) berührt er nicht.

   VERSION setzt der Server davor (webui.SW_JS): mit jeder neuen Version
   ändert sich die Datei, der Browser installiert sie neu und holt den
   Hinweis frisch. Angemeldet wird er von web/sw-anmelden.js — nur auf den
   Seiten für andere Geräte und nur über https (Service Worker gibt es nur
   in einem sicheren Kontext). */
'use strict';

var HINWEIS = '/handy/hinweis';
var KASTEN = 'wingfoilscout-hinweis-' + VERSION;
var FRIST_MS = 10000;

function hinweisHolen() {
  return fetch(HINWEIS, {credentials: 'same-origin', cache: 'no-store'}).then(function (antwort) {
    if (!antwort.ok) throw new Error('Hinweis: ' + antwort.status);
    return caches.open(KASTEN).then(function (kasten) { return kasten.put(HINWEIS, antwort); });
  });
}

function mitFrist(versprechen) {
  return new Promise(function (ja, nein) {
    var uhr = setTimeout(function () { nein(new Error('Frist')); }, FRIST_MS);
    versprechen.then(function (a) { clearTimeout(uhr); ja(a); },
                     function (f) { clearTimeout(uhr); nein(f); });
  });
}

self.addEventListener('install', function (e) {
  // Ohne abgelegten Hinweis gilt die Installation als gescheitert — der
  // Browser versucht es beim nächsten Besuch wieder.
  e.waitUntil(hinweisHolen().then(function () { return self.skipWaiting(); }));
});

self.addEventListener('activate', function (e) {
  e.waitUntil(caches.keys().then(function (namen) {
    return Promise.all(namen.filter(function (n) {
      return n.indexOf('wingfoilscout-hinweis-') === 0 && n !== KASTEN;
    }).map(function (n) { return caches.delete(n); }));
  }).then(function () { return self.clients.claim(); }));
});

self.addEventListener('fetch', function (e) {
  var anfrage = e.request;
  if (anfrage.mode === 'navigate' && anfrage.method === 'GET') {
    e.respondWith(mitFrist(fetch(anfrage)).catch(function () {
      return caches.open(KASTEN).then(function (kasten) { return kasten.match(HINWEIS); })
        .then(function (hinweis) { return hinweis || Response.error(); });
    }));
    return;
  }
  if (anfrage.method === 'POST' && new URL(anfrage.url).pathname === '/sprache') {
    var antwort = fetch(anfrage);
    e.respondWith(antwort);
    e.waitUntil(antwort.then(function (a) { if (a.ok) return hinweisHolen(); })
      .catch(function () {}));
  }
});
