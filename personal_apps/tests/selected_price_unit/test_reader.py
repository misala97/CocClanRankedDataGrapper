"""P01/P04/P05/P09: the bounded reader against a fake store, and its SQL text
against an in-memory SQLite database (syntax, expanding IN, filters, and the
tone classification compared with chatter_tone.classify_recorded_tone).

What is NOT proved here: MariaDB statement timeouts, cancellation, plans and
pool behaviour. SQLite has no statement timeout; nothing below claims one."""
import datetime as dt
import itertools

import pytest
import sqlalchemy as sa
from sqlalchemy.dialects.mysql import pymysql as mysql_pymysql

from features.radar import chatter_tone
from features.radar import price_chart_contract as c
from features.radar import price_chart_reader as reader

from .helpers import (Clock, FakeAdmission, FakeStore, bucket, company_row, instrument_row, naive,
                      series, tone_row, utc)

NOW = utc(2026, 9, 15, 13, 29)                     # 1D 08:00Z..13:29Z, 1W before today's open


@pytest.fixture(autouse=True)
def fresh_cache():
    reader.clear_local_cache()
    yield
    reader.clear_local_cache()


def build(store, *answers, span='1D', now=NOW, clock=None, sources=('bluesky', 'fourchan')):
    admission = FakeAdmission(*answers, log=store.log)
    payload = reader.build_response('AAPL', list(sources), span, now, coordinator=admission,
                                    store=store, clock=clock or Clock())
    return payload, admission


def test_a_cold_1d_request_is_six_bounded_statements_with_identity_before_admission():
    store = FakeStore(buckets=[bucket(naive(2026, 9, 15, 8))])
    payload, _ = build(store)
    assert store.log == ['company_by_symbol', 'primary_candidates', 'admission', 'bucket_rows',
                         'quote_rows', 'daily_rows', 'tone_rows']
    assert len(store.calls) <= 8
    assert all(0 < t <= reader.STATEMENT_TIMEOUT_S for t in store.timeouts.values())
    assert store.params['bucket_rows']['start'] == naive(2026, 9, 15, 8)
    assert store.params['bucket_rows']['end'] == naive(2026, 9, 15, 13, 29)
    assert set(payload) == {'version', 'identity', 'span', 'generated_at', 'window', 'acquisition',
                            'price', 'chatter', 'warnings'}
    assert payload['price'] is None and any('no usable price' in w for w in payload['warnings'])
    assert payload['chatter']['normal_per_slot'] is None
    assert len(payload['chatter']['tone']['slots']) == len(payload['chatter']['slots']) == 22


@pytest.mark.parametrize('store,code,status', [
    (FakeStore(companies=[]), 'unknown_ticker', 404),
    (FakeStore(companies=[company_row(delisted_at=naive(2026, 9, 1))]), 'unknown_ticker', 404),
    (FakeStore(instruments=[]), 'unsupported_instrument', 422),
    (FakeStore(instruments=[instrument_row(), instrument_row(id=8)]), 'unsupported_instrument', 422),
    (FakeStore(instruments=[instrument_row(currency='EUR')]), 'unsupported_instrument', 422),
    (FakeStore(instruments=[instrument_row(provider_symbol=' ')]), 'unsupported_instrument', 422),
    (FakeStore(instruments=[instrument_row(mapped_at=naive(2026, 9, 16))]), 'unsupported_instrument', 422),
    (FakeStore(instruments=[instrument_row(market='de')]), 'unsupported_instrument', 422),
])
def test_identity_refusals_happen_before_any_acquisition_or_data_read(store, code, status):
    with pytest.raises(c.ChartError) as error:
        build(store)
    assert (error.value.code, error.value.status) == (code, status)
    assert 'admission' not in store.log and 'bucket_rows' not in store.calls


def test_an_invalid_ticker_is_400():
    with pytest.raises(c.ChartError) as error:
        reader.build_response('???', ['bluesky'], '1D', NOW, coordinator=FakeAdmission(), store=FakeStore())
    assert (error.value.code, error.value.status) == ('invalid_ticker', 400)


