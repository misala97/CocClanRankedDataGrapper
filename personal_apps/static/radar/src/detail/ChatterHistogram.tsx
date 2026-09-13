import { useMemo, useState } from 'react'

import type { ChatterToneSlot, DetailChart } from '../types'
import { count } from '../format'
import { PLOT_R, TOP, FLOOR, isIntraday, slotLabel } from './PriceChart'

const TONE_COLORS = {
  bullish: '#45dda0',
  bearish: '#ff6b7c',
  neutral: 'var(--dim)',
  unjudged: '#748391',
  unavailable: '#46545e',
} as const

type DisplayBin = {
  start: number
  end: number
  total: number | null
  slot: ChatterToneSlot
}

export function percentageText(value: number, total: number): string {
  return total > 0 ? `${Math.round((value / total) * 100)}%` : '—'
}

export function poolHistogram(chart: DetailChart): DisplayBin[] {
  const length = chart.chatter.length
  const poolSize = length > 400 ? Math.ceil(length / 365) : 1
  const bins: DisplayBin[] = []
  // Never pool across an unobserved gap: a missing interval is not silence.
  for (let start = 0; start < length;) {
    let end = Math.min(length, start + poolSize)
    const missing = chart.chatter[start] === null
    for (let i = start + 1; i < end; i++) {
      if ((chart.chatter[i] === null) !== missing) { end = i; break }
    }
    if (missing) {
      bins.push({ start, end, total: null, slot: null })
      start = end
      continue
    }
    let total = 0
    const slot: NonNullable<ChatterToneSlot> = {
      bullish: 0, bearish: 0, neutral: 0, unjudged: 0, unavailable: 0, status: 'complete',
    }
    const keys = ['bullish', 'bearish', 'neutral', 'unjudged', 'unavailable'] as const
    for (let i = start; i < end; i++) {
      const value = chart.chatter[i] ?? 0
      total += value
      const tone = chart.chatter_tone?.slots[i]
      const valid = tone && keys.every(key => Number.isInteger(tone[key]) && tone[key] >= 0)
        && keys.reduce((sum, key) => sum + tone[key], 0) === value
      if (valid) for (const key of keys) slot[key] += tone[key]
      else slot.unavailable += value
    }
    slot.status = slot.unavailable === 0 ? 'complete'
      : slot.unavailable === total ? 'unavailable' : 'partial'
    bins.push({ start, end, total, slot })
    start = end
  }
  return bins
}

function intervalLabel(chart: DetailChart, bin: DisplayBin): string {
  const start = new Date(new Date(chart.from).getTime()
    + bin.start * chart.step_minutes * 60_000).toISOString()
  const end = new Date(new Date(chart.from).getTime()
    + bin.end * chart.step_minutes * 60_000).toISOString()
  return bin.end - bin.start > 1
    ? `${start} to ${end} (${slotLabel(chart, bin.start, true)}–${slotLabel(chart, bin.end - 1, true)})`
    : `${start} to ${end}`
}

function detailText(chart: DetailChart, bin: DisplayBin): string {
  if (bin.total === null) return `${intervalLabel(chart, bin)}; chatter unobserved`
  const total = bin.total
  const slot = bin.slot
  if (slot === null) {
    return `${intervalLabel(chart, bin)}; total ${count(total)} mentions; tone unavailable`
  }
  const parts = (['bullish', 'bearish', 'neutral', 'unjudged', 'unavailable'] as const)
    .map((key) => `${key} ${slot[key]} (${percentageText(slot[key], total)})`)
    .join(', ')
  return `${intervalLabel(chart, bin)}; total ${count(total)} mentions; ${parts}; basis recorded judgments${slot.status === 'unavailable' ? '; tone unavailable' : ''}`
}

