import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it } from 'vitest'
import { SharedConfirmPage } from './SharedConfirmPage'
import type { SharedConfirmPayload } from './types'

const base: SharedConfirmPayload = {
  shared_id: 7,
  leader_name: 'Michi',
  session_name: 'Push Day',
  started_at: null,
  refusal: null,
  discards_active: false,
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

  it('preselects an exact match and offers every candidate anyway', async () => {
    // Exact matches are already resolved and say so; only the ambiguous ones
    // carry a real decision, because asking seven times per shared workout
    // would make the common path the annoying one.
    mount()
    const exact = screen.getByLabelText('Bankdrücken')
    expect(exact).toHaveValue('55')
    await userEvent.setup().click(screen.getByRole('button', { name: /Zuordnung ändern/ }))
    expect(screen.getAllByRole('option').map((o) => o.textContent))
      .toContain('Bankdrücken (Kurzhantel)')
  })

  it('names the workout being joined and how long it has run', () => {
    const twelveMinutesAgo = new Date(Date.now() - 12 * 60_000).toISOString().slice(0, 19)
    mount({ started_at: twelveMinutesAgo })
    expect(screen.getByText('Michi trainiert seit 12 min')).toBeInTheDocument()
    expect(screen.getByText('Push Day')).toBeInTheDocument()
    expect(screen.getByText('Bankdrücken · Butterfly')).toBeInTheDocument()
  })

  it('calls a freeform workout just that', () => {
    mount({ session_name: null })
    expect(screen.getByText('Workout')).toBeInTheDocument()
  })

  it('asks only about the exercise with no same-named one of yours', () => {
    const { container } = mount()
    const card = container.querySelector('.lead')!
    expect(card).toHaveTextContent('Eine Übung heißt bei dir anders — welche ist es?')
    expect(card).toContainElement(screen.getByLabelText('Butterfly'))
    expect(card).not.toContainElement(screen.getByLabelText('Bankdrücken'))
    expect(card).toHaveTextContent('Die andere gibt es bei dir.')
  })

  it('confirms a fully matched workout in one line, above the button', () => {
    mount({ proposals: [base.proposals[0]!] })
    expect(screen.queryByText(/heißt bei dir anders/)).not.toBeInTheDocument()
    expect(screen.getByText('Die Übung gibt es bei dir.')).toBeInTheDocument()
  })

  it('keeps the matched selects in the accept form while they are folded away', async () => {
    mount()
    const exact = screen.getByLabelText('Bankdrücken') as HTMLSelectElement
    expect(exact.form).toBe(screen.getByRole('button', { name: 'Mitmachen' }).closest('form'))
    expect(exact.closest('[hidden]')).not.toBeNull()
    const toggle = screen.getByRole('button', { name: /Zuordnung ändern/ })
    expect(toggle).toHaveAttribute('aria-expanded', 'false')
    await userEvent.setup().click(toggle)
    expect(toggle).toHaveAttribute('aria-expanded', 'true')
    expect(exact.closest('[hidden]')).toBeNull()
  })

  it('offers only exercises of the list, the best candidate when nothing matched', () => {
    // No creating one instead: the list is everyone's.
    mount()
    const select = screen.getByLabelText('Butterfly') as HTMLSelectElement
    expect(select).toHaveValue('57')
    expect([...select.options].map((o) => o.value)).toEqual(['57'])
    expect(screen.queryByText(/anlegen/i)).not.toBeInTheDocument()
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
// can exercise the unmatched fallback. Coverage math needs both exercises
// matched going in -- otherwise every "starts fully covered" case here would
// be indistinguishable from "nothing is covered". Butterfly has a second
// candidate so the recount tests have somewhere to switch it to.
const proposals = [
  {
    name: 'Bankdrücken', leader_exercise_id: 10, exact_id: 55,
    candidates: [[55, 'Bankdrücken'], [56, 'Bankdrücken (Kurzhantel)']] as [number, string][],
  },
  {
    name: 'Butterfly', leader_exercise_id: 11, exact_id: 57,
    candidates: [[57, 'Reverse Fly (Machine)'], [60, 'Butterfly (Maschine)']] as [number, string][],
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

  it('preselects the best-covering routine even when it is not perfect', () => {
    // Only a perfect match was preselected, so one exercise the leader added
    // on the way in left the workout filed under no routine at all.
    mount({ proposals, templates: [
      { id: 1, name: 'Push', exercise_ids: [55] },
      { id: 2, name: 'Beine', exercise_ids: [99] },
    ] })
    expect(screen.getByLabelText('Zählt bei dir als')).toHaveValue('1')
  })

  it('preselects nothing when the best routine covers under half', () => {
    mount({
      proposals: [...proposals,
        { name: 'Dips', leader_exercise_id: 12, exact_id: 58, candidates: [[58, 'Dips']] },
        { name: 'Curls', leader_exercise_id: 13, exact_id: 59, candidates: [[59, 'Curls']] }],
      templates: [{ id: 1, name: 'Push', exercise_ids: [55] }],
    })
    expect(screen.getByLabelText('Zählt bei dir als')).toHaveValue('')
  })

  it('preselects nothing when two routines tie for best', () => {
    mount({ proposals, templates: [
      { id: 1, name: 'Push', exercise_ids: [55] },
      { id: 2, name: 'Push alt', exercise_ids: [57] },
    ] })
    expect(screen.getByLabelText('Zählt bei dir als')).toHaveValue('')
  })

  it('says before the button that an empty workout of your own goes away', () => {
    mount({ discards_active: true })
    expect(screen.getByText(/es wird verworfen/)).toBeInTheDocument()
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
    await user.selectOptions(screen.getByLabelText('Butterfly'), '60')
    const options = [...screen.getByLabelText('Zählt bei dir als')
      .querySelectorAll('option')].map((o) => o.textContent)
    expect(options).toContain('Push — 1 von 2 Übungen')
  })

  it('counts an unmatched proposal under the candidate its select shows', () => {
    // What the form posts is what the select shows; counting anything else
    // would claim coverage the accept route does not deliver.
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
    expect(screen.getByLabelText('Bankdrücken')).toHaveValue('55')
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
    await user.selectOptions(screen.getByLabelText('Butterfly'), '60')

    expect(picker).toHaveValue('1')
    expect([...picker.querySelectorAll('option')].map((o) => o.textContent))
      .toContain('Nur Butterfly — 0 von 2 Übungen')
  })
})
