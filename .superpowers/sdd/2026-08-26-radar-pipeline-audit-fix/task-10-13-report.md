# Tasks 10-13 ceremony batch report

## Scope and commits

- Worktree: `C:\Users\michi\Desktop\CodingStuff\.worktrees\radar-pipeline-audit`
- Branch: `codex/radar-pipeline-audit`
- Requested starting HEAD: `4264036`
- Task 10: `af11f2c` — `fix(radar): an unread feed reports no rate rather than a rate of zero`
- Task 11: `8a23a26` — `fix(radar): an unpriced model reads as unknown, not as free`
- Task 12: `e4de0b5` — `fix(radar): an outage mid-window is a gap in the chart, not quiet`
- Task 13: `d5997c9` — `fix(radar): account for breadth exclusions and extract once`

## Task 10 — failed reads are not measured zeroes

Changed `features/radar/sources/reddit.py`, `features/radar/ingest.py`,
`tests/test_radar_reddit.py`, and `tests/test_radar_ingest.py`.

- RED: the empty-feed assertion failed with `0.0 is None`; the raised-fetch
  assertion failed with `0 is None`.
- GREEN: `python -m pytest tests/test_radar_reddit.py tests/test_radar_ingest.py tests/test_radar_scheduling.py -v` — **66 passed**.
- Behavior: empty parsed feeds return `([], 'ok', None)`; malformed feeds
  continue through the existing unavailable path with a `None` rate; an
  exception from `run_cycle` records `catchup_depth[source] is None`.
- The Task 9 empty `per_source_status={}` not-due path was not modified.

## Task 11 — unknown model prices remain unknown

Changed `features/radar/spend.py`, `static/radar/src/types.ts`,
`static/radar/src/list/Spend.tsx`, `static/radar/src/list/Spend.test.tsx`,
`tests/test_radar_spend.py`, and `tests/test_radar_api.py`.

- RED backend: `python -m pytest tests/test_radar_spend.py -v -k "unpriced_model or surfaces_what"` — expected failures: `cost_micros(...)` returned `0`, and summary lacked `unpriced_tokens`.
- RED frontend: the new Spend test failed because a payload with only unknown-rate tokens rendered nothing.
- GREEN backend/API: `python -m pytest tests/test_radar_spend.py tests/test_radar_api.py -v -k "not page_embeds and not page_falls"` — **43 passed, 2 deselected**.
- GREEN frontend: `npx tsc --noEmit` succeeded; `npm test` — **403 + 81 passed**; `npm run build` succeeded for both Vite builds.
- Behavior: `cost_micros` returns `None` for an absent rate; `record` keeps
  token/call facts but does not add invented cost; `summary` exposes an integer
  `unpriced_tokens`; the API already forwards `spend.summary()` as a whole and
  the type/UI surface the caveat using existing `.below` secondary text.

## Task 12 — interior intraday gaps remain unknown

Changed `features/radar/detail.py` and `tests/test_radar_detail.py`.

- RED: `python -m pytest tests/test_radar_detail.py::test_an_outage_in_the_middle_of_the_window_is_not_drawn_as_quiet -v` — expected interior slots were zero rather than `None`.
- GREEN: `python -m pytest tests/test_radar_detail.py tests/test_radar_api.py -v` — **67 passed**.
- Behavior: `watched_slots` identifies only `ok`/`truncated` coverage per
  chart slot. Measured quiet stays `0`; uncovered interior slots are `None`;
  `watched_from` remains the earliest covered slot.

## Task 13 — breadth accounting, named floor, once-only extraction

Changed `features/radar/board.py`, `features/radar/leaderboard.py`,
`features/radar/ingest.py`, `tests/test_radar_board.py`, and
`tests/test_radar_ingest.py`.

- RED: the breadth report omitted `one_venue`; the monkeypatched named-floor
  regression produced `18.0` instead of `4.5`; duplicate identity extraction
  called the boundary twice.
- GREEN: focused three-test gate — **3 passed**; covering
  `python -m pytest tests/test_radar_board.py tests/test_radar_ingest.py -v`
  — **51 passed**.
- Required mutation tooth: restored
  `extracted.setdefault(raw.external_id, _extract_for(raw, lookup))`; the
  duplicate-ID call-count test failed with two `dup-extract` calls; restored
  the explicit-membership branch and re-ran the covering gate green.
- Behavior: min-venue exclusions add to `ranking.excluded['one_venue']`;
  leaderboard imports and uses `VARIANCE_FLOOR`; extraction is cached once per
  external ID and the fresh-ID set is computed once. The regression preserves
  one stored post, one rollup mention, and the later duplicate's engagement
  refresh.

## Batch verification

- `flask db current` before edits: `08316d3e4d77 (head)`; no migration
  downgrade was run.
- `git diff --check 4264036..HEAD`: clean.
- Broad gate, run independently to retain complete output:
  `python -m pytest tests/ -k radar -q` — **633 passed, 646 deselected,
  2 pre-existing deprecation warnings**. No Vite-manifest failures occurred
  because the required Task 11 frontend build had generated the ignored
  manifests.
- No deliberate mutation remains.

## Cleanup ownership

- Task 11 changed spend cleanup from a broad day-range delete to an exact
  `(day, model)` identity tuple list.
- Task 12 uses exact ticker `DTGAP12` cleanup.
- Task 13 uses exact ticker `BDT13` cleanup; its ingest regression uses the
  pre-existing exact `TEST_CHANNEL`, `TEST_TICKER`, source and cursor cleanup.
- No new broad `LIKE 'ZZ%'`, all-table, or cursor-wide deletion was added.

## Deviations and concerns

- The implementation worker was itself the single subagent required by the
  ceremony and did not spawn nested subagents. It performed the four tasks
  sequentially with per-task TDD red/green evidence.
- Task 11's first combined backend command included the two known page tests
  before frontend assets existed; they failed only for the known missing Vite
  manifest. The focused gate was immediately rerun with those page tests
  excluded and passed; the later build and broad gate had no manifest failures.
- `routes/api.py` needed no production edit: `serialize` already forwards the
  complete `spend.summary()` mapping. A new API-boundary regression proves
  `unpriced_tokens` reaches the payload.
- Preserved unrelated tracked modifications remain in
  `task-18-brief.md` and `task-19-brief.md`; they were neither staged nor
  altered by this batch. The existing pre-Task-13 broad `LIKE 'ZZ%'` cleanup
  debt in other tests remains a deferred final-review concern.
