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


def test_the_first_cycle_is_scheduled_immediately():
    """An interval trigger fires only after the interval elapses. Overnight
    that is thirty minutes of silence after starting the service, which reads
    as a dead daemon."""
    import inspect
    source = inspect.getsource(daemon.main)
    assert 'next_run_time' in source, 'first cycle would wait a full interval'


def _stub_scheduling(monkeypatch, due):
    monkeypatch.setattr(daemon.scheduling, 'ensure_tracked',
                        lambda *a, **k: 0)
    monkeypatch.setattr(daemon.scheduling, 'due_symbols',
                        lambda *a, **k: list(due))
    monkeypatch.setattr(daemon.scheduling, 'record_poll', lambda *a, **k: None)


def test_a_blocked_source_reports_missing_not_ok(monkeypatch):
    """Live on the VPS, StockTwits 403'd every request and the cycle recorded
    it as `ok` with zero counts -- because trending failed, the poll set was
    empty, and an empty symbol list short-circuits to success. Thirty days of
    those zeros would make the first real data look like an enormous spike."""
    import datetime as dt

    def blocked(*a, **k):
        raise daemon.stocktwits.StockTwitsUnavailable('403 Forbidden')

    monkeypatch.setattr(daemon.stocktwits, 'trending', blocked)
    _stub_scheduling(monkeypatch, due=[])

    result = daemon._stocktwits_fetcher(object())(dt.datetime(2026, 8, 21))
    assert result.status == 'missing'
    assert result.posts == []


def test_nothing_due_on_a_healthy_source_is_still_ok(monkeypatch):
    """The distinction the bug collapsed: no work to do is a real zero, and
    only a failure is `missing`."""
    import datetime as dt

    monkeypatch.setattr(daemon.stocktwits, 'trending', lambda c: ['AAA'])
    _stub_scheduling(monkeypatch, due=[])

    result = daemon._stocktwits_fetcher(object())(dt.datetime(2026, 8, 21))
    assert result.status == 'ok'


def test_scoring_covers_every_configured_source(monkeypatch):
    seen = []
    monkeypatch.setattr(daemon.scoring, 'score_source',
                        lambda source, now, **k: seen.append(source) or 1)
    daemon.score_all(_utc(2026, 8, 21, 14))
    assert set(seen) == set(daemon.SOURCES)


def test_one_source_failing_to_score_does_not_stop_the_others(monkeypatch):
    """Same rule as ingest. A bad baseline on one source is not a reason to
    leave the others unscored."""
    def flaky(source, now, **k):
        if source == 'bluesky':
            raise RuntimeError('bad baseline')
        return 3

    monkeypatch.setattr(daemon.scoring, 'score_source', flaky)
    result = daemon.score_all(_utc(2026, 8, 21, 14))
    assert result['bluesky'] == 0
    assert result['stocktwits'] == 3


def test_quote_polling_targets_the_loudest_tickers(monkeypatch):
    """The free tier is 60 calls a minute, so quotes go to the tickers actually
    on the board rather than to all 12,000 in the universe."""
    asked = {}

    class FakeProvider:
        def quotes(self, symbols):
            asked['symbols'] = list(symbols)
            return {}

    monkeypatch.setattr(daemon, '_loud_tickers', lambda now, limit: ['AAA', 'BBB'])
    monkeypatch.setattr(daemon.quotes, 'record_quotes', lambda q, now: 0)
    daemon.poll_quotes(_utc(2026, 8, 21, 14), FakeProvider(), limit=50)
    assert asked['symbols'] == ['AAA', 'BBB']


def test_a_dead_provider_does_not_kill_the_job(monkeypatch):
    class Dead:
        def quotes(self, symbols):
            raise RuntimeError('provider down')

    monkeypatch.setattr(daemon, '_loud_tickers', lambda now, limit: ['AAA'])
    result = daemon.poll_quotes(_utc(2026, 8, 21, 14), Dead())
    assert result['stored'] == 0
    assert result['error'] is True


def test_nothing_loud_means_no_provider_call(monkeypatch):
    """An empty board must not burn rate limit on a call with no symbols."""
    called = {'n': 0}

    class Counting:
        def quotes(self, symbols):
            called['n'] += 1
            return {}

    monkeypatch.setattr(daemon, '_loud_tickers', lambda now, limit: [])
    daemon.poll_quotes(_utc(2026, 8, 21, 14), Counting())
    assert called['n'] == 0


def test_sigma_refresh_covers_the_board(monkeypatch):
    """Volatility changes on the scale of weeks, so it refreshes on its own
    slow schedule rather than per page load."""
    asked = {}

    def fake_refresh(tickers, now):
        asked['tickers'] = list(tickers)
        return len(asked['tickers'])

    monkeypatch.setattr(daemon, '_loud_tickers', lambda now, limit: ['AAA', 'BBB'])
    monkeypatch.setattr(daemon.quotes, 'refresh_sigma', fake_refresh)
    assert daemon.refresh_volatility(_utc(2026, 8, 21, 14)) == 2
    assert asked['tickers'] == ['AAA', 'BBB']


def test_a_failing_sigma_refresh_is_contained(monkeypatch):
    def boom(tickers, now):
        raise RuntimeError('sigma blew up')

    monkeypatch.setattr(daemon, '_loud_tickers', lambda now, limit: ['AAA'])
    monkeypatch.setattr(daemon.quotes, 'refresh_sigma', boom)
    assert daemon.refresh_volatility(_utc(2026, 8, 21, 14)) == 0


