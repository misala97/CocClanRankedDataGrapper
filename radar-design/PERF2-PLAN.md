# PERF2 — shared background board results

> **For agentic workers:** REQUIRED SUB-SKILL: `superpowers:subagent-driven-development`.
> Steps use checkbox (`- [ ]`) syntax. **Part II is the only part authorized to
> run now.** Part I is the design Codex reviews; Part III and Part IV are
> preparation only.

**Goal:** take the board build off the web request path, so that two gunicorn
worker processes read one board that a producer built for both of them, and no
reader ever waits five seconds for a build it started itself.

**Architecture:** a bounded MariaDB-backed result store keyed by the exact
normalized board query. A producer outside the web request path claims a key
under a fenced lease, builds it with no transaction open, and publishes the
serialized payload atomically. Web workers only ever read. Per-account data
stays out of the stored payload and is added per request, as it already is.

**Tech stack:** the existing Flask app, SQLAlchemy over PyMySQL, MariaDB
10.11.14 on the target and MySQL 8.0.46 locally, APScheduler in the existing
`run_radar_ingest.py` daemon (candidate host, to be decided by measurement).

## Global constraints

Carried verbatim from `PERF1-PLAN.md` and from Codex's ruling
(`PERF1-CODEX-RULING.md`). Every task's requirements implicitly include these.

- **Semantics may not move.** Full filter/ranking/sorting semantics,
  source-version rules, distinct voices, tone denominator and null contracts,
  instrument identity, timestamps and account isolation. No smaller universe,
  shorter window, sampled counts or removed charts to hit a number.
- **No top-N limit before the calculations that globally correct sorting
  require.** `board.build` sorts before it limits, deliberately.
- **Targets are unchanged**: cold board API p95 at or under 2 s, warm p95 at or
  under 500 ms, board usable in the browser within 3 s, local sort and mode
  interactions within 100 ms where no new server result is needed. If one
  cannot be met, name the measured limiting factor — do not move the target.
- **An immediate `pending` response is not a usable board** and does not count
  as a cold success. Ready reads and first-ever missing-result completions are
  measured and reported separately.
- **Freshness must be truthful.** Stale data is never presented as newly
  computed.
- **Old `/radar/` and the hub keep working.** So does `observations.capture`,
  which is off and must stay off, and which is NOT to be coupled to the
  producer.
- **No** merge, push, deployment, production migration, service or
  configuration change, capture enablement or root-route promotion.
- **The held index `c4e17b90d3f2` is not on this branch** and no task may
  reintroduce it. `codex/radar-perf1` at `691f33a` is its evidence.
- **Reuse the existing database.** No Redis, no new service.

## Where this starts from

| | |
| --- | --- |
| Branch | `codex/radar-perf2`, based on `4221196`, the deployed SHA |
| Migration head | `a7c31f0b52d4`, same as production |
| Board build today | 24h All companies, one reader: **median 5.38s, p95 5.72s** on `personal_apps_radar_perf1` |
| Client abort | **8000 ms** (`static/radar/src/api.ts`) |
| Production workers | `gunicorn --workers 2`, no `--threads` — two single-threaded sync processes |
| Production pool | SQLAlchemy default 5 + 10 overflow = **15 connections per worker process** |

---

# Part I — the design

## I.1 The key

`_build_board` already keys on eight fields
(`features/radar/routes/api.py:451`). The shared key is those eight fields,
canonicalized to bytes:

```python
{"v": 1,
 "sources": [...],      # deduped
 "segments": [...],     # deduped
 "window": 12, "limit": 50, "venues": 1,
 "market": "us", "sort": None, "dir": "desc"}
```

serialized with `json.dumps(..., sort_keys=True, separators=(',', ':'))` and
hashed with SHA-256. The hash is the primary key; the JSON is stored beside it
so a key is readable without a decoder.

**Normalization is limited to transformations proven payload-identical**, and
Task S4 proves each one before it is adopted:

| Candidate | Why it is a candidate | Risk it must clear |
| --- | --- | --- |
| dedupe `sources` | `?sources=reddit,reddit` is one selection | none expected |
| sort `sources` | the payload's `sources` is already the rooted sorted set | `board.build` passes the list into `IN (...)`; order must not reach the payload |
| dedupe `segments` | same | none expected |
| **sort `segments`** | would collapse `?segment=mid,micro` and `?segment=micro,mid` | **the payload echoes `list(segments)` in request order** — likely rejected |
| force `dir='desc'` when `sort is None` | `board.build` ignores direction unless `sort in SORT_KEYS` | the payload echoes `dir` |

Any transformation that changes one byte of the payload is not adopted. A
larger key space is cheaper than a wrong board.

**`market` is never left to the default in a key.** `parse_query` resolves an
omitted market through `default_market(now)`, which flips between `de` and `us`
with the session. Resolution happens before the key is formed, so a key always
names a concrete market.

## I.2 The table

One table. It carries both the published result and the queue state, so
publication is one atomic `UPDATE` and there is no second table to keep
consistent.

```sql
CREATE TABLE radar_board_results (
  key_hash          CHAR(64)      NOT NULL,
  key_json          VARCHAR(1024) NOT NULL,
  payload_version   SMALLINT      NOT NULL,
  producer_revision VARCHAR(64)   NULL,
  state             VARCHAR(16)   NOT NULL,   -- pending|building|ready|failed
  warm              TINYINT       NOT NULL DEFAULT 0,
  as_of             DATETIME(6)   NULL,       -- the `now` the payload was built with
  built_at          DATETIME(6)   NULL,       -- when the build finished
  build_ms          INT           NULL,
  payload           MEDIUMBLOB    NULL,       -- zlib(json), never partial
  payload_bytes     INT           NULL,
  requested_at      DATETIME(6)   NOT NULL,
  request_count     INT           NOT NULL DEFAULT 0,
  lease_owner       VARCHAR(64)   NULL,
  lease_expires_at  DATETIME(6)   NULL,
  fence             BIGINT        NOT NULL DEFAULT 0,
  attempts          SMALLINT      NOT NULL DEFAULT 0,
  next_attempt_at   DATETIME(6)   NULL,
  last_error        VARCHAR(255)  NULL,
  PRIMARY KEY (key_hash),
  KEY ix_radar_board_results_queue (state, next_attempt_at),
  KEY ix_radar_board_results_warm (warm, as_of),
  KEY ix_radar_board_results_requested (requested_at)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
```

**Bounds.** Warm keys are never evicted. On-demand keys are capped at
`MAX_ON_DEMAND_KEYS = 128` rows, evicted by `requested_at` ascending. The queue
is capped at `MAX_PENDING = 32`; a cold key arriving past that cap is answered
`busy` — truthfully — rather than lengthening a queue nobody will reach in
time. Payload size is measured in Task S1 and bounds the table: a table cap of
`MAX_ON_DEMAND_KEYS` plus the warm set, times the measured payload, is the
storage claim, and it is a claim only once measured.

## I.3 The producer

One loop, concurrency **1**, in a process that is not a web worker.

```
claim:    UPDATE radar_board_results
             SET state='building', lease_owner=:me,
                 lease_expires_at=:now + LEASE, fence=fence+1,
                 attempts=attempts+1
           WHERE key_hash=:k
             AND ( (state IN ('pending','failed')
                    AND (next_attempt_at IS NULL OR next_attempt_at<=:now))
                OR (state='building' AND lease_expires_at < :now) )
          -- rowcount 1 = claimed. Read `fence` back; that number is the fence.
          -- COMMIT before building.

build:    board = board_mod.build(...); payload = serialize(board)
          -- no transaction held open across this. It takes seconds.

publish:  UPDATE radar_board_results
             SET state='ready', payload=:blob, payload_bytes=:n,
                 as_of=:as_of, built_at=:done, build_ms=:ms,
                 payload_version=:v, producer_revision=:rev,
                 lease_owner=NULL, lease_expires_at=NULL,
                 attempts=0, last_error=NULL, next_attempt_at=NULL
           WHERE key_hash=:k AND fence=:my_fence
          -- rowcount 0 means someone re-claimed while we built.
          -- Our result is older than theirs. DISCARD IT.

fail:     UPDATE ... SET state='failed', last_error=:msg,
                        next_attempt_at=:now + backoff(attempts),
                        lease_owner=NULL, lease_expires_at=NULL
           WHERE key_hash=:k AND fence=:my_fence
```

