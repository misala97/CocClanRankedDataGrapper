"""The Analysis endpoints on a real engine (PLAN C01/C02/C11-C14).

GATED. The bound database must pass destructive_target.require (explicit
opt-in AND an independently provisioned registry) BEFORE any SQL runs --
including the conftest admin lookup. Anywhere else the module fails loudly
rather than skipping silently. Run through scratchpad/ha1/local_runtime.py
test, never bare against default settings.

Ownership (REVIEW-1 P1-1, CORRECTION-1): each test generates its own symbols
and username, refuses before any mutation if any already exists, records
every created row's exact key and deletes only those keys in a finally. No
LIKE, no prefix wipe, no adoption of pre-existing rows.

CORRECTION-1 (2026-09-15): NOT executed -- no authorized HA1 target, and DB
execution is held pending review of this harness.

CORRECTION-2 (2026-09-15): U4 full-access-host 403 established on the real
host session plus a separate loopback permission test; U5 sub-second timeout
evidence. Still NOT executed.
"""
import datetime as dt
import secrets
import sys
from pathlib import Path

import pytest
import sqlalchemy as sa
from sqlalchemy import event

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scratchpad' / 'ha1'))

import ha1_harness as harness  # noqa: E402
import radar_disposable  # noqa: E402
from app import app as flask_app  # noqa: E402
from extensions import db  # noqa: E402
from features.radar import analysis as analysis_mod  # noqa: E402
from models import RadarInstrument, TickerUniverse  # noqa: E402

TABLES = ('radar_ticker_universe', 'radar_instruments', 'radar_daily_closes',
          'radar_bucket_sources', 'app_user')
FROM, TO = '2026-09-07', '2026-09-13'
FROM_DATE, TO_DATE = dt.date(2026, 9, 7), dt.date(2026, 9, 13)


@pytest.fixture(scope='module', autouse=True)
def _gate():
    """Refuse before the client fixture's admin lookup can run a SELECT."""
    with flask_app.app_context():
        radar_disposable.require(*TABLES)


class Owned:
    """This test's planned identities and exact-key seeding helpers. Call the
    helpers inside an app context."""

    def __init__(self, fixtures, symbols, usernames, fx):
        self.fixtures, self.symbols, self.usernames, self.fx = fixtures, symbols, usernames, fx

    def company(self, symbol, **kw):
        return self.fx.add_company(self.fixtures, db.session, symbol, **kw)

    def instrument(self, symbol, **kw):
        return self.fx.add_instrument(self.fixtures, db.session, symbol, **kw)

    def close(self, symbol, day, **kw):
        return self.fx.add_close(self.fixtures, db.session, symbol, day, **kw)

    def buckets(self, symbol, day, source='bluesky', **kw):
        return self.fx.add_buckets(self.fixtures, db.session,
                                   self.fx.bucket_rows(symbol, day, source, **kw))

    def user(self, username, password):
        return self.fx.add_user(self.fixtures, db.session, username, password)


@pytest.fixture()
def owned():
    import ha1_fixtures as fx  # imports models; the module gate has passed
    token = harness.run_token()
    symbols = {role: harness.owned_symbol(role, token) for role in ('M', 'O', 'G', 'W', 'E', 'B')}
    usernames = {'plain': harness.owned_username('plain', token)}
    fixtures = harness.OwnedFixtures(fx.SqlFixtureStore(lambda: db.session),
                                     symbols.values(), usernames.values())
    with flask_app.app_context():
        fixtures.__enter__()  # collision refusal BEFORE any mutation
    try:
        yield Owned(fixtures, symbols, usernames, fx)
    finally:
        with flask_app.app_context():
            fixtures.cleanup()


