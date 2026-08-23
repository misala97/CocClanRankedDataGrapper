# personal_apps/tests/test_radar_detail.py
"""One ticker's panel: the surface that answers "is this real".

The board can honestly say three venues are talking. Only this can show what
each venue said, and what the stock was doing for the three years before
anyone said anything -- which is the part that decides whether a spike is
worth acting on.

The chart tests below moved here from test_radar_board.py on 2026-08-23 when
the chart left the board payload. They are unchanged in substance: price and
chatter share one calendar axis, and the two kinds of gap in them mean
different things.
"""
import datetime as dt
import decimal

import pytest

from app import app as flask_app
from extensions import db
from features.radar import detail
from features.radar.config import source_config_version
from models import (RadarBucketSource, RadarDailyClose, TickerUniverse)

NOW = dt.datetime(2026, 3, 12, 15, 0, 0)
PREFIX = 'DT'
SPAN = detail.SPAN_DAYS['1Y']


@pytest.fixture()
def clean():
    def wipe():
        for model in (RadarBucketSource, RadarDailyClose):
            model.query.filter(model.ticker.like(f'{PREFIX}%')).delete(
                synchronize_session=False)
        TickerUniverse.query.filter(
            TickerUniverse.symbol.like(f'{PREFIX}%')).delete(
                synchronize_session=False)
        db.session.commit()

    with flask_app.app_context():
        wipe()
        yield
        wipe()


def bucket(ticker, minutes_ago=30, mentions=10, source='bluesky'):
    db.session.add(RadarBucketSource(
        ticker=ticker, bucket_start=NOW - dt.timedelta(minutes=minutes_ago),
        source=source, mention_count=mentions, high_confidence_count=mentions,
        low_count=0, distinct_authors=6, distinct_text_ratio=0.9,
        engagement_weighted_count=float(mentions), status='ok',
        source_config_version=source_config_version(),
        expected=1.0, variance=2.0, mention_z=5.0, baseline_days=30))


def close_on(ticker, days_ago, price='10'):
    db.session.add(RadarDailyClose(
        ticker=ticker, close_date=NOW.date() - dt.timedelta(days=days_ago),
        close=decimal.Decimal(price), fetched_at=NOW))


def chart_for(ticker, days=SPAN):
    """Build one chart the way the panel will, from the pieces under test."""
    start = NOW.date() - dt.timedelta(days=days - 1)
    from_dt = dt.datetime.combine(start, dt.time.min)
    stored = {row.close_date: row.close for row in
              RadarDailyClose.query.filter_by(ticker=ticker).all()}
    counts = detail.daily_counts([ticker], ['bluesky'], from_dt, NOW)
    watched = detail.first_watched_day(['bluesky'], from_dt, NOW)
    return detail.chart_for(ticker, start, days, stored, counts, watched)


# ------------------------------------------------------------------ chart ---
#
# Price and chatter on one calendar axis. The alignment is the whole reason
# they are one structure: a year holds ~252 trading days and 365 calendar
# days, so positioning each by its own index would drift them over a hundred
# days apart by December.

def test_the_chart_aligns_price_and_chatter_on_calendar_days(clean):
    bucket(f'{PREFIX}A')
    for offset in (0, 1, 2):
        close_on(f'{PREFIX}A', offset, str(10 + offset))
    db.session.commit()

    chart = chart_for(f'{PREFIX}A')

    assert len(chart.closes) == len(chart.chatter) == SPAN
    assert (NOW.date() - chart.start).days == SPAN - 1
    # Today is the last index of both arrays, so the two line up by date.
    assert float(chart.closes[-1]) == 10.0
    assert chart.chatter[-1] == 10


def test_a_day_the_market_did_not_trade_is_null_not_carried_forward(clean):
    """Null means no trade happened. The client draws the line across it;
    repeating the previous close here would invent a print."""
    bucket(f'{PREFIX}A')
    close_on(f'{PREFIX}A', 3)
    db.session.commit()

    chart = chart_for(f'{PREFIX}A')

    assert chart.closes[-1] is None
    assert float(chart.closes[-4]) == 10.0


def test_days_before_ingest_began_have_no_chatter_at_all(clean):
    """Not zero. We were not watching, and a zero bar would claim a silence we
    never observed -- the same rule the hourly series already follows."""
    bucket(f'{PREFIX}A')
    close_on(f'{PREFIX}A', 0)
    db.session.commit()

    chart = chart_for(f'{PREFIX}A')

    assert chart.chatter[0] is None
    assert chart.chatter[-1] == 10


def test_the_chart_reports_where_watching_began(clean):
    """The panel draws a boundary at this date. Without it, three years of
    price beside three days of chatter reads as three years of silence."""
    bucket(f'{PREFIX}A')
    close_on(f'{PREFIX}A', 0)
    db.session.commit()

    assert chart_for(f'{PREFIX}A').watched_from == NOW.date()


# ------------------------------------------------------------------- spans ---

def test_every_span_is_a_whole_number_of_calendar_days():
    """Indexed by calendar day, never trading day. A year holds ~252 of one
    and 365 of the other."""
    assert detail.SPAN_DAYS == {'1M': 30, '6M': 182, '1Y': 365, '3Y': 1095}


def test_the_longest_span_fits_inside_what_is_stored():
    """3Y draws 1095 calendar days, which is about 780 trading days. Asking
    for more than the store holds would render a truncated year as a complete
    one."""
    from features.radar import history

    assert history.HISTORY_DAYS >= detail.SPAN_DAYS['3Y'] * 252 / 365


def test_a_span_shorter_than_a_year_takes_the_recent_end(clean):
    bucket(f'{PREFIX}A')
    close_on(f'{PREFIX}A', 0, '99')
    close_on(f'{PREFIX}A', 200, '5')
    db.session.commit()

    month = chart_for(f'{PREFIX}A', detail.SPAN_DAYS['1M'])

    assert len(month.closes) == 30
    assert float(month.closes[-1]) == 99.0
    assert all(c is None for c in month.closes[:-1])
