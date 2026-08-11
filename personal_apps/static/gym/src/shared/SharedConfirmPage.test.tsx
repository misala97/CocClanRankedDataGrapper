import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it } from 'vitest'
import { SharedConfirmPage } from './SharedConfirmPage'
import type { SharedConfirmPayload } from './types'

const base: SharedConfirmPayload = {
  shared_id: 7,
  leader_name: 'Michi',
  refusal: null,
  proposals: [
    {
      name: 'Bankdrücken', leader_exercise_id: 10, exact_id: 55,
      candidates: [[55, 'Bankdrücken'], [56, 'Bankdrücken (Kurzhantel)']],
    },
    {
      name: 'Butterfly', leader_exercise_id: 11, exact_id: null,
      candidates: [[57, 'Reverse Fly (Machine)']],
    },
  ],
  templates: [],
}

const mount = (over: Partial<SharedConfirmPayload> = {}) =>
  render(<SharedConfirmPage payload={{ ...base, ...over }} />)

describe('SharedConfirmPage', () => {
  it('names who invited you', () => {
    mount()
    expect(screen.getByRole('heading', { name: 'Mit Michi trainieren' }))
      .toBeInTheDocument()
  })

  it('preselects an exact match and offers every candidate anyway', () => {
    // Exact matches are already resolved and say so; only the ambiguous ones
    // carry a real decision, because asking seven times per shared workout
    // would make the common path the annoying one.
    mount()
    const exact = screen.getByLabelText('Bankdrücken')
    expect(exact).toHaveValue('55')
    expect(screen.getAllByRole('option').map((o) => o.textContent))
      .toContain('Bankdrücken (Kurzhantel)')
  })

  it('falls back to creating a new exercise when nothing matched', () => {
    mount()
    expect(screen.getByLabelText('Butterfly')).toHaveValue('new')
  })

  it('posts each choice under the leader exercise it answers for', () => {
    mount()
    expect(screen.getByLabelText('Bankdrücken')).toHaveAttribute('name', 'match_10')
    expect(screen.getByLabelText('Butterfly')).toHaveAttribute('name', 'match_11')
    expect(screen.getByRole('button', { name: 'Mitmachen' }).closest('form'))
      .toHaveAttribute('action', '/gym/shared/7/accept')
    expect(screen.getByRole('button', { name: 'Ablehnen' }).closest('form'))
      .toHaveAttribute('action', '/gym/shared/7/decline')
  })

  describe('a refused invite', () => {
    it('states the reason and offers only the way back', () => {
      mount({ refusal: 'Du hast bereits ein laufendes Workout.', proposals: [] })
      expect(screen.getByText('Du hast bereits ein laufendes Workout.'))
        .toBeInTheDocument()
      expect(screen.getByRole('link', { name: 'Zurück' })).toHaveAttribute('href', '/gym')
    })

    it('offers nothing to confirm or decline', () => {
      mount({ refusal: 'Das Workout ist schon vorbei.', proposals: [] })
      expect(screen.queryByRole('button', { name: 'Mitmachen' })).not.toBeInTheDocument()
      expect(screen.queryByRole('button', { name: 'Ablehnen' })).not.toBeInTheDocument()
    })
  })

  it('still offers to join a workout with no exercises yet', () => {
    // The leader may not have added anything before inviting; the follower's
    // session is seeded from the structure as it stands at accept time.
    mount({ proposals: [] })
    expect(screen.getByRole('button', { name: 'Mitmachen' })).toBeInTheDocument()
    expect(screen.queryByRole('combobox')).not.toBeInTheDocument()
  })
})

const templates = [
  { id: 1, name: 'Push', exercise_ids: [55, 57] },
  { id: 2, name: 'Ganzkörper', exercise_ids: [55] },
]

// `base.proposals` leaves Butterfly on exact_id: null so the top-level suite
// can exercise the "Neu anlegen" fallback. Coverage math needs both exercises
// actually matched going in -- otherwise every "starts fully covered" case
// here would be indistinguishable from "nothing is covered", and the
// recount test would toggle a select that was already on its target value,
// passing whether or not the recount logic works at all.
const proposals = [
  {
    name: 'Bankdrücken', leader_exercise_id: 10, exact_id: 55,
    candidates: [[55, 'Bankdrücken'], [56, 'Bankdrücken (Kurzhantel)']] as [number, string][],
  },
  {
    name: 'Butterfly', leader_exercise_id: 11, exact_id: 57,
    candidates: [[57, 'Reverse Fly (Machine)']] as [number, string][],
  },
]

