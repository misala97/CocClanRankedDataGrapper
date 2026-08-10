import { render, screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it } from 'vitest'
import { StatistikPage } from './StatistikPage'
import type { StatistikPayload, TimelineRecord } from './types'

const record = (over: Partial<TimelineRecord> = {}): TimelineRecord => ({
  started_at: '2026-07-31T16:00:00', session_id: 900, exercise_id: 4,
  name: 'Reverse Fly (Machine)',
  weight: { value: 45, previous: 40 }, e1rm: null, ...over,
})

const base: StatistikPayload = {
  totals: {
    tonnage: 176963.4, sets: 452, reps: 3782, sessions: 26,
    first_session: '2026-06-14T16:00:00', days_training: 57,
    best_session: { session_id: 920, started_at: '2026-07-31T16:00:00', volume: 11040 },
  },
  longest_gap: 7,
  months: [
    { year: 2026, month: 6, volume: 51247, is_gap: false, has_deload: false, has_record: true },
    { year: 2026, month: 7, volume: 102494, is_gap: false, has_deload: true, has_record: false },
    { year: 2026, month: 8, volume: 0, is_gap: true, has_deload: false, has_record: false },
  ],
  progression: [{
    exercise_id: 9, name: 'Bench Press (Dumbbell)', sessions: 10,
    first_e1rm: 27.1, current_e1rm: 76, change_pct: 180.1, best_weight: 60,
    points: [27.1, 76], spark: '0.0,22.0 74.0,2.0', bar_pct: 50, is_up: true,
  }],
  rep_range: {
    buckets: [
      { label: '1-5', sets: 0, share: 0 },
      { label: '6-8', sets: 289, share: 63.9 },
      { label: '9-12', sets: 140, share: 31 },
      { label: '13+', sets: 23, share: 5.1 },
    ],
    sample: 452, dominant: { label: '6-8', sets: 289, share: 63.9 },
    statable: true, skipped: 0,
  },
  min_sets_for_rep_range: 50,
  fatigue: {
    sample: 151, statable: true, weight_change_pct: -5.1,
    first_reps: 9, last_reps: 7.9,
  },
  daypart: {
    parts: [
      { label: 'morning', sessions: 10, volume: 76135, avg_volume: 7613.5 },
      { label: 'evening', sessions: 16, volume: 100828, avg_volume: 6301.8 },
      { label: 'other', sessions: 0, volume: 0, avg_volume: 0 },
    ],
    statable: true,
  },
  weekday: {
    days: [
      { weekday: 0, sessions: 3, share: 11.5 },
      { weekday: 1, sessions: 8, share: 30.8 },
      { weekday: 2, sessions: 3, share: 11.5 },
      { weekday: 3, sessions: 3, share: 11.5 },
      { weekday: 4, sessions: 3, share: 11.5 },
      { weekday: 5, sessions: 3, share: 11.5 },
      { weekday: 6, sessions: 3, share: 11.7 },
    ],
    sample: 26, statable: true,
  },
  rest_gap: {
    buckets: [
      { label: '0-1', sessions: 15, avg_volume: 7302.1 },
      { label: '2', sessions: 6, avg_volume: 8000 },
      { label: '3', sessions: 3, avg_volume: 6000 },
      { label: '4+', sessions: 2, avg_volume: 4000 },
    ],
    statable: true,
  },
  effort: {
    groups: [
      { label: 'Rücken', volume: 57860.4, sets: 109, share: 32.7 },
      { label: 'Brust', volume: 40000, sets: 80, share: 22.6 },
    ],
    exercises: [
      { label: 'Lat Pulldown', volume: 23755.2, sets: 36, share: 13.4 },
      { label: 'Bench Press', volume: 12000, sets: 24, share: 6.8 },
    ],
    total_volume: 176963.4,
  },
  rest_habit: [150, 210],
  records_total: 43,
  recent_records: [record()],
  record_years: [{ year: 2026, records: [record({ session_id: 23 })] }],
  month_names: ['Januar', 'Februar', 'März', 'April', 'Mai', 'Juni', 'Juli',
    'August', 'September', 'Oktober', 'November', 'Dezember'],
  weekday_names: ['Montag', 'Dienstag', 'Mittwoch', 'Donnerstag', 'Freitag',
    'Samstag', 'Sonntag'],
  daypart_names: { morning: 'Vormittags', evening: 'Abends' },
}

