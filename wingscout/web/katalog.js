
var WASSER = {sea: N_('Meer'), lagoon: N_('Lagune'), lake: N_('See'), reservoir: N_('Stausee'), unknown: N_('unbekannt')};
var tbody = document.getElementById('ktbody'), zahl = document.getElementById('kzahl'),
    such = document.getElementById('ksuch'), land = document.getElementById('kland'),
    wasser = document.getElementById('kwasser'), was = document.getElementById('kwas'),
    kneu = document.getElementById('kneu'), ktreffer = document.getElementById('ktreffer');
var sortKey = 'name', sortAuf = true, map = null, marker = {}, aktiv = null;

function esc(v) {
  return String(v == null ? '' : v).replace(/[&<>"']/g, function (c) {
    return {'&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;'}[c];
  });
}
function km(a, b, c, d) {
  var r = 6371.0088, p1 = a * Math.PI / 180, p2 = c * Math.PI / 180, dp = p2 - p1, dl = (d - b) * Math.PI / 180;
  var h = Math.sin(dp / 2) * Math.sin(dp / 2) + Math.cos(p1) * Math.cos(p2) * Math.sin(dl / 2) * Math.sin(dl / 2);
  return 2 * r * Math.asin(Math.sqrt(h));
}
SPOTS.forEach(function (s) { s.km = km(HOME.lat, HOME.lon, s.lat, s.lon); });

function merkmale(s) {
  var h = '';                     // nicht „t“: das ist die Übersetzung (i18n.js_vorspann)
  h += s.verified ? '<span class="kpill kp-ok">' + t('bestätigt') + '</span>' : '<span class="kpill kp-warn">' + t('unbestätigt') + '</span>';
  if (s.thermik) h += '<span class="kpill kp-th">' + esc(s.thermik) + '</span>';
  var sbTitel = s.shorebreak_note ? ' title="' + esc(s.shorebreak_note) + '"' : '';
  if (s.shorebreak === 'yes') h += '<span class="kpill kp-warn"' + sbTitel + '>' + t('Shorebreak') + '</span>';
  else if (s.shorebreak === 'possible') h += '<span class="kpill kp-info"' + sbTitel + '>' + t('Shorebreak möglich') + '</span>';
  if (s.access) h += '<span class="kpill kp-info">' + esc(s.access) + '</span>';
  if (s.dogs === 'no') h += '<span class="kpill kp-warn">' + t('keine Hunde') + '</span>';
  if (s.ig_urteil === 'wing') h += '<span class="kpill kp-ok" title="' + esc(t('Instagram-Funde nennen Wing oder Foil (Suchtreffer, kein Beleg)')) + '">Instagram · Wing</span>';
  else if (s.instagram || s.ig_funde.length || (s.ig && s.ig.Instagram && s.ig.Instagram.indexOf('/explore/locations/') > 0))
    h += '<span class="kpill kp-info" title="' + esc(t('Ortsseite oder Suchtreffer auf Instagram')) + '">Instagram</span>';
  if (s.aus) h += '<span class="kpill kp-info">' + t('nicht in der Suche') + '</span>';
  if (s.tidal === true || s.tidal === false || s.water === 'sea' || s.water === 'lagoon') {
    // Tiden (1.18.0): ja / nein aus dem Katalog, sonst Automatik am Meer
    var tt = s.tidal === true ? t('Tiden: ja') : (s.tidal === false ? t('Tiden: nein') : t('Tiden: auto'));
    var titel = s.tidal === true ? t('Tidenzeiten werden gezeigt, auch wenn das Modell wenig Hub sieht')
      : (s.tidal === false ? t('keine Tidenanzeige an diesem Spot')
        : t('automatisch: Meer oder Lagune mit mindestens 0,5 m Hub im Modell — im Katalog nichts eingetragen'));
    if (s.tide) tt += ' · ' + fensterText(s.tide);
    h += '<span class="kpill ' + (s.tidal === false ? 'kp-info' : 'kp-tide') + '" title="' + esc(titel) + '">' + esc(tt) + '</span>';
  }
  return h;
}
function fensterText(f) {
  if (!f || !f.fahrbar) return '';
  // zahlFmt() aus dem Sprachvorspann: 1,5 · 1.5 — wie die Zahl dasteht, ungerundet
  if (f.fahrbar === 'hochwasser') return t('HW ± {stunden} h', {stunden: zahlFmt(f.stunden || 2)});
  if (f.fahrbar === 'niedrigwasser') return t('NW ± {stunden} h', {stunden: zahlFmt(f.stunden || 2)});
  // dieselben Texte wie in der Auswahl des Tiden-Editors (tideEditor)
  if (f.fahrbar === 'auflaufend') return t('nur auflaufend');
  if (f.fahrbar === 'ablaufend') return t('nur ablaufend');
  return t('nur {fenster}', {fenster: f.fahrbar});
}
function links(s) {
  var q = s.lat.toFixed(5) + ',' + s.lon.toFixed(5);
  var h = '<span class="klinks">' +
    '<a target="_blank" rel="noopener" href="https://www.windy.com/?' + q + ',12">Windy</a>' +
    '<a target="_blank" rel="noopener" href="https://www.openstreetmap.org/?mlat=' + s.lat + '&mlon=' + s.lon + '#map=15/' + s.lat + '/' + s.lon + '">OSM</a>';
  // Die Instagram-Adressen baut wingscout/instagram.py — dieselben wie im Report.
  // Ihre Beschriftung ist der Schlüssel: „Instagram“ bleibt, „Insta-Suche“ wird übersetzt.
  Object.keys(s.ig || {}).forEach(function (k) {
    h += '<a target="_blank" rel="noopener" href="' + esc(s.ig[k]) + '">' + esc(k === 'Insta-Suche' ? t('Insta-Suche') : k) + '</a>';
  });
  (s.ig_funde || []).forEach(function (f) {
    h += '<a target="_blank" rel="noopener" class="fund" href="' + esc(f.url) + '" title="' + esc(f.titel) + '">' + esc(f.text) + '</a>';
  });
  return h + '</span>';
}

