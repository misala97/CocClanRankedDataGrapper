import { act, render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { kg1 } from '../../format'
import { LivePanel } from './LivePanel'
import { Rail } from './Rail'
import { SessionTotals } from './SessionTotals'
import { useSheets } from '../stores'
import { payload } from '../types.test-d'
import type { SessionDetailPayload } from '../types'

beforeEach(() => {
  useSheets.setState(useSheets.getInitialState(), true)
})

const handlers = () => ({
  onConfirm: vi.fn(), onToggleSet: vi.fn(), onRestOver: vi.fn(),
})

const live = payload.visible_exercises.find((se) => se.id === payload.live_id)!

describe('LivePanel', () => {
  it('names the live exercise and opens its own sheet', async () => {
    const user = userEvent.setup()
    render(<LivePanel payload={payload} {...handlers()} />)
    expect(screen.getByRole('heading', { level: 2, name: live.name })).toBeInTheDocument()

    await user.click(screen.getByLabelText(`${live.name} — Optionen`))
    expect(useSheets.getState().openId).toBe(`sheet-ex-${live.id}`)
  })

  it('prefills the steppers from the pending set', () => {
    const next = live.sets.find((s) => !s.completed)!
    render(<LivePanel payload={payload} {...handlers()} />)
    expect(screen.getByLabelText('Gewicht eingeben'))
      .toHaveTextContent(kg1(next.weight!))
    expect(screen.getByLabelText('Wiederholungen eingeben'))
      .toHaveTextContent(String(next.reps))
  })

  it('confirms with whatever the steppers currently hold', async () => {
    const user = userEvent.setup()
    const h = handlers()
    render(<LivePanel payload={payload} {...h} />)

    await user.click(screen.getByLabelText('Gewicht erhöhen'))
    await user.click(screen.getByText('Satz geschafft'))
    const next = live.sets.find((s) => !s.completed)!
    expect(h.onConfirm).toHaveBeenCalledWith(
      next.weight! + payload.live_increment, next.reps, next.id)
  })

  it('binds the steppers to an open chip instead of logging it', async () => {
    // Tapping an open chip logged it on the spot with its PLANNED numbers,
    // whatever the steppers said.
    const user = userEvent.setup()
    const h = handlers()
    render(<LivePanel payload={payload} {...h} />)
    const open = live.sets.filter((s) => !s.completed)
    const later = open[open.length - 1]!

    await user.click(screen.getByLabelText(new RegExp(`^Satz ${live.sets.indexOf(later) + 1}, geplant`)))
    expect(h.onToggleSet).not.toHaveBeenCalled()
    expect(screen.getByLabelText('Gewicht eingeben')).toHaveTextContent(kg1(later.weight!))
    expect(screen.getByLabelText('Wiederholungen eingeben')).toHaveTextContent(String(later.reps))

    await user.click(screen.getByText('Satz geschafft'))
    expect(h.onConfirm).toHaveBeenCalledWith(later.weight, later.reps, later.id)
  })

  it('hands a tap on a done chip to the island, which offers the undo', async () => {
    const user = userEvent.setup()
    const h = handlers()
    render(<LivePanel payload={payload} {...h} />)
    const done = live.sets.find((s) => s.completed)!
    // A record is a done set too, and the regenerated fixture may hold one.
    await user.click(screen.getByLabelText(
      new RegExp(`^Satz ${live.sets.indexOf(done) + 1} (erledigt|— Rekord)`)))
    expect(h.onToggleSet).toHaveBeenCalledWith(done.id, false)
  })

  it('holds the confirm button while a set write is in flight', () => {
    // It keyed on the next set's id -- null once the last set was optimistically
    // done, so a double tap on an exercise's last set appended a phantom one.
    render(<LivePanel payload={payload} {...handlers()} confirmBusy />)
    expect(screen.getByText('Satz geschafft').closest('button')).toBeDisabled()
  })

  it('says everything is skipped rather than showing a skipped exercise as live', () => {
    const skipped: SessionDetailPayload = {
      ...payload,
      live_id: null,
      visible_exercises: payload.visible_exercises.map((se) => ({ ...se, skipped: true })),
    }
    render(<LivePanel payload={skipped} {...handlers()} />)
    expect(screen.getByRole('heading', { name: 'Alles übersprungen' })).toBeInTheDocument()
    expect(screen.queryByText('Noch keine Übung')).toBeNull()
  })

  it('snaps the steppers to the next pending set even when its numbers are the same', async () => {
    // The reset used to key on the seed VALUES. Two equal seeds in a row then
    // read as "nothing changed", so a bump made for one set silently carried
    // into the next -- but only then; a different seed snapped back. The owner
    // ruled no carry-forward (it overrides drop sets and ramp-ups), so the
    // coincidence is the bug: identity of the set decides, not its numbers.
    const user = userEvent.setup()
    const twoEqual: SessionDetailPayload = {
      ...payload,
      visible_exercises: payload.visible_exercises.map((se) =>
        se.id === live.id
          ? { ...se, sets: [
            { id: 900, weight: 50, reps: 10, completed: false, base_weight: null },
            { id: 901, weight: 50, reps: 10, completed: false, base_weight: null },
          ] }
          : se),
    }
    const { rerender } = render(<LivePanel payload={twoEqual} {...handlers()} />)
    await user.click(screen.getByLabelText('Gewicht erhöhen'))
    expect(screen.getByLabelText('Gewicht eingeben'))
      .toHaveTextContent(kg1(50 + payload.live_increment))

    const firstDone: SessionDetailPayload = {
      ...twoEqual,
      visible_exercises: twoEqual.visible_exercises.map((se) =>
        se.id === live.id
          ? { ...se, sets: se.sets.map((s) => (s.id === 900
            ? { ...s, completed: true, weight: 50 + payload.live_increment } : s)) }
          : se),
    }
    rerender(<LivePanel payload={firstDone} {...handlers()} />)
    expect(screen.getByLabelText('Gewicht eingeben')).toHaveTextContent(kg1(50))
  })

  it('snaps the steppers when another exercise goes live with the same numbers', async () => {
    const user = userEvent.setup()
    const other = payload.visible_exercises.find((se) => se.id !== live.id)!
    const next = live.sets.find((s) => !s.completed)!
    const { rerender } = render(<LivePanel payload={payload} {...handlers()} />)
    await user.click(screen.getByLabelText('Wiederholungen erhöhen'))
    expect(screen.getByLabelText('Wiederholungen eingeben'))
      .toHaveTextContent(String(next.reps! + 1))

    const switched: SessionDetailPayload = {
      ...payload,
      live_id: other.id,
      visible_exercises: payload.visible_exercises.map((se) =>
        se.id === other.id
          ? { ...se, skipped: false, sets: [
            { id: 950, weight: next.weight, reps: next.reps, completed: false, base_weight: null },
          ] }
          : se),
    }
    rerender(<LivePanel payload={switched} {...handlers()} />)
    expect(screen.getByLabelText('Wiederholungen eingeben'))
      .toHaveTextContent(String(next.reps))
  })

  it('keeps a bump while the same set is still the one up', async () => {
    // A refetch that changes nothing about the pending set must not throw the
    // lifter's dialled-in number away.
    const user = userEvent.setup()
    const { rerender } = render(<LivePanel payload={payload} {...handlers()} />)
    await user.click(screen.getByLabelText('Gewicht erhöhen'))
    const next = live.sets.find((s) => !s.completed)!

    rerender(<LivePanel payload={{ ...payload, sets_done: payload.sets_done }} {...handlers()} />)
    expect(screen.getByLabelText('Gewicht eingeben'))
      .toHaveTextContent(kg1(next.weight! + payload.live_increment))
  })

  it('says where the plan came from', () => {
    // Its own seed rather than the fixture's: the fixture is regenerated from
    // a real history, and the pick it finds changes with that history.
    const same: SessionDetailPayload = {
      ...payload,
      seed_sources: {
        ...payload.seed_sources,
        [String(live.id)]: { date: '2026-08-25T09:47:25', position: live.position, basis: 'slot' },
      },
    }
    render(<LivePanel payload={same} {...handlers()} />)
    const line = screen.getByText('Vorgabe').closest('p')!
    expect(line).toHaveTextContent('Vorgabe vom 25.08., gleiche Position im Workout.')
  })

  it('says so when the plan comes from an earlier, fresher slot', () => {
    const late: SessionDetailPayload = {
      ...payload,
      seed_sources: {
        ...payload.seed_sources,
        [String(live.id)]: { date: '2026-08-30T09:57:42', position: 1, basis: 'earlier_slot' },
      },
      visible_exercises: payload.visible_exercises.map((se) =>
        se.id === live.id ? { ...se, position: 4 } : se),
    }
    render(<LivePanel payload={late} {...handlers()} />)
    expect(screen.getByText('Vorgabe').closest('p')).toHaveTextContent(
      'Vorgabe vom 30.08., damals an Position 1 — so spät im Workout gibt es noch nichts, daher dein bestes Ergebnis von früher.')
  })

  it('says so when the plan comes from a later slot, and after a layoff', () => {
    const later: SessionDetailPayload = {
      ...payload,
      seed_sources: {
        ...payload.seed_sources,
        [String(live.id)]: { date: '2026-08-30T09:57:42', position: 5, basis: 'slot' },
      },
    }
    const { unmount } = render(<LivePanel payload={later} {...handlers()} />)
    expect(screen.getByText('Vorgabe').closest('p')).toHaveTextContent(
      'Vorgabe vom 30.08., damals später im Workout (Position 5).')
    unmount()

    const layoff: SessionDetailPayload = {
      ...payload,
      seed_sources: {
        ...payload.seed_sources,
        [String(live.id)]: { date: '2026-06-14T09:00:00', position: 2, basis: 'layoff' },
      },
    }
    render(<LivePanel payload={layoff} {...handlers()} />)
    expect(screen.getByText('Vorgabe').closest('p')).toHaveTextContent(
      'Vorgabe vom 14.06. — schon länger her, daher dein letztes Workout statt des besten.')
  })

  it('says nothing about a source when there is no history', () => {
    const none: SessionDetailPayload = {
      ...payload,
      seed_sources: { ...payload.seed_sources, [String(live.id)]: null },
    }
    render(<LivePanel payload={none} {...handlers()} />)
    expect(screen.queryByText('Vorgabe')).not.toBeInTheDocument()
  })

  it('falls back to the last set done when nothing is pending', () => {
    // Appending after everything is logged starts from the set you just did,
    // not the session's opening suggestion: the reason you are adding one is
    // that the last one went well enough to want another.
    const allDone: SessionDetailPayload = {
      ...payload,
      visible_exercises: payload.visible_exercises.map((se) =>
        se.id === live.id
          ? { ...se, sets: se.sets.map((s) => ({ ...s, completed: true })) }
          : se),
    }
    render(<LivePanel payload={allDone} {...handlers()} />)
    const last = live.sets[live.sets.length - 1]!
    expect(screen.getByLabelText('Gewicht eingeben'))
      .toHaveTextContent(kg1(last.weight!))
    expect(screen.getByText(/Alle Sätze erledigt/)).toBeInTheDocument()
  })

  it('gives an empty exercise the same steppers and the same button', () => {
    // An exercise added mid-workout arrives with no sets and is then picked as
    // live and never completes, blocking everything after it. The old panel
    // rendered "Alle Sätze erledigt" over an empty chip row and no button --
    // the exact opposite of the truth.
    const empty: SessionDetailPayload = {
      ...payload,
      visible_exercises: payload.visible_exercises.map((se) =>
        se.id === live.id ? { ...se, sets: [] } : se),
    }
    render(<LivePanel payload={empty} {...handlers()} />)
    expect(screen.getByText('Satz geschafft')).toBeInTheDocument()
    expect(screen.getByLabelText('Gewicht eingeben')).toBeInTheDocument()
    expect(screen.getByText(/Noch keine Sätze/)).toBeInTheDocument()
  })

  it('offers the first exercise when the workout has none', async () => {
    const user = userEvent.setup()
    const none: SessionDetailPayload = {
      ...payload, visible_exercises: [], live_id: null, live_index: 0,
    }
    render(<LivePanel payload={none} {...handlers()} />)
    expect(screen.getByRole('heading', { name: 'Noch keine Übung' })).toBeInTheDocument()

    await user.click(screen.getByText('Übung hinzufügen'))
    expect(useSheets.getState().openId).toBe('sheet-add-exercise')
  })

  it('puts advice above the workspace, not under the button', () => {
    const advised: SessionDetailPayload = {
      ...payload,
      stagnation_counts: { [String(live.id)]: 4 },
      ready_for_more: { sets: 3, weight: 35, is_latest: true, next_weight: 37.5 },
    }
    const { container } = render(<LivePanel payload={advised} {...handlers()} />)
    const stall = container.querySelector('.live__stall')!
    const button = container.querySelector('#set-confirm')!
    expect(stall.compareDocumentPosition(button))
      .toBe(Node.DOCUMENT_POSITION_FOLLOWING)
    expect(screen.getByText(/4 Workouts ohne neuen e1RM-PR/)).toBeInTheDocument()

    // Read the whole paragraph: the label is its own element, so a text query
    // spanning both would never match.
    const ready = container.querySelector('.live__ready')!
    expect(ready.textContent).toContain('Bereit')
    expect(ready.textContent).toContain('Letztes Mal 3 Sätze auf 35,0 kg')
    expect(ready.textContent).toContain(`mit ${payload.min_full_reps}+ Wdh.`)
    // Names the step, not only the evidence for it.
    expect(ready.textContent).toContain('Zeit für 37,5 kg')
    // Says "je Seite" exactly when the lift is logged per side.
    expect(ready.textContent!.includes('je Seite')).toBe(live.is_unilateral)
  })

  it('states the prescription in the stall line, and only states it', () => {
    // Owner decision: a stall means the current weight is already at the
    // edge, so the number is said, never seeded -- the steppers stay on the
    // proven weight. Same copy as the debrief's Nächstes-Mal advice.
    const advised: SessionDetailPayload = {
      ...payload,
      stagnation_counts: { [String(live.id)]: 4 },
      stall_next_weight: { [String(live.id)]: 68 },
    }
    render(<LivePanel payload={advised} {...handlers()} />)
    expect(screen.getByText(/auf 68,0 kg gehen, notfalls 2 Wdh\. weniger/))
      .toBeInTheDocument()
    // The steppers still pre-fill from history, not from the prescription --
    // the stepper renders its value as text, kg1-formatted.
    const next = live.sets.find((s) => !s.completed)!
    expect(screen.getByLabelText('Gewicht eingeben'))
      .toHaveTextContent(kg1(next.weight!))
  })

  it('falls back to the generic nudge when the stack is topped out', () => {
    // stall_next_weight omits an exercise whose known stack has no stop above
    // the plateau -- repeating the stuck number is not advice.
    const advised: SessionDetailPayload = {
      ...payload,
      stagnation_counts: { [String(live.id)]: 4 },
      stall_next_weight: {},
    }
    render(<LivePanel payload={advised} {...handlers()} />)
    expect(screen.getByText(/mehr Gewicht oder Wdh\. versuchen/)).toBeInTheDocument()
  })

  it('keeps the button name stable while a rest runs', () => {
    // A name that rewrote itself every second would be worse than no
    // countdown, so the clock is aria-hidden and the announcement goes to the
    // live region instead.
    const resting: SessionDetailPayload = {
      ...payload,
      resting: true,
      rest_total_seconds: 90,
      session: {
        ...payload.session,
        rest_ends_at: new Date(Date.now() + 90_000).toISOString().replace('Z', ''),
      },
    }
    const { container } = render(<LivePanel payload={resting} {...handlers()} />)
    expect(container.querySelector('#set-confirm')).toHaveClass('is-resting')
    expect(screen.getByText('Satz geschafft')).toBeInTheDocument()
    expect(container.querySelector('.go__clock'))
      .toHaveAttribute('aria-hidden', 'true')
  })

  it('rings the confirm button when the rest hits zero', () => {
    // The cue to start the next set arrives while the phone is face-down on a
    // bench, so the button announces itself once. .go.is-ready is the last
    // frame of the charge that ran underneath it -- the CSS was written for
    // the Jinja screen and no React code applied it, so the rest ending was
    // visually silent.
    vi.useFakeTimers()
    const nearlyOver: SessionDetailPayload = {
      ...payload,
      resting: true,
      rest_total_seconds: 90,
      session: {
        ...payload.session,
        rest_ends_at: new Date(Date.now() + 900).toISOString().replace('Z', ''),
      },
    }
    const { container } = render(<LivePanel payload={nearlyOver} {...handlers()} />)
    expect(container.querySelector('#set-confirm')).not.toHaveClass('is-ready')

    act(() => { vi.advanceTimersByTime(1200) })
    expect(container.querySelector('#set-confirm')).toHaveClass('is-ready')

    // One ring, not a permanent state: the class comes off with the animation.
    act(() => { vi.advanceTimersByTime(400) })
    expect(container.querySelector('#set-confirm')).not.toHaveClass('is-ready')
    vi.useRealTimers()
  })

  it('carries the rest countdown into the tab title, and restores it', () => {
    // Leaving mid-rest is exactly when this screen is not on screen to show
    // the countdown; the tab title covers the desk.
    document.title = 'Gym Tracker'
    const resting: SessionDetailPayload = {
      ...payload,
      resting: true,
      rest_total_seconds: 90,
      session: {
        ...payload.session,
        rest_ends_at: new Date(Date.now() + 90_000).toISOString().replace('Z', ''),
      },
    }
    const { unmount } = render(<LivePanel payload={resting} {...handlers()} />)
    expect(document.title).toMatch(/^\d:\d{2} Pause · Gym Tracker$/)
    unmount()
    expect(document.title).toBe('Gym Tracker')
  })
})

describe('Rail', () => {
  it('states position and the skipped count in words, since the rail cannot', () => {
    render(<Rail exercises={payload.visible_exercises} liveId={payload.live_id}
      liveIndex={payload.live_index} setsOpen={payload.sets_open}
      setsTotal={payload.sets_total} />)
    const skipped = payload.visible_exercises.filter((se) => se.skipped).length
    expect(screen.getByText(
      `Übung ${payload.live_index} von ${payload.visible_exercises.length}, ${skipped} übersprungen`,
    )).toBeInTheDocument()
  })

  it('names no position when everything is skipped', () => {
    const skipped = payload.visible_exercises.map((se) => ({ ...se, skipped: true }))
    render(<Rail exercises={skipped} liveId={null} liveIndex={0}
      setsOpen={0} setsTotal={0} />)
    expect(screen.getByText(`${skipped.length} von ${skipped.length} übersprungen`))
      .toBeInTheDocument()
    expect(screen.queryByText(/Übung 0 von/)).toBeNull()
  })

  it('hides the segments from assistive tech', () => {
    const { container } = render(
      <Rail exercises={payload.visible_exercises} liveId={payload.live_id} liveIndex={1}
        setsOpen={payload.sets_open} setsTotal={payload.sets_total} />)
    expect(container.querySelector('.rail')).toHaveAttribute('aria-hidden', 'true')
  })

  it('distinguishes none-yet from none-left, which are not the same state', () => {
    // sets_open counts only sets that EXIST, so treating zero as "none left"
    // is how a workout with nothing in it announced itself as finished.
    const { rerender } = render(<Rail exercises={payload.visible_exercises}
      liveId={payload.live_id} liveIndex={1} setsOpen={0} setsTotal={0} />)
    expect(screen.getByText('Noch nichts geplant')).toBeInTheDocument()

    rerender(<Rail exercises={payload.visible_exercises} liveId={payload.live_id}
      liveIndex={1} setsOpen={0} setsTotal={3} />)
    expect(screen.getByText('Alles erledigt')).toBeInTheDocument()

    rerender(<Rail exercises={payload.visible_exercises} liveId={payload.live_id}
      liveIndex={1} setsOpen={1} setsTotal={3} />)
    expect(screen.getByText('Noch 1 Satz')).toBeInTheDocument()

    rerender(<Rail exercises={payload.visible_exercises} liveId={payload.live_id}
      liveIndex={1} setsOpen={2} setsTotal={3} />)
    expect(screen.getByText('Noch 2 Sätze')).toBeInTheDocument()
  })

  it('says so when there is nothing to show', () => {
    render(<Rail exercises={[]} liveId={null} liveIndex={0} setsOpen={0} setsTotal={0} />)
    expect(screen.getByText('Noch keine Übungen')).toBeInTheDocument()
  })
})

describe('SessionTotals', () => {
  it('groups the volume German-style and pluralises the set count', () => {
    render(<SessionTotals volume={1920} setsDone={1}
      startedAt={payload.session.started_at} />)
    expect(screen.getByText('1.920')).toBeInTheDocument()
    expect(screen.getByText(/Satz ·/)).toBeInTheDocument()
  })

  it('pluralises past one', () => {
    render(<SessionTotals volume={0} setsDone={2}
      startedAt={payload.session.started_at} />)
    expect(screen.getByText(/Sätze ·/)).toBeInTheDocument()
  })
})

/** The live exercise met for the first time: planned blank (V2), with the
 *  lifter's other variants of the movement as a reference. */
const firstTime = (refs: SessionDetailPayload['first_time'][string] = [
  { label: 'Kurzhantel', weight: 26, reps: 10, per_side: true },
  { label: 'Maschine, Scheiben', weight: 27.5, reps: 10, per_side: false },
]): SessionDetailPayload => ({
  ...payload,
  visible_exercises: payload.visible_exercises.map((se) => (se.id !== live.id ? se : {
    ...se, is_unilateral: false,
    sets: se.sets.map((s) => ({ ...s, completed: false, weight: null, reps: null })),
  })),
  suggestions: { ...payload.suggestions, [String(live.id)]: null },
  seed_sources: { ...payload.seed_sources, [String(live.id)]: null },
  stagnation_counts: {}, stall_next_weight: {}, ready_for_more: null,
  record_set_ids: [], record_details: {},
  first_time: { [String(live.id)]: refs },
  live_floor: 20,
})

describe('LivePanel, first time', () => {
  it('says so, names the other variants, and plans blank sets', () => {
    render(<LivePanel payload={firstTime()} {...handlers()} />)
    const note = screen.getByText('Erstes Mal').closest('p')!
    expect(note).toHaveTextContent('Tipp ein, womit du anfängst — die nächsten Sätze übernehmen es.')
    expect(note).toHaveTextContent(
      'Deine anderen Varianten, zuletzt: Kurzhantel 26,0 kg je Seite × 10 · Maschine, Scheiben 27,5 kg × 10')
    expect(screen.getByRole('button', { name: /^Satz 1, noch ohne Zahlen/ })).toHaveTextContent('Satz 1')
    expect(screen.getByLabelText('Gewicht eingeben')).toHaveTextContent(/^$/)
    expect(screen.getByLabelText('Wiederholungen eingeben')).toHaveTextContent(/^$/)
  })

  it('leaves the references out when there are none', () => {
    render(<LivePanel payload={firstTime([])} {...handlers()} />)
    expect(screen.getByText('Erstes Mal')).toBeInTheDocument()
    expect(screen.queryByText(/Deine anderen Varianten/)).toBeNull()
  })

  it('asks for the weight, then the reps, then logs the set', async () => {
    const user = userEvent.setup()
    const h = handlers()
    const data = firstTime()
    const first = data.visible_exercises.find((se) => se.id === live.id)!.sets[0]!
    render(<LivePanel payload={data} {...h} />)

    await user.click(screen.getByRole('button', { name: 'Gewicht eintippen' }))
    const kg = screen.getByRole('textbox', { name: 'Gewicht eingeben' })
    expect(kg).toHaveFocus()
    expect(kg).toHaveAttribute('enterkeyhint', 'next')
    // The label moves on while the number is still being typed.
    await user.type(kg, '40')
    expect(screen.getByRole('button', { name: 'Wdh. eintippen' })).toBeInTheDocument()

    // "Weiter" on the keypad walks straight into the reps.
    await user.keyboard('{Enter}')
    const reps = screen.getByRole('textbox', { name: 'Wiederholungen eingeben' })
    expect(reps).toHaveFocus()
    await user.type(reps, '10{Enter}')

    await user.click(screen.getByText('Satz geschafft'))
    expect(h.onConfirm).toHaveBeenCalledWith(40, 10, first.id)
  })

  it('moves on from a typed weight when the button is tapped instead of Weiter', async () => {
    const user = userEvent.setup()
    const h = handlers()
    render(<LivePanel payload={firstTime()} {...h} />)

    await user.click(screen.getByRole('button', { name: 'Gewicht eintippen' }))
    await user.type(screen.getByRole('textbox', { name: 'Gewicht eingeben' }), '40')
    await user.click(screen.getByRole('button', { name: 'Wdh. eintippen' }))

    expect(screen.getByLabelText('Gewicht eingeben')).toHaveTextContent('40,0')
    expect(screen.getByRole('textbox', { name: 'Wiederholungen eingeben' })).toHaveFocus()
    expect(h.onConfirm).not.toHaveBeenCalled()
  })

  it('steps a blank weight up to the empty bar', async () => {
    const user = userEvent.setup()
    render(<LivePanel payload={firstTime()} {...handlers()} />)

    await user.click(screen.getByLabelText('Gewicht erhöhen'))
    expect(screen.getByLabelText('Gewicht eingeben')).toHaveTextContent('20,0')
    expect(screen.getByRole('button', { name: 'Wdh. eintippen' })).toBeInTheDocument()
  })

  it('takes the next set from what the server filled in, no blank flash', () => {
    // After set 1 the server (and the optimistic write before it) fills the
    // blanks with set 1's numbers: the steppers bind to them as a plan.
    const data = firstTime()
    const filled: SessionDetailPayload = {
      ...data,
      first_time: {},
      visible_exercises: data.visible_exercises.map((se) => (se.id !== live.id ? se : {
        ...se,
        sets: se.sets.map((s, i) => ({ ...s, weight: 40, reps: 10, completed: i === 0 })),
      })),
    }
    render(<LivePanel payload={filled} {...handlers()} />)
    expect(screen.queryByText('Erstes Mal')).toBeNull()
    expect(screen.getByLabelText('Gewicht eingeben')).toHaveTextContent('40,0')
    expect(screen.getByLabelText('Wiederholungen eingeben')).toHaveTextContent('10')
    expect(screen.getByText('Satz geschafft')).toBeInTheDocument()
  })
})
