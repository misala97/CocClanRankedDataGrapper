# Shared-session routine pick — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Let a lifter joining a shared workout book it under one of their own routines, so the session stops being invisible to their own routine bookkeeping.

**Architecture:** The confirmation page already matches the leader's exercises against the follower's catalogue. Its payload gains the follower's routines with their exercise ids; the React island ranks them by how many of the *currently selected* matches they contain and posts the chosen one; `gym_shared_accept` validates it through `my_templates()` and stores it as the follower session's `template_id`. Nothing else about the session changes.

**Tech Stack:** Flask + Pydantic payload schemas (`features/gym/schemas.py`), React island (`static/gym/src/shared/`), vitest + Testing Library, pytest.

## Global Constraints

- Spec: `docs/superpowers/specs/2026-08-11-gym-shared-session-routine-pick-design.md`. Read it before Task 1.
- UI copy is German. Code, comments and identifiers are English.
- Picking a routine sets `template_id` and nothing else. Rest times, exercise order, the exercise list and the session name stay untouched.
- Every cross-user id arriving from a form is resolved through a `scope.py` helper (`my_templates()`, `owned_exercise()`). Never trust a posted id.
- The page adds no CSS. Reuse `.field`, `.select`, `.label`, `.sheet__note`.
- Run from `personal_apps/`: `npx vitest run <path>`, `python -m pytest <path> -q`, `npm run build` (tsc + vite).
- Commit on branch `dev_personal`.

---

### Task 1: The confirmation payload carries the follower's routines

**Files:**
- Modify: `personal_apps/features/gym/schemas.py` (add `ConfirmTemplate` next to `MatchProposal` at :878, extend `SharedConfirmPayload` at :894)
- Modify: `personal_apps/features/gym/routes/partners.py` (`gym_shared_confirm`, :120-161)
- Test: `personal_apps/tests/test_gym_sharing.py` (including the `leader_with_partner` fixture teardown, :984-1010)

**Interfaces:**
- Consumes: nothing.
- Produces: `SharedConfirmPayload.templates: list[ConfirmTemplate]`, where `ConfirmTemplate` has `id: int`, `name: str`, `exercise_ids: list[int]`. Task 3 renders from it; Task 2 stores the id it carries.

- [ ] **Step 0: Let the fixture clean up more than one routine**

`leader_with_partner`'s teardown deletes a single template out of a
`made['template']` slot that tests mutate in. This task's test creates two (one
per lifter) and Task 2's create one each, so a single slot silently cannot hold
them — and an undeleted `WorkoutTemplate` blocks the `AppUser` delete that runs
after it. Replace that block:

```python
        # Every routine either lifter's test created. This was a single id in
        # a mutated dict slot, which could hold only one -- and a routine left
        # behind blocks the AppUser delete below on its foreign key. Sessions
        # pointing at one are already gone by now; TemplateExercise rows
        # cascade with their template (WorkoutTemplate.exercises is
        # delete-orphan).
        from models import WorkoutTemplate
        for user_id in (made['leader'], made['partner']):
            for row in WorkoutTemplate.query.filter_by(user_id=user_id).all():
                db.session.delete(row)
        db.session.commit()
```

Tests no longer need to set `made['template']`; leave the existing
`test_the_followers_session_carries_no_template_link` line that does, since it is
now harmless and removing it is unrelated churn.

Run: `python -m pytest tests/test_gym_sharing.py -q`
Expected: unchanged — all pass. This step refactors cleanup only.

- [ ] **Step 1: Write the failing test**

Add to `personal_apps/tests/test_gym_sharing.py`, after the existing
`test_the_followers_session_carries_no_template_link` block:

