# Radar Plan 4 — Leaderboard Data

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Assemble everything the radar has learned about a ticker into one ranked row, filtered by the sources and segment the viewer chose — the data behind the leaderboard, with no HTML in sight.

**Architecture:** One module that reads scored buckets, quotes and universe rows and returns a list of plain dataclasses, plus a JSON route that serves them. The surface that renders this is Plan 5 and goes through the design skill; nothing here decides what anything looks like.

**Tech Stack:** Python 3.12, Flask blueprint, SQLAlchemy, pytest. No new dependencies.

**Spec:** `docs/superpowers/specs/2026-08-20-radar-social-sentiment-design.md` §8.1, §8.6
**Predecessors:** Plans 1, 1b, 2 and 3 complete. 273 radar tests green.

## Global Constraints

- **No rendering.** This plan produces data. Templates, CSS and React are Plan 5.
- **The source selector is a read-time filter** (spec §8.6). It re-pools stored per-source components; it must never touch `source_config_version`, start a warm-up, or write anything.
- **Nothing outside `config.py` names a source.**
- **A missing thing is missing.** A ticker with no quote gets no divergence rather than a divergence of zero; a source with no row for a bucket drops out of the pooling rather than contributing nothing.
- **Ineligible rows are excluded, not ranked low** (spec §6.3). Below the floor there is no signal to rank.
- All datetimes UTC. The radar suite must keep passing under `-W error::DeprecationWarning`.
- Working directory for every command: `C:\Users\michi\Desktop\CodingStuff\personal_apps`.

---

## File Structure

**Create:**

| Path | Responsibility |
|---|---|
| `features/radar/leaderboard.py` | Row assembly, filtering, ranking |
| `features/radar/routes/__init__.py`, `routes/_blueprint.py`, `routes/api.py` | The blueprint and its JSON route |
| `tests/test_radar_leaderboard.py`, `tests/test_radar_api.py` | |

**Modify:** `app.py` (register the blueprint)

---

## Task 1: Row assembly

**Files:**
- Create: `personal_apps/features/radar/leaderboard.py`
- Test: `personal_apps/tests/test_radar_leaderboard.py`

**Interfaces:**
- Produces:
  - `Row` — dataclass with `ticker`, `name`, `segment`, `divergence`, `mention_z`, `mentions`, `expected`, `authors`, `text_ratio`, `sources`, `price`, `price_move`, `direction`, `price_status`, `baseline_days`, `marks`
  - `build_rows(sources, now, window_hours=4, segment=None, limit=50) -> list[Row]`

- [ ] **Step 1: Write the failing test**

