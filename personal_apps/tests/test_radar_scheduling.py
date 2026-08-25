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
    # Scoped by SOURCE, not by symbol prefix: a live ingest cycle writes real
    # symbols into this table under its own source name, and a symbol-prefix
    # filter would leave them behind for due_symbols to return instead of the
    # fixtures'.
    with flask_app.app_context():
        RadarPollState.query.filter(
            RadarPollState.source.in_(['testsource', 'othersource2'])).delete(
            synchronize_session=False)
        db.session.commit()
        yield
        RadarPollState.query.filter(
            RadarPollState.source.in_(['testsource', 'othersource2'])).delete(
            synchronize_session=False)
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
    scheduling.ensure_tracked('testsource', ['ZZA'], NOW)
    assert 'ZZA' in scheduling.due_symbols('testsource', NOW, limit=10)


def test_a_polled_symbol_is_not_due_again_until_its_interval_passes(ctx):
    scheduling.ensure_tracked('testsource', ['ZZA'], NOW)
    scheduling.record_poll('testsource', 'ZZA', NOW, rate=5.8)
    assert scheduling.due_symbols('testsource', NOW, limit=10) == []
    later = NOW + dt.timedelta(hours=3)
    assert 'ZZA' in scheduling.due_symbols('testsource', later, limit=10)


def test_a_symbol_that_heats_up_is_polled_sooner(ctx):
    """Self-correcting: the schedule tightens before anything is missed."""
    scheduling.ensure_tracked('testsource', ['ZZA'], NOW)
    scheduling.record_poll('testsource', 'ZZA', NOW, rate=0.5)
    cold_due = RadarPollState.query.filter_by(source='testsource', symbol='ZZA').one().next_due_at

    scheduling.record_poll('testsource', 'ZZA', NOW, rate=90.0)
    hot_due = RadarPollState.query.filter_by(source='testsource', symbol='ZZA').one().next_due_at
    assert hot_due < cold_due


def test_due_symbols_respects_the_request_budget(ctx):
    scheduling.ensure_tracked('testsource', ['ZZ%02d' % i for i in range(20)], NOW)
    assert len(scheduling.due_symbols('testsource', NOW, limit=6)) == 6


def test_the_most_overdue_symbols_come_first(ctx):
    """With a budget smaller than the backlog, starving one symbol forever
    would leave a permanent hole in its baseline."""
    scheduling.ensure_tracked('testsource', ['ZZA', 'ZZB'], NOW)
    scheduling.record_poll('testsource', 'ZZA', NOW, rate=1.0)
    scheduling.record_poll('testsource', 'ZZB', NOW - dt.timedelta(hours=6), rate=1.0)
    assert scheduling.due_symbols('testsource', NOW + dt.timedelta(hours=5),
                                  limit=1) == ['ZZB']


def test_tracking_is_per_source(ctx):
    """The same symbol on two sources has two rates and two schedules."""
    scheduling.ensure_tracked('testsource', ['ZZA'], NOW)
    scheduling.record_poll('testsource', 'ZZA', NOW, rate=60.0)
    scheduling.ensure_tracked('othersource2', ['ZZA'], NOW)
    assert 'ZZA' in scheduling.due_symbols('othersource2', NOW, limit=5)
    assert scheduling.due_symbols('testsource', NOW, limit=5) == []


# --- The ceiling was starving the busy subreddits, 2026-08-25 ---------------

def test_a_near_silent_subreddit_is_not_polled_every_45_minutes():
    """Measured live: two hours of Reddit produced 179 mentions across 92
    tickers, and exactly ONE bucket cleared the eligibility floor.

    The cause was budget allocation, not extraction. `interval_for_rate` sizes
    the interval so the 25-entry feed does not roll over -- but the result was
    clamped to a 45-minute ceiling, so a subreddit producing 0.07 comments an
    hour was polled 1.33 times an hour. Nineteen polls per comment, while
    r/wallstreetbets -- which needs one every 1.8 minutes to keep up -- fought
    seventeen near-dead subreddits for the same 30 feeds an hour.
    """
    from features.radar.config import REDDIT_MAX_POLL, REDDIT_MIN_POLL
    from features.radar.scheduling import interval_for_rate

    quiet = interval_for_rate(0.07, floor=REDDIT_MIN_POLL,
                              ceiling=REDDIT_MAX_POLL, page_size=25)

    assert quiet >= dt.timedelta(hours=4), (
        'a subreddit producing one comment every 14 hours is still being '
        'polled every %s' % quiet)