def test_the_bucket_sentinel_refuses_and_is_not_cached():
    store = FakeStore(buckets=[bucket(naive(2026, 9, 15, 8))] * (c.SOURCE_ROW_LIMIT + 1))
    with pytest.raises(c.ChartError) as error:
        build(store)
    assert (error.value.code, error.value.status) == ('read_limit', 503)
    store.buckets = [bucket(naive(2026, 9, 15, 8))]
    build(store)
    assert store.calls.count('bucket_rows') == 2


def test_a_store_failure_is_503_never_an_empty_success():
    store = FakeStore(fail={'bucket_rows': c.ChartError('store_unavailable', 503, 'x')})
    with pytest.raises(c.ChartError) as error:
        build(store)
    assert error.value.status == 503


def test_identity_is_revalidated_every_time_and_a_mapping_change_misses_the_cache():
    clock = Clock()
    store = FakeStore(buckets=[bucket(naive(2026, 9, 15, 8))])
    build(store, clock=clock)
    clock.now += 10
    build(store, clock=clock)
    assert store.calls.count('company_by_symbol') == 2 and store.calls.count('bucket_rows') == 1
    store.instruments = [instrument_row(mapped_at=naive(2026, 8, 2))]
    build(store, clock=clock)
    assert store.calls.count('bucket_rows') == 2
    clock.now += reader.LOCAL_CACHE_SECONDS
    build(store, clock=clock)
    assert store.calls.count('bucket_rows') == 3


def test_a_ready_series_reads_no_fallback_and_wins():
    window = c.window_for('1D', NOW)
    ready = {'state': 'ready', 'retry_after_seconds': None, 'reason': None,
             'series': series(int(window.start.timestamp()), received_at=NOW.timestamp() - 5,
                              values=(100.0, None, 101.0), interval=60)}
    store = FakeStore()
    payload, _ = build(store, ready)
    assert 'quote_rows' not in store.calls and 'daily_rows' not in store.calls
    assert payload['price']['kind'] == 'bar_close' and payload['price']['cache_age_seconds'] == 5
    assert [p['break_before'] for p in payload['price']['points']] == [False, True, True]


def test_pending_then_ready_uses_the_cached_counts_and_the_fallback_is_read_once():
    window = c.window_for('1D', NOW)
    pending = {'state': 'pending', 'retry_after_seconds': 2, 'reason': 'acquiring', 'series': None}
    ready = {'state': 'ready', 'retry_after_seconds': None, 'reason': None,
             'series': series(int(window.start.timestamp()), received_at=NOW.timestamp(), interval=60)}
    store = FakeStore(buckets=[bucket(naive(2026, 9, 15, 8))])
    clock = Clock()
    first, _ = build(store, pending, clock=clock)
    assert first['acquisition']['state'] == 'pending' and first['price'] is None
    second, _ = build(store, ready, clock=clock)
    assert second['price']['kind'] == 'bar_close'
    assert store.calls.count('bucket_rows') == 1 and store.calls.count('quote_rows') == 1
    assert second['chatter']['slots'] == first['chatter']['slots']


def quote(when, price=100.0, source='finnhub', **over):
    row = {'quote_ts': when, 'price': price, 'source': source, 'price_basis': 'trade', 'currency': 'USD',
           'market': 'us', 'mic': 'XNMS', 'fetched_at': when + dt.timedelta(seconds=30), 'is_shadow': False}
    row.update(over)
    return row


def test_quote_fallback_is_one_source_and_never_splices_daily_closes():
    q = [quote(naive(2026, 9, 15, 9, m), 100 + m, 'finnhub') for m in (0, 5, 10)]
    q += [quote(naive(2026, 9, 15, 12, 0), 200.0, 'yahoo_chart')]
    store = FakeStore(quotes=q, daily=[{'close_date': dt.date(2026, 9, 15)}])
    payload, _ = build(store)
    price = payload['price']
    assert 'daily_rows' not in store.calls
    assert (price['kind'], price['source'], price['fallback']) == ('stored_quote', 'yahoo_chart', True)
    assert [p['value'] for p in price['points']] == [200.0]
    assert any('were not combined' in w for w in payload['warnings'])


