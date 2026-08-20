# personal_apps/tests/test_radar_scheduling.py
"""Poll interval derives from each symbol's own message rate.

The API returns 30 messages whatever their timespan, so a fixed interval is
wrong in both directions at once: MSFT at 5.8 msgs/hr has five hours of
coverage and polling it every 15 minutes refetches the same data twenty times,
while BTC.X at 63/hr burns through 30 messages in 28 minutes and an hourly poll
loses data permanently (spec 3.5).
"""
import datetime as dt

import pytest

from app import app as flask_app
from extensions import db
from models import RadarPollState
from features.radar import scheduling

NOW = dt.datetime(2026, 8, 21, 14, 0, 0)


@pytest.fixture()
def ctx():
    with flask_app.app_context():
        RadarPollState.query.filter(
            RadarPollState.symbol.like('ZZ%')).delete(synchronize_session=False)
        db.session.commit()
        yield
        RadarPollState.query.filter(
            RadarPollState.symbol.like('ZZ%')).delete(synchronize_session=False)
        db.session.commit()


def test_a_hot_symbol_is_polled_at_the_floor():
    """63 msgs/hr means 30 messages last 28 minutes. Half of that is under the
    floor, so it polls as often as we allow."""
    assert scheduling.interval_for_rate(63.0) == dt.timedelta(minutes=15)


def test_a_quiet_symbol_is_polled_at_the_ceiling():
    """0.2 msgs/hr covers 150 hours. Polling hourly would be pure waste."""
    assert scheduling.interval_for_rate(0.2) == dt.timedelta(hours=4)


def test_a_middling_symbol_lands_between():
    """5.8 msgs/hr -- MSFT -- covers 5.2 hours; half of that is 2.6."""
    interval = scheduling.interval_for_rate(5.8)
    assert dt.timedelta(hours=2) < interval < dt.timedelta(hours=3)


def test_an_unmeasured_symbol_gets_the_floor():
    """No rate yet means poll it soon and find out."""
    assert scheduling.interval_for_rate(None) == dt.timedelta(minutes=15)
    assert scheduling.interval_for_rate(0.0) == dt.timedelta(hours=4)


def test_tracking_a_symbol_makes_it_immediately_due(ctx):
    scheduling.ensure_tracked('stocktwits', ['ZZA'], NOW)
    assert 'ZZA' in scheduling.due_symbols('stocktwits', NOW, limit=10)


def test_a_polled_symbol_is_not_due_again_until_its_interval_passes(ctx):
    scheduling.ensure_tracked('stocktwits', ['ZZA'], NOW)
    scheduling.record_poll('stocktwits', 'ZZA', NOW, rate=5.8)
    assert scheduling.due_symbols('stocktwits', NOW, limit=10) == []
    later = NOW + dt.timedelta(hours=3)
    assert 'ZZA' in scheduling.due_symbols('stocktwits', later, limit=10)


def test_a_symbol_that_heats_up_is_polled_sooner(ctx):
    """Self-correcting: the schedule tightens before anything is missed."""
    scheduling.ensure_tracked('stocktwits', ['ZZA'], NOW)
    scheduling.record_poll('stocktwits', 'ZZA', NOW, rate=0.5)
    cold_due = RadarPollState.query.filter_by(source='stocktwits', symbol='ZZA').one().next_due_at

    scheduling.record_poll('stocktwits', 'ZZA', NOW, rate=90.0)
    hot_due = RadarPollState.query.filter_by(source='stocktwits', symbol='ZZA').one().next_due_at
    assert hot_due < cold_due


def test_due_symbols_respects_the_request_budget(ctx):
    scheduling.ensure_tracked('stocktwits', ['ZZ%02d' % i for i in range(20)], NOW)
    assert len(scheduling.due_symbols('stocktwits', NOW, limit=6)) == 6


def test_the_most_overdue_symbols_come_first(ctx):
    """With a budget smaller than the backlog, starving one symbol forever
    would leave a permanent hole in its baseline."""
    scheduling.ensure_tracked('stocktwits', ['ZZA', 'ZZB'], NOW)
    scheduling.record_poll('stocktwits', 'ZZA', NOW, rate=1.0)
    scheduling.record_poll('stocktwits', 'ZZB', NOW - dt.timedelta(hours=6), rate=1.0)
    assert scheduling.due_symbols('stocktwits', NOW + dt.timedelta(hours=5),
                                  limit=1) == ['ZZB']


def test_tracking_is_per_source(ctx):
    """The same symbol on two sources has two rates and two schedules."""
    scheduling.ensure_tracked('stocktwits', ['ZZA'], NOW)
    scheduling.record_poll('stocktwits', 'ZZA', NOW, rate=60.0)
    scheduling.ensure_tracked('othersource', ['ZZA'], NOW)
    assert 'ZZA' in scheduling.due_symbols('othersource', NOW, limit=5)
    assert scheduling.due_symbols('stocktwits', NOW, limit=5) == []
