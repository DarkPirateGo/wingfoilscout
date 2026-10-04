#!/bin/bash
# Doppelklick: prüft, schreibt fest und lädt auf GitHub hoch.
cd "$(dirname "$0")" || exit 1
printf '\033c'
BOLD=$'\033[1m'; DIM=$'\033[2m'; OFF=$'\033[0m'
echo "${BOLD}Wingfoilscout veröffentlichen${OFF} ${DIM}— Prüflauf, Commit, Push${OFF}"
echo
bash tools/veroeffentlichen.sh
status=$?
echo
read -r -p "Enter zum Schließen. " _
exit $status
