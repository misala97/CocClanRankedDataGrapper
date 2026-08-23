import { SEGMENT_ORDER, segmentLabel, sourceLabel } from '../format'
import type { BoardPayload, SegmentFilter, Selection } from '../types'

const WINDOWS = [1, 4, 24]

/** Segment, sources and window.
 *
 *  Sources are peers. There is no primary and no default-off: the selector
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
        // Kept in the payload's order so the chips never reshuffle on click.
        : payload.all_sources.filter(
            (s) => s === name || selection.sources.includes(s)),
    })
  }

  return (
    <div className="controls" aria-busy={busy}>
      <div className="group">
        <span className="lbl" id="seg-lbl">Segment</span>
        <div className="seg" role="group" aria-labelledby="seg-lbl">
          {/* Every slot, always, in one order.
              Chips used to be dropped at a count of zero, on the reasoning
              that a dead chip is clutter. What it produced was a strip that
              changed shape between loads, so things moved under the cursor --
              Michi, 2026-08-23: "the settings are bad and switch around".
              A dimmed zero is information. A missing chip is a moving
              target. */}
          {SEGMENT_ORDER.map((key) => {
            const value = key === 'all' ? null : (key as SegmentFilter)
            const active = selection.segment === value
            const count = counts[key] ?? 0
            return (
              <button key={key} type="button" aria-pressed={active}
                      className={count ? undefined : 'nil'}
                      onClick={() => onChange({ ...selection, segment: value })}>
                {segmentLabel(key)}
                <span className="n">{count}</span>
              </button>
            )
          })}
        </div>
      </div>

      <div className="group">
        <span className="lbl" id="src-lbl">Sources</span>
        <div className="seg" role="group" aria-labelledby="src-lbl">
          {payload.all_sources.map((name) => {
            const on = selection.sources.includes(name)
            const last = on && selection.sources.length === 1
            return (
              <button key={name} type="button" className="chip" aria-pressed={on}
                      disabled={last}
                      title={last ? 'At least one source has to stay on' : undefined}
                      onClick={() => toggleSource(name)}>
                <span className="dot" />
                {sourceLabel(name)}
              </button>
            )
          })}
        </div>
      </div>

      {/* Breadth. Server-side: it changes which rows exist, so it refetches
          the way Segment does. */}
      <div className="group">
        <span className="lbl" id="venues-lbl">Venues</span>
        <div className="seg" role="group" aria-labelledby="venues-lbl">
          <button type="button" aria-pressed={selection.minVenues === 1}
                  onClick={() => onChange({ ...selection, minVenues: 1 })}>
            any <span className="n">{payload.venue_counts.any ?? 0}</span>
          </button>
          <button type="button" aria-pressed={selection.minVenues === 2}
                  onClick={() => onChange({ ...selection, minVenues: 2 })}>
            2+ <span className="n">{payload.venue_counts.multi ?? 0}</span>
          </button>
        </div>
      </div>

      <div className="group">
        <span className="lbl" id="score-lbl">Score</span>
        <div className="seg" role="group" aria-labelledby="score-lbl">
          {WINDOWS.map((hours) => (
            <button key={hours} type="button"
                    aria-pressed={selection.window === hours}
                    onClick={() => onChange({ ...selection, window: hours })}>
              {hours}h
            </button>
          ))}
        </div>
      </div>

      {/* The chart span used to sit here. It belongs to the panel now: it
          changes one ticker's chart, not which rows the board lists, and
          having it here made a control that decides nothing about the list
          look like one that does. */}
    </div>
  )
}
