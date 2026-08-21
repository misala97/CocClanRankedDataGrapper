# personal_apps/tests/test_radar_daemon.py
"""Cadence follows the NYSE session, not a fixed interval and not German local
time (spec 4.3, 4.4).

The DST case is the one that would otherwise ship broken: for about three weeks
each spring the US session starts an hour earlier in Berlin, and any cadence
keyed on Berlin hours would poll at overnight rates through a live open.
"""
import datetime as dt

import run_radar_ingest as daemon


def _utc(year, month, day, hour, minute=0):
    return dt.datetime(year, month, day, hour, minute, tzinfo=dt.timezone.utc)


def test_premarket_and_regular_poll_fastest():
    assert daemon.interval_for('premarket') == 180
    assert daemon.interval_for('regular') == 180


def test_afterhours_is_slower():
    assert daemon.interval_for('afterhours') == 600


def test_closed_is_slowest():
    assert daemon.interval_for('closed') == 1800


def test_an_unknown_state_falls_back_to_the_slow_interval():
    """A typo or a new state must not accidentally hammer the API."""
    assert daemon.interval_for('nonsense') == 1800


def test_interval_during_a_live_session_is_the_fast_one():
    assert daemon.interval_for(daemon.current_state(_utc(2026, 4, 15, 14))) == 180


def test_interval_during_the_dst_desync_window():
    """2026-03-16 13:45 UTC is 09:45 ET -- open -- but only 14:45 in Berlin,
    an hour earlier than the usual German open."""
    state = daemon.current_state(_utc(2026, 3, 16, 13, 45))
    assert state == 'regular'
    assert daemon.interval_for(state) == 180


def test_tick_returns_the_cycle_summary(monkeypatch):
    monkeypatch.setattr(daemon.ingest, 'run_cycle',
                        lambda now, fetchers: {'per_source': {}, 'mentions': 3,
                                              'buckets_written': 1,
                                              'catchup_depth': 1,
                                              'posts_seen': 3, 'posts_new': 3})
    result = daemon.tick(_utc(2026, 4, 15, 14),
                         fetchers={'stocktwits': lambda s: None})
    assert result['mentions'] == 3


def test_a_cycle_that_raises_does_not_kill_the_daemon(monkeypatch):
    """APScheduler drops a job whose function raises. Losing ingest until the
    next restart is worse than losing one cycle."""
    def boom(now, fetchers):
        raise RuntimeError('provider exploded')

    monkeypatch.setattr(daemon.ingest, 'run_cycle', boom)
    result = daemon.tick(_utc(2026, 4, 15, 14),
                         fetchers={'stocktwits': lambda s: None})
    assert result['status'] == 'error'


def test_every_configured_source_gets_a_fetcher():
    fetchers = daemon.build_fetchers()
    assert set(fetchers) == set(daemon.SOURCES)
    assert all(callable(f) for f in fetchers.values())


def test_reddit_is_gone():
    """Reddit closed self-serve API access. A leftover module is a trap: it
    imports cleanly and fails only at runtime, against a wall that is not
    coming down."""
    import importlib
    import pytest
    with pytest.raises(ImportError):
        importlib.import_module('features.radar.sources.reddit')


def test_the_request_budget_is_a_sane_fraction_of_the_hourly_one():
    """StockTwits publishes no limit; this is a conservative guess with
    adaptive backoff, not a documented ceiling."""
    assert 1 <= daemon.SYMBOL_BUDGET_PER_CYCLE <= 40
