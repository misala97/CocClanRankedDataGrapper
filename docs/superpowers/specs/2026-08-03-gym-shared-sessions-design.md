# Gym: training together, without training the same

**Date:** 2026-08-03
**Status:** Approved design, not yet implemented
**Scope:** `personal_apps` gym feature only.

## Why

Two people train the same workout side by side and the app makes each of them
build it twice. Every reorder, every swap when a machine is occupied, every
exercise added on a whim has to be repeated on the other phone — or the two
sessions quietly drift apart until they are no longer the same workout at all.

What is genuinely shared between training partners is *structure*: which
exercises, in what order. What is not shared is the load. Weight and reps are
the one thing that cannot transfer between two bodies.

So the app should carry the structure and leave the numbers alone.

## Decisions

### 1. Two sessions, linked — not one session, shared

Each person owns an ordinary `WorkoutSession`. Nothing about the ownership
model changes: every `owned_session()` and `my_sessions()` guarantee holds
untouched, and no route serves one user rows belonging to another.

The link is metadata. A follower's session appears in Verlauf, Statistik, the
finished-session debrief and the rest readouts as what it is — a normal
workout — because it is one.

*Rejected:* a single session with two users attached. It would have required
every existing query in the gym feature to learn about co-ownership, and the
per-user partitioning finished the same day is exactly what that would undo.

### 2. Propagation is a replay, not shared state

When the leader changes structure, the route writes the leader's session as it
does today, then applies the same change to the follower's session, translated
through a per-link exercise map.

This is the load-bearing choice. Because propagation is a *write*, the follower
only ever reads their own rows — there is no cross-user read on the hot path,
and no consistency protocol between two live clients. One write path, applied
twice, the second time translated.

### 3. The map is what makes divergent catalogues work

Exercises are per-user (four owned roots as of 2026-08-02). "Bankdrücken" in
one catalogue and "Bankdrücken" in another are different rows with different
ids. A structural change expressed in the leader's ids is meaningless against
the follower's data without a translation.

Hence `SharedSessionExercise`: one row per exercise pair, established when the
follower accepts.

### 4. The follower confirms once, before the workout starts

Confirmation belongs at the door, not in the middle of a set.

- **Exact name matches are silent.** Case- and whitespace-insensitive. If both
  people have "Bankdrücken", there is nothing to ask about, and asking seven
  times per shared workout would make the common path the annoying one.
- **Everything else asks**, with a dropdown of the follower's own catalogue
  plus a `Neu anlegen` option. Candidates are ordered by a deliberately dull
  rule — exercises whose name contains the leader's name, or whose name the
  leader's name contains, come first (case-insensitive); everything else
  follows alphabetically. Enough to float "KH Bankdrücken" to the top for
  "Bankdrücken" without pretending to understand German gym vocabulary.

*Rejected:* aggressive fuzzy matching. A wrong auto-match silently files sets
against the wrong exercise's history, which is worse than a question — and it
corrupts the stagnation and record logic that reads that history.

### 5. Mid-session additions resolve silently

An exercise added after the confirm screen was never confirmed, and the whole
reason confirmation is upfront is to keep it out of the workout. So: exact name
match links to the follower's existing exercise; anything else is created in
the follower's catalogue on the spot, owned by them. They can rename or tidy up
afterwards.

### 6. Structure is shared, performance is personal

| Propagates | Does not |
| --- | --- |
| Add exercise | Weight, reps |
| Remove exercise | **Number of sets** |
| Reorder | Rest seconds |
| Replace / substitute | Deload flag and percentage |
| Skip / unskip | Session name after seeding |

**Set count is deliberately personal.** Appending a fourth set is a decision
about your own body made mid-lift, not programming. If it propagated, an empty
set would appear in the partner's queue because someone else felt strong.

Rest follows the person, because the two train at independent pace. Deload is a
judgement about one person's own training block.

### 7. Independent pace

Each screen tracks its own current exercise and set. The shared structure stays
in sync; nobody waits on anybody. This is how partners actually train — a set
ahead or behind on the same station, or on different stations entirely.

### 8. The leader leaving does not end the follower's workout

When the leader finishes, the link goes dormant. The follower's session stays
live and entirely theirs; they simply stop receiving structural updates. No
prompt, no interruption. A workout must never be cut short by someone else's.

## The model

```
SharedSession
  id
  leader_session_id    -> gym_workout_sessions   NOT NULL
  follower_session_id  -> gym_workout_sessions   NULL until accepted
  leader_user_id       -> app_user               NOT NULL
  follower_user_id     -> app_user               NOT NULL
  created_at                                     NOT NULL
  accepted_at                                    NULL = pending
  ended_at                                       NULL = live

SharedSessionExercise
  id
  shared_session_id    -> shared_session         NOT NULL
  leader_exercise_id   -> gym_exercises          NOT NULL
  follower_exercise_id -> gym_exercises          NOT NULL
```

