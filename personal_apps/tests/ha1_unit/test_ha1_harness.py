"""DB-free tests for the HA1 DB/preview harness rules (CORRECTION-1, CORRECTION-2).

Nothing here opens a database, starts a server, touches the network or
launches a browser. The harness scripts themselves (probe_analysis.py,
preview_fixtures.py, verify_preview.py, tests/test_radar_analysis_api.py)
remain unexecuted; these tests pin the rules they import: exact fixture
ownership, collision refusal, guaranteed cleanup and its structured report,
budgets, timeout and deadline evaluation, preview identity and source/build
fingerprint, C15/C16 case recording, contrast, the pre-app gate, runtime Git
under a foreign owner (a real `git` subprocess on a temporary repository) and
the full-access host member gate (app.py's own gate function, run in a toy
Flask app without importing the application).
"""
import ast
import datetime as dt
import json
import re
import subprocess
import sys
from pathlib import Path

import pytest
from sqlalchemy.dialects import mysql

PERSONAL_APPS = Path(__file__).resolve().parents[2]
HA1 = PERSONAL_APPS / 'scratchpad' / 'ha1'
sys.path.insert(0, str(HA1))

import ha1_harness as harness  # noqa: E402
import local_runtime  # noqa: E402
from features.radar import analysis_contract as contract  # noqa: E402

TOKEN = 'A1B2C3'


class FakeFixtureStore:
    def __init__(self, rows=None, fail_delete=False):
        self.rows = {kind: [dict(key) for key in keys] for kind, keys in (rows or {}).items()}
        self.log = []
        self.fail_delete = fail_delete

    def existing(self, symbols, usernames):
        self.log.append('existing')
        found = {}
        for kind, keys in self.rows.items():
            for key in keys:
                owner = key.get('username') if kind == 'user' else key.get('symbol', key.get('ticker'))
                if owner in symbols or owner in usernames:
                    found.setdefault(kind, []).append(owner)
        return found

    def create(self, owned, kind, key):
        self.log.append(f'create:{kind}')
        self.rows.setdefault(kind, []).append(dict(key))
        owned.record(kind, key)

    def prepare_cleanup(self):
        self.log.append('prepare')

    def delete(self, kind, keys):
        self.log.append(f'delete:{kind}:{len(keys)}')
        if self.fail_delete:
            raise RuntimeError('delete failed')
        self.rows[kind] = [key for key in self.rows.get(kind, []) if key not in keys]

    def count_owned(self, kind, keys):
        return sum(1 for key in self.rows.get(kind, []) if key in keys)


PRE_EXISTING = {
    'company': [{'id': 1, 'symbol': 'ZQPREEXIST'}],
    'bucket': [{'ticker': 'ZQPREEXIST', 'bucket_start': dt.datetime(2026, 9, 9), 'source': 'bluesky'}],
    'user': [{'id': 5, 'username': 'zq-ha1-old-plain'}],
}


def planned():
    return harness.owned_symbol('M', TOKEN), harness.owned_symbol('S', TOKEN)


# --- ownership ----------------------------------------------------------------------

class TestOwnedFixtures:
    def test_generated_identities_are_valid_short_and_distinct(self):
        m, s = planned()
        assert m == 'ZQMA1B2C3' and len(m) <= 12 and m != s
        assert contract.valid_ticker(m) == m
        assert harness.owned_username('plain', TOKEN) == 'zq-ha1-a1b2c3-plain'
        assert len(harness.run_token()) == 6
        with pytest.raises(ValueError):
            harness.owned_symbol('M', 'x' * 20)

    def test_a_collision_refuses_before_any_mutation(self):
        m, s = planned()
        store = FakeFixtureStore({'bucket': [{'ticker': s, 'bucket_start': dt.datetime(2026, 9, 9),
                                              'source': 'x'}]})
        with pytest.raises(harness.FixtureCollision) as info:
            with harness.OwnedFixtures(store, (m, s)):
                pytest.fail('the block must not run')
        assert s in str(info.value)
        assert store.log == ['existing']

    def test_a_failure_cleans_up_exactly_the_recorded_rows_and_nothing_pre_existing(self):
        m, s = planned()
        store = FakeFixtureStore(PRE_EXISTING)
        with pytest.raises(RuntimeError, match='seeding broke'):
            with harness.OwnedFixtures(store, (m, s), [harness.owned_username('plain', TOKEN)]) as owned:
                store.create(owned, 'company', {'id': 2, 'symbol': m})
                store.create(owned, 'bucket', {'ticker': m, 'bucket_start': dt.datetime(2026, 9, 9),
                                               'source': 'bluesky'})
                store.create(owned, 'user', {'id': 6, 'username': harness.owned_username('plain', TOKEN)})
                raise RuntimeError('seeding broke')
        assert store.rows['company'] == PRE_EXISTING['company']
        assert store.rows['bucket'] == PRE_EXISTING['bucket']
        assert store.rows['user'] == PRE_EXISTING['user']
        # Children first, and a rollback before any delete.
        deletes = [entry for entry in store.log if entry.startswith('delete')]
        assert store.log.index('prepare') < store.log.index(deletes[0])
        assert deletes == ['delete:bucket:1', 'delete:company:1', 'delete:user:1']
        assert owned.cleanup_report()['status'] == 'complete'

    def test_the_block_cleans_up_on_success_too(self):
        m, s = planned()
        store = FakeFixtureStore()
        with harness.OwnedFixtures(store, (m, s)) as owned:
            store.create(owned, 'close', {'id': 9, 'ticker': m})
        assert store.rows['close'] == [] and owned.keys['close'] == []

    def test_only_planned_identities_can_be_recorded(self):
        m, s = planned()
        store = FakeFixtureStore()
        owned = harness.OwnedFixtures(store, (m, s))
        with pytest.raises(RuntimeError):
            owned.record('company', {'id': 1, 'symbol': m})  # before the collision check
        with owned:
            for kind, key in (('company', {'id': 1, 'symbol': 'ZQPREEXIST'}),
                              ('instrument', {'id': 1, 'ticker': 'AAPL'}),
                              ('bucket', {'ticker': 'ZQPREEXIST', 'bucket_start': dt.datetime(2026, 9, 9),
                                          'source': 'x'}),
                              ('user', {'id': 1, 'username': 'zq-ha1-old-plain'})):
                with pytest.raises(ValueError):
                    owned.record(kind, key)

    def test_persist_keeps_rows_and_the_manifest_round_trips_only_to_its_target(self):
        m, s = planned()
        store = FakeFixtureStore()
        bucket = {'ticker': m, 'bucket_start': dt.datetime(2026, 9, 9, 0, 15), 'source': 'bluesky'}
        with harness.OwnedFixtures(store, (m, s)) as owned:
            store.create(owned, 'company', {'id': 3, 'symbol': m})
            store.create(owned, 'bucket', bucket)
            manifest = owned.persist('127.0.0.1:3407/ha1')
        assert store.rows['company'] == [{'id': 3, 'symbol': m}]
        assert owned.cleanup_report()['status'] == 'kept'
        document = json.loads(json.dumps(manifest))
        with pytest.raises(ValueError, match='not the gated target'):
            harness.OwnedFixtures.from_manifest(store, document, '127.0.0.1:3408/other')
        assert store.rows['bucket'] == [bucket]
        restored = harness.OwnedFixtures.from_manifest(store, document, '127.0.0.1:3407/ha1')
        restored.cleanup()
        assert store.rows['company'] == [] and store.rows['bucket'] == []

    def test_persist_does_not_keep_rows_when_the_block_fails(self):
        m, s = planned()
        store = FakeFixtureStore()
        with pytest.raises(OSError):
            with harness.OwnedFixtures(store, (m, s)) as owned:
                store.create(owned, 'company', {'id': 3, 'symbol': m})
                owned.persist('t')
                raise OSError('manifest write failed')
        assert store.rows['company'] == []

    def test_an_incomplete_cleanup_is_reported_not_swallowed(self):
        m, s = planned()
        store = FakeFixtureStore(fail_delete=True)
        with pytest.raises(harness.CleanupIncomplete, match='company') as info:
            with harness.OwnedFixtures(store, (m, s)) as owned:
                store.create(owned, 'company', {'id': 3, 'symbol': m})
        assert info.value.remaining == {'company': [{'id': 3, 'symbol': m}]}

    def test_delete_now_removes_one_owned_sentinel(self):
        m, s = planned()
        store = FakeFixtureStore()
        sentinel = {'ticker': m, 'bucket_start': harness.off_grid_sentinel(dt.date(2026, 9, 7)),
                    'source': 'zqsrc00'}
        with harness.OwnedFixtures(store, (m, s)) as owned:
            store.create(owned, 'bucket', sentinel)
            owned.delete_now('bucket', sentinel)
            assert store.rows['bucket'] == [] and owned.keys['bucket'] == []
            with pytest.raises(ValueError):
                owned.delete_now('bucket', {**sentinel, 'source': 'other'})


