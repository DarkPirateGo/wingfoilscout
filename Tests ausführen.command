#!/usr/bin/env bash
# Doppelklick: kompletter Prüflauf mit allen Tests, Fenster bleibt danach offen.
cd "$(dirname "$0")" || exit 1
# Meldungen in der Sprache aus tools/sprache.sh; fehlt die Datei, auf Deutsch.
. tools/sprache.sh 2>/dev/null || sag() { printf '%s\n' "$1"; }
# Mit "bash" davor: das Ausführbar-Bit von check.sh geht auf dem Mac leicht verloren.
bash tools/check.sh
STATUS=$?
echo
read -r -p "$(sag "Enter zum Schließen. " "Press Enter to close. " \
                  "Appuie sur Entrée pour fermer. " "Pulsa Enter para cerrar. ")" _
exit $STATUS