```python
def test_confirm_offers_the_followers_own_routines(leader_with_partner):
    """The follower's routines, with the exercise ids the island compares
    against the selected matches. The LEADER's routines must never appear:
    they are named in a catalogue this lifter does not own."""
    from extensions import db
    from models import (Exercise, SharedSession, TemplateExercise,
                        WorkoutTemplate)

    with flask_app.app_context():
        own_bench = Exercise(name='pytest invite bench',
                             user_id=leader_with_partner['partner'])
        db.session.add(own_bench)
        db.session.flush()
        mine = WorkoutTemplate(name='pytest partner push',
                               user_id=leader_with_partner['partner'])
        mine.exercises.append(
            TemplateExercise(exercise_id=own_bench.id, position=1))
        theirs = WorkoutTemplate(name='pytest leader push',
                                 user_id=leader_with_partner['leader'])
        db.session.add_all([mine, theirs])
        db.session.commit()
        expected = {'id': mine.id, 'name': 'pytest partner push',
                    'exercise_ids': [own_bench.id]}

    _client_for(leader_with_partner['leader']).post(
        f"/gym/session/{leader_with_partner['session']}/invite",
        data={'partner_id': leader_with_partner['partner']})
    with flask_app.app_context():
        shared_id = SharedSession.query.filter_by(
            leader_session_id=leader_with_partner['session']).first().id

    response = _client_for(leader_with_partner['partner']).get(
        f'/gym/shared/{shared_id}/confirm')
    payload = embedded_payload(response.get_data(as_text=True))

    assert payload['templates'] == [expected]
```

`embedded_payload` and `_client_for` already exist in this file's imports /
helpers — check the top of the file and reuse them; do not write new ones.

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_gym_sharing.py::test_confirm_offers_the_followers_own_routines -q`
Expected: FAIL with `KeyError: 'templates'`.

- [ ] **Step 3: Add the schema**

In `personal_apps/features/gym/schemas.py`, directly above `class SharedConfirmPayload`:

```python
class ConfirmTemplate(_Model):
    """One of the FOLLOWER's own routines, offered as what this shared
    workout counts as on their side.

    exercise_ids are theirs, not the leader's: the island compares them
    against the matches selected on the page, which resolve to this
    lifter's catalogue.
    """
    id: int
    name: str
    exercise_ids: list[int]
```

and add the field to `SharedConfirmPayload`:

```python
    #: The follower's routines, for booking this workout under one of them.
    #: Empty when the invite carries a refusal -- there is nothing to book.
    templates: list[ConfirmTemplate]
```

- [ ] **Step 4: Build it in the confirm route**

In `personal_apps/features/gym/routes/partners.py`, add `WorkoutTemplate` to
the `models` import and `my_templates` to the `features.gym.scope` import
(`TemplateExercise` is reached through the relationship, so it is not
imported). Then, inside `gym_shared_confirm`, extend the
`if refusal is None:` block — after `proposals = [...]` — with:

```python
        # The follower's own routines. joinedload because each one's exercise
        # ids are read below: without it this is a query per routine, the
        # N+1 this codebase refuses to create.
        templates = [
            {'id': template.id, 'name': template.name,
             'exercise_ids': [te.exercise_id for te in template.exercises]}
            for template in (my_templates()
                             .options(joinedload(WorkoutTemplate.exercises))
                             .order_by(WorkoutTemplate.name)
                             .all())
        ]
```

Initialise `templates = []` beside `proposals = []` above the `if`, and pass
`templates=templates` into `SharedConfirmPayload(...)`. Add
`from sqlalchemy.orm import joinedload` to the imports.

- [ ] **Step 5: Run the test**

Run: `python -m pytest tests/test_gym_sharing.py::test_confirm_offers_the_followers_own_routines -q`
Expected: PASS.

- [ ] **Step 6: Run the whole sharing suite**

Run: `python -m pytest tests/test_gym_sharing.py -q`
Expected: all pass. `test_the_followers_session_carries_no_template_link` must
stay green — it is the guard that the leader's routine is never inherited.

- [ ] **Step 7: Commit**

```bash
git add personal_apps/features/gym/schemas.py personal_apps/features/gym/routes/partners.py personal_apps/tests/test_gym_sharing.py
git commit -m "feat(gym): the confirm page knows the follower's own routines"
```

---

### Task 2: Accepting an invite honours a posted routine

**Files:**
- Modify: `personal_apps/features/gym/routes/partners.py` (`gym_shared_accept`, :164-199 — the `WorkoutSession(...)` construction and its `template_id=None` comment)
- Test: `personal_apps/tests/test_gym_sharing.py`

**Interfaces:**
- Consumes: `ConfirmTemplate.id` from Task 1 — posted as the form field `template_id`.
- Produces: the follower's `WorkoutSession.template_id`, which `stats.routine_memory()` already reads.

- [ ] **Step 1: Write the failing tests**

Add three tests to `personal_apps/tests/test_gym_sharing.py`:

```python
def _accept_with_template(fixture, template_id):
    """Invite, then accept posting a routine id. Returns the follower's
    session id."""
    from extensions import db
    from models import SharedSession

    _client_for(fixture['leader']).post(
        f"/gym/session/{fixture['session']}/invite",
        data={'partner_id': fixture['partner']})
    with flask_app.app_context():
        shared_id = SharedSession.query.filter_by(
            leader_session_id=fixture['session']).first().id

    _client_for(fixture['partner']).post(
        f'/gym/shared/{shared_id}/accept',
        data={f"match_{fixture['exercise']}": 'new',
              'template_id': str(template_id)})

    with flask_app.app_context():
        return db.session.get(SharedSession, shared_id).follower_session_id


