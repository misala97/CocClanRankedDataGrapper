# Radar Plan 1 — Foundation and Reddit Ingest

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Get correct, gap-aware mention data from Reddit into `radar_buckets` on a session-tiered schedule, with nothing scored and nothing rendered.

**Architecture:** A `features/radar/` package mirroring `features/gym/`: pure modules with no Flask dependency (calendar, extraction, fingerprint, sentiment, config), a source module that speaks Reddit's OAuth API behind a normalized `FetchResult`, a rollup that writes 15-minute buckets carrying per-source ingest status, and an APScheduler daemon that picks its interval from the NYSE session clock. Scoring reads these buckets in Plan 2 and never re-reads raw text.

**Tech Stack:** Python 3.12, Flask 3 + Flask-SQLAlchemy + Flask-Migrate, MariaDB (prod) / MySQL 8 (dev), APScheduler, `requests`, pytest. No new third-party dependencies.

**Spec:** `docs/superpowers/specs/2026-08-20-radar-social-sentiment-design.md`

## Global Constraints

- **Reddit-only.** StockTwits is out of this plan (spec §3.3 — no firehose, ToS and access tier unresolved). Schema, `FetchResult` and the per-source status columns are built for two sources anyway; nothing may hardcode a single source.
- **No scoring in this plan.** No z-scores, no divergence, no baselines. Buckets store counts and status only. `mention_z_*`, `baseline_days_*` columns are created nullable and left NULL.
- **All datetimes are UTC** and stored `DATETIME(6)`. `TIMESTAMP` is prohibited (spec §5.4.4).
- **Every table `CHARACTER SET utf8mb4`** (spec §5.4.1). `radar_posts.body` is `MEDIUMTEXT` (§5.4.2).
- **Symbol columns are `utf8mb4_bin`** (§5.4.6), so every candidate token is uppercased before lookup (§4.2).
- **Prices are `DECIMAL(18,6)`**, never float (§5.4.5). No price columns land in this plan, but the rule applies when they do.
- **`sql_mode` must include `STRICT_TRANS_TABLES`** (§5.4.3) on both dev and the VPS. This is server configuration, not code, so no task creates it — verify it before Task 3 with `SELECT @@sql_mode;` and set it in the server config if absent. Without it an over-long body is silently truncated, and a truncated body corrupts ticker extraction with nothing to show for it downstream.
- **No live network calls in tests** (spec §10). Every HTTP interaction is mocked.
- **`missing` ≠ zero** (§4.5). A source that failed writes `missing`; it never writes a zero count.
- Code and identifiers in English. This app's radar UI is English (§2), unlike gym.
- Table names take a `radar_` prefix and are plural, matching `gym_workout_sessions`. The spec's singular names (`radar_post`) are conceptual.

---

## File Structure

**Create:**

| Path | Responsibility |
|---|---|
| `personal_apps/features/radar/__init__.py` | Empty package marker |
| `personal_apps/features/radar/config.py` | Subreddit list, stopwords, tunables, `source_config_version()` |
| `personal_apps/features/radar/market_calendar.py` | NYSE holidays, early closes, session state from a UTC instant |
| `personal_apps/features/radar/fingerprint.py` | `simhash64()` and text normalization |
| `personal_apps/features/radar/sentiment.py` | Lexicon scoring with negation |
| `personal_apps/features/radar/extraction.py` | Ticker matching and confidence tiers |
| `personal_apps/features/radar/universe.py` | Symbol universe seed, refresh, lookup, reassignment reset |
| `personal_apps/features/radar/sources/__init__.py` | `RawPost` / `FetchResult` dataclasses |
| `personal_apps/features/radar/sources/reddit.py` | Reddit OAuth, `/new` catch-up pagination |
| `personal_apps/features/radar/buckets.py` | 15-minute rollup, per-source status writes |
| `personal_apps/features/radar/ingest.py` | Cycle orchestration |
| `personal_apps/features/radar/retention.py` | Chunked pruning of posts and mentions |
| `personal_apps/run_radar_ingest.py` | APScheduler daemon, session-tiered cadence |

**Modify:**

- `personal_apps/models.py` — append four models
- `personal_apps/migrations/versions/<hash>_add_radar_tables.py` — new migration
- `.env` — five Reddit credential keys (documented, not committed)

**Deviations from spec §9.1's file list**, all additive: `market_calendar.py`, `fingerprint.py`, `buckets.py`, `config.py`, `retention.py`. §9.1 lists `ingest.py` as orchestration; rollup and pruning are separable responsibilities with their own tests, and the calendar is needed by both this plan's cadence and Plan 3's forward returns.

---

## Task 1: Config and source config versioning

**Files:**
- Create: `personal_apps/features/radar/__init__.py`
- Create: `personal_apps/features/radar/config.py`
- Test: `personal_apps/tests/test_radar_config.py`

**Interfaces:**
- Consumes: nothing
- Produces:
  - `SUBREDDITS: tuple[str, ...]`
  - `STOPWORDS: frozenset[str]`
  - `BUCKET_MINUTES: int` (15)
  - `PAGE_CAP: int` (10)
  - `POST_RETENTION_DAYS: int` (30)
  - `source_config_version() -> str` — 16-char hex

- [ ] **Step 1: Write the failing test**

```python
# personal_apps/tests/test_radar_config.py
"""The source config version is what stops a subreddit being added from
manufacturing a market-wide spike the next morning (spec 6.6). It has to be
stable across runs and sensitive to the list it hashes."""
from features.radar import config


def test_version_is_stable_across_calls():
    assert config.source_config_version() == config.source_config_version()


def test_version_changes_when_the_subreddit_list_changes(monkeypatch):
    before = config.source_config_version()
    monkeypatch.setattr(config, 'SUBREDDITS', config.SUBREDDITS + ('newsub',))
    assert config.source_config_version() != before


def test_version_ignores_subreddit_order():
    forward = config.source_config_version()
    reversed_list = tuple(reversed(config.SUBREDDITS))
    import unittest.mock as mock
    with mock.patch.object(config, 'SUBREDDITS', reversed_list):
        assert config.source_config_version() == forward


def test_version_is_short_hex():
    version = config.source_config_version()
    assert len(version) == 16
    assert all(c in '0123456789abcdef' for c in version)


def test_stopwords_are_uppercase():
    """Extraction uppercases candidates before checking membership; a
    lowercase entry here would never match and would silently let a false
    positive through."""
    assert all(word == word.upper() for word in config.STOPWORDS)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd personal_apps && python -m pytest tests/test_radar_config.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'features.radar'`

- [ ] **Step 3: Write minimal implementation**

```python
# personal_apps/features/radar/__init__.py
```

(empty file)

```python
# personal_apps/features/radar/config.py
"""Radar tunables.

Everything here is configuration in the sense that changing it changes what
gets ingested -- which is exactly why SUBREDDITS is hashed into a version
stamped onto every bucket. Baselines are computed only over buckets sharing the
current version, so adding a subreddit starts a warm-up instead of reading
straight through the discontinuity (spec 6.6).
"""
import hashlib
import json

SUBREDDITS = (
    'wallstreetbets',
    'stocks',
    'options',
    'pennystocks',
    'shortsqueeze',
    'Daytrading',
    'smallstreetbets',
    'SPACs',
)

# 15-minute grain. Fine enough for the 1h window in spec 6.9, coarse enough
# that a forever-retained table stays small.
BUCKET_MINUTES = 15

# Pages of 100 items to walk per subreddit per cycle before giving up and
# marking the affected buckets `truncated` (spec 4.3).
PAGE_CAP = 10

POST_RETENTION_DAYS = 30

# English words and trading slang that collide with real ticker symbols. Every
# entry costs a real ticker its bare-token matches, so entries are only added
# when the collision is common enough to outweigh that.
STOPWORDS = frozenset({
    'IT', 'ON', 'ALL', 'FOR', 'ARE', 'CAN', 'NOW', 'ONE', 'OUT', 'NEW',
    'ANY', 'BIG', 'GET', 'GOT', 'HAS', 'HIS', 'HER', 'HOW', 'ITS', 'LET',
    'MAN', 'MAY', 'OLD', 'SEE', 'TWO', 'WAY', 'WHO', 'YOU', 'AND', 'THE',
    'DD', 'CEO', 'CFO', 'CTO', 'EPS', 'ATH', 'IMO', 'IPO', 'ETF', 'IRA',
    'USA', 'GDP', 'CPI', 'FED', 'SEC', 'IRS', 'NYSE', 'PM', 'AM', 'EOD',
    'EOW', 'OTM', 'ITM', 'ATM', 'FD', 'FDS', 'YOLO', 'PUMP', 'HOLD',
    'BUY', 'SELL', 'PUT', 'PUTS', 'CALL', 'CALLS', 'LONG', 'SHORT',
    'BULL', 'BEAR', 'MOON', 'HODL', 'LMAO', 'IMHO', 'TLDR', 'EDIT',
})


def source_config_version():
    """A stable 16-char stamp for the active source configuration.

    Sorted before hashing so reordering the list is not a config change --
    only membership is. Stamped onto every bucket; see spec 6.6.
    """
    payload = json.dumps(sorted(SUBREDDITS), separators=(',', ':'))
    return hashlib.sha256(payload.encode('utf-8')).hexdigest()[:16]
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd personal_apps && python -m pytest tests/test_radar_config.py -v`
Expected: 5 passed

- [ ] **Step 5: Commit**

```bash
git add personal_apps/features/radar/__init__.py personal_apps/features/radar/config.py personal_apps/tests/test_radar_config.py
git commit -m "feat(radar): version the source config so adding a subreddit is not a spike"
```

---

## Task 2: NYSE market calendar

**Files:**
- Create: `personal_apps/features/radar/market_calendar.py`
- Test: `personal_apps/tests/test_radar_calendar.py`

**Interfaces:**
- Consumes: nothing
- Produces:
  - `session_state(when_utc: datetime) -> str` — one of `'premarket'`, `'regular'`, `'afterhours'`, `'closed'`
  - `is_trading_day(day: date) -> bool`
  - `early_close_days(year: int) -> set[date]`
  - `holidays(year: int) -> set[date]`

- [ ] **Step 1: Write the failing test**

```python
# personal_apps/tests/test_radar_calendar.py
"""Session state drives ingest cadence now and forward-return offsets in Plan 3.

The DST cases are the point of this suite: the EU and US switch on different
dates, so for about three weeks each spring the US open lands an hour earlier
in Berlin than usual. Anything that reasoned in German local time would
mis-tier ingest for exactly those weeks (spec 4.4).
"""
import datetime as dt
from zoneinfo import ZoneInfo

from features.radar import market_calendar as cal

BERLIN = ZoneInfo('Europe/Berlin')


def _utc(year, month, day, hour, minute=0):
    return dt.datetime(year, month, day, hour, minute, tzinfo=dt.timezone.utc)


def test_regular_session_on_an_ordinary_wednesday():
    # 2026-04-15 is a Wednesday. 14:00 UTC = 10:00 ET, mid-session.
    assert cal.session_state(_utc(2026, 4, 15, 14)) == 'regular'


def test_premarket_before_the_open():
    # 12:00 UTC = 08:00 ET.
    assert cal.session_state(_utc(2026, 4, 15, 12)) == 'premarket'


def test_afterhours_after_the_close():
    # 21:00 UTC = 17:00 ET.
    assert cal.session_state(_utc(2026, 4, 15, 21)) == 'afterhours'


def test_closed_overnight():
    # 03:00 UTC = 23:00 ET the previous day, past the 20:00 after-hours end.
    assert cal.session_state(_utc(2026, 4, 15, 3)) == 'closed'


def test_closed_on_a_weekend():
    # 2026-04-18 is a Saturday.
    assert cal.session_state(_utc(2026, 4, 18, 14)) == 'closed'


def test_closed_on_a_fixed_holiday():
    # Independence Day 2026 falls on a Saturday, so it is observed Friday 3rd.
    assert cal.session_state(_utc(2026, 7, 3, 14)) == 'closed'


def test_closed_on_good_friday():
    # Easter 2026 is April 5, so Good Friday is April 3.
    assert dt.date(2026, 4, 3) in cal.holidays(2026)
    assert cal.session_state(_utc(2026, 4, 3, 14)) == 'closed'


def test_thanksgiving_is_the_fourth_thursday():
    assert dt.date(2026, 11, 26) in cal.holidays(2026)


def test_day_after_thanksgiving_is_an_early_close():
    assert dt.date(2026, 11, 27) in cal.early_close_days(2026)
    # 18:30 UTC = 13:30 ET, past the 13:00 early close.
    assert cal.session_state(_utc(2026, 11, 27, 18, 30)) == 'afterhours'
    # 17:00 UTC = 12:00 ET, still open.
    assert cal.session_state(_utc(2026, 11, 27, 17)) == 'regular'


def test_dst_desync_window_us_already_switched_eu_has_not():
    """2026: US DST starts Mar 8, EU starts Mar 29. Between those dates the
    US open is 13:30 UTC and lands at 14:30 in Berlin rather than 15:30."""
    instant = _utc(2026, 3, 16, 13, 45)          # Monday, 09:45 ET
    assert cal.session_state(instant) == 'regular'
    assert instant.astimezone(BERLIN).hour == 14


def test_outside_the_desync_window_the_open_is_1530_berlin():
    instant = _utc(2026, 4, 15, 13, 45)          # 09:45 ET
    assert cal.session_state(instant) == 'regular'
    assert instant.astimezone(BERLIN).hour == 15


def test_naive_datetimes_are_rejected():
    """A naive datetime here would be silently interpreted as local time on
    whatever machine runs the daemon."""
    import pytest
    with pytest.raises(ValueError):
        cal.session_state(dt.datetime(2026, 4, 15, 14))
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd personal_apps && python -m pytest tests/test_radar_calendar.py -v`
Expected: FAIL with `ImportError: cannot import name 'market_calendar'`

- [ ] **Step 3: Write minimal implementation**

