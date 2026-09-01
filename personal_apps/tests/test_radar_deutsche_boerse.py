# personal_apps/tests/test_radar_deutsche_boerse.py
"""The delayed-file adapter, pinned to the captured contract.

Every JSON pointer here is the literal reviewed string from
docs/superpowers/specs/2026-08-31-radar-deutsche-boerse-feed-contract.md;
the sanitized fixtures reproduce the observed shapes. Rulings exercised:
R1 (NDJSON), R2 (one redirect to the exact bucket), R4 (unobserved
modification indicators reject the row, never guess semantics), R5 (XETR
lastTradeIndicator 'C' is the official close; XGAT has none), R7
(sub-venue MICs), R9 (empty gzip = market closed), R10 (non-EUR rows are
filtered).
"""
import datetime as dt
import decimal
import gzip
import json
import pathlib

import pytest

from features.radar.prices import PriceUnavailable
from features.radar.prices import deutsche_boerse as dbag

FIXTURES = pathlib.Path(__file__).parent / 'fixtures' / 'radar_market_data'


def fixture_bytes(name):
    rows = json.loads((FIXTURES / name).read_text(encoding='utf-8'))
    ndjson = '\n'.join(json.dumps(row) for row in rows) + '\n'
    return gzip.compress(ndjson.encode('utf-8'))


def feed_file(mic='XGAT', channel='posttrade',
              remote_id='DGAT-posttrade-2026-08-31T12_43.json.gz',
              source_ts=dt.datetime(2026, 8, 31, 12, 43)):
    return dbag.FeedFile(mic=mic, channel=channel, remote_id=remote_id,
                         source_ts=source_ts,
                         url='https://mfs.deutsche-boerse.com/api/download/'
                             + remote_id)


def parse_fixture(name, mic, channel, **file_kwargs):
    provider = dbag.DeutscheBoerseProvider(http=None)
    return provider.parse(feed_file(mic=mic, channel=channel, **file_kwargs),
                          fixture_bytes(name))


def mutated_fixture(name, mutate):
    rows = json.loads((FIXTURES / name).read_text(encoding='utf-8'))
    mutate(rows)
    ndjson = '\n'.join(json.dumps(row) for row in rows) + '\n'
    return gzip.compress(ndjson.encode('utf-8'))


def test_posttrade_fixture_preserves_identity_and_events():
    batch = parse_fixture('xgat_posttrade.json', mic='XGAT',
                          channel='posttrade')
    assert batch.mic == 'XGAT'
    assert batch.channel == 'posttrade'
    assert batch.source_ts == dt.datetime(2026, 8, 31, 12, 43)
    assert batch.reference_complete is False
    assert batch.references == ()
    assert batch.record_count == 2
    assert batch.trades == (
        dbag.TradeEvent(mic='XGAT', isin='DE000ZZTST01', event_id='zztrade-1',
                        original_event_id=None, action='new',
                        event_ts=dt.datetime(2026, 8, 31, 12, 42),
                        price=decimal.Decimal('100.0'), volume=20,
                        is_official_close=False, venue_mic='XGAT'),
        dbag.TradeEvent(mic='XGAT', isin='DE000ZZTST02', event_id='zztrade-2',
                        original_event_id=None, action='new',
                        event_ts=dt.datetime(2026, 8, 31, 12, 43),
                        price=decimal.Decimal('55.25'), volume=7,
                        is_official_close=False, venue_mic='XGRM'),
    )


def test_xetr_closing_auction_trade_carries_the_official_close_marker():
    batch = parse_fixture(
        'xetr_posttrade.json', mic='XETR', channel='posttrade',
        remote_id='DETR-posttrade-2026-08-31T15_35.json.gz',
        source_ts=dt.datetime(2026, 8, 31, 15, 35))
    marked = {trade.event_id: trade.is_official_close
              for trade in batch.trades}
    assert marked == {'zzxetra-trade-1': False, 'zzxetra-close-1': True}


def test_xgat_pretrade_fixture_yields_books_and_filters_non_eur():
    batch = parse_fixture(
        'xgat_pretrade.json', mic='XGAT', channel='pretrade',
        remote_id='DGAT-pretrade-2026-08-31T12_43.json.gz')
    # The USD row (ruling R10) is filtered and counted, not parsed.
    assert batch.books == (
        dbag.BookEvent(mic='XGAT', isin='DE000ZZTST01',
                       event_ts=dt.datetime(2026, 8, 31, 12, 42, 59),
                       bid=decimal.Decimal('99.9'),
                       ask=decimal.Decimal('100.1')),
    )
    assert batch.rejected_records == 1


