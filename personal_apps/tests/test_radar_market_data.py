# personal_apps/tests/test_radar_market_data.py
"""US market-data orchestration: grouped closes, the active set, the
post-close claim and the operational summary.

The grouped-close write keeps its one non-negotiable shape: the day's closes
and its accepted state commit TOGETHER, so a failure can never leave accepted
progress without the rows it vouches for. Archived rows of the retired
non-US market are never read, written or deleted here.
"""
import datetime as dt
import decimal

import pytest

from app import app as flask_app
from extensions import db
from features.radar import market_data
from models import RadarInstrument, RadarQuote

NOW = dt.datetime(2027, 1, 4, 12, 45)
PREFIX = 'T7MD'


@pytest.fixture()
def ctx():
    def clean():
        for model, column in (
                (RadarQuote, RadarQuote.ticker),
                (RadarInstrument, RadarInstrument.ticker)):
            model.query.filter(column.like(f'{PREFIX}%')).delete(
                synchronize_session=False)
        db.session.commit()

    with flask_app.app_context():
        clean()
        yield
        clean()


# --- nothing of the retired collector remains --------------------------------

RETIRED = ('select_price', 'Selected', 'CycleSummary', 'collect_german_cycle',
           'materialize_native_closes', 'downloads_last_24h',
           'DE_FILES_PER_CYCLE', 'DE_DOWNLOAD_BUDGET_24H',
           'DE_THROTTLE_BACKOFF_SECONDS', 'DE_COLLECT_MICS',
           'XETR_PRETRADE_LIMITS', 'STALE_SKIP_AGE', 'VENUE_BY_MIC',
           'MappingDecision', 'FeedRejected')


@pytest.mark.parametrize('name', RETIRED)
def test_the_retired_collector_is_gone(name):
    assert not hasattr(market_data, name)


def test_the_retired_provider_and_mapping_modules_are_gone():
    import importlib
    for module in ('features.radar.prices.deutsche_boerse',
                   'features.radar.prices.openfigi',
                   'features.radar.prices.ecb',
                   'features.radar.instruments',
                   'features.radar.reference_universe',
                   'features.radar.fx'):
        with pytest.raises(ModuleNotFoundError):
            importlib.import_module(module)


# --- backfill CLI ------------------------------------------------------------

@pytest.mark.parametrize('market', ['de', 'all'])
def test_the_backfill_offers_no_path_to_the_retired_market(market, capsys):
    from scripts import backfill_radar_market_history as cli
    with pytest.raises(SystemExit):
        cli.main(['--market', market])
    assert 'invalid choice' in capsys.readouterr().err


def test_us_universe_backfill_refuses_under_legacy(ctx, monkeypatch, capsys):
    from scripts import backfill_radar_market_history as cli
    monkeypatch.delenv('RADAR_US_CLOSE_SOURCE', raising=False)
    code = cli.main(['--market', 'us-universe', '--apply'])
    assert code == 2
    assert 'RADAR_US_CLOSE_SOURCE' in capsys.readouterr().err


def test_us_universe_dry_run_counts_unaccepted_trading_days(
        ctx, monkeypatch, capsys):
    from scripts import backfill_radar_market_history as cli
    monkeypatch.setenv('RADAR_US_CLOSE_SOURCE', 'shadow')
    code = cli.main(['--market', 'us-universe', '--limit', '7'])
    assert code == 0
    out = capsys.readouterr().out
    assert 'would attempt 7 trading days' in out
    assert 'next resume key:' in out


def test_us_universe_backfill_reports_periodic_progress(
        ctx, monkeypatch, capsys):
    """A long rate-limited run exposes progress before its final summary."""
    from scripts import backfill_radar_market_history as cli
    from features.radar import market_data as md
    from features.radar.prices import massive

    days = [dt.date(2099, 1, day) for day in range(1, 13)]
    monkeypatch.setenv('RADAR_US_CLOSE_SOURCE', 'shadow')
    monkeypatch.setattr(cli, '_us_trading_days', lambda newest, depth: days)
    monkeypatch.setattr(massive, 'MassiveProvider', lambda http: object())
    monkeypatch.setattr(
        md, 'ingest_grouped_day',
        lambda provider, day, now: type('Result', (), {
            'status': 'accepted' if day.day != 11 else 'rejected'})())

    assert cli.main(['--market', 'us-universe', '--apply']) == 0

    out = capsys.readouterr().out
    assert 'starting 12 trading days' in out
    assert 'progress 10/12 (83.3%) accepted=10 failed=0' in out
    assert 'progress 12/12 (100.0%) accepted=11 failed=1' in out


