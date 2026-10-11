"""QR-Codes, ohne Zusatzpaket (seit 2.5.0).

Für den Reiter „Handy“: die Adresse, unter der das iPhone Wingfoilscout im
WLAN öffnet, als Code für die Kamera — statt sie abzutippen. Bis dahin stand
sie nur als Text im Terminal (TODO.md: „~200 lines of QR encoder or the
`qrcode` package“; Wingfoilscouts einzige Abhängigkeit ist PyYAML).

Nach ISO/IEC 18004: Byte-Modus, Fehlerkorrektur M (15 %), Versionen 1 bis 10
(bis 213 Bytes — eine Adresse mit Schlüssel braucht etwa 50). Die Maske wählt
die Strafpunktregel der Norm. Der Aufbau folgt der Referenz von Project Nayuki
(„QR Code generator library“, MIT), hier auf das Nötige gekürzt; geprüft wird
er in tests/test_handy.py mit festen Ergebnissen, die beim Bau mit einem
unabhängigen Leser (OpenCV) gelesen wurden.
"""
from __future__ import annotations

# Je Version für Fehlerkorrektur M: Fehlerkorrekturwörter je Block und die
# Blöcke als (Anzahl, Datenwörter je Block) — Tabelle 9 der Norm.
_BLOECKE_M = {
    1: (10, [(1, 16)]), 2: (16, [(1, 28)]), 3: (26, [(1, 44)]), 4: (18, [(2, 32)]),
    5: (24, [(2, 43)]), 6: (16, [(4, 27)]), 7: (18, [(4, 31)]), 8: (22, [(2, 38), (2, 39)]),
    9: (22, [(3, 36), (2, 37)]), 10: (26, [(4, 43), (1, 44)]),
}
# Mittelpunkte der Ausrichtungsmuster je Version (Anhang E der Norm)
_AUSRICHTUNG = {1: [], 2: [6, 18], 3: [6, 22], 4: [6, 26], 5: [6, 30], 6: [6, 34],
                7: [6, 22, 38], 8: [6, 24, 42], 9: [6, 26, 46], 10: [6, 28, 50]}
_FORMAT_M = 0                      # Kennbits der Stufe M im Formatfeld


def _gf_mal(x: int, y: int) -> int:
    """Multiplikation im Körper GF(2⁸) mit dem Polynom x⁸+x⁴+x³+x²+1."""
    z = 0
    for i in reversed(range(8)):
        z = (z << 1) ^ ((z >> 7) * 0x11D)
        z ^= ((y >> i) & 1) * x
    return z


def _rs_teiler(grad: int) -> list[int]:
    ergebnis = [0] * (grad - 1) + [1]
    wurzel = 1
    for _ in range(grad):
        for j in range(grad):
            ergebnis[j] = _gf_mal(ergebnis[j], wurzel)
            if j + 1 < grad:
                ergebnis[j] ^= ergebnis[j + 1]
        wurzel = _gf_mal(wurzel, 0x02)
    return ergebnis


def _rs_rest(daten: list[int], teiler: list[int]) -> list[int]:
    rest = [0] * len(teiler)
    for b in daten:
        faktor = b ^ rest.pop(0)
        rest.append(0)
        for i, koeff in enumerate(teiler):
            rest[i] ^= _gf_mal(koeff, faktor)
    return rest


def _version_fuer(n_bytes: int) -> int:
    for v in range(1, 11):
        ecc, gruppen = _BLOECKE_M[v]
        datenwoerter = sum(n * k for n, k in gruppen)
        laengenbits = 8 if v < 10 else 16
        if 4 + laengenbits + 8 * n_bytes <= datenwoerter * 8:
            return v
    raise ValueError("zu lang für einen QR-Code bis Version 10")


