import { fireEvent, render, screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { Queue } from './Queue'
import { TickStrip } from './TickStrip'
import { useAnnouncer, useSheets, useWorkoutUi } from '../stores'
import { payload } from '../types.test-d'
import type { LiveExercise } from '../types'

beforeEach(() => {
  useSheets.setState(useSheets.getInitialState(), true)
  useWorkoutUi.setState(useWorkoutUi.getInitialState(), true)
  useAnnouncer.setState(useAnnouncer.getInitialState(), true)
})

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

  it('marks the live row for assistive tech, not by colour alone', () => {
    render(<Queue exercises={exercises} liveId={liveId} onReorder={noop} />)
    const live = exercises.find((se) => se.id === liveId)!
    expect(screen.getByText(live.name).closest('button'))
      .toHaveAttribute('aria-current', 'step')
  })

  it('leads with a tick when finished, a dot when live, the slot number otherwise', () => {
    const done: LiveExercise = {
      ...exercises[0]!, id: 90, name: 'Fertig', position: 4, skipped: false,
      sets: [{ id: 1, weight: 50, reps: 5, completed: true, base_weight: null }],
    }
    const { container } = render(
      <Queue exercises={[...exercises, done]} liveId={liveId} onReorder={noop} />)
    const row = container.querySelector('[data-se-id="90"]') as HTMLElement
    // A finished exercise leads with the tick, not with its slot number.
    expect(row.querySelector('.queue__mark')).toBeInTheDocument()
    expect(within(row).queryByText('4')).toBeNull()

    // The live one leads with the dot instead.
    const live = container.querySelector(`[data-se-id="${liveId}"]`)!
    expect(live.querySelector('.queue__now')).toBeInTheDocument()
    expect(live.querySelector('.queue__mark')).toBeNull()

    // One still ahead leads with its position.
    const ahead = exercises.find((se) => se.id !== liveId)!
    const aheadRow = container.querySelector(`[data-se-id="${ahead.id}"]`) as HTMLElement
    expect(within(aheadRow).getByText(String(ahead.position))).toBeInTheDocument()
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
