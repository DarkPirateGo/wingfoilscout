#!/bin/bash
# Einmaliger Lauf: holt die Wassergeometrie aus OpenStreetMap und misst je Spot
# die Anlauflänge in 36 Richtungen. Danach braucht das Tool dafür kein Netz mehr.

cd "$(dirname "$0")" || exit 1
# Meldungen in der Sprache aus tools/sprache.sh; fehlt die Datei, auf Deutsch.
. tools/sprache.sh 2>/dev/null || sag() { printf '%s\n' "$1"; }
printf '\033c'

BOLD=$'\033[1m'; DIM=$'\033[2m'; OFF=$'\033[0m'
sag "${BOLD}Ufergeometrie berechnen${OFF}" "${BOLD}Compute shoreline geometry${OFF}" \
    "${BOLD}Calculer la géométrie du rivage${OFF}" "${BOLD}Calcular la geometría de la orilla${OFF}"
echo
sag "Holt für jeden Spot die Küstenlinien und Wasserflächen aus OpenStreetMap
und misst, wie weit der Wind aus jeder Richtung über Wasser anläuft." \
    "Fetches the coastlines and water areas for every spot from OpenStreetMap
and measures how far the wind blows over water from each direction." \
    "Récupère pour chaque spot les côtes et les plans d'eau dans OpenStreetMap
et mesure, pour chaque direction, la distance que le vent parcourt sur l'eau." \
    "Descarga de OpenStreetMap las líneas de costa y masas de agua de cada spot
y mide, para cada dirección, cuánto recorre el viento sobre el agua."
echo
sag "${DIM}Dauert beim ersten Mal 10–30 Minuten, größtenteils Wartezeit gegenüber
den Overpass-Servern. Jeder Spot wird sofort gespeichert — abbrechen ist
harmlos, beim nächsten Start geht es weiter.${OFF}" \
    "${DIM}Takes 10–30 minutes the first time, mostly waiting for the Overpass
servers. Each spot is saved right away — stopping is harmless, the next run
picks up where this one left off.${OFF}" \
    "${DIM}La première fois, ça prend 10 à 30 minutes, surtout à attendre les
serveurs Overpass. Chaque spot est enregistré tout de suite : tu peux arrêter
sans souci, le prochain lancement reprendra là où il s'est arrêté.${OFF}" \
    "${DIM}La primera vez tarda 10–30 minutos, sobre todo esperando a los
servidores de Overpass. Cada spot se guarda al momento: puedes interrumpirlo
sin problema, la próxima vez seguirá donde se quedó.${OFF}"
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
  sag "${DIM}PyYAML fehlt, wird installiert …${OFF}" "${DIM}PyYAML is missing, installing it…${OFF}" \
      "${DIM}Il manque PyYAML, installation en cours…${OFF}" "${DIM}Falta PyYAML, instalándolo…${OFF}"
  python3 -m pip install -q -r requirements.txt \
    || python3 -m pip install -q --user -r requirements.txt \
    || python3 -m pip install -q --break-system-packages -r requirements.txt
fi

if [ -f geometry.json ]; then
  sag "Es gibt bereits eine geometry.json — fehlende Spots werden ergänzt." \
      "There's already a geometry.json — missing spots will be added." \
      "Il y a déjà un geometry.json : les spots manquants seront ajoutés." \
      "Ya hay un geometry.json: se añadirán los spots que falten."
  read -r -p "$(sag "Alles neu berechnen? (j/N) " "Recompute everything? (y/N) " \
                    "Tout recalculer ? (o/N) " "¿Recalcularlo todo? (s/N) ")" AGAIN
  # Ja heißt j oder y — und o (oui) bzw. s (sí), wie es die Frage anbietet.
  case "$AGAIN" in [jJyYoOsS]*) FORCE="--force" ;; *) FORCE="" ;; esac
  echo
fi

read -r -p "$(sag "Jetzt starten? (J/n) " "Start now? (Y/n) " \
                  "On y va ? (O/n) " "¿Empezamos? (S/n) ")" GO
case "$GO" in [nN]*) pause_and_exit 0 ;; esac
echo

python3 build_geometry.py $FORCE
STATUS=$?

echo
if [ $STATUS -eq 0 ]; then
  sag "${BOLD}Fertig.${OFF} Ab jetzt rechnet der Report Windlage und Wellenhöhe selbst." \
      "${BOLD}Done.${OFF} From now on the report works out wind angle and wave height itself." \
      "${BOLD}Terminé.${OFF} Désormais, le rapport calcule lui-même l'orientation du vent
et la hauteur des vagues." \
      "${BOLD}Listo.${OFF} A partir de ahora, el informe calcula por sí mismo la orientación
del viento y la altura de las olas."
else
  sag "Abgebrochen oder unvollständig (Code $STATUS)." "Stopped or incomplete (code $STATUS)." \
      "Interrompu ou incomplet (code $STATUS)." "Interrumpido o incompleto (código $STATUS)."
  sag "Nochmal starten macht dort weiter, wo es aufgehört hat." \
      "Running it again picks up where it left off." \
      "Relance-le : il reprendra là où il s'est arrêté." \
      "Si lo vuelves a iniciar, seguirá donde se quedó."
fi
pause_and_exit $STATUS
