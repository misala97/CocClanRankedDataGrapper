import type { CSSProperties } from 'react'
import type { LiveExercise } from '../types'

interface Props {
  exercises: LiveExercise[]
  liveId: number | null
  liveIndex: number
}

/**
 * The workout as a row of segments, plus the cap that says the same thing in
 * words.
 *
 * The rail is aria-hidden: it encodes position and progress that the cap
 * states directly, and a screen reader given N unlabelled spans learns
 * nothing. The cap carries the skipped count for the same reason -- the rail
 * distinguishes a skipped segment visually and could not say so.
 */
export function Rail({ exercises, liveId, liveIndex }: Props) {
  const skipped = exercises.filter((se) => se.skipped).length

  return (
    <>
      <div className="rail" aria-hidden="true">
        {exercises.map((se) => {
          const done = se.sets.filter((s) => s.completed).length
          const total = se.sets.length

          if (se.id === liveId) {
            // --p is the fill as a 0-1 scale factor, not a width.
            const style = { '--p': total ? (done / total).toFixed(4) : '0' } as CSSProperties
            return (
              <span className="rail__seg is-now" data-se-id={se.id} key={se.id}>
                <span className="rail__fill" style={style} />
              </span>
            )
          }

          const className = total > 0 && done === total
            ? 'rail__seg is-done'
            : se.skipped ? 'rail__seg is-skipped' : 'rail__seg'
          return <span className={className} data-se-id={se.id} key={se.id} />
        })}
      </div>
      <div className="rail__cap">
        <span className="label">
          {exercises.length === 0
            ? 'Noch keine Übungen'
            : `Übung ${liveIndex} von ${exercises.length}${skipped ? `, ${skipped} übersprungen` : ''}`}
        </span>
      </div>
    </>
  )
}
