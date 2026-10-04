
var RDATEN = null;
var rf = document.getElementById('rf'), rgo = document.getElementById('rgo'),
    rstatus = document.getElementById('rstatus'), rstatustext = document.getElementById('rstatustext'),
    rbanner = document.getElementById('rbanner'), rlog = document.getElementById('rlog'),
    rprotokoll = document.getElementById('rprotokoll'), rergebnis = document.getElementById('rergebnis'),
    rtip = document.getElementById('rtip'), rtimer = null;

function esc(v) {
  return String(v == null ? '' : v).replace(/[&<>"']/g, function (c) {
    return {'&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;'}[c];
  });
}
function z(v, n) { return (v == null || isNaN(v)) ? '–' : Number(v).toFixed(n == null ? 1 : n); }
/* „Sa 04.10.“ aus „2026-10-04T14:00“ — tagKurz() kommt aus dem Sprachvorspann
   (i18n.js_vorspann); eine eigene Funktion dieses Namens würde ihn überdecken. */
function tagIso(iso) {
  return tagKurz(new Date(iso.slice(0, 10) + 'T12:00:00'));
}

/* ── Der Verlauf ──────────────────────────────────────────────────────────────
   Standard: die Messung und die graue Spanne aller Modelle, sonst nichts.
   Einzelne Modelle, die Wingfoilscout-Bewertung und „bisher bestes Modell“
   (aus dem Gedächtnis) lassen sich zuschalten — höchstens drei zugleich,
   jede mit eigener Farbe und eigenem Strichmuster. Die Farbe hängt am
   Modell, solange es an ist, nicht an seiner Position in der Liste. */
var LINIEN = [
  {farbe: 'var(--s-l1)', strich: ''},
  {farbe: 'var(--s-l2)', strich: '6 4'},
  {farbe: 'var(--s-l3)', strich: '2 3'}
];
var MAX_LINIEN = LINIEN.length;

function wertVon(h, id) {
  if (id === 'wingscout') return h.v;
  var mv = h.mv || {};
  return mv[id] == null ? null : mv[id];
}
function modellName(spot, id) {
  if (id === 'wingscout') return t('Wingfoilscout-Bewertung');
  var z = ((spot.vergleich || {}).modelle || []).filter(function (m) { return m.id === id; })[0];
  return z ? z.name : ((spot.modellnamen || {})[id] || id);
}
function linienName(spot, id) {
  var bb = spot.bisher_bestes;
  return bb && bb.id === id ? t('{modell} (bisher bestes)', {modell: modellName(spot, id)}) : modellName(spot, id);
}
function angeschaltet(spot) { return spot._an || []; }
function istAn(spot, id) { return angeschaltet(spot).some(function (l) { return l.id === id; }); }
function schalte(spot, id) {
  var an = angeschaltet(spot).slice();
  var i = an.map(function (l) { return l.id; }).indexOf(id);
  if (i >= 0) { an.splice(i, 1); }
  else {
    if (an.length >= MAX_LINIEN) return false;
    var belegt = an.map(function (l) { return l.slot; });
    var frei = [0, 1, 2].filter(function (s) { return belegt.indexOf(s) < 0; })[0];
    an.push({id: id, slot: frei});
  }
  spot._an = an;
  return true;
}
/* Was als Windwert ins Diagramm darf: eine Zahl von 0 bis MAX_KN Knoten.
   Ein kaputter Wert in rueckblick.json — 999999 kn — zog bis 2.1.0 die Achse
   auf eine Million Knoten: 100 001 Gitterlinien, die Seite stand. Was
   außerhalb liegt, ist im Diagramm eine Lücke und zählt nicht für die
   Spanne; die Tabelle zeigt den Wert, wie er ist. */
var MAX_KN = 150;
function sinnvoll(v) { return typeof v === 'number' && isFinite(v) && v >= 0 && v <= MAX_KN; }
function spanneJeStunde(h) {
  var werte = Object.values(h.mv || {}).filter(sinnvoll);
  return werte.length < 2 ? null : [Math.min.apply(null, werte), Math.max.apply(null, werte)];
}