```python
# personal_apps/features/radar/market_calendar.py
"""NYSE session state, computed locally.

Local rather than from a data provider for two reasons: spec 10 forbids live
API calls in tests, and Plan 3's forward returns need historical session
boundaries, which a "is the market open right now" endpoint cannot give.

Everything crossing this module's boundary is timezone-aware UTC. Conversion to
America/New_York happens inside, and nothing here ever reasons in Berlin time --
that conversion belongs to the display layer (spec 4.4).
"""
import datetime as dt
from zoneinfo import ZoneInfo

NY = ZoneInfo('America/New_York')

PREMARKET_START = dt.time(4, 0)
REGULAR_START = dt.time(9, 30)
REGULAR_END = dt.time(16, 0)
EARLY_CLOSE_END = dt.time(13, 0)
AFTERHOURS_END = dt.time(20, 0)


def _easter(year):
    """Anonymous Gregorian algorithm. Good Friday is Easter minus two days,
    and it is the only NYSE holiday that is not a fixed or nth-weekday rule."""
    a = year % 19
    b, c = divmod(year, 100)
    d, e = divmod(b, 4)
    f = (b + 8) // 25
    g = (b - f + 1) // 3
    h = (19 * a + b - d - g + 15) % 30
    i, k = divmod(c, 4)
    lam = (32 + 2 * e + 2 * i - h - k) % 7
    m = (a + 11 * h + 22 * lam) // 451
    month, day = divmod(h + lam - 7 * m + 114, 31)
    return dt.date(year, month, day + 1)


def _nth_weekday(year, month, weekday, n):
    """The nth weekday of a month. weekday follows date.weekday(): Mon=0."""
    first = dt.date(year, month, 1)
    offset = (weekday - first.weekday()) % 7
    return first + dt.timedelta(days=offset + 7 * (n - 1))


def _last_weekday(year, month, weekday):
    if month == 12:
        following = dt.date(year + 1, 1, 1)
    else:
        following = dt.date(year, month + 1, 1)
    last = following - dt.timedelta(days=1)
    return last - dt.timedelta(days=(last.weekday() - weekday) % 7)


def _observed(day):
    """NYSE shifts a weekend holiday to the adjacent weekday."""
    if day.weekday() == 5:
        return day - dt.timedelta(days=1)
    if day.weekday() == 6:
        return day + dt.timedelta(days=1)
    return day


def holidays(year):
    """Full-day NYSE closures for a calendar year, already observed-shifted."""
    fixed = [
        dt.date(year, 1, 1),
        dt.date(year, 6, 19),
        dt.date(year, 7, 4),
        dt.date(year, 12, 25),
    ]
    days = {_observed(day) for day in fixed}
    days.add(_nth_weekday(year, 1, 0, 3))        # MLK Day
    days.add(_nth_weekday(year, 2, 0, 3))        # Washington's Birthday
    days.add(_easter(year) - dt.timedelta(days=2))   # Good Friday
    days.add(_last_weekday(year, 5, 0))          # Memorial Day
    days.add(_nth_weekday(year, 9, 0, 1))        # Labor Day
    days.add(_nth_weekday(year, 11, 3, 4))       # Thanksgiving
    return days


def early_close_days(year):
    """1pm ET closes. Each is only an early close when it lands on a day the
    market is otherwise open."""
    candidates = {
        _nth_weekday(year, 11, 3, 4) + dt.timedelta(days=1),   # day after Thanksgiving
        dt.date(year, 7, 3),
        dt.date(year, 12, 24),
    }
    closed = holidays(year)
    return {
        day for day in candidates
        if day.weekday() < 5 and day not in closed
    }


def is_trading_day(day):
    return day.weekday() < 5 and day not in holidays(day.year)


def session_state(when_utc):
    """One of 'premarket', 'regular', 'afterhours', 'closed'."""
    if when_utc.tzinfo is None:
        raise ValueError('session_state requires a timezone-aware UTC datetime')

    local = when_utc.astimezone(NY)
    day = local.date()
    if not is_trading_day(day):
        return 'closed'

    close = EARLY_CLOSE_END if day in early_close_days(day.year) else REGULAR_END
    now = local.time()

    if PREMARKET_START <= now < REGULAR_START:
        return 'premarket'
    if REGULAR_START <= now < close:
        return 'regular'
    if close <= now < AFTERHOURS_END:
        return 'afterhours'
    return 'closed'
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd personal_apps && python -m pytest tests/test_radar_calendar.py -v`
Expected: 12 passed

- [ ] **Step 5: Commit**

```bash
git add personal_apps/features/radar/market_calendar.py personal_apps/tests/test_radar_calendar.py
git commit -m "feat(radar): derive session state from the NYSE clock, not the German one"
```

---

## Task 3: Models and migration

**Files:**
- Modify: `personal_apps/models.py` (append at end of file)
- Create: `personal_apps/migrations/versions/<hash>_add_radar_tables.py`
- Test: `personal_apps/tests/test_radar_models.py`

**Interfaces:**
- Consumes: nothing
- Produces: `TickerUniverse`, `RadarPost`, `RadarMention`, `RadarBucket` importable from `models`

- [ ] **Step 1: Write the failing test**

```python
# personal_apps/tests/test_radar_models.py
"""Schema guards for the MariaDB specifics in spec 5.4.

These assert against the live dev database rather than the model metadata,
because the failures they guard against -- a rejected 4-byte insert, a
truncated body, a case-insensitive symbol match -- happen in the database and
not in SQLAlchemy.
"""
import datetime as dt

import pytest
import sqlalchemy as sa

from app import app as flask_app
from extensions import db
from models import RadarBucket, RadarMention, RadarPost, TickerUniverse


@pytest.fixture()
def ctx():
    with flask_app.app_context():
        yield


def _make_post(**overrides):
    fields = dict(
        source='reddit',
        external_id='t3_test_%s' % dt.datetime.utcnow().timestamp(),
        channel='wallstreetbets',
        author='someone',
        created_utc=dt.datetime(2026, 4, 15, 14, 0, 0),
        title='title',
        body='body',
        score=1,
        num_comments=0,
        url='https://example.invalid/x',
        simhash=0,
        first_seen=dt.datetime(2026, 4, 15, 14, 1, 0),
        last_seen=dt.datetime(2026, 4, 15, 14, 1, 0),
    )
    fields.update(overrides)
    return RadarPost(**fields)


def test_four_byte_characters_round_trip(ctx):
    """MariaDB's utf8 alias is utf8mb3 and would reject this. WSB posts are
    full of emoji, and a rejected insert is a silently dropped mention."""
    body = 'to the moon \U0001F680\U0001F4C8 diamond hands \U0001F48E\U0001F64C'
    post = _make_post(body=body)
    db.session.add(post)
    db.session.commit()
    db.session.expire(post)
    assert post.body == body
    db.session.delete(post)
    db.session.commit()


def test_body_holds_more_than_the_text_limit(ctx):
    """Reddit self-posts run to 40k characters, which exceeds TEXT under
    utf8mb4. MEDIUMTEXT or the tail is silently cut."""
    body = 'x' * 40000
    post = _make_post(body=body)
    db.session.add(post)
    db.session.commit()
    db.session.expire(post)
    assert len(post.body) == 40000
    db.session.delete(post)
    db.session.commit()


def test_symbol_lookup_is_case_sensitive(ctx):
    """utf8mb4_bin is what stops 'it' matching ticker IT. The cost is that
    extraction must uppercase before it looks anything up."""
    db.session.add(TickerUniverse(symbol='ZZTOP', name='Test Corp',
                                  exchange='TEST',
                                  first_seen=dt.datetime(2026, 1, 1)))
    db.session.commit()
    assert TickerUniverse.query.filter_by(symbol='ZZTOP').count() == 1
    assert TickerUniverse.query.filter_by(symbol='zztop').count() == 0
    TickerUniverse.query.filter_by(symbol='ZZTOP').delete()
    db.session.commit()


def test_bucket_unique_key_rejects_a_duplicate(ctx):
    start = dt.datetime(2026, 4, 15, 14, 0, 0)
    first = RadarBucket(ticker='ZZTOP', bucket_start=start, mention_count=1,
                        high_confidence_count=1, distinct_authors=1,
                        distinct_text_ratio=1.0, engagement_weighted_count=1.0,
                        count_reddit=1, count_stocktwits=0,
                        status_reddit='ok', status_stocktwits='missing',
                        sources_ok=1, source_config_version='deadbeefdeadbeef')
    db.session.add(first)
    db.session.commit()

    duplicate = RadarBucket(ticker='ZZTOP', bucket_start=start, mention_count=2,
                            high_confidence_count=2, distinct_authors=2,
                            distinct_text_ratio=1.0,
                            engagement_weighted_count=2.0,
                            count_reddit=2, count_stocktwits=0,
                            status_reddit='ok', status_stocktwits='missing',
                            sources_ok=1,
                            source_config_version='deadbeefdeadbeef')
    db.session.add(duplicate)
    with pytest.raises(sa.exc.IntegrityError):
        db.session.commit()
    db.session.rollback()

    RadarBucket.query.filter_by(ticker='ZZTOP').delete()
    db.session.commit()


def test_scoring_columns_start_null(ctx):
    """Plan 1 writes no scores. These columns exist so Plan 2 does not need a
    second migration, and they must be nullable until then."""
    start = dt.datetime(2026, 4, 15, 15, 0, 0)
    bucket = RadarBucket(ticker='ZZTOP', bucket_start=start, mention_count=1,
                         high_confidence_count=1, distinct_authors=1,
                         distinct_text_ratio=1.0, engagement_weighted_count=1.0,
                         count_reddit=1, count_stocktwits=0,
                         status_reddit='ok', status_stocktwits='missing',
                         sources_ok=1, source_config_version='deadbeefdeadbeef')
    db.session.add(bucket)
    db.session.commit()
    db.session.expire(bucket)
    assert bucket.mention_z_reddit is None
    assert bucket.mention_z_stocktwits is None
    assert bucket.baseline_days_reddit is None
    db.session.delete(bucket)
    db.session.commit()


def test_mention_cascades_when_its_post_is_deleted(ctx):
    post = _make_post()
    db.session.add(post)
    db.session.commit()
    db.session.add(RadarMention(post_id=post.id, ticker='ZZTOP',
                                confidence='high', lexicon_sentiment=0.5))
    db.session.commit()
    post_id = post.id
    db.session.delete(post)
    db.session.commit()
    assert RadarMention.query.filter_by(post_id=post_id).count() == 0
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd personal_apps && python -m pytest tests/test_radar_models.py -v`
Expected: FAIL with `ImportError: cannot import name 'RadarPost' from 'models'`

- [ ] **Step 3: Write minimal implementation**

Append to `personal_apps/models.py`:

```python
class TickerUniverse(db.Model):
    """Every symbol extraction is allowed to match.

    symbol is utf8mb4_bin so lookups are case-sensitive -- 'it' must not match
    ticker IT. Extraction uppercases candidates before it gets here.

    first_seen / delisted_at exist for symbol reassignment: a delisted symbol
    later given to a different company would otherwise inherit the old
    company's baseline, silently.
    """
    __tablename__ = 'radar_ticker_universe'
    __table_args__ = {'mysql_charset': 'utf8mb4'}

    id          = db.Column(db.Integer, primary_key=True, autoincrement=True)
    symbol      = db.Column(db.String(12, collation='utf8mb4_bin'),
                            nullable=False, unique=True, index=True)
    name        = db.Column(db.String(255), nullable=True)
    exchange    = db.Column(db.String(32), nullable=True)
    first_seen  = db.Column(db.DateTime(fsp=6), nullable=False)
    delisted_at = db.Column(db.DateTime(fsp=6), nullable=True)


class RadarPost(db.Model):
    """One ingested post or comment. 30-day rolling retention.

    body is MEDIUMTEXT: Reddit self-posts reach 40k characters, which is over
    the 64KB TEXT limit once utf8mb4 puts up to 4 bytes behind each one.
    """
    __tablename__ = 'radar_posts'
    __table_args__ = (
        db.UniqueConstraint('source', 'external_id', name='uq_radar_post_source_ext'),
        db.Index('ix_radar_posts_created_utc', 'created_utc'),
        {'mysql_charset': 'utf8mb4'},
    )

    id           = db.Column(db.BigInteger, primary_key=True, autoincrement=True)
    source       = db.Column(db.String(16), nullable=False)
    external_id  = db.Column(db.String(32), nullable=False)
    channel      = db.Column(db.String(64), nullable=False)
    author       = db.Column(db.String(64), nullable=True)
    created_utc  = db.Column(db.DateTime(fsp=6), nullable=False)
    title        = db.Column(db.String(512), nullable=True)
    body         = db.Column(MEDIUMTEXT, nullable=True)
    score        = db.Column(db.Integer, nullable=False, default=0)
    num_comments = db.Column(db.Integer, nullable=False, default=0)
    url          = db.Column(db.String(512), nullable=True)
    simhash      = db.Column(db.BigInteger, nullable=False, default=0)
    first_seen   = db.Column(db.DateTime(fsp=6), nullable=False)
    last_seen    = db.Column(db.DateTime(fsp=6), nullable=False)

    mentions = db.relationship('RadarMention', back_populates='post',
                               cascade='all, delete-orphan', lazy=True)


class RadarMention(db.Model):
    """One (post x ticker). Follows its post's retention."""
    __tablename__ = 'radar_mentions'
    __table_args__ = (
        db.Index('ix_radar_mentions_ticker_post', 'ticker', 'post_id'),
        db.Index('ix_radar_mentions_post', 'post_id'),
        {'mysql_charset': 'utf8mb4'},
    )

    id               = db.Column(db.BigInteger, primary_key=True, autoincrement=True)
    post_id          = db.Column(db.BigInteger,
                                 db.ForeignKey('radar_posts.id', ondelete='CASCADE'),
                                 nullable=False)
    ticker           = db.Column(db.String(12, collation='utf8mb4_bin'), nullable=False)
    confidence       = db.Column(db.Enum('high', 'medium', name='radar_confidence'),
                                 nullable=False)
    lexicon_sentiment = db.Column(db.Float, nullable=True)
    llm_sentiment     = db.Column(db.String(16), nullable=True)

    post = db.relationship('RadarPost', back_populates='mentions')


class RadarBucket(db.Model):
    """(ticker x 15 minutes). Retained forever; this is what scoring reads.

    Status is per source, not per bucket. With one column and two sources,
    StockTwits dropping while Reddit keeps working forces a choice between
    discarding good Reddit data and silently halving the count -- the second
    being exactly the baseline poisoning the status column exists to prevent
    (spec 4.5).

    The mention_z_* and baseline_days_* columns are written by Plan 2 and are
    NULL until then.
    """
    __tablename__ = 'radar_buckets'
    __table_args__ = (
        db.UniqueConstraint('ticker', 'bucket_start', name='uq_radar_bucket'),
        db.Index('ix_radar_buckets_start_ticker', 'bucket_start', 'ticker'),
        {'mysql_charset': 'utf8mb4'},
    )

    # The primary key is composite because this table is partitioned by
    # bucket_start, and MariaDB requires every unique key -- the primary key
    # included -- to contain every partitioning column. A bare `id` primary key
    # makes the partition ALTER fail with errno 1503. `id` stays leftmost so it
    # can still carry AUTO_INCREMENT.
    id                        = db.Column(db.BigInteger, primary_key=True, autoincrement=True)
    ticker                    = db.Column(db.String(12, collation='utf8mb4_bin'), nullable=False)
    bucket_start              = db.Column(db.DateTime(fsp=6), primary_key=True, nullable=False)

    mention_count             = db.Column(db.Integer, nullable=False, default=0)
    high_confidence_count     = db.Column(db.Integer, nullable=False, default=0)
    distinct_authors          = db.Column(db.Integer, nullable=False, default=0)
    distinct_text_ratio       = db.Column(db.Float, nullable=False, default=1.0)
    engagement_weighted_count = db.Column(db.Float, nullable=False, default=0.0)
    sentiment_mean            = db.Column(db.Float, nullable=True)
    sentiment_stdev           = db.Column(db.Float, nullable=True)

    count_reddit              = db.Column(db.Integer, nullable=False, default=0)
    count_stocktwits          = db.Column(db.Integer, nullable=False, default=0)

    status_reddit             = db.Column(
        db.Enum('ok', 'missing', 'truncated', name='radar_source_status'),
        nullable=False, default='missing')
    status_stocktwits         = db.Column(
        db.Enum('ok', 'missing', 'truncated', name='radar_source_status'),
        nullable=False, default='missing')
    sources_ok                = db.Column(db.SmallInteger, nullable=False, default=0)

    source_config_version     = db.Column(db.String(16), nullable=False)

    # Written by Plan 2.
    mention_z_reddit          = db.Column(db.Float, nullable=True)
    mention_z_stocktwits      = db.Column(db.Float, nullable=True)
    baseline_days_reddit      = db.Column(db.SmallInteger, nullable=True)
    baseline_days_stocktwits  = db.Column(db.SmallInteger, nullable=True)
```

