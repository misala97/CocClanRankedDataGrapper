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
  exercises: [
    { id: 55, name: 'Bankdrücken (Langhantel)' },
    { id: 57, name: 'Butterfly (Maschine)' },
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

  it('names the workout being joined, how long it has run and what is in it', () => {
    const twelveMinutesAgo = new Date(Date.now() - 12 * 60_000).toISOString().slice(0, 19)
    mount({ started_at: twelveMinutesAgo })
    expect(screen.getByText('Michi trainiert seit 12 min')).toBeInTheDocument()
    expect(screen.getByText('Push Day')).toBeInTheDocument()
    expect(screen.getByText('Bankdrücken (Langhantel) · Butterfly (Maschine)'))
      .toBeInTheDocument()
  })

  it('calls a freeform workout just that', () => {
    mount({ session_name: null })
    expect(screen.getByText('Workout')).toBeInTheDocument()
  })

  it('joins in one tap: both partners log the one list, so nothing asks', () => {
    // The exercise selects are gone: a follower's row names the leader's
    // exercise, so there is no answer to give and none to post.
    const { container } = mount()
    expect(screen.queryByRole('combobox')).not.toBeInTheDocument()
    expect(container.querySelector('[name^="match_"]')).toBeNull()
    expect(screen.queryByRole('button', { name: /Zuordnung|Routine/ })).not.toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Mitmachen' }).closest('form'))
      .toHaveAttribute('action', '/gym/shared/7/accept')
    expect(screen.getByRole('button', { name: 'Ablehnen' }).closest('form'))
      .toHaveAttribute('action', '/gym/shared/7/decline')
  })

  it('still offers to join a workout with no exercises yet', () => {
    // The leader may not have added anything before inviting; the follower's
    // session is seeded from the structure as it stands at accept time.
    mount({ exercises: [] })
    expect(screen.getByText(/Noch keine Übungen — sie kommen dazu, sobald Michi/))
      .toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Mitmachen' })).toBeInTheDocument()
  })

  it('says before the button that an empty workout of your own goes away', () => {
    mount({ discards_active: true })
    expect(screen.getByText(/es wird verworfen/)).toBeInTheDocument()
  })

  describe('a refused invite', () => {
    it('states the reason and offers only the way back', () => {
      mount({ refusal: 'Du hast bereits ein laufendes Workout.', exercises: [] })
      expect(screen.getByText('Du hast bereits ein laufendes Workout.'))
        .toBeInTheDocument()
      expect(screen.getByRole('link', { name: 'Zurück' })).toHaveAttribute('href', '/gym')
    })

    it('offers nothing to confirm or decline', () => {
      mount({ refusal: 'Das Workout ist schon vorbei.', exercises: [] })
      expect(screen.queryByRole('button', { name: 'Mitmachen' })).not.toBeInTheDocument()
      expect(screen.queryByRole('button', { name: 'Ablehnen' })).not.toBeInTheDocument()
    })
  })
})

const templates = [
  { id: 1, name: 'Push', exercise_ids: [55, 57] },
  { id: 2, name: 'Ganzkörper', exercise_ids: [55] },
]

describe('the routine picker', () => {
  it('is absent when no routine shares an exercise', () => {
    mount({ templates: [{ id: 3, name: 'Beine', exercise_ids: [99] }] })
    expect(screen.queryByLabelText('Zählt bei dir als')).not.toBeInTheDocument()
    expect(screen.queryByRole('button', { name: /Routine/ })).not.toBeInTheDocument()
  })

  it('ranks routines by how much of the workout they cover', () => {
    mount({ templates })
    const options = [...screen.getByLabelText('Zählt bei dir als')
      .querySelectorAll('option')].map((o) => o.textContent)
    expect(options).toEqual([
      'Keine Routine', 'Push — 2 von 2 Übungen', 'Ganzkörper — 1 von 2 Übungen',
    ])
  })

  it('preselects a routine that covers the whole workout and says so on the card', () => {
    const { container } = mount({ templates })
    expect(screen.getByLabelText('Zählt bei dir als')).toHaveValue('1')
    expect(container.querySelector('.lead')).toHaveTextContent('Zählt als Push.')
    expect(screen.getByRole('button', { name: /Routine ändern/ })).toBeInTheDocument()
  })

  it('preselects the best-covering routine even when it is not perfect', () => {
    // Only a perfect match was preselected, so one exercise the leader added
    // on the way in left the workout filed under no routine at all.
    mount({ templates: [
      { id: 1, name: 'Push', exercise_ids: [55] },
      { id: 2, name: 'Beine', exercise_ids: [99] },
    ] })
    expect(screen.getByLabelText('Zählt bei dir als')).toHaveValue('1')
  })

  it('preselects nothing when the best routine covers under half', () => {
    const { container } = mount({
      exercises: [...base.exercises, { id: 58, name: 'Dips (Maschine)' },
        { id: 59, name: 'Curls (Kurzhantel)' }],
      templates: [{ id: 1, name: 'Push', exercise_ids: [55] }],
    })
    expect(screen.getByLabelText('Zählt bei dir als')).toHaveValue('')
    expect(container.querySelector('.lead')).not.toHaveTextContent('Zählt als')
    expect(screen.getByRole('button', { name: /Routine wählen/ })).toBeInTheDocument()
  })

  it('preselects nothing when two routines tie for best', () => {
    mount({ templates: [
      { id: 1, name: 'Push', exercise_ids: [55] },
      { id: 2, name: 'Push alt', exercise_ids: [57] },
    ] })
    expect(screen.getByLabelText('Zählt bei dir als')).toHaveValue('')
  })

  it('preselects nothing when two routines cover it', () => {
    mount({ templates: [
      { id: 1, name: 'Push', exercise_ids: [55, 57] },
      { id: 2, name: 'Push alt', exercise_ids: [55, 57] },
    ] })
    expect(screen.getByLabelText('Zählt bei dir als')).toHaveValue('')
  })

  it('posts with the accept form while it is folded away', async () => {
    mount({ templates })
    const select = screen.getByLabelText('Zählt bei dir als') as HTMLSelectElement
    expect(select).toHaveAttribute('name', 'template_id')
    expect(select.form).toBe(screen.getByRole('button', { name: 'Mitmachen' }).closest('form'))
    expect(select.closest('[hidden]')).not.toBeNull()
    const toggle = screen.getByRole('button', { name: /Routine ändern/ })
    expect(toggle).toHaveAttribute('aria-expanded', 'false')
    await userEvent.setup().click(toggle)
    expect(toggle).toHaveAttribute('aria-expanded', 'true')
    expect(select.closest('[hidden]')).toBeNull()
  })

  it('drops the card line once the reader picks no routine', async () => {
    const { container } = mount({ templates })
    const user = userEvent.setup()
    await user.click(screen.getByRole('button', { name: /Routine ändern/ }))
    await user.selectOptions(screen.getByLabelText('Zählt bei dir als'), '')
    expect(screen.getByLabelText('Zählt bei dir als')).toHaveValue('')
    expect(container.querySelector('.lead')).not.toHaveTextContent('Zählt als')
  })
})
