@echo off
REM Doppelklick-Start fuer Wingfoilscout (Windows): oeffnet die Oberflaeche im Browser.
REM Die eine eigene Meldung steht in allen vier Sprachen der Oberflaeche, ohne
REM Sprachwahl: Ohne Python lief Wingfoilscout hier noch nie, also gibt es auch
REM keine gespeicherte Wahl (sprache.txt). Nur ASCII, weil cmd.exe UTF-8 sonst
REM als Zeichensalat zeigt.
cd /d "%~dp0"
where python >nul 2>&1 || (
  echo Python 3 wurde nicht gefunden.
  echo Python 3 was not found.
  echo Python 3 est introuvable.
  echo No se ha encontrado Python 3.
  pause
  exit /b 1
)
python -c "import yaml" >nul 2>&1 || python -m pip install -q -r requirements.txt
python -m wingscout.webui
pause
