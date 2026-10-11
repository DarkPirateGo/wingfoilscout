#!/bin/bash
# Doppelklick (seit 2.5.0): baut die App „Wingfoilscout“ mit eigenem Symbol
# und legt sie in den Ordner „Programme“ im Benutzerordner (~/Applications).
# Von dort ins Dock ziehen — ein Klick startet dann Wingfoilscout ohne
# Terminalfenster und öffnet den Browser. Wie, steht in tools/mac_app.sh.
# Einmal genügt; neu bauen nur, wenn der Wingfoilscout-Ordner umzieht.

cd "$(dirname "$0")" || exit 1
. tools/sprache.sh 2>/dev/null || sag() { printf '%s\n' "$1"; }
printf '\033c'
BOLD=$'\033[1m'; DIM=$'\033[2m'; OFF=$'\033[0m'
sag "${BOLD}Wingfoilscout${OFF} ${DIM}— App fürs Dock wird gebaut${OFF}" \
    "${BOLD}Wingfoilscout${OFF} ${DIM}— building the Dock app${OFF}" \
    "${BOLD}Wingfoilscout${OFF} ${DIM}— création de l'app pour le Dock${OFF}" \
    "${BOLD}Wingfoilscout${OFF} ${DIM}— creando la app para el Dock${OFF}"
echo

bash tools/mac_app.sh
STATUS=$?
echo
if [ $STATUS -ne 0 ]; then
  sag "Das hat nicht geklappt (Code $STATUS)." "That didn't work (code $STATUS)." \
      "Ça n'a pas marché (code $STATUS)." "No ha funcionado (código $STATUS)."
fi
read -r -p "$(sag "Enter zum Schließen. " "Press Enter to close. " \
                  "Appuie sur Entrée pour fermer. " "Pulsa Enter para cerrar. ")" _
exit $STATUS