def test_quote_fallback_excludes_rows_that_are_not_this_instrument_now():
    good = quote(naive(2026, 9, 15, 9, 0), 100.0)
    rejected = [
        quote(naive(2026, 9, 15, 9, 1), 101.0, is_shadow=True),
        quote(naive(2026, 9, 15, 9, 2), 102.0, market=None, mic=None),
        quote(naive(2026, 9, 15, 9, 3), 103.0, mic='XNYS'),
        quote(naive(2026, 9, 15, 9, 4), 104.0, currency='EUR'),
        quote(naive(2026, 9, 15, 9, 5), 0),
        quote(naive(2026, 9, 15, 9, 6), 106.0, fetched_at=naive(2026, 9, 15, 13, 40)),   # fetched after the read
        quote(naive(2026, 9, 15, 9, 7), 107.0, fetched_at=naive(2026, 9, 15, 9, 0)),     # fetched before its own event
        quote(naive(2026, 9, 14, 23, 0), 108.0),                                          # before the window
    ]
    store = FakeStore(quotes=[good] + rejected)
    payload, _ = build(store)
    assert [p['value'] for p in payload['price']['points']] == [100.0]
    before_mapping = FakeStore(quotes=[good], instruments=[instrument_row(mapped_at=naive(2026, 9, 15, 10))])
    payload, _ = build(before_mapping)
    assert payload['price'] is None


def test_quote_gaps_and_market_state_boundaries_break_the_line():
    q = [quote(naive(2026, 9, 15, 9, 0)), quote(naive(2026, 9, 15, 9, 5)),
         quote(naive(2026, 9, 15, 9, 30)), quote(naive(2026, 9, 15, 13, 25)), quote(naive(2026, 9, 15, 13, 28))]
    payload, _ = build(FakeStore(quotes=q))
    # 09:05->09:30 and 09:30->13:25 exceed the 15-minute join; 13:25->13:28 is premarket to premarket.
    assert [p['break_before'] for p in payload['price']['points']] == [False, False, True, True, False]
    across_open = [quote(naive(2026, 9, 15, 13, 25)), quote(naive(2026, 9, 15, 13, 31))]
    reader.clear_local_cache()
    payload, _ = build(FakeStore(quotes=across_open), now=utc(2026, 9, 15, 13, 40))
    assert [p['break_before'] for p in payload['price']['points']] == [False, True]


def test_an_overflowing_quote_read_refuses_the_fallback_rather_than_sampling_it():
    store = FakeStore(quotes=[quote(naive(2026, 9, 15, 9))] * (c.QUOTE_ROW_LIMIT + 1))
    payload, _ = build(store)
    assert payload['price'] is None and 'daily_rows' not in store.calls
    assert any('fallback was refused' in w for w in payload['warnings'])


def daily(day, close=50.0, **over):
    row = {'close_date': day, 'close': close, 'currency': 'USD', 'source': 'massive_grouped',
           'price_basis': 'close', 'adjustment_basis': 'split',
           'fetched_at': dt.datetime.combine(day, dt.time(23)), 'market': 'us', 'mic': 'XNMS',
           'is_shadow': False}
    row.update(over)
    return row


def test_1w_uses_only_stored_daily_closes_as_separate_dots():
    days = [dt.date(2026, 9, d) for d in (8, 9, 10, 11, 14)]
    store = FakeStore(daily=[daily(d, 50.0 + i) for i, d in enumerate(days)]
                      + [daily(dt.date(2026, 9, 15), 99.0)]            # outside this window
                      + [daily(dt.date(2026, 9, 10), 1.0, fetched_at=naive(2026, 9, 10, 19))])  # before its close
    payload, _ = build(store, span='1W')
    price = payload['price']
    assert 'quote_rows' not in store.calls
    assert price['kind'] == 'daily_close' and price['adjustment_basis'] == 'split'
    assert [p['at'] for p in price['points']] == ['2026-09-08T20:00:00Z', '2026-09-09T20:00:00Z',
                                                  '2026-09-11T20:00:00Z', '2026-09-14T20:00:00Z']
    assert [p['break_before'] for p in price['points']] == [False, True, True, True]
    assert any('unusable' in w for w in payload['warnings'])


