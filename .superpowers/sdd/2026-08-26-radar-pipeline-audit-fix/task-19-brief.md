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
            source='bluesky', external_id=ident, ticker='ZZA', channel='c',
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
- `test_the_superseded_page_cap_is_gone` (Task 5)
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
