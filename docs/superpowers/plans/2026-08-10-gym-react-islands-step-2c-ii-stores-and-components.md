# Gym React Islands — Step 2c-ii: Stores and Components

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the client-state stores and the component tree for the live workout screen, rendering from the session payload. Nothing is mounted; `session_detail.html` is untouched. 2c-iii mounts it and adds optimistic writes.

**Architecture:** Zustand holds the eleven pieces of state the server cannot know, in one store per concern. Components render from `SessionDetailPayload` and are pure with respect to it. Every component is unit-tested against a fixture built from the real endpoint.

**Tech Stack:** React 19, Zustand, TypeScript, Vitest, @testing-library/react.

**Spec:** `docs/superpowers/specs/2026-08-08-gym-react-islands-design.md`
**Precedent:** step 1's plan — same component/test shape, five times the surface.
**Depends on:** 2b (`758d072`) for the payload, 2c-i (`9594f0f`) for JSON mutations.

## Global Constraints

- **Nothing mounts.** No entry file, no change to `session_detail.html` or `vite.config.ts`. The page keeps working exactly as it does. 2c-iii is the swap.
- **No intentional visual change**, same rule as step 1: components emit the class names `gym.css` already styles. Deliberately *not* a pixel gate — the page has live clocks.
- **All copy is German, carried verbatim.** Comma decimals, `·` separators, `—` em-dashes.
- **The payload's int-keyed dicts arrive as string keys.** `suggestions['10']`, not `suggestions[10]`. Pinned server-side by `test_int_keyed_dicts_serialize_as_string_keys`; the TS types must say `Record<string, …>`.
- **Client state never derives from the payload.** That is the entire point of the port: the eleven pieces below have no representation on the server and must survive any refetch. A component that reads reorder-mode from the DOM has reintroduced the bug.
- **Text runs that interpolate values go in one template literal.** Step 1 measured this: React emits a text node per JSX expression and the browser rounds glyph advances per run, changing antialiasing. Nothing moves, but the raster differs.
- **Branch:** `dev_personal`.

## The eleven pieces of client state

Every one is destroyed by `refreshBody` today, and every one gets a home here:

| # | State | Store |
|---|---|---|
| 1 | Reorder mode unlocked | `useWorkoutUi` |
| 2 | This device is push-subscribed | `usePush` |
| 3 | Which sheet is open | `useSheets` |
| 4 | Which pane inside that sheet | `useSheets` |
| 5 | Add-list search query | `useSheets` |
| 6 | Number-entry overlay mid-edit | local component state |
| 7 | In-flight save count | `useSaveState` |
| 8 | Which forms are locked | `useSaveState` |
| 9 | Scroll position | *deleted* — nothing swaps the DOM any more |
| 10 | Rest countdown tick | `useRestTick` hook, from `rest_ends_at` |
| 11 | Save-error banner + retry | `useSaveState` |

Piece 9 disappears rather than moving. `refreshBody` replaced `#session-body` wholesale and scroll had to be saved and restored around it; React reconciles in place, so there is nothing to restore.

## File structure

```
static/gym/src/
  session/
    types.ts            mirror of schemas.SessionDetailPayload
    stores.ts           useWorkoutUi, useSheets, useSaveState, usePush
    useRestTick.ts      countdown derived from rest_ends_at
    components/
      SessionHeader.tsx    back, name, deload badge, clock, options
      SaveErrorBanner.tsx  the one visible answer to "did that save?"
      ReorderBar.tsx       the mode banner
      Stepper.tsx          field-num: hidden input + text readout + type-to-edit
      SetRow.tsx           one set: chips, weight x reps, done state
      LivePanel.tsx        the lifted panel for the exercise you are on
      QueueRow.tsx         one row of the queue
      Queue.tsx            the queue
      TickStrip.tsx        one tick per set in the workout
      sheets/              SessionSheet, DeloadSheet, AddExerciseSheet,
                           TemplateSheet, ExerciseSheet
    SessionPage.tsx     composes the above
  session/__fixtures__/session-payload.json   captured from the real endpoint
```

---

### Task 1: The payload types and a real fixture

Types first, and a fixture captured from the running endpoint rather than hand-written — step 1's hand-written fixture was wrong in five places.

**Files:**
- Create: `personal_apps/static/gym/src/session/types.ts`
- Create: `personal_apps/static/gym/src/session/__fixtures__/session-payload.json`
- Create: `personal_apps/scripts/make_session_fixture.py`

**Interfaces:**
- Produces: `SessionDetailPayload` and its nested types, imported by every later task. The fixture is the input every component test renders from.

- [ ] **Step 1: Write the fixture generator**

`personal_apps/scripts/make_session_fixture.py` — builds a session with two exercises (one with completed sets, one skipped), hits `/gym/session/<id>/detail.json`, writes the response, and deletes the session. Model it on `scripts/make_chart_fixture.py`, which already does this shape for the chart.

Two exercises, not one: a single-exercise session cannot exercise the queue, the live/not-live distinction, or the tick strip's per-exercise grouping.

- [ ] **Step 2: Generate it and read it**

```bash
cd personal_apps && python scripts/make_session_fixture.py
```

Then actually read the JSON. It is the contract; every type in Step 3 comes from it, not from the schema file's field names.

