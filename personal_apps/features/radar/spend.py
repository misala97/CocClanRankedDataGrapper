# personal_apps/features/radar/spend.py
"""What the model pass costs, counted from what the API already tells us.

There is no balance to ask for. Anthropic's Cost API reports SPEND rather than
remaining credit, requires a separate Admin API key, and the documentation
states twice that the Admin API is unavailable for individual accounts. So the
number here is built from `response.usage`, which every call returns anyway --
exact, free, needs no second credential, and attributable to radar rather than
to everything the key has ever done.

Read it against whatever was last loaded onto the account to know when to top
up. It cannot tell you the balance, because nothing can.
"""
import datetime as dt
from zoneinfo import ZoneInfo

import sqlalchemy as sa

from extensions import db
from models import RadarLlmSpend

# The reader's calendar, which is the surface's calendar: every clock and date
# on the board is Berlin time (routes/api.py: display_timezone). The meter
# used to book and read its day as the UTC date, which flips at 02:00 CEST --
# so at 02:00 the masthead reset to nothing while the reader's day was two
# hours old. A cost belongs to the day the reader would say it was spent on.
BERLIN = ZoneInfo('Europe/Berlin')


def _clock():
    """Patched by tests."""
    return dt.datetime.now(dt.timezone.utc)


def berlin_day(when=None):
    """The Berlin calendar day of an aware instant (default: now)."""
    when = when or _clock()
    return when.astimezone(BERLIN).date()

# USD per million tokens, (input, output). Anthropic list price.
#
# Deliberately not hashed into source_config_version: what a mention cost to
# read does not change which mentions are counted.
MODEL_RATES = {
    'claude-haiku-4-5': (1.00, 5.00),
    # Corrected 2026-09-06 from (3.00, 15.00). No Sonnet spend has ever been
    # booked -- the review tier has never run live -- so nothing is restated
    # by this; it would simply have overstated the review tier by 50% the
    # first time it did.
    'claude-sonnet-5': (2.00, 10.00),
    'claude-opus-5': (5.00, 25.00),
    # An EXPLICIT zero, and load-bearing. cost_micros returns None for an
    # unknown rate and the board then reports those tokens as `unpriced`,
    # which is the honest reading of "we do not know what this cost". A
    # local encoder is not unknown: it is free, and saying so is the
    # difference between a meter that reads zero and a meter that reads
    # "unpriced" forever.
    'radar-encoder-v1': (0.0, 0.0),
}

MICROS_PER_USD = 1_000_000


def cost_micros(model, input_tokens, output_tokens):
    """Integer micro-dollars for this usage, or None at an unknown rate.

    None is not zero: zero says the call was free. The usage is still recorded,
    and summary() exposes its tokens without inventing a dollar amount.
    """
    rate = MODEL_RATES.get(model)
    if rate is None:
        return None
    per_in, per_out = rate
    return round((input_tokens * per_in + output_tokens * per_out)
                 * MICROS_PER_USD / 1_000_000)


def record(model, calls, input_tokens, output_tokens, day=None):
    """Add one pass's usage to its day. Returns nothing.

    A call that used nothing writes nothing. A zero row would make an outage
    look like a quiet day, which is the confusion the bucket statuses exist to
    prevent everywhere else in this pipeline.
    """
    if not calls and not input_tokens and not output_tokens:
        return
    if day is None:
        day = berlin_day()

    row = RadarLlmSpend.query.filter_by(day=day, model=model).one_or_none()
    if row is None:
        row = RadarLlmSpend(day=day, model=model, calls=0, input_tokens=0,
                            output_tokens=0, cost_micros=0)
        db.session.add(row)

    row.calls += calls
    row.input_tokens += input_tokens
    row.output_tokens += output_tokens
    cost = cost_micros(model, input_tokens, output_tokens)
    if cost is not None:
        # Added at the rate that applies NOW, so a later price change cannot
        # reach backwards into a day that was already paid for.
        row.cost_micros += cost
    db.session.commit()


def _usd(micros):
    """Micros to dollars, as a float.

    float() is not decoration. SUM() over a BIGINT returns Decimal on MySQL
    and MariaDB, Decimal divided by an int stays Decimal, and Flask's JSON
    encoder raises on Decimal -- so the board would 500 the moment the first
    spend row existed, and only then. The same trap cost an afternoon in
    leaderboard.build_rows.
    """
    return float(micros or 0) / MICROS_PER_USD


def summary(today=None):
    """Today and month-to-date dollars plus tokens at an unknown rate.

    Month-to-date rather than a rolling thirty days: this is read against what
    was loaded onto the account, and that is billed by calendar month.
    """
    if today is None:
        today = berlin_day()
    first = today.replace(day=1)

    def total(since, until):
        return db.session.query(
            sa.func.coalesce(sa.func.sum(RadarLlmSpend.cost_micros), 0)).filter(
                RadarLlmSpend.day >= since,
                RadarLlmSpend.day <= until).scalar()

    def unpriced(since, until):
        """Tokens booked to models whose rate is absent from MODEL_RATES."""
        total = db.session.query(
            sa.func.coalesce(
                sa.func.sum(RadarLlmSpend.input_tokens
                            + RadarLlmSpend.output_tokens), 0)).filter(
                RadarLlmSpend.day >= since,
                RadarLlmSpend.day <= until,
                RadarLlmSpend.model.notin_(list(MODEL_RATES))).scalar()
        # SUM over BIGINT is Decimal on MySQL/MariaDB; JSON needs an int.
        return int(total or 0)

    return {
        'today_usd': _usd(total(today, today)),
        'month_usd': _usd(total(first, today)),
        'unpriced_tokens': unpriced(first, today),
    }
