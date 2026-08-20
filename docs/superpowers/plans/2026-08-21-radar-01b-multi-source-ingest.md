# Radar Plan 1b — Multi-Source Ingest

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the dead Reddit source with StockTwits, Bluesky and 4chan /biz/ as equal peers, behind a schema that supports an open set of sources and a UI that selects among them.

**Architecture:** Plan 1's pipeline is kept whole. Per-source data moves out of hardcoded columns into a `radar_bucket_sources` child table so the source set is open and any subset can be pooled at read time. Three source modules implement the existing `FetchResult` contract — two by polling, one by draining a websocket firehose in batches — and a per-symbol scheduler derives each symbol's poll interval from its own measured message rate.

**Tech Stack:** Python 3.12, Flask-SQLAlchemy, MySQL 8 (dev) / MariaDB (prod), APScheduler, `requests`, `websockets` (already installed), pytest.

**Spec:** `docs/superpowers/specs/2026-08-20-radar-social-sentiment-design.md` (revision 3)
**Predecessor:** `docs/superpowers/plans/2026-08-20-radar-01-foundation-ingest.md` (Tasks 1–11 complete, 104 tests green)

## Global Constraints

- **No source is privileged.** Nothing outside `sources/` and `config.py` may name a specific source. Any code branching on `source == 'stocktwits'` outside a source module is a defect.
- **`missing` ≠ zero**, still and always (spec §4.5). This plan adds a third way to violate it — Jetstream's silent cursor clamp — and Task 4 exists largely to catch it.
- **Crypto is excluded entirely** (spec §3.7). No segment, no tab. StockTwits exposes `instrument_class == 'CRYPTO'`; use the field, not an `.X` suffix guess.
- **`low` confidence is stored, never scored** (spec §4.2). Promotion to `medium` happens at rollup only.
- **All datetimes UTC**, `DATETIME(6)`, `TIMESTAMP` prohibited (spec §5.5.4).
- **No live network calls in tests** (spec §10). Every source is driven by a fake client or canned payload.
- **No scoring in this plan.** `expected`, `variance`, `mention_z`, `baseline_days` columns are created nullable and left NULL for Plan 2.
- Working directory for every command: `C:\Users\michi\Desktop\CodingStuff\personal_apps`. Tests via `python -m pytest`.

---

## File Structure

**Create:**

| Path | Responsibility |
|---|---|
| `features/radar/sources/stocktwits.py` | Trending + per-symbol streams, crypto filter |
| `features/radar/sources/bluesky.py` | Jetstream batch drain, clamp detection |
| `features/radar/sources/fourchan.py` | Catalog + thread fetch at 1 req/sec |
| `features/radar/scheduling.py` | Per-symbol poll intervals from measured rate |
| `tests/test_radar_bucket_sources.py`, `tests/test_radar_stocktwits.py`, `tests/test_radar_bluesky.py`, `tests/test_radar_fourchan.py`, `tests/test_radar_scheduling.py` | |

**Modify:** `models.py`, `features/radar/buckets.py`, `features/radar/ingest.py`, `features/radar/sources/__init__.py`, `features/radar/config.py`, `run_radar_ingest.py`, `tests/test_radar_buckets.py`, `tests/test_radar_ingest.py`

**Delete:** `features/radar/sources/reddit.py`, `tests/test_radar_reddit_source.py`

---

## Task 1: `radar_bucket_sources`

**Files:**
- Modify: `personal_apps/models.py`
- Create: `personal_apps/migrations/versions/<hash>_add_radar_bucket_sources.py`
- Test: `personal_apps/tests/test_radar_bucket_sources.py`

**Interfaces:**
- Produces: `models.RadarBucketSource`; `RadarBucket` loses its per-source columns and keeps `sources_ok`, `source_config_version` and the all-sources totals.

- [ ] **Step 1: Write the failing test**

```python
# personal_apps/tests/test_radar_bucket_sources.py
"""Per-source data in rows, not columns.

Two sources meant eight columns. Three makes twelve, and a UI that lets the
user pick a subset has to pool whichever ones they chose -- which columns named
after specific sources cannot express at all (spec 4.5, 8.6).
"""
import datetime as dt

import pytest
import sqlalchemy as sa

from app import app as flask_app
from extensions import db
from models import RadarBucket, RadarBucketSource

START = dt.datetime(2026, 8, 21, 14, 0, 0)


@pytest.fixture()
def ctx():
    with flask_app.app_context():
        RadarBucketSource.query.filter(
            RadarBucketSource.ticker.like('ZZ%')).delete(synchronize_session=False)
        RadarBucket.query.filter(
            RadarBucket.ticker.like('ZZ%')).delete(synchronize_session=False)
        db.session.commit()
        yield
        RadarBucketSource.query.filter(
            RadarBucketSource.ticker.like('ZZ%')).delete(synchronize_session=False)
        RadarBucket.query.filter(
            RadarBucket.ticker.like('ZZ%')).delete(synchronize_session=False)
        db.session.commit()


def _row(source='stocktwits', ticker='ZZA', count=3, status='ok'):
    return RadarBucketSource(
        ticker=ticker, bucket_start=START, source=source,
        mention_count=count, high_confidence_count=count, low_count=0,
        distinct_authors=count, distinct_text_ratio=1.0,
        engagement_weighted_count=float(count), sentiment_mean=0.1,
        sentiment_stdev=None, status=status)


def test_one_row_per_source_for_the_same_bucket(ctx):
    for source in ('stocktwits', 'bluesky', 'fourchan'):
        db.session.add(_row(source=source))
    db.session.commit()
    assert RadarBucketSource.query.filter_by(ticker='ZZA').count() == 3


def test_the_same_source_twice_in_one_bucket_is_rejected(ctx):
    db.session.add(_row())
    db.session.commit()
    db.session.add(_row(count=99))
    with pytest.raises(sa.exc.IntegrityError):
        db.session.commit()
    db.session.rollback()


def test_an_arbitrary_subset_pools_by_group_by(ctx):
    """The whole reason this table exists. The UI selector picks sources and
    the query sums over exactly those -- no schema knows their names."""
    db.session.add(_row(source='stocktwits', count=10))
    db.session.add(_row(source='bluesky', count=4))
    db.session.add(_row(source='fourchan', count=1))
    db.session.commit()

    chosen = ['stocktwits', 'bluesky']
    total = db.session.query(
        sa.func.sum(RadarBucketSource.mention_count)).filter(
        RadarBucketSource.ticker == 'ZZA',
        RadarBucketSource.bucket_start == START,
        RadarBucketSource.source.in_(chosen)).scalar()
    assert total == 14


def test_a_source_can_be_missing_while_another_is_ok(ctx):
    db.session.add(_row(source='stocktwits', status='ok'))
    db.session.add(_row(source='bluesky', status='truncated'))
    db.session.commit()
    statuses = {r.source: r.status for r in
                RadarBucketSource.query.filter_by(ticker='ZZA').all()}
    assert statuses == {'stocktwits': 'ok', 'bluesky': 'truncated'}


def test_low_confidence_is_counted_separately_from_scored(ctx):
    """low is stored but never scored (spec 4.2). Keeping the count is what
    lets the extractor's false-positive rate be measured against real data."""
    row = _row(count=5)
    row.low_count = 40
    db.session.add(row)
    db.session.commit()
    db.session.expire(row)
    assert row.mention_count == 5
    assert row.low_count == 40


def test_scoring_columns_start_null(ctx):
    db.session.add(_row())
    db.session.commit()
    row = RadarBucketSource.query.filter_by(ticker='ZZA').one()
    assert row.expected is None
    assert row.variance is None
    assert row.mention_z is None
    assert row.baseline_days is None


def test_the_parent_bucket_no_longer_has_per_source_columns(ctx):
    """A leftover count_reddit would be dead weight that some query eventually
    reads and quietly trusts."""
    for gone in ('count_reddit', 'count_stocktwits', 'status_reddit',
                 'status_stocktwits', 'mention_z_reddit', 'mention_z_stocktwits',
                 'baseline_days_reddit', 'baseline_days_stocktwits'):
        assert not hasattr(RadarBucket, gone), '%s should be gone' % gone


def test_the_parent_bucket_keeps_its_totals(ctx):
    for kept in ('mention_count', 'distinct_authors', 'sources_ok',
                 'source_config_version'):
        assert hasattr(RadarBucket, kept)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_radar_bucket_sources.py -v`
Expected: FAIL with `ImportError: cannot import name 'RadarBucketSource' from 'models'`

- [ ] **Step 3: Write minimal implementation**

Add to `personal_apps/models.py`, after `RadarBucket`:

