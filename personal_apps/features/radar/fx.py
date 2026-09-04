# personal_apps/features/radar/fx.py
"""Euro reference rates, and the one conversion the chart is allowed to do.

A ticker listed on Nasdaq and quoted at Tradegate has three years of closes
in dollars and a headline price in euros. Drawing the dollars on a euro axis
would be a lie by omission, and drawing nothing -- which is what the panel
did until 2026-09-05 -- is a lie by silence. So: convert, at read time,
against a rate somebody published on that date, and say so next to the line.

Read time, not write time, on purpose. The close store holds what a venue
printed. A converted number is a derived number and derived numbers do not
belong in it; today's rate would also silently restate every historical row
the next time anything touched them.
"""
import datetime as dt
import decimal

from extensions import db
from models import RadarFxRate

# The only pair the panel needs. Named rather than parameterised everywhere:
# a second pair is a schema question (which venue, which axis) and not a
# matter of passing another string.
BASE = 'EUR'
QUOTE = 'USD'

# How far a published rate may be carried forward, in days.
#
# TARGET closes for at most four consecutive days (Easter), so seven covers
# every real gap with room to spare. Beyond that the feed is broken rather
# than quiet, and drawing through it would hide exactly the outage a reader
# needs to see.
MAX_CARRY_DAYS = 7


def record_rates(rates, now, *, base=BASE, quote=QUOTE, source='ecb',
                 commit=True):
    """Upsert (date, rate) pairs. Returns rows written.

    Upsert because the ECB restates: the daily file is provisional for a few
    hours after publication, and the history file is the corrected record.
    """
    rates = list(rates)
    if not rates:
        return 0

    existing = {row.rate_date: row for row in RadarFxRate.query.filter(
        RadarFxRate.base == base, RadarFxRate.quote == quote,
        RadarFxRate.rate_date.in_([day for day, _ in rates])).all()}

    written = 0
    for day, rate in rates:
        row = existing.get(day)
        if row is None:
            db.session.add(RadarFxRate(
                rate_date=day, base=base, quote=quote,
                rate=decimal.Decimal(rate), source=source, fetched_at=now))
        else:
            row.rate = decimal.Decimal(rate)
            row.source = source
            row.fetched_at = now
        written += 1

    if commit:
        db.session.commit()
    return written


def rate_series(start, end, *, base=BASE, quote=QUOTE):
    """{date: rate} for every PUBLISHED day in the window.

    Holes are kept as holes. `rate_on` is what decides what a hole means;
    a series that pre-filled its weekends would have already decided.
    """
    rows = (db.session.query(RadarFxRate.rate_date, RadarFxRate.rate)
            .filter(RadarFxRate.base == base, RadarFxRate.quote == quote,
                    RadarFxRate.rate_date >= start,
                    RadarFxRate.rate_date <= end).all())
    return {day: rate for day, rate in rows}


def rate_on(series, day):
    """The rate in force on `day`: the last one published at or before it.

    None before the series begins. Not the earliest known rate -- a 2019
    close converted at 2024's rate is a fabricated price, and the honest
    answer to "what was this worth in euros" is that we do not know.
    """
    if not series:
        return None
    for back in range(0, MAX_CARRY_DAYS + 1):
        rate = series.get(day - dt.timedelta(days=back))
        if rate is not None:
            return rate
    return None


def convert_usd_to_eur(closes, series):
    """(date, usd) pairs -> (date, eur) pairs, dropping what we cannot price.

    The ECB quotes EUR/USD as dollars per euro, so euros are dollars DIVIDED
    by the rate. Quantised to four places, which is what RadarDailyClose.close
    stores and therefore the most precision the input ever carried.
    """
    converted = []
    for day, close in closes:
        rate = rate_on(series, day)
        if rate is None or rate == 0:
            continue
        converted.append(
            (day, (decimal.Decimal(close) / rate).quantize(
                decimal.Decimal('0.0001'), rounding=decimal.ROUND_HALF_UP)))
    return tuple(converted)
