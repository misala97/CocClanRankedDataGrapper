import { render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import { ExerciseChart } from './ExerciseChart'
import type { ChartGeometry, ChartPoint } from '../types'

function point(over: Partial<ChartPoint> & Pick<ChartPoint, 'x' | 'y'>): ChartPoint {
  return {
    e1rm: 100, started_at: '2026-06-01T18:00:00',
    is_best: false, is_deload: false, ...over,
  }
}

const chart: ChartGeometry = {
  width: 320, height: 160, lo: 90, hi: 110, axis_lo: 88, axis_hi: 112,
  ticks: [{ y_pct: 6.25, text: '112' }, { y_pct: 50, text: '100' }, { y_pct: 93.75, text: '88' }],
  dates: ['01.06.', '01.07.', '01.08.'],
  has_record: true, has_deload: true,
  series: [{
    position: 2, opacity: 1, width: 2.5, is_main: true,
    label_x: 300, label_y: 20, label_anchor: 'end',
    points: [
      point({ x: 10, y: 140 }),
      point({ x: 160, y: 80, is_deload: true }),
      point({ x: 310, y: 20, is_best: true }),
    ],
  }],
}

function twoSeries(): ChartGeometry {
  return {
    ...chart,
    series: [
      chart.series[0]!,
      {
        position: 5, opacity: 0.8, width: 1.9, is_main: false,
        label_x: 100, label_y: 60, label_anchor: 'start',
        points: [point({ x: 40, y: 120 }), point({ x: 100, y: 60 })],
      },
    ],
  }
}

const labels = { sessionCount: 3, firstDate: '01.06.2026', lastDate: '01.08.2026' }

describe('ExerciseChart', () => {
  it('draws three gridlines plus one segment fewer than it has points', () => {
    const { container } = render(<ExerciseChart chart={chart} {...labels} />)
    expect(container.querySelectorAll('line')).toHaveLength(3 + 2)
  })

  it('dots every segment touching a deload point', () => {
    const { container } = render(<ExerciseChart chart={chart} {...labels} />)
    const dashed = [...container.querySelectorAll('line')]
      .filter((l) => l.getAttribute('stroke-dasharray') === '3 4')
    // both segments touch the middle deload point
    expect(dashed).toHaveLength(2)
    dashed.forEach((l) => expect(l).toHaveAttribute('stroke', 'var(--unlit)'))
  })

  it('rings the record dot and leaves the deload dot hollow', () => {
    const { container } = render(<ExerciseChart chart={chart} {...labels} />)
    const circles = [...container.querySelectorAll('circle')]

    const record = circles.find((c) => c.classList.contains('chart__pr'))!
    expect(record).toHaveAttribute('r', '6')
    expect(record).toHaveAttribute('stroke', 'var(--done)')
    expect(record).toHaveAttribute('fill', 'var(--record)')

    const deload = circles.find((c) => c.getAttribute('fill') === 'none')!
    expect(deload).toHaveAttribute('stroke', 'var(--unlit)')
    expect(deload).toHaveAttribute('r', '3.5')
  })

  it('describes the range and the date span for a screen reader', () => {
    render(<ExerciseChart chart={chart} {...labels} />)
    const svg = screen.getByRole('img')
    expect(svg.getAttribute('aria-label')).toContain('3 Einheiten')
    expect(svg.getAttribute('aria-label')).toContain('01.06.2026 bis 01.08.2026')
    // the DATA range, not the padded axis range
    expect(svg.getAttribute('aria-label')).toContain('90,0 und 110,0')
  })

  it('shows the deload legend key only when a deload is plotted', () => {
    const { rerender } = render(<ExerciseChart chart={chart} {...labels} />)
    expect(screen.getByText('Deload')).toBeInTheDocument()

    rerender(<ExerciseChart chart={{ ...chart, has_deload: false }} {...labels} />)
    expect(screen.queryByText('Deload')).not.toBeInTheDocument()
  })

  it('shows the record legend key only when a record is plotted', () => {
    render(<ExerciseChart chart={{ ...chart, has_record: false }} {...labels} />)
    expect(screen.queryByText('Rekord')).not.toBeInTheDocument()
    expect(screen.getByText('e1RM')).toBeInTheDocument()
  })

  it('omits the position label when only one series is drawn', () => {
    render(<ExerciseChart chart={chart} {...labels} />)
    expect(screen.queryByText('P2')).not.toBeInTheDocument()
  })

  it('labels each series when more than one is drawn', () => {
    render(<ExerciseChart chart={twoSeries()} {...labels} />)
    expect(screen.getByText('P2')).toBeInTheDocument()
    expect(screen.getByText('P5')).toBeInTheDocument()
  })

  it('recedes the non-main series by opacity and stroke width', () => {
    const { container } = render(<ExerciseChart chart={twoSeries()} {...labels} />)
    const groups = [...container.querySelectorAll('.chart__ink > g')]
    expect(groups[0]).toHaveAttribute('opacity', '1')
    expect(groups[1]).toHaveAttribute('opacity', '0.8')
  })

  it('places the y tick labels by percentage, outside the svg', () => {
    const { container } = render(<ExerciseChart chart={chart} {...labels} />)
    const gutter = container.querySelector('.chart__y')!
    expect(gutter).toHaveAttribute('aria-hidden', 'true')
    expect(gutter.querySelectorAll('span')).toHaveLength(3)
    expect(gutter.querySelector('span')).toHaveStyle({ top: '6.25%' })
  })

  it('renders one axis mark per deduped date', () => {
    const { container } = render(
      <ExerciseChart chart={{ ...chart, dates: ['31.07.'] }} {...labels} />)
    expect(container.querySelectorAll('.chart__axis span')).toHaveLength(1)
  })
})

describe('tap to inspect', () => {
  const user = () => import('@testing-library/user-event').then((m) => m.default.setup())

  it('hints before anything is tapped, in reserved space', () => {
    const { container } = render(<ExerciseChart chart={chart} {...labels} />)
    expect(screen.getByText('Punkt antippen für Details')).toBeInTheDocument()
    expect(container.querySelector('.chart__picked')).toBeNull()
  })

  it('states the tapped point and rings it', async () => {
    const { container } = render(<ExerciseChart chart={chart} {...labels} />)
    const hits = container.querySelectorAll('.chart__hits circle[r="14"]')
    await (await user()).click(hits[2]!)
    const read = container.querySelector('.chart__read')!
    expect(read).toHaveTextContent('01.06.2026 · 100,0 kg e1RM')
    expect(read).toHaveTextContent('Rekord')
    // One series only: no P label in the readout.
    expect(read).not.toHaveTextContent('P2')
    expect(container.querySelector('.chart__picked')).not.toBeNull()
  })

  it('tags a deload point and names the slot with two series', async () => {
    const { container } = render(<ExerciseChart chart={twoSeries()} {...labels} />)
    const hits = container.querySelectorAll('.chart__hits circle[r="14"]')
    await (await user()).click(hits[1]!)
    const read = container.querySelector('.chart__read')!
    expect(read).toHaveTextContent('Deload')
    expect(read).toHaveTextContent('P2')
  })

  it('taps off again', async () => {
    const { container } = render(<ExerciseChart chart={chart} {...labels} />)
    const hit = container.querySelectorAll('.chart__hits circle[r="14"]')[0]!
    const u = await user()
    await u.click(hit)
    await u.click(hit)
    expect(screen.getByText('Punkt antippen für Details')).toBeInTheDocument()
  })

  it('keeps the hit overlay out of the ink and out of the accessibility tree', () => {
    const { container } = render(<ExerciseChart chart={chart} {...labels} />)
    // The golden-master compares .chart__ink against the Jinja original; the
    // overlay must not be in it. role="img" already hides SVG internals from
    // assistive tech -- the overlay stays pointer-only and aria-hidden, and
    // the session log below the chart is the accessible path to the values.
    expect(container.querySelectorAll('.chart__ink .chart__hits')).toHaveLength(0)
    expect(container.querySelector('.chart__hits')).toHaveAttribute('aria-hidden', 'true')
  })
})
