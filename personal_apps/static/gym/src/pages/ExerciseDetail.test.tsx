import { fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { ExerciseDetailPage } from './ExerciseDetail'
import type {
  E1rmPR, ExerciseDetailPayload, ExerciseGoal, ExerciseMeta, RoutineChoice, RunningWorkout,
  SessionRow, Stair, StairCol, WeightReps,
} from '../types'

/** Every date on the page is said against today: "Di", "03.08." without a
 *  year. Only Date is faked -- the clicks and waits keep real timers. */
beforeEach(() => {
  vi.useFakeTimers({ toFake: ['Date'] })
  vi.setSystemTime(new Date('2026-09-25T10:00:00Z'))
})
afterEach(() => {
  vi.useRealTimers()
  vi.unstubAllGlobals()
  vi.restoreAllMocks()
  history.replaceState(null, '', '/')
})

/** The first mention of the 1RM a reader meets -- text or aria-label, in
 *  document order. D16: it is the one that names it in full. */
function firstOneRm(root: HTMLElement): string | null {
  const walker = document.createTreeWalker(root, NodeFilter.SHOW_ELEMENT | NodeFilter.SHOW_TEXT)
  for (let node = walker.nextNode(); node !== null; node = walker.nextNode()) {
    const said = node.nodeType === Node.TEXT_NODE
      ? node.textContent
      : (node as Element).getAttribute('aria-label')
    if (said?.includes('1RM')) return said
  }
  return null
}

function payload(over: Partial<ExerciseDetailPayload> = {}): ExerciseDetailPayload {
  return {
    exercise: {
      id: 1, name: 'Bankdrücken', muscle_group: 'Brust', is_unilateral: false,
      default_rest_seconds: 90, weight_increment: 2.5, equipment: 'barbell',
      bar_weight: 20, stack_kg: null, secondary_muscle_groups: null,
      list_defaults: {
        default_rest_seconds: 90, weight_increment: 2.5, bar_weight: 20, stack_kg: null,
      },
      own: [], rest_for_all: null,
    },
    table: [], goal: null, weights: [], pr_e1rm: null, trend: null, stairs: [],
    position_pills: [], selected_position: null, state: null, sessions_since_pr: null,
    chip_class: null, chip_label: null,
    about: { picture: null, movement: null, variants: [] },
    equipment_labels: { barbell: 'Langhantel', stack: 'Stack', dumbbell: 'Kurzhantel' },
    on_list: true, running: null, routines: [],
    ...over,
  }
}

/** A stack the lifter set up: their own step, rest and stops over the list's. */
const stackExercise: ExerciseMeta = {
  ...payload().exercise, name: 'Latzug (Kabel)', muscle_group: 'Rücken', equipment: 'stack',
  weight_increment: 5, default_rest_seconds: 120, bar_weight: null, stack_kg: [5, 13, 21],
  list_defaults: {
    default_rest_seconds: 90, weight_increment: 2.5, bar_weight: null, stack_kg: null,
  },
  own: ['default_rest_seconds', 'stack_kg', 'weight_increment'],
}

/** `weight` × each of `reps`, one set each. */
const sets = (weight: number, ...reps: number[]): WeightReps[] =>
  reps.map((count) => ({ weight, reps: count }))

function row(over: Partial<SessionRow> = {}): SessionRow {
  return {
    session_id: 7, started_at: '2026-08-01T18:30:00', position: 2,
    is_deload: false, is_record: false, sets: sets(80, 8, 8, 8),
    volume: 1920, e1rm: 100, ...over,
  }
}

function col(over: Partial<StairCol> & Pick<StairCol, 'session_id' | 'started_at' | 'e1rm' | 'best'>): StairCol {
  return { position: 1, kind: 'workout', ...over }
}

/** Five Mondays, newest first as the table comes: a debut (never a record,
 *  D3), a dip, a record, a deload, one under the tread. */
const HISTORY: SessionRow[] = [
  row({ session_id: 5, started_at: '2026-09-07T17:00:00', position: 1, sets: sets(80, 7, 6, 6),
    volume: 1520, e1rm: 94 }),
  row({ session_id: 4, started_at: '2026-08-17T17:00:00', position: 1, is_deload: true,
    sets: sets(70, 8, 8), volume: 1120, e1rm: 89 }),
  row({ session_id: 3, started_at: '2026-08-03T17:00:00', position: 1, is_record: true,
    sets: sets(82.5, 5, 5, 4), volume: 1155, e1rm: 95 }),
  row({ session_id: 2, started_at: '2026-07-20T17:00:00', position: 1, sets: sets(75, 6, 6, 5),
    volume: 1275, e1rm: 88 }),
  row({ session_id: 1, started_at: '2026-07-06T17:00:00', position: 1,
    sets: sets(77.5, 6, 5, 5), volume: 1240, e1rm: 90 }),
]

/** The same five on the Rekordtreppe. The deload's 89 lies inside the kg
 *  range on purpose: drawn by its e1RM, it would sit above the 88 line. */
const ALLE: Stair = {
  position: null, lo: 88, hi: 95, ticks: [88, 90, 92, 94], since: 1, stalled: false,
  cols: [
    col({ session_id: 1, started_at: '2026-07-06T17:00:00', e1rm: 90, best: 90 }),
    col({ session_id: 2, started_at: '2026-07-20T17:00:00', e1rm: 88, best: 90 }),
    col({ session_id: 3, started_at: '2026-08-03T17:00:00', e1rm: 95, best: 95, kind: 'record' }),
    col({ session_id: 4, started_at: '2026-08-17T17:00:00', e1rm: 89, best: 95, kind: 'deload' }),
    col({ session_id: 5, started_at: '2026-09-07T17:00:00', e1rm: 94, best: 95 }),
  ],
}

const RECORD: E1rmPR = {
  e1rm: 95, weight: 82.5, reps: 5, session_id: 3, started_at: '2026-08-03T17:00:00', position: 1,
  is_record: true,
}

/** The page of a lift with that history. */
function logged(over: Partial<ExerciseDetailPayload> = {}): ExerciseDetailPayload {
  return payload({
    table: HISTORY, pr_e1rm: RECORD, sessions_since_pr: 1, stairs: [ALLE], ...over,
  })
}

function goal(over: Partial<ExerciseGoal> = {}): ExerciseGoal {
  return {
    sets: sets(40, 11, 10, 10), last_sets: sets(40, 10, 9, 9),
    last_at: '2026-09-22T17:00:00', rep_min: 8, rep_max: 12, stepped: false,
    step_ups: [42.5, 42.5, 42.5], ...over,
  }
}

describe('ExerciseDetailPage', () => {
  it('names the exercise as the h1, and says the muscle and the per-side weight under it', () => {
    const { container } = render(<ExerciseDetailPage payload={payload({
      exercise: { ...payload().exercise, muscle_group: null, is_unilateral: true },
    })} />)
    expect(screen.getByRole('heading', { level: 1 })).toHaveTextContent('Bankdrücken')
    // Per side, not "einseitig": a dumbbell press is two-sided (G-039). When
    // it was last done is the lead's now, and the slot is no word (D16).
    expect(container.querySelector('.exdetail__sub'))
      .toHaveTextContent(/^Ohne Muskelgruppe · Gewicht je Seite$/)
  })

  it('says what fills the page when nothing is logged, and still shows the exercise', () => {
    render(<ExerciseDetailPage payload={payload({
      about: { picture: '/static/gym/art/bench.webp', movement: 'Bankdrücken', variants: [] },
    })} />)
    expect(screen.getByText(/Noch kein Satz/)).toHaveTextContent(
      /^Noch kein Satz\. Sobald du sie loggst, stehen hier dein nächstes Ziel, deine Rekorde und jedes Workout\.$/)
    expect(screen.queryByRole('heading', { name: /^Workouts/ })).not.toBeInTheDocument()
    expect(screen.getByRole('img', { name: 'Zeichnung: Bankdrücken' })).toBeInTheDocument()
  })

  it('names the 1RM in full before anything says "1RM" (D16)', () => {
    const { container } = render(<ExerciseDetailPage payload={logged({ goal: goal() })} />)
    expect(firstOneRm(container)).toBe('Geschätztes Maximum (1RM)')
  })

  it('offers no way to delete the exercise: the list is everyone\'s', () => {
    render(<ExerciseDetailPage payload={logged()} />)
    expect(screen.queryByText(/löschen/i)).not.toBeInTheDocument()
  })

  it('opens the settings from the maintenance button', async () => {
    const user = userEvent.setup()
    render(<ExerciseDetailPage payload={payload()} />)

    const dialog = document.querySelector('dialog')!
    expect(dialog.open).toBe(false)
    await user.click(screen.getByText(/Pause und Schritt einstellen/))
    expect(dialog.open).toBe(true)
    expect(within(dialog).getByRole('heading', { name: 'Deine Einstellungen' })).toBeInTheDocument()
  })

  it('opens on the settings when "Deine Pause" links an exception here', () => {
    // The hash is dropped once used: a reload lands on the page itself.
    window.history.replaceState(null, '', '/gym/exercises/1#einstellungen')
    render(<ExerciseDetailPage payload={payload()} />)
    expect(document.querySelector('dialog')!.open).toBe(true)
    expect(window.location.hash).toBe('')
  })
})

describe('Nächstes Ziel (D9 A)', () => {
  const lead = () => within(screen.getByRole('region', { name: 'Nächstes Ziel' }))
  const rule = () => document.querySelector('.exgoal__rule')

  it('draws one line per weight, and says the sets to a screen reader', () => {
    const { container } = render(<ExerciseDetailPage payload={logged({
      goal: goal({ sets: [...sets(45, 8), ...sets(40, 11, 10, 10)], step_ups: [47.5, 42.5, 42.5, 42.5] }),
    })} />)
    expect([...container.querySelectorAll('.exgoal__w')].map((w) => w.textContent))
      .toEqual(['45kg', '40kg'])
    expect([...container.querySelectorAll('.exgoal__r')].map((r) => r.textContent))
      .toEqual(['8', '11·10·10'])
    expect(lead().getByText(
      '45 kg, 1 Satz: 8 Wiederholungen; 40 kg, 3 Sätze: 11, 10 und 10 Wiederholungen',
    )).toHaveClass('sr-only')
  })

  it('says the workout it builds on, the way a lifter says the day', () => {
    render(<ExerciseDetailPage payload={logged({ goal: goal() })} />)
    expect(lead().getByText('Letztes Mal · Di')).toBeInTheDocument()
    expect(lead().getByText('40,0 × 10 · 9 · 9')).toBeInTheDocument()
  })

  it('says where every set goes once the top of the range is reached', () => {
    render(<ExerciseDetailPage payload={logged({ goal: goal() })} />)
    expect(rule()).toHaveTextContent(
      'Schaffst du 12 in allen 3 Sätzen, geht jeder Satz eine Stufe hoch (42,5 kg) und beginnt '
      + 'wieder bei 8 Wdh.')
  })

  it('names each set\'s own next weight when they differ', () => {
    render(<ExerciseDetailPage payload={logged({
      goal: goal({ sets: [...sets(40, 11), ...sets(35, 12, 12)], step_ups: [42.5, 37.5, 37.5] }),
    })} />)
    expect(rule()).toHaveTextContent('eine Stufe hoch (42,5 · 37,5 · 37,5 kg)')
  })

  it('speaks of one set as one', () => {
    render(<ExerciseDetailPage payload={logged({
      goal: goal({ sets: sets(40, 11), last_sets: sets(40, 10), step_ups: [42.5] }),
    })} />)
    expect(rule()).toHaveTextContent(
      'Schaffst du 12 im Satz, geht der Satz eine Stufe hoch (42,5 kg) und beginnt wieder bei 8 Wdh.')
  })

  it('adds reps where a set has no step up', () => {
    // Bodyweight, or the top stop of a known stack: the only way on is reps.
    render(<ExerciseDetailPage payload={logged({
      goal: goal({ sets: sets(0, 11, 10, 10), step_ups: [null, null, null] }),
    })} />)
    expect(rule()).toHaveTextContent(
      'Schaffst du 12 in allen 3 Sätzen, kommt in jedem Satz eine Wiederholung dazu.')
  })

  it('steps the sets that have a step, and adds a rep to the rest', () => {
    // A stack's top stop first, lighter sets after: one set without a step
    // said "a rep more" of all three, while two of them go up.
    render(<ExerciseDetailPage payload={logged({
      goal: goal({ sets: [...sets(100, 12), ...sets(90, 12, 12)], step_ups: [null, 95, 95] }),
    })} />)
    expect(rule()).toHaveTextContent(
      'Schaffst du 12 in allen 3 Sätzen, gehen die Sätze mit einer nächsten Stufe hoch (95 kg) '
      + 'und beginnen wieder bei 8 Wdh.; bei den anderen kommt eine Wiederholung dazu.')
  })

  it('holds a target that already stepped up', () => {
    render(<ExerciseDetailPage payload={logged({
      goal: goal({ sets: sets(42.5, 8, 8, 8), stepped: true, step_ups: null }),
    })} />)
    expect(rule()).toHaveTextContent(
      'Eine Stufe höher: bleib dabei, bis du 12 in allen 3 Sätzen schaffst.')
  })

  it('is left out when there is nothing to build on', () => {
    render(<ExerciseDetailPage payload={logged({ goal: null })} />)
    expect(screen.queryByRole('region', { name: 'Nächstes Ziel' })).not.toBeInTheDocument()
  })
})

describe('Wiederholungen je Gewicht', () => {
  it('reads down a real table: weight, most reps, workouts, first day', () => {
    render(<ExerciseDetailPage payload={logged({
      weights: [
        { weight: 82.5, reps: 5, workouts: 1, first_at: '2026-08-03T17:00:00' },
        { weight: 80, reps: 7, workouts: 3, first_at: '2025-12-15T17:00:00' },
      ],
    })} />)
    const table = within(screen.getByRole('region', { name: 'Wiederholungen je Gewicht' }))
    expect(table.getAllByRole('row').map((line) => line.textContent)).toEqual([
      'GewichtMeiste Wdh.WorkoutsZuerst',
      '82,5 kg5103.08.',
      '80 kg7315.12.2025',
    ])
    expect(table.getByRole('rowheader', { name: '82,5 kg' })).toBeInTheDocument()
  })
})

describe('Geschätztes Maximum (1RM)', () => {
  const section = () => within(screen.getByRole('region', { name: 'Geschätztes Maximum (1RM)' }))
  const drift = () => document.querySelector('.exdrift')

  it('says the record and the set it came from', () => {
    render(<ExerciseDetailPage payload={logged()} />)
    expect(document.querySelector('.exrec'))
      .toHaveTextContent(/^Rekord 95,0 kg, aus 82,5 kg × 5 am 03\.08\.$/)
    expect(document.querySelector('.exrec__dot')).toBeInTheDocument()
  })

  it('calls a best no workout has beaten yet a Bestwert, not a record', () => {
    // The debut is never a record (D3): its best, still standing, is no gold.
    render(<ExerciseDetailPage payload={logged({ pr_e1rm: { ...RECORD, is_record: false } })} />)
    expect(document.querySelector('.exrec'))
      .toHaveTextContent(/^Bestwert 95,0 kg, aus 82,5 kg × 5 am 03\.08\.$/)
    expect(document.querySelector('.exrec__dot')).toBeNull()
  })

  it('dates a record from another year with its year', () => {
    render(<ExerciseDetailPage payload={logged({
      pr_e1rm: { ...RECORD, started_at: '2025-11-03T17:00:00' },
    })} />)
    expect(document.querySelector('.exrec')).toHaveTextContent('am 03.11.2025')
  })

  it('says only the trend right after a record', () => {
    render(<ExerciseDetailPage payload={logged({
      sessions_since_pr: 0, trend: { per_month: 1.24, workouts: 6 },
    })} />)
    expect(drift()).toHaveTextContent(/^Trend der letzten 6 Workouts: \+1,2 kg im Monat\.$/)
  })

  it('counts the workouts since the record, one as one', () => {
    const { rerender } = render(<ExerciseDetailPage payload={logged({ sessions_since_pr: 1 })} />)
    expect(drift()).toHaveTextContent(/^Seit 1 Workout ohne Rekord\.$/)
    rerender(<ExerciseDetailPage payload={logged({
      sessions_since_pr: 3, trend: { per_month: -0.4, workouts: 5 },
    })} />)
    expect(drift()).toHaveTextContent(
      /^Seit 3 Workouts ohne Rekord\. Trend der letzten 5 Workouts: −0,4 kg im Monat\.$/)
  })

  it('says the count alone, in the stall ink, while the lift is stalled', () => {
    // A rising trend beside a stall read as a contradiction (D9 round 1).
    render(<ExerciseDetailPage payload={logged({
      state: 'stagniert', sessions_since_pr: 4, trend: { per_month: 0.8, workouts: 6 },
      stairs: [{ ...ALLE, since: 4, stalled: true }],
    })} />)
    expect(drift()).toHaveTextContent(/^Seit 4 Workouts ohne Rekord\.$/)
    expect(drift()!.querySelector('.is-stall')).toHaveTextContent('Seit 4 Workouts ohne Rekord.')
  })

  it('says nothing about a drift there is none of', () => {
    render(<ExerciseDetailPage payload={logged({ sessions_since_pr: 0, trend: null })} />)
    expect(drift()).toBeNull()
  })

  it('says why there is no record when no set had a weight, and draws no 1RM (G-038)', () => {
    const { container } = render(<ExerciseDetailPage payload={payload({
      table: [row({ sets: sets(0, 12, 10), volume: 0, e1rm: 0 })],
    })} />)
    expect(section().getByText('Noch kein Rekord — bisher nur Sätze ohne Gewicht.')).toBeInTheDocument()
    expect(firstOneRm(container)).toBe('Geschätztes Maximum (1RM)')
    // "1RM 0,0" on every bodyweight row said nothing.
    expect(screen.queryByText(/^1RM /)).not.toBeInTheDocument()
  })

  it('says why there is no record when every set was past 12 reps', () => {
    const { container } = render(<ExerciseDetailPage payload={payload({
      table: [row({ sets: sets(30, 15, 14), e1rm: 45 })],
    })} />)
    expect(section().getByText(
      'Noch kein Rekord: geschätzt wird nur aus Sätzen mit 1 bis 12 Wiederholungen.',
    )).toBeInTheDocument()
    expect(firstOneRm(container)).toBe('Geschätztes Maximum (1RM)')
    expect(screen.getByText('1RM 45,0')).toBeInTheDocument()
  })
})

describe('the Rekordtreppe', () => {
  const plot = () => screen.getByRole('img', { name: /^Geschätztes Maximum in/ })
  const dots = () => [...document.querySelectorAll<SVGCircleElement>('circle.stair__dot')]
  const at = (dot: SVGCircleElement) => [dot.getAttribute('cx'), dot.getAttribute('cy')]
  const readout = () => document.querySelector('.exread')!

  it('draws the best so far as a stair that climbs at each record, and never falls', () => {
    render(<ExerciseDetailPage payload={logged()} />)
    const [first, , second, , last] = dots().map(at)
    const [tread, now] = [...document.querySelectorAll('.stair__tread')]
    // From the debut, flat past the dip to 88, up at the record to 95.
    expect(tread).toHaveAttribute('d', `M${first![0]} ${first![1]} H${second![0]} V${second![1]}`)
    // The tread since the last record: under the newest workout, not a line to it.
    expect(now).toHaveAttribute('d', `M${second![0]} ${second![1]} H${last![0]}`)
    expect(now).not.toHaveClass('is-stall')
    expect(Number(last![1])).toBeGreaterThan(Number(second![1]))
  })

  it('marks the records gold, and keys them only when there are any', () => {
    const { rerender } = render(<ExerciseDetailPage payload={logged()} />)
    expect(document.querySelectorAll('.stair__dot--rec')).toHaveLength(1)
    expect(within(document.querySelector('.exlegend') as HTMLElement).getByText('Rekord'))
      .toBeInTheDocument()

    const plain = ALLE.cols.map((c) => ({ ...c, kind: c.kind === 'record' ? 'workout' as const : c.kind }))
    rerender(<ExerciseDetailPage payload={logged({ stairs: [{ ...ALLE, cols: plain }] })} />)
    expect(document.querySelectorAll('.stair__dot--rec')).toHaveLength(0)
    expect(within(document.querySelector('.exlegend') as HTMLElement).queryByText('Rekord')).toBeNull()
  })

  it('puts a deload in a lane under the plot, not against the kg scale', () => {
    render(<ExerciseDetailPage payload={logged()} />)
    const lane = document.querySelector('.stair__dot--deload')!
    const lines = [...document.querySelectorAll('.stair__grid')].map((line) => Number(line.getAttribute('y1')))
    const others = dots().filter((dot) => dot !== lane).map((dot) => Number(dot.getAttribute('cy')))
    expect(Number(lane.getAttribute('cy'))).toBeGreaterThan(Math.max(...lines, ...others))
    expect(within(plot()).getAllByText('Deload')).toHaveLength(1)
  })

  it('says the drought at the last tread, in the stall hue while it is one', () => {
    const { rerender } = render(<ExerciseDetailPage payload={logged()} />)
    expect(within(plot()).getByText('1 ohne Rekord')).not.toHaveClass('is-stall')
    rerender(<ExerciseDetailPage payload={logged({
      state: 'stagniert', sessions_since_pr: 4, stairs: [{ ...ALLE, since: 4, stalled: true }],
    })} />)
    expect(within(plot()).getByText('4 ohne Rekord')).toHaveClass('is-stall')
    expect(document.querySelector('.stair__tread--now')).toHaveClass('is-stall')
  })

  it('says the whole drawing in its label, one period to a sentence', () => {
    const { rerender } = render(<ExerciseDetailPage payload={logged()} />)
    expect(plot()).toHaveAttribute('aria-label', 'Geschätztes Maximum in 5 Workouts, 06.07. bis '
      + '07.09. Bestwert 95,0 kg seit 03.08., seitdem 1 Workout ohne Rekord.')
    rerender(<ExerciseDetailPage payload={logged({ stairs: [{ ...ALLE, since: 0 }] })} />)
    expect(plot()).toHaveAttribute('aria-label', 'Geschätztes Maximum in 5 Workouts, 06.07. bis '
      + '07.09. Bestwert 95,0 kg seit 03.08.')
    // A date with its year does not end the sentence by itself.
    const lastYear = ALLE.cols.map((c) => ({ ...c, started_at: c.started_at.replace('2026', '2025') }))
    rerender(<ExerciseDetailPage payload={logged({ stairs: [{ ...ALLE, cols: lastYear, since: 0 }] })} />)
    expect(plot()).toHaveAttribute('aria-label', 'Geschätztes Maximum in 5 Workouts, 06.07.2025 bis '
      + '07.09.2025. Bestwert 95,0 kg seit 03.08.2025.')
  })

  it('ticks the first workout of each month and names it', () => {
    render(<ExerciseDetailPage payload={logged()} />)
    expect(document.querySelectorAll('.stair__tick')).toHaveLength(3)
    const names = [...plot().querySelectorAll('text.stair__axis')].map((text) => text.textContent)
    expect(names).toEqual(['88', '90', '92', '94', 'Deload', 'Juli', 'Aug.', 'Sep.'])
  })

  it('says the year where the drawing crosses one, January or not', () => {
    const days = ['2025-11-10', '2025-12-08', '2026-02-09', '2026-03-09']
    const cols = days.map((day, i) => col({
      session_id: 30 + i, started_at: `${day}T17:00:00`, e1rm: 90 + i, best: 90 + i,
      kind: i === 0 ? 'workout' : 'record',
    }))
    render(<ExerciseDetailPage payload={logged({
      stairs: [{ ...ALLE, cols, lo: 88, hi: 94, ticks: [88, 90, 92, 94], since: 0 }],
    })} />)
    const names = [...document.querySelectorAll('text.stair__axis')].map((text) => text.textContent)
    expect(names.slice(-4)).toEqual(['Nov.', 'Dez.', '2026', 'März'])
  })

  it('leaves out a month name with no room, and keeps its tick', () => {
    const cols = Array.from({ length: 10 }, (_, i) => col({
      session_id: 40 + i, started_at: `2026-${String(i + 1).padStart(2, '0')}-05T17:00:00`,
      e1rm: 90, best: 90,
    }))
    render(<ExerciseDetailPage payload={logged({
      stairs: [{ ...ALLE, cols, lo: 87.5, hi: 92.5, ticks: [88, 90, 92], since: 0 }],
    })} />)
    expect(document.querySelectorAll('.stair__tick')).toHaveLength(10)
    const names = [...document.querySelectorAll('text.stair__axis')]
      .map((text) => text.textContent).filter((text) => !/^\d+$/.test(text ?? ''))
    expect(names).toEqual(['Jan.', 'März', 'Mai', 'Juni', 'Aug.', 'Okt.'])
  })

  it('names a year before a month it would run into', () => {
    // Ten months a month apart: too tight for every name. The year is placed
    // first, so "Dez." gives way to "2026" -- never the year to a month.
    const months = ['2025-08', '2025-09', '2025-10', '2025-11', '2025-12', '2026-01', '2026-02',
      '2026-03', '2026-04', '2026-05']
    const cols = months.map((month, i) => col({
      session_id: 60 + i, started_at: `${month}-05T17:00:00`, e1rm: 90, best: 90,
    }))
    render(<ExerciseDetailPage payload={logged({
      stairs: [{ ...ALLE, cols, lo: 87.5, hi: 92.5, ticks: [88, 90, 92], since: 0 }],
    })} />)
    expect(document.querySelectorAll('.stair__tick')).toHaveLength(10)
    // After the three kg labels: "2026" is all digits too.
    const names = [...document.querySelectorAll('text.stair__axis')].map((text) => text.textContent)
    expect(names.slice(3)).toEqual(['Aug.', 'Okt.', '2026', 'März', 'Mai'])
  })

  it('reads a workout out on a tap: its day, its 1RM, its sets', () => {
    render(<ExerciseDetailPage payload={logged()} />)
    expect(readout()).toHaveTextContent('Workout antippen für Details')
    const svg = plot()
    vi.spyOn(svg, 'getBoundingClientRect').mockReturnValue(
      { left: 0, top: 0, width: 358, height: 200, right: 358, bottom: 200, x: 0, y: 0 } as DOMRect)
    fireEvent.click(svg, { clientX: 200, clientY: 50 })
    expect(readout()).toHaveTextContent('Mo 03.08. · 1RM 95,0 kgRekord82,5 × 5 · 5 · 4')
    expect(document.querySelector('.stair__sel')).toHaveAttribute('visibility', 'visible')
  })

  it('walks the workouts with the arrow keys, from the newest', async () => {
    const user = userEvent.setup()
    render(<ExerciseDetailPage payload={logged()} />)
    screen.getByRole('figure').focus()
    await user.keyboard('{ArrowLeft}')
    expect(readout()).toHaveTextContent('Mo 07.09. · 1RM 94,0 kg80,0 × 7 · 6 · 6')
    await user.keyboard('{ArrowLeft}')
    expect(readout()).toHaveTextContent('Mo 17.08. · 1RM 89,0 kgDeload70,0 × 8 · 8')
    await user.keyboard('{ArrowRight}{ArrowRight}{ArrowRight}')
    expect(readout()).toHaveTextContent('Mo 07.09.')
  })

  it('draws no stair with fewer than two workouts, and keeps the sentences', () => {
    // One workout is a debut: its best is no record yet.
    render(<ExerciseDetailPage payload={logged({
      table: [{ ...HISTORY[2]!, is_record: false }], stairs: [], sessions_since_pr: null,
      pr_e1rm: { ...RECORD, is_record: false },
    })} />)
    expect(screen.queryByRole('figure')).not.toBeInTheDocument()
    expect(document.querySelector('.exrec')).toHaveTextContent(/^Bestwert 95,0 kg/)
  })

  it('reads a deload out as one where it is drawn on the plot', () => {
    // A deload the tread climbs at (here the debut) sits on the plot as a
    // workout; the readout still says what it was.
    const debut = { ...HISTORY[4]!, is_deload: true }
    render(<ExerciseDetailPage payload={logged({ table: [...HISTORY.slice(0, 4), debut] })} />)
    screen.getByRole('figure').focus()
    fireEvent.keyDown(screen.getByRole('figure'), { key: 'ArrowLeft' })
    for (let i = 0; i < 4; i++) fireEvent.keyDown(screen.getByRole('figure'), { key: 'ArrowLeft' })
    expect(readout()).toHaveTextContent(/^Mo 06\.07\. · 1RM 90,0 kgDeload77,5 × 6 · 5 · 5$/)
  })

  it('puts the lane\'s "Deload" where it runs into no ring, and inside the drawing', () => {
    // Two deload workouts in a row at the right edge: flipped left, the label
    // ran across the ring before.
    const cols = Array.from({ length: 10 }, (_, i) => col({
      session_id: 70 + i, started_at: `2026-07-${String(i * 2 + 1).padStart(2, '0')}T17:00:00`,
      e1rm: i < 8 ? 90 + i * 0.5 : 88, best: 90 + Math.min(i, 7) * 0.5,
      kind: i < 8 ? (i === 0 ? 'workout' : 'record') : 'deload',
    }))
    render(<ExerciseDetailPage payload={logged({
      stairs: [{ ...ALLE, cols, lo: 88, hi: 94, ticks: [88, 90, 92, 94], since: 0 }],
    })} />)
    const rings = [...document.querySelectorAll('.stair__dot--deload')].map((ring) => Number(ring.getAttribute('cx')))
    expect(rings).toHaveLength(2)
    const label = within(plot()).getByText('Deload')
    const x = Number(label.getAttribute('x'))
    const w = 7.5 * 'Deload'.length
    const [from, to] = label.getAttribute('text-anchor') === 'end' ? [x - w, x] : [x, x + w]
    expect(from).toBeGreaterThanOrEqual(30)
    expect(to).toBeLessThanOrEqual(358)
    for (const cx of rings) expect(cx + 4 <= from || cx - 4 >= to).toBe(true)
  })
})

describe('the position pills (G-036, D9: "Alle" first)', () => {
  const DAYS = ['2026-07-06', '2026-07-13', '2026-07-20', '2026-07-27', '2026-08-03', '2026-08-10']
  /** Six workouts, first and third in the workout by turns. */
  const table = DAYS.map((day, i) => row({
    session_id: i + 1, started_at: `${day}T17:00:00`, position: i % 2 === 0 ? 1 : 3,
  })).reverse()
  const stairOf = (position: number | null, picks: number[]): Stair => ({
    position, lo: 88, hi: 97, ticks: [90, 95], since: position === null ? 0 : null, stalled: false,
    cols: picks.map((i) => col({
      session_id: i + 1, position: i % 2 === 0 ? 1 : 3, started_at: `${DAYS[i]}T17:00:00`,
      // A record is the lift's: the debut is none, whatever slot shows it.
      e1rm: 90 + i, best: 90 + i, kind: i === 0 ? 'workout' : 'record',
    })),
  })
  const served = (over: Partial<ExerciseDetailPayload> = {}) => logged({
    table, sessions_since_pr: 0,
    stairs: [stairOf(null, [0, 1, 2, 3, 4, 5]), stairOf(1, [0, 2, 4]), stairOf(3, [1, 3, 5])],
    position_pills: [1, 3], ...over,
  })
  const pills = () => within(screen.getByRole('navigation', { name: 'Nach Reihenfolge im Workout' }))
  const plot = () => screen.getByRole('img', { name: /^Geschätztes Maximum in/ })

  it('are links, so a pill opens in a new tab as what it says', () => {
    render(<ExerciseDetailPage payload={served()} />)
    expect(pills().getByRole('link', { name: 'Alle' })).toHaveAttribute('href', '/gym/exercises/1')
    expect(pills().getByRole('link', { name: 'Als 3. Übung' }))
      .toHaveAttribute('href', '/gym/exercises/1?position=3')
    expect(pills().getByRole('link', { name: 'Alle' })).toHaveAttribute('aria-current', 'true')
  })

  it('swap the stair in place: no fetch, and the address follows without a history entry', async () => {
    const fetchMock = vi.fn()
    vi.stubGlobal('fetch', fetchMock)
    const user = userEvent.setup()
    history.replaceState(null, '', '/gym/exercises/1')
    const entries = window.history.length
    render(<ExerciseDetailPage payload={served()} />)
    expect(plot().getAttribute('aria-label')).toMatch(/^Geschätztes Maximum in 6 Workouts, 06\.07\./)

    await user.click(pills().getByRole('link', { name: 'Als 3. Übung' }))
    expect(plot().getAttribute('aria-label')).toMatch(/^Geschätztes Maximum in 3 Workouts, 13\.07\. bis 10\.08\./)
    expect(pills().getByRole('link', { name: 'Als 3. Übung' })).toHaveAttribute('aria-current', 'true')
    expect(pills().getByRole('link', { name: 'Alle' })).not.toHaveAttribute('aria-current')
    expect(window.location.pathname + window.location.search).toBe('/gym/exercises/1?position=3')

    await user.click(pills().getByRole('link', { name: 'Alle' }))
    expect(plot().getAttribute('aria-label')).toMatch(/^Geschätztes Maximum in 6 Workouts/)
    expect(window.location.pathname + window.location.search).toBe('/gym/exercises/1')
    expect(window.history.length).toBe(entries)
    expect(fetchMock).not.toHaveBeenCalled()
  })

  it('leave a modified click to the link: a new tab or window, no swap', () => {
    const replace = vi.spyOn(history, 'replaceState')
    render(<ExerciseDetailPage payload={served()} />)
    // Last in line: whether the page took the click's default, then keep
    // jsdom from following the link.
    const taken: boolean[] = []
    const after = (event: Event) => { taken.push(event.defaultPrevented); event.preventDefault() }
    window.addEventListener('click', after)
    try {
      const pill = pills().getByRole('link', { name: 'Als 3. Übung' })
      for (const key of ['ctrlKey', 'metaKey', 'shiftKey', 'altKey']) fireEvent.click(pill, { [key]: true })
      fireEvent.click(pill, { button: 1 })
    } finally {
      window.removeEventListener('click', after)
    }
    expect(taken).toEqual([false, false, false, false, false])
    expect(plot().getAttribute('aria-label')).toMatch(/^Geschätztes Maximum in 6 Workouts/)
    expect(pills().getByRole('link', { name: 'Alle' })).toHaveAttribute('aria-current', 'true')
    expect(replace).not.toHaveBeenCalled()
    replace.mockRestore()
  })

  it('lens the stair alone: the log stays the whole exercise', async () => {
    const user = userEvent.setup()
    render(<ExerciseDetailPage payload={served()} />)
    await user.click(pills().getByRole('link', { name: 'Als 1. Übung' }))
    expect(screen.getByRole('heading', { name: /^Workouts/ })).toHaveTextContent('Workouts 6')
  })

  it('start the readout over on a new stair', async () => {
    const user = userEvent.setup()
    render(<ExerciseDetailPage payload={served()} />)
    screen.getByRole('figure').focus()
    await user.keyboard('{ArrowLeft}')
    expect(document.querySelector('.exread')).toHaveTextContent('Mo 10.08.')
    await user.click(pills().getByRole('link', { name: 'Als 1. Übung' }))
    expect(document.querySelector('.exread')).toHaveTextContent('Workout antippen für Details')
  })

  it('open on the pill the address names', () => {
    render(<ExerciseDetailPage payload={served({ selected_position: 3 })} />)
    expect(pills().getByRole('link', { name: 'Als 3. Übung' })).toHaveAttribute('aria-current', 'true')
    expect(plot().getAttribute('aria-label')).toMatch(/in 3 Workouts, 13\.07\./)
  })

  it('are left out for a lift done in one slot', () => {
    render(<ExerciseDetailPage payload={logged()} />)
    expect(screen.queryByRole('navigation', { name: 'Nach Reihenfolge im Workout' })).toBeNull()
  })
})

describe('Workouts', () => {
  const log = () => within(screen.getByRole('region', { name: /^Workouts/ }))
  const SEVEN = Array.from({ length: 7 }, (_, i) => row({
    session_id: 20 - i, started_at: `2026-09-${String(21 - i * 2).padStart(2, '0')}T17:00:00`,
  }))

  it('says each workout: its day, its sets, its volume and its 1RM', () => {
    render(<ExerciseDetailPage payload={payload({ table: [row({
      started_at: '2026-08-03T17:00:00', sets: [...sets(60, 8), ...sets(62.5, 6, 6)], volume: 1230, e1rm: 75,
    })] })} />)
    const line = log().getByRole('link')
    expect(line).toHaveAttribute('href', '/gym/session/7')
    expect(line).toHaveTextContent('Mo 03.08.60,0 × 8 · 62,5 × 6 · 61.230kg1RM 75,0')
  })

  it('dates a workout from another year with its year', () => {
    render(<ExerciseDetailPage payload={payload({ table: [row({ started_at: '2025-12-15T17:00:00' })] })} />)
    expect(log().getByText('Mo 15.12.2025')).toBeInTheDocument()
  })

  it('counts a workout once when the lift sat at two slots in it', () => {
    render(<ExerciseDetailPage payload={payload({
      table: [row({ session_id: 5, position: 1 }), row({ session_id: 5, position: 4 }),
        row({ session_id: 6, position: 1 })],
    })} />)
    expect(screen.getByRole('heading', { name: /^Workouts/ })).toHaveTextContent('Workouts 2')
  })

  it('tags every row the server marks, an overtaken record and a deload record too', () => {
    // The tag is the server's per-row mark (D3); a deload can hold one (G-078).
    render(<ExerciseDetailPage payload={payload({ table: [
      row({ session_id: 9, is_record: true }), row({ session_id: 8 }),
      row({ session_id: 7, is_record: true, is_deload: true }),
    ] })} />)
    expect(log().getAllByText('Rekord', { selector: '.vtag' })).toHaveLength(2)
    expect(log().getAllByText('Deload', { selector: '.vtag' })).toHaveLength(1)
    expect(log().getByText(/^Rekord: das beste geschätzte Maximum bis zu diesem Tag\./)).toBeInTheDocument()
  })

  it('shows five, then all in place, focus on the first one it brought', async () => {
    const user = userEvent.setup()
    render(<ExerciseDetailPage payload={payload({ table: SEVEN })} />)
    expect(log().getAllByRole('link')).toHaveLength(5)
    await user.click(log().getByRole('button', { name: 'Alle 7 Workouts zeigen' }))
    const rows = log().getAllByRole('link')
    expect(rows).toHaveLength(7)
    expect(log().queryByRole('button')).toBeNull()
    await waitFor(() => expect(document.activeElement).toBe(rows[5]))
  })

  it('offers no more with five or fewer', () => {
    render(<ExerciseDetailPage payload={payload({ table: SEVEN.slice(0, 5) })} />)
    expect(log().queryByRole('button')).toBeNull()
  })

  it('says a one-sided lift logs per side', () => {
    render(<ExerciseDetailPage payload={payload({
      exercise: { ...payload().exercise, is_unilateral: true }, table: [row()],
    })} />)
    expect(log().getByText('Gewicht je Seite geloggt; das Volumen zählt beide Seiten (×2).'))
      .toBeInTheDocument()
  })
})

describe('the exercise itself', () => {
  const rowing = {
    picture: '/static/gym/art/rudern.webp', movement: 'Rudern',
    variants: [{ id: 5, label: 'Kabel, sitzend' }, { id: 6, label: 'Langhantel' }],
  }

  it('shows its drawing, and what it trains', () => {
    render(<ExerciseDetailPage payload={logged({
      exercise: { ...payload().exercise, muscle_group: 'Rücken',
        secondary_muscle_groups: ['Bizeps', 'hintere Schulter', 'Unterarme'] },
      about: rowing,
    })} />)
    expect(screen.getByRole('img', { name: 'Zeichnung: Rudern' }))
      .toHaveAttribute('src', '/static/gym/art/rudern.webp')
    expect(document.querySelector('.exabout__facts'))
      .toHaveTextContent('Trainiert Rücken, dazu Bizeps, hintere Schulter und Unterarme.')
  })

  it('folds the other variants of its movement, each a link to its page', () => {
    render(<ExerciseDetailPage payload={logged({ about: rowing })} />)
    const fold = document.querySelector('details.exalt')!
    expect(fold).not.toHaveAttribute('open')
    expect(fold.querySelector('summary')).toHaveTextContent('Rudern auch mit 2 Varianten')
    // The movement is said to a screen reader on every link: "Langhantel"
    // alone names no exercise.
    expect([...fold.querySelectorAll('a')].map((link) => [link.textContent, link.getAttribute('href')]))
      .toEqual([['Rudern Kabel, sitzend', '/gym/exercises/5'], ['Rudern Langhantel', '/gym/exercises/6']])
  })

  it('says one variant as one, and none at all', () => {
    const { rerender } = render(<ExerciseDetailPage payload={logged({
      about: { ...rowing, variants: rowing.variants.slice(0, 1) },
    })} />)
    expect(document.querySelector('.exalt summary')).toHaveTextContent('Rudern auch mit 1 Variante')
    // Whole, not a prefix: "1 Variante" is the start of "1 Varianten" too.
    expect(document.querySelector('.exalt__n')).toHaveTextContent(/^1 Variante$/)
    rerender(<ExerciseDetailPage payload={logged({ about: { ...rowing, variants: [] } })} />)
    expect(document.querySelector('.exalt')).toBeNull()
  })
})

describe('the page of an exercise never done (M6 screen 2, G-041)', () => {
  const rowing = {
    picture: '/static/gym/art/rudern.webp', movement: 'Rudern',
    variants: [{ id: 5, label: 'Kabel, sitzend' }, { id: 6, label: 'Langhantel' }],
  }
  const routines: RoutineChoice[] = [
    { id: 3, name: 'Pull', count: 6, has: true },
    { id: 4, name: 'Push', count: 7, has: false },
  ]

  it('leads with the exercise, then the ways on, what fills the page, the other variants', () => {
    const { container } = render(<ExerciseDetailPage payload={payload({ about: rowing, routines })} />)
    const order = [...container.querySelectorAll(
      '.exabout__art, .exabout__facts, .exnew__acts, .exnew__none, .exnew__alt, .sec--maint')]
      .map((node) => node.className.split(' ').find((name) => /^(ex|sec--)/.test(name)))
    expect(order).toEqual(['exabout__art', 'exabout__facts', 'exnew__acts', 'exnew__none',
      'exnew__alt', 'sec--maint'])
    // The variants open, not folded: the rack is taken, the Smith machine
    // is free.
    expect(document.querySelector('details.exalt')).toBeNull()
    const alt = screen.getByRole('region', { name: 'Rudern auch mit' })
    expect(within(alt).getAllByRole('link').map((link) => [link.textContent, link.getAttribute('href')]))
      .toEqual([['Rudern Kabel, sitzend', '/gym/exercises/5'], ['Rudern Langhantel', '/gym/exercises/6']])
  })

  it('says a lift done today in the running workout, which the page cannot show yet', () => {
    const running: RunningWorkout = { session_id: 9, name: 'Push', count: 1, logged: 2 }
    render(<ExerciseDetailPage payload={payload({ running })} />)
    expect(document.querySelector('.exnew__none')).toHaveTextContent(
      /^Heute im laufenden Workout\. Sobald es beendet ist, stehen hier dein nächstes Ziel, deine Rekorde und jedes Workout\.$/)
  })

  it('offers no way on for an exercise off the list', () => {
    render(<ExerciseDetailPage payload={payload({ on_list: false, routines })} />)
    expect(document.querySelector('.exnew__acts')).toBeNull()
    expect(screen.queryByRole('button', { name: /Workout damit beginnen|Zur Routine/ })).toBeNull()
    expect(screen.getByText(/^Noch kein Satz/)).toBeInTheDocument()
  })
})

describe('the ways on: a workout, a routine (M6 screen 2)', () => {
  /** The form the page posts, as the server receives it. */
  function posted() {
    const submit = vi.spyOn(HTMLFormElement.prototype, 'submit').mockImplementation(() => {})
    return () => submit.mock.contexts.map((form) => {
      const fields = Object.fromEntries(new FormData(form as HTMLFormElement))
      delete fields.csrf_token
      return [(form as HTMLFormElement).getAttribute('action'), fields]
    })
  }

  it('begins a workout with the exercise when none is running', async () => {
    const user = userEvent.setup()
    const forms = posted()
    render(<ExerciseDetailPage payload={payload()} />)
    const go = screen.getByRole('button', { name: 'Workout damit beginnen' })
    expect(document.querySelector('.exnew__note')).toBeNull()
    await user.click(go)
    expect(forms()).toEqual([['/gym/start', { exercise_id: '1' }]])
    // A page change is on its way: a second tap would post a second workout.
    expect(go).toBeDisabled()
  })

  it('adds it at the end of the running workout, by that workout\'s name', async () => {
    const user = userEvent.setup()
    const forms = posted()
    const running: RunningWorkout = { session_id: 9, name: 'Push', count: 0, logged: 0 }
    render(<ExerciseDetailPage payload={payload({ running })} />)
    const go = screen.getByRole('button', { name: 'Zu „Push“ hinzufügen' })
    expect(go).toHaveAccessibleDescription('Kommt ans Ende des laufenden Workouts.')
    await user.click(go)
    // `back`: finished elsewhere since, the server sends the lifter back
    // here, told so.
    expect(forms()).toEqual([['/gym/session/9/exercises/add', { exercise_id: '1', back: 'exercise' }]])
  })

  it('says a running workout with no name as the running workout', () => {
    render(<ExerciseDetailPage payload={payload({
      running: { session_id: 9, name: null, count: 0, logged: 0 },
    })} />)
    expect(screen.getByRole('button', { name: 'Zum laufenden Workout hinzufügen' })).toBeInTheDocument()
  })

  it('asks before adding it to a workout it is already in', async () => {
    const user = userEvent.setup()
    const forms = posted()
    render(<ExerciseDetailPage payload={payload({
      running: { session_id: 9, name: 'Push', count: 1, logged: 0 },
    })} />)
    const go = screen.getByRole('button', { name: 'Zu „Push“ hinzufügen' })
    expect(go).toHaveAccessibleDescription('Ist schon drin.')
    await user.click(go)
    expect(forms()).toEqual([])
    expect(go).toHaveAccessibleDescription('Nochmal hinzufügen?')
    await user.click(go)
    expect(forms()).toEqual([['/gym/session/9/exercises/add', { exercise_id: '1', back: 'exercise' }]])
  })

  it('counts it when it is in twice', () => {
    render(<ExerciseDetailPage payload={payload({
      running: { session_id: 9, name: 'Push', count: 2, logged: 0 },
    })} />)
    expect(screen.getByRole('button', { name: 'Zu „Push“ hinzufügen' }))
      .toHaveAccessibleDescription('Ist schon 2× drin.')
  })

  it('sits under "Nächstes Ziel" on a page with history', () => {
    const { container } = render(<ExerciseDetailPage payload={logged({ goal: goal() })} />)
    const main = container.querySelector('.exdetail__main')!
    expect([...main.children].slice(0, 2).map((node) => node.className))
      .toEqual(['exgoal', 'exnew__acts'])
    expect(within(main as HTMLElement).getByRole('button', { name: 'Workout damit beginnen' }))
      .toBeInTheDocument()
  })

  it('offers a routine only to a lifter with one', () => {
    render(<ExerciseDetailPage payload={payload()} />)
    expect(screen.queryByRole('button', { name: 'Zur Routine …' })).toBeNull()
  })
})

describe('Zur Routine', () => {
  const ROUTINES: RoutineChoice[] = [
    { id: 3, name: 'Pull', count: 6, has: true },
    { id: 4, name: 'Push', count: 7, has: false },
  ]

  /** The server's answer to each add: the routines after it, or a failure. */
  function server(answer: () => RoutineChoice[] | Error) {
    const fetchMock = vi.fn(async (_url: string, _init: RequestInit) => {
      const reply = answer()
      if (reply instanceof Error) return { ok: false, status: 500, json: async () => ({}) } as Response
      return { ok: true, status: 200, json: async () => ({ routines: reply }) } as Response
    })
    vi.stubGlobal('fetch', fetchMock)
    return fetchMock
  }

  async function open(user: ReturnType<typeof userEvent.setup>) {
    render(<ExerciseDetailPage payload={payload({ routines: ROUTINES })} />)
    await user.click(screen.getByRole('button', { name: 'Zur Routine …' }))
    return within(document.getElementById('sheet-routine')!)
  }

  it('lists the routines, and says where the exercise already is', async () => {
    const user = userEvent.setup()
    const fetchMock = server(() => ROUTINES)
    const sheet = await open(user)
    expect(sheet.getByText('Bankdrücken kommt ans Ende der Routine, die du antippst.')).toBeInTheDocument()
    const pull = sheet.getByRole('button', { name: /Pull/ })
    expect(pull).toHaveTextContent('Pull6 Übungendrin')
    expect(pull).toHaveAttribute('aria-disabled', 'true')
    await user.click(pull)
    expect(fetchMock).not.toHaveBeenCalled()
    expect(sheet.getByRole('button', { name: /Push/ })).not.toHaveAttribute('aria-disabled')
  })

  it('adds it to the routine tapped, and stays open for another', async () => {
    const user = userEvent.setup()
    const fetchMock = server(() => [ROUTINES[0]!, { ...ROUTINES[1]!, count: 8, has: true }])
    const sheet = await open(user)
    await user.click(sheet.getByRole('button', { name: /Push/ }))
    await waitFor(() => expect(fetchMock).toHaveBeenCalledOnce())
    const [url, init] = fetchMock.mock.calls[0]!
    expect(url).toBe('/gym/templates/4/exercises/add')
    expect((init.body as FormData).get('exercise_id')).toBe('1')
    expect(await sheet.findByRole('status')).toHaveTextContent('Bankdrücken ist jetzt in „Push“.')
    const push = sheet.getByRole('button', { name: /Push/ })
    expect(push).toHaveTextContent('Push8 Übungendrin')
    expect(push).toHaveAttribute('aria-disabled', 'true')
    // The row tapped keeps the focus as it turns.
    expect(push).toHaveFocus()
    expect(document.getElementById('sheet-routine')).toHaveAttribute('open')
  })

  it('says a failed add, and lets the row be tapped again', async () => {
    const user = userEvent.setup()
    let fail = true
    const fetchMock = server(() => (fail ? new Error('down') : [ROUTINES[0]!, { ...ROUTINES[1]!, count: 8, has: true }]))
    const sheet = await open(user)
    await user.click(sheet.getByRole('button', { name: /Push/ }))
    expect(await sheet.findByText('Nicht gespeichert. Nochmal antippen.')).toBeInTheDocument()
    const push = sheet.getByRole('button', { name: /Push/ })
    expect(push).not.toHaveAttribute('aria-disabled')
    expect(push).toHaveTextContent('Push7 Übungen')
    fail = false
    await user.click(push)
    await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(2))
    expect(await sheet.findByText('Bankdrücken ist jetzt in „Push“.')).toBeInTheDocument()
  })

  it('dims the row on its way, and takes no other tap until it lands', async () => {
    // A slow add read as a tap that did nothing, and a tap on the next
    // routine went nowhere, unsaid.
    const user = userEvent.setup()
    let land: (reply: Response) => void = () => {}
    const fetchMock = vi.fn(() => new Promise<Response>((resolve) => { land = resolve }))
    vi.stubGlobal('fetch', fetchMock)
    const routines = [...ROUTINES, { id: 5, name: 'Beine', count: 5, has: false }]
    render(<ExerciseDetailPage payload={payload({ routines })} />)
    await user.click(screen.getByRole('button', { name: 'Zur Routine …' }))
    const sheet = within(document.getElementById('sheet-routine')!)
    const push = sheet.getByRole('button', { name: /Push/ })
    const beine = sheet.getByRole('button', { name: /Beine/ })
    await user.click(push)
    expect(push).toHaveClass('is-busy')
    expect(beine).toHaveAttribute('aria-disabled', 'true')
    expect(beine).not.toHaveClass('is-busy')
    await user.click(beine)
    expect(fetchMock).toHaveBeenCalledOnce()
    land({ ok: true, status: 200, json: async () => ({
      routines: [ROUTINES[0]!, { ...ROUTINES[1]!, count: 8, has: true }, routines[2]!],
    }) } as Response)
    await waitFor(() => expect(push).not.toHaveClass('is-busy'))
    expect(beine).not.toHaveAttribute('aria-disabled')
  })
})

