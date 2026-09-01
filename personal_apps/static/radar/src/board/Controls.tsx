import { Fragment, useRef, useState } from 'react'
import type { KeyboardEvent, ReactNode } from 'react'

import { segmentLabel, sourceLabel } from '../format'

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

const WINDOWS = [1, 4, 12, 24]

/** The views: what a reader actually switches between. All first as the way
 *  out of any filter, Discover as the default bundle, then the three that
 *  stand on their own. `recent_ipo` is a view rather than a member of
 *  Discover because a fresh listing is not obscure (types.ts), which is
 *  exactly why it needs a slot of its own. */
const VIEWS: (SegmentFilter | 'all')[] = ['all', 'discover', 'large', 'recent_ipo', 'fund']

/** What Discover is a union of, in descending-cap order. Shown only while
 *  Discover or one of them is in force. */
const MEMBERS: SegmentFilter[] = ['mid', 'micro', 'unknown']

/** The instrument strip: a row of views, the members of Discover while it
 *  is in force, and one line summarising everything else.
 *
 *  This replaced two strips of eight and nine flat text tabs 2026-09-01.
 *  The old segment strip rendered `All` and `Discover` -- aggregates -- as
 *  peers of the five raw sizes, so pressing Discover lit four tabs at once
 *  and `Unknown 0` could render pressed-and-dimmed; and seventeen underlined
 *  words in three rows made links, pressed tabs and unpressed tabs one
 *  visual species (critique, 2026-09-01). The window, the sources and the
 *  venue floor are "a question the reader asks, not a setting they
 *  maintain", so they fold into a sentence that unfolds on request.
 *
 *  Fixed slots where it matters: the five views never move or vanish, a
 *  zero-count view dims rather than disappearing, and the members line is
 *  the one thing that changes shape -- on a click the reader made, never
 *  between loads.
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
  // Folded by default and not persisted: a reader who changes a filter every
  // visit can leave it open for the visit.
  const [open, setOpen] = useState(false)
  const opener = useRef<HTMLButtonElement>(null)
  // Escape folds the filters from anywhere in the strip and hands focus back
  // to the control that opened them -- the one Escape that does anything on
  // this surface, and the one a reader who just unfolded them will try.
  const onKeyDown = (event: KeyboardEvent<HTMLDivElement>) => {
    if (event.key !== 'Escape' || !open) return
    event.preventDefault()
    setOpen(false)
    opener.current?.focus()
  }
  const lastSource = selection.sources.length === 1

  const discoverInForce = selection.segments.includes('discover')
  const memberInForce = selection.segments.some(
    (name) => (MEMBERS as string[]).includes(name))

  const pressMember = (member: SegmentFilter) => onChange({
    ...selection,
    // From the bundle, narrow to the one member. From a member, the usual
    // union toggle -- two members is a legitimate ask ("mid and micro").
    segments: discoverInForce ? [member]
      : toggleSegment(selection.segments, member),
  })

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
    <div className="controls" aria-busy={busy} onKeyDown={onKeyDown}>
      <div className="tabs views" role="group" aria-label="View">
        {VIEWS.map((key) => {
          const value = key === 'all' ? null : key
          // `all` is not a segment, it is the absence of a filter -- so it
          // reads as pressed exactly when nothing else is, and clicking it
          // clears rather than adding a seventh selection.
          const active = value === null
            ? selection.segments.length === 0
            : selection.segments.includes(value)
          const count = counts[key] ?? 0
          return (
            <button key={key} type="button" aria-pressed={active}
                    className={count ? 't' : 't nil'}
                    onClick={() => onChange({
                      ...selection,
                      segments: toggleSegment(selection.segments, value),
                    })}>
              {segmentLabel(key)}
              <span className="n">{count}</span>
            </button>
          )
        })}
      </div>

      {(discoverInForce || memberInForce) && (
        <div className="members" role="group" aria-label="Within Discover">
          <span className="lbl">within Discover:</span>
          {MEMBERS.map((member) => {
            // Covered: in force through the bundle rather than pressed
            // itself. A third state, but a mild one -- ink without the
            // underline -- so it does not have to be learned. The bundle
            // wins whatever else the list says: the server echoes the
            // group EXPANDED (`discover, mid, micro, unknown`), which is
            // what lit four tabs at once on the old strip.
            const pressed = !discoverInForce
              && selection.segments.includes(member)
            const count = counts[member] ?? 0
            const cls = ['t', count ? '' : 'nil',
                         discoverInForce ? 'covered' : '']
              .filter(Boolean).join(' ')
            return (
              <button key={member} type="button" aria-pressed={pressed}
                      className={cls} onClick={() => pressMember(member)}>
                {segmentLabel(member)}
                <span className="n">{count}</span>
              </button>
            )
          })}
        </div>
      )}

      {/* Window, sources and breadth as one sentence. Deviations from the
          defaults are said in place of the default word, and the sources
          are named whenever one is off, so a narrowed board never looks
          like the whole one. */}
      <p className="summary">
        <Summary payload={payload} selection={selection} />
        <button type="button" aria-expanded={open} ref={opener}
                aria-controls="radar-filters"
                aria-label={`${open ? 'Fold' : 'Change'} window, sources and venues`}
                onClick={() => setOpen(!open)}>
          {open ? 'done' : 'change'}
        </button>
      </p>

      {open && (
        <div className="tabs filters" id="radar-filters">
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
              const last = on && lastSource
              const label = sourceLabel(name)
              const short = shortSource(name)
              // aria-disabled, not disabled: a disabled button leaves the
              // tab order, and the reason used to live in a title -- so a
              // keyboard or screen-reader user got neither the control nor
              // the explanation. The click is a no-op (toggleSource) and
              // the reason is written beside it.
              return (
                <button key={name} type="button" className="t" aria-pressed={on}
                        aria-disabled={last || undefined}
                        aria-describedby={last ? 'radar-source-lock' : undefined}
                        title={short === label ? undefined : label}
                        onClick={() => toggleSource(name)}>
                  {short}
                </button>
              )
            })}
            {lastSource && (
              <span className="note" id="radar-source-lock">
                one source has to stay on
              </span>
            )}
          </div>
          <div className="grp end" role="group" aria-label="Venues">
            {/* `any 37 / 2+ 35` beside three source names read as more
                sources; the floor is the one group whose tabs do not say
                what they are. */}
            <span className="lbl">venues</span>
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
      )}
    </div>
  )
}

