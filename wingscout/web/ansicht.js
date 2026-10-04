/* Zwei Ansichten des Reports (seit 1.20.0). „Einfach“: jedes Ziel zwei
   Zeilen, jeder Abschnitt nur seine Überschrift — die Antwort ohne den
   Apparat dahinter. „Ausführlich“: alle Ziele und Abschnitte offen, wie der
   Report bis 1.19.2 aussah. Die Wahl bleibt im Browser (localStorage), damit
   sie für jeden neuen Report gilt; jede Klappe lässt sich trotzdem einzeln
   öffnen und schließen. Ohne Skript gilt Einfach — <details> braucht keins.
   „Weitere Ziele“ bleibt in beiden Ansichten zu: 40 Karten auf einmal will
   niemand, auch ausführlich nicht. */
(function () {
  var SCHLUESSEL = 'wingscout:ansicht';
  var leiste = document.querySelector('.ansicht');
  if (!leiste) return;
  var knoepfe = [].slice.call(leiste.querySelectorAll('button[data-ansicht]'));

  function klappen() {
    return [].slice.call(document.querySelectorAll('details.trip, details.abschnitt:not(#weitere)'));
  }
  function setzen(name, merken) {
    var offen = name === 'ausfuehrlich';
    klappen().forEach(function (d) { d.open = offen; });
    knoepfe.forEach(function (b) { b.classList.toggle('an', b.dataset.ansicht === name); });
    if (merken) { try { localStorage.setItem(SCHLUESSEL, name); } catch (e) { /* privat, egal */ } }
  }
  knoepfe.forEach(function (b) {
    b.addEventListener('click', function () { setzen(b.dataset.ansicht, true); });
  });
  var gemerkt = null;
  try { gemerkt = localStorage.getItem(SCHLUESSEL); } catch (e) { /* file:// ohne Speicher */ }
  if (gemerkt === 'ausfuehrlich') setzen('ausfuehrlich', false);
})();
