#!/usr/bin/env bash
# Änderungen prüfen, festschreiben und auf GitHub schieben — in dieser
# Reihenfolge. Der Prüflauf steht bewusst vorn: was nicht durch die Tests geht,
# soll gar nicht erst hochgeladen werden.
#
# Aufruf:  tools/veroeffentlichen.sh ["Nachricht"]
#          tools/veroeffentlichen.sh --version 1.1.0 ["Nachricht"]
#
# Was hochgeht, ist öffentlich und bleibt es — GitHub hält alte Commits sogar
# nach einem Force-Push noch vor. Darum nimmt das Skript von sich aus nur
# Änderungen an Dateien mit, die schon im Repository sind; neue Dateien zeigt
# es und fragt. Und es weigert sich, wenn eine persönliche Datei
# (tools/persoenliche_daten.py) oder die eigene Heimatkoordinate im Commit
# steht. Bis 2.1.0 nahm `git add -A` alles mit, was .gitignore nicht kannte
# (Review 04.10.2026, D1).
#
# Geprüft wird alles, was der Push mitnimmt: jeder Commit, der noch nicht auf
# GitHub ist — auch einer, der nicht von diesem Skript stammt —, und der neue
# Tag. Je Commit die Adressen von Autor und Committer, die Dateinamen und die
# neuen Zeilen. Bis 2.1.1 sah das Skript nur auf den eigenen Commit und auf
# user.email; author.email, frühere Commits und Umbenennungen gingen durch
# (Nachprüfung der Korrekturen, 04.10.2026).
set -euo pipefail
cd "$(dirname "$0")/.."

rot=$'\e[31m'; gruen=$'\e[32m'; dim=$'\e[2m'; fett=$'\e[1m'; aus=$'\e[0m'
meckern() { echo "${rot}$1${aus}"; exit 1; }
aufruf() {
  echo "Aufruf:  tools/veroeffentlichen.sh [\"Beschreibung\"]"
  echo "         tools/veroeffentlichen.sh --version X.Y.Z [\"Beschreibung\"]"
}

# ── 0. Angaben lesen ─────────────────────────────────────────────────────────
version=""
case "${1:-}" in
  -h|--help) aufruf; exit 0 ;;
  --version)
    if [ $# -lt 2 ] || [ -z "$2" ]; then
      aufruf; meckern "--version braucht eine Nummer, etwa: --version 1.1.0"
    fi
    version="$2"; shift 2
    grep -qE '^[0-9]+\.[0-9]+\.[0-9]+$' <<<"$version" \
      || meckern "Version muss X.Y.Z sein — drei Zahlen mit Punkten, etwa 1.1.0 —, nicht '$version'."
    ;;
  --*) aufruf; meckern "Unbekannte Angabe '$1'." ;;
esac
if [ $# -gt 1 ]; then
  aufruf; meckern "Zu viele Angaben — die Beschreibung gehört in Anführungszeichen."
fi
nachricht="${1:-}"

git rev-parse --git-dir >/dev/null 2>&1 || meckern "Das hier ist kein Git-Repository."
zweig="$(git symbolic-ref -q --short HEAD)" \
  || meckern "Gerade ist kein Zweig ausgecheckt (»detached HEAD«). Erst zurück auf den Zweig, etwa:  git checkout main"

# Abbrechen, nachdem schon etwas vorgemerkt ist: nichts halb vorgemerkt
# zurücklassen (die Dateien selbst bleiben, wie sie sind) — der nächste Lauf
# merkt ohnehin alles neu vor.
abbruch() {
  git reset -q >/dev/null 2>&1 || true
  if [ -n "$version" ]; then
    echo "${dim}Die Versionsnummer in wingscout/__init__.py ist schon gesetzt — der nächste Lauf mit derselben Nummer macht dort einfach weiter.${aus}"
  fi
  meckern "$1"
}

# Dateinamen aus `git … -z`, einer je Zeile, für tools/persoenliche_daten.py.
# Ohne -z setzt Git Namen wie  takeout/Saved "Places".json  in Anführungszeichen
# mit Escapes, und das Muster für takeout/ griff nicht mehr (Nachprüfung
# 04.10.2026). Ein Zeilenumbruch im Namen wird zum Leerzeichen.
zeilenweise() { tr '\n\000' ' \n'; }

# Ist $1 eine anonyme Adresse von GitHub? Genau ein @, und das vor
# users.noreply.github.com — »privat@example.de@users.noreply.github.com« nicht.
anonym() {
  case "$1" in
    *@*@*) return 1 ;;
    ?*@users.noreply.github.com) return 0 ;;
  esac
  return 1
}

