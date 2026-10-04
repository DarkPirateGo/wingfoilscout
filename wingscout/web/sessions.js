(function () {
  var tab = document.getElementById('sesstab'), alleLink = document.getElementById('sess_alle');
  if (!tab) return;
  var tbody = tab.querySelector('tbody'), koepfe = tab.querySelectorAll('th[data-k]');
  var zeilen = [].slice.call(tbody.querySelectorAll('tr'));
  // Je Spalte: welche Richtung der erste Klick nimmt. Zahlen, bei denen
  // „mehr" besser ist, absteigend; Ränge (Lage, Wasser) und Text aufsteigend.
  var erstAb = {dauer: true, wind: true, score: true, wing: false, lage: false, wasser: false, spot: false, wann: false, richtung: false};
  var numerisch = {dauer: true, wind: true, score: true, wing: true, lage: true, wasser: true};
  var aktiv = 'score', ab = true, alle = false;
  function wert(tr, spalte) {
    var td = tr.children[spalte];
    var v = td ? td.getAttribute('data-v') : '';
    return v == null ? '' : v;
  }
  function sortiere(k) {
    var spalte = -1;
    for (var i = 0; i < koepfe.length; i++) if (koepfe[i].getAttribute('data-k') === k) spalte = i;
    if (spalte < 0) return;
    var num = !!numerisch[k];
    zeilen.sort(function (a, b) {
      var x = wert(a, spalte), y = wert(b, spalte);
      if (num) { x = Number(x); y = Number(y); }
      var c = x < y ? -1 : (x > y ? 1 : 0);
      if (c === 0) { var sx = Number(wert(a, 8)), sy = Number(wert(b, 8)); c = sx < sy ? 1 : (sx > sy ? -1 : 0); }
      else if (ab) c = -c;
      return c;
    });
    zeilen.forEach(function (tr, i) { tbody.appendChild(tr); tr.classList.toggle('mehr', !alle && i >= 40); });
    [].forEach.call(koepfe, function (th) {
      th.classList.toggle('sort', th.getAttribute('data-k') === k);
      th.classList.toggle('auf', th.getAttribute('data-k') === k && !ab);
    });
  }
  [].forEach.call(koepfe, function (th) {
    th.addEventListener('click', function () {
      var k = th.getAttribute('data-k');
      if (k === aktiv) ab = !ab; else { aktiv = k; ab = !!erstAb[k]; }
      sortiere(aktiv);
    });
  });
  if (alleLink) alleLink.addEventListener('click', function (e) {
    e.preventDefault();
    alle = !alle;
    alleLink.textContent = alle ? t('nur die ersten 40 zeigen') : t('alle {n} zeigen', {n: zeilen.length});
    sortiere(aktiv);
  });
})();
