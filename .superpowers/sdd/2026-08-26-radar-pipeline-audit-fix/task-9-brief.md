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
- Consumes: Task 7 (`SOURCES` no longer holds StockTwits). Produces the source/status population Task 8 scores.
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

## Controller hardening — binding corrections before implementation

The extracted plan text above has five load-bearing omissions. These
corrections are requirements, not optional scope.

1. **Chain from the current Alembic head.** The live worktree and local DB are
   at `1d26ac48e744` (Task 3b), which revises Task 1's `c489b7c94875`.
   Generating from or explicitly chaining to Task 1 would fork history. The new
   migration's `down_revision` must be `1d26ac48e744`; verify `flask db heads`
   remains a single head.

2. **Widen every newly-prefixed durable writer.** `RadarPost.source` is still
   `String(16)`, so `reddit:wallstreetbets` cannot be inserted. Widen
   `radar_posts.source` to `String(48)` in the model and the same migration, in
   addition to the two columns named above. `radar_mention_events.source` is
   already 48. `RadarSourceCursor` and Reddit's `RadarPollState` key remain the
   root `reddit` by design; do not re-key either learned cursor/schedule.
   The downgrade must normalize prefixed `radar_posts.source` values back to
   `reddit` before narrowing to 16, and the report must state the semantic
   rollback limit for per-subreddit bucket history rather than claiming full
   rollback compatibility that the split cannot provide.

3. **Never write an aggregate zero child named `reddit`.** The draft first
   assigns `statuses['reddit'] = result.status` and then adds concrete statuses.
   `buckets.roll_up` treats every non-missing status key as countable, so that
   would write a root `reddit` child with zero mentions beside the real
   `reddit:<sub>` child. When `per_source_status` is non-empty, the rollup
   status map must contain only concrete names. Keep aggregate fetch status
   separate if logging needs it. A multi-sub fetch with one successful sub and
   a later missing/throttled sub must still ingest and roll up the successful
   sub; aggregate `result.status == 'missing'` must not discard its posts.

4. **Score concrete names.** `run_radar_ingest.score_all` currently iterates
   root `SOURCES`; after this task, `score_source('reddit', ...)` matches no new
   rows. Introduce one shared expansion helper (or an equivalently single
   source of truth) used by both API query expansion and daemon scoring, so the
   root chip remains `reddit` while scoring walks every configured
   `reddit:<sub>`. Keep fetcher keys and source cursors rooted.

5. **Make the required config-version bump real.** Task 7 left `SOURCES` at
   the same three roots and Task 9 does not change `REDDIT_SUBS`, so the current
   hash would not move merely because stored names become prefixed. Add an
   explicit, documented source-population/name generation input to
   `source_config_version()` and pin that changing it changes the stamp. Do not
   overload the journal's `ROLLUP_GENERATION = 2` without correcting its
   generation-specific documentation.

### Required behavioral tests and teeth

Add focused regressions beyond the single config lookup test in the draft:

- Two subreddit results in one cycle, one `ok` and one `truncated`, write only
  their own concrete child rows with their own statuses; no root `reddit`
  child exists. Repeat with one successful sub plus one missing/throttled sub
  and prove the successful posts survive.
- A stored Reddit post with the longest configured prefixed name can be
  inserted after migration; model and live DB widths are 48 for all three
  widened columns.
- Root API selection expands to concrete configured names for board and detail
  queries but serializes the viewer's root selection; a concrete prefixed link
  is accepted, and an unknown root is rejected.
- Daemon scoring calls concrete Reddit names and never the root name.
- The source-name generation changes `source_config_version()`.
- Poll state and cursor remain keyed to root `reddit` across the change.

Every absence-shaped assertion (`no root row`, successful sub not discarded,
old root not scored) must be observed failing under its targeted mutation and
then restored. Tests share the real local MySQL DB: use exact owned `ZZ%`
fixtures and exact cleanup, never broad prefix deletion.
