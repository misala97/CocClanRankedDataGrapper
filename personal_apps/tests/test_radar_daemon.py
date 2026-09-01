# personal_apps/tests/test_radar_daemon.py
"""Cadence follows the NYSE session, not a fixed interval and not German local
time (spec 4.3, 4.4).

The DST case is the one that would otherwise ship broken: for about three weeks
each spring the US session starts an hour earlier in Berlin, and any cadence
keyed on Berlin hours would poll at overnight rates through a live open.
"""
import datetime as dt
import decimal
from types import SimpleNamespace

import pytest

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
                                              'aggregate_status': {},
                                              'catchup_depth': {},
                                              'posts_seen': 3, 'posts_new': 3})
    result = daemon.tick(_utc(2026, 4, 15, 14),
                         fetchers={'bluesky': lambda s: None})
    assert result['mentions'] == 3


def test_a_cycle_that_raises_does_not_kill_the_daemon(monkeypatch):
    """APScheduler drops a job whose function raises. Losing ingest until the
    next restart is worse than losing one cycle."""
    def boom(now, fetchers):
        raise RuntimeError('provider exploded')

    monkeypatch.setattr(daemon.ingest, 'run_cycle', boom)
    result = daemon.tick(_utc(2026, 4, 15, 14),
                         fetchers={'bluesky': lambda s: None})
    assert result['status'] == 'error'
    assert result['per_source'] == {}
    assert result['aggregate_status'] == {}
    assert result['catchup_depth'] == {}


def test_every_configured_source_gets_a_fetcher():
    fetchers = daemon.build_fetchers()
    assert set(fetchers) == set(daemon.SOURCES)
    assert all(callable(f) for f in fetchers.values())


def test_reddit_reads_the_feeds_and_never_the_closed_api():
    """Replaces test_reddit_is_gone, 2026-08-24.

    That test asserted the module must not exist, because Reddit closed
    self-serve API access and a leftover module would fail only at runtime.
    The premise was half right and it took measuring to find out: the JSON API
    really is shut, and app registration at reddit.com/prefs/apps really is
    dead, but the published Atom feeds answer 200 with no auth at all.

      /r/pennystocks/new.json   403
      /r/pennystocks/new.rss    200

    So the wall the old test described is real and still standing -- this just
    pins that we go around it rather than into it. A module that reached for
    /api/ or .json would fail on every request against a closed door, which is
    exactly the trap the original was written to prevent.
    """
    from features.radar.sources import reddit

    # Every URL the module can reach, rather than a grep over its text -- the
    # docstring necessarily mentions the .json route in order to explain why
    # it is not used, and a text search cannot tell an explanation from a call.
    urls = [value for value in vars(reddit).values()
            if isinstance(value, str) and value.startswith('http')]

    assert urls == [reddit.FEED], f'unexpected endpoint reachable: {urls}'
    assert '.rss' in reddit.FEED
    assert '.json' not in reddit.FEED


def test_reddit_runs_on_its_own_clock_not_the_market_session():
    """The regression: four subs per 1800-second overnight cycle meant a full
    rotation of eighteen took over two hours, against a feed that turns over
    in under two minutes. Six hours of it produced one scorable mention.

    Reddit does not stop at the closing bell, and a missed comment is gone
    rather than late -- there is no cursor to catch up from.
    """
    import inspect
    source = inspect.getsource(daemon.main)

    assert "id='radar_reddit'" in source, 'reddit has no job of its own'
    assert 'REDDIT_INTERVAL_SECONDS' in source, 'reddit rides the session interval'
    assert "if name != 'reddit'" in source, 'reddit is still in the session cycle'


def test_the_first_cycle_is_scheduled_immediately():
    """An interval trigger fires only after the interval elapses. Overnight
    that is thirty minutes of silence after starting the service, which reads
    as a dead daemon."""
    import inspect
    source = inspect.getsource(daemon.main)
    assert 'next_run_time' in source, 'first cycle would wait a full interval'


def test_scoring_covers_every_configured_source(monkeypatch):
    seen = []
    monkeypatch.setattr(daemon.scoring, 'score_source',
                        lambda source, now, **k: seen.append(source) or 1)
    daemon.score_all(_utc(2026, 8, 21, 14))
    expected = {'bluesky', 'fourchan'} | {
        'reddit:%s' % sub for sub in daemon.REDDIT_SUBS}
    assert set(seen) == expected
    assert 'reddit' not in seen