```python
# personal_apps/tests/test_radar_leaderboard.py
"""One ranked row per ticker, from everything the radar knows.

Reads scored buckets, quotes and universe rows. Decides nothing about
appearance -- that is Plan 5 -- but does decide what is worth showing at all,
which is the eligibility floor's job and the one place a thin board must not
be padded.
"""
import datetime as dt
import decimal

import pytest

from app import app as flask_app
from extensions import db
from models import RadarBucketSource, RadarQuote, TickerUniverse
from features.radar import leaderboard
from features.radar.config import source_config_version

NOW = dt.datetime(2026, 8, 21, 15, 0, 0)


@pytest.fixture()
def board():
    with flask_app.app_context():
        for model in (RadarBucketSource, RadarQuote):
            model.query.filter(model.ticker.like('LB%')).delete(
                synchronize_session=False)
        TickerUniverse.query.filter(TickerUniverse.symbol.like('LB%')).delete(
            synchronize_session=False)
        db.session.commit()
        yield
        for model in (RadarBucketSource, RadarQuote):
            model.query.filter(model.ticker.like('LB%')).delete(
                synchronize_session=False)
        TickerUniverse.query.filter(TickerUniverse.symbol.like('LB%')).delete(
            synchronize_session=False)
        db.session.commit()


def universe_row(ticker, cap='50000000000', name='Test Corp'):
    db.session.add(TickerUniverse(
        symbol=ticker, name=name, exchange='NYSE',
        first_seen=dt.datetime(2020, 1, 1),
        market_cap=decimal.Decimal(cap) if cap else None))


def scored(ticker, source='bluesky', minutes_ago=30, mentions=10, authors=6,
           z=5.0, expected=1.0, variance=2.0, text_ratio=0.9, status='ok',
           baseline_days=30):
    db.session.add(RadarBucketSource(
        ticker=ticker, bucket_start=NOW - dt.timedelta(minutes=minutes_ago),
        source=source, mention_count=mentions, high_confidence_count=mentions,
        low_count=0, distinct_authors=authors, distinct_text_ratio=text_ratio,
        engagement_weighted_count=float(mentions), status=status,
        source_config_version=source_config_version(),
        expected=expected, variance=variance, mention_z=z,
        baseline_days=baseline_days))


def quoted(ticker, price, prev, minutes_ago=5, quote_ts=None):
    when = NOW - dt.timedelta(minutes=minutes_ago)
    db.session.add(RadarQuote(
        ticker=ticker, fetched_at=when, quote_ts=quote_ts or when,
        price=decimal.Decimal(price), prev_close=decimal.Decimal(prev),
        volume=1000))


def test_a_scored_eligible_ticker_becomes_a_row(board):
    universe_row('LBA')
    scored('LBA')
    quoted('LBA', '100.00', '100.00')
    db.session.commit()

    rows = leaderboard.build_rows(['bluesky'], NOW)
    assert [r.ticker for r in rows] == ['LBA']
    assert rows[0].name == 'Test Corp'
    assert rows[0].mentions == 10


def test_an_ineligible_ticker_is_excluded_not_ranked_low(board):
    """Below the floor there is no signal to rank. Showing it at the bottom
    would imply it was measured and found wanting, when it was never
    measurable."""
    universe_row('LBB')
    scored('LBB', mentions=2, authors=1)
    db.session.commit()
    assert leaderboard.build_rows(['bluesky'], NOW) == []


def test_ranking_is_by_divergence(board):
    """Loud and unmoved outranks equally loud and already up."""
    universe_row('LBUP')
    universe_row('LBFLAT')
    for ticker in ('LBUP', 'LBFLAT'):
        scored(ticker)
    quoted('LBUP', '112.00', '100.00')     # ran hard
    quoted('LBFLAT', '100.20', '100.00')   # barely moved
    db.session.commit()

    rows = leaderboard.build_rows(['bluesky'], NOW)
    assert [r.ticker for r in rows] == ['LBFLAT', 'LBUP']


def test_only_the_selected_sources_are_pooled(board):
    """The selector is a read-time filter over stored components."""
    universe_row('LBC')
    scored('LBC', source='bluesky', mentions=6, z=3.0)
    scored('LBC', source='fourchan', mentions=6, z=3.0)
    db.session.commit()

    both = leaderboard.build_rows(['bluesky', 'fourchan'], NOW)[0]
    one = leaderboard.build_rows(['bluesky'], NOW)[0]
    assert both.mentions == 12
    assert one.mentions == 6
    assert both.mention_z > one.mention_z


def test_a_row_records_which_sources_contributed(board):
    universe_row('LBD')
    scored('LBD', source='bluesky')
    scored('LBD', source='fourchan')
    db.session.commit()
    row = leaderboard.build_rows(['bluesky', 'fourchan'], NOW)[0]
    assert set(row.sources) == {'bluesky', 'fourchan'}


def test_a_single_source_row_is_marked(board):
    """The same divergence backed by two independent sources is stronger
    evidence than one, and the row has to say which it is."""
    universe_row('LBE')
    scored('LBE', source='bluesky')
    db.session.commit()
    assert 'single-source' in leaderboard.build_rows(['bluesky', 'fourchan'],
                                                     NOW)[0].marks


def test_a_frozen_tape_carries_no_divergence(board):
    """A halted stock keeps its last price while mentions explode because it
    halted -- maximum divergence produced entirely by an artifact."""
    universe_row('LBF')
    scored('LBF')
    frozen = NOW - dt.timedelta(minutes=40)
    for step in range(3):
        quoted('LBF', '100.00', '100.00', minutes_ago=10 - 2 * step,
               quote_ts=frozen)
    db.session.commit()

    row = leaderboard.build_rows(['bluesky'], NOW)[0]
    assert row.divergence is None
    assert 'no-print' in row.marks


def test_a_ticker_with_no_quote_still_appears_without_divergence(board):
    """The chatter is real even when we have no price for it. Dropping the row
    would hide a genuine signal; inventing a divergence would fabricate one."""
    universe_row('LBG')
    scored('LBG')
    db.session.commit()
    row = leaderboard.build_rows(['bluesky'], NOW)[0]
    assert row.divergence is None
    assert row.price is None


def test_a_thin_baseline_is_marked_provisional(board):
    universe_row('LBH')
    scored('LBH', baseline_days=3)
    db.session.commit()
    assert 'provisional' in leaderboard.build_rows(['bluesky'], NOW)[0].marks


def test_a_truncated_source_is_marked_partial(board):
    universe_row('LBI')
    scored('LBI', status='truncated')
    db.session.commit()
    assert 'partial' in leaderboard.build_rows(['bluesky'], NOW)[0].marks


def test_segment_filtering(board):
    universe_row('LBBIG', cap='50000000000')
    universe_row('LBSML', cap='100000000')
    for ticker in ('LBBIG', 'LBSML'):
        scored(ticker)
    db.session.commit()

    assert [r.ticker for r in leaderboard.build_rows(['bluesky'], NOW,
                                                     segment='large')] == ['LBBIG']
    assert [r.ticker for r in leaderboard.build_rows(['bluesky'], NOW,
                                                     segment='micro')] == ['LBSML']


def test_a_ticker_missing_from_the_universe_still_ranks(board):
    """Mentions of a symbol we have no profile for are still mentions, and the
    Unknown segment is a first-class tab rather than a discard pile."""
    scored('LBZZ')
    db.session.commit()
    row = leaderboard.build_rows(['bluesky'], NOW)[0]
    assert row.ticker == 'LBZZ'
    assert row.segment == 'unknown'


def test_the_limit_is_respected(board):
    for index in range(8):
        ticker = 'LB%02d' % index
        universe_row(ticker)
        scored(ticker, z=float(index))
    db.session.commit()
    assert len(leaderboard.build_rows(['bluesky'], NOW, limit=3)) == 3
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_radar_leaderboard.py -v`
Expected: FAIL with `ImportError: cannot import name 'leaderboard'`