export function ChatterHistogram({ chart }: { chart: DetailChart }) {
  const bins = useMemo(() => poolHistogram(chart), [chart])
  const firstObserved = Math.max(0, bins.findIndex((bin) => bin.total !== null))
  const [selected, setSelected] = useState<number | null>(
    firstObserved >= 0 ? firstObserved : null)
  const [hovered, setHovered] = useState<number | null>(null)
  const peak = Math.max(...bins.map(bin => Math.max(bin.total ?? 0,
    (chart.normal_per_slot ?? 0) * (bin.end - bin.start))), 1)
  const width = PLOT_R / Math.max(chart.chatter.length, 1)
  const active = hovered ?? selected

  const move = (delta: number) => {
    if (!bins.length) return
    const current = selected ?? firstObserved
    setSelected(Math.max(0, Math.min(bins.length - 1, current + delta)))
  }

  return (
    <div className="chatter-histogram">
      <div className="chatter-histogram-head">
        <div>
          <h3>Chatter tone — recorded judgments</h3>
          <p className="muted small">
            Tone colours use retained recent judgments. Older or unmatched
            chatter stays grey. Retained event horizon: 48 hours.
          </p>
        </div>
        <p className="chatter-tone-legend" aria-label="Tone legend">
          <span><i style={{ background: TONE_COLORS.bullish }} />Bullish</span>
          <span><i style={{ background: TONE_COLORS.bearish }} />Bearish</span>
          <span><i style={{ background: TONE_COLORS.neutral }} />Neutral / mixed</span>
          <span><i style={{ background: TONE_COLORS.unjudged }} />Unjudged / unresolved</span>
          <span><i style={{ background: TONE_COLORS.unavailable }} />Tone unavailable</span>
        </p>
      </div>
      <div
        className="chatter-histogram-canvas"
        role="group"
        tabIndex={0}
        aria-label="Chatter tone intervals. Use arrow keys to inspect intervals."
        onKeyDown={(event) => {
          if (event.key === 'ArrowLeft') { event.preventDefault(); move(-1) }
          else if (event.key === 'ArrowRight') { event.preventDefault(); move(1) }
          else if (event.key === 'Home') { event.preventDefault(); setSelected(0) }
          else if (event.key === 'End') { event.preventDefault(); setSelected(bins.length - 1) }
          else if (event.key === 'Escape') { setSelected(null); setHovered(null) }
        }}
      >
        <svg viewBox={`0 0 912 ${FLOOR + 26}`} role="img"
             aria-label="Stacked chatter tone histogram">
          <line x1="0" y1={FLOOR} x2={PLOT_R} y2={FLOOR}
                stroke="var(--rule)" vectorEffect="non-scaling-stroke" />
          {bins.map((bin, index) => {
            if (bin.total === null) return null
            const binWidth = (bin.end - bin.start) * width
            const x = bin.start * width + Math.min(binWidth * 0.18, 3)
            const barWidth = Math.max(binWidth * 0.64, 0.1)
            const values = bin.slot ?? {
              bullish: 0, bearish: 0, neutral: 0, unjudged: 0,
              unavailable: bin.total, status: 'unavailable' as const,
            }
            let y = FLOOR
            return (
              <g key={`${bin.start}-${bin.end}`}>
                {chart.normal_per_slot !== null && (
                  <line className="tone-normal" x1={bin.start * width} x2={bin.end * width}
                    y1={FLOOR - (chart.normal_per_slot * (bin.end - bin.start) / peak) * (FLOOR - TOP)}
                    y2={FLOOR - (chart.normal_per_slot * (bin.end - bin.start) / peak) * (FLOOR - TOP)}
                    stroke="var(--dim)" strokeDasharray="3 4" />
                )}
                {(['bullish', 'bearish', 'neutral', 'unjudged', 'unavailable'] as const)
                  .map((key) => {
                    const height = (values[key] / peak) * (FLOOR - TOP)
                    const rect = <rect key={key} x={x} y={y - height}
                      width={barWidth} height={Math.max(height, 0)}
                      data-tone={key} fill={TONE_COLORS[key]} opacity={active === index ? 1 : 0.9}
                      onMouseEnter={() => setHovered(index)}
                      onMouseLeave={() => setHovered(null)}
                      onClick={() => setSelected(index)} />
                    y -= height
                    return rect
                  })}
                <rect className="tone-hit" x={bin.start * width} y={TOP}
                  width={binWidth} height={FLOOR - TOP} fill="transparent"
                  onMouseEnter={() => setHovered(index)} onMouseLeave={() => setHovered(null)}
                  onClick={() => setSelected(index)} />
                {active === index && (
                  <line x1={x + barWidth / 2} y1={TOP} x2={x + barWidth / 2}
                        y2={FLOOR} stroke="var(--text)" opacity=".55"
                        vectorEffect="non-scaling-stroke" />
                )}
              </g>
            )
          })}
          <text className="ax" x={PLOT_R + 8} y={TOP + 12}>{count(peak)}</text>
          <text className="ax" x="0" y={FLOOR + 18}>{slotLabel(chart, 0, true)}</text>
          <text className="ax" x={PLOT_R} y={FLOOR + 18} textAnchor="end">
            {isIntraday(chart) ? 'now' : 'today'}
          </text>
        </svg>
        {active !== null && bins[active] && (
          <div className="chatter-interval-detail" aria-live="polite">
            {detailText(chart, bins[active])}
          </div>
        )}
      </div>
      <p className="rh-caption">
        Green and red describe recorded discussion only; they do not predict a
        price move or recommend a trade. Percentages use the full interval
        mention total. Dashed segments show the normal volume for each interval. Focus the chart and use arrow keys, Home, End or Escape.
      </p>
    </div>
  )
}
