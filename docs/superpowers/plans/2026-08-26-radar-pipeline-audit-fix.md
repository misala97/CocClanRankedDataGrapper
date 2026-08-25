# Radar Pipeline Audit Fix — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Fix the fourteen defects found by the 2026-08-26 radar pipeline audit, so the board stops discarding 43% of its busiest quarter-hours, stops ranking rows on stale scores, stops paying for tone nothing renders, and stops hashing config that nothing calls.

**Architecture:** A short-retention mention journal (`radar_mention_events`) becomes the durable record of every extracted mention, so `buckets.roll_up` can rebuild a bucket from everything that landed in it instead of from one cycle's cursor slice. Everything downstream keeps its current shape; the corrections are to what is stored, what is cleared, and what is read.

**Tech Stack:** Python 3.12, Flask + Flask-SQLAlchemy, Alembic migrations, MySQL 8 locally / MariaDB in production, pytest, React 19 + Vite for the island.

**Spec:** `docs/superpowers/specs/2026-08-26-radar-pipeline-audit-design.md`

## Global Constraints

- Branch: `dev_personal`. Never commit on `main`.
- All work is under `personal_apps/`. Run pytest **from `personal_apps/`** — the suites do `from app import app`, which needs that cwd.
- Tests run against the real local dev database. Radar suites namespace their fixtures with tickers matching `ZZ%` and must clean up after themselves.
- **Production is MariaDB, local dev is MySQL 8.** `CAST(... AS JSON)` is a parse error on MariaDB. DDL commits even when the surrounding migration then fails, so a migration that half-applies leaves the schema changed and the alembic version behind.
- `radar_buckets` and `radar_bucket_sources` are **partitioned monthly by `bucket_start`**. Every unique key, primary key included, must contain `bucket_start`. InnoDB supports no foreign keys on partitioned tables.
- Every datetime in this codebase is **naive UTC**. `dt.datetime.now(dt.timezone.utc).replace(tzinfo=None)`, never `utcnow()`.
- `config.source_config_version()` must be bumped by any change to **which mentions get counted**, and must not move for changes to how a counted mention is scored or aggregated. Each task below states which it is.
- An absence is never a zero. A missing verdict, a failed fetch, an unpriced model and an unobserved bucket all stay NULL.
- Green and red are reserved for price direction. Nothing else on the surface may use them.
- Alembic head at plan time is `a53d0b0fcc37`. Migrations chain from it in task order.
- Michi runs the deploy (`~/update_coc.sh` on the VPS) after `main` is pushed. Never write deploy commands into a task.

---

## File Structure

**New files**

| Path | Responsibility |
|---|---|
| `personal_apps/features/radar/journal.py` | Read and write `radar_mention_events`. The only module that knows the table exists. |
| `personal_apps/migrations/versions/<rev>_add_radar_mention_events.py` | Creates the journal table. |
| `personal_apps/migrations/versions/<rev>_add_mention_event_promoted.py` | The `promoted` flag the eligibility floor reads. |
| `personal_apps/migrations/versions/<rev>_widen_radar_source_columns.py` | `source` to `String(48)` on the two tables that key by it. |
| `personal_apps/migrations/versions/<rev>_baseline_days_to_float.py` | `baseline_days` SmallInteger to Float. |
| `personal_apps/scripts/backfill_radar_buckets.py` | One-shot repair of existing bucket counts from stored mentions. |
| `personal_apps/tests/test_radar_journal.py` | The journal's own suite. |
| `personal_apps/tests/test_radar_config_reachability.py` | Asserts no config member is dead. |

**Modified files**

| Path | Change |
|---|---|
| `personal_apps/models.py` | `RadarMentionEvent`; widen two `source` columns. |
| `personal_apps/features/radar/buckets.py` | `MentionRow.external_id`; `roll_up` reads the journal; clear scoring columns on a non-`ok` status. |
| `personal_apps/features/radar/ingest.py` | Pass `external_id`; extract once per post; `depths` NULL on failure; wire `allow_single_letter`. |
| `personal_apps/features/radar/config.py` | Delete `PAGE_CAP`; retire StockTwits entries; `MENTION_EVENT_RETENTION_HOURS`; prefix-aware source lookups. |
| `personal_apps/features/radar/scoring.py` | Score `truncated` rows. |
| `personal_apps/features/radar/sources/reddit.py` | Rate `None` not `0.0`; per-subreddit source names. |
| `personal_apps/features/radar/sources/stocktwits.py` | Deleted. |
| `personal_apps/features/radar/spend.py` | `cost_micros` returns `None`; `summary` reports unpriced tokens. |
| `personal_apps/features/radar/detail.py` | Interior gaps in the intraday chatter series. |
| `personal_apps/features/radar/detail_panel.py` | Breakdown reads `llm_sentiment`; disagreement count. |
| `personal_apps/features/radar/leaderboard.py` | `VARIANCE_FLOOR`; `baseline_days` not truncated to whole days. |
| `personal_apps/features/radar/board.py` | `min_venues` feeds `excluded`. |
| `personal_apps/features/radar/retention.py` | Prune the journal. |
| `personal_apps/features/radar/llm_sentiment.py` | Corrected cost record. |
| `personal_apps/run_radar_ingest.py` | StockTwits removed; prefixed reddit sources. |
| `personal_apps/routes/api.py` (radar) | Accept prefixed source names; serialize disagreement. |
| `personal_apps/static/radar/src/types.ts`, `detail/Breakdown.tsx` | Render the disagreement. |
| `personal_apps/scripts/discover_reddit_sources.py` | Refuse to run beside the daemon. |
| 8 radar test files | Move off `'stocktwits'` as their default source. |

---

# Stage 1 — Stop the data loss

## Task 1: The mention journal table

**Files:**
- Modify: `personal_apps/models.py` (append after `RadarLlmSpend`, ~line 833)
- Create: `personal_apps/migrations/versions/<rev>_add_radar_mention_events.py`
- Modify: `personal_apps/features/radar/config.py`
- Create: `personal_apps/tests/test_radar_journal.py`

**Interfaces:**
- Consumes: nothing.
- Produces: `models.RadarMentionEvent` with columns `id, source, external_id, ticker, created_utc, bucket_start, author, simhash, confidence, sentiment, engagement`; `config.MENTION_EVENT_RETENTION_HOURS = 48`.

This table is the record `roll_up` currently lacks. `radar_posts` cannot serve — a post whose tickers were all `low` is never stored, so promotion inputs are absent from it.

- [ ] **Step 1: Write the failing test**

Create `personal_apps/tests/test_radar_journal.py`:

```python
# personal_apps/tests/test_radar_journal.py
"""The journal is what makes a bucket rebuildable.

roll_up used to recompute a bucket from one cycle's in-memory mentions and
overwrite the result. Every source advances a cursor, so each cycle carries
only a slice, and a bucket touched by several cycles kept the last slice.
Measured in production 2026-08-26: 43% of the 10+ mention buckets lost.
"""
import datetime as dt

import pytest

from app import app as flask_app
from extensions import db
from models import RadarMentionEvent


@pytest.fixture()
def clean_events():
    with flask_app.app_context():
        RadarMentionEvent.query.filter(
            RadarMentionEvent.ticker.like('ZZ%')).delete(synchronize_session=False)
        db.session.commit()
        yield
        RadarMentionEvent.query.filter(
            RadarMentionEvent.ticker.like('ZZ%')).delete(synchronize_session=False)
        db.session.commit()


def test_the_table_accepts_one_event(clean_events):
    db.session.add(RadarMentionEvent(
        source='bluesky', external_id='zz-1', ticker='ZZA',
        created_utc=dt.datetime(2026, 4, 15, 14, 3, 0),
        bucket_start=dt.datetime(2026, 4, 15, 14, 0, 0),
        author='u1', simhash=111, confidence='high',
        sentiment=0.5, engagement=10.0))
    db.session.commit()

    row = RadarMentionEvent.query.filter_by(ticker='ZZA').one()
    assert row.confidence == 'high'
    assert row.bucket_start == dt.datetime(2026, 4, 15, 14, 0, 0)


def test_the_same_mention_cannot_be_stored_twice(clean_events):
    """(source, external_id, ticker) is the identity of a mention.

    A post returned by two overlapping cycles is one mention, not two, and the
    unique key is what stops a rebuild from double-counting it.
    """
    import sqlalchemy as sa

    for _ in range(2):
        db.session.add(RadarMentionEvent(
            source='bluesky', external_id='zz-dup', ticker='ZZB',
            created_utc=dt.datetime(2026, 4, 15, 14, 3, 0),
            bucket_start=dt.datetime(2026, 4, 15, 14, 0, 0),
            author='u1', simhash=222, confidence='high',
            sentiment=None, engagement=0.0))
    with pytest.raises(sa.exc.IntegrityError):
        db.session.commit()
    db.session.rollback()
```

- [ ] **Step 2: Run it to verify it fails**

Run from `personal_apps/`:

```bash
python -m pytest tests/test_radar_journal.py -v
```

Expected: collection error, `ImportError: cannot import name 'RadarMentionEvent' from 'models'`.

- [ ] **Step 3: Add the model**

Append to `personal_apps/models.py`, after `RadarLlmSpend`:

```python
class RadarMentionEvent(db.Model):
    """Every extracted mention, kept just long enough to rebuild its bucket.

    roll_up recomputes a bucket from scratch on every pass. That is right --
    cycles overlap and additive rollup would double-count the boundary -- but
    it can only be right if the recompute sees the WHOLE quarter-hour. Cycles
    advance a cursor, so what one cycle holds in memory is a slice, and
    rebuilding from that slice erased the earlier ones. Measured in production
    2026-08-26: 4.4% lost on singleton buckets, 42.9% on the 10+ buckets the
    board exists to rank.

    radar_posts cannot serve as this record. A post whose tickers were all
    `low` is never stored -- Bluesky alone would be 100 million rows a month --
    so the promotion inputs are simply absent from it.

    NOT partitioned, unlike radar_buckets: retention here is 48 hours with
    chunked deletes, so there is no month-sized range to drop.
    """
    __tablename__ = 'radar_mention_events'
    __table_args__ = (
        # The identity of a mention. A post returned by two overlapping cycles
        # is one mention, and this is what makes the rebuild idempotent.
        db.UniqueConstraint('source', 'external_id', 'ticker',
                            name='uq_radar_mention_event'),
        # How roll_up reads it back: every event in one ticker's quarter-hour.
        db.Index('ix_radar_mention_events_bucket', 'ticker', 'bucket_start'),
        # How retention finds what to drop.
        db.Index('ix_radar_mention_events_created', 'created_utc'),
        {'mysql_charset': 'utf8mb4'},
    )

    id           = db.Column(db.BigInteger, primary_key=True, autoincrement=True)
    # 48, not 24: a Reddit source name carries its subreddit
    # (`reddit:smallstreetbets`), and the width is not worth defending.
    source       = db.Column(db.String(48), nullable=False)
    external_id  = db.Column(db.String(128), nullable=False)
    ticker       = db.Column(db.String(12, collation='utf8mb4_bin'), nullable=False)
    created_utc  = db.Column(MYSQL_DATETIME(fsp=6), nullable=False)
    # Denormalised so the rebuild is one indexed read rather than a scan with
    # date arithmetic in the predicate.
    bucket_start = db.Column(MYSQL_DATETIME(fsp=6), nullable=False)
    author       = db.Column(db.String(64), nullable=True)
    simhash      = db.Column(MYSQL_BIGINT(unsigned=True), nullable=False, default=0)
    # PRE-promotion. `medium` is awarded at rollup from the complete bucket and
    # is never stored here, because storing it would freeze a decision that the
    # next cycle's arrivals can legitimately change.
    confidence   = db.Column(
        db.Enum('high', 'low', name='radar_event_confidence'), nullable=False)
    sentiment    = db.Column(db.Float, nullable=True)
    engagement   = db.Column(db.Float, nullable=False, default=0.0)
```

- [ ] **Step 4: Add the retention constant**

In `personal_apps/features/radar/config.py`, immediately after `POST_RETENTION_DAYS`:

```python
# How long the mention journal is kept. Buckets are the durable artifact; the
# journal exists only so a bucket can be rebuilt while cycles are still
# arriving in it. Two days is generous against a catch-up after an outage --
# what it must outlast is the deepest cursor rewind, not the retention of
# anything the board reads.
MENTION_EVENT_RETENTION_HOURS = 48
```

- [ ] **Step 5: Generate and edit the migration**

Run from `personal_apps/`:

```bash
python -m flask db revision -m "add radar mention events"
```

Edit the generated file so `down_revision = 'a53d0b0fcc37'` and:

```python
def upgrade():
    op.create_table(
        'radar_mention_events',
        sa.Column('id', sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column('source', sa.String(length=48), nullable=False),
        sa.Column('external_id', sa.String(length=128), nullable=False),
        sa.Column('ticker', sa.String(length=12, collation='utf8mb4_bin'),
                  nullable=False),
        sa.Column('created_utc', mysql.DATETIME(fsp=6), nullable=False),
        sa.Column('bucket_start', mysql.DATETIME(fsp=6), nullable=False),
        sa.Column('author', sa.String(length=64), nullable=True),
        sa.Column('simhash', mysql.BIGINT(unsigned=True), nullable=False),
        sa.Column('confidence', sa.Enum('high', 'low',
                                        name='radar_event_confidence'),
                  nullable=False),
        sa.Column('sentiment', sa.Float(), nullable=True),
        sa.Column('engagement', sa.Float(), nullable=False),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('source', 'external_id', 'ticker',
                            name='uq_radar_mention_event'),
        mysql_charset='utf8mb4',
    )
    op.create_index('ix_radar_mention_events_bucket', 'radar_mention_events',
                    ['ticker', 'bucket_start'])
    op.create_index('ix_radar_mention_events_created', 'radar_mention_events',
                    ['created_utc'])


def downgrade():
    op.drop_index('ix_radar_mention_events_created',
                  table_name='radar_mention_events')
    op.drop_index('ix_radar_mention_events_bucket',
                  table_name='radar_mention_events')
    op.drop_table('radar_mention_events')
```

- [ ] **Step 6: Apply it locally and run the test**

```bash
python -m flask db upgrade && python -m pytest tests/test_radar_journal.py -v
```

Expected: `2 passed`.

- [ ] **Step 7: Commit**

```bash
git add personal_apps/models.py personal_apps/features/radar/config.py personal_apps/migrations/versions personal_apps/tests/test_radar_journal.py
git commit -m "feat(radar): a journal of every extracted mention"
```

---

## Task 2: `roll_up` rebuilds a bucket from the journal

**Files:**
- Create: `personal_apps/features/radar/journal.py`
- Modify: `personal_apps/features/radar/buckets.py`
- Modify: `personal_apps/features/radar/ingest.py:160-186`
- Modify: `personal_apps/tests/test_radar_buckets.py:35-45,108-115`
- Modify: `personal_apps/tests/test_radar_journal.py`