def test_instrument_backfill_reports_progress(
        ctx, monkeypatch, capsys):
    """Instrument history backfills also remain visible while they run."""
    from scripts import backfill_radar_market_history as cli
    from features.radar.prices import yahoo

    target = type('Target', (), {
        'ticker': f'{PREFIX}GA', 'mic': 'XNAS', 'provider_symbol': f'{PREFIX}GA',
        'market': 'us', 'currency': 'USD'})()
    asked = []
    monkeypatch.setattr(cli, '_instrument_targets',
                        lambda market, now: [target])
    monkeypatch.setattr(
        yahoo, 'YahooProvider',
        lambda http: type('Provider', (), {
            'daily_closes': lambda self, symbol, days, mic_code:
                asked.append((symbol, mic_code)) or []})())

    assert cli.main(['--market', 'us', '--apply']) == 0

    out = capsys.readouterr().out
    assert 'us: starting 1 instruments' in out
    assert 'us: progress 1/1 (100.0%) stored=0' in out
    assert asked == [(f'{PREFIX}GA', 'XNAS')]


def test_instrument_dry_run_reports_the_resume_key(ctx, monkeypatch, capsys):
    from scripts import backfill_radar_market_history as cli
    from features.radar import market_data as md
    monkeypatch.setattr(md, 'active_price_tickers', lambda now: [])
    assert cli.main(['--market', 'us']) == 0
    assert 'would attempt 0 instruments' in capsys.readouterr().out


# --- the active set ---------------------------------------------------------

def test_active_price_tickers_is_the_union_of_the_three_windows(
        ctx, monkeypatch):
    from features.radar import leaderboard
    calls = []

    def fake_candidates(sources, now, hours):
        calls.append(hours)
        return {1: ['ZZONE'], 4: ['ZZONE', 'ZZFOUR'],
                24: ['ZZDAY']}[hours]

    monkeypatch.setattr(leaderboard, 'chatter_candidates', fake_candidates)
    assert market_data.active_price_tickers(NOW) == [
        'ZZDAY', 'ZZFOUR', 'ZZONE']
    assert sorted(calls) == [1, 4, 24]


def test_chatter_candidates_matches_build_rows_survivors(ctx, monkeypatch):
    """One judgement, one owner: the scheduler union must be exactly the
    leaderboard's own pass-one survivors."""
    from features.radar import leaderboard
    survivors = {'ZZAA': (1, 1.0, 1.0, 2, 1.0)}
    monkeypatch.setattr(
        leaderboard, '_chatter_survivors',
        lambda sources, now, hours: (survivors, {}, {}, {}))
    assert leaderboard.chatter_candidates(['reddit'], NOW, 4) == ['ZZAA']


# --- [A1] grouped instrument map and ingestion -------------------------------

def _us_instrument(ticker, provider_symbol=None, mic='XNAS'):
    from models import TickerUniverse
    if TickerUniverse.query.filter_by(symbol=ticker).one_or_none() is None:
        db.session.add(TickerUniverse(symbol=ticker, name=ticker,
                                      first_seen=NOW))
    db.session.add(RadarInstrument(
        ticker=ticker, market='us', venue='NASDAQ', mic=mic,
        provider_symbol=provider_symbol or ticker, currency='USD',
        is_primary=True, mapping_status='mapped', mapped_at=NOW))


@pytest.fixture()
def grouped_ctx(ctx):
    from models import RadarDailyClose, RadarGroupedCloseDay, TickerUniverse
    def clean():
        RadarDailyClose.query.filter(
            RadarDailyClose.ticker.like(f'{PREFIX}%')).delete(
            synchronize_session=False)
        RadarGroupedCloseDay.query.delete(synchronize_session=False)
        TickerUniverse.query.filter(
            TickerUniverse.symbol.like(f'{PREFIX}%')).delete(
            synchronize_session=False)
        db.session.commit()
    clean()
    yield
    clean()