`MEDIUMTEXT` needs an import. Add it to the existing import block at the top of `personal_apps/models.py`, above the model definitions:

```python
from sqlalchemy.dialects.mysql import MEDIUMTEXT
```

Generate the migration:

```bash
cd personal_apps && python -m flask --app app db migrate -m "add radar tables"
```

Then edit the generated file so the `upgrade()` ends with the partition statement, which Alembic cannot autogenerate:

```python
def upgrade():
    # ... autogenerated create_table calls stay as written ...

    # radar_buckets is retained forever. Monthly RANGE partitions keep the
    # 30-day baseline scan inside one or two partitions. The unique key
    # already contains bucket_start, which is what makes this legal.
    op.execute("""
        ALTER TABLE radar_buckets
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

- [ ] **Step 4: Apply the migration and run the tests**

```bash
cd personal_apps && python -m flask --app app db upgrade
```

Run: `cd personal_apps && python -m pytest tests/test_radar_models.py -v`
Expected: 6 passed

If `test_four_byte_characters_round_trip` fails with a truncation or encoding error, the table was created without `utf8mb4` — fix the migration, downgrade, re-upgrade. Do not work around it in Python.

- [ ] **Step 5: Commit**

```bash
git add personal_apps/models.py personal_apps/migrations/versions/ personal_apps/tests/test_radar_models.py
git commit -m "feat(radar): add the four ingest tables, with per-source status"
```

---

## Task 4: Text fingerprint and lexicon sentiment

**Files:**
- Create: `personal_apps/features/radar/fingerprint.py`
- Create: `personal_apps/features/radar/sentiment.py`
- Test: `personal_apps/tests/test_radar_text.py`

**Interfaces:**
- Consumes: nothing
- Produces:
  - `fingerprint.normalize(text: str) -> str`
  - `fingerprint.simhash64(text: str) -> int`
  - `sentiment.lexicon_score(text: str) -> float` — in `[-1.0, 1.0]`

- [ ] **Step 1: Write the failing test**

```python
# personal_apps/tests/test_radar_text.py
"""Distinct authors defeats one account posting fifty times. Distinct text
ratio is what defeats fifty accounts posting the same thing, which is the
actual shape of a brigade (spec 6.7).

The scope claim is deliberately narrow: exact-hash matching catches copy-paste
and low-effort templating. It does not catch paraphrase, and test_paraphrase_
is_not_caught pins that so nobody later describes this as a bot detector.
"""
from features.radar import fingerprint, sentiment


def test_identical_text_has_an_identical_hash():
    assert fingerprint.simhash64('GME to the moon') == fingerprint.simhash64('GME to the moon')


def test_hash_is_64_bit_unsigned():
    value = fingerprint.simhash64('some ordinary post body')
    assert 0 <= value < 2 ** 64


def test_copy_paste_survives_whitespace_and_case():
    a = fingerprint.simhash64('BUY GME NOW!!!   Squeeze  is coming')
    b = fingerprint.simhash64('buy gme now!!! squeeze is coming')
    assert a == b


def test_urls_are_stripped_so_referral_spam_collapses():
    a = fingerprint.simhash64('same pitch https://example.invalid/aaa')
    b = fingerprint.simhash64('same pitch https://example.invalid/bbb')
    assert a == b


def test_paraphrase_is_not_caught():
    """Documented limit, not a defect."""
    a = fingerprint.simhash64('GME is going to squeeze hard this week')
    b = fingerprint.simhash64('this week GME will see a serious short squeeze')
    assert a != b


def test_empty_text_is_stable():
    assert fingerprint.simhash64('') == fingerprint.simhash64('   ')


def test_bullish_text_scores_positive():
    assert sentiment.lexicon_score('this is a great buy, huge upside, bullish') > 0


def test_bearish_text_scores_negative():
    assert sentiment.lexicon_score('terrible earnings, this dumps, bearish crash') < 0


def test_neutral_text_scores_zero():
    assert sentiment.lexicon_score('the ticker was mentioned in a filing') == 0.0


def test_negation_flips_the_sign():
    assert sentiment.lexicon_score('not bullish at all') < 0


def test_score_is_bounded():
    shouting = 'bullish ' * 200
    assert -1.0 <= sentiment.lexicon_score(shouting) <= 1.0
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd personal_apps && python -m pytest tests/test_radar_text.py -v`
Expected: FAIL with `ImportError: cannot import name 'fingerprint'`

- [ ] **Step 3: Write minimal implementation**

```python
# personal_apps/features/radar/fingerprint.py
"""Near-duplicate detection for bucket-level distinct_text_ratio.

Exact simhash equality, not Hamming-distance clustering: the ratio only needs
to separate "fifty people said fifty things" from "fifty accounts pasted one
thing", and equality does that at a fraction of the cost. Paraphrase is out of
scope and stays out of scope (spec 6.7).
"""
import hashlib
import re

_URL_RE = re.compile(r'https?://\S+')
_NON_WORD_RE = re.compile(r'[^a-z0-9\s]+')
_WHITESPACE_RE = re.compile(r'\s+')

_BITS = 64


def normalize(text):
    """Lowercase, strip URLs and punctuation, collapse whitespace.

    URLs go first and entirely: referral spam is the same pitch with a
    different tracking code, and keeping the URL would make each copy unique.
    """
    lowered = (text or '').lower()
    without_urls = _URL_RE.sub(' ', lowered)
    without_punct = _NON_WORD_RE.sub(' ', without_urls)
    return _WHITESPACE_RE.sub(' ', without_punct).strip()


def _token_hash(token):
    digest = hashlib.blake2b(token.encode('utf-8'), digest_size=8).digest()
    return int.from_bytes(digest, 'big')


def simhash64(text):
    """A 64-bit simhash of the normalized text. Stable across processes --
    blake2b rather than hash(), whose seed is randomized per interpreter."""
    tokens = normalize(text).split()
    if not tokens:
        return 0

    weights = [0] * _BITS
    for token in tokens:
        value = _token_hash(token)
        for bit in range(_BITS):
            if value >> bit & 1:
                weights[bit] += 1
            else:
                weights[bit] -= 1

    result = 0
    for bit in range(_BITS):
        if weights[bit] > 0:
            result |= 1 << bit
    return result
```

```python
# personal_apps/features/radar/sentiment.py
"""Lexicon sentiment, applied to every mention at ingest.

Cheap and adequate for the long tail. It is knowingly weak on the sarcasm and
inverted positions WSB runs on -- that is what the Claude Haiku re-read on
radar top-N is for (spec 6.11), and the two scores disagreeing is itself the
signal that a post was one of those.
"""
import re

_WORD_RE = re.compile(r"[a-z']+")

_POSITIVE = {
    'bullish': 2.0, 'buy': 1.0, 'long': 0.5, 'calls': 1.0, 'moon': 1.5,
    'squeeze': 1.0, 'rip': 1.0, 'ripping': 1.5, 'great': 1.0, 'huge': 1.0,
    'upside': 1.5, 'undervalued': 1.5, 'beat': 1.0, 'strong': 1.0,
    'rally': 1.0, 'breakout': 1.5, 'green': 0.5, 'gains': 1.0, 'win': 1.0,
}

_NEGATIVE = {
    'bearish': 2.0, 'sell': 1.0, 'short': 0.5, 'puts': 1.0, 'crash': 1.5,
    'dump': 1.5, 'dumps': 1.5, 'dumping': 1.5, 'terrible': 1.5, 'bad': 1.0,
    'overvalued': 1.5, 'miss': 1.0, 'missed': 1.0, 'weak': 1.0, 'bag': 1.0,
    'bagholder': 1.5, 'red': 0.5, 'losses': 1.0, 'rug': 1.5, 'scam': 2.0,
}

_NEGATIONS = {'not', 'no', 'never', "isn't", "aint", "ain't", "doesn't", "don't"}

# How many tokens after a negation stay flipped.
_NEGATION_SCOPE = 3

# Divisor turning a raw sum into roughly [-1, 1] before clamping. Four strong
# words in one direction is already a maximally one-sided post.
_SCALE = 8.0


def lexicon_score(text):
    """A sentiment score in [-1.0, 1.0]. 0.0 means no lexicon words matched."""
    tokens = _WORD_RE.findall((text or '').lower())
    total = 0.0
    negated_until = -1

    for index, token in enumerate(tokens):
        if token in _NEGATIONS:
            negated_until = index + _NEGATION_SCOPE
            continue

        weight = _POSITIVE.get(token, 0.0) - _NEGATIVE.get(token, 0.0)
        if weight == 0.0:
            continue
        if index <= negated_until:
            weight = -weight
        total += weight

    return max(-1.0, min(1.0, total / _SCALE))
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd personal_apps && python -m pytest tests/test_radar_text.py -v`
Expected: 11 passed

- [ ] **Step 5: Commit**

```bash
git add personal_apps/features/radar/fingerprint.py personal_apps/features/radar/sentiment.py personal_apps/tests/test_radar_text.py
git commit -m "feat(radar): fingerprint post text and score it with a lexicon"
```

---

## Task 5: Ticker universe

**Files:**
- Create: `personal_apps/features/radar/universe.py`
- Test: `personal_apps/tests/test_radar_universe.py`

**Interfaces:**
- Consumes: `models.TickerUniverse`
- Produces:
  - `load_lookup() -> dict[str, dict]` — keyed by uppercase symbol, values have `name`, `exchange`
  - `upsert_symbols(rows: list[dict], now: datetime) -> dict[str, int]` — counts of `added`, `updated`, `reassigned`
  - `mark_delisted(symbols: list[str], now: datetime) -> int`

- [ ] **Step 1: Write the failing test**

```python
# personal_apps/tests/test_radar_universe.py
"""The universe is what bare-token extraction matches against.

The reassignment case is rare and silent when it happens: a delisted symbol
given to a different company would otherwise inherit the old company's
baseline, and every spike against that baseline would be wrong with no error
anywhere (spec 4.2).
"""
import datetime as dt

import pytest

from app import app as flask_app
from extensions import db
from models import TickerUniverse
from features.radar import universe


@pytest.fixture()
def clean_universe():
    with flask_app.app_context():
        TickerUniverse.query.filter(TickerUniverse.symbol.like('ZZ%')).delete(
            synchronize_session=False)
        db.session.commit()
        yield
        TickerUniverse.query.filter(TickerUniverse.symbol.like('ZZ%')).delete(
            synchronize_session=False)
        db.session.commit()


NOW = dt.datetime(2026, 4, 15, 12, 0, 0)


def test_upsert_adds_new_symbols(clean_universe):
    result = universe.upsert_symbols(
        [{'symbol': 'ZZA', 'name': 'Alpha Corp', 'exchange': 'NASDAQ'}], NOW)
    assert result['added'] == 1
    row = TickerUniverse.query.filter_by(symbol='ZZA').one()
    assert row.name == 'Alpha Corp'
    assert row.first_seen == NOW


