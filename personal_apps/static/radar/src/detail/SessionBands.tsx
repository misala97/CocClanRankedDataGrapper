import { useId } from 'react'
import type { ChartSession, DetailChart } from '../types'

type SessionBandsProps = {
  chart: DetailChart
  plotTop: number
  plotBottom: number
  plotRight: number
}

const LABELS: Record<ChartSession['kind'], string> = {
  premarket: 'Pre-market',
  afterhours: 'After hours',
  closed: 'Closed',
}

const FILLS: Record<ChartSession['kind'], string> = {
  premarket: 'var(--session-pre-soft)',
  afterhours: 'var(--session-after-soft)',
  // The neutral wash: a shut market is not a caution, it is furniture. The
  // token flips with the theme on its own.
  closed: 'var(--rule-soft)',
}

const INKS: Record<ChartSession['kind'], string> = {
  premarket: 'var(--session-pre)',
  afterhours: 'var(--session-after)',
  closed: 'var(--muted)',
}

/** What kind of time each stretch is, behind -- never over -- the data.
 *
 *  Three kinds since the single-lane chart: the extended sessions in their
 *  own tints and `closed` as a neutral wash. The wash is what makes a gap in
 *  the price line legible at a glance: no line inside gray is a weekend, no
 *  line on paper is an outage.
 */
export function SessionBands({ chart, plotTop, plotBottom, plotRight }: SessionBandsProps) {
  const clipId = `session-band-${useId().replaceAll(':', '')}`
  const slots = Math.max(chart.closes.length, chart.chatter.length)
  const start = Date.parse(chart.from)
  const end = start + slots * chart.step_minutes * 60_000
  if (!slots || !Number.isFinite(start) || end <= start) return null

  return (
    <g className="session-bands" aria-hidden="true">
      <defs>
        <clipPath id={clipId}>
          <rect x="0" y={plotTop} width={plotRight} height={plotBottom - plotTop} />
        </clipPath>
      </defs>
      {chart.sessions.map((session, index) => {
        // The extended-session tints earn their width only at the 1D zoom.
        // At 1W five days of pre/after/night stripes were a curtain louder
        // than the data (seen live 2026-08-30); wider slots keep only the
        // closed wash, whose rhythm is the orientation the bands are for.
        if (chart.step_minutes >= 60 && session.kind !== 'closed') return null
        const left = Math.max(start, Date.parse(session.start))
        const right = Math.min(end, Date.parse(session.end))
        if (!Number.isFinite(left) || !Number.isFinite(right) || right <= left) return null

        const x = ((left - start) / (end - start)) * plotRight
        const width = ((right - left) / (end - start)) * plotRight
        const label = LABELS[session.kind]
        // Closed stretches carry no label: on a week they are every night,
        // and seven "Closed" captions say less than the wash itself.
        const showLabel = session.kind !== 'closed' && width >= 56
        return (
          <g data-session={session.kind} key={`${session.kind}-${session.start}-${index}`}>
            <rect x={x} y={plotTop} width={width} height={plotBottom - plotTop}
                  clipPath={`url(#${clipId})`}
                  fill={FILLS[session.kind]} />
            {showLabel && (
              <text x={x + width / 2} y={plotTop + 13} textAnchor="middle"
                    clipPath={`url(#${clipId})`}
                    fill={INKS[session.kind]}>
                {label}
              </text>
            )}
          </g>
        )
      })}
    </g>
  )
}

/** The extended sessions present, for the chart's aria label. Closed is
 *  deliberately absent: "closed" as session context reads as the chart
 *  apologising for the calendar. */
export function sessionNames(sessions: ChartSession[]): string {
  return [...new Set(sessions
    .filter((session) => session.kind !== 'closed')
    .map((session) => LABELS[session.kind]))].join(', ')
}