def test_accepting_books_the_session_under_the_chosen_routine(leader_with_partner):
    from extensions import db
    from models import WorkoutSession, WorkoutTemplate

    with flask_app.app_context():
        mine = WorkoutTemplate(name='pytest partner push',
                               user_id=leader_with_partner['partner'])
        db.session.add(mine)
        db.session.commit()
        template_id = mine.id

    follower_session = _accept_with_template(leader_with_partner, template_id)

    with flask_app.app_context():
        assert db.session.get(
            WorkoutSession, follower_session).template_id == template_id


def test_accepting_refuses_a_routine_the_follower_does_not_own(leader_with_partner):
    """Attacker-chosen, like every other id arriving from this form: posting
    the LEADER's routine must not book the workout under it."""
    from extensions import db
    from models import WorkoutSession, WorkoutTemplate

    with flask_app.app_context():
        theirs = WorkoutTemplate(name='pytest leader push',
                                 user_id=leader_with_partner['leader'])
        db.session.add(theirs)
        db.session.commit()
        template_id = theirs.id

    follower_session = _accept_with_template(leader_with_partner, template_id)

    with flask_app.app_context():
        assert db.session.get(
            WorkoutSession, follower_session).template_id is None


def test_the_booked_session_counts_as_that_routines_last_performance(leader_with_partner):
    """The point of the whole feature, asserted as an effect rather than as a
    column: routine_memory() is what Heute reads, and before this it skipped
    every shared session."""
    import datetime as dt
    from extensions import db
    from features.gym import stats
    from models import WorkoutSession, WorkoutTemplate

    with flask_app.app_context():
        mine = WorkoutTemplate(name='pytest partner push',
                               user_id=leader_with_partner['partner'])
        db.session.add(mine)
        db.session.commit()
        template_id = mine.id

    _accept_with_template(leader_with_partner, template_id)

    with flask_app.app_context():
        template = db.session.get(WorkoutTemplate, template_id)
        sessions = WorkoutSession.query.filter_by(
            user_id=leader_with_partner['partner']).all()
        memory = stats.routine_memory([template], sessions, dt.datetime.utcnow())
        assert memory[0]['last_done'] is not None
        assert memory[0]['days_ago'] == 0
```

- [ ] **Step 2: Run them to verify they fail**

Run: `python -m pytest tests/test_gym_sharing.py -q -k "chosen_routine or does_not_own or last_performance"`
Expected: `test_accepting_books_the_session_under_the_chosen_routine` and
`test_the_booked_session_counts_as_that_routines_last_performance` FAIL
(`template_id` is `None`, `last_done` is `None`).
`test_accepting_refuses_a_routine_the_follower_does_not_own` already passes —
that is correct: it pins behaviour that must survive the change.

- [ ] **Step 3: Read the posted routine in `gym_shared_accept`**

Replace the `template_id=None` argument and its comment in the
`WorkoutSession(...)` construction with a resolved value. Above the
construction, add:

```python
    # The routine THIS lifter books the workout under, if they picked one on
    # the confirm page. Resolved through my_templates(), so a posted id that
    # belongs to somebody else -- the leader's own routine, most obviously --
    # resolves to None rather than claiming it.
    chosen_template = None
    posted_template_id = _to_int(request.form.get('template_id', ''))
    if posted_template_id:
        chosen_template = my_templates().filter_by(id=posted_template_id).first()