@pytest.fixture()
def seeded(owned):
    """One eligible company with a sparse week: closes on 8 and 10 (9 missing,
    11 an edge), a full Bluesky day on 9 and a partial one on 10."""
    symbol = owned.symbols['M']
    with flask_app.app_context():
        company = owned.company(symbol)
        instrument = owned.instrument(symbol)
        # A DE sibling and a shadow US row must never fill gaps.
        owned.instrument(symbol, market='de', mic='XETR', venue='Xetra', currency='EUR')
        owned.close(symbol, dt.date(2026, 9, 8))
        owned.close(symbol, dt.date(2026, 9, 10), close='11')
        owned.close(symbol, dt.date(2026, 9, 9), close='99', shadow=True)
        owned.close(symbol, dt.date(2026, 9, 9), close='98', market='de', mic='XETR', currency='EUR')
        owned.buckets(symbol, dt.date(2026, 9, 9))
        owned.buckets(symbol, dt.date(2026, 9, 10), count=2, slots=range(40))
        db.session.commit()
    return company, instrument


@pytest.fixture()
def plain_client(owned):
    """An ordinary signed-in account that is NOT an admin, owned by this test."""
    with flask_app.app_context():
        user_id = owned.user(owned.usernames['plain'], secrets.token_urlsafe(18))
        db.session.commit()
    flask_app.config['TESTING'] = True
    with flask_app.test_client() as test_client:
        with test_client.session_transaction() as flask_session:
            flask_session['user_id'] = user_id
        yield test_client


def company_url(company, instrument, start=FROM, end=TO, **extra):
    query = {'instrument_id': instrument, 'from': start, 'to': end, **extra}
    return f'/radar/api/analysis/company/{company}?' + '&'.join(
        f'{k}={v}' for k, v in query.items())


# --- C11 auth -----------------------------------------------------------------

def test_signed_out_reads_redirect_to_login(anon_client, seeded, owned):
    company, instrument = seeded
    assert anon_client.get(f'/radar/api/analysis/resolve?ticker={owned.symbols["M"]}').status_code == 302
    assert anon_client.get(company_url(company, instrument)).status_code == 302


def test_an_ordinary_signed_in_user_reads_analysis_without_admin(plain_client, seeded, owned):
    company, instrument = seeded
    resolved = plain_client.get(f'/radar/api/analysis/resolve?ticker={owned.symbols["M"]}')
    assert resolved.status_code == 200 and resolved.get_json()['company']['id'] == company
    read = plain_client.get(company_url(company, instrument))
    assert read.status_code == 200 and read.get_json()['instrument']['id'] == instrument


def _plain_user(owned):
    with flask_app.app_context():
        user_id = owned.user(owned.usernames['plain'], secrets.token_urlsafe(18))
        db.session.commit()
    return user_id


def test_the_full_access_host_member_gate_refuses_a_non_admin_with_exactly_403(seeded, owned):
    """Not HA1's rule and not changed by it: app.py's full-access host gate
    admits non-admins only to member blueprints, and radar is not one.

    CORRECTION-2 (U4): the session is established ON the full-access host, so
    the request reaches the member gate. A login redirect is NOT evidence of
    member policy -- it is what an unauthenticated request gets -- so the
    signed-out control must be 302 and the signed-in non-admin exactly 403."""
    from auth import FULL_ACCESS_HOST
    company, instrument = seeded
    user_id = _plain_user(owned)
    flask_app.config['TESTING'] = True
    with flask_app.test_client() as test_client:
        signed_out = test_client.get(company_url(company, instrument),
                                     base_url=f'http://{FULL_ACCESS_HOST}')
        assert signed_out.status_code == 302 and '/login' in signed_out.headers.get('Location', '')
        refused = harness.host_session_get(test_client, FULL_ACCESS_HOST, user_id,
                                           company_url(company, instrument))
        assert refused.status_code == 403, (refused.status_code, refused.headers.get('Location'))
        resolve = harness.host_session_get(test_client, FULL_ACCESS_HOST, user_id,
                                           f'/radar/api/analysis/resolve?ticker={owned.symbols["M"]}')
        assert resolve.status_code == 403


