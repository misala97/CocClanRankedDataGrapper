// The list's ordering, as a control rather than as a row of column headers.
//
// The table has clickable headers; the candidate rail has no header row and a
// phone has no room for one, so both need this. It is the SAME ordering --
// chatterSort owns every rule about direction, ties and where a null goes --
// and this is one more way to ask for it, not a second implementation of it.
import { SORT_LABELS, nextSort } from './chatterSort'
import type { ChatterSort, SortKey } from './chatterSort'

/** Derived, not restated. A second hand-written list of the keys would
 *  type-check perfectly while silently omitting a key added to SORT_LABELS,
 *  and the omission would show up as a sort the rail and the phone simply do
 *  not offer. Object key order is insertion order, which is the order
 *  chatterSort declares them in and the order the table's headers use. */
const SORT_KEYS = Object.keys(SORT_LABELS) as SortKey[]

export function SortPicker({ sort, onSort, className = 'rh-sortpicker',
                            idPrefix = 'rh-sort' }: {
  sort: ChatterSort | null
  onSort: (next: ChatterSort | null) => void
  className?: string
  /** Two of these can be on one page -- the rail's and the table's -- and a
   *  duplicated `id` would point both labels at the same select. */
  idPrefix?: string
}) {
  const selectId = `${idPrefix}-select`
  return (
    <div className={className}>
      <label className="rh-field" htmlFor={selectId}>
        <span>Sort by</span>
        <select
          id={selectId}
          value={sort ? sort.key : 'radar'}
          onChange={(event) => {
            const value = event.target.value
            onSort(value === 'radar'
              ? null
              : nextSort(null, value as SortKey))
          }}
        >
          <option value="radar">Radar order</option>
          {SORT_KEYS.map((key) => (
            <option key={key} value={key}>{SORT_LABELS[key]}</option>
          ))}
        </select>
      </label>
      {/* The visible text is the CURRENT order and the accessible name has
          to CONTAIN it -- WCAG 2.5.3, the same rule the row disclosures were
          corrected for. It read "Highest first" and answered to "Sort lowest
          first", so voice control had no handle on it at all and the two
          halves flatly contradicted each other. Now the name leads with what
          is written on it and then says what pressing it does. Disabled with
          no sort, and then it claims no order rather than asserting one that
          is not in effect. */}
      <button
        type="button"
        className="rh-button rh-sortdir"
        disabled={!sort}
        aria-label={sort
          ? `${sort.dir === 'asc' ? 'Lowest first' : 'Highest first'}`
            + ` — sort ${sort.dir === 'asc' ? 'highest' : 'lowest'} first instead`
          : 'Sort direction'}
        onClick={() => sort && onSort({
          key: sort.key, dir: sort.dir === 'asc' ? 'desc' : 'asc' })}
      >
        {!sort ? 'Direction'
          : sort.dir === 'asc' ? 'Lowest first' : 'Highest first'}
      </button>
    </div>
  )
}