class TestCleanupReport:
    """U7: the original failure and the cleanup failure both survive."""

    def test_both_failures_and_the_remaining_identities_are_kept_without_secrets(self):
        m, s = planned()
        user = harness.owned_username('plain', TOKEN)
        store = FakeFixtureStore(fail_delete=True)
        owned = harness.OwnedFixtures(store, (m, s), [user])
        with pytest.raises(RuntimeError, match='seeding broke') as info:
            with owned:
                store.create(owned, 'company', {'id': 3, 'symbol': m})
                store.create(owned, 'bucket', {'ticker': m, 'bucket_start': dt.datetime(2026, 9, 9),
                                               'source': 'bluesky'})
                store.create(owned, 'user', {'id': 4, 'username': user})
                raise RuntimeError('seeding broke on mysql+pymysql://root:hunter2@127.0.0.1:3407/ha1 '
                                   'password=hunter2')
        report = harness.run_failure_report(info.value, owned)
        text = json.dumps(report, default=str)
        assert 'hunter2' not in text
        assert report['exit_code'] == 1
        assert report['original_failure'].startswith('RuntimeError: seeding broke')
        assert report['cleanup']['status'] == 'incomplete'
        assert set(report['cleanup']['remaining']) == {'bucket', 'company', 'user'}
        assert report['cleanup']['remaining']['user'] == [{'id': 4, 'username': user}]
        assert len(report['failures']) == 2
        assert report['failures'][0].startswith('original failure')
        assert report['failures'][1].startswith('cleanup failure')
        assert m in report['failures'][1] and user in report['failures'][1]
        assert any('cleanup incomplete' in note for note in getattr(info.value, '__notes__', []))

    def test_a_cleanup_failure_alone_still_exits_nonzero(self):
        m, s = planned()
        store = FakeFixtureStore(fail_delete=True)
        owned = harness.OwnedFixtures(store, (m, s))
        with pytest.raises(harness.CleanupIncomplete) as info:
            with owned:
                store.create(owned, 'close', {'id': 7, 'ticker': m})
        report = harness.run_failure_report(info.value, owned)
        assert report['exit_code'] == 1 and report['cleanup']['remaining'] == {'close': [{'id': 7, 'ticker': m}]}

    def test_success_and_not_started(self):
        m, s = planned()
        store = FakeFixtureStore()
        owned = harness.OwnedFixtures(store, (m, s))
        with owned:
            store.create(owned, 'close', {'id': 7, 'ticker': m})
        assert harness.run_failure_report(None, owned)['exit_code'] == 0
        early = harness.run_failure_report(SystemExit('no admin'), None)
        assert early['exit_code'] == 1 and early['cleanup']['status'] == 'not_started'

    def test_redaction(self):
        assert harness.redact('mysql://u:secret@h/db') == 'mysql://u:***@h/db'
        assert 'abc' not in harness.redact('token=abc; password: abc')


class TestSqlStatements:
    """The SQL the fixture store would send, compiled without a database."""

    @pytest.fixture(scope='class')
    def fx(self):
        import ha1_fixtures
        return ha1_fixtures

    def test_deletes_and_counts_use_exact_keys_never_like(self, fx):
        m, _ = planned()
        keys = {
            'bucket': [{'ticker': m, 'bucket_start': dt.datetime(2026, 9, 9), 'source': 'bluesky'}],
            'close': [{'id': 7, 'ticker': m}], 'instrument': [{'id': 8, 'ticker': m}],
            'company': [{'id': 9, 'symbol': m}], 'user': [{'id': 10, 'username': 'zq-ha1-a1b2c3-plain'}],
        }
        dialect = mysql.dialect()
        for kind, owned_keys in keys.items():
            for statement in [*fx.delete_statements(kind, owned_keys), *fx.count_statements(kind, owned_keys)]:
                sql = str(statement.compile(dialect=dialect)).upper()
                assert 'LIKE' not in sql and ' IN ' in sql, (kind, sql)
                if kind == 'bucket':
                    assert 'TICKER, RADAR_BUCKET_SOURCES.BUCKET_START' in sql
                else:
                    assert '.ID IN' in sql, sql

    def test_large_key_sets_are_chunked(self, fx):
        m, _ = planned()
        keys = [{'ticker': m, 'bucket_start': dt.datetime(2026, 9, 9) + dt.timedelta(minutes=15 * n),
                 'source': 'zqsrc00'} for n in range(1201)]
        assert len(list(fx.delete_statements('bucket', keys))) == 3

    def test_collision_checks_are_exact_equality_sets(self, fx):
        dialect = mysql.dialect()
        statements = fx.existence_statements(planned(), ['zq-ha1-a1b2c3-plain'])
        assert [table for table, _ in statements] == [
            'radar_ticker_universe', 'radar_instruments', 'radar_daily_closes',
            'radar_bucket_sources', 'app_user']
        for _, statement in statements:
            sql = str(statement.compile(dialect=dialect)).upper()
            assert 'LIKE' not in sql and ' IN ' in sql


# --- budgets, plans, timeouts, deadline -------------------------------------------------

def measured(**over):
    base = {'statuses': [200] * 21, 'max_data_statements': 4, 'bucket_rows': 43008,
            'distinct_sources': 64, 'response_bytes': 900_000,
            'reader_alloc_bytes': 20 * 1024 * 1024, 'warm_ms': [100.0] * 20}
    base.update(over)
    return base


