# personal_apps/tests/test_radar_spend.py
"""What the model pass actually costs, accumulated from what the API returns.

There is no balance endpoint to ask. Anthropic's Cost API reports spend rather
than remaining credit, needs a separate Admin API key, and the docs say twice
that the Admin API is unavailable for individual accounts. So this counts the
tokens the responses already carry, which is exact, free, and attributable to
radar rather than to the whole key.

Money is stored in integer MICROS. A float here accumulates rounding every
call and then reports a total nobody can reconcile against a bank statement.
"""
import datetime as dt

import pytest

from app import app as flask_app
from extensions import db
from models import RadarLlmSpend
from features.radar import spend

TODAY = dt.date(2026, 8, 25)
MODEL = 'claude-haiku-4-5'


@pytest.fixture()
def clean_spend():
    with flask_app.app_context():
        RadarLlmSpend.query.filter(
            RadarLlmSpend.day >= dt.date(2026, 8, 1)).delete(
                synchronize_session=False)
        db.session.commit()
        yield
        RadarLlmSpend.query.filter(
            RadarLlmSpend.day >= dt.date(2026, 8, 1)).delete(
                synchronize_session=False)
        db.session.commit()


def test_a_days_first_call_creates_its_row(clean_spend):
    with flask_app.app_context():
        spend.record(MODEL, calls=1, input_tokens=2000, output_tokens=300,
                     day=TODAY)

        row = RadarLlmSpend.query.filter_by(day=TODAY, model=MODEL).one()
        assert row.calls == 1
        assert row.input_tokens == 2000
        assert row.output_tokens == 300


def test_later_calls_accumulate_onto_the_same_day(clean_spend):
    with flask_app.app_context():
        spend.record(MODEL, calls=1, input_tokens=2000, output_tokens=300,
                     day=TODAY)
        spend.record(MODEL, calls=2, input_tokens=1000, output_tokens=100,
                     day=TODAY)

        row = RadarLlmSpend.query.filter_by(day=TODAY, model=MODEL).one()
        assert (row.calls, row.input_tokens, row.output_tokens) == (3, 3000, 400)


def test_cost_is_computed_at_the_rate_that_applied(clean_spend):
    """Haiku 4.5 is $1.00/MTok in and $5.00/MTok out.

    1M input plus 1M output is $1.00 + $5.00 = $6.00 = 6,000,000 micros.
    """
    with flask_app.app_context():
        spend.record(MODEL, calls=1, input_tokens=1_000_000,
                     output_tokens=1_000_000, day=TODAY)

        row = RadarLlmSpend.query.filter_by(day=TODAY, model=MODEL).one()
        assert row.cost_micros == 6_000_000


def test_cost_is_frozen_rather_than_recomputed(clean_spend):
    """Stored, not derived from the current price list.

    Tokens are the fact and the rate is the fact at the time. Recomputing an
    old day against a new price would silently restate what was actually paid,
    which is the one thing a spend figure exists not to do.
    """
    with flask_app.app_context():
        spend.record(MODEL, calls=1, input_tokens=1_000_000, output_tokens=0,
                     day=TODAY)
        before = RadarLlmSpend.query.filter_by(day=TODAY, model=MODEL).one().cost_micros

        # A price rise must not reach backwards.
        original = dict(spend.MODEL_RATES)
        spend.MODEL_RATES[MODEL] = (99.0, 99.0)
        try:
            after = RadarLlmSpend.query.filter_by(
                day=TODAY, model=MODEL).one().cost_micros
            assert after == before
        finally:
            spend.MODEL_RATES.clear()
            spend.MODEL_RATES.update(original)


def test_an_unpriced_model_records_tokens_and_no_cost(clean_spend):
    """A model nobody put a rate in for still gets its usage counted.

    Guessing a price would produce a number that looks authoritative and is
    invented; dropping the row would lose the tokens too.
    """
    with flask_app.app_context():
        spend.record('claude-some-future-model', calls=1, input_tokens=500,
                     output_tokens=50, day=TODAY)

        row = RadarLlmSpend.query.filter_by(model='claude-some-future-model').one()
        assert row.input_tokens == 500
        assert row.cost_micros == 0


def test_nothing_is_written_for_a_call_that_used_nothing(clean_spend):
    """A failed batch reports no usage. A zero row would make an outage look
    like a quiet day, which is the same confusion the bucket statuses exist to
    prevent."""
    with flask_app.app_context():
        spend.record(MODEL, calls=0, input_tokens=0, output_tokens=0, day=TODAY)

        assert RadarLlmSpend.query.filter_by(day=TODAY).count() == 0


def test_the_summary_reports_today_and_the_month(clean_spend):
    with flask_app.app_context():
        spend.record(MODEL, calls=1, input_tokens=1_000_000, output_tokens=0,
                     day=TODAY)
        spend.record(MODEL, calls=1, input_tokens=2_000_000, output_tokens=0,
                     day=TODAY - dt.timedelta(days=5))

        got = spend.summary(today=TODAY)

        assert got['today_usd'] == pytest.approx(1.00)
        assert got['month_usd'] == pytest.approx(3.00)


def test_the_summary_returns_floats_not_decimals(clean_spend):
    """SUM() over a BIGINT returns Decimal on MySQL and MariaDB, and Flask's
    JSON encoder raises on Decimal.

    So the board would 500 the moment the first spend row existed and not one
    moment sooner -- green tests, green page, then a dead dashboard the first
    time the sentiment pass books anything. pytest.approx compares Decimal and
    float happily, which is why every other assertion here missed it.
    """
    with flask_app.app_context():
        spend.record(MODEL, calls=1, input_tokens=1_000_000, output_tokens=0,
                     day=TODAY)

        got = spend.summary(today=TODAY)

        assert isinstance(got['today_usd'], float)
        assert isinstance(got['month_usd'], float)


def test_the_month_stops_at_the_first_of_the_month(clean_spend):
    """Month-to-date, not a rolling thirty days -- it is read against what was
    loaded onto the account, and that is billed by calendar month."""
    with flask_app.app_context():
        spend.record(MODEL, calls=1, input_tokens=1_000_000, output_tokens=0,
                     day=dt.date(2026, 8, 1))
        spend.record(MODEL, calls=1, input_tokens=5_000_000, output_tokens=0,
                     day=dt.date(2026, 7, 31))

        got = spend.summary(today=TODAY)

        assert got['month_usd'] == pytest.approx(1.00)