- [ ] **Step 3: Write minimal implementation**

```python
# personal_apps/features/radar/leaderboard.py
"""One ranked row per ticker.

Reads scored buckets, quotes and universe rows; decides nothing about
appearance. What it does decide is what is worth showing at all -- the
eligibility floor -- and that matters more on a thin board than a busy one,
because the temptation to pad is greatest when there is little to show.
"""
import collections
import dataclasses
import datetime as dt

from models import RadarBucketSource, TickerUniverse

from . import divergence as divergence_mod
from . import quotes as quotes_mod
from . import scoring, universe
from .config import PROVISIONAL_BASELINE_DAYS


@dataclasses.dataclass
class Row:
    ticker: str
    name: str | None
    segment: str
    divergence: float | None
    mention_z: float | None
    mentions: int
    expected: float
    authors: int
    text_ratio: float
    sources: list
    price: object
    price_move: object
    direction: str
    price_status: str
    baseline_days: int | None
    marks: list


def _universe_rows(tickers):
    if not tickers:
        return {}
    rows = TickerUniverse.query.filter(
        TickerUniverse.symbol.in_(list(tickers))).all()
    return {row.symbol: row for row in rows}


def build_rows(sources, now, window_hours=4, segment=None, limit=50):
    """Ranked leaderboard rows for the selected sources.

    The source list is a read-time filter: it re-pools components that were
    stored per source, and never touches how anything was scored (spec 8.6).
    """
    since = now - dt.timedelta(hours=window_hours)

    scored_rows = (RadarBucketSource.query
                   .filter(RadarBucketSource.source.in_(list(sources)),
                           RadarBucketSource.bucket_start >= since,
                           RadarBucketSource.bucket_start < now,
                           RadarBucketSource.mention_z.isnot(None))
                   .all())

    grouped = collections.defaultdict(list)
    for row in scored_rows:
        grouped[row.ticker].append(row)

    profiles = _universe_rows(grouped.keys())
    today = now.date()
    rows = []

    for ticker, buckets in grouped.items():
        mentions = sum(b.mention_count for b in buckets)
        expected = sum(b.expected or 0.0 for b in buckets)
        variance = sum(b.variance or 0.0 for b in buckets)
        authors = max(b.distinct_authors for b in buckets)
        text_ratio = min(b.distinct_text_ratio for b in buckets)

        # Below the floor there is nothing to rank. Showing it low would imply
        # it was measured and found wanting, when it was never measurable.
        if not scoring.is_eligible(mentions, authors, text_ratio):
            continue

        mention_z = ((mentions - expected)
                     / max(variance, 0.25) ** 0.5) if variance else None

        contributing = sorted({b.source for b in buckets})
        baseline_days = min((b.baseline_days for b in buckets
                             if b.baseline_days is not None), default=None)

        profile = profiles.get(ticker)
        status = quotes_mod.price_status(ticker, now)
        move = quotes_mod.move_since(ticker, hours=window_hours, now=now)

        latest = None
        if status != 'unknown':
            from models import RadarQuote
            latest = (RadarQuote.query
                      .filter(RadarQuote.ticker == ticker,
                              RadarQuote.fetched_at <= now)
                      .order_by(RadarQuote.fetched_at.desc()).first())

        # A frozen tape reports no movement while mentions explode because it
        # froze. That is maximum divergence produced by an artifact, so the
        # row carries the mark and no score rather than a flattering number.
        value = None
        if status == 'ok' and move is not None and mention_z is not None:
            closes_sigma = None
            if profile is not None and profile.market_cap is not None:
                closes_sigma = None      # filled by the volatility job
            move_z = divergence_mod.price_move_z(move, closes_sigma)
            if move_z is not None:
                value = divergence_mod.divergence(mention_z, move_z)

        marks = []
        if status == 'stale':
            marks.append('no-print')
        if len(contributing) == 1 and len(sources) > 1:
            marks.append('single-source')
        if baseline_days is not None and baseline_days < PROVISIONAL_BASELINE_DAYS:
            marks.append('provisional')
        if any(b.status == 'truncated' for b in buckets):
            marks.append('partial')

        row_segment = universe.segment_for(
            profile.market_cap if profile else None,
            profile.ipo_date if profile else None,
            latest.price if latest else None,
            today)
        if segment is not None and row_segment != segment:
            continue

        rows.append(Row(
            ticker=ticker,
            name=profile.name if profile else None,
            segment=row_segment,
            divergence=value,
            mention_z=mention_z,
            mentions=mentions,
            expected=expected,
            authors=authors,
            text_ratio=text_ratio,
            sources=contributing,
            price=latest.price if latest else None,
            price_move=move,
            direction=divergence_mod.direction(move),
            price_status=status,
            baseline_days=baseline_days,
            marks=marks,
        ))

    # Divergence first where it exists, then mention_z. A ticker with no price
    # is not evidence of anything about its price, so it sorts below one that
    # has been measured -- but it is not dropped.
    rows.sort(key=lambda r: (r.divergence is not None,
                             r.divergence if r.divergence is not None else 0,
                             r.mention_z or 0), reverse=True)
    return rows[:limit]
```