def _codewoerter(daten: bytes, version: int) -> list[int]:
    """Daten im Byte-Modus, aufgefüllt, mit Fehlerkorrektur, verschränkt."""
    ecc, gruppen = _BLOECKE_M[version]
    kapazitaet = sum(n * k for n, k in gruppen)
    bits: list[int] = []

    def anhaengen(wert: int, laenge: int) -> None:
        bits.extend((wert >> i) & 1 for i in reversed(range(laenge)))
    anhaengen(0b0100, 4)                                   # Byte-Modus
    anhaengen(len(daten), 8 if version < 10 else 16)       # Zeichenzahl
    for b in daten:
        anhaengen(b, 8)
    anhaengen(0, min(4, kapazitaet * 8 - len(bits)))       # Ende
    anhaengen(0, (-len(bits)) % 8)
    woerter = [int("".join(map(str, bits[i:i + 8])), 2) for i in range(0, len(bits), 8)]
    fueller = 0xEC
    while len(woerter) < kapazitaet:
        woerter.append(fueller)
        fueller ^= 0xEC ^ 0x11

    teiler = _rs_teiler(ecc)
    bloecke, pos = [], 0
    for n, k in gruppen:
        for _ in range(n):
            stueck = woerter[pos:pos + k]
            pos += k
            bloecke.append((stueck, _rs_rest(stueck, teiler)))
    aus: list[int] = []
    for i in range(max(len(d) for d, _ in bloecke)):
        aus.extend(d[i] for d, _ in bloecke if i < len(d))
    for i in range(ecc):
        aus.extend(e[i] for _, e in bloecke)
    return aus