`backoff(attempts)` is `min(30 * 2 ** (attempts - 1), 900)` seconds. A key that
has failed `MAX_ATTEMPTS = 6` times keeps its last good payload, if it has one,
and stops being retried until a reader asks again, which resets `attempts`.

**This answers the two defects the in-process single-flight had**, which Codex
named: there is no unclaimed retry path, because a builder that does not hold
the fence cannot publish; and a hung builder cannot poison its key, because the
lease expires and the reclaim increments the fence past it.

**Host.** The candidate is a new APScheduler job in `run_radar_ingest.py`,
beside `_scheduled_observations` — which is the existing precedent for a
board-reading job in that daemon, registered whether or not it is enabled. It
is a **candidate**, not a decision: Task S9 measures what a producer sweep does
to the write path before anything is chosen. If it contends, the fallback is a
separate unit, and that is a release-package decision, not this one.

**Capture stays uncoupled.** `observations.capture` calls `build_payload`
directly and needs an exact board at an exact `now`. It gets an explicit
`allow_build=True` argument that bypasses the store entirely. The producer
never calls capture and capture never populates the store.

## I.4 The read path

`build_payload` never builds. In full:

1. `parse_query` as today, then form the key.
2. `SELECT` the row. If `payload_version` differs from the running code's
   `PAYLOAD_VERSION`, treat it as missing — that is deployment invalidation.
3. `state='ready'` and age within `MAX_AGE`: **serve it.** Add `watching` and
   `watch_rows` for this account, as today.
4. `state='ready'` and age between `MAX_AGE` and `HARD_MAX_AGE`: **serve it,
   marked stale**, with its true age, and enqueue a refresh.
5. `state='ready'` and age beyond `HARD_MAX_AGE`: treat as missing. A board an
   hour old misdescribes a rolling window.
6. Missing: enqueue (`INSERT ... ON DUPLICATE KEY UPDATE requested_at=:now,
   request_count=request_count+1`) and answer `pending`. **Two web workers
   racing here produce one row and one queued job**, because the primary key
   says so — this is the cross-process deduplication the in-process
   single-flight could not do.
7. Queue full: answer `busy`.

Enqueueing is one short statement. No web request ever holds a transaction
across a build, because no web request builds.

## I.5 The freshness contract

Every response carries, at the top level beside `generated_at`:

| Field | Meaning |
| --- | --- |
| `as_of` | the instant the board was computed for — identical to `generated_at`, which already means this |
| `built_at` | when the build finished |
| `age_seconds` | `now - as_of`, computed at read time |
| `stale` | age is past `MAX_AGE` |
| `pending` | no usable result exists yet for this selection |
| `max_age_seconds` | the contract's own threshold, so the client need not hard-code it |

Proposed values, **to be confirmed against the capacity Task S3 measures**:

| | |
| --- | --- |
| `REFRESH_EVERY` | 120 s for warm keys |
| `MAX_AGE` | 300 s |
| `HARD_MAX_AGE` | 3600 s |

**What invalidates a result.** Not only the 15-minute ingest bucket. The board
moves with: new mention buckets, the scoring pass rewriting `mention_z` and
`expected`, quotes (divergence and move), sentiment judgments (tone and the
`lean` sort), source configuration changes, and the **rolling window itself** —
`board.build` uses `now - timedelta(hours=window)` unfloored, so the window
slides continuously and any stored result is stale at both ends by its own age.
This is why age is a first-class field rather than a TTL nobody can see. The
60-second TTL in production today does **not** establish that a longer age is
acceptable; it establishes only that 60 seconds was acceptable.

## I.6 The warm set

Sixteen keys, chosen to cover what the surface opens on and what the owner
reports:

```
sources  = ('bluesky', 'fourchan', 'reddit')       every root
limit    = 50, venues = 1, sort = None, dir = 'desc'
market   in ('us', 'de')
segments in ('', 'discover,mid,micro,unknown')     All companies; the default
window   in (1, 4, 12, 24)
```

