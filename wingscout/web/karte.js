(function () {
  var D = KARTE;
  var el = document.getElementById('map');
  if (typeof L === 'undefined') {
    el.innerHTML = '<div class="nomap">' +
      t('Karte nicht geladen — Leaflet kam nicht durch. Der Report funktioniert ohne Karte weiter; die Spots stehen unten in den Tabellen.') + '</div>';
    document.getElementById('maptools').style.display = 'none';
    return;
  }
  el.innerHTML = '';
  var map = L.map('map', {scrollWheelZoom: false});
  // Eine eigene Ebene unterhalb der Punkte für alles, was nur Dekoration ist:
  // Thermikringe und der Radiuskreis. zIndex 350 liegt unter dem overlayPane
  // (400), pointerEvents:none nimmt ihr jede Möglichkeit, einen Klick
  // abzufangen. Der Radiuskreis lag bis 1.8.1 als zuletzt gezeichnete Fläche
  // ÜBER allen Punkten — mit fillOpacity .03 ist die Fläche gefüllt, und eine
  // gefüllte Leaflet-Fläche fängt jeden Klick in ihrem Inneren. Innerhalb des
  // Suchradius, also überall, wo Spots sind, ging deshalb kein Popup auf.
  map.createPane('dekor');
  map.getPane('dekor').style.zIndex = 350;
  map.getPane('dekor').style.pointerEvents = 'none';
  L.tileLayer('https://tile.openstreetmap.org/{z}/{x}/{y}.png', {
    maxZoom: 17, attribution: '&copy; OpenStreetMap'
  }).addTo(map);

  function esc(v) {
    return String(v == null ? '' : v).replace(/[&<>"']/g, function (c) {
      return {'&': '&amp;', '<': '&lt;', '>': '&gt;',
               '"': '&quot;', "'": '&#39;'}[c];
    });
  }

  /* ── Das Stundenband: dieselbe Farbskala wie das Raster im Report ─────── */
  function farbe(z) {
    if (!z) return 'var(--surface-2)';
    return 'rgba(174,31,104,' + (0.12 + 0.88 * Math.pow(z / 9, 1.5)).toFixed(2) + ')';
  }
  function band(m) {
    if (!m.sc) return '';
    var grenzen = {}, lauf = 0, i;
    for (i = 0; i < D.tage.length; i++) { grenzen[lauf] = 1; lauf += D.tage[i][1]; }
    var balken = '';
    for (i = 0; i < m.sc.length; i++) {
      var z = Number(m.sc[i]), kn = m.wd.substr(i * 2, 2);
      var titel = (D.stunden[i] || '') + ' · ' + Number(kn) + ' kn';
      balken += '<i class="' + (grenzen[i] ? 'tag' : '') + '" title="' + esc(titel) +
                '" style="height:' + (18 * (0.18 + 0.82 * z / 9)).toFixed(1) + 'px;background:' +
                farbe(z) + '"></i>';
    }
    var beschriftung = '';
    for (i = 0; i < D.tage.length; i++) {
      beschriftung += '<span style="flex:' + D.tage[i][1] + '">' + esc(D.tage[i][0]) + '</span>';
    }
    return '<div class="mband">' + balken + '</div>' +
           '<div class="mbandtag">' + beschriftung + '</div>';
  }

  var style = {
    top:   {radius: 11, color: '#7A1449', fillColor: '#AE1F68', fillOpacity: .92, weight: 2},
    hit:   {radius: 8,  color: '#7A1449', fillColor: '#AE1F68', fillOpacity: .55, weight: 1.5},
    quiet: {radius: 6,  color: '#5C7480', fillColor: '#8FA9B3', fillOpacity: .7,  weight: 1},
    out:   {radius: 5,  color: '#8FA9B3', fillColor: '#8FA9B3', fillOpacity: 0,   weight: 1.5}
  };

  var ebenen = {top: L.layerGroup(), hit: L.layerGroup(), quiet: L.layerGroup(),
                out: L.layerGroup(), camp: L.layerGroup(), thermik: L.layerGroup()};
  var punkte = {top: [], hit: [], quiet: [], out: []}, alleMarker = [];
  var linie = null;

  function luftlinie(m) {
    if (linie) map.removeLayer(linie);
    linie = L.polyline([[D.home.lat, D.home.lon], [m.lat, m.lon]],
      {color: '#14303C', weight: 1.5, opacity: .45, dashArray: '4 5'}).addTo(map);
  }

  var windySchalter = document.getElementById('l_windy');

  D.markers.forEach(function (m) {
    m.lat = Number(m.lat); m.lon = Number(m.lon);
    if (!isFinite(m.lat) || !isFinite(m.lon)) return;
    var mk = L.circleMarker([m.lat, m.lon], style[m.kind] || style.quiet);
    var q = encodeURIComponent(m.lat + ',' + m.lon);
    var koord = m.lat.toFixed(5) + ', ' + m.lon.toFixed(5);
    var sess = m.dirs ? '<br><span style="color:#6C858F">' +
               t('Richtung {richtung} · Wing {wing} m²', {richtung: esc(m.dirs), wing: esc(m.wings)}) + '</span>' : '';
    if (m.thermik) {
      sess += '<br><span style="color:#D98A2B">' + t('Thermikspot: {name}', {name: esc(m.thermik)}) + '</span>';
    }
    if (m.sb === 'yes' || m.sb === 'possible') {
      // Beide Texte sind in katalog.js wörtlich markiert (eingesammelt wird über alle Skripte);
      // tests/test_report_cli.py prüft die Bedingung hier so, wie sie dasteht.
      sess += '<br><span style="color:#8E650A">' + t(m.sb === 'yes' ? 'Shorebreak' : 'Shorebreak möglich') +
              (m.sb_note ? ': ' + esc(m.sb_note) : '') + '</span>';
    }
    if (m.tide) {
      // Die Lage rechnet tide.js beim Öffnen des Popups neu (siehe popupopen unten).
      sess += '<br><span style="color:#2F6F8F">' + t('Tide: {lage}', {lage: '<span data-tide="' + esc(JSON.stringify(m.tide)) + '">' +
              esc(m.tide_text || '') + '</span>'}) + '</span>';
    }
    var windyUrl = 'https://www.windy.com/?' + m.lat + ',' + m.lon + ',11';
    mk.bindPopup(
      '<b><a class="titel" target="_blank" rel="noopener" href="' + windyUrl + '">' +
        (m.rank ? m.rank + '. ' : '') + esc(m.name) + '</a></b><br>' + esc(m.line) + sess +
      '<br><span style="color:#6C858F">' + esc(m.drive) + '</span>' +
      (m.notes ? '<br><span style="color:#6C858F">' + esc(m.notes) + '</span>' : '') +
      '<div class="kmt" data-id="' + esc(m.id) + '" data-text="' + esc(m.kmt) + '"></div>' +
      band(m) +
      '<div class="pl">' +
        '<a target="_blank" rel="noopener" href="' + windyUrl + '">Windy</a>' +
        '<a target="_blank" rel="noopener" href="https://www.google.com/maps/dir/?api=1&origin=' +
          encodeURIComponent(D.home.lat + ',' + D.home.lon) + '&destination=' + q + '">' + t('Route') + '</a>' +
        '<a target="_blank" rel="noopener" href="https://park4night.com/en/search?lat=' + m.lat +
          '&lng=' + m.lon + '&z=12">Park4Night</a>' +
        '<a target="_blank" rel="noopener" href="https://www.openstreetmap.org/?mlat=' + m.lat +
          '&mlon=' + m.lon + '#map=14/' + m.lat + '/' + m.lon + '">' + t('Karte prüfen') + '</a>' +
        (m.ig ? '<a target="_blank" rel="noopener" href="' + esc(m.ig) + '">Instagram</a>' : '') +
      '</div>' +
      '<button class="koord" type="button" data-koord="' + esc(koord) + '">' + t('{koord} — kopieren', {koord: esc(koord)}) + '</button>',
      {maxWidth: 320});
    mk.bindTooltip(esc(m.name) + (m.thermik ? ' · ' + esc(m.thermik) : ''),
                   {className: 'spotname', direction: 'top', offset: [0, -4]});
    mk.on('click', function () {
      luftlinie(m);
      // Windy zusätzlich, nicht statt: das Popup mit Stundenband und Fahrt
      // bleibt geöffnet und wartet, wenn man aus dem neuen Tab zurückkommt.
      if (windySchalter && windySchalter.checked) {
        window.open('https://www.windy.com/?' + m.lat + ',' + m.lon + ',11',
                    '_blank', 'noopener');
      }
    });
    mk.addTo(ebenen[m.kind] || ebenen.quiet);
    // Dauerhafte Namen nur für Treffer: 277 Fahnen gleichzeitig sind ein
    // Farbteppich, in dem man nichts mehr findet. Beim Überfahren zeigt
    // jeder Punkt seinen Namen ohnehin.
    if (m.kind === 'top' || m.kind === 'hit') alleMarker.push(mk);
    // Eigene Ebene: ein orangener Ring um Spots mit hinterlegtem Thermikwissen.
    // Ein Ring statt eines eigenen Punktes, damit die Farbe des Rankings
    // sichtbar bleibt — beides gilt ja gleichzeitig.
    //
    // Der Ring ist Dekoration und fängt deshalb nichts ab: eigene Ebene unter
    // den Punkten, `interactive: false`, und die Ebene selbst auf
    // pointer-events:none. Der Name der Thermik steht im Tooltip des Punktes.
    if (m.thermik) {
      L.circleMarker([m.lat, m.lon], {radius: 13, color: '#D98A2B', weight: 2,
        fill: false, opacity: .9, interactive: false, pane: 'dekor'})
        .addTo(ebenen.thermik);
    }
    (punkte[m.kind] || punkte.quiet).push([m.lat, m.lon]);
  });

  (D.camps || []).forEach(function (c) {
    c.lat = Number(c.lat); c.lon = Number(c.lon);
    if (!isFinite(c.lat) || !isFinite(c.lon)) return;
    var bew = t('noch nicht bewertet');
    if (c.reviews) {
      var bewP = {note: c.rating.toFixed(1), n: c.reviews};
      bew = c.reviews === 1 ? t('{note} bei {n} Bewertung', bewP) : t('{note} bei {n} Bewertungen', bewP);
    }
    L.circleMarker([c.lat, c.lon],
      {radius: 5, color: '#1B4D38', fillColor: '#276B4F', fillOpacity: .85, weight: 1})
      .bindPopup('<b>' + esc(c.name) + '</b><br>' +
        '<span style="color:#6C858F">' + t('Hunde erlaubt') + ' · ' + esc(c.kind) + '<br>' +
        esc(bew) + ' · ' + t('{km} km bis {spot}', {km: c.km.toFixed(1), spot: esc(c.spot)}) + '</span>' +
        (c.url ? '<div class="pl"><a target="_blank" rel="noopener" href="' + esc(c.url) +
          '">Park4Night</a></div>' : ''))
      .bindTooltip(esc(c.name), {className: 'spotname', direction: 'top', offset: [0, -4]})
      .addTo(ebenen.camp);
  });

  var home = L.circleMarker([D.home.lat, D.home.lon],
    {radius: 7, color: '#14303C', fillColor: '#14303C', fillOpacity: 1, weight: 2}).addTo(map);
  home.bindPopup('<b>' + esc(D.home.name) + '</b><br>' + t('Startpunkt'));
  var ring = L.circle([D.home.lat, D.home.lon], {
    radius: D.radius_km * 1000 / (D.umweg || 1.22), color: '#14303C', weight: 1,
    opacity: .35, fillOpacity: .03, dashArray: '5 6',
    interactive: false, pane: 'dekor'          // Dekoration — fängt keinen Klick
  });

  /* ── Schalter ─────────────────────────────────────────────────────────── */
  function schalte(id, ebene) {
    var box = document.getElementById(id);
    if (!box) return;
    if (box.checked) ebene.addTo(map);
    box.addEventListener('change', function () {
      if (box.checked) ebene.addTo(map); else map.removeLayer(ebene);
    });
  }
  schalte('l_top', ebenen.top);
  schalte('l_hit', ebenen.hit);
  schalte('l_quiet', ebenen.quiet);
  schalte('l_out', ebenen.out);
  schalte('l_camp', ebenen.camp);
  schalte('l_thermik', ebenen.thermik);
  schalte('l_ring', ring);

  var namen = document.getElementById('l_names');
  namen.addEventListener('change', function () {
    alleMarker.forEach(function (mk) {
      var t = mk.getTooltip();
      if (!t) return;
      mk.unbindTooltip();
      mk.bindTooltip(t.getContent(), {className: 'spotname', direction: 'top',
        offset: [0, -4], permanent: namen.checked});
    });
  });

  function zeige(listen) {
    var pts = [];
    listen.forEach(function (k) { pts = pts.concat(punkte[k] || []); });
    pts.push([D.home.lat, D.home.lon]);
    map.fitBounds(L.latLngBounds(pts).pad(0.12));
  }
  document.getElementById('b_top').addEventListener('click', function () { zeige(['top']); });
  document.getElementById('b_all').addEventListener('click', function () { zeige(['top', 'hit', 'quiet']); });

  var voll = document.getElementById('b_full');
  voll.addEventListener('click', function () {
    el.classList.toggle('voll');
    voll.textContent = el.classList.contains('voll') ? t('Vollbild beenden') : t('Vollbild');
    setTimeout(function () { map.invalidateSize(); }, 60);
  });
  document.addEventListener('keydown', function (e) {
    if (e.key === 'Escape' && el.classList.contains('voll')) voll.click();
  });

  /* Koordinate kopieren — im Popup, weil man sie von dort ins Navi tippt. */
  map.on('popupopen', function (e) {
    if (window.WSKommentar) window.WSKommentar.alle(e.popup.getElement());
    if (window.WSTide) window.WSTide.alle(e.popup.getElement());
    var b = e.popup.getElement().querySelector('.koord');
    if (!b) return;
    b.addEventListener('click', function () {
      var text = b.getAttribute('data-koord');
      if (navigator.clipboard) navigator.clipboard.writeText(text);
      b.textContent = t('{koord} — kopiert', {koord: text});
    });
  });

  zeige(['top', 'hit', 'quiet']);
  map.on('click', function () { map.scrollWheelZoom.enable(); });

  // Am Handy steckt die Karte in einer Klappe (web/mobil.js). Wird sie
  // geöffnet, hatte Leaflet bis dahin keine Größe — ohne dieses Nachmessen
  // bleibt die Kachelfläche grau.
  document.addEventListener('wingscout:sichtbar', function () {
    setTimeout(function () { map.invalidateSize(); }, 60);
  });
})();
