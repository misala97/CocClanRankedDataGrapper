import { fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { HistoryPage, tonnes } from './HistoryPage'
import type { HistoryEntry, HistoryIndexMonth, HistoryPayload, HistoryRecord } from './types'
import { queryInAddress, recordsInAddress, useHistoryUi, withQuery, withRecords } from './store'
import { useSheets } from '../session/stores'

beforeEach(() => {
  useHistoryUi.setState(useHistoryUi.getInitialState(), true)
  window.history.replaceState(null, '', '/gym/verlauf')
})

const entry = (over: Partial<HistoryEntry> = {}): HistoryEntry => ({
  session_id: 7, name: 'Push Day', started_at: '2026-09-23T16:00:00',
  finished_at: '2026-09-23T16:52:00', is_deload: false, auto_finished: false,
  volume: 4200, record_count: 0, records: [], exercises: ['Bankdrücken', 'Dips'], partners: [],
  search: 'push day\n23.09.2026 september 2026', gap_days: null, ...over,
})

const payload = (entries: HistoryEntry[]): HistoryPayload => ({
  months: [{ label: 'September 2026', slug: '2026-09', entries, volume: 4200, records: 0 }],
  total: entries.length, gap_threshold: 14,
  summary: null, weeks: null, index: [], biggest_session_id: null,
  weekday_short: ['Mo', 'Di', 'Mi', 'Do', 'Fr', 'Sa', 'So'], running_session_id: null,
  exercise_search: {
    Bankdrücken: 'bankdrucken langhantel\nbench press\nflachbankdrucken', Dips: 'dips maschine',
  },
})

describe('HistoryPage', () => {
  it('says which workouts the app ended itself (D5)', () => {
    // Its end is its last set's time, three hours before anyone closed it.
    render(<HistoryPage payload={payload([entry({ auto_finished: true })])} />)
    expect(screen.getByText(/52 min · automatisch beendet$/)).toBeInTheDocument()
  })

  it('says nothing more about a workout the lifter finished', () => {
    render(<HistoryPage payload={payload([entry()])} />)
    expect(screen.getByText(/52 min$/)).toBeInTheDocument()
    expect(screen.queryByText(/automatisch beendet/)).not.toBeInTheDocument()
  })

  it('says no duration for a workout under a minute (G-024)', () => {
    // Imported rows end where they start: "< 1 min" beside 7.8 t.
    render(<HistoryPage payload={payload([entry({ finished_at: '2026-09-23T16:00:20' })])} />)
    expect(document.querySelector('.row__meta')).toHaveTextContent(/^Mi · 23\.09\. · \d\d:00$/)
  })
})

describe('the Verlauf search (G-145)', () => {
  const legs = entry({
    session_id: 8, name: 'Leg Day', exercises: ['Kniebeugen'],
    search: 'leg day\n20.09.2026 september 2026',
  })
  const both = () => ({
    ...payload([entry(), legs]),
    exercise_search: {
      ...payload([]).exercise_search, Kniebeugen: 'kniebeugen langhantel\nsquat\nback squat',
    },
  })
  const names = () => [...document.querySelectorAll('.row__name')].map((n) => n.textContent)

  it('finds a workout by what its exercises are also called, and by a typo', async () => {
    render(<HistoryPage payload={both()} />)
    const field = screen.getByRole('searchbox')
    await userEvent.type(field, 'bench')
    expect(names()).toEqual(['Push Day'])
    // The exercise it was found by comes first, marked.
    expect(document.querySelector('mark.row__hit')?.textContent).toBe('Bankdrücken')
    await userEvent.clear(field)
    await userEvent.type(field, 'Kniebeigen')
    expect(names()).toEqual(['Leg Day'])
    expect(document.querySelector('mark.row__hit')?.textContent).toBe('Kniebeugen')
  })

  it('finds by the date words and the name, umlauts folded', async () => {
    render(<HistoryPage payload={both()} />)
    const field = screen.getByRole('searchbox')
    await userEvent.type(field, '20.09')
    expect(names()).toEqual(['Leg Day'])
    await userEvent.clear(field)
    await userEvent.type(field, 'PUSH')
    expect(names()).toEqual(['Push Day'])
    expect(document.querySelector('mark.row__hit')).toBeNull()
    await userEvent.clear(field)
    await userEvent.type(field, 'BANKDRÜCKEN')
    expect(names()).toEqual(['Push Day'])
    expect(document.querySelector('mark.row__hit')?.textContent).toBe('Bankdrücken')
  })

  it('says when what it shows is only a typo away', async () => {
    render(<HistoryPage payload={both()} />)
    const field = screen.getByRole('searchbox')
    await userEvent.type(field, 'Kniebeigen')
    expect(screen.getByText('Kein genauer Treffer für „Kniebeigen“ – ähnlich geschrieben:'))
      .toBeInTheDocument()
    await userEvent.clear(field)
    await userEvent.type(field, 'Kniebeugen')
    expect(names()).toEqual(['Leg Day'])
    expect(screen.queryByText(/Kein genauer Treffer/)).toBeNull()
  })

  it('takes a whole name before its words: "Push 2" is not every Push', async () => {
    const two = entry({
      session_id: 9, name: 'Push 2', search: 'push 2\n31.07.2026 juli 2026',
    })
    const push = entry({ session_id: 10, name: 'Push', search: 'push\n23.09.2026 september 2026' })
    render(<HistoryPage payload={payload([two, push])} />)
    const field = screen.getByRole('searchbox')
    await userEvent.type(field, 'push 2')
    expect(names()).toEqual(['Push 2'])
    await userEvent.clear(field)
    await userEvent.type(field, 'push 23.09')
    expect(names()).toEqual(['Push'])
  })

  it('marks the exercise that holds the whole query, not its words spread over two', async () => {
    const flat = entry({ session_id: 11, name: 'A', exercises: ['Bankdrücken (Langhantel)', 'Seitheben (Kurzhantel)'] })
    const dumbbell = entry({ session_id: 12, name: 'B', exercises: ['Bankdrücken (Kurzhantel)', 'Dips'] })
    render(<HistoryPage payload={{
      ...payload([flat, dumbbell]),
      exercise_search: {
        'Bankdrücken (Langhantel)': 'bankdrucken langhantel\nbench press',
        'Seitheben (Kurzhantel)': 'seitheben kurzhantel\nlateral raise',
        'Bankdrücken (Kurzhantel)': 'bankdrucken kurzhantel\ndumbbell bench press',
        Dips: 'dips maschine',
      },
    }} />)
    await userEvent.type(screen.getByRole('searchbox'), 'Bankdrücken Kurzhantel')
    expect(names()).toEqual(['B'])
    expect([...document.querySelectorAll('mark.row__hit')].map((m) => m.textContent))
      .toEqual(['Bankdrücken (Kurzhantel)'])
  })

  it('reads a query that folds to nothing as none', async () => {
    render(<HistoryPage payload={both()} />)
    await userEvent.type(screen.getByRole('searchbox'), '-')
    expect(names()).toEqual(['Push Day', 'Leg Day'])
    expect(document.querySelector('mark.row__hit')).toBeNull()
  })
})

// ---- M3: what Statistik said about the whole history, said here ----------

const record = (over: Partial<HistoryRecord> = {}): HistoryRecord => ({
  exercise_id: 10, name: 'Bankdrücken', weight: 100, reps: 5, e1rm: 116.7, previous: 113.3,
  ...over,
})

const indexMonth = (over: Partial<HistoryIndexMonth>): HistoryIndexMonth => ({
  year: 2026, month: 8, label: 'August 2026', short: 'Aug', slug: '2026-08',
  volume: 0, deload_volume: 0, records: 0, is_gap: false, is_current: false, ...over,
})

/** Four workouts over four months, July without one: newest first, as the
 *  route sends them. */
const career = (): HistoryPayload => {
  const push = entry({ record_count: 1, records: [record()] })
  const push2 = entry({
    session_id: 9, name: 'Push Day 2', started_at: '2026-09-16T16:00:00',
    finished_at: '2026-09-16T17:00:00', volume: 2000,
    search: 'push day 2\n16.09.2026 september 2026',
  })
  const legs = entry({
    session_id: 8, name: 'Leg Day', started_at: '2026-08-20T16:00:00',
    finished_at: '2026-08-20T17:00:00', volume: 4000, exercises: ['Kniebeugen', 'Beinpresse'],
    search: 'leg day\n20.08.2026 august 2026', gap_days: 27, record_count: 2,
    records: [
      record({ exercise_id: 11, name: 'Kniebeugen', weight: 120, reps: 3, e1rm: 132, previous: 130 }),
      record({ exercise_id: 12, name: 'Beinpresse', weight: 200, reps: 8, e1rm: 253.3, previous: 250 }),
    ],
  })
  const pull = entry({
    session_id: 6, name: 'Pull Day', started_at: '2026-06-10T16:00:00',
    finished_at: '2026-06-10T17:00:00', volume: 3000, exercises: ['Klimmzüge'],
    search: 'pull day\n10.06.2026 juni 2026', gap_days: 71,
  })
  return {
    ...payload([]),
    months: [
      { label: 'September 2026', slug: '2026-09', entries: [push, push2], volume: 6200, records: 1 },
      { label: 'August 2026', slug: '2026-08', entries: [legs], volume: 4000, records: 2 },
      { label: 'Juni 2026', slug: '2026-06', entries: [pull], volume: 3000, records: 0 },
    ],
    total: 4,
    summary: { workouts: 4, first_at: '2026-06-10T16:00:00', tonnage: 15_400, longest_gap: 71 },
    weeks: { weeks_trained: 5, weeks_total: 16, longest_streak: 2 },
    index: [
      indexMonth({ month: 6, label: 'Juni 2026', short: 'Jun', slug: '2026-06', volume: 3000 }),
      indexMonth({ month: 7, label: 'Juli 2026', short: 'Jul', slug: '2026-07', is_gap: true }),
      indexMonth({ volume: 4000, deload_volume: 1000, records: 2 }),
      indexMonth({
        month: 9, label: 'September 2026', short: 'Sep', slug: '2026-09', volume: 6200,
        deload_volume: 500, records: 1, is_current: true,
      }),
    ],
    biggest_session_id: 7,
  }
}

const names = () => [...document.querySelectorAll('.row__name')].map((n) => n.textContent)
const lede = () => document.querySelector('.verlauf__lede')
const hitsLine = () => document.querySelector('.verlauf__hits')
const index = () => screen.getByRole('navigation', { name: 'Monate' })
const onlyRecords = () => screen.getByRole('button', { name: 'Nur Rekorde' })

describe('the lede', () => {
  it('says how many, since when, how much, and the longest break', () => {
    render(<HistoryPage payload={career()} />)
    expect(lede()).toHaveTextContent(
      '4 Workouts seit dem 10.06.2026, zusammen 15 Tonnen. Die längste Pause: 71 Tage.')
  })

  it('says "am" of a single workout, and no break', () => {
    render(<HistoryPage payload={{
      ...payload([entry({ volume: 850 })]),
      summary: { workouts: 1, first_at: '2026-09-23T16:00:00', tonnage: 850, longest_gap: 2 },
    }} />)
    expect(lede()).toHaveTextContent(/^1 Workout am 23\.09\.2026, zusammen 850 kg\.$/)
  })

  it('leaves out a tonnage of nothing and a break under a day', () => {
    render(<HistoryPage payload={{
      ...payload([entry({ volume: 0 }), entry({ session_id: 8, volume: 0 })]),
      summary: { workouts: 2, first_at: '2026-09-23T10:00:00', tonnage: 0, longest_gap: 0 },
    }} />)
    expect(lede()).toHaveTextContent(/^2 Workouts seit dem 23\.09\.2026\.$/)
  })

  it('says tonnes the way they are said', () => {
    // A figure keeps its unit on its line; 9.999 kg is ten tonnes, not "10,0".
    expect([352_400, 15_400, 10_000, 9_999, 3_240, 999.6, 850].map(tonnes))
      .toEqual(['352', '15', '10', '10', '3,2', '1,0'].map((t) => `${t} Tonnen`).concat('850 kg'))
  })

  it('never says a tonnage the next unit up would round to', () => {
    expect(tonnes(999.4)).toBe('999 kg')
    expect(tonnes(9_949)).toBe('9,9 Tonnen')
  })
})

describe('the month index', () => {
  const bars = () => [...index().querySelectorAll<HTMLElement>('.mindex__bar')]

  it('draws a bar per month, the tallest month the full height', () => {
    render(<HistoryPage payload={career()} />)
    expect(bars().map((bar) => bar.style.blockSize)).toEqual(['29px', '3px', '39px', '60px'])
    expect(bars().map((bar) => bar.className)).toEqual([
      'mindex__bar', 'mindex__bar is-gap', 'mindex__bar is-deload', 'mindex__bar is-current'])
    // The deload share of a finished month, hatched from the foot.
    expect(bars()[2]!.style.getPropertyValue('--deload-share')).toBe('25%')
    expect(bars()[3]!.style.getPropertyValue('--deload-share')).toBe('0%')
    expect([...index().querySelectorAll('.mindex__m')].map((m) => m.textContent))
      .toEqual(['Jun', 'Jul', 'Aug', 'Sep'])
    expect([...index().querySelectorAll('.mindex__rec')].map((r) => r.textContent)).toEqual(['2', '1'])
  })

  it('says each month in words, and jumps to its band', () => {
    render(<HistoryPage payload={career()} />)
    const months = within(index()).getAllByRole('listitem')
    expect(months).toHaveLength(4)
    expect(within(months[0]!).getByRole('link', { name: 'Juni 2026: 3.000 kg' }))
      .toHaveAttribute('href', '#monat-2026-06')
    expect(within(months[1]!).queryByRole('link')).toBeNull()
    expect(months[1]!.querySelector('.sr-only')).toHaveTextContent('Juli 2026: kein Workout')
    expect(within(months[2]!).getByRole('link', {
      name: /^August 2026: 4\.000 kg, 2\sRekorde, davon 1\.000 kg Deload$/,
    })).toHaveAttribute('href', '#monat-2026-08')
    expect(within(months[3]!).getByRole('link', {
      name: /^September 2026: 6\.200 kg, 1\sRekord, läuft noch$/,
    })).toHaveAttribute('href', '#monat-2026-09')
    // Each band is where the link goes.
    expect(document.getElementById('monat-2026-08')).toHaveAccessibleName('August 2026')
  })

  it('keys only what it draws', () => {
    render(<HistoryPage payload={career()} />)
    expect([...index().querySelectorAll('.mindex__key li')].map((li) => li.textContent))
      .toEqual(['Tonnage', 'Deload-Anteil', 'Monat ohne Workout', 'Läuft noch', 'Rekorde'])
    const plain = career()
    plain.index = [indexMonth({ volume: 4000 })]
    render(<HistoryPage payload={plain} />)
    expect([...screen.getAllByRole('navigation', { name: 'Monate' })[1]!
      .querySelectorAll('.mindex__key li')].map((li) => li.textContent)).toEqual(['Tonnage'])
  })

  it('unlinks a month the search or the filter empties', async () => {
    render(<HistoryPage payload={career()} />)
    const linked = () => [...index().querySelectorAll('a.mindex__mo')].map((a) => a.getAttribute('href'))
    expect(linked()).toEqual(['#monat-2026-06', '#monat-2026-08', '#monat-2026-09'])
    await userEvent.click(onlyRecords())
    expect(linked()).toEqual(['#monat-2026-08', '#monat-2026-09'])
    expect(index().querySelectorAll('.mindex__mo.is-off')).toHaveLength(2)
  })

  it.each([
    [{ weeks_trained: 6, weeks_total: 6, longest_streak: 6 }, 'In jeder der 6 Wochen trainiert.'],
    [{ weeks_trained: 3, weeks_total: 8, longest_streak: 1 }, 'In 3 von 8 Wochen trainiert.'],
    [{ weeks_trained: 5, weeks_total: 8, longest_streak: 5 }, 'In 5 von 8 Wochen trainiert, alle am Stück.'],
    [{ weeks_trained: 5, weeks_total: 16, longest_streak: 2 }, 'In 5 von 16 Wochen trainiert, 2 davon am Stück.'],
  ])('states the weeks trained: %o', (weeks, said) => {
    render(<HistoryPage payload={{ ...career(), weeks }} />)
    expect(index().querySelector('.mindex__cap')).toHaveTextContent(said)
  })

  it('says nothing of weeks it cannot state yet', () => {
    render(<HistoryPage payload={{ ...career(), weeks: null }} />)
    expect(index().querySelector('.mindex__cap')).toBeNull()
  })

  it('marks each January with its year', () => {
    // Past twelve months the strip would read "Sep … Sep".
    const turn = career()
    turn.index = [
      indexMonth({ year: 2026, month: 12, label: 'Dezember 2026', short: 'Dez', slug: '2026-12', volume: 900 }),
      indexMonth({ year: 2027, month: 1, label: 'Januar 2027', short: 'Jan', slug: '2027-01', volume: 900 }),
      indexMonth({ year: 2027, month: 2, label: 'Februar 2027', short: 'Feb', slug: '2027-02', volume: 900 }),
    ]
    render(<HistoryPage payload={turn} />)
    expect([...index().querySelectorAll('.mindex__m')].map((m) => m.textContent))
      .toEqual(['Dez', 'Jan ’27', 'Feb'])
  })

  it('fades the edge that has months out of view (G-046)', () => {
    // jsdom lays nothing out: a strip 400 wide over 1000 of months.
    let left = 0
    const strip = (el: Element) => el.classList.contains('mindex__bars')
    const layout: [string, PropertyDescriptor][] = [
      ['scrollWidth', { get(this: Element) { return strip(this) ? 1000 : 0 } }],
      ['clientWidth', { get(this: Element) { return strip(this) ? 400 : 0 } }],
      ['scrollLeft', { get: () => left, set: (v: number) => { left = Math.min(Math.max(v, 0), 600) } }],
    ]
    const own = layout.map(([name]) => [name, Object.getOwnPropertyDescriptor(HTMLElement.prototype, name)] as const)
    for (const [name, get] of layout) Object.defineProperty(HTMLElement.prototype, name, { configurable: true, ...get })
    try {
      render(<HistoryPage payload={career()} />)
      const bars = index().querySelector('.mindex__bars')!
      // Opened at the newest month: the older ones wait past the start.
      expect(bars).toHaveAttribute('data-more', 'start')
      left = 300
      fireEvent.scroll(bars)
      expect(bars).toHaveAttribute('data-more', 'both')
      left = 0
      fireEvent.scroll(bars)
      expect(bars).toHaveAttribute('data-more', 'end')
    } finally {
      for (const [name, was] of own) {
        if (was) Object.defineProperty(HTMLElement.prototype, name, was)
        else delete (HTMLElement.prototype as unknown as Record<string, unknown>)[name]
      }
    }
  })

  it('fades nothing while every month fits', () => {
    render(<HistoryPage payload={career()} />)
    expect(index().querySelector('.mindex__bars')).not.toHaveAttribute('data-more')
  })

  it('steps aside with the lede while rows are picked for export', async () => {
    render(<HistoryPage payload={career()} />)
    await userEvent.click(screen.getByRole('button', { name: 'Exportieren' }))
    expect(screen.queryByRole('navigation', { name: 'Monate' })).not.toBeInTheDocument()
    expect(lede()).toBeNull()
    expect(document.querySelector('.export__picked')).toHaveTextContent('0 ausgewählt')
  })
})

describe('Nur Rekorde', () => {
  it('shows the workouts that set one, each record on its row', async () => {
    render(<HistoryPage payload={career()} />)
    expect(onlyRecords()).toHaveAttribute('aria-pressed', 'false')
    await userEvent.click(onlyRecords())
    expect(onlyRecords()).toHaveAttribute('aria-pressed', 'true')
    expect(names()).toEqual(['Push Day', 'Leg Day'])
    const bench = screen.getByRole('link', {
      name: 'Bankdrücken: Rekord mit 100,0 kg × 5, geschätztes Maximum 116,7 kg, '
        + '+3,4 kg über dem alten (113,3 kg)',
    })
    expect(bench).toHaveAttribute('href', '/gym/exercises/10')
    expect(bench.querySelector('.recs__meta')).toHaveTextContent('100,0 kg × 5 · 1RM 116,7 kg')
    expect(bench.querySelector('.gain')).toHaveTextContent('+3,4kg')
    expect(screen.getByRole('list', { name: /^2\sRekorde in diesem Workout$/ }))
      .toHaveTextContent(/Kniebeugen.*Beinpresse/)
    // The records stand in for the exercise line and the count.
    expect(document.querySelector('.row__sub')).toBeNull()
    expect(document.querySelector('.verlauf__rc')).toBeNull()
  })

  it('counts the records and the workouts it left, and says what a record is', async () => {
    render(<HistoryPage payload={career()} />)
    expect(hitsLine()).toBeEmptyDOMElement()
    await userEvent.click(onlyRecords())
    expect(hitsLine()).toHaveTextContent(
      '3 Rekorde in 2 von 4 Workouts. Ein Rekord ist ein neues geschätztes Maximum (1RM).')
    expect([...document.querySelectorAll('.month__n')].map((n) => n.textContent!.replace(/\s/g, ' ')))
      .toEqual(['1 von 2 Workouts', '1 Workout'])
  })

  it('keeps itself in the address, and every other part of it', async () => {
    window.history.replaceState(null, '', '/gym/verlauf?x=1#monat-2026-08')
    render(<HistoryPage payload={career()} />)
    await userEvent.click(onlyRecords())
    expect(window.location.pathname + window.location.search + window.location.hash)
      .toBe('/gym/verlauf?x=1&rekorde#monat-2026-08')
    await userEvent.click(onlyRecords())
    expect(window.location.search).toBe('?x=1')
  })

  it('says so when no workout set one, and offers the way back', async () => {
    render(<HistoryPage payload={payload([entry(), entry({ session_id: 8, name: 'Leg Day' })])} />)
    await userEvent.click(onlyRecords())
    expect(screen.getByRole('status')).toHaveTextContent(
      'Noch kein Rekord. Ein Rekord ist ein neues geschätztes Maximum (1RM). Alle Workouts zeigen')
    expect(hitsLine()).toBeEmptyDOMElement()
    await userEvent.click(screen.getByRole('button', { name: 'Alle Workouts zeigen' }))
    expect(onlyRecords()).toHaveAttribute('aria-pressed', 'false')
    expect(names()).toEqual(['Push Day', 'Leg Day'])
  })

  it('combines with the search', async () => {
    render(<HistoryPage payload={career()} />)
    await userEvent.click(onlyRecords())
    await userEvent.type(screen.getByRole('searchbox'), 'pull')
    expect(screen.getByRole('status')).toHaveTextContent(
      'Kein Workout mit Rekord gefunden für pull. Suche zurücksetzen')
  })
})

describe('the rows of the whole history', () => {
  it('counts what the search left', async () => {
    render(<HistoryPage payload={career()} />)
    const field = screen.getByRole('searchbox')
    await userEvent.type(field, 'push')
    expect(hitsLine()).toHaveTextContent('2 von 4 Workouts passen.')
    await userEvent.clear(field)
    await userEvent.type(field, 'pull')
    expect(hitsLine()).toHaveTextContent('1 von 4 Workouts passt.')
    expect([...document.querySelectorAll('.month__n')].map((n) => n.textContent!.replace(/\s/g, ' ')))
      .toEqual(['1 Workout'])
  })

  it('marks a break, but only while nothing narrows the list', async () => {
    render(<HistoryPage payload={career()} />)
    const gaps = () => [...document.querySelectorAll('.gap')].map((g) => g.textContent)
    expect(gaps()).toEqual(['27 Tage Pause', '71 Tage Pause'])
    await userEvent.type(screen.getByRole('searchbox'), 'day')
    expect(gaps()).toEqual([])
    await userEvent.clear(screen.getByRole('searchbox'))
    expect(gaps()).toHaveLength(2)
    await userEvent.click(onlyRecords())
    expect(gaps()).toEqual([])
  })

  it('names the biggest workout, on its row alone', () => {
    render(<HistoryPage payload={career()} />)
    const tagged = [...document.querySelectorAll('.vtag--max')]
    expect(tagged).toHaveLength(1)
    expect(tagged[0]!.closest('.verlauf__row')!.querySelector('.row__name'))
      .toHaveTextContent('Push Day')
    expect(tagged[0]).toHaveTextContent('Größtes Workout')
  })

  it('counts each workout\'s records beside it while the filter is off', () => {
    render(<HistoryPage payload={career()} />)
    expect([...document.querySelectorAll('.verlauf__rc')].map((c) => c.textContent!.replace(/\s/g, ' ')))
      .toEqual(['1 Rekord', '2 Rekorde'])
  })
})

describe('the filter in the address', () => {
  it('reads it', () => {
    expect(recordsInAddress('?rekorde')).toBe(true)
    expect(recordsInAddress('?x=1&rekorde')).toBe(true)
    expect(recordsInAddress('?x=1')).toBe(false)
    expect(recordsInAddress('')).toBe(false)
  })

  it('writes it bare, and drops it without a stray "?"', () => {
    expect(withRecords('', true)).toBe('?rekorde')
    expect(withRecords('?rekorde', true)).toBe('?rekorde')
    expect(withRecords('?x=1', true)).toBe('?x=1&rekorde')
    expect(withRecords('?rekorde&x=1', false)).toBe('?x=1')
    expect(withRecords('?rekorde', false)).toBe('')
    expect(withRecords('?q=bank', true)).toBe('?q=bank&rekorde')
  })
})

describe('the search in the address (G-043)', () => {
  it('reads it', () => {
    expect(queryInAddress('?q=bank')).toBe('bank')
    expect(queryInAddress('?rekorde&q=rudern%20t-bar')).toBe('rudern t-bar')
    expect(queryInAddress('?rekorde')).toBe('')
  })

  it('writes it beside the filter, and drops it when blank', () => {
    expect(withQuery('', 'bank')).toBe('?q=bank')
    expect(withQuery('?rekorde', 'rudern t-bar')).toBe('?q=rudern%20t-bar&rekorde')
    expect(withQuery('?q=bank&rekorde', '')).toBe('?rekorde')
    expect(withQuery('?q=bank', '  ')).toBe('')
  })

  it('keeps what is typed in the address, the filter with it', async () => {
    // Back, forward and a reload lost the search: it lived in memory only.
    const user = userEvent.setup()
    render(<HistoryPage payload={payload([entry()])} />)
    await user.click(screen.getByRole('button', { name: /Nur Rekorde/ }))
    await user.type(screen.getByRole('searchbox'), 'push')
    expect(window.location.search).toBe('?q=push&rekorde')
    await user.clear(screen.getByRole('searchbox'))
    expect(window.location.search).toBe('?rekorde')
  })

  it('starts from the search the address holds', async () => {
    window.history.replaceState(null, '', '/gym/verlauf?q=bank&rekorde')
    vi.resetModules()
    const fresh = await import('./store')
    expect(fresh.useHistoryUi.getState().query).toBe('bank')
    expect(fresh.useHistoryUi.getState().onlyRecords).toBe(true)
  })
})

describe('an empty Verlauf (G-003)', () => {
  const empty = (running: number | null): HistoryPayload => ({
    ...payload([]), months: [], total: 0, running_session_id: running,
  })

  it('starts a workout from here, with a heading and one line', () => {
    // A 17 px link sent the lifter to Start to begin one there.
    render(<HistoryPage payload={empty(null)} />)
    expect(screen.getByRole('heading', { name: 'Noch keine beendeten Workouts' }))
      .toBeInTheDocument()
    const form = screen.getByRole('button', { name: 'Workout starten' }).closest('form')!
    expect(form).toHaveAttribute('action', '/gym/start')
    expect(form).toHaveAttribute('method', 'post')
    expect(form.querySelector('[name=csrf_token]')).not.toBeNull()
    expect(form.querySelector('[name=template_id]')).toBeNull()
    expect(screen.queryAllByRole('link')).toHaveLength(0)
  })

  it('goes back into the workout that is running instead', () => {
    // gym_start answers with the running workout anyway: "Workout starten"
    // would have said one thing and done another.
    render(<HistoryPage payload={empty(58)} />)
    expect(document.querySelector('.void__line'))
      .toHaveTextContent('Dein erstes läuft gerade. Sobald es beendet ist, steht es hier.')
    expect(screen.getByRole('link', { name: 'Weiter' })).toHaveAttribute('href', '/gym/session/58')
    expect(screen.queryByRole('button', { name: 'Workout starten' })).not.toBeInTheDocument()
  })
})

describe('"mit <Name>" on a row (D14)', () => {
  beforeEach(() => { useSheets.setState(useSheets.getInitialState(), true) })
  afterEach(() => { vi.unstubAllGlobals() })

  it("sits beside the row's link, and opens the partner's list as it ended", async () => {
    const user = userEvent.setup()
    vi.stubGlobal('fetch', vi.fn(async () => new Response(JSON.stringify({
      id: 5, username: 'jglaser', viewer_leads: false, link_live: false,
      since: '2026-09-23T16:02:00', started_at: '2026-09-23T15:58:00',
      finished_at: '2026-09-23T17:01:00', sets_done: 9, sets_total: 9, rest_left: null,
      rows: [{ id: 1, name: 'Bankdrücken', picture: null, state: 'done',
        sets: [{ weight: 60, reps: 8 }], open: 0 }],
    }))))
    render(<HistoryPage payload={payload([entry({ partners: [{ id: 5, username: 'jglaser' }] })])} />)
    const mit = screen.getByRole('button', { name: 'Zusammen mit jglaser. Liste von jglaser ansehen' })
    // Not inside the link: the row still opens the workout, this the list.
    expect(mit.closest('a')).toBeNull()
    expect(mit.closest('.verlauf__row')).not.toBeNull()
    await user.click(mit)
    const sheet = screen.getByRole('dialog', { name: 'jglaser' })
    await waitFor(() => expect(sheet)
      .toHaveTextContent(/Mi 23\.09\.\S* · fertig um 19:01 · 9 von 9 Sätzen/))
    // Closed, it takes its history entry back: none is left for the next test.
    await user.click(within(sheet).getByRole('button', { name: 'Fertig' }))
    expect(sheet).not.toHaveAttribute('open')
  })

  it('names no partner for a workout done alone', () => {
    render(<HistoryPage payload={payload([entry()])} />)
    expect(screen.queryByRole('button', { name: /^Zusammen mit/ })).toBeNull()
  })
})
