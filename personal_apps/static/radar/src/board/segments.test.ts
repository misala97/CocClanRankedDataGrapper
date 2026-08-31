import { describe, expect, it } from 'vitest'
import { toggleSegment } from './Controls'

describe('picking segments', () => {
  it('adds a second one rather than replacing the first', () => {
    /* Michi's ask: "small and micro at once" (Small being Discover's old
       name). The chips were a radio group and every click threw the previous
       selection away. */
    expect(toggleSegment(['discover'], 'micro')).toEqual(['discover', 'micro'])
  })

  it('turns one off without disturbing the others', () => {
    expect(toggleSegment(['discover', 'micro', 'large'], 'micro'))
      .toEqual(['discover', 'large'])
  })

  it('lands on All when the last one is turned off', () => {
    /* Zero selected and "no filter" are the same query. A strip where every
       chip is off while rows are still showing reads as broken. */
    expect(toggleSegment(['discover'], 'discover')).toEqual([])
  })

  it('clears everything when All is picked', () => {
    /* `all` is not a seventh segment, it is the absence of a filter -- so it
       replaces the selection instead of joining it. */
    expect(toggleSegment(['discover', 'large'], null)).toEqual([])
  })

  it('does not add the same segment twice', () => {
    const once = toggleSegment([], 'mid')
    expect(toggleSegment(once, 'mid')).toEqual([])
  })
})