def test_a_tone_failure_degrades_only_tone():
    store = FakeStore(buckets=[bucket(naive(2026, 9, 15, 8), count=4)],
                      quotes=[quote(naive(2026, 9, 15, 9))],
                      fail={'tone_rows': c.ChartError('read_limit', 503, 'slow')})
    payload, _ = build(store)
    assert payload['chatter']['slots'][0]['count'] == 4
    assert payload['chatter']['tone']['slots'][0]['status'] == 'unavailable'
    assert payload['price']['kind'] == 'stored_quote'
    assert any(w.startswith('tone: unavailable (read_limit)') for w in payload['warnings'])


def test_tone_rows_reconcile_through_the_reader():
    when = naive(2026, 9, 15, 8)
    store = FakeStore(buckets=[bucket(when, count=3)], tone=[tone_row(when, bullish=2, bearish=1)])
    payload, _ = build(store)
    assert payload['chatter']['tone']['slots'][0] == {
        'bullish': 2, 'bearish': 1, 'neutral': 0, 'unjudged': 0, 'unavailable': 0, 'status': 'complete'}
    assert store.params['tone_rows']['lower'] == when and store.params['tone_rows']['upper'] == naive(2026, 9, 15, 13, 29)


def test_a_waiting_window_reads_no_price_and_says_why():
    store = FakeStore()
    payload, _ = build(store, now=utc(2026, 9, 15, 8))
    assert payload['chatter']['slots'] == [] and payload['price'] is None
    assert 'quote_rows' not in store.calls and 'daily_rows' not in store.calls
    assert any(w.startswith('window:') for w in payload['warnings'])


# --- the SQL text ------------------------------------------------------------------

class _Dialect:
    name = 'mysql'
    is_mariadb = True


class _Bind:
    dialect = _Dialect()


class _Result:
    def mappings(self):
        return self

    def all(self):
        return []


class _CapturingSession:
    def __init__(self):
        self.statements = []

    def get_bind(self):
        return _Bind()

    def execute(self, statement, params):
        self.statements.append((str(statement), params))
        return _Result()

    def rollback(self):
        pass


def test_every_new_statement_is_statement_scoped_with_its_sentinel_on_mariadb():
    session = _CapturingSession()
    store = reader.ChartSqlStore(session)
    start, end = naive(2026, 9, 15, 8), naive(2026, 9, 15, 13)
    store.bucket_rows('AAPL', ['bluesky', 'reddit'], start, end, timeout_s=0.75)
    store.quote_rows('AAPL', 'XNMS', start, end, end, timeout_s=1.0)
    store.daily_rows('AAPL', 'XNMS', start.date(), end.date(), end, timeout_s=0.5)
    store.tone_rows('AAPL', ['bluesky'], start, end, timeout_s=0.001)
    prefixes = [sql.split(' FOR ')[0] for sql, _ in session.statements]
    assert prefixes == ['SET STATEMENT max_statement_time=0.750', 'SET STATEMENT max_statement_time=1.000',
                        'SET STATEMENT max_statement_time=0.500', 'SET STATEMENT max_statement_time=0.001']
    limits = [params['row_limit'] for _, params in session.statements]
    assert limits == [c.SOURCE_ROW_LIMIT + 1, c.QUOTE_ROW_LIMIT + 1, c.DAILY_ROW_LIMIT + 1, c.SOURCE_ROW_LIMIT + 1]
    assert 'radar_posts' not in session.statements[0][0]
    assert 'body' not in session.statements[3][0].lower() and 'title' not in session.statements[3][0].lower()


