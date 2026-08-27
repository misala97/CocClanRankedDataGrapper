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

## Controller hardening — binding extraction correction

The draft's proposed
`extracted.setdefault(raw.external_id, _extract_for(raw, lookup))` does **not**
guarantee once-per-post extraction: Python evaluates the default argument
before calling `setdefault`, so every duplicate external ID still calls
`_extract_for` even when the key already exists.

Use an explicit membership branch instead:

```python
if raw.external_id not in extracted:
    extracted[raw.external_id] = _extract_for(raw, lookup)
tickers = extracted[raw.external_id]
```

Compute the fresh external-ID set once before the second loop rather than
rebuilding a set comprehension on every iteration.

Add a behavioral regression with the same external ID appearing twice in one
batch. Instrument only the extraction boundary and assert it is called once
for that identity while both normal storage/rollup behavior and engagement
refresh remain correct. Teeth: restore the draft's eager `setdefault` form,
observe the call-count regression fail, then restore the explicit branch.