Two markets times two segment selections times four windows is sixteen. This
contains the default board `/radar/` renders with no arguments, and it contains
12h and 24h All companies in both markets.

**Sorted boards are not warmed.** Thirteen sort variants would multiply the set
by thirteen for a control most sessions never touch. They are on-demand, and
the cold cost of an unwarmed selection is exactly what Task S2 quantifies and
returns to Codex.

## I.7 Compatibility

| Consumer | Today | After |
| --- | --- | --- |
| `/api/board` | builds, 60 s memo | reads the store; may answer `pending` or `stale` |
| `/radar/` page (`views.py:31`) | server-renders a full build | server-renders whatever the store has, including `pending` |
| hub page (`views.py:56`) | same | same |
| `observations.capture` | direct `build_payload` | direct `build_payload(allow_build=True)`, unchanged behaviour |
| the island (`api.ts`) | 8 s timeout, seven error reasons | must learn `pending`: poll, do not treat as an error |

The client change is the one product-visible piece, and it is where the cold
target actually lands. **It is not in this design's authorization**; the design
states the contract the client will need.

## I.8 Risks this design does not remove

- **A first-ever unwarmed selection still costs a full build.** The store makes
  it happen once globally instead of once per worker, and it stops occupying a
  web worker while it happens — it does not make it fast. Quantified in S2.
- **The producer is one process at concurrency 1.** If the warm sweep does not
  fit its cadence, the answer is a smaller warm set or a faster build, not more
  producers, until contention is measured.
- **MariaDB is not MySQL.** Every number in Part II is local. The mechanism
  transfers; the seconds do not.

---

# Part II — the feasibility spike (authorized now)

Disposable. Everything lives in `radar-design/perf2-spike/` and **nothing in
`personal_apps/` is modified by any task in this part** except where a task
says so explicitly and reverts it. No migration is added; the spike creates its
table with raw DDL against `personal_apps_radar_perf1` and drops it on request.

**Prerequisites, all of them:** as in `radar-design/perf1-bench/README.md` —
run from `personal_apps/`, against `personal_apps_radar_perf1`
(9,272,064 rows), with `innodb_buffer_pool_size = 2560M`. Each script prints
the pool it found. A run that reports a smaller pool is not evidence.

**Every result goes into `PERF2-LEDGER.md` as it is measured**, with the script
that produced it named. A number with no script is not a result.

### Task S1: the store, and what a payload weighs

**Files:**
- Create: `radar-design/perf2-spike/store.py`
- Create: `radar-design/perf2-spike/keys.py`
- Create: `radar-design/perf2-spike/run_s1_payload.py`

**Interfaces:**
- Produces: `keys.canonical(query) -> (key_hash: str, key_json: str)`;
  `store.create_table(engine)`, `store.drop_table(engine)`,
  `store.read(engine, key_hash, now) -> Result | None`,
  `store.enqueue(engine, key_hash, key_json, now, warm=False) -> str` (the
  resulting state), `store.claim(engine, owner, now) -> Claim | None`,
  `store.publish(engine, claim, payload_bytes, as_of, built_at, build_ms) -> bool`,
  `store.fail(engine, claim, message, now) -> None`.
  `Result` carries `state, payload, as_of, built_at, age_seconds, payload_version`.
  `Claim` carries `key_hash, key_json, fence, owner`.

- [ ] **Step 1: write the table and the key**, exactly as Part I.2 and I.1
      specify. `keys.canonical` takes the `Query` dataclass from
      `features.radar.routes.api` and applies only dedupe — no sorting, no
      `dir` collapsing. Those are candidates S4 rules on.
- [ ] **Step 2: measure one payload.** Build 24h All companies US at a fixed
      `now`, `serialize` it, and record: raw JSON bytes, `zlib` level 6 bytes,
      compress milliseconds, decompress milliseconds. Repeat for 1h, 4h, 12h
      and for the default four-segment selection.
- [ ] **Step 3: measure what `serialize` costs beyond the board.**
      `spend.summary()`, `llm_sentiment.ops_summary()` and
      `market_data.ops_summary()` are database reads inside `serialize`. Time
      them separately. **This decides whether they are frozen into the stored
      payload or recomputed per read**, and the decision goes in the ledger
      with its number.