def test_reddit_poll_state_stays_keyed_to_the_root_source(monkeypatch):
    """Concrete post names must not retire the scheduler's learned state."""
    from app import app as flask_app
    from extensions import db
    from features.radar.sources import FetchResult
    from models import RadarPollState

    sub = 'zz_task9_sub'
    root = 'reddit'
    concrete = 'reddit:%s' % sub
    owned_sources = (root, concrete)
    now = dt.datetime(2026, 8, 27, 12, 0, 0)

    def wipe_owned_state():
        RadarPollState.query.filter(
            RadarPollState.source.in_(owned_sources),
            RadarPollState.symbol == sub).delete(synchronize_session=False)
        db.session.commit()

    with flask_app.app_context():
        wipe_owned_state()
        monkeypatch.setattr(daemon, 'REDDIT_SUBS', (sub,))
        monkeypatch.setattr(daemon, '_utcnow', lambda: now)
        monkeypatch.setattr(daemon.scheduling, 'retire_untracked',
                            lambda source, symbols: 0)
        monkeypatch.setattr(daemon.scheduling, 'due_symbols',
                            lambda source, current, limit: [sub])
        monkeypatch.setattr(
            daemon.reddit, 'fetch',
            lambda since_by_sub, client: FetchResult(
                posts=[], status='ok', rates={sub: 0.0},
                per_source_status={concrete: 'ok'}))

        try:
            daemon._reddit_fetcher(object())(now - dt.timedelta(minutes=5))
            rows = RadarPollState.query.filter(
                RadarPollState.source.in_(owned_sources),
                RadarPollState.symbol == sub).all()
            assert [(row.source, row.symbol) for row in rows] == [(root, sub)]
        finally:
            db.session.rollback()
            wipe_owned_state()


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
    assert result['fourchan'] == 3


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


def test_german_quote_failure_does_not_block_us_quotes(monkeypatch):
    """A denied German entitlement is not a US board outage."""
    us = SimpleNamespace(ticker='AAA', market='us', venue='Nasdaq', mic='XNAS',
                         provider_symbol='AAA', currency='USD')
    de = SimpleNamespace(ticker='AAA', market='de', venue='Xetra', mic='XETR',
                         provider_symbol='AAA1', currency='EUR')
    calls = []

    class UsProvider:
        def quotes(self, symbols):
            calls.append(('us', list(symbols)))
            from features.radar.prices import Quote
            return {'AAA': Quote('AAA', decimal.Decimal('220.00'),
                                 currency='USD')}

    class DeniedGermany:
        def quotes(self, symbols):
            calls.append(('de', list(symbols)))
            raise RuntimeError('entitlement denied')

    monkeypatch.setattr(daemon, '_loud_tickers', lambda now, limit: ['AAA'])
    monkeypatch.setattr(daemon, 'has_app_context', lambda: True)
    monkeypatch.setattr(
        daemon, '_market_instruments',
        lambda tickers, market: [us] if market == 'us' else [de])
    monkeypatch.setattr(daemon, '_mapping_refresh_due', lambda now: True)
    monkeypatch.setattr(daemon.instruments, 'refresh_mappings',
                        lambda provider, now: calls.append(('mapping', provider)))
    monkeypatch.setattr(daemon.quotes, 'record_quotes', lambda found, now: len(found))

    mapping_provider = object()
    result = daemon.poll_quotes(
        _utc(2026, 8, 21, 14), UsProvider(), de_provider=DeniedGermany(),
        mapping_provider=mapping_provider)

    assert result['us_stored'] == 1
    assert result['de_stored'] == 0
    assert result['de_error'] is True
    assert calls == [('us', ['AAA']), ('mapping', mapping_provider),
                     ('de', ['AAA1'])]


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


def test_the_nightly_prune_covers_quotes_as_well_as_posts():
    """The regression here is an omission, like the profile job's.

    retention.py handled posts and mentions and never touched radar_quotes,
    so that table grew without bound -- and since the board started reading it
    on every load it is the one most able to undo the work that made it fast.
    Asserting both are called, because the failure mode is a function that
    exists and is never reached.

    All three pruners are faked here, never the real ones: the real
    prune_mention_events would run against actual current time, and the
    shared dev database's radar_mention_events rows are all older than the
    48-hour retention window by the time this suite runs -- an unfaked call
    would delete every real row in the table.
    """
    called = []

    daemon.retention.prune_posts, real_posts = (
        lambda now: called.append('posts') or 0, daemon.retention.prune_posts)
    daemon.retention.prune_quotes, real_quotes = (
        lambda now: called.append('quotes') or 0, daemon.retention.prune_quotes)
    daemon.retention.prune_mention_events, real_events = (
        lambda now: called.append('events') or 0, daemon.retention.prune_mention_events)
    try:
        daemon._scheduled_prune()
    finally:
        daemon.retention.prune_posts = real_posts
        daemon.retention.prune_quotes = real_quotes
        daemon.retention.prune_mention_events = real_events

    assert called == ['posts', 'quotes', 'events']


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
    # This is the mixed-version path: no primary instruments have been seeded
    # yet, so refresh_history must retain the old ticker-only request instead
    # of reaching into the application database from this unit test.
    monkeypatch.setattr(daemon, '_market_instruments',
                        lambda tickers, market: [])
    monkeypatch.setattr(daemon.history, 'tickers_needing_history',
                        lambda candidates, today: ['BBB'])
    monkeypatch.setattr(daemon.history, 'fetch_into_store', fake_fetch)

    assert daemon.refresh_history(_utc(2026, 8, 21, 14), object()) == 1
    assert seen['tickers'] == ['BBB']


