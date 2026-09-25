import { describe, expect, it } from 'vitest'
import { clearDraft, readDraft, saveDraft, sweepDrafts } from './drafts'

describe('drafts (G-009)', () => {
  it('reads back the numbers dialled in for the set they were dialled for, and only that one', () => {
    saveDraft(1, { bound: '101', weight: 62.5, reps: 8 })
    expect(readDraft(1, '101')).toEqual({ bound: '101', weight: 62.5, reps: 8 })
    expect(readDraft(1, '102')).toBeNull()
    expect(readDraft(2, '101')).toBeNull()
    clearDraft(1)
    expect(readDraft(1, '101')).toBeNull()
  })

  it('keeps a blank as a blank, and takes nothing it cannot read as numbers', () => {
    saveDraft(1, { bound: '101', weight: null, reps: 8 })
    expect(readDraft(1, '101')).toEqual({ bound: '101', weight: null, reps: 8 })
    localStorage.setItem('gym-draft:1', JSON.stringify({ bound: '101', weight: '60', reps: 8 }))
    expect(readDraft(1, '101')).toBeNull()
    localStorage.setItem('gym-draft:1', '{not json')
    expect(readDraft(1, '101')).toBeNull()
  })

  it('sweeps the drafts of other workouts -- only one runs at a time', () => {
    saveDraft(1, { bound: '101', weight: 60, reps: 8 })
    saveDraft(2, { bound: '201', weight: 40, reps: 10 })
    localStorage.setItem('unrelated', 'x')
    sweepDrafts(2)
    expect(readDraft(1, '101')).toBeNull()
    expect(readDraft(2, '201')).not.toBeNull()
    expect(localStorage.getItem('unrelated')).toBe('x')
  })
})