```python
class RadarBucketSource(db.Model):
    """(ticker x bucket x source). What makes the source set open.

    Per-source data lived in columns named after specific sources until three
    sources and a UI selector made that untenable: a user-chosen subset has to
    be pooled at query time, and `count_stocktwits` cannot participate in that.

    expected and variance sit here beside mention_z because pooling a subset
    means summing components -- a weighted mean of z-scores is not a z-score
    (spec 6.2). Both are written by Plan 2 and are NULL until then.

    No foreign key to radar_buckets: InnoDB does not support foreign keys on
    partitioned tables and radar_buckets is partitioned monthly. This table is
    partitioned identically and joined on (ticker, bucket_start), which means
    retention and partition maintenance must treat the pair as one unit --
    nothing enforces it for us.
    """
    __tablename__ = 'radar_bucket_sources'
    __table_args__ = (
        db.Index('ix_radar_bucket_sources_start', 'bucket_start', 'source'),
        {'mysql_charset': 'utf8mb4'},
    )

    ticker                    = db.Column(db.String(12, collation='utf8mb4_bin'),
                                          primary_key=True)
    bucket_start              = db.Column(MYSQL_DATETIME(fsp=6), primary_key=True)
    source                    = db.Column(db.String(24), primary_key=True)

    mention_count             = db.Column(db.Integer, nullable=False, default=0)
    high_confidence_count     = db.Column(db.Integer, nullable=False, default=0)
    low_count                 = db.Column(db.Integer, nullable=False, default=0)
    distinct_authors          = db.Column(db.Integer, nullable=False, default=0)
    distinct_text_ratio       = db.Column(db.Float, nullable=False, default=1.0)
    engagement_weighted_count = db.Column(db.Float, nullable=False, default=0.0)
    sentiment_mean            = db.Column(db.Float, nullable=True)
    sentiment_stdev           = db.Column(db.Float, nullable=True)

    status                    = db.Column(
        db.Enum('ok', 'missing', 'truncated', name='radar_source_status'),
        nullable=False, default='missing')

    # Written by Plan 2.
    expected                  = db.Column(db.Float, nullable=True)
    variance                  = db.Column(db.Float, nullable=True)
    mention_z                 = db.Column(db.Float, nullable=True)
    baseline_days             = db.Column(db.SmallInteger, nullable=True)
```

Delete these eight columns from `RadarBucket`, and add `low_count`:

```python
    # (delete) count_reddit, count_stocktwits, status_reddit, status_stocktwits,
    #          mention_z_reddit, mention_z_stocktwits,
    #          baseline_days_reddit, baseline_days_stocktwits
    low_count                 = db.Column(db.Integer, nullable=False, default=0)
```

Generate the migration:

```bash
python -m flask --app app db migrate -m "add radar bucket sources"
```

Review the generated file. Autogenerate will emit the `create_table` and the eight `drop_column` calls. Delete anything it emits against non-radar tables. Then append the partition statement, which it cannot autogenerate:

```python
    op.execute("""
        ALTER TABLE radar_bucket_sources
        PARTITION BY RANGE (TO_DAYS(bucket_start)) (
            PARTITION p_2026_08 VALUES LESS THAN (TO_DAYS('2026-09-01')),
            PARTITION p_2026_09 VALUES LESS THAN (TO_DAYS('2026-10-01')),
            PARTITION p_2026_10 VALUES LESS THAN (TO_DAYS('2026-11-01')),
            PARTITION p_2026_11 VALUES LESS THAN (TO_DAYS('2026-12-01')),
            PARTITION p_2026_12 VALUES LESS THAN (TO_DAYS('2027-01-01')),
            PARTITION p_max VALUES LESS THAN MAXVALUE
        )
    """)
```

The primary key already contains `bucket_start`, which is what makes this legal — MySQL and MariaDB both require every unique key to contain every partitioning column.

- [ ] **Step 4: Apply and verify**

```bash
python -m flask --app app db upgrade
```

Run: `python -m pytest tests/test_radar_bucket_sources.py -v`
Expected: 8 passed

- [ ] **Step 5: Commit**

```bash
git add personal_apps/models.py personal_apps/migrations/versions/ personal_apps/tests/test_radar_bucket_sources.py
git commit -m "feat(radar): move per-source data into rows so the source set can grow"
```

---

## Task 2: Rollup writes per-source rows and awards `medium`

**Files:**
- Modify: `personal_apps/features/radar/buckets.py`
- Modify: `personal_apps/tests/test_radar_buckets.py`

**Interfaces:**
- Consumes: `models.RadarBucketSource`
- Produces: `roll_up(rows, statuses, touched) -> int` — unchanged signature; `statuses` is now `{source_name: status}` for any set of sources

- [ ] **Step 1: Write the failing test**

Append to `personal_apps/tests/test_radar_buckets.py`:

```python
def test_per_source_rows_are_written(clean_buckets):
    from models import RadarBucketSource
    rows = [row(source='stocktwits', author='u1', simhash=1),
            row(source='bluesky', author='u2', simhash=2)]
    buckets.roll_up(rows, {'stocktwits': 'ok', 'bluesky': 'ok'},
                    {dt.datetime(2026, 4, 15, 14, 0, 0)})
    per_source = {r.source: r.mention_count for r in
                  RadarBucketSource.query.filter_by(ticker='ZZA').all()}
    assert per_source == {'stocktwits': 1, 'bluesky': 1}
    assert RadarBucket.query.filter_by(ticker='ZZA').one().mention_count == 2


def test_an_unknown_source_name_needs_no_schema_change(clean_buckets):
    """The point of the child table. A source nobody has heard of writes a row
    like any other -- no migration, no column, no code that knows its name."""
    from models import RadarBucketSource
    buckets.roll_up([row(source='some_new_source')],
                    {'some_new_source': 'ok'},
                    {dt.datetime(2026, 4, 15, 14, 0, 0)})
    assert RadarBucketSource.query.filter_by(
        ticker='ZZA', source='some_new_source').one().mention_count == 1


def test_a_low_mention_is_promoted_by_another_authors_cashtag(clean_buckets):
    """Corroboration. Someone writing $ZZA vouches for someone else writing
    bare ZZA in the same window, so the bare one becomes scored."""
    rows = [row(confidence='low', author='u1', simhash=1),
            row(confidence='high', author='u2', simhash=2)]
    buckets.roll_up(rows, ALL_OK, {dt.datetime(2026, 4, 15, 14, 0, 0)})
    bucket = RadarBucket.query.filter_by(ticker='ZZA').one()
    assert bucket.mention_count == 2      # both scored
    assert bucket.low_count == 0


def test_the_same_author_cannot_corroborate_themselves(clean_buckets):
    """One person writing both ZZA and $ZZA is one opinion, not two."""
    rows = [row(confidence='low', author='u1', simhash=1),
            row(confidence='high', author='u1', simhash=2)]
    buckets.roll_up(rows, ALL_OK, {dt.datetime(2026, 4, 15, 14, 0, 0)})
    bucket = RadarBucket.query.filter_by(ticker='ZZA').one()
    assert bucket.mention_count == 1      # only the high one
    assert bucket.low_count == 1


def test_uncorroborated_lows_are_stored_but_not_scored(clean_buckets):
    rows = [row(confidence='low', author='u%d' % i, simhash=i) for i in range(4)]
    buckets.roll_up(rows, ALL_OK, {dt.datetime(2026, 4, 15, 14, 0, 0)})
    bucket = RadarBucket.query.filter_by(ticker='ZZA').one()
    assert bucket.mention_count == 0
    assert bucket.low_count == 4


def test_a_bucket_with_only_lows_still_records_its_source_status(clean_buckets):
    """The source was healthy and saw nothing scorable. That is a real zero,
    and it must stay distinguishable from the source being down."""
    from models import RadarBucketSource
    buckets.roll_up([row(confidence='low')], ALL_OK,
                    {dt.datetime(2026, 4, 15, 14, 0, 0)})
    assert RadarBucketSource.query.filter_by(
        ticker='ZZA', source='reddit').one().status == 'ok'
```

Change the module's `row()` helper default so `source` is a parameter — it already is — and update `ALL_OK` to reflect the new source set:

```python
ALL_OK = {'reddit': 'ok'}
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_radar_buckets.py -v`
Expected: FAIL — `test_per_source_rows_are_written` errors on `RadarBucketSource` having no rows

- [ ] **Step 3: Write minimal implementation**

Replace `_summarize` and `roll_up` in `personal_apps/features/radar/buckets.py`:

```python
def _promote(rows):
    """Award `medium` to bare mentions another author has cashtagged.

    A `low` is an uncorroborated bare token -- measured at roughly 85% false
    positives against the real universe, which is why it is never scored on its
    own. A `high` from a DIFFERENT author in the same bucket is what vouches
    for it. The same person writing both ZZA and $ZZA is one opinion twice, not
    corroboration, which is why the author must differ.

    Returns a new list; the input is not mutated.
    """
    vouchers = collections.defaultdict(set)
    for row in rows:
        if row.confidence == 'high' and row.author:
            vouchers[row.ticker].add(row.author)

    promoted = []
    for row in rows:
        if row.confidence == 'low' and (vouchers[row.ticker] - {row.author}):
            promoted.append(dataclasses.replace(row, confidence='medium'))
        else:
            promoted.append(row)
    return promoted


# Confidences that count toward a score. `low` is stored and excluded.
_SCORED = {'high', 'medium'}


def _summarize(rows):
    scored = [r for r in rows if r.confidence in _SCORED]
    authors = {r.author for r in scored if r.author}
    hashes = {r.simhash for r in scored}
    sentiments = [r.sentiment for r in scored if r.sentiment is not None]

    return {
        'mention_count': len(scored),
        'high_confidence_count': sum(1 for r in scored if r.confidence == 'high'),
        'low_count': sum(1 for r in rows if r.confidence == 'low'),
        'distinct_authors': len(authors),
        'distinct_text_ratio': (len(hashes) / len(scored)) if scored else 1.0,
        'engagement_weighted_count': sum(r.engagement for r in scored),
        'sentiment_mean': (sum(sentiments) / len(sentiments)) if sentiments else None,
        'sentiment_stdev': (statistics.pstdev(sentiments)
                            if len(sentiments) > 1 else None),
    }


def roll_up(rows, statuses, touched):
    """Write bucket totals and per-source rows for `touched` windows.

    statuses maps source name to 'ok' | 'missing' | 'truncated'. The set of
    source names is open -- nothing here knows or cares which they are.
    """
    countable = {source for source, status in statuses.items()
                 if status in _COUNTABLE}
    if not countable:
        return 0

    version = source_config_version()
    sources_ok = sum(1 for status in statuses.values() if status == 'ok')

    usable = [r for r in rows if r.source in countable]
    grouped = collections.defaultdict(list)
    for row in _promote(usable):
        grouped[(row.ticker, bucket_start_for(row.created_utc))].append(row)

    written = 0
    for (ticker, start), bucket_rows in grouped.items():
        if start not in touched:
            continue

        totals = _summarize(bucket_rows)
        bucket = RadarBucket.query.filter_by(
            ticker=ticker, bucket_start=start).one_or_none()
        if bucket is None:
            bucket = RadarBucket(ticker=ticker, bucket_start=start)
            db.session.add(bucket)
        for field, value in totals.items():
            setattr(bucket, field, value)
        bucket.sources_ok = sources_ok
        bucket.source_config_version = version

        by_source = collections.defaultdict(list)
        for row in bucket_rows:
            by_source[row.source].append(row)

        for source in countable:
            per = _summarize(by_source.get(source, []))
            child = RadarBucketSource.query.filter_by(
                ticker=ticker, bucket_start=start, source=source).one_or_none()
            if child is None:
                child = RadarBucketSource(ticker=ticker, bucket_start=start,
                                          source=source)
                db.session.add(child)
            for field, value in per.items():
                setattr(child, field, value)
            child.status = statuses[source]

        written += 1

    db.session.commit()
    return written
```

Fix the imports at the top of `buckets.py` — `_promote` uses `collections`,
which the module does not currently import, and `RadarBucketSource` is new:

```python
import collections
import dataclasses
import datetime as dt
import statistics

from extensions import db
from models import RadarBucket, RadarBucketSource
```

Delete the now-unused `SOURCES` tuple from `buckets.py`. `sources_ok` is
counted from `statuses` instead, which is what makes the source set open.

- [ ] **Step 4: Run tests**

Run: `python -m pytest tests/test_radar_buckets.py -v`
Expected: 17 passed

- [ ] **Step 5: Commit**

```bash
git add personal_apps/features/radar/buckets.py personal_apps/tests/test_radar_buckets.py
git commit -m "feat(radar): let one author's cashtag vouch for another's bare mention"
```

---

## Task 3: StockTwits source

**Files:**
- Create: `personal_apps/features/radar/sources/stocktwits.py`
- Test: `personal_apps/tests/test_radar_stocktwits.py`

**Interfaces:**
- Produces: `fetch(since, client, symbols) -> FetchResult`; `trending(client) -> list[str]`; `StockTwitsClient` with `get(path) -> dict`

- [ ] **Step 1: Write the failing test**

```python
# personal_apps/tests/test_radar_stocktwits.py
"""StockTwits: finance-native, dense, and narrow.

Measured at ~23 messages/hour on a trending symbol with 20-27 distinct authors
per 30 messages. Its discovery surface is only the 30 trending symbols, which
is why the standing set exists (spec 3.5).
"""
import datetime as dt

from features.radar.sources import FetchResult
from features.radar.sources import stocktwits


class FakeClient:
    def __init__(self, payloads):
        self.payloads = payloads
        self.calls = []

    def get(self, path, params=None):
        self.calls.append(path)
        if path not in self.payloads:
            raise stocktwits.StockTwitsUnavailable('404 %s' % path)
        return self.payloads[path]


def _message(ident, created, body='$ZZA to the moon', user=1, sentiment='Bullish'):
    return {
        'id': ident,
        'body': body,
        'created_at': created.strftime('%Y-%m-%dT%H:%M:%SZ'),
        'user': {'id': user, 'username': 'user%d' % user},
        'symbols': [{'symbol': 'ZZA'}],
        'entities': {'sentiment': {'basic': sentiment}} if sentiment else {},
        'likes': {'total': 3},
    }


BASE = dt.datetime(2026, 8, 21, 14, 0, 0)


def test_trending_filters_crypto_by_instrument_class():
    """instrument_class is explicit, so the filter is a field check rather than
    a guess at what .X means (spec 3.7)."""
    client = FakeClient({'/trending/symbols.json': {'symbols': [
        {'symbol': 'ZZA', 'instrument_class': 'Stock'},
        {'symbol': 'BTC.X', 'instrument_class': 'CRYPTO'},
        {'symbol': 'ZZB', 'instrument_class': 'Stock'},
    ]}})
    assert stocktwits.trending(client) == ['ZZA', 'ZZB']


def test_a_stream_becomes_rawposts():
    client = FakeClient({'/streams/symbol/ZZA.json': {
        'messages': [_message(2, BASE), _message(1, BASE - dt.timedelta(minutes=5))]}})
    result = stocktwits.fetch(BASE - dt.timedelta(hours=1), client, ['ZZA'])
    assert isinstance(result, FetchResult)
    assert result.status == 'ok'
    assert len(result.posts) == 2
    post = result.posts[0]
    assert post.source == 'stocktwits'
    assert post.external_id == 'stocktwits:2'
    assert post.native_tickers == ['ZZA']
    assert post.native_sentiment == 'Bullish'
    assert post.author == 'user1'


def test_messages_older_than_since_are_dropped():
    client = FakeClient({'/streams/symbol/ZZA.json': {'messages': [
        _message(2, BASE),
        _message(1, BASE - dt.timedelta(hours=4)),
    ]}})
    result = stocktwits.fetch(BASE - dt.timedelta(hours=1), client, ['ZZA'])
    assert [p.external_id for p in result.posts] == ['stocktwits:2']


def test_a_full_page_of_new_messages_is_truncated():
    """30 is the page size. All 30 newer than `since` means there are probably
    more we did not see, and an undercount must never reach a baseline."""
    messages = [_message(i, BASE - dt.timedelta(seconds=i)) for i in range(30)]
    client = FakeClient({'/streams/symbol/ZZA.json': {'messages': messages}})
    result = stocktwits.fetch(BASE - dt.timedelta(hours=1), client, ['ZZA'])
    assert result.status == 'truncated'
    assert len(result.posts) == 30


def test_one_symbol_failing_does_not_lose_the_others():
    client = FakeClient({'/streams/symbol/ZZA.json': {'messages': [_message(1, BASE)]}})
    result = stocktwits.fetch(BASE - dt.timedelta(hours=1), client, ['ZZA', 'MISSING'])
    assert [p.external_id for p in result.posts] == ['stocktwits:1']
    assert result.status == 'truncated'


def test_every_symbol_failing_is_missing_with_no_posts():
    client = FakeClient({})
    result = stocktwits.fetch(BASE - dt.timedelta(hours=1), client, ['ZZA', 'ZZB'])
    assert result.status == 'missing'
    assert result.posts == []


def test_message_rate_is_reported_per_symbol():
    """The scheduler derives each symbol's poll interval from this, because the
    API returns 30 messages whatever their timespan (spec 3.5)."""
    messages = [_message(i, BASE - dt.timedelta(minutes=i * 2)) for i in range(30)]
    client = FakeClient({'/streams/symbol/ZZA.json': {'messages': messages}})
    result = stocktwits.fetch(BASE - dt.timedelta(hours=6), client, ['ZZA'])
    # 30 messages spanning 58 minutes -> a bit over 30/hour.
    assert 25 < result.rates['ZZA'] < 40


def test_an_empty_stream_is_ok_not_missing():
    """A healthy source that saw nothing is a real zero. Only a failure is
    `missing` (spec 4.5)."""
    client = FakeClient({'/streams/symbol/ZZA.json': {'messages': []}})
    result = stocktwits.fetch(BASE - dt.timedelta(hours=1), client, ['ZZA'])
    assert result.status == 'ok'
    assert result.posts == []
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_radar_stocktwits.py -v`
Expected: FAIL with `ImportError: cannot import name 'stocktwits'`

- [ ] **Step 3: Extend `FetchResult`, then write the source**

`FetchResult` gains two fields. Replace the dataclass in `personal_apps/features/radar/sources/__init__.py`:

```python
@dataclasses.dataclass
class FetchResult:
    posts: list
    status: str                      # 'ok' | 'missing' | 'truncated'
    catchup_depth: int = 0
    # Earliest instant this fetch actually covers. Anything the caller asked
    # for before this was not delivered -- Jetstream clamps a too-old cursor
    # silently, and a caller that assumed otherwise would carry a hole it
    # believed was complete. None means the full requested range was covered.
    covered_since: object = None
    # Observed messages/hour per symbol, for the poll scheduler. Empty for
    # sources that are not polled per symbol.
    rates: dict = dataclasses.field(default_factory=dict)
```