def test_xetr_pretrade_top_of_book_rows_parse_and_depth_rows_are_skipped():
    batch = parse_fixture(
        'xetr_pretrade.json', mic='XETR', channel='pretrade',
        remote_id='DETR-pretrade-2026-08-31T12_43.json.gz')
    assert batch.books == (
        dbag.BookEvent(mic='XETR', isin='DE000ZZTST01',
                       event_ts=dt.datetime(2026, 8, 31, 12, 42, 59, 600000),
                       bid=decimal.Decimal('99.9'),
                       ask=decimal.Decimal('100.1')),
    )
    # A depth row is not an error; it is simply not a top-of-book event.
    assert batch.rejected_records == 0


@pytest.mark.parametrize('mutate, description', [
    (lambda rows: rows[0].update(mmtModificationInd='X'),
     'unobserved modification indicator'),
    (lambda rows: rows[0].update(venueOfExecution='XOFF'),
     'unobserved sub-venue'),
    (lambda rows: rows[0].update(instrumentIdentificationCode='SHORT'),
     'invalid ISIN'),
    (lambda rows: rows[0].update(price=-1),
     'non-positive price'),
    (lambda rows: rows[0].update(quantity=-5),
     'negative volume'),
    (lambda rows: rows[0].update(priceCurrency='USD'),
     'non-EUR trade'),
    (lambda rows: rows[0].update(tradingDateAndTime='yesterday'),
     'unparseable event time'),
    (lambda rows: rows[0].pop('transactionIdentificationCode'),
     'missing event id'),
])
def test_an_invalid_trade_row_is_rejected_and_counted(mutate, description):
    provider = dbag.DeutscheBoerseProvider(http=None)
    batch = provider.parse(
        feed_file(), mutated_fixture('xgat_posttrade.json', mutate))
    assert len(batch.trades) == 1, description
    assert batch.rejected_records == 1, description


def test_a_crossed_or_one_sided_book_produces_no_event():
    provider = dbag.DeutscheBoerseProvider(http=None)
    crossed = provider.parse(
        feed_file(channel='pretrade',
                  remote_id='DGAT-pretrade-2026-08-31T12_43.json.gz'),
        mutated_fixture('xgat_pretrade.json',
                        lambda rows: rows[0].update(bid=101.0, ask=100.0)))
    assert crossed.books == ()
    one_sided = provider.parse(
        feed_file(channel='pretrade',
                  remote_id='DGAT-pretrade-2026-08-31T12_43.json.gz'),
        mutated_fixture('xgat_pretrade.json',
                        lambda rows: rows[0].pop('ask')))
    assert one_sided.books == ()


def test_duplicate_event_id_with_conflicting_content_rejects_the_file():
    def duplicate_conflicting(rows):
        clone = dict(rows[0])
        clone['price'] = 999.0
        rows.append(clone)
    with pytest.raises(dbag.FeedRejected, match='conflicting'):
        dbag.DeutscheBoerseProvider(http=None).parse(
            feed_file(),
            mutated_fixture('xgat_posttrade.json', duplicate_conflicting))


def test_byte_identical_duplicate_rows_are_idempotent():
    def duplicate_identical(rows):
        rows.append(dict(rows[0]))
    batch = dbag.DeutscheBoerseProvider(http=None).parse(
        feed_file(),
        mutated_fixture('xgat_posttrade.json', duplicate_identical))
    assert len(batch.trades) == 2


def test_an_empty_gzip_file_is_a_valid_market_closed_batch():
    batch = dbag.DeutscheBoerseProvider(http=None).parse(
        feed_file(remote_id='DGAT-posttrade-2026-09-01T02_00.json.gz',
                  source_ts=dt.datetime(2026, 9, 1, 2, 0)),
        gzip.compress(b''))
    assert batch.trades == () and batch.books == ()
    assert batch.record_count == 0


def test_invalid_gzip_and_invalid_json_reject_the_whole_file():
    provider = dbag.DeutscheBoerseProvider(http=None)
    with pytest.raises(dbag.FeedRejected, match='gzip'):
        provider.parse(feed_file(), b'not a gzip stream')
    with pytest.raises(dbag.FeedRejected, match='JSON'):
        provider.parse(feed_file(), gzip.compress(b'{"broken": \n'))


