var f = document.getElementById('f'), go = document.getElementById('go'),
    panel = document.getElementById('panel'), logEl = document.getElementById('log'),
    banner = document.getElementById('banner'), frame = document.getElementById('frame'),
    hint = document.getElementById('hint'), wrap = document.getElementById('wrap'),
    statusbox = document.getElementById('statusbox'), statustext = document.getElementById('statustext'),
    protokoll = document.getElementById('protokoll'), timer = null;

function post(url) {
  return fetch(url, {method: 'POST', body: new URLSearchParams(new FormData(f))});
}

/* ── Voreinstellungen: ein Klick setzt Tage, Nächte und Radius ─────────── */
var presets = [].slice.call(document.querySelectorAll('.preset')),
    felder = {tage: f.days, naechte: f.nights, radius: f.radius},
    eigen = document.getElementById('eigen');

function presetAbgleich() {
  var treffer = null;
  presets.forEach(function (p) {
    var passt = Number(p.dataset.tage) === Number(felder.tage.value) &&
                Number(p.dataset.naechte) === Number(felder.naechte.value) &&
                Number(p.dataset.radius) === Number(felder.radius.value);
    p.setAttribute('aria-pressed', passt ? 'true' : 'false');
    if (passt) treffer = p;
  });
  eigen.textContent = treffer ? '' :
    t('Eigene Einstellung: {tage} Tage, {naechte} Nächte, {km} km',
      {tage: felder.tage.value, naechte: felder.naechte.value, km: felder.radius.value});
}

presets.forEach(function (p) {
  p.addEventListener('click', function () {
    felder.tage.value = p.dataset.tage;
    felder.naechte.value = p.dataset.naechte;
    felder.radius.value = p.dataset.radius;
    presetAbgleich();
  });
});
[felder.tage, felder.naechte, felder.radius].forEach(function (el) {
  el.addEventListener('input', presetAbgleich);
});
presetAbgleich();

/* ── Ab wann (seit 2.3.0): „Jetzt“ leert das Feld — leer heißt jetzt ──── */
var abFeld = document.getElementById('ab'), abJetzt = document.getElementById('abjetzt');
if (abFeld && abJetzt) {
  abJetzt.addEventListener('click', function () { abFeld.value = ''; abFeld.focus(); });
}

/* ── Position ──────────────────────────────────────────────────────────── */
var gps = document.getElementById('gps'), gpsmsg = document.getElementById('gpsmsg');

function gpsSay(text, bad) {
  gpsmsg.textContent = text;
  gpsmsg.style.color = bad ? 'var(--stop, #b3261e)' : 'var(--muted)';
}
function gpsDone() { gps.disabled = false; gps.textContent = t('Hier'); }
function gpsTake(p) {
  document.getElementById('start').value =
    p.coords.latitude.toFixed(5) + ', ' + p.coords.longitude.toFixed(5);
  gpsDone();
  gpsSay(t('Position übernommen, auf etwa {m} m genau.', {m: Math.round(p.coords.accuracy)}), false);
}
function gpsFail(err) {
  gpsDone();
  var help = {
    1: t('Der Browser darf nicht orten. In den Website-Einstellungen den Standort erlauben — und unter macOS zusätzlich in Systemeinstellungen → Datenschutz & Sicherheit → Ortungsdienste den Browser freigeben.'),
    2: t('Das Betriebssystem liefert keine Position. Unter macOS meist: Ortungsdienste aus oder für diesen Browser nicht freigegeben.'),
    3: t('Zeitüberschreitung — keine Antwort vom Ortungsdienst.')
  }[err && err.code] || (err && err.message) || t('Unbekannter Fehler.');
  gpsSay(t('Ortung fehlgeschlagen: {grund} Nimm stattdessen die Karte.', {grund: help}), true);
}

