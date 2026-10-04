/* Session-Tagebuch — eintragen, Sessions mit Vergleich, Vorschläge.
   Daten von der Seite: TAGEBUCH (Sessions, Namen, Quiver, Vorschläge, letzte
   Session) und SPOTS (id, name, region) für die Auswahl. */
var tf = document.getElementById('tf'), tgo = document.getElementById('tgo'),
    tspot = document.getElementById('tspot'), tspotid = document.getElementById('tspotid'),
    twing = document.getElementById('twing'),
    tstatus = document.getElementById('tstatus'), tstatustext = document.getElementById('tstatustext'),
    tbanner = document.getElementById('tbanner'), tprotokoll = document.getElementById('tprotokoll'),
    tlog = document.getElementById('tlog'), tvorschlaege = document.getElementById('tvorschlaege'),
    tsessions = document.getElementById('tsessions');
var DATEN = TAGEBUCH, ttimer = null;

var LEISTUNG = {unter: N_('untermotorisiert'), passt: N_('passt'), ueber: N_('übermotorisiert')};
var WASSER = {flach: N_('flach'), kabbelig: N_('kabbelig'), welle: N_('Welle')};

/* „2026-09-20T19:09“ → „20.09.2026 19:09“ wie überall sonst (Review 25.09., U6)
   schreibt datumZeit() aus dem Sprachvorspann, in der Form der Sprache:
   „20 Sep 2026, 19:09“. Zahlen ebenso: zahlFmt() — 4,2 · 4.2, 1.234 · 1,234. */
function esc(v) {
  return String(v == null ? '' : v).replace(/[&<>"']/g, function (c) {
    return {'&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;'}[c];
  });
}
function zahl(v, stellen, mindestens) {
  if (v == null || isNaN(v)) return '–';
  return zahlFmt(v, stellen == null ? 1 : stellen, mindestens);
}
function qm(v) { return zahl(v, 1, 1) + ' m²'; }
function faktorText(v) { return zahl(v, 2, 2); }
/* „Sa 20.09.“ aus „2026-09-20“ — tagKurz() und I18N kommen aus dem Sprachvorspann */
function tagDatum(iso) { return tagKurz(new Date(iso + 'T12:00:00')); }
function datumKurz(iso) {                     // mit Jahr: „Sa 20.09.2026“ · „Sat 20 Sep 2026“
  return tagDatum(iso) + (I18N.sprache === 'de' ? '' : ' ') + iso.slice(0, 4);
}
/* Wie TN() in Python: Einzahl für n == 1, sonst Mehrzahl; `n` ist Platzhalter.
   Die Texte kommen mit N_ markiert an, übersetzt wird hier. */
function plural(n, eins, viele) { return t(n === 1 ? eins : viele, {n: n}); }
function melde(art, text) { tbanner.className = art ? 'banner ' + art : ''; tbanner.textContent = text || ''; }
function post(pfad, daten) {
  return fetch(pfad, {method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify(daten)})
    .then(function (r) {
      return r.json().catch(function () { return {}; }).then(function (j) { j.ok = r.ok; return j; });
    })
    .catch(function () { return {ok: false, error: t('Wingfoilscout antwortet nicht — läuft es noch?')}; });
}

/* ── Spot: Name tippen, aus der Liste wählen ────────────────────────────────
   Eine eigene Trefferliste statt <datalist>: auf iOS Safari legt Safari deren
   Dropdown über das Eingabefeld, sobald mehr als etwa drei Vorschläge kommen —
   bei 278 Spots ist das unbenutzbar. Hier steht die Liste unter dem Feld, hat
   tippgroße Zeilen und lässt sich mit den Pfeiltasten bedienen. */
var nachLabel = {}, labelVon = {}, ALLE = [];
var tliste = document.getElementById('tspotliste');
var markiert = -1;

