#!/usr/bin/env bash
# Richtet die lokalen Git-Einstellungen ein, die Git nicht mitversioniert:
# den Pre-Commit-Hook und den Merge-Treiber für geometry.json.
# Einmal nach dem Klonen ausführen.
set -euo pipefail
cd "$(dirname "$0")/.."

# "bash" davor: das Ausführbar-Bit von check.sh geht auf dem Mac leicht verloren.
cat > .git/hooks/pre-commit <<'HOOK'
#!/usr/bin/env bash
exec bash tools/check.sh
HOOK
chmod +x .git/hooks/pre-commit
echo "Pre-Commit-Hook eingerichtet: tools/check.sh läuft vor jedem Commit."

# Merge-Treiber für geometry.json. .gitattributes verweist darauf, aber welcher
# Befehl dahintersteht, steht bewusst nur lokal — sonst könnte ein Repository
# fremden Code ausführen lassen, sobald man es klont.
git config merge.geometry.name "geometry.json vereinigen statt Konflikt melden"
git config merge.geometry.driver "python3 tools/merge_geometry.py %A %O %B"
echo "Merge-Treiber für geometry.json eingerichtet."
