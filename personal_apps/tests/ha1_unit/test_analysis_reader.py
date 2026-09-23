"""The bounded reader against a fake store (PLAN C02/C11-C14 logic that does
not need an engine): identity revalidation, error mapping, sentinel limits,
statement order, the monotonic time budget and the SQL the store sends.
DB-free; run with --confcutdir=tests/ha1_unit.

MariaDB statement timeout, cancellation, EXPLAIN and pooled-connection
hygiene are NOT provable here; they are the T4 target-bound gate."""
import datetime as dt
from decimal import Decimal

import pytest
import sqlalchemy as sa
from sqlalchemy import exc as sa_exc
from sqlalchemy.dialects.mysql import pymysql as mysql_pymysql

from features.radar import analysis
from features.radar import analysis_contract as contract
from features.radar.analysis_contract import ContractError

NOW = dt.datetime(2026, 9, 14, 12, 30, tzinfo=dt.timezone.utc)
D7, D13 = dt.date(2026, 9, 7), dt.date(2026, 9, 13)


def company(**over):
    row = {'id': 11, 'symbol': 'AAA', 'name': 'Aaa Corp',
           'first_seen': dt.datetime(2026, 1, 1), 'delisted_at': None}
    row.update(over)
    return row


def instrument(**over):
    row = {'id': 7, 'ticker': 'AAA', 'market': 'us', 'venue': 'NYSE', 'mic': 'XNYS',
           'provider_symbol': 'AAA', 'currency': 'USD', 'is_primary': 1,
           'mapping_status': 'mapped', 'mapped_at': dt.datetime(2026, 8, 1)}
    row.update(over)
    return row


class Clock:
    """A monotonic clock the test moves by hand."""

    def __init__(self, now=100.0):
        self.now = now

    def __call__(self):
        return self.now


class FakeStore:
    def __init__(self, companies=None, instruments=None, closes=None, buckets=None,
                 fail=None, clock=None, cost=None):
        self.companies = companies if companies is not None else [company()]
        self.instruments = instruments if instruments is not None else [instrument()]
        self.closes = closes or []
        self.buckets = buckets or []
        self.fail = fail or {}
        self.clock = clock
        self.cost = cost or {}
        self.calls = []
        self.timeouts = {}

    def _maybe(self, name, timeout_s):
        self.calls.append(name)
        self.timeouts[name] = timeout_s
        if self.clock is not None:
            self.clock.now += self.cost.get(name, 0.0)
        if name in self.fail:
            raise self.fail[name]

    def company_by_symbol(self, ticker, *, timeout_s):
        self._maybe('company_by_symbol', timeout_s)
        return [c for c in self.companies if c['symbol'] == ticker][:2]

    def company_by_id(self, company_id, *, timeout_s):
        self._maybe('company_by_id', timeout_s)
        return [c for c in self.companies if c['id'] == company_id][:1]

    def primary_candidates(self, ticker, *, timeout_s):
        self._maybe('primary_candidates', timeout_s)
        return [i for i in self.instruments
                if i['ticker'] == ticker and i['market'] == 'us' and i['is_primary']][:2]

    def instrument_by_id(self, instrument_id, *, timeout_s):
        self._maybe('instrument_by_id', timeout_s)
        return [i for i in self.instruments if i['id'] == instrument_id][:1]

    def daily_closes(self, ticker, mic, start, end, read_start, *, timeout_s):
        self._maybe('daily_closes', timeout_s)
        return self.closes[:8]

    def bucket_sources(self, ticker, start, end, *, timeout_s):
        self._maybe('bucket_sources', timeout_s)
        return self.buckets[:43009]


def refused(fn, *args, **kw):
    with pytest.raises(ContractError) as info:
        fn(*args, **kw)
    return info.value


# --- C02 resolve --------------------------------------------------------------