class TestBudgets:
    def test_nearest_rank_p95(self):
        assert harness.nearest_rank_p95(list(range(1, 21))) == 19
        assert harness.nearest_rank_p95([5.0]) == 5.0
        with pytest.raises(ValueError):
            harness.nearest_rank_p95([])

    def test_a_measurement_within_every_budget_passes(self):
        assert harness.budget_failures('max', measured()) == []

    @pytest.mark.parametrize('over, text', [
        ({'max_data_statements': 5}, 'max_data_statements=5'),
        ({'bucket_rows': 43009}, 'bucket_rows=43009'),
        ({'distinct_sources': 65}, 'distinct_sources=65'),
        ({'response_bytes': 1024 * 1024 + 1}, 'response_bytes'),
        ({'reader_alloc_bytes': 32 * 1024 * 1024 + 1}, 'reader_alloc_bytes'),
        ({'warm_ms': [100.0] * 18 + [1500.0, 1500.0]}, 'warm p95'),
        ({'warm_ms': [100.0] * 19}, '19 warm requests'),
        ({'statuses': [200] * 20 + [503]}, 'answered 200'),
        ({'reader_alloc_bytes': None}, 'not measured'),
    ])
    def test_each_budget_is_asserted(self, over, text):
        failures = harness.budget_failures('max', measured(**over))
        assert failures and any(text in failure for failure in failures), failures

    def test_the_row_sentinel_arithmetic_and_the_off_grid_key(self):
        assert harness.BUCKET_ROW_CAP == 43008 == contract.BUCKET_ROW_LIMIT
        assert harness.BUCKET_ROW_SENTINEL == contract.BUCKET_ROW_SENTINEL
        day = dt.date(2026, 9, 7)
        sentinel = harness.off_grid_sentinel(day)
        assert contract._slot_index(sentinel, day) is None

    def test_plans_must_be_index_constrained(self):
        assert harness.plan_failures('closes', [{'type': 'range'}, {'type': 'const'}]) == []
        assert harness.plan_failures('closes', [{'type': 'ALL'}])
        assert harness.plan_failures('closes', [])

    def test_budget_constants_match_the_reader(self):
        from features.radar import analysis
        assert harness.STATEMENT_LIMIT_S == analysis.STATEMENT_TIMEOUT_S
        assert harness.READER_BUDGET_S == analysis.READER_DEADLINE_S
        assert harness.MIN_STATEMENT_S == analysis.MIN_STATEMENT_S


def probe(kind, classification, elapsed=1.02):
    return {'classification': classification, 'elapsed_s': elapsed}


def subsecond(**over):
    result = {'classification': 'interrupted_error', 'requested_s': 0.25, 'effective_s': 0.2499,
              'rendered': 'SET STATEMENT max_statement_time=0.249 FOR', 'elapsed_s': 0.31,
              'overshoot_s': 0.06, 'budget_check_after': 'refused:analysis_limit'}
    result.update(over)
    return result


def hygiene(**over):
    result = {'dialect': 'mariadb:set_statement',
              'probes': {'sleep': probe('sleep', 'interrupted_error'),
                         'cpu': probe('cpu', 'interrupted_error'),
                         'cpu_subsecond': subsecond()},
              'recovery_ok': True,
              'connection_id_before': 42, 'connection_id_after': 42,
              'session_max_statement_time_before': '0.000000',
              'session_max_statement_time_after': '0.000000'}
    result.update(over)
    return result


class TestTimeout:
    def test_classification(self):
        assert harness.classify_timeout('cpu', 1969, None, 1.0, None) == 'interrupted_error'
        assert harness.classify_timeout('cpu', 3024, None, 1.0, None) == 'interrupted_error'
        assert harness.classify_timeout('cpu', 1146, None, 0.1, None) == 'other_error'
        assert harness.classify_timeout('cpu', None, 0, 40.0, None) == 'not_interrupted'
        # MySQL-family SLEEP returns 1 when interrupted, 0 when it completes.
        assert harness.classify_timeout('sleep', None, 1, 1.01, 3.0) == 'interrupted_silently'
        assert harness.classify_timeout('sleep', None, 0, 3.0, 3.0) == 'not_interrupted'
        assert harness.classify_timeout('sleep', None, 1, 2.95, 3.0) == 'not_interrupted'

    def test_a_clean_interrupt_on_one_connection_passes(self):
        assert harness.timeout_failures(hygiene(), 1.0) == []

    def test_a_silently_interrupted_sleep_is_not_the_pass_the_cpu_probe_must_earn(self):
        probes = hygiene()['probes']
        probes['sleep'] = probe('sleep', 'interrupted_silently')
        result = hygiene(probes=probes)
        assert harness.timeout_failures(result, 1.0) == []
        result['probes']['cpu'] = probe('cpu', 'not_interrupted', 30.0)
        assert any('CPU-bound' in f for f in harness.timeout_failures(result, 1.0))

    @pytest.mark.parametrize('over, text', [
        ({'dialect': 'mysql:max_execution_time'}, 'MariaDB target is required'),
        ({'probes': {'sleep': probe('sleep', 'not_interrupted', 3.0),
                     'cpu': probe('cpu', 'interrupted_error'), 'cpu_subsecond': subsecond()}}, 'uncancelled'),
        ({'probes': {'sleep': probe('sleep', 'interrupted_error'),
                     'cpu': probe('cpu', 'interrupted_error', 2.5), 'cpu_subsecond': subsecond()}}, 'only after'),
        ({'connection_id_after': 43}, 'one physical connection'),
        ({'connection_id_before': None, 'connection_id_after': None}, 'one physical connection'),
        ({'session_max_statement_time_after': '1.000000'}, 'session max_statement_time changed'),
        ({'probes': {}}, 'did not run'),
        ({'probes': {'sleep': probe('sleep', 'interrupted_error'), 'cpu': probe('cpu', 'interrupted_error')}},
         'sub-second CPU probe did not run'),
        ({'probes': {'sleep': probe('sleep', 'interrupted_error'), 'cpu': probe('cpu', 'interrupted_error'),
                     'cpu_subsecond': subsecond(classification='not_interrupted')}},
         'sub-second CPU statement was'),
        ({'recovery_ok': False}, 'recovery unproven'),
        ({'recovery_ok': None}, 'recovery unproven'),
    ])
    def test_every_unproven_or_dirty_outcome_fails(self, over, text):
        failures = harness.timeout_failures(hygiene(**over), 1.0)
        assert any(text in failure for failure in failures), failures

    @pytest.mark.parametrize('over, text', [
        ({'classification': 'not_interrupted'}, 'sub-second CPU statement was'),
        ({'classification': 'interrupted_silently'}, 'sub-second CPU statement was'),
        ({'requested_s': 1.0}, 'requested 1.0'),
        ({'effective_s': 0.0}, 'effective limit'),
        ({'effective_s': 0.3}, 'effective limit'),
        ({'rendered': 'SET STATEMENT max_statement_time=0 FOR'}, 'fractional'),
        ({'elapsed_s': 1.4}, 'stopped only after'),
        ({'elapsed_s': None}, 'elapsed time was not measured'),
        ({'overshoot_s': None}, 'overshoot was not recorded'),
    ])
    def test_the_subsecond_probe_must_be_complete_and_interrupted(self, over, text):
        failures = harness.subsecond_failures(subsecond(**over))
        assert any(text in failure for failure in failures), failures
        assert harness.subsecond_failures(subsecond()) == []
        assert harness.subsecond_failures(None) == ['timeout: the sub-second CPU probe did not run']

    def test_the_cpu_probes_scan_rows_instead_of_a_silently_truncated_benchmark(self):
        """LOCAL-QA runtime evidence (MariaDB 10.11.14): max_statement_time cut
        BENCHMARK() off at the limit but it returned 0 with no error, so the
        probe classified a real interrupt as not_interrupted. A row scan raises
        1969. Both CPU probes must send the row scan."""
        assert 'BENCHMARK' not in harness.CPU_PROBE_SQL.upper()
        assert re.fullmatch(r'SELECT COUNT\(\*\) AS value FROM seq_1_to_\d{9,} WHERE .+', harness.CPU_PROBE_SQL)
        source = (HA1 / 'ha1_fixtures.py').read_text(encoding='utf-8')
        assert 'BENCHMARK' not in source.upper()
        assert source.count('harness.CPU_PROBE_SQL') == 2

    def test_the_subsecond_limit_comes_from_the_production_budget_and_rendering(self):
        """What the probe will send, derived by the reader's own code."""
        from features.radar import analysis

        class Dialect:
            name = 'mysql'
            is_mariadb = True

        class Bind:
            dialect = Dialect()

        class Session:
            def get_bind(self):
                return Bind()

        budget = analysis.ReaderBudget(seconds=harness.SUBSECOND_REQUEST_S)
        effective = budget.statement_timeout()
        assert 0.2 < effective <= harness.SUBSECOND_REQUEST_S
        rendered = analysis.SqlStore(Session())._timed('SELECT 1', effective)
        assert re.fullmatch(r'SET STATEMENT max_statement_time=0\.2\d\d FOR SELECT 1', rendered), rendered
        assert analysis.seconds_literal(0.2499) == '0.249'
        assert harness.subsecond_failures(subsecond(effective_s=effective, rendered=rendered.split(' FOR ')[0]
                                                    + ' FOR')) == []


