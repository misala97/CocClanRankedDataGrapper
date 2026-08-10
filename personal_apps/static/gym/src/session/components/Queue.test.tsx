import { render, screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, describe, expect, it } from 'vitest'
import { Queue } from './Queue'
import { TickStrip } from './TickStrip'
import { useSheets, useWorkoutUi } from '../stores'
import { payload } from '../types.test-d'
import type { LiveExercise } from '../types'

beforeEach(() => {
  useSheets.setState(useSheets.getInitialState(), true)
  useWorkoutUi.setState(useWorkoutUi.getInitialState(), true)
})

const exercises = payload.visible_exercises
const liveId = payload.live_id

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
    render(<Queue exercises={exercises} liveId={liveId} />)
    for (const se of exercises) {
      expect(screen.getByText(se.name)).toBeInTheDocument()
    }
  })

  it('marks the live row for assistive tech, not by colour alone', () => {
    render(<Queue exercises={exercises} liveId={liveId} />)
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
      <Queue exercises={[...exercises, done]} liveId={liveId} />)
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
    const { container } = render(<Queue exercises={exercises} liveId={liveId} />)
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
    render(<Queue exercises={exercises} liveId={liveId} />)
    await user.click(screen.getByText(exercises[0]!.name))
    expect(useSheets.getState().openId).toBe(`sheet-ex-${exercises[0]!.id}`)
  })

  it('offers adding an exercise from the queue, not only from the corner sheet', async () => {
    // The queue is where you are already reading what the workout contains,
    // so it is where "and one more" belongs.
    const user = userEvent.setup()
    render(<Queue exercises={exercises} liveId={liveId} />)
    await user.click(screen.getByText('Übung hinzufügen'))
    expect(useSheets.getState().openId).toBe('sheet-add-exercise')
  })

  it('hides the add row during reorder, and puts the handles in the tab order', () => {
    // During a reorder every row in this list is a thing being moved, and an
    // action is not a position in the sequence.
    const { container, rerender } = render(
      <Queue exercises={exercises} liveId={liveId} />)
    expect(container.querySelectorAll('.drag-handle')[0]).toHaveAttribute('tabindex', '-1')

    useWorkoutUi.getState().setReorder(true)
    rerender(<Queue exercises={exercises} liveId={liveId} />)
    expect(screen.queryByText('Übung hinzufügen')).not.toBeInTheDocument()
    expect(container.querySelectorAll('.drag-handle')[0]).toHaveAttribute('tabindex', '0')
  })

  it('keys drag targets by class and id, and the add row by neither', () => {
    // session_reorder.js keys both drag and the arrow-key path off
    // .queue__row and data-se-id; the add row must carry neither.
    const { container } = render(<Queue exercises={exercises} liveId={liveId} />)
    const add = container.querySelector('.queue__add')!
    expect(add).not.toHaveClass('queue__row')
    expect(add.getAttribute('data-se-id')).toBeNull()
  })
})