def test_grouped_instrument_map_keys_exact_symbols_and_refuses_ambiguity(
        grouped_ctx):
    _us_instrument(f'{PREFIX}GA', provider_symbol=f'{PREFIX}GA')
    _us_instrument(f'{PREFIX}GB', provider_symbol=f'{PREFIX}SHARED')
    _us_instrument(f'{PREFIX}GC', provider_symbol=f'{PREFIX}SHARED',
                   mic='XNYS')
    db.session.commit()
    found, ambiguous = market_data.grouped_instrument_map()
    assert found[f'{PREFIX}GA'].ticker == f'{PREFIX}GA'
    assert found[f'{PREFIX}GA'].mic == 'XNAS'
    assert f'{PREFIX}SHARED' not in found
    assert ambiguous == [f'{PREFIX}SHARED']


class OneDayProvider:
    source = 'massive_grouped'

    def __init__(self, fetch):
        self.fetch = fetch
        self.calls = 0

    def grouped_closes(self, day):
        self.calls += 1
        return self.fetch


def _accepted_fetch(closes, provider_rows=6000):
    from features.radar.prices import massive
    return massive.GroupedFetch(
        status='accepted',
        day=massive.ProviderGroupedDay(
            closes=closes, payload_sha256='e' * 64,
            provider_rows=provider_rows, malformed_rows=0,
            duplicate_conflicts=0))


def test_grouped_ingest_refuses_to_run_under_legacy(grouped_ctx, monkeypatch):
    monkeypatch.delenv('RADAR_US_CLOSE_SOURCE', raising=False)
    provider = OneDayProvider(_accepted_fetch({}))
    with pytest.raises(RuntimeError, match='RADAR_US_CLOSE_SOURCE'):
        market_data.ingest_grouped_day(provider, NOW.date(), NOW)
    assert provider.calls == 0


def test_grouped_ingest_writes_shadow_rows_and_accepted_state(
        grouped_ctx, monkeypatch):
    import decimal as _decimal
    from models import RadarDailyClose, RadarGroupedCloseDay
    monkeypatch.setenv('RADAR_US_CLOSE_SOURCE', 'shadow')
    monkeypatch.setattr(market_data, 'active_price_tickers',
                        lambda now: [f'{PREFIX}GA'])
    _us_instrument(f'{PREFIX}GA')
    db.session.commit()

    result = market_data.ingest_grouped_day(
        OneDayProvider(_accepted_fetch(
            {f'{PREFIX}GA': _decimal.Decimal('55.25')})),
        NOW.date(), NOW)
    assert result.status == 'accepted'
    assert result.written == 1

    row = RadarDailyClose.query.filter_by(
        ticker=f'{PREFIX}GA', close_date=NOW.date()).one()
    assert (row.is_shadow, row.source, row.adjustment_basis) == (
        True, 'massive_grouped', 'split')
    state = RadarGroupedCloseDay.query.filter_by(
        source='massive_grouped', close_date=NOW.date(),
        is_shadow=True).one()
    assert state.status == 'accepted'
    assert state.active_matched == state.active_expected == 1


def test_grouped_ingest_excludes_pre_ipo_tickers_from_historical_coverage(
        grouped_ctx, monkeypatch):
    """A symbol cannot be a coverage miss before its provider IPO date."""
    import decimal as _decimal
    from models import RadarGroupedCloseDay, TickerUniverse
    monkeypatch.setenv('RADAR_US_CLOSE_SOURCE', 'shadow')
    tickers = [f'{PREFIX}GA', f'{PREFIX}GB']
    monkeypatch.setattr(market_data, 'active_price_tickers',
                        lambda now: tickers)
    for ticker in tickers:
        _us_instrument(ticker)
    TickerUniverse.query.filter_by(symbol=f'{PREFIX}GB').one().ipo_date = (
        NOW.date() + dt.timedelta(days=1))
    db.session.commit()

    result = market_data.ingest_grouped_day(
        OneDayProvider(_accepted_fetch(
            {f'{PREFIX}GA': _decimal.Decimal('55.25')})),
        NOW.date(), NOW)

    assert result.status == 'accepted'
    assert (result.active_matched, result.active_expected) == (1, 1)
    state = RadarGroupedCloseDay.query.filter_by(
        source='massive_grouped', close_date=NOW.date(),
        is_shadow=True).one()
    assert (state.active_matched, state.active_expected) == (1, 1)