def test_a_non_admin_on_loopback_is_permitted(seeded, owned):
    """The Analysis routes themselves are login_required only: the same
    non-admin, with the session on the loopback host, reads them."""
    company, instrument = seeded
    user_id = _plain_user(owned)
    flask_app.config['TESTING'] = True
    with flask_app.test_client() as test_client:
        read = harness.host_session_get(test_client, '127.0.0.1', user_id,
                                        company_url(company, instrument))
        assert read.status_code == 200 and read.get_json()['instrument']['id'] == instrument


# --- C02 resolve --------------------------------------------------------------

def test_resolve_pins_current_company_and_instrument_ids(client, seeded, owned):
    company, instrument = seeded
    response = client.get(f'/radar/api/analysis/resolve?ticker={owned.symbols["M"].lower()}')
    assert response.status_code == 200
    body = response.get_json()
    assert body['company']['id'] == company and body['company']['ticker'] == owned.symbols['M']
    assert body['instrument']['id'] == instrument
    assert body['instrument']['currency'] == 'USD' and body['instrument']['market'] == 'us'


def test_resolve_refuses_unknown_delisted_ambiguous_and_ineligible(client, seeded, owned):
    s = owned.symbols
    assert client.get(f'/radar/api/analysis/resolve?ticker={s["O"]}').status_code == 404
    with flask_app.app_context():
        owned.company(s['G'], delisted_at=dt.datetime(2026, 6, 1))
        owned.company(s['W'])
        owned.instrument(s['W'])
        owned.instrument(s['W'], mic='XNGS', venue='Nasdaq')
        owned.company(s['E'])
        owned.instrument(s['E'], currency='EUR')
        owned.company(s['B'])
        owned.instrument(s['B'], provider='')
        db.session.commit()
    gone = client.get(f'/radar/api/analysis/resolve?ticker={s["G"]}')
    assert gone.status_code == 404 and gone.get_json()['code'] == 'delisted_company'
    two = client.get(f'/radar/api/analysis/resolve?ticker={s["W"]}')
    assert two.status_code == 409 and two.get_json()['code'] == 'ambiguous_primary'
    eur = client.get(f'/radar/api/analysis/resolve?ticker={s["E"]}')
    assert eur.status_code == 422 and eur.get_json()['code'] == 'ineligible_instrument'
    assert client.get(f'/radar/api/analysis/resolve?ticker={s["B"]}').status_code == 422


def test_resolve_validates_its_query(client, seeded, owned):
    symbol = owned.symbols['M']
    assert client.get('/radar/api/analysis/resolve').status_code == 400
    assert client.get(f'/radar/api/analysis/resolve?ticker={symbol}&ticker={symbol}').status_code == 400
    assert client.get(f'/radar/api/analysis/resolve?ticker={symbol}&x=1').status_code == 400
    injected = client.get(f"/radar/api/analysis/resolve?ticker={symbol}'%20OR%201=1")
    assert injected.status_code == 400 and injected.get_json()['code'] == 'invalid_ticker'


# --- C01 range through the transport ---------------------------------------------

@pytest.mark.parametrize('query, code', [
    ({'start': '2026-09-13', 'end': '2026-09-07'}, 'reversed_range'),
    ({'start': '2026-09-06', 'end': '2026-09-13'}, 'range_too_long'),
    ({'start': '2026-02-29', 'end': '2026-03-01'}, 'invalid_date'),
    ({'span': '1D'}, 'unknown_query'),
])
def test_bad_ranges_are_400_with_a_stable_code(client, seeded, query, code):
    company, instrument = seeded
    response = client.get(company_url(company, instrument, **query))
    assert response.status_code == 400
    assert response.get_json()['code'] == code


def test_today_and_the_future_are_refused(client, seeded):
    company, instrument = seeded
    today = dt.datetime.now(dt.timezone.utc).date()
    response = client.get(company_url(company, instrument, start=today.isoformat(),
                                      end=today.isoformat()))
    assert response.status_code == 400
    assert response.get_json()['code'] == 'range_not_completed'


