import { describe, expect, it } from 'vitest'
import cases from './__fixtures__/search-cases.json'
import { FUZZY_FROM, apart, find, fold, isQuery, matches, mentions } from './search'

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
  const list = cases.library as Record<string, string>
  const lateral = list.dumbbell_lateral_raise!
  const pulldown = list.cable_lat_pulldown!

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

// The Python's own answers (scripts/make_search_cases.py), over the list's
// real search texts: the same query finds the same exercises here as there.
describe('search.ts agrees with library.py (G-145)', () => {
  const texts = Object.entries(cases.library as Record<string, string>)

  it('folds as library.fold does', () => {
    for (const [text, folded] of cases.fold) expect(fold(text!), text).toBe(folded)
  })

  it('types a word as a typo from the same length', () => {
    expect(FUZZY_FROM).toBe(cases.fuzzy_from)
  })

  it.each(cases.queries.map((c) => [c.query, c] as const))('finds what library.find finds: %s',
    (_query, { query, tier, hits }) => {
      const found = find(texts, query, ([, search]) => search)
      expect(found.hits.map(([key]) => key)).toEqual(hits)
      expect(found.tier).toBe(tier)
    })

  // Verlauf rows as HistoryPage searches them: the server's name and date
  // words, and each exercise's list text, apart.
  const library = cases.library as Record<string, string>
  const rows = Object.entries(cases.history).map(([row, { search, exercises }]) =>
    [row, apart([search, ...exercises.map((key) => library[key]!)])] as const)

  it.each(cases.history_queries.map((c) => [c.query, c] as const))(
    'finds the Verlauf rows library.find finds: %s', (_query, { query, tier, hits }) => {
      const found = find(rows, query, ([, search]) => search)
      expect(found.hits.map(([row]) => row)).toEqual(hits)
      expect(found.tier).toBe(tier)
    })
})

describe('find', () => {
  const push2 = apart(['push 2', '31.07.2026 juli 2026'])
  const push = apart(['push', '23.09.2026 september 2026'])
  const same = (text: string) => text

  it('takes the whole query as one run first, never across two texts', () => {
    // Joined by a space, "push 2" ran from Push's name into its date.
    expect(find([push2, push], 'Push 2', same)).toEqual({ hits: [push2], tier: 'phrase' })
    expect(find([push2, push], 'push 23.09', same)).toEqual({ hits: [push], tier: 'words' })
  })

  it('lets no date be a typo of another', () => {
    expect(find([push2], '31.06', same)).toEqual({ hits: [], tier: 'words' })
    expect(find(['kniebeugen langhantel'], 'kniebeigen', same))
      .toEqual({ hits: ['kniebeugen langhantel'], tier: 'typos' })
  })

  it('is every row without a query', () => {
    expect(find([push2, push], ' - ', same)).toEqual({ hits: [push2, push], tier: 'words' })
  })
})

describe('a query that folds to nothing', () => {
  it('is no query', () => {
    expect(isQuery('-')).toBe(false)
    expect(isQuery(' , ')).toBe(false)
    expect(isQuery('b')).toBe(true)
  })
})

describe('mentions', () => {
  it('says whether any word of the query is in the text', () => {
    expect(mentions('bankdrucken langhantel', 'bank juli', 'words')).toBe(true)
    expect(mentions('latzug kabel', 'bank juli', 'words')).toBe(false)
    expect(mentions('bankdrucken langhantel', 'bankdruken', 'typos')).toBe(true)
    expect(mentions('bankdrucken langhantel', 'bankdruken', 'words')).toBe(false)
  })

  it('wants the whole phrase when that is how the row was found', () => {
    // A workout found by "Bankdrücken Kurzhantel" marks that exercise, not
    // the barbell bench and the dumbbell raise beside it.
    const query = 'Bankdrücken Kurzhantel'
    expect(mentions('bankdrucken kurzhantel\ndumbbell bench press', query, 'phrase')).toBe(true)
    expect(mentions('bankdrucken langhantel\nbench press', query, 'phrase')).toBe(false)
    expect(mentions('seitheben kurzhantel\nlateral raise', query, 'phrase')).toBe(false)
    expect(mentions('seitheben kurzhantel\nlateral raise', query, 'words')).toBe(true)
  })
})
