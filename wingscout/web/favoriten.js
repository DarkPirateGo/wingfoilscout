/* Favoriten in der Startmaske (seit 2.4.0, gewünscht am 06.10.2026).
   Spot eintippen, aus der Trefferliste wählen — er kommt als Plakette in die
   Liste. Mit „Favoriten zuerst zeigen“ rechnet jede Suche sie mit, auch
   außerhalb des Radius, und der Report beginnt mit ihnen: Favoriten → die
   besten drei → Karte. Jede Änderung wird gleich gemerkt (POST /favoriten →
   favoriten.json); gesucht wird mit dem versteckten Feld „favoriten“.
   Daten von der Seite: FAVORITEN ({ids, zuerst, max}) und FAV_SPOTS
   ([{id, name, region}]). Die Trefferliste ist die des Tagebuchs: eine eigene
   statt <datalist>, weil iOS Safari deren Dropdown über das Feld legt.
   In einer Funktion, damit nichts mit suche.js im selben Skriptblock kollidiert. */
(function () {
  var feld = document.getElementById('favsuche'),
      liste = document.getElementById('favliste'),
      plaketten = document.getElementById('favchips'),
      versteckt = document.getElementById('favoriten'),
      zuerst = document.getElementById('fav_zuerst'),
      schalter = document.getElementById('favan'),
      meldung = document.getElementById('favmsg');
  if (!feld || !liste || !plaketten || !versteckt || !zuerst || !schalter || !meldung) return;

  var MAX = FAVORITEN.max || 10;
  var ids = [], nachId = {}, ALLE = [], markiert = -1, laeuft = false, nochmal = false;

  function esc(v) {
    return String(v == null ? '' : v).replace(/[&<>"']/g, function (c) {
      return {'&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;'}[c];
    });
  }
  /* Klein und ohne Akzente, auf beiden Seiten: „etang“ findet „Étang de
     Leucate“, „grun“ wie „grün“ findet „Grüner Brink“. */
  function flach(s) {
    s = String(s || '').toLowerCase();
    try { return s.normalize('NFD').replace(/[̀-ͯ]/g, ''); }
    catch (e) { return s; }
  }
  function melde(text) { meldung.textContent = text || ''; }

  FAV_SPOTS.forEach(function (s) {
    var label = s.name + (s.region ? ' · ' + s.region : '');
    nachId[s.id] = {name: s.name, label: label};
    ALLE.push({id: s.id, label: label, such: flach(label + ' ' + s.id)});
  });
  (FAVORITEN.ids || []).forEach(function (id) {
    if (nachId[id] && ids.indexOf(id) < 0 && ids.length < MAX) ids.push(id);
  });

  function zeichnen() {
    plaketten.innerHTML = ids.map(function (id, i) {
      var name = nachId[id] ? nachId[id].name : id;
      var weg = t('{name} aus den Favoriten nehmen', {name: name});
      return '<li><span title="' + esc(nachId[id] ? nachId[id].label : id) + '">' + esc(name) + '</span>' +
             '<button type="button" class="favweg" data-i="' + i + '" aria-label="' + esc(weg) +
             '" title="' + esc(weg) + '">×</button></li>';
    }).join('');
    plaketten.hidden = !ids.length;
    schalter.hidden = !ids.length;
    versteckt.value = ids.join(',');
    feld.placeholder = ids.length >= MAX ? t('Höchstens {n} Favoriten — erst einen herausnehmen', {n: MAX})
                                         : t('Spotname eintippen');
  }

  /* Gemerkt wird jede Änderung gleich. Schlägt es fehl, gilt die Liste trotzdem
     für die nächste Suche — sie steht im Formular —, nur nicht nach einem
     Neuladen. Immer nur eine Anfrage zugleich, und wer während einer ändert,
     schickt danach den neuesten Stand: zwei schnelle Klicks konnten sonst in
     falscher Reihenfolge ankommen und den älteren Stand stehen lassen
     (Review 07.10.2026). */
  function speichern() {
    if (laeuft) { nochmal = true; return; }
    laeuft = true; nochmal = false;
    fetch('/favoriten', {method: 'POST', headers: {'Content-Type': 'application/json'},
                         body: JSON.stringify({ids: ids, zuerst: zuerst.checked})})
      .then(function (r) {
        return r.json().catch(function () { return {}; }).then(function (j) { j.ok = r.ok; return j; });
      })
      .catch(function () { return {ok: false, error: t('Wingfoilscout antwortet nicht — läuft es noch?')}; })
      .then(function (j) {
        laeuft = false;
        if (nochmal) { speichern(); return; }
        melde(j.ok ? '' : t('Favoriten nicht gemerkt: {fehler}', {fehler: j.error || '?'}));
      });
  }

  /* Höchstens acht Treffer, ohne die schon gewählten — `schon` sagt, ob nur
     solche passten (dann heißt es nicht „kein Spot passt“). */
  function treffer(text) {
    var q = flach(text).trim(), schon = false;
    if (!q) return {liste: [], schon: false};
    var teile = q.split(/\s+/);
    var liste = ALLE.filter(function (s) {
      if (!teile.every(function (w) { return s.such.indexOf(w) >= 0; })) return false;
      if (ids.indexOf(s.id) >= 0) { schon = true; return false; }
      return true;
    }).slice(0, 8);
    return {liste: liste, schon: schon};
  }

  function listeSchliessen() {
    liste.hidden = true; liste.innerHTML = ''; markiert = -1;
    feld.setAttribute('aria-expanded', 'false');
    feld.removeAttribute('aria-activedescendant');
  }

  function listeZeigen(eintraege) {
    markiert = -1;
    feld.removeAttribute('aria-activedescendant');
    if (!eintraege.length) { listeSchliessen(); return; }
    liste.innerHTML = eintraege.map(function (s, i) {
      return '<button type="button" role="option" id="favopt-' + i + '" aria-selected="false" data-id="' +
             esc(s.id) + '">' + esc(s.label) + '</button>';
    }).join('');
    liste.hidden = false;
    feld.setAttribute('aria-expanded', 'true');
  }

  function markieren(knoepfe) {
    [].forEach.call(knoepfe, function (b, i) {
      b.classList.toggle('an', i === markiert);
      b.setAttribute('aria-selected', i === markiert ? 'true' : 'false');
    });
    if (markiert >= 0) {
      feld.setAttribute('aria-activedescendant', knoepfe[markiert].id);
      knoepfe[markiert].scrollIntoView({block: 'nearest'});
    }
  }

  function hinzu(id) {
    if (!nachId[id] || ids.indexOf(id) >= 0) { listeSchliessen(); return; }
    if (ids.length >= MAX) {
      melde(t('Höchstens {n} Favoriten — erst einen herausnehmen', {n: MAX}));
      listeSchliessen();
      return;
    }
    ids.push(id);
    feld.value = '';
    listeSchliessen();
    zeichnen();
    melde('');
    speichern();
  }

  feld.addEventListener('input', function () {
    var r = treffer(feld.value);
    listeZeigen(r.liste);
    if (!feld.value.trim() || r.liste.length) melde('');
    else melde(r.schon ? t('Schon unter deinen Favoriten.') : t('Kein Spot im Katalog passt dazu.'));
  });
  feld.addEventListener('focus', function () {
    if (feld.value.trim()) listeZeigen(treffer(feld.value).liste);
  });
  feld.addEventListener('keydown', function (e) {
    var knoepfe = liste.querySelectorAll('button');
    if (e.key === 'Escape') { listeSchliessen(); return; }
    // Enter wählt — und schickt nie das Suchformular ab, auch ohne Treffer
    if (e.key === 'Enter') {
      e.preventDefault();
      if (knoepfe.length) hinzu(knoepfe[markiert >= 0 ? markiert : 0].dataset.id);
      return;
    }
    if (!knoepfe.length) return;
    if (e.key === 'ArrowDown' || e.key === 'ArrowUp') {
      e.preventDefault();
      // Pfeil hoch ohne Auswahl: der letzte Treffer, nicht der vorletzte
      markiert = markiert < 0 ? (e.key === 'ArrowDown' ? 0 : knoepfe.length - 1)
                              : (markiert + (e.key === 'ArrowDown' ? 1 : knoepfe.length - 1)) % knoepfe.length;
      markieren(knoepfe);
    }
  });
  liste.addEventListener('click', function (e) {
    var b = e.target.closest('button[data-id]');
    if (b) hinzu(b.dataset.id);
  });
  // Antippen außerhalb schließt die Liste; `mousedown` kommt vor `blur`, damit
  // der Klick auf einen Treffer noch ankommt.
  document.addEventListener('mousedown', function (e) {
    if (!liste.hidden && !liste.contains(e.target) && e.target !== feld) listeSchliessen();
  });

  plaketten.addEventListener('click', function (e) {
    var b = e.target.closest('button.favweg');
    if (!b) return;
    var i = Number(b.dataset.i);
    ids.splice(i, 1);
    zeichnen();
    melde('');
    speichern();
    // Der Fokus bleibt in der Liste: auf dem Nachbarn, sonst im Eingabefeld
    var rest = plaketten.querySelectorAll('button.favweg');
    (rest[Math.min(i, rest.length - 1)] || feld).focus();
  });
  zuerst.addEventListener('change', speichern);

  zeichnen();
})();