Add to `personal_apps/features/radar/config.py`:

```python
# Below this many days of history a reading is marked provisional (spec 6.8).
PROVISIONAL_BASELINE_DAYS = 14
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_radar_leaderboard.py -v`
Expected: 13 passed

- [ ] **Step 5: Commit**

```bash
git add personal_apps/features/radar/leaderboard.py personal_apps/features/radar/config.py personal_apps/tests/test_radar_leaderboard.py
git commit -m "feat(radar): assemble one ranked row per ticker"
```

---

## Task 2: Volatility, cached per ticker

`build_rows` currently cannot compute divergence: it has no sigma, because fetching daily closes per ticker per page load would be absurd. Volatility belongs in a table, refreshed on its own schedule.

**Files:**
- Modify: `personal_apps/models.py`, `personal_apps/features/radar/quotes.py`, `personal_apps/features/radar/leaderboard.py`
- Create: migration
- Test: `personal_apps/tests/test_radar_quotes.py`

**Interfaces:**
- Produces: `TickerUniverse.daily_sigma`, `TickerUniverse.sigma_refreshed_at`; `quotes.refresh_sigma(provider, tickers, now) -> int`

- [ ] **Step 1: Write the failing test**

Append to `personal_apps/tests/test_radar_quotes.py`:

```python
def test_sigma_is_stored_on_the_universe_row(ctx):
    """Fetching 30 daily closes per ticker per page load would be absurd, so
    volatility lives in a column and is refreshed on its own schedule."""
    from models import TickerUniverse
    from features.radar import quotes as quotes_mod

    class FakeProvider:
        def daily_closes(self, symbol, days):
            return [(dt.date(2026, 7, 1) + dt.timedelta(days=i),
                     decimal.Decimal(100 + (i % 3))) for i in range(30)]

    db.session.add(TickerUniverse(symbol='QQS', name='Sigma Corp',
                                  exchange='NYSE', first_seen=NOW))
    db.session.commit()

    assert quotes_mod.refresh_sigma(FakeProvider(), ['QQS'], NOW) == 1
    row = TickerUniverse.query.filter_by(symbol='QQS').one()
    assert row.daily_sigma > 0
    assert row.sigma_refreshed_at == NOW
    TickerUniverse.query.filter_by(symbol='QQS').delete()
    db.session.commit()


def test_a_provider_with_no_history_leaves_sigma_alone(ctx):
    """No history is not a volatility of zero, and a zero sigma downstream
    would turn every price move into an infinite z."""
    from models import TickerUniverse
    from features.radar import quotes as quotes_mod

    class Empty:
        def daily_closes(self, symbol, days):
            return []

    db.session.add(TickerUniverse(symbol='QQT', name='Thin Corp',
                                  exchange='NYSE', first_seen=NOW,
                                  daily_sigma=0.02))
    db.session.commit()

    quotes_mod.refresh_sigma(Empty(), ['QQT'], NOW)
    assert TickerUniverse.query.filter_by(symbol='QQT').one().daily_sigma == \
        pytest.approx(0.02)
    TickerUniverse.query.filter_by(symbol='QQT').delete()
    db.session.commit()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_radar_quotes.py -v`