def test_us_history_uses_the_primary_instrument_mic_and_provider_symbol(monkeypatch):
    instrument = SimpleNamespace(
        ticker='AAA', market='us', venue='NYSE', mic='XNYS',
        provider_symbol='AAA.US', currency='USD')
    seen = {}

    def fake_fetch(provider, tickers, now, **kwargs):
        seen['tickers'] = list(tickers)
        seen.update(kwargs)
        return len(tickers)

    monkeypatch.setattr(daemon, '_loud_tickers', lambda now, limit: ['AAA'])
    monkeypatch.setattr(daemon, '_market_instruments',
                        lambda tickers, market: [instrument] if market == 'us' else [])
    monkeypatch.setattr(daemon.history, 'tickers_needing_history',
                        lambda candidates, today, **kwargs: list(candidates))
    monkeypatch.setattr(daemon.history, 'fetch_into_store', fake_fetch)

    assert daemon.refresh_history(_utc(2026, 8, 21, 14), object()) == 1
    assert seen == {
        'tickers': ['AAA'], 'market': 'us', 'mic': 'XNYS', 'currency': 'USD',
        'provider_symbols': {'AAA': 'AAA.US'},
    }


def test_the_history_job_respects_its_per_cycle_cap(monkeypatch):
    """Eight requests a minute is the real ceiling. A cycle that asked for
    everything would trip it and lose the whole batch."""
    asked = {}

    def fake_fetch(provider, tickers, now):
        asked['n'] = len(tickers)
        return len(tickers)

    many = [f'T{n}' for n in range(100)]
    monkeypatch.setattr(daemon, '_loud_tickers', lambda now, limit: many)
    monkeypatch.setattr(daemon, '_market_instruments',
                        lambda tickers, market: [])
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


def test_german_history_has_its_own_bound_and_provider_symbols(monkeypatch):
    de = SimpleNamespace(ticker='AAA', market='de', venue='Xetra', mic='XETR',
                         provider_symbol='APC', currency='EUR')
    seen = {}

    def fake_fetch(provider, tickers, now, **kwargs):
        seen['tickers'] = list(tickers)
        seen.update(kwargs)
        return len(tickers)

    monkeypatch.setattr(daemon, '_loud_tickers', lambda now, limit: ['AAA', 'BBB'])
    monkeypatch.setattr(daemon, '_market_instruments',
                        lambda tickers, market: [de] if market == 'de' else [])
    monkeypatch.setattr(daemon.history, 'tickers_needing_history',
                        lambda candidates, today, **kwargs: list(candidates))
    monkeypatch.setattr(daemon.history, 'fetch_into_store', fake_fetch)

    assert daemon.refresh_de_history(_utc(2026, 8, 21, 14), object(), limit=1) == 1
    assert seen == {
        'tickers': ['AAA'], 'market': 'de', 'mic': 'XETR', 'currency': 'EUR',
        'provider_symbols': {'AAA': 'APC'},
    }


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


def test_the_daemon_schedules_a_sentiment_job():
    """Same absence-shaped defect the history job's test documents.

    A pass nobody runs looks exactly like a pass that runs and finds nothing:
    every mention keeps answering on its lexicon score and the board renders
    normally, so the only evidence would be a column that never fills.
    """
    import inspect
    source = inspect.getsource(daemon.main)

    assert "id='radar_sentiment'" in source
    assert '_scheduled_sentiment' in source


def test_a_broken_sentiment_pass_does_not_take_the_daemon_down(monkeypatch):
    """It is an optional enrichment on top of ingest, and it is the only job
    here that depends on a third-party API key.

    An unset key raises at client construction, which would otherwise mean a
    missing environment variable silently costs the whole radar service --
    ingest, scoring, quotes and all -- to decorate a column nothing blocks on.
    """
    def explode():
        raise RuntimeError('ANTHROPIC_API_KEY is not set')

    monkeypatch.setattr(daemon.llm_sentiment, 'run_pass', explode)

    daemon._scheduled_sentiment()   # must not raise