gps.addEventListener('click', function () {
  if (!navigator.geolocation) { gpsFail({message: t('Dieser Browser kennt keine Ortung.')}); return; }
  if (!window.isSecureContext) {
    gpsFail({message: t('Die Seite gilt dem Browser nicht als sicher ({adresse}).', {adresse: location.origin})});
    return;
  }
  gps.disabled = true; gps.textContent = t('Suche …');
  gpsSay(t('Frage den Ortungsdienst … beim ersten Mal dauert das 10–20 Sekunden.'), false);
  navigator.geolocation.getCurrentPosition(gpsTake, function () {
    gpsSay(t('Genaue Ortung ging nicht, versuche die grobe …'), false);
    navigator.geolocation.getCurrentPosition(gpsTake, gpsFail,
      {enableHighAccuracy: false, timeout: 20000, maximumAge: 300000});
  }, {enableHighAccuracy: true, timeout: 12000, maximumAge: 60000});
});

/* ── Karte ─────────────────────────────────────────────────────────────── */
var pick = document.getElementById('pick'), pickmap = document.getElementById('pickmap'),
    pmap = null, pmark = null;

function loadLeaflet(done) {
  if (window.L) { done(); return; }
  // Mit Prüfsumme wie auf der Prüfseite: ein nachgeladenes Skript ohne
  // `integrity` wäre die eine Stelle, an der fremder Code in diese Seite käme.
  var css = document.createElement('link');
  css.rel = 'stylesheet';
  css.href = LEAFLET.css;
  css.integrity = LEAFLET.cssSri;
  css.crossOrigin = 'anonymous';
  document.head.appendChild(css);
  var js = document.createElement('script');
  js.src = LEAFLET.js;
  js.integrity = LEAFLET.jsSri;
  js.crossOrigin = 'anonymous';
  js.onload = done;
  js.onerror = function () {
    gpsSay(t('Karte lässt sich nicht laden — keine Verbindung zum Kartendienst. Koordinaten bitte eintippen oder einfügen.'), true);
  };
  document.head.appendChild(js);
}

function startCoords() {
  var m = (document.getElementById('start').value || '')
          .match(/(-?[0-9]{1,3}(?:[.,][0-9]+)?)[^0-9-]+(-?[0-9]{1,3}(?:[.,][0-9]+)?)/);
  if (!m) return [HOME.lat, HOME.lon];
  var a = parseFloat(m[1].replace(',', '.')), b = parseFloat(m[2].replace(',', '.'));
  if (isNaN(a) || isNaN(b) || Math.abs(a) > 90 || Math.abs(b) > 180) return [HOME.lat, HOME.lon];
  return [a, b];
}

function setFromMap(ll) {
  document.getElementById('start').value = ll.lat.toFixed(5) + ', ' + ll.lng.toFixed(5);
  gpsSay(t('Startpunkt von der Karte übernommen.'), false);
}

pick.addEventListener('click', function () {
  if (pickmap.style.display === 'block') {
    pickmap.style.display = 'none'; pick.textContent = t('Karte'); return;
  }
  loadLeaflet(function () {
    pickmap.style.display = 'block';
    pick.textContent = t('Karte zu');
    var c = startCoords();
    if (!pmap) {
      pmap = L.map('pickmap').setView(c, 9);
      L.tileLayer('https://tile.openstreetmap.org/{z}/{x}/{y}.png',
                  {maxZoom: 18, attribution: '© OpenStreetMap'}).addTo(pmap);
      pmark = L.marker(c, {draggable: true}).addTo(pmap);
      pmark.on('dragend', function () { setFromMap(pmark.getLatLng()); });
      pmap.on('click', function (e) { pmark.setLatLng(e.latlng); setFromMap(e.latlng); });
      gpsSay(t('Auf die Karte klicken oder die Nadel ziehen.'), false);
    } else {
      pmap.setView(c, 9); pmark.setLatLng(c);
    }
    setTimeout(function () { pmap.invalidateSize(); }, 60);
  });
});