(function () {
  SPOTS.forEach(function (s) {
    var label = s.name + (s.region ? ' · ' + s.region : '');
    if (nachLabel[label]) label += ' (' + s.id + ')';        // gleicher Name, gleiche Region
    nachLabel[label] = s.id; labelVon[s.id] = label;
    ALLE.push({id: s.id, label: label, such: label.toLowerCase()});
  });
})();

function spotGesetzt(id) {
  tspotid.value = id || '';
  if (tspotid.value) tspot.classList.remove('falsch');
}

function treffer(text) {
  var q = text.trim().toLowerCase();
  if (!q) return [];
  var teile = q.split(/\s+/);
  return ALLE.filter(function (s) {
    return teile.every(function (t) { return s.such.indexOf(t) >= 0; });
  }).slice(0, 8);
}

function listeZeigen(eintraege) {
  markiert = -1;
  if (!eintraege.length) { listeSchliessen(); return; }
  tliste.innerHTML = eintraege.map(function (s, i) {
    return '<button type="button" role="option" data-id="' + esc(s.id) + '" data-i="' + i + '">' +
           esc(s.label) + '</button>';
  }).join('');
  tliste.hidden = false;
  tspot.setAttribute('aria-expanded', 'true');
}

function listeSchliessen() {
  tliste.hidden = true; tliste.innerHTML = ''; markiert = -1;
  tspot.setAttribute('aria-expanded', 'false');
}

function waehle(id) {
  tspot.value = labelVon[id] || '';
  spotGesetzt(id);
  listeSchliessen();
}

tspot.addEventListener('input', function () {
  spotGesetzt(nachLabel[tspot.value]);
  listeZeigen(treffer(tspot.value));
});
// Rot erst, wenn das Feld verlassen wird, ohne dass ein Spot gewählt ist —
// während des Tippens ist „noch kein Treffer“ der Normalfall.
tspot.addEventListener('blur', function () {
  setTimeout(function () { tspot.classList.toggle('falsch', !!tspot.value && !tspotid.value); }, 150);
});
tspot.addEventListener('focus', function () {
  if (tspot.value && !tspotid.value) listeZeigen(treffer(tspot.value));
});
tspot.addEventListener('keydown', function (e) {
  var knoepfe = tliste.querySelectorAll('button');
  if (e.key === 'Escape') { listeSchliessen(); return; }
  if (!knoepfe.length) return;
  if (e.key === 'ArrowDown' || e.key === 'ArrowUp') {
    e.preventDefault();
    markiert = (markiert + (e.key === 'ArrowDown' ? 1 : knoepfe.length - 1)) % knoepfe.length;
    [].forEach.call(knoepfe, function (b, i) { b.classList.toggle('an', i === markiert); });
  } else if (e.key === 'Enter') {
    e.preventDefault();
    waehle(knoepfe[markiert >= 0 ? markiert : 0].dataset.id);
  }
});
tliste.addEventListener('click', function (e) {
  var b = e.target.closest('button[data-id]');
  if (b) waehle(b.dataset.id);
});
// Antippen außerhalb schließt die Liste; `mousedown` kommt vor `blur`, damit
// der Klick auf einen Treffer noch ankommt.
document.addEventListener('mousedown', function (e) {
  if (!tliste.hidden && !tliste.contains(e.target) && e.target !== tspot) listeSchliessen();
});

function wingsFuellen() {
  var gewaehlt = twing.value || (DATEN.letzte && DATEN.letzte.wing != null ? String(DATEN.letzte.wing) : '');
  var teile = ['<option value="">' + t('— wählen —') + '</option>'];
  (DATEN.wings || []).forEach(function (w) {
    var wert = String(w.size);
    teile.push('<option value="' + esc(wert) + '"' + (Number(wert) === Number(gewaehlt) && gewaehlt !== '' ? ' selected' : '') + '>' +
               esc(qm(w.size) + ' (' + zahl(w.low, 0) + '–' + zahl(w.high, 0) + ' kn)') + '</option>');
  });
  twing.innerHTML = teile.join('');
}