def test_grouped_ingest_excludes_a_symbol_before_massive_first_observed_day(
        grouped_ctx, monkeypatch):
    """A later Massive close proves an earlier provider absence is expected."""
    import decimal as _decimal
    from models import RadarDailyClose, RadarGroupedCloseDay
    monkeypatch.setenv('RADAR_US_CLOSE_SOURCE', 'shadow')
    tickers = [f'{PREFIX}GA', f'{PREFIX}GB']
    monkeypatch.setattr(market_data, 'active_price_tickers',
                        lambda now: tickers)
    for ticker in tickers:
        _us_instrument(ticker)
    db.session.add(RadarDailyClose(
        ticker=f'{PREFIX}GB', market='us', mic='XNAS', currency='USD',
        close_date=NOW.date() + dt.timedelta(days=1),
        close=decimal.Decimal('12.00'), fetched_at=NOW,
        source='massive_grouped', price_basis='close',
        adjustment_basis='split', is_shadow=True))
    db.session.commit()

    result = market_data.ingest_grouped_day(
        OneDayProvider(_accepted_fetch(
            {f'{PREFIX}GA': _decimal.Decimal('55.25')})),
        NOW.date(), NOW)

    assert result.status == 'accepted'
    assert (result.active_matched, result.active_expected) == (1, 1)
    state = RadarGroupedCloseDay.query.filter_by(
        source='massive_grouped', close_date=NOW.date(),
        is_shadow=True).one()
    assert (state.active_matched, state.active_expected) == (1, 1)


def test_grouped_ingest_excludes_only_missing_symbols_with_later_observations(
        grouped_ctx, monkeypatch):
    """A returned bootstrap symbol remains coverage; a missing later one does not."""
    import decimal as _decimal
    from models import RadarDailyClose, RadarGroupedCloseDay
    monkeypatch.setenv('RADAR_US_CLOSE_SOURCE', 'shadow')
    tickers = [f'{PREFIX}GA', f'{PREFIX}GB']
    monkeypatch.setattr(market_data, 'active_price_tickers',
                        lambda now: tickers)
    for ticker in tickers:
        _us_instrument(ticker)
        db.session.add(RadarDailyClose(
            ticker=ticker, market='us', mic='XNAS', currency='USD',
            close_date=NOW.date() + dt.timedelta(days=1),
            close=_decimal.Decimal('12.00'), fetched_at=NOW,
            source='massive_grouped', price_basis='close',
            adjustment_basis='split', is_shadow=True))
    db.session.commit()

    result = market_data.ingest_grouped_day(
        OneDayProvider(_accepted_fetch({
            f'{PREFIX}GA': _decimal.Decimal('55.25'),
        })), NOW.date(), NOW)

    assert result.status == 'accepted'
    assert (result.active_matched, result.active_expected) == (1, 1)
    state = RadarGroupedCloseDay.query.filter_by(
        source='massive_grouped', close_date=NOW.date(),
        is_shadow=True).one()
    assert (state.active_matched, state.active_expected) == (1, 1)


def test_grouped_ingest_keeps_never_observed_symbol_in_coverage(
        grouped_ctx, monkeypatch):
    """No provider history is not proof that a missing symbol is harmless."""
    import decimal as _decimal
    from models import RadarGroupedCloseDay
    monkeypatch.setenv('RADAR_US_CLOSE_SOURCE', 'shadow')
    tickers = [f'{PREFIX}GA', f'{PREFIX}GB']
    monkeypatch.setattr(market_data, 'active_price_tickers',
                        lambda now: tickers)
    for ticker in tickers:
        _us_instrument(ticker)
    db.session.commit()

    result = market_data.ingest_grouped_day(
        OneDayProvider(_accepted_fetch(
            {f'{PREFIX}GA': _decimal.Decimal('55.25')})),
        NOW.date(), NOW)

    assert result.status == 'rejected'
    assert (result.active_matched, result.active_expected) == (1, 2)
    state = RadarGroupedCloseDay.query.filter_by(
        source='massive_grouped', close_date=NOW.date(),
        is_shadow=True).one()
    assert state.error_code == 'below_acceptance_floor'


