import { describe, expect, it } from 'vitest'
import { morphFrom } from './vt'

const click = (el: HTMLElement) => ({ currentTarget: el }) as never

function row(name: string) {
  const a = document.createElement('a')
  const span = document.createElement('span')
  span.className = 'row__name'
  span.textContent = name
  a.appendChild(span)
  document.body.appendChild(a)
  return { a, span }
}

describe('morphFrom', () => {
  it('names the text element inside the tapped row', () => {
    const { a, span } = row('Bankdrücken')
    morphFrom('ex')(click(a))
    expect(span.style.getPropertyValue('view-transition-name')).toBe('ex')
    expect(a.style.getPropertyValue('view-transition-name')).toBe('')
  })

  it('falls back to the tapped element when nothing matches', () => {
    const a = document.createElement('a')
    document.body.appendChild(a)
    morphFrom('ex')(click(a))
    expect(a.style.getPropertyValue('view-transition-name')).toBe('ex')
  })

  it('names the tapped element itself with a null selector', () => {
    const { a, span } = row('Dips')
    morphFrom('ex', null)(click(a))
    expect(a.style.getPropertyValue('view-transition-name')).toBe('ex')
    expect(span.style.getPropertyValue('view-transition-name')).toBe('')
  })

  it('clears the previously named row first', () => {
    // The bfcache case: a back-navigation restores the mutated DOM, so the
    // row tapped LAST time is still named. Two elements with one name make
    // the browser skip the morph entirely.
    const first = row('Bankdrücken')
    const second = row('Dips')
    morphFrom('ex')(click(first.a))
    morphFrom('ex')(click(second.a))
    expect(first.span.style.getPropertyValue('view-transition-name')).toBe('')
    expect(second.span.style.getPropertyValue('view-transition-name')).toBe('ex')
    expect(document.querySelectorAll('[data-vt]')).toHaveLength(1)
  })

  it('clears across names, not only its own', () => {
    // Start page names 'ex' on stalls and 'session' on recent workouts; a
    // leftover from either would still be a stale snapshot layer.
    const stall = row('Bankdrücken')
    const workout = row('Push Day')
    morphFrom('ex')(click(stall.a))
    morphFrom('session')(click(workout.a))
    expect(stall.span.style.getPropertyValue('view-transition-name')).toBe('')
    expect(workout.span.style.getPropertyValue('view-transition-name')).toBe('session')
  })
})
