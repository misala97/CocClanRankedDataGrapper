# Gym audit fixes (2026-09-23) — plan + ledger

Source: the inline workflow audit of 2026-09-23 (8 bugs driven in the real UI, plus
usability recommendations). Owner approved: "fix all the bugs and also implement all the
usability suggestions". Branch `dev_personal`; commit only files touched here (the tree
carries unrelated dirty work). No push to main without an explicit OK.

Visual reworks (first-run Start, shared-confirm layout) follow the standing
mockups-before-code rule: direction round first, code after the pick.

## Tasks

| id | what | status |
|----|------|--------|
| B1 | Finish waits for in-flight/queued writes before navigating | done |
| B2 | Confirm button locked while any set write is pending (last-set double tap) | done |
| B3 | Live-surface write to a finished session refused (409), island reloads; finish idempotent; no rest/push on a finished session; bfcache restore reloads | done |
| B4 | `_live_context` fallback skips skipped rows; all-skipped state has its own copy | done |
| B5 | Add/edit set inputs validated (client disables, server rejects reps < 1, weight < 0, non-finite); sheet add row prefilled + locked | done |
| B6 | Pain flag saves on toggle; exercise note saves on blur | done |
| B7 | Statistik longest break counts the open gap to today | done |
| B8 | Debrief correction sheet: delete a set, add a set (also to exercises with nothing logged) | done |
| U1 | Un-logging a chip has an undo window; an open chip binds the steppers instead of logging | done |
| U2 | "Jetzt machen" in the exercise sheet (moves it ahead of the live one) | done |
| U3 | Discard a workout with no logged set (finish sheet) | done |
| U4 | Accepting an invite discards your own set-less running workout instead of refusing | done |
| U5 | Shared confirm auto-picks the best-covering routine, not only a perfect one | done |
| U6 | Debrief pace per set instead of the inflated "davon N min Pause" | done |
| U7 | Start per-week figure names its 4-week window | done |
| U8 | "Slot" copy becomes "Position" | done |
| U9 | "Bereit" note names the next weight | done |
| U10 | QueryClient created once (useState) | done |
| V1 | First-run Start — mockup round, then build | done (lane C) |
| V2 | Shared-confirm: collapse exact matches — mockup round, then build | done (lane C) |

## Ledger

(append: date, task, commit, tests)

- 2026-09-23 — B1-B8, U1-U10 in one commit on `dev_personal` ("fix(gym): the audit round").
  Tests: gym pytest 668 passed; vitest 463 passed; `tsc --noEmit` clean; `npm run build` ok.
  Driven with python-playwright at 390x844 against the dev DB: slow-wifi double tap on a
  last set logs no phantom set; finish with a set in flight waits ("Speichert noch…") and
  the set lands; a stale second tab's tap after finish reloads into the debrief (409, no set,
  no push); open chip binds the steppers; done chip un-logs after a 5s undo; Jetzt machen
  makes the row live; empty workout discards to /gym; all-skipped panel + rail copy; pain
  autosaves; empty add row disabled; debrief delete (undo) and Nachtragen (completed_at
  NULL); Start "(letzte 4 Wochen)"; joining with an empty own workout discards it.
- Found while verifying, fixed in the same commit: the undo toast rendered outside the
  open modal sheet, so "Rückgängig" was inert behind it (live sheet set delete too) — it now
  portals into the open dialog. Debrief correction rows moved onto the `.sset` grid (the
  added delete button overflowed a 390px sheet). Disabled `.icon-btn` now looks disabled.
- Open: V1, V2 (mockup rounds). Not pushed to main.
- 2026-09-23 — V1 direction round rendered: `personal_apps/scratchpad/puls/firstrun/06_start_firstrun_{a,b,c,c2}.html`
  (real gym.css shell, 390x844, light + dark, no overflow, no target < 44px). Lanes: A one
  lifted card + prose; B card + the Start charts drawn as Offen outlines; C ordered 3-step
  checklist (erstes Workout / als Routine speichern / Pausen-Timer), c2 = after workout 1.
  Recommended C. Awaiting Michi's pick; no production code for V1 yet.
- 2026-09-23 — V1 built as lane C (Michi: "go with c"). Server: `HeutePayload.onboarding`
  ({workouts, last}) while the account has no routine and < 3 finished workouts with a logged
  set; `save_as_template` takes `next=start` (a fixed token, not a URL). Client: `FirstRun`
  checklist replaces the routines section; reading sections hidden until the first workout;
  push prompt folded into step 3; checklist steps aside while a workout runs.
  Tests: gym pytest 674 passed + 1 flake (test_gym_reorder_reseed seed-date `days_ago`,
  ran while the playwright script wrote to the dev DB near UTC midnight; 39/39 alone);
  vitest 471 passed; tsc clean; build ok. Driven at 390x844 as user 4: empty -> Workout
  starten (no sheet) -> running card, no checklist -> first exercise + set + finish ->
  "1 von 3", save form -> back on Start with the routine as the lead. User 4 restored empty.
- 2026-09-23 — V2 direction round rendered: `personal_apps/scratchpad/puls/shared_confirm/07_confirm_{a,b,c}_{exact,mixed}.html`
  (real confirm shell; baseline = the real island fed a payload built like gym_shared_confirm for
  user 3 following user 1's HBF Push, via route interception, no invite rows written). Lanes:
  A exact matches collapse into one "gefunden" row, unmatched ones ask in cyan cards; B every
  exercise a receipt row, unmatched rows expand with a select; C the invite is one lead card
  (Mitmachen at y=207 when all match), unmatched selects inside it. Recommended C. Awaiting
  the pick. A/C headers need the leader session's name + start time in SharedConfirmPayload.
- 2026-09-24 — V2 built as lane C (Michi: "go with c"). `SharedConfirmPayload` gains
  `session_name` + `started_at`. The page is one lead card: who/what/how long, the leader's
  exercise list, unmatched exercises asking in the attention hue, one Erledigt line for the
  rest + the routine it books under, Mitmachen. Matched selects and the routine picker sit in
  a folded "Zuordnung ändern" panel, still posting with the accept form via `form=`.
  Found while verifying: `.field.grow` in the panel's column flex took 9rem per field (dropped
  `grow`). Tests: vitest 476, tsc clean, gym pytest 674 + the reseed flake below, sharing 82/82.
  Driven with two throwaway users at 390x844 (+dark, 1280): Start invite -> card, Mitmachen at
  y=209 when all match; Ablehnen removes the invite; with two renamed exercises, mapping one
  and leaving one new joined a session with the mapping, one new exercise, booked under the
  follower's HBF Push. Users removed.
- 2026-09-24 — test_gym_reorder_reseed's two `days_ago == 5` asserts were flaky: MySQL 8
  rounds DATETIME fractional seconds UP (probe: .900000 read back as the next second), so a
  fast run measured 4 days 23:59:59. They now round to whole days (separate test commit).