def deadline(**over):
    result = {
        'reader': {'status': 503, 'code': 'analysis_limit', 'elapsed_s': 5.08, 'overshoot_s': 0.08,
                   'handed_timeouts_s': [2.0, 2.0, 1.03, 0.041]},
        'http': {'status': 503, 'code': 'analysis_limit', 'elapsed_s': 5.13, 'overshoot_s': 0.13,
                 'full_request_ms': 5130.0, 'handed_timeouts_s': [2.0, 2.0, 1.03, 0.04]},
        'acceptance': harness.DEADLINE_ACCEPTANCE,
    }
    result.update(over)
    return result


class TestDeadline:
    """The REVIEW-2 deadline ruling: semantics asserted, overshoot reported."""

    def test_an_exhausted_budget_that_refuses_passes_the_semantics(self):
        assert harness.deadline_failures(deadline()) == []

    def test_overshoot_is_never_judged_against_a_self_chosen_tolerance(self):
        slow = deadline()
        slow['reader'] = {**slow['reader'], 'elapsed_s': 9.5, 'overshoot_s': 4.5}
        assert harness.deadline_failures(slow) == []
        assert slow['acceptance'] == 'mastermind_ruling_required'

    @pytest.mark.parametrize('scope, over, text', [
        ('reader', {'status': 200, 'code': None}, 'not 503 analysis_limit'),
        ('http', {'code': 'analysis_unavailable'}, 'not 503 analysis_limit'),
        ('reader', {'handed_timeouts_s': [2.0, 2.0, 0.0]}, 'statement limits outside'),
        ('reader', {'handed_timeouts_s': [2.5]}, 'statement limits outside'),
        ('reader', {'handed_timeouts_s': [2.0] * 5}, 'issued 5 data statements'),
        ('http', {'handed_timeouts_s': []}, 'limits were not recorded'),
        ('reader', {'overshoot_s': None}, 'overshoot_s was not measured'),
        ('http', {'full_request_ms': None}, 'full-request duration'),
    ])
    def test_semantic_violations_fail(self, scope, over, text):
        result = deadline()
        result[scope] = {**result[scope], **over}
        failures = harness.deadline_failures(result)
        assert any(text in failure for failure in failures), failures

    def test_missing_cases_and_self_approval_fail(self):
        assert harness.deadline_failures(None)
        assert any('reader budget-exhaustion' in f for f in harness.deadline_failures(deadline(reader=None)))
        assert any('Mastermind ruling' in f for f in harness.deadline_failures(deadline(acceptance='pass')))


class TestDialect:
    """U10: the dialect label only after a connection initialized it."""

    def test_an_uninitialized_dialect_is_not_labelled(self):
        class Fresh:
            name = 'mysql'
            is_mariadb = False
            server_version_info = None
        record = harness.dialect_record(Fresh(), lambda: pytest.fail('must not be read'))
        assert record['initialized'] is False and record['timeout_dialect'] is None and record['failure']

    def test_an_initialized_dialect_is_labelled_by_the_product(self):
        class Connected:
            name = 'mysql'
            is_mariadb = True
            server_version_info = (10, 11, 14)
        record = harness.dialect_record(Connected(), lambda: 'mariadb:set_statement')
        assert record == {'initialized': True, 'server_version_info': [10, 11, 14],
                          'timeout_dialect': 'mariadb:set_statement', 'failure': None}


# --- source/build fingerprint (U8) ------------------------------------------------------

def _tree(root: Path):
    files = {
        'personal_apps/app.py': 'app',
        'personal_apps/features/radar/analysis.py': 'reader',
        'personal_apps/templates/radar/hub.html': '<main>',
        'personal_apps/scratchpad/ha1/ha1_harness.py': 'rules',
        'personal_apps/static/radar/src/hub/Analysis.tsx': 'view',
        'personal_apps/static/radar/dist/assets/hub-1.js': 'bundle',
        'personal_apps/static/radar/dist/.vite/manifest.json': '{}',
    }
    for relative, text in files.items():
        path = root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding='utf-8')
    return files


class TestFingerprint:
    def test_deterministic_and_covering_untracked_source_and_build(self, tmp_path):
        files = _tree(tmp_path)
        first, second = harness.source_fingerprint(tmp_path), harness.source_fingerprint(tmp_path)
        assert first == second
        assert sorted(first['files']) == sorted(files)
        assert first['build_files'] == 2

    def test_mutable_records_logs_caches_and_tests_do_not_move_it(self, tmp_path):
        _tree(tmp_path)
        before = harness.source_fingerprint(tmp_path)['digest']
        for relative in ('radar-design/artifacts/ha1/runtime/preview-runtime-5041.json',
                         'radar-design/artifacts/ha1/runtime/preview-fixtures.json',
                         'personal_apps/scratchpad/ha1/__pycache__/ha1_harness.cpython-312.pyc',
                         'personal_apps/features/radar/__pycache__/analysis.cpython-312.pyc',
                         'personal_apps/static/radar/src/hub/Analysis.test.tsx',
                         'personal_apps/scratchpad/ha1/server.log',
                         'personal_apps/scratchpad/ha1/runtime/record.json'):
            path = tmp_path / relative
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text('mutable', encoding='utf-8')
        assert harness.source_fingerprint(tmp_path)['digest'] == before

    def test_every_mutable_harness_output_is_excluded_by_rule_and_sources_are_not(self):
        """By rule, not only by include scope: the real output locations the
        scripts write (derived from their own constants) and caches, logs and
        test files are excluded; ordinary sources are not."""
        runtime = local_runtime.RUNTIME_DIR.relative_to(local_runtime.CANDIDATE).as_posix()
        preview = (local_runtime.RUNTIME_DIR.parent / 'preview').relative_to(local_runtime.CANDIDATE).as_posix()
        for relative in (f'{runtime}/preview-runtime-5041.json', f'{runtime}/preview-fixtures.json',
                         f'{runtime}/preview-fixtures-report.json', f'{runtime}/probe_analysis.json',
                         f'{preview}/verify_preview.json', f'{preview}/typical-1440.png',
                         'personal_apps/scratchpad/ha1/__pycache__/local_runtime.cpython-312.pyc',
                         'personal_apps/static/radar/src/hub/Analysis.test.tsx',
                         'personal_apps/static/radar/src/hub/analysisApi.test.ts',
                         'personal_apps/serve.stderr.log'):
            assert harness.fingerprint_excluded(relative), relative
        for relative in ('personal_apps/static/radar/src/runtime/clock.ts',
                         'personal_apps/features/radar/analysis.py',
                         'personal_apps/static/radar/dist/assets/hub-1.js'):
            assert not harness.fingerprint_excluded(relative), relative

    def test_a_source_or_build_change_is_drift_that_names_the_file(self, tmp_path):
        _tree(tmp_path)
        started = harness.source_fingerprint(tmp_path)
        assert harness.fingerprint_failures(started, started) == []
        (tmp_path / 'personal_apps/features/radar/analysis.py').write_text('edited', encoding='utf-8')
        edited = harness.source_fingerprint(tmp_path)
        failures = harness.fingerprint_failures(started, edited)
        assert len(failures) == 1 and 'personal_apps/features/radar/analysis.py' in failures[0]
        assert 'restart' in failures[0] and 'NOT stopped' in failures[0]
        (tmp_path / 'personal_apps/features/radar/analysis.py').write_text('reader', encoding='utf-8')
        (tmp_path / 'personal_apps/static/radar/dist/assets/hub-2.js').write_text('new', encoding='utf-8')
        assert 'hub-2.js' in harness.fingerprint_failures(started, harness.source_fingerprint(tmp_path))[0]

    def test_missing_build_or_record_fingerprint_refuses(self, tmp_path):
        _tree(tmp_path)
        for path in (tmp_path / 'personal_apps/static/radar/dist').rglob('*'):
            if path.is_file():
                path.unlink()
        bare = harness.source_fingerprint(tmp_path)
        assert any('npm run build' in f for f in harness.fingerprint_failures(bare, bare))
        assert any('no source/build fingerprint' in f for f in harness.fingerprint_failures(None, bare))

    def test_the_candidate_inputs_include_untracked_ha1_files_and_exclude_runtime_state(self):
        inputs = harness.fingerprint_inputs(local_runtime.CANDIDATE)
        for required in ('personal_apps/scratchpad/ha1/ha1_harness.py',
                         'personal_apps/scratchpad/ha1/verify_preview.py',
                         'personal_apps/features/radar/analysis.py',
                         'personal_apps/features/radar/routes/analysis.py',
                         'personal_apps/static/radar/src/hub/Analysis.tsx',
                         'personal_apps/templates/radar/hub.html', 'personal_apps/app.py'):
            assert required in inputs, required
        assert not any('__pycache__' in name or '/runtime/' in name or name.endswith(('.pyc', '.log'))
                       or name.endswith(('.test.ts', '.test.tsx')) or name.startswith('radar-design/')
                       for name in inputs)