describe('the routine picker', () => {
  it('is absent when no routine shares an exercise', () => {
    mount({ proposals, templates: [{ id: 3, name: 'Beine', exercise_ids: [99] }] })
    expect(screen.queryByLabelText('Zählt bei dir als')).not.toBeInTheDocument()
  })

  it('ranks routines by how much of the workout they cover', () => {
    mount({ proposals, templates })
    const options = [...screen.getByLabelText('Zählt bei dir als')
      .querySelectorAll('option')].map((o) => o.textContent)
    expect(options).toEqual([
      'Keine Routine', 'Push — 2 von 2 Übungen', 'Ganzkörper — 1 von 2 Übungen',
    ])
  })

  it('preselects a routine that covers the whole workout', () => {
    mount({ proposals, templates })
    expect(screen.getByLabelText('Zählt bei dir als')).toHaveValue('1')
  })

  it('preselects nothing when two routines cover it', () => {
    mount({ proposals, templates: [
      { id: 1, name: 'Push', exercise_ids: [55, 57] },
      { id: 2, name: 'Push alt', exercise_ids: [55, 57] },
    ] })
    expect(screen.getByLabelText('Zählt bei dir als')).toHaveValue('')
  })

  it('recounts when a match changes, since coverage depends on it', async () => {
    // The reason this is computed on the client at all: switching the second
    // exercise away from the routine's drops its coverage in place.
    const user = userEvent.setup()
    mount({ proposals, templates })
    await user.selectOptions(screen.getByLabelText('Butterfly'), 'new')
    const options = [...screen.getByLabelText('Zählt bei dir als')
      .querySelectorAll('option')].map((o) => o.textContent)
    expect(options).toContain('Push — 1 von 2 Übungen')
  })

  it('counts a "Neu anlegen" proposal as covered when its name matches an owned exercise', () => {
    // gym_shared_accept's 'new' branch (partners.py) reuses an owned
    // exercise of the same name before creating one -- "Neu anlegen" is not
    // a guaranteed miss. If the client didn't reproduce that reuse, this
    // routine would read 1 von 2 and never preselect, even though the
    // session the server actually creates holds both its exercises.
    mount({
      proposals: [
        {
          name: 'Bankdrücken', leader_exercise_id: 10, exact_id: null,
          candidates: [[55, 'Bankdrücken']] as [number, string][],
        },
        {
          name: 'Butterfly', leader_exercise_id: 11, exact_id: 57,
          candidates: [[57, 'Reverse Fly (Machine)']] as [number, string][],
        },
      ],
      templates: [{ id: 1, name: 'Push', exercise_ids: [55, 57] }],
    })
    expect(screen.getByLabelText('Bankdrücken')).toHaveValue('new')
    const options = [...screen.getByLabelText('Zählt bei dir als')
      .querySelectorAll('option')].map((o) => o.textContent)
    expect(options).toContain('Push — 2 von 2 Übungen')
    expect(screen.getByLabelText('Zählt bei dir als')).toHaveValue('1')
  })

  it('counts two proposals that resolve to the same exercise once, not twice', () => {
    // The numerator already dedupes matches into a Set of ids; the
    // denominator has to match or a routine that covers everything the
    // follower will actually perform can never read as fully covered.
    mount({
      proposals: [
        {
          name: 'Kniebeuge', leader_exercise_id: 10, exact_id: 55,
          candidates: [[55, 'Kniebeuge']] as [number, string][],
        },
        {
          name: 'Squat', leader_exercise_id: 11, exact_id: 55,
          candidates: [[55, 'Kniebeuge']] as [number, string][],
        },
      ],
      templates: [{ id: 1, name: 'Beine', exercise_ids: [55] }],
    })
    const options = [...screen.getByLabelText('Zählt bei dir als')
      .querySelectorAll('option')].map((o) => o.textContent)
    expect(options).toContain('Beine — 1 von 1 Übungen')
    expect(screen.getByLabelText('Zählt bei dir als')).toHaveValue('1')
  })

  it('does not treat a near-miss name as the same exercise', () => {
    // The server matches on filter_by(name=...) -- byte equality, no
    // case-folding. Normalising here would silently claim coverage the
    // accept route will not deliver, and every other test in this block
    // uses byte-identical names, so nothing else would notice.
    mount({
      proposals: [{
        name: 'Bankdrücken', leader_exercise_id: 10, exact_id: null,
        candidates: [[55, 'bankdrücken ']] as [number, string][],
      }],
      templates: [{ id: 1, name: 'Push', exercise_ids: [55] }],
    })
    expect(screen.queryByLabelText('Zählt bei dir als')).not.toBeInTheDocument()
  })

  it('counts two genuinely new exercises as two, not as one', () => {
    // Both resolve to null, and null === null: deduping the resolved list
    // itself rather than only its ids would collapse them into a single
    // missing exercise. One covered exercise is in the fixture on purpose --
    // with none, the picker is absent either way and the denominator's bug
    // would be invisible.
    mount({
      proposals: [
        {
          name: 'Kniebeuge', leader_exercise_id: 10, exact_id: 55,
          candidates: [[55, 'Kniebeuge']] as [number, string][],
        },
        {
          name: 'Zercher Squat', leader_exercise_id: 11, exact_id: null,
          candidates: [[55, 'Kniebeuge']] as [number, string][],
        },
        {
          name: 'Jefferson Curl', leader_exercise_id: 12, exact_id: null,
          candidates: [[55, 'Kniebeuge']] as [number, string][],
        },
      ],
      templates: [{ id: 1, name: 'Beine', exercise_ids: [55] }],
    })
    expect([...screen.getByLabelText('Zählt bei dir als')
      .querySelectorAll('option')].map((o) => o.textContent))
      .toContain('Beine — 1 von 3 Übungen')
  })

  it('keeps a routine the reader picked even after its coverage drops to zero', async () => {
    // Filtering it out would leave the controlled select with no matching
    // option, so the browser resets it to the first one and the workout is
    // booked under nothing -- silently, mid-decision.
    const user = userEvent.setup()
    mount({
      proposals,
      templates: [
        { id: 1, name: 'Nur Butterfly', exercise_ids: [57] },
        { id: 2, name: 'Nur Bank', exercise_ids: [55] },
      ],
    })
    const picker = screen.getByLabelText('Zählt bei dir als')
    await user.selectOptions(picker, '1')
    await user.selectOptions(screen.getByLabelText('Butterfly'), 'new')

    expect(picker).toHaveValue('1')
    expect([...picker.querySelectorAll('option')].map((o) => o.textContent))
      .toContain('Nur Butterfly — 0 von 2 Übungen')
  })
})