# ── Was der Push mitnimmt ────────────────────────────────────────────────────
# Alles, was GitHub noch nicht hat: die Commits nach dem bekannten Stand von
# origin/<zweig>. Gibt es den Zweig dort noch nicht, alle, die auf keinem Zweig
# von origin liegen — beim allerersten Push also die ganze Historie.
basis="--remotes=origin"
if git rev-parse -q --verify "refs/remotes/origin/$zweig^{commit}" >/dev/null; then
  basis="refs/remotes/origin/$zweig"
fi
unterwegs() {   # git log über genau diese Commits; die Angaben ($1 …) gehen an git log
  git rev-parse -q --verify 'HEAD^{commit}' >/dev/null || return 0     # noch gar kein Commit
  git -c core.quotepath=off -c log.mailmap=false -c log.showRoot=true -c log.showSignature=false \
    log "$@" HEAD --not "$basis" --
}

# Prüft jeden Commit, den der Push mitnähme, und sagt, was nicht stimmt.
# 0 = in Ordnung, 1 = Persönliches gefunden (steht oben), 2 = nicht prüfbar.
unterwegs_pruefen() {
  local liste kopf kurz autor committer betreff letzter schlecht="" anzahl=0 nur_letzter=1 \
        namen verboten status ergebnis=0
  liste="$(unterwegs --format='h %H %h%na %ae%nc %ce%ns %s')" || return 2
  [ -n "$liste" ] || return 0
  letzter="$(git rev-parse HEAD)" || return 2

  # Absender: jede Zeile trägt vorn ihr Kennzeichen, damit keine leer ist
  # (eine leere Adresse fiele sonst am Ende der Liste weg)
  while IFS= read -r kopf && IFS= read -r autor && IFS= read -r committer && IFS= read -r betreff; do
    case "$kopf" in "h "*) ;; *) return 2 ;; esac
    case "$autor" in "a "*) ;; *) return 2 ;; esac
    case "$committer" in "c "*) ;; *) return 2 ;; esac
    case "$betreff" in "s "*) ;; *) return 2 ;; esac
    kopf="${kopf#h }"; autor="${autor#a }"; committer="${committer#c }"; betreff="${betreff#s }"
    if anonym "$autor" && anonym "$committer"; then continue; fi
    anzahl=$((anzahl + 1))
    [ "${kopf%% *}" = "$letzter" ] || nur_letzter=0
    kurz="${kopf#* }"
    schlecht="${schlecht}   ${kurz}  ${betreff}"$'\n'"      Autor: ${autor:-(keine)} · Committer: ${committer:-(keine)}"$'\n'
  done <<<"$liste"
  if [ "$anzahl" -gt 0 ]; then
    ergebnis=1
    echo
    echo "${rot}Diese Commits sind noch nicht auf GitHub und tragen eine private Adresse —${aus}"
    echo "${rot}oben wäre sie für jeden lesbar:${aus}"
    printf '%s' "$schlecht"
    if [ "$absender_ok" = 1 ]; then
      echo "Abhilfe (die Adresse für neue Commits stimmt schon):"
    else
      echo "Abhilfe — erst die Adresse wie oben einstellen, dann:"
    fi
    if [ "$nur_letzter" = 1 ]; then
      echo "  Es ist nur der letzte Commit. Mit der richtigen Adresse neu festschreiben —"
      echo "  Inhalt und Beschreibung bleiben:"
      echo "       git commit --amend --reset-author --no-edit"
    else
      echo "  Den letzten Commit richtet  git commit --amend --reset-author --no-edit"
      echo "  Ältere lassen sich nur ändern, indem man die Historie umschreibt — das nicht"
      echo "  allein versuchen: um Hilfe fragen (etwa Claude) und diese Meldung zeigen."
    fi
  fi

  # Dateinamen — je Commit, auch Umbenennungen (als neuer Name) und Merges
  namen="$(unterwegs -z -m --name-only --no-renames --diff-filter=ACMRT --format= | zeilenweise)" || return 2
  verboten="$(printf '%s\n' "$namen" | python3 tools/persoenliche_daten.py dateien --mit-grund)" \
    && status=0 || status=$?
  if [ "$status" = 1 ]; then
    ergebnis=1
    echo
    echo "${rot}In Commits, die noch nicht auf GitHub sind, stehen Dateien, die nie ins${aus}"
    echo "${rot}öffentliche Repository gehören:${aus}"
    printf '%s\n' "$verboten" | sort -u | sed 's/^/   /'
    echo "Steckt eine nur im letzten Commit:  git rm --cached -- \"<Datei>\"  und dann"
    echo "git commit --amend --no-edit  (auf dem Mac bleibt sie). Sonst um Hilfe fragen."
  elif [ "$status" != 0 ]; then
    return 2
  fi

  # Die Heimatkoordinate in den neuen Zeilen jedes Commits
  if [ -f config.yaml ]; then
    unterwegs -p -m -U0 --no-renames --no-color --no-ext-diff --no-textconv \
              --src-prefix=a/ --dst-prefix=b/ --format= \
      | python3 tools/persoenliche_daten.py heimat && status=0 || status=$?
    if [ "$status" = 1 ]; then
      ergebnis=1
      echo "   (in einem Commit, der noch nicht auf GitHub ist)"
      echo "Steht sie nur im letzten Commit: die Stelle durch einen neutralen Punkt ersetzen —"
      echo "etwa Hamburg, 53.55, 9.99 —, die Datei mit  git add -- \"<Datei>\"  vormerken und"
      echo "git commit --amend --no-edit. Sonst um Hilfe fragen."
    elif [ "$status" != 0 ]; then
      return 2
    fi
  fi

  if [ "$ergebnis" != 0 ] && [ "$basis" = "--remotes=origin" ]; then
    echo
    echo "${dim}Sind diese Commits doch schon auf GitHub? Dann kennt dieses Repository nur den${aus}"
    echo "${dim}Stand von dort nicht:  git fetch origin  — danach noch einmal.${aus}"
  fi
  return "$ergebnis"
}

