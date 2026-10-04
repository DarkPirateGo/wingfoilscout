"""Der Zeitraum einer Suche: ab wann und wie lange (seit 2.3.0).

Bis 2.1 begann jede Suche „jetzt“: die Tage voraus zählten ab heute. Seit
2.3.0 lässt sich ein Startzeitpunkt angeben — „Ab wann?“ in der Oberfläche,
`--ab` auf der Kommandozeile. Die Tage zählen dann ab seinem Datum, und
Stunden vor ihm fallen heraus wie vergangene („vor dem gewählten Start“).

Die Vorhersagen reichen 16 Tage ab heute (Open-Meteo: `forecast_days`
höchstens 16, siehe sources/openmeteo.py, marine.py, ensemble.py). Geholt
werden deshalb Vorlauf plus Zeitraum; reicht das über den 16. Tag hinaus,
wird der Zeitraum gekürzt, und die Suche sagt es. Ein Start nach dem letzten
Vorhersagetag geht nicht.

Der Startzeitpunkt ist Ortszeit dieses Rechners (so schickt ihn der Browser,
so tippt man ihn ein). Für jeden Spot wird er in dessen Ortszeit umgerechnet
wie „jetzt“ — „ab 10 Uhr“ ist in Lissabon 9 Uhr.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timedelta

MAX_TAGE = 16                # so weit reicht die Vorhersage, heute mitgezählt

# Was gelesen wird: wie das Feld der Oberfläche es schickt
# (`<input type="datetime-local">`: 2026-10-10T09:00), mit Leerzeichen oder
# Sekunden, nur das Datum — und die deutsche Schreibweise für die
# Kommandozeile.
FORMATE = ("%Y-%m-%dT%H:%M", "%Y-%m-%dT%H:%M:%S", "%Y-%m-%d %H:%M", "%Y-%m-%d",
           "%d.%m.%Y %H:%M", "%d.%m.%Y, %H:%M", "%d.%m.%Y")


class ZuWeit(ValueError):
    """Der Startzeitpunkt liegt hinter dem letzten Vorhersagetag."""


def lesen(text) -> datetime | None:
    """Der Startzeitpunkt aus einer Eingabe — None, wenn sie leer ist.
    Unlesbares hebt ValueError. Nur das Datum heißt: ab 0 Uhr."""
    text = str(text or "").strip()
    if not text:
        return None
    if len(text) > 40:
        raise ValueError(text[:40])
    for form in FORMATE:
        try:
            return datetime.strptime(text, form)
        except ValueError:
            continue
    raise ValueError(text)


def letzter_tag(heute: date | None = None) -> date:
    """Der letzte Tag, für den es noch eine Vorhersage gibt."""
    return (heute or date.today()) + timedelta(days=MAX_TAGE - 1)


@dataclass(frozen=True)
class Fenster:
    """Was eine Suche abdeckt. `ab` ist None, wenn sie jetzt beginnt."""
    ab: datetime | None
    erster_tag: date           # erster Tag des Zeitraums
    tage: int                  # Tage im Zeitraum — gekürzt, wenn die Vorhersage nicht so weit reicht
    gewuenscht: int            # Tage, wie angefragt
    vorlauf: int               # Tage von heute bis zum ersten Tag

    @property
    def abruf_tage(self) -> int:
        """So viele Tage ab heute müssen die Quellen liefern."""
        return self.vorlauf + self.tage

    @property
    def gekuerzt(self) -> bool:
        return self.tage < self.gewuenscht

    @property
    def tage_iso(self) -> tuple[str, str] | None:
        """(erster Tag, Tag nach dem letzten) als „JJJJ-MM-TT“ für den Filter
        in score_hours — None ohne Startzeitpunkt: dann liefern die Quellen
        genau den Zeitraum, wie bis 2.1."""
        if self.ab is None:
            return None
        return (self.erster_tag.isoformat(), (self.erster_tag + timedelta(days=self.tage)).isoformat())

    def ab_mit_zone(self) -> datetime | None:
        """Der Startzeitpunkt mit der Zone dieses Rechners — score_hours rechnet
        ihn je Spot in dessen Ortszeit um."""
        return self.ab.astimezone() if self.ab is not None else None

    def monate(self) -> set[int]:
        """Jeder Monat, den der Zeitraum berührt — für die Saison der Spots."""
        return {(self.erster_tag + timedelta(days=i)).month for i in range(max(1, self.tage))}


def fenster(ab: datetime | None, tage: int, jetzt: datetime | None = None) -> Fenster:
    """Der Zeitraum für einen Startzeitpunkt `ab` (None: jetzt) und `tage`.

    Ein Startzeitpunkt, der schon vorbei ist, zählt als „jetzt“ — die Suche
    beginnt dann wie immer. Liegt er hinter dem letzten Vorhersagetag, hebt
    das `ZuWeit`."""
    jetzt = jetzt or datetime.now()
    heute = jetzt.date()
    tage = max(1, min(MAX_TAGE, int(tage)))
    if ab is not None and ab <= jetzt:
        ab = None
    if ab is None:
        return Fenster(ab=None, erster_tag=heute, tage=tage, gewuenscht=tage, vorlauf=0)
    vorlauf = (ab.date() - heute).days
    if vorlauf >= MAX_TAGE:
        raise ZuWeit(ab.isoformat(timespec="minutes"))
    return Fenster(ab=ab, erster_tag=ab.date(), tage=min(tage, MAX_TAGE - vorlauf), gewuenscht=tage,
                   vorlauf=vorlauf)


def fuer_feld(dt: datetime) -> str:
    """Ein Zeitpunkt so, wie ihn `<input type="datetime-local">` erwartet."""
    return dt.strftime("%Y-%m-%dT%H:%M")