def test_duplicate_and_missing_keys_are_refused(client, seeded):
    company, instrument = seeded
    dup = client.get(company_url(company, instrument) + '&to=2026-09-12')
    assert dup.status_code == 400 and dup.get_json()['code'] == 'duplicate_query'
    missing = client.get(f'/radar/api/analysis/company/{company}?from={FROM}&to={TO}')
    assert missing.status_code == 400 and missing.get_json()['code'] == 'missing_query'
    zero = client.get(company_url(company, 0))
    assert zero.status_code == 400 and zero.get_json()['code'] == 'invalid_id'


# --- C02/C03/C04/C06 the read ---------------------------------------------------

def test_the_read_returns_independent_series_with_gaps_kept(client, seeded):
    company, instrument = seeded
    response = client.get(company_url(company, instrument))
    assert response.status_code == 200
    body = response.get_json()
    assert body['company']['id'] == company and body['instrument']['id'] == instrument
    assert body['identity_scope'] == 'current_mapping_retrospective'
    price = body['price']
    states = {p['date']: p['state'] for p in price['days']}
    assert states['2026-09-08'] == 'observed' and states['2026-09-10'] == 'observed'
    # Shadow and DE rows for the 9th never fill the gap.
    assert states['2026-09-09'] == 'missing'
    assert price['interior_modeled_missing'] == ['2026-09-09']
    assert price['usable_count'] == 2 and price['regime_changed'] is False
    by_day = {c['date']: c for c in body['chatter']['days']}
    assert by_day['2026-09-09']['mentions'] == 96 and by_day['2026-09-09']['coverage'] == 'observed'
    assert by_day['2026-09-10']['mentions'] == 80 and by_day['2026-09-10']['coverage'] == 'partial'
    assert by_day['2026-09-08']['mentions'] is None and by_day['2026-09-08']['coverage'] == 'unavailable'
    assert by_day['2026-09-08']['sources'][0]['coverage'] == 'unavailable'
    assert body['chatter']['first_observed'] == '2026-09-09T00:00:00Z'
    assert len(response.get_data()) < harness.RESPONSE_BYTES


def test_a_stale_bookmark_fails_visibly(client, seeded, owned):
    company, instrument = seeded
    with flask_app.app_context():
        owned.company(owned.symbols['O'])
        other_instrument = owned.instrument(owned.symbols['O'])
        db.session.commit()
    crossed = client.get(company_url(company, other_instrument))
    assert crossed.status_code == 409 and crossed.get_json()['code'] == 'identity_changed'
    assert client.get(company_url(company, 999999999)).status_code == 404
    assert client.get(company_url(999999999, instrument)).status_code == 404
    with flask_app.app_context():
        db.session.get(RadarInstrument, instrument).is_primary = False
        db.session.commit()
    demoted = client.get(company_url(company, instrument))
    assert demoted.status_code == 409 and demoted.get_json()['code'] == 'identity_changed'


def test_a_future_fetched_close_is_not_served(client, seeded, owned):
    company, instrument = seeded
    with flask_app.app_context():
        owned.close(owned.symbols['M'], dt.date(2026, 9, 11), close='12',
                    fetched_at=dt.datetime.now(dt.timezone.utc).replace(tzinfo=None) + dt.timedelta(days=1))
        db.session.commit()
    body = client.get(company_url(company, instrument)).get_json()
    assert {p['date']: p['state'] for p in body['price']['days']}['2026-09-11'] == 'missing'


def test_json_escaping_of_a_hostile_name(client, seeded):
    company, instrument = seeded
    with flask_app.app_context():
        db.session.get(TickerUniverse, company).name = '<script>alert(1)</script>'
        db.session.commit()
    response = client.get(company_url(company, instrument))
    assert response.status_code == 200
    assert response.get_json()['company']['name'] == '<script>alert(1)</script>'
    assert response.mimetype == 'application/json'