# ── 1. Gibt es überhaupt etwas zu tun? ───────────────────────────────────────
if [ -z "$(git status --porcelain)" ] && [ -z "$version" ]; then
  if [ -z "$(unterwegs --format=%h)" ]; then
    echo "${gruen}Nichts zu veröffentlichen — alles ist schon oben.${aus}"; exit 0
  fi
  echo "${dim}Keine neuen Änderungen, aber noch nicht gepushte Commits.${aus}"
fi

# ── 2. Absenderadressen ──────────────────────────────────────────────────────
# Jeder Commit trägt zwei Adressen (Autor und Committer), jeder Tag eine — und
# jeder, der die Historie ansieht, liest sie. Bis 2.1.0 war das eine private
# Adresse (Review 04.10.2026, D4). Durch geht nur die anonyme von GitHub.
# Welche Adressen Git wirklich nimmt, sagt `git var`: user.email, aber auch
# author.email und committer.email aus jeder Einstellungsdatei und die
# Umgebungsvariablen GIT_AUTHOR_EMAIL, GIT_COMMITTER_EMAIL und EMAIL.
adresse_aus() {   # "Name <adresse> Zeit Zone" → adresse (Git lässt < und > in Namen nicht zu)
  local kennung="$1"
  case "$kennung" in *"<"*">"*) ;; *) return 0 ;; esac
  kennung="${kennung#*<}"
  printf '%s' "${kennung%%>*}"
}
absender_pruefen() {   # 0 = beide Adressen anonym; sonst steht oben, was zu tun ist
  local autor committer user befehl schluessel wert n=1 erklaert=0
  autor="$(adresse_aus "$(git var GIT_AUTHOR_IDENT 2>/dev/null || true)")"
  committer="$(adresse_aus "$(git var GIT_COMMITTER_IDENT 2>/dev/null || true)")"
  if anonym "$autor" && anonym "$committer"; then return 0; fi
  echo "${rot}Git würde mit diesen Adressen festschreiben — und jeder Commit zeigt sie${aus}"
  echo "${rot}öffentlich auf GitHub:${aus}"
  echo "   Autor:     ${autor:-(keine — Git kennt noch keine Adresse)}"
  echo "   Committer: ${committer:-(keine — Git kennt noch keine Adresse)}"
  echo
  user="$(git config user.email || true)"
  if ! anonym "$user"; then
    befehl="git config --global user.email"
    if [ -n "$(git config --local user.email || true)" ]; then
      befehl="git config user.email"      # dieses Repository hat eine eigene Angabe, die gewinnt
    fi
    echo "  $n. Die anonyme Adresse von GitHub steht unter github.com → Settings → Emails,"
    echo "     bei »Keep my email addresses private« — etwa 12345678+DarkPirateGo@users.noreply.github.com."
    echo "     Im Terminal eintragen, mit deiner Nummer statt <id>:"
    echo "       $befehl \"<id>+DarkPirateGo@users.noreply.github.com\""
    n=$((n + 1)); erklaert=1
  fi
  for schluessel in author.email committer.email; do
    wert="$(git config "$schluessel" || true)"
    if [ -n "$wert" ] && ! anonym "$wert"; then
      echo "  $n. $schluessel steht in den Git-Einstellungen und gilt vor user.email — entfernen:"
      if [ -n "$(git config --local "$schluessel" || true)" ]; then
        echo "       git config --unset $schluessel"
      fi
      if [ -n "$(git config --global "$schluessel" || true)" ]; then
        echo "       git config --global --unset $schluessel"
      fi
      echo "     (Wo es sonst noch steht, zeigt:  git config --show-origin --get-all $schluessel)"
      n=$((n + 1)); erklaert=1
    fi
  done
  if [ -n "${GIT_AUTHOR_EMAIL:-}" ] && ! anonym "$GIT_AUTHOR_EMAIL"; then
    echo "  $n. Die Umgebungsvariable GIT_AUTHOR_EMAIL setzt die Adresse und gilt vor allem anderen."
    echo "     Für dieses Terminalfenster:  unset GIT_AUTHOR_EMAIL"
    echo "     Steht sie in ~/.zshrc oder ~/.bash_profile, die Zeile dort löschen."
    n=$((n + 1)); erklaert=1
  fi
  if [ -n "${GIT_COMMITTER_EMAIL:-}" ] && ! anonym "$GIT_COMMITTER_EMAIL"; then
    echo "  $n. Die Umgebungsvariable GIT_COMMITTER_EMAIL setzt die Adresse und gilt vor allem anderen."
    echo "     Für dieses Terminalfenster:  unset GIT_COMMITTER_EMAIL"
    echo "     Steht sie in ~/.zshrc oder ~/.bash_profile, die Zeile dort löschen."
    erklaert=1
  fi
  if [ "$erklaert" = 0 ]; then
    echo "  Woher die Adresse kommt, zeigt:  git config --show-origin --get-regexp 'email'"
  else
    echo "  ${dim}Hilft das nicht, zeigt  git config --show-origin --get-regexp 'email'  woher sie kommt.${aus}"
  fi
  return 1
}