function passt(s) {
  var q = such.value.trim().toLowerCase();
  if (land.value && s.country !== land.value) return false;
  if (wasser.value && s.water !== wasser.value) return false;
  if (was.value === 'unbestaetigt' && s.verified) return false;
  if (was.value === 'thermik' && !s.thermik) return false;
  if (was.value === 'shorebreak' && s.shorebreak !== 'yes' && s.shorebreak !== 'possible') return false;
  if (was.value === 'instagram' && !s.instagram && !s.ig_funde.length && !s.ig_urteil) return false;
  if (was.value === 'insta_offen' && s.ig_urteil && s.ig_urteil !== 'offen') return false;
  if (was.value === 'tide' && !s.tide && s.tidal !== true) return false;
  if (!q) return true;
  var text = [s.name, s.id, s.country, s.region, t(WASSER[s.water] || s.water), s.notes, s.comment, s.thermik, s.source].join(' ').toLowerCase();
  return q.split(/\s+/).every(function (w) { return text.indexOf(w) >= 0; });
}

/* ── Für alle vorschlagen (seit 2.3.0) ────────────────────────────────────
   Das Formular „Suggest a spot“ auf GitHub (.github/ISSUE_TEMPLATE/spot.yml),
   vorausgefüllt über die Adresse — die Schlüssel sind die `id`s der Felder.
   Nur ein Link: gesendet wird erst, wenn jemand das Formular dort abschickt. */
function vorschlagUrl(werte) {
  var p = new URLSearchParams();
  p.set('template', 'spot.yml');
  Object.keys(werte || {}).forEach(function (k) {
    var v = String(werte[k] == null ? '' : werte[k]).trim();
    if (v) p.set(k, v.slice(0, 300));
  });
  return VORSCHLAG + '?' + p.toString();
}
function korrekturUrl(s) {
  return vorschlagUrl({title: 'Spot: ' + s.name + ' – ' + t('Korrektur'), name: s.name,
                       koordinate: s.lat.toFixed(5) + ', ' + s.lon.toFixed(5)});
}