**Interfaces:**
- Consumes: `models.RadarMentionEvent` (Task 1).
- Produces: `journal.record(rows)` -> `None`; `journal.events_for(keys)` -> `list[buckets.MentionRow]`, where `keys` is an iterable of `(ticker, bucket_start)`. `buckets.MentionRow` gains a required field `external_id: str` in position 2, immediately after `ticker`.

This is the audit's largest finding. Do not fold anything else into it.

- [ ] **Step 1: Write the failing test**

Append to `personal_apps/tests/test_radar_journal.py`:

```python
def test_a_second_poll_inside_one_bucket_does_not_erase_the_first(clean_buckets,
                                                                  clean_events):
    """The production shape, which the old regression test never modelled.

    tests/test_radar_buckets.py fed its second roll_up call a SUPERSET of the
    first, modelling a full re-read of the window. No source does that: every
    one advances a cursor, so cycle N+1 carries a DISJOINT tail. The assertion
    encoded the assumption instead of testing it, and passed for months while
    production lost 43% of its busiest buckets.
    """
    from features.radar import buckets
    from models import RadarBucket

    start = {dt.datetime(2026, 4, 15, 14, 0, 0)}
    buckets.roll_up([_row(external_id='zz-a', author='u1', simhash=1, minute=1)],
                    _ALL_OK, start)
    buckets.roll_up([_row(external_id='zz-b', author='u2', simhash=2, minute=4)],
                    _ALL_OK, start)

    bucket = RadarBucket.query.filter_by(ticker='ZZA').one()
    assert bucket.mention_count == 2
    assert bucket.distinct_authors == 2


def test_the_same_post_arriving_twice_is_counted_once(clean_buckets, clean_events):
    """Cycles overlap by design; the unique key is what absorbs that."""
    from features.radar import buckets
    from models import RadarBucket

    start = {dt.datetime(2026, 4, 15, 14, 0, 0)}
    buckets.roll_up([_row(external_id='zz-a', author='u1', simhash=1)],
                    _ALL_OK, start)
    buckets.roll_up([_row(external_id='zz-a', author='u1', simhash=1)],
                    _ALL_OK, start)

    assert RadarBucket.query.filter_by(ticker='ZZA').one().mention_count == 1


def test_a_cashtag_vouches_across_cycle_boundaries(clean_buckets, clean_events):
    """Promotion is a property of the QUARTER-HOUR, not of one cycle's slice.

    _promote's own docstring says the window is the bucket. It could not be,
    while the only rows it saw were the ones this cycle happened to fetch.
    """
    from features.radar import buckets
    from models import RadarBucket

    start = {dt.datetime(2026, 4, 15, 14, 0, 0)}
    buckets.roll_up([_row(external_id='zz-low', author='u1', simhash=1,
                          confidence='low', minute=1)], _ALL_OK, start)
    buckets.roll_up([_row(external_id='zz-high', author='u2', simhash=2,
                          confidence='high', minute=9)], _ALL_OK, start)

    bucket = RadarBucket.query.filter_by(ticker='ZZA').one()
    # The low was promoted to medium by the later cycle's cashtag.
    assert bucket.mention_count == 2
    assert bucket.high_confidence_count == 1
    assert bucket.low_count == 0
```

Add at the top of the same file, after the `clean_events` fixture:

```python
@pytest.fixture()
def clean_buckets():
    from models import RadarBucket, RadarBucketSource
    with flask_app.app_context():
        for model in (RadarBucketSource, RadarBucket):
            model.query.filter(model.ticker.like('ZZ%')).delete(
                synchronize_session=False)
        db.session.commit()
        yield
        for model in (RadarBucketSource, RadarBucket):
            model.query.filter(model.ticker.like('ZZ%')).delete(
                synchronize_session=False)
        db.session.commit()


_ALL_OK = {'bluesky': 'ok'}


def _row(external_id, ticker='ZZA', minute=3, source='bluesky', author='u1',
         simhash=111, confidence='high', sentiment=0.5, engagement=10.0):
    from features.radar import buckets
    return buckets.MentionRow(
        ticker=ticker, external_id=external_id,
        created_utc=dt.datetime(2026, 4, 15, 14, minute, 0),
        source=source, author=author, simhash=simhash,
        confidence=confidence, sentiment=sentiment, engagement=engagement)
```

- [ ] **Step 2: Run it to verify it fails**

```bash
python -m pytest tests/test_radar_journal.py -v -k "second_poll or arriving_twice or vouches"
```

Expected: three failures, each `TypeError: MentionRow.__init__() got an unexpected keyword argument 'external_id'`.

- [ ] **Step 3: Add `external_id` to `MentionRow`**

In `personal_apps/features/radar/buckets.py`, in the dataclass:

```python
@dataclasses.dataclass
class MentionRow:
    """One extracted mention, flattened for rollup."""
    ticker: str
    # The mention's identity in the journal, with source. Without it a rebuild
    # cannot tell one author's second post apart from the same post arriving in
    # a second cycle, and overlapping cycles would double-count the boundary.
    external_id: str
    created_utc: dt.datetime
    source: str
    author: str | None
    simhash: int
    confidence: str
    sentiment: float | None
    engagement: float
```

- [ ] **Step 4: Write the journal module**

Create `personal_apps/features/radar/journal.py`:

```python
# personal_apps/features/radar/journal.py
"""Read and write radar_mention_events. The only module that knows it exists.

The journal answers one question for roll_up: what is EVERYTHING that landed in
this ticker's quarter-hour, regardless of which cycle carried it. Nothing else
in the pipeline reads it, and nothing reads it after retention drops the row --
the bucket is the durable artifact.
"""
import collections

import sqlalchemy as sa
from sqlalchemy.dialects.mysql import insert as mysql_insert

from extensions import db
from models import RadarMentionEvent

from .buckets import MentionRow, bucket_start_for

# Rows per INSERT. Large enough that a busy Bluesky cycle is a handful of
# statements, small enough to stay well inside max_allowed_packet.
_CHUNK = 500


def record(rows):
    """Store this cycle's mentions. Idempotent on (source, external_id, ticker).

    Only `engagement` is updated on a duplicate. Everything else was decided at
    first sight and must stay decided: re-deciding confidence on a later cycle
    would let a config change rewrite a bucket that was already counted, which
    is the hazard ingest's docstring has always warned about. Engagement is the
    exception because it genuinely grows after first sight.
    """
    if not rows:
        return

    payload = [{
        'source': row.source,
        'external_id': row.external_id,
        'ticker': row.ticker,
        'created_utc': row.created_utc,
        'bucket_start': bucket_start_for(row.created_utc),
        'author': row.author,
        'simhash': row.simhash,
        'confidence': row.confidence,
        'sentiment': row.sentiment,
        'engagement': row.engagement,
    } for row in rows]

    for start in range(0, len(payload), _CHUNK):
        statement = mysql_insert(RadarMentionEvent).values(payload[start:start + _CHUNK])
        db.session.execute(statement.on_duplicate_key_update(
            engagement=statement.inserted.engagement))
    db.session.commit()


def events_for(keys):
    """Every stored event in these (ticker, bucket_start) windows.

    Queried per bucket_start rather than per pair, because one cycle touches a
    handful of quarter-hours and hundreds of tickers -- an IN over the tickers
    inside each window uses the (ticker, bucket_start) index and takes one
    round trip per window instead of one per pair.
    """
    keys = list(keys)
    if not keys:
        return []

    by_window = collections.defaultdict(set)
    for ticker, start in keys:
        by_window[start].add(ticker)

    clauses = [sa.and_(RadarMentionEvent.bucket_start == start,
                       RadarMentionEvent.ticker.in_(list(tickers)))
               for start, tickers in by_window.items()]

    rows = RadarMentionEvent.query.filter(sa.or_(*clauses)).all()
    return [MentionRow(ticker=row.ticker, external_id=row.external_id,
                       created_utc=row.created_utc, source=row.source,
                       author=row.author, simhash=row.simhash,
                       confidence=row.confidence, sentiment=row.sentiment,
                       engagement=row.engagement)
            for row in rows]
```

- [ ] **Step 5: Rewrite `roll_up` to record and reload**

In `personal_apps/features/radar/buckets.py`, replace the body of `roll_up` from `usable = [...]` down to the line before `written = 0`:

```python
    usable = [r for r in rows if r.source in countable]

    # Store first, then rebuild from EVERYTHING in these windows -- not from
    # `usable`, which is one cycle's cursor slice. A bucket is recomputed from
    # scratch on every pass, which is right because cycles overlap and additive
    # rollup would double-count the boundary; it is only correct if the
    # recompute sees the whole quarter-hour. It did not, and production lost
    # 42.9% of its 10+ mention buckets to that (audit 2026-08-26).
    journal.record(usable)

    windows = {(r.ticker, bucket_start_for(r.created_utc)) for r in usable
               if bucket_start_for(r.created_utc) in touched}
    complete = journal.events_for(windows)

    grouped = collections.defaultdict(list)
    for row in _promote(complete):
        key = (row.ticker, bucket_start_for(row.created_utc))
        # A window the journal answered for that this cycle did not touch --
        # possible when two tickers share a bucket_start -- is not this cycle's
        # to rewrite.
        if key in windows:
            grouped[key].append(row)
```

Then delete the now-redundant guard inside the write loop:

```python
    for (ticker, start), bucket_rows in grouped.items():
        totals = _summarize(bucket_rows)
```

(that is, remove the `if start not in touched: continue` lines — `windows` already applied it.)

Add the import at the top of `buckets.py`, below the existing `from .config import ...`:

```python
from . import journal
```

**Note on the import cycle:** `journal` imports `MentionRow` and `bucket_start_for` from `buckets`, and `buckets` imports `journal`. Python resolves this because `buckets` imports the module object, not a name from it, and only calls into it at runtime. Keep it that way — `from .journal import record` at the top of `buckets.py` would fail.

- [ ] **Step 6: Give ingest's `MentionRow` constructions an `external_id`**

In `personal_apps/features/radar/ingest.py`, both `buckets.MentionRow(` calls take `external_id=raw.external_id` as the second argument:

```python
            mention_rows.append(buckets.MentionRow(
                ticker=symbol, external_id=raw.external_id,
                created_utc=raw.created_utc, source=raw.source,
                author=raw.author, simhash=fingerprint.simhash64(
                    '%s %s' % (raw.title or '', raw.body)),
                confidence=confidence, sentiment=score,
                engagement=float(raw.score + raw.num_comments)))
```

and

```python
            mention_rows.append(buckets.MentionRow(
                ticker=symbol, external_id=raw.external_id,
                created_utc=raw.created_utc, source=raw.source,
                author=raw.author, simhash=row.simhash, confidence=confidence,
                sentiment=score,
                engagement=float(raw.score + raw.num_comments)))
```

- [ ] **Step 7: Fix the misleading regression test**

In `personal_apps/tests/test_radar_buckets.py`, give the `row()` helper an
`external_id` and make the superset test say what it actually covers:

```python
def row(ticker='ZZA', minute=3, source='bluesky', author='u1', simhash=111,
        confidence='high', sentiment=0.5, engagement=10.0, external_id=None):
    return buckets.MentionRow(
        ticker=ticker,
        external_id=external_id or ('zz-%s-%s-%s' % (ticker, author, minute)),
        created_utc=dt.datetime(2026, 4, 15, 14, minute, 0),
        source=source, author=author, simhash=simhash,
        confidence=confidence, sentiment=sentiment, engagement=engagement)


ALL_OK = {'bluesky': 'ok'}
```

and replace `test_rerunning_a_cycle_replaces_rather_than_doubles`:

```python
def test_a_re_read_of_the_same_window_does_not_double(clean_buckets):
    """A cycle that re-reads a window it already read must not add to it.

    This is the overlap case, and it is the only one the old version of this
    test covered -- it fed the second call a SUPERSET, which no source
    produces. The disjoint case, which every source produces, lives in
    tests/test_radar_journal.py and used to fail.
    """
    start = {dt.datetime(2026, 4, 15, 14, 0, 0)}
    buckets.roll_up([row(author='u1', simhash=1)], ALL_OK, start)
    buckets.roll_up([row(author='u1', simhash=1), row(author='u2', simhash=2)],
                    ALL_OK, start)
    bucket = RadarBucket.query.filter_by(ticker='ZZA').one()
    assert bucket.mention_count == 2
```

Add the journal to that file's `clean_buckets` fixture teardown so tests do not leak into each other:

```python
        RadarMentionEvent.query.filter(
            RadarMentionEvent.ticker.like('ZZ%')).delete(synchronize_session=False)
```

(both before the `yield` and after it, alongside the existing deletes; import `RadarMentionEvent` from `models` at the top.)

- [ ] **Step 8: Run the radar bucket, journal and ingest suites**

```bash
python -m pytest tests/test_radar_journal.py tests/test_radar_buckets.py tests/test_radar_ingest.py tests/test_radar_bucket_sources.py -v
```

Expected: all pass. If `test_a_cashtag_vouches_across_cycle_boundaries` fails on `low_count`, `_promote` is still being handed `usable` rather than `complete` — recheck Step 5.

- [ ] **Step 9: Commit**

```bash
git add personal_apps/features/radar/journal.py personal_apps/features/radar/buckets.py personal_apps/features/radar/ingest.py personal_apps/tests/test_radar_journal.py personal_apps/tests/test_radar_buckets.py
git commit -m "fix(radar): rebuild a bucket from the whole quarter-hour, not one cycle"
```

---

## Task 3: A status rewrite clears the scoring columns

**Files:**
- Modify: `personal_apps/features/radar/buckets.py` (the per-source write loop)
- Modify: `personal_apps/tests/test_radar_bucket_sources.py`

**Interfaces:**
- Consumes: `roll_up` from Task 2.
- Produces: no new names. Behaviour: a `RadarBucketSource` row written with `status != 'ok'` has `expected`, `variance`, `mention_z`, `baseline_days` set to `None`.

In production 399 rows are marked `truncated` and still carry a `mention_z` written while they were `ok`. `leaderboard.build_rows` filters on `mention_z.isnot(None)`, so those rows are ranked on a score `scoring.score_source` would now refuse to produce.

- [ ] **Step 1: Write the failing test**

Append to `personal_apps/tests/test_radar_bucket_sources.py`:

```python
def test_a_downgrade_to_truncated_clears_the_stale_score(clean_buckets):
    """Scoring refuses a row that is not `ok`. Rewriting the status must not
    leave behind a z that the scorer would no longer produce.

    Found in production 2026-08-26: 399 rows marked truncated and still ranked
    on a mention_z from when they were ok.
    """
    import datetime as dt

    from extensions import db
    from features.radar import buckets
    from models import RadarBucketSource

    start = {dt.datetime(2026, 4, 15, 14, 0, 0)}
    buckets.roll_up([row(external_id='zz-1')], {'bluesky': 'ok'}, start)

    scored = RadarBucketSource.query.filter_by(
        ticker='ZZA', source='bluesky').one()
    scored.mention_z = 4.2
    scored.expected = 1.0
    scored.variance = 2.0
    scored.baseline_days = 9
    db.session.commit()

    buckets.roll_up([row(external_id='zz-2', author='u2', simhash=2)],
                    {'bluesky': 'truncated'}, start)

    after = RadarBucketSource.query.filter_by(
        ticker='ZZA', source='bluesky').one()
    assert after.status == 'truncated'
    assert after.mention_z is None
    assert after.expected is None
    assert after.variance is None
    assert after.baseline_days is None
```

If `test_radar_bucket_sources.py` has no local `row()` / `clean_buckets`, import them: `from test_radar_buckets import row, clean_buckets  # noqa: F401` — `tests/` is on `sys.path` and is not a package, which is the convention `conftest._admin_id` already documents.

- [ ] **Step 2: Run it to verify it fails**

```bash
python -m pytest tests/test_radar_bucket_sources.py::test_a_downgrade_to_truncated_clears_the_stale_score -v
```

Expected: `AssertionError: assert 4.2 is None`.

- [ ] **Step 3: Clear the columns**

In `personal_apps/features/radar/buckets.py`, inside `roll_up`'s per-source loop, after `child.status = statuses[source]`:

```python
            child.status = statuses[source]
            # scoring.score_source refuses any row that is not `ok`, so a row
            # leaving `ok` must lose the score it was given while it was one.
            # It kept it, and leaderboard ranks on mention_z IS NOT NULL --
            # 399 rows in production were being ranked on a z the scorer would
            # no longer compute for them (audit 2026-08-26).
            if child.status != 'ok':
                child.expected = None
                child.variance = None
                child.mention_z = None
                child.baseline_days = None
            child.source_config_version = version
```

- [ ] **Step 4: Run it to verify it passes**

```bash
python -m pytest tests/test_radar_bucket_sources.py tests/test_radar_buckets.py tests/test_radar_journal.py -v
```

Expected: all pass.

- [ ] **Step 5: Commit**

```bash
git add personal_apps/features/radar/buckets.py personal_apps/tests/test_radar_bucket_sources.py
git commit -m "fix(radar): a bucket leaving ok loses the score it earned as ok"
```

---

## Task 3b: The author count sees promoted mentions

**Files:**
- Modify: `personal_apps/models.py` (`RadarMentionEvent.promoted`)
- Create: `personal_apps/migrations/versions/<rev>_add_mention_event_promoted.py`
- Modify: `personal_apps/features/radar/journal.py`, `buckets.py`
- Modify: `personal_apps/features/radar/leaderboard.py:76-112`
- Modify: `personal_apps/tests/test_radar_leaderboard.py`

**Interfaces:**
- Consumes: `journal` (Task 2).
- Produces: `RadarMentionEvent.promoted` (Boolean, default False); `journal.mark_promoted(rows)` -> `None`; `journal.distinct_voices(tickers, sources, since, now, field)` -> `dict[str, int]` where `field` is `'author'` or `'channel'`.

`_promote` awards `medium` in memory and `RadarMention.confidence` holds only `high` and `low` — production has **zero** `medium` rows. Yet `leaderboard._distinct_authors`, `_distinct_channels` and `detail_panel._breakdown` all filter `confidence.in_(('high','medium'))`, so they see the `high` rows only while `bucket.mention_count` includes the promoted ones. Worse, a post whose tickers were *all* low is never stored, so its promoted mention has no `radar_mentions` row at all. The eligibility floor reads a smaller author count than the mention count it gates.

The journal now holds those mentions. Recording what `_promote` decided makes the count exact.

- [ ] **Step 1: Write the failing test**

Append to `personal_apps/tests/test_radar_leaderboard.py`:

```python
def test_a_promoted_mention_counts_towards_the_author_floor(clean_buckets,
                                                            clean_events):
    """The floor gated on a count that could not see half the mentions.

    `medium` is awarded at rollup and never written to radar_mentions -- zero
    such rows exist in production -- and a post whose tickers were all `low` is
    never stored at all. So bucket.mention_count counted the promoted mentions
    and the author query could not, and the eligibility floor judged a ticker
    on the smaller number (audit 2026-08-26).
    """
    import datetime as dt

    from features.radar import buckets, journal

    start = {dt.datetime(2026, 4, 15, 14, 0, 0)}
    buckets.roll_up([
        _row(external_id='zz-h', author='u1', simhash=1, confidence='high'),
        _row(external_id='zz-l', author='u2', simhash=2, confidence='low',
             minute=7),
    ], _ALL_OK, start)

    voices = journal.distinct_voices(
        ['ZZA'], ['bluesky'], dt.datetime(2026, 4, 15, 13, 0, 0),
        dt.datetime(2026, 4, 15, 15, 0, 0), 'author')
    # u2's bare mention was vouched for by u1's cashtag, so it is scored --
    # and its author is one of the ticker's independent voices.
    assert voices['ZZA'] == 2
```

Import `_row`, `_ALL_OK`, `clean_buckets` and `clean_events` from `test_radar_journal` at the top of the file: `from test_radar_journal import _row, _ALL_OK, clean_buckets, clean_events  # noqa: F401`.

- [ ] **Step 2: Run it to verify it fails**

```bash
python -m pytest tests/test_radar_leaderboard.py::test_a_promoted_mention_counts_towards_the_author_floor -v
```

Expected: `AttributeError: module 'features.radar.journal' has no attribute 'distinct_voices'`.

- [ ] **Step 3: Record what promotion decided**

Add to `RadarMentionEvent` in `personal_apps/models.py`:

```python
    # What _promote decided, written back after the rollup ran over the whole
    # bucket. `confidence` above is what the EXTRACTOR said, and stays that
    # way -- promotion is a property of the quarter-hour and legitimately
    # changes as more of it arrives, so the two facts are stored apart.
    promoted     = db.Column(db.Boolean, nullable=False, default=False)
```

Migration, chained after Task 1's:

```python
def upgrade():
    op.add_column('radar_mention_events',
                  sa.Column('promoted', sa.Boolean(), nullable=False,
                            server_default=sa.text('0')))


def downgrade():
    op.drop_column('radar_mention_events', 'promoted')
```

- [ ] **Step 4: Write it back, and read it**

In `personal_apps/features/radar/journal.py`:

```python
def mark_promoted(rows):
    """Record which bare mentions the rollup promoted.

    Called after _promote has seen the whole bucket, so what is stored is the
    decision rather than an intermediate. Idempotent: a later cycle recomputes
    the same bucket and writes the same answer, or a better-informed one.
    """
    promoted = [(row.source, row.external_id, row.ticker) for row in rows
                if row.confidence == 'medium']
    if not promoted:
        return
    for start in range(0, len(promoted), _CHUNK):
        clauses = [sa.and_(RadarMentionEvent.source == source,
                           RadarMentionEvent.external_id == external_id,
                           RadarMentionEvent.ticker == ticker)
                   for source, external_id, ticker in promoted[start:start + _CHUNK]]
        (RadarMentionEvent.query.filter(sa.or_(*clauses))
         .update({'promoted': True}, synchronize_session=False))
    db.session.commit()


def distinct_voices(tickers, sources, since, now, field):
    """Distinct authors or channels per ticker over the SCORED mentions.

    `field` is 'author' or 'channel'. Counted here rather than from
    radar_mentions because that table never holds `medium` -- promotion happens
    at rollup and is written back onto the journal, not onto the mention -- and
    because a post whose tickers were all `low` has no mention row at all.

    Buckets store distinct_authors as a COUNT, so aggregating them can only
    take a maximum, and a maximum systematically undercounts: two buckets
    holding {x, y} and {z, w} have four distinct voices and report two.
    Measured on live data, NVDA showed 26 real authors against a bucket
    maximum of 2.
    """
    if not tickers:
        return {}

    column = {'author': RadarMentionEvent.author,
              'channel': RadarMentionEvent.source}[field]
    rows = (db.session.query(RadarMentionEvent.ticker,
                             sa.func.count(sa.distinct(column)))
            .filter(RadarMentionEvent.ticker.in_(list(tickers)),
                    RadarMentionEvent.source.in_(list(sources)),
                    RadarMentionEvent.created_utc >= since,
                    RadarMentionEvent.created_utc < now,
                    sa.or_(RadarMentionEvent.confidence == 'high',
                           RadarMentionEvent.promoted.is_(True)))
            .group_by(RadarMentionEvent.ticker).all())
    # int() at the boundary: COUNT is Decimal on MySQL and MariaDB alike.
    return {ticker: int(count) for ticker, count in rows}
```

`'channel'` maps to `source` deliberately: since Task 9 the source name carries the subreddit, so a broadcast venue's channel *is* its source name. Note that in the docstring when Task 9 lands.

In `personal_apps/features/radar/buckets.py`, `roll_up`, after the promotion loop:

```python
    promoted_rows = _promote(complete)
    journal.mark_promoted(promoted_rows)

    grouped = collections.defaultdict(list)
    for row in promoted_rows:
        ...
```

- [ ] **Step 5: Point the leaderboard at it**

In `personal_apps/features/radar/leaderboard.py`, replace the bodies of `_distinct_authors` and `_distinct_channels` with calls, keeping their docstrings and adding the reason:

```python
def _distinct_authors(tickers, sources, since, now):
    """True distinct authors per ticker across the whole window.

    Read from the mention journal rather than from radar_mentions. That table
    never holds `medium` -- promotion is decided at rollup over the whole
    bucket and written back onto the journal -- and a post whose tickers were
    all `low` is never stored there at all, so the count it gave was smaller
    than the mention count the floor was gating.

    Falls back to nothing: a ticker whose events have aged out of the journal
    is absent from the result and the caller uses the bucket maximum, which
    undercounts in the safe direction.
    """
    return journal.distinct_voices(tickers, sources, since, now, 'author')


def _distinct_channels(tickers, sources, since, now):
    """The broadcast analogue. See _distinct_authors."""
    return journal.distinct_voices(tickers, sources, since, now, 'channel')
```

Add `from . import journal` to the imports.

The journal's 48-hour retention is longer than the 24-hour maximum board window, so nothing the leaderboard asks about has aged out. The existing `author_counts.get(ticker, <bucket max>)` fallback stays as the guard.

- [ ] **Step 6: Run the suites**

```bash
python -m flask db upgrade && python -m pytest tests/ -k radar -v
```

Expected: all pass. Expect some leaderboard fixtures to newly clear the eligibility floor — that is the fix working, and any test asserting a ticker is excluded needs its fixture checked rather than its assertion relaxed.

- [ ] **Step 7: Commit**

```bash
git add -A personal_apps
git commit -m "fix(radar): the eligibility floor can finally see the mentions it counts"
```

---

## Task 4: Wire `single_letter_cashtags_allowed`

**Files:**
- Modify: `personal_apps/features/radar/ingest.py:66-84` (`_extract_for`)
- Modify: `personal_apps/tests/test_radar_ingest.py`

**Interfaces:**
- Consumes: `config.single_letter_cashtags_allowed(source)` — already exists, called by nothing.
- Produces: no new names.

`SINGLE_LETTER_CASHTAGS` is hashed into `source_config_version`, so the stamp claims it is policy. `extract_tickers` defaults `allow_single_letter=True` and `_extract_for` never overrides it. Live cost: 353 single-letter mentions, 3.0% of the entire high-confidence corpus, on a source where the config says to reject them.

**Bumps `source_config_version`** — correctly, because it changes which mentions count.

- [ ] **Step 1: Write the failing test**

Append to `personal_apps/tests/test_radar_ingest.py`:

First give the file's existing `post()` helper (`tests/test_radar_ingest.py:56`) a
`source` parameter, since every test in the file needs one after Task 7 anyway:

```python
def post(ident='t3_1', body='$ZZG is ripping', score=5, author='u1',
         minute=10, title=None, source='stocktwits'):
    return RawPost(source=source, external_id=ident, channel='testsub',
                   author=author,
                   created_utc=dt.datetime(2026, 4, 15, 14, minute, 0),
                   title=title, body=body, score=score, num_comments=0,
                   url='https://example.invalid/%s' % ident)
```

Then append the test:

```python
def test_a_single_letter_cashtag_is_refused_on_a_general_network():
    """`$M` on Bluesky is money shorthand, not Macy's.

    Measured on live Bluesky: 119 of 3302 cashtag matches were single letters
    and essentially all were prose -- "Tax @60% for over a $M", "make $B's".
    config.SINGLE_LETTER_CASHTAGS has said so since it was written; nothing
    passed it to the extractor until now, and 353 such mentions reached the
    production corpus, 3.0% of the whole high-confidence set.
    """
    from features.radar import ingest

    lookup = {'B': {'name': 'Barnes Group Inc.', 'exchange': 'NYSE',
                    'distinctive': set()}}
    general = post(ident='zz-single', body='make $B and youre set',
                   source='bluesky')
    finance = post(ident='zz-single-2', body='make $B and youre set',
                   source='stocktwits')

    assert ingest._extract_for(general, lookup) == []
    # The same text on a finance-native population still yields the company.
    assert ingest._extract_for(finance, lookup) == [('B', 'high')]
```

After Task 7 retires StockTwits the second assertion has no source to use;
that task's Step 7 replaces it with the monkeypatched extension-point test in
the same shape as the coin-collision one.

- [ ] **Step 2: Run it to verify it fails**

```bash
python -m pytest tests/test_radar_ingest.py::test_a_single_letter_cashtag_is_refused_on_a_general_network -v
```

Expected: `AssertionError: assert [('B', 'high')] == []`.

- [ ] **Step 3: Pass the flag**

In `personal_apps/features/radar/ingest.py`, change the import and the call:

```python
from .config import (
    BUCKET_MINUTES, bare_token_confidence, bare_tokens_allowed,
    coin_collision_dropped, looks_like_bot_feed,
    single_letter_cashtags_allowed)
```

```python
    tickers = extraction.extract_tickers(
        raw.title, raw.body, lookup,
        allow_bare=bare_tokens_allowed(raw.source),
        allow_single_letter=single_letter_cashtags_allowed(raw.source),
        bare_confidence=bare_token_confidence(raw.source))
```

Update `_extract_for`'s docstring — it says "Three per-source judgements"; there are four.

- [ ] **Step 4: Run it to verify it passes**

```bash
python -m pytest tests/test_radar_ingest.py tests/test_radar_extraction.py -v
```

Expected: all pass.

- [ ] **Step 5: Commit**

