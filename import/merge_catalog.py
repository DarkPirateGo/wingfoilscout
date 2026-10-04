#!/usr/bin/env python3
"""Führt die recherchierten Koordinaten und die Jens-Dee-Pins in spots.yaml zusammen.

Zwei Schritte:
  1. Bisher geschätzte Spots bekommen die Koordinate ihrer Windfinder-Spotseite.
  2. Die Pins aus der Google-Maps-Liste kommen dazu — außer sie liegen näher als
     DEDUPE_KM an einem Spot, der schon im Katalog steht. Dann wird der
     bestehende Eintrag nur um einen Hinweis ergänzt.
"""
from __future__ import annotations
import math
from pathlib import Path

import yaml

DEDUPE_KM = 1.5

# id → (lat, lon, popularity, source, zusatz-notiz)
WINDFINDER = {
    "bodensee-fussach": (47.4985, 9.6287, "#1 Vorarlberg · #11 Österreich (Windfinder)",
                         "https://www.windfinder.com/forecast/bodensee_rohrspitz",
                         "Koordinate von der Windfinder-Spotseite Bodensee / Rohrspitz."),
    "chiemsee-chieming": (47.8476, 12.4748, "#15 Bayern (Windfinder)",
                          "https://www.windfinder.com/forecast/chiemsee_feldwies",
                          "Koordinate von Windfinder (Chiemsee / Feldwies) — deckt sich bis auf 500 m "
                          "mit einem Pin aus Jens Dees Liste."),
    "neuchatel-yvonand": (46.8003, 6.7425, "#1 Waadt · #5 Schweiz (Windfinder)",
                          "https://www.windfinder.com/forecast/neuenburgersee_yvonand", None),
    "fos-plage-napoleon": (43.4377, 4.9446, "#37 PACA · #208 Frankreich (Windfinder)",
                           "https://www.windfinder.com/forecast/fos_sur_mer", None),
    "etang-de-berre": (43.4781, 5.1704, "#116 PACA (Windfinder)",
                       "https://www.windfinder.com/forecast/berre-l-etang",
                       "Koordinate ist der Windfinder-Punkt Berre-l'Étang am Nordostufer."),
    "salagou": (43.6549, 3.3678, "#29 Okzitanien (Windfinder)",
                "https://www.windfinder.com/forecast/lac_du_salagou",
                "Windfinder führt den Salagou als eigenen Spot — das stützt meine Vermutung, "
                "ersetzt aber deine Bestätigung nicht."),
    "walchensee": (47.5884, 11.3134, "#40 Bayern (Windfinder)",
                   "https://de.windfinder.com/forecast/walchensee", None),
    "sankt-peter-ording": (54.3303, 8.5885, "#15 Schleswig-Holstein · #28 Deutschland · #118 weltweit (Windfinder)",
                           "https://de.windfinder.com/forecast/st._peter-ording", None),
    "fehmarn-suedstrand": (54.4078, 11.1977, "#69 Schleswig-Holstein · #157 Deutschland (Windfinder)",
                           "https://de.windfinder.com/forecast/suedstrand_fehmarn", None),
    "heiligenhafen-graswarder": (54.3800, 10.9300, "#74 Schleswig-Holstein · #166 Deutschland (Windfinder)",
                                 "https://de.windfinder.com/forecast/heiligenhafen", None),
}


def km(a, b) -> float:
    p1, p2 = math.radians(a[0]), math.radians(b[0])
    dp, dl = p2 - p1, math.radians(b[1] - a[1])
    x = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * 6371.0088 * math.asin(math.sqrt(x))


def main() -> None:
    spots = yaml.safe_load(Path("spots.yaml").read_text(encoding="utf-8"))
    pins = yaml.safe_load(Path("jensdee_pins.yaml").read_text(encoding="utf-8")) or []
    by_id = {s["id"]: s for s in spots}

    updated = 0
    for sid, (lat, lon, pop, src, extra) in WINDFINDER.items():
        s = by_id.get(sid)
        if not s:
            print(f"  ! {sid} nicht im Katalog")
            continue
        moved = km((s["lat"], s["lon"]), (lat, lon))
        s["lat"], s["lon"] = lat, lon
        s["popularity"] = pop
        s["source"] = src
        s["verified"] = True
        note = (s.get("notes") or "").split(" Windfinder führt")[0].strip()
        note = note.replace("Windfinder-Spotseite existiert — Koordinate noch nicht übernommen.", "").strip()
        note = note.replace("Koordinate von dort noch nicht übernommen.", "").strip()
        if extra:
            note = (note + " " + extra).strip()
        s["notes"] = note
        updated += 1
        print(f"  ✓ {sid}: Koordinate um {moved:.2f} km korrigiert")

    added, merged = 0, 0
    for pin in pins:
        near = [s for s in spots if km((s["lat"], s["lon"]), (pin["lat"], pin["lon"])) <= DEDUPE_KM]
        if near:
            target = min(near, key=lambda s: km((s["lat"], s["lon"]), (pin["lat"], pin["lon"])))
            d = km((target["lat"], target["lon"]), (pin["lat"], pin["lon"]))
            target["notes"] = ((target.get("notes") or "") +
                               f" Jens Dee hat hier ebenfalls einen Pin ({d*1000:.0f} m entfernt).").strip()
            merged += 1
            print(f"  ~ {pin['id']} fällt mit {target['id']} zusammen ({d*1000:.0f} m)")
            continue
        spots.append(pin)
        added += 1

    Path("spots.yaml").write_text(
        yaml.safe_dump(spots, allow_unicode=True, sort_keys=False, width=100, default_flow_style=False),
        encoding="utf-8")

    n_ver = sum(1 for s in spots if s.get("verified"))
    n_sec = sum(1 for s in spots if not s.get("sectors"))
    print(f"\n{updated} Koordinaten korrigiert · {added} Pins ergänzt · {merged} zusammengeführt")
    print(f"Katalog: {len(spots)} Spots, {n_ver} mit belegter Koordinate, {n_sec} ohne Windsektoren")


if __name__ == "__main__":
    main()
