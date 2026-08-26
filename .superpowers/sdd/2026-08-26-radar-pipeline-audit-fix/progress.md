# SDD ledger - plan: docs/superpowers/plans/2026-08-26-radar-pipeline-audit-fix.md

Spec: docs/superpowers/specs/2026-08-26-radar-pipeline-audit-design.md
Original branch: dev_personal
Continuation branch/worktree: codex/radar-pipeline-audit
Original base commit: 1470424
Continuation base commit: ee44f0d

Task order at continuation: 3b review, 3c, 4, 5, 6, 7, 9, 8, 10, 11,
12, 13, 14, 15, 16, 17, 18, 19.

Task 1: complete (commit 4f4cdf9, review clean) - mention journal table and
  48-hour retention constant; migration c489b7c94875.

Task 2: complete (commits fb622c8 + b9aeb0a, review clean) - roll_up rebuilds
  from the journal; promotion sees the whole quarter-hour. Mutation tests pin
  failed-source exclusion and frozen extractor confidence.
  Deploy carry: the journal is empty at deploy; a partial deployment bucket
  must not be rebuilt as if the journal covered its whole window.

Task 3: complete (commits 86175de + 4575fe0, review clean) - rows leaving
  status ok lose expected, variance, mention_z, and baseline_days. Task 6 must
  clear the 399 historical stale-score rows.

Task 3b: implementation commit ee44f0d; independent review was interrupted
  before a verdict. Continuation starts by completing that review.

Task 3b: review NOT APPROVED - Important: promoted=True is sticky although
  promotion is revocable. One voucher plus four lows promotes; adding a fifth
  low exceeds MAX_BARE_PER_VOUCHER and must revoke the entire group. The brief
  itself mandated the one-way write, so this is a plan defect rather than an
  implementer deviation. Fix round 1/5 pending.

Task 3b fix round 1: implemented in commit f3413b4. `mark_promoted` now
  replaces every recomputed low/medium verdict; the cap-plus-one regression
  proves prior promotions, voice count and bucket count are revoked together.
  Focused test 1/1 and covering tests 66/66 passed. Full radar gate reached
  585 passed and two unrelated template failures caused by the absent ignored
  Vite manifest; local npm build is unavailable because `tsc` is not installed.
  Independent re-review APPROVED: no Critical or Important findings. Minor
  self-referential report SHA wording corrected in the following docs commit.
  Task 3b complete.

Ruling: Task 3b promotion persistence replaces every recomputed bare verdict,
  writing False for current lows and True for current mediums - the journal
  must reflect the same latest full-bucket decision that mention_count uses.
  Cost if wrong is extra UPDATE work per touched bucket; leaving it sticky can
  pass the eligibility floor on voices that are no longer scored.

Ruling: isolate continuation in codex/radar-pipeline-audit - the original
  checkout contains unrelated Telegram changes; cost if wrong is one merge
  step back to dev_personal, while working in place risks staging user work.

Ruling: add Task 3c before further extraction/source changes - corrected
  rollups are a new baseline generation even though extraction membership is
  unchanged. The current scorer also derives from the current version and
  writes onto older-version rows. Cost if wrong is an unnecessary warm-up;
  omitting it mixes known-understated history with corrected counts and defeats
  source_config_version's compatibility boundary.

Ruling: run Task 9 before Task 8 - Reddit's aggregate status is already known
  to be the wrong population. Score truncated rows only after each subreddit
  owns its status. Cost if wrong is sequencing only; the final schema and
  behavior are unchanged.

Ruling: replace Task 5's universal raw-source reachability test with targeted
  behavioral guards - the draft counted comments, docstrings and unused
  imports as call sites, so it could pass the exact dead-hook defect it claimed
  to prevent. PAGE_CAP gets a direct deletion regression; bot filtering,
  single-letter extraction, profile scheduling and sentiment scheduling keep
  their runtime tests. Cost if wrong is that a different future dead constant
  needs another targeted test; the rejected generic test offered false rather
  than broad protection.