SCHEMA = """
CREATE TABLE radar_bucket_sources (ticker TEXT, bucket_start TEXT, source TEXT, mention_count INTEGER,
                                   status TEXT, source_config_version TEXT);
CREATE TABLE radar_quotes (ticker TEXT, market TEXT, mic TEXT, currency TEXT, quote_ts TEXT, price NUMERIC,
                           source TEXT, price_basis TEXT, fetched_at TEXT, is_shadow INTEGER);
CREATE TABLE radar_daily_closes (ticker TEXT, market TEXT, mic TEXT, currency TEXT, close_date TEXT,
                                 close NUMERIC, source TEXT, price_basis TEXT, adjustment_basis TEXT,
                                 fetched_at TEXT, is_shadow INTEGER);
CREATE TABLE radar_mention_events (id INTEGER PRIMARY KEY, source TEXT, external_id TEXT, ticker TEXT,
                                   bucket_start TEXT, confidence TEXT, promoted INTEGER,
                                   counts_as_human_chatter INTEGER);
CREATE TABLE radar_posts (id INTEGER PRIMARY KEY, source TEXT, external_id TEXT);
CREATE TABLE radar_mentions (id INTEGER PRIMARY KEY, post_id INTEGER, ticker TEXT, sentiment_relevance TEXT,
                             sentiment_content_origin TEXT, sentiment_attitude TEXT, llm_sentiment TEXT,
                             lexicon_sentiment REAL);
"""


@pytest.fixture()
def sqlite_store():
    engine = sa.create_engine('sqlite://')
    session = sa.orm.Session(engine)
    for statement in SCHEMA.strip().split(';'):
        if statement.strip():
            session.execute(sa.text(statement))
    yield reader.ChartSqlStore(session), session
    session.close()


def iso(when):
    return when.isoformat(sep=' ')


def test_the_bucket_quote_and_daily_sql_filter_what_they_claim(sqlite_store):
    store, session = sqlite_store
    rows = [('AAPL', '2026-09-15 08:00:00', 'bluesky'), ('AAPL', '2026-09-15 08:15:00', 'reddit:stocks'),
            ('AAPL', '2026-09-15 07:45:00', 'bluesky'), ('AAPL', '2026-09-15 13:00:00', 'bluesky'),
            ('MSFT', '2026-09-15 08:00:00', 'bluesky'), ('AAPL', '2026-09-15 08:30:00', 'fourchan')]
    for ticker, when, source in rows:
        session.execute(sa.text("INSERT INTO radar_bucket_sources VALUES (:t, :w, :s, 1, 'ok', 'v1')"),
                        {'t': ticker, 'w': when, 's': source})
    got = store.bucket_rows('AAPL', ['bluesky', 'reddit:stocks'], '2026-09-15 08:00:00', '2026-09-15 13:00:00',
                            timeout_s=1)
    assert [(r['bucket_start'], r['source']) for r in got] == [
        ('2026-09-15 08:00:00', 'bluesky'), ('2026-09-15 08:15:00', 'reddit:stocks')]
    quotes = [('us', 'XNMS', '2026-09-15 09:00:00', '2026-09-15 09:00:30', 0),
              ('us', 'XNMS', '2026-09-15 09:01:00', '2026-09-15 09:01:30', 1),
              ('us', 'XNYS', '2026-09-15 09:02:00', '2026-09-15 09:02:30', 0),
              (None, None, '2026-09-15 09:03:00', '2026-09-15 09:03:30', 0),
              ('us', 'XNMS', '2026-09-15 09:04:00', '2026-09-15 13:40:00', 0),
              ('us', 'XNMS', None, '2026-09-15 09:05:30', 0)]
    for market, mic, ts, fetched, shadow in quotes:
        session.execute(sa.text("INSERT INTO radar_quotes VALUES ('AAPL', :m, :mic, 'USD', :ts, 100, 'finnhub',"
                                " 'trade', :f, :sh)"), {'m': market, 'mic': mic, 'ts': ts, 'f': fetched, 'sh': shadow})
    got = store.quote_rows('AAPL', 'XNMS', '2026-09-15 08:00:00', '2026-09-15 13:29:00', '2026-09-15 13:29:00',
                           timeout_s=1)
    assert [r['quote_ts'] for r in got] == ['2026-09-15 09:00:00']
    for day, shadow, fetched in (('2026-09-14', 0, '2026-09-14 23:00:00'), ('2026-09-14', 1, '2026-09-14 23:00:00'),
                                 ('2026-09-15', 0, '2026-09-15 23:00:00'), ('2026-09-01', 0, '2026-09-01 23:00:00')):
        session.execute(sa.text("INSERT INTO radar_daily_closes VALUES ('AAPL', 'us', 'XNMS', 'USD', :d, 50,"
                                " 'massive_grouped', 'close', 'split', :f, :sh)"),
                        {'d': day, 'f': fetched, 'sh': shadow})
    got = store.daily_rows('AAPL', 'XNMS', '2026-09-08', '2026-09-15', '2026-09-15 13:29:00', timeout_s=1)
    assert [(r['close_date'], r['is_shadow']) for r in got] == [('2026-09-14', 0)]