Expected: FAIL — `TickerUniverse` has no attribute `daily_sigma`

- [ ] **Step 3: Write minimal implementation**

Add to `TickerUniverse` in `personal_apps/models.py`:

```python
    # Standard deviation of daily returns, from the daily-close provider.
    # Stored rather than computed on demand: divergence needs it for every row
    # of every page load, and it changes on the scale of weeks.
    daily_sigma        = db.Column(db.Float, nullable=True)
    sigma_refreshed_at = db.Column(MYSQL_DATETIME(fsp=6), nullable=True)
```

Add to `personal_apps/features/radar/quotes.py`:

```python
def refresh_sigma(provider, tickers, now):
    """Recompute and store daily volatility. Returns how many were updated.

    A ticker whose provider returns no history keeps whatever it had. No
    history is not a volatility of zero, and a zero sigma downstream turns
    every price move into an infinite z.
    """
    from models import TickerUniverse

    updated = 0
    for ticker in tickers:
        closes = provider.daily_closes(ticker, days=35)
        sigma = daily_sigma(closes)
        if sigma is None:
            continue

        row = TickerUniverse.query.filter_by(symbol=ticker).one_or_none()
        if row is None:
            continue
        row.daily_sigma = sigma
        row.sigma_refreshed_at = now
        updated += 1

    db.session.commit()
    return updated
```