# Erst die Adressen, dann jeder Commit, der noch nicht oben ist — beides vor
# allem anderen, damit noch nichts geändert ist, wenn etwas nicht durchgeht,
# und alles auf einmal gemeldet wird. Vor dem Push wird noch einmal geprüft
# (Schritt 8), dann mit dem neuen Commit und dem neuen Tag.
absender_ok=1
absender_pruefen || absender_ok=0
unterwegs_pruefen && status=0 || status=$?
if [ "$absender_ok" = 0 ] || [ "$status" = 1 ]; then
  echo
  meckern "Abgebrochen — noch nichts geändert, nichts hochgeladen. Nach der Reparatur denselben Befehl noch einmal."
elif [ "$status" != 0 ]; then
  meckern "Was hochginge, ließ sich nicht prüfen (siehe oben) — sicherheitshalber abgebrochen, noch nichts geändert."
fi

# ── 3. Version prüfen, aber noch nicht setzen ────────────────────────────────
# Erst prüfen, dann ändern: ein fehlgeschlagener Lauf soll keine halb gesetzte
# Versionsnummer hinterlassen. (Genau das ist beim ersten Einsatz passiert.)
if [ -n "$version" ]; then
  if [ -n "$(git tag -l "v$version")" ]; then meckern "Tag v$version gibt es schon."; fi
  if ! grep -q "^## $version" CHANGELOG.md 2>/dev/null; then
    echo "${rot}Hinweis:${aus} CHANGELOG.md hat noch keinen Abschnitt '## $version'."
    printf "Trotzdem weiter? [j/N] "
    antwort=""; read -r antwort || true
    [ "$antwort" = "j" ] || meckern "Abgebrochen. Erst den Changelog ergänzen."
  fi