- [ ] **Step 3: Write `types.ts`**

Mirror `features/gym/schemas.py`'s session models exactly. The four that will be got wrong if written from memory:

```ts
/** Keyed by SessionExercise.id, but JSON object keys are always strings --
 *  the client reads '10', never 10. Pinned server-side by
 *  test_int_keyed_dicts_serialize_as_string_keys. */
suggestions: Record<string, Suggestion | null>
stagnation_counts: Record<string, number>
/** A set on the server, a list on the wire. */
record_set_ids: number[]
/** Null, or a verdict. Never an empty object. */
ready_for_more: ReadyForMore | null
```

`pain` is `boolean`, not `string` — that one already cost a debugging round in 2b.

- [ ] **Step 4: Type-check and commit**

```bash
cd personal_apps && npx tsc --noEmit
```

```bash
git add personal_apps/static/gym/src/session personal_apps/scripts/make_session_fixture.py
git commit -m "feat(gym): type the session payload and capture a real fixture"
```

---

### Task 2: The stores

Self-contained, no React rendering. Where the bug class actually dies.

**Files:**
- Create: `personal_apps/static/gym/src/session/stores.ts`
- Create: `personal_apps/static/gym/src/session/stores.test.ts`
- Modify: `personal_apps/package.json` (add `zustand`)

**Interfaces:**
- Produces: `useWorkoutUi`, `useSheets`, `useSaveState`, `usePush`. Every component reads these; 2c-iii's mutation layer writes `useSaveState`.

- [ ] **Step 1: Install Zustand**

```bash
cd personal_apps && npm install zustand
```

- [ ] **Step 2: Write the failing tests**

Test the stores as plain objects via `getState()`/`setState()` — no rendering needed. Cover, at minimum:

- `useSheets`: opening a sheet closes any other (the old code did `current.close()` before `showModal()`, because a sheet on a sheet is not a state this design has); the pane resets when a sheet reopens; the add-list query survives a sheet close and reopen **only if that is the intended behaviour — check the old `filterAddList` first and match it**.
- `useWorkoutUi`: reorder toggles; toggling it off does not clear anything else.
- `useSaveState`: `begin()`/`end()` are counted, not boolean — two concurrent saves need two `end()`s before the sweep clears. The old code used `pendingSaves` as an integer for exactly this reason.
- `useSaveState`: an error records its retry callback and `dismiss()` clears it.
- `usePush`: `subscribed` is tri-state — `null` while the one-time probe is in flight, then `true`/`false`. The old code cached the probe and never re-asked; the store must allow the same.

- [ ] **Step 3: Write the stores, run, commit**

Each store is a `create()` with explicit actions. No store may read from the payload — enforce it by not importing `types.ts` here at all, which makes the constraint structural rather than a comment.

---

### Task 3: `useRestTick`

The countdown, derived from the server's `rest_ends_at` rather than owned by the client.

**Files:**
- Create: `personal_apps/static/gym/src/session/useRestTick.ts`
- Create: `personal_apps/static/gym/src/session/useRestTick.test.ts`

- [ ] **Step 1: Read the original first**

`startRestTick` in the pre-port `session_detail.html` is keyed on the rest's own end time and re-runs after every refresh. Read it before writing — its comment explains why it is keyed that way, and the reason survives the port.

- [ ] **Step 2: Test with fake timers**

`vi.useFakeTimers()`. Cover: counts down; fires its "rest over" effect once and only once; a new `rest_ends_at` restarts it; unmounting clears the timer. The once-and-only-once case is the one that matters — the original tracked it explicitly.

---

### Task 4–8: The components

One task per group, each ending green and committed. In this order, smallest blast radius first:

4. **`SessionHeader`, `SaveErrorBanner`, `ReorderBar`** — presentational, no payload logic beyond the deload badge.
5. **`Stepper`, `SetRow`** — the stepper carries the two subtleties worth preserving: the value lives in a hidden input so no keyboard opens mid-workout, and `toFixed` is display-only because rounding the stored number turns a 1.25 kg step into 1.3 after a few taps. Type-to-edit needs the `settled` flag from the original — a reentrant blur fires during `replaceWith` and would clobber an Escape.
6. **`TickStrip`, `QueueRow`, `Queue`** — one tick per set across the whole workout, skipped exercises omitted.
7. **The five sheets** — all native `<dialog>`, all reading `useSheets`. `jsdom` has no `showModal`; `test-setup.ts` already stands one in.
8. **`SessionPage`** — composition only. Its test renders the whole fixture and asserts the page's shape, not each child's details.

Each task: write the failing test, write the component, `npm test`, `npx tsc --noEmit`, commit.

---

## Verification checklist

- [ ] `npm test` green, `npx tsc --noEmit` clean
- [ ] `python -m pytest tests/ -q` still 566 — no Python touched
- [ ] No file under `src/session/` imports `session_detail.html` behaviour or reads the DOM for state
- [ ] `stores.ts` does not import `types.ts`
- [ ] The fixture was generated, not hand-written

## What this deliberately does not do

- **No mounting, no entry, no template change.** 2c-iii.
- **No mutations.** Components take callbacks; 2c-iii supplies them.
- **No polling.** The follower's `sync.json` poll is wired in 2c-iii.
