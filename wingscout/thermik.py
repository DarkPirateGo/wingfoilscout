"""Thermische Winde — Seebrise, Talwind, Berg-Tal-Zirkulation.

Warum überhaupt ein eigenes Modul: an einer ganzen Reihe von Spots versagen
die Standardmodelle. Die Ora am Gardasee, der Malojawind im Engadin, der
Maestral an der Adria entstehen aus dem Temperaturunterschied zwischen Land
und Wasser. Ein Gitter von 7 bis 25 km mittelt genau die Täler und
Küstenlinien weg, die diese Zirkulation erzeugen — das Modell zeigt dann 5 kn,
und vor Ort stehen 18 kn an.

Bisher half Wingfoilscout sich mit einer festen Zahl je Spot („Ora: 18 kn, zu 75 %
verlässlich"). Das ist besser als nichts, aber es ist ein Kalenderblatt: es
weiß nicht, ob heute die Sonne scheint oder ein Nordwind gegenanbläst. Dieses
Modul macht aus der festen Zahl eine wetterabhängige.

Die Physik, soweit sie belegt ist:

Temperaturunterschied. Die Seebrise setzt ein, wenn Land und Wasser sich um
etwa 4–5 °C unterscheiden — drei unabhängige Quellen nennen diese
Größenordnung (Miller et al. 2003, Reviews of Geophysics; varactu.fr;
bateaux.com). Der Zusammenhang oberhalb dieser Schwelle ist nichtlinear
(Prtenjak & Grisogono 2007), eine belegte Funktionsform dafür gibt es nicht.
Für Binnenseen fehlt ohnehin jede freie Quelle für die Wassertemperatur,
deshalb wird hier die eingestrahlte Energie als Ersatzgröße genommen: sie
treibt den Unterschied, und sie ist für jeden Punkt abrufbar.

Gegenwind. Das ist der wichtigste und am wenigsten intuitive Teil. Ein
ablandiger Gradientwind unterdrückt die Brise schon ab 7–8 kn (Centro Meteo
Ligure) beziehungsweise oberhalb Windstärke 2, also etwa 6 kn (weeronline.nl,
KNMI-nah). Aber: ein *schwacher* Gegenwind verstärkt sie, statt sie zu
schwächen — er hält die Brisenfront an der Küste fest, statt sie landeinwärts
davonlaufen zu lassen (Arritt 1993, J. Appl. Meteorol. 32; Centro Meteo
Ligure nennt dann 10–20 kn statt der üblichen 6–12). Die Antwort auf den
Gegenwind ist also nicht fallend, sondern hat ein Maximum bei schwachem
Gegenwind und bricht danach steil ab. Genau deshalb funktioniert der Maestral:
schwacher Nordwest-Gradient plus Thermik ist das Optimum.

Der Lake-Breeze-Index von Biggs & Graves (1962), ε = U²/(c_p·ΔT), ist die
etablierte Formel. Sein Schwellenwert ist aber standortabhängig — in der
Literatur finden sich 3, 7 und 10 für dieselbe Formel, je nach Ort und
verwendeter Windgröße. Eine dieser Zahlen zu übernehmen wäre Scheingenauigkeit;
übernommen ist hier nur die Struktur, dass der Gegenwind quadratisch eingeht.

Was dieses Modul NICHT kann: aus dem Nichts eine Thermik erfinden. Es rechnet
nur an Spots, für die im Katalog steht, dass es dort eine gibt, und mit den
Zahlen, die dort hinterlegt sind. Alles, was es tut, ist diese Zahlen nach
Wetterlage zu dämpfen — und im Report bleibt es als Annahme gekennzeichnet.
"""
from __future__ import annotations
import math

# ── Belegte Schwellen ────────────────────────────────────────────────────────
# Gegenwind in Knoten. Bis VERSTAERKT_BIS hilft er, ab BRICHT_AB ist Schluss.
HILFT_BIS = 3.0          # Arritt 1993: stärkste Brise bei leichtem Gegenwind
VERSTAERKT_BIS = 6.0     # weeronline.nl: oberhalb Bft 2 wird es eng
BRICHT_AB = 9.0          # Centro Meteo Ligure: 7–8 kn ablandig = keine Brise
VERSTAERKUNG = 1.15      # wie viel der schwache Gegenwind hinzugibt