def test_grouped_ingest_below_floor_rejects_and_stays_retryable(
        grouped_ctx, monkeypatch):
    import decimal as _decimal
    from models import RadarDailyClose, RadarGroupedCloseDay
    monkeypatch.setenv('RADAR_US_CLOSE_SOURCE', 'shadow')
    monkeypatch.setattr(market_data, 'active_price_tickers',
                        lambda now: [f'{PREFIX}GA'])
    _us_instrument(f'{PREFIX}GA')
    db.session.commit()

    thin = market_data.ingest_grouped_day(
        OneDayProvider(_accepted_fetch(
            {f'{PREFIX}GA': _decimal.Decimal('55.25')}, provider_rows=12)),
        NOW.date(), NOW)
    assert thin.status == 'rejected'
    assert RadarDailyClose.query.filter_by(
        ticker=f'{PREFIX}GA', close_date=NOW.date()).count() == 0
    state = RadarGroupedCloseDay.query.filter_by(
        close_date=NOW.date(), is_shadow=True).one()
    assert state.status == 'rejected'
    assert state.error_code == 'below_acceptance_floor'


def test_grouped_ingest_rejects_a_zero_active_denominator(
        grouped_ctx, monkeypatch):
    from models import RadarDailyClose, RadarGroupedCloseDay
    monkeypatch.setenv('RADAR_US_CLOSE_SOURCE', 'shadow')
    monkeypatch.setattr(market_data, 'active_price_tickers', lambda now: [])
    _us_instrument(f'{PREFIX}GA')
    db.session.commit()

    result = market_data.ingest_grouped_day(
        OneDayProvider(_accepted_fetch(
            {f'{PREFIX}GA': decimal.Decimal('55.25')})),
        NOW.date(), NOW)

    assert result.status == 'rejected'
    assert RadarDailyClose.query.filter_by(
        ticker=f'{PREFIX}GA', close_date=NOW.date()).count() == 0
    state = RadarGroupedCloseDay.query.filter_by(
        close_date=NOW.date(), is_shadow=True).one()
    assert state.error_code == 'empty_active_denominator'


def test_grouped_ingest_never_touches_an_archived_row(grouped_ctx, monkeypatch):
    import decimal as _decimal
    from models import RadarDailyClose
    monkeypatch.setenv('RADAR_US_CLOSE_SOURCE', 'massive')
    monkeypatch.setattr(market_data, 'active_price_tickers',
                        lambda now: [f'{PREFIX}GA'])
    _us_instrument(f'{PREFIX}GA')
    db.session.add(RadarDailyClose(
        ticker=f'{PREFIX}GA', market='de', mic='XGAT', currency='EUR',
        close_date=NOW.date(), close=decimal.Decimal('11.00'),
        fetched_at=NOW, source='deutsche_boerse_delayed',
        price_basis='close', adjustment_basis='split'))
    db.session.commit()

    market_data.ingest_grouped_day(
        OneDayProvider(_accepted_fetch(
            {f'{PREFIX}GA': _decimal.Decimal('55.25')})),
        NOW.date(), NOW)
    archived = RadarDailyClose.query.filter_by(
        ticker=f'{PREFIX}GA', market='de', mic='XGAT',
        close_date=NOW.date()).one()
    assert archived.close == decimal.Decimal('11.0000')
    us = RadarDailyClose.query.filter_by(
        ticker=f'{PREFIX}GA', market='us', close_date=NOW.date()).one()
    assert us.source == 'massive_grouped'