Task 3c: architecture review NOT APPROVED - Critical: `roll_up` could stamp a
  corrected generation onto an existing row while preserving its old score,
  and scorer-only invalidation occurred after the daemon's immediate ingest
  path. Important: SQL NULL, startup ordering and bootstrap-evidence failure
  were not pinned strongly enough.

Ruling: Task 3c clears score fields both at startup and on the exact bucket row
  whenever its generation changes; profile version is required; scorer cleanup
  is limited to the active lookback; tests cover explicit old hashes and real
  SQL NULL. Startup aborts before fetchers/scheduler when retained legacy
  evidence exists but bootstrap recovers zero rows. Cost if wrong is a startup
  abort on a genuinely inconsistent migrated database; continuing would make
  missing evidence indistinguishable from zero and serve relabelled scores.

Task 3c: implementation commit 7791963. Covering suite 137/137 passed; broad
  radar gate 595 passed with the two known missing-Vite-manifest failures.
  Independent Claude review found production behavior compliant but review NOT
  APPROVED because eight test/efficiency findings remain. Fix round 1/5 is in
  progress from `task-3c-fix-round-1.md`.

Task 3c review findings: runtime fail-closed `main()` test can be fooled by
  swallowing prepare errors; mixed-generation row scoring is unpinned; four
  global-window tests collide with current dev seed data; startup commit,
  current-version argument, `high_confidence_count > 0`, and score-presence
  update guard are unpinned; scorer invalidation repeats an unscoped 30-day
  scan per source.

Ruling: fix all eight in one scoped round. Add an optional source argument to
  defensive score invalidation while leaving startup all-source; move only the
  Task 3c global-window fixtures to 2027-06-01. Cost if wrong is a slightly
  wider public helper signature and future-dated test data; leaving the gaps
  allows silent fail-open startup, phantom cross-generation spikes, flaky
  counts, or repeated range locks.

Ruling: Task 6 now includes automated dry-run/apply/idempotence/Decimal and
  stale-score tests plus a `ticker_prefix` test-only scope. Repair decisions
  compare every recoverable lower-bound field rather than assuming equal high
  count means an equal aggregate; stale cleanup detects any non-NULL score
  field. Cost if wrong is a slightly larger one-shot script API and one extra
  test file; the old draft could mutate the shared dev corpus during tests,
  skip refreshed secondary aggregates, or ship a production backfill proven
  only by printing `examined 0`.
  The draft's unused `_BUCKET` SQL constant is deleted from the plan rather
  than shipping another defined-but-uncalled promise in the audit that is
  explicitly removing those.

Task 3c: fix round 1/5 (8 original findings addressed, 1 new Important open;
  commit c553c47). New issue: `test_radar_scoring.rows` broadened teardown to
  every `ZZ%` ticker in the shared dev DB, so one suite can erase another
  test's or user's namespaced evidence. Fix round 2/5 pending: exact owned
  ticker set plus sentinel mutation regression.

Task 3c: fix round 2/5 NOT ADDRESSED (commit 4850c9a; 2 Important open).
  Exact cleanup still claims `SSNOPE`, which this file only queries and never
  creates, and the sentinel regression pre-deletes every existing
  `ZZSENTINEL` row. Fix round 3/5 must remove the query-only ticker and use a
  per-run unique <=12-character sentinel with no pre-delete, cleaning only its
  exact identity in `finally`.

Task 3c: fix round 3/5 (2 addressed, 0 open; commit fa66e70). Scoped
  re-review APPROVED: exact ownership excludes query-only `SSNOPE`; the
  collision-safe 12-character sentinel is never pre-deleted and cleans only
  its own identity.

Task 3c: complete (commits 7791963..fa66e70, review clean). Final Task 3c
  covering gate: 141 passed. Latest broad gate: 598 passed with only the two
  established missing-Vite-manifest API template failures.

