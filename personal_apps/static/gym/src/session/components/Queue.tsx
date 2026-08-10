import type { LiveExercise } from '../types'
import { useSheets, useWorkoutUi } from '../stores'
import { Icon } from '../../components/Icon'

interface Props {
  exercises: LiveExercise[]
  liveId: number | null
}

/** What the trailing column says, which differs by what the row is. */
function loadSummary(se: LiveExercise, isLive: boolean): string {
  const done = se.sets.filter((s) => s.completed).length
  const total = se.sets.length
  if (se.skipped) return 'Übersprungen'
  if (isLive) return `${done}/${total}`
  if (total > 0 && done === total) return `${done}/${total}`
  if (total > 0) {
    return `${total} × ${se.sets[0]!.weight.toFixed(1).replace('.', ',')}`
  }
  return '—'
}

/**
 * The whole workout in order, INCLUDING the exercise you are on.
 *
 * Filtering the live one out left a hole in the sequence -- the list ran
 * 1, 3, 4 with nothing saying where you were, so it stopped being a map of the
 * session and became a list of leftovers. The live row duplicating the panel's
 * name is the point: the panel above is the workspace, this is the position.
 */
export function Queue({ exercises, liveId }: Props) {
  const openSheet = useSheets((s) => s.open)
  const reordering = useWorkoutUi((s) => s.reorderUnlocked)

  return (
    <div className="queue" id="queue">
      <h2 className="sr-only">Übungen</h2>

      {exercises.map((se) => {
        const done = se.sets.filter((s) => s.completed).length
        const total = se.sets.length
        const isLive = se.id === liveId
        const isDone = total > 0 && done === total

        const className = [
          'row queue__row',
          isLive ? 'is-now' : '',
          isDone ? 'is-done' : '',
          se.skipped ? 'is-skipped' : '',
        ].filter(Boolean).join(' ')

        return (
          <div className={className} data-se-id={se.id} key={se.id}>
            {/* A real button, not an aria-hidden span. Dragging is one way to
                move a row; focusing this and pressing ArrowUp/ArrowDown is the
                other, and without that second one reordering was impossible by
                keyboard and invisible to a screen reader. Only in the tab
                order while the mode is on, because outside it this does
                nothing and four inert stops between rows is worse than none. */}
            <button type="button" className="drag-handle"
              tabIndex={reordering ? 0 : -1}
              aria-label={`${se.name} verschieben`}>⠿</button>

            {/* Never colour alone: a tick for finished, a filled dot for the
                one you are on, the slot number for one still ahead. */}
            <span className="row__lead queue__lead">
              {isLive
                ? <span className="queue__now" aria-hidden="true" />
                : isDone
                  ? <span className="queue__mark"><Icon name="check" /></span>
                  : se.position}
            </span>

            <button type="button" className="row__main"
              {...(isLive ? { 'aria-current': 'step' as const } : {})}
              onClick={() => openSheet(`sheet-ex-${se.id}`)}>
              <span className="row__name">{se.name}</span>
            </button>

            <span className="row__trail queue__load">{loadSummary(se, isLive)}</span>
          </div>
        )
      })}

      {/* Adding an exercise lived only in the sheet in the top corner, which is
          the wrong end of the screen and the wrong place to look: the queue is
          where you are already reading what the workout contains.

          Not a .queue__row and carrying no data-se-id -- session_reorder.js
          keys both drag and the arrow-key path off those, and an action is not
          a position in the sequence. Hidden during a reorder for the same
          reason: every row in this list is then a thing being moved. */}
      {!reordering && (
        <div className="row queue__add">
          <span className="row__lead queue__lead" aria-hidden="true">
            <Icon name="plus" />
          </span>
          <button type="button" className="row__main"
            onClick={() => openSheet('sheet-add-exercise')}>
            <span className="row__name">Übung hinzufügen</span>
          </button>
        </div>
      )}
    </div>
  )
}
