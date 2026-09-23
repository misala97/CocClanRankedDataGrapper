
---

## SECOND REVIEW — what it found, and what it cost me

An independent read-only review of the concurrency patch reached the worker-
model conclusion above on its own, and then found three defects in the
single-flight by **executing** it rather than reading it. Two were real bugs
and one was a test that did not test what its name claimed.

### 1. A failed build started a herd

A woken waiter fell through and built **without claiming the key**, so every
waiter built, and each new arrival — finding `_board_builds` empty — started
another. The reviewer measured it:

```
one failing builder + 4 waiters -> 5 builds ran, 1 raised
(a single-flight should produce 2: the failure and ONE retry)
```

Firing precisely when the database is already unhealthy. `_build_board` now
loops back to the claim instead of falling through: the first waiter to wake
claims the retry and the rest wait on it. Bounded at two rounds so a
deterministically failing build cannot serialise every waiter behind
`BUILD_WAIT` apiece.

### 2. A hung build poisoned its key permanently

A build that neither returns nor raises never runs its `finally`, so its claim
stood forever and **every later reader of that selection paid the full
`BUILD_WAIT`** — indefinitely, and strictly worse than the code it replaced,
which cost only the hung request. The timeout path now clears that claim,
identity-checked so it can never clear a claim some other thread has since
made.

`BUILD_WAIT` came down from 30s to **8.0s**, matching the island's own abort.
The 30s reasoning — "a slow build should never be duplicated" — was right
about the board and wrong about everything else the waiter holds:
`login_required` has already checked a user out of the pool, so a parked
waiter holds one of fifteen connections and an open InnoDB read view against
a table `radar_ingest` writes to continuously.

### 3. The test I trusted was the one that did not work

`test_the_board_is_cached_before_the_waiters_are_woken` instrumented
`_board_builds.pop`, which happens after the cache write in **both** the
correct and the broken ordering. The reviewer reintroduced the bug and ran it
twenty times: it passed twenty times. The build-count test that `af3feb4`'s
message dismissed as passing "on scheduling luck" is in fact the only one that
ever caught it. Exactly inverted.

It now instruments `Event.set` itself — the thing whose order actually
matters.

### Every test is now mutation-checked

Each defect was put back and the suite re-run. A test that passes against the
bug it is named for is worse than no test, so this is no longer taken on
trust:

```
CAUGHT   cache written AFTER the waiters are woken
CAUGHT   waiter falls through unclaimed (the herd)
CAUGHT   timeout does not clear the dead claim (poisoning)
```

The poisoning test failed to catch its own bug on the first attempt, for a
reason worth keeping: the second reader's board was still in the cache, and a
cache hit never consults the claim. It expires the cache first now.

`conftest.py` clears `_board_builds` alongside `board_cache`; a claim left
behind by a killed builder would otherwise turn every later radar test on that
key into a `BUILD_WAIT` stall.

**229 backend tests pass**, four pre-existing environmental failures (this
worktree has no `npm run build`, so the page routes 404 — the same four with
this patch stashed).

---

## CORRECTION — the write cost was measured on the wrong write

The probe in `acceptance.py` INSERTed 20,000 rows at a `bucket_start` that did
not exist. Every fixture row sits on an exact hour and it wrote at `:30`, so
nothing collided: it measured 20,000 sequential appends at the right edge of a
`bucket_start`-leading B-tree, the cheapest pattern this index has. It claimed
to collide "the way ingest's `ON DUPLICATE KEY UPDATE` does" and did not. That
claim is in `31158f7`'s commit message too, and it is wrong there as well.

The real writers UPDATE columns this index carries — `scoring.py` bulk-updates
`expected`, `variance`, `mention_z` and `baseline_days`; `buckets.py` re-sets
`mention_count`, `distinct_authors`, `distinct_text_ratio` and `status` on the
live bucket every cycle. All eight are in the index, so each update
delete-marks and re-inserts a secondary-index entry instead of appending one.

Re-measured on that write — one bulk `UPDATE` of an indexed column across
16,793 rows that already exist, in the live partition, restored afterwards:

| | median of 3 |
| --- | --- |
| without the index | **0.42s** |
| with the index | **0.63s** |
| | **+50%** |

Roughly four times the penalty first reported. A per-row version of the same
test showed no difference at all (6.68s against 7.15s) because 16,793
separate statements are dominated by round-trip overhead — which is why the
bulk form is the one reported.

**+50% on the scoring pass is the number to weigh against the deployment.**
The pass already runs for tens of minutes.

## CORRECTION — two claims that had no artifact

The CORRECTION section above stated "six vCPUs" and "coc_stats running three
more gunicorn workers" as fact without evidence, in a document whose whole
discipline is that nothing is stated without one. The vCPU count comes from
the VPS build sheet, not from anything measured in this workstream. The
coc_stats workers ARE in the process listing quoted there, and the quote was
simply trimmed too far:

```
121326  gunicorn --workers 3 --bind 127.0.0.1:5000 app:app   (coc_stats)
121328  gunicorn --workers 2 --bind 127.0.0.1:5001 app:app   (personal_apps)
```

Both apps share one MariaDB. The vCPU figure should be treated as unverified
until someone reads it off the target.