class TestResolve:
    def test_a_unique_eligible_primary_resolves_to_ids(self):
        store = FakeStore()
        out = analysis.resolve_company('aaa', NOW, store)
        assert out['company'] == {'id': 11, 'ticker': 'AAA', 'name': 'Aaa Corp',
                                  'first_seen': '2026-01-01T00:00:00Z'}
        assert out['instrument']['id'] == 7 and out['instrument']['currency'] == 'USD'
        assert out['instrument']['mapped_at'] == '2026-08-01T00:00:00Z'
        assert store.calls == ['company_by_symbol', 'primary_candidates']

    def test_unknown_and_delisted_are_404(self):
        assert refused(analysis.resolve_company, 'ZZZ', NOW, FakeStore()).status == 404
        gone = FakeStore(companies=[company(delisted_at=dt.datetime(2026, 5, 1))])
        error = refused(analysis.resolve_company, 'AAA', NOW, gone)
        assert error.status == 404 and error.code == 'delisted_company'

    def test_two_eligible_primaries_is_409_not_first(self):
        store = FakeStore(instruments=[instrument(), instrument(id=8, mic='XNGS')])
        error = refused(analysis.resolve_company, 'AAA', NOW, store)
        assert error.status == 409 and error.code == 'ambiguous_primary'

    @pytest.mark.parametrize('over', [
        {'currency': 'EUR'}, {'mic': ' '}, {'mic': None}, {'provider_symbol': ''},
        {'venue': ''}, {'mapping_status': 'unverified'},
        {'mapped_at': dt.datetime(2026, 9, 14, 12, 31)}, {'mapped_at': None},
    ])
    def test_ineligible_candidates_are_422_with_no_fallback(self, over):
        store = FakeStore(instruments=[instrument(**over)])
        error = refused(analysis.resolve_company, 'AAA', NOW, store)
        assert error.status == 422 and error.code == 'ineligible_instrument'

    def test_no_us_primary_at_all_is_422(self):
        store = FakeStore(instruments=[instrument(market='de', mic='XETR', currency='EUR')])
        assert refused(analysis.resolve_company, 'AAA', NOW, store).code == 'ineligible_instrument'

    def test_injection_style_ticker_is_refused_before_any_read(self):
        store = FakeStore()
        error = refused(analysis.resolve_company, "AAA' OR 1=1 --", NOW, store)
        assert error.status == 400 and error.code == 'invalid_ticker'
        assert store.calls == []


# --- C02/C11-C14 read ---------------------------------------------------------