```python
# personal_apps/features/radar/sources/stocktwits.py
"""StockTwits ingest.

Finance-native and dense -- messages arrive already $TICKER-tagged and about
half carry a native bull/bear label -- but narrow: the discovery surface is the
30 trending symbols, so the standing set in the scheduler is what widens it.

Crypto is dropped here rather than downstream, using the explicit
instrument_class field rather than guessing at the .X suffix (spec 3.7).
"""
import datetime as dt

import requests

from . import FetchResult, RawPost

API_BASE = 'https://api.stocktwits.com/api/2'
USER_AGENT_DEFAULT = 'personal_apps-radar/0.1 (personal research)'

# The API returns at most this many messages per stream call. A full page of
# messages newer than `since` means there were probably more we never saw.
PAGE_SIZE = 30


class StockTwitsUnavailable(Exception):
    """This symbol's stream did not arrive. Never turns into a zero count."""


class StockTwitsClient:
    def __init__(self, user_agent=USER_AGENT_DEFAULT, timeout=25):
        self._headers = {'User-Agent': user_agent}
        self._timeout = timeout

    def get(self, path, params=None):
        try:
            response = requests.get(API_BASE + path, params=params,
                                    headers=self._headers, timeout=self._timeout)
            response.raise_for_status()
            return response.json()
        except (requests.RequestException, ValueError) as exc:
            raise StockTwitsUnavailable('%s: %s' % (path, exc)) from exc


def trending(client):
    """Trending equity symbols. Crypto is excluded by instrument_class."""
    payload = client.get('/trending/symbols.json')
    return [s['symbol'] for s in payload.get('symbols', [])
            if (s.get('instrument_class') or '').upper() != 'CRYPTO']


def _to_raw_post(message, symbol):
    created = dt.datetime.strptime(message['created_at'], '%Y-%m-%dT%H:%M:%SZ')
    user = message.get('user') or {}
    entities = message.get('entities') or {}
    sentiment = (entities.get('sentiment') or {}).get('basic')
    likes = (message.get('likes') or {}).get('total') or 0
    symbols = [s['symbol'] for s in (message.get('symbols') or [])] or [symbol]

    return RawPost(
        source='stocktwits',
        external_id='stocktwits:%s' % message['id'],
        channel=symbol,
        author=user.get('username'),
        created_utc=created,
        title=None,
        body=message.get('body') or '',
        score=int(likes),
        num_comments=0,
        url='https://stocktwits.com/message/%s' % message['id'],
        native_tickers=symbols,
        native_sentiment=sentiment,
    )


def fetch(since, client, symbols):
    """Every message newer than `since` across `symbols`.

    Also reports observed messages/hour per symbol, which is what lets the
    scheduler poll a hot symbol often and a quiet one rarely (spec 3.5).
    """
    posts, rates = [], {}
    failures = 0
    truncated = False

    for symbol in symbols:
        try:
            payload = client.get('/streams/symbol/%s.json' % symbol)
        except StockTwitsUnavailable:
            failures += 1
            continue

        messages = payload.get('messages') or []
        fresh = []
        for message in messages:
            post = _to_raw_post(message, symbol)
            if post.created_utc > since:
                fresh.append(post)

        if messages:
            stamps = [dt.datetime.strptime(m['created_at'], '%Y-%m-%dT%H:%M:%SZ')
                      for m in messages]
            span = (max(stamps) - min(stamps)).total_seconds() / 3600
            rates[symbol] = (len(messages) / span) if span > 0 else float(len(messages))

        # A full page, all of it new, means the window very likely overflowed.
        if len(fresh) >= PAGE_SIZE:
            truncated = True

        posts.extend(fresh)

    if symbols and failures == len(symbols):
        return FetchResult(posts=[], status='missing')

    status = 'truncated' if (truncated or failures) else 'ok'
    return FetchResult(posts=posts, status=status, rates=rates)
```

- [ ] **Step 4: Run tests**

Run: `python -m pytest tests/test_radar_stocktwits.py -v`
Expected: 8 passed

- [ ] **Step 5: Commit**

```bash
git add personal_apps/features/radar/sources/ personal_apps/tests/test_radar_stocktwits.py
git commit -m "feat(radar): read StockTwits streams, and drop crypto by its own field"
```

---

## Task 4: Bluesky source

**Files:**
- Create: `personal_apps/features/radar/sources/bluesky.py`
- Test: `personal_apps/tests/test_radar_bluesky.py`

**Interfaces:**
- Produces: `fetch(since, drain) -> FetchResult` where `drain(cursor_us, budget) -> iterable[dict]` yields Jetstream events

- [ ] **Step 1: Write the failing test**

```python
# personal_apps/tests/test_radar_bluesky.py
"""Bluesky: the whole network, thinly.

144k posts/hour producing ~340 scored ticker mentions/hour spread market-wide.
Sparse per-ticker baselines are the point -- a ticker at 0.1 mentions/hour that
jumps to 20 is an enormous z-score, which is discovery the other sources cannot
do (spec 3.8).

The cursor clamp is what this suite mostly guards. Jetstream replays about 36
hours and silently gives you less than you asked for beyond that.
"""
import datetime as dt

from features.radar.sources import FetchResult
from features.radar.sources import bluesky


def _us(when):
    return int(when.replace(tzinfo=dt.timezone.utc).timestamp() * 1_000_000)


def _event(when, text='$ZZA looks strong', did='did:plc:abc', operation='create'):
    return {
        'did': did,
        'time_us': _us(when),
        'commit': {
            'operation': operation,
            'collection': 'app.bsky.feed.post',
            'rkey': 'r%d' % _us(when),
            'record': {'text': text, 'createdAt': when.isoformat() + 'Z'},
        },
    }


BASE = dt.datetime(2026, 8, 21, 14, 0, 0)


def drain_returning(events):
    def drain(cursor_us, budget):
        return list(events)
    return drain


def test_events_become_rawposts():
    result = bluesky.fetch(BASE - dt.timedelta(minutes=10),
                           drain_returning([_event(BASE)]))
    assert isinstance(result, FetchResult)
    assert result.status == 'ok'
    post = result.posts[0]
    assert post.source == 'bluesky'
    assert post.channel == 'firehose'
    assert post.body == '$ZZA looks strong'
    assert post.author == 'did:plc:abc'
    assert post.created_utc == BASE


def test_non_create_operations_are_ignored():
    """Deletes and updates arrive on the same stream. A delete has no text and
    counting it would inflate volume with events that are not posts."""
    events = [_event(BASE, operation='delete'), _event(BASE, operation='create')]
    result = bluesky.fetch(BASE - dt.timedelta(minutes=10), drain_returning(events))
    assert len(result.posts) == 1


def test_posts_with_no_text_are_skipped():
    empty = _event(BASE)
    empty['commit']['record']['text'] = ''
    result = bluesky.fetch(BASE - dt.timedelta(minutes=10), drain_returning([empty]))
    assert result.posts == []


def test_a_silently_clamped_cursor_is_reported_as_truncated():
    """The trap. Ask Jetstream for 48 hours and it returns events from 36 hours
    ago with no error. A caller trusting that would carry a 12-hour hole it
    believed was complete -- exactly the fake spike `missing` exists to stop.
    """
    since = BASE - dt.timedelta(hours=48)
    earliest = BASE - dt.timedelta(hours=36)
    result = bluesky.fetch(since, drain_returning([_event(earliest), _event(BASE)]))
    assert result.status == 'truncated'
    assert result.covered_since == earliest


def test_an_honoured_cursor_reports_full_coverage():
    since = BASE - dt.timedelta(hours=6)
    result = bluesky.fetch(since, drain_returning([
        _event(since + dt.timedelta(seconds=30)), _event(BASE)]))
    assert result.status == 'ok'
    assert result.covered_since is None


def test_a_small_gap_is_tolerated():
    """A quiet minute at the start of the window is not a clamp. The tolerance
    keeps an idle network from being reported as a permanent hole."""
    since = BASE - dt.timedelta(hours=6)
    result = bluesky.fetch(since, drain_returning([
        _event(since + dt.timedelta(minutes=2)), _event(BASE)]))
    assert result.status == 'ok'


def test_a_failed_drain_is_missing():
    def drain(cursor_us, budget):
        raise bluesky.JetstreamUnavailable('connection refused')
    result = bluesky.fetch(BASE - dt.timedelta(hours=1), drain)
    assert result.status == 'missing'
    assert result.posts == []


def test_no_events_at_all_is_missing_not_a_quiet_network():
    """144k posts/hour means silence is a broken connection, never calm."""
    result = bluesky.fetch(BASE - dt.timedelta(hours=1), drain_returning([]))
    assert result.status == 'missing'
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_radar_bluesky.py -v`
Expected: FAIL with `ImportError: cannot import name 'bluesky'`

- [ ] **Step 3: Write the implementation**