/* ── Eine Session ─────────────────────────────────────────────────────────── */
function stundenDerSession(s) {
  var h0 = Number(s.von.slice(0, 2)), h1 = Number(s.bis.slice(0, 2)), m1 = Number(s.bis.slice(3, 5));
  return Math.max((m1 === 0 ? h1 : h1 + 1) - h0, 1);
}
function stationText(st, vg) {
  if (!st) return '';
  var text = (st.quelle ? st.quelle + ' ' : '') + (st.name || '') + ' · ' + zahl(st.km) + ' km';
  if (st.km > DATEN.station_nah_km) {
    text += ' — ' + t('weiter als {km} km, für die Vorschläge zählt die Vorhersage', {km: zahl(DATEN.station_nah_km, 0)});
  }
  return text;
}
function wert(titel, text, klein) {
  return '<div><i>' + esc(titel) + '</i><b>' + text + '</b>' + (klein ? '<small>' + klein + '</small>' : '') + '</div>';
}
function sessionKarte(s) {
  var vg = s.vergleich, name = DATEN.namen[s.spot] || s.spot;
  var teile = ['<div class="tsession" data-id="' + esc(s.id) + '">',
    '<div class="tkopf"><b>' + esc(name) + '</b><span class="tzeit">' + esc(datumKurz(s.datum)) + ' · ' +
      t('{von}–{bis} Uhr', {von: esc(s.von), bis: esc(s.bis)}) + '</span>',
    '<span class="tknoepfe"><button type="button" class="mini ghost" data-neu="' + esc(s.id) + '">' + t('Neu vergleichen') + '</button>' +
      '<button type="button" class="mini stop" data-weg="' + esc(s.id) + '">' + t('Löschen') + '</button></span></div>',
    '<div class="tchips"><span>' + esc(qm(s.wing)) + '</span><span class="l-' + esc(s.leistung) + '">' +
      esc(t(LEISTUNG[s.leistung] || s.leistung)) + '</span><span>' + esc(t(WASSER[s.wasser] || s.wasser)) + '</span>' +
      '<span class="tnote" title="' + esc(t('Note {note} von 5', {note: s.note})) + '">' + t('Note {note}', {note: esc(s.note)}) + '</span></div>'];
  if (!vg) {
    teile.push('<div class="tgrund">' + t('Noch nicht verglichen — „Neu vergleichen“ holt Vorhersage und Messung.') + '</div>');
  } else {
    var zeilen = [];
    if (vg.wingscout_kn != null || vg.gemessen_kn != null) {
      var ws = [];
      if (vg.wing_vorschlag != null) ws.push(t('Wing {groesse}', {groesse: qm(vg.wing_vorschlag)}));
      if (vg.wasser_vorhersage) ws.push(t(WASSER[vg.wasser_vorhersage] || vg.wasser_vorhersage));
      if (vg.score != null) ws.push(t('Güte {score} von 100', {score: vg.score}));
      zeilen.push(wert(t('Wingfoilscout sagte'), zahl(vg.wingscout_kn) + ' kn', esc(ws.join(' · ')) + (vg.thermik ? ' · ' + t('Thermik angenommen') : '')));
      zeilen.push(wert(t('gemessen'), vg.gemessen_kn != null ? zahl(vg.gemessen_kn) + ' kn' : '–',
                       vg.station ? esc(stationText(vg.station)) + (vg.gemessen_kn != null ? ' · ' +
                         t('{stunden} von {gesamt}', {stunden: plural(vg.gemessen_h, N_('{n} Stunde'), N_('{n} Stunden')),
                                                      gesamt: stundenDerSession(s)}) : '') : t('keine Station')));
      if (vg.spanne) zeilen.push(wert(t('Modelle'), zahl(vg.spanne[0]) + '–' + zahl(vg.spanne[1]) + ' kn',
                                      t('roh, ohne Windfaktor und Thermik')));
      teile.push('<div class="tzahlen">' + zeilen.join('') + '</div>');
      var hinweise = [];
      if (vg.wing_vorschlag != null && Math.abs(vg.wing_vorschlag - s.wing) > 1e-6)
        hinweise.push(t('Wingfoilscout hätte den {vorschlag} genommen, du bist den {gefahren} gefahren.',
                        {vorschlag: qm(vg.wing_vorschlag), gefahren: qm(s.wing)}));
      if (vg.wasser_vorhersage && vg.wasser_vorhersage !== s.wasser)
        hinweise.push(t('Wingfoilscout erwartete „{erwartet}“, du hattest „{hattest}“.',
                        {erwartet: t(WASSER[vg.wasser_vorhersage] || vg.wasser_vorhersage), hattest: t(WASSER[s.wasser] || s.wasser)}));
      if (hinweise.length) teile.push('<div class="thinweis">' + esc(hinweise.join(' ')) + '</div>');
    }
    if (vg.grund) teile.push('<div class="tgrund">' + esc(vg.grund) + '</div>');
    if (vg.letzter_versuch) teile.push('<div class="thinweis">' +
      t('Der Vergleich vom {zeit} fand weniger ({grund}) — der vorige bleibt stehen.', {
        zeit: esc(String(vg.letzter_versuch.gerechnet || '').replace('T', ' ')), grund: esc(vg.letzter_versuch.grund)}) + '</div>');
    if (vg.gerechnet) teile.push('<div class="tgrund">' +
      (vg.version ? t('Verglichen {zeit} mit Version {version}', {zeit: esc(datumZeit(String(vg.gerechnet))), version: esc(vg.version)})
                  : t('Verglichen {zeit}', {zeit: esc(datumZeit(String(vg.gerechnet)))})) + '</div>');
  }
  teile.push('</div>');
  return teile.join('');
}
function sessionsZeichnen() {
  var ss = DATEN.sessions || [];
  if (!ss.length) {
    tsessions.innerHTML = '<div class="tkarte"><h2>' + t('Sessions') + '</h2><p class="tklein">' + t('Noch keine Session eingetragen.') + '</p></div>';
    return;
  }
  var ohne = ss.filter(function (s) { return !s.vergleich || s.vergleich.gemessen_kn == null; });
  tsessions.innerHTML = '<div class="tkarte"><div class="tkopf"><h2>' + t('Sessions') + '</h2><span class="tklein">' +
    plural(ss.length, N_('{n} Session'), N_('{n} Sessions')) + '</span>' +
    (ohne.length ? '<span class="tknoepfe"><button type="button" class="mini ghost" id="talle">' +
      esc(plural(ohne.length, N_('{n} Session ohne Messung neu vergleichen'), N_('{n} Sessions ohne Messung neu vergleichen'))) +
      '</button></span>' : '') +
    '</div><div class="tliste">' + ss.map(sessionKarte).join('') + '</div></div>';
  var alle = document.getElementById('talle');
  if (alle) alle.addEventListener('click', function () {
    vergleiche(ohne.map(function (s) { return s.id; }));
  });
  [].forEach.call(tsessions.querySelectorAll('button[data-neu]'), function (b) {
    b.addEventListener('click', function () { vergleiche([b.dataset.neu]); });
  });
  [].forEach.call(tsessions.querySelectorAll('button[data-weg]'), function (b) {
    b.addEventListener('click', function () {
      if (!b.classList.contains('armed')) {                    // erst scharf machen, dann löschen
        b.classList.add('armed'); b.textContent = t('Wirklich löschen?');
        setTimeout(function () { b.classList.remove('armed'); b.textContent = t('Löschen'); }, 4000);
        return;
      }
      b.disabled = true;
      post('/tagebuch/loeschen', {id: b.dataset.weg}).then(function (j) {
        if (!j.ok) { melde('b-err', j.error || t('Nicht gelöscht.')); b.disabled = false; return; }
        melde('b-ok', t('Session gelöscht.'));
        lade();
      });
    });
  });
}

