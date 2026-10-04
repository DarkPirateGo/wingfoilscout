#!/bin/bash
# Doppelklick: holt den Stand von GitHub, ohne eigene Arbeit zu verlieren.
cd "$(dirname "$0")" || exit 1
# Meldungen in der Sprache aus tools/sprache.sh; fehlt die Datei, auf Deutsch.
. tools/sprache.sh 2>/dev/null || sag() { printf '%s\n' "$1"; }
printf '\033c'
BOLD=$'\033[1m'; DIM=$'\033[2m'; OFF=$'\033[0m'
sag "${BOLD}Wingfoilscout aktualisieren${OFF} ${DIM}— holen, zusammenführen, prüfen${OFF}" \
    "${BOLD}Update Wingfoilscout${OFF} ${DIM}— fetch, merge, check${OFF}" \
    "${BOLD}Mettre à jour Wingfoilscout${OFF} ${DIM}— récupérer, fusionner, vérifier${OFF}" \
    "${BOLD}Actualizar Wingfoilscout${OFF} ${DIM}— descargar, fusionar, comprobar${OFF}"
echo
bash tools/aktualisieren.sh
status=$?
echo
read -r -p "$(sag "Enter zum Schließen. " "Press Enter to close. " \
                  "Appuie sur Entrée pour fermer. " "Pulsa Enter para cerrar. ")" _
exit $status