def test_the_daemon_retires_subreddits_dropped_from_the_config():
    """due_symbols filters by SOURCE, not by REDDIT_SUBS.

    So a subreddit removed from the list keeps its radar_poll_state row and
    keeps being handed turns -- consuming exactly the request budget the
    removal was meant to free, and silently. Ten subs were dropped on
    2026-08-25; without this the cut would have changed nothing at all.
    """
    import inspect
    source = inspect.getsource(daemon._reddit_fetcher)

    assert 'retire_untracked' in source


# Task 3c: generation 2 rebuilds buckets from the complete mention journal
# instead of one cursor slice, which changes measured volume even though the
# extractor's membership rules do not. _prepare_rollup_generation is the
# one-time startup pass that keeps that correction from silently mixing with
# understated pre-fix history. The end-to-end version of this, against real
# rows, lives in
# tests/test_radar_journal.py::test_deploy_bootstrap_preserves_the_complete_open_bucket;
# these pin the daemon's own wiring and its fail-closed branch in isolation.

def test_prepare_rollup_generation_bootstraps_then_invalidates_then_commits(
        monkeypatch):
    """The call order is the contract: bootstrap has to land in the journal
    before anything downstream reads it, and invalidation is what actually
    clears the columns the leaderboard reads mention_z from."""
    calls = []

    def fake_bootstrap(since):
        calls.append(('bootstrap', since))
        return 3

    def fake_invalidate(version, since):
        calls.append(('invalidate', version, since))
        return 5

    monkeypatch.setattr(daemon.journal, 'bootstrap_from_mentions', fake_bootstrap)
    monkeypatch.setattr(daemon.scoring, 'invalidate_incompatible_scores',
                        fake_invalidate)
    monkeypatch.setattr(daemon.db.session, 'commit',
                        lambda: calls.append(('commit',)))

    now = _utc(2026, 4, 15, 15, 0)
    recovered, invalidated = daemon._prepare_rollup_generation(now)

    assert (recovered, invalidated) == (3, 5)
    assert [call[0] for call in calls] == ['bootstrap', 'invalidate', 'commit']
    since = now.replace(tzinfo=None) - dt.timedelta(
        hours=daemon.MENTION_EVENT_RETENTION_HOURS)
    assert calls[0][1] == since, 'bootstrap must see the retention-window floor'
    assert calls[1][2] == since, 'invalidation must share the same floor'
    assert calls[1][1] == daemon.source_config_version(), (
        'invalidation must receive the exact current generation')
    assert calls[2] == ('commit',), (
        'bootstrap and invalidation must be durable before startup continues')


def test_prepare_rollup_generation_fails_closed_on_unrecovered_legacy_evidence(
        monkeypatch):
    """Zero recovered is ambiguous by itself -- a fresh database and a
    migrated one whose bootstrap silently failed both report it. A legacy
    bucket already carrying high_confidence_count in the overlap window is
    what tells the two apart: it is proof the evidence existed, so recovering
    none of it means bootstrap is broken, not that the world was quiet.
    Continuing anyway would serve a relabelled score for evidence that never
    actually made it into the journal.

    The legacy-evidence check has no ticker filter -- production has to catch
    ANY source's bootstrap failure, not one ticker's -- so `now` is
    2027-06-01, beyond the real and seeded database history, so the global
    legacy-evidence query cannot match unrelated rows.
    """
    from app import app as flask_app
    from extensions import db
    from models import RadarBucketSource

    now = _utc(2027, 6, 1, 6, 0)
    since = now.replace(tzinfo=None) - dt.timedelta(
        hours=daemon.MENTION_EVENT_RETENTION_HOURS)
    with flask_app.app_context():
        RadarBucketSource.query.filter_by(ticker='ZZDAEMON').delete(
            synchronize_session=False)
        db.session.add(RadarBucketSource(
            ticker='ZZDAEMON', bucket_start=since + dt.timedelta(hours=1),
            source='bluesky', mention_count=9, high_confidence_count=6,
            low_count=0, distinct_authors=5, distinct_text_ratio=1.0,
            engagement_weighted_count=9.0, status='ok',
            source_config_version='old-generation'))
        db.session.commit()

    monkeypatch.setattr(daemon.journal, 'bootstrap_from_mentions', lambda s: 0)
    invalidate_called = []
    monkeypatch.setattr(daemon.scoring, 'invalidate_incompatible_scores',
                        lambda v, s: invalidate_called.append(True) or 0)

    try:
        with pytest.raises(RuntimeError):
            daemon._prepare_rollup_generation(now)
        assert not invalidate_called, (
            'a failed-closed bootstrap must never reach invalidation, or an '
            'ingest cycle could still slip in before the process actually exits')
    finally:
        with flask_app.app_context():
            RadarBucketSource.query.filter_by(ticker='ZZDAEMON').delete(
                synchronize_session=False)
            db.session.commit()


