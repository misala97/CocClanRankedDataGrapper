# personal_apps/tests/test_radar_market_data.py
"""The German collection orchestrator: selection, transactions, retention.

The collector's one non-negotiable shape: cursor, trade events, quote
snapshots, and the accepted cycle row commit TOGETHER per accepted file, so
a crash can never advance the cursor past data that was not stored.
"""
import datetime as dt
import decimal
import gzip
import json

import pytest

from app import app as flask_app
from extensions import db
from features.radar import market_data
from features.radar.prices import deutsche_boerse as dbag
from models import (RadarInstrument, RadarMappingGeneration,
                    RadarMarketDataCursor, RadarMarketDataCycle,
                    RadarMarketTradeEvent, RadarQuote)

NOW = dt.datetime(2027, 1, 4, 12, 45)
PREFIX = 'T7MD'


@pytest.fixture()
def ctx():
    def clean():
        for model, column in (
                (RadarQuote, RadarQuote.ticker),
                (RadarInstrument, RadarInstrument.ticker),
                (RadarMarketTradeEvent, RadarMarketTradeEvent.event_id)):
            model.query.filter(column.like(f'{PREFIX}%')).delete(
                synchronize_session=False)
        RadarMarketDataCursor.query.filter_by(
            source='deutsche_boerse_delayed').delete(synchronize_session=False)
        RadarMarketDataCycle.query.filter_by(
            source='deutsche_boerse_delayed').delete(synchronize_session=False)
        for generation in RadarMappingGeneration.query.all():
            if PREFIX in generation.payload_json:
                db.session.delete(generation)
        db.session.commit()

    with flask_app.app_context():
        clean()
        yield
        clean()


def trade(event_id, event_ts, price, isin=None, official=False):
    return dbag.TradeEvent(
        mic='XGAT', isin=isin or 'DE000ZZTST01',
        event_id=f'{PREFIX}{event_id}', original_event_id=None, action='new',
        event_ts=event_ts,
        price=decimal.Decimal(price) if price is not None else None,
        volume=10, is_official_close=official, venue_mic='XGAT')


def book(event_ts, bid, ask, isin=None):
    return dbag.BookEvent(mic='XGAT', isin=isin or 'DE000ZZTST01',
                          event_ts=event_ts, bid=decimal.Decimal(bid),
                          ask=decimal.Decimal(ask))


# --- price selection ---------------------------------------------------------

def test_latest_valid_trade_beats_midpoint():
    picked = market_data.select_price(
        now=NOW,
        trades=[trade('old', NOW - dt.timedelta(minutes=31), '99.00'),
                trade('new', NOW - dt.timedelta(minutes=20), '100.00')],
        book=book(NOW - dt.timedelta(minutes=18), '99.90', '100.10'))
    assert (picked.price, picked.price_basis) == (
        decimal.Decimal('100.00'), 'trade')


def test_fresh_book_is_indicative_when_no_fresh_trade():
    picked = market_data.select_price(
        now=NOW,
        trades=[trade('old', NOW - dt.timedelta(minutes=31), '99.00')],
        book=book(NOW - dt.timedelta(minutes=18), '99.90', '100.10'))
    assert (picked.price, picked.price_basis) == (
        decimal.Decimal('100.00'), 'midpoint')
    assert (picked.bid, picked.ask) == (
        decimal.Decimal('99.90'), decimal.Decimal('100.10'))


def test_the_1800_second_boundary_is_exact():
    at_boundary = market_data.select_price(
        now=NOW,
        trades=[trade('edge', NOW - dt.timedelta(seconds=1800), '100.00')],
        book=None)
    assert at_boundary.price_basis == 'trade'
    past = market_data.select_price(
        now=NOW,
        trades=[trade('past', NOW - dt.timedelta(seconds=1801), '100.00')],
        book=None)
    assert past is None


def test_stale_book_and_stale_trade_yield_nothing():
    assert market_data.select_price(
        now=NOW,
        trades=[trade('old', NOW - dt.timedelta(minutes=40), '99.00')],
        book=book(NOW - dt.timedelta(minutes=31), '99.90', '100.10')) is None


def test_selection_ignores_other_instruments_events():
    picked = market_data.select_price(
        now=NOW,
        trades=[trade('mine', NOW - dt.timedelta(minutes=5), '100.00'),
                trade('theirs', NOW - dt.timedelta(minutes=1), '500.00',
                      isin='DE000ZZTST02')],
        book=None, isin='DE000ZZTST01')
    assert picked.price == decimal.Decimal('100.00')


