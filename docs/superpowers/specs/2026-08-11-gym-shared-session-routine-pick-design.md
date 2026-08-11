# Shared session: log it under your own routine

## The problem

`gym_shared_accept` creates the follower's session with `template_id = None`,
deliberately: the routine the workout came from belongs to the *leader's*
catalogue, and claiming it would tell `routine_memory()` that this lifter had
performed a routine they have never owned.

That reasoning is sound and its consequence is a defect. `routine_memory()`
skips every session with no `template_id` (`stats.py`), so a shared workout is
invisible to the follower's own routine bookkeeping. Two people who always
train Push together see two different truths: the leader's "HBF Push" reports
the session, the follower's own Push routine still reads *"Noch nie gemacht"*
or drifts to *"vor 3 Wochen"*. Everything hanging off `template_id` inherits
the gap — the "Am längsten her" ordering on Heute, the deload suggestion, and
the debrief's "Vorlage aktualisieren" prompt, which never appears for a
follower at all.

The follower owns a routine that fits. They are simply never asked.

## What we are building

On the invite-confirmation page — where the follower already matches the
leader's exercises against their own catalogue — one more field: **which of
your own routines this counts as.**

The same workout is then booked under the leader's routine A on their side and
the follower's routine B on theirs. Two catalogues, two routines, one workout,
each side's own bookkeeping intact.

## Decisions

| Decision | Choice |
|---|---|
| Which routines are offered | Every routine sharing at least one exercise, ranked by coverage, each labelled with it |
| What picking one does | Sets `template_id` on the follower's session. Nothing else |
| Perfect match | Preselected when exactly one routine contains every exercise; never when two do |
| Where the list is computed | Client-side, from the currently selected matches |
| Rest times, order, exercises | Untouched — structure belongs to the leader |

### Why coverage-ranked rather than a strict gate

"Contains all the exercises" was the original phrasing and is the right
*default*, not the right *filter*. A single deviation by the leader — one
exercise added before the invite is accepted — makes a strict rule offer
nothing at all, with no way for the follower to see why the field vanished.
Ranked coverage keeps the perfect match on top, states the imperfect ones
honestly (`6 von 7 Übungen`), and leaves the judgement where it belongs.

### Why `template_id` and nothing else

The routine also stores a rest time per exercise, and adopting those would be
defensible ("rest follows the person"). It is still rejected: one visible
choice must have one visible effect, and a picker that silently rewrites the
rest timers is a second effect nobody asked for. Rest stays per-exercise and
adjustable inside the workout, as it already is.

Adopting the routine's *order* is rejected outright — it contradicts the rule
that structure comes from the leader, and `reconcile_follower` would revert it
on the leader's next structural change anyway.

## Implementation

### Backend

**`SharedConfirmPayload`** gains one field:

```python
class ConfirmTemplate(_Model):
    id: int
    name: str
    #: The FOLLOWER's own exercise ids -- what the island compares the
    #: selected matches against.
    exercise_ids: list[int]

class SharedConfirmPayload(_Model):
    ...
    templates: list[ConfirmTemplate]
```

**`gym_shared_confirm`** builds it from `my_templates()` with
`joinedload(WorkoutTemplate.exercises)` — without the eager load this is one
query per routine, the pattern this codebase refuses to create. Empty when the
invite carries a refusal: there is nothing to confirm, so there is nothing to
book.

**`gym_shared_accept`** reads `template_id` from the form and resolves it
through `my_templates().filter_by(id=...)`, the same scoping `gym_start` uses.
Anything absent, malformed, or belonging to somebody else resolves to `None` —
today's behaviour, unchanged. The comment explaining `template_id=None` is
rewritten: the objection it records applies to the *leader's* routine, not to
one the follower owns.

### Matching rule (client)

For each routine, count how many of the session's exercises — as currently
matched in the dropdowns — appear in it. Offer every routine with at least one,
sorted by count descending, then by name. Preselect only when exactly one
routine covers all of them.

The denominator is every proposal on the page, one per distinct exercise the
leader is doing. A proposal left on **Neu anlegen** has no id in the follower's
catalogue yet, so no routine can contain it: it counts toward the total and can
never be covered. That is the honest reading — the routine genuinely does not
have that lift — and it means switching such a dropdown to an existing exercise
can turn `6 von 7` into `7 von 7` in place, which is exactly why the count is
computed from the live selection rather than once on the server.

Two proposals resolving to the same exercise count once: coverage is a
comparison of sets, not of rows.

### Interface

A single `.field` with a `.select`, below the match fields, inside the existing
form — the page keeps needing no CSS of its own.

- Label: **Zählt bei dir als**
- Options: `Keine Routine`, then `HBF Push — 7 von 7 Übungen`
- Below it, one `.sheet__note`: *Das Workout erscheint auf deinem Start als
  Durchgang dieser Routine.*

With no routine sharing an exercise the field is not rendered at all. A dead
control that can never do anything is worse than silence.

## Edge cases

| Case | Behaviour |
|---|---|
| No routines, or none overlapping | Field absent |
| Two or more perfect matches | Nothing preselected; the reader chooses |
| A match dropdown is changed | Coverage recomputes and the list re-sorts |
| Someone else's `template_id` posted | Ignored; session stays unlinked |
| Leader deviates after accept | Link stays. A session that departs from its routine is ordinary, and the debrief already offers "Vorlage aktualisieren" |
| Session name | Stays the leader's, so both sides read it as the same workout |

## Tests

**Backend**

- Accepting with a routine id links the follower's session to it.
- Accepting with another user's routine id leaves it unlinked.
- Accepting without one leaves it unlinked (today's behaviour, pinned).
- **The payoff, asserted as an effect rather than a column:** after the join,
  `routine_memory()` reports the shared session as that routine's last
  performance.

**Frontend**

- Coverage labels state the real counts.
- Exactly one perfect match is preselected; two are not.
- The field is absent when nothing overlaps.
- Changing a match dropdown re-ranks the list — the reactive behaviour is the
  reason the computation lives client-side, so it is the one that gets pinned.

## Out of scope

Creating a routine from the confirmation page. The debrief already offers
"Dieses Workout als Vorlage speichern?" for a session with no routine, which
covers the follower who has no fitting one — after the workout, when they know
what they actually did.