/* ── Vorschläge ───────────────────────────────────────────────────────────── */
/* Hinweis, wenn dieselben Sessions beide Vorschläge stützen; `satz` ist sein
   erster Satz („… einen Vorschlag zum Windfaktor.“ bzw. „… zum Windfenster.“) */
function ueberschneidung(satz) {
  return '<div class="thinweis">' + satz + ' ' +
    t('Eine Session lässt sich mit dem Windfenster ebenso erklären wie mit Modellen, die an diesem Spot danebenliegen — beide zu übernehmen, korrigiert denselben Befund doppelt. Ob die Modelle danebenlagen, zeigt bei Sessions mit Messung der Vergleich unten.') +
    '</div>';
}
function belegText(b) {
  return tagDatum(b.datum) + ' ' + (DATEN.namen[b.spot] || b.spot) + ': ' +
         t('{leistung} bei {wind} kn ({basis})', {leistung: t(LEISTUNG[b.leistung] || b.leistung), wind: zahl(b.wind, 0), basis: b.basis});
}
function vorschlaegeZeichnen() {
  var vs = DATEN.vorschlaege || {}, fenster = vs.windfenster || [], faktor = vs.windfaktor || [];
  if (!(DATEN.sessions || []).length) { tvorschlaege.innerHTML = ''; return; }
  var teile = ['<div class="tkarte"><h2>' + t('Vorschläge') + '</h2><p class="tklein">' +
    t('Ab {n} Sessions, die in dieselbe Richtung zeigen. Nichts ändert sich von selbst — erst „Übernehmen“ schreibt.', {n: esc(vs.min_belege)}) + '</p>',
    '<h3>' + t('Windfenster je Wing') + ' <span>config.yaml</span></h3>'];
  if (!fenster.length) teile.push('<p class="tklein">' + t('Noch keine verglichene Session mit Wind.') + '</p>');
  fenster.forEach(function (w) {
    var neu = w.low_neu != null || w.high_neu != null;
    var low = w.low_neu != null ? w.low_neu : w.low, high = w.high_neu != null ? w.high_neu : w.high;
    teile.push('<div class="tvorschlag' + (neu ? ' neu' : '') + '"><div class="tvkopf"><b>' + esc(qm(w.size)) + '</b>' +
      '<span>' + zahl(w.low, 0) + '–' + zahl(w.high, 0) + ' kn</span>' +
      (neu ? '<span class="tpfeil">→</span><b class="tneu">' + zahl(low, 0) + '–' + zahl(high, 0) + ' kn</b>' +
             '<button type="button" class="mini tueber" data-art="windfenster" data-size="' + esc(w.size) +
             '" data-low="' + esc(low) + '" data-high="' + esc(high) + '">' + t('Übernehmen') + '</button>'
           : '<span class="tklein">' + esc(w.gruende.length ? plural(w.sessions, N_('{n} Session'), N_('{n} Sessions'))
               : plural(w.sessions, N_('{n} Session, kein Anlass für eine Änderung'), N_('{n} Sessions, kein Anlass für eine Änderung'))) + '</span>') +
      '</div>' +
      (w.gruende.length ? '<ul>' + w.gruende.map(function (g) { return '<li>' + esc(g) + '</li>'; }).join('') + '</ul>' : '') +
      (w.belege.length ? '<div class="tbelege">' + w.belege.map(function (b) { return esc(belegText(b)); }).join('<br>') + '</div>' : '') +
      (w.ueberschneidung ? ueberschneidung(t('Dieselben Sessions stützen auch einen Vorschlag zum Windfaktor.')) : '') +
      '</div>');
  });
  teile.push('<h3>' + t('Windfaktor je Spot') + ' <span>spots.yaml</span></h3>');
  if (!faktor.length) teile.push('<p class="tklein">' + t('Noch keine Session mit rohem Modellwind (ohne Thermikannahme).') + '</p>');
  faktor.forEach(function (f) {
    teile.push('<div class="tvorschlag' + (f.neu != null ? ' neu' : '') + '"><div class="tvkopf"><b>' + esc(f.name) + '</b>' +
      '<span>' + faktorText(f.wind_factor) + '</span>' +
      (f.neu != null ? '<span class="tpfeil">→</span><b class="tneu">' + faktorText(f.neu) + '</b>' +
                       '<button type="button" class="mini tueber" data-art="windfaktor" data-id="' + esc(f.id) +
                       '" data-wert="' + esc(f.neu) + '">' + t('Übernehmen') + '</button>'
                     : '<span class="tklein">' + esc(plural(f.sessions, N_('{n} Session'), N_('{n} Sessions'))) + '</span>') +
      '</div>' + (f.grund ? '<ul><li>' + esc(f.grund) + '</li></ul>' : '') +
      ((f.belege || []).length ? '<div class="tbelege">' + f.belege.map(function (b) { return esc(belegText(b)); }).join('<br>') + '</div>' : '') +
      (f.ueberschneidung ? ueberschneidung(t('Dieselben Sessions stützen auch einen Vorschlag zum Windfenster.')) : '') +
      '</div>');
  });
  teile.push('</div>');
  tvorschlaege.innerHTML = teile.join('');
  [].forEach.call(tvorschlaege.querySelectorAll('button.tueber'), function (b) {
    b.addEventListener('click', function () {
      var d = {art: b.dataset.art};
      if (d.art === 'windfenster') { d.size = Number(b.dataset.size); d.low = Number(b.dataset.low); d.high = Number(b.dataset.high); }
      else { d.id = b.dataset.id; d.wert = Number(b.dataset.wert); }
      b.disabled = true; b.textContent = t('Schreibt …');
      post('/tagebuch/uebernehmen', d).then(function (j) {
        if (!j.ok) { melde('b-err', j.error || t('Nicht übernommen.')); b.disabled = false; b.textContent = t('Übernehmen'); return; }
        melde('b-ok', j.message || t('Übernommen.'));
        if (j.gestartet) verfolge(); else lade();
      });
    });
  });
}

