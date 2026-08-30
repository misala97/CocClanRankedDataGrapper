import { Fragment } from 'react'

import { SEGMENT_ORDER, segmentLabel, sourceLabel } from '../format'

import type { BoardPayload, SegmentFilter, Selection } from '../types'

/** Add or remove one segment. `null` is the All tab and clears everything.
 *
 *  Turning the LAST tab off lands on All rather than on an empty board.
 *  Zero selected and "no filter" are the same query, and a strip where
 *  every tab is off but rows are still showing reads as broken.
 */
export function toggleSegment(current: SegmentFilter[],
                              value: SegmentFilter | null): SegmentFilter[] {
  if (value === null) return []
  return current.includes(value)
    ? current.filter((name) => name !== value)
    : [...current, value]
}

const WINDOWS = [1, 4, 24]

/** Where the segment strip breaks. The five size tiers on one line, the
 *  three that are not sizes on the next: 2026-08-30 the eight tabs with
 *  counts measured 432px of text against a 380px line, so they wrap --
 *  and an uncontrolled wrap orphaned `Funds` alone under seven peers.
 *  A deliberate break beats a coincidental one, and it keeps every tab
 *  in a fixed place between loads. */
const SEGMENT_BREAK_AFTER = 'micro'

/** The instrument strip: every scope choice as a flat text tab.
 *
 *  This replaced a labelled settings form (five uppercase gutter labels over
 *  pill chips) 2026-08-30. The labels said what the tabs already say, and the
 *  pill treatment made twelve rarely-touched controls the loudest thing on
 *  the pane. A pressed tab is ink with a violet underline; an unpressed one
 *  is dim text. Nothing else.
 *
 *  Fixed slots throughout, as before: a segment whose count is zero dims
 *  rather than disappearing, so the strip never changes shape between loads
 *  and nothing moves under the cursor.
 *
 *  Sources are peers. There is no primary and no default-off: the strip
 *  starts with every configured source on, and turning one off is a question
 *  the reader asks ("is this only 4chan?"), not a setting they maintain.
 *  Adding a fourth source must be a config entry plus an ingest module, so
 *  nothing here is written per source -- the list comes from the payload.
 *
 *  At least one source must stay selected. Turning off the last one would ask
 *  the server for a board built from nothing, which is not a view of anything.
 */
export function Controls({ payload, selection, busy, onChange }: {
  payload: BoardPayload
  selection: Selection
  busy: boolean
  onChange: (next: Selection) => void
}) {
  const counts = payload.segment_counts

  const toggleSource = (name: string) => {
    const on = selection.sources.includes(name)
    if (on && selection.sources.length === 1) return
    onChange({
      ...selection,
      sources: on
        ? selection.sources.filter((s) => s !== name)
        // Kept in the payload's order so the tabs never reshuffle on click.
        : payload.all_sources.filter(
            (s) => s === name || selection.sources.includes(s)),
    })
  }

  return (
    <div className="controls" aria-busy={busy}>
      <div className="tabs" role="group" aria-label="Segment">
        {SEGMENT_ORDER.map((key) => {
          const value = key === 'all' ? null : (key as SegmentFilter)
          // `all` is not a segment, it is the absence of a filter -- so it
          // reads as pressed exactly when nothing else is, and clicking it
          // clears rather than adding a seventh selection.
          const active = value === null
            ? selection.segments.length === 0
            : selection.segments.includes(value)
          const count = counts[key] ?? 0
          return (
            <Fragment key={key}>
              <button type="button" aria-pressed={active}
                      className={count ? 't' : 't nil'}
                      onClick={() => onChange({
                        ...selection,
                        segments: toggleSegment(selection.segments, value),
                      })}>
                {segmentLabel(key)}
                <span className="n">{count}</span>
              </button>
              {key === SEGMENT_BREAK_AFTER && <span className="brk" />}
            </Fragment>
          )
        })}
      </div>

      {/* Window, sources and breadth share the second line: three decisions
          of one or two tabs each, separated by hairlines rather than named.
          The window changes what the score means, sources change what was
          counted, venues change which rows exist -- all three refetch. */}
      <div className="tabs">
        <div className="grp" role="group" aria-label="Window">
          {WINDOWS.map((hours) => (
            <button key={hours} type="button" className="t"
                    aria-pressed={selection.window === hours}
                    onClick={() => onChange({ ...selection, window: hours })}>
              {hours}h
            </button>
          ))}
        </div>
        <div className="grp" role="group" aria-label="Sources">
          {payload.all_sources.map((name) => {
            const on = selection.sources.includes(name)
            const last = on && selection.sources.length === 1
            // The tab takes the label's first word -- "4chan", not
            // "4chan /biz/". The full name made the strip wider than the
            // pane and orphaned the venues group on a line of its own;
            // WHICH board it is stays on the tooltip and in the rows.
            const label = sourceLabel(name)
            const short = label.split(' ')[0]
            return (
              <button key={name} type="button" className="t" aria-pressed={on}
                      disabled={last}
                      title={last ? 'At least one source has to stay on'
                                  : short === label ? undefined : label}
                      onClick={() => toggleSource(name)}>
                {short}
              </button>
            )
          })}
        </div>
        <div className="grp end" role="group" aria-label="Venues">
          <button type="button" className="t"
                  aria-pressed={selection.minVenues === 1}
                  onClick={() => onChange({ ...selection, minVenues: 1 })}>
            any <span className="n">{payload.venue_counts.any ?? 0}</span>
          </button>
          <button type="button" className="t"
                  aria-pressed={selection.minVenues === 2}
                  onClick={() => onChange({ ...selection, minVenues: 2 })}>
            2+ <span className="n">{payload.venue_counts.multi ?? 0}</span>
          </button>
        </div>
      </div>

      {/* The chart span used to sit here. It belongs to the panel now: it
          changes one ticker's chart, not which rows the board lists, and
          having it here made a control that decides nothing about the list
          look like one that does. */}
    </div>
  )
}
