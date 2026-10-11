#!/bin/bash
# Baut die App „Wingfoilscout“ fürs Dock (seit 2.5.0) — aufgerufen vom
# Doppelklick „App fürs Dock erstellen“. Gewünscht am 10.10.2026: „eine schöne
# Verknüpfung mit Logo“.
#
# Die App ist ein kleines AppleScript-Programm (osacompile), das nur
# tools/app_start.sh in diesem Ordner startet; alles Weitere tut die
# Oberfläche wie immer. Warum AppleScript und kein Shell-Skript im Bündel:
# Ein Skript als Programmdatei hält macOS auf Apple-Silicon-Macs für ein
# Intel-Programm und will Rosetta installieren. Das Applet von osacompile
# läuft auf beiden.
#
# Gebaut wird sie hier, auf dem Mac, und nicht im Repository: Sie enthält den
# Pfad zu diesem Ordner, und ein selbst gebautes Programm trägt keine
# Quarantäne — macOS öffnet es ohne Rückfrage. Liegt der Ordner später
# woanders, sagt die App das und bittet, sie neu zu bauen.
#
# Das Symbol: tools/mac-app/Wingfoilscout.icns (Quelle: symbol.svg daneben).
# osacompile legt ein eigenes Symbol als Asset-Katalog an (Assets.car,
# CFBundleIconName) — der geht vor, also fliegt er raus. Danach neu
# signieren (ad hoc), denn jede Änderung im Bündel bricht die Signatur, und
# ohne gültige Signatur startet auf Apple Silicon gar nichts.

set -euo pipefail
cd "$(dirname "$0")/.."
PROJEKT=$(pwd -P)
. tools/sprache.sh 2>/dev/null || sag() { printf '%s\n' "$1"; }

KENNUNG="io.github.darkpiratego.wingfoilscout.dock"
ZIEL_ORDNER="$HOME/Applications"
APP="$ZIEL_ORDNER/Wingfoilscout.app"

if [ "$(uname)" != "Darwin" ] || ! command -v osacompile >/dev/null 2>&1; then
  sag "Die App fürs Dock gibt es nur auf dem Mac." "The Dock app only exists on a Mac." \
      "L'app pour le Dock n'existe que sur Mac." "La app para el Dock solo existe en Mac."
  exit 1
fi

# Ein Wingfoilscout.app, das nicht von hier stammt, bleibt unangetastet
if [ -e "$APP" ]; then
  alt=$(/usr/libexec/PlistBuddy -c "Print :CFBundleIdentifier" "$APP/Contents/Info.plist" 2>/dev/null || true)
  if [ "$alt" != "$KENNUNG" ]; then
    sag "In $ZIEL_ORDNER gibt es schon ein anderes „Wingfoilscout“ — bitte erst umbenennen oder löschen." \
        "There is already a different “Wingfoilscout” in $ZIEL_ORDNER — please rename or delete it first." \
        "Il y a déjà un autre « Wingfoilscout » dans $ZIEL_ORDNER — renomme-le ou supprime-le d'abord." \
        "Ya hay otro «Wingfoilscout» en $ZIEL_ORDNER — cámbiale el nombre o bórralo primero."
    exit 1
  fi
fi

# Text für AppleScript: Backslash und Anführungszeichen schützen
als_text() {
  local s=${1//\\/\\\\}
  printf '%s' "${s//\"/\\\"}"
}
STARTER="$PROJEKT/tools/app_start.sh"
FEHLT=$(sag "Der Wingfoilscout-Ordner ist nicht mehr da, wo er war ($PROJEKT). Wurde er verschoben? Dann am neuen Ort noch einmal „App fürs Dock erstellen“ doppelklicken." \
            "The Wingfoilscout folder is no longer where it was ($PROJEKT). Was it moved? Then double-click “App fürs Dock erstellen” again in its new place." \
            "Le dossier Wingfoilscout n'est plus là où il était ($PROJEKT). A-t-il été déplacé ? Double-clique alors à nouveau sur « App fürs Dock erstellen » à son nouvel emplacement." \
            "La carpeta de Wingfoilscout ya no está donde estaba ($PROJEKT). ¿La has movido? Entonces vuelve a hacer doble clic en «App fürs Dock erstellen» en su nuevo sitio.")

TMP=$(mktemp -d "${TMPDIR:-/tmp}/wingfoilscout-app.XXXXXX")
trap 'rm -rf "$TMP"' EXIT
NEU="$TMP/Wingfoilscout.app"

# Die Zeilen einzeln mit -e: so liest osacompile sie sicher als UTF-8
osacompile -o "$NEU" \
  -e "set starter to \"$(als_text "$STARTER")\"" \
  -e 'try' \
  -e 'do shell script "test -f " & quoted form of starter' \
  -e 'on error' \
  -e "display alert \"Wingfoilscout\" message \"$(als_text "$FEHLT")\" as warning" \
  -e 'return' \
  -e 'end try' \
  -e 'do shell script "/bin/bash " & quoted form of starter & " > /dev/null 2>&1 &"'

RES="$NEU/Contents/Resources"
PLIST="$NEU/Contents/Info.plist"
cp tools/mac-app/Wingfoilscout.icns "$RES/applet.icns"
rm -f "$RES/Assets.car"
/usr/libexec/PlistBuddy -c "Delete :CFBundleIconName" "$PLIST" >/dev/null 2>&1 || true
/usr/libexec/PlistBuddy -c "Set :CFBundleIdentifier $KENNUNG" "$PLIST" >/dev/null 2>&1 \
  || /usr/libexec/PlistBuddy -c "Add :CFBundleIdentifier string $KENNUNG" "$PLIST"
/usr/libexec/PlistBuddy -c "Set :CFBundleName Wingfoilscout" "$PLIST" >/dev/null 2>&1 || true
codesign --force --sign - "$NEU" >/dev/null

mkdir -p "$ZIEL_ORDNER"
rm -rf "$APP"
mv "$NEU" "$APP"
touch "$APP"          # damit Finder und Dock das neue Symbol zeigen
open -R "$APP"

sag "Fertig: Die App „Wingfoilscout“ liegt in $ZIEL_ORDNER und ist im Finder markiert.
Zieh sie ins Dock — ein Klick startet Wingfoilscout und öffnet den Browser.
Beenden wie immer oben rechts in der Oberfläche mit „Beenden“." \
    "Done: the “Wingfoilscout” app is in $ZIEL_ORDNER and selected in the Finder.
Drag it to the Dock — one click starts Wingfoilscout and opens the browser.
Quit as always with “Quit” at the top right of the interface." \
    "C'est fait : l'app « Wingfoilscout » se trouve dans $ZIEL_ORDNER et est sélectionnée dans le Finder.
Glisse-la dans le Dock — un clic lance Wingfoilscout et ouvre le navigateur.
Pour quitter, comme d'habitude : « Quitter » en haut à droite de l'interface." \
    "Listo: la app «Wingfoilscout» está en $ZIEL_ORDNER y seleccionada en el Finder.
Arrástrala al Dock — un clic inicia Wingfoilscout y abre el navegador.
Para salir, como siempre: «Salir» arriba a la derecha de la interfaz."
