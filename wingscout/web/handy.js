/* Reiter „Handy“ (seit 2.5.0): die Knöpfe schicken je eine Anfrage an den
   Server (POST /handy/…), danach lädt die Seite neu und zeigt den neuen Stand
   — Freigabe, QR-Code, Zertifikat; schickt der Server eine Meldung mit,
   bleibt die Seite stehen und zeigt sie. Knöpfe mit `data-zweimal` wollen
   einen zweiten Druck (wie „Beenden“): „Neuer Schlüssel“ sperrt alle
   verbundenen Handys aus. `data-daten` geht als JSON mit (seit 2.5.1: der
   Weg, aus dem freigegeben wird).

   Seit 2.5.1 sagt die Seite, solange freigegeben ist, was vom iPhone ankommt
   (GET /handy/stand, alle zwei Sekunden, nur solange die Seite zu sehen ist):
   verbunden, abgebrochen, ohne Schlüssel — oder nach einer Weile nichts, mit
   den üblichen Gründen. Klappt es beim Einrichten, springt die Seite auf die
   Ansicht „eingerichtet“. Jeder Text steht am Stück im Aufruf der
   Übersetzung, sonst findet tools/i18n_texte.py ihn nicht.
   In einer Funktion, damit nichts mit anderen Skripten der Seite kollidiert. */
(function () {
  var meldung = document.getElementById('hmeldung');
  function melde(text, gut) {
    if (!meldung) return;
    meldung.textContent = text || '';
    meldung.className = 'hmeldung' + (gut ? ' gut' : '');
  }

  function senden(pfad, knopf) {
    knopf.disabled = true;
    melde(t('Einen Moment …'), true);
    fetch(pfad, {method: 'POST', headers: {'Content-Type': 'application/json'},
                 body: knopf.getAttribute('data-daten') || '{}'})
      .then(function (r) {
        return r.json().catch(function () { return {}; }).then(function (j) { j.ok = r.ok && j.ok !== false; return j; });
      })
      .catch(function () { return {ok: false, error: t('Wingfoilscout antwortet nicht — läuft es noch?')}; })
      .then(function (j) {
        knopf.disabled = false;
        if (j.ok && j.message) { melde(j.message, true); return; }
        if (j.ok) { location.reload(); return; }
        melde(j.error || '?');
      });
  }

  [].forEach.call(document.querySelectorAll('button[data-pfad]'), function (knopf) {
    var text = knopf.textContent, scharf = null;
    knopf.addEventListener('click', function () {
      if (knopf.hasAttribute('data-zweimal') && !scharf) {
        knopf.classList.add('armed');
        knopf.textContent = t('Wirklich? Noch einmal drücken');
        scharf = setTimeout(function () {
          scharf = null;
          knopf.classList.remove('armed');
          knopf.textContent = text;
        }, 4000);
        return;
      }
      if (scharf) { clearTimeout(scharf); scharf = null; }
      senden(knopf.getAttribute('data-pfad'), knopf);
    });
  });

  // ── Was vom iPhone ankommt ──────────────────────────────────────────────
  var live = document.getElementById('hlive');
  if (!live) return;
  var ansicht = live.getAttribute('data-ansicht'), art = live.getAttribute('data-art');
  var geladen = Date.now(), basis = null;

  function zeige(text, klasse) {
    live.textContent = text;
    live.className = 'hlive' + (klasse ? ' ' + klasse : '');
  }

  function auswerten(j) {
    if (basis === null) basis = j.jetzt;
    if (j.verbunden) {
      // Beim Einrichten: geklappt, und zwar auf diesem Weg → die Ansicht „eingerichtet“
      if (ansicht !== 'fertig' && j.verbunden >= basis - 1 && j.verschluesselt === (art === 'https')) {
        location.href = '/handy';
        return false;
      }
      zeige('✓ ' + (j.verschluesselt ? t('Verbunden — verschlüsselt, um {zeit}.', {zeit: j.verbunden_um})
                                      : t('Verbunden — unverschlüsselt, um {zeit}.', {zeit: j.verbunden_um})), 'gut');
    } else if (j.abgebrochen) {
      zeige(t('Dein iPhone hat die verschlüsselte Verbindung abgebrochen ({zeit}) — meist, weil es dem Zertifikat noch nicht vertraut: Ist das Profil installiert und das Vertrauen eingeschaltet?', {zeit: j.abgebrochen_um}), 'achtung');
    } else if (j.ohne_schluessel) {
      zeige(t('Ein Gerät kam ohne gültigen Schlüssel ({zeit}) — den Code hier neu scannen.', {zeit: j.ohne_schluessel_um}), 'achtung');
    } else if (Date.now() - geladen > 25000) {
      zeige(art === 'http'
        ? t('Noch nichts angekommen. Ist auf dem iPhone die „Warnung vor unsicherer Verbindung“ aus? Ist es im selben WLAN wie der Mac? Fragt macOS, ob Python eingehende Verbindungen annehmen darf: „Erlauben“.')
        : t('Noch nichts angekommen. Ist das iPhone im selben WLAN wie der Mac? Fragt macOS, ob Python eingehende Verbindungen annehmen darf: „Erlauben“.'), 'achtung');
    } else {
      zeige(t('Warte auf dein iPhone …'), '');
    }
    return true;
  }

  function abfragen() {
    if (document.hidden) { setTimeout(abfragen, 2000); return; }
    fetch('/handy/stand', {cache: 'no-store'})
      .then(function (r) { return r.json(); })
      .then(function (j) {
        if (!j.aktiv) { location.reload(); return; }          // anderswo beendet
        if (auswerten(j)) setTimeout(abfragen, 2000);
      })
      .catch(function () { setTimeout(abfragen, 5000); });
  }
  abfragen();
})();