# --- transactional collection ------------------------------------------------

@pytest.fixture(autouse=True)
def uncapped(monkeypatch):
    """The transaction-shape tests below predate the host quota and feed
    two files per cycle; the cap is the quota tests' business (`calm`)."""
    monkeypatch.setattr(market_data, 'DE_FILES_PER_CYCLE', 50)
    monkeypatch.setattr(market_data, '_THROTTLE', {})


def _seed_generation_and_universe(ticker):
    from features.radar import instruments as inst
    decision = inst.MappingDecision(
        ticker=ticker, status='mapped', reason=None, mic='XGAT',
        symbol=ticker + 'D', isin='DE000ZZTST01', currency='EUR',
        mapping_source='openfigi')
    return inst.persist_generation([decision], NOW)


def _ndjson_gz(rows):
    return gzip.compress(
        ('\n'.join(json.dumps(row) for row in rows) + '\n').encode('utf-8'))


def _post_row(event_id, minute, second, price):
    return {
        'messageId': 'zz-batch', 'venueOfExecution': 'XGAT',
        'instrumentIdentificationCode': 'DE000ZZTST01',
        'transactionIdentificationCode': f'{PREFIX}{event_id}',
        'mmtModificationInd': '-', 'mmtAlgoInd': 'H', 'mmtTradingMode': 'U',
        'price': price, 'priceCurrency': 'EUR', 'priceNotation': 1,
        'quantity': 5,
        'tradingDateAndTime':
            f'2027-01-04T12:{minute:02d}:{second:02d}.000000000Z',
        'publicationDateAndTime':
            f'2027-01-04T12:{minute:02d}:{second:02d}.100000000Z',
        'tradingSystem': '7', 'venueOfPublication': 'XCEF',
    }


class ScriptedProvider:
    source = 'deutsche_boerse_delayed'

    def __init__(self, files_by_channel, bodies, throttled=False):
        self.files_by_channel = files_by_channel
        self.bodies = bodies
        self.downloads = []            # every remote_id a download was asked for
        self.throttled = throttled     # answer HTTP 429 to every download
        self._parser = dbag.DeutscheBoerseProvider(http=None)

    def files_after(self, mic, channel, cursor):
        files = [file for file in self.files_by_channel.get(channel, ())
                 if cursor is None or file.source_ts > cursor.source_ts]
        return sorted(files, key=lambda file: file.source_ts)

    def download(self, file, **limits):
        self.downloads.append(file.remote_id)
        if self.throttled:
            raise dbag.PriceUnavailable(f'HTTP 429 ({file.remote_id})')
        return self.bodies[file.remote_id]

    def parse(self, file, compressed, **limits):
        return self._parser.parse(file, compressed)


def _feed_file(remote_id, minute, channel='posttrade'):
    return dbag.FeedFile(
        mic='XGAT', channel=channel, remote_id=remote_id,
        source_ts=dt.datetime(2027, 1, 4, 12, minute),
        url='https://mfs.deutsche-boerse.com/api/download/' + remote_id)


def _scripted(ticker):
    file_a = _feed_file('DGAT-posttrade-2027-01-04T12_40.json.gz', 40)
    file_b = _feed_file('DGAT-posttrade-2027-01-04T12_41.json.gz', 41)
    provider = ScriptedProvider(
        {'posttrade': (file_a, file_b), 'pretrade': ()},
        {file_a.remote_id: _ndjson_gz([_post_row('t1', 40, 5, 100.0)]),
         file_b.remote_id: _ndjson_gz([_post_row('t2', 41, 5, 101.0)])})
    return provider


def test_a_mid_persist_failure_leaves_no_partial_state(ctx, monkeypatch):
    ticker = f'{PREFIX}AA'
    generation = _seed_generation_and_universe(ticker)
    provider = _scripted(ticker)

    from features.radar import quotes as quotes_mod

    def exploding(*args, **kwargs):
        raise RuntimeError('forced quote failure')

    monkeypatch.setattr(quotes_mod, 'record_quotes', exploding)
    with pytest.raises(RuntimeError):
        market_data.collect_german_cycle(
            provider, generation.id, [ticker], NOW, mode='shadow')

    assert RadarMarketDataCursor.query.filter_by(
        source='deutsche_boerse_delayed').count() == 0
    assert RadarMarketTradeEvent.query.filter(
        RadarMarketTradeEvent.event_id.like(f'{PREFIX}%')).count() == 0
    assert RadarQuote.query.filter(
        RadarQuote.ticker.like(f'{PREFIX}%')).count() == 0
    accepted = RadarMarketDataCycle.query.filter_by(
        source='deutsche_boerse_delayed', status='accepted').count()
    assert accepted == 0