Then wire it into `leaderboard.build_rows`, replacing the placeholder block:

```python
        value = None
        if status == 'ok' and move is not None and mention_z is not None:
            sigma = profile.daily_sigma if profile else None
            move_z = divergence_mod.price_move_z(
                move, quotes_mod.scale_sigma(sigma, window_hours))
            if move_z is not None:
                value = divergence_mod.divergence(mention_z, move_z)
```

Generate and apply the migration.

- [ ] **Step 4: Run tests**

Run: `python -m pytest tests/test_radar_quotes.py tests/test_radar_leaderboard.py -v`
Expected: all pass

- [ ] **Step 5: Commit**

```bash
git add personal_apps/models.py personal_apps/migrations/versions/ personal_apps/features/radar/quotes.py personal_apps/features/radar/leaderboard.py personal_apps/tests/test_radar_quotes.py
git commit -m "feat(radar): cache volatility so divergence can be computed per row"
```

---

## Task 3: The JSON route

**Files:**
- Create: `personal_apps/features/radar/routes/__init__.py`, `routes/_blueprint.py`, `routes/api.py`
- Modify: `personal_apps/app.py`
- Test: `personal_apps/tests/test_radar_api.py`

**Interfaces:**
- Produces: `GET /radar/api/board` accepting `sources`, `segment`, `window`, `limit`

- [ ] **Step 1: Write the failing test**

```python
# personal_apps/tests/test_radar_api.py
"""The JSON the surface will read.

Login-required and global: mention data is not personal, so all accounts see
identical rows (spec 8.5).
"""
import json


def test_the_board_requires_login(anon_client):
    response = anon_client.get('/radar/api/board')
    assert response.status_code in (302, 401, 403)


def test_the_board_returns_json(client):
    response = client.get('/radar/api/board')
    assert response.status_code == 200
    payload = json.loads(response.data)
    assert 'rows' in payload
    assert 'sources' in payload
    assert isinstance(payload['rows'], list)


def test_the_selected_sources_are_echoed_back(client):
    """The surface needs to know which selection produced these rows, or a
    stale request and a fresh one look identical."""
    payload = json.loads(client.get('/radar/api/board?sources=bluesky').data)
    assert payload['sources'] == ['bluesky']


def test_an_unknown_source_is_rejected(client):
    """Silently ignoring it would return the default board under a selection
    the viewer never made."""
    assert client.get('/radar/api/board?sources=nonsense').status_code == 400


def test_an_unknown_segment_is_rejected(client):
    assert client.get('/radar/api/board?segment=nonsense').status_code == 400


def test_the_window_is_bounded(client):
    """An unbounded window would scan the whole partitioned history on a page
    load."""
    assert client.get('/radar/api/board?window=99999').status_code == 400


def test_defaults_are_every_source_and_no_segment_filter(client):
    payload = json.loads(client.get('/radar/api/board').data)
    from features.radar.config import SOURCES
    assert set(payload['sources']) == set(SOURCES)
    assert payload['segment'] is None
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_radar_api.py -v`
Expected: FAIL with 404 — the blueprint is not registered

- [ ] **Step 3: Write minimal implementation**