# Eingestrahlte Energie seit Sonnenaufgang, ab der die Thermik voll trägt.
# 1,8 kWh/m² entspricht grob einem klaren Vormittag im Sommer. Das ist eine
# Normierung, keine belegte Schwelle — die Literatur nennt für die Einstrahlung
# keine Zahl, nur „es darf keine Wolkendecke da sein".
VOLLE_ENERGIE_WH = 1800.0


def _winkel(a: float, b: float) -> float:
    """Kleinerer Winkel zwischen zwei Richtungen in Grad (0..180)."""
    return abs((a - b + 180) % 360 - 180)


def gegenwind_faktor(wind_kn: float, wdir: float | None, thermik_dir: float | None) -> float:
    """Wie der Gradientwind auf die Thermik wirkt: 0 (erstickt) bis 1,15 (hilft).

    Ohne bekannte Thermikrichtung wird der volle Wind als Gegenwind gewertet —
    lieber vorsichtig als zu optimistisch.
    """
    if wind_kn <= 0:
        return 1.0
    if thermik_dir is None or wdir is None:
        gegen = wind_kn
    else:
        # cos(0°) = 1: Gradient kommt aus derselben Richtung, er trägt die
        # Thermik mit. cos(180°) = -1: er bläst dagegen.
        gegen = -wind_kn * math.cos(math.radians(_winkel(wdir, thermik_dir)))
    if gegen <= 0:
        return 1.0                                    # Rückenwind, keine Störung
    if gegen <= HILFT_BIS:
        return 1.0 + (VERSTAERKUNG - 1.0) * gegen / HILFT_BIS
    if gegen <= VERSTAERKT_BIS:
        anteil = (gegen - HILFT_BIS) / (VERSTAERKT_BIS - HILFT_BIS)
        return VERSTAERKUNG - (VERSTAERKUNG - 1.0) * anteil
    if gegen >= BRICHT_AB:
        return 0.0
    # Zwischen VERSTAERKT_BIS und BRICHT_AB quadratisch abfallend: der
    # Lake-Breeze-Index geht mit U² — die Struktur ist belegt, der Schwellenwert
    # nicht, deshalb nur die Form.
    rest = (BRICHT_AB - gegen) / (BRICHT_AB - VERSTAERKT_BIS)
    return rest * rest


def tagesgang(stunde: float, von: float, bis: float) -> float:
    """Wo im Thermikfenster wir stehen: 0 an den Rändern, 1 im kräftigen Teil.

    Alle Quellen beschreiben denselben Verlauf — langsam aufbauend am späten
    Vormittag, Maximum am frühen Nachmittag, abflauend zum Abend.
    """
    if not (von <= stunde < bis) or bis <= von:
        return 0.0
    lage = (stunde - von) / (bis - von)
    if lage < 0.25:
        return 0.4 + 2.4 * lage              # 0,4 bis 1,0
    if lage < 0.7:
        return 1.0
    return max(0.25, 1.0 - (lage - 0.7) / 0.3 * 0.75)


def energie_faktor(energie_wh: float | None, bewoelkung: float | None) -> float:
    """Wie viel Sonne seit Sonnenaufgang angekommen ist, auf 0..1 normiert.

    Bevorzugt die tatsächlich eingestrahlte Energie: sie gewichtet hohe Cirren
    und tiefe Stratusdecken richtig verschieden, was der Bedeckungsgrad nicht
    kann. Fehlt sie im Modell, ist die Bewölkung der Rückfall.
    """
    if energie_wh is not None:
        return max(0.0, min(1.0, energie_wh / VOLLE_ENERGIE_WH))
    if bewoelkung is None:
        return 0.7                                    # nichts bekannt: gedämpft
    return max(0.15, 1.0 - 0.85 * max(0.0, min(100.0, bewoelkung)) / 100.0)


def potenzial(th: dict, stunde: float, wind_kn: float, wdir: float | None,
              energie_wh: float | None, bewoelkung: float | None) -> float:
    """Wie gut die Thermik heute zu dieser Stunde läuft: 0 bis etwa 1,15."""
    von, bis = float(th.get("from", 12)), float(th.get("to", 18))
    zeit = tagesgang(stunde, von, bis)
    if zeit <= 0:
        return 0.0
    # Manche Thermik stirbt an einer bestimmten Grundströmung — der Malojawind
    # „funktioniert praktisch nie bei nördlicher Grundströmung" (SRF Meteo).
    sektor = th.get("suppressed_by")
    if sektor and wdir is not None and wind_kn >= 6:
        if any(_winkel(wdir, float(r)) <= 45 for r in sektor):
            return 0.0
    return zeit * energie_faktor(energie_wh, bewoelkung) * gegenwind_faktor(wind_kn, wdir, th.get("dir"))