def test_a_failed_grouped_write_rolls_back_closes_and_state(
        grouped_ctx, monkeypatch):
    import decimal as _decimal
    from features.radar import history
    from models import RadarDailyClose, RadarGroupedCloseDay
    monkeypatch.setenv('RADAR_US_CLOSE_SOURCE', 'shadow')
    monkeypatch.setattr(market_data, 'active_price_tickers',
                        lambda now: [f'{PREFIX}GA'])
    _us_instrument(f'{PREFIX}GA')
    _us_instrument(f'{PREFIX}GB')
    db.session.commit()

    original = history.record_closes
    calls = {'n': 0}

    def exploding(*args, **kwargs):
        calls['n'] += 1
        if calls['n'] == 2:
            raise RuntimeError('forced close failure')
        return original(*args, **kwargs)

    monkeypatch.setattr(history, 'record_closes', exploding)
    with pytest.raises(RuntimeError):
        market_data.ingest_grouped_day(
            OneDayProvider(_accepted_fetch({
                f'{PREFIX}GA': _decimal.Decimal('1.50'),
                f'{PREFIX}GB': _decimal.Decimal('2.50')})),
            NOW.date(), NOW)
    assert RadarDailyClose.query.filter(
        RadarDailyClose.ticker.like(f'{PREFIX}%'),
        RadarDailyClose.market == 'us').count() == 0
    assert RadarGroupedCloseDay.query.filter_by(
        close_date=NOW.date(), status='accepted').count() == 0


# --- the operational summary ------------------------------------------------

@pytest.fixture()
def ops_ctx(ctx):
    from models import RadarProviderSessionState
    market_data.clear_ops_memo()
    yield
    market_data.clear_ops_memo()
    RadarQuote.query.filter(RadarQuote.ticker.like(f'{PREFIX}%')).delete(
        synchronize_session=False)
    RadarProviderSessionState.query.filter(
        RadarProviderSessionState.source.like(f'{PREFIX}%')).delete(
        synchronize_session=False)
    db.session.commit()


def test_ops_summary_is_us_only(ops_ctx):
    """Exactly the US sections; archived quotes are not counted and an
    archived claim row is not reported."""
    from models import RadarProviderSessionState

    at = NOW - dt.timedelta(hours=1)
    before = market_data.ops_summary(NOW)
    market_data.clear_ops_memo()
    db.session.add_all([
        RadarQuote(ticker=f'{PREFIX}OPS', market='us', mic='XNAS',
                   currency='USD', fetched_at=at, quote_ts=at,
                   price=decimal.Decimal('1'), price_basis='trade',
                   source='finnhub'),
        RadarQuote(ticker=f'{PREFIX}OPS', market='de', mic='XGAT',
                   currency='EUR', fetched_at=at, quote_ts=at,
                   price=decimal.Decimal('1'), price_basis='midpoint',
                   bid=decimal.Decimal('1'), ask=decimal.Decimal('1'),
                   source='deutsche_boerse_delayed'),
        RadarProviderSessionState(source=f'{PREFIX}:us', market='us'),
        RadarProviderSessionState(source=f'{PREFIX}:de', market='de'),
    ])
    db.session.commit()

    summary = market_data.ops_summary(NOW)

    assert set(summary) == {'quote_basis_24h', 'grouped_closes',
                            'post_close_claims'}
    counts = summary['quote_basis_24h']
    assert counts.get('trade', 0) == before['quote_basis_24h'].get(
        'trade', 0) + 1
    assert counts.get('midpoint', 0) == before['quote_basis_24h'].get(
        'midpoint', 0)
    assert f'{PREFIX}:us:us' in summary['post_close_claims']
    assert not any(key.endswith(':de') for key in summary['post_close_claims'])


def test_watched_tickers_are_priced_even_when_nobody_talks_about_them(ctx, monkeypatch):
    """The quote pollers take active_price_tickers; a starred ticker with
    no chatter must be in it, or its row keeps a days-old quote."""
    from features.radar import leaderboard
    from models import RadarWatch
    from conftest import _admin_id
    monkeypatch.setattr(leaderboard, 'chatter_candidates', lambda *a, **k: [f'{PREFIX}LOUD'])
    RadarWatch.query.filter_by(ticker=f'{PREFIX}STAR').delete()
    db.session.add(RadarWatch(user_id=_admin_id(), ticker=f'{PREFIX}STAR', created_at=NOW))
    db.session.commit()
    try:
        tickers = market_data.active_price_tickers(NOW)
        assert f'{PREFIX}STAR' in tickers and f'{PREFIX}LOUD' in tickers
    finally:
        RadarWatch.query.filter_by(ticker=f'{PREFIX}STAR').delete()
        db.session.commit()