def test_prepare_rollup_generation_continues_when_the_database_is_genuinely_quiet(
        monkeypatch):
    """The complementary case: zero recovered with no legacy evidence in the
    overlap window at all is a fresh or genuinely quiet database, and the
    fail-closed check meant for a broken migration must not block it.

    Uses the same 2027-06-01 window as the fail-closed test, beyond the real
    and seeded database history.
    """
    from app import app as flask_app
    from extensions import db
    from models import RadarBucketSource

    now = _utc(2027, 6, 1, 6, 0)
    with flask_app.app_context():
        RadarBucketSource.query.filter_by(ticker='ZZQUIET').delete(
            synchronize_session=False)
        db.session.add(RadarBucketSource(
            ticker='ZZQUIET', bucket_start=now.replace(tzinfo=None),
            source='bluesky', mention_count=0, high_confidence_count=0,
            low_count=0, distinct_authors=0, distinct_text_ratio=1.0,
            engagement_weighted_count=0.0, status='missing',
            source_config_version='old-generation'))
        db.session.commit()

    monkeypatch.setattr(daemon.journal, 'bootstrap_from_mentions', lambda s: 0)
    invalidate_called = []
    monkeypatch.setattr(daemon.scoring, 'invalidate_incompatible_scores',
                        lambda v, s: invalidate_called.append(True) or 0)

    try:
        recovered, invalidated = daemon._prepare_rollup_generation(now)

        assert (recovered, invalidated) == (0, 0)
        assert invalidate_called, 'the quiet path must still reach invalidation'
    finally:
        with flask_app.app_context():
            RadarBucketSource.query.filter_by(ticker='ZZQUIET').delete(
                    synchronize_session=False)
            db.session.commit()


def test_main_prepares_the_rollup_generation_before_building_fetchers(monkeypatch):
    """No cycle may run against a mixed-generation database, so a bootstrap or
    invalidation failure has to prevent build_fetchers and the scheduler from
    ever existing -- not merely appear earlier than them in main()'s source
    text.

    This replaces a source-inspection version of the test that only checked
    substring order. The reviewer wrapped the _prepare_rollup_generation call
    in main() with `try/except Exception: recovered, invalidated = 0, 0` --
    the substrings stayed in the same order, so the old assertion kept
    passing, and all 40 daemon tests were still green, while the daemon would
    go on to start ingest over evidence it could not recover. Watching
    build_fetchers actually run, or not, is the only way to tell a real raise
    from one that got swallowed; main() raises on its first statement after
    logging config, so it never reaches the blocking scheduler loop.
    """
    def explode(now):
        raise RuntimeError('rollup generation bootstrap failed')

    called = []
    monkeypatch.setattr(daemon, '_prepare_rollup_generation', explode)
    monkeypatch.setattr(daemon, 'build_fetchers', lambda: called.append(True))

    with pytest.raises(RuntimeError):
        daemon.main()

    assert not called, ('a failed rollup-generation prepare must never reach '
                        'build_fetchers, or a cycle could run before the '
                        'process actually exits')


def test_manual_mapping_refresh_uses_the_catalog_provider(monkeypatch):
    """A manual operator refresh must run the same safe mapping path as cron."""
    seen = {}
    provider = object()
    from features.radar.instruments import MappingResult

    monkeypatch.setattr(daemon, '_mapping_provider', lambda: provider,
                        raising=False)
    monkeypatch.setattr(
        daemon.instruments, 'refresh_mappings',
        lambda selected, now: seen.update(provider=selected, now=now) or
        MappingResult(True, 2, 1, 1, 1))

    daemon.main(['--refresh-mappings'])

    assert seen['provider'] is provider
    assert seen['now'].tzinfo is dt.timezone.utc


def test_shadow_mode_mapping_job_builds_a_generation(monkeypatch):
    """R6 satisfied (§3.5/§3.6): shadow/active builds an OpenFIGI
    generation from the live reference catalogs instead of refusing."""
    from features.radar import reference_universe

    monkeypatch.setenv('RADAR_DE_PRICE_MODE', 'shadow')
    catalogs = {'XETR': object(), 'XGAT': object()}
    seen = {}
    generation = type('G', (), {'id': 7, 'payload_sha256': 'f' * 64})()

    monkeypatch.setattr(reference_universe, 'build_reference_catalogs',
                        lambda http, now: seen.update(now=now) or catalogs)
    monkeypatch.setattr(daemon.instruments, 'load_overrides',
                        lambda now=None: {})
    monkeypatch.setattr(
        daemon.instruments, 'build_generation',
        lambda provider, references, overrides, now:
        seen.update(references=references) or generation)
    monkeypatch.setattr(
        daemon.instruments, 'refresh_mappings',
        lambda provider, now: pytest.fail(
            'shadow mode must not run the legacy catalog refresh'))

    result = daemon._scheduled_mappings()

    assert result is generation
    assert seen['references'] is catalogs
    assert seen['now'].tzinfo is None


