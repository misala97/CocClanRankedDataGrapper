import { render, screen } from '@testing-library/react'
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