State derives from the timestamps rather than a status column: pending
(`accepted_at IS NULL`), active (accepted, `ended_at IS NULL`), ended.
`ended_at` is stamped when **either** session finishes — whichever comes
first — which is what makes the link dormant in Decision 8.

`(leader_session_id, follower_user_id)` is unique: inviting the same person
twice to the same workout re-surfaces the existing invite rather than creating
a second one.

`SharedSession` cascades from the leader's session, so deleting a workout
cannot strand a link.

**The follower's session carries no `template_id`.** The routine belongs to the
leader's catalogue, and pointing at it would be a cross-user reference into
data the follower cannot otherwise reach. It would also corrupt
`routine_memory()`, which answers "when did *you* last do this routine" — a
shared session is not evidence that the follower has a routine they have never
owned.

**A mapped exercise cannot be deleted out from under the link.** The follower's
session already references it through a `SessionExercise` row, and
`gym_delete_exercise` refuses to delete an exercise that is in use. No new
guard is needed.

**Multiple followers cost nothing.** The replay loops over accepted links. No
UI is built for it — invites go out one at a time — but if all three accounts
ever train together the model already holds.

## Flow

### Inviting

The leader picks a partner from the other accounts, either when starting a
routine or already mid-workout — the same mechanism, since the follower seeds
from current state either way. The leader's session starts immediately and is
never blocked on acceptance. Their lead card reads `Warte auf <name>`, then
`<name> ist dabei`.

### Joining

Push fires and a pending-invite card lands on the follower's Heute. Opening it
gives the confirm screen described in Decision 4.

Accepting creates their session, seeded from the leader's structure **as it
stands at that moment** — not as it stood when the invite was sent. Exercises
added while the follower was still walking to the gym are included.

### Refusing

Three states cannot produce a join, each with its own message rather than a
generic failure:

- **Follower already has a live workout.** `Du hast bereits ein laufendes
  Workout.` The app allows one active session; joining would mean abandoning
  theirs, which is not a decision to make on their behalf.
- **Leader already finished.** `Das Workout ist schon vorbei.`
- **Declined.** The card disappears and the leader's card returns to solo. No
  notification back — declining is not an event worth a buzz.

### Keeping up

The follower's live page polls a small JSON endpoint roughly every five
seconds, **only while the page is visible**. A backgrounded phone makes no
requests. The endpoint returns a structure version; unchanged means a few bytes
and no work.

On a change, the queue list re-renders from a server-rendered partial. The
panel — the exercise they are on, the weight half-typed into a stepper — is
never touched.

The one exception: if the leader removed the exercise the follower currently
has **open**, the page reloads. There is no honest way to keep showing a panel
for something that no longer exists.

Polling stops when either session finishes or the link ends.

*Rejected:* WebSockets or SSE. A persistent connection means a new dependency,
new deploy configuration on a plain gunicorn setup, and a live socket draining
a phone battery through a workout — to save four seconds of latency on a
reorder.

## Security

This is the first feature where one user's action writes into another user's
rows. The seam is narrow by construction.

**No cross-user reads on the hot path.** Decision 2 gives this for free: the
follower polls their own session and reads their own rows.

Exactly two cross-user accesses exist:

- **The confirm screen** — the follower reads the leader's exercise *names and
  order*. No sets, no weights, no history. Gated on a pending invite the leader
  created.
- **Invite status** — the leader reads `accepted_at` on the link, never the
  follower's session.

**The cross-user write goes through one chokepoint.** A single function
performs every propagation and refuses unless all of the following hold: the
link exists, it is accepted, it has not ended, `leader_user_id` is the caller,
and the target is that link's recorded `follower_session_id`. One function to
audit, in the same spirit as `scope.py` being the one place reads are gated.

Exercise auto-creation is bounded identically: the name comes from the leader,
the owner is **always** the follower.

## Testing

Beyond the happy path:

- A stranger cannot replay structure into anyone's session — the chokepoint
  refuses.
- The leader cannot read the follower's sets through any route.
- An exact-name match **links** rather than duplicating: no second
  "Bankdrücken" appears in the follower's catalogue.
- An auto-created exercise is owned by the follower, not the leader.
- **Set count does not propagate.** A negative test, and the single behaviour
  most likely to regress silently.
- The leader finishing leaves the follower live and editable.
- A follower with an active workout is refused, and their workout is left
  untouched.
- A structural change increments the version; logging a set does not.
- Accepting seeds from the leader's *current* structure, not the routine as it
  was at invite time.
- The follower's session has no `template_id`, so the shared workout does not
  appear in their routine history.
- Either side finishing stamps `ended_at`, and propagation stops afterwards.

## Out of scope

- **Seeing a partner's numbers**, live or afterwards. Structure only.
- **Symmetric editing.** Structure is leader-only; the follower's session is
  otherwise fully theirs, but their structural changes do not travel back.
- **Real-time transport.** See the rejection under *Keeping up*.
- **A history of who you trained with.** The link is operational state, not a
  social record.
