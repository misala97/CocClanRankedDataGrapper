# Radar Watching and Search Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Search the whole ticker universe from the radar masthead, and mark stocks as "watching" so they sit in a Watching tier above the board — per account, with real rows even below the eligibility floor.

**Architecture:** One new table (`radar_watch`), two small Flask endpoints (watch toggle, universe search), and a `build_pinned` path through the existing leaderboard that builds rows for named tickers regardless of the floor. The board payload gains `watching` + `watch_rows` per request on top of the shared 60s memo. The React island adds a `Search` combobox, a star column/button, and a Watching tier in `ListPane`.

**Tech Stack:** Flask + SQLAlchemy + Alembic (MySQL dev, MariaDB prod), pytest; React 19 + TypeScript + Vite, vitest + testing-library; playwright (python) for screenshots.

**Spec:** `docs/superpowers/specs/2026-09-02-radar-watching-and-search-design.md` — read it first; the spec wins on any conflict.

## Global Constraints

- Python and TS paths are relative to `personal_apps/` unless they start with `docs/`. Run all `npx`/`pytest` commands from `personal_apps/`.
- Every stored datetime is naive UTC (project convention). `radar_watch.created_at` too.
- Absence is never zero: a pinned ticker with no bucket has `ratio`, `mention_z`, `divergence`, `normal_per_hour` = `null`.
- Ticker shape everywhere: `^[A-Za-z][A-Za-z0-9.-]{0,9}$`, uppercased.
- Search: 8 matches max, `q` capped at 40 chars, ranking exact-symbol → symbol-prefix → name-contains, delisted excluded.
- The board memo (`routes/api.board_cache`) stays viewer-invariant; per-user data is added after the cached build.
- Frontend: no new dependencies. CSS goes in `static/radar/radar.css` using the existing tokens (`--mark`, `--ink`, `--dim`, `--rule`, `--raise`, `--r`, `--r-pill`, `--s*`, `--ease`, `--fast`; there is no popover z token -- the dropdown uses `z-index: 100`, the skip link's layer). Keyframes are FROM-only with `backwards` fill (`motion.test.ts` enforces it).
- Test commands: `python -m pytest tests/<file> -q -p no:cacheprovider` and `npx vitest run -c vite.radar.config.ts <file>`. Typecheck with `npx tsc --noEmit`. Build with `npx vite build -c vite.radar.config.ts` before any browser check.
- Commit after every task; never `git add` `static/radar/dist/` (gitignored). Chain verification with `&&` only — no `grep | head` pipelines, no heredocs mid-chain (they hide failures).
- Work on branch `dev_personal`. Merging to `main` happens at the end (Task 10).

---

### Task 1: `radar_watch` table, migration and `watch.py`

**Files:**
- Modify: `models.py` (append after `RadarLlmSpend`, near the other radar models)
- Create: `migrations/versions/b7e1c4d9a2f3_add_radar_watch.py`
- Create: `features/radar/watch.py`
- Test: `tests/test_radar_watch.py`

**Interfaces:**
- Produces: `models.RadarWatch` (columns `id`, `user_id`, `ticker`, `created_at`); `watch.normalise(ticker) -> str` (raises `watch.BadTicker`); `watch.tickers_for(user_id) -> list[str]` (by `created_at`, then id); `watch.add(user_id, ticker, now=None) -> list[str]`; `watch.remove(user_id, ticker) -> list[str]`.

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_radar_watch.py
"""What one account is watching: per account, idempotent, shape-checked."""
import datetime as dt

import pytest

from app import app as flask_app
from extensions import db
from models import AppUser, RadarWatch
from features.radar import watch


@pytest.fixture()
def two_users():
    """Two throwaway accounts. Rows they write are deleted with them (FK
    cascade), so the fixture only has to delete the users."""
    with flask_app.app_context():
        for name in ('pytest watcher a', 'pytest watcher b'):
            AppUser.query.filter_by(username=name).delete()
        db.session.commit()
        a = AppUser(username='pytest watcher a', password_hash='x')
        b = AppUser(username='pytest watcher b', password_hash='x')
        db.session.add_all([a, b])
        db.session.commit()
        yield a.id, b.id
        for name in ('pytest watcher a', 'pytest watcher b'):
            AppUser.query.filter_by(username=name).delete()
        db.session.commit()


def test_marks_are_per_account(two_users):
    a, b = two_users
    with flask_app.app_context():
        watch.add(a, 'nvda')
        watch.add(b, 'TSLA')

        assert watch.tickers_for(a) == ['NVDA']
        assert watch.tickers_for(b) == ['TSLA']


def test_add_is_idempotent_and_keeps_first_seen_order(two_users):
    a, _ = two_users
    with flask_app.app_context():
        watch.add(a, 'TSLA', now=dt.datetime(2026, 9, 2, 10, 0))
        watch.add(a, 'NVDA', now=dt.datetime(2026, 9, 2, 10, 1))
        watch.add(a, 'TSLA', now=dt.datetime(2026, 9, 2, 10, 2))

        assert watch.tickers_for(a) == ['TSLA', 'NVDA']
        assert RadarWatch.query.filter_by(user_id=a).count() == 2


def test_remove_of_an_unwatched_ticker_is_not_an_error(two_users):
    a, _ = two_users
    with flask_app.app_context():
        watch.add(a, 'NVDA')

        assert watch.remove(a, 'TSLA') == ['NVDA']
        assert watch.remove(a, 'NVDA') == []


def test_a_malformed_ticker_is_refused(two_users):
    a, _ = two_users
    with flask_app.app_context():
        for bad in ('', '1ABC', 'TOO-LONG-TICKER', 'a b', 'NV;DA'):
            with pytest.raises(watch.BadTicker):
                watch.add(a, bad)
        assert watch.tickers_for(a) == []


def test_deleting_the_account_deletes_its_marks(two_users):
    a, _ = two_users
    with flask_app.app_context():
        watch.add(a, 'NVDA')
        AppUser.query.filter_by(id=a).delete()
        db.session.commit()

        assert RadarWatch.query.filter_by(user_id=a).count() == 0
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `python -m pytest tests/test_radar_watch.py -q -p no:cacheprovider`
Expected: FAIL — `ImportError: cannot import name 'RadarWatch' from 'models'`.

- [ ] **Step 3: Add the model**

Append to `models.py` (after the `RadarLlmSpend` class; `dt`, `sa`, `db` are already imported at the top of the file):

```python
class RadarWatch(db.Model):
    """A ticker one account is watching.

    The first per-account fact in radar. Every other radar row is shared --
    mention data is not personal -- but a mark is the reader's own, and the
    gym feature already scopes by `app_user.id` the same way. One row per
    (account, ticker); the surface orders by `created_at`, the order the
    reader made the marks in.
    """
    __tablename__ = 'radar_watch'
    __table_args__ = (
        db.UniqueConstraint('user_id', 'ticker', name='uq_radar_watch_user_ticker'),
        {'mysql_charset': 'utf8mb4'},
    )

    id         = db.Column(db.BigInteger, primary_key=True, autoincrement=True)
    user_id    = db.Column(db.Integer,
                           db.ForeignKey('app_user.id', ondelete='CASCADE'),
                           nullable=False, index=True)
    # The radar ticker identity, market-independent, same collation as
    # radar_ticker_universe.symbol so 'IT' and 'it' cannot both exist.
    ticker     = db.Column(db.String(12, collation='utf8mb4_bin'), nullable=False)
    created_at = db.Column(db.DateTime, nullable=False, default=dt.datetime.utcnow)
```

- [ ] **Step 4: Write the migration**

```python
# migrations/versions/b7e1c4d9a2f3_add_radar_watch.py
"""add radar_watch

One row per (account, ticker) the account is watching. Plain DDL: nothing
here that MariaDB parses differently from MySQL.

Revision ID: b7e1c4d9a2f3
Revises: 6a21d4e8c9f0
Create Date: 2026-09-02
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import mysql


revision = 'b7e1c4d9a2f3'
down_revision = '6a21d4e8c9f0'
branch_labels = None
depends_on = None


def upgrade():
    is_sqlite = op.get_bind().dialect.name == 'sqlite'
    op.create_table(
        'radar_watch',
        sa.Column('id', sa.Integer() if is_sqlite else mysql.BIGINT(),
                  primary_key=True, autoincrement=True),
        sa.Column('user_id', sa.Integer(),
                  sa.ForeignKey('app_user.id', ondelete='CASCADE'),
                  nullable=False),
        sa.Column('ticker',
                  sa.String(length=12,
                            collation=None if is_sqlite else 'utf8mb4_bin'),
                  nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.UniqueConstraint('user_id', 'ticker', name='uq_radar_watch_user_ticker'),
        **({} if is_sqlite else {'mysql_charset': 'utf8mb4'}),
    )
    op.create_index('ix_radar_watch_user_id', 'radar_watch', ['user_id'])


def downgrade():
    op.drop_index('ix_radar_watch_user_id', table_name='radar_watch')
    op.drop_table('radar_watch')
```

Apply it locally: `flask db upgrade` (from `personal_apps/`). Expected output ends with `Running upgrade 6a21d4e8c9f0 -> b7e1c4d9a2f3, add radar_watch`.

- [ ] **Step 5: Write `watch.py`**

```python
# features/radar/watch.py
"""What one account is watching.

The reader's own marks -- never a signal from the tool. Per account, because
a star that lands on someone else's board is noise; idempotent, because a
double-tap must not be an error; shape-checked, because the ticker goes
straight into IN (...) clauses and URLs.
"""
import datetime as dt
import re

import sqlalchemy as sa

from extensions import db
from models import RadarWatch

# Letters, then a class suffix on some listings (BRK.B, RDS-A), never long.
# The same shape the island applies to `?t=`.
TICKER_SHAPE = re.compile(r'^[A-Za-z][A-Za-z0-9.-]{0,9}$')


class BadTicker(ValueError):
    """A ticker that is not shaped like one."""


def normalise(ticker):
    """The ticker uppercased, or BadTicker."""
    if not ticker or not TICKER_SHAPE.match(ticker):
        raise BadTicker(ticker)
    return ticker.upper()


def tickers_for(user_id):
    """The account's marks, oldest first -- the order they were made in."""
    rows = (db.session.query(RadarWatch.ticker)
            .filter(RadarWatch.user_id == user_id)
            .order_by(RadarWatch.created_at, RadarWatch.id).all())
    return [ticker for (ticker,) in rows]


def add(user_id, ticker, now=None):
    """Mark a ticker. Returns the account's full list."""
    ticker = normalise(ticker)
    exists = RadarWatch.query.filter_by(user_id=user_id, ticker=ticker).one_or_none()
    if exists is None:
        db.session.add(RadarWatch(user_id=user_id, ticker=ticker,
                                  created_at=now or dt.datetime.utcnow()))
        try:
            db.session.commit()
        except sa.exc.IntegrityError:
            # Two taps racing past the SELECT above: the row exists, which
            # is what was asked for.
            db.session.rollback()
    return tickers_for(user_id)


def remove(user_id, ticker):
    """Unmark a ticker. Returns the account's full list; removing a ticker
    that was not marked is not an error."""
    ticker = normalise(ticker)
    RadarWatch.query.filter_by(user_id=user_id, ticker=ticker).delete()
    db.session.commit()
    return tickers_for(user_id)
```

- [ ] **Step 6: Run the tests to verify they pass**

Run: `python -m pytest tests/test_radar_watch.py -q -p no:cacheprovider`
Expected: `5 passed`.

- [ ] **Step 7: Commit**

```bash
git add models.py migrations/versions/b7e1c4d9a2f3_add_radar_watch.py features/radar/watch.py tests/test_radar_watch.py
git commit -m "feat(radar): radar_watch table and watch module

One row per (account, ticker); per account like the gym's rows, idempotent,
ticker shape-checked. Plain DDL for MariaDB."
```

---

### Task 2: Watch endpoints and the CSRF gate

**Files:**
- Modify: `features/radar/routes/_blueprint.py` (append the gate)
- Modify: `features/radar/routes/api.py` (imports + two routes, after `board()`)
- Modify: `templates/radar/board.html` (meta tag in `<head>`)
- Modify: `static/radar/dev.html` (comment only — the harness has no session token; watch toggles 403 there and that is documented)
- Test: `tests/test_radar_watch_api.py`

**Interfaces:**
- Consumes: `watch.add/remove/BadTicker` (Task 1); `auth.current_user()`, `auth.login_required`, `auth._valid_csrf`.
- Produces: `PUT /radar/api/watch/<ticker>` and `DELETE /radar/api/watch/<ticker>` → `{"watching": [...]}`; 400 `{"error": "bad ticker"}`; 403 without `X-CSRF-Token` when `CSRF_STRICT`.

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_radar_watch_api.py
"""The watch endpoints: per account, idempotent, and behind the CSRF gate."""
import pytest

from app import app as flask_app
from extensions import db
from models import AppUser, RadarWatch
from conftest import _admin_id


@pytest.fixture()
def clean_marks():
    with flask_app.app_context():
        RadarWatch.query.filter_by(user_id=_admin_id()).delete()
        db.session.commit()
        yield
        RadarWatch.query.filter_by(user_id=_admin_id()).delete()
        db.session.commit()


def test_put_and_delete_return_the_callers_list(client, clean_marks):
    assert client.put('/radar/api/watch/nvda').get_json() == {'watching': ['NVDA']}
    assert client.put('/radar/api/watch/TSLA').get_json() == {'watching': ['NVDA', 'TSLA']}
    assert client.put('/radar/api/watch/NVDA').get_json() == {'watching': ['NVDA', 'TSLA']}
    assert client.delete('/radar/api/watch/NVDA').get_json() == {'watching': ['TSLA']}
    assert client.delete('/radar/api/watch/NVDA').status_code == 200


def test_a_malformed_ticker_is_400(client, clean_marks):
    response = client.put('/radar/api/watch/1abc')
    assert response.status_code == 400
    assert response.get_json() == {'error': 'bad ticker'}


def test_the_marks_need_a_session(anon_client):
    assert anon_client.put('/radar/api/watch/NVDA').status_code in (302, 401, 403)


def test_writes_need_the_csrf_token_when_the_gate_is_closed(client, clean_marks, monkeypatch):
    """Suites run with the gate open (Flask-WTF's convention); this test
    closes it, the way test_gym_csrf.py does for the gym blueprint."""
    monkeypatch.setitem(flask_app.config, 'CSRF_STRICT', True)

    assert client.put('/radar/api/watch/NVDA').status_code == 403

    with client.session_transaction() as flask_session:
        flask_session['csrf_token'] = 'pytest-token'
    ok = client.put('/radar/api/watch/NVDA', headers={'X-CSRF-Token': 'pytest-token'})
    assert ok.status_code == 200
    assert ok.get_json() == {'watching': ['NVDA']}
    # Reads stay open.
    assert client.get('/radar/api/board?market=us').status_code == 200
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `python -m pytest tests/test_radar_watch_api.py -q -p no:cacheprovider`
Expected: FAIL — `assert 405 == 200` / `AttributeError` (no route yet).

- [ ] **Step 3: Add the CSRF gate to the radar blueprint**

Append to `features/radar/routes/_blueprint.py` (keep whatever it already defines; add the imports it lacks):

```python
from flask import abort, current_app, request


@radar_bp.before_request
def _require_csrf_on_writes():
    """Second defence layer on every radar write, behind SameSite=Lax --
    the gym blueprint's rule, copied rather than shared, because the two
    features share nothing on purpose.

    The token is auth.py's per-session one: board.html delivers it as
    <meta name="csrf-token">, the island sends it as X-CSRF-Token. Suites
    run with the gate open unless CSRF_STRICT is set, so tests do not each
    mint and thread a token; test_radar_watch_api.py pins the closed gate.
    """
    if request.method in ('GET', 'HEAD', 'OPTIONS'):
        return
    if current_app.config.get('TESTING') and not current_app.config.get('CSRF_STRICT'):
        return
    from auth import _valid_csrf
    submitted = request.headers.get('X-CSRF-Token') or request.form.get('csrf_token')
    if not _valid_csrf(submitted):
        abort(403)
```

- [ ] **Step 4: Add the routes**

In `features/radar/routes/api.py`, extend the imports:

```python
from auth import current_user, login_required
from .. import watch
```

and append after the `board()` route:

```python
@radar_bp.route('/api/watch/<ticker>', methods=['PUT'])
@login_required
def watch_put(ticker):
    """Mark a ticker for the caller. Idempotent; answers the whole list so
    the client never merges."""
    try:
        return jsonify({'watching': watch.add(current_user().id, ticker)})
    except watch.BadTicker:
        return jsonify({'error': 'bad ticker'}), 400


@radar_bp.route('/api/watch/<ticker>', methods=['DELETE'])
@login_required
def watch_delete(ticker):
    """Unmark a ticker for the caller. Unmarking the unmarked is a 200."""
    try:
        return jsonify({'watching': watch.remove(current_user().id, ticker)})
    except watch.BadTicker:
        return jsonify({'error': 'bad ticker'}), 400
```

- [ ] **Step 5: Deliver the token to the page**

In `templates/radar/board.html`, inside `<head>` after the `<title>`:

```html
  {# The per-session CSRF token the island sends as X-CSRF-Token on every
     write (the watch endpoints). auth.py mints it; the radar blueprint's
     before_request checks it. #}
  <meta name="csrf-token" content="{{ csrf_token() }}">
```

In `static/radar/dev.html`, extend the top comment with one line:

```
  No csrf-token meta here: the harness has no Jinja. Reads work; the watch
  toggles answer 403 under the harness and that is expected.
```

- [ ] **Step 6: Run the tests to verify they pass**

Run: `python -m pytest tests/test_radar_watch_api.py tests/test_radar_api.py -q -p no:cacheprovider`
Expected: all pass (`4 passed` in the new file; `test_radar_api.py` unchanged).

- [ ] **Step 7: Commit**

```bash
git add features/radar/routes/_blueprint.py features/radar/routes/api.py templates/radar/board.html static/radar/dev.html tests/test_radar_watch_api.py
git commit -m "feat(radar): watch endpoints behind a CSRF gate

PUT/DELETE /radar/api/watch/<ticker>, idempotent, answering the caller's
whole list. The radar blueprint gets the gym's before_request CSRF rule
for writes; board.html delivers the token."
```

---

### Task 3: Universe search

**Files:**
- Create: `features/radar/search.py`
- Modify: `features/radar/routes/api.py` (import + route after the watch routes)
- Test: `tests/test_radar_search.py`

**Interfaces:**
- Consumes: `models.TickerUniverse` (`symbol`, `name`, `exchange`, `market_cap`, `ipo_date`, `is_etf`, `delisted_at`); `universe.segment_for(market_cap, ipo_date, last_price, today, name=None, is_etf=None)`; `watch.tickers_for`.
- Produces: `search.Match` dataclass (`ticker`, `name`, `exchange`, `segment`); `search.search_universe(q, today, limit=8) -> list[Match]`; `GET /radar/api/search?q=` → `{"matches": [{ticker, name, exchange, segment, watching}]}`.

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_radar_search.py
"""Search over the whole universe: symbol first, then names, eight at most."""
import datetime as dt
import decimal

import pytest

from app import app as flask_app
from extensions import db
from models import RadarWatch, TickerUniverse
from features.radar import search
from conftest import _admin_id

TODAY = dt.date(2026, 9, 2)
# ZQ-prefixed so no real universe row can collide.
SEEDED = [
    ('ZQA',   'Zqa Widgets Inc',        'Q', '50000000000', None),
    ('ZQAB',  'Zqab Holdings',          'N', '900000000', None),
    ('ZQC',   'Other Name Corp',        'S', '4000000', None),
    ('ZQGONE','Zqa Delisted Co',        'Q', '1000000', dt.datetime(2026, 1, 1)),
    ('ZQZ',   'Something With zqa in',  'P', None, None),
]


@pytest.fixture()
def seeded():
    with flask_app.app_context():
        TickerUniverse.query.filter(TickerUniverse.symbol.like('ZQ%')).delete(
            synchronize_session=False)
        RadarWatch.query.filter(RadarWatch.ticker.like('ZQ%')).delete(
            synchronize_session=False)
        for symbol, name, exchange, cap, delisted in SEEDED:
            db.session.add(TickerUniverse(
                symbol=symbol, name=name, exchange=exchange,
                first_seen=dt.datetime(2026, 1, 1), delisted_at=delisted,
                market_cap=decimal.Decimal(cap) if cap else None))
        db.session.commit()
        yield
        TickerUniverse.query.filter(TickerUniverse.symbol.like('ZQ%')).delete(
            synchronize_session=False)
        RadarWatch.query.filter(RadarWatch.ticker.like('ZQ%')).delete(
            synchronize_session=False)
        db.session.commit()


def test_symbol_exact_then_prefix_then_name(seeded):
    with flask_app.app_context():
        found = [m.ticker for m in search.search_universe('zqa', TODAY)]
    # ZQA exact, ZQAB prefix, then the two whose NAME contains "zqa";
    # ZQGONE is delisted and never appears.
    assert found == ['ZQA', 'ZQAB', 'ZQZ']


def test_name_search_is_case_insensitive_and_carries_identity(seeded):
    with flask_app.app_context():
        [match] = search.search_universe('OTHER NAME', TODAY)
    assert match.ticker == 'ZQC'
    assert match.name == 'Other Name Corp'
    assert match.exchange == 'S'
    assert match.segment == 'micro'


def test_a_missing_cap_is_the_unknown_segment(seeded):
    with flask_app.app_context():
        [match] = search.search_universe('ZQZ', TODAY)
    assert match.segment == 'unknown'


def test_empty_and_overlong_queries(seeded):
    with flask_app.app_context():
        assert search.search_universe('', TODAY) == []
        assert search.search_universe('   ', TODAY) == []
        # Capped at 40 characters, so a pasted paragraph is a cheap query.
        assert search.search_universe('z' * 200, TODAY) == search.search_universe('z' * 40, TODAY)


def test_at_most_eight(seeded):
    with flask_app.app_context():
        assert len(search.search_universe('a', TODAY)) <= 8


def test_the_endpoint_marks_what_the_caller_watches(client, seeded):
    with flask_app.app_context():
        db.session.add(RadarWatch(user_id=_admin_id(), ticker='ZQAB',
                                  created_at=dt.datetime(2026, 9, 2)))
        db.session.commit()

    payload = client.get('/radar/api/search?q=zqa').get_json()

    by_ticker = {m['ticker']: m for m in payload['matches']}
    assert by_ticker['ZQAB']['watching'] is True
    assert by_ticker['ZQA']['watching'] is False
    assert set(by_ticker['ZQA']) == {'ticker', 'name', 'exchange', 'segment', 'watching'}


def test_the_endpoint_needs_a_session(anon_client):
    assert anon_client.get('/radar/api/search?q=zqa').status_code in (302, 401, 403)
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `python -m pytest tests/test_radar_search.py -q -p no:cacheprovider`
Expected: FAIL — `ImportError: cannot import name 'search'`.

- [ ] **Step 3: Write `search.py`**

```python
# features/radar/search.py
"""Find a stock by symbol or name, anywhere in the universe.

Identity only. Whether a match is on today's board, and its score, the
island knows from the rows it already holds; building a board to say so
here would cost more than the whole search.
"""
import dataclasses

import sqlalchemy as sa

from models import TickerUniverse

from . import universe

LIMIT = 8
MAX_QUERY = 40


@dataclasses.dataclass
class Match:
    ticker: str
    name: str | None
    exchange: str | None
    segment: str


def search_universe(q, today, limit=LIMIT):
    """Matches for `q`: exact symbol, then symbols starting with it, then
    names containing it -- each group alphabetical, `limit` in all.

    Symbols are utf8mb4_bin, so the symbol side compares the uppercased
    query; names compare case-insensitively. Delisted symbols never match:
    a symbol reassigned to another company is a different stock.
    """
    q = (q or '').strip()[:MAX_QUERY]
    if not q:
        return []
    upper = q.upper()
    contains = f'%{q}%'
    rank = sa.case(
        (TickerUniverse.symbol == upper, 0),
        (TickerUniverse.symbol.like(f'{upper}%'), 1),
        else_=2)
    rows = (TickerUniverse.query
            .filter(TickerUniverse.delisted_at.is_(None))
            .filter(sa.or_(TickerUniverse.symbol.like(f'{upper}%'),
                           TickerUniverse.name.ilike(contains)))
            .order_by(rank, TickerUniverse.symbol)
            .limit(limit).all())
    return [Match(
        ticker=row.symbol,
        name=row.name,
        exchange=row.exchange,
        # No price at hand, and none needed: the segment is a size, and
        # the penny-price override only matters on a board row.
        segment=universe.segment_for(row.market_cap, row.ipo_date, None,
                                     today, row.name, row.is_etf),
    ) for row in rows]
```

- [ ] **Step 4: Add the route**

In `features/radar/routes/api.py`, extend the imports:

```python
from .. import search as search_mod
```

and append after `watch_delete`:

```python
@radar_bp.route('/api/search')
@login_required
def search():
    """Symbol-or-name search over the universe, eight matches at most."""
    now = dt.datetime.now(dt.timezone.utc).replace(tzinfo=None)
    watching = set(watch.tickers_for(current_user().id))
    return jsonify({'matches': [
        {'ticker': m.ticker, 'name': m.name, 'exchange': m.exchange,
         'segment': m.segment, 'watching': m.ticker in watching}
        for m in search_mod.search_universe(request.args.get('q', ''), now.date())
    ]})
```

- [ ] **Step 5: Run the tests to verify they pass**

Run: `python -m pytest tests/test_radar_search.py -q -p no:cacheprovider`
Expected: `7 passed`.

- [ ] **Step 6: Commit**

```bash
git add features/radar/search.py features/radar/routes/api.py tests/test_radar_search.py
git commit -m "feat(radar): search the universe by symbol or name

GET /radar/api/search?q= -- exact symbol, symbol prefix, then name
contains; eight matches; identity only, the client annotates the rest."
```

---

### Task 4: `build_pinned` — rows for named tickers regardless of the floor

**Files:**
- Modify: `features/radar/leaderboard.py` (add fields to `Row`; extract `_fold`, `_aggregate`, `_assemble`; add `build_pinned`)
- Modify: `features/radar/phrasing.py` (floor clause; `row_clauses` gains `window_hours`)
- Modify: `features/radar/board.py` (extract `_entries`; add `build_pinned_rows`)
- Test: `tests/test_radar_leaderboard.py` (append), `tests/test_radar_phrasing.py` (append)

**Interfaces:**
- Consumes: everything already in `leaderboard.py` (`_chatter_survivors`, `_universe_rows`, `_quote_sigmas`, `quotes_mod.quote_views_for/moves_for/scale_sigma`, `scoring.is_eligible`, `_rejection`, `journal.distinct_voice_counts`).
- Produces: `leaderboard.Row.eligible: bool` (default `True`) and `Row.floor_reason: str | None` (default `None`; one of `no_mentions`, `too_few_mentions`, `too_few_voices`, `repeated_text`); `leaderboard.build_pinned(tickers, sources, now, window_hours=4, market='us') -> list[Row]`; `phrasing.row_clauses(row, session, window_hours=4)`; `board.build_pinned_rows(tickers, sources, now, window_hours=4, market='us') -> list[BoardRow]`.

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_radar_leaderboard.py` (its helpers `universe_row`, `scored`, `quoted`, `NOW`, `board` fixture and the `LB` prefix cleanup already exist there):

```python
def test_a_pinned_ticker_below_the_floor_still_gets_a_row(board):
    """Watching is the reader's mark; the floor decides ranking, not
    existence. A watched stock with two mentions gets a row that says so."""
    universe_row('LBPIN')
    scored('LBPIN', mentions=2, authors=1)
    quoted('LBPIN', '10.00', '9.80')
    db.session.commit()

    [row] = leaderboard.build_pinned(['LBPIN'], ['bluesky'], NOW)

    assert row.ticker == 'LBPIN'
    assert row.eligible is False
    assert row.floor_reason == 'too_few_mentions'
    assert row.mentions == 2
    assert row.price == decimal.Decimal('10.00')


def test_a_pinned_ticker_above_the_floor_gets_the_row_it_would_have_had(board):
    universe_row('LBPON')
    scored('LBPON')
    quoted('LBPON', '100.00', '100.00')
    db.session.commit()

    [ranked] = build_rows(['bluesky'], NOW)
    [pinned] = leaderboard.build_pinned(['LBPON'], ['bluesky'], NOW)

    assert pinned.eligible is True
    assert pinned.floor_reason is None
    assert (pinned.mentions, pinned.mention_z, pinned.divergence, pinned.marks) == \
        (ranked.mentions, ranked.mention_z, ranked.divergence, ranked.marks)


def test_a_pinned_ticker_with_no_bucket_is_absent_not_zero(board):
    """No bucket in the window: nothing measured. Every derived figure is
    None -- never 0 -- and the reason names the silence."""
    universe_row('LBNIL')
    quoted('LBNIL', '5.00', '5.00')
    db.session.commit()

    [row] = leaderboard.build_pinned(['LBNIL'], ['bluesky'], NOW)

    assert row.eligible is False
    assert row.floor_reason == 'no_mentions'
    assert row.mentions == 0
    assert row.mention_z is None
    assert row.divergence is None
    assert row.baseline_days is None
    assert row.sources == []


def test_pinned_rows_keep_the_order_asked_and_drop_duplicates(board):
    for ticker in ('LBP1', 'LBP2'):
        universe_row(ticker)
        quoted(ticker, '1.00', '1.00')
    db.session.commit()

    rows = leaderboard.build_pinned(['LBP2', 'LBP1', 'LBP2'], ['bluesky'], NOW)

    assert [r.ticker for r in rows] == ['LBP2', 'LBP1']
    assert leaderboard.build_pinned([], ['bluesky'], NOW) == []
```

Append to `tests/test_radar_phrasing.py` (it already imports `phrasing` and has a row-building helper; if its helper is named differently, use `leaderboard.Row(...)` directly as below):

```python
def test_a_row_under_the_floor_says_why_instead_of_a_ratio():
    from features.radar import leaderboard
    from features.radar.phrasing import row_clauses

    def quiet(reason, mentions=0, authors=0):
        return leaderboard.Row(
            ticker='LBQ', name='Q', segment='micro', divergence=None,
            mention_z=None, mentions=mentions, expected=0.0, authors=authors,
            text_ratio=1.0, sources=[], venues=0, price=None, price_move=None,
            direction='flat', price_status='unknown', quote=None,
            baseline_days=None, marks=[], eligible=False, floor_reason=reason)

    texts = {reason: [c.text for c in row_clauses(quiet(reason, mentions, authors), 'closed', 4)]
             for reason, mentions, authors in (
                 ('no_mentions', 0, 0), ('too_few_mentions', 2, 1),
                 ('too_few_mentions', 1, 1), ('too_few_voices', 6, 1),
                 ('too_few_voices', 6, 2), ('repeated_text', 9, 4))}

    assert texts['no_mentions'] == ['no mentions in 4h']
    assert 'one voice only, under the floor' in texts['too_few_voices'] or \
           '2 voices, under the floor' in texts['too_few_voices']
    assert texts['repeated_text'] == ['repeated text, under the floor']
    kinds = [c.kind for c in row_clauses(quiet('too_few_mentions', 2, 1), 'closed', 4)]
    assert kinds == ['warn']
```

(`_price_clauses` adds nothing with `price_status='unknown'` and `price_move=None`, so the clause list is exactly the warn clause.)

- [ ] **Step 2: Run the tests to verify they fail**

Run: `python -m pytest tests/test_radar_leaderboard.py tests/test_radar_phrasing.py -q -p no:cacheprovider -k "pinned or under_the_floor"`
Expected: FAIL — `AttributeError: module 'features.radar.leaderboard' has no attribute 'build_pinned'` / `TypeError: Row.__init__() got an unexpected keyword argument 'eligible'`.

- [ ] **Step 3: Extend `Row` and extract the shared pieces in `leaderboard.py`**

Add two defaulted fields at the end of the `Row` dataclass (after `marks: list`):

```python
    # Whether this row cleared the eligibility floor. Always True on a
    # ranked board -- the floor is applied before a Row exists -- and
    # False on a pinned (watched) row that would not have been listed.
    eligible: bool = True
    # Which gate it failed, when it did: one of _GATE_ORDER or
    # 'no_mentions' (no bucket in the window at all). phrasing.py turns
    # it into words.
    floor_reason: str | None = None
```

Replace the aggregate query inside `_chatter_survivors` with a call to a new helper, and replace the fold in its loop. The new helpers (add above `_chatter_survivors`):

```python
def _aggregate(scored_sources, since, now, tickers=None):
    """One aggregated row per (ticker, source) over the window.

    Aggregated in SQL rather than in Python -- see _chatter_survivors for the
    measurement that decided it. `tickers` narrows the scan to named ones
    (the pinned path); None means every ticker with a scored bucket.
    """
    bucket = RadarBucketSource
    query = (db.session.query(
        bucket.ticker.label('ticker'),
        bucket.source.label('source'),
        sa.func.sum(bucket.mention_count).label('mentions'),
        sa.func.sum(sa.func.coalesce(bucket.expected, 0.0)).label('expected'),
        sa.func.sum(sa.func.coalesce(bucket.variance, 0.0)).label('variance'),
        sa.func.max(bucket.distinct_authors).label('authors'),
        sa.func.min(bucket.distinct_text_ratio).label('text_ratio'),
        sa.func.min(bucket.baseline_days).label('baseline_days'),
        sa.func.max(sa.case((bucket.status == 'truncated', 1), else_=0))
        .label('truncated'))
        .filter(bucket.source.in_(scored_sources),
                bucket.bucket_start >= since,
                bucket.bucket_start < now,
                bucket.mention_z.isnot(None)))
    if tickers is not None:
        query = query.filter(bucket.ticker.in_(list(tickers)))
    grouped = collections.defaultdict(list)
    for row in query.group_by(bucket.ticker, bucket.source).all():
        grouped[row.ticker].append(row)
    return grouped


def _fold(parts, authors, channels):
    """One ticker's per-source rows folded into the figures the floor and the
    row use. `authors` is the journal's true count or None (then the bucket
    maximum, which undercounts in the safe direction)."""
    mentions = int(sum(part.mentions for part in parts))
    expected = float(sum(part.expected for part in parts))
    variance = float(sum(part.variance for part in parts))
    authors = authors if authors is not None else int(max(part.authors for part in parts))
    text_ratio = float(min(part.text_ratio for part in parts))
    by_kind = collections.defaultdict(lambda: [0, 1.0])
    for part in parts:
        totals = by_kind[source_kind(part.source)]
        totals[0] += int(part.mentions)
        totals[1] = min(totals[1], float(part.text_ratio))
    contributions = {
        kind: scoring.Contribution(
            mentions=totals[0],
            voices=(channels if kind == 'broadcast' else authors),
            text_ratio=totals[1])
        for kind, totals in by_kind.items()
    }
    return mentions, expected, variance, authors, text_ratio, contributions
```

In `_chatter_survivors`, the block from `bucket = RadarBucketSource` through `grouped[row.ticker].append(row)` becomes:

```python
    grouped = _aggregate(scored_sources, since, now)
```

and the loop body from `mentions = int(sum(...))` through the `contributions = {...}` dict becomes:

```python
        mentions, expected, variance, authors, text_ratio, contributions = _fold(
            parts, author_counts.get(ticker), channel_counts.get(ticker, 0))
```

(the `if not scoring.is_eligible(contributions): ... continue` and `survivors[ticker] = (...)` lines stay as they are). Delete the now-unused `selected_venues` line in `_chatter_survivors` if `tsc`-style unused-variable lint complains; Python does not, so leaving it is fine.

Then extract pass two. Replace the body of the `for ticker, (mentions, expected, variance, authors, text_ratio) in survivors.items():` loop in `build_rows` with:

```python
        row = _assemble(ticker, (mentions, expected, variance, authors, text_ratio),
                        grouped[ticker], profiles.get(ticker), quote_views[ticker],
                        moves, quote_sigmas, window_hours, selected_venues, today)
        if allowed and row.segment not in allowed:
            continue
        # Breadth as a filter, not as a score -- counted apart from the
        # floor: this is the reader's own filter doing what they asked.
        if row.venues < min_venues:
            excluded['one_venue'] += 1
            continue
        rows.append(row)
```

and add the helper above `build_rows`:

```python
def _assemble(ticker, folded, parts, profile, quote, moves, quote_sigmas,
              window_hours, selected_venues, today,
              eligible=True, floor_reason=None):
    """Everything that costs a lookup, for one ticker, into a Row.

    Shared by the ranked board and the pinned (watched) rows so the two can
    never disagree about what a row says.
    """
    mentions, expected, variance, authors, text_ratio = folded
    mention_z = ((mentions - expected)
                 / max(variance, VARIANCE_FLOOR) ** 0.5) if variance else None
    contributing = sorted({part.source for part in parts})
    # One venue per ROOT, not per stored name -- see Row.venues.
    venues = len({source_root(name) for name in contributing})
    baseline_days = min((float(part.baseline_days) for part in parts
                         if part.baseline_days is not None), default=None)

    status = quote.tape_status
    move = (moves.get((ticker, quote.market))
            if quote.score_eligible else None)
    # A frozen tape reports no movement while mentions explode because it
    # froze -- maximum divergence produced by an artifact, so no score.
    value = None
    if quote.score_eligible and move is not None and mention_z is not None:
        sigma = quote_sigmas.get(ticker)
        move_z = divergence_mod.price_move_z(
            move, quotes_mod.scale_sigma(sigma, window_hours))
        if move_z is not None:
            value = divergence_mod.divergence(mention_z, move_z)

    marks = []
    if status == 'stale':
        marks.append('no-print')
    if venues == 1 and selected_venues > 1:
        marks.append('single-source')
    if baseline_days is not None and baseline_days < PROVISIONAL_BASELINE_DAYS:
        marks.append('provisional' if baseline_days >= 1.0 else 'warming-up')
    if any(part.truncated for part in parts):
        marks.append('partial')

    segment = universe.segment_for(
        profile.market_cap if profile else None,
        profile.ipo_date if profile else None,
        quote.price, today,
        profile.name if profile else None,
        profile.is_etf if profile else None)

    return Row(
        ticker=ticker,
        name=profile.name if profile else None,
        segment=segment,
        divergence=value,
        mention_z=mention_z,
        mentions=mentions,
        expected=expected,
        authors=authors,
        text_ratio=text_ratio,
        sources=contributing,
        venues=venues,
        price=quote.price,
        price_move=move,
        direction=divergence_mod.direction(move),
        price_status=status,
        quote=quote,
        baseline_days=baseline_days,
        marks=marks,
        eligible=eligible,
        floor_reason=floor_reason,
    )
```

Keep the existing comments in `build_rows` above the loop; delete the loop's old body (it moved into `_assemble` verbatim).

- [ ] **Step 4: Add `build_pinned`**

Append to `leaderboard.py`:

```python
def build_pinned(tickers, sources, now, window_hours=4, market='us'):
    """Rows for named tickers regardless of the eligibility floor.

    The floor decides ranking, not existence: a watched stock the reader
    marked deserves a row saying what was measured and why it was not
    ranked. Same aggregate, same lookups, same Row as the board -- with
    `eligible` False and `floor_reason` set where the floor would have
    dropped it, and every derived figure None where nothing was measured.
    """
    tickers = list(dict.fromkeys(t.upper() for t in tickers))
    if not tickers:
        return []
    since = now - dt.timedelta(hours=window_hours)
    scored_sources = expand_sources(sources)
    selected_venues = len({source_root(name) for name in sources})

    grouped = _aggregate(scored_sources, since, now, tickers=tickers)
    voices = journal.distinct_voice_counts(tickers, sources, since, now)
    profiles = _universe_rows(tickers)
    quote_views = quotes_mod.quote_views_for(tickers, market, now)
    moves = quotes_mod.moves_for(
        [(ticker, view.market, view.mic) for ticker, view in quote_views.items()
         if view.price is not None], window_hours, now)
    today = now.date()
    quote_sigmas = _quote_sigmas(quote_views, today)

    rows = []
    for ticker in tickers:
        parts = grouped.get(ticker, [])
        if parts:
            authors_seen, channels_seen = voices.get(ticker, (None, 0))
            mentions, expected, variance, authors, text_ratio, contributions = _fold(
                parts, authors_seen, channels_seen)
            eligible = scoring.is_eligible(contributions)
            reason = None if eligible else _rejection(contributions)
        else:
            # No bucket in the window: nothing measured, and the fold would
            # divide by nothing. Zeros here are counts of nothing observed,
            # not measurements; the derived figures come out None.
            mentions, expected, variance, authors, text_ratio = 0, 0.0, 0.0, 0, 1.0
            eligible, reason = False, 'no_mentions'
        rows.append(_assemble(
            ticker, (mentions, expected, variance, authors, text_ratio), parts,
            profiles.get(ticker), quote_views[ticker], moves, quote_sigmas,
            window_hours, selected_venues, today,
            eligible=eligible, floor_reason=reason))
    return rows
```

(`_rejection` already exists below; Python resolves it at call time.)

- [ ] **Step 5: The floor clause in `phrasing.py`**

Change the signature and body of `row_clauses`:

```python
def row_clauses(row, session, window_hours=4):
    """The phrase for one leaderboard row, in reading order.

    `session` is the exchange state. With the market shut there is no price
    clause at all -- the page says "market closed" once, and a mark carried by
    every row is not a mark.

    A row under the floor (a watched stock that was not ranked) says why,
    once, instead of a ratio: "2 mentions in 4h, under the floor" is the
    finding, and a ratio against a baseline the floor already rejected
    would dress it up as one.
    """
    if not getattr(row, 'eligible', True):
        return [_floor_clause(row, window_hours)] + _price_clauses(row, session)

    clauses = []
    # ... the existing body unchanged from here ...
```

and add, below `_breadth_clauses`:

```python
def _floor_clause(row, window_hours):
    """Why the floor kept this row off the board, in the row's own words."""
    reason = getattr(row, 'floor_reason', None)
    if reason == 'no_mentions':
        text = f'no mentions in {window_hours}h'
    elif reason == 'too_few_mentions':
        noun = 'mention' if row.mentions == 1 else 'mentions'
        text = f'{row.mentions} {noun} in {window_hours}h, under the floor'
    elif reason == 'too_few_voices':
        text = ('one voice only' if row.authors <= 1 else f'{row.authors} voices') \
            + ', under the floor'
    elif reason == 'repeated_text':
        text = 'repeated text, under the floor'
    else:
        text = 'under the floor'
    return Clause('warn', text)
```

- [ ] **Step 6: `board.build_pinned_rows` and the `_entries` extraction**

In `features/radar/board.py`, move the block of `build()` from `tickers = [row.ticker for row in ranked]` through the `rows = [BoardRow(...) for row in ranked]` list into a helper, and call it:

```python
def _entries(ranked, sources, now, window_hours):
    """What the surface needs to draw each row, beyond the rank: the 24h
    series, the price series, the normal line, the triplet, the tone and
    the words. Shared by the ranked board and the pinned rows."""
    tickers = [row.ticker for row in ranked]
    since = now - dt.timedelta(hours=SERIES_HOURS)

    covered = _covered_hours(sources, since, now)
    totals = _hourly_counts(tickers, sources, since, now)
    prices = _hourly_prices(ranked, since, now)
    triplets = _triplets(tickers, sources, now)
    # The lean arrows must agree with the detail panel's chatter breakdown,
    # which counts the SELECTED window -- not the sparkline's 24h axis.
    tones = _tones(tickers, sources,
                   now - dt.timedelta(hours=window_hours), now)

    empty_triplet = {hours: None for hours in TRIPLET_HOURS}
    return [BoardRow(
        rank=row,
        series=_series_for(row.ticker, totals, covered, since, now),
        price_series=_price_series_for(row.ticker, prices, since, now),
        # Guarded by the same rule as the ratio wording: an expected under
        # the baseline floor is noise, and drawing a "normal" line off it
        # would be the bar version of "200x normal".
        normal_per_hour=(row.expected / window_hours
                         if phrasing.ratio_value(row.mentions,
                                                 row.expected) is not None
                         else None),
        triplet=triplets.get(row.ticker, empty_triplet),
        tone=tones.get(row.ticker, Tone(0, 0, 0)),
        clauses=phrasing.row_clauses(row, row.quote.session, window_hours),
    ) for row in ranked]


def build_pinned_rows(tickers, sources, now, window_hours=4, market='us'):
    """Board entries for watched tickers, whatever the floor said."""
    pinned = leaderboard.build_pinned(tickers, sources, now,
                                      window_hours=window_hours, market=market)
    return _entries(pinned, sources, now, window_hours)
```

In `build()`, the moved block becomes one line: `rows = _entries(ranked, sources, now, window_hours)`.

- [ ] **Step 7: Run the tests to verify they pass**

Run: `python -m pytest tests/test_radar_leaderboard.py tests/test_radar_phrasing.py tests/test_radar_board.py tests/test_radar_api.py -q -p no:cacheprovider`
Expected: all pass (the four new leaderboard tests, the phrasing test, and no regression in board/api).

- [ ] **Step 8: Commit**

```bash
git add features/radar/leaderboard.py features/radar/phrasing.py features/radar/board.py tests/test_radar_leaderboard.py tests/test_radar_phrasing.py
git commit -m "feat(radar): rows for named tickers regardless of the floor

leaderboard.build_pinned reuses the board's aggregate, fold and assembly
(now shared helpers) and marks rows the floor would have dropped with
eligible=False and the gate they failed; phrasing says why in words."
```

---

### Task 5: `watching` and `watch_rows` on the board payload

**Files:**
- Modify: `features/radar/routes/api.py` (`_row`, `build_payload`, `board()`)
- Modify: `features/radar/routes/views.py` (`board_page()`)
- Test: `tests/test_radar_api.py` (append)

**Interfaces:**
- Consumes: `watch.tickers_for` (Task 1), `board_mod.build_pinned_rows` (Task 4).
- Produces: payload fields `watching: list[str]`, `watch_rows: list[row]`; every row (board and watch) carries `eligible: bool`. `build_payload(args, now=None, user_id=None)`.

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_radar_api.py`:

```python
def test_the_board_carries_the_callers_watch_rows_and_nobody_elses(client, monkeypatch):
    """Per-user data rides on top of the shared board: same rows for every
    account, different watch_rows -- and the memo is keyed on the
    selection alone."""
    import datetime as dt
    from app import app as flask_app
    from extensions import db
    from models import AppUser, RadarWatch
    from features.radar.routes import api
    from conftest import _admin_id

    with flask_app.app_context():
        AppUser.query.filter_by(username='pytest other watcher').delete()
        db.session.commit()
        other = AppUser(username='pytest other watcher', password_hash='x')
        db.session.add(other)
        db.session.commit()
        other_id = other.id
        RadarWatch.query.filter_by(user_id=_admin_id()).delete()
        db.session.add(RadarWatch(user_id=_admin_id(), ticker='ZZWATCH',
                                  created_at=dt.datetime(2026, 9, 2)))
        db.session.commit()
    try:
        api.board_cache.clear()
        mine = client.get('/radar/api/board?market=us').get_json()
        with client.session_transaction() as flask_session:
            flask_session['user_id'] = other_id
        theirs = client.get('/radar/api/board?market=us').get_json()

        assert mine['watching'] == ['ZZWATCH']
        assert [r['ticker'] for r in mine['watch_rows']] == ['ZZWATCH']
        assert mine['watch_rows'][0]['eligible'] is False
        assert mine['watch_rows'][0]['clauses'][0] == {
            'kind': 'warn', 'text': 'no mentions in 4h'}
        assert theirs['watching'] == [] and theirs['watch_rows'] == []
        assert theirs['rows'] == mine['rows']
        assert all('eligible' in r for r in mine['rows'])
        assert len(api.board_cache) == 1
    finally:
        with flask_app.app_context():
            RadarWatch.query.filter_by(user_id=_admin_id()).delete()
            AppUser.query.filter_by(id=other_id).delete()
            db.session.commit()
```

(`client` is the module's admin-session fixture from `conftest.py`.)

- [ ] **Step 2: Run the test to verify it fails**

Run: `python -m pytest tests/test_radar_api.py -q -p no:cacheprovider -k watch_rows`
Expected: FAIL — `KeyError: 'watching'`.

- [ ] **Step 3: Serialize `eligible`, add the per-user fields**

In `_row()` in `api.py`, add after `'marks': r.marks,`:

```python
        # False only on a watched row the floor would have dropped; the
        # island renders it quiet and its warn clause says why.
        'eligible': r.eligible,
```

Change `build_payload`:

```python
def build_payload(args, now=None, user_id=None):
    """Validated query -> serialized board. Shared by the page and the API.

    `user_id` adds the caller's watching list and its rows on top of the
    memoised, viewer-invariant board -- a handful of tickers, uncached
    because it is per account.
    """
    now = now or dt.datetime.now(dt.timezone.utc).replace(tzinfo=None)
    query = parse_query(args, now=now)
    board = _build_board(query, now)
    board.sources = sorted({source_root(s) for s in query.sources})
    payload = serialize(board)
    watching = watch.tickers_for(user_id) if user_id is not None else []
    payload['watching'] = watching
    payload['watch_rows'] = [_row(entry) for entry in board_mod.build_pinned_rows(
        watching, query.sources, now, window_hours=query.window,
        market=query.market)] if watching else []
    return payload
```

(keep the existing comments about the unexpanded selection and the rooted `sources` above those lines.)

In `board()`: `return jsonify(build_payload(request.args, user_id=current_user().id))`.

In `features/radar/routes/views.py`, import `current_user` beside `login_required` and pass it in both calls:

```python
    user_id = current_user().id
    try:
        payload = build_payload(request.args, user_id=user_id)
    except BadQuery:
        payload = build_payload({}, user_id=user_id)
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `python -m pytest tests/test_radar_api.py tests/test_radar_board_cache.py -q -p no:cacheprovider`
Expected: all pass. (`test_radar_board_cache.py` calls `build_payload(args, now=...)` without `user_id` — still valid.)

- [ ] **Step 5: Commit**

```bash
git add features/radar/routes/api.py features/radar/routes/views.py tests/test_radar_api.py
git commit -m "feat(radar): the board payload carries the caller's watching and watch_rows

Per account, added after the shared memoised build; every row now says
whether it cleared the floor."
```

---

### Task 6: Frontend plumbing — types, API calls, watching state

**Files:**
- Modify: `static/radar/src/types.ts`
- Modify: `static/radar/src/api.ts`
- Create: `static/radar/src/csrf.ts`
- Create: `static/radar/src/fixtures.ts` (the board/detail shapes tests share)
- Modify: `static/radar/src/board/BoardPage.tsx`
- Test: `static/radar/src/api.test.ts` (create), `static/radar/src/board/watching.test.tsx` (create)

**Interfaces:**
- Produces: `Row.eligible?: boolean`; `BoardPayload.watching?: string[]`, `BoardPayload.watch_rows?: Row[]`; `SearchMatch` type; `fetchSearch(q, signal?) -> Promise<SearchMatch[]>`; `setWatch(ticker, on) -> Promise<string[]>`; `csrfToken()`; `BoardPage` state `watching: string[]` and `toggleWatch(ticker)` passed down as `watching` + `onToggleWatch` props to `ListPane` and `DetailPane` (consumed in Tasks 7–9).

- [ ] **Step 1: Write the failing tests**

```ts
// static/radar/src/api.test.ts
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import { fetchSearch, setWatch } from './api'
import { resetCsrfCache } from './csrf'

beforeEach(() => {
  document.head.innerHTML = '<meta name="csrf-token" content="tok-123">'
  resetCsrfCache()
})
afterEach(() => { vi.unstubAllGlobals(); document.head.innerHTML = '' })

describe('search', () => {
  it('asks for the query and unwraps the matches', async () => {
    const spy = vi.fn(async () => ({
      ok: true, redirected: false, status: 200,
      json: async () => ({ matches: [{ ticker: 'NVDA', name: 'NVIDIA', exchange: 'Q', segment: 'large', watching: false }] }),
    }))
    vi.stubGlobal('fetch', spy)

    const found = await fetchSearch('nv idia')

    expect(String(spy.mock.calls[0]![0])).toBe('/radar/api/search?q=nv%20idia')
    expect(found.map((m) => m.ticker)).toEqual(['NVDA'])
  })
})

describe('watching', () => {
  it('PUTs to mark and DELETEs to unmark, with the csrf token, and returns the list', async () => {
    const spy = vi.fn(async () => ({
      ok: true, redirected: false, status: 200,
      json: async () => ({ watching: ['NVDA'] }),
    }))
    vi.stubGlobal('fetch', spy)

    expect(await setWatch('NVDA', true)).toEqual(['NVDA'])
    expect(await setWatch('NVDA', false)).toEqual(['NVDA'])

    const [onUrl, onInit] = spy.mock.calls[0] as unknown as [string, RequestInit]
    const [, offInit] = spy.mock.calls[1] as unknown as [string, RequestInit]
    expect(onUrl).toBe('/radar/api/watch/NVDA')
    expect(onInit.method).toBe('PUT')
    expect(offInit.method).toBe('DELETE')
    expect((onInit.headers as Record<string, string>)['X-CSRF-Token']).toBe('tok-123')
    expect((onInit.headers as Record<string, string>).Accept).toBe('application/json')
  })
})
```

```tsx
// static/radar/src/board/watching.test.tsx
// The star's optimism: it flips at once, the server is told, the board is
// refetched on success, and it reverts on failure.
import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import { BoardPage } from './BoardPage'
import { detail, payload, row } from '../fixtures'

function stubFetch({ watchFails = false, watching = ['BBB'] } = {}) {
  const spy = vi.fn(async (url: string, init?: RequestInit) => {
    if (url.includes('/api/watch/')) {
      if (watchFails) return { ok: false, redirected: false, status: 500, json: async () => ({}) }
      return { ok: true, redirected: false, status: 200, json: async () => ({ watching }) }
    }
    if (url.includes('/api/ticker/')) {
      return { ok: true, redirected: false, status: 200,
        json: async () => detail(url.split('/api/ticker/')[1]!.split('?')[0]!) }
    }
    return { ok: true, redirected: false, status: 200,
      json: async () => payload({ watching, watch_rows: [row({ ticker: 'BBB' })] }) }
  })
  vi.stubGlobal('fetch', spy)
  return spy
}
const calls = (part: string) => vi.mocked(fetch).mock.calls.filter((c) => String(c[0]).includes(part))

beforeEach(() => { window.history.replaceState(null, '', '/radar/') })
afterEach(() => vi.unstubAllGlobals())

describe('marking a stock', () => {
  it('flips the star at once, tells the server, then refetches the board', async () => {
    stubFetch()
    render(<BoardPage initial={payload()} />)
    await screen.findByText(/AAA is being discussed/)

    await userEvent.click(screen.getByRole('button', { name: 'Watch BBB' }))

    expect(screen.getByRole('button', { name: 'Stop watching BBB' })).toBeInTheDocument()
    await waitFor(() => expect(calls('/api/watch/BBB')).toHaveLength(1))
    await waitFor(() => expect(calls('/api/board')).toHaveLength(1))
  })

  it('reverts the star when the server refuses', async () => {
    stubFetch({ watchFails: true })
    render(<BoardPage initial={payload()} />)
    await screen.findByText(/AAA is being discussed/)

    await userEvent.click(screen.getByRole('button', { name: 'Watch BBB' }))

    await waitFor(() =>
      expect(screen.getByRole('button', { name: 'Watch BBB' })).toBeInTheDocument())
    expect(calls('/api/board')).toHaveLength(0)
  })

  it('opens on the watching list the server embedded', () => {
    stubFetch()
    render(<BoardPage initial={payload({ watching: ['AAA'] })} />)

    expect(screen.getByRole('button', { name: 'Stop watching AAA' })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Watch BBB' })).toBeInTheDocument()
  })
})
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `npx vitest run -c vite.radar.config.ts static/radar/src/api.test.ts static/radar/src/board/watching.test.tsx`
Expected: FAIL — `fetchSearch is not a function` / `Unable to find an accessible element with the role "button" and name "Watch BBB"`.

- [ ] **Step 3: Types**

In `static/radar/src/types.ts`, add to `Row` (after `clauses: Clause[]`):

```ts
  /** False only on a watched row the floor would have dropped: the island
   *  renders it quiet and its warn clause says why. Absent on payloads
   *  embedded before 2026-09-02, which is the same as true. */
  eligible?: boolean
```

add to `BoardPayload` (after `excluded`):

```ts
  /** The caller's marks, oldest first, and one row per mark for the
   *  current selection -- whatever the floor said. Absent on older embeds. */
  watching?: string[]
  watch_rows?: Row[]
```

and export the search shape (after `Selection`):

```ts
/** One universe match. Identity only: whether it is on the board, and its
 *  score, the island knows from the rows it holds. */
export interface SearchMatch {
  ticker: string
  name: string | null
  exchange: string | null
  segment: Segment
  watching: boolean
}
```

- [ ] **Step 4: The shared fixtures**

The three new suites (and Tasks 7-9) build boards and details; `BoardPage.test.tsx` already carries these shapes inline. Export them once. Not imported by app code, so never bundled; `tsconfig.json` typechecks it.

```ts
// static/radar/src/fixtures.ts
// Shapes for tests: one quote, one board row, one payload, one detail -- the
// ones BoardPage.test.tsx grew, exported so the newer suites do not each
// carry a forty-line copy. Not imported by app code, so never bundled.
import type { BoardPayload, Detail, MarketQuote, Row } from './types'

export function quote(): MarketQuote {
  return {
    market: 'us', venue: 'Nasdaq', mic: 'XNAS', currency: 'USD', price: 10,
    regular_move: 0.012, extended_move: null, session: 'regular',
    quality: 'live', age_seconds: 0, quoted_at: '2026-08-22T19:00:00Z',
    tape_status: 'ok', score_eligible: true, score_term: 'divergence',
    is_fallback: false,
    source: 'legacy',
    price_basis: 'trade',
    bid: null,
    ask: null,
  }
}

export function row(over: Partial<Row> = {}): Row {
  return {
    ticker: 'AAA', name: 'Alpha Inc', segment: 'large',
    divergence: 0.5, mention_z: 3.2, mentions: 20, expected: 6, ratio: 20 / 6,
    authors: 9,
    text_ratio: 0.9, sources: ['bluesky'],
    price: 10, price_move: 0.012, direction: 'up', price_status: 'ok',
    baseline_days: 30, marks: [],
    series: Array.from({ length: 25 }, (_, i) => ({ hour: `h${i}`, count: i })),
    price_series: Array.from({ length: 25 }, () => null),
    normal_per_hour: null,
    triplet: { '1': 1.1, '4': 3.2, '24': 2.0 },
    tone: { bullish: 4, neutral: 10, bearish: 2 },
    clauses: [{ kind: 'ratio', text: '3x its normal' },
              { kind: 'venues', text: '2 venues' }],
    eligible: true,
    ...over, quote: over.quote ?? quote(),
  }
}

export function payload(over: Partial<BoardPayload> = {}): BoardPayload {
  return {
    generated_at: '2026-08-22T19:00:00Z',
    market: 'us', display_timezone: 'Europe/Berlin',
    market_venue: 'US markets', next_boundary_label: 'closes',
    next_boundary_at: '2026-08-22T20:00:00Z',
    sources: ['bluesky', 'fourchan', 'reddit'],
    all_sources: ['bluesky', 'fourchan', 'reddit'],
    segments: [], session: 'regular', window_hours: 4,
    min_venues: 1, venue_counts: { any: 4, multi: 2 },
    segment_counts: { all: 4, large: 4 },
    triplet_hours: [1, 4, 24], series_hours: 24, lead_count: 3,
    rows: [row({ ticker: 'AAA' }), row({ ticker: 'BBB' }),
           row({ ticker: 'CCC' }), row({ ticker: 'DDD' })],
    excluded: {},
    watching: [], watch_rows: [],
    ...over,
  }
}

export function detail(ticker = 'AAA', market: Detail['market'] = 'us'): Detail {
  return {
    market, display_timezone: 'Europe/Berlin',
    identity: {
      ticker, name: 'Alpha Inc', exchange: 'NASDAQ', segment: 'large',
      market_cap: 1e9, ipo_date: '2020-01-01', price: 10, price_move: 0.012,
      price_status: 'ok', session: 'regular',
      quote: quote(),
    },
    read: [{ kind: 'plain', text: market === 'de'
      ? `${ticker} on de is being discussed.`
      : `${ticker} is being discussed.` }],
    chart: {
      from: '2025-08-23T00:00:00Z', span: '1Y', step_minutes: 1440,
      closes: Array.from({ length: 365 }, (_, i) => 100 + i),
      chatter: Array.from({ length: 365 }, (_, i) => (i < 360 ? null : i)),
      sessions: [],
      history_proxy: false, proxy_mic: null, proxy_venue: null,
      native_mic: null, native_venue: null, native_from: null,
      normal_per_slot: null,
      watched_from: '2026-08-18',
    },
    breakdown: {
      venues: [{ source: 'bluesky', mentions: 20, voices: 9 }],
      bullish: 4, neutral: 10, bearish: 2, disagreements: 1,
      top_author_share: 0.2, top_two_share: 0.3,
      peak_hour: '2026-08-22T14:00:00Z', peak_count: 9,
      first_seen: '2026-08-18', mentions: 20, voices: 9,
    },
    posts: [], post_total: 0,
  }
}
```

- [ ] **Step 5: `csrf.ts` and the API calls**

```ts
// static/radar/src/csrf.ts
// The per-session CSRF token, as board.html's <meta name="csrf-token">
// delivered it. Read lazily and memoised; the radar blueprint checks it on
// every write. The gym has the same three lines, on purpose: the two
// features share nothing.

let cached: string | null = null

export function csrfToken(): string {
  if (cached === null) {
    cached = document.querySelector('meta[name="csrf-token"]')
      ?.getAttribute('content') ?? ''
  }
  return cached
}

/** Test seam: jsdom documents have no shell meta. */
export function resetCsrfCache() {
  cached = null
}
```

In `static/radar/src/api.ts`: import `SearchMatch` in the type import and `csrfToken`:

```ts
import { csrfToken } from './csrf'
import type { BoardPayload, Detail, PanelSpan, SearchMatch, Selection } from './types'
```

Give `getJson` an `init` parameter and merge it (replace the signature and the `fetch(...)` call):

```ts
async function getJson<T>(url: string, signal?: AbortSignal,
                          init: RequestInit = {}): Promise<T> {
  // ...unchanged setup...
    const response = await fetch(url, {
      ...init,
      headers: { ...HEADERS, ...(init.headers as Record<string, string> | undefined) },
      credentials: 'same-origin', signal: controller.signal,
    })
  // ...unchanged...
```

Append:

```ts
/** Symbol-or-name matches from the whole universe, eight at most. */
export async function fetchSearch(q: string, signal?: AbortSignal): Promise<SearchMatch[]> {
  const found = await getJson<{ matches: SearchMatch[] }>(
    `/radar/api/search?q=${encodeURIComponent(q)}`, signal)
  return found.matches
}

/** Mark or unmark a ticker. Answers the caller's whole list, so nothing is
 *  merged client-side. Carries the CSRF token the radar blueprint demands
 *  on writes. */
export async function setWatch(ticker: string, on: boolean): Promise<string[]> {
  const answer = await getJson<{ watching: string[] }>(
    `/radar/api/watch/${encodeURIComponent(ticker)}`, undefined,
    { method: on ? 'PUT' : 'DELETE', headers: { 'X-CSRF-Token': csrfToken() } })
  return answer.watching
}
```

- [ ] **Step 6: Watching state in `BoardPage`**

In `static/radar/src/board/BoardPage.tsx`: import `setWatch` from `'../api'`. After the `selected` state add:

```tsx
  // The caller's marks. Optimistic: the star flips before the server
  // answers, the server's list replaces it, and a refusal puts it back.
  // The board's own payload also carries the list, so a refetch keeps it
  // true without a second request.
  const [watching, setWatching] = useState<string[]>(initial.watching ?? [])
  useEffect(() => { setWatching(payload.watching ?? []) }, [payload])
```

after `select` add:

```tsx
  const toggleWatch = useCallback(async (ticker: string) => {
    const before = watching
    const on = !before.includes(ticker)
    setWatching(on ? [...before, ticker] : before.filter((t) => t !== ticker))
    try {
      setWatching(await setWatch(ticker, on))
      // The watched rows are built server-side; a refetch brings the new
      // one in (or takes the old one out). Memo hit, so instant.
      void load(selection, selected, true)
    } catch {
      setWatching(before)
    }
  }, [watching, selection, selected, load])
```

and pass both to the panes: `<ListPane ... watching={watching} onToggleWatch={toggleWatch} />` and `<DetailPane ... watching={watching.includes(selected ?? '')} onToggleWatch={selected ? () => void toggleWatch(selected) : undefined} />`.

Until Tasks 7 and 8 land, `ListPane` and `DetailPane` do not accept these props; add them to both components' prop types now as optional (`watching?: string[]; onToggleWatch?: (ticker: string) => void` on ListPane, `watching?: boolean; onToggleWatch?: () => void` on DetailPane) without using them, so `tsc` stays green. `ListPane` must pass `watching`/`onToggleWatch` through to `TickerRow` for the watching test's buttons to exist — that is Task 7's job; the watching test stays RED until Task 7 completes. Run only `api.test.ts` green here.

- [ ] **Step 7: Run the tests**

Run: `npx vitest run -c vite.radar.config.ts static/radar/src/api.test.ts && npx tsc --noEmit`
Expected: `2 passed`; tsc clean. (`watching.test.tsx` goes green in Task 7.)

- [ ] **Step 8: Commit**

```bash
git add static/radar/src/types.ts static/radar/src/api.ts static/radar/src/csrf.ts static/radar/src/fixtures.ts static/radar/src/api.test.ts static/radar/src/board/BoardPage.tsx static/radar/src/board/watching.test.tsx static/radar/src/list/ListPane.tsx static/radar/src/detail/DetailPane.tsx
git commit -m "feat(radar): watching state and the search and watch API calls

Optimistic toggle in BoardPage; setWatch carries the CSRF token; the
payload's watching list is the source of truth after every refetch."
```

---

### Task 7: The Watching tier, the star column and quiet rows

**Files:**
- Modify: `static/radar/src/list/ListPane.tsx`
- Modify: `static/radar/src/list/TickerRow.tsx`
- Modify: `static/radar/radar.css`
- Test: `static/radar/src/list/watchtier.test.tsx` (create); `static/radar/src/list/tiers.test.tsx`, `keys.test.tsx`, `narrow.test.tsx`, `marks.test.tsx`, `TickerRow.test.tsx` (unchanged, must stay green); `static/radar/src/board/watching.test.tsx` (goes green)

**Interfaces:**
- Consumes: `watching`, `onToggleWatch` props (Task 6); `Row.eligible`, `payload.watch_rows`.
- Produces: `TickerRow` props `watching?: boolean`, `onToggleWatch?: (ticker: string) => void`; markup `div.line > [button.star, a.row]`; `a.row.quiet` when `eligible === false`; `export function scoreText(row: Row): string` (used by Task 9); Watching tier `p.tier.watching`.

- [ ] **Step 1: Write the failing tests**

```tsx
// static/radar/src/list/watchtier.test.tsx
import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it, vi } from 'vitest'

import { ListPane } from './ListPane'
import { payload as basePayload, row } from '../fixtures'
import type { BoardPayload, Row, Selection } from '../types'

const r = (ticker: string, over: Partial<Row> = {}): Row => row({ ticker, name: ticker, ...over })

const quiet = (ticker: string): Row => r(ticker, {
  eligible: false, divergence: null, mention_z: null, mentions: 2, expected: 0,
  ratio: null, normal_per_hour: null,
  // Zeros counted, nothing observed: the chart must draw no body from these.
  series: Array.from({ length: 25 }, (_, i) => ({ hour: `h${i}`, count: 0 })),
  clauses: [{ kind: 'warn', text: '2 mentions in 4h, under the floor' }],
})

const selection: Selection = {
  market: 'us', sources: ['bluesky', 'fourchan', 'reddit'], segments: [], window: 4, minVenues: 1,
}

const payload = (over: Partial<BoardPayload> = {}): BoardPayload => basePayload({
  rows: [r('A'), r('B'), r('C')], segment_counts: { all: 3, large: 3 }, ...over,
})

function sequence(container: HTMLElement): string[] {
  return Array.from(container.querySelectorAll('.tier, .row')).map((node) =>
    node.classList.contains('tier')
      ? `tier:${node.textContent!.replace(/\s+/g, ' ').trim().split(' ·')[0]}`
      : `row:${node.querySelector('.tk')!.textContent}${node.classList.contains('quiet') ? '(quiet)' : ''}`)
}

function list(over: Partial<BoardPayload> = {}, onToggleWatch = vi.fn()) {
  const utils = render(
    <ListPane payload={payload(over)} selection={selection} selected={null}
              busy={false} onSelect={() => {}} onChange={() => {}}
              watching={over.watching ?? []} onToggleWatch={onToggleWatch} />)
  return { ...utils, onToggleWatch }
}

describe('the Watching tier', () => {
  it('sits above the scored tier and takes its rows out of the ranked ones', () => {
    const { container } = list({ watching: ['B', 'Q'], watch_rows: [r('B'), quiet('Q')] })

    expect(sequence(container)).toEqual([
      'tier:Watching', 'row:B', 'row:Q(quiet)',
      'tier:Scored against price', 'row:A', 'row:C',
    ])
    expect(screen.getByText(/Scored against price/).closest('.tier')).toHaveTextContent(/\b2\b/)
  })

  it('is absent when nothing is watched', () => {
    list()
    expect(screen.queryByText(/^Watching/)).toBeNull()
  })

  it('shows a freshly starred board row at once, before the refetch brings its watch row', () => {
    /* The star is optimistic; the tier must not wait for the server. */
    const { container } = list({ watching: ['C'], watch_rows: [] })

    expect(sequence(container)).toEqual([
      'tier:Watching', 'row:C', 'tier:Scored against price', 'row:A', 'row:B',
    ])
  })

  it('renders a quiet row with no score and the floor\'s reason', () => {
    const { container } = list({ watching: ['Q'], watch_rows: [quiet('Q')] })

    const q = container.querySelector('.row.quiet')!
    expect(q.querySelector('.score')).toHaveTextContent('—')
    expect(q.querySelector('.sub.warn')).toHaveTextContent('2 mentions in 4h, under the floor')
    expect(q.querySelector('.chart path')).toBeNull()
  })

  it('puts a star beside every row, named for its action', async () => {
    const { onToggleWatch } = list({ watching: ['B'], watch_rows: [r('B')] })

    expect(screen.getByRole('button', { name: 'Stop watching B' })).toHaveAttribute('aria-pressed', 'true')
    await userEvent.click(screen.getByRole('button', { name: 'Watch A' }))

    expect(onToggleWatch).toHaveBeenCalledWith('A')
    // The star is a sibling of the link, never inside it.
    expect(screen.getByRole('button', { name: 'Watch A' }).closest('a')).toBeNull()
    expect(screen.getByRole('link', { name: /^A/ })).toHaveAttribute('id', 'radar-row-A')
  })
})
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `npx vitest run -c vite.radar.config.ts static/radar/src/list/watchtier.test.tsx`
Expected: FAIL — no Watching tier, no star buttons.

- [ ] **Step 3: `TickerRow` — star, quiet, `scoreText`**

In `static/radar/src/list/TickerRow.tsx`:

Replace `rankedBy` with an exported text helper plus the quiet case:

```tsx
/** The score cell's text for any row, board or watched. */
export function scoreText(row: Row): string {
  if (row.eligible === false) return '—'
  return scoredAgainstPrice(row) ? divergence(row.divergence) : zscore(row.mention_z)
}

function rankedBy(row: Row) {
  if (row.eligible === false) {
    return { label: '', value: '—',
             why: 'Under the floor this window: watched, not ranked.' }
  }
  const scored = scoredAgainstPrice(row)
  const term = rankTermFor(scored ? 'divergence' : 'chatter')
  return { ...term, value: scoreText(row) }
}
```

Add the two props to the component's props type (after `onSelect`):

```tsx
  /** Whether the reader has marked this row, and how to flip that. Absent
   *  where the row is rendered without an account (tests, legacy). */
  watching?: boolean
  onToggleWatch?: (ticker: string) => void
```

and destructure them: `const { row, selected, suppress = [], quoteSuppress = [], liftedAge = null, selection, onSelect, watching = false, onToggleWatch } = props`.

Wrap the returned `<a>` so the star is a sibling, not a child:

```tsx
  const quiet = row.eligible === false
  return (
    <div className={`line${quiet ? ' quiet' : ''}`}>
      {/* A button beside the link, never inside it: a control inside a link
          is invalid, and the row must stay a link with a copyable URL. */}
      {onToggleWatch && (
        <button type="button" className={`star${watching ? ' on' : ''}`}
                aria-pressed={watching}
                aria-label={`${watching ? 'Stop watching' : 'Watch'} ${row.ticker}`}
                onClick={() => onToggleWatch(row.ticker)}>
          {watching ? '★' : '☆'}
        </button>
      )}
      <a className={`row${selected ? ' on' : ''}${quiet ? ' quiet' : ''}`}
         ... (the existing <a> unchanged) ...
      </a>
    </div>
  )
```

In the chart, draw nothing when the row is quiet and nothing was counted: change `const areas = chatterAreas(row.series, BOX, yMax)` and `const outline = chatterRuns(...)` to

```tsx
  // A quiet row with nothing counted draws no body: an empty violet lane
  // beside the ranked rows would say "measured, and it was nothing".
  const counted = row.series.some((point) => point.count !== null && point.count > 0)
  const areas = counted ? chatterAreas(row.series, BOX, yMax) : []
  const outline = counted ? chatterRuns(row.series, BOX, yMax) : []
```

- [ ] **Step 4: `ListPane` — the tier and the split**

In `static/radar/src/list/ListPane.tsx`, add the props (after `account`):

```tsx
  /** The reader's marks and how to flip one; rendered as the Watching tier
   *  and as the star beside each row. */
  watching?: string[]
  onToggleWatch?: (ticker: string) => void
```

destructure `watching = [], onToggleWatch`, and replace `const [scored, chatter] = splitTiers(payload.rows)` with:

```tsx
  // Watched rows come from the server (`watch_rows`, built whatever the
  // floor said) -- and, until the refetch after a star lands, from the
  // board's own rows, so a fresh mark moves up at once. One row per ticker,
  // in the order the marks were made; the ranked tiers skip them.
  const marked = new Set(watching)
  const served = payload.watch_rows ?? []
  const watchRows = [
    ...served.filter((r) => marked.has(r.ticker)),
    ...payload.rows.filter((r) => marked.has(r.ticker)
      && !served.some((w) => w.ticker === r.ticker)),
  ].sort((a, b) => watching.indexOf(a.ticker) - watching.indexOf(b.ticker))
  const ranked = payload.rows.filter((r) => !marked.has(r.ticker))
  const [scored, chatter] = splitTiers(ranked)
```

change the captions gate to `const captions = payload.session !== 'closed' && ranked.length > 0`, pass the new props in `renderRow`:

```tsx
    <TickerRow key={row.ticker} row={row} onSelect={onSelect}
               suppress={shared} quoteSuppress={quoteShared.keys}
               liftedAge={quoteShared.agedTypical}
               session={payload.session} selection={selection}
               selected={row.ticker === selected}
               watching={marked.has(row.ticker)} onToggleWatch={onToggleWatch} />
```

and render the tier first inside `.rows`, before the scored caption:

```tsx
        {watchRows.length > 0 && (
          <p className="tier watching">
            <b>Watching</b>
            <span className="dot"> ·</span>{' '}
            <span className="what">your marks, in every view</span>
            {' '}
            <span className="n">{watchRows.length}</span>
          </p>
        )}
        {watchRows.map(renderRow)}
```

Also add a first empty span to the column header so it lines up with the star gutter: `<div className="cols" aria-hidden="true"><span className="gutter" />` … (the CSS below gives the header the same padding instead — pick the CSS route, no extra span).

- [ ] **Step 5: CSS**

In `static/radar/radar.css`:

Replace `.row + .tier { margin-top: var(--s3); border-top: 1px solid var(--rule); }` with `.line + .tier { margin-top: var(--s3); border-top: 1px solid var(--rule); }` and add after the `.tier .n` rule:

```css
/* The reader's own tier: no term, because its order is the reader's. */
.tier.watching .what { color: var(--muted); }
```

After the `.row` block add:

```css
/* The row and its star. The link keeps the ledger grid; the star sits in a
   gutter the link leaves on its left -- a sibling, never a child, because a
   control inside a link is invalid and the row must stay a copyable URL. */
.line { position: relative; flex: none; }
.line .star {
  position: absolute; left: var(--s6); top: 50%; transform: translateY(-50%);
  z-index: 1; font: inherit; font-size: 13px; line-height: 1;
  padding: 6px; margin: -6px; border: 0; background: none;
  color: var(--dim); cursor: pointer;
  transition: color var(--fast) var(--ease);
}
.line .star:hover { color: var(--ink); }
.line .star.on { color: var(--ink); }
.line .star:focus-visible { outline: 2px solid var(--mark); outline-offset: 1px; }
/* A watched row the floor would have dropped: present, quiet, honest. */
.row.quiet .tk { color: var(--ink-2); }
.row.quiet .score b { color: var(--muted); font-weight: 500; }
```

Widen the left padding so the gutter exists: in `.row` change `padding: 5px var(--s6);` to `padding: 5px var(--s6) 5px calc(var(--s6) + 22px);` and in `.cols` change `padding: 7px var(--s6) 5px;` to `padding: 7px var(--s6) 5px calc(var(--s6) + 22px);`. In the `@media (max-width: 900px)` row block change `padding: 7px var(--s5);` to `padding: 7px var(--s5) 7px calc(var(--s5) + 22px);` and add `.line .star { left: var(--s5); }` inside that block. Add `.line .star` to the `@media (pointer: coarse)` block: `.line .star { padding: 10px; margin: -10px; }`.

Extend the press layer: add `.line .star` to the selector list of the `:active` rule near `radar.css:1413` (the one starting `.t:not([aria-disabled="true"]):active, .spans button:active, ...`) and to the matching `transition:` rule just above it.

- [ ] **Step 6: Run the tests**

Run: `npx vitest run -c vite.radar.config.ts && npx tsc --noEmit`
Expected: all green, including `watchtier.test.tsx` (5) and `board/watching.test.tsx` (3) from Task 6; the existing row/tier/keys/narrow suites unchanged.

- [ ] **Step 7: Commit**

```bash
git add static/radar/src/list/ListPane.tsx static/radar/src/list/TickerRow.tsx static/radar/radar.css static/radar/src/list/watchtier.test.tsx
git commit -m "feat(radar): the Watching tier, a star on every row, quiet rows

Marked stocks sit above the board in every view; a fresh star moves the
row up at once; a watched stock under the floor renders quiet with the
floor's reason as its line."
```

---

### Task 8: The panel's Watch button

**Files:**
- Modify: `static/radar/src/detail/Identity.tsx`
- Modify: `static/radar/src/detail/DetailPane.tsx`
- Modify: `static/radar/radar.css`
- Test: `static/radar/src/detail/Identity.test.tsx` (create)

**Interfaces:**
- Consumes: `DetailPane` props `watching?: boolean`, `onToggleWatch?: () => void` (declared in Task 6).
- Produces: `Identity` props `watching?: boolean`, `onToggleWatch?: () => void`; button `.ident .watch` with accessible name "Watch NVDA" / "Stop watching NVDA".

- [ ] **Step 1: Write the failing test**

```tsx
// static/radar/src/detail/Identity.test.tsx
import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it, vi } from 'vitest'

import { Identity } from './Identity'
import { detail } from '../fixtures'
import type { Detail } from '../types'

const identity: Detail['identity'] = { ...detail('NVDA').identity, name: 'NVIDIA Corp' }

describe('the panel\'s watch button', () => {
  it('offers to watch, and to stop', async () => {
    const toggle = vi.fn()
    const { rerender } = render(<Identity identity={identity} watching={false} onToggleWatch={toggle} />)

    await userEvent.click(screen.getByRole('button', { name: 'Watch NVDA' }))
    expect(toggle).toHaveBeenCalledTimes(1)

    rerender(<Identity identity={identity} watching onToggleWatch={toggle} />)
    expect(screen.getByRole('button', { name: 'Stop watching NVDA' }))
      .toHaveAttribute('aria-pressed', 'true')
  })

  it('shows no button without an account to mark for', () => {
    render(<Identity identity={identity} />)
    expect(screen.queryByRole('button', { name: /watch/i })).toBeNull()
  })
})
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `npx vitest run -c vite.radar.config.ts static/radar/src/detail/Identity.test.tsx`
Expected: FAIL — no button named "Watch NVDA".

- [ ] **Step 3: Implement**

In `static/radar/src/detail/Identity.tsx`, extend the signature and render the button after the name line:

```tsx
export function Identity({ identity, watching = false, onToggleWatch }: {
  identity: Detail['identity']
  /** The reader's mark on this ticker, and how to flip it. */
  watching?: boolean
  onToggleWatch?: () => void
}) {
  // ...facts unchanged...
  return (
    <div className="ident">
      <div>
        <h2 id="panel-ticker">{identity.ticker}</h2>
        <div className="full">{identity.name ?? 'Name unknown'}</div>
        <div className="facts">{facts.join(' · ')}</div>
        {onToggleWatch && (
          <button type="button" className={`watch${watching ? ' on' : ''}`}
                  aria-pressed={watching}
                  aria-label={`${watching ? 'Stop watching' : 'Watch'} ${identity.ticker}`}
                  onClick={onToggleWatch}>
            {watching ? '★ Watching' : '☆ Watch'}
          </button>
        )}
      </div>
      {/* .px block unchanged */}
    </div>
  )
}
```

In `DetailPane.tsx`, forward the props: `<Identity identity={detail.identity} watching={watching} onToggleWatch={onToggleWatch} />` (the props were added to `DetailPane`'s type in Task 6; destructure them).

CSS, after the `.ident .facts` rules (find `.ident` in radar.css):

```css
/* The panel's mark: the same pill as Reload, pressed when watching. */
.ident .watch {
  margin-top: var(--s3); font: inherit; font-size: var(--t-xs);
  padding: 2px 10px; border: 1px solid var(--rule); border-radius: var(--r-pill);
  background: var(--raise); color: var(--ink-2); cursor: pointer;
  transition: color var(--fast) var(--ease), border-color var(--fast) var(--ease);
}
.ident .watch:hover { color: var(--ink); }
.ident .watch.on { color: var(--ink); border-color: var(--ink-2); }
.ident .watch:focus-visible { outline: 2px solid var(--mark); outline-offset: 1px; }
```

and add `.ident .watch` to the same two press-layer selector lists near `radar.css:1413`.

- [ ] **Step 4: Run the tests**

Run: `npx vitest run -c vite.radar.config.ts static/radar/src/detail/Identity.test.tsx static/radar/src/hardening.test.tsx static/radar/src/board/BoardPage.test.tsx && npx tsc --noEmit`
Expected: all green.

- [ ] **Step 5: Commit**

```bash
git add static/radar/src/detail/Identity.tsx static/radar/src/detail/DetailPane.tsx static/radar/radar.css static/radar/src/detail/Identity.test.tsx
git commit -m "feat(radar): watch from the panel"
```

---

### Task 9: The search combobox

**Files:**
- Create: `static/radar/src/board/Search.tsx`
- Modify: `static/radar/src/list/ListPane.tsx` (render it in the masthead; pass `onSelect`)
- Modify: `static/radar/radar.css`
- Test: `static/radar/src/board/Search.test.tsx` (create)

**Interfaces:**
- Consumes: `fetchSearch` (Task 6), `scoreText` (Task 7), `exchangeLabel`/`segmentLabel` from `../format`, `SearchMatch`.
- Produces: `Search` component with props `rows: Row[]`, `watching: string[]`, `onPick: (ticker: string) => void`, `onToggleWatch?: (ticker: string) => void`; rendered by `ListPane` between the market switch and the spend mark, with `onPick={onSelect}`.

- [ ] **Step 1: Write the failing tests**

```tsx
// static/radar/src/board/Search.test.tsx
import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import { Search } from './Search'
import { row } from '../fixtures'
import type { SearchMatch } from '../types'

const matches: SearchMatch[] = [
  { ticker: 'NVDA', name: 'NVIDIA Corp', exchange: 'Q', segment: 'large', watching: false },
  { ticker: 'NVAX', name: 'Novavax', exchange: 'Q', segment: 'micro', watching: false },
]

function stubSearch(found = matches) {
  const spy = vi.fn(async (url: string) => ({
    ok: true, redirected: false, status: 200,
    json: async () => ({ matches: url.includes('q=nv') ? found : [] }),
  }))
  vi.stubGlobal('fetch', spy)
  return spy
}

beforeEach(() => vi.useFakeTimers({ shouldAdvanceTime: true }))
afterEach(() => { vi.useRealTimers(); vi.unstubAllGlobals() })

function search(props: Partial<Parameters<typeof Search>[0]> = {}) {
  const onPick = vi.fn(); const onToggleWatch = vi.fn()
  render(<Search rows={[row({ ticker: 'NVDA' })]} watching={['NVAX']} onPick={onPick}
                 onToggleWatch={onToggleWatch} {...props} />)
  return { onPick, onToggleWatch, input: screen.getByRole('combobox') }
}

describe('finding a stock', () => {
  it('fetches once the typing settles, and only for the last query', async () => {
    const spy = stubSearch()
    const { input } = search()
    const user = userEvent.setup({ advanceTimers: vi.advanceTimersByTime })

    await user.type(input, 'nv')
    await waitFor(() => expect(screen.getByRole('listbox')).toBeInTheDocument())

    expect(spy).toHaveBeenCalledTimes(1)
    expect(String(spy.mock.calls[0]![0])).toBe('/radar/api/search?q=nv')
    expect(screen.getAllByRole('option')).toHaveLength(2)
  })

  it('annotates each match from what the page already knows', async () => {
    stubSearch()
    const { input } = search()
    const user = userEvent.setup({ advanceTimers: vi.advanceTimersByTime })

    await user.type(input, 'nv')
    await screen.findByRole('listbox')

    expect(screen.getByRole('option', { name: /NVDA/ })).toHaveTextContent('on the board · +0.50')
    expect(screen.getByRole('option', { name: /NVAX/ })).toHaveTextContent('watching')
  })

  it('walks the list with the arrows and opens the panel with Enter', async () => {
    stubSearch()
    const { input, onPick } = search()
    const user = userEvent.setup({ advanceTimers: vi.advanceTimersByTime })

    await user.type(input, 'nv')
    await screen.findByRole('listbox')
    await user.keyboard('{ArrowDown}{Enter}')

    expect(onPick).toHaveBeenCalledWith('NVAX')
    expect(screen.queryByRole('listbox')).toBeNull()
    expect(input).toHaveValue('nv')
  })

  it('stars a match without opening it', async () => {
    stubSearch()
    const { input, onToggleWatch, onPick } = search()
    const user = userEvent.setup({ advanceTimers: vi.advanceTimersByTime })

    await user.type(input, 'nv')
    await screen.findByRole('listbox')
    await user.click(screen.getByRole('button', { name: 'Watch NVDA' }))

    expect(onToggleWatch).toHaveBeenCalledWith('NVDA')
    expect(onPick).not.toHaveBeenCalled()
  })

  it('is reached with / and left with Escape, in stages', async () => {
    stubSearch()
    const { input } = search()
    const user = userEvent.setup({ advanceTimers: vi.advanceTimersByTime })

    fireEvent.keyDown(window, { key: '/' })
    expect(document.activeElement).toBe(input)

    await user.type(input, 'nv')
    await screen.findByRole('listbox')
    await user.keyboard('{Escape}')
    expect(screen.queryByRole('listbox')).toBeNull()
    expect(input).toHaveValue('nv')
    await user.keyboard('{Escape}')
    expect(input).toHaveValue('')
  })

  it('says so when nothing matches', async () => {
    stubSearch([])
    const { input } = search()
    const user = userEvent.setup({ advanceTimers: vi.advanceTimersByTime })

    await user.type(input, 'nv')

    await waitFor(() => expect(screen.getByRole('listbox')).toHaveTextContent('Nothing matches'))
  })
})
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `npx vitest run -c vite.radar.config.ts static/radar/src/board/Search.test.tsx`
Expected: FAIL — `Failed to resolve import "./Search"`.

- [ ] **Step 3: Write the component**

```tsx
// static/radar/src/board/Search.tsx
import { useEffect, useRef, useState } from 'react'
import type { KeyboardEvent } from 'react'

import { fetchSearch } from '../api'
import { exchangeLabel, segmentLabel } from '../format'
import { scoreText } from '../list/TickerRow'
import type { Row, SearchMatch } from '../types'

/** How long typing has to go quiet before a request goes out. */
const SETTLE_MS = 150

/** Find a stock by symbol or name, anywhere in the universe.
 *
 *  A combobox in the masthead: `/` reaches it from anywhere, the arrows walk
 *  the matches, Enter opens the panel -- for a stock on the board or not,
 *  through the same path a row click takes. Each match is annotated from
 *  what the page already holds (on the board with its score, watching,
 *  or quiet today); the endpoint returns identity only.
 */
export function Search({ rows, watching, onPick, onToggleWatch }: {
  rows: Row[]
  watching: string[]
  onPick: (ticker: string) => void
  onToggleWatch?: (ticker: string) => void
}) {
  const [q, setQ] = useState('')
  const [matches, setMatches] = useState<SearchMatch[]>([])
  const [open, setOpen] = useState(false)
  const [active, setActive] = useState(-1)
  const input = useRef<HTMLInputElement>(null)
  // The request that may still publish. A slow answer to an old query must
  // not replace the list the reader is looking at.
  const latest = useRef(0)

  // `/` focuses, as on GitHub -- unless the reader is already typing.
  useEffect(() => {
    const onKey = (event: globalThis.KeyboardEvent) => {
      if (event.key !== '/' || event.ctrlKey || event.metaKey || event.altKey) return
      const target = event.target as HTMLElement | null
      if (target && (target.tagName === 'INPUT' || target.tagName === 'TEXTAREA'
                     || target.isContentEditable)) return
      event.preventDefault()
      input.current?.focus()
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [])

  useEffect(() => {
    const query = q.trim()
    const mine = ++latest.current
    if (!query) {
      setMatches([]); setOpen(false); setActive(-1)
      return
    }
    const controller = new AbortController()
    const timer = setTimeout(() => {
      fetchSearch(query, controller.signal).then((found) => {
        if (mine !== latest.current) return
        setMatches(found); setOpen(true); setActive(found.length ? 0 : -1)
      }).catch(() => {
        if (mine !== latest.current) return
        setMatches([]); setOpen(true); setActive(-1)
      })
    }, SETTLE_MS)
    return () => { clearTimeout(timer); controller.abort() }
  }, [q])

  const status = (match: SearchMatch): string => {
    const onBoard = rows.find((r) => r.ticker === match.ticker)
    if (onBoard) return `on the board · ${scoreText(onBoard)}`
    if (watching.includes(match.ticker) || match.watching) return 'watching'
    return 'quiet today'
  }

  const pick = (ticker: string) => {
    onPick(ticker)
    setOpen(false)
  }

  const onKeyDown = (event: KeyboardEvent<HTMLInputElement>) => {
    if (event.key === 'ArrowDown' && open) {
      event.preventDefault(); setActive((i) => Math.min(i + 1, matches.length - 1))
    } else if (event.key === 'ArrowUp' && open) {
      event.preventDefault(); setActive((i) => Math.max(i - 1, 0))
    } else if (event.key === 'Enter' && open && active >= 0 && matches[active]) {
      event.preventDefault(); pick(matches[active]!.ticker)
    } else if (event.key === 'Escape') {
      // In stages: the list, then the words, then the box.
      event.preventDefault()
      if (open) setOpen(false)
      else if (q) setQ('')
      else input.current?.blur()
    }
  }

  const listId = 'radar-search-list'
  const optionId = (ticker: string) => `radar-search-${ticker}`

  return (
    <div className="search">
      <input ref={input} type="search" role="combobox" aria-label="Find a stock"
             aria-expanded={open} aria-controls={listId} aria-autocomplete="list"
             aria-activedescendant={open && active >= 0 && matches[active]
               ? optionId(matches[active]!.ticker) : undefined}
             placeholder="Find a stock" value={q} spellCheck={false}
             onChange={(event) => setQ(event.target.value)}
             onKeyDown={onKeyDown}
             onFocus={() => { if (matches.length || q.trim()) setOpen(Boolean(q.trim())) }} />
      {open && (
        <ul id={listId} role="listbox" className="matches">
          {matches.map((match, index) => (
            <li key={match.ticker} id={optionId(match.ticker)} role="option"
                aria-selected={index === active}
                aria-label={`${match.ticker} ${match.name ?? ''}`}
                className={index === active ? 'active' : undefined}
                onMouseEnter={() => setActive(index)}>
              {/* mousedown is prevented so the input keeps focus and the
                  list does not close before the click lands. */}
              <button type="button" className="pick"
                      onMouseDown={(event) => event.preventDefault()}
                      onClick={() => pick(match.ticker)}>
                <b>{match.ticker}</b>
                <span className="nm">{match.name ?? '—'}</span>
                <span className="meta">
                  {[exchangeLabel(match.exchange), segmentLabel(match.segment)]
                    .filter(Boolean).join(' · ')}
                </span>
                <span className="st">{status(match)}</span>
              </button>
              {onToggleWatch && (
                <button type="button"
                        className={`star${watching.includes(match.ticker) ? ' on' : ''}`}
                        aria-pressed={watching.includes(match.ticker)}
                        aria-label={`${watching.includes(match.ticker) ? 'Stop watching' : 'Watch'} ${match.ticker}`}
                        onMouseDown={(event) => event.preventDefault()}
                        onClick={() => onToggleWatch(match.ticker)}>
                  {watching.includes(match.ticker) ? '★' : '☆'}
                </button>
              )}
            </li>
          ))}
          {matches.length === 0 && (
            <li className="none" role="option" aria-selected="false">Nothing matches</li>
          )}
        </ul>
      )}
    </div>
  )
}
```

`scoreText` for a divergence row returns `signed(value, 2)` → `+0.50`, which the annotation test expects.

- [ ] **Step 4: Mount it in the masthead**

In `ListPane.tsx`, import `Search` from `'../board/Search'` and render it in `.brand` between the market switch and the spend mark:

```tsx
          <MarketSwitch selection={selection} onChange={onChange} />
          <Search rows={payload.rows} watching={watching}
                  onPick={onSelect} onToggleWatch={onToggleWatch} />
          <SpendMark payload={payload} />
```

- [ ] **Step 5: CSS**

Add after the `.brand .spend + .age` rule:

```css
/* Find a stock. The box sits in the masthead beside the market; the list
   drops over the controls and arrives like the folded filters do. */
.brand .search { position: relative; margin-left: var(--s5); }
.brand .search input {
  font: inherit; font-size: var(--t-xs); width: 190px;
  padding: 3px 10px; border: 1px solid var(--rule); border-radius: var(--r-pill);
  background: var(--raise); color: var(--ink);
  transition: border-color var(--fast) var(--ease);
}
.brand .search input::placeholder { color: var(--muted); }
.brand .search input:focus-visible { outline: 2px solid var(--mark); outline-offset: 1px; }
.brand .search input::-webkit-search-cancel-button { display: none; }
.search .matches {
  position: absolute; top: calc(100% + 6px); left: 0; width: 380px; max-width: calc(100vw - 2 * var(--s6));
  z-index: 100; margin: 0; padding: 4px 0; list-style: none;
  background: var(--raise); border: 1px solid var(--rule); border-radius: var(--r);
  animation: settle 160ms var(--ease) backwards;
}
.search .matches li { display: grid; grid-template-columns: minmax(0, 1fr) auto; align-items: center; }
.search .matches li.active { background: var(--mark-wash); }
.search .matches .pick {
  font: inherit; font-size: var(--t-xs); text-align: left;
  display: grid; grid-template-columns: 56px minmax(0, 1fr) auto; column-gap: var(--s3);
  align-items: baseline; width: 100%; padding: 6px 10px; border: 0; background: none;
  color: var(--ink-2); cursor: pointer;
}
.search .matches .pick b { color: var(--ink); font-weight: 700; }
.search .matches .pick .nm { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.search .matches .pick .meta { grid-column: 2; font-size: var(--t-ax); color: var(--muted); }
.search .matches .pick .st { grid-column: 3; grid-row: 1 / 3; font-size: var(--t-ax); color: var(--muted); white-space: nowrap; }
.search .matches .star {
  font: inherit; font-size: 13px; line-height: 1; padding: 6px 12px; border: 0; background: none;
  color: var(--dim); cursor: pointer; transition: color var(--fast) var(--ease);
}
.search .matches .star:hover, .search .matches .star.on { color: var(--ink); }
.search .matches .star:focus-visible { outline: 2px solid var(--mark); outline-offset: -2px; }
.search .matches .none { padding: 8px 10px; font-size: var(--t-xs); color: var(--muted); }
@media (max-width: 900px) {
  /* Its own line under the wordmark; the masthead has no width to spare. */
  .brand { flex-wrap: wrap; }
  .brand .search { flex-basis: 100%; order: 9; margin: var(--s2) 0 0; }
  .brand .search input { width: 100%; }
  .search .matches { width: 100%; }
}
```

Add `.search .matches .star, .search .matches .pick` to the same two press-layer selector lists near `radar.css:1413`.

- [ ] **Step 6: Run the tests**

Run: `npx vitest run -c vite.radar.config.ts && npx tsc --noEmit`
Expected: all green (6 new in `Search.test.tsx`; `keys.test.tsx`'s Escape test still passes — the search input is not focused there).

- [ ] **Step 7: Commit**

```bash
git add static/radar/src/board/Search.tsx static/radar/src/board/Search.test.tsx static/radar/src/list/ListPane.tsx static/radar/radar.css
git commit -m "feat(radar): find a stock from the masthead

A combobox over the whole universe: / focuses, arrows walk, Enter opens
the panel, Escape leaves in stages; matches annotated from the page."
```

---

### Task 10: PRODUCT.md, browser verification, merge

**Files:**
- Modify: `features/radar/PRODUCT.md`
- Modify: `docs/superpowers/specs/2026-09-02-radar-watching-and-search-design.md` (status line only)
- Verification script: `personal_apps/scratchpad/verify_watching.py` (create; not committed — `scratchpad/` holds throwaway scripts)

- [ ] **Step 1: PRODUCT.md**

In `features/radar/PRODUCT.md`, under "Deliberately absent", replace the line `- No watchlist, no portfolio, no positions` with:

```
- No portfolio, no positions. **Watching exists** since 2026-09-02: the
  reader's own marks, kept per account, never a signal from the tool — a
  watched stock gets a row above the board saying what was measured, and
  the surface still recommends nothing.
```

Keep `- No alerts (...)` as it is. In the spec, change `**Status:** approved in brainstorm 2026-09-02, spec for review` to `**Status:** built 2026-09-02 (plan docs/superpowers/plans/2026-09-02-radar-watching-and-search.md)`.

- [ ] **Step 2: Build and run the whole gate**

Run from `personal_apps/`:

```bash
npx vitest run -c vite.radar.config.ts && npx tsc --noEmit && npx vite build -c vite.radar.config.ts && python -m pytest tests/test_radar_watch.py tests/test_radar_watch_api.py tests/test_radar_search.py tests/test_radar_api.py tests/test_radar_leaderboard.py tests/test_radar_phrasing.py tests/test_radar_board.py tests/test_radar_board_cache.py -q -p no:cacheprovider
```

Expected: every suite green.

- [ ] **Step 3: Browser check on the Flask dev server**

Start the server (`preview_start` name `personal_apps`, or `flask run --port 5001`), then write and run the script. It signs in with a minted session cookie (see `reference_personal_apps_local_run` in memory: `SecureCookieSessionInterface` with `{'user_id': 1}`), marks one board ticker and one quiet ticker through the API, and screenshots three viewports with the search open.

```python
# scratchpad/verify_watching.py  (run with PYTHONPATH=. from personal_apps/)
import os, urllib.request
from playwright.sync_api import sync_playwright
from app import app as flask_app
from flask.sessions import SecureCookieSessionInterface

OUT = os.path.join(os.path.dirname(__file__), 'verify_watching')
os.makedirs(OUT, exist_ok=True)
ser = SecureCookieSessionInterface().get_signing_serializer(flask_app)
name = flask_app.config.get('SESSION_COOKIE_NAME') or 'session'
cookie = ser.dumps({'user_id': 1})

with sync_playwright() as p:
    b = p.chromium.launch()
    ctx = b.new_context(viewport={'width': 1440, 'height': 900})
    ctx.add_cookies([{'name': name, 'value': cookie, 'domain': 'localhost', 'path': '/'}])
    pg = ctx.new_page()
    pg.goto('http://localhost:5001/radar/?market=us&window=24', wait_until='networkidle')
    pg.wait_for_selector('.row', timeout=30000)
    first = pg.locator('.row .tk').nth(0).text_content()
    # Mark the top board row and a quiet ticker through the real buttons/API.
    pg.click(f'button[aria-label="Watch {first}"]')
    pg.wait_for_selector('.tier.watching', timeout=30000)
    pg.fill('input[role="combobox"]', 'HTZ'); pg.wait_for_selector('[role="listbox"]', timeout=30000)
    pg.click('[role="listbox"] button[aria-label^="Watch HTZ"]')
    pg.wait_for_function("() => document.querySelectorAll('.tier.watching ~ .line').length >= 2", timeout=30000)
    pg.fill('input[role="combobox"]', 'nv'); pg.wait_for_selector('[role="listbox"]', timeout=30000)
    pg.screenshot(path=os.path.join(OUT, 'desk_1440.png'))
    print('watching tier rows:', pg.evaluate("() => [...document.querySelectorAll('.line')].slice(0,3).map(l => l.querySelector('.tk').textContent + (l.classList.contains('quiet') ? ' (quiet)' : ''))"))
    for w, h, tag in ((768, 1024, 'tablet'), (390, 844, 'phone')):
        c = b.new_context(viewport={'width': w, 'height': h})
        c.add_cookies([{'name': name, 'value': cookie, 'domain': 'localhost', 'path': '/'}])
        q = c.new_page(); q.goto('http://localhost:5001/radar/?market=us&window=24', wait_until='networkidle')
        q.wait_for_selector('.tier.watching', timeout=30000)
        q.screenshot(path=os.path.join(OUT, f'{tag}.png'))
        print(tag, 'overflowX', q.evaluate("() => document.documentElement.scrollWidth > document.documentElement.clientWidth"))
    # Leave the account as it was.
    for t in (first, 'HTZ'):
        pg.click(f'button[aria-label="Stop watching {t}"]'); pg.wait_for_timeout(300)
    b.close()
```

View the three PNGs (Read tool). Check: Watching tier above the scored tier with the board row and a quiet HTZ row; star column aligned with the header gutter; search dropdown over the controls; no horizontal overflow on the phone; the dropdown on its own line on the phone.

- [ ] **Step 4: Commit and merge**

```bash
git add features/radar/PRODUCT.md docs/superpowers/specs/2026-09-02-radar-watching-and-search-design.md
git commit -m "docs(radar): watching is no longer deliberately absent"
git checkout main && git merge dev_personal && git push origin main && git push origin dev_personal && git checkout dev_personal
```

Deploy note for Michi (non-routine): this round carries a migration — `flask db upgrade` on the VPS before restarting the service.
