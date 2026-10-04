
/* Was gerade läuft, sieht man auf jedem Reiter (seit 1.18.3): ein pulsender
   Punkt am Reiter der Seite, die den Lauf gestartet hat — Suche, Rückblick
   oder Tagebuch —, und ist eine Suche fertig, seit diese Seite offen ist, ein
   stiller Punkt an „Ziele“: der Report ist neuer als das, was man sieht. Ein
   Lauf gehört zum Programm, nicht zum Fenster; Hin- und Herwechseln bricht
   nichts ab, und das soll man auch sehen. Fragt alle zwei Sekunden nach
   /status; hört auf, wenn das Programm nicht mehr antwortet (Beenden). */
(function () {
  var nav = document.querySelector('nav.reiter');
  if (!nav) return;
  var links = {}, titel = {}, seitenstart = Date.now() / 1000, fehler = 0, uhr = null;
  [].forEach.call(nav.querySelectorAll('a[href]'), function (a) {
    links[a.getAttribute('href')] = a; titel[a.getAttribute('href')] = a.title || '';
  });
  var WOHER = {run: '/', ingest: '/', rueckblick: '/rueckblick', tagebuch: '/tagebuch'};
  function markiere(klasse, ziel, text) {
    Object.keys(links).forEach(function (k) {
      links[k].classList.remove(klasse);
      if (!links[k].classList.contains('laeuft') && !links[k].classList.contains('neu')) links[k].title = titel[k];
    });
    var a = ziel ? links[ziel] : null;
    if (!a || a.classList.contains('an')) return;
    a.classList.add(klasse); a.title = text;
  }
  function frage() {
    fetch('/status', {cache: 'no-store'}).then(function (r) { return r.json(); }).then(function (j) {
      fehler = 0;
      if (j.state === 'running') {
        markiere('neu', null, '');
        markiere('laeuft', WOHER[j.kind] || '/', t('läuft gerade — im Hintergrund, auch wenn du den Reiter wechselst'));
      } else {
        markiere('laeuft', null, '');
        var frisch = j.state === 'done' && j.kind === 'run' && j.ende && j.ende > seitenstart;
        markiere('neu', frisch ? '/report' : null, t('neuer Report, seit diese Seite offen ist'));
      }
    }).catch(function () {
      if (++fehler >= 3 && uhr) { clearInterval(uhr); uhr = null; }
    });
  }
  frage();
  uhr = setInterval(frage, 2000);
  document.addEventListener('visibilitychange', function () { if (!document.hidden) frage(); });
})();
