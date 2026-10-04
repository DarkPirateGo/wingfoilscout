/* Der Sprachumschalter neben Logo und Version (seit 2.1.0): die Wahl geht an
   den Server (gemerkt in sprache.txt) und gilt ab der nächsten Seite und für
   den nächsten Report. Danach lädt die Seite neu, in der neuen Sprache. */
(function () {
  [].forEach.call(document.querySelectorAll('select.sprachwahl'), function (wahl) {
    wahl.addEventListener('change', function () {
      wahl.disabled = true;
      fetch('/sprache', {method: 'POST', body: new URLSearchParams({sprache: wahl.value})})
        .then(function (r) { if (r.ok) location.reload(); else wahl.disabled = false; })
        .catch(function () { wahl.disabled = false; });
    });
  });
})();
