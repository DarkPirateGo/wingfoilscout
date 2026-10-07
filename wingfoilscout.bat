@echo off
REM Doppelklick-Start fuer Wingfoilscout (Windows): oeffnet die Oberflaeche im Browser.
REM Die eine eigene Meldung steht in allen vier Sprachen der Oberflaeche, ohne
REM Sprachwahl: Ohne Python lief Wingfoilscout hier noch nie, also gibt es auch
REM keine gespeicherte Wahl (sprache.txt). Nur ASCII, weil cmd.exe UTF-8 sonst
REM als Zeichensalat zeigt. Keine Sprungmarken (goto): die Datei hat
REM LF-Zeilenenden, und cmd.exe findet Sprungmarken dann nicht immer.
REM
REM Seit 2.4.0 wird Python ausprobiert statt nur gesucht: "python" kann der
REM Platzhalter des Microsoft Store sein, der nur auf den Store verweist (dann
REM scheiterte bis 2.3.0 erst die Installation von PyYAML). Danach der Starter
REM "py" von python.org. Verlangt wird 3.9 oder neuer, wie auf dem Mac.
cd /d "%~dp0"
set "PY="
python -c "import sys; sys.exit(sys.version_info < (3, 9))" >nul 2>&1 && set "PY=python"
if not defined PY (
  py -3 -c "import sys; sys.exit(sys.version_info < (3, 9))" >nul 2>&1 && set "PY=py -3"
)
if not defined PY (
  echo Python 3.9 oder neuer wurde nicht gefunden - bitte von python.org installieren.
  echo Python 3.9 or newer was not found - please install it from python.org.
  echo Python 3.9 ou plus recent est introuvable - installez-le depuis python.org.
  echo No se ha encontrado Python 3.9 o posterior - instalelo desde python.org.
  pause
  exit /b 1
)
%PY% -c "import yaml" >nul 2>&1 || %PY% -m pip install -q -r requirements.txt
%PY% -m wingscout.webui
pause