```

and change the constructor argument to:

```python
        # The leader's routine is never inherited: it is named in a catalogue
        # this lifter does not own, and claiming it would tell
        # routine_memory() they had performed a routine that is not theirs.
        # One of their OWN routines is a different matter -- that is what the
        # confirm page's picker posts, and booking it there is the only way a
        # shared workout ever reaches their routine bookkeeping.
        template_id=chosen_template.id if chosen_template else None,
```

Add `my_templates` to the `features.gym.scope` import if Task 1 did not.

- [ ] **Step 4: Run the tests**

Run: `python -m pytest tests/test_gym_sharing.py -q -k "chosen_routine or does_not_own or last_performance"`
Expected: 3 passed.

- [ ] **Step 5: Run the full backend suite**

Run: `python -m pytest tests -q`
Expected: all pass, including
`test_the_followers_session_carries_no_template_link`.

- [ ] **Step 6: Commit**

```bash
git add personal_apps/features/gym/routes/partners.py personal_apps/tests/test_gym_sharing.py
git commit -m "feat(gym): a shared workout can count as your own routine"
```

---

### Task 3: The confirm page offers the picker

**Files:**
- Modify: `personal_apps/static/gym/src/shared/types.ts`
- Modify: `personal_apps/static/gym/src/shared/SharedConfirmPage.tsx`
- Test: `personal_apps/static/gym/src/shared/SharedConfirmPage.test.tsx`

**Interfaces:**
- Consumes: `SharedConfirmPayload.templates` from Task 1; posts the form field `template_id` read by Task 2.
- Produces: nothing downstream.

- [ ] **Step 1: Write the failing tests**

Add to `SharedConfirmPage.test.tsx`. Extend the `base` fixture with
`templates: []` first, then:

```tsx
const templates = [
  { id: 1, name: 'Push', exercise_ids: [55, 57] },
  { id: 2, name: 'Ganzkörper', exercise_ids: [55] },
]

describe('the routine picker', () => {
  it('is absent when no routine shares an exercise', () => {
    mount({ templates: [{ id: 3, name: 'Beine', exercise_ids: [99] }] })
    expect(screen.queryByLabelText('Zählt bei dir als')).not.toBeInTheDocument()
  })

  it('ranks routines by how much of the workout they cover', () => {
    mount({ templates })
    const options = [...screen.getByLabelText('Zählt bei dir als')
      .querySelectorAll('option')].map((o) => o.textContent)
    expect(options).toEqual([
      'Keine Routine', 'Push — 2 von 2 Übungen', 'Ganzkörper — 1 von 2 Übungen',
    ])
  })

  it('preselects a routine that covers the whole workout', () => {
    mount({ templates })
    expect(screen.getByLabelText('Zählt bei dir als')).toHaveValue('1')
  })

  it('preselects nothing when two routines cover it', () => {
    mount({ templates: [
      { id: 1, name: 'Push', exercise_ids: [55, 57] },
      { id: 2, name: 'Push alt', exercise_ids: [55, 57] },
    ] })
    expect(screen.getByLabelText('Zählt bei dir als')).toHaveValue('')
  })

  it('recounts when a match changes, since coverage depends on it', async () => {
    // The reason this is computed on the client at all: switching the second
    // exercise away from the routine's drops its coverage in place.
    const user = userEvent.setup()
    mount({ templates })
    await user.selectOptions(screen.getByLabelText('Butterfly'), 'new')
    const options = [...screen.getByLabelText('Zählt bei dir als')
      .querySelectorAll('option')].map((o) => o.textContent)
    expect(options).toContain('Push — 1 von 2 Übungen')
  })
})
```

Add `import userEvent from '@testing-library/user-event'` to the file if it is
not already imported.

- [ ] **Step 2: Run them to verify they fail**

Run: `npx vitest run static/gym/src/shared/SharedConfirmPage.test.tsx`
Expected: FAIL — `Unable to find a label with the text of: Zählt bei dir als`.

- [ ] **Step 3: Extend the type**

In `static/gym/src/shared/types.ts`:

```ts
export interface ConfirmTemplate {
  id: number
  name: string
  /** The FOLLOWER's own exercise ids -- compared against the selected
   *  matches, which resolve to the same catalogue. */
  exercise_ids: number[]
}
```

and add to `SharedConfirmPayload`:

```ts
  /** The follower's routines, for booking this workout under one of them. */
  templates: ConfirmTemplate[]
