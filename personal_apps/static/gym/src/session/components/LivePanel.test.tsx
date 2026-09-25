import { act, fireEvent, render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { kg1 } from '../../format'
import { BAND_ARMS_MS, CONFIRM_GUARD_MS, LivePanel } from './LivePanel'
import { Rail } from './Rail'
import { SessionTotals } from './SessionTotals'
import { useOutbox, useSheets } from '../stores'
import { payload } from '../types.test-d'
import type { SeedSource, SessionDetailPayload } from '../types'

beforeEach(() => {
  useSheets.setState(useSheets.getInitialState(), true)
  useOutbox.setState(useOutbox.getInitialState(), true)
})

const handlers = () => ({
  onConfirm: vi.fn(), onToggleSet: vi.fn(), onRestOver: vi.fn(),
  onShiftRest: vi.fn(), onSkipRest: vi.fn(),
})

const live = payload.visible_exercises.find((se) => se.id === payload.live_id)!

/** The fixture with the live exercise's sets replaced. */
function withLiveSets(sets: typeof live.sets): SessionDetailPayload {
  return {
    ...payload,
    visible_exercises: payload.visible_exercises.map((se) =>
      (se.id === live.id ? { ...se, sets } : se)),
  }
}

describe('LivePanel', () => {
  it('names the live exercise and opens its own sheet', async () => {
    const user = userEvent.setup()
    render(<LivePanel payload={payload} {...handlers()} />)
    expect(screen.getByRole('heading', { level: 2, name: live.name })).toBeInTheDocument()

    await user.click(screen.getByLabelText(`${live.name} — Optionen`))
    expect(useSheets.getState().openId).toBe(`sheet-ex-${live.id}`)
  })

  it('shows the drawing beside the name, a tap from the sheet with it whole', async () => {
    // Round 4: the small tile, not a band across the card.
    const user = userEvent.setup()
    expect(live.picture).not.toBeNull()
    render(<LivePanel payload={payload} {...handlers()} />)
    const tile = screen.getByRole('button', { name: `${live.name} — Bild` })
    expect(tile).toHaveClass('pic', 'pic--live')
    expect(tile.querySelector('img')).toHaveAttribute('src', live.picture)
    expect(tile.closest('.live__title')!.querySelector('h2')).toHaveTextContent(live.name)

    await user.click(tile)
    expect(useSheets.getState().openId).toBe(`sheet-ex-${live.id}`)
  })

  it('holds the drawing\'s place with the dumbbell until there is one', () => {
    // Not a button then: the sheet it would open has no picture to show.
    const undrawn: SessionDetailPayload = {
      ...payload,
      visible_exercises: payload.visible_exercises.map((se) =>
        se.id === live.id ? { ...se, picture: null } : se),
    }
    const { container } = render(<LivePanel payload={undrawn} {...handlers()} />)
    expect(screen.queryByRole('button', { name: `${live.name} — Bild` })).toBeNull()
    const tile = container.querySelector('.live__title .pic--live.pic--none')!
    expect(tile).toHaveAttribute('aria-hidden', 'true')
    expect(tile.querySelector('svg.icon-dumbbell')).toBeInTheDocument()
    expect(screen.getByRole('heading', { level: 2, name: live.name })).toBeInTheDocument()
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

  it('drops a bounce on "Satz geschafft", and is never held for the connection (G-138)', async () => {
    // Held while a set write was in flight, the button stayed held for as
    // long as the wifi was gone: offline, no set could be logged at all. A
    // double tap still must not log the next set, or append a phantom one
    // after an exercise's last.
    const user = userEvent.setup()
    const h = handlers()
    const now = vi.spyOn(Date, 'now').mockReturnValue(1_000_000)
    render(<LivePanel payload={payload} {...h} />)
    const go = screen.getByText('Satz geschafft').closest('button')!
    expect(go).toBeEnabled()

    await user.click(go)
    now.mockReturnValue(1_000_000 + CONFIRM_GUARD_MS - 1)
    await user.click(go)
    expect(h.onConfirm).toHaveBeenCalledTimes(1)

    now.mockReturnValue(1_000_000 + CONFIRM_GUARD_MS)
    await user.click(go)
    expect(h.onConfirm).toHaveBeenCalledTimes(2)
    now.mockRestore()
  })

  it('marks the chips whose write waits on the phone (B6)', () => {
    const done = live.sets.find((s) => s.completed)!
    useOutbox.setState({ state: 'waiting', count: 1, setIds: [done.id] })
    render(<LivePanel payload={payload} {...handlers()} />)
    const index = live.sets.indexOf(done) + 1
    const chip = screen.getByLabelText(new RegExp(`^Satz ${index} (erledigt|— Rekord)`))
    expect(chip).toHaveClass('is-waiting')
    expect(chip.getAttribute('aria-label')).toContain('wartet auf Verbindung')
    expect(document.querySelectorAll('.set.is-waiting')).toHaveLength(1)
  })

  it('keeps the numbers dialled in for a set through a reload (G-009)', async () => {
    // Component state alone: iOS dropping the PWA in the background put the
    // plan back on a set the lifter had already set up.
    const user = userEvent.setup()
    const next = live.sets.find((s) => !s.completed)!
    const first = render(<LivePanel payload={payload} {...handlers()} />)
    await user.click(screen.getByLabelText('Wiederholungen erhöhen'))
    await user.click(screen.getByLabelText('Wiederholungen erhöhen'))
    first.unmount()

    render(<LivePanel payload={payload} {...handlers()} />)
    expect(screen.getByLabelText('Wiederholungen eingeben'))
      .toHaveTextContent(String(next.reps! + 2))
  })

  it('drops the draft once the set is logged, and for any other set', async () => {
    const user = userEvent.setup()
    const next = live.sets.find((s) => !s.completed)!
    const h = handlers()
    const first = render(<LivePanel payload={payload} {...h} />)
    await user.click(screen.getByLabelText('Wiederholungen erhöhen'))
    await user.click(screen.getByText('Satz geschafft').closest('button')!)
    expect(h.onConfirm).toHaveBeenCalledWith(next.weight, next.reps! + 1, next.id)
    first.unmount()

    render(<LivePanel payload={payload} {...handlers()} />)
    expect(screen.getByLabelText('Wiederholungen eingeben')).toHaveTextContent(String(next.reps))
  })

  it('drops the draft when the steppers move to another set', async () => {
    // Dialled in, then the lifter bound the steppers to a later chip: the
    // numbers were left behind, and a reload must not bring them back.
    const user = userEvent.setup()
    const [next, later] = live.sets.filter((s) => !s.completed)
    const first = render(<LivePanel payload={payload} {...handlers()} />)
    await user.click(screen.getByLabelText('Wiederholungen erhöhen'))
    await user.click(screen.getByLabelText(new RegExp(`^Satz ${live.sets.indexOf(later!) + 1}, geplant`)))
    first.unmount()

    render(<LivePanel payload={payload} {...handlers()} />)
    expect(screen.getByLabelText('Wiederholungen eingeben')).toHaveTextContent(String(next!.reps))
  })

  it('keeps the numbers dialled in when the set just added gets its real id (B6 review)', async () => {
    // Appended with no signal, drawn as -5 until the add lands: its real id
    // is the same set, and the numbers dialled for the next one stay.
    const user = userEvent.setup()
    const drawn = withLiveSets(live.sets.map((s) => ({ ...s, completed: true }))
      .concat({ id: -5, weight: 70, reps: 5, completed: true, base_weight: null, key: 'k1' }))
    const named = withLiveSets(drawn.visible_exercises.find((se) => se.id === live.id)!.sets
      .map((s) => (s.id === -5 ? { ...s, id: 900 } : s)))
    const view = render(<LivePanel payload={drawn} {...handlers()} />)
    await user.click(screen.getByLabelText('Wiederholungen erhöhen'))
    view.rerender(<LivePanel payload={named} {...handlers()} />)
    expect(screen.getByLabelText('Wiederholungen eingeben')).toHaveTextContent('6')
  })

  it('keeps the numbers dialled for a set just added and reopened, as it gets its real id (B6 re-review)', async () => {
    // Bound by its drawn id, the steppers were re-seeded -- and the draft
    // cleared -- the moment the add landed.
    const user = userEvent.setup()
    const drawn = withLiveSets(live.sets.map((s) => ({ ...s, completed: true }))
      .concat({ id: -5, weight: 70, reps: 5, completed: false, base_weight: null, key: 'k1' }))
    const named = withLiveSets(drawn.visible_exercises.find((se) => se.id === live.id)!.sets
      .map((s) => (s.id === -5 ? { ...s, id: 900 } : s)))
    const view = render(<LivePanel payload={drawn} {...handlers()} />)
    await user.click(screen.getByLabelText('Wiederholungen erhöhen'))
    expect(screen.getByLabelText('Wiederholungen eingeben')).toHaveTextContent('6')
    view.rerender(<LivePanel payload={named} {...handlers()} />)
    expect(screen.getByLabelText('Wiederholungen eingeben')).toHaveTextContent('6')
  })

  it('keeps a set just added picked, as it gets its real id (B6 re-review)', async () => {
    const user = userEvent.setup()
    const open = live.sets.map((s, i) => ({ ...s, completed: i > 0 ? s.completed : false }))
    const drawn = withLiveSets(open
      .concat({ id: -5, weight: 70, reps: 5, completed: false, base_weight: null, key: 'k1' }))
    const named = withLiveSets(drawn.visible_exercises.find((se) => se.id === live.id)!.sets
      .map((s) => (s.id === -5 ? { ...s, id: 900 } : s)))
    const view = render(<LivePanel payload={drawn} {...handlers()} />)
    const added = () => screen.getByLabelText(new RegExp(`^Satz ${live.sets.length + 1}, geplant`))
    await user.click(added())
    expect(screen.getByLabelText('Wiederholungen eingeben')).toHaveTextContent('5')
    view.rerender(<LivePanel payload={named} {...handlers()} />)
    expect(screen.getByLabelText('Wiederholungen eingeben')).toHaveTextContent('5')
    expect(added()).toHaveClass('is-now')
    // The same chip, not one drawn anew: that dropped the keyboard's focus.
    expect(added()).toHaveFocus()
  })

  it('never takes a draft left for another set', async () => {
    const user = userEvent.setup()
    const next = live.sets.find((s) => !s.completed)!
    const first = render(<LivePanel payload={payload} {...handlers()} />)
    await user.click(screen.getByLabelText('Wiederholungen erhöhen'))
    first.unmount()

    // The server moved on meanwhile: that set is done, the next one is up.
    const moved: SessionDetailPayload = {
      ...payload,
      visible_exercises: payload.visible_exercises.map((se) =>
        se.id === live.id
          ? { ...se, sets: se.sets.map((s) => (s.id === next.id ? { ...s, completed: true } : s)) }
          : se),
    }
    const after = live.sets.find((s) => !s.completed && s.id !== next.id)
    render(<LivePanel payload={moved} {...handlers()} />)
    const shown = after?.reps ?? next.reps
    expect(screen.getByLabelText('Wiederholungen eingeben')).toHaveTextContent(String(shown))
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
            { id: 900, weight: 50, reps: 10, completed: false, base_weight: null, key: null },
            { id: 901, weight: 50, reps: 10, completed: false, base_weight: null, key: null },
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
            { id: 950, weight: next.weight, reps: next.reps, completed: false, base_weight: null, key: null },
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

  // Its own seed rather than the fixture's: the fixture is regenerated from a
  // real history, and the pick it finds changes with that history. Dates are
  // well over a week back, so the line names the date, not a weekday.
  const LIFTED = [{ weight: 55, reps: 10 }, { weight: 55, reps: 9 }, { weight: 55, reps: 8 }]
  const seeded = (source: Partial<SeedSource>, over: Partial<SessionDetailPayload> = {}) => ({
    ...payload,
    ...over,
    seed_sources: {
      ...payload.seed_sources,
      [String(live.id)]: {
        date: '2026-08-25T09:47:25', position: live.position, basis: 'slot' as const,
        is_latest: true, sets: LIFTED, ...source,
      },
    },
  })
  /** The rule behind the numbers, one tap away (D8). */
  const openSource = async () => {
    await userEvent.setup().click(screen.getByRole('button', { name: /^(Letztes Mal|Stärkste Einheit)/ }))
    return screen.getByText('Vorgabe').closest('p')!
  }

  it('leads with what was lifted, in one line', () => {
    // G-053: the numbers, not the position-matching rule behind them. The box
    // took 60-90px of every card for a sentence nobody needed mid-set.
    render(<LivePanel payload={seeded({})} {...handlers()} />)
    const line = screen.getByRole('button', { name: /^Letztes Mal/ })
    expect(line).toHaveTextContent('Letztes Mal 25.08. 55,0 × 10 · 9 · 8')
    expect(line).toHaveAttribute('aria-expanded', 'false')
    expect(screen.queryByText('Vorgabe')).not.toBeInTheDocument()
  })

  it('says "Letztes Mal" only when it was the last time', () => {
    // The best result lately, seeded at this slot, can be ten days old while
    // a lighter workout came after it.
    render(<LivePanel payload={seeded({ is_latest: false })} {...handlers()} />)
    expect(screen.queryByRole('button', { name: /^Letztes Mal/ })).not.toBeInTheDocument()
    expect(screen.getByRole('button', { name: /^Stärkste Einheit 25\.08\./ })).toBeInTheDocument()
  })

  it('says where the plan came from on a tap', async () => {
    render(<LivePanel payload={seeded({})} {...handlers()} />)
    const rule = await openSource()
    expect(rule).toHaveTextContent('Vorgabe vom 25.08., gleiche Position im Workout.')
    expect(screen.getByRole('button', { name: /^Letztes Mal/ }))
      .toHaveAttribute('aria-expanded', 'true')
  })

  it('says so when the plan comes from an earlier, fresher slot', async () => {
    const late = seeded(
      { date: '2026-08-30T09:57:42', position: 1, basis: 'earlier_slot' },
      { visible_exercises: payload.visible_exercises.map((se) =>
        se.id === live.id ? { ...se, position: 4 } : se) })
    render(<LivePanel payload={late} {...handlers()} />)
    expect(await openSource()).toHaveTextContent(
      'Vorgabe vom 30.08., damals an Position 1 — so spät im Workout gibt es noch nichts, daher dein bestes Ergebnis von früher.')
  })

  it('says so when the plan comes from a later slot, and after a layoff', async () => {
    const later = seeded({ date: '2026-08-30T09:57:42', position: 5 })
    const { unmount } = render(<LivePanel payload={later} {...handlers()} />)
    expect(await openSource()).toHaveTextContent(
      'Vorgabe vom 30.08., damals später im Workout (Position 5).')
    unmount()

    const layoff = seeded({ date: '2026-06-14T09:00:00', position: 2, basis: 'layoff' })
    render(<LivePanel payload={layoff} {...handlers()} />)
    expect(await openSource()).toHaveTextContent(
      'Vorgabe vom 14.06. — schon länger her, daher dein letztes Workout statt des besten.')
  })

  it('says nothing about a source when there is no history', () => {
    const none: SessionDetailPayload = {
      ...payload,
      seed_sources: { ...payload.seed_sources, [String(live.id)]: null },
    }
    render(<LivePanel payload={none} {...handlers()} />)
    expect(screen.queryByText('Vorgabe')).not.toBeInTheDocument()
    expect(screen.queryByRole('button', { name: /^(Letztes Mal|Stärkste Einheit)/ }))
      .not.toBeInTheDocument()
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
    }
    const { container } = render(<LivePanel payload={advised} {...handlers()} />)
    const button = container.querySelector('#set-confirm')!
    for (const advice of [container.querySelector('.live__stall')!,
      container.querySelector('.targetline')!]) {
      expect(advice.compareDocumentPosition(button))
        .toBe(Node.DOCUMENT_POSITION_FOLLOWING)
    }
    // The stall line keeps its fact and gives no weight of its own: what to
    // lift is the target's to say (D2 P1), one answer rather than two.
    const stall = container.querySelector('.live__stall')!
    expect(stall.textContent).toBe('Stagniert 4 Workouts ohne neuen e1RM-PR.')
  })

  it('says the target set by set, and only says it', () => {
    // Each set at its own weight, one rep on (Michi, M2 09-24), in the
    // Vorgabe line's own notation. Said, never seeded: the steppers keep
    // pre-filling last time's numbers.
    const aimed: SessionDetailPayload = {
      ...payload,
      next_targets: { [String(live.id)]: [
        { weight: 40, reps: 9 }, { weight: 35, reps: 10 }, { weight: 35, reps: 9 }] },
    }
    const { container } = render(<LivePanel payload={aimed} {...handlers()} />)
    expect(container.querySelector('.targetline')!.textContent)
      .toBe('Ziel 40,0 × 9 · 35,0 × 10 · 9')
    const next = live.sets.find((s) => !s.completed)!
    expect(screen.getByLabelText('Gewicht eingeben'))
      .toHaveTextContent(kg1(next.weight!))
  })

  it('leads with the target, then where the plan came from', () => {
    // The exercise page's order (M2): "Nächstes Ziel", then "Letztes Mal".
    const { container } = render(<LivePanel payload={payload} {...handlers()} />)
    const target = container.querySelector('.targetline')!
    expect(target.compareDocumentPosition(container.querySelector('.seedline')!))
      .toBe(Node.DOCUMENT_POSITION_FOLLOWING)
  })

  it('has no target line without a workout to build on', () => {
    const { container } = render(
      <LivePanel payload={{ ...payload, next_targets: {} }} {...handlers()} />)
    expect(container.querySelector('.targetline')).toBeNull()
  })

  it('names what a deload marked late would lift, and changes nothing', () => {
    // D4: marked after the first set, the deload rescales nothing (08-12
    // rule); the exercise says the weight instead, where its target stood.
    const late: SessionDetailPayload = {
      ...payload,
      session: { ...payload.session, is_deload: true, deload_pct: 70 },
      next_targets: {},
      deload_hints: { [String(live.id)]: 35 },
    }
    const { container } = render(<LivePanel payload={late} {...handlers()} />)
    const hint = container.querySelector('.targetline--deload')!
    expect(hint.textContent)
      .toBe(`Deload 70 % ≈ 35,0 kg${live.is_unilateral ? ' je Seite' : ''}`)
    const next = live.sets.find((s) => !s.completed)!
    expect(screen.getByLabelText('Gewicht eingeben'))
      .toHaveTextContent(kg1(next.weight!))
  })

  /** A rest of `total` seconds with `left` still to go, after the live
   *  exercise's first set. */
  const restingFor = (left: number, total = 90): SessionDetailPayload => ({
    ...payload,
    resting: true,
    rest_total_seconds: total,
    session: {
      ...payload.session,
      rest_ends_at: new Date(Date.now() + left * 1000).toISOString().replace('Z', ''),
      resting_set_id: live.sets[0]!.id,
    },
  })
  /** The same rest ended `ago` seconds back, as the server reports it then. */
  const restOver = (ago: number): SessionDetailPayload => ({
    ...restingFor(-ago), resting: false, rest_total_seconds: 0,
  })

  it('keeps the button name stable while a rest runs', () => {
    // A name that rewrote itself every second would be worse than no
    // countdown. The clock has its own band now, outside the button.
    const { container } = render(<LivePanel payload={restingFor(90)} {...handlers()} />)
    const confirm = container.querySelector('#set-confirm')!
    expect(confirm).toHaveClass('is-resting')
    expect(confirm).toHaveAccessibleName('Satz geschafft')
    expect(confirm).not.toHaveTextContent(/\d:\d\d/)
  })

  it('puts the countdown in a band above the button, readable from the bench', () => {
    // G-055: "Pause 2:25" was 13px at the edge of the orange button.
    const { container } = render(<LivePanel payload={restingFor(60)} {...handlers()} />)
    const band = screen.getByRole('group', { name: 'Pause' })
    expect(band).toHaveTextContent('Pause · von 1:30')
    expect(screen.getByRole('timer')).toHaveTextContent(/^(1:00|0:59)$/)
    const confirm = container.querySelector('#set-confirm')!
    expect(band.compareDocumentPosition(confirm) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy()
  })

  it('moves or ends the rest from the band', () => {
    // Ending a rest early was ⋮ -> "Pause beenden", and there was no ±15 s.
    // The keys say what they show, so "+15" is also what a voice user says.
    vi.useFakeTimers()
    const h = handlers()
    render(<LivePanel payload={restingFor(60)} {...h} />)
    act(() => { vi.advanceTimersByTime(BAND_ARMS_MS) })

    fireEvent.click(screen.getByRole('button', { name: '+15 Sekunden' }))
    expect(h.onShiftRest).toHaveBeenLastCalledWith(15)
    fireEvent.click(screen.getByRole('button', { name: '−15 Sekunden' }))
    expect(h.onShiftRest).toHaveBeenLastCalledWith(-15)
    fireEvent.click(screen.getByRole('button', { name: 'Pause beenden' }))
    expect(h.onSkipRest).toHaveBeenCalledTimes(1)
    vi.useRealTimers()
  })

  it('ignores taps on a band that has only just appeared', () => {
    // I1 review: the band pushes the confirm button down, and the second tap
    // of a double tap on "Satz geschafft" landed on "−15".
    vi.useFakeTimers()
    const h = handlers()
    render(<LivePanel payload={restingFor(60)} {...h} />)
    fireEvent.click(screen.getByRole('button', { name: '−15 Sekunden' }))
    fireEvent.click(screen.getByRole('button', { name: 'Pause beenden' }))
    expect(h.onShiftRest).not.toHaveBeenCalled()
    expect(h.onSkipRest).not.toHaveBeenCalled()

    act(() => { vi.advanceTimersByTime(BAND_ARMS_MS) })
    fireEvent.click(screen.getByRole('button', { name: '−15 Sekunden' }))
    expect(h.onShiftRest).toHaveBeenCalledWith(-15)
    vi.useRealTimers()
  })

  it('arms a band that arrives with a later answer, not with the panel', () => {
    // The set's answer brings the band; the panel has been up for minutes.
    vi.useFakeTimers()
    const h = handlers()
    const { rerender } = render(<LivePanel payload={payload} {...h} />)
    expect(screen.queryByRole('group', { name: 'Pause' })).not.toBeInTheDocument()
    act(() => { vi.advanceTimersByTime(5000) })

    rerender(<LivePanel payload={restingFor(60)} {...h} />)
    fireEvent.click(screen.getByRole('button', { name: '−15 Sekunden' }))
    expect(h.onShiftRest).not.toHaveBeenCalled()

    act(() => { vi.advanceTimersByTime(BAND_ARMS_MS) })
    fireEvent.click(screen.getByRole('button', { name: '−15 Sekunden' }))
    expect(h.onShiftRest).toHaveBeenCalledWith(-15)
    vi.useRealTimers()
  })

  describe('a band that stays up', () => {
    // Fix-round review: staying until the next set, the band is moved by the
    // card above it (the next exercise's name, a line that comes or goes),
    // and the button with it -- the double tap's second press finds a key.
    let bandTop = 300
    beforeEach(() => {
      bandTop = 300
      vi.useFakeTimers()
      vi.spyOn(HTMLElement.prototype, 'getBoundingClientRect').mockImplementation(function (this: HTMLElement) {
        const top = this.classList.contains('restband') ? bandTop : 0
        return { top, bottom: top, left: 0, right: 0, width: 0, height: 0, x: 0, y: top, toJSON: () => ({}) }
      })
    })
    afterEach(() => {
      vi.restoreAllMocks()
      vi.useRealTimers()
    })

    it('ignores taps again once it is pushed down', () => {
      const h = handlers()
      render(<LivePanel payload={restingFor(60)} {...h} />)
      act(() => { vi.advanceTimersByTime(BAND_ARMS_MS) })
      fireEvent.click(screen.getByRole('button', { name: '+15 Sekunden' }))
      expect(h.onShiftRest).toHaveBeenCalledTimes(1)

      bandTop = 420
      act(() => { vi.advanceTimersByTime(1000) })   // the next render measures it
      fireEvent.click(screen.getByRole('button', { name: '+15 Sekunden' }))
      expect(h.onShiftRest).toHaveBeenCalledTimes(1)

      act(() => { vi.advanceTimersByTime(BAND_ARMS_MS) })
      fireEvent.click(screen.getByRole('button', { name: '+15 Sekunden' }))
      expect(h.onShiftRest).toHaveBeenCalledTimes(2)
    })

    it('stays armed when it moves up, and measures the next push from there', () => {
      // Up, the band leaves the button's old spot to what is below it.
      const h = handlers()
      render(<LivePanel payload={restingFor(60)} {...h} />)
      act(() => { vi.advanceTimersByTime(BAND_ARMS_MS) })

      bandTop = 200
      act(() => { vi.advanceTimersByTime(1000) })
      fireEvent.click(screen.getByRole('button', { name: '+15 Sekunden' }))
      expect(h.onShiftRest).toHaveBeenCalledTimes(1)

      bandTop = 260   // down again, but still above where it started
      act(() => { vi.advanceTimersByTime(1000) })
      fireEvent.click(screen.getByRole('button', { name: '+15 Sekunden' }))
      expect(h.onShiftRest).toHaveBeenCalledTimes(1)
    })

    it('stays armed through its own ticks', () => {
      // A tick re-renders the panel every second; only a move re-arms.
      const h = handlers()
      render(<LivePanel payload={restingFor(60)} {...h} />)
      act(() => { vi.advanceTimersByTime(2000) })   // lands on a tick
      fireEvent.click(screen.getByRole('button', { name: 'Pause beenden' }))
      expect(h.onSkipRest).toHaveBeenCalledTimes(1)
    })
  })

  it('offers no "+15" past the longest rest there is', () => {
    render(<LivePanel payload={restingFor(300, 600)} {...handlers()} />)
    expect(screen.getByRole('button', { name: '+15 Sekunden' })).toBeDisabled()
    expect(screen.getByRole('button', { name: '−15 Sekunden' })).toBeEnabled()
  })

  it('keeps the band once the rest is over, counting up, until the next set', () => {
    // Round 4: gone, the band took the button 112px up while the phone rang.
    const { container } = render(<LivePanel payload={restOver(12)} {...handlers()} />)
    const band = screen.getByRole('group', { name: 'Pause' })
    expect(band).toHaveTextContent('Pause vorbei')
    expect(band).toHaveClass('is-over')
    expect(screen.getByRole('timer')).toHaveTextContent(/^\+0:1[23]$/)
    // Nothing left to shorten, lengthen or end.
    expect(screen.queryByRole('button', { name: /Sekunden|Pause beenden/ })).not.toBeInTheDocument()
    expect(container.querySelector('#set-confirm')).not.toHaveClass('is-resting')
  })

  it('counts up from zero when the server ended the rest a moment ahead of this clock', () => {
    // A skip stamps the end with the server's now; a phone a few seconds slow
    // must not count that back down as a rest.
    render(<LivePanel payload={{ ...restingFor(4), resting: false, rest_total_seconds: 0 }}
      {...handlers()} />)
    expect(screen.getByRole('group', { name: 'Pause' })).toHaveTextContent('Pause vorbei')
    expect(screen.getByRole('timer')).toHaveTextContent('+0:00')
  })

  it('shows no band while nothing rests', () => {
    render(<LivePanel payload={payload} {...handlers()} />)
    expect(screen.queryByRole('group', { name: 'Pause' })).not.toBeInTheDocument()
    expect(screen.queryByRole('timer')).not.toBeInTheDocument()
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
        resting_set_id: live.sets[0]!.id,
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
        resting_set_id: live.sets[0]!.id,
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
  stagnation_counts: {}, next_targets: {}, deload_hints: {},
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