def test_a_normal_cycle_commits_cursor_events_quote_and_cycle_together(ctx):
    ticker = f'{PREFIX}AA'
    generation = _seed_generation_and_universe(ticker)
    provider = _scripted(ticker)

    summary = market_data.collect_german_cycle(
        provider, generation.id, [ticker], NOW, mode='shadow')
    assert summary.status == 'accepted'
    assert summary.selected_quotes >= 1

    cursor = RadarMarketDataCursor.query.filter_by(
        source='deutsche_boerse_delayed', mic='XGAT',
        channel='posttrade').one()
    assert cursor.remote_id == 'DGAT-posttrade-2027-01-04T12_41.json.gz'
    assert RadarMarketTradeEvent.query.filter(
        RadarMarketTradeEvent.event_id.like(f'{PREFIX}%')).count() == 2
    quote = RadarQuote.query.filter_by(ticker=ticker).one()
    assert quote.is_shadow is True
    assert quote.source == 'deutsche_boerse_delayed'
    assert quote.price == decimal.Decimal('101.000000')
    assert quote.quote_ts == dt.datetime(2027, 1, 4, 12, 41, 5)


def test_rerunning_the_same_files_writes_nothing_new(ctx):
    ticker = f'{PREFIX}AA'
    generation = _seed_generation_and_universe(ticker)
    provider = _scripted(ticker)
    market_data.collect_german_cycle(
        provider, generation.id, [ticker], NOW, mode='shadow')

    again = market_data.collect_german_cycle(
        provider, generation.id, [ticker], NOW + dt.timedelta(minutes=5),
        mode='shadow')
    assert again.status == 'no_newer'
    assert RadarMarketTradeEvent.query.filter(
        RadarMarketTradeEvent.event_id.like(f'{PREFIX}%')).count() == 2
    assert RadarQuote.query.filter_by(ticker=ticker).count() == 1


class _ExpiringProvider(ScriptedProvider):
    """Downloads of named files fail, like the provider's ~1-day expiry."""

    def __init__(self, files_by_channel, bodies, dead):
        super().__init__(files_by_channel, bodies)
        self.dead = dead

    def download(self, file, **limits):
        if file.remote_id in self.dead:
            raise dbag.PriceUnavailable(f'HTTP 404 ({file.remote_id})')
        return super().download(file, **limits)


def test_an_expired_backlog_file_is_skipped_not_wedged(ctx):
    """Production 2026-09-01: a deleted upstream file made every cycle
    fail at the same download forever. Old-and-gone files are skipped;
    fresh files behind them still collect in the SAME pass."""
    ticker = f'{PREFIX}AA'
    generation = _seed_generation_and_universe(ticker)
    dead = dbag.FeedFile(
        mic='XGAT', channel='posttrade',
        remote_id='DGAT-posttrade-2027-01-03T06_00.json.gz',
        source_ts=dt.datetime(2027, 1, 3, 6, 0),
        url='https://mfs.deutsche-boerse.com/api/download/x')
    fresh = _feed_file('DGAT-posttrade-2027-01-04T12_41.json.gz', 41)
    provider = _ExpiringProvider(
        {'posttrade': (dead, fresh), 'pretrade': ()},
        {fresh.remote_id: _ndjson_gz([_post_row('t2', 41, 5, 101.0)])},
        dead={dead.remote_id})

    summary = market_data.collect_german_cycle(
        provider, generation.id, [ticker], NOW, mode='shadow')

    assert summary.status == 'accepted'
    cursor = RadarMarketDataCursor.query.filter_by(
        source='deutsche_boerse_delayed', mic='XGAT',
        channel='posttrade').one()
    assert cursor.remote_id == fresh.remote_id
    assert RadarQuote.query.filter_by(ticker=ticker).count() == 1


