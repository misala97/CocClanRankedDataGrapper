import { describe, expect, it } from 'vitest'
import { unlikely } from './setInput'

/** "Sicher?" (Q5, G-070): more than twice the lifter's best at the exercise. */
describe('unlikely', () => {
  const best = { weight: 60, reps: 12 }

  it('asks past twice the heaviest weight, and not at twice', () => {
    expect(unlikely({ weight: 120, reps: 8 }, best)).toBeNull()
    expect(unlikely({ weight: 120.5, reps: 8 }, best)).toBe('Sicher? Bisher höchstens 60,0 kg.')
  })

  it('asks past twice the most reps, and not at twice', () => {
    expect(unlikely({ weight: 60, reps: 24 }, best)).toBeNull()
    expect(unlikely({ weight: 60, reps: 25 }, best)).toBe('Sicher? Bisher höchstens 12 Wdh.')
  })

  it('says the unit the exercise is lifted in', () => {
    expect(unlikely({ weight: 130, reps: 8 }, best, 'kg je Seite'))
      .toBe('Sicher? Bisher höchstens 60,0 kg je Seite.')
  })

  it('asks nothing before the first set', () => {
    expect(unlikely({ weight: 999, reps: 999 }, null)).toBeNull()
  })

  it('judges no weight at a bodyweight exercise, only its reps', () => {
    const bodyweight = { weight: 0, reps: 10 }
    expect(unlikely({ weight: 20, reps: 10 }, bodyweight)).toBeNull()
    expect(unlikely({ weight: 0, reps: 21 }, bodyweight)).toBe('Sicher? Bisher höchstens 10 Wdh.')
  })
})