def tagespotenzial(th: dict, werte) -> float:
    """Wie gut die Thermik an diesem Tag läuft: 0 bis etwa 1,1.

    `werte` sind Paare (Stunde, Stundenpotenzial) eines Tages.

    Bis 1.5.1 zeigte der Report hier das Maximum über die Session. Das ist an
    einem sonnigen Tag fast immer die Stunde, in der Tagesgang, Einstrahlung
    und Gegenwind zufällig alle drei passen — im Lauf vom 16.09.2026 lagen
    deshalb alle fünf Thermikziele zwischen 96 und 100 Prozent, der Balken
    unterschied also nichts. Gemittelt wird jetzt über das ganze
    Thermikfenster, gewichtet mit dem Tagesgang: eine einzelne gute Stunde
    trägt so viel, wie sie wiegt.

    Der Tagesgang kürzt sich dabei heraus — übrig bleibt, was heute
    tatsächlich verschieden ist: wie viel Sonne ankommt und ob ein Gegenwind
    bläst. Mal der Verlässlichkeit des Spots aus dem Katalog, denn zwischen
    „quasi täglich" und „wenn alles passt" liegt der eigentliche Unterschied
    zwischen zwei Thermikzielen.
    """
    von, bis = float(th.get("from", 12)), float(th.get("to", 18))
    zaehler = nenner = 0.0
    for stunde, wert in werte:
        gewicht = tagesgang(float(stunde), von, bis)
        if gewicht <= 0:
            continue
        zaehler += float(wert or 0.0)
        nenner += gewicht
    if nenner <= 0:
        return 0.0
    return (zaehler / nenner) * float(th.get("reliability", 0.6))


def ist_thermikspot(spot: dict) -> bool:
    """Steht für diesen Spot Thermikwissen im Katalog?"""
    return bool(spot.get("thermal"))


def gilt_heute(th: dict, monat: int) -> bool:
    monate = th.get("months")
    return not monate or monat in monate


def annahme(spot: dict, t, wind_kn: float, wdir: float | None, cfg,
            energie_wh: float | None = None, bewoelkung: float | None = None):
    """(wind, richtung, angenommen, potenzial) — die Thermik als Annahme.

    Angenommen wird nur, was über dem liegt, was das Modell ohnehin zeigt, und
    nur, wenn im Katalog eine Zahl steht. Spots ohne belegte Zahl bleiben als
    Thermikspot markiert, bekommen aber keinen erfundenen Wind.
    """
    th = spot.get("thermal")
    tcfg = cfg.get("thermal", {}) or {}
    if not th or not tcfg.get("enabled", True):
        return wind_kn, wdir, False, 0.0
    if not gilt_heute(th, t.month):
        return wind_kn, wdir, False, 0.0
    p = potenzial(th, t.hour, wind_kn, wdir, energie_wh, bewoelkung)
    if p <= 0:
        return wind_kn, wdir, False, 0.0
    typisch = th.get("typical_kn")
    if not typisch:
        return wind_kn, wdir, False, p             # bekannter Spot, keine Zahl
    # Die Stärke ist die Stärke: typische Knoten mal heutigem Potenzial. Bis
    # 1.6.1 stand hier zusätzlich die Verlässlichkeit — 16 kn bei 70 % gaben
    # 11 kn, eine Zahl, die an keinem Tag auftritt: läuft die Ora, sind es
    # 16, sonst 0. Der Wing wurde für 11 gewählt und passte in beiden Fällen
    # nicht. Die Verlässlichkeit ist eine Wahrscheinlichkeit und geht jetzt
    # dort ein, wo Wahrscheinlichkeiten hingehören: in die Reihenfolge der
    # Ziele (score.rank_trips), an der Stelle des Ensembles, das die Thermik
    # nicht sehen kann.
    erwartet = float(typisch) * float(tcfg.get("trust", 1.0)) * p
    if erwartet <= wind_kn:
        return wind_kn, wdir, False, p
    # Unter 8 kn Gradientwind gibt die Thermik die Richtung vor, darüber
    # bleibt die Richtung des Modells die bessere Auskunft.
    richtung = th.get("dir") if wind_kn < 8 and th.get("dir") is not None else wdir
    return erwartet, richtung, True, p
