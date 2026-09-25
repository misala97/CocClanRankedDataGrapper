import { act, fireEvent, render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { HAND_OVER_MS, Queue } from './Queue'
import { TickStrip } from './TickStrip'
import { useAnnouncer, useSheets, useWorkoutUi } from '../stores'
import { payload } from '../types.test-d'
import type { LiveExercise } from '../types'

beforeEach(() => {
  useSheets.setState(useSheets.getInitialState(), true)
  useWorkoutUi.setState(useWorkoutUi.getInitialState(), true)
  useAnnouncer.setState(useAnnouncer.getInitialState(), true)
})

// A test on fake timers that fails midway must not leave the rest on them:
// userEvent waits on real ones, and every later test times out instead.
afterEach(() => { vi.useRealTimers() })

const exercises = payload.visible_exercises
const liveId = payload.live_id
const noop = () => {}

describe('TickStrip', () => {
  it('draws one tick per set and states the count as its accessible name', () => {
    render(<TickStrip states={payload.tick_states}
      done={payload.sets_done} total={payload.sets_total} />)
    const strip = screen.getByRole('img')
    expect(strip).toHaveAttribute(
      'aria-label', `${payload.sets_done} von ${payload.sets_total} Sätzen erledigt`)
    expect(strip.querySelectorAll('.tick')).toHaveLength(payload.tick_states.length)
  })

  it('lights the done ticks and heats the one you are on', () => {
    const { container } = render(
      <TickStrip states={['done', 'now', 'open']} done={1} total={3} />)
    const ticks = [...container.querySelectorAll('.tick')]
    expect(ticks[0]).toHaveClass('is-on')
    expect(ticks[1]).toHaveClass('is-hot')
    expect(ticks[2]!.className).toBe('tick')
  })
})

describe('Queue', () => {
  it('lists the whole workout including the exercise you are on', () => {
    // Filtering the live one out left a hole in the sequence -- the list ran
    // 1, 3, 4 with nothing saying where you were, so it stopped being a map of
    // the session and became a list of leftovers.
    render(<Queue exercises={exercises} liveId={liveId} onReorder={noop} />)
    for (const se of exercises) {
      expect(screen.getByText(se.name)).toBeInTheDocument()
    }
  })

  it('still tells a screen reader each row\'s place, now that no number shows', () => {
    // I1b review: the number was the only position cue, and the drawing that
    // took its place is aria-hidden. The row's place in THIS list, as before.
    const gappy = exercises.map((se, i) => ({ ...se, position: (i + 1) * 3 }))
    const { container } = render(<Queue exercises={gappy} liveId={liveId} onReorder={noop} />)
    const places = [...container.querySelectorAll('.queue__row .queue__lead .sr-only')]
      .map((el) => el.textContent)
    expect(places).toEqual(gappy.map((_, i) => `${i + 1}.`))
  })

  it('hands the wash to the next row with the drawing landing, once', () => {
    // gym.css has carried .just-now since the Jinja screen; the port never
    // set it (I1b review). Not on the first render: nothing was handed over.
    vi.useFakeTimers()
    const other = exercises.find((se) => se.id !== liveId)!
    const { container, rerender } = render(
      <Queue exercises={exercises} liveId={liveId} onReorder={noop} />)
    expect(container.querySelector('.just-now')).toBeNull()

    rerender(<Queue exercises={exercises} liveId={other.id} onReorder={noop} />)
    expect(container.querySelector(`[data-se-id="${other.id}"]`)).toHaveClass('just-now')
    expect(container.querySelectorAll('.just-now')).toHaveLength(1)

    act(() => { vi.advanceTimersByTime(HAND_OVER_MS) })
    expect(container.querySelector('.just-now')).toBeNull()
  })

  it('marks the live row for assistive tech, not by colour alone', () => {
    render(<Queue exercises={exercises} liveId={liveId} onReorder={noop} />)
    const live = exercises.find((se) => se.id === liveId)!
    expect(screen.getByText(live.name).closest('button'))
      .toHaveAttribute('aria-current', 'step')
  })

  it('leads with a tick when finished, the drawing when live or still ahead', () => {
    // Round 4: the drawing took the slot number's place. Done keeps its tick
    // -- done is the thing to know about it, and never by colour alone.
    const done: LiveExercise = {
      ...exercises[0]!, id: 90, name: 'Fertig', position: 4, skipped: false,
      sets: [{ id: 1, weight: 50, reps: 5, completed: true, base_weight: null, key: null }],
    }
    const drawn = exercises.map((se) => ({ ...se, picture: `/static/gym/art/x-${se.id}.webp?v=1` }))
    const { container } = render(
      <Queue exercises={[...drawn, done]} liveId={liveId} onReorder={noop} />)
    const row = container.querySelector('[data-se-id="90"]') as HTMLElement
    expect(row.querySelector('.queue__mark')).toBeInTheDocument()
    expect(row.querySelector('.pic')).toBeNull()

    const live = container.querySelector(`[data-se-id="${liveId}"]`)!
    expect(live.querySelector('.pic--queue img')!.getAttribute('src'))
      .toBe(`/static/gym/art/x-${liveId}.webp?v=1`)
    expect(live.querySelector('.queue__mark')).toBeNull()

    const ahead = drawn.find((se) => se.id !== liveId)!
    const aheadRow = container.querySelector(`[data-se-id="${ahead.id}"]`) as HTMLElement
    expect(aheadRow.querySelector('.pic--queue img')).toBeInTheDocument()
  })

  it('keeps the drawing on the live row once its last set is logged', () => {
    // Everything logged, the last exercise stays live: it is still the one
    // you are on, not a finished one further up.
    const allDone = exercises.map((se) => ({
      ...se, skipped: false, sets: se.sets.map((s) => ({ ...s, completed: true })),
    }))
    const { container } = render(<Queue exercises={allDone} liveId={liveId} onReorder={noop} />)
    const live = container.querySelector(`[data-se-id="${liveId}"]`)!
    expect(live.querySelector('.pic--queue')).toBeInTheDocument()
    expect(live.querySelector('.queue__mark')).toBeNull()
  })

  it('draws the dumbbell for an exercise without a drawing, and shows no number', () => {
    // The list's own order is the order; the stored slot never was (it can
    // have holes or twins), and the row's place no longer needs spelling out
    // on screen -- only to a screen reader (above).
    const gappy = exercises.map((se, i) => ({
      ...se, skipped: false, picture: null, position: (i + 1) * 3,
    }))
    const { container } = render(<Queue exercises={gappy} liveId={liveId} onReorder={noop} />)
    const second = container.querySelector(`[data-se-id="${gappy[1]!.id}"]`) as HTMLElement
    expect(second.querySelector('.pic--queue.pic--none svg.icon-dumbbell')).toBeInTheDocument()
    for (const lead of container.querySelectorAll('.queue__row .queue__lead')) {
      const shown = [...lead.children].filter((el) => !el.classList.contains('sr-only'))
      expect(shown.map((el) => el.textContent).join('')).toBe('')
    }
  })

  it('summarises each row by what it is', () => {
    const { container } = render(<Queue exercises={exercises} liveId={liveId} onReorder={noop} />)
    const skipped = exercises.find((se) => se.skipped)!
    const row = container.querySelector(`[data-se-id="${skipped.id}"]`)!
    expect(row).toHaveTextContent('Übersprungen')

    const live = container.querySelector(`[data-se-id="${liveId}"]`)!
    const liveSe = exercises.find((se) => se.id === liveId)!
    const doneCount = liveSe.sets.filter((s) => s.completed).length
    expect(live).toHaveTextContent(`${doneCount}/${liveSe.sets.length}`)
  })

  it('says "neu" for a row planned blank, not a weight it never had', () => {
    // An exercise with no history waits with no numbers (V2); "3 × 20,0" was
    // the placeholder talking.
    const other = exercises.find((se) => se.id !== liveId)!
    const blank: LiveExercise = {
      ...other, skipped: false,
      sets: [1, 2, 3].map((n) => ({
        id: 900 + n, weight: null, reps: null, completed: false, base_weight: null, key: null,
      })),
    }
    const { container } = render(<Queue liveId={liveId} onReorder={noop}
      exercises={exercises.map((se) => (se.id === other.id ? blank : se))} />)
    const row = container.querySelector(`[data-se-id="${other.id}"]`)!
    expect(row.querySelector('.queue__load')).toHaveTextContent(/^neu$/)
  })

  it('says what a deload marked late would lift on the rows still ahead', () => {
    // D4: nothing rescales once a set is done, so a row ahead keeps its plan
    // and says the deload's weight under it. Not the live row: the card
    // above says it there.
    const other = exercises.find((se) => se.id !== liveId)!
    const ahead: LiveExercise = {
      ...other, skipped: false,
      sets: [1, 2, 3].map((n) => ({
        id: 900 + n, weight: 50, reps: 8, completed: false, base_weight: null, key: null,
      })),
    }
    const { container } = render(<Queue liveId={liveId} onReorder={noop}
      exercises={exercises.map((se) => (se.id === other.id ? ahead : se))}
      deloadHints={{ [String(other.id)]: 35, [String(liveId)]: 42.5 }} />)
    const row = container.querySelector(`[data-se-id="${other.id}"]`)!
    expect(row.querySelector('.queue__load')).toHaveTextContent(/^3 × 50,0/)
    expect(row.querySelector('.queue__deload')).toHaveTextContent('Deload ≈ 35,0')
    const live = container.querySelector(`[data-se-id="${liveId}"]`)!
    expect(live.querySelector('.queue__deload')).toBeNull()
  })

  it('opens that exercise own sheet from its row', async () => {
    // One interaction for every exercise instead of a menu on each.
    const user = userEvent.setup()
    render(<Queue exercises={exercises} liveId={liveId} onReorder={noop} />)
    await user.click(screen.getByText(exercises[0]!.name))
    expect(useSheets.getState().openId).toBe(`sheet-ex-${exercises[0]!.id}`)
  })

  it('offers adding an exercise from the queue, not only from the corner sheet', async () => {
    // The queue is where you are already reading what the workout contains,
    // so it is where "and one more" belongs.
    const user = userEvent.setup()
    render(<Queue exercises={exercises} liveId={liveId} onReorder={noop} />)
    await user.click(screen.getByText('Übung hinzufügen'))
    expect(useSheets.getState().openId).toBe('sheet-add-exercise')
  })

  it('hides the add row during reorder, and puts the handles in the tab order', () => {
    // During a reorder every row in this list is a thing being moved, and an
    // action is not a position in the sequence.
    const { container, rerender } = render(
      <Queue exercises={exercises} liveId={liveId} onReorder={noop} />)
    expect(container.querySelectorAll('.drag-handle')[0]).toHaveAttribute('tabindex', '-1')

    useWorkoutUi.getState().setReorder(true)
    rerender(<Queue exercises={exercises} liveId={liveId} onReorder={noop} />)
    expect(screen.queryByText('Übung hinzufügen')).not.toBeInTheDocument()
    expect(container.querySelectorAll('.drag-handle')[0]).toHaveAttribute('tabindex', '0')
  })

  it('applies the mode class the reorder CSS keys off', () => {
    // The old body.is-reordering contract had no writer after the React port
    // and shipped the mode dead behind passing tests. This pins the VISIBLE
    // contract -- the class the stylesheet actually selects on -- not just
    // the store flag.
    const { container, rerender } = render(
      <Queue exercises={exercises} liveId={liveId} onReorder={noop} />)
    expect(container.querySelector('.queue')).not.toHaveClass('is-reordering')

    useWorkoutUi.getState().setReorder(true)
    rerender(<Queue exercises={exercises} liveId={liveId} onReorder={noop} />)
    expect(container.querySelector('.queue')).toHaveClass('is-reordering')
  })

  it('moves a row with the arrow keys, announces it, and posts the order', () => {
    const onReorder = vi.fn()
    useWorkoutUi.getState().setReorder(true)
    const { container } = render(
      <Queue exercises={exercises} liveId={liveId} onReorder={onReorder} />)
    const first = container.querySelectorAll<HTMLButtonElement>('.drag-handle')[0]!
    first.focus()
    fireEvent.keyDown(first, { key: 'ArrowDown' })

    const ids = exercises.map((se) => se.id)
    expect(onReorder).toHaveBeenCalledWith([ids[1], ids[0], ...ids.slice(2)])
    expect(useAnnouncer.getState().message)
      .toBe(`${exercises[0]!.name}, Position 2 von ${ids.length}.`)
  })

  it('finishes a drag whose pointerup lands somewhere else', () => {
    // Reordering the list moves the handle's DOM node, and Chrome drops
    // pointer capture when the capturing element is detached -- so from the
    // first swap onwards the events go to whatever is under the cursor. With
    // the listeners on the handle, the mouse drag never committed and left
    // the ghost clone and the dimmed row on screen; touch was fine, because
    // touch pointers get implicit capture. Hence: move and release AWAY from
    // the handle, which is what the browser actually delivers.
    const onReorder = vi.fn()
    useWorkoutUi.getState().setReorder(true)
    const { container } = render(
      <Queue exercises={exercises} liveId={liveId} onReorder={onReorder} />)
    const first = container.querySelectorAll<HTMLButtonElement>('.drag-handle')[0]!
    const rows = container.querySelectorAll('.queue__row')
    // Row 2 sits below row 1; jsdom reports every rect as zero, so the swap
    // itself is not what this asserts -- the commit is.
    fireEvent.pointerDown(first, { pointerId: 1, clientY: 0 })
    fireEvent.pointerMove(window, { pointerId: 1, clientY: 40 })
    fireEvent.pointerUp(document.body, { pointerId: 1, clientY: 40 })

    expect(onReorder).toHaveBeenCalled()
    expect(document.querySelector('.drag-ghost')).toBeNull()
    expect(rows[0]).not.toHaveClass('is-dragging')
  })

  it('ignores the arrow keys outside reorder mode', () => {
    const onReorder = vi.fn()
    const { container } = render(
      <Queue exercises={exercises} liveId={liveId} onReorder={onReorder} />)
    fireEvent.keyDown(container.querySelectorAll('.drag-handle')[0]!,
      { key: 'ArrowDown' })
    expect(onReorder).not.toHaveBeenCalled()
  })

  it('keys drag targets by class and id, and the add row by neither', () => {
    // session_reorder.js keys both drag and the arrow-key path off
    // .queue__row and data-se-id; the add row must carry neither.
    const { container } = render(<Queue exercises={exercises} liveId={liveId} onReorder={noop} />)
    const add = container.querySelector('.queue__add')!
    expect(add).not.toHaveClass('queue__row')
    expect(add.getAttribute('data-se-id')).toBeNull()
  })
})
