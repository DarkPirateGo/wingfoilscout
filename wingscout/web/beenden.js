
/* Beenden: der Knopf oben rechts in der Reiterleiste, auf jeder Seite (seit
   1.18.2 — vorher unten im Suchformular, also auf keinem anderen Reiter zu
   sehen). Zwei Klicks, damit er nicht aus Versehen mitten in einem Lauf
   auslöst; danach POST /shutdown, und die Seite sagt, dass Wingfoilscout aus ist.
   Im eingebetteten Report gibt es den Knopf nicht (die Leiste nimmt sich dort
   selbst heraus), dann tut das Skript nichts. */
(function () {
  var knopf = document.getElementById('quit');
  if (!knopf || knopf.dataset.init) return;
  knopf.dataset.init = '1';
  var scharf = false, uhr = null;
  function entschaerfen() { scharf = false; knopf.classList.remove('armed'); knopf.textContent = t('Beenden'); }
  knopf.addEventListener('click', function () {
    if (!scharf) {
      scharf = true; knopf.classList.add('armed'); knopf.textContent = t('Wirklich beenden?');
      uhr = setTimeout(entschaerfen, 5000);
      return;
    }
    clearTimeout(uhr);
    knopf.disabled = true; knopf.textContent = t('Beendet');
    // Die Suchseite fragt den Stand im Takt ab; nach dem Ende gäbe das nur Fehlermeldungen.
    if (window.timer) { clearInterval(window.timer); window.timer = null; }
    fetch('/shutdown', {method: 'POST'}).catch(function () {});
    setTimeout(function () {
      document.body.innerHTML = '<div class="wrap"><h1>' + t('Wingfoilscout ist beendet.') + '</h1>' +
        '<p class="sub">' + t('Das Terminalfenster hat sich mitbeendet, dieses Browserfenster kannst du schließen. Zum Weitermachen wieder auf „Wingfoilscout starten“ doppelklicken.') + '</p></div>';
    }, 400);
  });
})();
