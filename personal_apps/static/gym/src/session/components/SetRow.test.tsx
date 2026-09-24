import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it, vi } from 'vitest'
import { SetRow } from './SetRow'
import type { LiveSet } from '../types'

const aSet = (over: Partial<LiveSet> = {}): LiveSet => ({
  id: 100, weight: 62.5, reps: 8, completed: false, base_weight: null, ...over,
})

const props = {
  ordinal: 1, isRecord: false, isNext: false, isUnilateral: false,
  onToggle: vi.fn(),
}

describe('SetRow', () => {
  it('shows weight times reps in German', () => {
    // Every chip shows the same weight-times-reps: a filled chip is the result
    // it was logged at, an outlined chip is the plan it is prefilled for.
    // Without the plan the lifter at the machine had to remember last week's
    // numbers just to decide whether to add weight.
    render(<SetRow {...props} set={aSet()} />)
    expect(screen.getByRole('button')).toHaveTextContent('62,5 × 8')
  })

  it('names a set still waiting for its numbers instead of inventing some', async () => {
    // A blank plan (an exercise with no history) reads "Satz 2", and tapping
    // it picks it like any open chip -- the steppers decide the numbers.
    const user = userEvent.setup()
    const onToggle = vi.fn()
    render(<SetRow {...props} ordinal={2} isNext onToggle={onToggle}
      set={aSet({ weight: null, reps: null })} />)
    const chip = screen.getByRole('button', { name: /^Satz 2, noch ohne Zahlen/ })
    expect(chip).toHaveTextContent(/^Satz 2$/)
    expect(chip.className).toBe('set is-blank is-now')

    await user.click(chip)
    expect(onToggle).toHaveBeenCalledWith(100, true)
  })

  it('says which number a half-blank set still lacks', () => {
    render(<SetRow {...props} set={aSet({ weight: 40, reps: null })} />)
    expect(screen.getByRole('button', { name: /^Satz 1, noch ohne Wdh\./ }))
      .toHaveTextContent(/^Satz 1$/)
  })

  it('is plain when open, filled when done, gold when a record', () => {
    const { rerender } = render(<SetRow {...props} set={aSet()} />)
    expect(screen.getByRole('button').className).toBe('set')

    rerender(<SetRow {...props} set={aSet({ completed: true })} />)
    expect(screen.getByRole('button')).toHaveClass('is-done')

    rerender(<SetRow {...props} set={aSet({ completed: true })} isRecord />)
    expect(screen.getByRole('button')).toHaveClass('is-record')
    expect(screen.getByRole('button')).not.toHaveClass('is-done')
  })

  it('ticks a logged set, so it reads as settled rather than loud', () => {
    // G-112: the filled done chip outweighed the next set, and in dark it was
    // the brightest thing on the card. It is a tint now, and the tick says
    // "done" where the fill used to.
    const { rerender } = render(<SetRow {...props} set={aSet({ completed: true })} />)
    expect(screen.getByRole('button').querySelector('svg')).not.toBeNull()
    expect(screen.getByRole('button')).toHaveTextContent('62,5 × 8')

    rerender(<SetRow {...props} set={aSet()} isNext />)
    expect(screen.getByRole('button').querySelector('svg')).toBeNull()
  })

  it('marks the set you are about to do', () => {
    render(<SetRow {...props} set={aSet()} isNext />)
    expect(screen.getByRole('button')).toHaveClass('is-now')
  })

  it('gives a record its own accessible name', () => {
    // The two fills are 1.03:1 apart in the dark theme and the chip's label
    // used to be byte-identical to a logged set's, so the rarest state in the
    // app did not exist for a screen reader at all.
    render(<SetRow {...props} set={aSet({ completed: true })} isRecord ordinal={2} />)
    const label = screen.getByRole('button').getAttribute('aria-label')!
    expect(label).toContain('Satz 2')
    expect(label).toContain('Rekord')
    expect(label).toContain('antippen zum Zurücksetzen')
  })

  it('distinguishes a done set from a planned one by name', () => {
    const { rerender } = render(
      <SetRow {...props} set={aSet({ completed: true })} ordinal={3} />)
    expect(screen.getByRole('button').getAttribute('aria-label'))
      .toContain('Satz 3 erledigt')

    rerender(<SetRow {...props} set={aSet()} ordinal={3} />)
    const open = screen.getByRole('button').getAttribute('aria-label')!
    expect(open).toContain('Satz 3, geplant')
    expect(open).not.toContain('Zurücksetzen')
  })

  it('says per side for a unilateral exercise', () => {
    render(<SetRow {...props} set={aSet()} isUnilateral />)
    expect(screen.getByRole('button').getAttribute('aria-label'))
      .toContain('je Seite')
  })

  it('asks for the state it wants, not for a flip', () => {
    // The chip states the state it wants -- see gym_toggle_set_complete. A
    // done chip un-logs, an open chip logs, and the server is told which
    // rather than being asked to invert whatever it currently has.
    const onToggle = vi.fn()
    const { rerender } = render(
      <SetRow {...props} set={aSet()} onToggle={onToggle} />)
    const user = userEvent.setup()

    return (async () => {
      await user.click(screen.getByRole('button'))
      expect(onToggle).toHaveBeenLastCalledWith(100, true)

      rerender(<SetRow {...props} set={aSet({ completed: true })} onToggle={onToggle} />)
      await user.click(screen.getByRole('button'))
      expect(onToggle).toHaveBeenLastCalledWith(100, false)
    })()
  })

  it('cannot be tapped twice while its write is in flight', async () => {
    // The confirm target is in the thumb zone and its answer arrives a round
    // trip later, so a second tap before the first resolves is what a sweaty
    // hand does -- not an edge case.
    const user = userEvent.setup()
    const onToggle = vi.fn()
    render(<SetRow {...props} set={aSet()} onToggle={onToggle} busy />)

    await user.click(screen.getByRole('button'))
    expect(onToggle).not.toHaveBeenCalled()
  })
})