def test_a_pass_of_only_expired_files_advances_past_them(ctx):
    ticker = f'{PREFIX}AA'
    generation = _seed_generation_and_universe(ticker)
    dead = dbag.FeedFile(
        mic='XGAT', channel='posttrade',
        remote_id='DGAT-posttrade-2027-01-03T06_00.json.gz',
        source_ts=dt.datetime(2027, 1, 3, 6, 0),
        url='https://mfs.deutsche-boerse.com/api/download/x')
    provider = _ExpiringProvider(
        {'posttrade': (dead,), 'pretrade': ()}, {}, dead={dead.remote_id})

    summary = market_data.collect_german_cycle(
        provider, generation.id, [ticker], NOW, mode='shadow')

    assert summary.status == 'no_newer'
    assert 'expired files skipped' in (summary.error_code or '')
    cursor = RadarMarketDataCursor.query.filter_by(
        source='deutsche_boerse_delayed', mic='XGAT',
        channel='posttrade').one()
    assert cursor.remote_id == dead.remote_id
    # The next cycle no longer sees the dead file at all.
    again = market_data.collect_german_cycle(
        provider, generation.id, [ticker], NOW + dt.timedelta(minutes=5),
        mode='shadow')
    assert again.status == 'no_newer'
    assert again.error_code is None


def test_a_fresh_download_failure_still_aborts_without_advancing(ctx):
    """Only EXPIRED files may be skipped: a failing fresh file means the
    data still exists upstream and must be retried, never jumped."""
    ticker = f'{PREFIX}AA'
    generation = _seed_generation_and_universe(ticker)
    fresh = _feed_file('DGAT-posttrade-2027-01-04T12_41.json.gz', 41)
    provider = _ExpiringProvider(
        {'posttrade': (fresh,), 'pretrade': ()}, {},
        dead={fresh.remote_id})

    summary = market_data.collect_german_cycle(
        provider, generation.id, [ticker], NOW, mode='shadow')

    assert summary.status == 'transport_error'
    assert RadarMarketDataCursor.query.filter_by(
        source='deutsche_boerse_delayed', mic='XGAT',
        channel='posttrade').count() == 0


def test_a_structurally_corrupt_file_rejects_and_does_not_advance(ctx):
    ticker = f'{PREFIX}AA'
    generation = _seed_generation_and_universe(ticker)
    file_a = _feed_file('DGAT-posttrade-2027-01-04T12_40.json.gz', 40)
    provider = ScriptedProvider(
        {'posttrade': (file_a,), 'pretrade': ()},
        {file_a.remote_id: b'this is not gzip'})

    summary = market_data.collect_german_cycle(
        provider, generation.id, [ticker], NOW, mode='shadow')
    assert summary.status == 'rejected'
    assert RadarMarketDataCursor.query.filter_by(
        source='deutsche_boerse_delayed').count() == 0
    rejected = RadarMarketDataCycle.query.filter_by(
        source='deutsche_boerse_delayed', status='rejected').count()
    assert rejected >= 1


def test_shadow_mode_never_writes_live_rows(ctx):
    ticker = f'{PREFIX}AA'
    generation = _seed_generation_and_universe(ticker)
    market_data.collect_german_cycle(
        _scripted(ticker), generation.id, [ticker], NOW, mode='shadow')
    assert RadarQuote.query.filter_by(
        ticker=ticker, is_shadow=False).count() == 0


# --- backfill CLI ------------------------------------------------------------

def test_de_backfill_discovers_an_activated_xetra_proxy(ctx):
    from features.radar import instruments
    from scripts import backfill_radar_market_history as cli
    ticker = f'{PREFIX}PX'
    decision = instruments.MappingDecision(
        ticker=ticker, status='mapped', reason=None, mic='XGAT',
        symbol='ZZTG', isin='DE000ZZTST01', currency='EUR',
        mapping_source='openfigi', history_proxy_mic='XETR',
        history_proxy_symbol='ZZXE',
        history_proxy_isin='DE000ZZTST01',
        history_proxy_currency='EUR')
    generation = instruments.persist_generation([decision], NOW)
    instruments.activate_generation(generation.id, NOW)

    targets = cli._instrument_targets('de', NOW)

    target = next(row for row in targets if row.ticker == ticker)
    assert (target.mic, target.provider_symbol, target.is_primary,
            target.isin) == ('XETR', 'ZZXE', False, 'DE000ZZTST01')


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
        'ticker': f'{PREFIX}GA', 'mic': 'XETR', 'provider_symbol': f'{PREFIX}GA',
        'market': 'de', 'currency': 'EUR'})()
    monkeypatch.setattr(cli, '_instrument_targets',
                        lambda market, now: [target])
    monkeypatch.setattr(
        yahoo, 'YahooProvider',
        lambda http: type('Provider', (), {
            'daily_closes': lambda self, symbol, days, mic_code: []})())

    assert cli.main(['--market', 'de', '--apply']) == 0

    out = capsys.readouterr().out
    assert 'de: starting 1 instruments' in out
    assert 'de: progress 1/1 (100.0%) stored=0' in out


