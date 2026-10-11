/* Den Service Worker anmelden (seit 2.5.3, siehe web/sw.js) — nur auf den
   Seiten für andere Geräte (webui.mobil_js) und nur in einem sicheren Kontext:
   über https mit dem Zertifikat des Macs. Über http gibt es am iPhone keinen
   Service Worker; dort bleibt es beim Verhalten wie bisher. Scheitert die
   Anmeldung, merkt man davon nichts — die Seite läuft wie ohne. */
(function () {
  if (!window.isSecureContext || !('serviceWorker' in navigator)) return;
  navigator.serviceWorker.register('/sw.js').catch(function () {});
})();
