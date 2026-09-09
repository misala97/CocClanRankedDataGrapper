// What was recorded, by the day the reader lived through.
//
// The hard part of this page is what it must refuse to say. A day nobody
// recorded reads as a gap, not a zero. A day whose only runs crashed reads as a
// gap too, with the crash count beside it, because a run that never reported
// its totals is not a run that measured nothing. And nothing is ever labelled
// complete: successful cycles prove those cycles happened, never that every
// post on every source was seen.
//
// A table rather than a chart. Every figure here is one a reader may need to
// compare or quote, and a bar someone has to hover to read is not a figure.
import { useState } from 'react'

import { fetchActivity } from '../api'
import type { ActivityDay, ActivityPayload } from '../types'
import { Loading, Unavailable } from './PageState'
import { useQuery } from '@tanstack/react-query'
import { REFRESH_MS } from './queries'

const WINDOWS: { days: 1 | 7 | 30; label: string }[] = [
  { days: 1, label: '1 day' },
  { days: 7, label: '7 days' },
  { days: 30, label: '30 days' },
]

export function Activity() {
  const [days, setDays] = useState<1 | 7 | 30>(7)
  const query = useQuery({
    queryKey: ['radar-hub', 'activity', days],
    queryFn: ({ signal }) => fetchActivity(days, signal),
    // Recorded history changes once a cycle at most. Polling it at the board's
    // rate would ask a question whose answer cannot have moved.
    staleTime: REFRESH_MS * 5,
    retry: (count, error) => {
      const reason = (error as { reason?: string })?.reason
      return reason !== 'session' && reason !== 'forbidden' && count < 2
    },
  })

  return (
    <>
      <div className="rh-heading">
        <div>
          <h1>Activity</h1>
          <p>
            The fetch cycles that were recorded, by Berlin day. This is a
            record of what ran — not a measure of how much of the internet was
            covered.
          </p>
        </div>
        <div className="rh-spans" role="group" aria-label="Window">
          {WINDOWS.map((window) => (
            <button
              key={window.days}
              type="button"
              aria-pressed={window.days === days}
              onClick={() => setDays(window.days)}
            >
              {window.label}
            </button>
          ))}
        </div>
      </div>

      {query.isLoading && !query.data ? <Loading label="Loading activity…" /> : null}
      {!query.data && query.error
        ? <Unavailable error={query.error} retry={() => void query.refetch()} />
        : null}
      {query.data ? <Recorded payload={query.data} /> : null}
    </>
  )
}

function Recorded({ payload }: { payload: ActivityPayload }) {
  return (
    <div className="rh-panel">
      <div className="rh-tablewrap" role="region" aria-label="Recorded activity"
           tabIndex={0}>
        <table className="rh-table">
          <thead>
            <tr>
              <th scope="col">Day</th>
              <th scope="col" className="right">Fetched</th>
              <th scope="col" className="right">New posts</th>
              <th scope="col" className="right">Mentions</th>
              <th scope="col" className="right">Bucket writes</th>
              <th scope="col">Runs</th>
            </tr>
          </thead>
          <tbody>
            {payload.days.map((day) => (
              <Day key={day.date} day={day} />
            ))}
          </tbody>
        </table>
      </div>
      <p className="rh-tablefoot small muted">
        {recordingLine(payload)}{' '}
        Counters keep the meanings ingest gave them: fetched counts deliveries
        and repeats a post two overlapping cycles returned, and bucket writes
        counts work performed rather than distinct quarter-hours.
      </p>
    </div>
  )
}

function Day({ day }: { day: ActivityDay }) {
  const unobserved = day.completed_runs === 0
  return (
    <tr data-testid={`rh-day-${day.date}`}>
      <th scope="row">
        {dayLabel(day.date)}
        <span className="rh-sub">
          {day.completeness === 'partial' ? 'Partial coverage' : 'Not recorded'}
        </span>
      </th>
      <Counter value={day.posts_seen} />
      <Counter value={day.posts_new} />
      <Counter value={day.mentions} />
      <Counter value={day.buckets_written} />
      <td data-label="Runs">
        {unobserved
          ? <span className="muted">None completed</span>
          : <strong className="num">{day.completed_runs} completed</strong>}
        <span className="rh-sub">
          {[
            day.counted_runs !== day.completed_runs
              ? `counters from ${day.counted_runs} of ${day.completed_runs}`
              : null,
            day.incomplete_runs ? `${day.incomplete_runs} unfinished` : null,
            day.error_runs ? `${day.error_runs} failed` : null,
          ].filter(Boolean).join(' · ')
            // "no failures recorded" beside a day with no runs reads as a
            // clean day. There were no runs to fail.
            || (unobserved ? 'nothing ran, or nothing reported'
                           : 'no failures recorded')}
        </span>
      </td>
    </tr>
  )
}

/** Null is a gap, and it is drawn as one. A zero here would say the sources
 *  were quiet on a day when nothing was watching them. */
function Counter({ value }: { value: number | null }) {
  return (
    <td className="right" data-label="Count">
      {value === null
        ? <span className="muted" title="No completed run reported this">—</span>
        : <strong className="num">{value.toLocaleString('en-US')}</strong>}
    </td>
  )
}

function recordingLine(payload: ActivityPayload): string {
  if (payload.recording_started_at === null) {
    return 'No run has been recorded yet, so every day here is a gap rather '
      + 'than a quiet day.'
  }
  return `Recording began ${dayLabel(payload.recording_started_at.slice(0, 10))}.`
    + ' Days before that are not missing measurements — nothing was recording.'
}

function dayLabel(date: string): string {
  try {
    return new Date(`${date}T12:00:00Z`).toLocaleDateString('en-GB',
      { weekday: 'short', day: 'numeric', month: 'short' })
  } catch {
    return date
  }
}