def test_upsert_is_idempotent(clean_universe):
    rows = [{'symbol': 'ZZA', 'name': 'Alpha Corp', 'exchange': 'NASDAQ'}]
    universe.upsert_symbols(rows, NOW)
    second = universe.upsert_symbols(rows, NOW + dt.timedelta(days=7))
    assert second['added'] == 0
    assert TickerUniverse.query.filter_by(symbol='ZZA').count() == 1


def test_symbols_are_stored_uppercase(clean_universe):
    universe.upsert_symbols(
        [{'symbol': 'zzb', 'name': 'Beta Corp', 'exchange': 'NASDAQ'}], NOW)
    assert TickerUniverse.query.filter_by(symbol='ZZB').count() == 1


def test_reassignment_resets_first_seen(clean_universe):
    """Same symbol, different company, after a delisting. first_seen moving is
    what tells Plan 2's baseline to start over rather than continue."""
    universe.upsert_symbols(
        [{'symbol': 'ZZC', 'name': 'Old Company', 'exchange': 'NYSE'}], NOW)
    universe.mark_delisted(['ZZC'], NOW + dt.timedelta(days=30))

    later = NOW + dt.timedelta(days=200)
    result = universe.upsert_symbols(
        [{'symbol': 'ZZC', 'name': 'Totally Different Inc', 'exchange': 'NYSE'}],
        later)

    assert result['reassigned'] == 1
    row = TickerUniverse.query.filter_by(symbol='ZZC').one()
    assert row.name == 'Totally Different Inc'
    assert row.first_seen == later
    assert row.delisted_at is None


def test_a_rename_is_not_a_reassignment(clean_universe):
    """A live company changing its name keeps its history. Only a name change
    across a delisting is a reassignment."""
    universe.upsert_symbols(
        [{'symbol': 'ZZD', 'name': 'Acme Inc', 'exchange': 'NYSE'}], NOW)
    later = NOW + dt.timedelta(days=100)
    result = universe.upsert_symbols(
        [{'symbol': 'ZZD', 'name': 'Acme Holdings Inc', 'exchange': 'NYSE'}],
        later)

    assert result['reassigned'] == 0
    row = TickerUniverse.query.filter_by(symbol='ZZD').one()
    assert row.first_seen == NOW


def test_lookup_is_keyed_by_uppercase_symbol(clean_universe):
    universe.upsert_symbols(
        [{'symbol': 'ZZE', 'name': 'Echo Corp', 'exchange': 'NASDAQ'}], NOW)
    lookup = universe.load_lookup()
    assert 'ZZE' in lookup
    assert lookup['ZZE']['name'] == 'Echo Corp'
    assert 'zze' not in lookup


def test_delisted_symbols_stay_in_the_lookup(clean_universe):
    """A delisted ticker still gets talked about, and dropping it from the
    lookup would turn those mentions into silent misses."""
    universe.upsert_symbols(
        [{'symbol': 'ZZF', 'name': 'Foxtrot Corp', 'exchange': 'NYSE'}], NOW)
    universe.mark_delisted(['ZZF'], NOW + dt.timedelta(days=1))
    assert 'ZZF' in universe.load_lookup()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd personal_apps && python -m pytest tests/test_radar_universe.py -v`
Expected: FAIL with `ImportError: cannot import name 'universe'`

- [ ] **Step 3: Write minimal implementation**

```python
# personal_apps/features/radar/universe.py
"""The set of symbols extraction is allowed to match.

Seeded from a symbol listing and refreshed weekly. The interesting logic is
reassignment: a symbol that was delisted and later reappears under a different
company name is a different instrument, and continuing its baseline would make
every subsequent spike wrong with nothing to show for it in the logs.
"""
from extensions import db
from models import TickerUniverse


def _significant(name):
    """A comparable form of a company name.

    Legal-form suffixes are dropped so 'Acme Inc' and 'Acme Holdings Inc' can
    be recognized as the same company renaming itself rather than a new one.
    """
    if not name:
        return ''
    noise = {'inc', 'inc.', 'corp', 'corp.', 'corporation', 'co', 'co.',
             'ltd', 'ltd.', 'limited', 'plc', 'holdings', 'group', 'the',
             'company', 'sa', 'ag', 'nv'}
    words = [w for w in name.lower().replace(',', ' ').split() if w not in noise]
    return ' '.join(words)


def _is_reassignment(row, incoming_name):
    """A different company on a symbol that had been delisted.

    Both halves are required. A name change while listed is a rename; a
    delisting followed by the same name returning is a relisting.
    """
    if row.delisted_at is None:
        return False
    old = _significant(row.name)
    new = _significant(incoming_name)
    if not old or not new:
        return False
    return old.split()[:1] != new.split()[:1]


def upsert_symbols(rows, now):
    """Add or refresh universe rows. Returns counts of what happened."""
    counts = {'added': 0, 'updated': 0, 'reassigned': 0}

    for row in rows:
        symbol = (row.get('symbol') or '').strip().upper()
        if not symbol:
            continue
        name = row.get('name')
        exchange = row.get('exchange')

        existing = TickerUniverse.query.filter_by(symbol=symbol).one_or_none()
        if existing is None:
            db.session.add(TickerUniverse(symbol=symbol, name=name,
                                          exchange=exchange, first_seen=now))
            counts['added'] += 1
            continue

        if _is_reassignment(existing, name):
            existing.first_seen = now
            existing.delisted_at = None
            counts['reassigned'] += 1
        elif existing.delisted_at is not None:
            existing.delisted_at = None

        if existing.name != name or existing.exchange != exchange:
            counts['updated'] += 1
        existing.name = name
        existing.exchange = exchange

    db.session.commit()
    return counts


def mark_delisted(symbols, now):
    """Stamp delisted_at. The rows stay -- a delisted ticker still gets
    talked about, and dropping it would turn those mentions into silent
    misses rather than into recorded ones."""
    marked = 0
    for symbol in symbols:
        row = TickerUniverse.query.filter_by(
            symbol=symbol.strip().upper()).one_or_none()
        if row is not None and row.delisted_at is None:
            row.delisted_at = now
            marked += 1
    db.session.commit()
    return marked


def load_lookup():
    """Every symbol, keyed uppercase. Extraction uppercases candidates before
    it gets here -- the column is utf8mb4_bin and will not do it for us."""
    return {
        row.symbol: {'name': row.name, 'exchange': row.exchange}
        for row in TickerUniverse.query.all()
    }
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd personal_apps && python -m pytest tests/test_radar_universe.py -v`
Expected: 7 passed

- [ ] **Step 5: Commit**

```bash
git add personal_apps/features/radar/universe.py personal_apps/tests/test_radar_universe.py
git commit -m "feat(radar): keep a symbol universe that survives reassignment"
```

---

## Task 6: Ticker extraction

**Files:**
- Create: `personal_apps/features/radar/extraction.py`
- Test: `personal_apps/tests/test_radar_extraction.py`

**Interfaces:**
- Consumes: `config.STOPWORDS`, `universe.load_lookup()` shape
- Produces: `extract_tickers(title: str | None, body: str | None, lookup: dict) -> list[tuple[str, str]]` — `(symbol, confidence)`, confidence in `{'high', 'medium'}`, deduped with the highest confidence per symbol, sorted by symbol

- [ ] **Step 1: Write the failing test**

```python
# personal_apps/tests/test_radar_extraction.py
"""Extraction is the highest-risk component in the pipeline: every false
positive becomes a fake spike, and the fake spike looks exactly like a real
one downstream.

The corpus below is deliberately adversarial in both directions -- posts that
must yield tickers, and posts full of symbol-shaped tokens that must yield
none.
"""
from features.radar.extraction import extract_tickers

LOOKUP = {
    'GME': {'name': 'GameStop Corp', 'exchange': 'NYSE'},
    'AAPL': {'name': 'Apple Inc', 'exchange': 'NASDAQ'},
    'IT': {'name': 'Gartner Inc', 'exchange': 'NYSE'},
    'ALL': {'name': 'Allstate Corp', 'exchange': 'NYSE'},
    'DD': {'name': 'DuPont de Nemours Inc', 'exchange': 'NYSE'},
    'F': {'name': 'Ford Motor Company', 'exchange': 'NYSE'},
    'TSLA': {'name': 'Tesla Inc', 'exchange': 'NASDAQ'},
}


def symbols(title, body):
    return [symbol for symbol, _ in extract_tickers(title, body, LOOKUP)]


def test_cashtag_is_high_confidence():
    assert extract_tickers(None, 'loading up on $GME', LOOKUP) == [('GME', 'high')]


def test_cashtag_is_matched_case_insensitively_but_stored_upper():
    assert extract_tickers(None, 'buying $gme today', LOOKUP) == [('GME', 'high')]


def test_bare_symbol_is_medium_confidence():
    assert extract_tickers(None, 'AAPL looks strong here', LOOKUP) == [('AAPL', 'medium')]


def test_bare_symbol_with_company_name_is_promoted():
    result = extract_tickers('Apple earnings', 'AAPL reports tonight', LOOKUP)
    assert result == [('AAPL', 'high')]


def test_stopwords_are_rejected_as_bare_tokens():
    """The whole reason the blacklist exists. Every token here is a real
    ticker and none of them is being talked about."""
    text = 'DD on my ATH puts, IT is ALL priced in IMO, EOD PM CEO'
    assert symbols(None, text) == []


def test_a_stopword_as_a_cashtag_is_still_accepted():
    """An explicit $DD is unambiguous in a way bare DD is not."""
    assert extract_tickers(None, 'my $DD thesis', LOOKUP) == [('DD', 'high')]


def test_unknown_symbols_are_not_invented():
    assert symbols(None, 'ZZZZ and QQQQ are ripping') == []


def test_single_letter_bare_tokens_are_rejected():
    """F is a real ticker and also the most common one-letter token in
    English. Bare single letters are never worth the false positives."""
    assert symbols(None, 'F this market') == []


def test_single_letter_cashtag_is_accepted():
    assert extract_tickers(None, 'long $F into earnings', LOOKUP) == [('F', 'high')]


def test_title_and_body_are_both_scanned():
    assert symbols('GME thread', 'nothing here') == ['GME']


def test_duplicate_mentions_collapse_to_one():
    assert extract_tickers(None, 'GME GME GME', LOOKUP) == [('GME', 'medium')]


def test_highest_confidence_wins_for_one_symbol():
    result = extract_tickers(None, 'GME is moving, $GME calls', LOOKUP)
    assert result == [('GME', 'high')]


def test_multiple_symbols_are_sorted():
    result = symbols(None, '$TSLA and $AAPL and $GME')
    assert result == ['AAPL', 'GME', 'TSLA']


def test_possessives_and_punctuation_do_not_break_matching():
    assert symbols(None, "GME's move, (AAPL) too.") == ['AAPL', 'GME']


def test_lowercase_prose_is_not_a_ticker():
    """Bare matching is uppercase-only. 'it is all gme' must yield nothing --
    lowercase is prose, and treating it as symbols would match constantly."""
    assert symbols(None, 'it is all gme to me') == []


def test_empty_input_is_safe():
    assert extract_tickers(None, None, LOOKUP) == []
    assert extract_tickers('', '', LOOKUP) == []
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd personal_apps && python -m pytest tests/test_radar_extraction.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'features.radar.extraction'`

- [ ] **Step 3: Write minimal implementation**

```python
# personal_apps/features/radar/extraction.py
"""Ticker matching, in confidence tiers.

The asymmetry between cashtags and bare tokens is the whole design. `$DD` is a
deliberate act of notation and is taken at face value even for blacklisted
symbols; bare `DD` in a WSB post is almost always the phrase, not DuPont, and
is rejected. Bare matching is uppercase-only for the same reason -- lowercase
`it` is prose and would match on nearly every post ever written.
"""
import re

from .config import STOPWORDS

# Cashtags accept 1-5 letters. Bare tokens require 2-5: single uppercase
# letters are far more often sentence fragments, initials or profanity than
# they are Ford.
_CASHTAG_RE = re.compile(r'\$([A-Za-z]{1,5})\b')
_BARE_RE = re.compile(r'\b([A-Z]{2,5})\b')

_NAME_NOISE = {'inc', 'inc.', 'corp', 'corp.', 'corporation', 'co', 'co.',
               'ltd', 'ltd.', 'limited', 'plc', 'holdings', 'group', 'the',
               'company', 'motor', 'de'}

_CONFIDENCE_RANK = {'medium': 0, 'high': 1}


def _company_tokens(name):
    """The words of a company name worth looking for in a post body."""
    if not name:
        return set()
    words = re.findall(r"[A-Za-z']+", name.lower())
    return {w for w in words if w not in _NAME_NOISE and len(w) > 2}


