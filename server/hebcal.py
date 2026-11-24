"""Israeli holidays computed locally from the Hebrew calendar (no outside service).

The arithmetic is the standard one (Reingold and Dershowitz, "Calendrical Calculations"): a Hebrew year
starts on the molad of Tishrei moved by the four postponement rules, and months alternate 30/29 days
with Marheshvan and Kislev varying by the year's length. Days are Python ordinals (date.toordinal()).

The clinic is closed on the yom tov days observed in Israel and on Independence Day:
Rosh Hashana (two days), Yom Kippur, Sukkot (first day), Shemini Atzeret/Simchat Torah, Pesach (first and
seventh days), Shavuot, and Yom HaAtzmaut with the Knesset's moves (Friday or Saturday -> Thursday,
Monday -> Tuesday). Other days off are the clinic's own setting.
"""
from datetime import date

NISAN, IYYAR, SIVAN, TISHREI = 1, 2, 3, 7
EPOCH = -1373427  # R.D. of 1 Tishrei AM 1


def leap(y):
    return (7 * y + 1) % 19 < 7


def _elapsed(y):
    months = (235 * y - 234) // 19
    parts = 12084 + 13753 * months
    day = months * 29 + parts // 25920
    return day + 1 if (3 * (day + 1)) % 7 < 3 else day


def _correction(y):
    ny0, ny1, ny2 = _elapsed(y - 1), _elapsed(y), _elapsed(y + 1)
    if ny2 - ny1 == 356:
        return 2
    if ny1 - ny0 == 382:
        return 1
    return 0


def new_year(y):
    return EPOCH + _elapsed(y) + _correction(y)


def _days_in_year(y):
    return new_year(y + 1) - new_year(y)


def _last_day(m, y):
    n = _days_in_year(y)
    if m in (2, 4, 6, 10, 13) or (m == 12 and not leap(y)) or (m == 8 and n % 10 != 5) or (m == 9 and n % 10 == 3):
        return 29
    return 30


def to_date(y, m, d):
    """Gregorian date of day d of Hebrew month m (Nisan = 1 ... Tishrei = 7 ... Adar II = 13) of year y."""
    rd = new_year(y) + d - 1
    last = 13 if leap(y) else 12
    if m < TISHREI:
        for mm in range(TISHREI, last + 1):
            rd += _last_day(mm, y)
        for mm in range(1, m):
            rd += _last_day(mm, y)
    else:
        for mm in range(TISHREI, m):
            rd += _last_day(mm, y)
    return date.fromordinal(rd)


def _atzmaut(y):
    d = to_date(y, IYYAR, 5)
    wd = d.weekday()  # Monday = 0 ... Sunday = 6
    if wd == 4:       # Friday -> Thursday
        return date.fromordinal(d.toordinal() - 1)
    if wd == 5:       # Saturday -> Thursday
        return date.fromordinal(d.toordinal() - 2)
    if wd == 0:       # Monday -> Tuesday
        return date.fromordinal(d.toordinal() + 1)
    return d


def holidays(year):
    """{date: Hebrew name} of the closed days that fall in Gregorian `year`."""
    out = {}
    for hy in (year + 3760, year + 3761):
        for (m, d, name) in ((TISHREI, 1, "ראש השנה"), (TISHREI, 2, "ראש השנה"), (TISHREI, 10, "יום כיפור"),
                             (TISHREI, 15, "סוכות"), (TISHREI, 22, "שמיני עצרת"), (NISAN, 15, "פסח"),
                             (NISAN, 21, "שביעי של פסח"), (SIVAN, 6, "שבועות")):
            g = to_date(hy, m, d)
            if g.year == year:
                out[g] = name
        g = _atzmaut(hy)
        if g.year == year:
            out[g] = "יום העצמאות"
    return dict(sorted(out.items()))
