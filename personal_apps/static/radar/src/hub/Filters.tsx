// The controls that change which board the server builds.
//
// Every one of these is a server-side filter: changing it is a new request and
// a new cache entry, not a narrowing of the rows already on screen. That is
// why they live here rather than beside the in-page text filter, which does
// the opposite.
//
// The vocabulary is the server's, taken from the payload it echoed back:
// `all_sources` for the feeds it actually offers, `segment_counts` for the
// groups it can filter to. Nothing here invents an option the API would
// refuse -- a control that produces a 400 is a control that strands the
// reader.
import type { BoardPayload, Market, SegmentFilter, Selection } from '../types'
import { sourceLabel } from '../format'

/** api.py WINDOWS. A window outside this is rejected there with a 400. */
const WINDOWS = [1, 4, 12, 24] as const

/** api.py VENUE_FLOORS. */
const VENUES = [
  { value: 1, label: 'Any venue' },
  { value: 2, label: 'More than one venue' },
] as const

const MARKETS: { value: Market; label: string }[] = [
  { value: 'us', label: 'US' },
  { value: 'de', label: 'Germany' },
]

/** The groups the board offers, in the order the server counts them. `all` is
 *  the empty selection -- present-but-empty is how the API is asked for All,
 *  and omitting it would hand the server its own default instead. */
const SEGMENTS: { value: SegmentFilter | 'all'; label: string }[] = [
  { value: 'all', label: 'All companies' },
  { value: 'discover', label: 'Discover' },
  { value: 'large', label: 'Large' },
  { value: 'mid', label: 'Mid' },
  { value: 'micro', label: 'Micro' },
  { value: 'recent_ipo', label: 'Recent IPO' },
  { value: 'fund', label: 'Funds' },
  { value: 'unknown', label: 'Unclassified' },
]

export function Filters({ board, selection, onChange }: {
  board: BoardPayload
  selection: Selection
  onChange: (next: Selection) => void
}) {
  return (
    <div className="rh-filters">
      <label className="rh-field">
        <span>Market</span>
        <select
          value={selection.market}
          onChange={(event) => onChange({
            ...selection, market: event.target.value as Market })}
        >
          {MARKETS.map((market) => (
            <option key={market.value} value={market.value}>{market.label}</option>
          ))}
        </select>
      </label>

      <label className="rh-field">
        <span>Window</span>
        <select
          value={selection.window}
          onChange={(event) => onChange({
            ...selection, window: Number(event.target.value) })}
        >
          {WINDOWS.map((hours) => (
            <option key={hours} value={hours}>
              {hours === 1 ? 'Last hour' : `Last ${hours} hours`}
            </option>
          ))}
        </select>
      </label>

      <label className="rh-field">
        <span>Size</span>
        <select
          value={selection.segments[0] ?? 'all'}
          onChange={(event) => onChange({
            ...selection,
            segments: event.target.value === 'all'
              ? []
              : [event.target.value as SegmentFilter],
          })}
        >
          {SEGMENTS.map((segment) => (
            <option key={segment.value} value={segment.value}>
              {segment.label}
            </option>
          ))}
        </select>
      </label>

      <label className="rh-field">
        <span>Breadth</span>
        <select
          value={selection.minVenues}
          onChange={(event) => onChange({
            ...selection, minVenues: Number(event.target.value) })}
        >
          {VENUES.map((venue) => (
            <option key={venue.value} value={venue.value}>{venue.label}</option>
          ))}
        </select>
      </label>

      <fieldset className="rh-sources">
        <legend>Feeds</legend>
        {board.all_sources.map((source) => {
          // A concrete subreddit selection roots to its feed, so a link
          // naming one sub keeps that feed lit rather than lighting none.
          const on = selection.sources.some(
            (chosen) => chosen.split(':')[0] === source)
          // The last one standing cannot be turned off, and says so rather
          // than absorbing the click. Two subreddits are still one feed, so
          // "last" counts roots and not entries.
          const onlyOne = on && rootsOf(selection.sources).length === 1
          return (
            <label key={source}>
              <input
                type="checkbox"
                checked={on}
                disabled={onlyOne}
                aria-describedby={onlyOne ? FLOOR_ID : undefined}
                onChange={() => onChange({
                  ...selection, sources: toggle(selection.sources, source) })}
              />
              {sourceLabel(source)}
            </label>
          )
        })}
        <p id={FLOOR_ID} className="rh-sources-note">
          At least one feed has to stay selected — a board with no feeds is
          not one the server can build.
        </p>
      </fieldset>
    </div>
  )
}

const FLOOR_ID = 'rh-feeds-floor'

/** The feeds a selection covers, each named once. `reddit:options` and
 *  `reddit:wallstreetbets` are two entries and one feed. */
function rootsOf(sources: string[]): string[] {
  return Array.from(new Set(sources.map((name) => name.split(':')[0] ?? name)))
}

/** Turning a feed off drops it and every concrete venue under it.
 *
 *  Turning the LAST one off returns the selection unchanged. It previously
 *  returned every other feed instead, which is not a refusal: unchecking
 *  Reddit silently produced a Bluesky-and-4chan board, fetched it, and left
 *  the controls showing Reddit unchecked. An empty list is not a board the
 *  server can build, and neither is a substitute for one nobody asked for.
 *
 *  The checkbox is disabled in that state too, so the reader is told rather
 *  than having a click absorbed. This stays as the guarantee: a disabled
 *  input is a UI affordance, not an invariant.
 */
export function toggle(current: string[], source: string): string[] {
  const on = current.some((chosen) => chosen.split(':')[0] === source)
  if (!on) return [...current, source]
  const rest = current.filter((chosen) => chosen.split(':')[0] !== source)
  return rest.length ? rest : current
}