function zeichne() {
  var liste = SPOTS.filter(passt);
  liste.sort(function (a, b) {
    var x = a[sortKey], y = b[sortKey];
    if (typeof x === 'string') { x = x.toLowerCase(); y = String(y).toLowerCase(); }
    var c = x < y ? -1 : (x > y ? 1 : 0);
    return sortAuf ? c : -c;
  });
  tbody.innerHTML = liste.map(function (s) {
    return '<tr data-id="' + esc(s.id) + '"' + (s.id === aktiv ? ' class="aktiv"' : '') + '>' +
      '<td class="name"><b class="kn">' + esc(s.name) + '</b> ' + merkmale(s) +
      '<span class="kakt"><a href="#" data-akt="umbenennen">' + t('umbenennen') + '</a><a href="#" data-akt="verschieben">' + t('verschieben') + '</a>' +
      '<a href="#" data-akt="tide">' + t('Tiden …') + '</a>' +
      '<a href="#" class="weg" data-akt="loeschen">' + t('löschen') + '</a>' +
      '<a class="vorschlag" href="' + esc(korrekturUrl(s)) + '" target="_blank" rel="noopener noreferrer">' +
      t('Korrektur vorschlagen') + '</a></span>' +
      (s.notes ? '<small title="' + esc(s.notes) + '">' + esc(s.notes) + '</small>' : '') +
      '<div class="kmt" data-id="' + esc(s.id) + '" data-text="' + esc(s.comment || '') + '"></div>' + links(s) + '</td>' +
      '<td class="n">' + esc(s.country || '–') + (s.region ? '<br>' + esc(s.region) : '') + '</td>' +
      '<td class="n">' + esc(t(WASSER[s.water] || s.water)) + '</td>' +
      '<td class="n">' + Math.round(s.km) + '</td></tr>';
  }).join('');
  var unb = liste.filter(function (s) { return !s.verified; }).length;
  zahl.textContent = t('{n} von {gesamt} Spots', {n: liste.length, gesamt: SPOTS.length}) + (unb ? ' · ' + t('{n} unbestätigt', {n: unb}) : '') +
    (liste.length && liste.length < SPOTS.length ? ' · ' + t('Karte zeigt die Auswahl') : '');
  [].forEach.call(tbody.querySelectorAll('.kakt a[data-akt]'), function (a) {
    a.addEventListener('click', function (e) {
      e.preventDefault(); e.stopPropagation();
      aktion(a.dataset.akt, a.closest('tr').dataset.id, a.closest('td'));
    });
  });
  // Der Link öffnet GitHub in einem neuen Tab — die Zeile bleibt, wie sie ist
  [].forEach.call(tbody.querySelectorAll('.kakt a.vorschlag'), function (a) {
    a.addEventListener('click', function (e) { e.stopPropagation(); });
  });
  [].forEach.call(tbody.querySelectorAll('tr'), function (tr) {
    tr.addEventListener('click', function () { zeige(tr.dataset.id, true); });
  });
  WSKommentar.alle(tbody);
  karteFiltern(liste);
}
document.addEventListener('kommentar', function (e) {
  var s = spotVon(e.detail.id);
  if (s) s.comment = e.detail.comment;
});