function chart(spot, idx) {
  var st = spot.stunden || [];
  if (!st.length) return '';
  var W = 900, H = 150, L = 34, R = 12, T = 10, B = 22;
  var an = angeschaltet(spot), maxKn = 10;
  st.forEach(function (h) {
    if (sinnvoll(h.m)) maxKn = Math.max(maxKn, h.m);
    var sp = spanneJeStunde(h); if (sp) maxKn = Math.max(maxKn, sp[1]);
    an.forEach(function (l) { var w = wertVon(h, l.id); if (sinnvoll(w)) maxKn = Math.max(maxKn, w); });
  });
  maxKn = Math.ceil(maxKn / 5) * 5;
  var n = st.length, x = function (i) { return L + (W - L - R) * i / Math.max(1, n - 1); },
      y = function (kn) { return T + (H - T - B) * (1 - kn / maxKn); };
  // Am Handy steht das Diagramm in einem Wischbereich: auf 375 pt wären 48
  // Stunden auf 310 px gequetscht und die Tagesbeschriftung unlesbar.
  var teile = ['<div class="rscroll"><svg class="rchart" viewBox="0 0 ' + W + ' ' + H + '" preserveAspectRatio="none" data-idx="' + idx +
               '" data-max="' + maxKn + '" role="img" aria-label="' + esc(t('Wind gemessen und Spanne der Modelle')) + '">'];
  // Nachtstunden hinterlegen — dort zählt die Vorhersage nicht
  var i, start = null;
  for (i = 0; i <= n; i++) {
    var nacht = i < n && (Number(st[i].t.slice(11, 13)) < 8 || Number(st[i].t.slice(11, 13)) >= 20);
    if (nacht && start === null) start = i;
    if (!nacht && start !== null) {
      teile.push('<rect class="band" x="' + x(start) + '" y="' + T + '" width="' + (x(i - 1) - x(start) + (W - L - R) / Math.max(1, n - 1)) + '" height="' + (H - T - B) + '"/>');
      start = null;
    }
  }
  for (var kn = 0; kn <= maxKn; kn += (maxKn > 30 ? 10 : 5)) {
    teile.push('<line class="gitter" x1="' + L + '" x2="' + (W - R) + '" y1="' + y(kn) + '" y2="' + y(kn) + '"/>');
    teile.push('<text class="achse" x="' + (L - 6) + '" y="' + (y(kn) + 3) + '" text-anchor="end">' + kn + '</text>');
  }
  for (i = 0; i < n; i++) {
    if (st[i].t.slice(11, 13) === '00') {
      teile.push('<line class="tag" x1="' + x(i) + '" x2="' + x(i) + '" y1="' + T + '" y2="' + (H - B) + '"/>');
    }
    if (st[i].t.slice(11, 13) === '12') {
      teile.push('<text class="achse" x="' + x(i) + '" y="' + (H - 7) + '" text-anchor="middle">' + esc(tagIso(st[i].t)) + '</text>');
    }
  }
  function pfad(wert) {
    var d = '', offen = false;
    for (var k = 0; k < n; k++) {
      var w = wert(st[k]);
      if (!sinnvoll(w)) { offen = false; continue; }
      d += (offen ? ' L ' : ' M ') + x(k).toFixed(1) + ' ' + y(w).toFixed(1);
      offen = true;
    }
    return d;
  }
  // Die Spanne aller Vergleichsmodelle als graue Fläche
  var oben = [], unten = [];
  for (var k = 0; k < n; k++) {
    var sp = spanneJeStunde(st[k]);
    if (!sp) {
      if (oben.length > 1) teile.push(huelle(oben, unten));
      oben = []; unten = []; continue;
    }
    oben.push([x(k), y(sp[1])]); unten.push([x(k), y(sp[0])]);
  }
  if (oben.length > 1) teile.push(huelle(oben, unten));
  an.forEach(function (l) {
    var s = LINIEN[l.slot];
    teile.push('<path class="linie" style="stroke:' + s.farbe + '"' + (s.strich ? ' stroke-dasharray="' + s.strich + '"' : '') +
               ' d="' + pfad(function (h) { return wertVon(h, l.id); }) + '"/>');
  });
  teile.push('<path class="mess" d="' + pfad(function (h) { return h.m; }) + '"/>');
  teile.push('<line class="kreuz" x1="0" x2="0" y1="' + T + '" y2="' + (H - B) + '"/>');
  an.forEach(function (l) {
    teile.push('<circle class="punkt" data-id="' + esc(l.id) + '" r="4" style="fill:' + LINIEN[l.slot].farbe + '"/>');
  });
  teile.push('<circle class="punkt mess" r="4" style="fill:var(--s-mess)"/>');
  teile.push('<rect class="fang" x="' + L + '" y="' + T + '" width="' + (W - L - R) + '" height="' + (H - T - B) + '"/>');
  teile.push('</svg></div>');
  return teile.join('');
}

