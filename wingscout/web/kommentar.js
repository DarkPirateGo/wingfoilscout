
window.WSKommentar = (function () {
  var stand = {};
  function esc(v) {
    // Anführungszeichen als Hex-Escapes, damit jede Zeile dieses Skripts
    // eine gerade Zahl davon hat — so prüfen es die Tests der Seiten.
    return String(v == null ? '' : v).replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')
      .replace(/\x22/g, '&quot;').replace(/\x27/g, '&#39;');
  }
  function halt(e) { e.stopPropagation(); }
  function baue(box, id, text) {
    text = text || '';
    stand[id] = text;
    box.dataset.text = text;
    box.innerHTML = (text ? '<span class="kmt-text">' + esc(text) + '</span>' : '<span class="kmt-leer">' + t('kein Kommentar') + '</span>') +
      '<a href="#" class="kmt-edit">' + (text ? t('bearbeiten') : t('Kommentar schreiben')) + '</a>';
    box.querySelector('.kmt-edit').addEventListener('click', function (e) {
      e.preventDefault(); e.stopPropagation(); editor(box, id, text);
    });
  }
  function editor(box, id, text) {
    box.innerHTML = '<textarea maxlength="2000" placeholder="' + esc(t('Was man hier wissen muss — Parken, Einstieg, wie es war …')) + '"></textarea>' +
      '<div class="kmt-knoepfe"><button type="button" class="kmt-ok">' + t('Speichern') + '</button>' +
      '<button type="button" class="kmt-nein">' + t('Abbrechen') + '</button><span class="kmt-meld"></span></div>';
    var ta = box.querySelector('textarea'), ok = box.querySelector('.kmt-ok'), meld = box.querySelector('.kmt-meld');
    ta.value = text || '';
    ['click', 'mousedown', 'keydown', 'dblclick'].forEach(function (ev) { box.addEventListener(ev, halt); });
    ta.focus();
    box.querySelector('.kmt-nein').addEventListener('click', function () { baue(box, id, text); });
    ok.addEventListener('click', function () {
      var neu = ta.value.trim();
      ok.disabled = true; meld.textContent = '';
      fetch('/katalog/kommentar', {method: 'POST', headers: {'Content-Type': 'application/json'},
                                   body: JSON.stringify({id: id, comment: neu})})
        .then(function (r) { return r.json().then(function (j) { return {ok: r.ok, j: j}; }); })
        .then(function (res) {
          if (!res.ok || res.j.error) { meld.textContent = res.j.error || t('Fehlgeschlagen.'); ok.disabled = false; return; }
          document.dispatchEvent(new CustomEvent('kommentar', {detail: {id: id, comment: res.j.comment || ''} }));
        })
        .catch(function () {
          meld.textContent = t('Speichern geht nur in der Wingfoilscout-Oberfläche — hier ist der Report eine Datei ohne Programm dahinter.');
          ok.disabled = false;
        });
    });
  }
  function alle(root) {
    [].forEach.call((root || document).querySelectorAll('.kmt[data-id]'), function (box) {
      if (box.dataset.init) return;
      box.dataset.init = '1';
      var id = box.dataset.id;
      baue(box, id, stand[id] !== undefined ? stand[id] : (box.dataset.text || ''));
    });
  }
  document.addEventListener('kommentar', function (e) {
    var id = e.detail.id, text = e.detail.comment;
    stand[id] = text;
    [].forEach.call(document.querySelectorAll('.kmt[data-id]'), function (box) {
      if (box.dataset.id === id) baue(box, id, text);
    });
  });
  return {alle: alle, baue: baue, stand: stand, esc: esc};
})();
