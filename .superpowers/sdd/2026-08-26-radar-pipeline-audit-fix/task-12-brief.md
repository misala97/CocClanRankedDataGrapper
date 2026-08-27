## Task 12: Interior gaps in the intraday chatter chart

**Files:**
- Modify: `personal_apps/features/radar/detail.py:168-231`
- Modify: `personal_apps/tests/test_radar_detail.py`

**Interfaces:**
- Consumes: nothing.
- Produces: `detail.watched_slots(sources, start, now, step_minutes, slots)` -> `set[int]`, replacing `_watched_from_index`. `intraday_chart_for` uses it.

`_watched_from_index` is `MIN(bucket_start)` over the window, so only the *leading* gap becomes null. A mid-window outage draws zeros. `board._covered_hours` does this correctly, per hour, over the same data — two honesty standards for one fact.

- [ ] **Step 1: Write the failing test**

Append to `personal_apps/tests/test_radar_detail.py`:

```python
def test_an_outage_in_the_middle_of_the_window_is_not_drawn_as_quiet(clean_buckets):
    """board._covered_hours has always got this right, per hour. The detail
    chart only nulled the LEADING gap, so a daemon that stopped for an hour and
    resumed drew a stretch of zero chatter that nobody measured.
    """
    import datetime as dt

    from features.radar import buckets, detail

    now = dt.datetime(2026, 4, 15, 16, 0, 0)
    # Two buckets an hour apart, nothing in between.
    for minute, hour in ((0, 14), (0, 15)):
        start = dt.datetime(2026, 4, 15, hour, minute, 0)
        buckets.roll_up([row(external_id='zz-%d' % hour, minute=minute)],
                        {'bluesky': 'ok'}, {start})

    chart = detail.intraday_chart_for('ZZA', ['bluesky'], now, '1D')

    observed = [c for c in chart.chatter if c is not None]
    assert observed, 'the two measured slots should carry counts'
    # The stretch between them was never observed and must be null, not zero.
    assert None in chart.chatter[1:-1]
```

- [ ] **Step 2: Run it to verify it fails**

```bash
python -m pytest tests/test_radar_detail.py::test_an_outage_in_the_middle_of_the_window_is_not_drawn_as_quiet -v
```

Expected: `AssertionError: assert None in [0, 0, 0, ...]`.

- [ ] **Step 3: Replace the leading-edge index with a covered set**

In `personal_apps/features/radar/detail.py`, replace `_watched_from_index` with:

```python
def watched_slots(sources, start, now, step_minutes, slots):
    """The slots in which any bucket at all was written for these sources.

    The proxy for "ingest was alive", and the same one board._covered_hours
    uses. It is a proxy and not a record: a genuine board-wide silence reads
    the same as a stopped daemon, and both resolve to "not measured" -- the
    honest half of the ambiguity, where the dishonest half would draw a zero.

    Replaces a MIN(bucket_start) that only ever nulled the LEADING gap, so an
    outage in the middle of a window was drawn as an hour of quiet.
    """
    rows = (db.session.query(RadarBucketSource.bucket_start)
            .filter(RadarBucketSource.source.in_(list(sources)),
                    RadarBucketSource.bucket_start >= start,
                    RadarBucketSource.bucket_start < now,
                    RadarBucketSource.status.in_(('ok', 'truncated')))
            .distinct().all())

    covered = set()
    for (bucket_start,) in rows:
        index = _slot_index(bucket_start, start, step_minutes, slots)
        if index is not None:
            covered.add(index)
    return covered
```

and in `intraday_chart_for`:

```python
    covered = watched_slots(sources, start, now, step_minutes, slots)

    chatter = []
    for index in range(slots):
        # A slot nobody was watching is unknown, not silent. Same rule the
        # daily chart follows, and now the same rule for an outage in the
        # MIDDLE of the window rather than only before it began.
        chatter.append(counts[index] if index in covered else None)

    first_watched = min(covered) if covered else None
    return Chart(start=start, closes=closes, chatter=chatter,
                 watched_from=(start + dt.timedelta(
                     minutes=first_watched * step_minutes)
                     if first_watched is not None else None),
                 step_minutes=step_minutes)
```

- [ ] **Step 4: Run it to verify it passes**

```bash
python -m pytest tests/test_radar_detail.py tests/test_radar_api.py -v
```

Expected: all pass.

- [ ] **Step 5: Commit**

```bash
git add personal_apps/features/radar/detail.py personal_apps/tests/test_radar_detail.py
git commit -m "fix(radar): an outage mid-window is a gap in the chart, not quiet"
```

---