function zeichne() { wingsFuellen(); vorschlaegeZeichnen(); sessionsZeichnen(); }
function lade() {
  return fetch('/tagebuch/daten').then(function (r) { return r.json(); }).then(function (d) { DATEN = d; zeichne(); });
}

/* ── Vergleich im Hintergrund ─────────────────────────────────────────────── */
function uhrzeit(epoch) {
  if (!epoch) return '';
  var d = new Date(epoch * 1000);
  return ' (' + (d.getHours() < 10 ? '0' : '') + d.getHours() + ':' + (d.getMinutes() < 10 ? '0' : '') + d.getMinutes() + ')';
}
function verfolge(fremd) {
  tstatus.style.display = 'flex';
  tstatustext.textContent = fremd ? t('Es läuft gerade etwas anderes — das Tagebuch wartet.') : t('Holt Vorhersage und Messung …');
  tprotokoll.style.display = 'block'; tprotokoll.open = false; tlog.textContent = '';
  if (!ttimer) ttimer = setInterval(poll, 700);
}
function poll() {
  fetch('/status').then(function (r) { return r.json(); }).then(function (j) {
    tlog.textContent = (j.log || []).join('\n');
    tlog.scrollTop = tlog.scrollHeight;
    var letzte = j.log && j.log[j.log.length - 1];
    if (letzte) tstatustext.textContent = letzte.trim().slice(0, 90);
    if (j.state === 'running') return;
    clearInterval(ttimer); ttimer = null;
    tstatus.style.display = 'none';
    if (j.state === 'done' && j.kind === 'tagebuch') melde('b-ok', (j.summary || t('Fertig.')) + uhrzeit(j.ende));
    else if (j.state === 'error' && j.kind === 'tagebuch') { melde('b-err', (j.error || t('Unbekannter Fehler.')) + uhrzeit(j.ende)); tprotokoll.open = true; }
    lade();
  }).catch(function () {
    clearInterval(ttimer); ttimer = null; tstatus.style.display = 'none';
    melde('b-err', t('Wingfoilscout antwortet nicht — läuft es noch?'));
  });
}
function vergleiche(ids) {
  post('/tagebuch/vergleichen', {ids: ids}).then(function (j) {
    if (!j.ok) { melde('b-err', j.error || t('Konnte nicht starten.')); return; }
    melde('', '');
    verfolge();
  });
}