function huelle(oben, unten) {
  var d = 'M ' + oben.map(function (p) { return p[0].toFixed(1) + ' ' + p[1].toFixed(1); }).join(' L ') +
          ' L ' + unten.slice().reverse().map(function (p) { return p[0].toFixed(1) + ' ' + p[1].toFixed(1); }).join(' L ') + ' Z';
  return '<path class="huelle" d="' + d + '"/>';
}
function muster(farbe, strich, dick) {
  return '<svg class="muster" width="24" height="8" aria-hidden="true"><line x1="1" y1="4" x2="23" y2="4" style="stroke:' + farbe +
         '" stroke-width="' + (dick || 2) + '"' + (strich ? ' stroke-dasharray="' + strich + '"' : '') + ' stroke-linecap="round"/></svg>';
}
function legende(spot) {
  var teile = ['<span>' + muster('var(--s-mess)', '', 2.5) + t('gemessen an der Station') + '</span>'];
  if ((spot.stunden || []).some(function (h) { return spanneJeStunde(h); })) {
    teile.push('<span><i class="flaeche"></i>' + t('Spanne der Modelle') + '</span>');
  }
  angeschaltet(spot).forEach(function (l) {
    teile.push('<span>' + muster(LINIEN[l.slot].farbe, LINIEN[l.slot].strich) + esc(linienName(spot, l.id)) + '</span>');
  });
  teile.push('<span>' + t('grau hinterlegt: Nacht') + '</span>');
  return '<div class="rlegende">' + teile.join('') + '</div>';
}

function vorzeichen(v) {
  if (v == null || isNaN(v)) return '–';
  if (Math.abs(v) < 0.05) return '0.0';
  return (v > 0 ? '+' : '') + z(v);
}
function prozent(v) { return v == null ? '–' : Math.round(v * 100) + ' %'; }

/* Die Kennzahlen oben auf der Karte — neutral, nicht die einer Linie */
function kennzahlen(spot) {
  var vg = spot.vergleich || {}, bb = spot.bisher_bestes, st = spot.stunden || [];
  var gemessen = st.filter(function (h) { return h.m != null; }).length;
  var spannen = st.map(spanneJeStunde).filter(function (s) { return s; });
  var mittel = spannen.length ? spannen.reduce(function (a, s) { return a + s[1] - s[0]; }, 0) / spannen.length : null;
  var bestes = (vg.modelle || []).filter(function (m) { return m.id === vg.bestes; })[0];
  return '<div class="rzahlen">' +
    '<span><b>' + gemessen + ' h</b><i>' + t('Stunden mit Messung') + '</i></span>' +
    '<span><b>' + (mittel == null ? '–' : z(mittel) + ' kn') + '</b><i>' + t('Spanne der Modelle im Mittel') + '</i></span>' +
    '<span><b>' + (bestes ? esc(bestes.name) + ' · ' + z((bestes.masse || {}).mae) + ' kn' : '–') + '</b>' +
      '<i>' + t('bestes Modell dieser Tage (MAE)') + '</i></span>' +
    '<span><b>' + (bb ? esc(bb.name) + (bb.mae != null ? ' · ' + z(bb.mae) + ' kn' : '') : '–') + '</b>' +
      '<i>' + (!bb ? t('bisher bestes Modell — noch keine Historie')
                   : bb.quelle === 'spot' ? t('bisher bestes Modell (hier, {n} Tage)', {n: bb.tage || 0})
                   : t('bisher bestes Modell (alle Spots, {n} Tage)', {n: bb.tage || 0})) + '</i></span>' +
    '</div>';
}