function karteBauen() {
  if (map || typeof L === 'undefined') return;
  map = L.map('kmap', {scrollWheelZoom: false});
  L.tileLayer('https://tile.openstreetmap.org/{z}/{x}/{y}.png', {maxZoom: 17, attribution: '© OpenStreetMap'}).addTo(map);
  SPOTS.forEach(function (s) {
    var mk = L.circleMarker([s.lat, s.lon], {radius: 6, color: s.verified ? '#7A1449' : '#8E650A',
      fillColor: s.verified ? '#AE1F68' : '#D9B35C', fillOpacity: .8, weight: 1.2});
    mk.bindTooltip(esc(s.name), {className: 'spotname', direction: 'top', offset: [0, -4]});
    mk.bindPopup('<b>' + esc(s.name) + '</b><br><span style="color:#6C858F">' + esc(s.country) +
      (s.region ? ' · ' + esc(s.region) : '') + ' · ' + esc(t(WASSER[s.water] || s.water)) + ' · ' + Math.round(s.km) + ' km</span>' +
      (s.notes ? '<br><span style="color:#6C858F">' + esc(s.notes) + '</span>' : '') +
      '<div class="pl">' + links(s) + '</div>', {maxWidth: 320});
    mk.on('click', function () { zeige(s.id, false); });
    marker[s.id] = mk;
    mk.addTo(map);
  });
  L.circleMarker([HOME.lat, HOME.lon], {radius: 6, color: '#14303C', fillColor: '#14303C', fillOpacity: 1, weight: 2})
    .bindTooltip(t('Startpunkt')).addTo(map);
  map.on('click', function () { map.scrollWheelZoom.enable(); });
  map.fitBounds(L.latLngBounds(SPOTS.map(function (s) { return [s.lat, s.lon]; })).pad(0.05));
}

function karteFiltern(liste) {
  karteBauen();
  if (!map) return;
  var drin = {};
  liste.forEach(function (s) { drin[s.id] = 1; });
  SPOTS.forEach(function (s) {
    var mk = marker[s.id];
    if (!mk) return;
    if (drin[s.id]) { if (!map.hasLayer(mk)) mk.addTo(map); }
    else if (map.hasLayer(mk)) map.removeLayer(mk);
  });
  if (liste.length && liste.length < SPOTS.length) {
    map.fitBounds(L.latLngBounds(liste.map(function (s) { return [s.lat, s.lon]; })).pad(0.15), {maxZoom: 12});
  }
}

