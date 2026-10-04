#!/bin/bash
# Doppelklick: der Prüfstand — stimmt Wingfoilscout noch? Braucht Netz, dauert
# beim ersten Mal ein paar Minuten (Messwerte und alte Vorhersagen werden
# geholt und danach behalten).

cd "$(dirname "$0")" || exit 1
# Meldungen in der Sprache aus tools/sprache.sh; fehlt die Datei, auf Deutsch.
. tools/sprache.sh 2>/dev/null || sag() { printf '%s\n' "$1"; }
printf '\033c'
BOLD=$'\033[1m'; DIM=$'\033[2m'; OFF=$'\033[0m'
sag "${BOLD}Wingfoilscout · Prüfstand${OFF}" "${BOLD}Wingfoilscout · Benchmark${OFF}" \
    "${BOLD}Wingfoilscout · Banc d'essai${OFF}" "${BOLD}Wingfoilscout · Banco de pruebas${OFF}"
sag "${DIM}Referenzspots, ein Punkt an Land, Vorhersage gegen Messung. Was geprüft wird: BENCHMARK.md${OFF}" \
    "${DIM}Reference spots, one point on land, forecast vs. measurement. What gets checked: BENCHMARK.md${OFF}" \
    "${DIM}Spots de référence, un point à terre, prévision contre mesure. Ce qui est vérifié : BENCHMARK.md${OFF}" \
    "${DIM}Spots de referencia, un punto en tierra, previsión frente a medición. Qué se comprueba: BENCHMARK.md${OFF}"
echo

pause_and_exit() {
  echo
  read -r -p "$(sag "Enter zum Schließen. " "Press Enter to close. " \
                    "Appuie sur Entrée pour fermer. " "Pulsa Enter para cerrar. ")" _
  exit "${1:-0}"
}

if ! command -v python3 >/dev/null 2>&1; then
  sag "Python 3 wurde nicht gefunden." "Python 3 was not found." \
      "Python 3 est introuvable." "No se encontró Python 3."
  pause_and_exit 1
fi
if ! python3 -c "import yaml" >/dev/null 2>&1; then
  python3 -m pip install -q -r requirements.txt || python3 -m pip install -q --user -r requirements.txt \
    || python3 -m pip install -q --break-system-packages -r requirements.txt
fi

python3 tools/pruefstand.py "$@"
STATUS=$?
echo
case $STATUS in
  0) sag "${BOLD}Alles in Ordnung.${OFF}" "${BOLD}All good.${OFF}" \
         "${BOLD}Tout est en ordre.${OFF}" "${BOLD}Todo en orden.${OFF}" ;;
  2) sag "Nichts prüfbar — kein Netz? Später noch einmal." \
         "Nothing to check — no network? Try again later." \
         "Rien à vérifier — pas de réseau ? Réessaie plus tard." \
         "Nada que comprobar: ¿no hay conexión? Vuelve a intentarlo más tarde." ;;
  *) sag "${BOLD}Mindestens ein Fehler.${OFF} Die Zeilen mit ✗ oben sagen, was." \
         "${BOLD}At least one check failed.${OFF} The lines marked ✗ above say which." \
         "${BOLD}Au moins une erreur.${OFF} Les lignes marquées ✗ ci-dessus disent laquelle." \
         "${BOLD}Al menos un fallo.${OFF} Las líneas marcadas con ✗ arriba dicen cuál." ;;
esac
pause_and_exit $STATUS