/* Je Spot: jedes Modell gegen dieselbe Messung */
function vergleichTabelle(spot) {
  var vg = spot.vergleich || {}, zeilen = vg.modelle || [], bb = spot.bisher_bestes;
  if (!zeilen.length) return '';
  var art = {regional: t('regional'),
             bewertung: spot.modell ? t('Bewertung mit Spotwissen, Regionalmodell {modell}', {modell: spot.modell}) : t('Bewertung mit Spotwissen')};
  var rows = zeilen.map(function (r) {
    var m = r.masse || {}, best = r.id === vg.bestes;
    return '<tr><td' + (best ? ' class="gut"' : '') + '>' + (best ? '★ ' : '') + esc(r.name) +
      (art[r.art] ? '<span class="art">' + esc(art[r.art]) + '</span>' : '') +
      (bb && bb.id === r.id ? '<span class="art">' + t('bisher bestes') + '</span>' : '') + '</td><td' + (best ? ' class="gut"' : '') + '>' +
      z(m.mae) + '</td><td>' + vorzeichen(m.bias) + '</td><td>' + prozent(m.richtung) + '</td><td>' + z(m.f1, 2) +
      '</td><td>' + (m.n || 0) + '</td></tr>';
  });
  return '<details class="rtabelle rvergleich" open><summary>' + t('Modelle im Vergleich — wer lag hier am nächsten an der Messung? (★ bestes dieser Tage)') + '</summary>' +
    '<table><thead><tr><th>' + t('Modell') + '</th><th>MAE kn</th><th>Bias kn</th><th>' + t('Richtung') + '</th><th>F1 ≥ 12 kn</th><th>' + t('Stunden') + '</th></tr></thead><tbody>' +
    rows.join('') + '</tbody></table></details>';
}

function modellChips(spot, idx) {
  var zeilen = ((spot.vergleich || {}).modelle || []).filter(function (m) { return m.id !== 'wingscout' && (m.masse || {}).n; });
  var hatWs = (spot.stunden || []).some(function (h) { return h.v != null; });
  if (!zeilen.length && !hatWs) return '';
  var voll = angeschaltet(spot).length >= MAX_LINIEN, bb = spot.bisher_bestes;
  function knopf(id, text, extra) {
    var an = istAn(spot, id);
    var klassen = (an ? 'an ' : '') + (extra || '');
    return '<button type="button" data-idx="' + idx + '" data-modell="' + esc(id) + '"' +
      ' aria-pressed="' + (an ? 'true' : 'false') + '"' + (klassen.trim() ? ' class="' + klassen.trim() + '"' : '') +
      (!an && voll ? ' disabled title="' + esc(t('Höchstens drei Linien zugleich — erst eine abschalten')) + '"' : '') + '>' + text + '</button>';
  }
  var teile = ['<div class="rchips"><span>' + t('Ins Diagramm:') + '</span>'];
  if (bb) teile.push(knopf(bb.id, t('Bisher bestes Modell: {modell}', {modell: esc(bb.name)}), 'bisher'));
  else teile.push('<button type="button" class="bisher" disabled title="' + esc(t('Das Gedächtnis kennt noch kein Modell mit 24 gemeinsamen Stunden')) + '">' +
                  t('Bisher bestes Modell: noch keine Historie') + '</button>');
  zeilen.forEach(function (m) { teile.push(knopf(m.id, esc(m.name))); });
  if (hatWs) teile.push(knopf('wingscout', t('Wingfoilscout-Bewertung')));
  if (angeschaltet(spot).length) teile.push('<button type="button" data-idx="' + idx + '" data-modell="" class="aus">' + t('alle aus') + '</button>');
  teile.push('</div>');
  return teile.join('');
}

