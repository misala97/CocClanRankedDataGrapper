/**
 * The one search (walkthrough G-145): features/gym/library.py's `fold`,
 * `matches` and `find`, rule for rule. The add sheet, Übungen and Verlauf
 * all search with it -- four matchers used to fold four ways, so a word that
 * found an exercise on one page found nothing on the next.
 *
 * Each row's text is folded on the server (library.fold); only the query is
 * folded here, so the two folds must agree. The cases in
 * __fixtures__/search-cases.json are the Python's own answers
 * (scripts/make_search_cases.py), and search.test.ts holds this file to them.
 */

const UMLAUT: Record<string, string> = { ä: 'a', ö: 'o', ü: 'u' }

/** library.FUZZY_FROM: a query word this long may be one typo off. A shorter
 *  one stays exact -- one edit is most of a four-letter word. Letters only:
 *  "31.07" one edit off is 01.07., 03.07., 13.07. and 31.08. */
export const FUZZY_FROM = 5

/** library._may_be_a_typo. \p{L} is the set Python's str.isalpha tests. */
const mayBeATypo = (word: string) => word.length >= FUZZY_FROM && /^\p{L}+$/u.test(word)

/** library.fold: casefolded, ä/ae -> a (likewise ö and ü, and ß -> ss),
 *  punctuation to spaces, runs of space to one. */
export function fold(text: string): string {
  return text
    .toLowerCase()
    // Python's casefold does this one itself; toLowerCase leaves ß alone.
    .replace(/ß/g, 'ss')
    .replace(/ae/g, 'a').replace(/oe/g, 'o').replace(/ue/g, 'u')
    .replace(/[äöü]/g, (c) => UMLAUT[c]!)
    .replace(/[-,()°']/g, ' ')
    .split(/\s+/).filter(Boolean).join(' ')
}

const words = (query: string) => fold(query).split(' ').filter(Boolean)

/** Whether `query` asks anything: one that folds to nothing ("-") is no
 *  query, and a page shows what it shows without one. */
export function isQuery(query: string): boolean {
  return words(query).length > 0
}

const hasWords = (search: string, queryWords: string[], typos = false) =>
  queryWords.every((word) => search.includes(word)
    || (typos && mayBeATypo(word) && oneEditOff(word, search)))

/** library.matches: every word of the folded query occurs in `search`, a
 *  folded text -- in any order, from different aliases, and a fragment counts
 *  ("lat raise" finds Lateral Raise). With `typos`, a word of FUZZY_FROM
 *  letters or more may be one edit off. No query matches everything. */
export function matches(search: string, query: string, typos = false): boolean {
  return hasWords(search, words(query), typos)
}

/** Folded texts kept apart, as library.fold_apart keeps them: a query's
 *  words may come from any of them, its whole phrase only from one. */
export const apart = (texts: readonly string[]) => texts.join('\n')

/** How library.find found what it found: the whole query as one run, every
 *  word somewhere, or with a word one typo off. */
export type Tier = 'phrase' | 'words' | 'typos'

export interface Found<T> {
  hits: T[]
  tier: Tier
}

/** library.find: the rows by the first of three tiers that finds any --
 *  the whole query as one run inside one of a row's texts ("Push 2" is the
 *  workout Push 2, not every Push of 2026), every word anywhere, every word
 *  with the long ones allowed a typo. Typos only as the fallback: one edit
 *  from "bench" is "rench", and French Press is no bench press. No query is
 *  every row. */
export function find<T>(rows: readonly T[], query: string, text: (row: T) => string): Found<T> {
  const phrase = fold(query)
  const queryWords = phrase.split(' ').filter(Boolean)
  if (queryWords.length === 0) return { hits: [...rows], tier: 'words' }
  const runs = rows.filter((row) => text(row).includes(phrase))
  if (runs.length > 0) return { hits: runs, tier: 'phrase' }
  const all = rows.filter((row) => hasWords(text(row), queryWords))
  if (all.length > 0 || !queryWords.some(mayBeATypo)) return { hits: all, tier: 'words' }
  return { hits: rows.filter((row) => hasWords(text(row), queryWords, true)), tier: 'typos' }
}

/** Whether `search`, one part of a row, is what `find` found the row by:
 *  it holds the whole phrase, when that is how; else any word of it, a typo
 *  off when that is how. What a row marks as the part of it that matched. */
export function mentions(search: string, query: string, tier: Tier): boolean {
  if (tier === 'phrase') return search.includes(fold(query))
  return words(query).some((word) => hasWords(search, [word], tier === 'typos'))
}

/** library._one_edit_off: whether some stretch of `text` is at most one edit
 *  from `word` -- a letter added, dropped or changed, or two neighbours
 *  swapped. Sellers' dynamic programme with the swap of optimal string
 *  alignment; `above[j]` is the fewest edits turning the word so far into a
 *  stretch ending at j. That minimum never falls from one letter to the
 *  next, so past one edit the search stops. */
function oneEditOff(word: string, text: string): boolean {
  let before = new Int32Array(text.length + 1)
  let above = new Int32Array(text.length + 1)
  for (let i = 1; i <= word.length; i++) {
    const row = new Int32Array(text.length + 1)
    row[0] = i
    let least = i
    for (let j = 1; j <= text.length; j++) {
      let best = Math.min(above[j]! + 1, row[j - 1]! + 1,
        above[j - 1]! + (word[i - 1] === text[j - 1] ? 0 : 1))
      if (i > 1 && j > 1 && word[i - 1] === text[j - 2] && word[i - 2] === text[j - 1]) {
        best = Math.min(best, before[j - 2]! + 1)
      }
      row[j] = best
      if (best < least) least = best
    }
    if (least > 1) return false
    before = above
    above = row
  }
  return true
}
