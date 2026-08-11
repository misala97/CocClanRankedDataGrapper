import { render } from '@testing-library/react'
import { act } from 'react'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { SessionTotals } from './SessionTotals'

const mount = (volume: number) => render(
  <SessionTotals volume={volume} setsDone={1} startedAt="2026-08-10T17:00:00" />)
const again = (volume: number) => (
  <SessionTotals volume={volume} setsDone={2} startedAt="2026-08-10T17:00:00" />)

describe('SessionTotals count-up', () => {
  afterEach(() => { vi.unstubAllGlobals() })

  it('jumps instantly under prefers-reduced-motion', () => {
    vi.stubGlobal('matchMedia', vi.fn(() => ({ matches: true })))
    const { container, rerender } = mount(1000)
    rerender(again(1500))
    expect(container.querySelector('.grew__num')!.textContent).toBe('1.500')
    expect(container.querySelector('.is-counting')).toBeNull()
  })

  it('counts up to the new total, lit while it runs, and settles', () => {
    // The thesis motion (4.1): the port shipped .is-counting with no writer,
    // so the one number that grows just jumped. This pins the writer.
    vi.stubGlobal('matchMedia', vi.fn(() => ({ matches: false })))
    let clock = 0
    vi.stubGlobal('performance', { now: () => clock })
    const frames: FrameRequestCallback[] = []
    vi.stubGlobal('requestAnimationFrame',
      (cb: FrameRequestCallback) => { frames.push(cb); return frames.length })
    vi.stubGlobal('cancelAnimationFrame', () => {})

    const { container, rerender } = mount(1000)
    clock = 50
    rerender(again(1500))
    // Mid-tween: the digits are lit and a frame is scheduled.
    expect(container.querySelector('.grew__num')).toHaveClass('is-counting')
    expect(frames.length).toBeGreaterThan(0)

    // rAF stamps the frame's start, which can PREDATE the effect's t0 -- the
    // count must clamp at `from` instead of easing below it (it flashed
    // "-120" on its way to 960 in the first live run).
    act(() => { frames.shift()!(0) })
    expect(container.querySelector('.grew__num')!.textContent).toBe('1.000')

    // One frame past COUNT_MS finishes the tween.
    act(() => { clock = 400; frames.shift()!(clock) })
    expect(container.querySelector('.grew__num')!.textContent).toBe('1.500')
    expect(container.querySelector('.is-counting')).toBeNull()
  })
})