- [ ] **Step 4: record the storage bound** as a number of megabytes, from the
      measured payload and the row caps.
- [ ] **Step 5: commit.**

```bash
git add radar-design/perf2-spike radar-design/PERF2-LEDGER.md
git commit -m "spike(radar): the board result store, and what a board weighs"
```

### Task S2: cross-process reuse, and the cold miss measured apart

**Files:**
- Create: `radar-design/perf2-spike/producer.py`
- Create: `radar-design/perf2-spike/reader.py`
- Create: `radar-design/perf2-spike/run_s2_reuse.py`

**Interfaces:**
- Consumes: everything S1 produces.
- Produces: `producer.serve_once(engine, owner, now) -> str | None` (the key it
  built, or None); `reader.read_payload(engine, args, now, user_id) -> dict`,
  which is the shape `build_payload` will take: it reads the store, adds
  `watching` and `watch_rows`, and **never builds**.

- [ ] **Step 1: two independent OS processes must reuse one result.** Not two
      threads. `run_s2_reuse.py` starts a producer with `subprocess.Popen`,
      waits for `state='ready'`, then starts **two more subprocesses**, each
      running `reader.py` against the same key, and compares the SHA-256 of
      what each received. Assert identical digests and a build count of one,
      and record each reader's wall time.
- [ ] **Step 2: report ready reads on their own.** Twenty serial ready reads
      per window at 12h and 24h through `reader.read_payload`, including the
      per-account `watch_rows` query. Median, p95, max. **This is the number
      that answers the warm target.**
- [ ] **Step 3: report the first-ever miss on its own, in three parts.**
      For a key never built: (a) the time for the reader to answer `pending`;
      (b) the time from enqueue to `state='ready'`; (c) (a) plus (b) — the time
      until a reader can actually see that board. **(c) is the cold number.**
      State plainly that (a) is not a board.
- [ ] **Step 4: two processes race a cold key.** Two reader subprocesses hit
      the same missing key inside the same millisecond window. Assert exactly
      one row and exactly one queued job — the global deduplication the
      in-process single-flight could not do.
- [ ] **Step 5: commit.**

### Task S3: can one producer keep sixteen keys fresh

**Files:**
- Create: `radar-design/perf2-spike/run_s3_capacity.py`

- [ ] **Step 1: sweep the warm set once**, concurrency 1, and record every
      key's build milliseconds and the total.
- [ ] **Step 2: sweep it three times** and report the median sweep.
- [ ] **Step 3: compute the sustainable cadence** — the shortest
      `REFRESH_EVERY` for which a sweep finishes with margin, and the duty
      cycle at that cadence. If 120 s does not fit, say what does, and say what
      the warm set would have to shrink to for 120 s to fit.
- [ ] **Step 4: state the worst age a warm key reaches** at the chosen cadence,
      which is the freshness the contract can honestly promise.
- [ ] **Step 5: commit.**

### Task S4: the semantics do not move

**Files:**
- Create: `radar-design/perf2-spike/run_s4_parity.py`

- [ ] **Step 1: fix `now`.** One instant, injected, for every comparison in
      this task. A moving `now` makes parity untestable.
- [ ] **Step 2: compare store against direct build** for at least these twelve
      selections, by SHA-256 of the full serialized payload: 12h All US, 24h
      All US, 24h All DE, 12h default-segments US, 1h All US, 4h All US, 24h
      `venues=2` US, 24h `limit=100` US, 24h `sort=lean` descending US, 24h
      `sort=mentions` ascending US, `sources=reddit` 24h US, and
      `sources=reddit:wallstreetbets` 24h US.
- [ ] **Step 3: rule on each normalization candidate** from Part I.1 by
      measurement: build both orderings and compare payload digests. Adopt only
      what is byte-identical. Record each verdict in the ledger.
- [ ] **Step 4: prove the sort-before-limit contract survives.** For
      `sort=lean` at `limit=50`, assert the store's rows equal the direct
      build's rows in order — this is the one the brief says is load-bearing.
- [ ] **Step 5: commit.**

### Task S5: private data stays private

**Files:**
- Create: `radar-design/perf2-spike/run_s5_isolation.py`