/** The tab takes the label's first word -- "4chan", not "4chan /biz/". The
 *  full name made the strip wider than the pane; WHICH board it is stays on
 *  the tooltip and in the rows. */
function shortSource(name: string): string {
  return sourceLabel(name).split(' ')[0]!
}

/** `4h · 3 sources · any venue`, or what differs from that. */
function Summary({ payload, selection }: {
  payload: BoardPayload
  selection: Selection
}) {
  const allOn = payload.all_sources.every((s) => selection.sources.includes(s))
  const sources = allOn
    ? `${payload.all_sources.length} sources`
    : payload.all_sources.filter((s) => selection.sources.includes(s))
        .map(shortSource).join(', ')
  const tokens: ReactNode[] = [
    <b key="window">{selection.window}h</b>,
    <Fragment key="sources">{sources}</Fragment>,
    <Fragment key="venues">
      {selection.minVenues > 1 ? `${selection.minVenues}+ venues` : 'any venue'}
    </Fragment>,
  ]
  return (
    <>
      {tokens.map((token, index) => (
        <Fragment key={index}>
          <span className="tok">
            {token}
            {index < tokens.length - 1 && <span className="dot"> ·</span>}
          </span>
          {index < tokens.length - 1 && ' '}
        </Fragment>
      ))}
    </>
  )
}