```bash
git add personal_apps/features/radar/ingest.py personal_apps/tests/test_radar_ingest.py
git commit -m "fix(radar): the single-letter cashtag rule was hashed but never called"
```

---

## Task 5: Delete `PAGE_CAP`, and make dead config impossible

**Files:**
- Modify: `personal_apps/features/radar/config.py`
- Create: `personal_apps/tests/test_radar_config_reachability.py`

**Interfaces:**
- Consumes: nothing.
- Produces: no new runtime names.

`PAGE_CAP` has zero references anywhere, tests included; `sources/fourchan.py` paginates under its own `THREAD_CAP`. This is the fourth member of `config` to have been dead in production — the bot filter, the profile job and the sentiment job preceded it — so the durable fix is the test, not the deletion.

- [ ] **Step 1: Write the failing test**

Create `personal_apps/tests/test_radar_config_reachability.py`:

```python
# personal_apps/tests/test_radar_config_reachability.py
"""No member of radar's config may be dead.

Four have been, in production, while being hashed into
source_config_version and therefore claiming to be policy: the bot filter
(defined 2026-08-22, called from 2026-08-25), the profile job, the sentiment
job, and single_letter_cashtags_allowed (audit 2026-08-26, 3% of the corpus).

Reachability is checked against SOURCE TEXT rather than runtime coverage,
because the failure mode is a name that is imported and never invoked -- which
coverage would report as covered.
"""
import pathlib
import re

from features.radar import config

_ROOT = pathlib.Path(__file__).resolve().parent.parent

# Where a config member may legitimately be used.
_SEARCH_DIRS = ('features/radar', 'routes', 'scripts', 'tests')
_SEARCH_FILES = ('run_radar_ingest.py',)

# Members with no call site and a reason. Every entry is a decision, not a
# waiver: if a name is here, someone chose to keep it unused.
_EXEMPT = {
    # Read only through coin_collision_dropped, which is itself reachable.
    # Kept as a map rather than collapsed to a constant because Telegram will
    # need its own entry.
    'COIN_SYMBOLS_MEAN_STOCKS',
}


def _corpus():
    texts = []
    for name in _SEARCH_DIRS:
        for path in (_ROOT / name).rglob('*.py'):
            if path.name == 'config.py' and 'features/radar' in path.as_posix():
                continue
            texts.append(path.read_text(encoding='utf-8'))
    for name in _SEARCH_FILES:
        texts.append((_ROOT / name).read_text(encoding='utf-8'))
    return '\n'.join(texts)


def _config_source():
    return pathlib.Path(config.__file__).read_text(encoding='utf-8')


def _public_members():
    return sorted(name for name in dir(config)
                  if not name.startswith('_')
                  and name not in ('dt', 'hashlib', 'json', 're'))


def test_every_config_member_is_reachable():
    corpus = _corpus()
    own = _config_source()
    dead = []
    for name in _public_members():
        if name in _EXEMPT:
            continue
        if re.search(r'\b%s\b' % re.escape(name), corpus):
            continue
        # Transitive: used by another config member, which the loop checks
        # separately. `\b` twice so a prefix does not satisfy a longer name.
        uses = len(re.findall(r'\b%s\b' % re.escape(name), own))
        if uses > 1:
            continue
        dead.append(name)

    assert not dead, (
        'config members with no call site: %s. Either wire them, delete them, '
        'or add them to _EXEMPT with a reason.' % ', '.join(dead))
```

- [ ] **Step 2: Run it to verify it fails**

```bash
python -m pytest tests/test_radar_config_reachability.py -v
```

Expected: `AssertionError: config members with no call site: PAGE_CAP`.

If other names appear, they are real findings — check each before adding it to `_EXEMPT`.

- [ ] **Step 3: Delete `PAGE_CAP`**

In `personal_apps/features/radar/config.py`, remove:

```python
# Pages to walk per channel per cycle before giving up and
# marking the affected buckets `truncated` (spec 4.3).
PAGE_CAP = 10
```

`sources/fourchan.py` already caps with `THREAD_CAP`; nothing else referenced this.

- [ ] **Step 4: Run it to verify it passes**

```bash
python -m pytest tests/test_radar_config_reachability.py -v
```

Expected: `1 passed`.

- [ ] **Step 5: Commit**

```bash
git add personal_apps/features/radar/config.py personal_apps/tests/test_radar_config_reachability.py
git commit -m "fix(radar): delete PAGE_CAP and pin that config cannot go dead again"
```

---

## Task 6: Backfill the buckets the old rollup truncated

**Files:**
- Create: `personal_apps/scripts/backfill_radar_buckets.py`

**Interfaces:**
- Consumes: `models.RadarBucketSource`, `RadarPost`, `RadarMention`.
- Produces: a one-shot script, run manually, no imports elsewhere.

The repair is partial by construction. `high` counts are exactly recoverable from `radar_posts` × `radar_mentions`; promoted `medium` mentions are not, because the events that created them were never written anywhere. The unrecoverable half is `low`-derived, and `low_count` is read by no surface.

- [ ] **Step 1: Write the script**

Create `personal_apps/scripts/backfill_radar_buckets.py`:

```python
"""Repair bucket counts the pre-2026-08-26 rollup truncated.

roll_up rebuilt each bucket from one cycle's cursor slice and overwrote, so a
quarter-hour touched by several cycles kept only the last one. Measured across
the live corpus: 14.1% of Bluesky's high-confidence mentions and 16.0% of
Reddit's never reached a bucket, rising to 42.9% on the 10+ mention buckets.

PARTIAL BY CONSTRUCTION. radar_mentions holds every mention of every STORED
post, which is exactly the `high` set. Promoted `medium` mentions came from
posts that were never stored -- the journal that would have kept them did not
exist -- so they cannot be recovered and mention_count stays understated by
that amount. low_count likewise. Neither is read by any surface.

Read-only until --apply. Run from personal_apps/:

    python -m scripts.backfill_radar_buckets            # report
    python -m scripts.backfill_radar_buckets --apply    # write
"""
import argparse
import sys

import sqlalchemy as sa

sys.path.insert(0, '.')

from app import app                                        # noqa: E402
from extensions import db                                  # noqa: E402
from models import RadarBucketSource                       # noqa: E402

# The 15-minute floor, in SQL. MariaDB and MySQL agree on this form; DATE_FORMAT
# to the hour and then add the quarter, rather than arithmetic on a UNIX
# timestamp, which loses the fractional-second precision the column carries.
_BUCKET = sa.text(
    "DATE_ADD(DATE_FORMAT(p.created_utc, '%Y-%m-%d %H:00:00'),"
    " INTERVAL FLOOR(MINUTE(p.created_utc)/15)*15 MINUTE)")

_TRUTH = sa.text("""
    SELECT p.source AS src, m.ticker AS tk,
           DATE_ADD(DATE_FORMAT(p.created_utc, '%Y-%m-%d %H:00:00'),
                    INTERVAL FLOOR(MINUTE(p.created_utc)/15)*15 MINUTE) AS bs,
           COUNT(*) AS n_high,
           COUNT(DISTINCT p.author) AS n_authors,
           COUNT(DISTINCT p.simhash) AS n_hashes,
           SUM(p.score + p.num_comments) AS engagement
      FROM radar_mentions m
      JOIN radar_posts p ON p.id = m.post_id
     WHERE m.confidence = 'high'
     GROUP BY 1, 2, 3
""")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--apply', action='store_true',
                        help='write the repaired counts')
    args = parser.parse_args()

    with app.app_context():
        rows = db.session.execute(_TRUTH).all()
        repaired = examined = 0

        for src, tk, bs, n_high, n_authors, n_hashes, engagement in rows:
            bucket = RadarBucketSource.query.filter_by(
                ticker=tk, bucket_start=bs, source=src).one_or_none()
            if bucket is None:
                continue
            examined += 1
            # int() at the boundary: COUNT and SUM come back Decimal from both
            # MySQL and MariaDB, and Decimal against a float column is a
            # TypeError waiting for the first row that needs it.
            n_high = int(n_high)
            if bucket.high_confidence_count >= n_high:
                continue

            bucket.high_confidence_count = n_high
            # mention_count stays >= high: the promoted mediums it also counted
            # are unrecoverable, so take whichever is larger rather than
            # overwriting a real figure with an incomplete one.
            bucket.mention_count = max(int(bucket.mention_count), n_high)
            bucket.distinct_authors = max(int(bucket.distinct_authors),
                                          int(n_authors))
            bucket.distinct_text_ratio = min(
                float(bucket.distinct_text_ratio),
                (int(n_hashes) / n_high) if n_high else 1.0)
            bucket.engagement_weighted_count = max(
                float(bucket.engagement_weighted_count), float(engagement or 0))
            repaired += 1

        print('examined %d bucket rows, %d understated' % (examined, repaired))
        if args.apply:
            db.session.commit()
            print('written')
        else:
            db.session.rollback()
            print('dry run -- nothing written, pass --apply')


if __name__ == '__main__':
    main()
```

- [ ] **Step 2: Dry-run it locally**

```bash
python -m scripts.backfill_radar_buckets
```

Expected: a line of the form `examined N bucket rows, M understated`, then `dry run -- nothing written`. On a local dev database with no radar data, `examined 0`.

- [ ] **Step 3: Commit**

```bash
git add personal_apps/scripts/backfill_radar_buckets.py
git commit -m "feat(radar): a one-shot repair for buckets the old rollup truncated"
```

The production run happens after deploy, against the live database, and is Michi's call to trigger.

---

# Stage 2 — Sources that misrepresent themselves

## Task 7: Retire StockTwits

**Files:**
- Delete: `personal_apps/features/radar/sources/stocktwits.py`, `personal_apps/tests/test_radar_stocktwits.py`
- Modify: `personal_apps/features/radar/config.py`
- Modify: `personal_apps/run_radar_ingest.py`
- Modify: `personal_apps/features/radar/scheduling.py` (docstrings only)
- Modify: `personal_apps/tests/test_radar_buckets.py`, `test_radar_bucket_sources.py`, `test_radar_config.py`, `test_radar_daemon.py`, `test_radar_ingest.py`, `test_radar_profile.py`, `test_radar_scoring.py`

**Interfaces:**
- Consumes: nothing.
- Produces: `config.SOURCES == ('bluesky', 'fourchan', 'reddit')`.

Diagnosed 2026-08-26: `cf-mitigated: challenge`, `server: cloudflare`, `<title>Just a moment...</title>` — every endpoint, every user agent including none, identical from the VPS and from a home connection. StockTwits placed its whole API behind bot management. Reaching it means defeating a bot challenge, which is out of scope on principle. Zero posts, zero poll rows, no cursor, in five days of production.

**Bumps `source_config_version`.**

- [ ] **Step 1: Write the failing test**

Append to `personal_apps/tests/test_radar_config.py`:

```python
def test_stocktwits_is_retired():
    """Cloudflare bot management, diagnosed 2026-08-26.

    403 on every endpoint with every user agent, from two networks. It reported
    `missing` honestly for five days and produced nothing, while remaining a
    selectable venue in the UI -- an invitation to filter on a source that has
    never returned a row.
    """
    from features.radar import config

    assert 'stocktwits' not in config.SOURCES
    assert 'stocktwits' not in config.BARE_TOKENS_ALLOWED
    assert 'stocktwits' not in config.SINGLE_LETTER_CASHTAGS
    assert 'stocktwits' not in config.SOURCE_KIND
    assert not hasattr(config, 'STOCKTWITS_REQUESTS_PER_HOUR')


def test_no_source_reads_a_coin_symbol_as_a_company():
    """A consequence of the retirement, named so it is not rediscovered.

    StockTwits was the only population where $LINK meant Interlink rather than
    Chainlink. With it gone, COIN_COLLISION_SYMBOLS are dropped everywhere --
    49 real tickers lose their mentions on every live source. The map stays a
    map rather than collapsing to a constant, because Telegram will need its
    own entry and the extension point is the point.
    """
    from features.radar import config

    assert not any(config.COIN_SYMBOLS_MEAN_STOCKS.values())
    assert config.coin_collision_dropped('bluesky', 'LINK') is True
```

- [ ] **Step 2: Run it to verify it fails**

```bash
python -m pytest tests/test_radar_config.py -v -k "stocktwits_is_retired or coin_symbol_as_a_company"
```

Expected: `AssertionError: assert 'stocktwits' not in ('stocktwits', 'bluesky', 'fourchan', 'reddit')`.

- [ ] **Step 3: Strip StockTwits from config**

In `personal_apps/features/radar/config.py`:

```python
SOURCES = ('bluesky', 'fourchan', 'reddit')
```

Remove the `'stocktwits'` entry and its comment from `BARE_TOKENS_ALLOWED`, `COIN_SYMBOLS_MEAN_STOCKS`, `SINGLE_LETTER_CASHTAGS` and `SOURCE_KIND`. Delete `STOCKTWITS_REQUESTS_PER_HOUR` and its comment.

Add above `COIN_SYMBOLS_MEAN_STOCKS`:

```python
# Sources where a coin-shaped symbol should be read as the coin, not the
# company. Finance-native populations are the exception -- and since StockTwits
# was retired 2026-08-26 there are none, so every symbol in
# COIN_COLLISION_SYMBOLS is now dropped on every live source. That costs 49
# real tickers their mentions, which is the price of not putting Chainlink
# chatter under Interlink Electronics.
#
# Kept as a map rather than collapsed to a constant: Telegram is the next
# source and will need its own entry, and the extension point is the point.
```

- [ ] **Step 4: Delete the module and its suite**

```bash
git rm personal_apps/features/radar/sources/stocktwits.py personal_apps/tests/test_radar_stocktwits.py
```

- [ ] **Step 5: Strip StockTwits from the daemon**

In `personal_apps/run_radar_ingest.py`: delete `_stocktwits_fetcher` entirely; remove `stocktwits` from the `from features.radar.sources import ...` line; remove `STOCKTWITS_REQUESTS_PER_HOUR` from the config import; delete `_CYCLES_PER_HOUR` and `SYMBOL_BUDGET_PER_CYCLE`; remove `st_client` and the `'stocktwits'` entry from `build_fetchers`.

Update the module docstring — it says "Three sources run behind one contract."

- [ ] **Step 6: Re-document the scheduler's orphaned reasons**

In `personal_apps/features/radar/scheduling.py`, `MIN_INTERVAL` / `MAX_INTERVAL` are documented as StockTwits-shaped and every remaining caller overrides them. Re-document as generic defaults. In `retire_untracked`, the prohibition names StockTwits as its example; restate it as the property:

```python
    ONLY for a source whose configured list is the COMPLETE set -- Reddit,
    where REDDIT_SUBS is exhaustive. A source whose tracked set is a rolling
    window must never call this: a symbol falling out of the window is
    temporary, and deleting the row throws away a real observed_rate that took
    hours to learn.
```