- [ ] **Step 1: two accounts, one key.** Give user A and user B different
      watch lists. Have both read the same stored key.
- [ ] **Step 2: assert the stored blob is account-free.** Decompress the stored
      payload and assert `watching` and `watch_rows` are absent from it —
      searched as raw bytes for each account's tickers, not only by key name.
- [ ] **Step 3: assert each response carries its own.** A's response has A's
      tickers, B's has B's, and neither has the other's.
- [ ] **Step 4: commit.**

### Task S6: failure is bounded

**Files:**
- Create: `radar-design/perf2-spike/run_s6_failure.py`

- [ ] **Step 1: kill a producer mid-build.** Kill the subprocess during a
      build. Assert the key stays `building` until `lease_expires_at`, then a
      second producer reclaims it and publishes. Record the recovery time.
- [ ] **Step 2: fence an overtaken builder.** Producer 1 claims, is paused past
      its lease, producer 2 reclaims and publishes a newer result, then
      producer 1 tries to publish. **Assert producer 1's publish affects zero
      rows and the newer result stands.**
- [ ] **Step 3: a build that always raises.** Assert bounded attempts, growing
      backoff, no unclaimed retry, and the last good payload still served,
      marked stale, throughout.
- [ ] **Step 4: producer outage.** Stop the producer entirely for longer than
      `MAX_AGE`. Assert readers keep getting a truthful stale board with a real
      age, that **no web-path build is ever started**, and that recovery needs
      no manual step.
- [ ] **Step 5: no long transactions.** Instrument the producer's connection
      and assert no transaction is open across the build. Report the longest
      transaction seen.
- [ ] **Step 6: commit.**

### Task S7: restart, empty, expired

**Files:**
- Create: `radar-design/perf2-spike/run_s7_lifecycle.py`

- [ ] **Step 1: web-worker restart.** Read a ready key in one process, exit,
      start a fresh process, read again. Assert the second read is a ready read
      at ready-read latency — the result survived the process, which the
      in-process dict never did.
- [ ] **Step 2: fully empty store.** Truncate, then measure the first request
      for the default board: what the reader answers, and how long until a
      board exists.
- [ ] **Step 3: expired data.** Age a stored result past `MAX_AGE` and past
      `HARD_MAX_AGE` by writing `as_of` backwards. Assert the three behaviours
      of Part I.4 — serve, serve stale, treat as missing — and that the
      reported `age_seconds` is the real age.
- [ ] **Step 4: deployment invalidation.** Store a result at
      `payload_version = N`, read it with the code at `N + 1`, assert it is
      treated as missing.
- [ ] **Step 5: commit.**

### Task S8: rapid filter switching, and the browser

**Files:**
- Create: `radar-design/perf2-spike/run_s8_switching.py`
- Create: `radar-design/perf2-spike/run_s8_browser.py`

- [ ] **Step 1: six filter changes back to back** through the store path, with
      the warm set warm. PERF1 measured 34.54 s total and 5.41 s worst for this
      on the deployed code; report the same two numbers.
- [ ] **Step 2: the same six with three of them unwarmed**, which is the honest
      case, and report it separately.
- [ ] **Step 3: a real browser.** Serve the app locally (`PYTHONPATH=.`, port
      5001, minted session cookie), point **python-playwright** at `/radar/`,
      and record time to a first contentful board for a warm key, an unwarmed
      key and a stale key. Screenshot each. A `pending` render is reported as
      `pending`, not as a board.
- [ ] **Step 4: commit.**

### Task S9: what the producer does to ingest

**Files:**
- Create: `radar-design/perf2-spike/run_s9_contention.py`

- [ ] **Step 1: baseline the write side.** Run the representative bulk update
      `radar-design/perf1-bench/write_cost.py` measures — one bulk `UPDATE` of
      an indexed column across 16,793 existing rows, restored afterwards — with
      no producer running. Median of three.
- [ ] **Step 2: run it under a producer sweep** and report both sides: how much
      slower the write got, and how much slower the sweep got.
- [ ] **Step 3: rule on the host.** If the producer measurably delays the write
      path, the ingest daemon is the wrong host and the ledger says so. This is
      a measurement, not a preference.
