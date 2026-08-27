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

