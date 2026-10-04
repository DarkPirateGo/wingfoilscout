/* Der Report am Handy (seit 1.17.0).

   Am Rechner steht alles untereinander da, und das ist richtig so: ein großer
   Bildschirm zeigt Kopf, Karte und Ziele nebeneinander weg. Am Handy sind
   dieselben Abschnitte drei Wischer, bevor die Antwort kommt — deshalb sind
   Parameter und Karte dort zugeklappt. Geöffnet wird die Karte erst auf
   Wunsch; Leaflet muss dann seine Größe neu messen, weil es in einem
   geschlossenen <details> keine hatte. */
(function () {
  var handy = window.matchMedia('(max-width: 700px)');
  var klappen = [].slice.call(document.querySelectorAll('details.zu-am-handy'));
  if (!klappen.length) return;

  function anpassen() {
    klappen.forEach(function (d) {
      // Nur der Startzustand: was der Leser selbst geöffnet hat, bleibt offen.
      if (d.dataset.beruehrt) return;
      d.open = !handy.matches;
    });
  }
  klappen.forEach(function (d) {
    d.addEventListener('toggle', function () {
      d.dataset.beruehrt = '1';
      if (d.open) document.dispatchEvent(new CustomEvent('wingscout:sichtbar', {detail: d.id || ''}));
    });
  });
  anpassen();
  if (handy.addEventListener) handy.addEventListener('change', anpassen);
})();

/* Stundenraster: Tipp auf eine Zelle zeigt, was sonst nur der Tooltip sagt
   (seit 1.19.0). Am Handy gibt es kein Hover, mit der Tastatur keinen Fokus
   auf tausend Zellen — der Text der Zelle erscheint deshalb in einem Kasten
   unter dem Raster, der nächste Tipp ersetzt ihn, ein Tipp daneben schließt
   ihn. Am Rechner geht der Klick genauso; der Tooltip bleibt. */
(function () {
  var raster = document.getElementById('hmraster');
  if (!raster) return;
  var kasten = document.createElement('div');
  kasten.className = 'zellinfo';
  kasten.hidden = true;
  raster.parentNode.insertBefore(kasten, raster.nextSibling);
  var aktiv = null;
  function schliessen() {
    kasten.hidden = true;
    if (aktiv) { aktiv.classList.remove('gewaehlt'); aktiv = null; }
  }
  raster.addEventListener('click', function (e) {
    var zelle = e.target.closest ? e.target.closest('.cell') : null;
    if (!zelle || !zelle.title) { schliessen(); return; }
    var name = zelle.closest('.hm');
    var spot = name ? name.querySelector('.hmname a') : null;
    if (aktiv) aktiv.classList.remove('gewaehlt');
    aktiv = zelle; zelle.classList.add('gewaehlt');
    kasten.textContent = (spot ? spot.textContent + ' · ' : '') + zelle.title;
    kasten.hidden = false;
  });
  document.addEventListener('click', function (e) {
    if (!kasten.hidden && !raster.contains(e.target) && e.target !== kasten) schliessen();
  });
})();