# --- preview identity, case recording, C15/C16 ----------------------------------------------

FINGERPRINT = {'version': 1, 'digest': 'd1', 'files': {'personal_apps/app.py': 'h'}, 'build_files': 1}


def runtime(**over):
    record = {'version': 2, 'target': '127.0.0.1:3407/ha1', 'registry': 'C:/reg.json',
              'candidate_root': 'C:/cand', 'branch': 'codex/radar-ha1-us-daily-explore',
              'head': 'abc', 'port': 5041, 'pid': 1, 'nonce': 'n0nce', 'fingerprint': FINGERPRINT}
    record.update(over)
    return record


def identity(record, **over):
    args = {'target': '127.0.0.1:3407/ha1', 'registry': 'C:/reg.json', 'root': 'C:/cand',
            'branch': 'codex/radar-ha1-us-daily-explore', 'head': 'abc', 'port': 5041,
            'header_nonce': 'n0nce', 'pid_alive': True, 'fingerprint': FINGERPRINT}
    args.update(over)
    return harness.preview_identity_failures(record, **args)


class TestPreviewIdentity:
    def test_the_gated_candidate_passes(self):
        assert identity(runtime()) == []

    @pytest.mark.parametrize('record_over, args_over, text', [
        ({'target': '127.0.0.1:3407/other'}, {}, 'runtime target'),
        ({'registry': 'C:/elsewhere.json'}, {}, 'runtime registry'),
        ({'candidate_root': 'C:/main'}, {}, 'candidate_root'),
        ({'head': 'def'}, {}, 'runtime head'),
        ({'branch': 'main'}, {}, 'runtime branch'),
        ({'port': 5021}, {}, 'runtime port'),
        ({'version': 1}, {}, 'runtime version'),
        ({}, {'header_nonce': None}, 'nonce'),
        ({}, {'header_nonce': 'forged'}, 'nonce'),
        ({}, {'pid_alive': False}, 'not alive'),
        ({'fingerprint': None}, {}, 'no source/build fingerprint'),
        ({}, {'fingerprint': {**FINGERPRINT, 'digest': 'd2', 'files': {'personal_apps/app.py': 'x'}}},
         'drift'),
        ({}, {'fingerprint': None}, 'not computed'),
    ])
    def test_any_mismatch_refuses(self, record_over, args_over, text):
        assert any(text in f for f in identity(runtime(**record_over), **args_over))

    def test_no_record_refuses(self):
        assert 'no runtime identity record' in identity(None)[0]