```python
# personal_apps/features/radar/sources/bluesky.py
"""Bluesky ingest, over the public Jetstream firehose.

No credentials: Jetstream is open, and searchPosts -- the one endpoint that
needs auth -- is not wanted anyway, since search returns a ranked sample where
the firehose returns everything.

Drained in batches rather than held open. Jetstream accepts a cursor in
microseconds, so the daemon reconnects from its last processed timestamp,
catches up, and disconnects on the same schedule as the polling sources.

The cursor clamp is the thing to be careful about. Replay reaches back roughly
36 hours; ask for more and Jetstream returns events from as far back as it has
with no error and no warning. Trusting the connection would mean carrying a
hole while believing the range was covered, which is precisely how a gap turns
into a fake spike (spec 4.5).
"""
import datetime as dt

from . import FetchResult, RawPost

JETSTREAM_URL = ('wss://jetstream2.us-east.bsky.network/subscribe'
                 '?wantedCollections=app.bsky.feed.post')

# How far the first delivered event may sit after the requested cursor before
# it counts as a clamp rather than a quiet moment. The network does ~144k
# posts/hour, so minutes of genuine silence do not happen.
CLAMP_TOLERANCE = dt.timedelta(minutes=5)


class JetstreamUnavailable(Exception):
    """The firehose did not deliver. Never becomes a zero count."""


def _to_raw_post(event):
    commit = event.get('commit') or {}
    record = commit.get('record') or {}
    text = record.get('text') or ''
    if not text:
        return None

    when = dt.datetime.utcfromtimestamp(event['time_us'] / 1_000_000)
    did = event.get('did') or ''
    rkey = commit.get('rkey') or ''

    return RawPost(
        source='bluesky',
        external_id='bluesky:%s:%s' % (did, rkey),
        channel='firehose',
        author=did,
        created_utc=when,
        title=None,
        body=text,
        score=0,
        num_comments=0,
        url='https://bsky.app/profile/%s/post/%s' % (did, rkey),
    )


def fetch(since, drain, budget_seconds=45):
    """Drain the firehose from `since` and normalize what comes back.

    `drain(cursor_us, budget)` is injected so the whole module is testable
    without a network, which spec 10 requires.
    """
    cursor_us = int(since.replace(tzinfo=dt.timezone.utc).timestamp() * 1_000_000)

    try:
        events = list(drain(cursor_us, budget_seconds))
    except JetstreamUnavailable:
        return FetchResult(posts=[], status='missing')

    if not events:
        # At ~144k posts/hour, an empty drain is a broken connection rather
        # than a calm network.
        return FetchResult(posts=[], status='missing')

    posts = []
    for event in events:
        if (event.get('commit') or {}).get('operation') != 'create':
            continue
        post = _to_raw_post(event)
        if post is not None:
            posts.append(post)

    earliest = min(dt.datetime.utcfromtimestamp(e['time_us'] / 1_000_000)
                   for e in events)

    if earliest - since > CLAMP_TOLERANCE:
        # Jetstream gave us less history than we asked for and said nothing.
        return FetchResult(posts=posts, status='truncated', covered_since=earliest)

    return FetchResult(posts=posts, status='ok')
```

Add the real drain alongside it, used only by the daemon:

```python
def live_drain(cursor_us, budget_seconds):
    """Connect, replay from the cursor, stop at the budget. Real network."""
    import asyncio
    import json
    import time

    import websockets

    async def _run():
        collected = []
        url = '%s&cursor=%d' % (JETSTREAM_URL, cursor_us)
        started = time.time()
        try:
            async with websockets.connect(url, max_size=None) as socket:
                while time.time() - started < budget_seconds:
                    try:
                        raw = await asyncio.wait_for(socket.recv(), timeout=15)
                    except asyncio.TimeoutError:
                        break
                    try:
                        collected.append(json.loads(raw))
                    except ValueError:
                        continue
        except Exception as exc:
            raise JetstreamUnavailable(str(exc)) from exc
        return collected

    return asyncio.run(_run())
```

- [ ] **Step 4: Run tests**

Run: `python -m pytest tests/test_radar_bluesky.py -v`
Expected: 8 passed

- [ ] **Step 5: Commit**

```bash
git add personal_apps/features/radar/sources/bluesky.py personal_apps/tests/test_radar_bluesky.py
git commit -m "feat(radar): drain the Bluesky firehose, and catch it clamping the cursor"
```

---

## Task 5: 4chan /biz/ source

**Files:**
- Create: `personal_apps/features/radar/sources/fourchan.py`
- Test: `personal_apps/tests/test_radar_fourchan.py`

**Interfaces:**
- Produces: `fetch(since, client, board='biz') -> FetchResult`; `FourChanClient` with `get_json(path) -> object`

- [ ] **Step 1: Write the failing test**

```python
# personal_apps/tests/test_radar_fourchan.py
"""4chan /biz/: narrow, crypto-heavy, useful as corroboration.

Measured at 22.7 posts/hour with 171 ticker mentions across 1450 posts. Thin
for equities once crypto is filtered, but every post carries a poster id, so
the distinct-author gate works -- anonymous is not identity-free (spec 3.6).
"""
import datetime as dt

from features.radar.sources import FetchResult
from features.radar.sources import fourchan


class FakeClient:
    def __init__(self, catalog, threads):
        self.catalog = catalog
        self.threads = threads
        self.calls = []

    def get_json(self, path):
        self.calls.append(path)
        if path.endswith('catalog.json'):
            return self.catalog
        for number, payload in self.threads.items():
            if path.endswith('/%d.json' % number):
                return payload
        raise fourchan.FourChanUnavailable('404 %s' % path)


BASE = dt.datetime(2026, 8, 21, 14, 0, 0)


def _epoch(when):
    return int(when.replace(tzinfo=dt.timezone.utc).timestamp())


def _post(number, when, com='$ZZA is the play', poster='AbCdEf12'):
    return {'no': number, 'time': _epoch(when), 'com': com, 'id': poster}


def _catalog(entries):
    return [{'page': 1, 'threads': entries}]


def test_thread_posts_become_rawposts():
    client = FakeClient(
        _catalog([{'no': 100, 'last_modified': _epoch(BASE)}]),
        {100: {'posts': [_post(100, BASE), _post(101, BASE)]}})
    result = fourchan.fetch(BASE - dt.timedelta(hours=1), client)
    assert isinstance(result, FetchResult)
    assert result.status == 'ok'
    assert len(result.posts) == 2
    post = result.posts[0]
    assert post.source == 'fourchan'
    assert post.channel == 'biz'
    assert post.external_id == 'fourchan:biz:100'
    assert post.author == 'AbCdEf12'


def test_html_is_stripped_and_entities_decoded():
    """Comments arrive as HTML with <br> and &gt; quoting."""
    client = FakeClient(
        _catalog([{'no': 100, 'last_modified': _epoch(BASE)}]),
        {100: {'posts': [_post(100, BASE, com='&gt;buy <b>$ZZA</b><br>now')]}})
    body = fourchan.fetch(BASE - dt.timedelta(hours=1), client).posts[0].body
    assert '<b>' not in body
    assert '&gt;' not in body
    assert '$ZZA' in body


def test_posts_older_than_since_are_dropped():
    client = FakeClient(
        _catalog([{'no': 100, 'last_modified': _epoch(BASE)}]),
        {100: {'posts': [_post(100, BASE - dt.timedelta(days=2)),
                         _post(101, BASE)]}})
    result = fourchan.fetch(BASE - dt.timedelta(hours=1), client)
    assert [p.external_id for p in result.posts] == ['fourchan:biz:101']


def test_threads_untouched_since_the_cursor_are_not_fetched():
    """The catalog carries last_modified, so an idle thread costs no request.
    At 1 request/second that is the difference between a cycle finishing and
    not."""
    client = FakeClient(
        _catalog([{'no': 100, 'last_modified': _epoch(BASE)},
                  {'no': 200, 'last_modified': _epoch(BASE - dt.timedelta(days=3))}]),
        {100: {'posts': [_post(100, BASE)]},
         200: {'posts': [_post(200, BASE)]}})
    fourchan.fetch(BASE - dt.timedelta(hours=1), client)
    assert not any('200.json' in call for call in client.calls)


def test_hitting_the_thread_cap_marks_truncated():
    entries = [{'no': n, 'last_modified': _epoch(BASE)} for n in range(60)]
    threads = {n: {'posts': [_post(n, BASE)]} for n in range(60)}
    result = fourchan.fetch(BASE - dt.timedelta(hours=1),
                            FakeClient(_catalog(entries), threads), thread_cap=5)
    assert result.status == 'truncated'
    assert len(result.posts) == 5


def test_an_unreachable_catalog_is_missing():
    class Failing:
        def get_json(self, path):
            raise fourchan.FourChanUnavailable('503')
    result = fourchan.fetch(BASE - dt.timedelta(hours=1), Failing())
    assert result.status == 'missing'
    assert result.posts == []


def test_one_dead_thread_does_not_lose_the_others():
    """Threads get pruned constantly; a 404 mid-cycle is routine."""
    client = FakeClient(
        _catalog([{'no': 100, 'last_modified': _epoch(BASE)},
                  {'no': 999, 'last_modified': _epoch(BASE)}]),
        {100: {'posts': [_post(100, BASE)]}})
    result = fourchan.fetch(BASE - dt.timedelta(hours=1), client)
    assert len(result.posts) == 1
    assert result.status == 'truncated'


def test_a_post_without_a_poster_id_falls_back_to_its_thread():
    """Some boards omit ids. Falling back to the thread keeps distinct-author
    counting conservative rather than crediting every post to one 'anon'."""
    client = FakeClient(
        _catalog([{'no': 100, 'last_modified': _epoch(BASE)}]),
        {100: {'posts': [{'no': 101, 'time': _epoch(BASE), 'com': '$ZZA'}]}})
    assert fourchan.fetch(BASE - dt.timedelta(hours=1), client).posts[0].author == \
        'thread:100'
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_radar_fourchan.py -v`
Expected: FAIL with `ImportError: cannot import name 'fourchan'`

- [ ] **Step 3: Write the implementation**