class TestRead:
    def test_statement_order_and_payload_shape(self):
        closes = [{'close_date': dt.date(2026, 9, 9), 'close': Decimal('10.5'),
                   'currency': 'USD', 'source': 'massive_grouped', 'price_basis': 'close',
                   'adjustment_basis': 'split', 'market': 'us', 'mic': 'XNYS',
                   'is_shadow': 0, 'fetched_at': dt.datetime(2026, 9, 9, 23)}]
        buckets = [{'bucket_start': dt.datetime(2026, 9, 9) + dt.timedelta(minutes=15 * s),
                    'source': 'bluesky', 'mention_count': 1, 'status': 'ok',
                    'source_config_version': 'cfgA'} for s in range(96)]
        store = FakeStore(closes=closes, buckets=buckets)
        out = analysis.read_company(11, 7, D7, D13, NOW, store)
        assert store.calls == ['company_by_id', 'instrument_by_id', 'daily_closes',
                               'bucket_sources']
        assert out['schema_version'] == 1 and out['mode'] == 'retrospective'
        assert out['identity_scope'] == 'current_mapping_retrospective'
        assert out['request'] == {'from': '2026-09-07', 'to': '2026-09-13',
                                  'chatter_timezone': 'UTC', 'max_days': 7}
        assert out['read_started_at'] == '2026-09-14T12:30:00Z'
        assert out['read_finished_at'].endswith('Z')
        assert len(out['price']['days']) == 7 and len(out['chatter']['days']) == 7
        assert out['price']['usable_count'] == 1
        assert out['chatter']['days'][2]['mentions'] == 96
        assert 'warnings' not in out['price'] and 'warnings' not in out['chatter']
        assert any(w.startswith('identity:') for w in out['warnings'])

    def test_empty_stores_are_a_successful_independent_empty_state(self):
        out = analysis.read_company(11, 7, D7, D13, NOW, FakeStore())
        assert all(p['state'] == 'missing' for p in out['price']['days'])
        assert all(c['coverage'] == 'unavailable' for c in out['chatter']['days'])

    def test_missing_ids_are_404(self):
        assert refused(analysis.read_company, 99, 7, D7, D13, NOW, FakeStore()).code == 'unknown_company'
        assert refused(analysis.read_company, 11, 99, D7, D13, NOW, FakeStore()).code == 'unknown_instrument'

    @pytest.mark.parametrize('over', [
        {'ticker': 'BBB'}, {'is_primary': 0}, {'market': 'de'}, {'mapping_status': 'stale'},
    ])
    def test_a_remapped_or_mismatched_identity_is_409_never_retargeted(self, over):
        store = FakeStore(instruments=[instrument(**over)])
        error = refused(analysis.read_company, 11, 7, D7, D13, NOW, store)
        assert error.status == 409 and error.code == 'identity_changed'
        assert 'daily_closes' not in store.calls

    def test_a_pinned_read_revalidates_the_chosen_mapping_without_a_uniqueness_scan(self):
        # A second eligible primary appearing later is the resolver's to
        # refuse; the pinned read checks only its own chosen row, and says so
        # by never asking for candidates.
        store = FakeStore(instruments=[instrument(), instrument(id=8, mic='XNGS')])
        analysis.read_company(11, 7, D7, D13, NOW, store)
        assert 'primary_candidates' not in store.calls

    def test_an_unsupported_selection_is_422(self):
        store = FakeStore(instruments=[instrument(currency='EUR')])
        error = refused(analysis.read_company, 11, 7, D7, D13, NOW, store)
        assert error.status == 422 and error.code == 'ineligible_instrument'

    def test_a_delisted_company_is_404_on_read(self):
        store = FakeStore(companies=[company(delisted_at=dt.datetime(2026, 9, 1))])
        assert refused(analysis.read_company, 11, 7, D7, D13, NOW, store).status == 404

    def test_sentinel_rows_are_a_503_limit_not_truncated_success(self):
        close = {'close_date': dt.date(2026, 9, 9), 'close': Decimal('1'), 'currency': 'USD',
                 'source': 'finnhub', 'price_basis': 'close', 'adjustment_basis': 'split',
                 'market': 'us', 'mic': 'XNYS', 'is_shadow': 0,
                 'fetched_at': dt.datetime(2026, 9, 9)}
        store = FakeStore(closes=[close] * 8)
        error = refused(analysis.read_company, 11, 7, D7, D13, NOW, store)
        assert error.status == 503 and error.code == 'analysis_limit'
        bucket = {'bucket_start': dt.datetime(2026, 9, 9), 'source': 'bluesky',
                  'mention_count': 1, 'status': 'ok', 'source_config_version': 'a'}
        store = FakeStore(buckets=[bucket] * 43009)
        error = refused(analysis.read_company, 11, 7, D7, D13, NOW, store)
        assert error.status == 503 and error.code == 'analysis_limit'

    def test_a_store_failure_is_503_and_the_next_request_is_fresh(self):
        failing = FakeStore(fail={'daily_closes': ContractError('analysis_unavailable', 503, 'x')})
        error = refused(analysis.read_company, 11, 7, D7, D13, NOW, failing)
        assert error.code == 'analysis_unavailable' and 'bucket_sources' not in failing.calls
        fresh = FakeStore()
        assert analysis.read_company(11, 7, D7, D13, NOW, fresh)['price']['usable_count'] == 0

    def test_more_than_seven_days_is_refused_before_any_read(self):
        store = FakeStore()
        error = refused(analysis.read_company, 11, 7, D7, dt.date(2026, 9, 14), NOW, store)
        assert error.status == 400 and store.calls == []

    def test_unknown_mic_gets_no_calendar_and_says_so(self):
        store = FakeStore(instruments=[instrument(mic='XXXX')])
        out = analysis.read_company(11, 7, D7, D13, NOW, store)
        assert {p['calendar_hint'] for p in out['price']['days']} == {'unknown'}
        assert any(w.startswith('calendar:') for w in out['warnings'])


# --- P2-3 the monotonic budget (fake clock) -----------------------------------

