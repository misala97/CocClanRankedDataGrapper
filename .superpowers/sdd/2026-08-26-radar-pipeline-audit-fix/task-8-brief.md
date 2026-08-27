## Task 8: Score `truncated` buckets

**Files:**
- Modify: `personal_apps/features/radar/scoring.py:88-104`
- Modify: `personal_apps/tests/test_radar_scoring.py`

**Interfaces:**
- Consumes: Task 3 (without it, a stale z is indistinguishable from a newly-legitimate one) and Task 9 (the status must belong to one subreddit, not aggregate Reddit).
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

## Controller hardening — binding test correction

The draft's second test asserts only the value of `SCOREABLE_STATUSES`. That
does not pin the consumer: a future write loop could ignore the constant and
score every current-generation row while the test stays green.

Replace or supplement it with a behavioral regression that creates enough
current-generation `ok` history for a baseline plus a directly-owned
current-generation `missing` `RadarBucketSource` row, calls `score_source`, and
proves all four score fields remain NULL. The fixture must use an exact owned
`ZZ%` ticker and exact cleanup in the shared real MySQL database.

Teeth is mandatory for both status branches:

- Restore the pre-task `row.status != 'ok'` guard and observe the truncated
  regression fail because its score remains NULL.
- Remove/bypass the `row.status not in SCOREABLE_STATUSES` guard and observe
  the missing-row regression fail because it gains a score.

Also pin that `baselines.usable` and `profile.build_profile` still admit only
`ok`; scoring truncated observations must not let known undercounts describe
normal. Record both RED failures, both mutation failures, and the focused
covering output in `task-8-report.md`.