def test_instrument_dry_run_reports_the_resume_key(ctx, monkeypatch, capsys):
    from scripts import backfill_radar_market_history as cli
    from features.radar import market_data as md
    monkeypatch.setattr(md, 'active_price_tickers', lambda now: [])
    assert cli.main(['--market', 'us']) == 0
    assert 'would attempt 0 instruments' in capsys.readouterr().out


# --- native close materialization (spec §8.3) --------------------------------

def _journal_event(event_id, event_ts, price, official=False):
    db.session.add(RadarMarketTradeEvent(
        mic='XGAT', isin='DE000ZZTST01', event_id=f'{PREFIX}{event_id}',
        action='new', event_ts=event_ts,
        price=decimal.Decimal(price), volume=1,
        is_official_close=official, source_remote_id='zz',
        received_at=event_ts))


def test_native_close_prefers_the_official_marker(ctx):
    from models import RadarDailyClose
    RadarDailyClose.query.filter(
        RadarDailyClose.ticker.like(f'{PREFIX}%')).delete(
        synchronize_session=False)
    generation = _seed_generation_and_universe(f'{PREFIX}AA')
    # 2027-01-04 is a Monday; session closes 22:00 Berlin = 21:00 UTC.
    _journal_event('c1', dt.datetime(2027, 1, 4, 15, 0), '100.00')
    _journal_event('c2', dt.datetime(2027, 1, 4, 16, 34), '101.00',
                   official=True)
    _journal_event('c3', dt.datetime(2027, 1, 4, 20, 0), '102.00')
    db.session.commit()

    after_close = dt.datetime(2027, 1, 4, 21, 30)
    written = market_data.materialize_native_closes(
        generation.id, after_close, mode='shadow')
    assert written == 1
    row = RadarDailyClose.query.filter_by(
        ticker=f'{PREFIX}AA', market='de', mic='XGAT',
        close_date=dt.date(2027, 1, 4)).one()
    # The official close wins over the later ordinary trade.
    assert (row.close, row.is_shadow) == (decimal.Decimal('101.0000'), True)

    # Idempotent re-run restates rather than duplicates.
    market_data.materialize_native_closes(
        generation.id, after_close, mode='shadow')
    assert RadarDailyClose.query.filter_by(
        ticker=f'{PREFIX}AA', market='de', mic='XGAT',
        close_date=dt.date(2027, 1, 4)).count() == 1
    RadarDailyClose.query.filter(
        RadarDailyClose.ticker.like(f'{PREFIX}%')).delete(
        synchronize_session=False)
    db.session.commit()


def test_native_close_falls_back_to_the_final_session_trade(ctx):
    from models import RadarDailyClose
    RadarDailyClose.query.filter(
        RadarDailyClose.ticker.like(f'{PREFIX}%')).delete(
        synchronize_session=False)
    generation = _seed_generation_and_universe(f'{PREFIX}AA')
    _journal_event('f1', dt.datetime(2027, 1, 4, 15, 0), '100.00')
    _journal_event('f2', dt.datetime(2027, 1, 4, 20, 59), '103.00')
    db.session.commit()

    market_data.materialize_native_closes(
        generation.id, dt.datetime(2027, 1, 4, 21, 30), mode='shadow')
    row = RadarDailyClose.query.filter_by(
        ticker=f'{PREFIX}AA', market='de', mic='XGAT',
        close_date=dt.date(2027, 1, 4)).one()
    assert row.close == decimal.Decimal('103.0000')
    RadarDailyClose.query.filter(
        RadarDailyClose.ticker.like(f'{PREFIX}%')).delete(
        synchronize_session=False)
    db.session.commit()


def test_an_incomplete_session_is_not_materialized(ctx):
    from models import RadarDailyClose
    generation = _seed_generation_and_universe(f'{PREFIX}AA')
    _journal_event('m1', dt.datetime(2027, 1, 4, 15, 0), '100.00')
    db.session.commit()

    mid_session = dt.datetime(2027, 1, 4, 16, 0)
    assert market_data.materialize_native_closes(
        generation.id, mid_session, mode='shadow') == 0
    assert RadarDailyClose.query.filter_by(
        ticker=f'{PREFIX}AA', market='de').count() == 0


# --- retention ---------------------------------------------------------------

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