const mount = (over: Partial<StatistikPayload> = {}) =>
  render(<StatistikPage payload={{ ...base, ...over }} />)

const nothing: Partial<StatistikPayload> = {
  rep_range: { ...base.rep_range, statable: false, dominant: null, sample: 4 },
  fatigue: { sample: 0, statable: false, weight_change_pct: null, first_reps: null, last_reps: null },
  daypart: { ...base.daypart, statable: false },
  weekday: { ...base.weekday, statable: false },
  rest_gap: { ...base.rest_gap, statable: false },
  rest_habit: null,
}

describe('StatistikPage', () => {
  it('answers before it reports', () => {
    mount()
    expect(screen.getByRole('heading', { level: 1 }))
      .toHaveTextContent('Du hast 177 Tonnen bewegt und dabei nie länger als 7 Tage pausiert.')
    expect(screen.getByText('Seit 14.06.2026 · 1 Monat')).toBeInTheDocument()
    // Tonnage is a number nobody can feel.
    expect(screen.getByText(/ausgewachsene Elefanten/)).toHaveTextContent('≈ 29')
  })

  it('drops the gap clause when there is no break to report', () => {
    mount({ longest_gap: 0 })
    expect(screen.getByRole('heading', { level: 1 }))
      .toHaveTextContent('Du hast 177 Tonnen bewegt.')
  })

  it('states the training span in days below a month', () => {
    mount({ totals: { ...base.totals, days_training: 12 } })
    expect(screen.getByText(/Seit/)).toHaveTextContent('12 Tage')
  })

  it('links the biggest workout', () => {
    mount()
    expect(screen.getByRole('link', { name: '11.040 kg' }))
      .toHaveAttribute('href', '/gym/session/920')
  })

  it('has nothing to show before the first workout', () => {
    mount({ totals: { ...base.totals, sessions: 0 } })
    expect(screen.getByText(/Noch keine abgeschlossenen Workouts/)).toBeInTheDocument()
    expect(screen.queryByRole('heading', { level: 1 })).not.toBeInTheDocument()
  })

  it('shows a dash rather than a rate it cannot compute', () => {
    mount({ totals: { ...base.totals, days_training: 3 } })
    expect(screen.getByText('Schnitt').previousSibling).toHaveTextContent('—')
  })

  describe('the career strip', () => {
    it('gives every bar its own accessible text', () => {
      // role="img" told assistive tech to ignore every child, so the per-bar
      // titles were unreachable in principle and the flagship figure conveyed
      // exactly one fact: that it existed.
      mount()
      const bars = screen.getAllByRole('listitem')
      expect(bars[0]).toHaveAccessibleName('Juni 2026: 51.247 kg, Rekordmonat')
      expect(bars[1]).toHaveAccessibleName('Juli 2026: 102.494 kg, Deload')
      expect(bars[2]).toHaveAccessibleName('August 2026: 0 kg, keine Einheit')
    })

    it('draws a gap as a break rather than as a zero', () => {
      const { container } = mount()
      const bars = container.querySelectorAll('.mo')
      expect(bars[1]).toHaveStyle({ blockSize: '100%' })
      expect(bars[2]).toHaveStyle({ blockSize: '2%' })
      expect(bars[2]).toHaveClass('is-gap')
    })

    it('states a tapped month in words, and taps off again', async () => {
      // The touch path to what aria-label already tells assistive tech and
      // title tells the mouse.
      const { container } = mount()
      expect(screen.getByText('Balken antippen für Details')).toBeInTheDocument()
      const bars = container.querySelectorAll('.mo')
      const user = userEvent.setup()
      await user.click(bars[0]!)
      const read = container.querySelector('.chart__read')!
      expect(read).toHaveTextContent('Juni 2026 · 51.247 kg')
      expect(read).toHaveTextContent('Rekordmonat')
      expect(bars[0]).toHaveClass('is-picked')
      await user.click(bars[0]!)
      expect(screen.getByText('Balken antippen für Details')).toBeInTheDocument()
    })

    it('names a gap month as one', async () => {
      const { container } = mount()
      await userEvent.setup().click(container.querySelectorAll('.mo')[2]!)
      expect(container.querySelector('.chart__read'))
        .toHaveTextContent('August 2026 · 0 kg · keine Einheit')
    })

    it('dedupes its ticks by index, not by text', () => {
      // At two months the midpoint IS the last month, so first/middle/last
      // printed the same label twice side by side.
      const { container } = mount({ months: base.months.slice(0, 2) })
      const ticks = container.querySelectorAll('.months__axis .label')
      expect([...ticks].map((t) => t.textContent)).toEqual(['Jun 2026', 'Jul 2026'])
    })
  })

  describe('progression', () => {
    it('draws a diverging bar and states the move', () => {
      const { container } = mount()
      expect(screen.getByRole('link', { name: 'Bench Press (Dumbbell)' }))
        .toHaveAttribute('href', '/gym/exercises/9')
      expect(screen.getByText('+180 %')).toHaveClass('is-up')
      expect(screen.getByText('27,1 → 76,0 kg')).toBeInTheDocument()
      expect(container.querySelector('.prog__bar')).toHaveClass('prog__bar--up')
    })

    it('marks a loss as a direction, not as a second list', () => {
      const { container } = mount({
        progression: [{ ...base.progression[0]!, change_pct: -12.4, is_up: false }],
      })
      expect(screen.getByText('-12 %')).toHaveClass('is-down')
      expect(container.querySelector('.prog__bar')).toHaveClass('prog__bar--down')
      expect(container.querySelector('polyline')).toHaveAttribute('stroke', 'var(--stall)')
    })

    it('says so with too little history', () => {
      mount({ progression: [] })
      expect(screen.getByText('Noch zu wenig Historie, um Fortschritt zu messen.'))
        .toBeInTheDocument()
    })
  })

  describe('where the work goes', () => {
    it('shows every group, so the shares still sum to 100', () => {
      // Truncating to a top-6 dropped a group from the bar AND the key, under
      // a header still claiming a share of the whole.
      const { container } = mount()
      expect(container.querySelectorAll('.stack-bar > span')).toHaveLength(2)
      expect(screen.getByText(/Rücken 33 %/)).toBeInTheDocument()
      expect(screen.getByText(/Brust 23 %/)).toBeInTheDocument()
    })

    it('ranks the top exercises against the biggest of them', () => {
      const { container } = mount()
      const bars = container.querySelectorAll('.prog--plain .prog__bar')
      expect(bars[0]).toHaveStyle({ inlineSize: '100%' })
      expect(bars[1]).toHaveStyle({ inlineSize: '50.5%' })
      expect(screen.getByText('24 t')).toBeInTheDocument()
    })

    it('says so with nothing logged', () => {
      mount({ effort: { groups: [], exercises: [], total_volume: 0 } })
      expect(screen.getByText('Noch keine Sätze protokolliert.')).toBeInTheDocument()
    })
  })

  describe('the reading column', () => {
    it('names the dominant rep range and highlights its bar', () => {
      // .dominant is the whole bucket, not its label -- comparing a string to
      // it was always false, so the highlight never once rendered and the four
      // bars were four identical bars.
      const { container } = mount()
      expect(screen.getByText('6-8', { selector: 'em' })).toBeInTheDocument()
      const fills = container.querySelectorAll('.rb__fill')
      expect(fills[1]).toHaveClass('is-top')
      expect(fills[0]).not.toHaveClass('is-top')
      // The share exists only as bar height, so it is stated as text too.
      expect(screen.getAllByRole('listitem').find(
        (n) => n.getAttribute('aria-label')?.startsWith('6-8'),
      )).toHaveAccessibleName('6-8 Wdh.: 64 Prozent, am häufigsten')
    })

    it('states the fatigue drop-off with its sample', () => {
      mount()
      expect(screen.getByText(/Satz 1 bis letzter Satz/)).toHaveTextContent('-1,1 Wdh.')
      expect(screen.getByText(/Gewichtsänderung/))
        .toHaveTextContent('Bei -5,1 % Gewichtsänderung. Aus 151 Einheiten.')
    })

    it('names the favourite time and day', () => {
      mount()
      expect(screen.getByText(/Abends/)).toHaveTextContent('Abends, am liebsten Dienstags')
      expect(screen.getByText(/häufigste Tag/))
        .toHaveTextContent('Dienstag ist mit 31 % der häufigste Tag. Aus 26 Workouts.')
    })

    it('leaves every unanswerable question open rather than guessing', () => {
      mount(nothing)
      expect(screen.getByText(/dafür braucht es mindestens 50/)).toBeInTheDocument()
      expect(screen.getByText('Noch nicht genug Einheiten mit mehreren Sätzen.'))
        .toBeInTheDocument()
      expect(screen.getByText('Noch nicht genug Workouts, um ein Muster zu behaupten.'))
        .toBeInTheDocument()
      expect(screen.getByText(/mehrere Workouts je Abstand/)).toBeInTheDocument()
      // Every question is still ASKED -- that is the whole rule.
      expect(screen.getByText('In welchem Wiederholungsbereich?')).toBeInTheDocument()
      expect(screen.getByText('Wann trainierst du?')).toBeInTheDocument()
    })

    it('drops the rest question entirely without timestamps', () => {
      // The whole block including its wrapping div: `.read + .read` paints a
      // rule and a gap from the div's mere presence, so an empty one still
      // looked like a broken section.
      const { container } = mount({ rest_habit: null })
      expect(screen.queryByText('Wie lange pausierst du?')).not.toBeInTheDocument()
      expect(container.querySelectorAll('.read')).toHaveLength(4)
    })

    it('states planned against actual rest as mm:ss', () => {
      mount()
      expect(screen.getByText(/Du planst/))
        .toHaveTextContent('Du planst 2:30, nimmst dir 3:30.')
    })
  })

  describe('the record timeline', () => {
    it('shows the recent ones flat and folds the rest into year bands', () => {
      mount()
      const section = screen.getByRole('region', { name: 'Jeder Rekord' })
      expect(within(section).getByText('43 insgesamt')).toBeInTheDocument()
      // "weitere", not "Rekorde": the flat rows above are usually the same
      // year, so "2026 · 31 Rekorde" under twelve more 2026 records reads as
      // a contradiction.
      expect(within(section).getByText('1 weitere')).toBeInTheDocument()
    })

    it('leads with the weight record and mentions the e1RM alongside', () => {
      mount({
        recent_records: [record({
          weight: { value: 45, previous: 40 }, e1rm: { value: 57, previous: 53.3 },
        })],
        record_years: [],
      })
      expect(screen.getByText(/45,0 kg/)).toHaveTextContent('45,0 kg vorher 40,0')
      expect(screen.getByText('auch e1RM 57,0')).toBeInTheDocument()
    })

    it('falls back to the e1RM when that is the only record set', () => {
      const { container } = mount({
        recent_records: [record({ weight: null, e1rm: { value: 57, previous: 53.3 } })],
        record_years: [],
      })
      expect(container.querySelector('.rec__val'))
        .toHaveTextContent('57,0 kg e1RM vorher 53,3')
      expect(screen.queryByText(/auch e1RM/)).not.toBeInTheDocument()
    })

    it('is absent when nothing has been beaten yet', () => {
      mount({ recent_records: [], record_years: [], records_total: 0 })
      expect(screen.queryByRole('region', { name: 'Jeder Rekord' })).not.toBeInTheDocument()
    })
  })
})
