# PERF3 — shared board results, the product slice

> **For agentic workers:** REQUIRED SUB-SKILL: `superpowers:subagent-driven-development`.
> Steps use checkbox (`- [ ]`) syntax. One implementation worker per task,
> then one independent read-only review per task, then one whole-branch
> review. Every number goes into `PERF3-LEDGER.md` with the script that made
> it. **Nothing here touches production.**

**Goal:** the board is built once, by one supervised producer process, and
every web worker only ever reads it — with `pending`, `stale`, `busy`,
`failed` and genuinely-empty states that both clients render truthfully.

**Architecture:** one MariaDB/MySQL table keyed by (generation namespace,
exact normalized query) carries both the published payload and the queue
state. A dedicated producer claims under an unguessable per-claim lease
token, builds with no transaction open, and publishes atomically. Admission
and eviction are serialized by a per-namespace control row, so two
independent web processes cannot race a bound. Readers never build; a miss
enqueues and answers `pending`, and both clients poll with bounded backoff.

**Tech stack:** Flask 3.1 / SQLAlchemy 2.0 / Flask-Migrate 4.1 / PyMySQL on
MySQL 8.0.46 locally and MariaDB 10.11.14 on the target; React 19 with
TanStack Query 5 (hub) and plain hooks (old board); Vitest 4; pytest 9;
python-playwright 1.61.

## Binding ruling

`radar-design/PERF2-CODEX-RULING.md` (also the tail of
`CODEX-DECISIONS.md`). Where this plan and the ruling differ, the ruling
wins and the ledger records the discrepancy. The PERF2 spike under
`radar-design/perf2-spike/` is **evidence to learn from, not code to copy**:
it declares `VARCHAR(2048)`, deduplicates segments, has no namespace, uses a
per-row integer fence, and checks the queue cap only on row creation. Each
of those is corrected below.

## Global constraints

Every task's requirements implicitly include these.

- **Semantics may not move.** Filter/ranking/sorting semantics, source-version
  rules, distinct voices, tone denominator and null contracts, instrument
  identity, timestamps and account isolation are unchanged. `board.build`
  sorts before it limits, still.
- **Readers never build when the shared path is on.** No fallback branch that
  builds synchronously — not on a miss, not on stale, not on busy, not on a
  failed key. Enforced by a tripwire test that monkeypatches `board.build`
  to raise.
- **Keys preserve ordered/duplicated segments and the echoed direction.**
  `['mid','micro','mid']` and `['mid','micro']` are DIFFERENT keys. Sources
  are deduplicated and sorted only because Task 7 proves the payload is
  byte-identical either way; if that proof ever fails, the normalization
  goes, not the test.
- **`key_json` is `TEXT`** and the producer asserts the stored JSON reproduces
  the claimed hash before publishing. A 37-source, ~4,000-character legal key
  must round-trip under `sql_mode=''` as well as strict mode.
- **Namespace = SHA-256 of (PAYLOAD_VERSION, build revision, config
  fingerprint).** Producers and readers claim, read, publish, fail and clean
  only inside their own namespace. No `unknown` revision in production: a
  missing revision raises `ConfigError` when the shared path is enabled.
- **Fencing is an unguessable per-claim token** (`secrets.token_hex(16)`),
  checked together with namespace, key, owner and `queue_state='building'`.
  A stale builder can neither publish nor fail a newer row.
- **Bounds are enforced atomically.** 32 admitted pending/building/due-failed
  jobs per namespace, 128 on-demand rows per namespace, plus the 8 warm rows.
  Admission and eviction run under `SELECT ... FOR UPDATE` on the namespace's
  control row. Active claims are never evicted. `busy` writes nothing.
- **Queue state and payload availability are independent.** Disposition is
  decided from `payload`, `payload_version` and `as_of`, never from
  `queue_state`. A `building`/`failed` row with a usable prior payload keeps
  serving it under the age contract.
- **Freshness contract:** fresh ≤ 120 s, stale 120 < age ≤ 600 s (served,
  marked, refresh enqueued), hard-expired > 600 s (treated as missing). All
  three configurable by environment and tested at the exact boundaries.
  Always report `as_of`, `built_at`, `age_seconds`; both clients always show
  "Calculated … ago". Warm refresh target 120 s per key from its own
  `as_of`.
- **Fair scheduling:** `enqueued_at` is set when a row ENTERS `pending` and
  never moved by a poll. The producer alternates strictly between due warm
  work (oldest `as_of` first) and on-demand demand (oldest `enqueued_at`
  first) whenever both classes have claimable work. Polls (`poll=1`) never
  increment `request_count`.
- **Timestamps:** `as_of` = wall clock at the start of that key's build;
  `built_at` = wall clock at publication preparation; lease and backoff use
  the wall clock; elapsed time uses `time.perf_counter()`.
- **Transactions:** the claim commits before the build; no transaction is
  open while polling, sleeping, awaiting work or holding a lease idle; the
  ORM session is `remove()`d between jobs. The build's own read transaction
  is documented and bounded by the lease.
- **Capture stays off and uncoupled.** `observations.capture` calls
  `build_payload_direct` and never the store. `RADAR_OBSERVATION_CAPTURE_ENABLED`
  is set nowhere.
- **Feature flag:** `RADAR_BOARD_SHARED_RESULTS` — unset/`off` keeps today's
  synchronous memoised path byte-for-byte; `on` routes `/radar/`,
  `/radar/hub/` and `/radar/api/board` through the store. Reversible by
  environment plus restart.
- **Visual identity and sort/filter semantics of both clients are unchanged.**
  New states use existing components' vocabulary (`.oops`/`.none` on the
  old board, `rh-notice`/`rh-empty` in the hub). This is not B2.
- **Threads and the held index are untouched.** No `--threads`, no
  `c4e17b90d3f2`, no lock added to unrelated modules.
- **No merge, push, deployment, production migration/configuration, unit
  install, capture enablement or root promotion.** Databases:
  `personal_apps_radar_perf3` (tests; clone of `te1`, 29 FKs, stamp
  `a7c31f0b52d4`, gym data present) and `personal_apps_radar_perf3_scale`
  (timings; clone of `perf1` minus spike tables, 9.27 M `radar_bucket_sources`
  rows). The shared `personal_apps_radar_perf1` fixture is not modified.
- **Every measurement names its script**, its database and the buffer pool
  it found. A `pending` answer is never reported as a board.

---

## File structure

| Path | Responsibility |
| --- | --- |
| `personal_apps/features/radar/board_keys.py` | canonical key v2, `query_from_json`, round-trip check |
| `personal_apps/features/radar/board_namespace.py` | build revision resolution, config fingerprint, namespace hash, `ConfigError` |
| `personal_apps/features/radar/board_store.py` | the two tables' operations: read, admit, claim, publish, fail, warm refresh, eviction, retirement, heartbeat; env-configured limits |
| `personal_apps/features/radar/board_producer.py` | one job (`serve_once`), the loop, fair class choice, shutdown, readiness |
| `personal_apps/features/radar/board_shared.py` | the read path: envelope, disposition, per-account enrichment, pending shell |
| `personal_apps/features/radar/board_metrics.py` | one structured, identifier-free log line per board read and per build |
| `personal_apps/run_radar_board_producer.py` | the entrypoint the systemd unit runs |
| `personal_apps/models.py` | `RadarBoardNamespace`, `RadarBoardResult` |
| `personal_apps/migrations/versions/b7e3f9c1a2d4_add_radar_board_results.py` | one additive revision after `a7c31f0b52d4` |
| `personal_apps/features/radar/routes/api.py` | `build_payload_direct`, flag dispatch in `build_payload`, `poll` argument |
| `personal_apps/features/radar/routes/operations.py` | producer health on the admin ops endpoint |
| `personal_apps/features/radar/observations.py` | calls `build_payload_direct` |
| `personal_apps/static/radar/src/types.ts`, `api.ts`, `embedded.ts`, `pending.ts` | envelope types, `poll` flag, poll schedule |
| `personal_apps/static/radar/src/board/BoardPage.tsx`, `list/ListPane.tsx`, `list/Spend.tsx` | old board states |
| `personal_apps/static/radar/src/hub/queries.ts`, `Hub.tsx`, `PageState.tsx` | hub states |
| `personal_apps/tests/test_radar_board_keys.py` … `test_radar_board_parity.py` | backend tests, one file per module |
| `personal_apps/scratchpad/perf3/*.py` | rehearsal and measurement scripts (not app code) |
| `radar-design/PERF3-LEDGER.md`, `PERF3-RELEASE.md`, `HANDOFF.md` | the record |

---

### Task 1: the key and the namespace

**Files:**
- Create: `personal_apps/features/radar/board_keys.py`
- Create: `personal_apps/features/radar/board_namespace.py`
- Test: `personal_apps/tests/test_radar_board_keys.py`
- Test: `personal_apps/tests/test_radar_board_namespace.py`

**Interfaces:**
- Produces: `board_keys.KEY_VERSION = 2`;
  `board_keys.canonical(query) -> (key_hash: str, key_json: str)`;
  `board_keys.query_from_json(key_json) -> Query`;
  `board_keys.round_trips(key_hash, key_json) -> bool`.
- Produces: `board_namespace.PAYLOAD_VERSION = 1`;
  `board_namespace.ConfigError(RuntimeError)`;
  `board_namespace.build_revision(*, env=os.environ, root=None) -> str`;
  `board_namespace.config_fingerprint() -> str` (16 hex);
  `board_namespace.namespace() -> str` (64 hex, memoised per process);
  `board_namespace.describe() -> dict` with `payload_version`, `revision`,
  `fingerprint`, `namespace`.