/* ── Eintragen ────────────────────────────────────────────────────────────── */
tf.addEventListener('submit', function (e) {
  e.preventDefault();
  spotGesetzt(nachLabel[tspot.value]);
  var d = {};
  new FormData(tf).forEach(function (v, k) { d[k] = v; });
  var fehlt = [];
  if (!d.spot) fehlt.push(t('Spot (aus der Liste wählen)'));
  if (!d.von || !d.bis) fehlt.push(t('Zeit'));
  if (!d.wing) fehlt.push(t('Wing'));
  if (!d.leistung) fehlt.push(t('Leistung'));
  if (!d.wasser) fehlt.push(t('Wasser'));
  if (!d.note) fehlt.push(t('Note'));
  if (fehlt.length) { melde('b-err', t('Es fehlt noch: {felder}.', {felder: fehlt.join(', ')})); return; }
  tgo.disabled = true; tgo.textContent = t('Speichert …');
  post('/tagebuch/neu', d).then(function (j) {
    tgo.disabled = false; tgo.textContent = t('Eintragen');
    if (!j.ok) { melde('b-err', j.error || t('Nicht gespeichert.')); return; }
    // Für die nächste Session bleiben Spot, Datum und Wing stehen
    ['von', 'bis'].forEach(function (n) { tf.elements[n].value = ''; });
    [].forEach.call(tf.querySelectorAll('input[type=radio]'), function (r) { r.checked = false; });
    if (j.gestartet) {
      melde('b-ok', t('Gespeichert. Wingfoilscout holt jetzt Vorhersage und Messung für diese Stunden …'));
      verfolge();
    } else {
      melde('b-warn', t('Gespeichert. Der Vergleich konnte nicht starten, weil gerade etwas anderes läuft — später bei der Session „Neu vergleichen“.'));
      lade();
    }
  });
});

if (DATEN.letzte && DATEN.letzte.spot && labelVon[DATEN.letzte.spot]) {
  waehle(DATEN.letzte.spot);
}
zeichne();

/* Wie die Such- und die Rückblickseite (seit 1.18.3 bzw. 1.20.1): ein
   Vergleich läuft im Hintergrund weiter, wenn man den Reiter wechselt — die
   Seite fragt beim Laden nach dem Stand und zeigt ihn, statt so zu tun, als
   wäre nichts. */
fetch('/status').then(function (r) { return r.json(); }).then(function (j) {
  if (j.state === 'running') { verfolge(j.kind !== 'tagebuch'); poll(); }
  else if (j.kind === 'tagebuch' && (j.state === 'done' || j.state === 'error')) {
    tprotokoll.style.display = 'block'; tlog.textContent = (j.log || []).join('\n');
    if (j.state === 'done') melde('b-ok', (j.summary || t('Fertig.')) + uhrzeit(j.ende));
    else { melde('b-err', (j.error || t('Unbekannter Fehler.')) + uhrzeit(j.ende)); tprotokoll.open = true; }
  }
}).catch(function () {});