class _Raster:
    def __init__(self, version: int):
        self.version = version
        self.n = 17 + 4 * version
        self.dunkel = [[False] * self.n for _ in range(self.n)]
        self.fest = [[False] * self.n for _ in range(self.n)]   # Funktionsmuster

    def setzen(self, x: int, y: int, dunkel: bool) -> None:
        self.dunkel[y][x] = dunkel
        self.fest[y][x] = True

    def funktionsmuster(self) -> None:
        n = self.n
        for i in range(n):                                     # Taktlinien
            self.setzen(6, i, i % 2 == 0)
            self.setzen(i, 6, i % 2 == 0)
        for x, y in ((3, 3), (n - 4, 3), (3, n - 4)):          # Suchmuster samt Rand
            for dy in range(-4, 5):
                for dx in range(-4, 5):
                    xx, yy = x + dx, y + dy
                    if 0 <= xx < n and 0 <= yy < n:
                        d = max(abs(dx), abs(dy))
                        self.setzen(xx, yy, d not in (2, 4))
        pos = _AUSRICHTUNG[self.version]
        for i, a in enumerate(pos):
            for j, b in enumerate(pos):
                if (i == 0 and j == 0) or (i == 0 and j == len(pos) - 1) or (i == len(pos) - 1 and j == 0):
                    continue                                   # die Ecken mit Suchmustern
                for dy in range(-2, 3):
                    for dx in range(-2, 3):
                        self.setzen(a + dx, b + dy, max(abs(dx), abs(dy)) != 1)
        self.format(0)                                         # Platz halten, später überschrieben
        if self.version >= 7:
            rest = self.version
            for _ in range(12):
                rest = (rest << 1) ^ ((rest >> 11) * 0x1F25)
            bits = self.version << 12 | rest
            for i in range(18):
                dunkel = (bits >> i) & 1 == 1
                a, b = n - 11 + i % 3, i // 3
                self.setzen(a, b, dunkel)
                self.setzen(b, a, dunkel)

    def format(self, maske: int) -> None:
        daten = _FORMAT_M << 3 | maske
        rest = daten
        for _ in range(10):
            rest = (rest << 1) ^ ((rest >> 9) * 0x537)
        bits = (daten << 10 | rest) ^ 0x5412
        n = self.n

        def bit(i: int) -> bool:
            return (bits >> i) & 1 == 1
        for i in range(6):
            self.setzen(8, i, bit(i))
        self.setzen(8, 7, bit(6))
        self.setzen(8, 8, bit(7))
        self.setzen(7, 8, bit(8))
        for i in range(9, 15):
            self.setzen(14 - i, 8, bit(i))
        for i in range(8):
            self.setzen(n - 1 - i, 8, bit(i))
        for i in range(8, 15):
            self.setzen(8, n - 15 + i, bit(i))
        self.setzen(8, n - 8, True)                            # das immer dunkle Modul

    def daten(self, woerter: list[int]) -> None:
        n, i = self.n, 0
        for rechts in range(n - 1, 0, -2):
            if rechts <= 6:
                rechts -= 1
            for senkrecht in range(n):
                for j in range(2):
                    x = rechts - j
                    aufwaerts = ((rechts + 1) & 2) == 0
                    y = n - 1 - senkrecht if aufwaerts else senkrecht
                    if not self.fest[y][x] and i < len(woerter) * 8:
                        self.dunkel[y][x] = (woerter[i >> 3] >> (7 - (i & 7))) & 1 == 1
                        i += 1

    def maskieren(self, maske: int) -> None:
        bedingung = (
            lambda x, y: (x + y) % 2 == 0,
            lambda x, y: y % 2 == 0,
            lambda x, y: x % 3 == 0,
            lambda x, y: (x + y) % 3 == 0,
            lambda x, y: (x // 3 + y // 2) % 2 == 0,
            lambda x, y: x * y % 2 + x * y % 3 == 0,
            lambda x, y: (x * y % 2 + x * y % 3) % 2 == 0,
            lambda x, y: ((x + y) % 2 + x * y % 3) % 2 == 0,
        )[maske]
        for y in range(self.n):
            for x in range(self.n):
                if not self.fest[y][x] and bedingung(x, y):
                    self.dunkel[y][x] = not self.dunkel[y][x]

    def strafpunkte(self) -> int:
        n, m, punkte = self.n, self.dunkel, 0
        zeilen = [m[y] for y in range(n)] + [[m[y][x] for y in range(n)] for x in range(n)]
        muster = ([True, False, True, True, True, False, True, False, False, False, False],
                  [False, False, False, False, True, False, True, True, True, False, True])
        for z in zeilen:
            lauf = 1
            for i in range(1, n):
                if z[i] == z[i - 1]:
                    lauf += 1
                else:
                    if lauf >= 5:
                        punkte += 3 + lauf - 5
                    lauf = 1
            if lauf >= 5:
                punkte += 3 + lauf - 5
            for i in range(n - 10):
                if z[i:i + 11] in muster:
                    punkte += 40
        for y in range(n - 1):
            for x in range(n - 1):
                if m[y][x] == m[y][x + 1] == m[y + 1][x] == m[y + 1][x + 1]:
                    punkte += 3
        dunkel = sum(sum(z) for z in m)
        punkte += (abs(dunkel * 20 - n * n * 10) // (n * n)) * 10
        return punkte


def matrix(text: str) -> list[list[bool]]:
    """Die Module des QR-Codes für `text` (UTF-8), Zeile für Zeile; True = dunkel."""
    daten = text.encode("utf-8")
    version = _version_fuer(len(daten))
    woerter = _codewoerter(daten, version)
    beste = None
    for maske in range(8):
        r = _Raster(version)
        r.funktionsmuster()
        r.daten(woerter)
        r.maskieren(maske)
        r.format(maske)
        punkte = r.strafpunkte()
        if beste is None or punkte < beste[0]:
            beste = (punkte, r)
    return beste[1].dunkel


def svg(text: str, rand: int = 4, titel: str = "") -> str:
    """Der Code als SVG: schwarz auf weiß, mit der Ruhezone der Norm (vier
    Module) — so liest ihn jede Kamera, auch auf einer dunklen Seite.
    Ein Pfad für alle dunklen Module, je Zeile zusammengefasst. Zum
    Einbetten in HTML gedacht — dort braucht SVG kein xmlns."""
    m = matrix(text)
    n = len(m) + 2 * rand
    wege = []
    for y, zeile in enumerate(m):
        x = 0
        while x < len(zeile):
            if zeile[x]:
                start = x
                while x < len(zeile) and zeile[x]:
                    x += 1
                wege.append(f"M{start + rand} {y + rand}h{x - start}v1h-{x - start}z")
            else:
                x += 1
    beschriftung = f"<title>{titel}</title>" if titel else ""
    return (f"<svg viewBox='0 0 {n} {n}' shape-rendering='crispEdges' "
            f"role='img'>{beschriftung}<rect width='{n}' height='{n}' fill='#fff'/>"
            f"<path fill='#000' d='{''.join(wege)}'/></svg>")