```python
# personal_apps/features/radar/sources/fourchan.py
"""4chan /biz/ ingest.

Public JSON API, no auth. Documented rate limit is 1 request/second, honoured
here -- which is why the catalog's last_modified matters: skipping idle threads
is the difference between a cycle finishing inside its budget and not.

Thin for equities and dominated by crypto, so its value is corroboration: a
ticker loud on both this and another source is a different object from one loud
on either alone (spec 3.6).
"""
import datetime as dt
import html
import re
import time

import requests

from . import FetchResult, RawPost

API_BASE = 'https://a.4cdn.org'
USER_AGENT_DEFAULT = 'personal_apps-radar/0.1 (personal research)'

# Documented courtesy limit.
REQUEST_INTERVAL_SECONDS = 1.0
THREAD_CAP = 30

_TAG_RE = re.compile(r'<[^>]+>')


class FourChanUnavailable(Exception):
    """This request did not arrive. Never becomes a zero count."""


class FourChanClient:
    def __init__(self, user_agent=USER_AGENT_DEFAULT, timeout=25):
        self._headers = {'User-Agent': user_agent}
        self._timeout = timeout

    def get_json(self, path):
        try:
            response = requests.get(API_BASE + path, headers=self._headers,
                                    timeout=self._timeout)
            response.raise_for_status()
            return response.json()
        except (requests.RequestException, ValueError) as exc:
            raise FourChanUnavailable('%s: %s' % (path, exc)) from exc


def _clean(comment):
    """Comments are HTML: <br> line breaks, <a> quote links, &gt; greentext."""
    if not comment:
        return ''
    return html.unescape(_TAG_RE.sub(' ', comment)).strip()


def _to_raw_post(post, thread_no, board):
    when = dt.datetime.utcfromtimestamp(post['time'])
    body = '%s %s' % (_clean(post.get('sub')), _clean(post.get('com')))

    return RawPost(
        source='fourchan',
        external_id='fourchan:%s:%d' % (board, post['no']),
        channel=board,
        # Poster ids are per-thread and per-day, which is exactly the identity
        # the distinct-author gate wants. Without one, crediting the thread is
        # conservative -- it cannot inflate the author count.
        author=post.get('id') or ('thread:%d' % thread_no),
        created_utc=when,
        title=_clean(post.get('sub')) or None,
        body=body.strip(),
        score=0,
        num_comments=0,
        url='https://boards.4chan.org/%s/thread/%d#p%d' % (board, thread_no, post['no']),
    )


def fetch(since, client, board='biz', thread_cap=THREAD_CAP, pause=0.0):
    """Posts newer than `since` from threads active since then."""
    try:
        catalog = client.get_json('/%s/catalog.json' % board)
    except FourChanUnavailable:
        return FetchResult(posts=[], status='missing')

    entries = [t for page in catalog for t in (page.get('threads') or [])]
    cutoff = since.replace(tzinfo=dt.timezone.utc).timestamp()
    active = [t for t in entries if (t.get('last_modified') or 0) >= cutoff]
    active.sort(key=lambda t: t.get('last_modified', 0), reverse=True)

    capped = len(active) > thread_cap
    posts, failures = [], 0

    for entry in active[:thread_cap]:
        try:
            thread = client.get_json('/%s/thread/%d.json' % (board, entry['no']))
        except FourChanUnavailable:
            # Threads are pruned constantly; a 404 mid-cycle is routine.
            failures += 1
            continue
        for post in thread.get('posts', []):
            raw = _to_raw_post(post, entry['no'], board)
            if raw.created_utc > since:
                posts.append(raw)
        if pause:
            time.sleep(pause)

    status = 'truncated' if (capped or failures) else 'ok'
    return FetchResult(posts=posts, status=status, catchup_depth=len(active[:thread_cap]))
```

- [ ] **Step 4: Run tests**

Run: `python -m pytest tests/test_radar_fourchan.py -v`
Expected: 8 passed

- [ ] **Step 5: Commit**

```bash
git add personal_apps/features/radar/sources/fourchan.py personal_apps/tests/test_radar_fourchan.py
git commit -m "feat(radar): read /biz/ threads without refetching idle ones"
```

---

## Task 6: Per-symbol poll scheduling

**Files:**
- Create: `personal_apps/features/radar/scheduling.py`
- Modify: `personal_apps/models.py` (add `RadarPollState`)
- Create: migration
- Test: `personal_apps/tests/test_radar_scheduling.py`

**Interfaces:**
- Produces: `interval_for_rate(rate) -> timedelta`; `due_symbols(source, now, limit) -> list[str]`; `record_poll(source, symbol, now, rate) -> None`; `ensure_tracked(source, symbols, now) -> int`

- [ ] **Step 1: Write the failing test**

```python
# personal_apps/tests/test_radar_scheduling.py
"""Poll interval derives from each symbol's own message rate.

The API returns 30 messages whatever their timespan, so a fixed interval is
wrong in both directions at once: MSFT at 5.8 msgs/hr has five hours of
coverage and polling it every 15 minutes refetches the same data twenty times,
while BTC.X at 63/hr burns through 30 messages in 28 minutes and an hourly poll
loses data permanently (spec 3.5).
"""
import datetime as dt

import pytest

from app import app as flask_app
from extensions import db
from models import RadarPollState
from features.radar import scheduling

NOW = dt.datetime(2026, 8, 21, 14, 0, 0)


@pytest.fixture()
def ctx():
    with flask_app.app_context():
        RadarPollState.query.filter(
            RadarPollState.symbol.like('ZZ%')).delete(synchronize_session=False)
        db.session.commit()
        yield
        RadarPollState.query.filter(
            RadarPollState.symbol.like('ZZ%')).delete(synchronize_session=False)
        db.session.commit()


def test_a_hot_symbol_is_polled_at_the_floor():
    """63 msgs/hr means 30 messages last 28 minutes. Half of that is under the
    floor, so it polls as often as we allow."""
    assert scheduling.interval_for_rate(63.0) == dt.timedelta(minutes=15)


def test_a_quiet_symbol_is_polled_at_the_ceiling():
    """0.2 msgs/hr covers 150 hours. Polling hourly would be pure waste."""
    assert scheduling.interval_for_rate(0.2) == dt.timedelta(hours=4)


def test_a_middling_symbol_lands_between():
    """5.8 msgs/hr -- MSFT -- covers 5.2 hours; half of that is 2.6."""
    interval = scheduling.interval_for_rate(5.8)
    assert dt.timedelta(hours=2) < interval < dt.timedelta(hours=3)


def test_an_unmeasured_symbol_gets_the_floor():
    """No rate yet means poll it soon and find out."""
    assert scheduling.interval_for_rate(None) == dt.timedelta(minutes=15)
    assert scheduling.interval_for_rate(0.0) == dt.timedelta(hours=4)


def test_tracking_a_symbol_makes_it_immediately_due(ctx):
    scheduling.ensure_tracked('stocktwits', ['ZZA'], NOW)
    assert 'ZZA' in scheduling.due_symbols('stocktwits', NOW, limit=10)


def test_a_polled_symbol_is_not_due_again_until_its_interval_passes(ctx):
    scheduling.ensure_tracked('stocktwits', ['ZZA'], NOW)
    scheduling.record_poll('stocktwits', 'ZZA', NOW, rate=5.8)
    assert scheduling.due_symbols('stocktwits', NOW, limit=10) == []
    later = NOW + dt.timedelta(hours=3)
    assert 'ZZA' in scheduling.due_symbols('stocktwits', later, limit=10)


def test_a_symbol_that_heats_up_is_polled_sooner(ctx):
    """Self-correcting: the schedule tightens before anything is missed."""
    scheduling.ensure_tracked('stocktwits', ['ZZA'], NOW)
    scheduling.record_poll('stocktwits', 'ZZA', NOW, rate=0.5)
    cold_due = RadarPollState.query.filter_by(source='stocktwits', symbol='ZZA').one().next_due_at

    scheduling.record_poll('stocktwits', 'ZZA', NOW, rate=90.0)
    hot_due = RadarPollState.query.filter_by(source='stocktwits', symbol='ZZA').one().next_due_at
    assert hot_due < cold_due


def test_due_symbols_respects_the_request_budget(ctx):
    scheduling.ensure_tracked('stocktwits', ['ZZ%02d' % i for i in range(20)], NOW)
    assert len(scheduling.due_symbols('stocktwits', NOW, limit=6)) == 6


def test_the_most_overdue_symbols_come_first(ctx):
    """With a budget smaller than the backlog, starving one symbol forever
    would leave a permanent hole in its baseline."""
    scheduling.ensure_tracked('stocktwits', ['ZZA', 'ZZB'], NOW)
    scheduling.record_poll('stocktwits', 'ZZA', NOW, rate=1.0)
    scheduling.record_poll('stocktwits', 'ZZB', NOW - dt.timedelta(hours=6), rate=1.0)
    assert scheduling.due_symbols('stocktwits', NOW + dt.timedelta(hours=5),
                                  limit=1) == ['ZZB']


def test_tracking_is_per_source(ctx):
    """The same symbol on two sources has two rates and two schedules."""
    scheduling.ensure_tracked('stocktwits', ['ZZA'], NOW)
    scheduling.record_poll('stocktwits', 'ZZA', NOW, rate=60.0)
    scheduling.ensure_tracked('othersource', ['ZZA'], NOW)
    assert 'ZZA' in scheduling.due_symbols('othersource', NOW, limit=5)
    assert scheduling.due_symbols('stocktwits', NOW, limit=5) == []
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_radar_scheduling.py -v`
Expected: FAIL with `ImportError: cannot import name 'RadarPollState' from 'models'`

- [ ] **Step 3: Write the implementation**

Add to `personal_apps/models.py`:

