#!/usr/bin/env python3
"""Doppelklick-Start: 3 Tage, 500 km, Report öffnet sich im Browser.

Argumente von der Kommandozeile werden durchgereicht. Vorher standen die
Voreinstellungen fest verdrahtet hier, und `run.py --demo` lief trotzdem gegen
die echte API — ein Flag, das stillschweigend verpufft, ist schlimmer als
keines.
"""
from __future__ import annotations
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from wingscout.cli import programm          # main() mit Maske 077: Report und Cache nur für dich

STANDARD = ["--days", "3", "--radius", "500", "--open"]
raise SystemExit(programm(sys.argv[1:] or STANDARD))