class TestBudget:
    @pytest.fixture()
    def clock(self, monkeypatch):
        clock = Clock()
        monkeypatch.setattr(analysis.time, 'monotonic', clock)
        return clock

    def test_each_statement_gets_min_of_two_seconds_and_what_is_left(self, clock):
        store = FakeStore(clock=clock, cost={'company_by_id': 1.0, 'instrument_by_id': 1.2,
                                             'daily_closes': 1.9})
        analysis.read_company(11, 7, D7, D13, NOW, store)
        assert store.timeouts['company_by_id'] == pytest.approx(2.0)
        assert store.timeouts['instrument_by_id'] == pytest.approx(2.0)
        # 1.0 + 1.2 spent: 2.8 left, still capped at 2.
        assert store.timeouts['daily_closes'] == pytest.approx(2.0)
        # 4.1 spent: 0.9 left, so the last statement gets 0.9, not 2.
        assert store.timeouts['bucket_sources'] == pytest.approx(0.9)
        assert max(store.timeouts.values()) <= analysis.STATEMENT_TIMEOUT_S

    def test_an_expired_budget_refuses_the_next_statement_before_sending_it(self, clock):
        # The closes statement itself returns inside its own limit, but the
        # budget is spent by the time the buckets would be asked for.
        store = FakeStore(clock=clock, cost={'daily_closes': 5.0})
        error = refused(analysis.read_company, 11, 7, D7, D13, NOW, store)
        assert error.code == 'analysis_limit' and error.status == 503
        assert 'bucket_sources' not in store.calls

    def test_under_a_millisecond_left_is_refused_not_sent_as_unlimited(self, clock):
        store = FakeStore(clock=clock, cost={'company_by_id': 4.9995})
        error = refused(analysis.read_company, 11, 7, D7, D13, NOW, store)
        assert error.code == 'analysis_limit'
        assert store.calls == ['company_by_id']

    def test_materialization_past_the_budget_is_refused(self, clock):
        # The rows arrived, but materializing them used the rest of the budget.
        store = FakeStore(clock=clock, cost={'bucket_sources': 5.5})
        error = refused(analysis.read_company, 11, 7, D7, D13, NOW, store)
        assert error.code == 'analysis_limit'

    def test_reduction_past_the_budget_is_refused(self, clock, monkeypatch):
        real = contract.chatter_days

        def slow(*args, **kwargs):
            clock.now += 6.0
            return real(*args, **kwargs)
        monkeypatch.setattr(contract, 'chatter_days', slow)
        error = refused(analysis.read_company, 11, 7, D7, D13, NOW, FakeStore())
        assert error.code == 'analysis_limit'

    def test_the_resolver_is_budgeted_too(self, clock):
        store = FakeStore(clock=clock, cost={'company_by_symbol': 4.4})
        analysis.resolve_company('AAA', NOW, store)
        assert store.timeouts['primary_candidates'] == pytest.approx(0.6)
        store = FakeStore(clock=clock, cost={'company_by_symbol': 5.1})
        assert refused(analysis.resolve_company, 'AAA', NOW, store).code == 'analysis_limit'
        assert 'primary_candidates' not in store.calls


# --- the SQL the store sends --------------------------------------------------

class _Session:
    """A stub session: records what would be executed, or raises."""

    def __init__(self, dialect_name='sqlite', mariadb=False, error=None, fail_on=None):
        self.error = error
        self.fail_on = fail_on
        self.rolled_back = False
        self.executed = []
        self.dialect = type('D', (), {'name': dialect_name, 'is_mariadb': mariadb})()

    def get_bind(self):
        return type('B', (), {'dialect': self.dialect})()

    def execute(self, statement, params):
        self.executed.append((str(statement), params))
        if self.error is not None and (self.fail_on is None or self.fail_on in str(statement)):
            raise self.error
        return type('R', (), {'mappings': lambda s: type('M', (), {'all': lambda m: []})()})()

    def rollback(self):
        self.rolled_back = True


def _dbapi(errno, cls=sa_exc.OperationalError):
    return cls('SELECT 1', {}, Exception(errno, 'boom'))


