# shellcheck shell=bash
# Sprache der Terminal-Meldungen in den Doppelklick-Skripten (seit 2.1.0):
# Deutsch, Englisch, Französisch oder Spanisch — wie die Oberfläche. Die
# Skripte lesen diese Datei ein (ausgeführt wird sie nicht):
#
#   . tools/sprache.sh 2>/dev/null || sag() { printf '%s\n' "$1"; }
#
# Fehlt sie, bleibt es beim Deutschen wie bisher. Danach steht die Sprache in
# $SPRACHE (de, en, fr oder es), und
#
#   sag "Deutsch" "English" "Français" "Español"
#
# gibt die Meldung in dieser Sprache aus, mit Zeilenende wie echo. Sie darf
# über mehrere Zeilen gehen; fehlt eine Übersetzung, gilt die englische, sonst
# die deutsche. Für read -p ohne Zeilenende: read -r -p "$(sag "Weiter? " …)" x
#
# Welche Sprache gilt — die erste, die passt:
#   1. die im Umschalter der Oberfläche gewählte: sprache.txt neben den
#      Skripten (SPRACH_DATEI in wingscout/i18n.py). Nur WINGSCOUT_SPRACHE
#      schlägt sie, wie in Python — die Tests setzen sie auf de.
#   2. die erste der vier unter den bevorzugten Sprachen von macOS
#      (Systemeinstellungen → Allgemein → Sprache & Region)
#   3. LC_ALL, LC_MESSAGES, LANG
#   4. Englisch
# Exportiert wird nichts: python3 -m wingscout.webui wählt seine Sprache selbst.
#
# Bash 3.2, die von macOS: keine assoziativen Arrays, kein ${x,,}.

# Genau de/en/fr/es, groß oder klein → $SPRACHE; alles andere zählt nicht.
_sprache_nimm() {
  case $1 in
    [Dd][Ee]) SPRACHE=de ;;
    [Ee][Nn]) SPRACHE=en ;;
    [Ff][Rr]) SPRACHE=fr ;;
    [Ee][Ss]) SPRACHE=es ;;
    *) return 1 ;;
  esac
}

# Die Sprache vorn in „de-DE“, „    "fr-CA",“ oder „es_ES.UTF-8“.
_sprache_vorne() {
  local wert=$1
  wert=${wert#"${wert%%[[:alpha:]]*}"}      # alles vor dem ersten Buchstaben weg
  _sprache_nimm "${wert%%[![:alpha:]]*}"    # nur die Buchstaben bis dahin: de-DE → de
}

_sprache_ermitteln() {
  local wert zeile
  SPRACHE=
  # 1. Festgelegt oder im Umschalter gewählt (die App schreibt „en“ und ein Zeilenende)
  wert=${WINGSCOUT_SPRACHE:-}
  _sprache_nimm "${wert//[[:space:]]/}" && return 0
  if [ -r "$_sprache_datei" ]; then
    wert=$(< "$_sprache_datei")
    _sprache_nimm "${wert//[[:space:]]/}" && return 0
  fi
  # 2. macOS. Die Ausgabe ist eine Liste wie
  #      (
  #          "de-DE",
  #          en
  #      )
  #    — Kürzel ohne Bindestrich stehen ohne Anführungszeichen da.
  case ${OSTYPE:-} in
    darwin*)
      while IFS= read -r zeile; do
        _sprache_vorne "$zeile" && return 0
      done <<< "$(defaults read -g AppleLanguages 2>/dev/null)"
      ;;
  esac
  # 3. Die Umgebung des Terminals, 4. sonst Englisch
  _sprache_vorne "${LC_ALL:-}" || _sprache_vorne "${LC_MESSAGES:-}" \
    || _sprache_vorne "${LANG:-}" || SPRACHE=en
}

# sprache.txt liegt neben den Skripten, eine Ebene über dieser Datei.
_sprache_datei=${BASH_SOURCE[0]:-tools/sprache.sh}
case $_sprache_datei in
  */*) _sprache_datei=${_sprache_datei%/*}/../sprache.txt ;;
  *)   _sprache_datei=../sprache.txt ;;
esac
_sprache_ermitteln

sag() {
  case $SPRACHE in
    en) printf '%s\n' "${2:-$1}" ;;
    fr) printf '%s\n' "${3:-${2:-$1}}" ;;
    es) printf '%s\n' "${4:-${2:-$1}}" ;;
    *)  printf '%s\n' "$1" ;;
  esac
}
