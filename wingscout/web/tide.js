
/* Tide zur Anzeigezeit. Der Report ist eine Datei; „jetzt auflaufend“ stimmt
   nur, wenn es beim Öffnen gerechnet wird, nicht beim Erstellen. Jedes
   Element mit data-tide trägt die Hoch- und Niedrigwasser des Spots als
   Unix-Sekunden (epoch) plus die Ortszeit-Beschriftung; gerechnet wird in
   Sekunden, damit die Zeitzone des Browsers keine Rolle spielt. */
window.WSTide = (function () {
  // t(), tagKurz() und die Wochentage (I18N.wt) kommen aus dem Sprachvorspann
  // jeder Seite (i18n.js_vorspann). tests/test_tide.py führt das Skript ohne
  // ihn in Node aus; dort setzt dieses t() nur die Platzhalter ein.
  var t = window.t || function (s, p) { for (var k in p) s = s.split('{' + k + '}').join(String(p[k])); return s; };
  var STAU = 30 * 60;                       // ± 30 min um den Scheitel: Stauwasser
  function pad(n) { return (n < 10 ? '0' : '') + n; }
  function ortszeit(epoch, versatz) {     // Uhrzeit am Spot aus Unix-Sekunden
    var d = new Date((epoch + versatz) * 1000);
    return pad(d.getUTCHours()) + ':' + pad(d.getUTCMinutes());
  }
  function ortstag(epoch, versatz) {
    var d = new Date((epoch + versatz) * 1000);
    return d.toISOString().slice(0, 10);
  }
  function wochentag(tag) {
    var d = new Date(tag + 'T00:00:00Z');
    return isNaN(d) ? '' : I18N.wt[d.getUTCDay()];
  }
  function tagDatum(tag) {               // „Sa 04.10.“ aus „2026-10-04“, dem Datum am Spot
    var d = new Date(tag + 'T12:00:00');
    return isNaN(d) ? '' : tagKurz(d);
  }
  function dauer(sek) {
    var min = Math.round(sek / 60);
    if (min < 1) return t('jetzt');
    if (min < 60) return min + ' min';
    var h = Math.floor(min / 60), m = min % 60;
    return h + ' h' + (m ? ' ' + m + ' min' : '');
  }
  function art(ev) { return ev.art === 'HW' ? t('Hochwasser') : t('Niedrigwasser'); }
  function wann(ev, heute) {             // „um 14:50“ oder „Fr 03:15“, wenn nicht heute
    return ev.tag && ev.tag !== heute ? wochentag(ev.tag) + ' ' + ev.zeit : t('um {zeit}', {zeit: ev.zeit});
  }
  /* Die Fenster als [von, bis] in Sekunden — dieselbe Regel wie in tide.py */
  function fenster(d) {
    var f = d.fenster, ev = d.ereignisse || [], aus = [], i;
    if (!f || !ev.length) return aus;
    if (f.fahrbar === 'hochwasser' || f.fahrbar === 'niedrigwasser') {
      var such = f.fahrbar === 'hochwasser' ? 'HW' : 'NW', b = (f.stunden || 2) * 3600;
      for (i = 0; i < ev.length; i++) if (ev[i].art === such) aus.push([ev[i].epoch - b, ev[i].epoch + b]);
    } else {
      // Halbtiden von Scheitel zu Scheitel; vor dem ersten und nach dem letzten
      // Ereignis eine halbe Periode (≈ 6 h 12 min) ergänzt, wie in tide.py
      var ende = f.fahrbar === 'auflaufend' ? 'HW' : 'NW', halb = 6.2 * 3600, kette = ev.slice();
      if (kette[0].art === ende) kette.unshift({art: '', epoch: kette[0].epoch - halb});
      if (kette[kette.length - 1].art !== ende) kette.push({art: ende, epoch: kette[kette.length - 1].epoch + halb});
      for (i = 1; i < kette.length; i++) if (kette[i].art === ende) aus.push([kette[i - 1].epoch, kette[i].epoch]);
    }
    return aus;
  }
  function text(d, jetzt) {
    var ev = d.ereignisse || [], vor = null, nach = null, i, s;
    if (!ev.length) return '';
    var heute = ortstag(jetzt, d.versatz || 0);
    for (i = 0; i < ev.length; i++) { if (ev[i].epoch <= jetzt) vor = ev[i]; else { nach = ev[i]; break; } }
    if (!nach) return t('Der Report ist älter als sein Tidenverlauf — neu suchen.');
    if (!vor && nach.epoch - jetzt > 26 * 3600) {
      return t('Tidenzeiten ab {tag}', {tag: tagDatum(nach.tag)});
    }
    if (nach.epoch - jetzt <= STAU) s = t('Jetzt {art} ({zeit})', {art: art(nach), zeit: nach.zeit});
    else if (vor && jetzt - vor.epoch <= STAU) s = t('Jetzt {art} ({zeit})', {art: art(vor), zeit: vor.zeit});
    else s = (nach.art === 'HW' ? t('Jetzt auflaufend') : t('Jetzt ablaufend')) + ' · ' +
             t('{art} {wann} (in {dauer})', {art: art(nach), wann: wann(nach, heute), dauer: dauer(nach.epoch - jetzt)});
    var fs = fenster(d), drin = null, naechstes = null;
    for (i = 0; i < fs.length; i++) {
      if (fs[i][0] <= jetzt && jetzt <= fs[i][1]) { drin = fs[i]; break; }
      if (fs[i][0] > jetzt && !naechstes) naechstes = fs[i];
    }
    if (drin) s += ' · ' + t('im Tidenfenster bis {zeit} (noch {dauer})', {zeit: ortszeit(drin[1], d.versatz || 0), dauer: dauer(drin[1] - jetzt)});
    else if (naechstes) {
      var tag = ortstag(naechstes[0], d.versatz || 0);
      s += ' · ' + t('nächstes Tidenfenster {von}–{bis} (in {dauer})', {
        von: (tag !== heute ? wochentag(tag) + ' ' : '') + ortszeit(naechstes[0], d.versatz || 0),
        bis: ortszeit(naechstes[1], d.versatz || 0), dauer: dauer(naechstes[0] - jetzt)});
    } else if (fs.length) s += ' · ' + t('kein weiteres Tidenfenster im Zeitraum');
    return s;
  }
  function setze(el) {
    var d;
    try { d = JSON.parse(el.dataset.tide || ''); } catch (e) { return; }
    if (!d || !d.ereignisse) return;
    var t = text(d, Math.floor(Date.now() / 1000));
    if (t) el.textContent = t;
  }
  function alle(root) {
    [].forEach.call((root || document).querySelectorAll('[data-tide]'), setze);
  }
  function start() {
    alle();
    setInterval(function () { alle(); }, 60 * 1000);
    document.addEventListener('visibilitychange', function () { if (!document.hidden) alle(); });
  }
  return {alle: alle, start: start, text: text, fenster: fenster};
})();