class TestCaseRecording:
    """U6/U9: zero-check cases, shared-block attribution, unsupported checks."""

    def test_an_exception_in_a_shared_block_is_attributed_to_every_case(self):
        results = {}
        with harness.cases(results, ('resolve_pin_replace', 'de_entry_us_label'), '390') as (c, de):
            c.check(True, 'unused')
            raise TimeoutError('selector never appeared')
        assert results['resolve_pin_replace']['failures'] == ['[390] raised TimeoutError: selector never appeared']
        assert results['de_entry_us_label']['failures'] == ['[390] raised TimeoutError: selector never appeared']

    def test_the_old_nested_form_would_have_hidden_the_outer_case(self):
        """Documents the defect this replaced: with two nested context
        managers the inner one swallows the exception."""
        results = {}
        with harness.case(results, 'outer') as outer:
            outer.check(True, 'reached')
            with harness.case(results, 'inner'):
                raise RuntimeError('boom')
        assert results['outer']['failures'] == [] and results['inner']['failures']

    def test_a_case_with_zero_checks_fails(self):
        results = {}
        with harness.case(results, 'contrast_text'):
            pass
        assert 'zero checks is not a pass' in results['contrast_text']['failures'][0]
        assert harness.case_failures({'x': {'failures': [], 'checks': 0}}, required=('x',))

    def test_an_unsupported_check_is_a_failure_not_a_success(self):
        results = {}
        with harness.case(results, 'menu_escape', '320') as c:
            c.unsupported('menu button hidden')
        assert results['menu_escape']['failures'] == ['[320] UNSUPPORTED, not a pass: menu button hidden']

    def test_checks_accumulate_across_labels_and_facts_keep_their_label(self):
        results = {}
        for label in ('1440', '390'):
            with harness.case(results, 'viewport', label) as c:
                c.check(True, 'x')
                c.facts['w'] = label
        assert results['viewport']['checks'] == 2
        assert results['viewport']['facts'] == {'1440': {'w': '1440'}, '390': {'w': '390'}}

    def test_every_acceptance_case_is_required(self):
        assert len(harness.c16_failures({})) == len(harness.ACCEPTANCE_CASES)
        results = {name: {'failures': [], 'checks': 1} for name in harness.ACCEPTANCE_CASES}
        assert harness.c16_failures(results) == []
        results['limit_503']['failures'].append('[390] missing text')
        assert harness.c16_failures(results) == ['limit_503: [390] missing text']
        for required in ('keyboard_days', 'zoom_200', 'session_expiry', 'invalid_range_ticker_only',
                         'non_admin_access', 'touch_targets_44', 'us_primary_usd_visible_mobile',
                         'contrast_graphics', 'price_line_runs', 'skip_link_and_tab_order',
                         'c15_no_board_poll_on_analysis', 'c15_back_to_pre_selection_analysis',
                         'c15_signed_out_redirects', 'c15_filter_only_bookmark', 'source_build_identity'):
            assert required in harness.ACCEPTANCE_CASES

    def test_verify_preview_records_every_required_case_and_the_ruled_assertions(self):
        source = (HA1 / 'verify_preview.py').read_text(encoding='utf-8')
        for name in harness.ACCEPTANCE_CASES:
            if name.startswith('viewport_'):
                continue
            assert f"'{name}'" in source, name
        assert "f'viewport_{label}'" in source
        assert 'length + 1' in source and "== '#analysis'" in source and 'page.go_forward()' in source
        assert 'BOARD_QUIET_MS' in source and "'/radar/api/board'" in source
        assert 'button.tap()' in source and 'harness.contrast_failures' in source
        assert 'harness.contrast_ratio' not in source  # no ad-hoc, skippable contrast path
        assert 'with case(' not in source  # no locally nested attribution

    def test_local_qa_run2_harness_faults_stay_corrected(self):
        """LOCAL-QA run2: substring 't=' matched 'segment='; unroute before
        releasing held routes raised and left the handler installed; the skip
        link check started Tab from an earlier focus point."""
        source = (HA1 / 'verify_preview.py').read_text(encoding='utf-8')
        assert "'t=' not in page.evaluate" not in source
        assert "'t' not in parse_qs(urlsplit(page.url).query)" in source
        loading = source[source.index("'loading_state'"):source.index("'timeout_error'")]
        assert loading.index('route.continue_()') < loading.index('injected.unroute(COMPANY_API)')
        assert 'finally:' in loading
        timeout = source[source.index("'timeout_error'"):source.index("'network_error_retry'")]
        assert timeout.index('route.abort()') < timeout.index('injected.unroute(COMPANY_API)')
        for name, end in (('loading_state', 'timeout_error'), ('timeout_error', 'network_error_retry'),
                          ('network_error_retry', 'session_expiry'), ('session_expiry', 'zoom_200')):
            block = source[source.index(f"'{name}'"):source.index(f"'{end}'")]
            # run3: a shared tab served cached keys, so nothing was intercepted.
            assert 'injected = context.new_page()' in block, name
            assert 'page.' not in block.replace('injected.', '').replace('new_page', ''), name
        assert source.count("c.check(len(held) >= 1") == 2 and 'c.check(len(aborted) >= 1' in source
        assert 'c.check(302 in answers' in source
        skip = source[source.index("'skip_link_and_tab_order'"):source.index("'explicit_range_push_back_refresh'")]
        assert 'tab_page = context.new_page()' in skip and 'document.activeElement.blur()' not in skip

    def test_every_viewport_asserts_the_range_inputs_show_whole_dates(self):
        """FINAL-UI-CHECK F1: page overflow did not catch a date clipped inside
        its input; each viewport case now measures the value against the box."""
        source = (HA1 / 'verify_preview.py').read_text(encoding='utf-8')
        viewport = source[source.index("(f'viewport_{label}', 'no_document_overflow')"):
                          source.index("screenshot(page, f'typical-{label}')")]
        assert 'page.evaluate(DATE_CLIP_JS)' in viewport
        assert "not item['clipped']" in viewport and "len(item['value']) == 10" in viewport
        clip = source[source.index('DATE_CLIP_JS = '):source.index('FOCUS_JS = ')]
        assert 'el.scrollWidth > el.clientWidth' in clip and 'measureText' in clip
        assert 'paddingLeft' in clip and 'paddingRight' in clip

    def test_only_traced_allocation_reads_send_the_widened_statement_limit(self):
        assert harness.TRACED_STATEMENT_LIMIT_S > harness.STATEMENT_LIMIT_S
        source = (HA1 / 'probe_analysis.py').read_text(encoding='utf-8')
        assert source.count('statement_floor_s=harness.TRACED_STATEMENT_LIMIT_S') == 1
        allocation = source[source.index('def reader_allocation'):source.index('def explain')]
        assert 'statement_floor_s=harness.TRACED_STATEMENT_LIMIT_S' in allocation
        assert 'tracemalloc.start' not in source[source.index('def http_latency'):source.index('def reader_allocation')]
        assert "'sent_limit_s': sent" in source and "'timeout_s': timeout_s" in source

    def test_the_board_quiet_window_is_observed_in_progress_segments_not_shortened(self):
        """LOCAL-QA: the 130 s window is waited in <=30 s segments with a
        progress line after each; the segments still add up to the full window."""
        assert harness.quiet_segments(130_000) == [30_000, 30_000, 30_000, 30_000, 10_000]
        assert harness.quiet_segments(60_000, 60_000) == [60_000]
        for total in (1, 29_999, 30_000, 130_000, 250_001):
            segments = harness.quiet_segments(total)
            assert sum(segments) == total and all(0 < s <= harness.PROGRESS_SEGMENT_MS for s in segments)
        with pytest.raises(ValueError):
            harness.quiet_segments(0)
        source = (HA1 / 'verify_preview.py').read_text(encoding='utf-8')
        assert 'page.wait_for_timeout(BOARD_QUIET_MS)' not in source
        assert 'harness.quiet_segments(BOARD_QUIET_MS)' in source and 'BOARD_QUIET_MS = 130_000' in source


# --- contrast (U6) ---------------------------------------------------------------------------

DARK = [{'node': 'div.rh', 'color': 'rgb(17, 35, 49)', 'image': False}]


def sample(selector='.x', value='rgb(255, 255, 255)', layers=None, matched=1, prop='color'):
    return {'selector': selector, 'property': prop, 'matched': matched,
            'pairs': [] if not matched else [{'value': value, 'layers': DARK if layers is None else layers}]}