/* Über alle Spots dieses Rückblicks, und über alles, was je geprüft wurde */
function gesamtTabelle(zeilen, mitTagen) {
  var rows = zeilen.map(function (r, i) {
    var m = r.masse || {};
    return '<tr><td' + (i === 0 ? ' class="gut"' : '') + '>' + esc(r.name) + '</td><td' + (i === 0 ? ' class="gut"' : '') + '>' +
      z(m.mae) + '</td><td>' + vorzeichen(m.bias) + '</td><td>' + prozent(m.richtung) + '</td><td>' + z(m.f1, 2) +
      '</td><td>' + (r.spots || 0) + '</td><td>' + (r.bestes || 0) + '</td>' + (mitTagen ? '<td>' + (r.tage || 0) + '</td>' : '') +
      '<td>' + (m.n || 0) + '</td></tr>';
  });
  return '<div class="rtabelle rvergleich"><table><thead><tr><th>' + t('Modell') + '</th><th>MAE kn</th><th>Bias kn</th><th>' + t('Richtung') + '</th>' +
    '<th>F1 ≥ 12 kn</th><th>' + t('Spots') + '</th><th>' + t('bestes an') + '</th>' + (mitTagen ? '<th>' + t('Tage') + '</th>' : '') +
    '<th>' + t('Stunden') + '</th></tr></thead><tbody>' +
    rows.join('') + '</tbody></table></div>';
}

function gesamtBlock(daten) {
  var teile = [];
  var g = daten.vergleich_gesamt || [];
  if (g.length) {
    teile.push('<div class="rgesamt"><h2>' + t('Welches Modell lag in diesem Rückblick am besten?') + '</h2>' +
      '<p>' + t('Alle geprüften Ziele zusammen, sortiert nach dem mittleren Fehler. Die Modelle stehen roh da, wie Open-Meteo sie liefert; die „Wingfoilscout-Bewertung“ rechnet Spotwissen ein (Windfaktor, Thermik, Regionalmodell). Regionalmodelle zählen nur an den Spots, die sie abdecken — „Spots“ sagt, an wie vielen.') +
      '</p>' + gesamtTabelle(g, false) + '</div>');
  }
  var ged = daten.gedaechtnis || {};
  if (ged.fehler) teile.push('<div class="rgesamt"><p>' + esc(ged.fehler) + '</p></div>');
  if ((ged.modelle || []).length) {
    var js = (ged.je_spot || []).map(function (sp) {
      return '<tr><td>' + esc(sp.name) + '</td><td class="gut">' + esc(sp.bestes) + ' (' + z(sp.mae) + ')</td><td>' +
        (sp.zweites ? esc(sp.zweites) + ' (' + z(sp.zweites_mae) + ')' : '–') + '</td><td>' + z(sp.wingscout_mae) +
        '</td><td>' + (sp.tage || 0) + '</td></tr>';
    });
    teile.push('<div class="rgesamt"><h2>' + t('Gedächtnis: alle bisherigen Prüfungen') + '</h2>' +
      '<p>' + t('Seit {seit} · {tage} Tage · {spots} Spots.', {seit: esc(ged.seit), tage: ged.tage || 0, spots: ged.spots || 0}) + ' ' +
      t('Jeder Tag zählt einmal — eine neue Prüfung ersetzt einen Tag, der schon da war. Erst nach einigen Wochen ist die Rangliste belastbar; ein bestes Modell wird je Spot erst ab 24 gemeinsamen Stunden genannt. Daraus kommt „Bisher bestes Modell“ an jedem Spot: das beste dort, und wo der Spot noch keine 24 Stunden hat, das beste über alle Spots.') +
      '</p>' +
      gesamtTabelle(ged.modelle, true) +
      (js.length ? '<details class="rtabelle rvergleich"><summary>' + t('Je Spot: welches Modell dort am besten lag') + '</summary><table><thead><tr>' +
        '<th>' + t('Spot') + '</th><th>' + t('bestes (MAE kn)') + '</th><th>' + t('zweites') + '</th><th>Wingfoilscout</th><th>' + t('Tage') + '</th></tr></thead><tbody>' + js.join('') +
        '</tbody></table></details>' : '') + '</div>');
  }
  return teile.join('');
}

