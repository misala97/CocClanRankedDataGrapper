/** Over a search's rows when nothing matched as typed and these are a typo
 *  away (search.find's 'typos' tier). Unlabelled, a list of near misses read
 *  as if the search matched something else than what was typed (B9 review).
 *  Übungen, Verlauf and the add sheet all say it the same way. */
export function NearMisses({ query }: { query: string }) {
  return (
    <p className="search-near" role="status">
      {`Kein genauer Treffer für „${query.trim()}“ – ähnlich geschrieben:`}
    </p>
  )
}