def test_shadow_mode_mapping_job_writes_nothing_on_incomplete_reference(
        monkeypatch, caplog):
    from features.radar import reference_universe
    from features.radar.instruments import IncompleteReference

    monkeypatch.setenv('RADAR_DE_PRICE_MODE', 'shadow')
    monkeypatch.setattr(reference_universe, 'build_reference_catalogs',
                        lambda http, now: {})
    monkeypatch.setattr(daemon.instruments, 'load_overrides',
                        lambda now=None: {})

    def refuse(provider, references, overrides, now):
        raise IncompleteReference('XGAT: official reference universe is '
                                  'not complete')
    monkeypatch.setattr(daemon.instruments, 'build_generation', refuse)

    with caplog.at_level('ERROR'):
        assert daemon._scheduled_mappings() is None
    assert any('reference incomplete' in record.message
               for record in caplog.records)


def test_shadow_mode_mapping_job_survives_a_provider_outage(monkeypatch):
    from features.radar import reference_universe
    from features.radar.prices import PriceUnavailable

    monkeypatch.setenv('RADAR_DE_PRICE_MODE', 'shadow')
    monkeypatch.setattr(reference_universe, 'build_reference_catalogs',
                        lambda http, now: {})
    monkeypatch.setattr(daemon.instruments, 'load_overrides',
                        lambda now=None: {})

    def outage(provider, references, overrides, now):
        raise PriceUnavailable('openfigi 429')
    monkeypatch.setattr(daemon.instruments, 'build_generation', outage)

    assert daemon._scheduled_mappings() is None


def test_mapping_success_details_are_read_inside_the_session(monkeypatch):
    """Production 2026-09-01: the success log read generation.id AFTER the
    app context closed -- DetachedInstanceError out of a job whose build
    had already committed. The fake here detaches exactly like the ORM:
    attribute reads outside an app context raise."""
    from flask import has_app_context
    from features.radar import reference_universe

    monkeypatch.setenv('RADAR_DE_PRICE_MODE', 'shadow')
    monkeypatch.setattr(reference_universe, 'build_reference_catalogs',
                        lambda http, now: {})
    monkeypatch.setattr(daemon.instruments, 'load_overrides',
                        lambda now=None: {})

    class DetachingGeneration:
        @property
        def id(self):
            if not has_app_context():
                raise RuntimeError('detached read')
            return 7

        @property
        def payload_sha256(self):
            if not has_app_context():
                raise RuntimeError('detached read')
            return 'f' * 64

    monkeypatch.setattr(
        daemon.instruments, 'build_generation',
        lambda provider, references, overrides, now: DetachingGeneration())

    result = daemon._scheduled_mappings()

    assert isinstance(result, DetachingGeneration)


def test_shadow_mode_mapping_job_never_lets_an_exception_escape(monkeypatch):
    """The scheduled job runs under APScheduler: an escaped exception would
    poison the job, so even an unforeseen error must degrade to None."""
    from features.radar import reference_universe

    monkeypatch.setenv('RADAR_DE_PRICE_MODE', 'shadow')

    def explode(http, now):
        raise RuntimeError('unforeseen')
    monkeypatch.setattr(reference_universe, 'build_reference_catalogs',
                        explode)

    assert daemon._scheduled_mappings() is None


def test_daemon_schedules_weekly_mapping_refresh(monkeypatch):
    """Mappings otherwise stay frozen after the deploy-time probe succeeds."""
    created = []

    class CapturingScheduler:
        def __init__(self, **kwargs):
            self.jobs = []
            created.append(self)

        def add_job(self, func, trigger, **kwargs):
            self.jobs.append((func, trigger, kwargs))

        def start(self):
            pass

        def shutdown(self):
            pass

    monkeypatch.setattr(daemon, 'BackgroundScheduler', CapturingScheduler)
    monkeypatch.setattr(daemon, '_prepare_rollup_generation', lambda now: (0, 0))
    monkeypatch.setattr(daemon, 'build_fetchers', lambda: {})
    monkeypatch.setattr(daemon.time, 'sleep',
                        lambda seconds: (_ for _ in ()).throw(KeyboardInterrupt))

    daemon.main([])

    jobs = {job[2]['id']: job for job in created[0].jobs}
    mapping = jobs['radar_mappings']
    assert mapping[0] is daemon._scheduled_mappings
    assert mapping[1] == 'interval'
    assert mapping[2]['weeks'] == 1
    assert mapping[2]['max_instances'] == 1
    assert mapping[2]['coalesce'] is True
    # Pre-v2 legacy cadence: weekly only, no startup fire.
    assert 'next_run_time' not in mapping[2]


