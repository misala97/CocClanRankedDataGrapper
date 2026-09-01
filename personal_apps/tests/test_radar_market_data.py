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

    def __init__(self, files_by_channel, bodies):
        self.files_by_channel = files_by_channel
        self.bodies = bodies
        self._parser = dbag.DeutscheBoerseProvider(http=None)

    def files_after(self, mic, channel, cursor):
        files = [file for file in self.files_by_channel.get(channel, ())
                 if cursor is None or file.source_ts > cursor.source_ts]
        return sorted(files, key=lambda file: file.source_ts)

    def download(self, file, **limits):
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


# --- retention ---------------------------------------------------------------

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