- [ ] **Step 1: write the key tests.** In `tests/test_radar_board_keys.py`,
      using `from features.radar.routes.api import Query`:

```python
def q(**over):
    base = dict(sources=['bluesky', 'fourchan', 'reddit'], segments=[],
                window=12, limit=50, min_venues=1, market='us', sort=None,
                direction='desc')
    base.update(over)
    return Query(**base)

def test_duplicated_segments_are_a_different_key():
    """Codex reproduced the spike collapsing these. The payload echoes
    segments verbatim, so the key must too."""
    a, _ = board_keys.canonical(q(segments=['mid', 'micro', 'mid']))
    b, _ = board_keys.canonical(q(segments=['mid', 'micro']))
    assert a != b

def test_segment_order_is_a_different_key():
    assert board_keys.canonical(q(segments=['mid', 'micro']))[0] != \
        board_keys.canonical(q(segments=['micro', 'mid']))[0]

def test_direction_is_kept_even_without_a_sort():
    assert board_keys.canonical(q(direction='asc'))[0] != \
        board_keys.canonical(q(direction='desc'))[0]

def test_sources_are_deduplicated_and_sorted():
    """Task 7 proves the payload is byte-identical either way; this pins
    the normalization that proof licenses."""
    a, ja = board_keys.canonical(q(sources=['reddit', 'bluesky', 'reddit']))
    b, jb = board_keys.canonical(q(sources=['bluesky', 'reddit']))
    assert a == b and ja == jb

def test_market_must_be_resolved():
    with pytest.raises(AssertionError):
        board_keys.canonical(q(market='moon'))

def test_the_json_is_the_exact_inverse():
    query = q(segments=['mid', 'mid'], sort='lean', direction='asc',
              limit=100, min_venues=2, market='de',
              sources=['reddit:wallstreetbets', 'bluesky'])
    key_hash, key_json = board_keys.canonical(query)
    back = board_keys.query_from_json(key_json)
    assert board_keys.canonical(back) == (key_hash, key_json)
    assert back.segments == ['mid', 'mid'] and back.direction == 'asc'

def test_a_long_legal_key_round_trips():
    """37 sources of long-but-legal names: ~4,000 characters."""
    names = ['reddit:' + ('x' * 100) + str(i) for i in range(37)]
    key_hash, key_json = board_keys.canonical(q(sources=names))
    assert len(key_json) > 3500
    assert board_keys.round_trips(key_hash, key_json)
    assert not board_keys.round_trips(key_hash, key_json[:-1])

def test_the_key_version_is_two():
    assert json.loads(board_keys.canonical(q())[1])['v'] == 2
```

- [ ] **Step 2: run them, watch them fail** (`ModuleNotFoundError`).
- [ ] **Step 3: implement `board_keys.py`.** `canonical` asserts
      `query.market in ('us', 'de')`; sources = `sorted(set(query.sources))`;
      segments = `list(query.segments)` verbatim; fields
      `{'v': 2, 'sources', 'segments', 'window', 'limit', 'venues', 'market',
      'sort', 'dir'}`; `json.dumps(fields, sort_keys=True,
      separators=(',', ':'))`; SHA-256 hex. `query_from_json` asserts `v == 2`
      and rebuilds a `Query`. `round_trips` recomputes the hash of the JSON
      and ALSO re-canonicalises the decoded query and compares both.
- [ ] **Step 4: write the namespace tests.**

```python
def test_revision_prefers_the_explicit_environment(tmp_path):
    assert board_namespace.build_revision(
        env={'RADAR_BUILD_REVISION': 'a' * 40}, root=tmp_path) == 'a' * 40

def test_revision_reads_the_build_file_next(tmp_path):
    (tmp_path / 'BUILD_REVISION').write_text('b' * 40 + '\n')
    assert board_namespace.build_revision(env={}, root=tmp_path) == 'b' * 40

def test_revision_reads_git_head_last(tmp_path):
    git = tmp_path / '.git'; git.mkdir()
    (git / 'HEAD').write_text('ref: refs/heads/main\n')
    (git / 'refs' / 'heads').mkdir(parents=True)
    (git / 'refs' / 'heads' / 'main').write_text('c' * 40 + '\n')
    assert board_namespace.build_revision(env={}, root=tmp_path) == 'c' * 40

def test_a_worktree_gitfile_is_followed(tmp_path): ...  # `.git` is a file "gitdir: <path>"; commondir + packed-refs

def test_no_revision_is_a_configuration_error(tmp_path):
    with pytest.raises(board_namespace.ConfigError):
        board_namespace.build_revision(env={}, root=tmp_path)

def test_a_malformed_revision_is_refused(tmp_path):
    with pytest.raises(board_namespace.ConfigError):
        board_namespace.build_revision(env={'RADAR_BUILD_REVISION': 'not hex'}, root=tmp_path)

def test_the_namespace_moves_with_each_input(monkeypatch):
    base = board_namespace.compute_namespace(1, 'a' * 40, 'f' * 16)
    assert board_namespace.compute_namespace(2, 'a' * 40, 'f' * 16) != base
    assert board_namespace.compute_namespace(1, 'b' * 40, 'f' * 16) != base
    assert board_namespace.compute_namespace(1, 'a' * 40, '0' * 16) != base

def test_the_fingerprint_covers_source_and_price_configuration(monkeypatch):
    before = board_namespace.config_fingerprint()
    monkeypatch.setattr(board_namespace, '_fingerprint_inputs',
                        lambda: {'source_config_version': 'changed'})
    assert board_namespace.config_fingerprint() != before

def test_the_process_namespace_is_memoised_and_resolves_here():
    """This worktree is a git checkout, so the git fallback resolves."""
    a = board_namespace.namespace(); b = board_namespace.namespace()
    assert a == b and len(a) == 64
```

- [ ] **Step 5: implement `board_namespace.py`.** Resolution order:
      `env['RADAR_BUILD_REVISION']` → `<root>/BUILD_REVISION` file →
      git HEAD read from files (handle `.git` directory, `.git` gitfile
      `gitdir:` for worktrees, `ref:` indirection, `packed-refs`,
      `commondir`); `root` defaults to the repository root two levels above
      `personal_apps/`. A revision must match `^[0-9a-f]{7,64}$`. Anything
      unresolved raises `ConfigError('RADAR_BUILD_REVISION is not set, no
      BUILD_REVISION file, and no git HEAD could be read')`. Never a
      subprocess. `_fingerprint_inputs()` returns
      `{'source_config_version': config.source_config_version(),
      'price_provider': list(config.price_provider_config()),
      'reddit_fetcher': config.REDDIT_FETCHER,
      'default_segment': config.DEFAULT_SEGMENT,
      'sort_keys': list(board.SORT_KEYS)}`; fingerprint is the first 16 hex
      of SHA-256 over its sorted JSON. `compute_namespace(version, revision,
      fingerprint)` = SHA-256 hex of `f'{version}:{revision}:{fingerprint}'`.
      `namespace()` memoises in a module dict; `reset()` clears it for tests.
- [ ] **Step 6: run both files green; commit.**

```bash
git add personal_apps/features/radar/board_keys.py personal_apps/features/radar/board_namespace.py personal_apps/tests/test_radar_board_keys.py personal_apps/tests/test_radar_board_namespace.py
git commit -m "feat(radar): the shared board key keeps every echoed dimension, and the cache namespace is derived, not typed"
```

---

### Task 2: the tables, the migration, and the store

**Files:**
- Modify: `personal_apps/models.py` (append after `RadarBoardObservation`)
- Create: `personal_apps/migrations/versions/b7e3f9c1a2d4_add_radar_board_results.py`
- Create: `personal_apps/features/radar/board_store.py`
- Create: `personal_apps/scratchpad/perf3/rehearse_board_results_mariadb.py`
- Test: `personal_apps/tests/test_radar_board_results_migration.py`
- Test: `personal_apps/tests/test_radar_board_store.py`

**Interfaces:**
- Consumes: `board_keys.canonical`, `board_namespace.namespace()`,
  `board_namespace.PAYLOAD_VERSION`.