/* ── Spots aufnehmen, Ufergeometrie ────────────────────────────────────── */
var addBtn = document.getElementById('addspots'), spotFile = document.getElementById('spotfile'),
    geoBtn = document.getElementById('rungeo');

spotFile.addEventListener('change', function () {
  var file = spotFile.files[0];
  if (!file) return;
  var reader = new FileReader();
  reader.onload = function () {
    var box = document.getElementById('spots_text');
    box.value = (box.value ? box.value + '\n' : '') + reader.result;
  };
  reader.readAsText(file);
});

function starteLauf(pfad, knopf, laufText, ruheText) {
  knopf.disabled = true;
  if (laufText) knopf.textContent = laufText;
  panel.className = 'on'; logEl.textContent = ''; frame.innerHTML = '';
  banner.className = ''; banner.textContent = '';
  statusbox.style.display = 'flex'; statustext.textContent = t('Läuft …');
  protokoll.style.display = 'block'; protokoll.open = false;
  post(pfad).then(function (r) {
    if (r.status === 409 || r.status === 400) {
      knopf.disabled = false; if (ruheText) knopf.textContent = ruheText;
      statusbox.style.display = 'none';
      banner.className = 'banner b-err';
      if (r.status === 409) { banner.textContent = t('Es läuft schon etwas — bitte warten.'); return; }
      // 400: der Server sagt, was nicht lesbar war (z. B. der Startpunkt)
      r.json().then(function (j) { banner.textContent = j.error || t('Eingabe nicht lesbar.'); })
        .catch(function () { banner.textContent = t('Eingabe nicht lesbar.'); });
      if (pfad === '/run') { var start = document.getElementById('start'); if (start) start.focus(); }
      return;
    }
    if (!timer) timer = setInterval(poll, 700);
  }).catch(function () {
    knopf.disabled = false; if (ruheText) knopf.textContent = ruheText;
    statusbox.style.display = 'none';
    banner.className = 'banner b-err';
    banner.textContent = t('Keine Verbindung zum Programm — läuft Wingfoilscout noch?');
  });
}

addBtn.addEventListener('click', function () {
  if (!document.getElementById('spots_text').value.trim()) {
    hint.textContent = t('Erst Koordinaten eintragen.'); return;
  }
  starteLauf('/addspots', addBtn, t('Nehme auf …'), t('Aufnehmen'));
});

geoBtn.addEventListener('click', function () {
  starteLauf('/geometry', geoBtn, t('Rechnet …'), geoBtn.textContent);
});

f.addEventListener('submit', function (e) {
  e.preventDefault();
  starteLauf('/run', go, t('Sucht …'), t('Spots suchen'));
});

/* Beenden: seit 1.18.2 in der Reiterleiste (web/beenden.js), nicht mehr hier. */

document.getElementById('save').addEventListener('click', function () {
  post('/save').then(function () {
    hint.textContent = t('Als Standard gemerkt.');
    setTimeout(function () { hint.textContent = ''; }, 2500);
  });
});

/* ── Fortschritt ───────────────────────────────────────────────────────── */
var KNOEPFE = {run: N_('Sucht …'), ingest: N_('Nehme auf …')};
var VORNE = {rueckblick: N_('Rückblick: {text}'), tagebuch: N_('Tagebuch: {text}')};
function vorne(kind, text) { return VORNE[kind] ? t(VORNE[kind], {text: text}) : text; }

function knoepfeFrei() {
  go.disabled = false; go.textContent = t('Spots suchen');
  addBtn.disabled = false; addBtn.textContent = t('Aufnehmen');
  geoBtn.disabled = false; if (geoBtn.dataset.ruhe) geoBtn.textContent = geoBtn.dataset.ruhe;
}