def extract_tickers(title, body, lookup):
    """Return sorted (symbol, confidence) pairs for one post.

    lookup is universe.load_lookup()'s shape: uppercase symbol -> {'name',
    'exchange'}. Candidates are uppercased before lookup because the symbol
    column is utf8mb4_bin and will not fold case.
    """
    text = ' '.join(part for part in (title, body) if part)
    if not text.strip():
        return []

    lowered_words = set(re.findall(r"[a-z']+", text.lower()))
    found = {}

    def record(symbol, confidence):
        previous = found.get(symbol)
        if previous is None or _CONFIDENCE_RANK[confidence] > _CONFIDENCE_RANK[previous]:
            found[symbol] = confidence

    # Cashtags: explicit notation, accepted even for blacklisted symbols.
    for raw in _CASHTAG_RE.findall(text):
        symbol = raw.upper()
        if symbol in lookup:
            record(symbol, 'high')

    # Bare uppercase tokens: rejected if blacklisted, promoted if the company
    # name is nearby in the same post.
    for raw in _BARE_RE.findall(text):
        symbol = raw.upper()
        if symbol in STOPWORDS or symbol not in lookup:
            continue
        name_tokens = _company_tokens(lookup[symbol].get('name'))
        confidence = 'high' if name_tokens & lowered_words else 'medium'
        record(symbol, confidence)

    return sorted(found.items())
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd personal_apps && python -m pytest tests/test_radar_extraction.py -v`
Expected: 16 passed

- [ ] **Step 5: Commit**

```bash
git add personal_apps/features/radar/extraction.py personal_apps/tests/test_radar_extraction.py
git commit -m "feat(radar): extract tickers without turning every DD post into DuPont"
```

---

## Task 7: Source interface and the Reddit source

**Files:**
- Create: `personal_apps/features/radar/sources/__init__.py`
- Create: `personal_apps/features/radar/sources/reddit.py`
- Test: `personal_apps/tests/test_radar_reddit_source.py`

**Interfaces:**
- Consumes: `config.SUBREDDITS`, `config.PAGE_CAP`
- Produces:
  - `sources.RawPost` — dataclass with the spec §4.1 fields
  - `sources.FetchResult` — `posts: list[RawPost]`, `status: str`, `catchup_depth: int`
  - `reddit.fetch(since: datetime, client: RedditClient) -> FetchResult`
  - `reddit.RedditClient` — wraps OAuth and `get_listing(path, params) -> dict`

- [ ] **Step 1: Write the failing test**

```python
# personal_apps/tests/test_radar_reddit_source.py
"""Reddit's 100-item listing is comfortable at rest and far too small during a
squeeze, which is precisely when the data matters. Catch-up pagination is what
stops ingest silently truncating at the worst possible moment, and `truncated`
is what stops the undercount reaching a baseline (spec 4.3, 4.5).

Pagination walks *backwards* through /new using `after`. `before` returns items
NEWER than the given fullname and would loop on an empty page instead of
catching up -- test_pagination_uses_after pins that.
"""
import datetime as dt

from features.radar.sources import FetchResult, RawPost
from features.radar.sources import reddit


class FakeClient:
    """Serves canned listing pages and records the params it was called with."""

    def __init__(self, pages_by_path):
        self.pages_by_path = pages_by_path
        self.calls = []

    def get_listing(self, path, params):
        self.calls.append((path, dict(params)))
        pages = self.pages_by_path.get(path, [])
        after = params.get('after')
        index = 0
        if after is not None:
            index = next(i + 1 for i, page in enumerate(pages)
                         if page['data']['after'] == after)
        if index >= len(pages):
            return {'data': {'children': [], 'after': None}}
        return pages[index]


def _child(kind, ident, created, body='body', author='u1', score=1):
    return {
        'kind': kind,
        'data': {
            'id': ident,
            'name': '%s_%s' % (kind, ident),
            'author': author,
            'created_utc': created.replace(tzinfo=dt.timezone.utc).timestamp(),
            'title': 'a title' if kind == 't3' else None,
            'selftext': body if kind == 't3' else '',
            'body': body if kind == 't1' else '',
            'score': score,
            'num_comments': 0,
            'permalink': '/r/x/comments/%s/' % ident,
            'subreddit': 'wallstreetbets',
        },
    }


def _page(children, after):
    return {'data': {'children': children, 'after': after}}


BASE = dt.datetime(2026, 4, 15, 14, 0, 0)


def test_a_single_page_is_ok():
    client = FakeClient({
        '/r/wallstreetbets/new': [_page([_child('t3', 'a', BASE)], None)],
    })
    result = reddit.fetch(BASE - dt.timedelta(hours=1), client,
                          subreddits=('wallstreetbets',), kinds=('new',))
    assert isinstance(result, FetchResult)
    assert result.status == 'ok'
    assert [p.external_id for p in result.posts] == ['t3_a']


def test_posts_are_normalized_into_rawpost():
    client = FakeClient({
        '/r/wallstreetbets/new': [_page([_child('t3', 'a', BASE, body='GME')], None)],
    })
    post = reddit.fetch(BASE - dt.timedelta(hours=1), client,
                        subreddits=('wallstreetbets',), kinds=('new',)).posts[0]
    assert isinstance(post, RawPost)
    assert post.source == 'reddit'
    assert post.channel == 'wallstreetbets'
    assert post.body == 'GME'
    assert post.created_utc == BASE
    assert post.native_tickers == []
    assert post.native_sentiment is None


def test_pagination_uses_after_and_stops_at_since():
    """Two pages; `since` sits between them, so page 2 is fetched and its
    older items are dropped."""
    newer = _child('t3', 'a', BASE)
    older = _child('t3', 'b', BASE - dt.timedelta(hours=3))
    client = FakeClient({
        '/r/wallstreetbets/new': [
            _page([newer], 't3_a'),
            _page([older], None),
        ],
    })
    result = reddit.fetch(BASE - dt.timedelta(hours=1), client,
                          subreddits=('wallstreetbets',), kinds=('new',))
    assert [p.external_id for p in result.posts] == ['t3_a']
    assert result.status == 'ok'
    assert client.calls[1][1]['after'] == 't3_a'
    assert 'before' not in client.calls[1][1]


def test_hitting_the_page_cap_marks_truncated():
    """Every page is full of items newer than `since`, so catch-up never
    completes. The data returned is real but incomplete, and only the status
    records that."""
    pages = [_page([_child('t3', str(i), BASE)], 't3_%d' % i) for i in range(20)]
    client = FakeClient({'/r/wallstreetbets/new': pages})
    result = reddit.fetch(BASE - dt.timedelta(hours=1), client,
                          subreddits=('wallstreetbets',), kinds=('new',),
                          page_cap=3)
    assert result.status == 'truncated'
    assert result.catchup_depth == 3
    assert len(result.posts) == 3


def test_a_client_error_marks_missing_and_returns_no_posts():
    """`missing` must never be expressed as a zero count -- that is the
    baseline poisoning the status column exists to prevent."""
    class Failing:
        def get_listing(self, path, params):
            raise reddit.RedditUnavailable('503')

    result = reddit.fetch(BASE - dt.timedelta(hours=1), Failing(),
                          subreddits=('wallstreetbets',), kinds=('new',))
    assert result.status == 'missing'
    assert result.posts == []


def test_one_subreddit_failing_does_not_lose_the_others():
    class PartlyFailing(FakeClient):
        def get_listing(self, path, params):
            if path.startswith('/r/stocks'):
                raise reddit.RedditUnavailable('503')
            return super().get_listing(path, params)

    client = PartlyFailing({
        '/r/wallstreetbets/new': [_page([_child('t3', 'a', BASE)], None)],
    })
    result = reddit.fetch(BASE - dt.timedelta(hours=1), client,
                          subreddits=('wallstreetbets', 'stocks'), kinds=('new',))
    assert [p.external_id for p in result.posts] == ['t3_a']
    assert result.status == 'truncated'


def test_comments_are_ingested_too():
    """A large share of ticker mentions live in comment threads."""
    client = FakeClient({
        '/r/wallstreetbets/comments': [
            _page([_child('t1', 'c', BASE, body='GME squeeze')], None)],
    })
    result = reddit.fetch(BASE - dt.timedelta(hours=1), client,
                          subreddits=('wallstreetbets',), kinds=('comments',))
    assert result.posts[0].external_id == 't1_c'
    assert result.posts[0].title is None
    assert result.posts[0].body == 'GME squeeze'


def test_deleted_bodies_are_normalized_to_empty():
    client = FakeClient({
        '/r/wallstreetbets/new': [
            _page([_child('t3', 'a', BASE, body='[deleted]', author='[deleted]')],
                  None)],
    })
    post = reddit.fetch(BASE - dt.timedelta(hours=1), client,
                        subreddits=('wallstreetbets',), kinds=('new',)).posts[0]
    assert post.body == ''
    assert post.author is None
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd personal_apps && python -m pytest tests/test_radar_reddit_source.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'features.radar.sources'`

- [ ] **Step 3: Write minimal implementation**

```python
# personal_apps/features/radar/sources/__init__.py
"""The normalized shape every source produces.

Two sources exist in the design and one is implemented; nothing downstream may
assume which. status is per source per cycle and is what the rollup writes onto
buckets -- a source returning rows is not automatically `ok`, because hitting
the page cap makes it `truncated` (spec 4.1, 4.5).
"""
import dataclasses
import datetime as dt


@dataclasses.dataclass
class RawPost:
    source: str
    external_id: str
    channel: str
    author: str | None
    created_utc: dt.datetime
    title: str | None
    body: str
    score: int
    num_comments: int
    url: str
    native_tickers: list = dataclasses.field(default_factory=list)
    native_sentiment: str | None = None


@dataclasses.dataclass
class FetchResult:
    posts: list
    status: str            # 'ok' | 'missing' | 'truncated'
    catchup_depth: int = 0
```

```python
# personal_apps/features/radar/sources/reddit.py
"""Reddit ingest.

Catch-up pagination walks backwards through /new with `after` until it reaches
items older than `since`. `before` would be wrong here: it returns items NEWER
than the given fullname, so a catch-up loop built on it fetches an empty page
and concludes it is up to date while a squeeze is still being written.

Uses `requests` directly rather than a Reddit client library -- the surface used
is two endpoints and one token grant, and the dependency is not worth it.
"""
import datetime as dt

import requests

from . import FetchResult, RawPost
from ..config import PAGE_CAP, SUBREDDITS

USER_AGENT_DEFAULT = 'personal_apps-radar/0.1'
TOKEN_URL = 'https://www.reddit.com/api/v1/access_token'
API_BASE = 'https://oauth.reddit.com'

_DELETED = {'[deleted]', '[removed]'}


class RedditUnavailable(Exception):
    """Any failure that means this cycle did not get the data. Callers turn
    this into a `missing` or `truncated` status -- never into a zero count."""


class RedditClient:
    """OAuth token handling and one listing call.

    Credentials come from the environment: REDDIT_CLIENT_ID,
    REDDIT_CLIENT_SECRET, REDDIT_USERNAME, REDDIT_PASSWORD, REDDIT_USER_AGENT.
    """

    def __init__(self, client_id, client_secret, username, password,
                 user_agent=USER_AGENT_DEFAULT, timeout=15):
        self._auth = (client_id, client_secret)
        self._credentials = {'grant_type': 'password',
                             'username': username, 'password': password}
        self._headers = {'User-Agent': user_agent}
        self._timeout = timeout
        self._token = None
        self._token_expires = dt.datetime.min.replace(tzinfo=dt.timezone.utc)

    def _ensure_token(self):
        now = dt.datetime.now(dt.timezone.utc)
        if self._token and now < self._token_expires:
            return
        try:
            response = requests.post(TOKEN_URL, auth=self._auth,
                                     data=self._credentials,
                                     headers=self._headers,
                                     timeout=self._timeout)
            response.raise_for_status()
            payload = response.json()
        except (requests.RequestException, ValueError) as exc:
            raise RedditUnavailable('token request failed: %s' % exc) from exc

        self._token = payload['access_token']
        # Renew a minute early rather than discovering expiry mid-catch-up.
        lifetime = int(payload.get('expires_in', 3600)) - 60
        self._token_expires = now + dt.timedelta(seconds=max(lifetime, 60))

    def get_listing(self, path, params):
        self._ensure_token()
        headers = dict(self._headers)
        headers['Authorization'] = 'Bearer %s' % self._token
        try:
            response = requests.get(API_BASE + path, params=params,
                                    headers=headers, timeout=self._timeout)
            response.raise_for_status()
            return response.json()
        except (requests.RequestException, ValueError) as exc:
            raise RedditUnavailable('listing %s failed: %s' % (path, exc)) from exc


def _clean(value):
    """Reddit writes '[deleted]' into the field rather than clearing it."""
    if value is None:
        return None
    return None if value in _DELETED else value


def _to_raw_post(child):
    kind = child['kind']
    data = child['data']
    body = data.get('selftext') if kind == 't3' else data.get('body')
    body = _clean(body) or ''

    return RawPost(
        source='reddit',
        external_id=data.get('name') or '%s_%s' % (kind, data['id']),
        channel=data.get('subreddit') or '',
        author=_clean(data.get('author')),
        created_utc=dt.datetime.utcfromtimestamp(float(data['created_utc'])),
        title=_clean(data.get('title')) if kind == 't3' else None,
        body=body,
        score=int(data.get('score') or 0),
        num_comments=int(data.get('num_comments') or 0),
        url='https://www.reddit.com%s' % (data.get('permalink') or ''),
    )


def _fetch_one(client, path, since, page_cap):
    """Walk one listing backwards until items predate `since`.

    Returns (posts, hit_cap). Raises RedditUnavailable if the listing could
    not be read at all.
    """
    posts = []
    after = None
    for depth in range(page_cap):
        params = {'limit': 100, 'raw_json': 1}
        if after is not None:
            params['after'] = after

        payload = client.get_listing(path, params)
        data = payload.get('data') or {}
        children = data.get('children') or []
        if not children:
            return posts, False, depth + 1

        caught_up = False
        for child in children:
            post = _to_raw_post(child)
            if post.created_utc <= since:
                caught_up = True
                continue
            posts.append(post)

        after = data.get('after')
        if caught_up or after is None:
            return posts, False, depth + 1

    return posts, True, page_cap