# --- C13 bounded reads ---------------------------------------------------------

def test_the_read_uses_at_most_four_data_selects_on_selected_indexes(client, seeded, owned):
    company, instrument = seeded
    statements = []

    def before(conn, cursor, statement, parameters, context, executemany):
        if 'radar_' in statement and '@@' not in statement:
            statements.append(statement)
    with flask_app.app_context():
        engine = db.engine
        event.listen(engine, 'before_cursor_execute', before)
        try:
            assert client.get(company_url(company, instrument)).status_code == 200
        finally:
            event.remove(engine, 'before_cursor_execute', before)
    assert len(statements) <= harness.MAX_DATA_SELECTS and len(statements) == 4, statements
    assert all('radar_posts' not in s and 'radar_mentions' not in s for s in statements)
    assert not any('DATE(' in s.upper().replace(' ', '') for s in statements)
    # EXPLAIN the reader's own named SQL with the binds it sends; never
    # driver-level %s SQL re-wrapped in sa.text.
    with flask_app.app_context():
        read_start = dt.datetime.now(dt.timezone.utc).replace(tzinfo=None)
        problems = []
        for name, sql, params in analysis_mod.data_statements(
                company, instrument, owned.symbols['M'], 'XNYS', FROM_DATE, TO_DATE, read_start):
            plan = [dict(row) for row in db.session.execute(sa.text('EXPLAIN ' + sql), params).mappings().all()]
            problems += harness.plan_failures(name, plan)
        db.session.rollback()
    assert not problems, problems


def test_more_sources_than_supported_is_an_honest_503(client, seeded, owned):
    company, instrument = seeded
    with flask_app.app_context():
        for n in range(harness.MAX_SOURCES + 1):
            owned.buckets(owned.symbols['M'], dt.date(2026, 9, 12), source=f'zq{n}', slots=range(1))
        db.session.commit()
    response = client.get(company_url(company, instrument))
    assert response.status_code == 503
    assert response.get_json()['code'] == 'analysis_limit'


# --- C14 failure ------------------------------------------------------------------

def test_a_store_failure_is_503_through_production_translation(client, seeded, monkeypatch):
    company, instrument = seeded

    def broken(self, ticker, mic, start, end, read_start, *, timeout_s):
        # Raised INSIDE SqlStore._rows, so its DBAPI translation is what runs.
        return self._rows('SELECT * FROM zq_ha1_no_such_table', timeout_s)
    monkeypatch.setattr(analysis_mod.SqlStore, 'daily_closes', broken)
    response = client.get(company_url(company, instrument))
    assert response.status_code == 503
    assert response.get_json()['code'] == 'analysis_unavailable'
    assert 'zq_ha1_no_such_table' not in response.get_data(as_text=True)
    monkeypatch.undo()
    assert client.get(company_url(company, instrument)).status_code == 200


def test_the_statement_timeout_interrupts_and_leaves_one_connection_clean(client, seeded):
    """SLEEP and a CPU-bound SELECT through the production SqlStore under a
    one-second limit, on ONE checked-out connection: an uncancelled statement
    fails, and the connection's id and session max_statement_time must match
    before and after. Anything but MariaDB fails rather than pretending.

    CORRECTION-2 (U5): the same probe also sends a CPU-bound statement under
    the 0.250 s limit ReaderBudget computes, rendered as a fractional
    `SET STATEMENT max_statement_time=0.NNN`, records requested/effective
    limits, elapsed and overshoot, and proves a normal statement succeeds on
    the same connection afterwards (ha1_harness.timeout_failures)."""
    import ha1_fixtures as fx
    company, instrument = seeded
    with flask_app.app_context():
        result = fx.timeout_probe(db.engine, 1.0)
    failures = harness.timeout_failures(result, 1.0)
    assert not failures, (failures, result)
    assert client.get(company_url(company, instrument)).status_code == 200