def test_a_gzip_bomb_is_rejected_before_json_decode():
    bomb = gzip.compress(b' ' * 5_000_000)
    with pytest.raises(dbag.FeedRejected, match='ratio'):
        dbag.DeutscheBoerseProvider(http=None).parse(
            feed_file(), bomb, max_uncompressed=10_000_000, max_ratio=100)


# --- filename grammar and index listing (transport) --------------------------

def test_filename_grammar_parses_minute_and_daily_files():
    parsed = dbag.parse_filename('DGAT-posttrade-2026-09-01T08_34.json.gz')
    assert parsed == ('XGAT', 'posttrade',
                      dt.datetime(2026, 9, 1, 8, 34), False)
    daily = dbag.parse_filename('DETR-pretrade-daily-2026-08-31.json.gz')
    assert daily == ('XETR', 'pretrade',
                     dt.datetime(2026, 8, 31, 0, 0), True)


@pytest.mark.parametrize('name', [
    'DGAT-posttrade-2026-09-01T08_34.json',        # not gzip
    'XGAT-posttrade-2026-09-01T08_34.json.gz',     # wrong source prefix
    'DGAT-webinar-2026-09-01T08_34.json.gz',       # wrong channel
    'DGAT-posttrade-2026-13-01T08_34.json.gz',     # impossible date
    '../DGAT-posttrade-2026-09-01T08_34.json.gz',  # traversal
    'DGAT-posttrade-2026-09-01T08_34.json.gz.exe',
])
def test_lookalike_filenames_are_rejected(name):
    assert dbag.parse_filename(name) is None


def test_files_after_lists_ordered_unseen_minute_files():
    class FakeHttp:
        def list_index(self, mic, channel):
            return {'CurrentFiles': [
                'DGAT-posttrade-2026-09-01T08_34.json.gz',
                'DGAT-posttrade-daily-2026-08-31.json.gz',
                'DGAT-posttrade-2026-09-01T08_33.json.gz',
                'DGAT-posttrade-2026-09-01T08_32.json.gz',
                'not-a-feed-file.txt',
                'DETR-posttrade-2026-09-01T08_34.json.gz',  # wrong venue
            ]}

    provider = dbag.DeutscheBoerseProvider(http=FakeHttp())
    cursor = type('Cursor', (), {
        'remote_id': 'DGAT-posttrade-2026-09-01T08_32.json.gz',
        'source_ts': dt.datetime(2026, 9, 1, 8, 32)})()
    files = provider.files_after('XGAT', 'posttrade', cursor)
    assert [f.remote_id for f in files] == [
        'DGAT-posttrade-2026-09-01T08_33.json.gz',
        'DGAT-posttrade-2026-09-01T08_34.json.gz',
    ]
    assert all(not f.is_daily for f in files)


def test_files_after_without_cursor_returns_recent_files_in_order():
    class FakeHttp:
        def list_index(self, mic, channel):
            return {'CurrentFiles': [
                'DGAT-posttrade-2026-09-01T08_34.json.gz',
                'DGAT-posttrade-2026-09-01T08_33.json.gz',
            ]}

    files = dbag.DeutscheBoerseProvider(http=FakeHttp()).files_after(
        'XGAT', 'posttrade', None)
    assert [f.source_ts for f in files] == [
        dt.datetime(2026, 9, 1, 8, 33), dt.datetime(2026, 9, 1, 8, 34)]


def test_a_cold_start_skips_the_listed_backlog():
    """Production 2026-09-01: the index listed almost two days of files,
    the oldest already deleted upstream, and a first-ever cursor started
    at the very back. A cold start must begin near the head of the feed."""
    class FakeHttp:
        def list_index(self, mic, channel):
            return {'CurrentFiles': [
                'DGAT-posttrade-2026-08-30T23_00.json.gz',
                'DGAT-posttrade-2026-09-01T08_10.json.gz',
                'DGAT-posttrade-2026-09-01T08_25.json.gz',
                'DGAT-posttrade-2026-09-01T08_34.json.gz',
            ]}

    provider = dbag.DeutscheBoerseProvider(http=FakeHttp())
    files = provider.files_after('XGAT', 'posttrade', None)
    assert [f.remote_id for f in files] == [
        'DGAT-posttrade-2026-09-01T08_25.json.gz',
        'DGAT-posttrade-2026-09-01T08_34.json.gz',
    ]

    # An existing cursor is downtime recovery: the window must NOT apply.
    cursor = type('Cursor', (), {
        'remote_id': 'DGAT-posttrade-2026-08-30T22_59.json.gz',
        'source_ts': dt.datetime(2026, 8, 30, 22, 59)})()
    recovered = provider.files_after('XGAT', 'posttrade', cursor)
    assert len(recovered) == 4