class TestContrast:
    def test_parse_supported_and_unsupported_colours(self):
        assert harness.parse_color('rgb(255, 255, 255)') == ((255.0, 255.0, 255.0), 1.0)
        assert harness.parse_color('rgba(0, 0, 0, 0)') == ((0.0, 0.0, 0.0), 0.0)
        assert harness.parse_color('rgb(10 20 30 / 50%)') == ((10.0, 20.0, 30.0), 0.5)
        assert harness.parse_color('transparent') == ((0.0, 0.0, 0.0), 0.0)
        for text in ('oklch(70% 0.1 200)', 'color(srgb 1 1 1)', 'none', 'url("#rh-an-hatch")', '', None,
                     'rgb(300, 0, 0)'):
            with pytest.raises(harness.UnsupportedColour):
                harness.parse_color(text)

    def test_ratio_reference_values(self):
        assert harness.contrast_ratio((0, 0, 0), (255, 255, 255)) == pytest.approx(21.0)
        # hub.css --dim on --panel, as REVIEW-1 computed.
        assert harness.contrast_ratio((0x8f, 0xa3, 0xb8), (0x11, 0x23, 0x31)) == pytest.approx(6.19, abs=0.01)

    def test_translucent_backgrounds_are_composited_over_the_real_opaque_ancestor(self):
        layers = [{'node': 'td', 'color': 'rgba(255, 255, 255, 0.5)', 'image': False},
                  {'node': 'div', 'color': 'rgba(0, 0, 0, 0)', 'image': False},
                  {'node': 'main', 'color': 'rgb(0, 0, 0)', 'image': False},
                  {'node': 'html', 'color': 'rgb(255, 0, 0)', 'image': False}]
        assert harness.effective_background(layers) == pytest.approx((127.5, 127.5, 127.5))

    def test_no_opaque_ancestor_or_an_image_is_unverified(self):
        with pytest.raises(harness.UnverifiedBackground):
            harness.effective_background([{'node': 'td', 'color': 'rgba(0, 0, 0, 0)', 'image': False}])
        with pytest.raises(harness.UnverifiedBackground):
            harness.effective_background([{'node': 'td', 'color': 'rgb(0, 0, 0)', 'image': True}])
        with pytest.raises(harness.UnverifiedBackground):
            harness.effective_background([])

    def test_translucent_text_is_composited_before_the_ratio(self):
        opaque, _ = harness.contrast_failures([sample(value='rgb(255, 255, 255)')], minimum=4.5, kind='text')
        faded, _ = harness.contrast_failures([sample(value='rgba(255, 255, 255, 0.2)')], minimum=4.5, kind='text')
        assert opaque == [] and faded and 'below 4.5:1' in faded[0]

    def test_empty_selectors_unparsed_colours_and_nothing_evaluated_fail(self):
        failures, evaluated = harness.contrast_failures([sample(matched=0)], minimum=4.5, kind='text')
        assert 'matched no rendered element' in failures[0] and evaluated == []
        assert any('no contrast pair was evaluated' in f for f in failures)
        failures, _ = harness.contrast_failures([sample(value='oklch(80% 0.1 200)')], minimum=4.5, kind='text')
        assert any('unsupported colour' in f and 'not skipped' in f for f in failures)
        failures, _ = harness.contrast_failures([sample(layers=[])], minimum=4.5, kind='text')
        assert any('unverified' in f for f in failures)
        failures, _ = harness.contrast_failures([sample(value='rgba(255, 255, 255, 0)')], minimum=4.5, kind='text')
        assert any('fully transparent' in f for f in failures)
        assert harness.contrast_failures([], minimum=4.5, kind='text')[0]

    def test_low_contrast_is_attributed_to_its_own_selector(self):
        samples = [sample('.good', 'rgb(255, 255, 255)'), sample('.bad', 'rgb(40, 55, 70)')]
        failures, evaluated = harness.contrast_failures(samples, minimum=4.5, kind='text')
        assert len(failures) == 1 and failures[0].startswith('text .bad color')
        assert [entry['selector'] for entry in evaluated] == ['.good', '.bad']

    def test_graphics_use_three_to_one_and_text_four_and_a_half(self):
        # About 3.5:1 on the dark panel: a pass for a graphic, a fail for text.
        mid = sample('.line', 'rgb(115, 125, 135)', prop='stroke')
        ratio = harness.contrast_ratio((115, 125, 135), (17, 35, 49))
        assert 3.0 < ratio < 4.5
        assert harness.contrast_failures([mid], minimum=harness.GRAPHIC_CONTRAST_MIN, kind='graphics')[0] == []
        assert harness.contrast_failures([mid], minimum=harness.TEXT_CONTRAST_MIN, kind='text')[0]


# --- chart expectations (U9) -----------------------------------------------------------------

class TestChartExpectations:
    def test_adjacent_runs(self):
        assert harness.adjacent_runs([True, True, False, False, True, True, True]) == [[0, 1], [4, 5, 6]]
        assert harness.adjacent_runs([False, True, False]) == [[1]]
        assert harness.adjacent_runs([]) == []

    def test_the_lines_window_has_trading_ends_and_an_interior_break(self):
        weekday = lambda day: day.weekday() < 5  # noqa: E731
        monday = dt.date(2026, 9, 14)
        assert harness.interior_break_window(monday, weekday) == (dt.date(2026, 9, 8), monday)
        friday = dt.date(2026, 9, 11)
        start, end = harness.interior_break_window(friday, weekday)
        assert (start, end) == (dt.date(2026, 9, 4), dt.date(2026, 9, 10))
        flags = [weekday(start + dt.timedelta(days=n)) for n in range(7)]
        assert flags[0] and flags[-1] and not all(flags)
        assert harness.interior_break_window(monday, lambda day: False) is None


# --- the full-access host member gate (U4) -----------------------------------------------------

APP_PY = PERSONAL_APPS / 'app.py'
GATE = '_require_login_on_full_access_host'
HOST = 'mgemmel.viewdns.net'
ADMIN_ID, MEMBER_ID = 1, 7
COMPANY = '/radar/api/analysis/company/1'


def toy_app(*, remove_member_gate=False, add_radar_member=False):
    """app.py's OWN before_request gate and member set, parsed from its source
    and run in a stand-in Flask app. The application is never imported."""
    import flask

    tree = ast.parse(APP_PY.read_text(encoding='utf-8'))
    members = gate = None
    for node in tree.body:
        if isinstance(node, ast.Assign) and any(isinstance(t, ast.Name) and t.id == '_MEMBER_BLUEPRINTS'
                                                for t in node.targets):
            members = set(ast.literal_eval(node.value))
        if isinstance(node, ast.FunctionDef) and node.name == GATE:
            gate = node
    assert members is not None and gate is not None, 'app.py no longer has the member gate'
    gate.decorator_list = []
    if remove_member_gate:
        gate.body = [statement for statement in gate.body
                     if not (isinstance(statement, ast.If) and '_MEMBER_BLUEPRINTS' in ast.unparse(statement.test))]
    if add_radar_member:
        members.add('radar')
    app = flask.Flask('ha1_toy_gate')
    app.secret_key = 'toy-only'
    app.config['TESTING'] = True
    for name, rule, endpoint in (('auth', '/login', 'login'), ('radar', COMPANY, 'read'), ('gym', '/gym/', 'index')):
        blueprint = flask.Blueprint(name, __name__)
        blueprint.add_url_rule(rule, endpoint, lambda: 'ok')
        app.register_blueprint(blueprint)
    namespace = {'request': flask.request, 'redirect': flask.redirect, 'url_for': flask.url_for,
                 'abort': flask.abort, 'FULL_ACCESS_HOST': HOST, '_MEMBER_BLUEPRINTS': members,
                 '_request_hostname': lambda: flask.request.host.split(':')[0].rstrip('.').lower(),
                 '_is_logged_in': lambda: 'user_id' in flask.session,
                 'is_admin': lambda: flask.session.get('user_id') == ADMIN_ID}
    exec(compile(ast.fix_missing_locations(ast.Module(body=[gate], type_ignores=[])), str(APP_PY), 'exec'),
         namespace)
    app.before_request(namespace[GATE])
    return app


class TestFullAccessHostGate:
    def test_the_real_gate_refuses_a_non_admin_with_exactly_403_and_permits_the_rest(self):
        app = toy_app()
        with app.test_client() as client:
            assert client.get(COMPANY, base_url=f'http://{HOST}').status_code == 302
            assert harness.host_session_get(client, HOST, MEMBER_ID, COMPANY).status_code == 403
            assert harness.host_session_get(client, HOST, MEMBER_ID, '/gym/').status_code == 200
            assert harness.host_session_get(client, HOST, ADMIN_ID, COMPANY).status_code == 200
        with app.test_client() as client:
            # G-151: every public host holds a member to the member blueprints.
            assert harness.host_session_get(client, 'pubquizmainz.viewdns.net', MEMBER_ID,
                                            COMPANY).status_code == 403
        with app.test_client() as client:
            assert harness.host_session_get(client, '127.0.0.1', MEMBER_ID, COMPANY).status_code == 200

    def test_a_session_on_the_default_host_never_reaches_the_member_gate(self):
        """Why CORRECTION-1's `in (302, 403)` passed vacuously (REVIEW-2 U4)."""
        with toy_app().test_client() as client:
            with client.session_transaction() as flask_session:
                flask_session['user_id'] = MEMBER_ID
            assert client.get(COMPANY, base_url=f'http://{HOST}').status_code == 302

    @pytest.mark.parametrize('mutation', [{'remove_member_gate': True}, {'add_radar_member': True}])
    def test_removing_the_member_gate_is_detected(self, mutation):
        with toy_app(**mutation).test_client() as client:
            assert harness.host_session_get(client, HOST, MEMBER_ID, COMPANY).status_code == 200  # != 403

    def test_the_api_suite_asserts_exactly_403_on_the_host_session(self):
        source = (PERSONAL_APPS / 'tests' / 'test_radar_analysis_api.py').read_text(encoding='utf-8')
        assert 'harness.host_session_get(test_client, FULL_ACCESS_HOST' in source
        assert 'refused.status_code == 403' in source
        assert "host_session_get(test_client, '127.0.0.1'" in source
        assert 'in (302, 403)' not in source
        assert 'app' not in sys.modules


