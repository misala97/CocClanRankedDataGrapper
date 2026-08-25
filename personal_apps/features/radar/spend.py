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

import sqlalchemy as sa

from extensions import db
from models import RadarLlmSpend

# USD per million tokens, (input, output). Anthropic list price.
#
# Deliberately not hashed into source_config_version: what a mention cost to
# read does not change which mentions are counted.
MODEL_RATES = {
    'claude-haiku-4-5': (1.00, 5.00),
    'claude-sonnet-5': (3.00, 15.00),
    'claude-opus-5': (5.00, 25.00),
}

MICROS_PER_USD = 1_000_000


def cost_micros(model, input_tokens, output_tokens):
    """Integer micro-dollars for this usage at the current rate.

    Zero for a model with no rate on file. Guessing one would produce a number
    that looks authoritative and is invented; the tokens are still recorded, so
    the omission is visible and fixable later.
    """
    rate = MODEL_RATES.get(model)
    if rate is None:
        return 0
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
        day = dt.datetime.now(dt.timezone.utc).date()

    row = RadarLlmSpend.query.filter_by(day=day, model=model).one_or_none()
    if row is None:
        row = RadarLlmSpend(day=day, model=model, calls=0, input_tokens=0,
                            output_tokens=0, cost_micros=0)
        db.session.add(row)

    row.calls += calls
    row.input_tokens += input_tokens
    row.output_tokens += output_tokens
    # Added at the rate that applies NOW, so a later price change cannot reach
    # backwards into a day that was already paid for.
    row.cost_micros += cost_micros(model, input_tokens, output_tokens)
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
    """Today and month-to-date, in dollars.

    Month-to-date rather than a rolling thirty days: this is read against what
    was loaded onto the account, and that is billed by calendar month.
    """
    if today is None:
        today = dt.datetime.now(dt.timezone.utc).date()
    first = today.replace(day=1)

    def total(since, until):
        return db.session.query(
            sa.func.coalesce(sa.func.sum(RadarLlmSpend.cost_micros), 0)).filter(
                RadarLlmSpend.day >= since,
                RadarLlmSpend.day <= until).scalar()

    return {
        'today_usd': _usd(total(today, today)),
        'month_usd': _usd(total(first, today)),
    }