```

- [ ] **Step 4: Make the matches controlled and render the picker**

Rewrite the body of `SharedConfirmPage` so the match selects are controlled —
coverage cannot react to a value the component does not hold. Keep every
existing `name`, `className` and option, so the posted form is unchanged:

```tsx
export function SharedConfirmPage({ payload }: { payload: SharedConfirmPayload }) {
  // Controlled, unlike the original uncontrolled defaultValue: the routine
  // list below counts against the CURRENT selection, so the page has to hold
  // it. The `name` attributes are untouched, so the form still posts exactly
  // what gym_shared_accept has always read.
  const [matches, setMatches] = useState<Record<number, string>>(
    () => Object.fromEntries(payload.proposals.map((proposal) => [
      proposal.leader_exercise_id,
      proposal.exact_id === null ? 'new' : String(proposal.exact_id),
    ])))
  // null means "the reader has not touched it", which is what lets the
  // preselection keep following the matches until they do.
  const [routine, setRoutine] = useState<string | null>(null)

  // A proposal left on "Neu anlegen" has no id in this catalogue yet, so no
  // routine can contain it: it counts toward the total and can never be
  // covered. That is the honest reading -- the routine really does not have
  // that lift.
  const chosen = new Set(Object.values(matches)
    .filter((value) => value !== 'new').map(Number))
  const total = payload.proposals.length
  const ranked = payload.templates
    .map((template) => ({
      ...template,
      covered: template.exercise_ids.filter((id) => chosen.has(id)).length,
    }))
    .filter((template) => template.covered > 0)
    .sort((a, b) => b.covered - a.covered || a.name.localeCompare(b.name, 'de'))

  const perfect = ranked.filter((template) => template.covered === total)
  const autoPick = perfect.length === 1 ? String(perfect[0]!.id) : ''
  const routineValue = routine ?? autoPick

  return (
    <section className="sec" aria-labelledby="sec-confirm">
      <div className="sec__head">
        <h2 className="label" id="sec-confirm">{`Mit ${payload.leader_name} trainieren`}</h2>
      </div>

      {payload.refusal !== null ? (
        <>
          <p className="empty">{payload.refusal}</p>
          <a className="btn btn--ghost" href="/gym">Zurück</a>
        </>
      ) : (
        <>
          {/* Exact matches are already resolved and say so. Only the genuinely
              ambiguous ones carry a decision, because asking seven times per
              shared workout would make the common path the annoying one. */}
          <form method="post" action={`/gym/shared/${payload.shared_id}/accept`}>
            <CsrfField />
            {payload.proposals.map((proposal) => (
              <div className="field grow" key={proposal.leader_exercise_id}>
                <label className="label" htmlFor={`match-${proposal.leader_exercise_id}`}>
                  {proposal.name}
                </label>
                <select className="select" id={`match-${proposal.leader_exercise_id}`}
                  name={`match_${proposal.leader_exercise_id}`}
                  value={matches[proposal.leader_exercise_id]}
                  onChange={(e) => setMatches((current) => ({
                    ...current,
                    [proposal.leader_exercise_id]: e.target.value,
                  }))}>
                  <option value="new">Neu anlegen</option>
                  {proposal.candidates.map(([id, name]) => (
                    <option value={id} key={id}>{name}</option>
                  ))}
                </select>
              </div>
            ))}

            {/* Absent rather than empty: a control that can never do anything
                is worse than silence. */}
            {ranked.length > 0 && (
              <div className="field grow">
                <label className="label" htmlFor="confirm-routine">Zählt bei dir als</label>
                <select className="select" id="confirm-routine" name="template_id"
                  value={routineValue}
                  onChange={(e) => setRoutine(e.target.value)}>
                  <option value="">Keine Routine</option>
                  {ranked.map((template) => (
                    <option value={template.id} key={template.id}>
                      {`${template.name} — ${template.covered} von ${total} Übungen`}
                    </option>
                  ))}
                </select>
                <p className="sheet__note">
                  Das Workout erscheint auf deinem Start als Durchgang dieser Routine.
                </p>
              </div>
            )}

            <button type="submit" className="btn btn--live btn--block">Mitmachen</button>
          </form>

          <form method="post" action={`/gym/shared/${payload.shared_id}/decline`}>
            <CsrfField />
            <button type="submit" className="btn btn--ghost">Ablehnen</button>
          </form>
        </>
      )}
    </section>
  )
}
```

Add `import { useState } from 'react'` at the top.

- [ ] **Step 5: Run the page's tests**

Run: `npx vitest run static/gym/src/shared/SharedConfirmPage.test.tsx`
Expected: all pass, including the pre-existing ones — the match selects still
carry their `name` and options.

- [ ] **Step 6: Typecheck, build, and run the whole frontend suite**

Run: `npm run build && npx vitest run`
Expected: build succeeds, all suites pass.

- [ ] **Step 7: Commit**

```bash
git add personal_apps/static/gym/src/shared/
git commit -m "feat(gym): pick which of your routines a shared workout counts as"
```

---

### Task 4: Verify the flow against two real accounts

**Files:**
- Create: scratchpad script only. Nothing in the repo.

**Interfaces:**
- Consumes: everything above.
- Produces: nothing.

- [ ] **Step 1: Start the dev server**

Run in the background from `personal_apps/`:
`python -c "from app import app; app.run(host='127.0.0.1', port=5001, debug=False, use_reloader=False)"`

- [ ] **Step 2: Build a leader session and an invite**

Write a scratchpad script (not in the repo) that, inside `flask_app.app_context()`:

1. Ensures a second account exists — the dev database has one, production has
   three. Create `AppUser(username='zz_sync_partner', password_hash=generate_password_hash(...), is_admin=False)` if `AppUser.query.count() < 2`.
2. Deletes any unfinished `WorkoutSession` (clear `resting_set_id` first), or
   `/gym/start` redirects to the running workout instead of starting one.
3. Starts the leader's session: `flask_app.test_client()` with
   `session['user_id'] = leader.id`, then `POST /gym/start` with the leader's
   `template_id`.
4. Posts `POST /gym/session/<id>/invite` with `partner_id=<follower>`.
5. Mints a browser cookie per user:
   `SecureCookieSessionInterface().get_signing_serializer(flask_app).dumps({'user_id': uid})`.

Set `flask_app.config['TESTING'] = True` so the CSRF gate lets the test client
through. Print the shared id and both cookies. **Stop before accepting** — the
confirm page is what is under test.

- [ ] **Step 3: Give the follower a matching routine**

In the same script, create a `WorkoutTemplate` owned by the follower whose
`TemplateExercise` rows point at follower-catalogue exercises with the same
names as the leader's session exercises — those are what the confirm page's
exact matching will resolve the dropdowns to, so they are what makes the
routine a full-coverage match.

- [ ] **Step 4: Drive the confirm page with playwright**

Load `/gym/shared/<id>/confirm` as the follower at 390×844 and assert:
the picker is present, the perfect match is preselected, the option label
reads `N von N Übungen`, and switching one exercise match to "Neu anlegen"
lowers the count in place. Screenshot it and **read the PNG** — this is a new
surface and it has to be looked at, in both themes.

- [ ] **Step 5: Accept and confirm the payoff**

Submit the form, then load `/gym` as the follower and assert their routine no
longer reads "Noch nie gemacht" — it reports the workout that just started.
This is the whole point of the feature, seen the way the lifter sees it.

- [ ] **Step 6: Clean up**

Delete the throwaway account, its exercises, its routine, both sessions and
the link from the dev database. Stop the dev server. Confirm no unfinished
session is left behind — `pytest` finishes any it finds, which would silently
end a real workout.

- [ ] **Step 7: Final full run**

Run: `python -m pytest tests -q && npx vitest run && npm run build`
Expected: everything green.