describe('Deine Einstellungen', () => {
  /** The sheet open on `exercise`, with the server answering each save with
   *  `answer`. The page's refresh after a save (a GET) is answered apart and
   *  not counted. */
  function sheet(exercise: ExerciseMeta, answer?: (fields: FormData) => ExerciseMeta | Error) {
    let saved = exercise
    const fetchMock = vi.fn(async (_url: string, init: RequestInit) => {
      const fields = init.body as FormData
      const reply = answer?.(fields) ?? exercise
      if (reply instanceof Error) throw reply
      saved = reply
      return { ok: true, status: 200, json: async () => reply } as Response
    })
    vi.stubGlobal('fetch', (url: string, init?: RequestInit) => (init?.body === undefined
      ? Promise.resolve({
        ok: true, status: 200, redirected: false, url, json: async () => payload({ exercise: saved }),
      } as Response)
      : fetchMock(url, init)))
    window.history.replaceState(null, '', '/gym/exercises/1#einstellungen')
    render(<ExerciseDetailPage payload={payload({ exercise })} />)
    return { fetchMock, dialog: within(document.querySelector('dialog')!) }
  }

  const setting = (name: string) =>
    within(screen.getByRole('heading', { name }).closest('section')!)

  it('says where each value comes from, and marks what it falls back to', () => {
    sheet(stackExercise)
    const rest = setting('Pause nach jedem Satz')
    expect(rest.getByText('Deine')).toBeInTheDocument()
    expect(rest.getAllByRole('button').map((b) => b.textContent))
      .toEqual(['0:30', '1:00', '1:30Standard', '2:00', '2:30', 'Andere'])
    expect(rest.getByRole('button', { name: '2:00' })).toHaveAttribute('aria-pressed', 'true')

    const step = setting('Schritt bei + und − (kg)')
    expect(step.getAllByRole('button').map((b) => b.textContent))
      .toEqual(['2,5Standard', '5', '7', '8', '10', 'Andere'])
    expect(step.getByRole('button', { name: '5' })).toHaveAttribute('aria-pressed', 'true')

    const stops = setting('Gewichtsstufen')
    expect(stops.getByText('5, 13, 21')).toBeInTheDocument()
    expect(stops.getByRole('button', { name: 'Gewichtsstufen ändern' })).toBeInTheDocument()
    expect(stops.getByRole('button', { name: 'Wieder gleichmäßig' })).toBeInTheDocument()
  })

  it('goes back to the standard stops by that name', () => {
    sheet({ ...stackExercise,
      list_defaults: { ...stackExercise.list_defaults, stack_kg: [5, 10, 15] } })
    expect(setting('Gewichtsstufen').getByRole('button', { name: 'Zurück zum Standard' }))
      .toBeInTheDocument()
  })

  it('asks for a bar only where the list knows one, and stops only on a stack', () => {
    sheet(payload().exercise)
    const bar = setting('Stangengewicht (kg)')
    expect(bar.getAllByRole('button').map((b) => b.textContent))
      .toEqual(['Ohne', '10', '15', '20Standard', '25', 'Andere'])
    expect(screen.queryByRole('heading', { name: 'Gewichtsstufen' })).toBeNull()
  })

  it('never asks a stack for a bar', () => {
    sheet(stackExercise)
    expect(screen.queryByRole('heading', { name: 'Stangengewicht (kg)' })).toBeNull()
  })

  it('saves a tap at once, one field, and shows it as the lifter\'s', async () => {
    const user = userEvent.setup()
    const { fetchMock } = sheet(payload().exercise, (fields) => ({
      ...payload().exercise, default_rest_seconds: Number(fields.get('default_rest_seconds')),
      own: ['default_rest_seconds'],
    }))
    const rest = setting('Pause nach jedem Satz')
    expect(rest.getByText('Standard', { selector: '.setting__src' })).toBeInTheDocument()

    await user.click(rest.getByRole('button', { name: '2:30' }))
    await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(1))
    const [url, init] = fetchMock.mock.calls[0]!
    expect(url).toBe('/gym/exercises/1/update')
    expect([...(init.body as FormData).entries()]).toEqual([['default_rest_seconds', '150']])
    expect(rest.getByRole('button', { name: '2:30' })).toHaveAttribute('aria-pressed', 'true')
    expect(await rest.findByText('Deine')).toBeInTheDocument()
  })

  it('goes back to the standard in one tap', async () => {
    const user = userEvent.setup()
    const { fetchMock } = sheet(stackExercise, () => ({
      ...stackExercise, default_rest_seconds: 90,
      own: stackExercise.own.filter((f) => f !== 'default_rest_seconds'),
    }))
    const rest = setting('Pause nach jedem Satz')
    await user.click(rest.getByRole('button', { name: '1:30 Standard' }))
    await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(1))
    expect([...(fetchMock.mock.calls[0]![1].body as FormData).entries()])
      .toEqual([['default_rest_seconds', '90']])
    expect(rest.getByText('Standard', { selector: '.setting__src' })).toBeInTheDocument()
  })

  it('puts the value back and says why when a save fails', async () => {
    const user = userEvent.setup()
    sheet(payload().exercise, () => new TypeError('Failed to fetch'))
    const rest = setting('Pause nach jedem Satz')
    await user.click(rest.getByRole('button', { name: '2:30' }))
    expect(await screen.findByRole('alert'))
      .toHaveTextContent('Verbindung fehlgeschlagen — deine letzte Änderung wurde nicht gespeichert.')
    expect(rest.getByRole('button', { name: '1:30 Standard' })).toHaveAttribute('aria-pressed', 'true')
  })

  it('falls back to the rest for all, and calls an own rest an exception', () => {
    sheet({ ...payload().exercise, default_rest_seconds: 180, rest_for_all: 150,
      own: ['default_rest_seconds'] })
    expect(screen.getByText('Nur für dich. Ohne Ausnahme gilt deine Pause, 2:30.'))
      .toBeInTheDocument()
    const rest = setting('Pause nach jedem Satz')
    expect(rest.getByText('Ausnahme')).toBeInTheDocument()
    expect(rest.getAllByRole('button').map((b) => b.textContent))
      .toEqual(['1:30', '2:00', '2:30Deine', '3:00', '3:30', 'Andere'])
  })

  it('says a rest that is not its own follows the rest for all', () => {
    sheet({ ...payload().exercise, default_rest_seconds: 150, rest_for_all: 150, own: [] })
    const rest = setting('Pause nach jedem Satz')
    expect(rest.getByText('Wie deine Pause', { selector: '.setting__src' })).toBeInTheDocument()
  })

  it('takes a machine\'s own stops typed once, and only a list of them', async () => {
    const user = userEvent.setup()
    const even = { ...stackExercise, stack_kg: null,
      own: stackExercise.own.filter((f) => f !== 'stack_kg') }
    const { fetchMock } = sheet(even)
    const stops = setting('Gewichtsstufen')
    // The step, not a ladder from 0: a real stack starts where it starts (G-042).
    expect(stops.getByText('Gleichmäßig, in Schritten von 5 kg.')).toBeInTheDocument()

    await user.click(stops.getByRole('button', { name: 'Das Gerät hat andere Gewichtsstufen' }))
    const field = stops.getByLabelText(/Jede Gewichtsstufe in kg/)
    await user.type(field, '12')
    expect(stops.getByRole('button', { name: 'Übernehmen' })).toBeDisabled()
    await user.type(field, ', 5; 19')
    await user.click(stops.getByRole('button', { name: 'Übernehmen' }))
    await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(1))
    expect([...(fetchMock.mock.calls[0]![1].body as FormData).entries()])
      .toEqual([['stack_kg', '5, 12, 19']])
  })

  it('says the new step in the goal\'s rule once it is saved', async () => {
    // A new step moves where every set goes next: the rule must not keep
    // saying the old weight until a reload.
    const user = userEvent.setup()
    const stepped: ExerciseMeta = { ...payload().exercise, weight_increment: 5, own: ['weight_increment'] }
    vi.stubGlobal('fetch', vi.fn(async (url: string, init?: RequestInit) => {
      const body = init?.body === undefined
        ? logged({ exercise: stepped, goal: goal({ step_ups: [45, 45, 45] }) })
        : stepped
      return { ok: true, status: 200, redirected: false, url, json: async () => body } as Response
    }))
    window.history.replaceState(null, '', '/gym/exercises/1#einstellungen')
    render(<ExerciseDetailPage payload={logged({ goal: goal() })} />)
    expect(document.querySelector('.exgoal__rule')).toHaveTextContent('(42,5 kg)')
    await user.click(setting('Schritt bei + und − (kg)').getByRole('button', { name: '5' }))
    await waitFor(() => expect(document.querySelector('.exgoal__rule')).toHaveTextContent('(45 kg)'))
  })
})