/* Alle Stunden als Tabelle — zugleich die Tabellenansicht jeder Linie */
function tabelle(spot) {
  var st = spot.stunden || [];
  if (!st.length) return '';
  var modelle = ((spot.vergleich || {}).modelle || []).filter(function (m) { return m.id !== 'wingscout' && (m.masse || {}).n; });
  var kopf = '<th>' + t('Stunde (Ortszeit)') + '</th><th>' + t('gemessen kn') + '</th><th>' + t('Richtung') + '</th><th>' + t('Spanne kn') + '</th>' +
    modelle.map(function (m) { return '<th>' + esc(m.name) + '</th>'; }).join('') + '<th>Wingfoilscout</th>';
  var zeilen = st.map(function (h) {
    var sp = spanneJeStunde(h);
    return '<tr><td>' + esc(h.t.slice(0, 10) + ' ' + h.t.slice(11, 16)) + '</td><td>' + z(h.m) + '</td><td>' +
           (h.md == null ? '–' : h.md + '°') + '</td><td>' + (sp ? z(sp[0]) + '–' + z(sp[1]) : '–') + '</td>' +
           modelle.map(function (m) { return '<td>' + z(wertVon(h, m.id)) + '</td>'; }).join('') +
           '<td>' + z(h.v) + '</td></tr>';
  });
  return '<details class="rtabelle"><summary>' + t('Alle Stunden als Tabelle') + '</summary><div class="rbreit"><table><thead><tr>' + kopf +
         '</tr></thead><tbody>' + zeilen.join('') + '</tbody></table></div></details>';
}

function zeichne(daten) {
  if (!daten || !daten.spots) {
    // Ein Satz statt Leere unter der Erklärung (Review 25.09., U9)
    rergebnis.innerHTML = '<p class="sub" style="margin-top:14px">' + t('Noch kein Rückblick — oben „Prüfen“ drücken, dann stehen hier die Messungen gegen die Vorhersage.') + '</p>';
    return;
  }
  RDATEN = daten;
  var teile = ['<div class="rliste">'];
  teile.push('<p class="sub" style="margin:18px 0 0">' + t('{von} bis {bis}', {von: esc(daten.von), bis: esc(daten.bis)}) +
             ' · ' + t('geprüft {zeit}', {zeit: esc(String(daten.zeit || '').replace('T', ' '))}) +
             (daten.max_km ? ' · ' + t('Stationen bis {km} km', {km: esc(Math.round(daten.max_km))}) : '') + '</p>');
  daten.spots.forEach(function (sp, idx) {
    teile.push('<div class="rkarte"><div class="rkopf">' +
      (sp.rang ? '<span class="rrang">' + esc(sp.rang) + '</span>' : '') +
      '<b>' + esc(sp.name) + '</b>' +
      (sp.station ? '<span class="rstation">' + esc(sp.station.quelle) + ' ' + esc(sp.station.name || sp.station.id) +
                    ' · ' + t('{km} km vom Spot', {km: esc(sp.station.km)}) +
                    (sp.station.statt ? ' · ' + t('statt {quelle} {name} ({km} km, nur {n} von {moeglich} Stunden bis jetzt)', {
                      quelle: esc(sp.station.statt.quelle), name: esc(sp.station.statt.name), km: esc(sp.station.statt.km),
                      n: esc(sp.station.statt.stunden), moeglich: esc(sp.station.moeglich)}) : '') +
                    '</span>' : '') +
      '</div>');
    if (sp.abdeckung) teile.push('<p class="rabdeckung">' + t('Messung vorhanden: {stunden}', {stunden: esc(sp.abdeckung)}) + '</p>');
    teile.push('<div class="kmt" data-id="' + esc(sp.id) + '" data-text="' + esc(KOMMENTARE[sp.id] || '') + '"></div>');
    if (sp.grund) {
      teile.push('<p class="rgrund">' + esc(sp.grund) + '</p></div>');
      return;
    }
    teile.push(kennzahlen(sp));
    teile.push(legende(sp));
    teile.push(chart(sp, idx));
    teile.push(modellChips(sp, idx));
    teile.push(vergleichTabelle(sp));
    teile.push(tabelle(sp));
    teile.push('</div>');
  });
  teile.push('</div>');
  teile.push(gesamtBlock(daten));
  rergebnis.innerHTML = teile.join('');
  WSKommentar.alle(rergebnis);
  [].forEach.call(rergebnis.querySelectorAll('.rchips button[data-idx]'), function (b) {
    b.addEventListener('click', function () {
      var spot = RDATEN.spots[Number(b.dataset.idx)];
      if (!b.dataset.modell) spot._an = [];
      else schalte(spot, b.dataset.modell);
      var y = window.scrollY; zeichne(RDATEN); window.scrollTo(0, y);
    });
  });
  fadenkreuz(daten);
}

