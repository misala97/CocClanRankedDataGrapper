import { describe, expect, it } from 'vitest'
import { fold, matches } from './search'

// Each expected value is what features.gym.library.fold returns for the same
// text: the server folds what the query is matched against, so a case that
// drifts here is a search that silently stops finding.
describe('fold', () => {
  it.each([
    ['  Bankdrücken ', 'bankdrucken'],
    ['BANKDRUECKEN', 'bankdrucken'],
    ['Außenrotation', 'aussenrotation'],
    ['T-Bar Row', 't bar row'],
    ['Rudern, eng (Kabel)', 'rudern eng kabel'],
    ['Face Pull 90°', 'face pull 90'],
    ["Farmer's Walk", 'farmer s walk'],
    ['Überzüge', 'uberzuge'],
  ])('%s -> %s', (text, folded) => {
    expect(fold(text)).toBe(folded)
  })
})

describe('matches', () => {
  // Real search texts (library.Entry.search_text).
  const lateral = 'seitheben kurzhantel lateral raise dumbbell lateral raise seitenheben'
  const pulldown = 'latzug kabel lat pulldown lat pulldown kabelzug latziehen latzug breit'

  it('finds by fragments, in any order', () => {
    expect(matches(lateral, 'lat raise')).toBe(true)
    expect(matches(lateral, 'Raise LAT')).toBe(true)
  })

  it('narrows instead of widening: every word has to be there', () => {
    expect(matches(pulldown, 'lat raise')).toBe(false)
  })

  it('matches everything on an empty query', () => {
    expect(matches(pulldown, '   ')).toBe(true)
  })
})