- [ ] **Step 4: commit.**

---

# Part III — worker threading, prepared not applied

Codex approved a **local evaluation** of two workers with two threads against
the two sync workers production runs. No unit file is edited and no service is
restarted by any step here.

**A limit stated first: gunicorn does not run on Windows**, and there is no WSL
on this machine. What is measured is therefore a **model** — N operating-system
processes each running the WSGI app with either one or two request threads —
not gunicorn itself. The ledger says so beside every number, and the return
says so to Codex. Anything that depends on gunicorn's own arbiter, worker
lifecycle or signal handling is **not** measured here.

### Task T1: two sync processes against two threaded processes

**Files:**
- Create: `radar-design/perf2-spike/run_t1_workers.py`

- [ ] **Step 1: build both models.** Two processes with one thread each, and
      two processes with two threads each, both serving the real WSGI app.
- [ ] **Step 2: non-Radar responsiveness under board load.** Drive two
      concurrent board builds and measure the latency of a cheap non-Radar
      request throughout. This is the claim that mattered: *two sync workers
      mean two board builds block the whole of personal_apps*. Confirm or
      refute it with a number.
- [ ] **Step 3: connection pool.** Record peak checked-out connections per
      process in both models against the 5 plus 10 default, and say how close
      two threaded workers come to exhausting it.
- [ ] **Step 4: memory.** Resident set size per process at rest and under two
      builds.
- [ ] **Step 5: shared mutable state.** Enumerate the module-level mutable
      state a threaded model would newly share within one process — starting
      with `board_cache`, `_board_lock`, the spend counters and any
      `llm_sentiment` module state — and state for each whether it is
      thread-safe. Reading the code is evidence here; guessing is not.
- [ ] **Step 6: write the recommendation**, with the gunicorn caveat, and the
      exact reversible unit-file change as text for a later release package.
      **Do not apply it.**
- [ ] **Step 7: commit.**

---

# Part IV — the latency log, prepared not activated

Codex chose request-duration access logging over a global slow-query-log
change, for preparation and local verification only.

### Task T2: the access-log proposal

**Files:**
- Create: `radar-design/PERF2-TELEMETRY.md`

- [ ] **Step 1: write the exact gunicorn `access_log_format`** with elapsed
      time (`%(L)s`), status and the path **without** query string, cookies,
      headers or any account identifier. `%(U)s` is the path without the query
      string; `%(r)s` is the request line **with** it and must not be used.
- [ ] **Step 2: verify the format really omits what it claims to.** Run
      gunicorn's own formatter locally against a request carrying a query
      string, a cookie and an `Authorization` header, and paste the resulting
      line. If gunicorn cannot be run on this machine, format the same fields
      through its own logger class directly and say that is what was done.
- [ ] **Step 3: estimate volume.** Requests per day times bytes per line, from
      the real route mix, and the resulting daily and 14-day size.
- [ ] **Step 4: rotation and retention**, as a concrete `logrotate` stanza
      matching the box's existing conventions.
- [ ] **Step 5: rollback** — the exact one-line reversal and what it costs.
- [ ] **Step 6: state plainly that this is not activated** and that activation
      is a target configuration change nobody has authorized.
- [ ] **Step 7: commit.**

---

# Part V — what Codex must still decide

Each of these is a question this design cannot answer by itself. The return
carries a measured number beside each one.

1. **The cold contract.** An unwarmed selection cannot meet the 2 s target: the
   build is around 4.5 s at 24h and moving it off the request path does not
   shorten it. S2 Step 3 quantifies it. Does the product accept a truthful
   `pending` for unwarmed selections, or does the warm set grow, or does the
   target move?
2. **The warm set's size**, against S3's measured capacity.
3. **The producer's host** — the ingest daemon or its own unit — against S9.
4. **Whether the ops summaries freeze** into the payload or are recomputed per
   read, against S1 Step 3.
5. **The refresh cadence and `MAX_AGE`**, against S3.
6. **Whether `--threads` is worth its risk**, against T1.
7. **Whether the held index returns.** It is worth around 0.9 s of a build that
   would now happen in the background, which is a different and weaker case
   than when a reader waited for it.
