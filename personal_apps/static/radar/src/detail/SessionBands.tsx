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
}

/** Extended-session context behind, never over, the measured chart paths. */
export function SessionBands({ chart, plotTop, plotBottom, plotRight }: SessionBandsProps) {
  const slots = Math.max(chart.closes.length, chart.chatter.length)
  const start = Date.parse(chart.from)
  const end = start + slots * chart.step_minutes * 60_000
  if (!slots || !Number.isFinite(start) || end <= start) return null

  return (
    <g className="session-bands" aria-hidden="true">
      {chart.sessions.map((session, index) => {
        const left = Math.max(start, Date.parse(session.start))
        const right = Math.min(end, Date.parse(session.end))
        if (!Number.isFinite(left) || !Number.isFinite(right) || right <= left) return null

        const x = ((left - start) / (end - start)) * plotRight
        const width = ((right - left) / (end - start)) * plotRight
        const label = LABELS[session.kind]
        const showLabel = width >= 56
        return (
          <g data-session={session.kind} key={`${session.kind}-${session.start}-${index}`}>
            <rect x={x} y={plotTop} width={width} height={plotBottom - plotTop}
                  fill={`var(--session-${session.kind === 'premarket' ? 'pre' : 'after'}-soft)`} />
            {showLabel && (
              <text x={x + width / 2} y={plotTop + 13} textAnchor="middle"
                    fill={`var(--session-${session.kind === 'premarket' ? 'pre' : 'after'})`}>
                {label}
              </text>
            )}
          </g>
        )
      })}
    </g>
  )
}

export function sessionNames(sessions: ChartSession[]): string {
  return [...new Set(sessions.map((session) => LABELS[session.kind]))].join(', ')
}