function zeige(id, mitKarte) {
  aktiv = id;
  [].forEach.call(tbody.querySelectorAll('tr'), function (tr) { tr.classList.toggle('aktiv', tr.dataset.id === id); });
  var tr = tbody.querySelector('tr[data-id="' + id.replace(/"/g, '') + '"]');
  if (tr && !mitKarte) tr.scrollIntoView({block: 'nearest'});
  if (mitKarte && map && marker[id]) {
    map.setView(marker[id].getLatLng(), Math.max(map.getZoom(), 11));
    marker[id].openPopup();
  }
}

/* ── Schon drin? ──────────────────────────────────────────────────────────── */
function naechste() {
  var v = kneu.value.trim();
  if (!v) { ktreffer.textContent = ''; return; }
  var m = v.match(/(-?[0-9]{1,3}(?:[.,][0-9]+)?)[^0-9-]+(-?[0-9]{1,3}(?:[.,][0-9]+)?)/);
  var liste;
  if (m) {
    var la = parseFloat(m[1].replace(',', '.')), lo = parseFloat(m[2].replace(',', '.'));
    if (isNaN(la) || isNaN(lo) || Math.abs(la) > 90 || Math.abs(lo) > 180) { ktreffer.textContent = t('Koordinate nicht lesbar.'); return; }
    liste = SPOTS.map(function (s) { return {s: s, d: km(la, lo, s.lat, s.lon)}; }).sort(function (a, b) { return a.d - b.d; }).slice(0, 4);
    ktreffer.innerHTML = liste.map(function (e) {
      var nah = e.d <= 0.3 ? ' — <span style="color:var(--stop)">' + t('so gut wie derselbe Punkt') + '</span>' : (e.d <= 3 ? ' — ' + t('in der Nähe') : '');
      return '<div><b>' + e.d.toFixed(1) + ' km</b> · <a href="#" data-id="' + esc(e.s.id) + '">' + esc(e.s.name) + '</a>' + nah + '</div>';
    }).join('');
  } else {
    var q = v.toLowerCase();
    liste = SPOTS.filter(function (s) { return (s.name + ' ' + s.id + ' ' + s.notes).toLowerCase().indexOf(q) >= 0; }).slice(0, 6);
    ktreffer.innerHTML = liste.length ? liste.map(function (s) {
      return '<div><a href="#" data-id="' + esc(s.id) + '">' + esc(s.name) + '</a> · ' + esc(s.country) + ' · ' + Math.round(s.km) + ' km</div>';
    }).join('') : t('Kein Spot mit diesem Namen im Katalog.');
  }
  [].forEach.call(ktreffer.querySelectorAll('a'), function (a) {
    a.addEventListener('click', function (e) { e.preventDefault(); zeige(a.dataset.id, true); });
  });
}

/* ── Katalog pflegen: umbenennen, löschen, verschieben, neu ───────────────── */
var kmeldung = document.getElementById('kmeldung');
function melde(el, text, art) { el.textContent = text || ''; el.className = 'kmeld' + (art ? ' ' + art : ''); }
function post(pfad, daten) {
  return fetch(pfad, {method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify(daten)})
    .then(function (r) { return r.json().then(function (j) { return {ok: r.ok, status: r.status, j: j}; }); });
}
function spotVon(id) { for (var i = 0; i < SPOTS.length; i++) if (SPOTS[i].id === id) return SPOTS[i]; return null; }

function aktion(was, id, zelle) {
  var s = spotVon(id);
  if (!s) return;
  if (was === 'umbenennen') {
    var b = zelle.querySelector('b.kn');
    var box = document.createElement('span'); box.className = 'kedit';
    box.innerHTML = '<input type="text" value="' + esc(s.name) + '" maxlength="120"> ' +
                    '<button type="button" class="klein">' + t('Speichern') + '</button><button type="button" class="klein grau">' + t('Abbrechen') + '</button>';
    b.replaceWith(box);
    var inp = box.querySelector('input'), ok = box.querySelectorAll('button')[0], nein = box.querySelectorAll('button')[1];
    inp.focus(); inp.select();
    nein.addEventListener('click', function () { zeichne(); });
    function speichern() {
      var name = inp.value.trim();
      if (!name || name === s.name) { zeichne(); return; }
      ok.disabled = true;
      post('/katalog/umbenennen', {id: id, name: name}).then(function (res) {
        if (!res.ok || res.j.error) { melde(kmeldung, res.j.error || t('Fehlgeschlagen.'), 'err'); ok.disabled = false; return; }
        s.name = res.j.name;
        if (marker[id]) { marker[id].unbindTooltip(); marker[id].bindTooltip(esc(s.name), {className: 'spotname', direction: 'top', offset: [0, -4]}); }
        melde(kmeldung, res.j.message, 'ok'); zeichne();
      }).catch(function (e) { melde(kmeldung, t('Keine Verbindung zum Programm: {fehler}', {fehler: e}), 'err'); ok.disabled = false; });
    }
    ok.addEventListener('click', speichern);
    inp.addEventListener('keydown', function (e) { if (e.key === 'Enter') speichern(); if (e.key === 'Escape') zeichne(); });
    inp.addEventListener('click', function (e) { e.stopPropagation(); });
    box.addEventListener('click', function (e) { e.stopPropagation(); });
  } else if (was === 'loeschen') {
    var akt = zelle.querySelector('.kakt');
    akt.innerHTML = '<span class="kedit">' + t('Wirklich löschen?') + ' <button type="button" class="klein">' + t('Ja, löschen') + '</button>' +
                    '<button type="button" class="klein grau">' + t('Nein') + '</button></span>';
    akt.addEventListener('click', function (e) { e.stopPropagation(); });
    akt.querySelectorAll('button')[1].addEventListener('click', function () { zeichne(); });
    akt.querySelectorAll('button')[0].addEventListener('click', function () {
      this.disabled = true;
      post('/katalog/loeschen', {id: id}).then(function (res) {
        if (!res.ok || res.j.error) { melde(kmeldung, res.j.error || t('Fehlgeschlagen.'), 'err'); zeichne(); return; }
        SPOTS = SPOTS.filter(function (x) { return x.id !== id; });
        if (marker[id]) { if (map && map.hasLayer(marker[id])) map.removeLayer(marker[id]); delete marker[id]; }
        if (aktiv === id) aktiv = null;
        melde(kmeldung, res.j.message, 'ok'); zeichne();
      }).catch(function (e) { melde(kmeldung, t('Keine Verbindung zum Programm: {fehler}', {fehler: e}), 'err'); zeichne(); });
    });
  } else if (was === 'verschieben') {
    ziehStart(s);
  } else if (was === 'tide') {
    tideEditor(s, zelle);
  }
}

/* Tiden je Spot: auto / ja / nein und wahlweise ein Tidenfenster. Schreibt
   `tidal:` und den Block `tide:` in spots.yaml (POST /katalog/tide). */
function tideEditor(s, zelle) {
  var akt = zelle.querySelector('.kakt');
  var modus = s.tidal === true ? 'ja' : (s.tidal === false ? 'nein' : 'auto');
  var f = s.tide || {fahrbar: '', stunden: 2};
  function opt(v, text, cur) { return '<option value="' + v + '"' + (v === cur ? ' selected' : '') + '>' + text + '</option>'; }
  akt.innerHTML = '<span class="kedit ktide">' +
    '<label>' + t('Tiden') + ' <select class="kt-modus">' + opt('auto', t('automatisch'), modus) + opt('ja', t('ja'), modus) + opt('nein', t('nein'), modus) + '</select></label>' +
    '<label>' + t('fahrbar') + ' <select class="kt-fenster">' + opt('', t('immer'), f.fahrbar) + opt('hochwasser', t('um Hochwasser'), f.fahrbar) +
      opt('niedrigwasser', t('um Niedrigwasser'), f.fahrbar) + opt('auflaufend', t('nur auflaufend'), f.fahrbar) + opt('ablaufend', t('nur ablaufend'), f.fahrbar) + '</select></label>' +
    '<label class="kt-std">± <input type="number" min="0.5" max="6" step="0.5" value="' + esc(f.stunden || 2) + '"> h</label>' +
    '<button type="button" class="klein">' + t('Speichern') + '</button><button type="button" class="klein grau">' + t('Abbrechen') + '</button></span>';
  var box = akt.querySelector('.ktide'), selM = box.querySelector('.kt-modus'), selF = box.querySelector('.kt-fenster'),
      std = box.querySelector('.kt-std'), inp = std.querySelector('input'),
      ok = box.querySelectorAll('button')[0], nein = box.querySelectorAll('button')[1];
  function passeAn() {
    selF.disabled = selM.value === 'nein';
    if (selF.disabled) selF.value = '';
    std.style.display = (selF.value === 'hochwasser' || selF.value === 'niedrigwasser') ? '' : 'none';
  }
  passeAn();
  selM.addEventListener('change', passeAn);
  selF.addEventListener('change', passeAn);
  ['click', 'mousedown', 'keydown'].forEach(function (ev) { box.addEventListener(ev, function (e) { e.stopPropagation(); }); });
  nein.addEventListener('click', function () { zeichne(); });
  ok.addEventListener('click', function () {
    ok.disabled = true;
    post('/katalog/tide', {id: s.id, tidal: selM.value, fahrbar: selF.value, stunden: inp.value}).then(function (res) {
      if (!res.ok || res.j.error) { melde(kmeldung, res.j.error || t('Fehlgeschlagen.'), 'err'); ok.disabled = false; return; }
      s.tidal = res.j.tidal === 'ja' ? true : (res.j.tidal === 'nein' ? false : null);
      s.tide = res.j.tide || null;
      melde(kmeldung, res.j.message, 'ok'); zeichne();
    }).catch(function (e) { melde(kmeldung, t('Keine Verbindung zum Programm: {fehler}', {fehler: e}), 'err'); ok.disabled = false; });
  });
}

/* Verschieben: eine ziehbare Nadel über dem Punkt, Klick in die Karte setzt sie */
var zieh = {spot: null, nadel: null};
var kzieh = document.getElementById('kzieh'), kziehname = document.getElementById('kziehname'),
    kziehkoord = document.getElementById('kziehkoord');
function ziehStart(s) {
  ziehEnde();
  karteBauen();
  if (!map) { melde(kmeldung, t('Die Karte ist noch nicht geladen.'), 'err'); return; }
  zeige(s.id, true);
  if (marker[s.id]) marker[s.id].closePopup();
  zieh.spot = s;
  zieh.nadel = L.marker([s.lat, s.lon], {draggable: true, zIndexOffset: 1000}).addTo(map);
  zieh.nadel.on('dragend', ziehZeige);
  map.on('click', ziehKlick);
  map.setView([s.lat, s.lon], Math.max(map.getZoom(), 14));
  kziehname.textContent = s.name;
  kzieh.style.display = '';
  ziehZeige();
}
function ziehKlick(e) { if (zieh.nadel) { zieh.nadel.setLatLng(e.latlng); ziehZeige(); } }
function ziehZeige() {
  if (!zieh.nadel) return;
  var ll = zieh.nadel.getLatLng();
  kziehkoord.textContent = ll.lat.toFixed(5) + ', ' + ll.lng.toFixed(5);
}
function ziehEnde() {
  if (zieh.nadel && map) { map.removeLayer(zieh.nadel); map.off('click', ziehKlick); }
  zieh.nadel = null; zieh.spot = null;
  kzieh.style.display = 'none';
}
document.getElementById('kziehnein').addEventListener('click', ziehEnde);
document.getElementById('kziehok').addEventListener('click', function () {
  if (!zieh.nadel || !zieh.spot) return;
  var s = zieh.spot, ll = zieh.nadel.getLatLng(), knopf = this;
  knopf.disabled = true; knopf.textContent = t('Rechnet …');
  post('/katalog/verschieben', {id: s.id, koordinate: ll.lat.toFixed(6) + ', ' + ll.lng.toFixed(6)}).then(function (res) {
    knopf.disabled = false; knopf.textContent = t('Übernehmen');
    if (!res.ok || res.j.error) { melde(kmeldung, res.j.error || t('Fehlgeschlagen.'), 'err'); return; }
    s.lat = Number(ll.lat.toFixed(6)); s.lon = Number(ll.lng.toFixed(6)); s.verified = true;
    s.km = km(HOME.lat, HOME.lon, s.lat, s.lon);
    if (marker[s.id]) {
      marker[s.id].setLatLng([s.lat, s.lon]);
      marker[s.id].setStyle({color: '#7A1449', fillColor: '#AE1F68'});
    }
    melde(kmeldung, res.j.message || t('Verschoben.'), 'ok');
    ziehEnde(); zeichne();
  }).catch(function (e) { knopf.disabled = false; knopf.textContent = t('Übernehmen'); melde(kmeldung, t('Keine Verbindung zum Programm: {fehler}', {fehler: e}), 'err'); });
});

/* Neuer Spot */
var kneumeld = document.getElementById('kneumeld'), kneuok = document.getElementById('kneuok');
function neuEintragen(trotzdem) {
  var daten = {name: document.getElementById('kname').value.trim(), koordinate: document.getElementById('kkoord').value.trim(),
               water: document.getElementById('kwasserneu').value, country: document.getElementById('klandneu').value.trim(),
               notes: document.getElementById('knotiz').value.trim(), geometrie: document.getElementById('kgeo').checked,
               comment: document.getElementById('kkommentar').value.trim(), trotzdem: !!trotzdem};
  if (!daten.koordinate) { melde(kneumeld, t('Eine Koordinate braucht es mindestens.'), 'err'); return; }
  kneuok.disabled = true; kneuok.textContent = daten.geometrie ? t('Rechnet …') : '…';
  post('/katalog/neu', daten).then(function (res) {
    kneuok.disabled = false; kneuok.textContent = t('Eintragen');
    if (res.status === 409 && res.j.doppelt) {
      kneumeld.innerHTML = esc(res.j.error) + ' <a href="#" id="ktrotzdem">' + t('Trotzdem eintragen') + '</a>';
      kneumeld.className = 'kmeld err';
      document.getElementById('ktrotzdem').addEventListener('click', function (e) { e.preventDefault(); neuEintragen(true); });
      return;
    }
    if (!res.ok || res.j.error) { melde(kneumeld, res.j.error || t('Fehlgeschlagen.'), 'err'); return; }
    var s = {id: res.j.id, name: res.j.name, country: res.j.country || '', region: '', water: res.j.water || 'unknown',
             lat: res.j.lat, lon: res.j.lon, verified: true, thermik: '', shorebreak: '', shorebreak_note: '',
             access: '', dogs: '', notes: res.j.notes || '', comment: res.j.comment || '', source: 'eigene Eingabe', instagram: '',
             ig: {'Insta-Suche': 'https://www.google.com/search?q=' + encodeURIComponent('site:instagram.com "' + res.j.name + '" wingfoil')},
             ig_funde: [], ig_urteil: '', aus: false};
    s.km = km(HOME.lat, HOME.lon, s.lat, s.lon);
    SPOTS.push(s);
    if (map) {
      var mk = L.circleMarker([s.lat, s.lon], {radius: 6, color: '#7A1449', fillColor: '#AE1F68', fillOpacity: .8, weight: 1.2});
      mk.bindTooltip(esc(s.name), {className: 'spotname', direction: 'top', offset: [0, -4]});
      mk.on('click', function () { zeige(s.id, false); });
      marker[s.id] = mk; mk.addTo(map);
    }
    melde(kneumeld, res.j.message, 'ok');
    ['kname', 'kkoord', 'knotiz', 'klandneu', 'kkommentar'].forEach(function (k) { document.getElementById(k).value = ''; });
    such.value = ''; aktiv = s.id; zeichne(); zeige(s.id, true);
  }).catch(function (e) { kneuok.disabled = false; kneuok.textContent = t('Eintragen'); melde(kneumeld, t('Keine Verbindung zum Programm: {fehler}', {fehler: e}), 'err'); });
}
kneuok.addEventListener('click', function () { neuEintragen(false); });

// „Für alle vorschlagen“ unter dem Formular: was dort steht, kommt mit
// (Name, Koordinate, Notiz) — der Kommentar nicht, der ist deiner.
var kvorschlag = document.getElementById('kvorschlag');
if (kvorschlag) {
  kvorschlag.addEventListener('click', function () {
    // Steht oben in „Schon drin?“ etwas, zählt es als Koordinate oder Link —
    // oder, wenn es keins ist, als Name.
    var oben = kneu.value.trim();
    var istOrt = /-?\d{1,3}[.,]\d+\D+-?\d{1,3}[.,]\d+/.test(oben) || /maps|goo\.gl/i.test(oben);
    kvorschlag.href = vorschlagUrl({
      name: document.getElementById('kname').value || (istOrt ? '' : oben),
      koordinate: document.getElementById('kkoord').value || (istOrt ? oben : ''),
      hinweise: document.getElementById('knotiz').value
    });
  });
}
/* Die Koordinate aus „Schon drin?“ wandert ins Formular, wenn sie eine ist */
kneu.addEventListener('input', function () {
  var m = kneu.value.match(/-?[0-9]{1,3}[.,][0-9]+[^0-9-]+-?[0-9]{1,3}[.,][0-9]+/);
  if (m) document.getElementById('kkoord').value = kneu.value.trim();
});

// Das Suchfeld nur auf 'input': ein 'change' feuert auch beim Verlassen des
// Felds — also genau dann, wenn man auf „umbenennen“ klickt — und die
// neu gezeichnete Tabelle warf den Editor wieder weg.
such.addEventListener('input', zeichne);
[land, wasser, was].forEach(function (el) { el.addEventListener('change', zeichne); });
kneu.addEventListener('input', naechste);
[].forEach.call(document.querySelectorAll('.kliste th[data-k]'), function (th) {
  th.addEventListener('click', function () {
    if (sortKey === th.dataset.k) sortAuf = !sortAuf; else { sortKey = th.dataset.k; sortAuf = true; }
    [].forEach.call(document.querySelectorAll('.kliste th'), function (x) { x.classList.remove('sort', 'auf'); });
    th.classList.add('sort'); if (sortAuf) th.classList.add('auf');
    zeichne();
  });
});
zeichne();