- [ ] **Step 7: Move the test suites off `'stocktwits'`**

In each of `test_radar_buckets.py`, `test_radar_bucket_sources.py`, `test_radar_daemon.py`, `test_radar_ingest.py`, `test_radar_profile.py`, `test_radar_scoring.py`, replace `'stocktwits'` with `'bluesky'` as the default source, including `ALL_OK` and any `fetcher_for(..., source=...)` default.

Two tests need more than a rename:

- `test_radar_ingest.py::test_a_coin_collision_is_dropped_on_a_general_source` still passes — `bluesky` is `False` in the map.
- `test_radar_ingest.py::test_the_same_symbol_still_counts_on_a_finance_source` has no finance source left. Replace it with a test that pins the monkeypatched extension point, so the mechanism stays covered:

```python
def test_a_source_can_opt_into_reading_coin_symbols_as_companies(seeded, monkeypatch):
    """The extension point, kept alive with no live source using it.

    StockTwits was the only population where $LINK meant Interlink. It is
    retired; this pins that a future finance-native source can still opt in,
    rather than the map quietly becoming a constant nobody can override.
    """
    from features.radar import config

    monkeypatch.setitem(config.COIN_SYMBOLS_MEAN_STOCKS, 'bluesky', True)
    assert config.coin_collision_dropped('bluesky', 'LINK') is False
```

- [ ] **Step 8: Run the whole radar suite**

```bash
python -m pytest tests/ -k radar -v
```

Expected: all pass, and `test_radar_stocktwits.py` is gone from collection.

- [ ] **Step 9: Commit**

```bash
git add -A personal_apps
git commit -m "fix(radar): retire StockTwits, which Cloudflare has refused since launch"
```

---

## Task 8: Score `truncated` buckets

**Files:**
- Modify: `personal_apps/features/radar/scoring.py:88-104`
- Modify: `personal_apps/tests/test_radar_scoring.py`

**Interfaces:**
- Consumes: Task 3 (without it, a stale z is indistinguishable from a newly-legitimate one).
- Produces: no new names. Behaviour: `score_source` writes `expected`, `variance`, `mention_z`, `baseline_days` on rows with `status in ('ok', 'truncated')`; `baselines.usable` and `profile.build_profile` are unchanged and still see `ok` only.

Reddit has 4,372 truncated bucket rows against 478 `ok`, so 90% of the source is excluded from scoring entirely — which is why it produced four elevated rows in 4.5 days. An undercounted observation against a correctly-scaled expectation biases z **downward**, so scoring these is conservative, and the `partial` mark carries the caveat.

- [ ] **Step 1: Write the failing test**

Append to `personal_apps/tests/test_radar_scoring.py`:

```python
def test_a_truncated_bucket_is_scored_from_ok_baselines(clean_buckets):
    """Truncated counts are real but incomplete. Refusing to score them at all
    cost Reddit 90% of its buckets and left it with four elevated rows in four
    and a half days (audit 2026-08-26).

    The undercount biases z DOWNWARD against a correctly-scaled expectation, so
    scoring it is the conservative direction; the `partial` mark is what tells
    the reader.
    """
    import datetime as dt

    from extensions import db
    from features.radar import buckets, scoring
    from models import RadarBucketSource

    now = dt.datetime(2026, 4, 15, 15, 0, 0)
    # Build some ok history so a baseline exists at all.
    for minute in range(0, 45, 15):
        start = {dt.datetime(2026, 4, 15, 14, minute, 0)}
        buckets.roll_up([row(external_id='zz-ok-%d' % minute, minute=minute)],
                        {'bluesky': 'ok'}, start)
    # Then one truncated quarter-hour.
    buckets.roll_up([row(external_id='zz-tr', minute=46)],
                    {'bluesky': 'truncated'},
                    {dt.datetime(2026, 4, 15, 14, 45, 0)})

    scoring.score_source('bluesky', now)

    truncated = RadarBucketSource.query.filter_by(
        ticker='ZZA', source='bluesky',
        bucket_start=dt.datetime(2026, 4, 15, 14, 45, 0)).one()
    assert truncated.status == 'truncated'
    assert truncated.mention_z is not None
    assert truncated.expected is not None


def test_a_missing_bucket_is_still_never_scored(clean_buckets):
    """`missing` writes no row at all, so there is nothing to score. This pins
    that widening scoring to `truncated` did not widen it to everything."""
    from features.radar import scoring

    assert 'missing' not in scoring.SCOREABLE_STATUSES
    assert scoring.SCOREABLE_STATUSES == frozenset({'ok', 'truncated'})
```

- [ ] **Step 2: Run it to verify it fails**

```bash
python -m pytest tests/test_radar_scoring.py -v -k "truncated_bucket_is_scored or missing_bucket_is_still"
```

Expected: the first `AssertionError: assert None is not None`, the second `AttributeError: module 'features.radar.scoring' has no attribute 'SCOREABLE_STATUSES'`.

- [ ] **Step 3: Widen what gets scored**

In `personal_apps/features/radar/scoring.py`, above `score_source`:

```python
# Statuses a score may be written onto. NOT the same set baselines are built
# from: `truncated` counts are real but incomplete, so they are worth ranking
# and worthless as a description of normal. baselines.usable and
# profile.build_profile still take `ok` alone.
#
# Widened 2026-08-26. Refusing to score truncated rows excluded 90% of Reddit,
# which produced four elevated rows in four and a half days. An undercounted
# observation against a correctly-scaled expectation understates z, so the
# error runs towards silence rather than towards a false spike -- and the row
# carries the `partial` mark either way.
SCOREABLE_STATUSES = frozenset({'ok', 'truncated'})
```

and in the write loop:

```python
        for row in rows:
            # A source that was DOWN has nothing to be surprised about --
            # scoring it would invent a reading from a gap. A source that was
            # merely incomplete is a different fact: see SCOREABLE_STATUSES.
            if row.status not in SCOREABLE_STATUSES:
                continue
```

- [ ] **Step 4: Run it to verify it passes**

```bash
python -m pytest tests/test_radar_scoring.py tests/test_radar_baselines.py tests/test_radar_profile.py tests/test_radar_leaderboard.py -v
```

Expected: all pass. `test_radar_leaderboard.py` matters here — the `partial` mark becomes reachable for the first time, so any test asserting `marks == []` on a truncated fixture now needs updating to expect `['partial']`.

- [ ] **Step 5: Commit**

```bash
git add personal_apps/features/radar/scoring.py personal_apps/tests
git commit -m "fix(radar): rank truncated buckets instead of discarding ninety percent of reddit"
```

---

## Task 9: Per-subreddit source names

**Files:**
- Create: `personal_apps/migrations/versions/<rev>_widen_radar_source_columns.py`
- Modify: `personal_apps/models.py` (`RadarBucketSource.source`, `RadarPollState.source`)
- Modify: `personal_apps/features/radar/config.py`
- Modify: `personal_apps/features/radar/sources/reddit.py`
- Modify: `personal_apps/run_radar_ingest.py`
- Modify: `personal_apps/features/radar/routes/api.py`
- Modify: `personal_apps/tests/test_radar_reddit.py`, `test_radar_config.py`

**Interfaces:**
- Consumes: Task 7 (`SOURCES` no longer holds StockTwits), Task 8.
- Produces: `config.source_root(source)` -> `str`, the part before `':'`. `config.source_kind`, `bare_tokens_allowed`, `bare_token_confidence` and `coin_collision_dropped` all resolve through it. `RawPost.source` for Reddit becomes `'reddit:<sub>'`.

`sources/reddit._roll_up` collapses every subreddit in a cycle into one worst-case status, and `REDDIT_SUBS_PER_CYCLE = 1` makes that a single sub's verdict. r/wallstreetbets turns its 25-entry feed over in under two minutes against a 120-second poll, so it is permanently `truncated` — and it carries 47% of all Reddit volume, so its permanent truncation is Reddit's.

**Bumps `source_config_version`.**

- [ ] **Step 1: Write the failing test**

Append to `personal_apps/tests/test_radar_config.py`:

```python
def test_a_prefixed_source_inherits_its_roots_policy():
    """`reddit:wallstreetbets` is Reddit for every per-source judgement.

    Splitting the source name is what stops one sub's permanent feed rollover
    from marking every other sub's buckets truncated. It must not also split
    the policy: an unlisted sub inherits Reddit's rules rather than falling
    through to the strict default, which would silently disable bare tokens on
    a source that depends on them.
    """
    from features.radar import config

    assert config.source_root('reddit:wallstreetbets') == 'reddit'
    assert config.source_root('bluesky') == 'bluesky'
    assert config.bare_tokens_allowed('reddit:wallstreetbets') is True
    assert config.bare_token_confidence('reddit:pennystocks') == 'high'
    assert config.source_kind('reddit:thetagang') == 'forum'
    assert config.coin_collision_dropped('reddit:weedstocks', 'LINK') is True
```

- [ ] **Step 2: Run it to verify it fails**

```bash
python -m pytest tests/test_radar_config.py::test_a_prefixed_source_inherits_its_roots_policy -v
```

Expected: `AttributeError: module 'features.radar.config' has no attribute 'source_root'`.

- [ ] **Step 3: Add `source_root` and route every per-source lookup through it**

In `personal_apps/features/radar/config.py`, above `source_kind`:

```python
def source_root(source):
    """The policy-bearing part of a source name.

    Reddit carries its subreddit -- `reddit:wallstreetbets` -- so that one
    sub's feed rolling over between polls marks its own buckets truncated and
    not every other sub's. Before 2026-08-26 they shared one name and one
    status, and with REDDIT_SUBS_PER_CYCLE = 1 that meant whichever sub the
    cycle happened to read decided the status of all of them. In production
    that was 4372 truncated rows against 478 ok.

    The policy must NOT split with the name. An unlisted sub inherits Reddit's
    judgements rather than falling through to the strict default, which would
    silently disable bare tokens on a source that has nothing else.
    """
    return source.split(':', 1)[0]
```

Then in the same module:

```python
def source_kind(source):
    return SOURCE_KIND.get(source_root(source), 'forum')


def single_letter_cashtags_allowed(source):
    return SINGLE_LETTER_CASHTAGS.get(source_root(source), False)


def coin_collision_dropped(source, symbol):
    """True when this symbol should be ignored on this source."""
    if COIN_SYMBOLS_MEAN_STOCKS.get(source_root(source), False):
        return False
    return symbol in COIN_COLLISION_SYMBOLS


def bare_tokens_allowed(source):
    return BARE_TOKENS_ALLOWED.get(source_root(source), False)


def bare_token_confidence(source):
    return BARE_TOKEN_CONFIDENCE.get(source_root(source), 'low')
```

- [ ] **Step 4: Widen the two `source` columns**

In `personal_apps/models.py`:

```python
    # 48, not 24: a Reddit source name carries its subreddit
    # (`reddit:smallstreetbets` is 22 characters and the margin at 24 was two).
    source                    = db.Column(db.String(48), primary_key=True)
```

on `RadarBucketSource`, and on `RadarPollState`:

```python
    source          = db.Column(db.String(48), primary_key=True)
```

Generate the migration:

```bash
python -m flask db revision -m "widen radar source columns"
```

Edit it to chain from Task 1's revision and:

```python
def upgrade():
    # radar_bucket_sources is PARTITIONED, and `source` is part of its primary
    # key. MODIFY COLUMN rebuilds the table; at ~300k rows that is seconds, but
    # it is not online -- expect the ingest daemon's writes to block briefly.
    op.alter_column('radar_bucket_sources', 'source',
                    existing_type=sa.String(length=24),
                    type_=sa.String(length=48), existing_nullable=False)
    op.alter_column('radar_poll_state', 'source',
                    existing_type=sa.String(length=24),
                    type_=sa.String(length=48), existing_nullable=False)


def downgrade():
    op.alter_column('radar_poll_state', 'source',
                    existing_type=sa.String(length=48),
                    type_=sa.String(length=24), existing_nullable=False)
    op.alter_column('radar_bucket_sources', 'source',
                    existing_type=sa.String(length=48),
                    type_=sa.String(length=24), existing_nullable=False)
```

- [ ] **Step 5: Emit prefixed source names from Reddit**

In `personal_apps/features/radar/sources/reddit.py`, `_to_raw_post`:

```python
    return RawPost(
        # The SUBREDDIT is part of the source, not only of the channel. One
        # name meant one status for the whole cycle, and with one sub read per
        # cycle that was whichever sub happened to be due -- r/wallstreetbets
        # is permanently truncated and used to mark every quieter sub with it.
        source='reddit:%s' % sub,
        external_id=entry.findtext('a:id', '', ATOM),
        channel=sub,
        ...
```

`fetch` returns one `FetchResult` per cycle and `_roll_up` collapses statuses. With one sub per cycle that collapse is a no-op today, but keep it correct for a larger budget: return the per-sub statuses so `ingest` can stamp each source name separately.

In `fetch`, record the status per subreddit as well as in the flat list:

```python
    posts, statuses, rates = [], [], {}
    by_sub = {}

    for index, (sub, since) in enumerate(since_by_sub.items()):
        if index and pause:
            time.sleep(pause)
        try:
            found, status, rate = fetch_one(sub, since, client)
        except RedditThrottled:
            statuses.append('missing')
            by_sub[sub] = 'missing'
            break
        except RedditUnavailable:
            statuses.append('missing')
            by_sub[sub] = 'missing'
            rates[sub] = None
            continue
        posts.extend(found)
        statuses.append(status)
        by_sub[sub] = status
        rates[sub] = rate

    return FetchResult(posts=posts, status=_roll_up(statuses), rates=rates,
                       per_source_status={'reddit:%s' % sub: status
                                          for sub, status in by_sub.items()})
```

and add the field to `FetchResult` in `personal_apps/features/radar/sources/__init__.py`:

```python
    # Status per emitted source name, where one fetch covers several. Reddit
    # reads a slice of subreddits and each is its own source; the rolled-up
    # `status` above is what the cycle reports, and this is what the rollup
    # stamps on each source's rows. Empty means `status` applies to everything
    # this result produced.
    per_source_status: dict = dataclasses.field(default_factory=dict)
```

In `personal_apps/features/radar/ingest.py`, `run_cycle`, after `statuses[source] = result.status`:

```python
        # A fetcher covering several source names reports each. Reddit does:
        # one cycle reads a slice of subreddits and each is its own source.
        statuses.update(result.per_source_status)
```

- [ ] **Step 6: Track and retire per-subreddit poll state**

In `personal_apps/run_radar_ingest.py`, `_reddit_fetcher` schedules by bare subreddit name (`REDDIT_SUBS`), which is unchanged — poll state is keyed by `(source='reddit', symbol=<sub>)` and stays that way. Only the emitted `RawPost.source` changes. Add the note:

```python
        # Poll state stays keyed by the bare source name with the subreddit as
        # its symbol. Only what the POSTS carry is prefixed -- the scheduler's
        # unit is the subreddit either way, and re-keying it would retire every
        # learned observed_rate on deploy.
```

- [ ] **Step 7: Accept prefixed names at the API boundary**

In `personal_apps/features/radar/routes/api.py`, `parse_query`:

```python
    raw_sources = args.get('sources')
    if raw_sources:
        selected = [s.strip() for s in raw_sources.split(',') if s.strip()]
        # A prefixed name is valid when its ROOT is a known source: the UI
        # offers `reddit` as one chip, and a link may name one subreddit.
        if any(source_root(s) not in SOURCES for s in selected):
            raise BadQuery('unknown source')
    else:
        selected = list(SOURCES)
```

`selected` defaulting to `list(SOURCES)` no longer matches any stored Reddit row, because those now carry `reddit:<sub>`. Expand it:

```python
def expand_sources(names):
    """Concrete stored source names for a selection.

    `reddit` means every configured subreddit, because that is what the chip
    promises. A caller naming one subreddit gets exactly it.
    """
    out = []
    for name in names:
        if name == 'reddit':
            out.extend('reddit:%s' % sub for sub in REDDIT_SUBS)
        else:
            out.append(name)
    return out
```

and use it where `query.sources` reaches `board_mod.build` and `detail_panel.build`:

```python
    board = board_mod.build(expand_sources(query.sources), now,
                            window_hours=query.window,
                            segments=query.segments, limit=query.limit,
                            min_venues=query.min_venues)
```

```python
        built = detail_panel.build(ticker.upper(), expand_sources(query.sources),
                                   now, window_hours=query.window, span=span)
```

Import what it needs at the top of the file:

```python
from ..config import DEFAULT_SEGMENT, REDDIT_SUBS, SOURCES, source_root
```

`board_mod.build` copies what it is given onto `Board.sources`, and `serialize` echoes that back as the payload's `sources`, which the UI compares against `all_sources` to decide which chips are lit. Expanded, that would light eight subreddit chips the reader never chose. So `build_payload` restores the selection before serializing:

```python
    board = board_mod.build(expand_sources(query.sources), now, ...)
    # What the VIEWER picked, not what it expanded to. The payload's `sources`
    # drives which chips are lit, and the chip is `reddit`.
    board.sources = list(query.sources)
    return serialize(board)
```

- [ ] **Step 8: Run the suites**

```bash
python -m flask db upgrade && python -m pytest tests/ -k radar -v
```

Expected: all pass.

- [ ] **Step 9: Commit**

```bash
git add -A personal_apps
git commit -m "feat(radar): one subreddit's rollover no longer truncates the rest"
```

---

# Stage 3 — The remaining absences

## Task 10: A failed read is not a measured zero

**Files:**
- Modify: `personal_apps/features/radar/sources/reddit.py:150-160` (`fetch_one`)
- Modify: `personal_apps/features/radar/ingest.py:215-225` (`run_cycle`)
- Modify: `personal_apps/tests/test_radar_reddit.py`, `test_radar_ingest.py`

**Interfaces:**
- Consumes: nothing.
- Produces: `fetch_one` returns `(posts, status, None)` when no entry parses. `run_cycle`'s summary carries `catchup_depth[source] = None` for a source that raised.

`interval_for_rate(0)` returns the ceiling, and `REDDIT_MAX_POLL` is six hours. A parse failure or a transient empty feed is currently recorded as "genuinely silent" and earns a six-hour backoff. `None` is the value the scheduler already understands as "never measured" and answers with the floor.

- [ ] **Step 1: Write the failing test**

Append to `personal_apps/tests/test_radar_reddit.py`:

```python
def test_a_feed_that_parses_to_nothing_reports_no_rate():
    """Zero is a measurement. Nothing arriving is not one.

    interval_for_rate(0) returns the CEILING, which is six hours since
    2026-08-25 -- so an unparseable feed used to earn the same backoff as a
    genuinely dead subreddit. None is the value the scheduler already
    understands as never-measured, and it answers with the floor.
    """
    import datetime as dt

    from features.radar.sources import reddit

    class _Empty:
        def get_feed(self, sub):
            return ('<?xml version="1.0" encoding="UTF-8"?>'
                    '<feed xmlns="http://www.w3.org/2005/Atom"></feed>')

    posts, status, rate = reddit.fetch_one(
        'zztest', dt.datetime(2026, 4, 15, 14, 0, 0), _Empty())
    assert posts == []
    assert status == 'ok'
    assert rate is None
```

Append to `personal_apps/tests/test_radar_ingest.py`:

```python
def test_a_failed_fetch_reports_no_catchup_depth(seeded):
    """Depth zero says the source reached back nowhere. It reached back
    nothing, which is a different fact and must stay one."""
    from features.radar import ingest

    def explode(since):
        raise RuntimeError('nope')

    summary = ingest.run_cycle(dt.datetime(2026, 4, 15, 15, 0, 0),
                               {'bluesky': explode})
    assert summary['per_source']['bluesky'] == 'missing'
    assert summary['catchup_depth']['bluesky'] is None
```

- [ ] **Step 2: Run them to verify they fail**

```bash
python -m pytest tests/test_radar_reddit.py -k parses_to_nothing tests/test_radar_ingest.py -k failed_fetch -v
```

Expected: `assert 0.0 is None` and `assert 0 is None`.

- [ ] **Step 3: Return `None`**

In `personal_apps/features/radar/sources/reddit.py`, `fetch_one`:

```python
    entries = root.findall('a:entry', ATOM)
    posts = [p for p in (_to_raw_post(e, sub) for e in entries) if p]
    if not posts:
        # No rate, not a rate of zero. interval_for_rate reads zero as
        # "genuinely silent" and answers with the ceiling -- six hours since
        # 2026-08-25 -- so a parse failure used to cost the sub most of a day.
        # None means never measured, and answers with the floor.
        return [], 'ok', None
```

In `personal_apps/features/radar/ingest.py`, `run_cycle`'s exception handler:

```python
            logger.exception('radar source %s failed this cycle', source)
            statuses[source] = 'missing'
            # Not zero. Zero says the source reached back nowhere; nothing
            # arrived at all, and the two are different facts.
            depths[source] = None
            continue
```

Check `run_radar_ingest.tick`'s fallback dict — it returns `'catchup_depth'`-less summaries on an exception. Leave it; nothing reads the field there.

- [ ] **Step 4: Run them to verify they pass**

```bash
python -m pytest tests/test_radar_reddit.py tests/test_radar_ingest.py tests/test_radar_scheduling.py -v
```

Expected: all pass. `record_poll` already accepts `None` — `interval_for_rate` handles it as the first branch.

- [ ] **Step 5: Commit**

```bash
git add personal_apps/features/radar/sources/reddit.py personal_apps/features/radar/ingest.py personal_apps/tests
git commit -m "fix(radar): an unread feed reports no rate rather than a rate of zero"
```

---

## Task 11: An unpriced model does not cost nothing

**Files:**
- Modify: `personal_apps/features/radar/spend.py`
- Modify: `personal_apps/features/radar/routes/api.py` (`serialize`)
- Modify: `personal_apps/static/radar/src/types.ts`, `list/Spend.tsx`
- Modify: `personal_apps/tests/test_radar_spend.py`

**Interfaces:**
- Consumes: nothing.
- Produces: `spend.cost_micros(model, input_tokens, output_tokens)` returns `int | None`. `spend.summary()` returns `{'today_usd', 'month_usd', 'unpriced_tokens'}` where `unpriced_tokens` is an int.

`cost_micros` returns `0` for a model with no rate, `record` adds that zero, and `summary()` reports only dollars — so the tokens that were meant to make the omission visible never surface. A model swap makes the bill read as free.

- [ ] **Step 1: Write the failing test**

Append to `personal_apps/tests/test_radar_spend.py`:

```python
def test_an_unpriced_model_costs_null_not_nothing():
    """Zero is a price. Not knowing the price is not one."""
    from features.radar import spend

    assert spend.cost_micros('claude-not-a-real-model', 1000, 100) is None
    assert spend.cost_micros('claude-haiku-4-5', 1_000_000, 0) == 1_000_000


def test_the_summary_surfaces_what_it_could_not_price(clean_spend):
    """The docstring's claim that 'the tokens are still recorded, so the
    omission is visible' was only true of the table. summary() returned
    dollars alone, so a model swap read as a free day on the board."""
    import datetime as dt

    from features.radar import spend

    day = dt.date(2026, 4, 15)
    spend.record('claude-haiku-4-5', calls=1, input_tokens=1_000_000,
                 output_tokens=0, day=day)
    spend.record('claude-unknown-9', calls=1, input_tokens=500_000,
                 output_tokens=1000, day=day)

    result = spend.summary(today=day)
    assert result['today_usd'] == 1.0
    assert result['unpriced_tokens'] == 501_000
```

Add a `clean_spend` fixture to that file if none exists, deleting `RadarLlmSpend` rows for `day=dt.date(2026, 4, 15)` before and after.

- [ ] **Step 2: Run it to verify it fails**

```bash
python -m pytest tests/test_radar_spend.py -v -k "unpriced_model or surfaces_what"
```

Expected: `assert 0 is None`, then `KeyError: 'unpriced_tokens'`.

- [ ] **Step 3: Make the absence a NULL**

In `personal_apps/features/radar/spend.py`:

```python
def cost_micros(model, input_tokens, output_tokens):
    """Integer micro-dollars for this usage, or None at an unknown rate.

    None, not zero. Zero is a price -- it says the call was free -- and a model
    swap would then read as a free day on the board. The tokens are still
    recorded either way, and summary() reports the ones it could not price so
    the omission is visible where anyone looks.
    """
    rate = MODEL_RATES.get(model)
    if rate is None:
        return None
    per_in, per_out = rate
    return round((input_tokens * per_in + output_tokens * per_out)
                 * MICROS_PER_USD / 1_000_000)
```

In `record`, guard the accumulation:

```python
    cost = cost_micros(model, input_tokens, output_tokens)
    if cost is not None:
        # Added at the rate that applies NOW, so a later price change cannot
        # reach backwards into a day that was already paid for.
        row.cost_micros += cost
```

In `summary`, add the unpriced total:

```python
    def unpriced(since, until):
        """Tokens booked against a model with no rate on file.

        Read off the same rows: a model absent from MODEL_RATES contributed
        tokens and no cost, so its token totals are what is missing from the
        dollar figures above.
        """
        known = list(MODEL_RATES)
        total = db.session.query(
            sa.func.coalesce(
                sa.func.sum(RadarLlmSpend.input_tokens
                            + RadarLlmSpend.output_tokens), 0)).filter(
                RadarLlmSpend.day >= since,
                RadarLlmSpend.day <= until,
                RadarLlmSpend.model.notin_(known)).scalar()
        # int() at the boundary: SUM over BIGINT is Decimal on MySQL and
        # MariaDB alike, and Flask's JSON encoder raises on Decimal.
        return int(total or 0)

    return {
        'today_usd': _usd(total(today, today)),
        'month_usd': _usd(total(first, today)),
        # Never folded into the dollars. A token nobody could price is not
        # worth zero dollars; it is worth an unknown amount, and saying so is
        # the only honest option the board has.
        'unpriced_tokens': unpriced(first, today),
    }
```

- [ ] **Step 4: Surface it**

In `personal_apps/static/radar/src/types.ts`:

```ts
  spend?: { today_usd: number; month_usd: number; unpriced_tokens: number }
```

In `personal_apps/static/radar/src/list/Spend.tsx`, after the existing line, render the caveat only when it applies:

```tsx
      {spend.unpriced_tokens > 0 && (
        <span className="caveat">
          plus {spend.unpriced_tokens.toLocaleString()} tokens at an unknown
          rate
        </span>
      )}
```

Use whatever class the file already uses for secondary text — do not introduce a new colour, and do not use green or red.

- [ ] **Step 5: Run the tests and the frontend build**

```bash
python -m pytest tests/test_radar_spend.py tests/test_radar_api.py -v && npm run build
```

Expected: tests pass, build succeeds.

- [ ] **Step 6: Commit**

```bash
git add personal_apps/features/radar/spend.py personal_apps/features/radar/routes/api.py personal_apps/static/radar/src personal_apps/tests/test_radar_spend.py
git commit -m "fix(radar): an unpriced model reads as unknown, not as free"
```

---

## Task 12: Interior gaps in the intraday chatter chart

**Files:**
- Modify: `personal_apps/features/radar/detail.py:168-231`
- Modify: `personal_apps/tests/test_radar_detail.py`

**Interfaces:**
- Consumes: nothing.
- Produces: `detail.watched_slots(sources, start, now, step_minutes, slots)` -> `set[int]`, replacing `_watched_from_index`. `intraday_chart_for` uses it.

`_watched_from_index` is `MIN(bucket_start)` over the window, so only the *leading* gap becomes null. A mid-window outage draws zeros. `board._covered_hours` does this correctly, per hour, over the same data — two honesty standards for one fact.

- [ ] **Step 1: Write the failing test**

Append to `personal_apps/tests/test_radar_detail.py`:

```python
def test_an_outage_in_the_middle_of_the_window_is_not_drawn_as_quiet(clean_buckets):
    """board._covered_hours has always got this right, per hour. The detail
    chart only nulled the LEADING gap, so a daemon that stopped for an hour and
    resumed drew a stretch of zero chatter that nobody measured.
    """
    import datetime as dt

    from features.radar import buckets, detail

    now = dt.datetime(2026, 4, 15, 16, 0, 0)
    # Two buckets an hour apart, nothing in between.
    for minute, hour in ((0, 14), (0, 15)):
        start = dt.datetime(2026, 4, 15, hour, minute, 0)
        buckets.roll_up([row(external_id='zz-%d' % hour, minute=minute)],
                        {'bluesky': 'ok'}, {start})

    chart = detail.intraday_chart_for('ZZA', ['bluesky'], now, '1D')

    observed = [c for c in chart.chatter if c is not None]
    assert observed, 'the two measured slots should carry counts'
    # The stretch between them was never observed and must be null, not zero.
    assert None in chart.chatter[1:-1]
```

- [ ] **Step 2: Run it to verify it fails**

```bash
python -m pytest tests/test_radar_detail.py::test_an_outage_in_the_middle_of_the_window_is_not_drawn_as_quiet -v
```

Expected: `AssertionError: assert None in [0, 0, 0, ...]`.

- [ ] **Step 3: Replace the leading-edge index with a covered set**

In `personal_apps/features/radar/detail.py`, replace `_watched_from_index` with:

```python
def watched_slots(sources, start, now, step_minutes, slots):
    """The slots in which any bucket at all was written for these sources.

    The proxy for "ingest was alive", and the same one board._covered_hours
    uses. It is a proxy and not a record: a genuine board-wide silence reads
    the same as a stopped daemon, and both resolve to "not measured" -- the
    honest half of the ambiguity, where the dishonest half would draw a zero.

    Replaces a MIN(bucket_start) that only ever nulled the LEADING gap, so an
    outage in the middle of a window was drawn as an hour of quiet.
    """
    rows = (db.session.query(RadarBucketSource.bucket_start)
            .filter(RadarBucketSource.source.in_(list(sources)),
                    RadarBucketSource.bucket_start >= start,
                    RadarBucketSource.bucket_start < now,
                    RadarBucketSource.status.in_(('ok', 'truncated')))
            .distinct().all())

    covered = set()
    for (bucket_start,) in rows:
        index = _slot_index(bucket_start, start, step_minutes, slots)
        if index is not None:
            covered.add(index)
    return covered
```

and in `intraday_chart_for`:

```python
    covered = watched_slots(sources, start, now, step_minutes, slots)

    chatter = []
    for index in range(slots):
        # A slot nobody was watching is unknown, not silent. Same rule the
        # daily chart follows, and now the same rule for an outage in the
        # MIDDLE of the window rather than only before it began.
        chatter.append(counts[index] if index in covered else None)

    first_watched = min(covered) if covered else None
    return Chart(start=start, closes=closes, chatter=chatter,
                 watched_from=(start + dt.timedelta(
                     minutes=first_watched * step_minutes)
                     if first_watched is not None else None),
                 step_minutes=step_minutes)
```

- [ ] **Step 4: Run it to verify it passes**

```bash
python -m pytest tests/test_radar_detail.py tests/test_radar_api.py -v
```

Expected: all pass.

- [ ] **Step 5: Commit**

```bash
git add personal_apps/features/radar/detail.py personal_apps/tests/test_radar_detail.py
git commit -m "fix(radar): an outage mid-window is a gap in the chart, not quiet"
```

---

## Task 13: Three small corrections

**Files:**
- Modify: `personal_apps/features/radar/leaderboard.py:263`
- Modify: `personal_apps/features/radar/board.py:280-290`
- Modify: `personal_apps/features/radar/ingest.py:95-186`
- Modify: `personal_apps/tests/test_radar_board.py`

**Interfaces:**
- Consumes: nothing.
- Produces: no new names. `Board.excluded` may now carry the key `'one_venue'`.

- [ ] **Step 1: Write the failing test**

Append to `personal_apps/tests/test_radar_board.py`:

```python
def test_the_breadth_filter_reports_what_it_removed(clean_buckets, clean_events):
    """Board.excluded is documented as 'what the eligibility floor AND the
    breadth filter left out'. The breadth filter's half was never counted, so
    raising the venue floor made rows vanish with no account of where."""
    import datetime as dt

    from features.radar import board, buckets, scoring

    now = dt.datetime(2026, 4, 15, 16, 0, 0)
    # One ticker, one venue, comfortably over the eligibility floor: five
    # mentions, five authors, five distinct texts.
    for n in range(5):
        start = dt.datetime(2026, 4, 15, 15, 0, 0)
        buckets.roll_up([_row(external_id='zz-%d' % n, author='u%d' % n,
                              simhash=100 + n, minute=0)],
                        _ALL_OK, {start})
    scoring.score_source('bluesky', now)

    wide_open = board.build(['bluesky'], now, window_hours=4, min_venues=1)
    assert any(r.rank.ticker == 'ZZA' for r in wide_open.rows)

    filtered = board.build(['bluesky'], now, window_hours=4, min_venues=2)
    assert not any(r.rank.ticker == 'ZZA' for r in filtered.rows)
    assert filtered.excluded.get('one_venue', 0) >= 1
```

Import the shared helpers at the top of the file:
`from test_radar_journal import _row, _ALL_OK, clean_buckets, clean_events  # noqa: F401`.

- [ ] **Step 2: Run it to verify it fails**

```bash
python -m pytest tests/test_radar_board.py::test_the_breadth_filter_reports_what_it_removed -v
```

Expected: `AssertionError: assert 0 >= 1` on the last line — the row is correctly filtered out and correctly unaccounted for.

- [ ] **Step 3: Count what the breadth filter removed**

In `personal_apps/features/radar/board.py`, `build`:

```python
    allowed = segments_in(segments)
    if allowed:
        ranked = [row for row in ranked if row.segment in allowed]
    if min_venues > 1:
        # Counted, not silent. `excluded` is what stops a short board and a
        # stopped ingest looking the same, and the breadth filter's half of it
        # was missing -- so raising the floor made rows vanish unaccounted for.
        kept = [row for row in ranked if len(row.sources) >= min_venues]
        removed = len(ranked) - len(kept)
        if removed:
            ranking.excluded['one_venue'] = (
                ranking.excluded.get('one_venue', 0) + removed)
        ranked = kept
    ranked = ranked[:limit]
```

- [ ] **Step 4: Use the named floor**

In `personal_apps/features/radar/leaderboard.py`, add `VARIANCE_FLOOR` to the config import and:

```python
        mention_z = ((mentions - expected)
                     / max(variance, VARIANCE_FLOOR) ** 0.5) if variance else None
```

- [ ] **Step 5: Extract once per post**

In `personal_apps/features/radar/ingest.py`, `_store_mentioning_posts` calls `_extract_for` in both of its loops. Compute once:

```python
    fresh, new_count = [], 0
    extracted = {}
    for raw in raw_posts:
        row = existing.get(raw.external_id)
        # Once per post per call. The second loop below used to re-extract
        # every already-stored post, which is wasted work and -- worse -- a
        # second decision under whatever rules apply now.
        tickers = extracted.setdefault(raw.external_id, _extract_for(raw, lookup))
```

and in the second loop:

```python
    for raw in raw_posts:
        if raw.external_id in {r.external_id for r, _, _ in fresh}:
            continue
        tickers = extracted.get(raw.external_id, [])
        if not tickers:
            continue
```

Correct the docstring, which claims a stored post is "never re-extracted, so a stopword or universe change cannot silently rewrite history under a bucket that was already counted". That is now true for a different reason and should say so:

```python
    Extraction runs ONCE per post per cycle, and the journal keeps the result:
    a post arriving again in a later cycle upserts its existing event rather
    than re-deciding it, so a stopword or universe change cannot rewrite
    history under a bucket that was already counted.
```

- [ ] **Step 6: Run the suites**

```bash
python -m pytest tests/ -k radar -v
```

Expected: all pass.

- [ ] **Step 7: Commit**

```bash
git add personal_apps/features/radar personal_apps/tests
git commit -m "fix(radar): count what the breadth filter removed, name the variance floor, extract once"
```

---

# Stage 4 — The tone pass earns its bill

## Task 14: The detail breakdown reads the model verdict

**Files:**
- Modify: `personal_apps/features/radar/detail_panel.py:118-170`
- Modify: `personal_apps/tests/test_radar_detail.py`

**Interfaces:**
- Consumes: nothing.
- Produces: `Breakdown` gains `disagreements: int` (Task 15 renders it; this task computes the verdict precedence only).

`board._tones` prefers the model verdict correctly and is serialized as `row.tone` — which no component renders. `detail/Breakdown.tsx` draws the one tone bar that exists, and it is fed by `detail_panel._breakdown`, which selects `lexicon_sentiment` and never joins `llm_sentiment`. So 11,789 paid-for verdicts reach no pixel.

- [ ] **Step 1: Write the failing test**

Append to `personal_apps/tests/test_radar_detail.py`:

```python
def test_the_breakdown_prefers_the_model_verdict_over_the_lexicon():
    """The one surface that draws a tone bar never read the verdicts.

    Production 2026-08-26: 11,789 of 11,794 scored mentions carried a model
    verdict, at $1.24 a day, and the panel rendered the forty-word lexicon.
    """
    from features.radar import detail_panel

    assert detail_panel._tone_of(lexicon=0.8, verdict='bearish') == 'bearish'
    assert detail_panel._tone_of(lexicon=0.8, verdict=None) == 'bullish'
    # `unclear` votes neither way AND blocks the lexicon: it means the post
    # named the ticker without saying anything about it, and that read is
    # better informed than the word list it overrides.
    assert detail_panel._tone_of(lexicon=0.8, verdict='unclear') is None
    assert detail_panel._tone_of(lexicon=None, verdict=None) is None
```

- [ ] **Step 2: Run it to verify it fails**

```bash
python -m pytest tests/test_radar_detail.py::test_the_breakdown_prefers_the_model_verdict_over_the_lexicon -v
```

Expected: `AttributeError: module 'features.radar.detail_panel' has no attribute '_tone_of'`.

- [ ] **Step 3: Add the precedence and join the verdict**

In `personal_apps/features/radar/detail_panel.py`, above `_breakdown`:

```python
def _tone_of(lexicon, verdict):
    """'bullish', 'bearish' or None, from the two scores together.

    The model outranks the word list where both spoke. The lexicon is forty
    words with a negation window: it reads "great, another green day" after a
    crash as bullish, which is exactly the case spec 6.11 specified a re-read
    for.

    `unclear` votes neither way and BLOCKS the lexicon. It means the post named
    the ticker without expressing a view, and that read is better informed than
    the word list it overrides.

    A NULL verdict falls back to the lexicon rather than counting as toneless:
    verdicts arrive on a scheduled pass, so a fresh mention has none, and
    treating that as silence would make the newest posts look even-handed.
    """
    if verdict == 'bullish':
        return 'bullish'
    if verdict == 'bearish':
        return 'bearish'
    if verdict is not None:            # 'neutral' or 'unclear'
        return None
    if lexicon and lexicon > 0:
        return 'bullish'
    if lexicon and lexicon < 0:
        return 'bearish'
    return None
```

In `_breakdown`, select the verdict alongside the score and use the helper:

```python
    score = RadarMention.lexicon_sentiment
    verdict = RadarMention.llm_sentiment
    rows = (db.session.query(RadarPost.source, RadarPost.author,
                             RadarPost.channel, RadarPost.created_utc,
                             score, verdict)
            .join(RadarMention, RadarMention.post_id == RadarPost.id)
            .filter(...)                       # unchanged
            .all())
```

```python
    bullish = bearish = disagreements = 0

    for source, author, channel, when, sentiment, llm in rows:
        ...
        tone = _tone_of(sentiment, llm)
        if tone == 'bullish':
            bullish += 1
        elif tone == 'bearish':
            bearish += 1
        # A post the word list read one way and the model read the other is a
        # post that was being sarcastic. Both scores are kept precisely so this
        # comparison is possible; nothing performed it until now.
        lexicon_only = _tone_of(sentiment, None)
        if llm is not None and lexicon_only is not None and tone != lexicon_only:
            disagreements += 1
```

Add `disagreements: int` to the `Breakdown` dataclass and pass it in the return.

- [ ] **Step 4: Run it to verify it passes**

```bash
python -m pytest tests/test_radar_detail.py tests/test_radar_api.py -v
```

Expected: all pass.

- [ ] **Step 5: Commit**

```bash
git add personal_apps/features/radar/detail_panel.py personal_apps/tests/test_radar_detail.py
git commit -m "fix(radar): the panel's tone bar reads the verdicts it has been paying for"
```

---

## Task 15: Render the disagreement

**Files:**
- Modify: `personal_apps/features/radar/routes/api.py` (`serialize_detail`)
- Modify: `personal_apps/static/radar/src/types.ts`, `detail/Breakdown.tsx`
- Modify: `personal_apps/tests/test_radar_api.py`

**Interfaces:**
- Consumes: `Breakdown.disagreements` (Task 14).
- Produces: `breakdown.disagreements` in the detail payload.

- [ ] **Step 1: Write the failing test**

Append to `personal_apps/tests/test_radar_api.py`:

```python
def test_the_detail_payload_carries_the_sarcasm_signal():
    """Two sentiment scores are kept so their DISAGREEMENT can be read. Until
    now nothing compared them, which made the second one decoration.

    Asserted on the serializer rather than through a route, so it does not
    depend on which tickers the local database happens to hold.
    """
    import dataclasses

    from features.radar import detail_panel
    from features.radar.routes import api

    breakdown = detail_panel.Breakdown(
        venues=[], bullish=3, neutral=1, bearish=2, disagreements=2,
        top_author_share=None, top_two_share=None, peak_hour=None,
        peak_count=0, first_seen=None, mentions=6, voices=4)
    built = _stub_detail(breakdown)

    payload = api.serialize_detail(built)
    assert payload['breakdown']['disagreements'] == 2
```

`_stub_detail` builds the minimal `detail_panel.build` return the serializer
reads. If `test_radar_api.py` has no such helper, add one that constructs the
dataclass with the same field names `serialize_detail` touches — `ticker`,
`name`, `exchange`, `segment`, `market_cap`, `ipo_date`, `price`,
`price_move`, `price_status`, `session`, `mentions`, `expected`,
`baseline_days`, `chart`, `breakdown`, `posts`, `post_total`, `span` — reading
them off `detail_panel.py`'s own dataclass definitions.

- [ ] **Step 2: Run it to verify it fails**

```bash
python -m pytest tests/test_radar_api.py::test_the_detail_payload_carries_the_sarcasm_signal -v
```

Expected: `KeyError: 'disagreements'`.

- [ ] **Step 3: Serialize it**

In `personal_apps/features/radar/routes/api.py`, inside `serialize_detail`'s `'breakdown'` dict:

```python
            'bearish': b.bearish,
            # How often the word list and the model read the same post the
            # opposite way. Both scores exist so this is answerable, and a
            # disagreement is the sarcasm the lexicon cannot see.
            'disagreements': b.disagreements,
```

- [ ] **Step 4: Render it**

In `personal_apps/static/radar/src/types.ts`, add `disagreements: number` to the breakdown type.

In `personal_apps/static/radar/src/detail/Breakdown.tsx`, beside the existing bullish/bearish wording, render it only when non-zero:

```tsx
      {b.disagreements > 0 && (
        <span className="wording">
          <b>{b.disagreements}</b> read differently by the model
        </span>
      )}
```

Follow the file's existing markup and class conventions. The tone bar's colours are unchanged — green and red stay reserved for price direction, as the file's own comment at line 20 already says.

- [ ] **Step 5: Run the tests and build**

```bash
python -m pytest tests/test_radar_api.py -v && npm run build
```

Expected: tests pass, build succeeds.

- [ ] **Step 6: Commit**

```bash
git add personal_apps/features/radar/routes/api.py personal_apps/static/radar/src personal_apps/tests/test_radar_api.py
git commit -m "feat(radar): show where the model and the word list disagree"
```

---

## Task 16: Make `provisional` mean something

**Files:**
- Modify: `personal_apps/features/radar/scoring.py:82-86`
- Modify: `personal_apps/features/radar/leaderboard.py:270-300`
- Modify: `personal_apps/tests/test_radar_scoring.py`, `test_radar_leaderboard.py`