Task 4: complete (commit c6ff071, spec review approved; no Critical/Important).
  `single_letter_cashtags_allowed` is now a live extraction argument and the
  Bluesky-vs-finance behavior has red/mutation evidence.

Task 5: complete (commit c6ff071, spec review approved; no Critical/Important).
  Superseded `PAGE_CAP` and its dead comment are deleted; targeted deletion,
  bot-filter, profile-job and sentiment-job guards pass.

Task 4+5 minor (deferred to final review): `_extract_for` says there are four
  per-source judgements but its prose enumerates only three, omitting the
  single-letter-cashtag judgement.

Codex-to-Claude stop checkpoint (2026-08-26): Michi requested an immediate
  stop near the Codex session limit. Task 6 implementer Socrates was
  interrupted and shut down before producing any code, tests, report or
  commit; Task 6 remains not started. HEAD before the handoff-only commit is
  ee24d65. No active worker remains. Claude must begin with the hardened
  `task-6-brief.md`, preserve the completed/reviewed Tasks 1-5, and follow the
  remaining order 6, 7, 9, 8, 10-13, 14-17, 18-19, final review. The prepared
  ignored `task-7-brief.md` is included in the handoff checkpoint for later use.

Task 6: complete (commits d11ccb5..8b0a07d, review clean). One-shot backfill
  script plus its test file. Independent review APPROVED the implementation
  with one Important and two Minor findings; fix round 1 closed the Important
  and one Minor, and the scoped re-review returned zero findings at every
  severity. Focused gate 4/4 then 5/5; broad radar gate 605 passed with only
  the two established missing-Vite-manifest API template failures. The real
  dry-run path runs clean and reports 210 bucket rows examined, 165
  understated, against local dev data - so this is measured behaviour, not a
  script proven only by printing `examined 0`.

Task 6 deviation (accepted): equality of `distinct_text_ratio` and
  `engagement_weighted_count` uses `math.isclose`, not `==`. MySQL FLOAT is
  single-precision and round-trips lossily, which broke the brief's literal
  idempotency guarantee; reproduced independently by the reviewer.

Task 6 fix round 1: the stale-score query's `ticker_prefix` scoping passed
  only because this dev database currently holds zero real rows matching
  `status != 'ok' AND any-score-column-not-null` outside `ZZBF` - which is
  precisely the population the production run exists to clear, so the luck was
  temporary. A data-independent sentinel-prefix assertion now pins it, teeth
  confirmed under deletion of the filter. Separately, `_TRUTH`'s computed
  `bs` came back a Python `str` and the ORM lookup relied on implicit
  string-to-datetime coercion; production is MariaDB, so it is now parsed
  explicitly to a naive UTC datetime, guarded for drivers already returning
  one. Dry-run numbers unchanged across the type change.

Task 6 minor (deferred to final review): the `int()`-at-the-boundary comment
  claims COUNT returns Decimal, which is empirically true only of SUM on this
  driver. Left as-is because the same phrasing is an existing house
  convention (features/radar/journal.py:204); it misleads a reader but
  changes no behaviour.

Task 7: IMPLEMENTED, NOT REVIEWED (commit 945c9d7). StockTwits retired:
  module and its 11-test suite deleted, config/daemon/scheduler stripped, six
  test suites moved off the source name, and the UI source label removed from
  static/radar/src/format.ts with BoardPage.test.tsx updated to match.
  `source_config_version()` moved fc1a0ee4cab51d65 -> 8106787f1fa72179 with no
  manual edit, which is the intended bump and a deploy-time baseline warm-up.
  Broad gate 594 passed, 2 skipped, plus only the two established
  missing-Vite-manifest failures. Review package already generated at
  .superpowers/sdd/review-73981db..945c9d7.diff - do not regenerate it.

Task 7 review must go to the most capable model, not Sonnet. Michi's standing
  ruling is Sonnet for every review EXCEPT StockTwits and Reddit; Task 7 is
  StockTwits, and Tasks 9 and 8 are Reddit.