fi

# ── 4. Prüflauf ──────────────────────────────────────────────────────────────
# Mit "bash" davor: das Ausführbar-Bit geht auf dem Mac leicht verloren.
# Der Pre-Commit-Hook lässt denselben Prüflauf gleich noch einmal laufen —
# dann mit der neuen Versionsnummer. Was nur mit der alten Nummer besteht,
# fällt erst dort auf; darum steht der Prüflauf hier und der Hook bleibt.
echo "${fett}Prüflauf …${aus}"
bash tools/check.sh || meckern "Prüflauf fehlgeschlagen — es wird nichts hochgeladen."

# ── 5. Jetzt erst die Versionsnummer ─────────────────────────────────────────
# Steht sie schon drin, ist das kein Fehler: so sieht es aus, wenn ein früherer
# Lauf die Nummer gesetzt hat und danach am Commit gescheitert ist (20.09.2026,
# ein Test hatte die Version fest verdrahtet). Dann geht es einfach weiter.
if [ -n "$version" ]; then
  python3 - "$version" <<'VERSION'
import pathlib, re, sys
neu = sys.argv[1]
p = pathlib.Path("wingscout/__init__.py"); s = p.read_text(encoding="utf-8")
m = re.search(r'__version__ = "([^"]+)"', s)
if not m:
    raise SystemExit("__version__ nicht gefunden in wingscout/__init__.py")
if m.group(1) == neu:
    print(f"Version steht schon auf {neu}.")
else:
    p.write_text(s[:m.start(1)] + neu + s[m.end(1):], encoding="utf-8")
    print(f"Version auf {neu} gesetzt (vorher {m.group(1)}).")
VERSION
fi

# ── 6. Was genau geht hoch? ──────────────────────────────────────────────────
# Von sich aus nur Dateien, die schon im Repository sind (geändert oder
# gelöscht). Eine neue Datei kommt nur dazu, wenn jemand »ja« tippt.
# --literal-pathspecs: ein Dateiname mit * oder ? ist ein Name, kein Muster.
git add -u