def test_an_empty_board_needs_no_volatility_call(monkeypatch):
    called = {'n': 0}

    def counting(tickers, now):
        called['n'] += 1
        return 0

    monkeypatch.setattr(daemon, '_loud_tickers', lambda now, limit: [])
    monkeypatch.setattr(daemon.quotes, 'refresh_sigma', counting)
    daemon.refresh_volatility(_utc(2026, 8, 21, 14))
    assert called['n'] == 0


# Company profiles. There was no job for this until 2026-08-22: market_cap was
# NULL for every one of the 12,595 universe rows, so universe.segment_for()
# returned Unknown for every ticker and the segment selector -- an explicit
# product requirement -- had never worked in production.

def test_profiles_are_refreshed_for_the_board(monkeypatch):
    seen = {}

    def fake_refresh(provider, symbols, now):
        seen['symbols'] = list(symbols)
        return len(symbols)

    monkeypatch.setattr(daemon, '_profiles_due', lambda now, limit: ['AAA', 'BBB'])
    monkeypatch.setattr(daemon.universe, 'refresh_profiles', fake_refresh)

    assert daemon.refresh_profiles(_utc(2026, 8, 21, 14), object()) == 2
    assert seen['symbols'] == ['AAA', 'BBB']


def test_an_empty_board_spends_no_profile_calls(monkeypatch):
    called = {'n': 0}

    def counting(provider, symbols, now):
        called['n'] += 1
        return 0

    monkeypatch.setattr(daemon, '_profiles_due', lambda now, limit: [])
    monkeypatch.setattr(daemon.universe, 'refresh_profiles', counting)

    daemon.refresh_profiles(_utc(2026, 8, 21, 14), object())
    assert called['n'] == 0


def test_a_failing_profile_provider_does_not_kill_the_cycle(monkeypatch):
    """APScheduler drops a job whose function raises, so an unhandled error
    would silently end profile refreshes until the next restart."""
    def boom(provider, symbols, now):
        raise RuntimeError('provider down')

    monkeypatch.setattr(daemon, '_profiles_due', lambda now, limit: ['AAA'])
    monkeypatch.setattr(daemon.universe, 'refresh_profiles', boom)

    assert daemon.refresh_profiles(_utc(2026, 8, 21, 14), object()) == 0


def test_the_daemon_schedules_a_profile_job():
    """The regression this pins is an omission, not a bug: every other piece
    of the profile path existed and worked, and nothing called it."""
    import inspect
    source = inspect.getsource(daemon.main)

    assert "id='radar_profiles'" in source
    assert '_scheduled_profiles' in source


# Daily closes. The binding constraint is Twelve Data's eight requests a
# minute, not its 800/day quota, so what the job spends its cycle on matters
# more than how often it runs.

def test_history_is_fetched_for_tickers_that_have_none(monkeypatch):
    seen = {}

    def fake_fetch(provider, tickers, now):
        seen['tickers'] = list(tickers)
        return len(tickers)

    monkeypatch.setattr(daemon, '_loud_tickers', lambda now, limit: ['AAA', 'BBB'])
    monkeypatch.setattr(daemon.history, 'tickers_needing_history',
                        lambda candidates, today: ['BBB'])
    monkeypatch.setattr(daemon.history, 'fetch_into_store', fake_fetch)

    assert daemon.refresh_history(_utc(2026, 8, 21, 14), object()) == 1
    assert seen['tickers'] == ['BBB']


def test_the_history_job_respects_its_per_cycle_cap(monkeypatch):
    """Eight requests a minute is the real ceiling. A cycle that asked for
    everything would trip it and lose the whole batch."""
    asked = {}

    def fake_fetch(provider, tickers, now):
        asked['n'] = len(tickers)
        return len(tickers)

    many = [f'T{n}' for n in range(100)]
    monkeypatch.setattr(daemon, '_loud_tickers', lambda now, limit: many)
    monkeypatch.setattr(daemon.history, 'tickers_needing_history',
                        lambda candidates, today: list(candidates))
    monkeypatch.setattr(daemon.history, 'fetch_into_store', fake_fetch)

    daemon.refresh_history(_utc(2026, 8, 21, 14), object(), limit=20)
    assert asked['n'] == 20


def test_a_failing_history_provider_does_not_kill_the_cycle(monkeypatch):
    def boom(provider, tickers, now):
        raise RuntimeError('provider down')

    monkeypatch.setattr(daemon, '_loud_tickers', lambda now, limit: ['AAA'])
    monkeypatch.setattr(daemon.history, 'tickers_needing_history',
                        lambda candidates, today: ['AAA'])
    monkeypatch.setattr(daemon.history, 'fetch_into_store', boom)

    assert daemon.refresh_history(_utc(2026, 8, 21, 14), object()) == 0


def test_nothing_due_spends_no_requests(monkeypatch):
    called = {'n': 0}

    def counting(provider, tickers, now):
        called['n'] += 1
        return 0

    monkeypatch.setattr(daemon, '_loud_tickers', lambda now, limit: ['AAA'])
    monkeypatch.setattr(daemon.history, 'tickers_needing_history',
                        lambda candidates, today: [])
    monkeypatch.setattr(daemon.history, 'fetch_into_store', counting)

    daemon.refresh_history(_utc(2026, 8, 21, 14), object())
    assert called['n'] == 0


def test_the_daemon_schedules_a_history_job():
    """The profile job shipped unscheduled and nothing caught it, because the
    defect was an absence. Assert the registration itself."""
    import inspect
    source = inspect.getsource(daemon.main)

    assert "id='radar_history'" in source
    assert '_scheduled_history' in source