ATTITUDES = (None, 'positive', 'negative', 'mixed', 'none', 'other')
VERDICTS = (None, 'bullish', 'bearish', 'neutral', 'unclear')


def test_the_tone_sql_classifies_exactly_as_classify_recorded_tone(sqlite_store):
    store, session = sqlite_store
    base = naive(2026, 9, 15, 8)
    expected = {}
    ids = itertools.count(1)
    for index, (attitude, verdict) in enumerate(itertools.product(ATTITUDES, VERDICTS)):
        when = base + dt.timedelta(minutes=15 * index)
        event = next(ids)
        session.execute(sa.text("INSERT INTO radar_mention_events VALUES (:id, 'bluesky', :x, 'AAPL', :w,"
                                " 'high', 0, NULL)"), {'id': event, 'x': f'p{event}', 'w': iso(when)})
        session.execute(sa.text("INSERT INTO radar_posts VALUES (:id, 'bluesky', :x)"), {'id': event, 'x': f'p{event}'})
        session.execute(sa.text("INSERT INTO radar_mentions VALUES (:id, :id, 'AAPL', NULL, NULL, :a, :v, 0.9)"),
                        {'id': event, 'a': attitude, 'v': verdict})
        expected[iso(when)] = chatter_tone.classify_recorded_tone(
            attitude=attitude, llm_sentiment=verdict, lexicon_sentiment=0.9)
    rows = store.tone_rows('AAPL', ['bluesky'], iso(base), iso(base + dt.timedelta(days=1)), timeout_s=1)
    assert len(rows) == len(expected)
    for row in rows:
        category = [k for k in c.TONE_CATEGORIES if row[k] == 1]
        assert category == [expected[row['bucket_start']]], row
        assert row['total'] == 1 and row['eligibility_conflicts'] == 0


def test_the_tone_sql_marks_invalid_events_unavailable_and_skips_ineligible_ones(sqlite_store):
    store, session = sqlite_store
    when = iso(naive(2026, 9, 15, 8))

    def event(id_, confidence='high', promoted=0, human=None, ticker='AAPL', post=True, mentions=((None, None),)):
        session.execute(sa.text("INSERT INTO radar_mention_events VALUES (:id, 'bluesky', :x, :t, :w, :c, :p, :h)"),
                        {'id': id_, 'x': f'e{id_}', 't': ticker, 'w': when, 'c': confidence, 'p': promoted, 'h': human})
        if post:
            session.execute(sa.text("INSERT INTO radar_posts VALUES (:id, 'bluesky', :x)"), {'id': id_, 'x': f'e{id_}'})
        for n, (relevance, origin) in enumerate(mentions):
            session.execute(sa.text("INSERT INTO radar_mentions VALUES (:id, :pid, 'AAPL', :r, :o, 'positive', NULL, NULL)"),
                            {'id': id_ * 10 + n, 'pid': id_, 'r': relevance, 'o': origin})

    event(1)                                                   # valid: bullish
    event(2, mentions=(('irrelevant', None),))                 # conflict
    event(3, mentions=((None, None), (None, None)))            # two mentions
    event(4, post=False, mentions=())                          # no post
    event(5, confidence='low')                                 # excluded
    event(6, confidence='low', promoted=1)                     # promoted: bullish
    event(7, human=0)                                          # not human chatter: excluded
    event(8, ticker='MSFT')                                    # other ticker: excluded
    rows = store.tone_rows('AAPL', ['bluesky'], when, iso(naive(2026, 9, 15, 9)), timeout_s=1)
    assert len(rows) == 1
    row = rows[0]
    assert (row['total'], row['bullish'], row['unavailable'], row['eligibility_conflicts']) == (5, 2, 3, 1)
