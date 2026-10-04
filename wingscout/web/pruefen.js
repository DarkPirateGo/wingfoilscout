
var map = null, nadel = null, aktiv = null;

function karteBauen() {
  if (map || typeof L === 'undefined') return;
  var mitte = SPOTS.length ? [SPOTS[0].lat, SPOTS[0].lon] : [HOME.lat, HOME.lon];
  map = L.map('pmap').setView(mitte, 14);
  L.tileLayer('https://tile.openstreetmap.org/{z}/{x}/{y}.png',
              {maxZoom: 19, attribution: '© OpenStreetMap'}).addTo(map);
  map.on('click', function (e) { if (nadel) { nadel.setLatLng(e.latlng); uebernehmenInsFeld(e.latlng); } });
}

function feldVon(id) {
  var karte = document.querySelector(".pkarte[data-id='" + id + "']");
  return karte ? karte.querySelector('.neu') : null;
}

function uebernehmenInsFeld(ll) {
  if (!aktiv) return;
  var feld = feldVon(aktiv);
  if (feld) feld.value = ll.lat.toFixed(6) + ', ' + ll.lng.toFixed(6);
}

function zeige(id) {
  karteBauen();
  if (!map) return;
  var spot = SPOTS.filter(function (s) { return s.id === id; })[0];
  if (!spot) return;
  aktiv = id;
  [].forEach.call(document.querySelectorAll('.pkarte'), function (k) {
    k.classList.toggle('aktiv', k.dataset.id === id);
  });
  var feld = feldVon(id);
  var start = [spot.lat, spot.lon];
  if (feld && feld.value.trim()) {
    var m = feld.value.match(/(-?[0-9]+(?:[.,][0-9]+)?)[^0-9-]+(-?[0-9]+(?:[.,][0-9]+)?)/);
    if (m) start = [parseFloat(m[1].replace(',', '.')), parseFloat(m[2].replace(',', '.'))];
  }
  if (!nadel) {
    nadel = L.marker(start, {draggable: true}).addTo(map);
    nadel.on('dragend', function () { uebernehmenInsFeld(nadel.getLatLng()); });
  } else {
    nadel.setLatLng(start);
  }
  map.setView(start, 15);
  setTimeout(function () { map.invalidateSize(); }, 60);
}

function melde(karte, text, art) {
  var p = karte.querySelector('.pmsg');
  p.textContent = text;
  p.className = 'pmsg ' + (art || '');
}

function senden(pfad, daten, karte, knopf, laufText) {
  var alt = knopf.textContent;
  knopf.disabled = true;
  knopf.textContent = laufText;
  melde(karte, '', '');
  fetch(pfad, {method: 'POST', headers: {'Content-Type': 'application/json'},
               body: JSON.stringify(daten)})
    .then(function (r) { return r.json().then(function (j) { return {ok: r.ok, j: j}; }); })
    .then(function (res) {
      knopf.disabled = false;
      knopf.textContent = alt;
      if (!res.ok || res.j.error) { melde(karte, res.j.error || t('Fehlgeschlagen.'), 'err'); return; }
      melde(karte, res.j.message || t('Gespeichert.'), 'ok');
      if (res.j.erledigt) karte.classList.add('perledigt');
    })
    .catch(function (e) {
      knopf.disabled = false;
      knopf.textContent = alt;
      melde(karte, t('Keine Verbindung zum Programm: {fehler}', {fehler: e}), 'err');
    });
}

[].forEach.call(document.querySelectorAll('.pkarte'), function (karte) {
  var id = karte.dataset.id;
  karte.querySelector('.zeigen').addEventListener('click', function () { zeige(id); });
  karte.querySelector('.uebernehmen').addEventListener('click', function () {
    var wert = karte.querySelector('.neu').value.trim();
    if (!wert) { melde(karte, t('Erst eine Koordinate wählen — Nadel ziehen oder eintippen.'), 'err'); return; }
    senden('/pruefen/setzen', {id: id, koordinate: wert}, karte, this, t('Rechnet …'));
  });
  karte.querySelector('.passt').addEventListener('click', function () {
    senden('/pruefen/ok', {id: id}, karte, this, '…');
  });
});

[].forEach.call(document.querySelectorAll('.pfilter button'), function (b) {
  b.addEventListener('click', function () {
    var wahl = b.dataset.stufe;
    [].forEach.call(document.querySelectorAll('.pfilter button'), function (x) {
      x.classList.toggle('an', x === b);
    });
    var sichtbar = 0;
    [].forEach.call(document.querySelectorAll('.pkarte'), function (k) {
      var zeigen = (wahl === 'alle' || k.dataset.stufe === wahl);
      k.hidden = !zeigen;
      if (zeigen) sichtbar++;
    });
    // Die Karte auf den ersten sichtbaren Spot stellen, sonst zeigt sie
    // weiter einen Punkt, der gar nicht mehr in der Liste steht.
    var erste = document.querySelector('.pkarte:not([hidden])');
    if (erste) zeige(erste.dataset.id);
  });
});

if (SPOTS.length) zeige(SPOTS[0].id);