def test_grouped_ingest_uses_ipo_eligible_fallback_when_all_observations_are_later(
        grouped_ctx, monkeypatch):
    """Bootstrap history must not turn a healthy old provider day vacuous."""
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
            f'{PREFIX}GB': _decimal.Decimal('44.75'),
        })), NOW.date(), NOW)

    assert result.status == 'accepted'
    assert (result.active_matched, result.active_expected) == (2, 2)
    state = RadarGroupedCloseDay.query.filter_by(
        source='massive_grouped', close_date=NOW.date(),
        is_shadow=True).one()
    assert (state.active_matched, state.active_expected) == (2, 2)


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


def test_grouped_ingest_never_touches_a_german_row(grouped_ctx, monkeypatch):
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
    german = RadarDailyClose.query.filter_by(
        ticker=f'{PREFIX}GA', market='de', mic='XGAT',
        close_date=NOW.date()).one()
    assert german.close == decimal.Decimal('11.0000')
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


def test_prune_market_data_bounds_events_and_cycles(ctx):
    from features.radar import retention
    old = NOW - dt.timedelta(hours=49)
    fresh = NOW - dt.timedelta(hours=1)
    db.session.add_all([
        RadarMarketTradeEvent(
            mic='XGAT', isin='DE000ZZTST01', event_id=f'{PREFIX}old',
            action='new', event_ts=old, price=decimal.Decimal('1'),
            volume=1, is_official_close=False, source_remote_id='zz',
            received_at=old),
        RadarMarketTradeEvent(
            mic='XGAT', isin='DE000ZZTST01', event_id=f'{PREFIX}new',
            action='new', event_ts=fresh, price=decimal.Decimal('1'),
            volume=1, is_official_close=False, source_remote_id='zz',
            received_at=fresh),
        RadarMarketDataCycle(
            source='deutsche_boerse_delayed', mic='XGAT', channel='posttrade',
            scheduled_at=NOW - dt.timedelta(days=15), mode='shadow',
            status='accepted'),
        RadarMarketDataCycle(
            source='deutsche_boerse_delayed', mic='XGAT', channel='posttrade',
            scheduled_at=NOW - dt.timedelta(days=1), mode='shadow',
            status='accepted'),
    ])
    db.session.commit()

    retention.prune_market_data(NOW)

    remaining_events = {row.event_id for row in
                        RadarMarketTradeEvent.query.filter(
                            RadarMarketTradeEvent.event_id.like(
                                f'{PREFIX}%'))}
    assert remaining_events == {f'{PREFIX}new'}
    remaining_cycles = RadarMarketDataCycle.query.filter_by(
        source='deutsche_boerse_delayed').all()
    assert [cycle.scheduled_at for cycle in remaining_cycles] == [
        NOW - dt.timedelta(days=1)]


# --- the host's quota (2026-09-02 outage) ------------------------------------
#
# Deutsche Börse throttled the VPS after ~520 minute-file downloads and kept
# it throttled while the collector retried two files every five minutes.
# Three rules close that: newest-first with a per-cycle cap, a rolling 24h
# download budget, and exponential backoff on HTTP 429.


def test_the_collector_sleeps_outside_the_tradegate_session():
    """A closed venue must cost no mapping, listing, or download work."""
    night = dt.datetime(2026, 9, 3, 3, 0, 0)

    summary = market_data.collect_german_cycle(
        provider=None, generation_id=None, active_tickers=[], now=night,
        mode='active')

    assert summary.status == 'closed'
    assert summary.files_seen == 0


def test_only_quote_supplying_mics_are_collected():
    assert market_data.DE_COLLECT_MICS == ('XGAT',)


def test_a_mixed_generation_spends_feed_work_only_on_quote_supplying_mics(ctx):
    from features.radar import instruments

    tickers = [f'{PREFIX}TG', f'{PREFIX}XE']
    generation = instruments.persist_generation([
        instruments.MappingDecision(
            ticker=tickers[0], status='mapped', reason=None, mic='XGAT',
            symbol='ZZTG', isin='DE000ZZTST01', currency='EUR',
            mapping_source='openfigi'),
        instruments.MappingDecision(
            ticker=tickers[1], status='mapped', reason=None, mic='XETR',
            symbol='ZZXE', isin='DE000ZZTST02', currency='EUR',
            mapping_source='openfigi'),
    ], NOW)
    provider = ScriptedProvider({'pretrade': (), 'posttrade': ()}, {})

    market_data.collect_german_cycle(
        provider, generation.id, tickers, NOW, mode='active')

    assert {row.mic for row in RadarMarketDataCycle.query.all()} == {'XGAT'}


