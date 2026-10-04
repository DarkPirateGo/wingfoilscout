#!/usr/bin/env bash
# Prüflauf vor jedem Commit: kompiliert, testet, schaut nach Altlasten.
# Aufruf:  tools/check.sh          (aus dem Projektordner)
#          tools/check.sh --schnell   nur Syntax und die schnellen Tests
set -euo pipefail
cd "$(dirname "$0")/.."

rot=$'\e[31m'; gruen=$'\e[32m'; dim=$'\e[2m'; aus=$'\e[0m'
fehler=0

# Python-Version zuerst: zu alte Fassungen scheitern nicht an einem Test,
# sondern schon beim Einlesen einer Datei — und melden dann einen Fehler, der
# nach einem kaputten Test aussieht statt nach einer alten Umgebung.
python3 - <<'VERSION' || { echo "${rot}Prüflauf abgebrochen.${aus}"; exit 1; }
import sys
if sys.version_info < (3, 9):
    print(f"   Python {sys.version.split()[0]} ist zu alt — Wingfoilscout braucht 3.9 oder neuer.")
    print("   Abhilfe: 'brew install python' oder von python.org, danach ein neues")
    print("   Terminalfenster öffnen.")
    raise SystemExit(1)
VERSION

echo "${dim}1/5 Syntax${aus}"
python3 -m py_compile wingscout/*.py wingscout/sources/*.py build_geometry.py run.py tests/*.py tools/*.py import/*.py
# Das JavaScript der Oberfläche (wingscout/web/) — mit Node, wenn es da ist
if command -v node >/dev/null 2>&1; then
  for js in wingscout/web/*.js; do node --check "$js" || fehler=1; done
fi

echo "${dim}2/5 Linter${aus}"
# ruff mit den Regeln aus pyproject.toml. Ist er nicht installiert, nur ein
# Hinweis — ein frischer Mac soll am Prüflauf nicht scheitern.
if command -v ruff >/dev/null 2>&1; then
  ruff check --quiet . || fehler=1
elif python3 -m ruff --version >/dev/null 2>&1; then
  python3 -m ruff check --quiet . || fehler=1
else
  echo "   ruff nicht installiert — übersprungen (einmalig: brew install ruff,"
  echo "   sonst pipx install ruff; 'pip install' lehnt Homebrews Python ab, PEP 668)"
fi

echo "${dim}3/5 Tests${aus}"
# Der Testlauf steht ausdrücklich als Bedingung im if: unter `set -e` und
# `pipefail` beendete ein roter Test sonst das ganze Skript an Ort und Stelle —
# ohne Schritt 4 und 5 und ohne Schlusszeile. (Bis 2.1.0 stand dafür eine
# PIPESTATUS-Abfrage hinter dem Lauf, die deshalb nie zum Zug kam.)
muster="test*.py"
if [ "${1:-}" = "--schnell" ]; then muster="test_[gics]*.py"; fi
ausgabe="$(mktemp "${TMPDIR:-/tmp}/wingfoilscout-tests.XXXXXX")"
trap 'rm -f "$ausgabe"' EXIT
if python3 -m unittest discover -s tests -t . -p "$muster" >"$ausgabe" 2>&1; then
  tail -3 "$ausgabe"
else
  grep -E "^(FAIL|ERROR):" "$ausgabe" | sed 's/^/   /' || true    # welche Tests, nicht nur wie viele
  tail -3 "$ausgabe"
  fehler=1
fi

echo "${dim}4/5 Katalog${aus}"
python3 - <<'PY' || fehler=1
import sys; sys.path.insert(0, ".")
from wingscout.spots import load_spots
from wingscout.config import load_config
spots = load_spots("spots.yaml"); load_config("config.example.yaml")
print(f"   {len(spots)} Spots, Konfiguration liest sauber")
PY

echo "${dim}5/5 Altlasten${aus}"
if grep -rn "print(" wingscout/*.py wingscout/sources/*.py | grep -v "^wingscout/webui.py" | grep -v "file=sys.stderr" >/dev/null; then
  echo "   ${rot}print() außerhalb der Oberfläche — bitte über log() melden${aus}"; fehler=1
fi
# Was im nächsten Commit steht (im Pre-Commit-Hook: genau dieser Commit):
# keine persönliche Datei und nicht die eigene Heimatkoordinate. Dieselbe
# Liste wie in tools/veroeffentlichen.sh und im Prüflauf auf GitHub. Namen mit
# -z: sonst setzt Git einen Namen wie  takeout/Saved "Places".json  in
# Anführungszeichen, und das Muster greift nicht. Die Vorsilben a/ und b/
# ausdrücklich: mit diff.noprefix oder diff.mnemonicPrefix in der eigenen
# Git-Einstellung fehlen sie, und die Suche nach der Heimatkoordinate
# übersprang jede Datei (Nachprüfung 04.10.2026).
if git rev-parse --git-dir >/dev/null 2>&1; then
  verboten="$(git diff --cached --name-only -z --no-renames --diff-filter=ACMRT \
              | tr '\n\000' ' \n' | python3 tools/persoenliche_daten.py dateien --mit-grund)" && status=0 || status=$?
  if [ "$status" = 1 ]; then
    echo "   ${rot}Persönliche Dateien im Commit — sie gehören nie ins Repository:${aus}"
    printf '%s\n' "$verboten" | sed 's/^/     /'
    fehler=1
  elif [ "$status" != 0 ]; then
    echo "   ${rot}Die Prüfung auf persönliche Dateien ist gescheitert (siehe oben)${aus}"; fehler=1
  fi
  git -c core.quotepath=off diff --cached --no-color --no-ext-diff --no-textconv --no-renames -U0 \
      --src-prefix=a/ --dst-prefix=b/ \
    | python3 tools/persoenliche_daten.py heimat || fehler=1
fi
[ $fehler -eq 0 ] && echo "   nichts gefunden"

if [ $fehler -eq 0 ]; then echo "${gruen}Alles grün.${aus}"; else echo "${rot}Prüflauf fehlgeschlagen.${aus}"; fi
exit $fehler
