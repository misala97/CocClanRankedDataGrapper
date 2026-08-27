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
    """Replace the promotion verdict for every recomputed bare mention.

    Promotion is not monotonic: one voucher may carry four bare mentions,
    then a fifth makes the entire group incredible and revokes all four.
    Reset every low/medium row in the recomputed windows before marking the
    current mediums true.
    """
    decisions = [(row.source, row.external_id, row.ticker,
                  row.confidence == 'medium')
                 for row in rows if row.confidence in ('low', 'medium')]
    if not decisions:
        return
    for start in range(0, len(decisions), _CHUNK):
        chunk = decisions[start:start + _CHUNK]
        clauses = [sa.and_(RadarMentionEvent.source == source,
                           RadarMentionEvent.external_id == external_id,
                           RadarMentionEvent.ticker == ticker)
                   for source, external_id, ticker, _ in chunk]
        (RadarMentionEvent.query.filter(sa.or_(*clauses))
         .update({'promoted': False}, synchronize_session=False))

        promoted = [(source, external_id, ticker)
                    for source, external_id, ticker, value in chunk if value]
        if promoted:
            promoted_clauses = [sa.and_(
                RadarMentionEvent.source == source,
                RadarMentionEvent.external_id == external_id,
                RadarMentionEvent.ticker == ticker)
                for source, external_id, ticker in promoted]
            (RadarMentionEvent.query.filter(sa.or_(*promoted_clauses))
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
              'channel': RadarMentionEvent.channel}[field]
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

Add a regression that first rolls up one high voucher plus exactly
`MAX_BARE_PER_VOUCHER` bare mentions and observes their `promoted=True` flags,
then adds one more bare event in the same bucket and recomputes. All prior bare
events must become `promoted=False`, `distinct_voices` must count only the high
voucher, and the bucket's scored `mention_count` must fall back to one. This
test must fail against the one-way `False -> True` implementation.

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