def fetch(since, client, subreddits=SUBREDDITS, kinds=('new', 'comments'),
          page_cap=PAGE_CAP):
    """Everything posted after `since` across the configured subreddits.

    status is the worst outcome across all listings walked:
      - every listing complete            -> 'ok'
      - any listing capped, or any single listing unreadable while others
        succeeded                          -> 'truncated'
      - nothing readable at all            -> 'missing'
    """
    posts = []
    deepest = 0
    capped = False
    failures = 0
    attempts = 0

    for subreddit in subreddits:
        for kind in kinds:
            attempts += 1
            path = '/r/%s/%s' % (subreddit, kind)
            try:
                found, hit_cap, depth = _fetch_one(client, path, since, page_cap)
            except RedditUnavailable:
                failures += 1
                continue
            posts.extend(found)
            deepest = max(deepest, depth)
            capped = capped or hit_cap

    if failures == attempts:
        return FetchResult(posts=[], status='missing', catchup_depth=0)

    status = 'truncated' if (capped or failures) else 'ok'
    return FetchResult(posts=posts, status=status, catchup_depth=deepest)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd personal_apps && python -m pytest tests/test_radar_reddit_source.py -v`
Expected: 8 passed

- [ ] **Step 5: Commit**

```bash
git add personal_apps/features/radar/sources/ personal_apps/tests/test_radar_reddit_source.py
git commit -m "feat(radar): catch up through Reddit listings instead of truncating silently"
```

---

## Task 8: Bucket rollup

**Files:**
- Create: `personal_apps/features/radar/buckets.py`
- Test: `personal_apps/tests/test_radar_buckets.py`

**Interfaces:**
- Consumes: `models.RadarBucket`, `config.BUCKET_MINUTES`, `config.source_config_version()`
- Produces:
  - `bucket_start_for(when: datetime) -> datetime`
  - `MentionRow` — dataclass: `ticker`, `created_utc`, `source`, `author`, `simhash`, `confidence`, `sentiment`, `engagement`
  - `roll_up(rows: list[MentionRow], statuses: dict[str, str], touched: set[datetime]) -> int` — upserts buckets, returns rows written

- [ ] **Step 1: Write the failing test**

```python
# personal_apps/tests/test_radar_buckets.py
"""The rollup is where per-source status becomes durable.

`truncated` is the subtle case: those counts are real but incomplete, so they
must be visible on the live leaderboard while being barred from any baseline.
Plan 2 enforces the second half; this suite pins that the status reaches the
row at all, because a bucket written `ok` when it was truncated is
indistinguishable from a genuine quiet period forever after.
"""
import datetime as dt

import pytest

from app import app as flask_app
from extensions import db
from models import RadarBucket
from features.radar import buckets
from features.radar.config import source_config_version


@pytest.fixture()
def clean_buckets():
    with flask_app.app_context():
        RadarBucket.query.filter(RadarBucket.ticker.like('ZZ%')).delete(
            synchronize_session=False)
        db.session.commit()
        yield
        RadarBucket.query.filter(RadarBucket.ticker.like('ZZ%')).delete(
            synchronize_session=False)
        db.session.commit()


def row(ticker='ZZA', minute=3, source='reddit', author='u1', simhash=111,
        confidence='high', sentiment=0.5, engagement=10.0):
    return buckets.MentionRow(
        ticker=ticker,
        created_utc=dt.datetime(2026, 4, 15, 14, minute, 0),
        source=source, author=author, simhash=simhash,
        confidence=confidence, sentiment=sentiment, engagement=engagement)


ALL_OK = {'reddit': 'ok', 'stocktwits': 'missing'}


def test_bucket_start_floors_to_fifteen_minutes():
    assert buckets.bucket_start_for(dt.datetime(2026, 4, 15, 14, 3, 59)) == \
        dt.datetime(2026, 4, 15, 14, 0, 0)
    assert buckets.bucket_start_for(dt.datetime(2026, 4, 15, 14, 44, 0)) == \
        dt.datetime(2026, 4, 15, 14, 30, 0)


def test_counts_are_written(clean_buckets):
    buckets.roll_up([row(author='u1', simhash=1), row(author='u2', simhash=2)],
                    ALL_OK, {dt.datetime(2026, 4, 15, 14, 0, 0)})
    bucket = RadarBucket.query.filter_by(ticker='ZZA').one()
    assert bucket.mention_count == 2
    assert bucket.distinct_authors == 2
    assert bucket.count_reddit == 2
    assert bucket.high_confidence_count == 2


def test_distinct_text_ratio_catches_a_copy_paste_brigade(clean_buckets):
    """Fifty accounts posting one thing. distinct_authors sees nothing wrong;
    this is the column that does."""
    rows = [row(author='u%d' % i, simhash=999) for i in range(4)]
    buckets.roll_up(rows, ALL_OK, {dt.datetime(2026, 4, 15, 14, 0, 0)})
    bucket = RadarBucket.query.filter_by(ticker='ZZA').one()
    assert bucket.distinct_authors == 4
    assert bucket.distinct_text_ratio == pytest.approx(0.25)


def test_per_source_status_is_stored_separately(clean_buckets):
    buckets.roll_up([row()], {'reddit': 'ok', 'stocktwits': 'missing'},
                    {dt.datetime(2026, 4, 15, 14, 0, 0)})
    bucket = RadarBucket.query.filter_by(ticker='ZZA').one()
    assert bucket.status_reddit == 'ok'
    assert bucket.status_stocktwits == 'missing'
    assert bucket.sources_ok == 1


def test_truncated_counts_are_kept_and_marked(clean_buckets):
    buckets.roll_up([row()], {'reddit': 'truncated', 'stocktwits': 'missing'},
                    {dt.datetime(2026, 4, 15, 14, 0, 0)})
    bucket = RadarBucket.query.filter_by(ticker='ZZA').one()
    assert bucket.mention_count == 1
    assert bucket.status_reddit == 'truncated'
    assert bucket.sources_ok == 0


def test_a_missing_source_writes_no_bucket_rather_than_a_zero(clean_buckets):
    """The single most important rule in the ingest layer. A zero here would
    poison the baseline and manufacture a spike when ingest resumes."""
    written = buckets.roll_up([], {'reddit': 'missing', 'stocktwits': 'missing'},
                              {dt.datetime(2026, 4, 15, 14, 0, 0)})
    assert written == 0
    assert RadarBucket.query.filter_by(ticker='ZZA').count() == 0


def test_rerunning_a_cycle_replaces_rather_than_doubles(clean_buckets):
    start = {dt.datetime(2026, 4, 15, 14, 0, 0)}
    buckets.roll_up([row(author='u1', simhash=1)], ALL_OK, start)
    buckets.roll_up([row(author='u1', simhash=1), row(author='u2', simhash=2)],
                    ALL_OK, start)
    bucket = RadarBucket.query.filter_by(ticker='ZZA').one()
    assert bucket.mention_count == 2


def test_mentions_split_across_bucket_boundaries(clean_buckets):
    touched = {dt.datetime(2026, 4, 15, 14, 0, 0),
               dt.datetime(2026, 4, 15, 14, 15, 0)}
    buckets.roll_up([row(minute=3), row(minute=20)], ALL_OK, touched)
    assert RadarBucket.query.filter_by(ticker='ZZA').count() == 2


def test_config_version_is_stamped(clean_buckets):
    buckets.roll_up([row()], ALL_OK, {dt.datetime(2026, 4, 15, 14, 0, 0)})
    bucket = RadarBucket.query.filter_by(ticker='ZZA').one()
    assert bucket.source_config_version == source_config_version()


def test_sentiment_mean_is_averaged(clean_buckets):
    buckets.roll_up([row(sentiment=1.0, author='u1', simhash=1),
                     row(sentiment=0.0, author='u2', simhash=2)],
                    ALL_OK, {dt.datetime(2026, 4, 15, 14, 0, 0)})
    bucket = RadarBucket.query.filter_by(ticker='ZZA').one()
    assert bucket.sentiment_mean == pytest.approx(0.5)


def test_scoring_columns_are_left_untouched(clean_buckets):
    """Plan 1 writes no scores. A rollup that reset these would silently
    invalidate Plan 2's work on every cycle."""
    buckets.roll_up([row()], ALL_OK, {dt.datetime(2026, 4, 15, 14, 0, 0)})
    bucket = RadarBucket.query.filter_by(ticker='ZZA').one()
    bucket.mention_z_reddit = 4.2
    db.session.commit()

    buckets.roll_up([row(), row(author='u2', simhash=2)], ALL_OK,
                    {dt.datetime(2026, 4, 15, 14, 0, 0)})
    db.session.expire(bucket)
    assert bucket.mention_z_reddit == 4.2
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd personal_apps && python -m pytest tests/test_radar_buckets.py -v`
Expected: FAIL with `ImportError: cannot import name 'buckets'`

- [ ] **Step 3: Write minimal implementation**

```python
# personal_apps/features/radar/buckets.py
"""Rollup from mentions to (ticker x 15 minutes).

Two rules carry the weight here.

A source that failed writes no row at all. Writing zero would be
indistinguishable from a genuinely quiet quarter-hour, would drag the trailing
mean down, and would manufacture a spike the moment ingest resumed -- which is
the whole reason status is per source rather than per bucket (spec 4.5).

A rerun of the same window replaces its counts rather than adding to them.
Cycles overlap by design, since catch-up re-reads the boundary, and additive
rollup would inflate every bucket that spans two cycles.
"""
import dataclasses
import datetime as dt
import statistics

from extensions import db
from models import RadarBucket

from .config import BUCKET_MINUTES, source_config_version

SOURCES = ('reddit', 'stocktwits')

# Statuses whose counts are real enough to store. `missing` is not one:
# see the module docstring.
_COUNTABLE = {'ok', 'truncated'}


@dataclasses.dataclass
class MentionRow:
    """One extracted mention, flattened for rollup."""
    ticker: str
    created_utc: dt.datetime
    source: str
    author: str | None
    simhash: int
    confidence: str
    sentiment: float | None
    engagement: float


