#!/bin/bash
# Doppelklick-Start für das iPhone: wie „Wingfoilscout starten“, nur hört die
# Oberfläche zusätzlich im WLAN. Weil damit jedes Gerät im Netz anklopfen
# könnte, gilt ein Zugangsschlüssel — die Adresse mit Schlüssel steht nach dem
# Start hier im Fenster und in der Oberfläche unter „Datenquellen“.
# Das Fenster bleibt offen, solange die Oberfläche läuft — zum Beenden schließen.

cd "$(dirname "$0")" || exit 1
# Meldungen auf Deutsch, Englisch, Französisch oder Spanisch — welche, sagt
# tools/sprache.sh (`sag "Deutsch" "English" "Français" "Español"`). Fehlt die
# Datei, bleibt es beim Deutschen.
. tools/sprache.sh 2>/dev/null || sag() { printf '%s\n' "$1"; }
printf '\033c'
BOLD=$'\033[1m'; DIM=$'\033[2m'; OFF=$'\033[0m'
sag "${BOLD}Wingfoilscout${OFF} ${DIM}— Oberfläche wird gestartet, auch fürs iPhone im WLAN${OFF}" \
    "${BOLD}Wingfoilscout${OFF} ${DIM}— starting the interface, also for the iPhone over Wi-Fi${OFF}" \
    "${BOLD}Wingfoilscout${OFF} ${DIM}— démarrage de l'interface, aussi pour l'iPhone en Wi-Fi${OFF}" \
    "${BOLD}Wingfoilscout${OFF} ${DIM}— iniciando la interfaz, también para el iPhone por wifi${OFF}"
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
  sag "Auf dem Mac: 'brew install python' oder von python.org installieren." \
      "On a Mac: 'brew install python', or install it from python.org." \
      "Sur Mac : 'brew install python', ou installe-le depuis python.org." \
      "En Mac: 'brew install python', o instálalo desde python.org."
  pause_and_exit 1
fi

# Frischer Mac: /usr/bin/python3 ist nur ein Platzhalter, bis die
# Befehlszeilenwerkzeuge da sind — der erste Aufruf bietet ihre Installation
# an und scheitert. Dann nicht „zu alt“ melden, sondern sagen, was passiert (2.1.0).
if [ "$(uname)" = "Darwin" ] && [ "$(command -v python3)" = "/usr/bin/python3" ] \
   && ! xcode-select -p >/dev/null 2>&1; then
  sag "Python fehlt noch. macOS bietet gleich an, die Befehlszeilenwerkzeuge zu
installieren — die bringen Python mit. Auf „Installieren“ klicken, warten,
bis es fertig ist, und dann noch einmal doppelklicken." \
      "Python is still missing. macOS is about to offer to install the Command Line
Tools — they come with Python. Click “Install”, wait until it's done,
then double-click again." \
      "Il manque encore Python. macOS va te proposer d'installer les outils de ligne
de commande, qui contiennent Python. Clique sur « Installer », attends que
ce soit fini, puis double-clique à nouveau." \
      "Todavía falta Python. macOS te ofrecerá enseguida instalar las herramientas
de línea de comandos, que incluyen Python. Haz clic en «Instalar», espera a
que termine y vuelve a hacer doble clic."
  xcode-select --install >/dev/null 2>&1
  pause_and_exit 1
fi

# 3.9 ist das, was Apple mitliefert — deshalb ist das die Untergrenze, und
# deshalb steht in jeder Datei "from __future__ import annotations". Ohne das
# scheitert schon das Einlesen, mit einer Meldung, die nach einem
# Programmfehler aussieht statt nach einer alten Umgebung.
if ! python3 -c 'import sys; raise SystemExit(0 if sys.version_info >= (3, 9) else 1)'; then
  VERSION=$(python3 -c 'import sys; print(sys.version.split()[0])')
  sag "Python $VERSION ist zu alt." "Python $VERSION is too old." \
      "Python $VERSION est trop ancien." "Python $VERSION es demasiado antiguo."
  sag "Wingfoilscout braucht 3.9 oder neuer: 'brew install python' oder von python.org,
danach ein neues Terminalfenster öffnen." \
      "Wingfoilscout needs 3.9 or newer: 'brew install python' or from python.org,
then open a new terminal window." \
      "Wingfoilscout a besoin de la 3.9 ou plus récente : 'brew install python' ou
depuis python.org, puis ouvre une nouvelle fenêtre de terminal." \
      "Wingfoilscout necesita la 3.9 o posterior: 'brew install python' o desde
python.org, y luego abre una ventana nueva de terminal."
  pause_and_exit 1
fi

if ! python3 -c "import yaml" >/dev/null 2>&1; then
  sag "${DIM}PyYAML fehlt, wird installiert …${OFF}" "${DIM}PyYAML is missing, installing it…${OFF}" \
      "${DIM}Il manque PyYAML, installation en cours…${OFF}" "${DIM}Falta PyYAML, instalándolo…${OFF}"
  python3 -m pip install -q -r requirements.txt \
    || python3 -m pip install -q --user -r requirements.txt \
    || python3 -m pip install -q --break-system-packages -r requirements.txt
  if ! python3 -c "import yaml" >/dev/null 2>&1; then
    sag "Installation fehlgeschlagen. Von Hand: python3 -m pip install PyYAML" \
        "Installation failed. Install it by hand: python3 -m pip install PyYAML" \
        "L'installation a échoué. À la main : python3 -m pip install PyYAML" \
        "La instalación ha fallado. A mano: python3 -m pip install PyYAML"
    pause_and_exit 1
  fi
fi

if [ ! -f geometry.json ]; then
  sag "${DIM}Hinweis: Ohne Ufergeometrie fehlen Windlage und Wellenhöhe.
In der Oberfläche einmal 'Fehlende Ufergeometrie berechnen' drücken.${OFF}" \
      "${DIM}Note: without shoreline geometry, wind angle and wave height are missing.
Compute the missing shoreline geometry once in the interface.${OFF}" \
      "${DIM}Remarque : sans la géométrie du rivage, il manque l'orientation du vent
et la hauteur des vagues. Calcule-la une fois dans l'interface.${OFF}" \
      "${DIM}Nota: sin la geometría de la orilla faltan la orientación del viento y la
altura de las olas. Calcúlala una vez en la interfaz.${OFF}"
  echo
fi

python3 -m wingscout.webui --lan
STATUS=$?
if [ $STATUS -ne 0 ]; then
  echo
  sag "Die Oberfläche ist mit Code $STATUS beendet." "The interface exited with code $STATUS." \
      "L'interface s'est arrêtée avec le code $STATUS." "La interfaz terminó con el código $STATUS."
  pause_and_exit $STATUS
fi

# Sauberes Ende braucht keinen Tastendruck mehr — beendet wird jetzt über den
# Knopf in der Oberfläche, und dann soll hier nichts mehr im Weg stehen.
sag "${DIM}Dieses Fenster kannst du schließen.${OFF}" "${DIM}You can close this window.${OFF}" \
    "${DIM}Tu peux fermer cette fenêtre.${OFF}" "${DIM}Ya puedes cerrar esta ventana.${OFF}"
exit 0
