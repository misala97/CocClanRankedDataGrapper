import { useState } from 'react'
import type { RunningWorkout } from '../types'
import { postNavigate } from '../api'
import { Icon } from './Icon'

/** The running workout's button: its name, or what it is when it has none. */
export function addTo(running: RunningWorkout): string {
  return running.name !== null ? `Zu „${running.name}“ hinzufügen` : 'Zum laufenden Workout hinzufügen'
}

/**
 * The two ways on from an exercise's page (M6 screen 2, G-041): into a
 * workout -- a new one with it, or the running one at its end -- and into a
 * routine. The workout's way is a real form post: the server answers with
 * the workout, and that is where the lifter lands.
 */
export function ExerciseActions({ exerciseId, running, onRoutine }: {
  exerciseId: number
  running: RunningWorkout | null
  /** Opens the routine sheet; null with no routine to add to. */
  onRoutine: (() => void) | null
}) {
  const [armed, setArmed] = useState(false)
  const [busy, setBusy] = useState(false)
  const already = running?.count ?? 0

  const go = () => {
    if (busy) return
    // Already in the running workout: the first tap asks, the second adds,
    // as in the add sheet -- twice is legitimate, twice by accident is the
    // easy mistake.
    if (already > 0 && !armed) {
      setArmed(true)
      return
    }
    setBusy(true)
    const fields = { exercise_id: String(exerciseId) }
    if (running === null) postNavigate('/gym/start', fields)
    // Finished since this page was read: back here, told so, not to its
    // debrief without the exercise.
    else postNavigate(`/gym/session/${running.session_id}/exercises/add`, { ...fields, back: 'exercise' })
  }

  let note: string | null = null
  if (running !== null) {
    if (armed) note = 'Nochmal hinzufügen?'
    else if (already > 0) note = already === 1 ? 'Ist schon drin.' : `Ist schon ${already}× drin.`
    else note = 'Kommt ans Ende des laufenden Workouts.'
  }

  return (
    <div className="exnew__acts">
      {/* A tap is a page change on its way: both buttons wait for it. */}
      <button type="button" className="btn btn--live" disabled={busy} onClick={go}
        aria-describedby={note !== null ? 'exnew-note' : undefined}>
        <Icon name="plus" />
        {running === null ? 'Workout damit beginnen' : addTo(running)}
      </button>
      {note !== null && (
        <p className={armed ? 'exnew__note is-armed' : 'exnew__note'} id="exnew-note"
          aria-live="polite">{note}</p>
      )}
      {onRoutine !== null && (
        <button type="button" className="btn btn--ghost" disabled={busy}
          onClick={onRoutine}>Zur Routine …</button>
      )}
    </div>
  )
}