```python
# personal_apps/features/radar/routes/_blueprint.py
"""The radar blueprint, alone in its own module.

Same pattern as the gym blueprint: every routes/ module imports radar_bp from
here rather than from the package, so importing one never pulls in the others.
That is the whole reason this file exists.
"""
from flask import Blueprint

radar_bp = Blueprint('radar', __name__, url_prefix='/radar')
```

```python
# personal_apps/features/radar/routes/__init__.py
"""Radar routes, split by surface.

Importing a module here registers its routes onto radar_bp, so each must be
imported below even though the names look unused.
"""
from ._blueprint import radar_bp     # noqa: F401

from . import api                    # noqa: F401
```

```python
# personal_apps/features/radar/routes/api.py
"""JSON for the leaderboard surface."""
import datetime as dt

from flask import jsonify, request

from auth import login_required

from .. import leaderboard
from ..config import SOURCES
from ._blueprint import radar_bp

SEGMENTS = ('large', 'mid', 'micro', 'unknown', 'recent_ipo')
WINDOWS = (1, 4, 24)
MAX_LIMIT = 100


def _decimal_or_none(value):
    return float(value) if value is not None else None


@radar_bp.route('/api/board')
@login_required
def board():
    """Ranked rows for the selected sources, segment and window.

    Every parameter is validated rather than coerced. Silently ignoring an
    unknown source would return the default board under a selection the viewer
    never made, which is worse than an error.
    """
    raw_sources = request.args.get('sources')
    if raw_sources:
        selected = [s.strip() for s in raw_sources.split(',') if s.strip()]
        if any(s not in SOURCES for s in selected):
            return jsonify({'error': 'unknown source'}), 400
    else:
        selected = list(SOURCES)

    segment = request.args.get('segment') or None
    if segment is not None and segment not in SEGMENTS:
        return jsonify({'error': 'unknown segment'}), 400

    try:
        window = int(request.args.get('window', 4))
    except ValueError:
        return jsonify({'error': 'bad window'}), 400
    if window not in WINDOWS:
        return jsonify({'error': 'unsupported window'}), 400

    try:
        limit = min(int(request.args.get('limit', 50)), MAX_LIMIT)
    except ValueError:
        return jsonify({'error': 'bad limit'}), 400

    now = dt.datetime.now(dt.timezone.utc).replace(tzinfo=None)
    rows = leaderboard.build_rows(selected, now, window_hours=window,
                                  segment=segment, limit=limit)

    return jsonify({
        'generated_at': now.isoformat() + 'Z',
        'sources': selected,
        'segment': segment,
        'window_hours': window,
        'rows': [{
            'ticker': r.ticker,
            'name': r.name,
            'segment': r.segment,
            'divergence': r.divergence,
            'mention_z': r.mention_z,
            'mentions': r.mentions,
            'expected': r.expected,
            'authors': r.authors,
            'text_ratio': r.text_ratio,
            'sources': r.sources,
            'price': _decimal_or_none(r.price),
            'price_move': _decimal_or_none(r.price_move),
            'direction': r.direction,
            'price_status': r.price_status,
            'baseline_days': r.baseline_days,
            'marks': r.marks,
        } for r in rows],
    })
```

Register in `personal_apps/app.py`, beside the other blueprints:

```python
from features.radar.routes import radar_bp
app.register_blueprint(radar_bp)
```

- [ ] **Step 4: Run tests**

Run: `python -m pytest tests/test_radar_api.py -v`
Expected: 7 passed

- [ ] **Step 5: Commit**

```bash
git add personal_apps/features/radar/routes/ personal_apps/app.py personal_apps/tests/test_radar_api.py
git commit -m "feat(radar): serve the board as JSON"
```

---

## Task 4: Schedule the volatility refresh

**Files:**
- Modify: `personal_apps/run_radar_ingest.py`, `personal_apps/tests/test_radar_daemon.py`