- Produces (all take `engine` and a naive-UTC `now`; all open and close
  their own short transactions; nothing here holds a transaction across a
  call boundary):
  - `board_store.Limits` dataclass read from env by `board_store.limits()`:
    `fresh_seconds=120`, `hard_expiry_seconds=600`, `refresh_seconds=120`,
    `lease_seconds=120`, `max_queue=32`, `max_on_demand=128`,
    `max_attempts=6`, `park_seconds=900`, `retire_seconds=86400`,
    `warm_limit=8` (env names `RADAR_BOARD_FRESH_SECONDS`,
    `RADAR_BOARD_HARD_EXPIRY_SECONDS`, `RADAR_BOARD_REFRESH_SECONDS`,
    `RADAR_BOARD_LEASE_SECONDS`, `RADAR_BOARD_MAX_QUEUE`,
    `RADAR_BOARD_MAX_ON_DEMAND`, `RADAR_BOARD_MAX_ATTEMPTS`,
    `RADAR_BOARD_PARK_SECONDS`, `RADAR_BOARD_NAMESPACE_RETIRE_SECONDS`).
  - `ensure_namespace(engine, ns, now, *, revision, payload_version)`
    (idempotent insert of the control row).
  - `read(engine, ns, key_hash) -> Result | None` where `Result` carries
    `key_hash, key_json, queue_state, warm, payload, payload_version, as_of,
    built_at, build_ms, enqueued_at, requested_at, request_count, attempts,
    next_attempt_at, last_error, lease_expires_at`.
  - `admit(engine, ns, key_hash, key_json, now, *, warm=False, poll=False)
    -> str` returning `'pending' | 'building' | 'busy' | 'parked'`.
  - `due_warm(engine, ns, now) -> list[str]` and
    `refresh_warm(engine, ns, warm_keys, now)` which upserts the warm rows
    and moves those whose `as_of` is NULL or ≤ `now - refresh_seconds` and
    whose `queue_state` is `idle` to `pending` with `enqueued_at=now`.
  - `claim(engine, ns, owner, now, *, prefer='warm' | 'demand') ->
    Claim | None` with `Claim(key_hash, key_json, token, owner, warm,
    enqueued_at, attempts)`.
  - `publish(engine, ns, claim, blob, *, as_of, built_at, build_ms,
    producer_revision) -> bool`, `fail(engine, ns, claim, error, now) -> bool`.
  - `evict(engine, ns, now) -> int`, `retire_namespaces(engine, keep_ns,
    now) -> int`, `heartbeat(engine, ns, owner, now, *, success_at=None,
    error=None)`, `health(engine, ns) -> dict`, `queue_summary(engine, ns,
    now) -> dict(pending, building, failed_due, on_demand_rows, warm_ready)`.

- [ ] **Step 1: the models.** Append to `models.py`:

```python
class RadarBoardNamespace(db.Model):
    """One row per cache generation. Its row lock serialises admission and
    eviction across independent web and producer processes; its
    timestamps are the producer's health and the retirement clock."""
    __tablename__ = 'radar_board_namespaces'
    __table_args__ = ({'mysql_charset': 'utf8mb4'},)
    namespace         = db.Column(db.String(64), primary_key=True)
    payload_version   = db.Column(db.SmallInteger, nullable=False)
    producer_revision = db.Column(db.String(64), nullable=True)
    created_at        = db.Column(MYSQL_DATETIME(fsp=6), nullable=False)
    last_seen_at      = db.Column(MYSQL_DATETIME(fsp=6), nullable=False)
    producer_owner    = db.Column(db.String(64), nullable=True)
    producer_seen_at  = db.Column(MYSQL_DATETIME(fsp=6), nullable=True)
    producer_success_at = db.Column(MYSQL_DATETIME(fsp=6), nullable=True)
    producer_error    = db.Column(db.String(255), nullable=True)


class RadarBoardResult(db.Model):
    """The published board for one exact selection AND its queue state.
    Queue state and payload availability are independent columns."""
    __tablename__ = 'radar_board_results'
    __table_args__ = (
        db.Index('ix_radar_board_results_queue', 'namespace', 'queue_state',
                 'next_attempt_at'),
        db.Index('ix_radar_board_results_warm', 'namespace', 'warm', 'as_of'),
        db.Index('ix_radar_board_results_demand', 'namespace', 'warm',
                 'requested_at'),
        {'mysql_charset': 'utf8mb4'},
    )
    namespace         = db.Column(db.String(64), primary_key=True)
    key_hash          = db.Column(db.String(64), primary_key=True)
    key_json          = db.Column(db.Text, nullable=False)
    payload_version   = db.Column(db.SmallInteger, nullable=False)
    producer_revision = db.Column(db.String(64), nullable=True)
    queue_state       = db.Column(db.String(16), nullable=False)   # idle|pending|building|failed
    warm              = db.Column(db.Boolean, nullable=False, default=False, server_default=sa.false())
    as_of             = db.Column(MYSQL_DATETIME(fsp=6), nullable=True)
    built_at          = db.Column(MYSQL_DATETIME(fsp=6), nullable=True)
    build_ms          = db.Column(db.Integer, nullable=True)
    payload           = db.Column(MEDIUMBLOB, nullable=True)
    payload_bytes     = db.Column(db.Integer, nullable=True)
    enqueued_at       = db.Column(MYSQL_DATETIME(fsp=6), nullable=True)
    requested_at      = db.Column(MYSQL_DATETIME(fsp=6), nullable=False)
    request_count     = db.Column(db.Integer, nullable=False, default=0, server_default='0')
    lease_owner       = db.Column(db.String(64), nullable=True)
    lease_token       = db.Column(db.String(32), nullable=True)
    lease_expires_at  = db.Column(MYSQL_DATETIME(fsp=6), nullable=True)
    attempts          = db.Column(db.SmallInteger, nullable=False, default=0, server_default='0')
    next_attempt_at   = db.Column(MYSQL_DATETIME(fsp=6), nullable=True)
    last_error        = db.Column(db.String(255), nullable=True)
```

`MEDIUMBLOB` comes from `sqlalchemy.dialects.mysql`; `MYSQL_DATETIME` is
already imported in `models.py`.

- [ ] **Step 2: the migration**, revision `b7e3f9c1a2d4`, `down_revision =
      'a7c31f0b52d4'`. Two `op.create_table` calls with the exact columns
      above, `mysql_charset='utf8mb4'`, the three indexes, and a downgrade
      that drops `radar_board_results` then `radar_board_namespaces`. One
      DDL statement per table per direction (the pattern
      `test_radar_migration.py` enforces). No data migration.
- [ ] **Step 3: migration tests** in `test_radar_board_results_migration.py`
      following `test_radar_projection_migration.py` (`disposable` fixture
      pinned to `personal_apps_radar_perf3`; alembic in-process):
      upgrade from `a7c31f0b52d4` creates exactly the two tables and the
      three indexes; downgrade removes exactly them and leaves
      `radar_board_observations` untouched; upgrade again is clean; `flask db
      heads` is single; and **the `TEXT` round-trip**: insert a 4,000-char
      `key_json` and a 12 KB blob, read them back byte-identical, under
      `SET SESSION sql_mode=''` as well as the default strict mode.
- [ ] **Step 4: the store tests** in `test_radar_board_store.py` against the
      disposable database (skip unless `db.engine.url.database ==
      'personal_apps_radar_perf3'`; use a random namespace per test and
      delete its rows in teardown). Pin, each as its own test:
      - `admit` of a missing key creates one `pending` row with
        `enqueued_at == requested_at == now`, `request_count == 1`.
      - two `admit`s of the same key from two threads on two engine
        connections leave ONE row, `request_count == 2`, `enqueued_at`
        unchanged by the second.
      - `admit(poll=True)` bumps neither `request_count` nor `enqueued_at`.
      - the 33rd distinct on-demand `admit` in a namespace answers `'busy'`
        and writes nothing (row count unchanged); a warm `admit` is never
        busy.
      - a `failed` row inside its backoff answers `'parked'` and stays
        `failed`; a `failed` row past `next_attempt_at` counts toward the 32.
      - the 129th on-demand row evicts the oldest `requested_at` row that is
        not `building`; a `building` row is skipped even when oldest.
      - `claim` returns None when nothing is due; claims a `pending` row,
        sets `queue_state='building'`, a 32-hex `lease_token`,
        `lease_expires_at = now + lease_seconds`, `attempts + 1`; a second
        `claim` from another owner returns None while the lease is live and
        succeeds after it expires with a DIFFERENT token.
      - `publish` with the live token sets `queue_state='idle'`, stores
        `payload`, `as_of`, `built_at`, `build_ms`, `payload_version`,
        clears the lease and `attempts`; `publish` with a stale token
        affects 0 rows and returns False.
      - **eviction/recreation fencing:** claim (token T1) → let lease expire
        → second owner claims (T2) and publishes → row evicted by `evict`
        after 128 newer rows → row recreated by `admit` → `publish` with T1
        returns False and `fail` with T1 returns False; the recreated row is
        `pending` with no payload.
      - `fail` sets `queue_state='failed'`, `next_attempt_at = now +
        min(30 * 2 ** (attempts - 1), 900)`, keeps the prior `payload`; at
        `attempts == 6` the row is parked 900 s.
      - `refresh_warm` upserts the 8 warm keys, marks only those with
        `as_of` older than `refresh_seconds` (or NULL) `pending`, and never
        touches a `building` row.
      - `retire_namespaces` deletes rows of a namespace whose `last_seen_at`
        is older than `retire_seconds` and is not the caller's; a live
        second namespace is untouched.
      - `heartbeat` / `health` round-trip the producer fields.
      - every public function leaves no open transaction: assert via a
        SQLAlchemy `begin`/`commit`/`rollback` event listener that each call
        ends with zero transactions in flight.
- [ ] **Step 5: implement `board_store.py`.** The load-bearing statements:

```sql
-- admit (inside ONE transaction; the control row lock is the mutex)
SELECT namespace FROM radar_board_namespaces WHERE namespace = :ns FOR UPDATE;
SELECT queue_state, next_attempt_at, warm FROM radar_board_results
 WHERE namespace = :ns AND key_hash = :k;
-- if missing or (idle) or (failed AND next_attempt_at <= :now):
SELECT COUNT(*) FROM radar_board_results
 WHERE namespace = :ns AND (queue_state IN ('pending', 'building')
    OR (queue_state = 'failed' AND next_attempt_at <= :now));
-- >= max_queue and not warm and this key not already in that count -> 'busy', ROLLBACK, write nothing
INSERT INTO radar_board_results (namespace, key_hash, key_json, payload_version,
  queue_state, warm, enqueued_at, requested_at, request_count)
VALUES (:ns, :k, :j, :v, 'pending', :w, :now, :now, :initial)
ON DUPLICATE KEY UPDATE
  requested_at = :now,
  request_count = request_count + :initial,           -- :initial is 0 for a poll
  warm = GREATEST(warm, :w),
  enqueued_at = CASE WHEN queue_state IN ('pending', 'building') THEN enqueued_at
                     WHEN queue_state = 'failed' AND next_attempt_at > :now THEN enqueued_at
                     ELSE :now END,
  queue_state = CASE WHEN queue_state = 'building' THEN 'building'
                     WHEN queue_state = 'failed' AND next_attempt_at > :now THEN 'failed'
                     ELSE 'pending' END;
-- then, if not warm: evict oldest non-building on-demand rows beyond max_on_demand
COMMIT;

-- claim: candidates for one class, then a fenced UPDATE per candidate
UPDATE radar_board_results
   SET queue_state = 'building', lease_owner = :me, lease_token = :token,
       lease_expires_at = :expires, attempts = LEAST(attempts + 1, :max_attempts)
 WHERE namespace = :ns AND key_hash = :k
   AND ( (queue_state = 'pending')
      OR (queue_state = 'failed' AND next_attempt_at <= :now)
      OR (queue_state = 'building' AND lease_expires_at < :now) );

-- publish
UPDATE radar_board_results
   SET queue_state = 'idle', payload = :blob, payload_bytes = :n, as_of = :as_of,
       built_at = :built_at, build_ms = :ms, payload_version = :v,
       producer_revision = :rev, lease_owner = NULL, lease_token = NULL,
       lease_expires_at = NULL, attempts = 0, last_error = NULL, next_attempt_at = NULL
 WHERE namespace = :ns AND key_hash = :k AND lease_owner = :me
   AND lease_token = :token AND queue_state = 'building';

-- fail: same WHERE, sets queue_state='failed', last_error, next_attempt_at,
--       clears the lease, keeps payload/as_of/built_at.
```

`claim(prefer='warm')` selects warm candidates ordered by `as_of ASC`
(NULLs first); `prefer='demand'` selects `warm = 0` ordered by
`enqueued_at ASC`; each returns up to 8 candidates and tries the fenced
UPDATE in order; the caller falls back to the other class when the
preferred one yields nothing. Read the token back inside the claiming
transaction. `admit` for `poll=True` on a missing row STILL inserts (the
result may have been evicted) but with `:initial = 0`.

- [ ] **Step 6: MariaDB rehearsal.** `scratchpad/perf3/rehearse_board_results_mariadb.py`
      modelled on `scratchpad/rehearse_mariadb.py`: own Flask app bound to
      `REHEARSAL_URL` (loopback, port 3399, MariaDB asserted), drop/recreate
      the schema, stamp `a7c31f0b52d4`, upgrade to `b7e3f9c1a2d4`, assert
      both tables and three indexes via `information_schema`, insert the
      4,000-char key and a 12 KB blob under `sql_mode=''` and strict, read
      back identical, run `admit → claim → publish → read` through the real
      `board_store` against that engine, downgrade, assert both tables gone
      and `radar_board_observations` intact, upgrade again. Print a numbered
      check list. The controller starts the portable server from
      `C:/Users/michi/AppData/Local/Temp/claude/c--Users-michi-Desktop-CodingStuff/1067a3f3-80ea-40f8-86f1-2098692a7340/scratchpad/mariadb/mariadb-10.11.14-winx64/bin/`
      on port 3399 with a fresh datadir before this task is dispatched and
      names the exact command in the ledger.
- [ ] **Step 7: run `flask db upgrade` on `personal_apps_radar_perf3`**
      (`cd personal_apps && PYTHONPATH=. FLASK_APP=app.py py -3.12 -m flask db upgrade`)
      so the disposable database's stamp matches its schema; record
      `flask db current` in the ledger. Run the two test files green.
      Also run `tests/test_radar_migration.py` to prove the chain still
      has one head.
- [ ] **Step 8: commit.**

```bash
git add personal_apps/models.py personal_apps/migrations/versions/b7e3f9c1a2d4_add_radar_board_results.py personal_apps/features/radar/board_store.py personal_apps/scratchpad/perf3/rehearse_board_results_mariadb.py personal_apps/tests/test_radar_board_results_migration.py personal_apps/tests/test_radar_board_store.py
git commit -m "feat(radar): the board result store -- namespaced, token-fenced, and bounded under a row lock"
```

---

### Task 3: the producer

**Files:**
- Create: `personal_apps/features/radar/board_producer.py`
- Create: `personal_apps/run_radar_board_producer.py`
- Create: `personal_apps/features/radar/board_metrics.py`
- Test: `personal_apps/tests/test_radar_board_producer.py`

**Interfaces:**
- Consumes: everything Task 2 produces; `board_keys`; `board_namespace`;
  `features.radar.routes.api.parse_query`, `serialize`, `Query`;
  `board.build`; `config.source_root`.
- Produces:
  - `board_producer.warm_queries(now) -> list[Query]`: the EIGHT warm keys
    derived by calling `parse_query({'market': m, 'segment': seg,
    'window': str(w)}, now=now)` for `m in ('us', 'de')`, `seg in ('',
    DEFAULT_SEGMENT)`, `w in (12, 24)` — limit, venues, sources, sort and
    direction come from the parser's own defaults, never typed here.
  - `board_producer.build_blob(query, *, now) -> (blob: bytes, as_of,
    built_at, build_ms, payload_bytes)`: `board.build(...)`, root the
    sources exactly as `build_payload` does, `serialize`, add
    `ops_collected_at = as_of.isoformat() + 'Z'`, `json.dumps(sort_keys=True,
    default=str)`, `zlib.compress(level=6)`.
  - `board_producer.serve_once(engine, ns, owner, now_fn, *, prefer) ->
    str | None` (the key served, or None); `board_producer.Loop` with
    `run(stop_event)`, `tick()`, `readiness(engine, ns, now) -> dict`.
  - `board_metrics.log_read(**fields)` and `board_metrics.log_build(**fields)`
    which emit one line each on logger `radar.board` at INFO:
    `board read demand=initial|poll class=warm|ondemand key=<12 hex>
    outcome=ready|stale|pending|busy|failed cache_age=<s or -> queue_age=<s or ->
    read_ms=<n> account_ms=<n>` and `board build key=<12 hex> class=…
    queue_wait=<s> build_ms=<n> payload_bytes=<n> result=published|overtaken|failed`.
    No user ids, no query strings, no URLs, ever — a test greps the lines.

- [ ] **Step 1: tests first**, on the disposable database, with
      `board.build` monkeypatched to a fast fake that returns a `Board` with
      deterministic rows (see `test_radar_board_cache.py::counting_build`),
      and a fake clock:
      - `warm_queries` returns exactly 8 distinct keys, every one with
        `limit == 50`, `min_venues == 1`, `sort is None`,
        `direction == 'desc'`, `sources == list(SOURCES)`, and the segment
        list parsed from `DEFAULT_SEGMENT` for four of them and `[]` for the
        other four.
      - `serve_once` claims, builds, publishes; `read` afterwards decodes to
        the same payload; `as_of` is the clock at the START of the build
        (advance the fake clock inside the fake build and assert `as_of <
        built_at` by exactly that advance); `build_ms` is measured with
        `perf_counter` (monkeypatch it).
      - **round-trip guard:** corrupt `key_json` in the row (UPDATE it to a
        different legal key) → `serve_once` fails the row with
        `last_error` starting `KeyMismatch` and publishes nothing.
      - **fair scheduling:** 4 warm rows due and 6 demand rows pending →
        the order of served keys alternates warm, demand, warm, demand …
        and after all warm rows are served the remaining demand rows
        follow; the mirror case (demand first) also alternates. A sustained
        mixed run of 40 ticks with new demand arriving every tick never
        leaves a warm key older than `2 * refresh_seconds` and never leaves a
        demand row waiting more than `2 * (median build)` ticks — assert
        both bounds.
      - **failure:** a build that raises `RuntimeError('boom')` → row
        `failed`, backoff 30 s, prior payload kept and `read` still returns
        it; six failures → parked 900 s; attempts reset on the next success.
      - **overtaken builder:** claim with token T1, expire the lease, a
        second `serve_once` publishes with T2, then complete the first job
        (its `publish` returns False) → the row keeps T2's `as_of`;
        `log_build` says `result=overtaken`.
      - **no open transaction while idle:** run `Loop.tick()` with nothing
        due under the begin/commit listener from Task 2 and assert zero
        transactions are open after it returns and that `db.session` has no
        active transaction (`db.session.get_transaction() is None`) after
        every job.
      - **bounded shutdown:** start `Loop.run(stop_event)` in a thread with
        a fake build that sleeps 0.3 s, set the event mid-build, and assert
        the thread exits after that build completes (and publishes) within
        1 s.
      - **readiness:** `readiness()` returns `ready=False` with the missing
        keys listed until all 8 warm rows have a payload with `age <=
        fresh_seconds`, then `ready=True`.
      - **heartbeat:** after a tick the namespace row has `producer_seen_at
        == now`; after a publish `producer_success_at == now`; after a
        failure `producer_error` names the exception type.
      - metrics lines contain no `user`, `?`, `/radar` or account id.
