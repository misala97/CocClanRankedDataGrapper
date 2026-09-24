import { render, screen } from '@testing-library/react'
import { act } from 'react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { RecordTakeover } from './RecordTakeover'
import type { Celebration } from '../useRecordTakeover'

/* jsdom has no canvas 2d context, so confetti.play() returns its no-op and
 * these exercise the slab: the copy, the count, the exit and the dismiss. The
 * particles are verified in the browser, not here. */

const celebration = (over: Partial<Celebration> = {}): Celebration => ({
  setId: 101,
  record: {
    kind: 'e1rm', value: 82.5, previous: 80.0,
    previous_at: '2026-09-09T18:30:00',
  },
  exerciseName: 'Bankdrücken',
  ordinal: 3,
  position: 3,
  ...over,
})

const mount = (over: Partial<Celebration> = {}, onDismiss = () => {}) =>
  render(<RecordTakeover celebration={celebration(over)} onDismiss={onDismiss} />)

beforeEach(() => {
  vi.useFakeTimers()
  vi.stubGlobal('matchMedia', vi.fn(() => ({ matches: true })))
})
afterEach(() => {
  vi.useRealTimers()
  vi.unstubAllGlobals()
})

describe('RecordTakeover', () => {
  it('names the record an e1RM record, the only kind there is (D3)', () => {
    mount()
    expect(screen.getByText('Neuer e1RM-Rekord')).toBeInTheDocument()
    expect(screen.queryByText(/Gewichts-Rekord/)).not.toBeInTheDocument()
  })

  it('says which set of which exercise it was', () => {
    mount()
    expect(screen.getByText('Bankdrücken · Satz 3')).toBeInTheDocument()
  })

  it('states what the record beat, and when', () => {
    mount()
    // Day and month only, like the Vorgabe line on the same panel.
    expect(screen.getByText('vorher 80,0 kg · 09.09. · als 3. Übung')).toBeInTheDocument()
  })

  it('is announced rather than being silent decoration', () => {
    mount()
    expect(screen.getByRole('status')).toBeInTheDocument()
  })

  it('shows the true number immediately under prefers-reduced-motion', () => {
    // matchMedia is stubbed to `matches: true` above: no tween, so the number
    // must already be the record and not the weight it beat.
    const { container } = mount()
    act(() => { vi.advanceTimersByTime(200) })
    expect(container.querySelector('.record-takeover__num')!.textContent).toBe('82,5')
  })

  it('starts from the beaten number when motion is allowed', () => {
    vi.stubGlobal('matchMedia', vi.fn(() => ({ matches: false })))
    const { container } = mount()
    // Before the count is even kicked off, the slab reads the OLD best --
    // seeding it at the new value would show the answer and animate nothing.
    expect(container.querySelector('.record-takeover__num')!.textContent).toBe('80,0')
  })

  it('begins leaving before it is unmounted, so it fades instead of cutting', () => {
    const { container } = mount()
    expect(container.querySelector('.record-takeover')!.className)
      .not.toContain('is-out')
    act(() => { vi.advanceTimersByTime(820) })
    expect(container.querySelector('.record-takeover')!.className).toContain('is-out')
  })

  it('dismisses on a tap', () => {
    const onDismiss = vi.fn()
    mount({}, onDismiss)
    screen.getByRole('status').click()
    expect(onDismiss).toHaveBeenCalledOnce()
  })
})
