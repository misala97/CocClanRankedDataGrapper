import { SEGMENT_ORDER, segmentLabel, sourceLabel } from '../format'
import type { BoardPayload, ChartSpan, Segment, Selection } from '../types'

const WINDOWS = [1, 4, 24]
const SPANS: ChartSpan[] = ['24h', '1M', '3M', '1Y']

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
export function Controls({ payload, selection, busy, onChange, span, onSpan }: {
  payload: BoardPayload
  selection: Selection
  busy: boolean
  onChange: (next: Selection) => void
  /** Which slice of the year the charts draw. Client-side only. */
  span: ChartSpan
  onSpan: (next: ChartSpan) => void
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
          {/* A segment with no rows is dropped -- except the one currently
              selected. Hiding the active filter leaves the reader looking at
              an empty board with nothing on screen saying which filter
              emptied it, which is how a filter becomes a bug report. */}
          {SEGMENT_ORDER.filter((key) => key === 'all' || counts[key]
                                || key === selection.segment).map((key) => {
            const value = key === 'all' ? null : (key as Segment)
            const active = selection.segment === value
            return (
              <button key={key} type="button" aria-pressed={active}
                      onClick={() => onChange({ ...selection, segment: value })}>
                {segmentLabel(key)}
                <span className="n">{counts[key] ?? 0}</span>
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

      {/* Two time controls, named for what they decide rather than both being
          called Window. Score changes what the SERVER ranks and refetches;
          Chart changes what is DRAWN and costs no request, because the whole
          year is already in the payload. */}
      {/* Breadth. Server-side, unlike Chart -- it changes which rows exist,
          not how they are drawn, so it refetches like Segment does. */}
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

      <div className="group">
        <span className="lbl" id="span-lbl">Chart</span>
        <div className="seg" role="group" aria-labelledby="span-lbl">
          {SPANS.map((option) => (
            <button key={option} type="button"
                    aria-pressed={span === option}
                    onClick={() => onSpan(option)}>
              {option}
            </button>
          ))}
        </div>
      </div>
    </div>
  )
}