```python
class RadarPollState(db.Model):
    """When each symbol was last polled, and when it is next due.

    Per source, because the same symbol has a different message rate on each.
    """
    __tablename__ = 'radar_poll_state'
    __table_args__ = (
        db.Index('ix_radar_poll_state_due', 'source', 'next_due_at'),
        {'mysql_charset': 'utf8mb4'},
    )

    source          = db.Column(db.String(24), primary_key=True)
    symbol          = db.Column(db.String(12, collation='utf8mb4_bin'),
                                primary_key=True)
    last_polled_at  = db.Column(MYSQL_DATETIME(fsp=6), nullable=True)
    next_due_at     = db.Column(MYSQL_DATETIME(fsp=6), nullable=False)
    observed_rate   = db.Column(db.Float, nullable=True)   # messages per hour
```

```python
# personal_apps/features/radar/scheduling.py
"""Per-symbol poll scheduling.

Sources that return a fixed page size regardless of timespan cannot be polled
on a fixed interval: the page is hours of history for a quiet symbol and
minutes for a busy one. Polling the quiet one often refetches the same data;
polling the busy one rarely loses data permanently. So the interval comes from
each symbol's own measured rate, which makes the schedule self-correcting -- a
symbol that heats up is polled faster before anything is missed (spec 3.5).
"""
import datetime as dt

from extensions import db
from models import RadarPollState

# Messages a single call returns. Coverage is this divided by the rate.
PAGE_SIZE = 30

# Half the coverage window, so a rate estimate that is somewhat wrong still
# does not lose messages.
SAFETY_FACTOR = 0.5

MIN_INTERVAL = dt.timedelta(minutes=15)
MAX_INTERVAL = dt.timedelta(hours=4)


def interval_for_rate(rate):
    """How long until this symbol should be polled again.

    A rate of None means never measured -- poll soon and find out. A measured
    rate of zero means genuinely silent, so wait the maximum.
    """
    if rate is None:
        return MIN_INTERVAL
    if rate <= 0:
        return MAX_INTERVAL

    coverage_hours = PAGE_SIZE / rate
    interval = dt.timedelta(hours=coverage_hours * SAFETY_FACTOR)
    return max(MIN_INTERVAL, min(MAX_INTERVAL, interval))


def ensure_tracked(source, symbols, now):
    """Add any symbols not yet tracked, due immediately. Returns how many."""
    existing = {
        row.symbol for row in
        RadarPollState.query.filter(RadarPollState.source == source,
                                    RadarPollState.symbol.in_(list(symbols))).all()
    } if symbols else set()

    added = 0
    for symbol in symbols:
        if symbol in existing:
            continue
        db.session.add(RadarPollState(source=source, symbol=symbol,
                                      next_due_at=now, observed_rate=None))
        added += 1
    db.session.commit()
    return added


def due_symbols(source, now, limit):
    """The most overdue symbols, up to the request budget.

    Ordered by how long they have been waiting, so a backlog larger than the
    budget rotates instead of starving the same symbols forever -- a symbol
    never polled is a permanent hole in its baseline.
    """
    rows = (RadarPollState.query
            .filter(RadarPollState.source == source,
                    RadarPollState.next_due_at <= now)
            .order_by(RadarPollState.next_due_at.asc())
            .limit(limit).all())
    return [row.symbol for row in rows]


def record_poll(source, symbol, now, rate):
    """Stamp a completed poll and schedule the next one from the new rate."""
    row = RadarPollState.query.filter_by(source=source, symbol=symbol).one_or_none()
    if row is None:
        row = RadarPollState(source=source, symbol=symbol)
        db.session.add(row)

    row.last_polled_at = now
    row.observed_rate = rate
    row.next_due_at = now + interval_for_rate(rate)
    db.session.commit()
```

Generate and apply the migration:

```bash
python -m flask --app app db migrate -m "add radar poll state"
python -m flask --app app db upgrade
```

- [ ] **Step 4: Run tests**

Run: `python -m pytest tests/test_radar_scheduling.py -v`
Expected: 10 passed

- [ ] **Step 5: Commit**

```bash
git add personal_apps/features/radar/scheduling.py personal_apps/models.py personal_apps/migrations/versions/ personal_apps/tests/test_radar_scheduling.py
git commit -m "feat(radar): poll each symbol as often as its own chatter demands"
```

---

## Task 7: Multi-source ingest

**Files:**
- Modify: `personal_apps/features/radar/ingest.py`
- Modify: `personal_apps/tests/test_radar_ingest.py`

**Interfaces:**
- Produces: `run_cycle(now, fetchers) -> dict` where `fetchers` is `{source_name: callable(since) -> FetchResult}`; summary gains `per_source`

- [ ] **Step 1: Write the failing test**

Append to `personal_apps/tests/test_radar_ingest.py`:

```python
def test_two_sources_ingest_in_one_cycle(seeded):
    def st(since):
        return FetchResult(posts=[post(ident='st1', body='$ZZG up')], status='ok')

    def bs(since):
        p = post(ident='bs1', body='$ZZG up')
        p.source = 'bluesky'
        return FetchResult(posts=[p], status='ok')

    result = ingest.run_cycle(NOW, {'stocktwits': st, 'bluesky': bs})
    assert result['posts_new'] == 2
    assert result['per_source']['stocktwits'] == 'ok'
    assert result['per_source']['bluesky'] == 'ok'

    with flask_app.app_context():
        from models import RadarBucketSource
        sources = {r.source for r in
                   RadarBucketSource.query.filter_by(ticker='ZZG').all()}
        assert sources == {'stocktwits', 'bluesky'}


def test_one_source_failing_does_not_stop_the_other(seeded):
    """The entire reason status is per source. A dead Bluesky must not cost us
    a healthy StockTwits cycle, and must not write a zero for itself."""
    def st(since):
        return FetchResult(posts=[post(ident='st1', body='$ZZG up')], status='ok')

    def bs(since):
        return FetchResult(posts=[], status='missing')

    result = ingest.run_cycle(NOW, {'stocktwits': st, 'bluesky': bs})
    assert result['per_source'] == {'stocktwits': 'ok', 'bluesky': 'missing'}

    with flask_app.app_context():
        from models import RadarBucketSource
        rows = {r.source: r.status for r in
                RadarBucketSource.query.filter_by(ticker='ZZG').all()}
        assert rows == {'stocktwits': 'ok'}      # no bluesky row at all


def test_a_sources_since_is_tracked_independently(seeded):
    """Each source advances its own cursor. One catching up must not drag the
    others back over ground they already covered."""
    captured = {}

    def st(since):
        captured['stocktwits'] = since
        return FetchResult(posts=[post(ident='st1', minute=10)], status='ok')

    def bs(since):
        captured['bluesky'] = since
        return FetchResult(posts=[], status='ok')

    ingest.run_cycle(NOW, {'stocktwits': st, 'bluesky': bs})
    ingest.run_cycle(NOW, {'stocktwits': st, 'bluesky': bs})
    assert captured['stocktwits'] == dt.datetime(2026, 4, 15, 14, 10, 0)
    assert captured['bluesky'] != captured['stocktwits']


def test_covered_since_shortens_the_rolled_up_window(seeded):
    """When a source reports it could not reach as far back as asked -- the
    Jetstream clamp -- buckets before that point must not be written as though
    they were covered."""
    def bs(since):
        p = post(ident='bs1', minute=18)
        p.source = 'bluesky'
        return FetchResult(posts=[p], status='truncated',
                           covered_since=dt.datetime(2026, 4, 15, 14, 15, 0))

    ingest.run_cycle(NOW, {'bluesky': bs})
    with flask_app.app_context():
        from models import RadarBucketSource
        starts = [r.bucket_start for r in
                  RadarBucketSource.query.filter_by(source='bluesky').all()]
        assert all(s >= dt.datetime(2026, 4, 15, 14, 15, 0) for s in starts)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_radar_ingest.py -v`
Expected: FAIL — `run_cycle()` takes a single fetcher, not a mapping

- [ ] **Step 3: Write the implementation**

Replace `run_cycle` and `_touched_buckets` in `personal_apps/features/radar/ingest.py`:

```python
def _touched_buckets(mention_rows, since, now):
    """Every bucket a cycle covered, including ones with no mentions.

    Derived from the span rather than the rows, so a healthy source that saw
    nothing records a genuine zero -- a different fact from `missing`, and one
    that must stay distinguishable.
    """
    windows = set()
    cursor = buckets.bucket_start_for(since)
    end = buckets.bucket_start_for(now)
    while cursor <= end:
        windows.add(cursor)
        cursor += dt.timedelta(minutes=BUCKET_MINUTES)
    for row in mention_rows:
        windows.add(buckets.bucket_start_for(row.created_utc))
    return windows


def run_cycle(now, fetchers):
    """Fetch every source, store, extract, roll up once.

    `fetchers` maps source name to a callable taking `since`. The set is open;
    nothing here knows which sources exist.
    """
    lookup = universe.load_lookup()
    statuses, per_source_depth = {}, {}
    all_raw, all_mentions = [], []
    touched = set()
    posts_new = 0

    for source, fetcher in fetchers.items():
        since = _since_for(source)
        result = fetcher(since)
        statuses[source] = result.status
        per_source_depth[source] = result.catchup_depth

        if result.status == 'missing':
            continue

        # A source that could not reach as far back as asked did not cover the
        # earlier part of the window, and must not have buckets written for it.
        effective_since = result.covered_since or since
        touched |= _touched_buckets([], effective_since, now)

        stored, new_count = _store_posts(result.posts, now)
        posts_new += new_count
        mention_rows = _extract_mentions(result.posts, stored, lookup)
        all_raw.extend(result.posts)
        all_mentions.extend(mention_rows)

    db.session.commit()

    for row in all_mentions:
        touched.add(buckets.bucket_start_for(row.created_utc))

    written = buckets.roll_up(all_mentions, statuses, touched)

    return {'posts_seen': len(all_raw), 'posts_new': posts_new,
            'mentions': len(all_mentions), 'buckets_written': written,
            'per_source': statuses, 'catchup_depth': per_source_depth}
```

