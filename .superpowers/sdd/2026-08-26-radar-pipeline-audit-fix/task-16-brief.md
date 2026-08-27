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