- [ ] **Step 2: implement `board_producer.py`.** `Loop.tick(now)`:
      1. `ensure_namespace`; `heartbeat`.
      2. `refresh_warm(engine, ns, warm_keys, now)`.
      3. choose class: `self.next_class` alternates between `'warm'` and
         `'demand'` **only when the previous tick served the preferred
         class**; if the preferred class had nothing, serve the other and
         leave the preference so the starved class is tried first next time.
      4. `serve_once(...)`; on None sleep `poll_interval` (0.5 s) OUTSIDE any
         transaction (`db.session.remove()` first).
      5. every 60 s: `evict`, `retire_namespaces`, log `queue_summary`.
      `serve_once` computes `as_of = now_fn()` immediately before
      `board.build`, `build_ms` via `perf_counter`, `built_at = now_fn()`
      after serialization, then `publish`. On any exception: `fail` with
      `f'{type(exc).__name__}'` (no message text in the row) and log.
      Always `db.session.remove()` in a `finally`.
- [ ] **Step 3: the entrypoint `run_radar_board_producer.py`.** Mirrors
      `run_radar_ingest.py`'s shape (imports `app`, `logging.basicConfig`,
      `argparse`): flags `--once` (one tick, exit 0), `--readiness` (print
      `readiness()` as JSON, exit 0 when ready else 1), `--poll-interval`
      (default 0.5), `--owner` (default `f'{socket.gethostname()}:{os.getpid()}'`).
      `SIGTERM` and `SIGINT` set the stop event. Startup fails loudly with
      `ConfigError` when the namespace cannot be derived. Logs the namespace
      description once at start.
- [ ] **Step 4: run the tests green; commit.**

```bash
git add personal_apps/features/radar/board_producer.py personal_apps/features/radar/board_metrics.py personal_apps/run_radar_board_producer.py personal_apps/tests/test_radar_board_producer.py
git commit -m "feat(radar): one supervised producer builds the board -- fairly, fenced, and with nothing open while it waits"
```

---

### Task 4: the read path, the flag, and the API

**Files:**
- Create: `personal_apps/features/radar/board_shared.py`
- Modify: `personal_apps/features/radar/routes/api.py:508-547`
- Modify: `personal_apps/features/radar/routes/views.py` (no logic change;
  keep `build_payload` import — it dispatches)
- Modify: `personal_apps/features/radar/observations.py:60,133`
- Modify: `personal_apps/features/radar/routes/operations.py` (ops payload)
- Test: `personal_apps/tests/test_radar_board_shared_api.py`
- Modify: `personal_apps/tests/test_radar_observations.py` (the strip-list
  test must call `build_payload_direct`)

**Interfaces:**
- Consumes: Task 2 store, Task 1 keys/namespace, Task 3 metrics.
- Produces:
  - `api.shared_results_enabled() -> bool` (env
    `RADAR_BOARD_SHARED_RESULTS` in `{'1','true','yes','on'}`).
  - `api.build_payload_direct(args, now=None, user_id=None)` — today's
    function body, unchanged, plus the envelope fields below with
    `shared=False`.
  - `api.build_payload(args, now=None, user_id=None, poll=False)` —
    dispatches to `board_shared.read_payload` when enabled, else to
    `build_payload_direct`.
  - `board_shared.disposition(result, now, limits) -> (kind, age)` with
    `kind in ('missing', 'ready', 'stale')` — pure.
  - `board_shared.read_payload(engine, args, now, user_id, *, poll) -> dict`.
  - The **envelope**, present on EVERY board response from either path:

| field | ready | stale | pending | busy |
| --- | --- | --- | --- | --- |
| `shared` | path flag | | | |
| `pending` | false | false | **true** | false |
| `busy` | false | false | false | **true** |
| `stale` | false | **true** | false | false |
| `failed` | last build failed (bool) | same | same | false |
| `as_of`, `built_at`, `generated_at` | ISO Z | ISO Z | **null** | **null** |
| `age_seconds` | float | float | null | null |
| `fresh_seconds`, `hard_expiry_seconds` | limits | | | |
| `retry_after_ms` | null | 5000 | 1000 + 500·min(queue position, 8) | 5000 |
| `queue_age_seconds` | null | null | now − enqueued_at | null |
| `ops_collected_at` | = as_of | = as_of | null | null |
| `rows` | list | list | **null** | **null** |
| `watching`, `watch_rows` | per account | per account | `[]`, `[]` | `[]`, `[]` |
| selection echo (`market`, `window_hours`, `segments`, `sources`, `all_sources`, `min_venues`, `sort`, `dir`, `display_timezone`, `market_venue`, `session`, `next_boundary_label`, `next_boundary_at`, `triplet_hours`, `series_hours`, `lead_count`) | from payload | from payload | **computed from the parsed query** (session via `session_state`, boundary via `board._next_boundary`) | same |
| `segment_counts`, `venue_counts`, `excluded` | from payload | from payload | `{}`, `{'any': 0, 'multi': 0}`, `{}` | same |
| `spend`, `sentiment_ops`, `market_data_ops` | frozen in payload | frozen | **absent** | absent |

  The legacy path sets `as_of = built_at = generated_at`, `age_seconds =
  now - generated_at`, `stale = pending = busy = failed = False`,
  `retry_after_ms = None`, `queue_age_seconds = None`, `ops_collected_at =
  generated_at`, `shared = False`, and the limits.
- The route `/radar/api/board` reads `poll` from `request.args.get('poll')
  == '1'` and passes it through. `parse_query` ignores `poll` (it reads
  named keys only — verify, do not change it).

- [ ] **Step 1: tests first**, `test_radar_board_shared_api.py`, on the
      disposable database, with the flag set via `monkeypatch.setenv`:
      - **tripwire:** with the flag on, `board.build` and
        `leaderboard.build_rows` monkeypatched to raise, a GET of
        `/radar/api/board` for a key with no row answers 200, `pending:
        true`, `rows: null`, `generated_at: null`, `as_of: null`, and the
        selection echo matches the query; a second GET with `poll=1` leaves
        `request_count == 1`.
      - **ready:** publish a payload through `board_store` directly (a
        fixture `published(query, as_of)` in the test file that compresses
        a fake serialized board) with `as_of = now - 119.999 s` →
        `stale: false`, `age_seconds` ≈ 119.999, rows present, `generated_at
        == as_of`.
      - **exact boundaries:** `as_of = now - 120 s` → `stale: false`;
        `now - 120.001 s` → `stale: true` and the row is `pending`
        afterwards (refresh enqueued); `now - 600 s` → `stale: true`;
        `now - 600.001 s` → `pending: true`, `rows: null` (hard-expired is
        missing), row `pending`.
      - **failed with a usable payload:** row `failed`, `last_error =
        'RuntimeError'`, `as_of` 30 s old → served, `failed: true`,
        `stale: false`.
      - **busy:** 32 pending on-demand rows → a new key answers
        `busy: true`, `pending: false`, `retry_after_ms == 5000`, and the row
        count is unchanged.
      - **mixed versions:** a row published under a different namespace is
        invisible: the same key in namespace B is `pending` in namespace A
        while B's payload is still served to a reader whose
        `board_namespace.namespace()` is monkeypatched to B.
      - **per-account enrichment:** two accounts with different marks read
        the same key; each response carries its own `watching` and
        `watch_rows`; the stored blob (decompressed) contains neither
        account's tickers as raw bytes and no `watching` key.
      - **capture stays direct:** `observations.capture` with the flag ON
        calls `build_payload_direct` (monkeypatch it and assert the call),
        never `board_shared.read_payload`.
      - **legacy unchanged:** flag off → the response equals today's payload
        plus the envelope fields, and `board_cache` is used exactly as
        `test_radar_board_cache.py` pins (that file keeps passing).
      - **server-rendered pages embed the envelope:** `/radar/` and
        `/radar/hub/` with the flag on and no row embed `pending: true`
        with `rows: null`.
      - **ops health:** `/radar/api/ops` (admin) carries `board_results:
        {namespace, enabled, producer: {owner, seen_at, success_at, error},
        warm_ready, warm_total: 8, queue: {pending, building, failed_due},
        on_demand_rows}`; a non-admin still gets 403.
      - **metrics:** the read log line for each of ready/stale/pending/busy
        carries the right `outcome`, `demand=poll` for `poll=1`, and no
        identifier.
- [ ] **Step 2: implement `board_shared.py`.** `read_payload`: parse,
      canonical key, `ensure_namespace` (once per process, memoised),
      `store.read`, `disposition`; on `missing` → `admit(..., poll=poll)` →
      envelope pending/busy/parked (parked = pending with
      `retry_after_ms=5000` and `failed: true`); on `stale` → `admit(...,
      poll=poll)` for the refresh, then serve; decode, add envelope, add
      per-account `watching`/`watch_rows` exactly as `build_payload` does
      today, timing the account half for the metrics line. Queue position =
      count of `pending` rows in the namespace with `enqueued_at <` this
      row's. All datetimes ISO with `Z`.
- [ ] **Step 3: `api.py`:** rename the current body to
      `build_payload_direct`, add the legacy envelope fields to it, add
      `shared_results_enabled`, the new `build_payload` dispatcher, and
      `poll` on the route. `observations.py` imports and calls
      `build_payload_direct`. `operations.py` adds `board_results` from
      `board_store.health` + `queue_summary` + `board_namespace.describe()`
      (guarded: if the shared tables are absent, report `enabled` and
      `error: 'table missing'` rather than 500 — the flag may be on before
      the migration only by operator error, and the ops page must still
      render).