neue="$(git -c core.quotepath=off ls-files --others --exclude-standard)"
if [ -n "$neue" ]; then
  echo
  echo "${fett}Neue Dateien, die noch nie auf GitHub waren:${aus}"
  printf '%s\n' "$neue" | sed 's/^/   /'
  echo
  echo "Was hochgeht, ist öffentlich — für immer. Persönliches gehört nicht dazu:"
  echo "eigene Listen und Exporte, Bildschirmfotos, Kopien der config.yaml."
  echo "Gehören ${fett}alle${aus} diese Dateien ins öffentliche Repository?"
  printf "  ja = mit hochladen · nein = nur auf diesem Mac lassen · Enter = abbrechen: "
  antwort=""; read -r antwort || true
  case "$antwort" in
    ja|Ja|JA)
      printf '%s\n' "$neue" | while IFS= read -r datei; do
        git --literal-pathspecs add -- "$datei" || exit 1
      done || abbruch "Die neuen Dateien ließen sich nicht vormerken (siehe oben)."
      ;;
    nein|Nein|NEIN)
      echo "${dim}Die neuen Dateien bleiben nur auf diesem Mac.${aus}"
      ;;
    *)
      abbruch "Abgebrochen — nichts festgeschrieben, nichts hochgeladen."
      ;;
  esac
fi

# Was nie ins Repository darf, auch wenn es von Hand vorgemerkt wurde
# (git add -f) — dann wird gar nichts festgeschrieben. Jeder neue Name zählt,
# auch das Ziel einer Umbenennung: bis 2.1.1 sah das Skript nur auf neu
# angelegte Dateien (--diff-filter=A), und Git meldete
# »mv import/jensdee_pins.yaml takeout/« als Umbenennung — die ging durch.
verboten="$(git diff --cached --name-only -z --no-renames --diff-filter=ACMRT \
            | zeilenweise | python3 tools/persoenliche_daten.py dateien)" && status=0 || status=$?
if [ "$status" = 1 ]; then
  echo
  echo "${rot}Diese Dateien gehören nie ins öffentliche Repository:${aus}"
  printf '%s\n' "$verboten" | python3 tools/persoenliche_daten.py dateien --mit-grund | sed 's/^/   /' || true
  echo "Sie sind wieder aus dem Commit genommen; auf dem Mac bleiben sie unverändert."
  abbruch "Abgebrochen — nichts festgeschrieben, nichts hochgeladen."
elif [ "$status" != 0 ]; then
  abbruch "Die Prüfung auf persönliche Dateien ist selbst gescheitert (siehe oben) — sicherheitshalber wird nichts hochgeladen."
fi

# Die eigene Heimatkoordinate (rider.home aus config.yaml) in einer Zeile,
# die neu dazukommt — etwa als Beispielwert in einem Test. Die Vorsilben a/
# und b/ stehen ausdrücklich da: mit diff.noprefix oder diff.mnemonicPrefix in
# der eigenen Git-Einstellung fehlten sie, und die Prüfung übersprang jede
# Datei (Nachprüfung 04.10.2026).
if [ -f config.yaml ]; then
  git -c core.quotepath=off diff --cached --no-color --no-ext-diff --no-textconv --no-renames -U0 \
      --src-prefix=a/ --dst-prefix=b/ \
    | python3 tools/persoenliche_daten.py heimat && status=0 || status=$?
  if [ "$status" = 1 ]; then
    abbruch "Abgebrochen: die Heimatkoordinate steht im Commit (Fundstellen oben). Dort durch einen neutralen Punkt ersetzen — etwa Hamburg, 53.55, 9.99 — und denselben Befehl noch einmal."
  elif [ "$status" != 0 ]; then
    abbruch "Ob die Heimatkoordinate im Commit steht, ließ sich nicht prüfen (siehe oben) — sicherheitshalber wird nichts hochgeladen."
  fi
else
  echo "${dim}Keine config.yaml — nach der Heimatkoordinate wird nicht gesucht.${aus}"
fi

if git diff --cached --quiet; then
  echo "${dim}Nichts festzuschreiben.${aus}"
