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
| V1 | First-run Start — mockup round, then build | open |
| V2 | Shared-confirm: collapse exact matches — mockup round, then build | open |

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
