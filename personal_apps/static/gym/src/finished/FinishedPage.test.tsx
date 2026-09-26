import { act, render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { FinishedPage } from './FinishedPage'
import type { FinishedExercise, FinishedPayload, SessionRecord } from './types'
import { useSheets } from '../session/stores'
import { useUndo } from '../undo'

beforeEach(() => {
  useSheets.setState(useSheets.getInitialState(), true)
})

const exercise = (over: Partial<FinishedExercise> = {}): FinishedExercise => ({
  exercise_id: 10, name: 'Bankdrücken', position: 1,
  sets: [[60, 8], [60, 8]], sets_display: '2 × 60 kg', volume: 960,
  best_weight: 60, e1rm: 75, has_history: true, is_record: false, record: null,
  sessions_since_pr: 2, verdict: null, next_sets: null,
  set_rows: [{ id: 501, weight: 60, reps: 8, is_record: false },
    { id: 502, weight: 60, reps: 8, is_record: false }],
  session_exercise_id: 90, notes: null, pain: false, best: null, ...over,
})

const record = (over: Partial<SessionRecord> = {}): SessionRecord => ({
  kind: 'e1rm', name: 'Bankdrücken', exercise_id: 10, position: 1,
  value: 72.5, weight: 60, reps: 8, previous: 70, previous_at: '2026-07-20T10:00:00', ...over,
})

const base: FinishedPayload = {
  session: {
    id: 42, name: 'Push Day',
    started_at: '2026-08-09T16:00:00', finished_at: '2026-08-09T17:05:00',
    auto_finished: false, is_deload: false, deload_pct: null, bodyweight_kg: null, notes: null,
    template_id: null, template_name: null,
  },
  exercises: [exercise()],
  total_volume: 12345,
  total_sets: 2,
  records: [],
  record_count: 0,
  comparison: null,
  plan_moved_to: null,
  plan_base: null,
  partners: [],
  is_deload: false,
  deload_default_pct: 60,
  deload_applied: false,
  tick_states: ['done', 'done'],
  set_pace_seconds: null,
  unlogged: [],
  weekday_short: ['Mo', 'Di', 'Mi', 'Do', 'Fr', 'Sa', 'So'],
  just_finished: false,
  template_exercises: null,
  template_next_exercises: null,
}

const mount = (over: Partial<FinishedPayload> = {}) =>
  render(<FinishedPage payload={{ ...base, ...over }} />)

const deload = (over: Partial<FinishedPayload> = {}): Partial<FinishedPayload> => ({
  session: { ...base.session, is_deload: true, deload_pct: 70 },
  is_deload: true, ...over,
})

const empty: Partial<FinishedPayload> = { total_sets: 0, total_volume: 0, exercises: [], tick_states: [] }

/** Dates in a sentence carry their year only when it is not this one. */
const inSeptember2026 = () => {
  vi.useFakeTimers({ toFake: ['Date'] })
  vi.setSystemTime(new Date('2026-09-25T12:00:00Z'))
}
afterEach(() => { vi.useRealTimers() })

/**
 * The markup half of the finished-page tests that used to live in the Python
 * suite: those now assert on the payload the server embeds, and the rendering
 * they grepped for is asserted here.
 */
describe('FinishedPage', () => {
  it('heads with the session, its date and its duration', () => {
    mount()
    expect(screen.getByRole('heading', { level: 1 })).toHaveTextContent('Push Day')
    // The weekday leads the date, which is printed once -- the name often
    // embeds one already.
    expect(screen.getByText('So 09.08.2026 · 65 Minuten')).toBeInTheDocument()
    expect(screen.queryByText(/Automatisch beendet/)).not.toBeInTheDocument()
  })

  it('says no duration for a workout under a minute (G-024)', () => {
    // Imported workouts end where they start; "unter 1 Minute" beside the
    // tonnage read as a fact.
    mount({ session: { ...base.session, finished_at: '2026-08-09T16:00:40' } })
    expect(screen.getByText('So 09.08.2026')).toBeInTheDocument()
    expect(screen.queryByText(/Minute/)).not.toBeInTheDocument()
  })

  it('says when the app ended the workout itself (D5)', () => {
    // Its end is the last set, and the duration stops there.
    mount({ session: { ...base.session, auto_finished: true } })
    expect(screen.getByText('Automatisch beendet — nach 3 Stunden ohne Satz.'))
      .toBeInTheDocument()
  })

  it('labels a deload in the header, with its percentage only when applied', () => {
    const { container, unmount } = mount({ ...deload(), deload_applied: true })
    expect(container.querySelector('.vtag--deload')).toHaveTextContent('Deload 70 %')
    unmount()
    const later = mount(deload())
    expect(later.container.querySelector('.vtag--deload')).toHaveTextContent(/^Deload$/)
  })

  describe('what was done', () => {
    it('leads with the volume, the counts beside it', () => {
      const { container } = mount()
      expect(screen.getByText('12.345')).toBeInTheDocument()
      expect(container.querySelector('.grew__side')).toHaveTextContent(/^2 Sätze1 Übung$/)
    })

    it('counts one set as one (G-011)', () => {
      const { container } = mount({ total_sets: 1, tick_states: ['done'] })
      expect(container.querySelector('.grew__side')).toHaveTextContent(/^1 Satz1 Übung$/)
      expect(screen.getByRole('img')).toHaveAccessibleName('1 Satz erledigt')
    })

    it('says an empty workout does not count, and no volume', () => {
      mount(empty)
      expect(screen.getByText('Kein Satz erfasst — dieses Workout zählt nicht mit.'))
        .toBeInTheDocument()
      expect(screen.queryByText('kg bewegt')).not.toBeInTheDocument()
    })

    it('keeps no headline verdict, tiles, mean or last time (D10)', () => {
      // "N neue Rekorde.", the three tiles, "+13 % zum Schnitt dieses
      // Workouts" and "Letztes Mal … · Schnitt …" are gone: one line compares.
      const { container } = mount({ records: [record()], record_count: 1 })
      expect(screen.queryByText(/neuer Rekord\./)).not.toBeInTheDocument()
      expect(container.querySelector('.band, .verdict, .finished__prev')).toBeNull()
      expect(screen.queryByText(/Letztes Mal|dieses Workouts/)).not.toBeInTheDocument()
    })
  })

  describe('the one comparison (D10)', () => {
    const against = [
      { id: 71, started_at: '2026-08-27T16:00:00', volume: 10218 },
      { id: 67, started_at: '2026-08-23T16:00:00', volume: 10498 },
    ]

    it('names both workouts it is measured against, newest first, a tap away', () => {
      inSeptember2026()
      mount({ comparison: { pct: 2, against } })
      const line = screen.getByText(/zum Schnitt von/)
      expect(line).toHaveTextContent('+2 % zum Schnitt von Do 27.08. und So 23.08.')
      const links = within(line).getAllByRole('link')
      expect(links.map((link) => link.getAttribute('href')))
        .toEqual(['/gym/session/71', '/gym/session/67'])
    })

    it('says less with a true minus, and the same as ±0', () => {
      mount({ comparison: { pct: -17, against } })
      expect(screen.getByText('−17 %')).toBeInTheDocument()
      mount({ comparison: { pct: 0, against } })
      expect(screen.getByText('±0 %')).toBeInTheDocument()
    })

    it('says why a deload has none', () => {
      mount(deload())
      expect(screen.getByText('Deload: bewusst leichter, darum ohne Vergleich.'))
        .toBeInTheDocument()
    })

    it('is silent without one', () => {
      mount()
      expect(screen.queryByText(/zum Schnitt|ohne Vergleich/)).not.toBeInTheDocument()
      mount({ ...deload(), ...empty })
      expect(screen.queryByText(/ohne Vergleich/)).not.toBeInTheDocument()
    })
  })

  describe('the tick strip', () => {
    it('counts the gold ticks in its label, not the records', () => {
      // 21 ticks with 1 gold once announced "davon 3 mit Rekord": the label
      // counted records while the strip shows record SETS.
      mount({ tick_states: ['done', 'record', 'done'], total_sets: 3,
              records: [record()], record_count: 1 })
      expect(screen.getByRole('img'))
        .toHaveAccessibleName('3 Sätze erledigt, davon 1 mit Rekord')
    })

    it('says nothing about records when none earned a tick', () => {
      mount()
      expect(screen.getByRole('img')).toHaveAccessibleName('2 Sätze erledigt')
    })
  })

  describe('records', () => {
    it('flares exactly one, however many there are, with the set that made it', () => {
      inSeptember2026()
      mount({
        records: [record(), record({ name: 'Dips', exercise_id: 11 }),
          record({ name: 'Rudern', exercise_id: 12 })],
        record_count: 3,
      })
      expect(screen.getAllByText('Neuer Rekord')).toHaveLength(1)
      expect(screen.getByText('72,5')).toBeInTheDocument()
      // Named in full once, its first use on the page (D16); no position.
      expect(screen.getByText(
        'geschätztes Maximum (1RM), aus 60,0 kg × 8 · vorher 70,0 kg am 20.07.')).toBeInTheDocument()
      // The rest say themselves on their own rows, not in a list of their own.
      expect(screen.queryByRole('region', { name: 'Weitere Rekorde' })).toBeNull()
    })

    it('celebrates on arrival, not on every later visit', () => {
      const { container } = mount({ records: [record()], record_count: 1 })
      expect(container.querySelector('.record-flare')).not.toHaveClass('is-fresh')
      const fresh = mount({ records: [record()], record_count: 1, just_finished: true })
      expect(fresh.container.querySelector('.record-flare')).toHaveClass('is-fresh')
    })
  })

  it('prescribes nothing beside the plan', () => {
    // The advice box's "auf 68,0 kg gehen" was a second answer to what to
    // lift, and could disagree with "Nächstes Mal".
    mount({ exercises: [exercise({ verdict: 'stagniert', sessions_since_pr: 4 })] })
    expect(screen.queryByText(/gehen, notfalls/)).not.toBeInTheDocument()
  })

  describe('the exercise rows', () => {
    const rows = () => screen.getByRole('region', { name: 'Übungen' })

    it('stands next time under what was done, set by set (D10)', () => {
      mount({ exercises: [exercise({
        set_rows: [{ id: 501, weight: 27.5, reps: 10, is_record: false },
          { id: 502, weight: 27.5, reps: 9, is_record: false },
          { id: 503, weight: 27.5, reps: 8, is_record: false }],
        next_sets: [{ weight: 27.5, reps: 11 }, { weight: 27.5, reps: 10 }, { weight: 27.5, reps: 9 }],
      })] })
      const steps = rows().querySelector('.steps')!
      expect(steps).not.toHaveClass('steps--flow')
      expect(steps).toHaveTextContent('Geschafft27,5kg×10·9·8Nächstes Mal27,5kg×11·10·9')
      expect((steps as HTMLElement).style.getPropertyValue('--n')).toBe('3')
      expect(steps.querySelectorAll('.steps__c--next')).toHaveLength(6)
    })

    it('stands a longer or a shorter plan under what was done, too', () => {
      const done = (reps: number[]) => reps.map((count, i) =>
        ({ id: 510 + i, weight: 60, reps: count, is_record: i === 0 }))
      const next = (reps: number[]) => reps.map((count) => ({ weight: 60, reps: count }))
      // The routine holds a set more than was done: the last one repeated.
      const longer = mount({ exercises: [exercise({
        set_rows: done([10, 9, 8]), next_sets: next([10, 10, 9, 9]) })] })
      const steps = longer.container.querySelector('.steps') as HTMLElement
      expect(steps).not.toHaveClass('steps--flow')
      expect(steps.style.getPropertyValue('--n')).toBe('4')
      // The record set's reps are gold in the grid too.
      expect(steps.querySelectorAll('.is-record')).toHaveLength(1)
      longer.unmount()
      // A set fewer: the routine holds three now.
      const shorter = mount({ exercises: [exercise({
        set_rows: done([10, 9, 8, 8]), next_sets: next([11, 10, 9]) })] })
      expect(shorter.container.querySelector('.steps')).not.toHaveClass('steps--flow')
    })

    it('lets set under set run on where it is wider than its row, until the row is wide enough', () => {
      // A pyramid's three weights at 390 px: a grid cannot wrap, and it
      // pushed the page sideways. jsdom lays nothing out; the widths are set.
      const observers = new Set<() => void>()
      vi.stubGlobal('ResizeObserver', class {
        constructor(private readonly notify: () => void) {}
        observe() { observers.add(this.notify) }
        disconnect() { observers.delete(this.notify) }
      })
      let room = 330
      const needs = vi.spyOn(Element.prototype, 'scrollWidth', 'get').mockImplementation(
        function (this: Element) { return this.classList.contains('steps--flow') ? room : 420 })
      const has = vi.spyOn(Element.prototype, 'clientWidth', 'get').mockImplementation(() => room)
      try {
        mount({ exercises: [exercise({
          next_sets: [{ weight: 60, reps: 9 }, { weight: 60, reps: 9 }] })] })
        expect(rows().querySelector('.steps')).toHaveClass('steps--flow')
        room = 480
        act(() => { observers.forEach((notify) => notify()) })
        expect(rows().querySelector('.steps')).not.toHaveClass('steps--flow')
      } finally {
        needs.mockRestore()
        has.mockRestore()
        vi.unstubAllGlobals()
      }
    })

    it('lets the lines run on where the weights change at other places', () => {
      mount({ exercises: [exercise({
        next_sets: [{ weight: 62.5, reps: 6 }, { weight: 60, reps: 9 }],
      })] })
      expect(rows().querySelector('.steps')).toHaveClass('steps--flow')
      expect(rows().querySelector('.steps')).toHaveTextContent(
        'Geschafft60,0kg×8·8Nächstes Mal62,5kg×6·60,0kg×9')
    })

    it("lets a deload's lines run on: its plan comes from the workout before", () => {
      mount({ ...deload(), exercises: [exercise({
        next_sets: [{ weight: 80, reps: 9 }, { weight: 80, reps: 9 }],
      })] })
      expect(rows().querySelector('.steps')).toHaveClass('steps--flow')
    })

    it('shows only what was done without a plan', () => {
      mount()
      expect(rows().querySelector('.steps')).toBeNull()
      expect(rows().querySelector('.steps__done')).toHaveTextContent('60,0kg×8·8')
      expect(within(rows()).queryByText('Nächstes Mal')).not.toBeInTheDocument()
    })

    it('washes the reps of a set that beat the record gold', () => {
      mount({ exercises: [exercise({
        set_rows: [{ id: 501, weight: 60, reps: 8, is_record: false },
          { id: 502, weight: 60, reps: 10, is_record: true }],
      })] })
      const gold = rows().querySelectorAll('.is-record')
      expect(gold).toHaveLength(1)
      expect(gold[0]).toHaveTextContent('10')
    })

    it('says what a record beat, and chips it', () => {
      mount({ exercises: [exercise({ is_record: true, verdict: 'rekord',
                                     record: { value: 71.5, previous: 68.3 } })] })
      expect(within(rows()).getByText(/^Rekord: 1RM/))
        .toHaveTextContent('Rekord: 1RM 71,5 kg, vorher 68,3 kg')
      expect(rows().querySelector('.vtag--record')).toHaveTextContent('Rekord')
    })

    it('says how long a lift has stood still, and when it is new', () => {
      mount({ exercises: [
        exercise({ position: 1, verdict: 'stagniert', sessions_since_pr: 4 }),
        exercise({ position: 2, exercise_id: 11, session_exercise_id: 91, verdict: 'neu' }),
      ] })
      expect(within(rows()).getByText('Seit 4 Workouts ohne Rekord')).toBeInTheDocument()
      expect(within(rows()).getByText('Zum ersten Mal')).toBeInTheDocument()
      // The one chip left is "Rekord" (D10).
      expect(rows().querySelector('.vtag')).toBeNull()
    })

    const hit = (id: number) => exercise({ exercise_id: id, session_exercise_id: id,
      is_record: true, verdict: 'rekord', record: { value: 80, previous: 75 } })

    it('says an all-record workout once instead of in every chip', () => {
      mount({ exercises: [hit(1), hit(2), hit(3)] })
      expect(screen.getByText('Alle 3 Übungen mit Rekord.')).toBeInTheDocument()
      expect(rows().querySelector('.vtag--record')).toBeNull()
      expect(within(rows()).getAllByText(/^Rekord: 1RM/)).toHaveLength(3)
    })

    it('chips each record where not every row set one', () => {
      mount({ exercises: [hit(1), hit(2), exercise({ exercise_id: 3, session_exercise_id: 3 })] })
      expect(screen.queryByText(/Übungen mit Rekord\./)).not.toBeInTheDocument()
      expect(rows().querySelectorAll('.vtag--record')).toHaveLength(2)
    })

    it('points to the newer workout the plan moved on to', () => {
      inSeptember2026()
      mount({ plan_moved_to: { id: 12686, started_at: '2026-09-23T16:00:00' } })
      const pointer = within(rows()).getByRole('link', { name: /Der Plan fürs nächste Mal/ })
      expect(pointer).toHaveTextContent(
        'Der Plan fürs nächste Mal steht jetzt beim Workout vom Mi 23.09.')
      expect(pointer).toHaveAttribute('href', '/gym/session/12686')
    })

    it('points only the rest there while a row still plans here', () => {
      // A lift the newer workout left out: its next live card builds on
      // this row, so its plan stays, and the pointer speaks for the others.
      inSeptember2026()
      mount({ plan_moved_to: { id: 12686, started_at: '2026-09-23T16:00:00' },
              exercises: [exercise({ next_sets: [{ weight: 80, reps: 9 }] }),
                          exercise({ exercise_id: 2, session_exercise_id: 2 })] })
      expect(within(rows()).getByRole('link', { name: /steht jetzt beim Workout/ }))
        .toHaveTextContent(/^Der Plan für die übrigen Übungen steht jetzt beim Workout vom Mi 23\.09\.$/)
      expect(within(rows()).getAllByText('Nächstes Mal')).toHaveLength(1)
    })

    it("names the workout a deload's plan builds on", () => {
      inSeptember2026()
      const planned = [exercise({ next_sets: [{ weight: 80, reps: 9 }] })]
      mount({ ...deload(), exercises: planned,
              plan_base: { id: 5, started_at: '2026-07-24T16:00:00' } })
      expect(screen.getByText(
        'Nächstes Mal wieder mit deinen Arbeitsgewichten, aufgebaut auf Fr 24.07.'))
        .toBeInTheDocument()
      // A date with its year ends the sentence with a stop of its own.
      mount({ ...deload(), exercises: planned,
              plan_base: { id: 4, started_at: '2025-07-24T16:00:00' } })
      expect(screen.getByText(/aufgebaut auf Do 24\.07\.2025\.$/)).toBeInTheDocument()
      mount({ ...deload(), exercises: planned })
      expect(screen.getByText('Nächstes Mal wieder mit deinen Arbeitsgewichten, '
        + 'aufgebaut auf dem jeweils letzten Workout davor.')).toBeInTheDocument()
    })

    it("keeps a deload's note under the pointer while a row still plans", () => {
      inSeptember2026()
      mount({ ...deload(), plan_moved_to: { id: 12686, started_at: '2026-09-23T16:00:00' },
              exercises: [exercise({ next_sets: [{ weight: 80, reps: 9 }] })],
              plan_base: { id: 5, started_at: '2026-07-24T16:00:00' } })
      expect(within(rows()).getByRole('link', { name: /steht jetzt beim Workout/ }))
        .toBeInTheDocument()
      expect(screen.getByText(
        'Nächstes Mal wieder mit deinen Arbeitsgewichten, aufgebaut auf Fr 24.07.'))
        .toBeInTheDocument()
    })

    it('says nothing of next time on a deload without a plan', () => {
      mount(deload())
      expect(screen.queryByText(/Arbeitsgewichten/)).not.toBeInTheDocument()
    })

    it('opens the sheet for a workout with nothing logged, too', async () => {
      mount({ ...empty, unlogged: [{ session_exercise_id: 91, name: 'Butterfly', best: null }] })
      await userEvent.click(screen.getByRole('button', { name: /Sätze & Notizen/ }))
      expect(within(screen.getByRole('dialog')).getByText('Butterfly')).toBeInTheDocument()
    })

    it('leaves the list out when there is nothing in it', () => {
      mount(empty)
      expect(screen.queryByRole('region', { name: 'Übungen' })).toBeNull()
    })
  })

  describe('the correction sheet', () => {
    it('edits the real set rows', async () => {
      mount()
      await userEvent.click(screen.getByRole('button', { name: /Sätze & Notizen/ }))
      const sheet = screen.getByRole('dialog')
      const forms = within(sheet).getAllByRole('button', { name: /Satz \d speichern/ })
      expect(forms).toHaveLength(2)
      expect(forms[0]!.closest('form')).toHaveAttribute('action', '/gym/set/501/update')
      expect(forms[1]!.closest('form')).toHaveAttribute('action', '/gym/set/502/update')
    })

    it('carries the note and the pain flag', async () => {
      mount({ exercises: [exercise({ notes: 'Knie zwickt', pain: true })] })
      await userEvent.click(screen.getByRole('button', { name: /Sätze & Notizen/ }))
      const sheet = screen.getByRole('dialog')
      expect(within(sheet).getByRole('checkbox', { name: /Schmerz/ })).toBeChecked()
      expect(within(sheet).getByLabelText('Notiz')).toHaveValue('Knie zwickt')
    })

    it('offers no note form for an exercise with no session row behind it', async () => {
      mount({ exercises: [exercise({ session_exercise_id: null })] })
      await userEvent.click(screen.getByRole('button', { name: /Sätze & Notizen/ }))
      const sheet = screen.getByRole('dialog')
      expect(within(sheet).queryByRole('checkbox')).not.toBeInTheDocument()
    })
  })

  it('offers bodyweight and a session note, which only this screen can edit', async () => {
    mount({ session: { ...base.session, bodyweight_kg: 91.4, notes: 'nach Feierabend' } })
    await userEvent.click(screen.getByRole('button', { name: /Körpergewicht/ }))
    const sheet = screen.getByRole('dialog')
    expect(within(sheet).getByLabelText(/Körpergewicht/)).toHaveValue(91.4)
    expect(within(sheet).getByLabelText('Notiz')).toHaveValue('nach Feierabend')
  })

  describe('the template prompt', () => {
    it('offers to save a freeform workout as a template', () => {
      mount({ just_finished: true })
      expect(screen.getByText('Dieses Workout als Routine speichern?')).toBeInTheDocument()
      const input = screen.getByLabelText('Name der neuen Routine')
      // template_name, not name: gym_save_as_template reads the former, and
      // the route redirects identically whether it saved anything or not.
      expect(input).toHaveAttribute('name', 'template_name')
      expect(input.closest('form'))
        .toHaveAttribute('action', '/gym/session/42/save_as_template')
    })

    it('offers to update the routine a template workout came from', () => {
      mount({
        just_finished: true,
        session: { ...base.session, template_id: 3, template_name: 'Push' },
        // A real difference -- with none, the prompt (rightly) does not exist.
        template_exercises: ['Dips'],
        template_next_exercises: ['Bankdrücken'],
      })
      expect(screen.getByText(/mit dieser Übungsliste und Reihenfolge aktualisieren/))
        .toBeInTheDocument()
      expect(screen.getByRole('button', { name: 'Routine aktualisieren' }).closest('form'))
        .toHaveAttribute('action', '/gym/session/42/update_template')
    })

    it('states what the update would change', () => {
      // The rendered diff that replaced the blind confirm(). Both halves are
      // server-computed: the "after" is what the update route would actually
      // write, not the performed list.
      mount({
        just_finished: true,
        session: { ...base.session, template_id: 3, template_name: 'Push' },
        template_exercises: ['Dips'],
        template_next_exercises: ['Bankdrücken'],
      })
      const diff = document.querySelector('.prompt__diff')!
      expect(diff.textContent).toContain('Neu: Bankdrücken.')
      expect(diff.textContent).toContain('Entfällt: Dips.')
    })

    it('names what moves in a reorder (G-077)', () => {
      mount({
        just_finished: true,
        session: { ...base.session, template_id: 3, template_name: 'Pull' },
        template_exercises: ['Bizepscurls', 'Hammercurls', 'Rudern'],
        template_next_exercises: ['Hammercurls', 'Bizepscurls', 'Rudern'],
      })
      expect(document.querySelector('.prompt__diff')!.textContent)
        .toBe('Reihenfolge: Hammercurls jetzt vor Bizepscurls.')
    })

    it('names one exercise moved back as that one, not each it passed (G-077)', () => {
      mount({
        just_finished: true,
        session: { ...base.session, template_id: 3, template_name: 'Pull' },
        template_exercises: ['Latzug', 'Rudern', 'Face Pulls', 'Bizepscurls'],
        template_next_exercises: ['Rudern', 'Face Pulls', 'Bizepscurls', 'Latzug'],
      })
      expect(document.querySelector('.prompt__diff')!.textContent)
        .toBe('Reihenfolge: Latzug jetzt nach Bizepscurls.')
    })

    it('says an order change beside a list change (G-077)', () => {
      // The walkthrough's "Nur die Reihenfolge ändert sich." stood where the
      // list had changed; with a change in the list, the order went unsaid.
      mount({
        just_finished: true,
        session: { ...base.session, template_id: 3, template_name: 'Pull' },
        template_exercises: ['Bizepscurls', 'Hammercurls', 'Face Pulls'],
        template_next_exercises: ['Hammercurls', 'Bizepscurls', 'Rudern'],
      })
      expect(document.querySelector('.prompt__diff')!.textContent).toBe(
        'Neu: Rudern. Entfällt: Face Pulls. Reihenfolge: Hammercurls jetzt vor Bizepscurls.')
    })

    it('keeps the update in the menu when the workout is opened again (G-077, Q6)', async () => {
      // The offer used to exist only on ?just_finished: reopened from
      // Verlauf, the workout had no way to update its routine at all.
      mount({
        session: { ...base.session, template_id: 3, template_name: 'Pull' },
        template_exercises: ['Bizepscurls', 'Hammercurls'],
        template_next_exercises: ['Hammercurls', 'Bizepscurls'],
      })
      expect(document.querySelector('.prompt')).toBeNull()
      await userEvent.click(screen.getByRole('button', { name: 'Routine „Pull“ aktualisieren …' }))
      const sheet = screen.getByRole('dialog')
      expect(within(sheet).getByText('Reihenfolge: Hammercurls jetzt vor Bizepscurls.'))
        .toBeInTheDocument()
      expect(within(sheet).getByRole('button', { name: 'Routine aktualisieren' }).closest('form'))
        .toHaveAttribute('action', '/gym/session/42/update_template')
    })

    it("updates the routine from its sheet without leaving the sheet's entry behind (B7 re-review)", async () => {
      // Back from the page the update lands on found that entry: a dead step.
      const user = userEvent.setup()
      history.replaceState({ page: 'debrief' }, '')
      const sent: unknown[] = []
      const submit = vi.spyOn(HTMLFormElement.prototype, 'submit')
        .mockImplementation(function record(this: HTMLFormElement) {
          sent.push([this.getAttribute('action'), history.state])
        })
      mount({
        session: { ...base.session, template_id: 3, template_name: 'Pull' },
        template_exercises: ['Bizepscurls', 'Hammercurls'],
        template_next_exercises: ['Hammercurls', 'Bizepscurls'],
      })
      await user.click(screen.getByRole('button', { name: 'Routine „Pull“ aktualisieren …' }))
      const sheet = screen.getByRole('dialog')
      await user.click(within(sheet).getByRole('button', { name: 'Routine aktualisieren' }))
      await waitFor(() => expect(sent).toHaveLength(1))
      expect(sent[0]).toEqual(['/gym/session/42/update_template', { page: 'debrief' }])
      submit.mockRestore()
    })

    it('closes the sheet on back, not the debrief (G-066)', async () => {
      history.replaceState(null, '')
      mount({
        session: { ...base.session, template_id: 3, template_name: 'Pull' },
        template_exercises: ['Bizepscurls', 'Hammercurls'],
        template_next_exercises: ['Hammercurls', 'Bizepscurls'],
      })
      await userEvent.click(screen.getByRole('button', { name: 'Routine „Pull“ aktualisieren …' }))
      expect((history.state as { gymSheet?: boolean } | null)?.gymSheet).toBe(true)
      const popped = new Promise<void>((resolve) => {
        window.addEventListener('popstate', () => resolve(), { once: true })
      })
      history.back()
      await act(() => popped)
      expect(useSheets.getState().openId).toBeNull()
    })

    it('offers the update once on arrival: in the prompt, not the menu (G-077)', () => {
      mount({
        just_finished: true,
        session: { ...base.session, template_id: 3, template_name: 'Pull' },
        template_exercises: ['Bizepscurls', 'Hammercurls'],
        template_next_exercises: ['Hammercurls', 'Bizepscurls'],
      })
      expect(screen.getAllByRole('button', { name: /aktualisieren/ })).toHaveLength(1)
      expect(document.querySelector('.prompt')).not.toBeNull()
    })

    it('keeps no update in the menu that would change nothing (G-077)', () => {
      mount({
        session: { ...base.session, template_id: 3, template_name: 'Pull' },
        template_exercises: ['Bizepscurls'],
        template_next_exercises: ['Bizepscurls'],
      })
      expect(screen.queryByRole('button', { name: /aktualisieren/ })).toBeNull()
    })

    it('lists the new order when much of it moves (G-077)', () => {
      mount({
        just_finished: true,
        session: { ...base.session, template_id: 3, template_name: 'Pull' },
        template_exercises: ['A', 'B', 'C', 'D'],
        template_next_exercises: ['D', 'C', 'B', 'A'],
      })
      expect(document.querySelector('.prompt__diff')!.textContent)
        .toBe('Neue Reihenfolge: D, C, B, A.')
    })

    it('disappears when the update would change nothing', () => {
      mount({
        just_finished: true,
        session: { ...base.session, template_id: 3, template_name: 'Push' },
        template_exercises: ['Bankdrücken'],
        template_next_exercises: ['Bankdrücken'],
      })
      expect(screen.queryByText(/mit dieser Übungsliste und Reihenfolge aktualisieren/))
        .not.toBeInTheDocument()
    })

    it('is absent on a later visit and on an empty workout', () => {
      mount()
      expect(screen.queryByText(/als Routine speichern/)).not.toBeInTheDocument()
      mount({ just_finished: true, total_sets: 0, exercises: [], tick_states: [] })
      expect(screen.queryByText(/als Routine speichern/)).not.toBeInTheDocument()
    })
  })

  describe('measured pace', () => {
    // Pace per set, not "Pause": the gap between two logged sets includes the
    // set itself, so the old total claimed nearly the whole workout as rest.
    it('reports what it counted, per set', () => {
      mount({ set_pace_seconds: 185 })
      // Pace with the rest in it, said so (D16) -- not "davon 50 Minuten Pause".
      expect(screen.getByText('Ø 3:05 min je Satz (inkl. Pause)')).toBeInTheDocument()
      expect(screen.queryByText(/Minuten Pause/)).not.toBeInTheDocument()
    })

    it('says nothing without timestamps to build it from', () => {
      mount({ set_pace_seconds: null })
      expect(screen.queryByText(/je Satz/)).not.toBeInTheDocument()
    })
  })

  it('keeps a replaced original and its substitute apart in one slot', () => {
    // B3 review: both sit at position 1, and the position was the key.
    const errors = vi.spyOn(console, 'error').mockImplementation(() => {})
    mount({ exercises: [
      exercise({ session_exercise_id: 90 }),
      exercise({ exercise_id: 11, name: 'Schrägbankdrücken', session_exercise_id: 91,
                 set_rows: [{ id: 503, weight: 50, reps: 8, is_record: false }] }),
    ] })
    expect(screen.getAllByText('Bankdrücken').length).toBeGreaterThan(0)
    expect(screen.getAllByText('Schrägbankdrücken').length).toBeGreaterThan(0)
    expect(errors.mock.calls.flat().join(' ')).not.toMatch(/same key/)
    errors.mockRestore()
  })

  it('keeps deleting a workout quiet', () => {
    mount()
    const del = screen.getByRole('button', { name: 'Workout löschen' })
    expect(del).toHaveClass('quiet-acts__btn--danger')
  })

  it('goes on to Start after finishing, and back to Verlauf when opened again (G-045)', () => {
    // The one way on; the header's back arrow is the other, to Verlauf.
    const outs = () => within(document.querySelector('.outs') as HTMLElement)
    const { unmount } = mount({ just_finished: true })
    expect(outs().getAllByRole('link')).toHaveLength(1)
    expect(outs().getByRole('link', { name: 'Zum Start' })).toHaveAttribute('href', '/gym')
    unmount()
    mount()
    expect(outs().getAllByRole('link')).toHaveLength(1)
    expect(outs().getByRole('link', { name: 'Zurück zum Verlauf' }))
      .toHaveAttribute('href', '/gym/verlauf')
    expect(screen.queryByRole('link', { name: 'Verlauf' })).toBeNull()
  })

  it('puts the routine update first among the quiet actions on a later visit', () => {
    mount({
      session: { ...base.session, template_id: 3, template_name: 'Pull' },
      template_exercises: ['Bizepscurls', 'Hammercurls'],
      template_next_exercises: ['Hammercurls', 'Bizepscurls'],
    })
    const quiet = document.querySelector('.quiet-acts')!
    expect(within(quiet as HTMLElement).getAllByRole('button').map((b) => b.textContent))
      .toEqual(['Routine „Pull“ aktualisieren …', 'Körpergewicht & Notiz',
        'Als Deload markieren', 'Workout löschen'])
  })

  it('says whom it was done with, and opens their list as it ended (D14)', async () => {
    const user = userEvent.setup()
    const fetchMock = vi.fn(async (_url: string) => new Response(JSON.stringify({
      id: 5, username: 'jglaser', viewer_leads: true, link_live: false,
      since: '2026-08-09T16:02:00', started_at: '2026-08-09T15:58:00',
      finished_at: '2026-08-09T17:01:00', sets_done: 9, sets_total: 9, rest_left: null,
      rows: [{ id: 1, name: 'Bankdrücken', picture: null, state: 'done',
        sets: [{ weight: 60, reps: 8 }], open: 0 }],
    })))
    vi.stubGlobal('fetch', fetchMock)
    try {
      mount({ partners: [{ id: 5, username: 'jglaser' }] })
      // In the name stack, under the pace: part of what the workout was.
      const head = document.querySelector('.session-top__name') as HTMLElement
      await user.click(within(head).getByRole('button', {
        name: 'Zusammen mit jglaser. Liste von jglaser ansehen',
      }))
      const sheet = screen.getByRole('dialog', { name: 'jglaser' })
      // The day is said: opened from a workout in the past.
      await waitFor(() => expect(sheet)
        .toHaveTextContent(/So 09\.08\.\S* · fertig um 19:01 · 9 von 9 Sätzen/))
      expect(String(fetchMock.mock.calls[0]![0])).toBe('/gym/shared/5/list.json')
      // Closed, it takes its history entry back: none is left for the next test.
      await user.click(within(sheet).getByRole('button', { name: 'Fertig' }))
      expect(sheet).not.toHaveAttribute('open')
    } finally {
      vi.unstubAllGlobals()
    }
  })

  it('names no partner for a workout done alone', () => {
    mount()
    expect(screen.queryByRole('button', { name: /^Zusammen mit/ })).toBeNull()
    expect(document.getElementById('sheet-partner')).toBeNull()
  })

  it.each([false, true])(
    'leaves a deleted workout for Verlauf, and out of the history (keepalive %s)',
    async (keepalive) => {
      // The undo window now also closes when the app goes to the background
      // (G-062), and the page is still there when the lifter comes back: it
      // must not go on showing a workout that no longer exists. Replaced, not
      // pushed: Back would reload a page that is gone (G-141).
      const replace = vi.fn()
      vi.stubGlobal('location', { ...window.location, replace, assign: vi.fn() })
      vi.stubGlobal('fetch', vi.fn(async () => ({
        ok: true, redirected: false, url: '/gym/session/1/delete',
        json: async () => ({ deleted: true }),
      } as unknown as Response)))
      try {
        const user = userEvent.setup()
        mount()
        await user.click(screen.getByRole('button', { name: 'Workout löschen' }))
        await act(async () => { useUndo.getState().commitNow(keepalive) })
        expect(replace).toHaveBeenCalledWith('/gym/verlauf')
      } finally {
        vi.unstubAllGlobals()
      }
    })
})

describe('deleting the workout (G-044)', () => {
  // The offer left pending is test-setup.ts's to drop: a reset of the store
  // here, first, nulled its timer before that clearTimeout could read it.
  afterEach(() => { vi.unstubAllGlobals() })

  it('takes the workout off the page at once, every action with it', async () => {
    // It stayed for the whole undo window, every action live under "Workout
    // gelöscht." -- and a sheet opened in the window left its entry behind
    // (B7 review): now there is nothing left to open.
    const fetch = vi.fn()
    vi.stubGlobal('fetch', fetch)
    const user = userEvent.setup()
    mount()
    await user.click(screen.getByRole('button', { name: 'Workout löschen' }))
    expect(screen.getByRole('heading', { level: 1 })).toHaveTextContent('Push Day')
    expect(screen.getByRole('heading', { level: 1 })).toHaveClass('finished__name--gone')
    expect(screen.getByText('Gelöscht. Gleich geht es weiter zum Verlauf.')).toBeInTheDocument()
    expect(screen.queryByText('Bankdrücken')).not.toBeInTheDocument()
    // The toast's own controls are all that is left.
    expect(screen.getAllByRole('button').filter((b) => b.closest('.undo-toast') === null))
      .toHaveLength(0)
    expect(screen.getByRole('button', { name: 'Rückgängig' })).toBeInTheDocument()
    expect(screen.queryAllByRole('link')).toHaveLength(0)
    expect(document.querySelectorAll('dialog')).toHaveLength(0)
    expect(fetch).not.toHaveBeenCalled()
  })

  it('brings it back whole on Rückgängig, nothing sent', async () => {
    const fetch = vi.fn()
    vi.stubGlobal('fetch', fetch)
    const user = userEvent.setup()
    mount()
    await user.click(screen.getByRole('button', { name: 'Workout löschen' }))
    await user.click(screen.getByRole('button', { name: 'Rückgängig' }))
    expect(screen.getByRole('button', { name: 'Workout löschen' })).toBeInTheDocument()
    expect(screen.getAllByText('Bankdrücken').length).toBeGreaterThan(0)
    expect(screen.getByRole('heading', { level: 1 })).not.toHaveClass('finished__name--gone')
    expect(fetch).not.toHaveBeenCalled()
  })

  it('brings it back with the reason when the delete fails', async () => {
    const replace = vi.fn()
    vi.stubGlobal('location', { ...window.location, replace, assign: vi.fn() })
    vi.stubGlobal('fetch', vi.fn(async () => { throw new TypeError('offline') }))
    const user = userEvent.setup()
    mount()
    await user.click(screen.getByRole('button', { name: 'Workout löschen' }))
    await act(async () => { useUndo.getState().commitNow() })
    expect(await screen.findByRole('alert')).toHaveTextContent('Verbindung fehlgeschlagen')
    // The focus comes back with the page, as after Rückgängig.
    expect(screen.getByRole('button', { name: 'Workout löschen' })).toHaveFocus()
    expect(screen.getAllByText('Bankdrücken').length).toBeGreaterThan(0)
    expect(replace).not.toHaveBeenCalled()
  })

  it('takes the focus with it: onto the name, back onto "Workout löschen" after Rückgängig', async () => {
    // The button the focus was on goes with the page, the toast's with the
    // toast: a keyboard or screen-reader user was left on <body>.
    vi.stubGlobal('fetch', vi.fn())
    const user = userEvent.setup()
    const { rerender } = mount()
    // Opening the debrief moves nothing: no scroll to its foot.
    expect(document.body).toHaveFocus()
    await user.click(screen.getByRole('button', { name: 'Workout löschen' }))
    const name = screen.getByRole('heading', { level: 1 })
    expect(name).toHaveFocus()
    // The strike is only drawn; the line under the name says it.
    expect(name).toHaveAccessibleDescription('Gelöscht. Gleich geht es weiter zum Verlauf.')
    // A render inside the window leaves the focus where the lifter put it.
    const undo = screen.getByRole('button', { name: 'Rückgängig' })
    undo.focus()
    rerender(<FinishedPage payload={{ ...base }} />)
    expect(undo).toHaveFocus()
    await user.click(undo)
    expect(screen.getByRole('button', { name: 'Workout löschen' })).toHaveFocus()
  })
})

describe('the ways back to Verlauf (G-043)', () => {
  const cameFrom = (address: string) =>
    Object.defineProperty(document, 'referrer', { value: address, configurable: true })
  afterEach(() => {
    Reflect.deleteProperty(document, 'referrer')
    vi.unstubAllGlobals()
  })

  it('goes back to Verlauf as it was left, its search and filter with it', () => {
    // A search, a hit opened, the arrow: the search was gone -- and an
    // installed app has no Back button of its own.
    cameFrom(`${window.location.origin}/gym/verlauf?q=bank&rekorde`)
    mount()
    const ways = screen.getAllByRole('link', { name: 'Zurück zum Verlauf' })
    expect(ways).toHaveLength(2)
    for (const way of ways) expect(way).toHaveAttribute('href', '/gym/verlauf?q=bank&rekorde')
  })

  it('goes to a plain Verlauf from anywhere else', () => {
    for (const elsewhere of [`${window.location.origin}/gym/session/5`,
      'https://elsewhere.example/gym/verlauf?q=bank', '']) {
      cameFrom(elsewhere)
      const { unmount } = mount()
      for (const way of screen.getAllByRole('link', { name: 'Zurück zum Verlauf' })) {
        expect(way).toHaveAttribute('href', '/gym/verlauf')
      }
      unmount()
    }
  })

  it('leaves a deleted workout for Verlauf as it was left', async () => {
    cameFrom(`${window.location.origin}/gym/verlauf?q=bank`)
    const replace = vi.fn()
    vi.stubGlobal('location', { ...window.location, replace, assign: vi.fn() })
    vi.stubGlobal('fetch', vi.fn(async () => ({
      ok: true, redirected: false, url: '/gym/session/1/delete',
      json: async () => ({ deleted: true }),
    } as unknown as Response)))
    const user = userEvent.setup()
    mount()
    await user.click(screen.getByRole('button', { name: 'Workout löschen' }))
    await act(async () => { useUndo.getState().commitNow() })
    expect(replace).toHaveBeenCalledWith('/gym/verlauf?q=bank')
  })
})

describe('saving without a reload', () => {
  const fetchPayload = (over: Partial<FinishedPayload>) =>
    vi.fn(async () => ({
      ok: true,
      json: async () => ({ ...base, ...over }),
    } as unknown as Response))

  it('posts the correction and re-renders from the answer, sheet still open', async () => {
    const fresh = exercise({ sets_display: '2 × 65 kg', set_rows: [
      { id: 501, weight: 65, reps: 8, is_record: false },
      { id: 502, weight: 60, reps: 8, is_record: false },
    ] })
    // just_finished true in the ANSWER: the client must overwrite it with its
    // own, because a POST carries no ?just_finished and the flare belongs to
    // the visit.
    vi.stubGlobal('fetch', fetchPayload({ exercises: [fresh], just_finished: false }))

    mount({ just_finished: true })
    await userEvent.click(screen.getByRole('button', { name: /Sätze & Notizen/ }))
    const sheet = screen.getByRole('dialog')
    await userEvent.click(within(sheet).getByRole('button', { name: 'Satz 1 speichern' }))

    const [url, init] = (fetch as ReturnType<typeof vi.fn>).mock.calls[0] as [string, RequestInit]
    expect(url).toBe('/gym/set/501/update')
    expect((init.headers as Record<string, string>)['Accept']).toBe('application/json')
    expect((init.body as FormData).get('weight')).toBe('60')

    // Re-rendered from the answer...
    expect(document.querySelector('.steps__done')).toHaveTextContent('65,0kg×8·60,0kg×8')
    // ...with the sheet still open and the visit's flag preserved.
    expect(screen.getByRole('dialog')).toBeInTheDocument()
    expect(screen.getByText('Dieses Workout als Routine speichern?')).toBeInTheDocument()
    vi.unstubAllGlobals()
  })

  it('keeps a quarter-kilo weight, as the live screen does (G-146)', async () => {
    vi.stubGlobal('fetch', fetchPayload({}))
    mount()
    await userEvent.click(screen.getByRole('button', { name: /Sätze & Notizen/ }))
    const sheet = screen.getByRole('dialog')
    const weight = within(sheet).getByRole('spinbutton', { name: /Satz 1, Gewicht in kg/ })
    await userEvent.clear(weight)
    await userEvent.type(weight, '11.25')
    // A step of 0.5 made the browser refuse it before the save ran.
    expect((weight as HTMLInputElement).checkValidity()).toBe(true)
    await userEvent.click(within(sheet).getByRole('button', { name: 'Satz 1 speichern' }))

    const [, init] = (fetch as ReturnType<typeof vi.fn>).mock.calls[0] as [string, RequestInit]
    expect((init.body as FormData).get('weight')).toBe('11.25')
    vi.unstubAllGlobals()
  })

  it('takes a quarter-kilo weight in the new-set form too (G-146)', async () => {
    vi.stubGlobal('fetch', fetchPayload({}))
    mount()
    await userEvent.click(screen.getByRole('button', { name: /Sätze & Notizen/ }))
    const added = within(screen.getByRole('dialog'))
      .getAllByRole('spinbutton', { name: /neuer Satz, Gewicht in kg/ })[0]!
    await userEvent.clear(added)
    await userEvent.type(added, '11.25')
    expect((added as HTMLInputElement).checkValidity()).toBe(true)
    vi.unstubAllGlobals()
  })

  it('re-renders as a deload when the deload toggle answers', async () => {
    vi.stubGlobal('fetch', fetchPayload({
      session: { ...base.session, is_deload: true, deload_pct: 60 },
      is_deload: true,
    }))
    mount()
    await userEvent.click(screen.getByRole('button', { name: 'Als Deload markieren' }))
    expect(await screen.findByText('Deload: bewusst leichter, darum ohne Vergleich.'))
      .toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Deload-Markierung entfernen' }))
      .toBeInTheDocument()
    vi.unstubAllGlobals()
  })

  it('says so when the save fails, and keeps the page', async () => {
    vi.stubGlobal('fetch', vi.fn(async () => { throw new TypeError('offline') }))
    mount()
    await userEvent.click(screen.getByRole('button', { name: /Körpergewicht/ }))
    const sheet = screen.getByRole('dialog')
    await userEvent.click(within(sheet).getByRole('button', { name: 'Speichern' }))
    expect(await within(sheet).findByRole('alert'))
      .toHaveTextContent('Verbindung fehlgeschlagen')
    // Nothing navigated, nothing blanked.
    expect(screen.getByRole('heading', { level: 1 })).toHaveTextContent('Push Day')
    vi.unstubAllGlobals()
  })

  it('deletes a set after the undo window, and the debrief follows', async () => {
    // A set logged by mistake used to be permanent once the workout finished.
    useUndo.setState({ pending: null, timer: null })
    const fetchMock = fetchPayload({
      exercises: [exercise({ sets_display: '1 × 60 kg',
        set_rows: [{ id: 502, weight: 60, reps: 8, is_record: false }] })],
      total_sets: 1,
    })
    vi.stubGlobal('fetch', fetchMock)
    mount()
    await userEvent.click(screen.getByRole('button', { name: /Sätze & Notizen/ }))
    const sheet = screen.getByRole('dialog')
    await userEvent.click(within(sheet).getByRole('button', { name: 'Bankdrücken, Satz 1 löschen' }))

    // Hidden at once, nothing sent yet.
    expect(within(sheet).getAllByRole('button', { name: /Satz \d speichern/ })).toHaveLength(1)
    expect(fetchMock).not.toHaveBeenCalled()

    useUndo.getState().commitNow()
    const [url] = fetchMock.mock.calls[0] as unknown as [string]
    expect(url).toBe('/gym/set/501/delete')
    await waitFor(() => expect(document.querySelectorAll('.steps__done .steps__set'))
      .toHaveLength(1))
    vi.unstubAllGlobals()
  })

  it('adds a set -- also to an exercise with nothing logged', async () => {
    const fetchMock = fetchPayload({})
    vi.stubGlobal('fetch', fetchMock)
    mount({ unlogged: [{ session_exercise_id: 91, name: 'Butterfly', best: null }] })
    await userEvent.click(screen.getByRole('button', { name: /Sätze & Notizen/ }))
    const sheet = screen.getByRole('dialog')

    // Seeded from the last set of the exercise it belongs to.
    expect(within(sheet).getByLabelText('Bankdrücken, neuer Satz, Gewicht in kg')).toHaveValue(60)
    expect(within(sheet).getByText('Butterfly')).toBeInTheDocument()

    await userEvent.type(within(sheet).getByLabelText('Butterfly, neuer Satz, Gewicht in kg'), '30')
    await userEvent.type(within(sheet).getByLabelText('Butterfly, neuer Satz, Wiederholungen'), '12')
    await userEvent.click(within(sheet).getByRole('button', { name: 'Butterfly, Satz nachtragen' }))
    const [url, init] = fetchMock.mock.calls[0] as unknown as [string, RequestInit]
    expect(url).toBe('/gym/session-exercise/91/sets/add')
    expect((init.body as FormData).get('weight')).toBe('30')
    expect((init.body as FormData).get('reps')).toBe('12')
    // The debrief writes without the live screen's header: corrections to a
    // finished workout are allowed, a stale live screen's writes are not.
    expect((init.headers as Record<string, string>)['X-Gym-Surface']).toBeUndefined()
    vi.unstubAllGlobals()
  })

  describe('"Sicher?" past twice the best (Q5, B7 review)', () => {
    // A fat-fingered 600 kg counted the moment it landed, records and all.
    const best = { weight: 60, reps: 10 }
    const openSheet = async () => {
      await userEvent.click(screen.getByRole('button', { name: /Sätze & Notizen/ }))
      return within(screen.getByRole('dialog'))
    }
    const retype = async (field: HTMLElement, value: string) => {
      await userEvent.clear(field)
      await userEvent.type(field, value)
    }
    afterEach(() => { vi.unstubAllGlobals() })

    it('asks before a correction saves, and saves on "Ja, speichern"', async () => {
      const fetchMock = fetchPayload({})
      vi.stubGlobal('fetch', fetchMock)
      mount({ exercises: [exercise({ best })] })
      const sheet = await openSheet()
      await retype(sheet.getByLabelText('Bankdrücken, Satz 1, Gewicht in kg'), '600')
      await userEvent.click(sheet.getByRole('button', { name: 'Satz 1 speichern' }))
      expect(sheet.getByText('Sicher? Bisher höchstens 60,0 kg.')).toBeInTheDocument()
      expect(fetchMock).not.toHaveBeenCalled()

      await userEvent.click(sheet.getByRole('button', { name: 'Ja, speichern' }))
      const [url, init] = fetchMock.mock.calls[0] as unknown as [string, RequestInit]
      expect(url).toBe('/gym/set/501/update')
      expect((init.body as FormData).get('weight')).toBe('600')
    })

    it('takes the question away as the numbers are typed again', async () => {
      const fetchMock = fetchPayload({})
      vi.stubGlobal('fetch', fetchMock)
      mount({ exercises: [exercise({ best })] })
      const sheet = await openSheet()
      const weight = sheet.getByLabelText('Bankdrücken, Satz 1, Gewicht in kg')
      await retype(weight, '600')
      await userEvent.click(sheet.getByRole('button', { name: 'Satz 1 speichern' }))
      await retype(weight, '65')
      expect(sheet.queryByText(/Sicher\?/)).toBeNull()
      expect(sheet.queryByRole('button', { name: 'Ja, speichern' })).toBeNull()
      await userEvent.click(sheet.getByRole('button', { name: 'Satz 1 speichern' }))
      expect(fetchMock).toHaveBeenCalledOnce()
    })

    it('asks nothing about numbers the row already held', async () => {
      // 60 x 8 against a best of 20 x 3: logged so, and said yes to then.
      const fetchMock = fetchPayload({})
      vi.stubGlobal('fetch', fetchMock)
      mount({ exercises: [exercise({ best: { weight: 20, reps: 3 } })] })
      const sheet = await openSheet()
      await userEvent.click(sheet.getByRole('button', { name: 'Satz 1 speichern' }))
      expect(sheet.queryByText(/Sicher\?/)).toBeNull()
      expect(fetchMock).toHaveBeenCalledOnce()
    })

    it('saves past twice the best at once without a history', async () => {
      const fetchMock = fetchPayload({})
      vi.stubGlobal('fetch', fetchMock)
      mount()
      const sheet = await openSheet()
      await retype(sheet.getByLabelText('Bankdrücken, Satz 1, Gewicht in kg'), '600')
      await userEvent.click(sheet.getByRole('button', { name: 'Satz 1 speichern' }))
      expect(sheet.queryByText(/Sicher\?/)).toBeNull()
      expect(fetchMock).toHaveBeenCalledOnce()
    })

    it("asks before a logged exercise's \"Nachtragen\" too", async () => {
      const fetchMock = fetchPayload({})
      vi.stubGlobal('fetch', fetchMock)
      mount({ exercises: [exercise({ best })] })
      const sheet = await openSheet()
      await retype(sheet.getByLabelText('Bankdrücken, neuer Satz, Gewicht in kg'), '130')
      await userEvent.click(sheet.getByRole('button', { name: 'Bankdrücken, Satz nachtragen' }))
      expect(sheet.getByText('Sicher? Bisher höchstens 60,0 kg.')).toBeInTheDocument()
      expect(fetchMock).not.toHaveBeenCalled()
    })

    it('asks before "Nachtragen" adds reps past twice the best, and adds on "Ja, nachtragen"', async () => {
      const fetchMock = fetchPayload({})
      vi.stubGlobal('fetch', fetchMock)
      mount({ unlogged: [{ session_exercise_id: 91, name: 'Butterfly', best: { weight: 30, reps: 12 } }] })
      const sheet = await openSheet()
      await userEvent.type(sheet.getByLabelText('Butterfly, neuer Satz, Gewicht in kg'), '30')
      await userEvent.type(sheet.getByLabelText('Butterfly, neuer Satz, Wiederholungen'), '25')
      await userEvent.click(sheet.getByRole('button', { name: 'Butterfly, Satz nachtragen' }))
      expect(sheet.getByText('Sicher? Bisher höchstens 12 Wdh.')).toBeInTheDocument()
      expect(fetchMock).not.toHaveBeenCalled()

      await userEvent.click(sheet.getByRole('button', { name: 'Ja, nachtragen' }))
      const [url, init] = fetchMock.mock.calls[0] as unknown as [string, RequestInit]
      expect(url).toBe('/gym/session-exercise/91/sets/add')
      expect((init.body as FormData).get('reps')).toBe('25')
    })
  })

  it('will not add an empty set', async () => {
    const fetchMock = fetchPayload({})
    vi.stubGlobal('fetch', fetchMock)
    mount({ unlogged: [{ session_exercise_id: 91, name: 'Butterfly', best: null }] })
    await userEvent.click(screen.getByRole('button', { name: /Sätze & Notizen/ }))
    const sheet = screen.getByRole('dialog')
    await userEvent.click(within(sheet).getByRole('button', { name: 'Butterfly, Satz nachtragen' }))
    expect(fetchMock).not.toHaveBeenCalled()
    vi.unstubAllGlobals()
  })
})