else
  echo
  echo "${fett}So sieht der Commit aus${aus} ${dim}(?? = bleibt nur auf diesem Mac)${aus}"
  git -c core.quotepath=off status --short -uall
  echo
  if [ -z "$nachricht" ]; then
    printf "Beschreibung des Commits (leer = abbrechen): "
    read -r nachricht || nachricht=""
    [ -n "$nachricht" ] || abbruch "Ohne Beschreibung kein Commit."
  fi
  git commit -q -m "$nachricht" \
    || abbruch "Commit fehlgeschlagen (der Prüflauf im Pre-Commit-Hook? siehe oben). Nach der Reparatur denselben Befehl noch einmal."
  echo "${gruen}Festgeschrieben.${aus}"
fi

# ── 7. Tag setzen ────────────────────────────────────────────────────────────
tag_neu=""
if [ -n "$version" ]; then
  git tag -a "v$version" -m "Wingfoilscout $version" \
    || meckern "Der Tag v$version ließ sich nicht setzen (siehe oben). Der Commit ist hier gespeichert, hochgeladen ist nichts."
  tag_neu=1
  echo "${gruen}Tag v$version gesetzt.${aus}"
fi

# ── 8. Letzte Prüfung, dann hochladen ────────────────────────────────────────
# Unmittelbar vor dem Push noch einmal alles, was mitginge: der neue Commit
# und jeder frühere, der noch nicht oben ist (auch der, den ein Merge oder ein
# Cherry-Pick mit fremdem Autor hinterlässt), dazu der Tagger des neuen Tags.
echo "${fett}Prüfe, was hochgeht …${aus}"
unterwegs_pruefen && status=0 || status=$?
if [ "$status" = 0 ] && [ -n "$version" ]; then
  tagger="$(git for-each-ref --format='%(taggeremail)' "refs/tags/v$version")" || tagger=""
  tagger="${tagger#<}"; tagger="${tagger%>}"
  if ! anonym "$tagger"; then
    echo "${rot}Der Tag v$version trägt die Adresse »${tagger:-(keine)}« — oben wäre sie für jeden lesbar.${aus}"
    status=1
  fi
fi
if [ "$status" != 0 ]; then
  if [ -n "$tag_neu" ]; then
    git tag -d "v$version" >/dev/null 2>&1 || true      # der nächste Lauf setzt ihn neu
  fi
  if [ "$status" = 1 ]; then
    meckern "Nichts hochgeladen. Ein Commit ist hier gespeichert — nach der Reparatur (siehe oben) denselben Befehl noch einmal."
  fi
  meckern "Was hochginge, ließ sich nicht prüfen (siehe oben) — sicherheitshalber wird nichts hochgeladen."
fi

# Nur der Zweig und der neue Tag, beide oder keiner (--atomic). `--tags`
# schob bis 2.1.0 jeden lokalen Tag mit — auch einen alten, der auf Commits
# zeigt, die aus der öffentlichen Historie entfernt wurden (Review 04.10.2026,
# D7). --no-follow-tags: mit push.followTags in der eigenen Git-Einstellung
# gingen sonst alle älteren Tags mit, die auf diesen Zweig zeigen
# (Nachprüfung 04.10.2026).
echo "${fett}Lade nach GitHub (Zweig $zweig) …${aus}"
if [ -n "$version" ]; then
  git push --atomic --no-follow-tags origin "$zweig" "refs/tags/v$version" \
    || meckern "Hochladen fehlgeschlagen (siehe oben). Commit und Tag sind hier gespeichert — nach der Reparatur:  git push --atomic --no-follow-tags origin $zweig refs/tags/v$version"
else
  git push --no-follow-tags origin "$zweig" \
    || meckern "Hochladen fehlgeschlagen (siehe oben). Der Commit ist hier gespeichert — nach der Reparatur denselben Befehl noch einmal."
fi
echo "${gruen}Fertig.${aus}"

if [ -n "$version" ]; then
  echo
  echo "Für das Release auf GitHub: Releases → Create a new release →"
  echo "Tag v$version wählen → Abschnitt aus CHANGELOG.md einsetzen."
fi