- [ ] **Step 4: Run tests**

Run: `python -m pytest tests/test_radar_ingest.py -v`
Expected: 11 passed

- [ ] **Step 5: Commit**

```bash
git add personal_apps/features/radar/ingest.py personal_apps/tests/test_radar_ingest.py
git commit -m "feat(radar): run every source in one cycle, each with its own cursor"
```

---

## Task 8: Wire the daemon, retire Reddit

**Files:**
- Modify: `personal_apps/run_radar_ingest.py`
- Modify: `personal_apps/features/radar/config.py`
- Delete: `personal_apps/features/radar/sources/reddit.py`, `personal_apps/tests/test_radar_reddit_source.py`
- Modify: `personal_apps/tests/test_radar_daemon.py`

**Interfaces:**
- Produces: `build_fetchers() -> dict[str, callable]`

- [ ] **Step 1: Write the failing test**

Append to `personal_apps/tests/test_radar_daemon.py`:

```python
def test_every_configured_source_gets_a_fetcher():
    fetchers = daemon.build_fetchers()
    assert set(fetchers) == set(daemon.SOURCES)
    assert all(callable(f) for f in fetchers.values())


def test_reddit_is_gone():
    """Reddit closed self-serve API access. A leftover module is a trap: it
    imports cleanly and fails only at runtime, against a wall that is not
    coming down."""
    import importlib
    import pytest
    with pytest.raises(ImportError):
        importlib.import_module('features.radar.sources.reddit')


def test_the_request_budget_is_split_across_sources():
    """StockTwits' limit is undocumented; the budget is a conservative guess
    with adaptive backoff, not a number anyone published."""
    assert daemon.SYMBOL_BUDGET_PER_CYCLE >= 1
    assert daemon.SYMBOL_BUDGET_PER_CYCLE <= 40
```

Update the existing `test_tick_returns_the_cycle_summary` and `test_a_cycle_that_raises_does_not_kill_the_daemon` to pass a mapping:

```python
    result = daemon.tick(_utc(2026, 4, 15, 14), fetchers={'stocktwits': lambda s: None})
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_radar_daemon.py -v`
Expected: FAIL with `AttributeError: module 'run_radar_ingest' has no attribute 'build_fetchers'`

- [ ] **Step 3: Write the implementation**

Add to `personal_apps/features/radar/config.py`:

```python
# Active sources. Adding one is a module in sources/ plus an entry here --
# nothing else in the pipeline names a source (spec 8.6).
SOURCES = ('stocktwits', 'bluesky', 'fourchan')

# StockTwits publishes no rate-limit headers and 20 consecutive requests drew
# no 429, so this is a conservative budget rather than a documented ceiling.
# The daemon backs off on 429 regardless.
STOCKTWITS_REQUESTS_PER_HOUR = 150
```

Replace the Reddit wiring in `personal_apps/run_radar_ingest.py`:

```python
from features.radar import ingest, market_calendar, retention, scheduling
from features.radar.config import SOURCES, STOCKTWITS_REQUESTS_PER_HOUR
from features.radar.sources import bluesky, fourchan, stocktwits

# Cycles per hour at the fastest cadence, used to divide the hourly budget.
_CYCLES_PER_HOUR = 20
SYMBOL_BUDGET_PER_CYCLE = max(1, STOCKTWITS_REQUESTS_PER_HOUR // _CYCLES_PER_HOUR)


def _stocktwits_fetcher(client):
    def fetch(since):
        # Trending is both the discovery surface and a source of new symbols
        # for the standing set.
        try:
            hot = stocktwits.trending(client)
            scheduling.ensure_tracked('stocktwits', hot, dt.datetime.utcnow())
        except stocktwits.StockTwitsUnavailable:
            logger.warning('stocktwits trending unavailable this cycle')

        now = dt.datetime.utcnow()
        symbols = scheduling.due_symbols('stocktwits', now,
                                         limit=SYMBOL_BUDGET_PER_CYCLE)
        result = stocktwits.fetch(since, client, symbols)
        for symbol in symbols:
            scheduling.record_poll('stocktwits', symbol, now,
                                   result.rates.get(symbol))
        return result
    return fetch


def build_fetchers():
    """One callable per active source, each taking `since`."""
    st_client = stocktwits.StockTwitsClient()
    fc_client = fourchan.FourChanClient()

    return {
        'stocktwits': _stocktwits_fetcher(st_client),
        'bluesky': lambda since: bluesky.fetch(since, bluesky.live_drain),
        'fourchan': lambda since: fourchan.fetch(
            since, fc_client, pause=fourchan.REQUEST_INTERVAL_SECONDS),
    }


def tick(now_utc, fetchers):
    """One cycle across every source, with failures contained.

    APScheduler drops a job whose function raises, so an unhandled error here
    would silently end ingest until the next restart.
    """
    try:
        summary = ingest.run_cycle(now_utc.replace(tzinfo=None), fetchers)
    except Exception:
        logger.exception('radar ingest cycle failed')
        return {'status': 'error', 'posts_seen': 0, 'posts_new': 0,
                'mentions': 0, 'buckets_written': 0, 'per_source': {}}

    logger.info('radar cycle posts=%d new=%d mentions=%d buckets=%d sources=%s',
                summary['posts_seen'], summary['posts_new'],
                summary['mentions'], summary['buckets_written'],
                summary['per_source'])
    return summary
```

Replace `main()` and `_scheduled_cycle`, deleting the Reddit imports,
`build_client` and the old singular `build_fetcher`:

```python
def _scheduled_cycle(scheduler, fetchers):
    """Run a cycle, then reschedule at the interval the session now calls for."""
    now = dt.datetime.now(dt.timezone.utc)
    with app.app_context():
        tick(now, fetchers)

    state = current_state(now)
    scheduler.reschedule_job('radar_cycle', trigger='interval',
                             seconds=interval_for(state))


def main():
    logging.basicConfig(level=logging.INFO)
    fetchers = build_fetchers()

    scheduler = BackgroundScheduler(timezone='UTC')
    scheduler.add_job(_scheduled_cycle, 'interval', seconds=180,
                      id='radar_cycle', args=[scheduler, fetchers],
                      max_instances=1, coalesce=True)
    scheduler.add_job(_scheduled_prune, 'cron', hour=4, minute=30,
                      id='radar_prune')
    scheduler.start()
    logger.info('radar ingest daemon started, sources=%s', ','.join(SOURCES))

    try:
        while True:
            import time
            time.sleep(60)
    except (KeyboardInterrupt, SystemExit):
        scheduler.shutdown()
```

Delete the dead module and its suite:

```bash
git rm personal_apps/features/radar/sources/reddit.py personal_apps/tests/test_radar_reddit_source.py
```

- [ ] **Step 4: Run the full suite**

Run: `python -m pytest tests/ -q`
Expected: all radar tests pass. Four pre-existing gym failures (`test_gym_ownership`, `test_gym_exercise_ownership`, `test_gym_routes_smoke` ×2) are unrelated — they assert single-owner state that the production data restore violates.

- [ ] **Step 5: Commit**

```bash
git add -A personal_apps/run_radar_ingest.py personal_apps/features/radar/config.py personal_apps/tests/test_radar_daemon.py
git commit -m "feat(radar): drive three sources from one daemon, and retire Reddit"
```

---

## Done when

- `python -m pytest tests/test_radar_*.py -q` passes in full
- A live cycle writes `radar_bucket_sources` rows for all three sources
- Killing one source's network access leaves the other two writing rows, and writes **no** row for the dead one
- `grep -rn "reddit" personal_apps/features/radar/` returns nothing

## Deliberately deferred

**The standing set is not seeded by market cap.** Spec §3.5 describes three
poll tiers, the third being a few hundred symbols chosen by market cap. That
needs market cap, which needs the price provider — and no price provider lands
in this plan. StockTwits' `fundamentals` payload was checked and carries
`TotalAssets`, `TotalDebt` and `BookValuePerShare` but **no market cap and no
price**, so it cannot stand in.

Until then the standing set bootstraps itself: `ensure_tracked` adds every
trending symbol it sees and those rows persist, so the polled set grows to
cover everything that has ever trended. That is a reasonable approximation of
"symbols worth having history for", and it accumulates from the first cycle
rather than waiting on a dependency.

The `watchlist_count` field StockTwits returns — 138,187 for WMT — is a usable
popularity denominator and may turn out better than market cap for judging
whether chatter is unusual *for that ticker's audience size*. Worth measuring
in Plan 2 before committing to market cap as the segment axis.

## What Plan 2 picks up

Scoring reads `radar_bucket_sources` and writes `expected`, `variance`, `mention_z` and `baseline_days` per source row; the leaderboard pools whichever sources the UI selector has chosen. Nothing in this plan computes a score.