def test_a_busy_subreddit_still_gets_the_floor():
    """Teeth. Raising the ceiling must not touch what a loud sub is given --
    r/wallstreetbets turns its feed over in under two minutes and what a slow
    poll misses is gone, not late."""
    from features.radar.config import REDDIT_MAX_POLL, REDDIT_MIN_POLL
    from features.radar.scheduling import interval_for_rate

    busy = interval_for_rate(818, floor=REDDIT_MIN_POLL,
                             ceiling=REDDIT_MAX_POLL, page_size=25)

    assert busy == REDDIT_MIN_POLL


def test_a_middling_subreddit_keeps_the_cadence_its_rate_implies():
    """The ceiling should bind only on subs whose own rate asks for less than
    it. r/stocks at 67 comments an hour wants roughly 20 minutes, and that
    must be unaffected by where the ceiling sits."""
    from features.radar.config import REDDIT_MAX_POLL, REDDIT_MIN_POLL
    from features.radar.scheduling import interval_for_rate

    middling = interval_for_rate(67, floor=REDDIT_MIN_POLL,
                                 ceiling=REDDIT_MAX_POLL, page_size=25)

    assert dt.timedelta(minutes=10) < middling < dt.timedelta(minutes=45)


def test_the_ceiling_cannot_lose_comments_it_was_not_going_to_lose():
    """The safety check on raising it: a subreddit slow enough to be pinned at
    the ceiling must not fill its 25-entry feed within one interval, or the
    change trades starvation for silent data loss."""
    from features.radar.config import REDDIT_MAX_POLL

    from features.radar.scheduling import SAFETY_FACTOR

    hours = REDDIT_MAX_POLL.total_seconds() / 3600
    # A sub is pinned at the ceiling when (25 / rate) * SAFETY_FACTOR exceeds
    # it, so the fastest pinned sub runs at this rate.
    fastest_pinned = 25 * SAFETY_FACTOR / hours
    fill_hours = 25 / fastest_pinned

    # Its feed must take substantially longer to fill than one interval, or
    # the change trades starvation for silent data loss.
    assert fill_hours >= 2 * hours, (
        'at a %sh ceiling the fastest pinned sub fills its feed in %.1fh'
        % (hours, fill_hours))


# --- Retiring a source's dropped symbols, 2026-08-25 ------------------------

def test_a_dropped_subreddit_stops_being_polled(ctx):
    """due_symbols filters by SOURCE, not by the configured list.

    So removing a subreddit from REDDIT_SUBS leaves its radar_poll_state row
    behind and the scheduler keeps handing it turns forever -- consuming
    exactly the request budget the removal was meant to free. The cut would
    have been a no-op, and a silent one: the sub would still appear in the
    logs, still cost feeds, and nothing would look wrong.
    """
    scheduling.ensure_tracked('testsource', ['ZZA', 'ZZB'], NOW)

    retired = scheduling.retire_untracked('testsource', ['ZZA'])

    assert retired == 1
    assert scheduling.due_symbols('testsource', NOW, limit=10) == ['ZZA']


def test_retiring_leaves_other_sources_alone(ctx):
    """One shared table, one row per (source, symbol). A reddit list edit must
    not reach into StockTwits' state."""
    scheduling.ensure_tracked('testsource', ['ZZA'], NOW)
    scheduling.ensure_tracked('othersource2', ['ZZB'], NOW)

    scheduling.retire_untracked('testsource', [])

    assert scheduling.due_symbols('othersource2', NOW, limit=10) == ['ZZB']


def test_retiring_nothing_is_not_retiring_everything(ctx):
    """The empty-list trap. `symbols` empty has to mean "this source tracks
    nothing", but an accidental empty config would then wipe live state -- so
    the caller that owns a fixed list is the only one allowed to call this,
    and StockTwits, whose hot set legitimately empties, never does."""
    scheduling.ensure_tracked('testsource', ['ZZA', 'ZZB'], NOW)

    assert scheduling.retire_untracked('testsource', ['ZZA', 'ZZB']) == 0
    assert len(scheduling.due_symbols('testsource', NOW, limit=10)) == 2