- [ ] **Step 1: Write the failing test**

Append to `personal_apps/tests/test_radar_daemon.py`:

```python
def test_sigma_refresh_covers_the_board(monkeypatch):
    """Volatility changes on the scale of weeks, so it refreshes on its own
    slow schedule rather than per page load."""
    asked = {}
    monkeypatch.setattr(daemon, '_loud_tickers', lambda now, limit: ['AAA', 'BBB'])
    monkeypatch.setattr(daemon.quotes, 'refresh_sigma',
                        lambda provider, tickers, now: asked.setdefault(
                            'tickers', list(tickers)) and 0 or len(tickers))
    daemon.refresh_volatility(_utc(2026, 8, 21, 14), object())
    assert asked['tickers'] == ['AAA', 'BBB']


def test_a_failing_sigma_refresh_is_contained(monkeypatch):
    def boom(provider, tickers, now):
        raise RuntimeError('provider down')

    monkeypatch.setattr(daemon, '_loud_tickers', lambda now, limit: ['AAA'])
    monkeypatch.setattr(daemon.quotes, 'refresh_sigma', boom)
    assert daemon.refresh_volatility(_utc(2026, 8, 21, 14), object()) == 0
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_radar_daemon.py -v`
Expected: FAIL — no attribute `refresh_volatility`

- [ ] **Step 3: Write minimal implementation**

Add to `personal_apps/run_radar_ingest.py`:

```python
from features.radar.prices import twelvedata as twelvedata_provider

# Twelve Data allows 800 requests a day and volatility moves on the scale of
# weeks, so this is deliberately slow and small.
SIGMA_LIMIT = 60
SIGMA_INTERVAL_HOURS = 12


def refresh_volatility(now_utc, provider, limit=SIGMA_LIMIT):
    """Recompute daily sigma for the tickers on the board."""
    tickers = _loud_tickers(now_utc, limit)
    if not tickers:
        return 0
    try:
        return quotes.refresh_sigma(provider, tickers,
                                    now_utc.replace(tzinfo=None))
    except Exception:
        logger.exception('radar volatility refresh failed')
        return 0


def _scheduled_volatility():
    now = dt.datetime.now(dt.timezone.utc)
    provider = twelvedata_provider.TwelveDataProvider(
        twelvedata_provider.TwelveDataHttp())
    with app.app_context():
        updated = refresh_volatility(now, provider)
    logger.info('radar volatility refreshed %d tickers', updated)
```

Register in `main()`:

```python
    scheduler.add_job(_scheduled_volatility, 'interval',
                      hours=SIGMA_INTERVAL_HOURS, id='radar_volatility',
                      max_instances=1, coalesce=True,
                      next_run_time=dt.datetime.now(dt.timezone.utc)
                      + dt.timedelta(minutes=5))
```

- [ ] **Step 4: Run the full radar suite**

Run: `python -m pytest tests/test_radar_*.py -q -W error::DeprecationWarning`
Expected: all pass

- [ ] **Step 5: Commit**

```bash
git add personal_apps/run_radar_ingest.py personal_apps/tests/test_radar_daemon.py
git commit -m "feat(radar): refresh volatility on its own slow schedule"
```

---

## Done when

- `python -m pytest tests/test_radar_*.py -q -W error::DeprecationWarning` passes
- `GET /radar/api/board` returns JSON for a logged-in session and refuses an anonymous one
- A ticker below the eligibility floor is absent from the board rather than ranked last
- A ticker with a frozen tape appears with `divergence: null` and a `no-print` mark

## What Plan 5 picks up

The surface. That is design work rather than plumbing — it goes through the design skill, starts from what this JSON actually contains, and gets mockups before any component is written.

## What is still deferred

The spike log, session-relative forward returns and the did-it-work aggregates (spec §7). They were pushed behind the leaderboard deliberately: a log of what cleared the bar is worth little until it is possible to see whether anything clears it.