/* ── Fadenkreuz mit Werten ─────────────────────────────────────────────────── */
function fadenkreuz(daten) {
  [].forEach.call(document.querySelectorAll('svg.rchart'), function (svg) {
    var spot = daten.spots[Number(svg.dataset.idx)], st = spot.stunden || [], an = angeschaltet(spot);
    var fang = svg.querySelector('.fang'), kreuz = svg.querySelector('.kreuz'), pm = svg.querySelector('.punkt.mess');
    var W = 900, L = 34, R = 12, H = 150, T = 10, B = 22, n = st.length, maxKn = Number(svg.dataset.max) || 20;
    function y(kn) { return T + (H - T - B) * (1 - kn / maxKn); }
    function punkt(el, x, w) {
      if (!el) return;
      if (sinnvoll(w)) { el.setAttribute('cx', x); el.setAttribute('cy', y(w)); el.style.display = 'block'; }
      else el.style.display = 'none';
    }
    fang.addEventListener('mousemove', function (e) {
      var box = svg.getBoundingClientRect();
      var px = (e.clientX - box.left) / box.width * W;
      var i = Math.round((px - L) / (W - L - R) * Math.max(1, n - 1));
      i = Math.max(0, Math.min(n - 1, i));
      var h = st[i], x = L + (W - L - R) * i / Math.max(1, n - 1), sp = spanneJeStunde(h);
      kreuz.setAttribute('x1', x); kreuz.setAttribute('x2', x); kreuz.style.display = 'block';
      punkt(pm, x, h.m);
      var zeilen = ['<b>' + t('{tag} {zeit} Uhr', {tag: esc(tagIso(h.t)), zeit: esc(h.t.slice(11, 16))}) + '</b>',
                    h.md == null ? t('gemessen {kn} kn', {kn: z(h.m)}) : t('gemessen {kn} kn aus {grad}°', {kn: z(h.m), grad: h.md})];
      if (sp) zeilen.push(t('Modelle {von}–{bis} kn', {von: z(sp[0]), bis: z(sp[1])}));
      an.forEach(function (l) {
        var w = wertVon(h, l.id);
        punkt(svg.querySelector('.punkt[data-id="' + l.id + '"]'), x, w);
        zeilen.push(esc(linienName(spot, l.id)) + ' ' + z(w) + ' kn' +
                    (l.id === 'wingscout' && h.modell ? ' (' + esc(h.modell) + ')' : '') +
                    (l.id === 'wingscout' && h.thermik ? ' · ' + t('Thermik angenommen') : ''));
      });
      rtip.innerHTML = zeilen.join('<br>');
      rtip.style.display = 'block';
      rtip.style.left = (e.pageX + 14) + 'px';
      rtip.style.top = (e.pageY - 10) + 'px';
    });
    fang.addEventListener('mouseleave', function () {
      kreuz.style.display = 'none'; rtip.style.display = 'none';
      [].forEach.call(svg.querySelectorAll('.punkt'), function (p) { p.style.display = 'none'; });
    });
  });
}

/* ── Lauf starten und verfolgen ───────────────────────────────────────────── */
function uhrzeit(epoch) {
  if (!epoch) return '';
  var d = new Date(epoch * 1000);
  return ' (' + (d.getHours() < 10 ? '0' : '') + d.getHours() + ':' + (d.getMinutes() < 10 ? '0' : '') + d.getMinutes() + ')';
}
/* Spinner, Knopf gesperrt, Protokoll auf — beim Start wie beim Wiederkommen.
   `fremd`: es läuft gerade etwas anderes (eine Suche, ein Import); dann
   wartet der Rückblick, statt beim Klick mit 409 abgewiesen zu werden. */
