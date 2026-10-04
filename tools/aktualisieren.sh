#!/usr/bin/env bash
# Neuen Stand von GitHub holen, ohne eigene Arbeit zu verlieren.
#
# Die Reihenfolge ist der ganze Trick:
#   1. eigene unfertige Änderungen beiseitelegen (git stash)
#   2. holen und die eigenen Commits oben draufsetzen (rebase)
#   3. Beiseitegelegtes zurückholen
#   4. Prüflauf — erst danach gilt der neue Stand als gut
# Geht Schritt 2 oder 4 schief, steht am Ende, wie man zurückkommt. Es wird
# nichts weggeworfen: jeder Zwischenstand bleibt im Stash oder im Reflog.
set -euo pipefail
cd "$(dirname "$0")/.."

rot=$'\e[31m'; gruen=$'\e[32m'; gelb=$'\e[33m'; dim=$'\e[2m'; fett=$'\e[1m'; aus=$'\e[0m'
meckern() { echo "${rot}$1${aus}"; exit 1; }

git rev-parse --git-dir >/dev/null 2>&1 || meckern "Das hier ist kein Git-Repository."
vorher="$(git rev-parse HEAD)"
zweig="$(git rev-parse --abbrev-ref HEAD)"

# ── 1. Eigenes beiseite ──────────────────────────────────────────────────────
beiseite=0
if [ -n "$(git status --porcelain)" ]; then
  echo "${dim}Lege eigene, noch nicht festgeschriebene Änderungen beiseite …${aus}"
  git status --short
  git stash push -u -m "vor dem Aktualisieren $(date '+%d.%m. %H:%M')" >/dev/null
  beiseite=1
fi

# ── 2. Holen ─────────────────────────────────────────────────────────────────
echo "${fett}Hole den Stand von GitHub …${aus}"
git fetch origin
neu="$(git log "HEAD..origin/$zweig" --oneline | wc -l | tr -d ' ')"
if [ "$neu" = "0" ]; then
  echo "${gruen}Schon aktuell.${aus}"
else
  echo "${fett}$neu neue Commits:${aus}"
  git log "HEAD..origin/$zweig" --pretty='  %h %an: %s'
  echo
  if ! git rebase "origin/$zweig"; then
    echo
    echo "${gelb}Konflikt.${aus} Zwei Fassungen derselben Stelle — das muss ein Mensch entscheiden."
    echo "Betroffen:"; git diff --name-only --diff-filter=U | sed 's/^/  /'
    echo
    echo "Weiter:   Datei bearbeiten, dann  git add <datei>  und  git rebase --continue"
    echo "Zurück:   git rebase --abort      (danach ist alles wie vorher)"
    [ "$beiseite" = "1" ] && echo "${gelb}Achtung:${aus} Beiseitegelegtes liegt noch im Stash — nach dem Rebase: git stash pop"
    exit 1
  fi
fi

# ── 3. Eigenes zurück ────────────────────────────────────────────────────────
if [ "$beiseite" = "1" ]; then
  echo "${dim}Hole Beiseitegelegtes zurück …${aus}"
  if ! git stash pop; then
    echo "${gelb}Das Zurückholen kollidiert mit dem neuen Stand.${aus}"
    echo "Die betroffenen Stellen von Hand zusammenführen, dann  git stash drop"
    exit 1
  fi
fi

# ── 4. Prüflauf ──────────────────────────────────────────────────────────────
echo "${fett}Prüflauf auf dem neuen Stand …${aus}"
if bash tools/check.sh; then
  echo "${gruen}Aktualisiert, alles grün.${aus}"
else
  echo
  echo "${rot}Der neue Stand besteht die Tests nicht.${aus}"
  echo "Damit ist etwas kaputtgegangen — nicht bei dir, sondern im geholten Stand."
  echo "Zurück auf den Stand von vorhin:"
  echo "    git reset --hard $vorher"
  echo "Und dem anderen Bescheid geben, was der Prüflauf meldet."
  exit 1
fi

# ── 5. Was folgt daraus? ─────────────────────────────────────────────────────
if [ -n "$(git log "origin/$zweig..HEAD" --oneline 2>/dev/null)" ]; then
  echo "${dim}Du hast eigene Commits, die noch nicht oben sind — tools/veroeffentlichen.sh${aus}"
fi
