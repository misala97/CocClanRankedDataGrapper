import { render, screen } from '@testing-library/react'
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
      .toHaveTextContent(kg1(next.weight))
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
      next.weight + payload.live_increment, next.reps)
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
      .toHaveTextContent(kg1(last.weight))
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
      ready_for_more: { sets: 3, weight: 35, is_latest: true },
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
      .toHaveTextContent(kg1(next.weight))
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