function zeigeLauf(fremd) {
  rgo.disabled = true; rgo.textContent = fremd ? t('Wartet …') : t('Holt …');
  rbanner.className = ''; rbanner.textContent = '';
  rstatus.style.display = 'flex';
  rstatustext.textContent = fremd ? t('Es läuft gerade etwas anderes — der Rückblick wartet.') : t('Läuft …');
  rprotokoll.style.display = 'block'; rprotokoll.open = false; rlog.textContent = '';
  if (!rtimer) rtimer = setInterval(poll, 700);
}
function zeigeErgebnis(j) {
  rstatus.style.display = 'none';
  rgo.disabled = false; rgo.textContent = t('Prüfen');
  if (j.kind !== 'rueckblick') return;                 // eine fremde Arbeit ist fertig — nichts zu sagen
  if (j.state === 'done') {
    rbanner.className = 'banner b-ok'; rbanner.textContent = (j.summary || t('Fertig.')) + uhrzeit(j.ende);
  } else if (j.state === 'error') {
    rbanner.className = 'banner b-err'; rbanner.textContent = (j.error || t('Unbekannter Fehler.')) + uhrzeit(j.ende);
    rprotokoll.open = true;
  }
}
function poll() {
  fetch('/status').then(function (r) { return r.json(); }).then(function (j) {
    rlog.textContent = (j.log || []).join('\n');
    rlog.scrollTop = rlog.scrollHeight;
    var letzte = j.log && j.log[j.log.length - 1];
    if (letzte) rstatustext.textContent = letzte.trim().slice(0, 90);
    if (j.state === 'running') return;
    clearInterval(rtimer); rtimer = null;
    zeigeErgebnis(j);
    if (j.state === 'done' && j.kind === 'rueckblick') {
      fetch('/rueckblick/daten').then(function (r) { return r.json(); }).then(zeichne);
    }
  }).catch(function () {});
}

rf.addEventListener('submit', function (e) {
  e.preventDefault();
  zeigeLauf(false);
  fetch('/rueckblick/start', {method: 'POST', body: new URLSearchParams(new FormData(rf))}).then(function (r) {
    if (r.status === 409) {
      clearInterval(rtimer); rtimer = null;
      rgo.disabled = false; rgo.textContent = t('Prüfen'); rstatus.style.display = 'none';
      rbanner.className = 'banner b-err'; rbanner.textContent = t('Es läuft schon etwas — bitte warten.');
      return;
    }
    if (!r.ok) {
      return r.json().then(function (j) {
        clearInterval(rtimer); rtimer = null;
        rgo.disabled = false; rgo.textContent = t('Prüfen'); rstatus.style.display = 'none';
        rbanner.className = 'banner b-err'; rbanner.textContent = j.error || t('Fehlgeschlagen.');
      });
    }
  });
});

zeichne(DATEN);          // ohne Daten steht der Satz „Noch kein Rückblick“ da (U9)

/* Ein Lauf gehört zum Programm, nicht zum Fenster (suche.js, seit 1.18.3) —
   die Rückblickseite wusste bis 1.20.0 beim Wiederkommen trotzdem nichts von
   ihm: kein Spinner, „Prüfen“ frei, das alte Ergebnis stand da, als wäre
   nichts passiert, und das neue kam erst nach einem Neuladen. Jetzt fragt sie
   beim Laden nach dem Stand: läuft ein Rückblick, zeigt sie ihn und pollt
   weiter; läuft etwas anderes, wartet sie; war das Letzte ein Rückblick,
   steht sein Ergebnis mit Uhrzeit da (die Daten hat die Seite vom Server
   schon frisch bekommen). */
fetch('/status').then(function (r) { return r.json(); }).then(function (j) {
  if (j.state === 'running') { zeigeLauf(j.kind !== 'rueckblick'); poll(); }
  else if (j.kind === 'rueckblick' && (j.state === 'done' || j.state === 'error')) {
    rprotokoll.style.display = 'block'; rlog.textContent = (j.log || []).join('\n');
    zeigeErgebnis(j);
  }
}).catch(function () {});
