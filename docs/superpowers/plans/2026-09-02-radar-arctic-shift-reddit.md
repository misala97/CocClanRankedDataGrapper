# Radar Reddit-through-Arctic-Shift Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Read the full comment and post stream of 34 subreddits through Arctic Shift's public API instead of the anonymous Reddit RSS trickle, backfill 30 days so baselines are real from day one, and keep the RSS path in the tree behind a switch.

**Architecture:** A new source module `features/radar/sources/arctic_shift.py` emits `RawPost`s under the existing `reddit:<sub>` names, so nothing downstream changes. Per-sub cursors live in a new small table. The daemon keeps Reddit on its own scheduler job (latency isolation; the daemon tests pin that wiring) and picks the adapter by `config.REDDIT_FETCHER`. A one-off script backfills 30 days through the same intake functions the live cycle uses.

**Tech Stack:** Flask + SQLAlchemy + Alembic (MySQL 8 dev, MariaDB prod), `requests`, pytest against the dev DB with duck-typed fake clients (no `requests` patching).

**Spec:** `docs/superpowers/specs/2026-09-02-radar-arctic-shift-reddit-design.md` — read it first. Where this plan deviates from the spec (listed in Task 6), the plan wins; Task 6 updates the spec.

## Global Constraints

- Paths are relative to `personal_apps/` unless they start with `docs/`. Run `python -m pytest <files> -q -p no:cacheprovider` from `personal_apps/`; run `git` from the repo root. The full pytest suite takes ~20 min — run the files each task names.
- Every stored datetime is naive UTC. Arctic Shift returns epoch seconds; convert with `dt.datetime.fromtimestamp(epoch, dt.timezone.utc).replace(tzinfo=None)`.
- Source names are `reddit:<sub>` verbatim; the 8 existing names keep their exact spelling (`wallstreetbets`, `pennystocks`, `shortsqueeze`, `thetagang`, `options`, `smallstreetbets`, `swingtrading`, `weedstocks`); every new name is lowercase. Arctic Shift's `subreddit` parameter is case-insensitive (probed).
- Authors are stored as `/u/<name>` (the RSS path stored the feed's `/u/` form; author rules and distinct-voice counts must see one spelling across the switch). A `[deleted]` author is `None`.
- Comment titles are `'/u/<author> on <parent title>'`; a parent the archive does not hold gets `'/u/<author> on [thread unavailable]'` (the splitter needs a non-empty context: `clean_text` strips the trailing space and `' on ' in title` would then fail). Titles are clipped to 512 characters (`RadarPost.title` is `String(512)`).
- External ids are the Reddit fullnames the API returns as `name` (`t1_<id>` comments, `t3_<id>` posts); the RSS path stored the same `t1_` ids, so the switch dedupes comments. `url` is `https://www.reddit.com` + `permalink`, never the post's `url` field (an external link).
- `score` is `int(item.get('score') or 0)`; `num_comments` likewise (0 for comments).
- Arctic Shift: base `https://arctic-shift.photon-reddit.com/api`; endpoints `/comments/search`, `/posts/search` (params `subreddit`, `after` epoch seconds, `sort=asc`, `limit` ≤ 1000 or `auto`), `/posts/ids?ids=t3_a,t3_b` (≤100 ids). `after` is EXCLUSIVE at whole-second granularity: request `after = cursor − 1` and let ids dedupe. Responses are `{"data": [...]}`. A `429` ends the cycle's requests; the never-requested subs stay ABSENT from `per_source_status`.
- A subreddit is atomic per cycle: its posts and BOTH cursor advances are published only when both reads (comments, posts) completed as `ok` or `truncated`; if either fails the sub is `missing`, none of its posts are returned and neither cursor moves, so the next cycle asks again from the same place (Codex review, 2026-09-02).
- Per-sub status: `ok` when every page was read, `truncated` when the page cap was hit with a full last page, `missing` on any error. The aggregate reuses `sources.reddit._roll_up` (all missing → `missing`; any missing or truncated → `truncated`; else `ok`), the existing Reddit convention.
- Cursor per `(sub, kind)` = newest `created_utc` accepted; cold start `now − 2 h` (the root cursor's cold start too, so no hole at the switch).
- Config: `REDDIT_FETCHER = 'arctic_shift'` (`'rss'` = old path, unchanged), `ARCTIC_SHIFT_INTERVAL_SECONDS = 300`, `ARCTIC_SHIFT_MAX_PAGES = 3`, `ARCTIC_SHIFT_PAGE_SIZE = 1000`, `ARCTIC_SHIFT_COLD_START = dt.timedelta(hours=2)`. `reddit_subs` leaves the `source_config_version` hash; `reddit_fetcher` enters it.
- Bucket growth: `roll_up` writes one `RadarBucketSource` child per countable source per touched (ticker, window), zeros included, so with 34 subs that table grows ~10× faster than today (~2 M rows/month). Michi accepted this on 2026-09-02 (105 GB free); no retention change in this plan.
- The backfill rolls up one whole day across ALL configured subs with the full status map, so every sub gets its zero child rows exactly as a live cycle writes them; and it runs with `roll_up(..., preserve_parent=True)`, which never rewrites an existing parent `RadarBucket` (the journal keeps 48 h, so a rebuild of an old window would erase Bluesky/4chan totals from the parent). The daemon is STOPPED while the backfill runs: both sides floor to 15-minute buckets, so no time cutoff separates their windows.
- Commit after every task; never stage `.superpowers/`, `.claude/`, `static/radar/dist/`, `scratchpad/`. Work on `dev_personal`; merge at the end (Task 6).

---

### Task 1: Config — the switch, the constants, the list, the version hash

**Files:**
- Modify: `features/radar/config.py` (`REDDIT_SUBS` block ~408; the version payload ~787-792; module docstring lines 4-6 and the comment at ~404 that say the sub list is hashed)
- Test: `tests/test_radar_config.py` (append)

**Interfaces:**
- Produces: `config.REDDIT_FETCHER: str`, `config.ARCTIC_SHIFT_INTERVAL_SECONDS: int`, `config.ARCTIC_SHIFT_MAX_PAGES: int`, `config.ARCTIC_SHIFT_PAGE_SIZE: int`, `config.ARCTIC_SHIFT_COLD_START: dt.timedelta`, `config.REDDIT_SUBS` (34 names). `source_config_version()` changes with `REDDIT_FETCHER`, not with `REDDIT_SUBS`.

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_radar_config.py` (it already imports `config`; check the import name at the top and match it):

```python
def test_the_subreddit_list_no_longer_moves_the_version(monkeypatch):
    """Since the 2026-08-26 split every reddit:<sub> is its own population
    with its own baseline; adding a sub must not restart Bluesky's."""
    before = config.source_config_version()
    monkeypatch.setattr(config, 'REDDIT_SUBS', config.REDDIT_SUBS + ('zz_new_sub',))
    assert config.source_config_version() == before


def test_the_reddit_fetcher_moves_the_version(monkeypatch):
    """RSS saw a few percent of Reddit; Arctic Shift sees all of it. The two
    are different populations and must not share a baseline."""
    before = config.source_config_version()
    monkeypatch.setattr(config, 'REDDIT_FETCHER', 'rss')
    assert config.source_config_version() != before


def test_the_arctic_shift_constants_are_sane():
    assert config.REDDIT_FETCHER in ('arctic_shift', 'rss')
    assert config.ARCTIC_SHIFT_INTERVAL_SECONDS >= 120
    assert 1 <= config.ARCTIC_SHIFT_MAX_PAGES <= 10
    assert config.ARCTIC_SHIFT_PAGE_SIZE <= 1000
    assert len(config.REDDIT_SUBS) == len(set(s.lower() for s in config.REDDIT_SUBS))
    for sub in config.REDDIT_SUBS:
        assert sub == sub.lower(), sub
        assert len('reddit:' + sub) <= 48, sub
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `python -m pytest tests/test_radar_config.py -q -p no:cacheprovider -k "version or arctic"`
Expected: FAIL — `AttributeError: module 'features.radar.config' has no attribute 'REDDIT_FETCHER'` and the subreddit-list test fails because the version still moves.

- [ ] **Step 3: Implement**

In `features/radar/config.py` replace the `REDDIT_SUBS = (...)` tuple (8 names) with:

```python
REDDIT_SUBS = (
    # The eight the RSS path read, spelled exactly as stored.
    'wallstreetbets', 'pennystocks', 'shortsqueeze', 'thetagang',
    'options', 'smallstreetbets', 'swingtrading', 'weedstocks',
    # Measured through Arctic Shift on 2026-09-02 with the real extractor
    # (scripts/measure_arctic_shift_subreddits.py); general trading
    # communities only, single-ticker subs stay out, regional ones except
    # the German WSB stay out (their symbols collide with the US universe).
    'daytrading', 'stocks', 'valueinvesting', 'trading', 'stockmarket',
    'pennystock', 'stocks_picks', 'wallstreetbetshuzzah', 'futurestrading',
    'schwab', 'optionswheel', 'biotech_stocks', 'technicalanalysis',
    'fidelity', 'webull', 'thinkorswim', 'realdaytrading', 'burryology',
    'shroomstocks', 'uraniumsqueeze', 'spacs', 'spacstocks', 'squeezeplays',
    'biotechplays', 'investing', 'mauerstrassenwetten',
)

# ---- which Reddit reader runs ----------------------------------------------
# 'arctic_shift': the open archive's public API, the full comment and post
# stream per subreddit, 5-10 minutes behind, ~120k requests/hour allowed.
# 'rss': the anonymous feed path this replaced on 2026-09-02 -- one feed per
# ~100 s for every subreddit together, a few percent of the stream. Kept in
# the tree in case the archive goes away; flipping back is this one line.
REDDIT_FETCHER = 'arctic_shift'
ARCTIC_SHIFT_INTERVAL_SECONDS = 300        # the archive lags 5-10 min; 5-min reads are enough
ARCTIC_SHIFT_MAX_PAGES = 3                 # per (sub, kind) per cycle; more = truncated
ARCTIC_SHIFT_PAGE_SIZE = 1000              # the API's 'auto' ceiling
ARCTIC_SHIFT_COLD_START = dt.timedelta(hours=2)   # same as the root cursor's
```

Update the comment above it (~line 404) — it says the list is hashed into `source_config_version` and "starts a baseline warm-up"; replace that sentence with: "Not hashed into source_config_version since 2026-09-02: each `reddit:<sub>` is its own population, a new sub warms up alone." Update the module docstring's matching sentence (lines 4-6) the same way. In the version payload replace

```python
        'reddit_subs': sorted(REDDIT_SUBS),
```

with

```python
        # Which Reddit reader produced the population: RSS saw a few percent
        # of the stream, Arctic Shift sees all of it. The subreddit LIST is
        # deliberately not hashed (2026-09-02): every reddit:<sub> is its own
        # population and a new sub warms up alone.
        'reddit_fetcher': REDDIT_FETCHER,
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `python -m pytest tests/test_radar_config.py tests/test_radar_reddit.py -q -p no:cacheprovider`
Expected: all pass (`test_radar_reddit.py` re-derives the longest `reddit:<sub>` name for its width checks — 27 chars, under 48).

- [ ] **Step 5: Commit**

```bash
git add personal_apps/features/radar/config.py personal_apps/tests/test_radar_config.py
git commit -m "feat(radar): the Reddit reader is a config switch; 34 subreddits; the list leaves the version hash

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>"
```

---

### Task 2: The per-sub cursor table

**Files:**
- Modify: `models.py` (append after `RadarWatch`)
- Create: `migrations/versions/c8d2e5f7a1b4_add_radar_reddit_cursors.py`
- Test: `tests/test_radar_reddit_cursors.py`

**Interfaces:**
- Produces: `models.RadarRedditCursor` (`sub`, `kind`, `cursor_utc`, `updated_at`; pk (sub, kind)).

- [ ] **Step 1: Write the failing test**

```python
# tests/test_radar_reddit_cursors.py
"""Where the Arctic Shift reader is, per subreddit and kind."""
import datetime as dt

import pytest

from app import app as flask_app
from extensions import db
from models import RadarRedditCursor


@pytest.fixture()
def clean():
    with flask_app.app_context():
        RadarRedditCursor.query.filter(RadarRedditCursor.sub.like('zzarc%')).delete(
            synchronize_session=False)
        db.session.commit()
        yield
        RadarRedditCursor.query.filter(RadarRedditCursor.sub.like('zzarc%')).delete(
            synchronize_session=False)
        db.session.commit()


def test_one_cursor_per_sub_and_kind(clean):
    now = dt.datetime(2027, 1, 1, 12, 0, 0)
    with flask_app.app_context():
        db.session.add(RadarRedditCursor(sub='zzarc', kind='comments', cursor_utc=now, updated_at=now))
        db.session.add(RadarRedditCursor(sub='zzarc', kind='posts',
                                         cursor_utc=now - dt.timedelta(hours=1), updated_at=now))
        db.session.commit()

        rows = {(r.sub, r.kind): r.cursor_utc for r in
                RadarRedditCursor.query.filter_by(sub='zzarc').all()}

        assert rows == {('zzarc', 'comments'): now,
                        ('zzarc', 'posts'): now - dt.timedelta(hours=1)}
        assert db.session.get(RadarRedditCursor, ('zzarc', 'comments')).cursor_utc == now
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `python -m pytest tests/test_radar_reddit_cursors.py -q -p no:cacheprovider`
Expected: FAIL — `ImportError: cannot import name 'RadarRedditCursor'`.

- [ ] **Step 3: Add the model**

Append to `models.py` after `RadarWatch`:

```python
class RadarRedditCursor(db.Model):
    """Where the Arctic Shift reader is, per subreddit and kind.

    Not radar_source_cursors: that table holds ONE cursor per root source
    and ingest advances it every cycle; a per-sub watermark is a different
    fact (reddit.py explains why one shared watermark starves the quiet
    subs). Advanced only when a sub's read succeeded, and staged in the
    cycle's session so it commits with the posts it covers.
    """
    __tablename__ = 'radar_reddit_cursors'
    __table_args__ = {'mysql_charset': 'utf8mb4'}

    sub        = db.Column(db.String(64, collation='utf8mb4_bin'), primary_key=True)
    kind       = db.Column(db.String(12), primary_key=True)      # 'comments' | 'posts'
    cursor_utc = db.Column(MYSQL_DATETIME(fsp=6), nullable=False)
    updated_at = db.Column(MYSQL_DATETIME(fsp=6), nullable=False)
```

(`MYSQL_DATETIME` is the helper the other radar models use; it is defined near the top of `models.py`.)

- [ ] **Step 4: Write the migration**

```python
# migrations/versions/c8d2e5f7a1b4_add_radar_reddit_cursors.py
"""add radar_reddit_cursors

One watermark per (subreddit, kind) for the Arctic Shift reader. Plain DDL.

Revision ID: c8d2e5f7a1b4
Revises: b7e1c4d9a2f3
Create Date: 2026-09-02
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import mysql


revision = 'c8d2e5f7a1b4'
down_revision = 'b7e1c4d9a2f3'
branch_labels = None
depends_on = None


def upgrade():
    is_sqlite = op.get_bind().dialect.name == 'sqlite'
    stamp = sa.DateTime() if is_sqlite else mysql.DATETIME(fsp=6)
    op.create_table(
        'radar_reddit_cursors',
        sa.Column('sub', sa.String(length=64,
                                   collation=None if is_sqlite else 'utf8mb4_bin'),
                  primary_key=True),
        sa.Column('kind', sa.String(length=12), primary_key=True),
        sa.Column('cursor_utc', stamp, nullable=False),
        sa.Column('updated_at', stamp, nullable=False),
        **({} if is_sqlite else {'mysql_charset': 'utf8mb4'}),
    )


def downgrade():
    op.drop_table('radar_reddit_cursors')
```

Apply locally: `flask db upgrade` from `personal_apps/`. Expected: `Running upgrade b7e1c4d9a2f3 -> c8d2e5f7a1b4, add radar_reddit_cursors`. (If `flask db heads` shows a different single head, set `down_revision` to it and say so.)

- [ ] **Step 5: Run the test to verify it passes**

Run: `python -m pytest tests/test_radar_reddit_cursors.py -q -p no:cacheprovider`
Expected: `1 passed`.

- [ ] **Step 6: Commit**

```bash
git add personal_apps/models.py personal_apps/migrations/versions/c8d2e5f7a1b4_add_radar_reddit_cursors.py personal_apps/tests/test_radar_reddit_cursors.py
git commit -m "feat(radar): radar_reddit_cursors -- one watermark per subreddit and kind

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>"
```

---

### Task 3: The adapter — `sources/arctic_shift.py`

**Files:**
- Create: `features/radar/sources/arctic_shift.py`
- Test: `tests/test_radar_arctic_shift.py`

**Interfaces:**
- Consumes: `sources.RawPost`, `sources.FetchResult`, `sources.reddit._roll_up`, config constants from Task 1.
- Produces:
  - `class ArcticShiftUnavailable(Exception)`, `class ArcticShiftThrottled(ArcticShiftUnavailable)`
  - `class ArcticShiftClient(user_agent=USER_AGENT_DEFAULT, timeout=30)` with `get_json(path, params) -> list` (the `data` list)
  - `fetch(cursors, client, *, subs, now, max_pages=ARCTIC_SHIFT_MAX_PAGES, page_size=ARCTIC_SHIFT_PAGE_SIZE, cold_start=ARCTIC_SHIFT_COLD_START, pause=0.0) -> (FetchResult, dict)` — the dict maps `(sub, kind)` to the newest naive-UTC `created_utc` accepted for that read
  - `page_range(client, sub, kind, since, until, *, page_size=ARCTIC_SHIFT_PAGE_SIZE, pause=0.0) -> list[dict]` — every item with `since <= created_utc < until`, fully paged (the backfill's reader)
  - `to_raw_posts(items, sub, kind, titles) -> list[RawPost]`, `parent_titles(client, link_ids) -> dict`
  - `probe_subs(client, subs) -> list[str]` — subs the archive returned nothing for (the misspelling guard)

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_radar_arctic_shift.py
"""The Arctic Shift reader: mapping, paging, cursors, statuses. Pure -- a
duck-typed fake client, no DB, the way test_radar_reddit.py works."""
import datetime as dt

import pytest

from features.radar.sources import arctic_shift
from features.radar.sources.reddit import _roll_up

NOW = dt.datetime(2027, 1, 4, 12, 45, 0)
EPOCH = dt.datetime(1970, 1, 1)


def epoch(when):
    return int((when - EPOCH).total_seconds())


def comment(ident, when, author='someone', body='ZZA to the moon', link='t3_parent1', score=1):
    return {'id': ident, 'name': f't1_{ident}', 'author': author, 'body': body,
            'created_utc': epoch(when), 'score': score, 'link_id': link,
            'permalink': f'/r/zzarc/comments/parent1/title/{ident}/', 'subreddit': 'zzarc'}


def submission(ident, when, title='ZZA thesis', selftext='long read', score=3, num_comments=2):
    return {'id': ident, 'name': f't3_{ident}', 'author': 'op', 'title': title,
            'selftext': selftext, 'created_utc': epoch(when), 'score': score,
            'num_comments': num_comments, 'permalink': f'/r/zzarc/comments/{ident}/title/',
            'url': 'https://example.invalid/off-site', 'subreddit': 'zzarc'}


class FakeClient:
    """Scripted per (path, subreddit): a list of responses consumed in
    order. An Exception instance is raised instead of returned."""

    def __init__(self, script, parents=None):
        self.script = {key: list(values) for key, values in script.items()}
        self.parents = parents or {}
        self.calls = []

    def get_json(self, path, params):
        self.calls.append((path, dict(params)))
        if path == '/posts/ids':
            ids = params['ids'].split(',')
            return [{'id': i[3:], 'name': i, 'title': self.parents[i]}
                    for i in ids if i in self.parents]
        queue = self.script.get((path, params['subreddit']), [])
        answer = queue.pop(0) if queue else []
        if isinstance(answer, Exception):
            raise answer
        return answer


def minute(n):
    return NOW - dt.timedelta(minutes=n)


# --- mapping -----------------------------------------------------------------

def test_a_comment_maps_to_the_rss_shape():
    posts = arctic_shift.to_raw_posts([comment('c1', minute(3))], 'zzarc', 'comments',
                                      {'t3_parent1': 'Why ZZA ripped'})
    [raw] = posts
    assert raw.source == 'reddit:zzarc' and raw.channel == 'zzarc'
    assert raw.external_id == 't1_c1'
    assert raw.author == '/u/someone'
    assert raw.title == '/u/someone on Why ZZA ripped'
    assert raw.body == 'ZZA to the moon'
    assert raw.score == 1 and raw.num_comments == 0
    assert raw.url == 'https://www.reddit.com/r/zzarc/comments/parent1/title/c1/'
    assert raw.created_utc == minute(3)


def test_a_comment_without_a_known_parent_keeps_a_non_empty_context():
    [raw] = arctic_shift.to_raw_posts([comment('c1', minute(3), link='t3_gone')],
                                      'zzarc', 'comments', {})
    assert raw.title == '/u/someone on [thread unavailable]'


def test_a_deleted_author_and_a_missing_score_are_safe():
    [raw] = arctic_shift.to_raw_posts(
        [{**comment('c1', minute(3)), 'author': '[deleted]', 'score': None}],
        'zzarc', 'comments', {'t3_parent1': 'x'})
    assert raw.author is None
    assert raw.title == '/u/[deleted] on x'
    assert raw.score == 0


def test_a_submission_maps_with_its_own_title_and_permalink():
    [raw] = arctic_shift.to_raw_posts([submission('p1', minute(9))], 'zzarc', 'posts', {})
    assert raw.external_id == 't3_p1'
    assert raw.title == 'ZZA thesis' and raw.body == 'long read'
    assert raw.score == 3 and raw.num_comments == 2
    assert raw.url == 'https://www.reddit.com/r/zzarc/comments/p1/title/'
    assert raw.author == '/u/op'


def test_a_long_synthetic_title_is_clipped_to_the_column():
    [raw] = arctic_shift.to_raw_posts([comment('c1', minute(3))], 'zzarc', 'comments',
                                      {'t3_parent1': 'x' * 600})
    assert len(raw.title) == 512
    assert raw.title.startswith('/u/someone on ')


# --- paging and cursors ------------------------------------------------------

def test_a_cycle_reads_each_sub_from_its_cursor_minus_one_second():
    client = FakeClient({
        ('/comments/search', 'zzarc'): [[comment('c1', minute(4)), comment('c2', minute(2))]],
        ('/posts/search', 'zzarc'): [[submission('p1', minute(5))]],
    }, parents={'t3_parent1': 'Why ZZA ripped'})
    cursors = {('zzarc', 'comments'): minute(30), ('zzarc', 'posts'): minute(40)}

    result, advanced = arctic_shift.fetch(cursors, client, subs=['zzarc'], now=NOW,
                                          page_size=100)

    comments_call = next(p for path, p in client.calls if path == '/comments/search')
    assert comments_call['after'] == epoch(minute(30)) - 1
    assert comments_call['sort'] == 'asc' and comments_call['limit'] == 100
    assert result.status == 'ok'
    assert result.per_source_status == {'reddit:zzarc': 'ok'}
    assert sorted(p.external_id for p in result.posts) == ['t1_c1', 't1_c2', 't3_p1']
    assert advanced == {('zzarc', 'comments'): minute(2), ('zzarc', 'posts'): minute(5)}


def test_a_cold_sub_starts_two_hours_back():
    client = FakeClient({('/comments/search', 'zzarc'): [[]], ('/posts/search', 'zzarc'): [[]]})

    result, advanced = arctic_shift.fetch({}, client, subs=['zzarc'], now=NOW,
                                          cold_start=dt.timedelta(hours=2))

    first = client.calls[0][1]
    assert first['after'] == epoch(NOW - dt.timedelta(hours=2)) - 1
    assert result.status == 'ok' and result.posts == []
    assert advanced == {}                       # nothing accepted, nothing moves


def test_a_full_page_pages_on_and_the_cap_reports_truncated():
    page1 = [comment(f'a{i}', minute(60) + dt.timedelta(seconds=i)) for i in range(3)]
    page2 = [comment(f'b{i}', minute(50) + dt.timedelta(seconds=i)) for i in range(3)]
    page3 = [comment(f'c{i}', minute(40) + dt.timedelta(seconds=i)) for i in range(3)]
    client = FakeClient({('/comments/search', 'zzarc'): [page1, page2, page3],
                         ('/posts/search', 'zzarc'): [[]]},
                        parents={'t3_parent1': 'x'})

    result, advanced = arctic_shift.fetch({('zzarc', 'comments'): minute(70)}, client,
                                          subs=['zzarc'], now=NOW, page_size=3, max_pages=2)

    ids = sorted(p.external_id for p in result.posts)
    assert ids == sorted(f't1_{c["id"]}' for c in page1 + page2)
    assert result.per_source_status == {'reddit:zzarc': 'truncated'}
    assert result.status == 'truncated'
    # Cursor at the newest ACCEPTED comment; the archive is asked again from there.
    assert advanced[('zzarc', 'comments')] == minute(50) + dt.timedelta(seconds=2)
    second_call = [p for path, p in client.calls if path == '/comments/search'][1]
    assert second_call['after'] == page1[-1]['created_utc'] - 1


def test_a_short_last_page_is_complete_and_ok():
    page1 = [comment(f'a{i}', minute(60) + dt.timedelta(seconds=i)) for i in range(3)]
    page2 = [comment('b0', minute(50))]
    client = FakeClient({('/comments/search', 'zzarc'): [page1, page2],
                         ('/posts/search', 'zzarc'): [[]]}, parents={'t3_parent1': 'x'})

    result, _ = arctic_shift.fetch({('zzarc', 'comments'): minute(70)}, client,
                                   subs=['zzarc'], now=NOW, page_size=3, max_pages=2)

    assert result.per_source_status == {'reddit:zzarc': 'ok'}
    assert len(result.posts) == 4


def test_ids_returned_twice_across_the_second_boundary_are_read_once():
    edge = minute(50)
    page1 = [comment('a0', edge - dt.timedelta(seconds=1)), comment('a1', edge)]
    page2 = [comment('a1', edge), comment('a2', edge + dt.timedelta(seconds=1))]  # a1 again
    client = FakeClient({('/comments/search', 'zzarc'): [page1, page2, []],
                         ('/posts/search', 'zzarc'): [[]]}, parents={'t3_parent1': 'x'})

    result, _ = arctic_shift.fetch({('zzarc', 'comments'): minute(70)}, client,
                                   subs=['zzarc'], now=NOW, page_size=2, max_pages=5)

    assert sorted(p.external_id for p in result.posts) == ['t1_a0', 't1_a1', 't1_a2']


# --- statuses ----------------------------------------------------------------

def test_a_failing_sub_is_missing_and_keeps_its_cursor_while_the_others_read():
    client = FakeClient({
        ('/comments/search', 'zzbad'): [arctic_shift.ArcticShiftUnavailable('HTTP 500')],
        ('/posts/search', 'zzbad'): [[]],
        ('/comments/search', 'zzarc'): [[comment('c1', minute(2))]],
        ('/posts/search', 'zzarc'): [[]],
    }, parents={'t3_parent1': 'x'})
    cursors = {('zzbad', 'comments'): minute(30), ('zzarc', 'comments'): minute(30)}

    result, advanced = arctic_shift.fetch(cursors, client, subs=['zzbad', 'zzarc'], now=NOW)

    assert result.per_source_status == {'reddit:zzbad': 'missing', 'reddit:zzarc': 'ok'}
    assert result.status == _roll_up(['missing', 'ok'])       # 'truncated', the Reddit convention
    assert ('zzbad', 'comments') not in advanced
    assert advanced[('zzarc', 'comments')] == minute(2)


def test_a_sub_whose_posts_read_fails_publishes_nothing_and_moves_no_cursor():
    """Comments came back, posts did not: nothing of that sub is returned
    and neither cursor advances, so the comments are read again next cycle
    instead of being stored under a missing source and never counted."""
    client = FakeClient({
        ('/comments/search', 'zzarc'): [[comment('c1', minute(2))]],
        ('/posts/search', 'zzarc'): [arctic_shift.ArcticShiftUnavailable('HTTP 502')],
    }, parents={'t3_parent1': 'x'})

    result, advanced = arctic_shift.fetch({('zzarc', 'comments'): minute(30)}, client,
                                          subs=['zzarc'], now=NOW)

    assert result.per_source_status == {'reddit:zzarc': 'missing'}
    assert result.posts == []
    assert advanced == {}


def test_a_429_ends_the_cycle_and_the_rest_are_not_asked():
    client = FakeClient({
        ('/comments/search', 'zzarc'): [arctic_shift.ArcticShiftThrottled('HTTP 429')],
        ('/comments/search', 'zzbrc'): [[comment('c1', minute(2))]],
        ('/posts/search', 'zzbrc'): [[]],
    })

    result, advanced = arctic_shift.fetch({}, client, subs=['zzarc', 'zzbrc'], now=NOW)

    assert result.per_source_status == {'reddit:zzarc': 'missing'}   # zzbrc absent: never asked
    assert result.status == 'missing'
    assert advanced == {}
    assert all(p['subreddit'] == 'zzarc' for _, p in client.calls if 'subreddit' in p)


# --- parent titles -----------------------------------------------------------

def test_parent_titles_are_fetched_in_batches_and_cached_across_cycles():
    parents = {f't3_p{i}': f'title {i}' for i in range(150)}
    client = FakeClient({}, parents=parents)
    arctic_shift.reset_title_cache()

    first = arctic_shift.parent_titles(client, list(parents))
    calls = [p for path, p in client.calls if path == '/posts/ids']
    assert first == parents
    assert len(calls) == 2 and all(len(c['ids'].split(',')) <= 100 for c in calls)

    again = arctic_shift.parent_titles(client, ['t3_p1', 't3_p2'])
    assert again == {'t3_p1': 'title 1', 't3_p2': 'title 2'}
    assert len([p for path, p in client.calls if path == '/posts/ids']) == 2   # cache hit


# --- the backfill's reader and the probe ---------------------------------------

def test_page_range_reads_a_window_completely_and_stops_at_until():
    day = NOW.replace(hour=0, minute=0, second=0)
    inside = [comment(f'i{i}', day + dt.timedelta(hours=i)) for i in range(3)]
    beyond = [comment('z', day + dt.timedelta(days=1, seconds=5))]
    client = FakeClient({('/comments/search', 'zzarc'): [inside[:2], inside[2:] + beyond, []]})

    items = arctic_shift.page_range(client, 'zzarc', 'comments', day, day + dt.timedelta(days=1),
                                    page_size=2)

    assert [i['id'] for i in items] == ['i0', 'i1', 'i2']


def test_probe_names_the_subs_the_archive_has_nothing_for():
    client = FakeClient({('/posts/search', 'zzarc'): [[submission('p1', minute(5))]],
                         ('/posts/search', 'zzempty'): [[]]})
    assert arctic_shift.probe_subs(client, ['zzarc', 'zzempty']) == ['zzempty']
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `python -m pytest tests/test_radar_arctic_shift.py -q -p no:cacheprovider`
Expected: FAIL — `ImportError: cannot import name 'arctic_shift'`.

- [ ] **Step 3: Write the adapter**

```python
# features/radar/sources/arctic_shift.py
"""Reddit through Arctic Shift, the open archive with a public API.

WHY NOT REDDIT ITSELF. The anonymous feed path (reddit.py) gets one feed per
~100 s for every subreddit together, the 25 newest comments of whichever sub
is due -- a few percent of r/wallstreetbets alone. Reddit's own API needs a
manual approval that takes weeks and may not come. The archive returns the
whole comment and post stream per subreddit, paged by time, 5-10 minutes
behind, ~120k requests an hour allowed. Measured 2026-09-02: ~1,700
comments/hour over the configured subs against ~140 mentions/hour from all
three sources before.

WHAT STAYS THE SAME. Posts come out under the existing `reddit:<sub>` names
with the RSS path's shapes -- `/u/<name>` authors, `t1_`/`t3_` fullnames as
external ids, comment titles `'/u/<author> on <parent title>'` -- so the
forum gate, the finance-native bare tokens, the author rules, the comment
splitting and the phrasing all apply unchanged, and the switch dedupes
against what RSS stored.

CURSORS. One per (sub, kind), the newest created_utc accepted; the archive's
`after` is exclusive at whole-second granularity, so every request asks from
`cursor - 1` and ids dedupe the overlap. One shared watermark would starve
the quiet subs behind the busy one (reddit.py:185-191).
"""
import collections
import datetime as dt
import time

import requests

from . import FetchResult, RawPost
from .reddit import _roll_up
from ..config import (ARCTIC_SHIFT_COLD_START, ARCTIC_SHIFT_MAX_PAGES,
                      ARCTIC_SHIFT_PAGE_SIZE)

API_BASE = 'https://arctic-shift.photon-reddit.com/api'
USER_AGENT_DEFAULT = 'personal_apps-radar/0.1 (personal research)'
REDDIT_BASE = 'https://www.reddit.com'
TITLE_MAX = 512                      # RadarPost.title is String(512)
UNKNOWN_PARENT = '[thread unavailable]'
IDS_PER_CALL = 100
KINDS = ('comments', 'posts')
_EPOCH = dt.datetime(1970, 1, 1)


class ArcticShiftUnavailable(Exception):
    """The archive did not answer usefully for one request."""


class ArcticShiftThrottled(ArcticShiftUnavailable):
    """HTTP 429: the host is throttling us; nothing more this cycle."""


class ArcticShiftClient:
    """Index-free, key-free: GET a search path with query params."""

    def __init__(self, user_agent=USER_AGENT_DEFAULT, timeout=30):
        self._session = requests.Session()
        self._session.headers['User-Agent'] = user_agent
        self._timeout = timeout

    def get_json(self, path, params):
        try:
            response = self._session.get(API_BASE + path, params=params,
                                         timeout=self._timeout)
        except requests.RequestException as exc:
            raise ArcticShiftUnavailable(f'{path}: {exc}') from exc
        if response.status_code == 429:
            raise ArcticShiftThrottled(f'{path}: HTTP 429')
        if not response.ok:
            raise ArcticShiftUnavailable(f'{path}: HTTP {response.status_code}')
        try:
            payload = response.json()
        except ValueError as exc:
            raise ArcticShiftUnavailable(f'{path}: not JSON') from exc
        data = payload.get('data') if isinstance(payload, dict) else None
        return data if isinstance(data, list) else []


# ---- time --------------------------------------------------------------------

def _epoch(when):
    return int((when - _EPOCH).total_seconds())


def _naive_utc(epoch):
    return dt.datetime.fromtimestamp(int(epoch), dt.timezone.utc).replace(tzinfo=None)


# ---- mapping -----------------------------------------------------------------

def _author(item):
    name = item.get('author')
    if not name or name == '[deleted]':
        return None
    return '/u/%s' % name


def _clip(title):
    return title if len(title) <= TITLE_MAX else title[:TITLE_MAX]


def to_raw_posts(items, sub, kind, titles):
    """RawPosts in the RSS path's shapes. `titles` maps t3_ fullnames to
    parent titles (comments need them for their synthetic title)."""
    out = []
    for item in items:
        created = item.get('created_utc')
        if created is None:
            continue
        ident = item.get('id')
        author = _author(item)
        permalink = item.get('permalink') or ''
        if kind == 'comments':
            handle = author or '/u/[deleted]'
            parent = titles.get(item.get('link_id') or '', '') or UNKNOWN_PARENT
            out.append(RawPost(
                source='reddit:%s' % sub,
                external_id=item.get('name') or 't1_%s' % ident,
                channel=sub,
                author=author,
                created_utc=_naive_utc(created),
                title=_clip('%s on %s' % (handle, parent)),
                body=item.get('body') or '',
                score=int(item.get('score') or 0),
                num_comments=0,
                url=REDDIT_BASE + permalink,
            ))
        else:
            out.append(RawPost(
                source='reddit:%s' % sub,
                external_id=item.get('name') or 't3_%s' % ident,
                channel=sub,
                author=author,
                created_utc=_naive_utc(created),
                title=_clip(item.get('title') or '') or None,
                body=item.get('selftext') or '',
                score=int(item.get('score') or 0),
                num_comments=int(item.get('num_comments') or 0),
                url=REDDIT_BASE + permalink,
            ))
    return out


# ---- parent titles -----------------------------------------------------------

# t3 fullname -> title, for the life of the process. Bounded: a day of
# r/wallstreetbets is a few thousand threads; the cache is cleared when it
# passes the cap rather than evicted, which is fine for a lookup this cheap.
_TITLES = {}
_TITLE_CACHE_MAX = 50_000


def reset_title_cache():
    _TITLES.clear()


def parent_titles(client, link_ids):
    """Titles for the given t3_ fullnames, batched, cached. Ids the archive
    does not hold are simply absent from the answer."""
    wanted = [i for i in dict.fromkeys(link_ids) if i and i not in _TITLES]
    for start in range(0, len(wanted), IDS_PER_CALL):
        chunk = wanted[start:start + IDS_PER_CALL]
        for post in client.get_json('/posts/ids', {'ids': ','.join(chunk)}):
            name = post.get('name') or 't3_%s' % post.get('id')
            _TITLES[name] = post.get('title') or ''
    if len(_TITLES) > _TITLE_CACHE_MAX:
        keep = {i: _TITLES[i] for i in link_ids if i in _TITLES}
        _TITLES.clear()
        _TITLES.update(keep)
    return {i: _TITLES[i] for i in link_ids if i in _TITLES}


# ---- paging ------------------------------------------------------------------

def _pages(client, sub, kind, since, *, until=None, max_pages=None,
           page_size=ARCTIC_SHIFT_PAGE_SIZE, pause=0.0):
    """Items with created_utc >= since (and < until when given), ascending,
    deduplicated by fullname across the overlap at each second boundary.
    Returns (items, complete): complete is False when max_pages was hit
    with a full page still coming back."""
    items, seen = [], set()
    after = _epoch(since) - 1
    pages = 0
    while True:
        params = {'subreddit': sub, 'after': after, 'sort': 'asc', 'limit': page_size}
        if until is not None:
            params['before'] = _epoch(until)
        page = client.get_json('/%s/search' % kind, params)
        pages += 1
        fresh = 0
        for item in page:
            created = item.get('created_utc')
            if created is None or created < _epoch(since):
                continue
            if until is not None and created >= _epoch(until):
                continue
            name = item.get('name') or '%s_%s' % ('t1' if kind == 'comments' else 't3',
                                                  item.get('id'))
            if name in seen:
                continue
            seen.add(name)
            items.append(item)
            fresh += 1
        if len(page) < page_size:
            return items, True
        if max_pages is not None and pages >= max_pages:
            return items, False
        newest = max(int(item['created_utc']) for item in page)
        if newest - 1 <= after and fresh == 0:
            # A whole page inside one second and nothing new: the archive
            # cannot be paged past it with a one-second key. Take what we
            # have rather than loop.
            return items, True
        after = newest - 1
        if pause:
            time.sleep(pause)


def page_range(client, sub, kind, since, until, *, page_size=ARCTIC_SHIFT_PAGE_SIZE,
               pause=0.0):
    """Every item in [since, until), fully paged. The backfill's reader."""
    items, _complete = _pages(client, sub, kind, since, until=until,
                              page_size=page_size, pause=pause)
    return items


# ---- the cycle ---------------------------------------------------------------

def fetch(cursors, client, *, subs, now, max_pages=ARCTIC_SHIFT_MAX_PAGES,
          page_size=ARCTIC_SHIFT_PAGE_SIZE, cold_start=ARCTIC_SHIFT_COLD_START,
          pause=0.0):
    """One cycle over `subs`. Returns (FetchResult, advanced) where
    `advanced` maps (sub, kind) to the newest created_utc accepted -- the
    caller persists it.

    A SUBREDDIT IS ATOMIC. Its posts and both cursor advances are published
    only when both reads (comments, posts) completed as ok or truncated. If
    either fails the sub is `missing`, none of its posts are returned and
    neither cursor moves: run_cycle stores what a fetch returns whatever
    the status says, but journals only countable sources -- so comments
    returned under a missing sub would be stored and never counted while
    an advanced cursor made sure they were never read again.

    A 429 ends the cycle: the archive is one host, so asking the next sub
    would only deepen the throttle, and sleeping cannot recover the work
    -- the radar_reddit job simply asks again in ARCTIC_SHIFT_INTERVAL
    seconds. Subs never asked stay ABSENT from per_source_status (no
    observation, no row), the RSS convention.
    """
    raw_by_sub = collections.defaultdict(list)
    statuses = {}
    advanced = {}
    throttled = False
    for sub in subs:
        if throttled:
            break
        source = 'reddit:%s' % sub
        sub_status = 'ok'
        reads = []
        sub_advanced = {}
        for kind in KINDS:
            since = cursors.get((sub, kind)) or (now - cold_start)
            try:
                items, complete = _pages(client, sub, kind, since, max_pages=max_pages,
                                         page_size=page_size, pause=pause)
            except ArcticShiftThrottled:
                sub_status = 'missing'
                throttled = True
                break
            except ArcticShiftUnavailable:
                sub_status = 'missing'
                break
            if not complete:
                sub_status = 'truncated'
            if items:
                sub_advanced[(sub, kind)] = _naive_utc(
                    max(int(item['created_utc']) for item in items))
            reads.append((kind, items))
        statuses[source] = sub_status
        if sub_status != 'missing':
            raw_by_sub[sub] = reads
            advanced.update(sub_advanced)

    link_ids = [item.get('link_id') for sub_reads in raw_by_sub.values()
                for kind, items in sub_reads if kind == 'comments'
                for item in items if item.get('link_id')]
    try:
        titles = parent_titles(client, link_ids) if link_ids else {}
    except ArcticShiftUnavailable:
        titles = {}          # comments keep the unavailable-thread context

    posts = []
    for sub, sub_reads in raw_by_sub.items():
        for kind, items in sub_reads:
            posts.extend(to_raw_posts(items, sub, kind, titles))

    return (FetchResult(posts=posts, status=_roll_up(list(statuses.values())),
                        per_source_status=statuses),
            advanced)


def probe_subs(client, subs):
    """Subs the archive has nothing for -- a misspelled name answers 200
    and an empty list forever, and an all-zero 'ok' history would build a
    baseline out of nothing. Logged at daemon start, never fatal."""
    silent = []
    for sub in subs:
        try:
            page = client.get_json('/posts/search',
                                   {'subreddit': sub, 'limit': 1, 'sort': 'desc'})
        except ArcticShiftUnavailable:
            continue
        if not page:
            silent.append(sub)
    return silent
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `python -m pytest tests/test_radar_arctic_shift.py tests/test_radar_reddit.py -q -p no:cacheprovider`
Expected: all pass. (`test_radar_reddit.py:85-112` requires `reddit.FEED` to be the only http URL in `vars(reddit)` — the new module is separate, so that holds.)

- [ ] **Step 5: Commit**

```bash
git add personal_apps/features/radar/sources/arctic_shift.py personal_apps/tests/test_radar_arctic_shift.py
git commit -m "feat(radar): the Arctic Shift reader -- Reddit's full stream in the RSS path's shapes

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>"
```

---

### Task 4: Daemon wiring — the switch picks the reader, cursors ride the cycle's commit

**Files:**
- Modify: `run_radar_ingest.py` (the config import at ~38-40; `build_fetchers` ~286; `_scheduled_reddit`'s docstring ~985; the `add_job(... id='radar_reddit' ...)` call in `main()` ~1172; a startup probe right after `build_fetchers()` in `main()`)
- Test: `tests/test_radar_daemon.py` (append)

**Interfaces:**
- Consumes: `arctic_shift.fetch/ArcticShiftClient/probe_subs` (Task 3), `RadarRedditCursor` (Task 2), config (Task 1).
- Produces: `run_radar_ingest._arctic_fetcher(client) -> fetch(since)`; `build_fetchers()['reddit']` is the Arctic Shift closure under `REDDIT_FETCHER == 'arctic_shift'`, the RSS closure under `'rss'`; the `radar_reddit` job interval follows the reader.

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_radar_daemon.py` (it imports the daemon as `daemon` and has `_utc(...)`; check the names at the top and match them):

```python
def test_the_switch_picks_the_reddit_reader(monkeypatch):
    monkeypatch.setattr(daemon, 'REDDIT_FETCHER', 'arctic_shift')
    assert daemon.build_fetchers()['reddit'].__qualname__.startswith('_arctic_fetcher')
    monkeypatch.setattr(daemon, 'REDDIT_FETCHER', 'rss')
    assert daemon.build_fetchers()['reddit'].__qualname__.startswith('_reddit_fetcher')
    assert set(daemon.build_fetchers()) == set(daemon.SOURCES)


def test_the_reddit_job_interval_follows_the_reader(monkeypatch):
    monkeypatch.setattr(daemon, 'REDDIT_FETCHER', 'arctic_shift')
    assert daemon._reddit_job_seconds() == daemon.ARCTIC_SHIFT_INTERVAL_SECONDS
    monkeypatch.setattr(daemon, 'REDDIT_FETCHER', 'rss')
    assert daemon._reddit_job_seconds() == daemon.REDDIT_INTERVAL_SECONDS


def test_the_arctic_fetcher_stages_cursors_for_the_cycles_commit(monkeypatch):
    """The closure loads the per-sub cursors, calls the adapter, and stages
    the advanced ones WITHOUT committing -- run_cycle's single commit
    carries them with the posts they cover, so a failed cycle moves
    nothing."""
    import datetime as dt
    from extensions import db
    from features.radar.sources import FetchResult
    from features.radar.sources import arctic_shift
    from models import RadarRedditCursor
    now = dt.datetime(2027, 1, 4, 12, 45, 0)
    seen = {}

    def fake_fetch(cursors, client, *, subs, now, **kwargs):
        seen['cursors'] = dict(cursors)
        seen['subs'] = list(subs)
        return (FetchResult(posts=[], status='ok', per_source_status={'reddit:zzarc': 'ok'}),
                {('zzarc', 'comments'): now - dt.timedelta(minutes=1)})
    monkeypatch.setattr(arctic_shift, 'fetch', fake_fetch)
    monkeypatch.setattr(daemon, 'REDDIT_SUBS', ('zzarc',))
    monkeypatch.setattr(daemon, '_utcnow', lambda: now)
    with daemon.app.app_context():
        RadarRedditCursor.query.filter_by(sub='zzarc').delete()
        db.session.add(RadarRedditCursor(sub='zzarc', kind='posts',
                                         cursor_utc=now - dt.timedelta(hours=3), updated_at=now))
        db.session.commit()
        try:
            fetch = daemon._arctic_fetcher(client=object())
            result = fetch(now - dt.timedelta(hours=2))

            assert result.status == 'ok'
            assert seen['subs'] == ['zzarc']
            assert seen['cursors'] == {('zzarc', 'posts'): now - dt.timedelta(hours=3)}
            staged = db.session.get(RadarRedditCursor, ('zzarc', 'comments'))
            assert staged is not None
            assert staged.cursor_utc == now - dt.timedelta(minutes=1)
            db.session.rollback()                      # nothing was committed
            assert db.session.get(RadarRedditCursor, ('zzarc', 'comments')) is None
        finally:
            RadarRedditCursor.query.filter_by(sub='zzarc').delete()
            db.session.commit()
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `python -m pytest tests/test_radar_daemon.py -q -p no:cacheprovider -k "reddit_reader or job_interval or stages_cursors"`
Expected: FAIL — `AttributeError: module 'run_radar_ingest' has no attribute 'REDDIT_FETCHER'` / `_arctic_fetcher`.

- [ ] **Step 3: Implement**

In `run_radar_ingest.py`:

Extend the config import (the `from features.radar.config import (...)` at ~38-40) with `ARCTIC_SHIFT_INTERVAL_SECONDS, REDDIT_FETCHER,` (keep alphabetical order inside the parentheses), and add `from features.radar.sources import arctic_shift` beside the other source imports, plus `from models import RadarRedditCursor` if `models` is not already imported there (check; otherwise extend the existing import).

Add after `_reddit_fetcher`:

```python
def _arctic_fetcher(client):
    """Reddit through Arctic Shift (features/radar/sources/arctic_shift.py).

    The per-sub cursors are loaded here, handed to the adapter, and the
    advanced ones are STAGED in the session -- not committed. run_cycle's
    single commit carries them with the posts they cover, so a cycle that
    fails after the fetch moves nothing and the next one asks again from
    the same place. `since` from the root cursor is ignored on purpose:
    one shared watermark starves the quiet subs (reddit.py:185-191).
    """
    def fetch(since):
        now = _utcnow()
        cursors = {(row.sub, row.kind): row.cursor_utc
                   for row in RadarRedditCursor.query.all()}
        result, advanced = arctic_shift.fetch(cursors, client, subs=REDDIT_SUBS, now=now)
        for (sub, kind), newest in advanced.items():
            row = db.session.get(RadarRedditCursor, (sub, kind))
            if row is None:
                db.session.add(RadarRedditCursor(sub=sub, kind=kind,
                                                 cursor_utc=newest, updated_at=now))
            elif newest > row.cursor_utc:
                row.cursor_utc = newest
                row.updated_at = now
        return result
    return fetch


def _reddit_job_seconds():
    """The radar_reddit job's interval follows the reader: the archive lags
    minutes, the feed turned over in under two."""
    return (ARCTIC_SHIFT_INTERVAL_SECONDS if REDDIT_FETCHER == 'arctic_shift'
            else REDDIT_INTERVAL_SECONDS)
```

Change `build_fetchers`:

```python
def build_fetchers():
    """One callable per active source, each taking `since`."""
    fc_client = fourchan.FourChanClient()
    if REDDIT_FETCHER == 'arctic_shift':
        reddit_fetch = _arctic_fetcher(arctic_shift.ArcticShiftClient())
    else:
        reddit_fetch = _reddit_fetcher(reddit.RedditClient())
    return {
        'bluesky': lambda since: bluesky.fetch(since, bluesky.live_drain),
        'fourchan': lambda since: fourchan.fetch(
            since, fc_client, pause=fourchan.REQUEST_INTERVAL_SECONDS),
        'reddit': reddit_fetch,
    }
```

In `main()`, the `scheduler.add_job(_scheduled_reddit(fetchers['reddit']), 'interval', seconds=REDDIT_INTERVAL_SECONDS, ...)` call becomes `seconds=_reddit_job_seconds(),` — and keep the literal `REDDIT_INTERVAL_SECONDS` in `main()`'s source by leaving the surrounding comment that names it (test_radar_daemon.py:115-128 asserts the string is present; add a comment line `# RSS: REDDIT_INTERVAL_SECONDS; Arctic Shift: ARCTIC_SHIFT_INTERVAL_SECONDS` directly above the call). Right after `fetchers = build_fetchers()` in `main()` add:

```python
    if REDDIT_FETCHER == 'arctic_shift':
        # A misspelled subreddit answers 200 and an empty list forever; say
        # so once at start rather than build a baseline out of nothing.
        try:
            silent = arctic_shift.probe_subs(arctic_shift.ArcticShiftClient(), REDDIT_SUBS)
        except Exception:      # the probe must never keep the daemon from starting
            silent = []
        if silent:
            logger.warning('radar reddit: the archive has nothing for %s',
                           ', '.join(silent))
```

Add to `_scheduled_reddit`'s docstring, after the first paragraph: "Under REDDIT_FETCHER='arctic_shift' the same job runs the archive reader every ARCTIC_SHIFT_INTERVAL_SECONDS; it stays a job of its own so a slow archive never delays Bluesky and 4chan."

- [ ] **Step 4: Run the tests to verify they pass**

Run: `python -m pytest tests/test_radar_daemon.py tests/test_radar_ingest.py tests/test_radar_reddit.py -q -p no:cacheprovider`
Expected: all pass, including the pre-existing source-text assertions (`id='radar_reddit'`, `REDDIT_INTERVAL_SECONDS`, `if name != 'reddit'` in `main`; `retire_untracked` in `_reddit_fetcher`).

- [ ] **Step 5: Commit**

```bash
git add personal_apps/run_radar_ingest.py personal_apps/tests/test_radar_daemon.py
git commit -m "feat(radar): the daemon reads Reddit through the archive behind the switch

Per-sub cursors are staged into the cycle's commit; the radar_reddit
job keeps its own clock at the archive's cadence; a startup probe names
subreddits the archive has nothing for.

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>"
```

---

### Task 5: The backfill script

**Files:**
- Modify: `features/radar/buckets.py` (`roll_up`, ~135-247: a `preserve_parent` keyword)
- Create: `scripts/backfill_arctic_shift.py`
- Test: `tests/test_radar_arctic_backfill.py`

**Interfaces:**
- Consumes: `arctic_shift.page_range/to_raw_posts/parent_titles/ArcticShiftClient` (Task 3), `ingest._store_mentioning_posts(raw_posts, lookup, now) -> (mention_rows, new_count, intake)`, `buckets.roll_up(rows, statuses, touched)` (commits), `buckets.bucket_start_for`, `universe.load_lookup()`, `config.BUCKET_MINUTES`, `config.POST_RETENTION_DAYS`, `config.REDDIT_SUBS`.
- Produces: `buckets.roll_up(rows, statuses, touched, *, preserve_parent=False)` — with `preserve_parent=True` an existing parent `RadarBucket` is left exactly as it is (children are written as always; a parent that does not exist yet is created from the rows); `backfill.days(start, end) -> list[(day_start, day_end)]`, `backfill.run_day(client, subs, day_start, day_end, lookup, *, apply, pause=0.0) -> dict` (counts for the whole day across `subs`), `backfill.daemon_is_active() -> bool`, `backfill.main(argv)`.

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_radar_arctic_backfill.py
"""The one-off backfill: day chunks, resume, and one real day through the
same intake the live cycle uses."""
import datetime as dt
import json

import pytest

from app import app as flask_app
from extensions import db
from features.radar import buckets
from features.radar.config import source_config_version
from models import RadarBucket, RadarBucketSource, RadarPost
from scripts import backfill_arctic_shift as backfill
from test_radar_arctic_shift import FakeClient, comment, submission   # tests/ is on sys.path

PREFIX = 'zzarcbf'
QUIET = 'zzarcquiet'
DAY = dt.datetime(2027, 1, 4)


@pytest.fixture()
def clean():
    def wipe():
        for name in (PREFIX, QUIET):
            RadarPost.query.filter(RadarPost.source == f'reddit:{name}').delete(
                synchronize_session=False)
            RadarBucketSource.query.filter(RadarBucketSource.source == f'reddit:{name}').delete(
                synchronize_session=False)
        db.session.commit()
    with flask_app.app_context():
        wipe()
        yield
        wipe()


def test_days_are_whole_utc_days_oldest_first():
    chunks = backfill.days(dt.datetime(2027, 1, 1, 15, 0), dt.datetime(2027, 1, 4, 10, 0))
    assert chunks[0] == (dt.datetime(2027, 1, 1), dt.datetime(2027, 1, 2))
    assert chunks[-1] == (dt.datetime(2027, 1, 4), dt.datetime(2027, 1, 4, 10, 0))
    assert len(chunks) == 4


def test_resume_skips_what_was_done(tmp_path):
    path = tmp_path / 'resume.json'
    done = backfill.load_resume(path)
    assert done == set()
    backfill.mark_done(path, '2027-01-01', 'zzarc')
    assert backfill.load_resume(path) == {('2027-01-01', 'zzarc')}


def _lookup():
    from features.radar import universe
    return universe.annotate_distinctive({'ZZTQ': {'name': 'Zztq Corp', 'exchange': 'Q'}})


def _day_client(when):
    return FakeClient({
        ('/comments/search', PREFIX): [[comment('c1', when, body='ZZTQ to the moon'),
                                        comment('c2', when + dt.timedelta(minutes=1),
                                                author='other', body='$ZZTQ again')], []],
        ('/posts/search', PREFIX): [[submission('p1', when, title='ZZTQ thesis')], []],
        ('/comments/search', QUIET): [[], []],
        ('/posts/search', QUIET): [[], []],
    }, parents={'t3_parent1': 'ZZTQ thread'})


def test_a_day_lands_as_posts_and_ok_children_for_every_sub_under_the_current_version(clean):
    """The whole day, all subs at once, one rollup with the full status
    map: the sub that spoke gets its counts, the sub that did not gets an
    explicit zero row -- the same rows a live cycle would have written."""
    when = DAY + dt.timedelta(hours=10, minutes=5)
    with flask_app.app_context():
        counts = backfill.run_day(_day_client(when), [PREFIX, QUIET], DAY,
                                  DAY + dt.timedelta(days=1), _lookup(), apply=True)

        assert counts['fetched'] == 3
        stored = RadarPost.query.filter_by(source=f'reddit:{PREFIX}').all()
        assert {p.external_id for p in stored} >= {'t1_c1', 't1_c2'}
        window = buckets.bucket_start_for(when)
        loud = RadarBucketSource.query.filter_by(
            source=f'reddit:{PREFIX}', ticker='ZZTQ', bucket_start=window).one()
        quiet = RadarBucketSource.query.filter_by(
            source=f'reddit:{QUIET}', ticker='ZZTQ', bucket_start=window).one()
        assert loud.status == 'ok' and loud.mention_count >= 2
        assert quiet.status == 'ok' and quiet.mention_count == 0
        assert loud.source_config_version == source_config_version()
        assert quiet.source_config_version == source_config_version()

        # Idempotent: the same day again stores nothing new.
        again = backfill.run_day(_day_client(when), [PREFIX, QUIET], DAY,
                                 DAY + dt.timedelta(days=1), _lookup(), apply=True)
        assert again['new_posts'] == 0
        assert RadarPost.query.filter_by(source=f'reddit:{PREFIX}').count() == len(stored)


def test_an_existing_parent_bucket_is_left_alone(clean):
    """The journal keeps 48 h. Rebuilding an old window's parent from it
    would erase Bluesky's and 4chan's totals; the backfill writes children
    and leaves an existing parent exactly as it was."""
    when = DAY + dt.timedelta(hours=10, minutes=5)
    window = buckets.bucket_start_for(when)
    with flask_app.app_context():
        RadarBucket.query.filter_by(ticker='ZZTQ', bucket_start=window).delete()
        db.session.add(RadarBucket(ticker='ZZTQ', bucket_start=window, mention_count=7,
                                   high_confidence_count=7, low_count=0, distinct_authors=5,
                                   sources_ok=2))
        db.session.commit()
        try:
            backfill.run_day(_day_client(when), [PREFIX, QUIET], DAY,
                             DAY + dt.timedelta(days=1), _lookup(), apply=True)

            parent = RadarBucket.query.filter_by(ticker='ZZTQ', bucket_start=window).one()
            assert parent.mention_count == 7 and parent.distinct_authors == 5
            assert RadarBucketSource.query.filter_by(
                source=f'reddit:{PREFIX}', ticker='ZZTQ', bucket_start=window).one().mention_count >= 2
        finally:
            RadarBucket.query.filter_by(ticker='ZZTQ', bucket_start=window).delete()
            db.session.commit()


def test_a_parent_that_did_not_exist_is_created_from_the_day(clean):
    when = DAY + dt.timedelta(hours=10, minutes=5)
    window = buckets.bucket_start_for(when)
    with flask_app.app_context():
        RadarBucket.query.filter_by(ticker='ZZTQ', bucket_start=window).delete()
        db.session.commit()
        try:
            backfill.run_day(_day_client(when), [PREFIX, QUIET], DAY,
                             DAY + dt.timedelta(days=1), _lookup(), apply=True)
            parent = RadarBucket.query.filter_by(ticker='ZZTQ', bucket_start=window).one()
            assert parent.mention_count >= 2
        finally:
            RadarBucket.query.filter_by(ticker='ZZTQ', bucket_start=window).delete()
            db.session.commit()


def test_a_dry_run_counts_and_stores_nothing(clean):
    when = DAY + dt.timedelta(hours=10)
    with flask_app.app_context():
        counts = backfill.run_day(_day_client(when), [PREFIX, QUIET], DAY,
                                  DAY + dt.timedelta(days=1), _lookup(), apply=False)
        assert counts['fetched'] == 3
        assert RadarPost.query.filter_by(source=f'reddit:{PREFIX}').count() == 0


def test_apply_refuses_while_the_daemon_runs(monkeypatch, capsys):
    monkeypatch.setattr(backfill, 'daemon_is_active', lambda: True)
    assert backfill.main(['--apply', '--days', '1', '--subs', PREFIX]) == 2
    assert 'radar_ingest is running' in capsys.readouterr().err


- [ ] **Step 2: Run the tests to verify they fail**

Run: `python -m pytest tests/test_radar_arctic_backfill.py -q -p no:cacheprovider`
Expected: FAIL — `ModuleNotFoundError: No module named 'scripts.backfill_arctic_shift'`.

- [ ] **Step 3: Teach `roll_up` to leave an existing parent alone**

In `features/radar/buckets.py`, change the signature to `def roll_up(rows, statuses, touched, *, preserve_parent=False):` and add to its docstring:

```
    `preserve_parent=True` is the backfill's mode: a parent RadarBucket
    that already exists is left exactly as it is. The parent is rebuilt
    from the journal, and the journal keeps 48 h -- rebuilding an old
    window would erase every other source's totals from it. A parent that
    does not exist yet is created from these rows, which is the truth for
    a window nothing else observed.
```

Then replace the parent-writing block

```python
        bucket = RadarBucket.query.filter_by(
            ticker=ticker, bucket_start=start).one_or_none()
        if bucket is None:
            bucket = RadarBucket(ticker=ticker, bucket_start=start)
            db.session.add(bucket)
        for field, value in totals.items():
            setattr(bucket, field, value)
        bucket.sources_ok = sources_ok
        bucket.source_config_version = version
```

with

```python
        bucket = RadarBucket.query.filter_by(
            ticker=ticker, bucket_start=start).one_or_none()
        if bucket is None:
            bucket = RadarBucket(ticker=ticker, bucket_start=start)
            db.session.add(bucket)
            existed = False
        else:
            existed = True
        if not (preserve_parent and existed):
            for field, value in totals.items():
                setattr(bucket, field, value)
            bucket.sources_ok = sources_ok
            bucket.source_config_version = version
```

Nothing else in `roll_up` changes; the children are written exactly as before.

- [ ] **Step 4: Write the script**

```python
# scripts/backfill_arctic_shift.py
"""Backfill Reddit through Arctic Shift, day by day, through the live intake.

Why: the archive holds history and the baselines need 30 days of it, or
every Reddit-heavy ticker spikes for weeks after the switch. Each day of
each subreddit goes through the SAME functions the live cycle uses --
extraction, the journal, the bucket rollup -- so a backfilled bucket is
indistinguishable from a lived one, stamped with the current
source_config_version.

Run on the VPS after the deploy WITH THE DAEMON STOPPED: both sides
floor timestamps to 15-minute buckets, so no time cutoff keeps their
windows apart and two roll_ups on one window would race. The script
refuses --apply while radar_ingest is active.

    cd /root/coc-stats/personal_apps
    systemctl stop radar_ingest
    PYTHONPATH=. /root/coc-stats/venv/bin/python -m scripts.backfill_arctic_shift --apply
    systemctl start radar_ingest

Options: --days N (default POST_RETENTION_DAYS), --subs a,b (default
REDDIT_SUBS), --resume PATH (default scratchpad/arctic_backfill_resume.json),
--pause SECONDS between requests (default 0.2). Without --apply it fetches
and counts, storing nothing. Interrupted? Run it again: the resume file
skips finished days and the unique keys make a repeated day harmless.

One DAY is the unit, across every configured sub at once: the day's
posts are stored sub by sub, then ONE roll_up over the day's mention rows
with the full status map, so every sub gets its zero child rows exactly
as a live cycle writes them, and preserve_parent=True leaves the parent
buckets other sources built alone (the journal only holds 48 h).

Cost: the judge reads only mentions inside its 24 h window, so the last
day's reachable tickers are judged exactly as the live cycle would have
judged them; older days cost no model spend. The nightly prune removes
the journal rows of days older than 48 h the next morning; the buckets
they built stay.
"""
import argparse
import datetime as dt
import json
import os
import subprocess
import sys
import time

sys.path.insert(0, '.')  # noqa: E402

from app import app  # noqa: E402
from extensions import db  # noqa: E402
from features.radar import buckets, ingest, universe  # noqa: E402
from features.radar.config import BUCKET_MINUTES, POST_RETENTION_DAYS, REDDIT_SUBS  # noqa: E402
from features.radar.sources import arctic_shift  # noqa: E402

DEFAULT_RESUME = os.path.join('scratchpad', 'arctic_backfill_resume.json')


def daemon_is_active():
    """True when systemd says radar_ingest is running; False where there is
    no systemd (a dev machine) so the guard never blocks local runs."""
    try:
        done = subprocess.run(['systemctl', 'is-active', '--quiet', 'radar_ingest'],
                              check=False, timeout=10)
    except (OSError, subprocess.SubprocessError):
        return False
    return done.returncode == 0


def days(start, end):
    """Whole UTC days from `start`'s day to `end`, oldest first; the last
    chunk ends at `end` itself."""
    out = []
    day = start.replace(hour=0, minute=0, second=0, microsecond=0)
    while day < end:
        nxt = day + dt.timedelta(days=1)
        out.append((day, min(nxt, end)))
        day = nxt
    return out


def load_resume(path):
    if not os.path.exists(path):
        return set()
    with open(path, encoding='utf-8') as handle:
        return {tuple(item) for item in json.load(handle)}


def mark_done(path, day_key, sub):
    done = load_resume(path)
    done.add((day_key, sub))          # sub is '*' for a whole day
    os.makedirs(os.path.dirname(path) or '.', exist_ok=True)
    with open(path, 'w', encoding='utf-8') as handle:
        json.dump(sorted(done), handle)


def _windows(day_start, day_end):
    step = dt.timedelta(minutes=BUCKET_MINUTES)
    start = buckets.bucket_start_for(day_start)
    out = set()
    while start < day_end:
        out.add(start)
        start += step
    return out


def run_day(client, subs, day_start, day_end, lookup, *, apply, pause=0.0):
    """One day across `subs` through the live intake. Returns counts."""
    counts = {'day': day_start.date().isoformat(), 'fetched': 0, 'new_posts': 0,
              'mentions': 0, 'buckets': 0}
    day_rows = []
    for sub in subs:
        raw = []
        for kind in arctic_shift.KINDS:
            items = arctic_shift.page_range(client, sub, kind, day_start, day_end, pause=pause)
            titles = {}
            if kind == 'comments':
                link_ids = [i.get('link_id') for i in items if i.get('link_id')]
                try:
                    titles = arctic_shift.parent_titles(client, link_ids) if link_ids else {}
                except arctic_shift.ArcticShiftUnavailable:
                    titles = {}
            raw.extend(arctic_shift.to_raw_posts(items, sub, kind, titles))
        counts['fetched'] += len(raw)
        if not apply or not raw:
            continue
        mention_rows, new_count, _intake = ingest._store_mentioning_posts(raw, lookup, day_end)
        db.session.commit()
        counts['new_posts'] += new_count
        day_rows.extend(mention_rows)
    if not apply:
        return counts
    counts['mentions'] = len(day_rows)
    # ONE rollup for the day with EVERY sub countable: the quiet subs get
    # their explicit zero rows, as a live cycle would write them. Parents
    # other sources built for these windows are left as they are.
    counts['buckets'] = buckets.roll_up(
        day_rows, {'reddit:%s' % sub: 'ok' for sub in subs},
        _windows(day_start, day_end), preserve_parent=True)
    return counts


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.split('\n')[0])
    parser.add_argument('--apply', action='store_true', help='store; default is a dry run')
    parser.add_argument('--days', type=int, default=POST_RETENTION_DAYS)
    parser.add_argument('--subs', default=','.join(REDDIT_SUBS))
    parser.add_argument('--resume', default=DEFAULT_RESUME)
    parser.add_argument('--pause', type=float, default=0.2)
    args = parser.parse_args(argv)
    if args.apply and daemon_is_active():
        print('radar_ingest is running: stop it first (systemctl stop radar_ingest); '
              'two rollups on one window would race', file=sys.stderr)
        return 2
    subs = [s for s in args.subs.split(',') if s]
    now = dt.datetime.utcnow().replace(microsecond=0)
    start = now - dt.timedelta(days=args.days)
    client = arctic_shift.ArcticShiftClient()
    done = load_resume(args.resume) if args.apply else set()
    with app.app_context():
        lookup = universe.load_lookup()
        for day_start, day_end in days(start, now):
            key = day_start.date().isoformat()
            if (key, '*') in done:
                continue
            started = time.perf_counter()
            counts = run_day(client, subs, day_start, day_end, lookup,
                             apply=args.apply, pause=args.pause)
            print('%s  fetched %7d  new posts %6d  mentions %6d  buckets %5d  %.0fs'
                  % (key, counts['fetched'], counts['new_posts'], counts['mentions'],
                     counts['buckets'], time.perf_counter() - started), flush=True)
            if args.apply:
                mark_done(args.resume, key, '*')
    return 0


if __name__ == '__main__':
    sys.exit(main())
```

- [ ] **Step 5: Run the tests to verify they pass**

Run: `python -m pytest tests/test_radar_arctic_backfill.py tests/test_radar_ingest.py tests/test_radar_buckets.py -q -p no:cacheprovider`
Expected: all pass. If `ingest._store_mentioning_posts` needs the lookup shape `load_lookup()` produces beyond what the test builds, seed a `TickerUniverse` row for `ZZTQ` in the fixture and use `universe.load_lookup()` — note the change in the report.

- [ ] **Step 6: Commit**

```bash
git add personal_apps/features/radar/buckets.py personal_apps/scripts/backfill_arctic_shift.py personal_apps/tests/test_radar_arctic_backfill.py
git commit -m "feat(radar): backfill Reddit history through Arctic Shift, day by day, via the live intake

One rollup per day with every sub countable; roll_up gains preserve_parent
so a window other sources built keeps its parent (the journal holds 48 h)

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>"
```

---

### Task 6: Spec deviations, full gate, merge, operator sequence

**Files:**
- Modify: `docs/superpowers/specs/2026-09-02-radar-arctic-shift-reddit-design.md` (a "Built as" section + status line)

- [ ] **Step 1: Record the deviations in the spec**

Append to the spec, before "## Appendix":

```markdown
## Built as (2026-09-02, deviations from the text above)

- **Reddit keeps its own scheduler job** (`radar_reddit`, every
  `ARCTIC_SHIFT_INTERVAL_SECONDS` = 300 s) rather than joining the main
  cycle: a slow archive must never delay Bluesky and 4chan, and the daemon
  tests pin that wiring. Its cycle still goes through `run_cycle`.
- **Cursor table is `radar_reddit_cursors`** (`sub`, `kind`, `cursor_utc`,
  `updated_at`); `radar_source_cursors` already existed with one root
  cursor per source. Cursor = newest accepted `created_utc`; requests use
  `after = cursor − 1` (the API is exclusive at the second) and ids dedupe.
  Cold start 2 h, the root cursor's own.
- **Authors are stored as `/u/<name>`**, the RSS path's spelling, so voice
  counts and author rules see one person across the switch.
- **A comment whose thread the archive lacks** is titled
  `'/u/<author> on [thread unavailable]'`: the splitter needs a non-empty
  context (`clean_text` strips the trailing space).
- **A subreddit is atomic per cycle**: posts and both cursor advances
  are published only when both reads completed; a failed read leaves the
  sub `missing` with nothing returned and nothing moved (a comments read
  that succeeded would otherwise be stored under a missing source, never
  counted, and never read again).
- **Aggregate status reuses `reddit._roll_up`**: one sub missing among
  ok subs is `truncated`, all missing is `missing`. A `429` ends the
  cycle's requests with no sleep: the job asks again in five minutes, so
  sleeping could not recover work and would only hold the scheduler
  worker. Subs never asked are absent from the per-source map.
- **The backfill runs with the daemon STOPPED** (the script refuses
  `--apply` otherwise): both sides floor to 15-minute buckets, so no time
  cutoff keeps their windows apart. One day across all subs is the unit,
  rolled up once with every sub countable so the quiet subs get their
  zero rows; `roll_up(preserve_parent=True)` leaves existing parent
  buckets alone because the journal only holds 48 h and a rebuild would
  erase the other sources' totals.
- **The log line** for a cycle shows the concrete map under `sources=`
  (34 `reddit:<sub>` keys) and the root verdict under `aggregate=`.
- **Bucket growth** accepted: ~34 child rows per touched (ticker, window).
```

Change the status line to `**Status:** built 2026-09-02 (plan docs/superpowers/plans/2026-09-02-radar-arctic-shift-reddit.md)`.

- [ ] **Step 2: Full gate**

From `personal_apps/`:

```bash
python -m pytest tests/test_radar_config.py tests/test_radar_reddit.py tests/test_radar_reddit_cursors.py tests/test_radar_arctic_shift.py tests/test_radar_daemon.py tests/test_radar_ingest.py tests/test_radar_arctic_backfill.py tests/test_radar_buckets.py tests/test_radar_scoring.py tests/test_radar_api.py -q -p no:cacheprovider && npx vitest run -c vite.radar.config.ts && npx tsc --noEmit
```

Expected: every suite green (the island is untouched; vitest confirms nothing regressed through the payload).

- [ ] **Step 3: A live dry run against the archive**

From `personal_apps/`: `PYTHONPATH=. python -m scripts.backfill_arctic_shift --days 1 --subs stocks,pennystocks` (dry run, no `--apply`). Expected: two lines per day with `fetched` in the hundreds for r/stocks, tens for r/pennystocks, `new posts 0` (dry run), no traceback. Then one live adapter cycle against the dev DB:

```bash
python -c "
import datetime as dt
from app import app
from extensions import db
from features.radar.sources import arctic_shift
with app.app_context():
    result, advanced = arctic_shift.fetch({}, arctic_shift.ArcticShiftClient(), subs=('stocks', 'pennystocks'), now=dt.datetime.utcnow(), cold_start=dt.timedelta(minutes=30))
    print(result.status, result.per_source_status, len(result.posts), 'posts;', advanced)
"
```

Expected: `ok {'reddit:stocks': 'ok', 'reddit:pennystocks': 'ok'} <tens> posts; {...cursors...}`.

- [ ] **Step 4: Commit and merge**

```bash
git add docs/superpowers/specs/2026-09-02-radar-arctic-shift-reddit-design.md
git commit -m "docs(radar): Arctic Shift spec marked built, with the deviations

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>"
git checkout main && git merge dev_personal && git push origin main && git push origin dev_personal && git checkout dev_personal
```

- [ ] **Step 5: Operator sequence (Michi, on the VPS)**

1. Routine deploy (`update_coc.sh` runs the migration and restarts `radar_ingest`; the first `radar_reddit` cycle reads the last two hours of all 34 subs).
2. Check the first cycles: `journalctl -u radar_ingest.service --since '15 minutes ago' --no-pager | grep -E 'radar reddit|aggregate='` — expect `aggregate=...reddit=ok` and, if any, a `the archive has nothing for` warning naming misspelled subs.
3. Backfill, once, with the daemon stopped (Bluesky and 4chan pause for the duration; their cursors resume):
   ```bash
   systemctl stop radar_ingest
   cd /root/coc-stats/personal_apps && PYTHONPATH=. nohup /root/coc-stats/venv/bin/python -m scripts.backfill_arctic_shift --apply > /tmp/arctic_backfill.log 2>&1 &
   tail -f /tmp/arctic_backfill.log
   ```
   Expect 30 lines, one per day, ~40–60k fetched each, a few minutes each. Interrupted: run the same command again, finished days are skipped. When it ends: `systemctl start radar_ingest`.
4. Next morning: the board's Reddit venues show 30-day baselines (no `baselines starting over` for tickers Reddit has talked about all month); `radar_bucket_sources` has grown by a few hundred thousand rows.