def test_shadow_mode_builds_a_mapping_generation_shortly_after_restart(
        monkeypatch):
    """The German collector maps nothing without a generation; a restart
    under shadow must not wait a week for the first interval fire."""
    created = []

    class CapturingScheduler:
        def __init__(self, **kwargs):
            self.jobs = []
            created.append(self)

        def add_job(self, func, trigger, **kwargs):
            self.jobs.append((func, trigger, kwargs))

        def start(self):
            pass

        def shutdown(self):
            pass

    monkeypatch.setenv('RADAR_DE_PRICE_MODE', 'shadow')
    monkeypatch.setattr(daemon, 'BackgroundScheduler', CapturingScheduler)
    monkeypatch.setattr(daemon, '_prepare_rollup_generation', lambda now: (0, 0))
    monkeypatch.setattr(daemon, 'build_fetchers', lambda: {})
    monkeypatch.setattr(daemon.time, 'sleep',
                        lambda seconds: (_ for _ in ()).throw(KeyboardInterrupt))

    daemon.main([])

    mapping = {job[2]['id']: job for job in created[0].jobs}['radar_mappings']
    assert mapping[2]['weeks'] == 1
    assert mapping[2]['next_run_time'] is not None


def test_a_broken_review_pass_does_not_take_the_daemon_down(monkeypatch):
    """The review tier sits on top of the primary the way the primary sits on
    top of ingest: optional, isolated, never fatal."""
    monkeypatch.setattr(daemon.llm_sentiment, 'run_pass', lambda: 0)

    def explode():
        raise RuntimeError('sonnet is unreachable')

    monkeypatch.setattr(daemon.llm_sentiment, 'run_review_pass', explode)

    daemon._scheduled_sentiment()   # must not raise


# --- Market data v2 orchestration (plan Task 9) ------------------------------

class CapturingScheduler:
    instances = []

    def __init__(self, **kwargs):
        self.jobs = []
        CapturingScheduler.instances.append(self)

    def add_job(self, func, trigger, **kwargs):
        self.jobs.append((func, trigger, kwargs))

    def start(self):
        pass

    def shutdown(self):
        pass


def _captured_jobs(monkeypatch):
    CapturingScheduler.instances = []
    monkeypatch.setattr(daemon, 'BackgroundScheduler', CapturingScheduler)
    monkeypatch.setattr(daemon, '_prepare_rollup_generation',
                        lambda now: (0, 0))
    monkeypatch.setattr(daemon, 'build_fetchers', lambda: {})
    monkeypatch.setattr(
        daemon.time, 'sleep',
        lambda seconds: (_ for _ in ()).throw(KeyboardInterrupt))
    daemon.main([])
    return {job[2]['id']: job for job in
            CapturingScheduler.instances[0].jobs}


def test_the_five_market_data_jobs_register_once_and_radar_quotes_is_gone(
        monkeypatch):
    monkeypatch.delenv('RADAR_US_PRICE_PROVIDER', raising=False)
    jobs = _captured_jobs(monkeypatch)
    assert 'radar_quotes' not in jobs
    assert jobs['radar_us_quotes'][2]['minutes'] == 5      # finnhub default
    assert jobs['radar_de_market_data'][2]['minutes'] == 5
    assert jobs['radar_market_history' if 'radar_market_history' in jobs
                else 'radar_history'][1] == 'interval'
    grouped = jobs['radar_us_grouped_closes']
    assert grouped[1] == 'cron'
    assert (grouped[2]['hour'], grouped[2]['minute']) == (23, 30)
    assert jobs['radar_mappings'][2]['weeks'] == 1


def test_the_yahoo_fallback_flag_widens_the_us_cadence(monkeypatch):
    monkeypatch.setenv('RADAR_US_PRICE_PROVIDER', 'yahoo')
    jobs = _captured_jobs(monkeypatch)
    assert jobs['radar_us_quotes'][2]['minutes'] == 15


def test_invalid_flags_refuse_startup(monkeypatch):
    from features.radar.config import price_provider_config
    monkeypatch.setenv('RADAR_US_PRICE_PROVIDER', 'bloomberg')
    with pytest.raises(RuntimeError, match='RADAR_US_PRICE_PROVIDER'):
        price_provider_config()
    monkeypatch.setenv('RADAR_US_PRICE_PROVIDER', 'finnhub')
    monkeypatch.setenv('RADAR_US_CLOSE_SOURCE', 'shadow')
    monkeypatch.delenv('RADAR_MASSIVE_API_KEY', raising=False)
    with pytest.raises(RuntimeError, match='RADAR_MASSIVE_API_KEY'):
        price_provider_config()