def test_ops_summary_reports_the_clamped_german_download_budget(ctx, monkeypatch):
    monkeypatch.setattr(market_data, 'DE_FILES_PER_CYCLE', 1)
    monkeypatch.setattr(market_data, 'DE_DOWNLOAD_BUDGET_24H', 4)
    for minute in range(5):
        completed_at = NOW - dt.timedelta(minutes=minute)
        db.session.add(RadarMarketDataCycle(
            source='deutsche_boerse_delayed', mic='XGAT',
            channel='posttrade', scheduled_at=completed_at,
            completed_at=completed_at, mode='active', status='accepted',
            files_seen=1, files_accepted=1, record_count=1,
            selected_count=0, rejected_records=0, compressed_bytes=0,
            uncompressed_bytes=0, parse_ms=0))
    db.session.commit()
    market_data.clear_ops_memo()
    try:
        summary = market_data.ops_summary(NOW)
    finally:
        market_data.clear_ops_memo()

    assert summary['de_download_budget_24h'] == {
        'spent': 5, 'limit': 4, 'remaining': 0}


def test_ops_summary_exposes_the_configured_session_budget(ctx):
    market_data.clear_ops_memo()
    try:
        summary = market_data.ops_summary(NOW)
    finally:
        market_data.clear_ops_memo()

    assert summary['de_download_budget_24h'] == {
        'spent': 0, 'limit': 400, 'remaining': 400}


def _minute_files(minutes, channel='posttrade'):
    files, bodies = [], {}
    for index, minute in enumerate(minutes):
        file = _feed_file(f'DGAT-{channel}-2027-01-04T12_{minute:02d}.json.gz', minute,
                          channel=channel)
        files.append(file)
        bodies[file.remote_id] = _ndjson_gz(
            [_post_row(f't{minute}', minute, 5, 100.0 + index)])
    return files, bodies


@pytest.fixture()
def calm(monkeypatch):
    """A fresh throttle memory and a generous budget, per test."""
    monkeypatch.setattr(market_data, '_THROTTLE', {})
    monkeypatch.setattr(market_data, 'DE_DOWNLOAD_BUDGET_24H', 1000)
    monkeypatch.setattr(market_data, 'DE_FILES_PER_CYCLE', 1)


def test_a_cycle_downloads_only_the_newest_files_and_skips_the_backlog(ctx, calm):
    """Five minute-files newer than the cursor, cap 1: only the newest is
    fetched, the cursor lands on it, the skip is written down. Trades in
    the skipped files are gone -- sampled history, by decision."""
    ticker = f'{PREFIX}AA'
    generation = _seed_generation_and_universe(ticker)
    files, bodies = _minute_files([36, 37, 38, 39, 40])
    provider = ScriptedProvider({'posttrade': tuple(files), 'pretrade': ()}, bodies)

    summary = market_data.collect_german_cycle(
        provider, generation.id, [ticker], NOW, mode='active')

    assert provider.downloads == ['DGAT-posttrade-2027-01-04T12_40.json.gz']
    assert summary.status == 'accepted'
    cursor = RadarMarketDataCursor.query.get(('deutsche_boerse_delayed', 'XGAT', 'posttrade'))
    assert cursor.remote_id == 'DGAT-posttrade-2027-01-04T12_40.json.gz'
    row = RadarMarketDataCycle.query.filter_by(channel='posttrade').order_by(
        RadarMarketDataCycle.id.desc()).first()
    assert row.files_seen == 1
    assert 'skipped 4' in (row.error_code or '')


def test_a_429_backs_the_channel_off_and_the_next_cycle_makes_no_request(ctx, calm):
    ticker = f'{PREFIX}AA'
    generation = _seed_generation_and_universe(ticker)
    files, bodies = _minute_files([40])
    provider = ScriptedProvider({'posttrade': tuple(files), 'pretrade': ()}, bodies,
                                throttled=True)

    first = market_data.collect_german_cycle(provider, generation.id, [ticker], NOW,
                                             mode='active')
    assert first.status == 'transport_error'
    assert provider.downloads == ['DGAT-posttrade-2027-01-04T12_40.json.gz']

    # Five minutes later: inside the backoff, not even a listing.
    provider.throttled = False
    second = market_data.collect_german_cycle(
        provider, generation.id, [ticker], NOW + dt.timedelta(minutes=5), mode='active')
    assert second.status == 'transport_error'
    assert 'throttled' in (second.error_code or '')
    assert len(provider.downloads) == 1
    row = RadarMarketDataCycle.query.filter_by(channel='posttrade').order_by(
        RadarMarketDataCycle.id.desc()).first()
    assert row.files_seen == 0

    # Past the backoff: it tries again, and the host having relented, succeeds.
    third = market_data.collect_german_cycle(
        provider, generation.id, [ticker], NOW + dt.timedelta(minutes=31), mode='active')
    assert third.status == 'accepted'
    assert len(provider.downloads) == 2


