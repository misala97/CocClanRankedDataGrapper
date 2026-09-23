/**
 * The exercise search, on the contract of features/gym/library.py's `matches`:
 * an exercise is found when every word of the folded query occurs in its
 * `search` text -- its name and aliases, folded on the server by library.fold.
 * Only the query is folded here, so the two folds must agree rule for rule;
 * the cases in search.test.ts are the Python's own outputs.
 */

const UMLAUT: Record<string, string> = { ä: 'a', ö: 'o', ü: 'u' }

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

/** Every word of the query occurs in `search`: in any order, from different
 *  aliases, and a fragment counts ("lat raise" finds Lateral Raise). An empty
 *  query matches everything. */
export function matches(search: string, query: string): boolean {
  return fold(query).split(' ').filter(Boolean).every((word) => search.includes(word))
}