Task 7 scope expansions the review must check, none independently verified:
  three daemon tests DELETED rather than renamed because they called the
  now-deleted `_stocktwits_fetcher` and `SYMBOL_BUDGET_PER_CYCLE` - the claim
  that the missing-vs-ok distinction stays covered at run_cycle level needs a
  mutation, not a reading; three pre-existing config/ingest tests rewritten as
  monkeypatch extension-point tests because no surviving source sets
  BARE_TOKENS_ALLOWED, COIN_SYMBOLS_MEAN_STOCKS or SINGLE_LETTER_CASHTAGS
  True; about twelve prose restatements separating present-tense claims from
  historical measurements. `models.py:660` and the migration files were
  deliberately left - genuine historical column names, correct call.

Ruling: the standing "tsc is not installed, npm run build cannot run" note is
  now DISPROVED. A real npm install gives a clean tsc type-check and vitest
  78/78 including BoardPage.test.tsx. Tasks 11, 15 and 16 were planned around
  that command being unavailable and must be replanned with the runner
  available. Cost if wrong is one npm install; leaving the note stands three
  frontend tasks down on verification they can actually run.

Task 7 review: NEEDS FIXES (0 Critical, 2 Important, 1 Minor; teeth 4/6).
  Production retirement, source list, config-version bump, frontend removal,
  historical references and prose distinctions are compliant. Open Important
  findings: no surviving regression proves an empty healthy fetch remains
  `ok`; the ingest coin-symbol opt-in test calls config directly and does not
  pin ingest's consumer. Fix round 1/5 pending from
  `task-7-fix-round-1.md`.

Task 7 minor (deferred to final review): `test_stocktwits_is_retired` omits
  direct key absence from `COIN_SYMBOLS_MEAN_STOCKS`; adding a false-valued
  StockTwits key survives because `not any(values)` checks values, not keys.

Ruling: harden Task 9 before dispatch — the extracted draft would write a
  zero-valued aggregate `reddit` child beside concrete subreddit rows because
  `statuses` doubled as fetch summary and rollup population; it would discard
  successful earlier subreddits when a later sub made aggregate status
  `missing`; and daemon scoring would continue calling only the root name,
  matching no new rows. Concrete per-sub statuses alone feed rollup, partial
  successes survive, and one shared expansion drives API queries and scoring.
  Cost if wrong is a wider ingest/API change and more regression tests; leaving
  it makes the source split either pollute storage or produce unscored Reddit.

Ruling: Task 9 widens `RadarPost.source` as well as the two planned columns and
  chains its migration from current head `1d26ac48e744` — the post column is
  String(16), shorter than `reddit:wallstreetbets`, and Task 3b already added a
  migration after Task 1. Cost if wrong is one extra online table alter and a
  more explicit downgrade; leaving it makes the first mentioning Reddit post
  fail and/or forks Alembic history.

Ruling: Task 9 adds a dedicated source-name population generation to
  `source_config_version()` — Task 7 already left `SOURCES` at the same three
  roots and Task 9 leaves `REDDIT_SUBS` membership unchanged, so the promised
  bump otherwise does not happen. Cost if wrong is an unnecessary baseline
  warm-up; omitting it mixes aggregate-Reddit and per-subreddit populations.

Task 7: fix round 1/5 (2 addressed, 0 open; commit 3b74f32). Added a
  behavioral empty-healthy `run_cycle` regression and moved the coin-symbol
  opt-in assertion through `ingest._extract_for`; both targeted production
  mutations failed as required, then were restored. The same commit narrowed
  the ingest fixture's shared-DB cleanup from broad `ZZ%`/all-cursor deletion
  to exact owned rows and source keys. Covering gate: 59 passed.

Task 7: complete (commits 945c9d7..3b74f32, review clean). High-capability
  scoped re-review APPROVED both Important findings with no new findings at
  any severity. The one original Minor remains deferred to final review.
