#!/bin/bash
# Was die App „Wingfoilscout“ im Dock bei einem Klick tut (seit 2.5.0): die
# Oberfläche im Hintergrund starten, ohne Terminalfenster — sie öffnet dann
# selbst den Browser. Läuft sie schon, öffnet sie nur den Browser
# (port_klaeren in wingscout/webui.py). Beendet wird wie immer über
# „Beenden“ oben rechts in der Oberfläche. Gebaut wird die App von
# tools/mac_app.sh („App fürs Dock erstellen“), sie ruft nur dieses Skript auf.
#
# Eine App bekommt von macOS eine schmale Umgebung (PATH=/usr/bin:/bin:…):
# python3 aus Homebrew oder von python.org stünde da nicht im Pfad. Deshalb
# wird er hier gesucht — zuerst so, wie ihn das Terminal findet, dann an den
# üblichen Orten. Fehlt etwas (Python, PyYAML) oder scheitert der Start, über-
# nimmt der gewohnte Starter im Terminal: er sagt, was fehlt, und richtet
# PyYAML ein.
#
# Nie mit --lan: Fürs Handy freigegeben wird nur im Reiter „Handy“, mit
# Absicht und für diesen einen Lauf.

cd "$(dirname "$0")/.." || exit 1

# Python 3.9 oder neuer, mit PyYAML?
passt() {
  [ -n "$1" ] && [ -x "$1" ] \
    && "$1" -c 'import sys, yaml; raise SystemExit(0 if sys.version_info >= (3, 9) else 1)' >/dev/null 2>&1
}

# /usr/bin/python3 ist auf einem frischen Mac nur ein Platzhalter, bis die
# Befehlszeilenwerkzeuge da sind — ein Aufruf öffnete dann deren Installation.
echt() {
  [ "$1" != "/usr/bin/python3" ] || xcode-select -p >/dev/null 2>&1
}

PY=""
for kandidat in \
    "$(/bin/zsh -lc 'command -v python3' 2>/dev/null)" \
    "$(/bin/bash -lc 'command -v python3' 2>/dev/null)" \
    /opt/homebrew/bin/python3 \
    /usr/local/bin/python3 \
    /Library/Frameworks/Python.framework/Versions/Current/bin/python3 \
    /usr/bin/python3; do
  if echt "$kandidat" && passt "$kandidat"; then
    PY=$kandidat
    break
  fi
done

if [ -z "$PY" ]; then
  open "Wingfoilscout starten.command"
  exit 0
fi

mkdir -p cache
nohup "$PY" -m wingscout.webui >cache/oberflaeche.log 2>&1 </dev/null &
pid=$!
# Steht die Oberfläche nach ein paar Sekunden noch, läuft sie. Ist sie schon
# beendet: mit 0, weil sie bereits lief und nur den Browser geöffnet hat —
# sonst ist etwas schiefgegangen, und der Starter im Terminal zeigt, was.
sleep 4
if ! kill -0 "$pid" 2>/dev/null; then
  if ! wait "$pid"; then
    open "Wingfoilscout starten.command"
  fi
fi
exit 0
