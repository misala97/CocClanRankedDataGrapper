# Codex rulings on Claude's return

Reviewed 2026-09-09. Source inspected in C:/Users/michi/Desktop/CodingStuff-worktrees/radar-foundations, branch codex/radar-foundations. Actual HEAD is b78b5d284f703c484581b01780ae8b16f63beb9a, newer than CODEX-RETURN.md's 1e30096. Git status reported no changes (with access warnings for ignore/cache paths). Later commits are handoff documentation. No application code, database or deployment was changed during this review; tests reported by Claude were read, not rerun by Codex.

## 1. counted_runs: approved

Keep it and adopt it into the activity contract. completed_runs counts successful runs; counted_runs counts compatible summaries contributing to the counters. Activity.tsx displays their difference. Removing the key to match the original enumeration would reduce accuracy. Null per-counter handling remains required; counted_runs does not prove all counters were present or all source activity was captured.

## 2. Filters.tsx: approved, with a focused correction

The file fulfills an existing requirement, not additional product scope. Separate ownership of filter controls is appropriate.

However, toggle() currently returns all other feeds when the last selected feed is unchecked. Example: sources=['reddit'] with all_sources=['bluesky','fourchan','reddit'] becomes ['bluesky','fourchan']. Its comment says the action is refused, but the implementation changes the selection to unrelated feeds. This needs correction before marking the returned implementation fully accepted.

Claude task R1: retain the current selection when removing its final selected root would leave none; optionally disable that final checked checkbox with an accessible explanation. Preserve concrete subreddit selections. Add a behavior test that begins with only Reddit, clicks its checkbox, and asserts Reddit remains selected and no request for unrelated feeds is issued. Also cover a concrete reddit:subreddit selection and normal removal when a second feed is selected. Run the focused Filters/hub tests, obtain read-only review, and record the fix commit in HUB-LEDGER.md. Do not repeat completed H1–H4 tasks.

## 3. Recorded limits

### Activity query: retain temporarily; measurement required before rollout

Keep portable Python aggregation for the local review. Do not approve its capacity using the quoted 2,880 runs/30 days estimate: that uses the observation archive's 15-minute cadence. Ingest is scheduled separately; config.py has CYCLE_SECONDS=180 and REDDIT_INTERVAL_SECONDS=120, with session/provider-dependent scheduling. The actual number and size of recorded runs must be measured from those writers, not inferred from capture frequency.

Claude task R2: correct the estimate in source comments and handoff/ledger. Prepare a repeatable disposable-DB benchmark using representative envelopes and actual configured ingest schedules. Record run count, total JSON bytes, DB query/aggregation time and endpoint response time for 1/7/30 days. Real-server measurement remains a rollout check; do not access production by inference. If the measured endpoint is slow, propose a portable typed-counter or daily-rollup design with existing schema/null semantics rather than introducing unverified JSON SQL expressions. This does not block visual review.

### capture(now): accepted as an internal injected-clock interface

The only production scheduler caller passes _utcnow(); accepting a time argument makes deterministic tests possible and is not itself a defect. No public backfill endpoint or user-supplied timestamp is authorized.

Correct the wording: observed_at is copied from the supplied now; the function does not independently enforce wall-clock truth. The guarantee holds through the reviewed scheduler call path. Preserve that call-path test, naive-UTC convention, actual payload generated_at and immutable slots. Any future backfill/import feature requires a distinct provenance contract.

## 4. Shared-code changes: approved for this scope

Keep 403 read/write distinction in api.ts: the new admin read can be forbidden while writes can fail at the existing CSRF gate. Do not generalize every future write403 to session if permission-controlled mutations are later added.

Keep resolve_asset_css and manifest memoization. The hub entry needs its emitted stylesheet and the helper preserves the separate feature asset directories. Existing recorded asset/Gym regression checks support this change. This approval is for the current entry graph, not a claim that every future dynamic-chunk CSS ordering scenario has been verified.

## Other finding and next handoff

Leave the independently reproduced pre-existing ingest-test cleanup defect in its separate task. It is not a reason to alter the product scope or rerun completed implementation tasks.

Next: Claude applies R1, corrects documentation and supplies R2 measurement evidence; owner can review the opt-in hub visually in parallel. No merge, deployment, root-route promotion or capture enablement is approved here. Codex has not yet performed a full independent implementation or visual audit.

This ruling file is currently in the planning checkout. Carry it into the implementation worktree and update its canonical ledgers/handoff before continuing; do not rely on chat memory.