def test_download_follows_exactly_one_redirect_to_the_observed_bucket(
        monkeypatch):
    calls = []

    class Redirecting:
        status_code = 301
        headers = {'Location':
                   'https://storage.googleapis.com/'
                   'mv-cef-prod-europe-west3-private-min-by-min-files/'
                   'DGAT/DGAT-posttrade-2026-09-01T08_34.json.gz?X-Goog=1'}
        content = b''

    class Payload:
        status_code = 200
        headers = {}
        content = gzip.compress(b'')

        @staticmethod
        def raise_for_status():
            return None

    class FakeSession:
        def get(self, url, timeout=None, allow_redirects=None, stream=None):
            calls.append((url, allow_redirects))
            return Redirecting() if 'mfs.deutsche-boerse.com' in url \
                else Payload()

    http = dbag.DeutscheBoerseHttp()
    http._session = FakeSession()
    body = http.download(feed_file())
    assert body == Payload.content
    assert calls[0][1] is False and calls[1][1] is False
    assert calls[1][0].startswith(
        'https://storage.googleapis.com/'
        'mv-cef-prod-europe-west3-private-min-by-min-files/')


@pytest.mark.parametrize('location', [
    'https://storage.googleapis.com/some-other-bucket/x.json.gz',
    'https://evil.example/mv-cef-prod-europe-west3-private-min-by-min-files/x',
    'http://storage.googleapis.com/'
    'mv-cef-prod-europe-west3-private-min-by-min-files/x.json.gz',
])
def test_redirects_to_any_other_target_are_rejected(location):
    class Redirecting:
        status_code = 301
        headers = {'Location': location}
        content = b''

    class FakeSession:
        def get(self, url, timeout=None, allow_redirects=None, stream=None):
            return Redirecting()

    http = dbag.DeutscheBoerseHttp()
    http._session = FakeSession()
    with pytest.raises(PriceUnavailable, match='redirect'):
        http.download(feed_file())


def test_oversized_downloads_are_rejected():
    class Huge:
        status_code = 200
        headers = {}
        content = b'x' * 200

        @staticmethod
        def raise_for_status():
            return None

    class FakeSession:
        def get(self, url, timeout=None, allow_redirects=None, stream=None):
            return Huge()

    http = dbag.DeutscheBoerseHttp()
    http._session = FakeSession()
    with pytest.raises(PriceUnavailable, match='compressed'):
        http.download(feed_file(), max_compressed=100)


# --- correction semantics as pure functions (plan Task 5 Step 6) -------------

def _event(event_id, action='new', original=None, ts=None, price='100.00'):
    return dbag.TradeEvent(
        mic='XGAT', isin='DE000ZZTST01', event_id=event_id,
        original_event_id=original, action=action,
        event_ts=ts or dt.datetime(2026, 8, 31, 12, 0),
        price=decimal.Decimal(price) if price else None,
        volume=1, is_official_close=False, venue_mic='XGAT')


def test_apply_trade_events_orders_and_applies_corrections():
    first = _event('t1', ts=dt.datetime(2026, 8, 31, 12, 0))
    correction = _event('t2', action='correct', original='t1',
                        ts=dt.datetime(2026, 8, 31, 12, 1), price='101.00')
    updated = dbag.apply_trade_events({}, [correction, first])
    assert set(updated) == {'t2'}
    assert updated['t2'].price == decimal.Decimal('101.00')


def test_apply_trade_events_cancellation_removes_the_original():
    first = _event('t1')
    cancel = _event('t3', action='cancel', original='t1',
                    ts=dt.datetime(2026, 8, 31, 12, 2), price=None)
    assert dbag.apply_trade_events({'t1': first}, [cancel]) == {}


def test_a_correction_for_an_unknown_original_is_rejected():
    orphan = _event('t9', action='correct', original='missing',
                    ts=dt.datetime(2026, 8, 31, 12, 3))
    with pytest.raises(dbag.FeedRejected, match='original'):
        dbag.apply_trade_events({}, [orphan])