def test_a_second_429_doubles_the_backoff(ctx, calm):
    ticker = f'{PREFIX}AA'
    generation = _seed_generation_and_universe(ticker)
    files, bodies = _minute_files([40])
    provider = ScriptedProvider({'posttrade': tuple(files), 'pretrade': ()}, bodies,
                                throttled=True)

    market_data.collect_german_cycle(provider, generation.id, [ticker], NOW, mode='active')
    market_data.collect_german_cycle(provider, generation.id, [ticker],
                                     NOW + dt.timedelta(minutes=31), mode='active')
    assert len(provider.downloads) == 2

    # 31 minutes after the second failure is inside a 60-minute backoff.
    market_data.collect_german_cycle(provider, generation.id, [ticker],
                                     NOW + dt.timedelta(minutes=62), mode='active')
    assert len(provider.downloads) == 2
    market_data.collect_german_cycle(provider, generation.id, [ticker],
                                     NOW + dt.timedelta(minutes=92), mode='active')
    assert len(provider.downloads) == 3


def test_the_rolling_download_budget_stops_the_collector(ctx, calm, monkeypatch):
    """Cycle rows are the ledger: files_seen is downloads attempted. Over
    the 24h budget, a cycle records itself and asks for nothing."""
    ticker = f'{PREFIX}AA'
    generation = _seed_generation_and_universe(ticker)
    files, bodies = _minute_files([40])
    provider = ScriptedProvider({'posttrade': tuple(files), 'pretrade': ()}, bodies)
    monkeypatch.setattr(market_data, 'DE_DOWNLOAD_BUDGET_24H', 3)
    for minute in (5, 10, 15):
        db.session.add(RadarMarketDataCycle(
            source='deutsche_boerse_delayed', mic='XGAT', channel='posttrade',
            scheduled_at=NOW - dt.timedelta(hours=1, minutes=minute),
            completed_at=NOW - dt.timedelta(hours=1, minutes=minute),
            mode='active', status='accepted', files_seen=1, files_accepted=1,
            record_count=1, selected_count=0, rejected_records=0,
            compressed_bytes=0, uncompressed_bytes=0, parse_ms=0))
    db.session.commit()

    summary = market_data.collect_german_cycle(
        provider, generation.id, [ticker], NOW, mode='active')

    assert provider.downloads == []
    assert summary.status == 'transport_error'
    assert 'budget' in (summary.error_code or '')


def test_a_pre_quota_cycle_row_counts_as_one_attempt(ctx, calm, monkeypatch):
    """Rows written before the cap carried files LISTED in files_seen (31 a
    cycle) while attempting one download and breaking on it. Counted at
    face value they spent the budget for a day after the deploy (seen
    live: 'download budget spent 5056/300'). A row over the cap is one
    attempt."""
    ticker = f'{PREFIX}AA'
    generation = _seed_generation_and_universe(ticker)
    files, bodies = _minute_files([40])
    provider = ScriptedProvider({'posttrade': tuple(files), 'pretrade': ()}, bodies)
    monkeypatch.setattr(market_data, 'DE_DOWNLOAD_BUDGET_24H', 3)
    db.session.add(RadarMarketDataCycle(
        source='deutsche_boerse_delayed', mic='XGAT', channel='pretrade',
        scheduled_at=NOW - dt.timedelta(hours=1), completed_at=NOW - dt.timedelta(hours=1),
        mode='active', status='transport_error', files_seen=31, files_accepted=0,
        record_count=0, selected_count=0, rejected_records=0,
        compressed_bytes=0, uncompressed_bytes=0, parse_ms=0,
        error_code='HTTP 429 (DGAT-pretrade-2027-01-04T11_45.json.gz'))
    db.session.commit()

    assert market_data.downloads_last_24h(NOW) == 1
    summary = market_data.collect_german_cycle(
        provider, generation.id, [ticker], NOW, mode='active')
    assert summary.status == 'accepted'
    assert provider.downloads == ['DGAT-posttrade-2027-01-04T12_40.json.gz']


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