- [ ] **Step 4: run** `tests/test_radar_board_shared_api.py
      tests/test_radar_api.py tests/test_radar_board_cache.py
      tests/test_radar_observations.py tests/test_radar_hub_page.py
      tests/test_radar_operations_api.py` green; commit.

```bash
git add personal_apps/features/radar/board_shared.py personal_apps/features/radar/routes/api.py personal_apps/features/radar/routes/operations.py personal_apps/features/radar/observations.py personal_apps/tests/test_radar_board_shared_api.py personal_apps/tests/test_radar_observations.py
git commit -m "feat(radar): the board API reads the shared result behind a flag, and a miss is a pending answer, never a build"
```

---

### Task 5: the old board learns pending, stale, busy and failed

**Files:**
- Modify: `personal_apps/static/radar/src/types.ts:278-338`
- Modify: `personal_apps/static/radar/src/api.ts`
- Modify: `personal_apps/static/radar/src/embedded.ts`
- Create: `personal_apps/static/radar/src/pending.ts`
- Modify: `personal_apps/static/radar/src/board/BoardPage.tsx`
- Modify: `personal_apps/static/radar/src/list/ListPane.tsx` (the `Age`
  component and the rows block)
- Modify: `personal_apps/static/radar/src/list/Spend.tsx` (guard absent `spend`)
- Modify: `personal_apps/static/radar/src/fixtures.ts` (envelope defaults)
- Modify: `personal_apps/static/radar/radar.css` (only new state classes:
  `.age.stale`, `.age.expired`, `.none.pending`, `.oops.busy`)
- Test: `personal_apps/static/radar/src/pending.test.ts`
- Test: `personal_apps/static/radar/src/board/pending.test.tsx`

**Interfaces:**
- Consumes: the envelope of Task 4.
- Produces: `types.ts`: `BoardPayload` gains `shared: boolean`, `pending:
  boolean`, `busy: boolean`, `stale: boolean`, `failed: boolean`,
  `as_of: string | null`, `built_at: string | null`, `generated_at: string
  | null`, `age_seconds: number | null`, `fresh_seconds: number`,
  `hard_expiry_seconds: number`, `retry_after_ms: number | null`,
  `queue_age_seconds: number | null`, `ops_collected_at: string | null`,
  `rows: Row[] | null`; `spend?`, `sentiment_ops?`, `market_data_ops?` stay
  optional. Add `type ReadyBoard = BoardPayload & { rows: Row[]; as_of: string;
  generated_at: string }` and `isReady(p): p is ReadyBoard`.
- `api.fetchBoard(selection, signal, { poll?: boolean })` appends `&poll=1`
  when polling. `TIMEOUT_MS` stays 8000.
- `pending.ts`: `nextDelay(attempt: number, waitedMs: number,
  retryAfterMs: number | null, random = Math.random): number` — schedule
  `[1000, 1500, 2000, 3000, 3000, …]`, 5000 once `waitedMs >= 30_000`,
  never below `retryAfterMs`, ±20 % jitter; `DELAYED_AFTER_MS = 30_000`;
  `class Poller` with `start(fn)`, `stop()`, `pause()` (on hidden),
  `resume()` (on visible: one immediate fetch, schedule continues), a
  `generation` counter so a response from an older start is ignored.

- [ ] **Step 1: `pending.test.ts`:** the schedule values with `random` fixed
      at 0.5; jitter bounds; `retry_after_ms` as a floor; 5000 after 30 s;
      `Poller` stops on `stop()`, pauses on `pause()`, fires immediately on
      `resume()`, and a late callback from generation 1 is dropped after
      generation 2 starts.