function uhrzeit(epoch) {
  if (!epoch) return '';
  var d = new Date(epoch * 1000);
  return (d.getHours() < 10 ? '0' : '') + d.getHours() + ':' + (d.getMinutes() < 10 ? '0' : '') + d.getMinutes();
}

/* Ein Lauf gehört zum Programm, nicht zum Fenster: er läuft im Hintergrund
   weiter, auch wenn man auf einen anderen Reiter geht. Bis 1.18.2 wusste die
   Suchseite beim Wiederkommen nichts davon — kein Spinner, Knopf frei, und
   „Spots suchen“ antwortete 409. Sie sah aus wie abgebrochen. Jetzt fragt sie
   beim Laden nach dem Stand: läuft etwas, zeigt sie es und pollt weiter; ist
   das Letzte fertig, zeigt sie das Ergebnis mit Uhrzeit. */
function zeigeLauf(j) {
  panel.className = 'on'; frame.innerHTML = ''; banner.className = ''; banner.textContent = '';
  statusbox.style.display = 'flex'; statustext.textContent = t('Läuft …');
  protokoll.style.display = 'block';
  go.disabled = true; addBtn.disabled = true; geoBtn.disabled = true;
  if (j.kind === 'run') go.textContent = t(KNOEPFE.run);
  else if (j.kind === 'ingest') addBtn.textContent = t(KNOEPFE.ingest);
  if (!timer) timer = setInterval(poll, 700);
}

function zeigeErgebnis(j) {
  statusbox.style.display = 'none';
  knoepfeFrei();
  var wann = uhrzeit(j.ende), stempel = wann ? ' (' + wann + ')' : '';
  if (j.state === 'done' && j.kind !== 'run') {
    banner.className = 'banner b-ok';
    banner.textContent = vorne(j.kind, j.summary) + stempel;
  } else if (j.state === 'done') {
    banner.className = 'banner b-ok';
    // Am Handy kein eingebetteter Report: ein Report in einem iframe auf
    // 375 pt ist ein Fenster im Fenster, mit zwei Bildlaufleisten. Dort
    // führt ein Knopf zum Reiter „Ziele“, der dieselbe Seite ganz zeigt.
    if (window.matchMedia('(max-width: 700px)').matches) {
      banner.textContent = j.summary + stempel + '. ';
      frame.innerHTML = '<a href="/report" style="text-decoration:none">' +
        '<button type="button" class="go">' + t('Ziele ansehen') + '</button></a>';
    } else {
      banner.textContent = j.summary + stempel + ' — ' + t('Report unten.') + ' ';
      var a = document.createElement('a');
      a.href = '/report'; a.target = '_blank'; a.textContent = t('in neuem Tab öffnen');
      banner.appendChild(a);
      wrap.className = 'wrap weit';
      frame.innerHTML = '<iframe src="/report?t=' + Date.now() + '"></iframe>';
    }
  } else {
    banner.className = 'banner b-err';
    banner.textContent = vorne(j.kind, j.error || t('Unbekannter Fehler.')) + stempel;
    protokoll.open = true;
  }
}

function poll() {
  fetch('/status').then(function (r) { return r.json(); }).then(function (j) {
    logEl.textContent = j.log.join('\n');
    logEl.scrollTop = logEl.scrollHeight;
    var letzte = j.log[j.log.length - 1];
    if (letzte) statustext.textContent = letzte.trim().slice(0, 90);
    if (j.state === 'running') return;
    clearInterval(timer); timer = null;
    zeigeErgebnis(j);
  }).catch(function () {});
}

geoBtn.dataset.ruhe = geoBtn.textContent;
fetch('/status').then(function (r) { return r.json(); }).then(function (j) {
  if (j.state === 'running') { zeigeLauf(j); poll(); }
  else if (j.state === 'done' || j.state === 'error') {
    panel.className = 'on'; protokoll.style.display = 'block';
    logEl.textContent = j.log.join('\n');
    zeigeErgebnis(j);
  }
}).catch(function () {});