def bucket_start_for(when):
    """Floor a UTC instant to its 15-minute bucket."""
    return when.replace(minute=(when.minute // BUCKET_MINUTES) * BUCKET_MINUTES,
                        second=0, microsecond=0)


def _summarize(rows):
    authors = {r.author for r in rows if r.author}
    hashes = {r.simhash for r in rows}
    sentiments = [r.sentiment for r in rows if r.sentiment is not None]

    return {
        'mention_count': len(rows),
        'high_confidence_count': sum(1 for r in rows if r.confidence == 'high'),
        'distinct_authors': len(authors),
        'distinct_text_ratio': (len(hashes) / len(rows)) if rows else 1.0,
        'engagement_weighted_count': sum(r.engagement for r in rows),
        'count_reddit': sum(1 for r in rows if r.source == 'reddit'),
        'count_stocktwits': sum(1 for r in rows if r.source == 'stocktwits'),
        'sentiment_mean': (sum(sentiments) / len(sentiments)) if sentiments else None,
        'sentiment_stdev': (statistics.pstdev(sentiments)
                            if len(sentiments) > 1 else None),
    }


def roll_up(rows, statuses, touched):
    """Write buckets for `touched` windows from `rows`.

    statuses maps source name to 'ok' | 'missing' | 'truncated' for this
    cycle. touched is the set of bucket starts the cycle covered, passed in
    rather than derived from rows so that a window which produced no mentions
    from a healthy source still records a genuine zero.

    Returns the number of bucket rows written.
    """
    countable = [source for source in SOURCES
                 if statuses.get(source, 'missing') in _COUNTABLE]
    if not countable:
        return 0

    version = source_config_version()
    sources_ok = sum(1 for source in SOURCES
                     if statuses.get(source, 'missing') == 'ok')

    grouped = {}
    for row in rows:
        if row.source not in countable:
            continue
        key = (row.ticker, bucket_start_for(row.created_utc))
        grouped.setdefault(key, []).append(row)

    written = 0
    for (ticker, start), bucket_rows in grouped.items():
        if start not in touched:
            continue

        values = _summarize(bucket_rows)
        existing = RadarBucket.query.filter_by(
            ticker=ticker, bucket_start=start).one_or_none()

        if existing is None:
            existing = RadarBucket(ticker=ticker, bucket_start=start)
            db.session.add(existing)

        for field, value in values.items():
            setattr(existing, field, value)
        existing.status_reddit = statuses.get('reddit', 'missing')
        existing.status_stocktwits = statuses.get('stocktwits', 'missing')
        existing.sources_ok = sources_ok
        existing.source_config_version = version
        written += 1

    db.session.commit()
    return written
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd personal_apps && python -m pytest tests/test_radar_buckets.py -v`
Expected: 11 passed

- [ ] **Step 5: Commit**

```bash
git add personal_apps/features/radar/buckets.py personal_apps/tests/test_radar_buckets.py
git commit -m "feat(radar): roll mentions into buckets that never fake a zero"
```

---

## Task 9: Ingest orchestration

**Files:**
- Create: `personal_apps/features/radar/ingest.py`
- Test: `personal_apps/tests/test_radar_ingest.py`

**Interfaces:**
- Consumes: `sources.reddit.fetch`, `extraction.extract_tickers`, `universe.load_lookup`, `fingerprint.simhash64`, `sentiment.lexicon_score`, `buckets.roll_up`
- Produces: `run_cycle(now: datetime, fetcher: callable) -> dict` with keys `posts_seen`, `posts_new`, `mentions`, `buckets_written`, `status`, `catchup_depth`

- [ ] **Step 1: Write the failing test**

```python
# personal_apps/tests/test_radar_ingest.py
"""End-to-end through the pipeline with the network replaced by a callable.

The deleted-post case is the one worth reading twice: the text goes, the counts
stay. Removing the mention rows would rewrite history every time a user deleted
a post, and the aggregate fact that a ticker was discussed is not what needs
forgetting (spec 4.1).
"""
import datetime as dt

import pytest

from app import app as flask_app
from extensions import db
from models import RadarBucket, RadarMention, RadarPost, TickerUniverse
from features.radar import ingest
from features.radar.sources import FetchResult, RawPost

NOW = dt.datetime(2026, 4, 15, 14, 20, 0)


@pytest.fixture()
def seeded(clean_radar):
    with flask_app.app_context():
        db.session.add(TickerUniverse(symbol='ZZG', name='Zulu Games Corp',
                                      exchange='NYSE',
                                      first_seen=dt.datetime(2026, 1, 1)))
        db.session.commit()
        yield


@pytest.fixture()
def clean_radar():
    with flask_app.app_context():
        RadarPost.query.filter(RadarPost.channel == 'testsub').delete(
            synchronize_session=False)
        RadarBucket.query.filter(RadarBucket.ticker.like('ZZ%')).delete(
            synchronize_session=False)
        TickerUniverse.query.filter(TickerUniverse.symbol.like('ZZ%')).delete(
            synchronize_session=False)
        db.session.commit()
        yield
        RadarPost.query.filter(RadarPost.channel == 'testsub').delete(
            synchronize_session=False)
        RadarBucket.query.filter(RadarBucket.ticker.like('ZZ%')).delete(
            synchronize_session=False)
        TickerUniverse.query.filter(TickerUniverse.symbol.like('ZZ%')).delete(
            synchronize_session=False)
        db.session.commit()


def post(ident='t3_1', body='$ZZG is ripping', score=5, author='u1',
         minute=10, title=None):
    return RawPost(source='reddit', external_id=ident, channel='testsub',
                   author=author,
                   created_utc=dt.datetime(2026, 4, 15, 14, minute, 0),
                   title=title, body=body, score=score, num_comments=0,
                   url='https://example.invalid/%s' % ident)


def fetcher_for(result):
    def fetcher(since):
        return result
    return fetcher


def test_a_post_becomes_a_mention_and_a_bucket(seeded):
    result = ingest.run_cycle(
        NOW, fetcher_for(FetchResult(posts=[post()], status='ok')))

    assert result['posts_new'] == 1
    assert result['mentions'] == 1
    assert result['buckets_written'] == 1

    with flask_app.app_context():
        stored = RadarPost.query.filter_by(external_id='t3_1').one()
        assert stored.simhash != 0
        mention = RadarMention.query.filter_by(post_id=stored.id).one()
        assert mention.ticker == 'ZZG'
        assert mention.confidence == 'high'
        assert mention.lexicon_sentiment is not None
        bucket = RadarBucket.query.filter_by(ticker='ZZG').one()
        assert bucket.mention_count == 1


def test_reseeing_a_post_updates_its_score_without_duplicating(seeded):
    ingest.run_cycle(NOW, fetcher_for(FetchResult(posts=[post(score=5)], status='ok')))
    result = ingest.run_cycle(
        NOW, fetcher_for(FetchResult(posts=[post(score=900)], status='ok')))

    assert result['posts_new'] == 0
    with flask_app.app_context():
        assert RadarPost.query.filter_by(external_id='t3_1').count() == 1
        assert RadarPost.query.filter_by(external_id='t3_1').one().score == 900


def test_a_deleted_post_loses_its_text_but_keeps_its_counts(seeded):
    ingest.run_cycle(NOW, fetcher_for(FetchResult(posts=[post()], status='ok')))
    ingest.run_cycle(
        NOW,
        fetcher_for(FetchResult(posts=[post(body='', author=None)], status='ok')))

    with flask_app.app_context():
        stored = RadarPost.query.filter_by(external_id='t3_1').one()
        assert stored.body == ''
        assert RadarMention.query.filter_by(post_id=stored.id).count() == 1
        assert RadarBucket.query.filter_by(ticker='ZZG').one().mention_count == 1


def test_a_missing_source_writes_nothing_at_all(seeded):
    result = ingest.run_cycle(
        NOW, fetcher_for(FetchResult(posts=[], status='missing')))

    assert result['status'] == 'missing'
    assert result['buckets_written'] == 0
    with flask_app.app_context():
        assert RadarBucket.query.filter(RadarBucket.ticker.like('ZZ%')).count() == 0


def test_a_truncated_cycle_still_stores_its_mentions(seeded):
    result = ingest.run_cycle(
        NOW, fetcher_for(FetchResult(posts=[post()], status='truncated',
                                     catchup_depth=10)))

    assert result['status'] == 'truncated'
    assert result['catchup_depth'] == 10
    with flask_app.app_context():
        bucket = RadarBucket.query.filter_by(ticker='ZZG').one()
        assert bucket.mention_count == 1
        assert bucket.status_reddit == 'truncated'


def test_posts_with_no_recognizable_ticker_are_stored_but_bucket_nothing(seeded):
    """Storing them is what makes the next cycle's `since` correct."""
    result = ingest.run_cycle(
        NOW,
        fetcher_for(FetchResult(posts=[post(body='market feels weird today')],
                                status='ok')))

    assert result['posts_new'] == 1
    assert result['mentions'] == 0
    with flask_app.app_context():
        assert RadarBucket.query.filter(RadarBucket.ticker.like('ZZ%')).count() == 0


def test_since_advances_to_the_newest_stored_post(seeded):
    captured = {}

    def fetcher(since):
        captured['since'] = since
        return FetchResult(posts=[post(minute=10)], status='ok')

    ingest.run_cycle(NOW, fetcher)
    ingest.run_cycle(NOW, fetcher)
    assert captured['since'] == dt.datetime(2026, 4, 15, 14, 10, 0)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd personal_apps && python -m pytest tests/test_radar_ingest.py -v`
Expected: FAIL with `ImportError: cannot import name 'ingest'`

- [ ] **Step 3: Write minimal implementation**

```python
# personal_apps/features/radar/ingest.py
"""One ingest cycle: fetch, store, extract, roll up.

The fetcher is injected rather than imported so the whole pipeline is testable
without a network, which spec 10 requires. run_radar_ingest.py supplies the
real one.
"""
import datetime as dt

import sqlalchemy as sa

from extensions import db
from models import RadarMention, RadarPost

from . import buckets, extraction, fingerprint, sentiment, universe
from .config import BUCKET_MINUTES

# How far back a cycle rolls up when there is no stored history yet.
_COLD_START_WINDOW = dt.timedelta(hours=2)


def _since_for(source):
    """The newest stored post for a source, or a cold-start window.

    Driven by stored data rather than by a clock, so a daemon restart or a
    missed cycle catches up instead of leaving a hole.
    """
    newest = db.session.query(sa.func.max(RadarPost.created_utc)).filter(
        RadarPost.source == source).scalar()
    return newest if newest is not None else dt.datetime.utcnow() - _COLD_START_WINDOW


def _store_posts(raw_posts, now):
    """Upsert posts. Returns {external_id: RadarPost} and a new-post count."""
    if not raw_posts:
        return {}, 0

    ids = [p.external_id for p in raw_posts]
    existing = {
        row.external_id: row
        for row in RadarPost.query.filter(RadarPost.external_id.in_(ids)).all()
    }

    stored = {}
    new_count = 0
    for raw in raw_posts:
        row = existing.get(raw.external_id)
        if row is None:
            row = RadarPost(source=raw.source, external_id=raw.external_id,
                            channel=raw.channel, created_utc=raw.created_utc,
                            first_seen=now)
            db.session.add(row)
            new_count += 1

        # Engagement grows after first sight, so these always refresh.
        row.score = raw.score
        row.num_comments = raw.num_comments
        row.last_seen = now
        row.url = raw.url

        # Text and author are only overwritten while they still exist
        # upstream; a deletion blanks them, and the mention rows stay.
        row.title = raw.title
        row.body = raw.body
        row.author = raw.author
        row.simhash = fingerprint.simhash64('%s %s' % (raw.title or '', raw.body))

        stored[raw.external_id] = row

    db.session.flush()
    return stored, new_count


def _extract_mentions(raw_posts, stored, lookup):
    """Create mention rows for posts that do not have them yet.

    Extraction runs once per post. Re-running it on every refetch would let a
    stopword or universe change silently rewrite history, and a bucket whose
    counts move under it is worse than one computed from a stale rule.
    """
    post_ids = [row.id for row in stored.values() if row.id is not None]
    already = set()
    if post_ids:
        already = {
            post_id for (post_id,) in
            db.session.query(RadarMention.post_id).filter(
                RadarMention.post_id.in_(post_ids)).distinct().all()
        }

    mention_rows = []
    for raw in raw_posts:
        row = stored.get(raw.external_id)
        if row is None or row.id in already:
            continue

        score = sentiment.lexicon_score('%s %s' % (raw.title or '', raw.body))
        for symbol, confidence in extraction.extract_tickers(
                raw.title, raw.body, lookup):
            db.session.add(RadarMention(post_id=row.id, ticker=symbol,
                                        confidence=confidence,
                                        lexicon_sentiment=score))
            mention_rows.append(buckets.MentionRow(
                ticker=symbol, created_utc=raw.created_utc, source=raw.source,
                author=raw.author, simhash=row.simhash, confidence=confidence,
                sentiment=score,
                engagement=float(raw.score + raw.num_comments)))

    return mention_rows


def _touched_buckets(mention_rows, since, now):
    """Every bucket this cycle covered, including ones with no mentions.

    Derived from the cycle's time span rather than from the rows, so a healthy
    source that simply saw nothing records a genuine zero -- which is a
    different fact from `missing` and must stay distinguishable.
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


def run_cycle(now, fetcher, source='reddit'):
    """Fetch, store, extract and roll up once. Returns a summary dict."""
    since = _since_for(source)
    result = fetcher(since)

    statuses = {'reddit': 'missing', 'stocktwits': 'missing'}
    statuses[source] = result.status

    if result.status == 'missing':
        return {'posts_seen': 0, 'posts_new': 0, 'mentions': 0,
                'buckets_written': 0, 'status': 'missing',
                'catchup_depth': result.catchup_depth}

    lookup = universe.load_lookup()
    stored, new_count = _store_posts(result.posts, now)
    mention_rows = _extract_mentions(result.posts, stored, lookup)
    db.session.commit()

    written = buckets.roll_up(mention_rows, statuses,
                              _touched_buckets(mention_rows, since, now))

    return {'posts_seen': len(result.posts), 'posts_new': new_count,
            'mentions': len(mention_rows), 'buckets_written': written,
            'status': result.status, 'catchup_depth': result.catchup_depth}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd personal_apps && python -m pytest tests/test_radar_ingest.py -v`
Expected: 7 passed

- [ ] **Step 5: Commit**

```bash
git add personal_apps/features/radar/ingest.py personal_apps/tests/test_radar_ingest.py
git commit -m "feat(radar): run one ingest cycle from fetch to bucket"
```

---

## Task 10: Retention

**Files:**
- Create: `personal_apps/features/radar/retention.py`
- Test: `personal_apps/tests/test_radar_retention.py`

**Interfaces:**
- Consumes: `models.RadarPost`, `config.POST_RETENTION_DAYS`
- Produces: `prune_posts(now: datetime, chunk_size: int = 5000) -> int`

- [ ] **Step 1: Write the failing test**

```python
# personal_apps/tests/test_radar_retention.py
"""Raw text ages out at 30 days; buckets are forever.

Chunking is not a nicety. A single unbounded delete of 30 days of Reddit posts
locks the table and writes one enormous transaction, on the same connection the
daemon needs for its next cycle.
"""
import datetime as dt

import pytest

from app import app as flask_app
from extensions import db
from models import RadarBucket, RadarMention, RadarPost
from features.radar import retention

NOW = dt.datetime(2026, 4, 15, 12, 0, 0)


@pytest.fixture()
def aged_posts():
    with flask_app.app_context():
        RadarPost.query.filter(RadarPost.channel == 'testsub').delete(
            synchronize_session=False)
        db.session.commit()

        for index, age_days in enumerate([1, 10, 29, 31, 60]):
            created = NOW - dt.timedelta(days=age_days)
            post = RadarPost(source='reddit', external_id='t3_age%d' % index,
                             channel='testsub', author='u1', created_utc=created,
                             title=None, body='x', score=1, num_comments=0,
                             url='https://example.invalid/', simhash=1,
                             first_seen=created, last_seen=created)
            db.session.add(post)
            db.session.flush()
            db.session.add(RadarMention(post_id=post.id, ticker='ZZR',
                                        confidence='high', lexicon_sentiment=0.0))
        db.session.commit()
        yield
        RadarPost.query.filter(RadarPost.channel == 'testsub').delete(
            synchronize_session=False)
        RadarBucket.query.filter(RadarBucket.ticker.like('ZZ%')).delete(
            synchronize_session=False)
        db.session.commit()


def test_only_posts_past_the_window_are_deleted(aged_posts):
    deleted = retention.prune_posts(NOW)
    assert deleted == 2
    remaining = RadarPost.query.filter_by(channel='testsub').count()
    assert remaining == 3


def test_mentions_go_with_their_posts(aged_posts):
    retention.prune_posts(NOW)
    surviving_ids = {row.id for row in
                     RadarPost.query.filter_by(channel='testsub').all()}
    orphans = RadarMention.query.filter(
        RadarMention.ticker == 'ZZR',
        RadarMention.post_id.notin_(surviving_ids or {0})).count()
    assert orphans == 0


def test_buckets_survive_their_posts(aged_posts):
    """The whole storage design rests on this: buckets are the queryable
    layer and outlive the text they were computed from."""
    old = NOW - dt.timedelta(days=60)
    db.session.add(RadarBucket(
        ticker='ZZR', bucket_start=old, mention_count=3,
        high_confidence_count=3, distinct_authors=3, distinct_text_ratio=1.0,
        engagement_weighted_count=9.0, count_reddit=3, count_stocktwits=0,
        status_reddit='ok', status_stocktwits='missing', sources_ok=1,
        source_config_version='deadbeefdeadbeef'))
    db.session.commit()

    retention.prune_posts(NOW)
    assert RadarBucket.query.filter_by(ticker='ZZR', bucket_start=old).count() == 1


def test_chunking_deletes_everything_across_several_passes(aged_posts):
    deleted = retention.prune_posts(NOW, chunk_size=1)
    assert deleted == 2


def test_pruning_an_empty_window_is_a_no_op(aged_posts):
    retention.prune_posts(NOW)
    assert retention.prune_posts(NOW) == 0
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd personal_apps && python -m pytest tests/test_radar_retention.py -v`
Expected: FAIL with `ImportError: cannot import name 'retention'`

- [ ] **Step 3: Write minimal implementation**

```python
# personal_apps/features/radar/retention.py
"""Rolling deletion of raw text.

Buckets are never touched here. They are the queryable layer and are retained
forever; raw posts exist only long enough to be extracted from and read on a
detail page (spec 5).
"""
import datetime as dt
import time

import sqlalchemy as sa

from extensions import db
from models import RadarPost

from .config import POST_RETENTION_DAYS

# Breathing room between chunks so the daemon's next cycle is not queued behind
# a long delete on the same connection.
_CHUNK_PAUSE_SECONDS = 0.05


def prune_posts(now, chunk_size=5000, pause=_CHUNK_PAUSE_SECONDS):
    """Delete posts older than the retention window, in chunks.

    Mentions follow via ON DELETE CASCADE. Returns the number deleted.
    """
    cutoff = now - dt.timedelta(days=POST_RETENTION_DAYS)
    total = 0

    while True:
        ids = [
            row_id for (row_id,) in
            db.session.query(RadarPost.id)
            .filter(RadarPost.created_utc < cutoff)
            .order_by(RadarPost.created_utc)
            .limit(chunk_size).all()
        ]
        if not ids:
            break

        db.session.query(RadarPost).filter(RadarPost.id.in_(ids)).delete(
            synchronize_session=False)
        db.session.commit()
        total += len(ids)

        if len(ids) < chunk_size:
            break
        if pause:
            time.sleep(pause)

    return total
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd personal_apps && python -m pytest tests/test_radar_retention.py -v`
Expected: 5 passed

- [ ] **Step 5: Commit**

```bash
git add personal_apps/features/radar/retention.py personal_apps/tests/test_radar_retention.py
git commit -m "feat(radar): age out raw posts in chunks, keep every bucket"
```

---

## Task 11: The daemon

**Files:**
- Create: `personal_apps/run_radar_ingest.py`
- Test: `personal_apps/tests/test_radar_daemon.py`

**Interfaces:**
- Consumes: `market_calendar.session_state`, `ingest.run_cycle`, `retention.prune_posts`, `sources.reddit.RedditClient`
- Produces:
  - `interval_for(state: str) -> int` — seconds
  - `build_fetcher(client) -> callable`
  - `tick(now: datetime, fetcher: callable) -> dict`

- [ ] **Step 1: Write the failing test**

```python
# personal_apps/tests/test_radar_daemon.py
"""Cadence follows the NYSE session, not a fixed interval and not German local
time (spec 4.3, 4.4).

The DST case is the one that would otherwise ship broken: for about three weeks
each spring the US session starts an hour earlier in Berlin, and any cadence
keyed on Berlin hours would poll at overnight rates through a live open.
"""
import datetime as dt

import run_radar_ingest as daemon


def _utc(year, month, day, hour, minute=0):
    return dt.datetime(year, month, day, hour, minute, tzinfo=dt.timezone.utc)


def test_premarket_and_regular_poll_fastest():
    assert daemon.interval_for('premarket') == 180
    assert daemon.interval_for('regular') == 180


def test_afterhours_is_slower():
    assert daemon.interval_for('afterhours') == 600


def test_closed_is_slowest():
    assert daemon.interval_for('closed') == 1800


def test_an_unknown_state_falls_back_to_the_slow_interval():
    """A typo or a new state must not accidentally hammer the API."""
    assert daemon.interval_for('nonsense') == 1800


def test_interval_during_a_live_session_is_the_fast_one():
    assert daemon.interval_for(daemon.current_state(_utc(2026, 4, 15, 14))) == 180


def test_interval_during_the_dst_desync_window():
    """2026-03-16 13:45 UTC is 09:45 ET -- open -- but only 14:45 in Berlin,
    an hour earlier than the usual German open."""
    state = daemon.current_state(_utc(2026, 3, 16, 13, 45))
    assert state == 'regular'
    assert daemon.interval_for(state) == 180


def test_tick_returns_the_cycle_summary(monkeypatch):
    monkeypatch.setattr(daemon.ingest, 'run_cycle',
                        lambda now, fetcher: {'status': 'ok', 'mentions': 3,
                                              'buckets_written': 1,
                                              'catchup_depth': 1,
                                              'posts_seen': 3, 'posts_new': 3})
    result = daemon.tick(_utc(2026, 4, 15, 14), fetcher=lambda since: None)
    assert result['mentions'] == 3


def test_a_cycle_that_raises_does_not_kill_the_daemon(monkeypatch):
    """APScheduler drops a job whose function raises. Losing ingest until the
    next restart is worse than losing one cycle."""
    def boom(now, fetcher):
        raise RuntimeError('provider exploded')

    monkeypatch.setattr(daemon.ingest, 'run_cycle', boom)
    result = daemon.tick(_utc(2026, 4, 15, 14), fetcher=lambda since: None)
    assert result['status'] == 'error'
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd personal_apps && python -m pytest tests/test_radar_daemon.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'run_radar_ingest'`

- [ ] **Step 3: Write minimal implementation**

```python
# personal_apps/run_radar_ingest.py
"""Radar ingest daemon.

Mirrors run_gym_notifier.py: an APScheduler process holding a Flask app context,
deployed as its own systemd unit and restarted by the VPS deploy script.

Cadence is chosen per cycle from the NYSE session rather than fixed, because
chatter volume follows the session and polling overnight at session rates is
wasted work. The state comes from the exchange calendar, never from local time
-- see the DST note in features/radar/market_calendar.py.
"""
import datetime as dt
import logging
import os

from apscheduler.schedulers.background import BackgroundScheduler

from app import app
from features.radar import ingest, market_calendar, retention
from features.radar.config import SUBREDDITS
from features.radar.sources import reddit

logger = logging.getLogger('radar.ingest')

INTERVALS = {
    'premarket': 180,
    'regular': 180,
    'afterhours': 600,
    'closed': 1800,
}
# An unrecognized state polls at the slowest rate. Failing towards fewer API
# calls is the safe direction when the alternative is hammering Reddit.
FALLBACK_INTERVAL = 1800


def interval_for(state):
    return INTERVALS.get(state, FALLBACK_INTERVAL)


def current_state(now_utc):
    return market_calendar.session_state(now_utc)


def build_fetcher(client):
    """Bind the Reddit client into the one-argument fetcher ingest expects."""
    def fetcher(since):
        return reddit.fetch(since, client, subreddits=SUBREDDITS)
    return fetcher


def build_client():
    return reddit.RedditClient(
        client_id=os.getenv('REDDIT_CLIENT_ID'),
        client_secret=os.getenv('REDDIT_CLIENT_SECRET'),
        username=os.getenv('REDDIT_USERNAME'),
        password=os.getenv('REDDIT_PASSWORD'),
        user_agent=os.getenv('REDDIT_USER_AGENT', reddit.USER_AGENT_DEFAULT),
    )


def tick(now_utc, fetcher):
    """One cycle, with failures contained.

    APScheduler drops a job whose function raises, so an unhandled error here
    would silently end ingest until the next restart -- losing far more than
    the cycle that failed.
    """
    try:
        summary = ingest.run_cycle(now_utc.replace(tzinfo=None), fetcher)
    except Exception:
        logger.exception('radar ingest cycle failed')
        return {'status': 'error', 'posts_seen': 0, 'posts_new': 0,
                'mentions': 0, 'buckets_written': 0, 'catchup_depth': 0}

    logger.info('radar cycle status=%s posts=%d new=%d mentions=%d '
                'buckets=%d catchup_depth=%d',
                summary['status'], summary['posts_seen'], summary['posts_new'],
                summary['mentions'], summary['buckets_written'],
                summary['catchup_depth'])
    return summary


def _scheduled_cycle(scheduler, fetcher):
    """Run a cycle, then reschedule at the interval the session now calls for."""
    now = dt.datetime.now(dt.timezone.utc)
    with app.app_context():
        tick(now, fetcher)

    state = current_state(now)
    scheduler.reschedule_job('radar_cycle', trigger='interval',
                             seconds=interval_for(state))


def _scheduled_prune():
    with app.app_context():
        deleted = retention.prune_posts(dt.datetime.utcnow())
        if deleted:
            logger.info('radar retention pruned %d posts', deleted)


def main():
    logging.basicConfig(level=logging.INFO)
    fetcher = build_fetcher(build_client())

    scheduler = BackgroundScheduler(timezone='UTC')
    scheduler.add_job(_scheduled_cycle, 'interval', seconds=180,
                      id='radar_cycle', args=[scheduler, fetcher],
                      max_instances=1, coalesce=True)
    scheduler.add_job(_scheduled_prune, 'cron', hour=4, minute=30,
                      id='radar_prune')
    scheduler.start()
    logger.info('radar ingest daemon started')

    try:
        while True:
            import time
            time.sleep(60)
    except (KeyboardInterrupt, SystemExit):
        scheduler.shutdown()


if __name__ == '__main__':
    main()
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd personal_apps && python -m pytest tests/test_radar_daemon.py -v`
Expected: 8 passed

- [ ] **Step 5: Run the whole suite and confirm nothing regressed**

Run: `cd personal_apps && python -m pytest tests/ -q`
Expected: all tests pass, including the pre-existing gym and auth suites

- [ ] **Step 6: Commit**

```bash
git add personal_apps/run_radar_ingest.py personal_apps/tests/test_radar_daemon.py
git commit -m "feat(radar): poll on the session clock and survive a failed cycle"
```

---

## Task 12: Seed the universe and prove ingest end to end

**Files:**
- Create: `personal_apps/scripts/seed_radar_universe.py`
- Modify: `.env` (locally, not committed)
- Test: manual verification, documented below

**Interfaces:**
- Consumes: `universe.upsert_symbols`
- Produces: a populated `radar_ticker_universe`

- [ ] **Step 1: Write the seed script**

```python
# personal_apps/scripts/seed_radar_universe.py
"""Seed radar_ticker_universe from a symbol listing file.

Run against a downloaded listing rather than an API so it works offline and so
re-seeding is deterministic. Expects a CSV with at least `symbol` and `name`
columns; nasdaqtrader.com publishes pipe-delimited files in this shape.

    python scripts/seed_radar_universe.py path/to/symbols.csv

Re-running is safe: upsert_symbols is idempotent and only resets a baseline
when a symbol genuinely changed hands (features/radar/universe.py).
"""
import csv
import datetime as dt
import sys

sys.path.insert(0, '.')

from app import app                       # noqa: E402
from features.radar import universe       # noqa: E402


def load_rows(path):
    with open(path, newline='', encoding='utf-8') as handle:
        sample = handle.read(4096)
        handle.seek(0)
        delimiter = '|' if '|' in sample.splitlines()[0] else ','
        for row in csv.DictReader(handle, delimiter=delimiter):
            symbol = (row.get('symbol') or row.get('Symbol') or '').strip()
            name = (row.get('name') or row.get('Security Name') or '').strip()
            exchange = (row.get('exchange') or row.get('Listing Exchange') or '').strip()
            if not symbol or not symbol.isalpha() or len(symbol) > 5:
                continue
            yield {'symbol': symbol, 'name': name, 'exchange': exchange}


def main():
    if len(sys.argv) != 2:
        print('usage: seed_radar_universe.py <symbols.csv>')
        return 1

    rows = list(load_rows(sys.argv[1]))
    with app.app_context():
        counts = universe.upsert_symbols(rows, dt.datetime.utcnow())
    print('universe: %d added, %d updated, %d reassigned (from %d rows)'
          % (counts['added'], counts['updated'], counts['reassigned'], len(rows)))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
```

- [ ] **Step 2: Add the Reddit credentials to `.env`**

Register a **script** app at https://www.reddit.com/prefs/apps, then add to `personal_apps/.env` (this file is not committed):

```
REDDIT_CLIENT_ID=...
REDDIT_CLIENT_SECRET=...
REDDIT_USERNAME=...
REDDIT_PASSWORD=...
REDDIT_USER_AGENT=personal_apps-radar/0.1 by u/<your-reddit-username>
```

Reddit rejects generic user agents, so the trailing username is not decoration.

- [ ] **Step 3: Seed the universe**

```bash
cd personal_apps && python scripts/seed_radar_universe.py ../symbols.csv
```

Expected: a line reporting several thousand symbols added.

- [ ] **Step 4: Run one real cycle by hand**

```bash
cd personal_apps && python -c "import datetime as dt; from app import app; from features.radar import ingest; import run_radar_ingest as d; f = d.build_fetcher(d.build_client()); ctx = app.app_context(); ctx.push(); print(ingest.run_cycle(dt.datetime.utcnow(), f))"
```

Expected: a summary dict with `status` `ok` or `truncated`, non-zero `posts_seen`, and non-zero `buckets_written`.

If `status` is `missing`, the credentials or user agent are wrong — check for a 401 by running the token request alone. **A `missing` cycle correctly writes nothing**, so an empty `radar_buckets` here is the system working, not a bug to route around.

- [ ] **Step 5: Confirm what landed**

```bash
cd personal_apps && python -c "from app import app; from models import RadarBucket, RadarPost; ctx = app.app_context(); ctx.push(); print('posts', RadarPost.query.count()); print('buckets', RadarBucket.query.count()); [print(b.ticker, b.bucket_start, b.mention_count, b.distinct_authors, round(b.distinct_text_ratio, 2), b.status_reddit) for b in RadarBucket.query.order_by(RadarBucket.mention_count.desc()).limit(15)]"
```

Expected: recognizable tickers at the top. **Read this list critically** — it is the first real test of the extractor, and any obviously wrong symbol (a stopword that slipped through, a common word matching a real ticker) is a `config.STOPWORDS` addition plus a new case in `test_radar_extraction.py`, not something to leave for later. False positives compound: every one becomes a fake spike in Plan 2.

- [ ] **Step 6: Commit**

```bash
git add personal_apps/scripts/seed_radar_universe.py
git commit -m "feat(radar): seed the ticker universe from a symbol listing"
```

---

## Done when

- `cd personal_apps && python -m pytest tests/ -q` passes in full
- `radar_buckets` contains rows from a real Reddit cycle with plausible tickers
- A cycle run with deliberately broken credentials writes **no** buckets and reports `status='missing'`
- The daemon starts, logs a cycle, and reschedules itself

Plan 2 (scoring) reads `radar_buckets` and writes `mention_z_*` and `baseline_days_*`. Nothing in this plan computes a score, and the columns stay NULL until then.
