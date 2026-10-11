/* Reiter „Handy“ (seit 2.5.0): die Knöpfe schicken je eine Anfrage an den
   Server (POST /handy/…), danach lädt die Seite neu und zeigt den neuen Stand
   — Freigabe, QR-Code, Zertifikat; schickt der Server eine Meldung mit,
   bleibt die Seite stehen und zeigt sie. Knöpfe mit `data-zweimal` wollen
   einen zweiten Druck (wie „Beenden“): „Neuer Schlüssel“ sperrt alle
   verbundenen Handys aus.
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
    fetch(pfad, {method: 'POST', headers: {'Content-Type': 'application/json'}, body: '{}'})
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
})();
