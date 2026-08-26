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