**Interfaces:**
- Consumes: nothing.
- Produces: `RadarBucketSource.baseline_days` becomes a float (fractional days). `leaderboard.Row.marks` may carry `'warming-up'` in place of `'provisional'` when the config version is what is thin.

`baseline_days = 0` on 147,228 of 147,429 scored Bluesky rows. Two causes: `span.days` truncates a 23-hour span to zero, and `source_config_version` changed nine times in 4.5 days so `usable` sees one hour. `PROVISIONAL_BASELINE_DAYS = 14` therefore fires on 100% of the board.

- [ ] **Step 1: Write the failing test**

Append to `personal_apps/tests/test_radar_scoring.py`:

```python
def test_a_baseline_shorter_than_a_day_is_not_reported_as_zero_days(clean_buckets):
    """span.days truncates. Twenty-three hours of history is not no history,
    and reporting it as zero put every row on the board permanently
    provisional -- 147,228 of 147,429 in production."""
    import datetime as dt

    from features.radar import buckets, scoring
    from models import RadarBucketSource

    now = dt.datetime(2026, 4, 16, 14, 0, 0)
    for hour in (14, 20, 23):
        start = dt.datetime(2026, 4, 15, hour, 0, 0)
        buckets.roll_up([row(external_id='zz-%d' % hour, minute=0)],
                        {'bluesky': 'ok'}, {start})

    scoring.score_source('bluesky', now)

    scored = RadarBucketSource.query.filter_by(
        ticker='ZZA', source='bluesky').first()
    assert 0 < scored.baseline_days < 1
```

- [ ] **Step 2: Run it to verify it fails**

```bash
python -m pytest tests/test_radar_scoring.py::test_a_baseline_shorter_than_a_day_is_not_reported_as_zero_days -v
```

Expected: `assert 0 < 0.0`.

- [ ] **Step 3: Stop truncating**

In `personal_apps/features/radar/scoring.py`:

```python
        span = max(o.bucket_start for o in good) - min(o.bucket_start for o in good)
        # Fractional. `.days` truncated twenty-three hours to zero, which put
        # every row under PROVISIONAL_BASELINE_DAYS forever -- a mark that
        # fires on 100% of a board carries no information.
        baseline_days = span.total_seconds() / 86400.0
```

The column is `db.SmallInteger` at `personal_apps/models.py:709`. Change it:

```python
    # Float since 2026-08-26. SmallInteger meant span.days, and .days truncated
    # twenty-three hours of history to zero -- which put every row on the board
    # under PROVISIONAL_BASELINE_DAYS permanently.
    baseline_days             = db.Column(db.Float, nullable=True)
```

Migration, chained after Task 9's:

```python
def upgrade():
    op.alter_column('radar_bucket_sources', 'baseline_days',
                    existing_type=mysql.SMALLINT(),
                    type_=sa.Float(), existing_nullable=True)


def downgrade():
    op.alter_column('radar_bucket_sources', 'baseline_days',
                    existing_type=sa.Float(),
                    type_=mysql.SMALLINT(), existing_nullable=True)
```

`leaderboard` takes `MIN(baseline_days)` across a ticker's sources and compares
against `PROVISIONAL_BASELINE_DAYS`; both work unchanged on a float.

- [ ] **Step 4: Split the mark**

In `personal_apps/features/radar/leaderboard.py`, in the marks block:

```python
        if baseline_days is not None and baseline_days < PROVISIONAL_BASELINE_DAYS:
            # Two different facts wear this badge, and only one is about the
            # ticker. A NEW ticker has thin history of its own; every ticker on
            # the board has thin history when the extraction rules changed
            # recently, because baselines are built per config version. Saying
            # `provisional` for both made it fire on all of them.
            marks.append('provisional' if baseline_days >= 1.0 else 'warming-up')
```

Add `'warming-up'` wherever `marks` values are enumerated on the client
(`static/radar/src/list/marks.test.tsx` and the component it covers), with the
same neutral styling `provisional` already has.

- [ ] **Step 5: Run the suites and the build**

```bash
python -m flask db upgrade && python -m pytest tests/ -k radar -v && npm run build
```

Expected: all pass.

- [ ] **Step 6: Commit**

```bash
git add -A personal_apps
git commit -m "fix(radar): a badge that fires on every row is not a badge"
```

---

## Task 17: Correct the cost record

**Files:**
- Modify: `personal_apps/features/radar/llm_sentiment.py:1-30`

**Interfaces:**
- Consumes: nothing.
- Produces: no new names.

The module docstring estimates "about 1335 scored mentions a day" and "roughly twenty cents a day". Measured 2026-08-25: 344 calls, 798,198 input tokens, 89,281 output tokens, **$1.2446** — 5x the volume and 6x the cost.

- [ ] **Step 1: Correct the docstring**

Replace the `COST.` paragraph in `personal_apps/features/radar/llm_sentiment.py`:

```
COST. Measured, not estimated, on 2026-08-25: 344 calls, 798,198 input tokens,
89,281 output, $1.2446 for the day. The earlier figure in this docstring --
"about 1335 scored mentions a day ... roughly twenty cents" -- was 5x low on
volume and 6x low on cost, because it counted the mentions a day's BUCKETS
carry rather than the mentions the pass is handed. spec 6.11's own estimate
("order of 150k input tokens/day, cents") is wrong by the same factor.

No daily ceiling. PASS_LIMIT caps one pass at 400 and the pass runs every ten
minutes, so the theoretical maximum is 57,600 mentions a day against an
observed 6,880 -- the ceiling that matters is how many mentions ingest
produces, and a spend cap would silently stop reading tone rather than
signalling that something upstream had changed. The figure is on the board;
watch it there.
```

- [ ] **Step 2: Verify nothing else asserts the old numbers**

```bash
grep -rn "twenty cents\|1335" personal_apps/
```

Expected: no remaining hits outside the corrected docstring.

- [ ] **Step 3: Commit**

```bash
git add personal_apps/features/radar/llm_sentiment.py
git commit -m "docs(radar): the tone pass costs six times what the docstring claimed"
```

---

# Stage 5 — Operational

## Task 18: The discovery script stops fighting the daemon

**Files:**
- Modify: `personal_apps/scripts/discover_reddit_sources.py`

**Interfaces:**
- Consumes: nothing.
- Produces: a `--anyway` flag; without it the script exits non-zero when `radar_ingest` is running.

The script polls the same `/comments/.rss` feeds at `SLEEP = 45.0`. The daemon polls one feed per 120 seconds against a budget measured at `x-ratelimit-remaining = 0.0` after a single request. From one IP they 429 each other, and the daemon's cycle then reports `missing` and writes no buckets.

- [ ] **Step 1: Add the guard**

In `personal_apps/scripts/discover_reddit_sources.py`, above `main()`:

```python
def _daemon_is_running():
    """True when radar_ingest holds the Reddit budget.

    Reddit's anonymous feed budget is per IP and is one request per window --
    `x-ratelimit-remaining` reads 0.0 after a single call, measured on the VPS
    2026-08-25. This script asks every 45 seconds and the daemon every 120, so
    run together they refuse each other, and the daemon's cycle then reports
    `missing` and writes no buckets at all. Nothing else coordinates them.

    systemctl only exists where the daemon is deployed. Anywhere else the
    answer is no, which is right: a dev machine is not sharing the budget.
    """
    import shutil
    import subprocess

    if shutil.which('systemctl') is None:
        return False
    result = subprocess.run(['systemctl', 'is-active', 'radar_ingest'],
                            capture_output=True, text=True)
    return result.stdout.strip() == 'active'
```

and in `main()`, immediately after parsing arguments:

```python
    if _daemon_is_running() and not args.anyway:
        print('radar_ingest is running and shares this IP\'s Reddit budget --\n'
              'one request per window, so the two will refuse each other and\n'
              'the daemon will write no buckets while this runs.\n\n'
              'Stop it first:  systemctl stop radar_ingest\n'
              'Or override:    --anyway', file=sys.stderr)
        return 1
```

Add the flag to the parser:

```python
    parser.add_argument('--anyway', action='store_true',
                        help='run even while radar_ingest holds the budget')
```

and make `main()`'s return value the process exit code:

```python
if __name__ == '__main__':
    sys.exit(main() or 0)
```

- [ ] **Step 2: Verify the guard is inert locally**

```bash
python -c "import sys; sys.path.insert(0,'.'); from scripts.discover_reddit_sources import _daemon_is_running; print(_daemon_is_running())"
```

Expected: `False` on Windows, where `systemctl` does not exist.

- [ ] **Step 3: Commit**

```bash
git add personal_apps/scripts/discover_reddit_sources.py
git commit -m "fix(radar): the discovery script no longer 429s the daemon it shares an IP with"
```

---

## Task 19: Prune the journal

**Files:**
- Modify: `personal_apps/features/radar/retention.py`
- Modify: `personal_apps/run_radar_ingest.py` (`_scheduled_prune`)
- Modify: `personal_apps/tests/test_radar_retention.py`

**Interfaces:**
- Consumes: `config.MENTION_EVENT_RETENTION_HOURS` (Task 1), `models.RadarMentionEvent`.
- Produces: `retention.prune_mention_events(now, chunk_size=5000, pause=...)` -> `int`.

- [ ] **Step 1: Write the failing test**

Append to `personal_apps/tests/test_radar_retention.py`:

```python
def test_the_journal_is_pruned_by_when_the_post_was_written(clean_events):
    """By created_utc, not by when the row was inserted. A catch-up after an
    outage ingests posts hours old, and once their bucket is past the retention
    window nothing will rewrite it -- so that is what decides."""
    import datetime as dt

    from extensions import db
    from features.radar import retention
    from models import RadarMentionEvent

    now = dt.datetime(2026, 4, 20, 12, 0, 0)
    for hours, ident in ((1, 'zz-new'), (72, 'zz-old')):
        created = now - dt.timedelta(hours=hours)
        db.session.add(RadarMentionEvent(
            source='bluesky', external_id=ident, ticker='ZZA',
            created_utc=created,
            bucket_start=created.replace(minute=0, second=0, microsecond=0),
            author='u1', simhash=1, confidence='high',
            sentiment=None, engagement=0.0))
    db.session.commit()

    assert retention.prune_mention_events(now) == 1
    remaining = [e.external_id for e in
                 RadarMentionEvent.query.filter_by(ticker='ZZA').all()]
    assert remaining == ['zz-new']
```

- [ ] **Step 2: Run it to verify it fails**

```bash
python -m pytest tests/test_radar_retention.py::test_the_journal_is_pruned_by_when_the_post_was_written -v
```

Expected: `AttributeError: module 'features.radar.retention' has no attribute 'prune_mention_events'`.

- [ ] **Step 3: Add the pruner**

In `personal_apps/features/radar/retention.py`, add `RadarMentionEvent` to the models import, `MENTION_EVENT_RETENTION_HOURS` to the config import, and:

```python
def prune_mention_events(now, chunk_size=5000, pause=_CHUNK_PAUSE_SECONDS):
    """Delete journal rows whose bucket can no longer be rewritten.

    By created_utc rather than by insertion time. A catch-up after an outage
    ingests posts hours old, and what decides is when the POST was written --
    once its quarter-hour is past the window, no cycle will touch that bucket
    again and the events behind it have nothing left to answer.

    Returns the number deleted.
    """
    cutoff = now - dt.timedelta(hours=MENTION_EVENT_RETENTION_HOURS)
    total = 0

    while True:
        ids = [
            row_id for (row_id,) in
            db.session.query(RadarMentionEvent.id)
            .filter(RadarMentionEvent.created_utc < cutoff)
            .order_by(RadarMentionEvent.created_utc)
            .limit(chunk_size).all()
        ]
        if not ids:
            break

        db.session.query(RadarMentionEvent).filter(
            RadarMentionEvent.id.in_(ids)).delete(synchronize_session=False)
        db.session.commit()
        total += len(ids)
        if pause:
            time.sleep(pause)

    return total
```

- [ ] **Step 4: Schedule it**

In `personal_apps/run_radar_ingest.py`, `_scheduled_prune`:

```python
        events = retention.prune_mention_events(now)
        if events:
            logger.info('radar retention pruned %d mention events', events)
```

- [ ] **Step 5: Run it to verify it passes**

```bash
python -m pytest tests/test_radar_retention.py tests/test_radar_daemon.py -v
```

Expected: all pass.

- [ ] **Step 6: Full suite and build**

```bash
python -m pytest tests/ -v && npm run build
```

Expected: everything green.

- [ ] **Step 7: Commit**

```bash
git add personal_apps/features/radar/retention.py personal_apps/run_radar_ingest.py personal_apps/tests/test_radar_retention.py
git commit -m "feat(radar): prune the mention journal at forty-eight hours"
```

---

## Not in this plan

**Rendering `tone` on the board row** (spec §2.11). The payload already carries it and `TickerRow` draws nothing. That is visual work and goes through the `impeccable` skill in its own cycle, after this plan lands — green and red stay reserved for price direction, so tone needs an encoding of its own that a plan cannot specify.

**Retiring 4chan.** It works — cursor advancing, posts across the window — but produces 20 stored posts in 4.5 days because `COIN_SYMBOLS_MEAN_STOCKS['fourchan'] = False` drops /biz/'s whole vocabulary, while costing 147,763 zero rows and 66,153 rescored rows every fifteen minutes. Whether /biz/ is worth having at all is a judgement, not a defect, and it was raised and left open.

---

## Verification before calling this done

The trap from prior work applies: **an assertion whose passing state is an absence proves nothing until it has been shown to fail.** Before the final merge, run each of these against the code as it was *before* its own task, and confirm it fails:

- `test_a_second_poll_inside_one_bucket_does_not_erase_the_first` (Task 2)
- `test_a_downgrade_to_truncated_clears_the_stale_score` (Task 3)
- `test_a_promoted_mention_counts_towards_the_author_floor` (Task 3b)
- `test_the_breadth_filter_reports_what_it_removed` (Task 13)
- `test_every_config_member_is_reachable` (Task 5)
- `test_a_feed_that_parses_to_nothing_reports_no_rate` (Task 10)
- `test_a_failed_fetch_reports_no_catchup_depth` (Task 10)
- `test_an_unpriced_model_costs_null_not_nothing` (Task 11)
- `test_an_outage_in_the_middle_of_the_window_is_not_drawn_as_quiet` (Task 12)

`git stash` the task's source change, run the test, confirm the failure message names the real defect, restore.

Then, on `dev_personal`:

```bash
python -m pytest tests/ -v
```

and merge to `main` and push both branches.

After Michi deploys, run the backfill against production:

```bash
python -m scripts.backfill_radar_buckets
```

then again with `--apply` once the dry-run count looks right.