class TestSqlStore:
    def test_timeout_errno_is_a_limit(self):
        session = _Session(error=_dbapi(1969))
        error = refused(analysis.SqlStore(session).company_by_id, 1, timeout_s=2.0)
        assert error.code == 'analysis_limit' and session.rolled_back

    def test_other_store_errors_are_unavailable_without_sql_in_the_message(self):
        session = _Session(error=_dbapi(1045))
        error = refused(analysis.SqlStore(session).company_by_id, 1, timeout_s=2.0)
        assert error.code == 'analysis_unavailable' and session.rolled_back
        assert 'SELECT' not in error.message and 'boom' not in error.message

    def test_a_missing_table_on_the_closes_read_is_translated_by_rows(self):
        # The same injection the API suite uses: the failure is raised INSIDE
        # SqlStore._rows, so production translation is what is exercised.
        session = _Session(dialect_name='mysql', mariadb=True,
                           error=_dbapi(1146, sa_exc.ProgrammingError),
                           fail_on='radar_daily_closes')
        store = analysis.SqlStore(session)
        responses = {'radar_ticker_universe': [company()], 'radar_instruments': [instrument()]}

        def execute(statement, params):
            text = str(statement)
            session.executed.append((text, params))
            if 'radar_daily_closes' in text:
                raise session.error
            rows = next(v for k, v in responses.items() if k in text)
            return type('R', (), {'mappings': lambda s: type('M', (), {'all': lambda m: rows})()})()
        session.execute = execute
        error = refused(analysis.read_company, 11, 7, D7, D13, NOW, store)
        assert error.code == 'analysis_unavailable' and error.status == 503
        assert session.rolled_back
        assert not any('radar_bucket_sources' in text for text, _ in session.executed)

    def test_timeout_syntax_follows_the_dialect_with_fractional_seconds(self):
        session = _Session()
        store = analysis.SqlStore(session)
        assert store.timeout_dialect() == 'sqlite:none'
        assert store._timed('SELECT 1', 2.0) == 'SELECT 1'
        session.dialect = type('D', (), {'name': 'mysql', 'is_mariadb': True})()
        assert store._timed('SELECT 1', 2.0) == 'SET STATEMENT max_statement_time=2.000 FOR SELECT 1'
        assert store._timed('SELECT 1', 0.8) == 'SET STATEMENT max_statement_time=0.800 FOR SELECT 1'
        assert store._timed('SELECT 1', 0.0019) == 'SET STATEMENT max_statement_time=0.001 FOR SELECT 1'
        with pytest.raises(ContractError):
            store._timed('SELECT 1', 0.0004)
        session.dialect = type('D', (), {'name': 'mysql', 'is_mariadb': False})()
        assert store._timed('SELECT 1', 2.0).startswith('SELECT /*+ MAX_EXECUTION_TIME(2000) */')
        assert store._timed('SELECT 1', 0.25).startswith('SELECT /*+ MAX_EXECUTION_TIME(250) */')

    def test_every_timed_statement_compiles_with_named_binds_for_pymysql(self):
        dialect = mysql_pymysql.dialect()
        read_start = dt.datetime(2026, 9, 14, 12, 30)
        store = analysis.SqlStore(_Session(dialect_name='mysql', mariadb=True))
        for name, sql, params in analysis.data_statements(11, 7, 'AAA', 'XNYS', D7, D13, read_start):
            for text in (store._timed(sql, 1.25), 'EXPLAIN ' + sql):
                compiled = sa.text(text).bindparams(**params).compile(dialect=dialect)
                # pymysql is a positional driver: every named bind becomes one
                # %s, and positiontup says which value goes where.
                assert set(compiled.params) == set(params), name
                assert len(compiled.positiontup) == str(compiled).count('%s'), name
                assert set(compiled.positiontup) == set(params), name
                assert '%%s' not in str(compiled), name
            assert str(store._timed(sql, 1.25)).startswith(
                'SET STATEMENT max_statement_time=1.250 FOR SELECT')

    def test_rewrapping_driver_sql_in_text_loses_every_bind(self):
        # The REVIEW-1 P1-2 anti-pattern, pinned so nobody reintroduces it:
        # driver-level %s SQL wrapped in sa.text has no bind names at all.
        dialect = mysql_pymysql.dialect()
        _, sql, params = analysis.data_statements(
            11, 7, 'AAA', 'XNYS', D7, D13, dt.datetime(2026, 9, 14))[2]
        driver_sql = str(sa.text(sql).bindparams(**params).compile(dialect=dialect))
        rewrapped = sa.text('EXPLAIN ' + driver_sql).compile(dialect=dialect)
        assert rewrapped.positiontup == [] and '%%s' in str(rewrapped)

    def test_the_store_sends_the_same_binds_the_harness_explains(self):
        session = _Session(dialect_name='mysql', mariadb=True)
        store = analysis.SqlStore(session)
        read_start = dt.datetime(2026, 9, 14, 12, 30)
        store.company_by_id(11, timeout_s=2.0)
        store.instrument_by_id(7, timeout_s=2.0)
        store.daily_closes('AAA', 'XNYS', D7, D13, read_start, timeout_s=2.0)
        store.bucket_sources('AAA', D7, D13, timeout_s=2.0)
        expected = analysis.data_statements(11, 7, 'AAA', 'XNYS', D7, D13, read_start)
        assert [params for _, params in session.executed] == [p for _, _, p in expected]
        assert expected[2][2]['row_limit'] == contract.DAILY_ROW_SENTINEL
        assert expected[3][2]['row_limit'] == contract.BUCKET_ROW_SENTINEL
        assert expected[3][2]['utc_end'] == dt.datetime(2026, 9, 14)