- [ ] **Step 2: `board/pending.test.tsx`** with `stubFetch` routed by URL
      as `BoardPage.test.tsx` does:
      - an embedded pending payload renders the controls, the status
        "Calculating this board…", NO rows, NO "Nothing cleared the bar",
        and no timestamp; a `poll=1` request follows within the first delay.
      - when the poll answers a ready board, the rows appear and the age
        line reads "Calculated 0s ago".
      - switching the window while pending aborts the poll for the old
        selection (its late answer never lands: assert the rows are the
        new selection's), and the pending state names the NEW window.
      - `document.visibilityState = 'hidden'` stops polling; `'visible'`
        resumes with an immediate request.
      - after 30 s of pending (fake timers) the text changes to "Still
        calculating…" with a Retry button and a hint to change the
        selection; polls continue at 5 s.
      - a `busy` answer shows "The board is busy with other selections"
        with Retry, keeps controls usable, polls every 5 s.
      - a `stale` board renders its rows, the age line reads "Calculated 3m
        ago · refreshing", and polls at 5 s until `stale: false`.
      - a board whose age passes `hard_expiry_seconds` on the client clock
        is replaced by the pending state on the next tick (rows gone).
      - a `failed: true` board with rows shows the rows plus "Last refresh
        failed"; `failed` with `rows: null` shows the `.oops` error with
        Retry.
      - a ready EMPTY board (`rows: []`) still renders "Nothing cleared the
        bar in this window." — never for pending.
      - a legacy payload (`shared: false`, all flags false) renders exactly
        as today (`BoardPage.test.tsx` keeps passing unchanged).
- [ ] **Step 3: implement.** `BoardPage`: hold `received = Date.now()` beside
      the payload; a `Poller` ref; `load()` sets the payload from ANY answer
      (pending included — that removes the previous selection's rows, which
      is the ruling's requirement) and starts/stops the poller by
      `payload.pending || payload.busy || payload.stale`; `useEffect` on
      `visibilitychange`; the generation counter increments in `load`.
      `ListPane`: `Age` becomes `AgeLine({ payload, received })` and always
      renders `Calculated {humanAge(age)} ago` where `age = age_seconds +
      (Date.now() − received)/1000` ticking every second; stale adds
      `· refreshing`; the rows block renders `<p className="none pending"
      role="status">` for pending/busy/delayed instead of rows. `embedded.ts`:
      accept `rows === null` when `pending || busy` is true. `Spend.tsx`:
      render nothing when `payload.spend` is absent.
- [ ] **Step 4: `npx vitest run -c vite.radar.config.ts static/radar/src/board static/radar/src/pending.test.ts static/radar/src/list`**
      green, `npx tsc --noEmit` clean, `npm run build` green; commit.

```bash
git add personal_apps/static/radar/src personal_apps/static/radar/radar.css
git commit -m "feat(radar): the board island polls a pending answer and always says when its board was calculated"
```

---

### Task 6: the hub learns the same states

**Files:**
- Modify: `personal_apps/static/radar/src/hub/queries.ts`
- Modify: `personal_apps/static/radar/src/hub/Hub.tsx`
- Modify: `personal_apps/static/radar/src/hub/PageState.tsx`
- Modify: `personal_apps/static/radar/src/hub/Overview.tsx`, `Chatter.tsx`,
  `Watching.tsx` (accept `ReadyBoard`, render the age line)
- Modify: `personal_apps/static/radar/src/hub/hub.css` (new notice variants only)
- Test: `personal_apps/static/radar/src/hub/pending.test.tsx`
- Modify: `personal_apps/static/radar/src/hub/state.test.tsx`

**Interfaces:**
- Consumes: Task 5's types and `pending.ts`.
- Produces: `useBoard` returns react-query's result whose `data` may be a
  pending/busy envelope; `refetchInterval` is a function: pending/busy →
  `nextDelay(attempt, waited, retry_after_ms)` (attempt and waited kept in
  a ref keyed by `boardKey`), stale → 5000, ready → `REFRESH_MS`, hidden →
  `false`. Poll refetches call `fetchBoard(selection, signal, { poll: true })`
  when the current data is pending/busy/stale. `PageState.tsx` gains
  `Pending({ selection, delayed, onRetry })`, `Busy({ onRetry })`,
  `AgeLine({ board, received })` and `FailedNotice`.

- [ ] **Step 1: tests.** In `hub/pending.test.tsx`, mount `Hub` with a
      pending embedded payload: the Overview shows `Pending` (no "Nothing
      cleared the floor", no "built …"), the filters render, the next fetch
      carries `poll=1`; the ready answer renders Chatter with rows and the
      age line; a stale board shows the amber notice "Calculated 4m ago ·
      refreshing"; a busy answer shows `Busy`; after 30 s `Pending` shows
      the delayed copy with Retry; a hidden document stops refetching
      (`refetchInterval` returns false — assert no fetch during 10 s of fake
      time); changing the selection while pending abandons the old key's
      answer (assert the rendered context line names the new window, and
      the old key's late resolution does not repaint the new key's page).
      Extend `state.test.tsx` with the refetch-interval function's cases.
- [ ] **Step 2: implement.** `Hub.tsx` `Page`: before the
      overview/chatter/watching branch, if `board.data && !isReady(board.data)`
      render `Busy` or `Pending`; `StaleNotice` stays for a FAILED refresh
      with data; add `AgeLine` under the heading of the three pages (they
      already print `built {stamp(...)}` — replace that fragment with
      `Calculated {age} ago` and keep the venue/window words). The header
      `marketLabel` guards `board.data.session` for the envelope.
- [ ] **Step 3: run the hub suites, `tsc`, `npm run build`; commit.**

```bash
git add personal_apps/static/radar/src/hub
git commit -m "feat(radar): the hub renders pending, busy, stale and failed boards as what they are"
```

---

### Task 7: parity, adversarially

**Files:**
- Test: `personal_apps/tests/test_radar_board_parity.py`

**Interfaces:**
- Consumes: `board_producer.build_blob`, `board_shared.read_payload`,
  `api.build_payload_direct`, the seeding helpers' SHAPE from
  `tests/test_radar_board.py` (`universe`, `bucket`, `post` — copy them into
  this file under prefix `PT`, do not import test modules).

- [ ] **Step 1: a deterministic fixture** at `NOW = dt.datetime(2026, 1, 20,
      15, 0)` with prefix `PT`: 60 tickers (`PT00`…`PT59`) so that
      membership moves across `limit=50` under every sort; per ticker a
      universe row with caps spread across large/mid/micro/unknown/fund and
      two recent IPOs; buckets on `bluesky`, `fourchan` and
      `reddit:wallstreetbets` with distinct `mentions`, `expected`, `z`;
      posts with **real tones**: bullish, bearish, neutral (lexicon 0.0),
      unknown (no sentiment row) and null (`sentiment_judged_at` NULL) so
      `lean` has ties and Nones; quotes with moves for 40 of 60 tickers so
      `move` and `divergence` have Nones; one ticker with a pre-split root
      `reddit` bucket under an older `source_config_version` so the
      source-version rule is exercised; markets: quotes for both `us` and
      `de` (XGAT) on ten tickers.
- [ ] **Step 2: the comparison.** `def digest(payload)` strips the
      envelope-only fields (`shared, pending, busy, stale, failed, age_seconds,
      retry_after_ms, queue_age_seconds, watching, watch_rows, built_at`) and
      `spend`/`sentiment_ops`/`market_data_ops` (monkeypatched to constants
      anyway), then SHA-256 of `json.dumps(sort_keys=True, default=str)`.
      For every case: (a) `build_payload_direct(args, now=NOW,
      user_id=None)`; (b) `build_blob(query, now=NOW)` published into the
      store and read back via `read_payload(... user_id=None)`; assert equal
      digests AND equal `rows` order. Cases, each `pytest.mark.parametrize`d:
      - every `SORT_KEY × ('asc', 'desc')` at `limit=50` and at `limit=100`;
      - `sort=None` with `dir=asc` (echo preserved);
      - segments `''`, `DEFAULT_SEGMENT`, `'mid,micro,mid'`, `'micro,mid'`
        — and assert the LAST TWO are different keys and different echoes;
      - `venues=2`; `market=de`; omitted market at two clocks that resolve
        to `us` and `de` (assert the key names the resolved market);
      - sources `'reddit'`, `'reddit:wallstreetbets'`, `'bluesky,bluesky'`
        (dedupe proof: digest equals `'bluesky'`), `'reddit,bluesky'` vs
        `'bluesky,reddit'` (sort proof: same digest, same key);
      - the 37-source long key (names from `REDDIT_SUBS` plus long legal
        placeholders) — digest equal and the stored `key_json` length > 900.
- [ ] **Step 3: accounts.** Three accounts (`plain_user`-style fixtures)
      watching `['PT05']`, `['PT58', 'PT01']` and `[]`; read the same key:
      each response's `watching`/`watch_rows` equals `build_payload_direct`'s
      for that account; the blob contains none of them. A fourth account
      whose `build_pinned_rows` raises (monkeypatch) gets a 500 from the
      route today — assert the shared route behaves the same (the error is
      not swallowed into an empty list).
- [ ] **Step 4: run; commit.** The fixture seeds real rows and must delete
      them before and after (prefix filter), as `test_radar_board.py` does.

```bash
git add personal_apps/tests/test_radar_board_parity.py
git commit -m "test(radar): the shared board is the direct board, on every sort, both directions, and across the limit"
```

---

### Task 8: production-scale verification and the browser

**Files:**
- Create: `personal_apps/scratchpad/perf3/env_check.py` (asserts
  `personal_apps_radar_perf3_scale`, pool ≥ 2000 MB, the deployed index set,
  prints rows)
- Create: `personal_apps/scratchpad/perf3/serve_perf3.py` (the real app, flag
  on, one process, `--port`)
- Create: `personal_apps/scratchpad/perf3/measure_perf3.py`
- Create: `personal_apps/scratchpad/perf3/two_workers_perf3.py`
- Create: `personal_apps/scratchpad/perf3/browser_perf3.py`
- Create: `personal_apps/scratchpad/perf3/profile_watch_perf3.py`
- Modify: `radar-design/PERF3-LEDGER.md` (every number, every script)

Every script runs from `personal_apps/` with `PERSONAL_DB_NAME=personal_apps_radar_perf3_scale`
in its environment, `RADAR_BOARD_SHARED_RESULTS=on`, `RADAR_BUILD_REVISION`
set to `git rev-parse HEAD`, and prints the preflight block first. The
scale database was cloned from `perf1` (synthetic; source names
`reddit:sub00..32`) — spell the warm set's sources as the fixture's own
DISTINCT list exactly as `perf2-spike/selections.py` explains, and say so
beside every number. `flask db upgrade` is run once on the scale database
by the controller before this task and recorded.

**Amendment, 2026-09-11 -- an environment variable cannot select the
database.** Found while migrating the scale database. `app.py` calls
`load_dotenv(override=True)`, so the worktree `.env`
(`PERSONAL_DB_NAME="personal_apps_radar_perf3"`) silently overwrites any
`PERSONAL_DB_NAME` a script sets in its environment, and `find_dotenv()` also
asserts when a script arrives on stdin. The sentence above is therefore wrong
as written. Every Task 8 script and every subprocess it starts goes through
`personal_apps/scratchpad/perf3/scale_env.py`, which (1) loads the worktree
`.env` by explicit path WITHOUT override, for the credentials; (2) replaces
`dotenv.load_dotenv` with a no-op before `app` is imported; (3) sets
`PERSONAL_DB_NAME=personal_apps_radar_perf3_scale`; (4) asserts
`db.engine.url.database` after import and refuses anything else. Scripts
import it first (`import scale_env; scale_env.bind()`); subprocesses (the
producer, the web-model workers, `serve_perf3.py`) are launched as
`py -3.12 scratchpad/perf3/scale_env.py <script.py> [args...]`, which applies
the same four steps and runs the target with `runpy.run_path` and the
remaining argv. Never edit `.env` for this. The migration of the scale
database to `b7e3f9c1a2d4` was done this way by the controller.

**Amendment, 2026-09-11 (second) -- align the scale fixture with the wall
clock before anything is measured.** The perf1-derived fixture's data ends at
`2026-09-10 12:00` UTC (buckets and quotes; mention events start at
`2026-09-08 13:00`), and every process on the shared path reads the real
clock, so a board built today sees a partial or empty window. At
`2026-09-11 00:55` UTC a 24h window held 201,504 rows instead of about 405,000,
and a 12h window held none. Every board query is bounded above by `now`
(`leaderboard.py:183-184`; `board.py:200-201`, `259-260`, `315-316`,
`383-384`; `coverage.py:60-61`), so rows dated after the measuring clock are
invisible to any window, and extending the fixture forward is safe. The test
database is no substitute: its buckets end at `2026-09-01 18:15`, so every
board there is empty at the real clock. All of Task 8, the browser runs
included, therefore runs on the aligned scale database.

**Step 0, before Step 1:** `personal_apps/scratchpad/perf3/align_scale_fixture.py`,
through `scale_env`, idempotent and re-runnable before each measurement
session:

1. Copy the most recent 24-hour slice of `radar_bucket_sources`,
   `radar_mention_events` and `radar_quotes` forward by whole days (+1 d, +2 d,
   ...) until the data reaches at least 24 h beyond the moment the script runs.
   Whole-day shifts keep the 15-minute grid and the weekday pattern.
2. Delete the same number of the OLDEST whole days from `radar_bucket_sources`
   only, so the table keeps about 23 days and about 9.27 M rows, the target's
   shape. The other two tables hold only a day or two of history and lose
   nothing.
3. Keep every primary key unique, read each table's key from
   `information_schema` before writing, and touch no other table.
4. Print the row counts before and after, the new data span per table, the
   rows inside the 24h and 12h windows at the current clock, and re-run the
   preflight (index set, buffer pool).

**Limits stated beside every Task 8 number.** The fixture has no
`radar_posts`, so tone and the `lean` sort do no real work at scale; any `lean`
timing is a lower bound. The fixture has one `app_user`; the watch-profile
accounts are created by the scripts and deleted afterwards. The source names
are the fixture's placeholders (`reddit:sub00`..`sub32`), spelled as its own
DISTINCT list, as `perf2-spike/selections.py` explains.

- [ ] **Step 1: `measure_perf3.py`**, n = 20 each, reported separately as
      median / p95 / max:
      (a) ready read through `read_payload` with an account watching three
      tickers, 12h and 24h;
      (b) empty store: `TRUNCATE` both tables → first request answers
      `pending` in X ms (NOT a board) → time until the producer (a running
      subprocess of `run_radar_board_producer.py`) publishes → time until a
      reader sees the board; the three parts stated apart, the sum labelled
      "cold, UNMET ≤ 2 s goal";
      (c) restart: kill and restart the web-model process, first read
      afterwards is a ready read;
      (d) a cold on-demand selection (`sort=lean` 24h, then `limit=100`
      cold and repeated) with the producer running: queue wait and
      build-to-usable stated apart;
      (e) memory: working set of the producer and of each web-model
      process at rest and after 100 reads;
      (f) queue age: with the 8 warm keys refreshing at 120 s and one
      on-demand request every 10 s for 10 minutes, the worst warm age and
      the worst demand wait, sampled from the table every 5 s;
      (g) under representative write contention: repeat (f) while
      `perf1-bench/write_cost.py`'s bulk UPDATE runs three times (copy the
      statement into the script; the perf1 helper must not be pointed at
      this database) — report both the sweep and the write side.
- [ ] **Step 2: `two_workers_perf3.py`:** the T1 model (two OS processes,
      one thread each, real WSGI app, flag on) with a producer subprocess;
      drive two concurrent cold board requests and measure a cheap
      non-Radar request (`/gym/` or `/`) throughout — the number that says
      whether the shared path removes the 7.6 s block. Label it MODEL,
      not gunicorn, everywhere.
- [ ] **Step 3: `profile_watch_perf3.py`:** the per-account half on the
      scale database for accounts watching 0, 3, 10 and 25 tickers; if the
      25-mark case exceeds 150 ms median, implement the bounded strategy —
      a per-process memo of `build_pinned_rows` keyed on
      `(user_id, tuple(watching), key_hash, as_of)`, at most 64 entries —
      in `board_shared.py`, with a test, and re-measure. Otherwise record
      that the strategy was not needed and why.
- [ ] **Step 4: `browser_perf3.py`** (python-playwright, headless chromium,
      a session cookie minted with the app's own serializer as
      `perf2-spike/run_s8_browser.py` does): against `serve_perf3.py` with
      the producer running, on BOTH `/radar/` and `/radar/hub/`:
      - empty store → the page shows the pending copy, no rows, no "Nothing
        cleared", no timestamp; screenshot; then the board arrives; record
        time-to-rows and time-to-usable separately; screenshot;
      - rapid switching: six window/segment changes 200 ms apart; assert
        the final rows belong to the final selection (compare `window_hours`
        in the rendered context line and the rows' membership against
        `read_payload` for that selection) — no old-response overwrite;
      - hidden tab: `page.evaluate` to set `visibilityState` hidden (or use
        a second page and `page.bringToFront`) while pending; count
        `/api/board?…poll=1` requests over 10 s (expect 0); make it visible;
        expect an immediate poll;
      - stale → fresh: age a warm row to 300 s via SQL, reload, assert the
        age line and the refreshing marker, wait for the producer's refresh,
        assert the marker clears;
      - hard-expired: age a row to 700 s, reload, assert the pending state
        rather than the old board;
      - delayed: stop the producer, request a cold key, wait 31 s, assert
        the delayed copy and the Retry control; start the producer, assert
        recovery with no reload.
      Save every screenshot under `radar-design/perf3-shots/` and list them
      in the ledger.
- [ ] **Step 5: write the ledger section** "Production-scale verification"
      with every table, the preflight blocks, the scripts, and the
      statement of the unmet cold goal. Commit scripts, shots and ledger.

```bash
git add personal_apps/scratchpad/perf3 radar-design/PERF3-LEDGER.md radar-design/perf3-shots
git commit -m "perf(radar): the shared path measured at production scale -- ready, empty-store, restart, cold, memory, queue age, contention"
```

---

### Task 9: suites, builds, and the release package

**Files:**
- Create: `radar-design/PERF3-RELEASE.md`
- Create: `radar-design/perf3-release/radar_board_producer.service` (proposed
  unit text, NOT installed)
- Create: `radar-design/perf3-release/BUILD_REVISION.md` (the two-line
  deploy addition)
- Modify: `radar-design/PERF3-LEDGER.md`, `radar-design/HANDOFF.md`

**Amendment, 2026-09-11 -- telemetry, as the ruling actually asks for it.**
The PERF2 access-log proposal is not carried unchanged. Codex's telemetry
ruling: "Path without query strings can still contain identifiers in dynamic
routes: use safe route labels/redaction where necessary rather than claiming
%(U)s guarantees no identifying data", and "Verify target Gunicorn version and
systemd ExecStart percent escaping before presenting a paste-ready unit
delta." Gunicorn's access-log atoms cannot print a route template, so a safe
label has to come from the application. Task 9 therefore adds the following,
prepared and OFF by default:

- `personal_apps/request_timing.py`, registered from `app.py`. When
  `PERSONAL_REQUEST_TIMING_LOG` is truthy (`1`, `true`, `yes`, `on`), it
  writes one INFO line per request on logger `app.request`: the method, the
  matched route TEMPLATE (`request.url_rule.rule`, for example
  `/radar/api/ticker/<ticker>`; `<unmatched>` for a request no rule matched;
  every static asset folded into one `<static>` label), the status, the
  response bytes when known, and elapsed milliseconds from a monotonic clock.
  It never writes the path's values, the query string, cookies, headers, the
  client address or any account identifier. When the variable is off, no hook
  is registered at all.
- Tests: off by default emits nothing and registers no hook; on, a request to
  `/radar/api/ticker/NVDA?window=24` logs the template and never `NVDA` or
  `window`; an unmatched path logs `<unmatched>`; a static asset logs
  `<static>`; the enabled hook's overhead is measured over 1,000 requests
  through the Flask test client and recorded in the ledger.
- It goes to stdout, so journald keeps it. The ledger's facts section records
  systemd v255's journald defaults; the release package states that the
  target's own journald settings are unread and must be checked
  (`journalctl --disk-usage`, `/etc/systemd/journald.conf` and its `.d`
  drop-ins) before relying on them.
- The gunicorn access log stays documented as the alternative only: every `%`
  doubled inside `ExecStart=`, the format quoted as one argument, the
  identifier caveat stated, and the gunicorn version marked unverified on the
  target (26.2.0 locally, where a sync worker with `threads > 1` becomes
  gthread).
- Rollback is unsetting the variable and restarting the web unit. Logs are
  left where they are; nothing deletes a log directory.

- [ ] **Step 1: the backend suites, whole**, on `personal_apps_radar_perf3`:
      `PYTHONPATH=. py -3.12 -m pytest tests -q -p no:cacheprovider
      2>&1 | tee ../radar-design/perf3-release/pytest-full.txt`. Classify
      EVERY failure individually in the ledger: caused by this branch / a
      known pre-existing failure with its prior citation
      (`test_radar_ingest.py`'s three, the synthetic-fixture data-shape
      ones from PERF2's ledger) / new-and-unexplained (investigate to a
      cause). Then `npm test` and `npm run build`, same treatment.
- [ ] **Step 2: `PERF3-RELEASE.md`**, one concrete delta with these
      sections: (1) migration `b7e3f9c1a2d4` — additive, rehearsed on
      MariaDB 10.11.14 (cite the ledger), run by `update_coc.sh`'s existing
      `flask db upgrade`, no writer stop needed for it (no existing table is
      altered) but `radar_ingest` is stopped by the script anyway; (2) the
      producer unit — full text, `User`/`WorkingDirectory`/`EnvironmentFile`
      marked "reconcile against `personal_apps_web.service`, which was never
      read", `ExecStart=… python run_radar_board_producer.py`,
      `Restart=always`, `RestartSec=10`, `TimeoutStopSec=150` (> lease
      120 s), `KillSignal=SIGTERM`; plus the `update_coc.sh` additions:
      `systemctl stop/start radar_board_producer` beside `radar_ingest`, and
      `git rev-parse HEAD > personal_apps/BUILD_REVISION` after the
      checkout; (3) flag sequencing — deploy with the flag OFF (behaviour
      unchanged), start the producer, run `python run_radar_board_producer.py
      --readiness` until it exits 0 (the prewarm gate), set
      `RADAR_BOARD_SHARED_RESULTS=on` in the web unit's environment, restart
      `personal_apps_web`; (4) telemetry — the `radar.board` log lines
      (journald, no file), what they contain and do not, the PERF2
      access-log proposal unchanged and still not activated; (5) rollback —
      flag off + restart web (complete rollback of behaviour; tables and
      producer may stay), then optionally stop/disable the producer; the
      migration downgrade is available but not required; nothing deletes
      logs; (6) resource measurements from Task 8 — producer memory, web
      memory, table size bound `(8 + 128) × 13 KB` per live namespace,
      retirement after 24 h; (7) what is NOT in this package — threads,
      index, capture, root promotion, B1; (8) open risks — MariaDB not
      measured for the build, gunicorn not run locally, the unmet 2 s cold
      goal, and the 5.6 s build read transaction on the producer.
- [ ] **Step 3: `HANDOFF.md`** — replace the CURRENT block at the top with
      PERF3's: worktree, branch, HEAD, dirty files, the two databases and
      their stamps, completed tasks, review findings and dispositions,
      exact test commands and results, protected files, what the release
      package proposes, and that nothing is deployed.
- [ ] **Step 4: commit.**

```bash
git add radar-design/PERF3-RELEASE.md radar-design/perf3-release radar-design/PERF3-LEDGER.md radar-design/HANDOFF.md
git commit -m "docs(radar): PERF3 return -- suites classified, the release delta, and the handoff"
```

---

## After Task 9

One independent whole-branch read-only review (most capable non-Fable
model) with `superpowers:requesting-code-review`'s template, its findings
resolved by ONE fix dispatch, re-reviewed, and the ledger's review section
written. Then the return to Codex: exact SHA, the ledger, the release
package, and the local preview command:

```
cd C:/Users/michi/Desktop/CodingStuff-worktrees/radar-perf3/personal_apps
set RADAR_BOARD_SHARED_RESULTS=on
PYTHONPATH=. py -3.12 run_radar_board_producer.py            # terminal 1
PYTHONPATH=. py -3.12 scratchpad/perf3/serve_perf3.py --port 5071   # terminal 2
```