def test_cleanup_evidence_is_all_or_none(monkeypatch):
    from features.radar.config import price_provider_config
    monkeypatch.setenv('RADAR_US_CLOSE_ACTIVATED_AT', '2026-09-01T00:00:00Z')
    monkeypatch.delenv('RADAR_US_CLOSE_GATE_REPORT_SHA256', raising=False)
    monkeypatch.delenv('RADAR_US_CLOSE_GATE_AUDIT_SHA256', raising=False)
    with pytest.raises(RuntimeError, match='all three'):
        price_provider_config()
    monkeypatch.setenv('RADAR_US_CLOSE_GATE_REPORT_SHA256', 'a' * 64)
    monkeypatch.setenv('RADAR_US_CLOSE_GATE_AUDIT_SHA256', 'B' * 64)
    with pytest.raises(RuntimeError, match='SHA-256'):
        price_provider_config()
    monkeypatch.setenv('RADAR_US_CLOSE_GATE_AUDIT_SHA256', 'b' * 64)
    assert price_provider_config()[0] == 'finnhub'


def test_a_closed_us_calendar_makes_no_provider_call(monkeypatch):
    calls = []
    monkeypatch.setattr(
        daemon.finnhub_provider, 'FinnhubProvider',
        lambda http: calls.append('constructed'))
    closed = dt.datetime(2026, 8, 30, 9, 0, tzinfo=dt.timezone.utc)  # Sunday
    with daemon.app.app_context():
        result = daemon._run_us_price_cycle('finnhub', closed)
    assert result['skipped'] == 'market_closed'
    assert calls == []


def test_the_post_close_cycle_is_claimed_exactly_once(monkeypatch):
    from features.radar import market_data
    from models import RadarProviderSessionState
    with daemon.app.app_context():
        RadarProviderSessionState.query.filter_by(
            source='zz:test', market='us').delete(synchronize_session=False)
        daemon.db.session.commit()
        session_date = dt.date(2026, 8, 28)
        now = dt.datetime(2026, 8, 28, 21, 10)
        first = market_data.claim_post_close('zz:test', 'us', now,
                                             session_date)
        second = market_data.claim_post_close('zz:test', 'us', now,
                                              session_date)
        assert first == session_date
        assert second is None
        # An OLDER session date can never re-claim after a restart.
        assert market_data.claim_post_close(
            'zz:test', 'us', now, session_date - dt.timedelta(days=1)) is None
        # The next session date claims normally.
        assert market_data.claim_post_close(
            'zz:test', 'us', now, session_date + dt.timedelta(days=3)) == \
            session_date + dt.timedelta(days=3)
        RadarProviderSessionState.query.filter_by(
            source='zz:test', market='us').delete(synchronize_session=False)
        daemon.db.session.commit()


def test_the_post_close_window_is_sixty_minutes(monkeypatch):
    # Friday 2026-08-28: US extended session closes 20:00 ET = 00:00 UTC Sat.
    from features.radar.market_calendars import session_bounds
    friday = dt.datetime(2026, 8, 28, 16, 0, tzinfo=dt.timezone.utc)
    closes_at = session_bounds('us', friday).closes_at
    inside = closes_at + dt.timedelta(minutes=30)
    outside = closes_at + dt.timedelta(minutes=61)
    gate_inside, date_inside = daemon._us_session_gate(inside)
    gate_outside, _ = daemon._us_session_gate(outside)
    assert gate_inside == 'post_close'
    assert date_inside == closes_at.date()
    assert gate_outside == 'closed'


def test_grouped_job_is_a_no_op_under_legacy(monkeypatch):
    calls = []
    monkeypatch.delenv('RADAR_US_CLOSE_SOURCE', raising=False)
    monkeypatch.setattr(
        daemon.market_data if hasattr(daemon, 'market_data') else daemon,
        '_never', None, raising=False)
    from features.radar.prices import massive as massive_mod

    class Exploding:
        def __init__(self, *args, **kwargs):
            calls.append('constructed')

    monkeypatch.setattr(massive_mod, 'MassiveProvider', Exploding)
    result = daemon._scheduled_us_grouped_closes()
    assert result == {'skipped': 'legacy'}
    assert calls == []


def test_ops_summary_is_memoized_and_provider_free(monkeypatch):
    from features.radar import market_data
    with daemon.app.app_context():
        market_data.clear_ops_memo()
        now = dt.datetime(2027, 1, 4, 12, 0)
        first = market_data.ops_summary(now)
        counter = {'n': 0}
        original_query = daemon.db.session.query

        def counting_query(*args, **kwargs):
            counter['n'] += 1
            return original_query(*args, **kwargs)

        monkeypatch.setattr(daemon.db.session, 'query', counting_query)
        second = market_data.ops_summary(now + dt.timedelta(seconds=30))
        assert second is first
        assert counter['n'] == 0
        assert 'grouped_closes' in first
        assert 'post_close_claims' in first
        market_data.clear_ops_memo()