# --- runtime Git under a foreign owner (U1) ---------------------------------------------------

def _git(*args, **kwargs):
    return subprocess.run(['git', *args], capture_output=True, text=True, **kwargs)


@pytest.fixture()
def foreign_repo(tmp_path, monkeypatch):
    """A real repository, with Git's global and system configuration isolated
    so no pre-existing safe.directory entry can make the test pass."""
    isolated_global = tmp_path / 'isolated-global.gitconfig'
    monkeypatch.setenv('GIT_CONFIG_GLOBAL', str(isolated_global))
    monkeypatch.setenv('GIT_CONFIG_NOSYSTEM', '1')
    monkeypatch.delenv('GIT_TEST_ASSUME_DIFFERENT_OWNER', raising=False)
    repo = tmp_path / 'candidate with space'
    repo.mkdir()
    assert _git('init', '-q', str(repo)).returncode == 0
    assert _git('-C', str(repo), '-c', 'user.name=ha1', '-c', 'user.email=ha1@invalid',
                'commit', '-q', '--allow-empty', '-m', 'ha1').returncode == 0
    head = _git('-C', str(repo), 'rev-parse', 'HEAD').stdout.strip()
    monkeypatch.setenv('GIT_TEST_ASSUME_DIFFERENT_OWNER', '1')
    return repo, head, isolated_global


class TestRuntimeGit:
    def test_a_foreign_owner_refuses_plain_git_and_the_runtime_scopes_trust_per_command(self, foreign_repo):
        repo, head, isolated_global = foreign_repo
        plain = _git('-C', str(repo), 'rev-parse', 'HEAD')
        assert plain.returncode == 128 and 'dubious ownership' in plain.stderr
        assert local_runtime.git('rev-parse', 'HEAD', candidate=repo) == head
        assert local_runtime.git('rev-parse', '--abbrev-ref', 'HEAD', candidate=str(repo))
        assert not isolated_global.exists() or 'safe' not in isolated_global.read_text(encoding='utf-8')
        # Trust was never persisted: plain Git still refuses afterwards.
        assert _git('-C', str(repo), 'rev-parse', 'HEAD').returncode == 128

    def test_a_git_failure_is_a_clear_systemexit(self, tmp_path):
        with pytest.raises(SystemExit, match=r'git rev-parse HEAD failed in .*exit 128'):
            local_runtime.git('rev-parse', 'HEAD', candidate=tmp_path / 'not-a-repository-dir')

    def test_git_that_cannot_start_is_a_clear_systemexit(self, monkeypatch):
        def missing(*args, **kwargs):
            raise FileNotFoundError('git')
        monkeypatch.setattr(local_runtime.subprocess, 'run', missing)
        with pytest.raises(SystemExit, match='could not be started'):
            local_runtime.git('rev-parse', 'HEAD')

    def test_the_command_is_scoped_to_the_resolved_candidate(self, monkeypatch):
        seen = []

        def record(command, **kwargs):
            seen.append(command)
            return subprocess.CompletedProcess(command, 0, stdout='x\n', stderr='')
        monkeypatch.setattr(local_runtime.subprocess, 'run', record)
        local_runtime.git('rev-parse', 'HEAD')
        resolved = Path(local_runtime.CANDIDATE).resolve()
        assert seen == [['git', '-c', f'safe.directory={resolved.as_posix()}', '-C', str(resolved),
                         'rev-parse', 'HEAD']]
        assert not any('--global' in part or '*' in part for part in seen[0])


# --- the pre-app gate ------------------------------------------------------------------------

@pytest.fixture()
def registry(tmp_path):
    path = tmp_path / 'registry.json'
    path.write_text(json.dumps({'version': 1, 'targets': ['127.0.0.1:3407/personal_apps_ha1_test']}))
    return path


class TestGate:
    def env(self, registry, target='127.0.0.1:3407/personal_apps_ha1_test'):
        return {'RADAR_HA1_TARGET': target, 'RADAR_HA1_REGISTRY': str(registry)}

    def test_a_registered_loopback_target_passes(self, registry):
        assert local_runtime.gate(self.env(registry)) == (
            '127.0.0.1', 3407, 'personal_apps_ha1_test', '127.0.0.1:3407/personal_apps_ha1_test',
            str(registry))

    @pytest.mark.parametrize('target, text', [
        ('10.0.0.5:3407/personal_apps_ha1_test', 'loopback'),
        ('127.0.0.1:3306/personal_apps_ha1_test', 'protected server'),
        ('127.0.0.1:3399/personal_apps_ha1_test', 'protected server'),
        ('127.0.0.1:3407/personal_apps', 'protected'),
        ('127.0.0.1:3407/personal_apps_radar_b1c', 'protected'),
        ('127.0.0.1:3407/unregistered', 'not registered'),
        ('127.0.0.1/personal_apps_ha1_test', 'host:port/database'),
    ])
    def test_refusals(self, registry, target, text):
        with pytest.raises(SystemExit, match=text):
            local_runtime.gate(self.env(registry, target))

    def test_missing_or_relative_registry_refuses(self, registry):
        with pytest.raises(SystemExit, match='not authorized'):
            local_runtime.gate({})
        with pytest.raises(SystemExit, match='absolute'):
            local_runtime.gate({'RADAR_HA1_TARGET': '127.0.0.1:3407/personal_apps_ha1_test',
                                'RADAR_HA1_REGISTRY': 'registry.json'})

    def test_test_mode_runs_only_inspected_suites(self):
        assert local_runtime.TEST_SUITES == ('tests/test_radar_analysis_api.py',
                                             'tests/test_radar_board_sort.py')

    def test_importing_the_runtime_does_not_import_the_app(self):
        assert 'app' not in sys.modules

    def test_verify_preview_gates_before_any_network_or_browser(self, monkeypatch, registry, tmp_path):
        import urllib.request

        import verify_preview

        def no_network(*args, **kwargs):
            raise AssertionError('network before the gate')
        monkeypatch.setattr(urllib.request, 'urlopen', no_network)
        with pytest.raises(SystemExit, match='not authorized'):
            verify_preview.preflight(['verify_preview.py', '5041'], env={})
        monkeypatch.setattr(local_runtime, 'runtime_path', lambda port: tmp_path / 'absent.json')
        monkeypatch.setattr(local_runtime, 'git', lambda *args, **kwargs: 'x')
        monkeypatch.setattr(verify_preview, 'MANIFEST', tmp_path / 'absent-manifest.json')
        with pytest.raises(SystemExit) as info:
            verify_preview.preflight(['verify_preview.py', '5041'], env=self.env(registry))
        assert 'no runtime identity record' in str(info.value)
        assert 'nothing was logged into' in str(info.value)
        with pytest.raises(SystemExit, match='another preview'):
            verify_preview.preflight(['verify_preview.py', '5021'], env=self.env(registry))
        assert 'playwright' not in sys.modules
