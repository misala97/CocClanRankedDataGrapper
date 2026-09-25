import { useEffect, useMemo, useState } from 'react'
import type { ExerciseDetailPayload, SessionRow, StairCol } from '../types'
import { getJson } from '../api'
import { Icon } from '../components/Icon'
import { ExerciseHeader } from '../components/ExerciseHeader'
import { GoalPanel } from '../components/GoalPanel'
import { WeightTable } from '../components/WeightTable'
import { MaxSection } from '../components/MaxSection'
import { SessionLog } from '../components/SessionLog'
import { ExerciseAbout, ExerciseArt, ExerciseVariants } from '../components/ExerciseAbout'
import { ExerciseActions } from '../components/ExerciseActions'
import { RoutineSheet } from '../components/RoutineSheet'
import { EditSheet } from '../components/EditSheet'

/** "Deine Pause" links an exception here: the page opens on the settings. */
const SETTINGS_HASH = '#einstellungen'

interface Props {
  payload: ExerciseDetailPayload
}

/**
 * Exercise detail (D9, M2 "A mit 1"): what to lift next and the workout it
 * builds on, the two ways on (a workout, a routine), how far each weight
 * went, the estimated max as the Rekordtreppe, every workout, the exercise
 * itself, and last the lifter's own settings. Never done (M6 screen 2): the
 * exercise first, its ways on, what will fill the page, its other variants.
 * Nothing here re-derives a number -- every value comes from
 * routes._exercise_detail_payload. The exercise itself is the one list's:
 * nobody renames or deletes it here.
 *
 * Everything is the whole exercise. The "Als N. Übung" pills lens the stair
 * alone, so a pill tap swaps it in place and only rewrites the address
 * (replaceState: back leaves the page, it does not walk the pills).
 */
export function ExerciseDetailPage({ payload }: Props) {
  // State, not the prop: the settings sheet hands back the saved exercise.
  const [p, setP] = useState(payload)
  const [selected, setSelected] = useState(payload.selected_position)
  useEffect(() => {
    setP(payload)
    setSelected(payload.selected_position)
  }, [payload])
  const [editing, setEditing] = useState(false)
  const [routing, setRouting] = useState(false)
  const id = p.exercise.id

  // Arrived from an exception under "Deine Pause": open on the settings, and
  // drop the hash so a reload or the back button lands on the page itself.
  useEffect(() => {
    if (window.location.hash !== SETTINGS_HASH) return
    setEditing(true)
    history.replaceState(history.state, '', window.location.pathname + window.location.search)
  }, [])

  const rows = useMemo(() => {
    const byKey = new Map<string, SessionRow>()
    for (const row of p.table) byKey.set(`${row.session_id}-${row.position}`, row)
    return byKey
  }, [p.table])
  const rowOf = (col: StairCol) => rows.get(`${col.session_id}-${col.position}`)

  const select = (position: number | null) => {
    setSelected(position)
    history.replaceState(history.state, '',
      position === null ? `/gym/exercises/${id}` : `/gym/exercises/${id}?position=${position}`)
  }

  // Off today's list (a retired row) nothing offers the exercise, so
  // neither does its page.
  const actions = p.on_list && (
    <ExerciseActions exerciseId={id} running={p.running}
      onRoutine={p.routines.length > 0 ? () => setRouting(true) : null} />
  )

  return (
    <>
      <div className="exdetail">
        <ExerciseHeader exercise={p.exercise} chipClass={p.chip_class} chipLabel={p.chip_label} />

        {p.table.length > 0 ? (
          <>
            {/* Two wrappers, so the desktop grid has two stable children to
                place. They are inert on phones -- plain blocks whose children
                still carry their own gutters -- and become the analysis column
                and the log column at 900px. */}
            <div className="exdetail__main">
              {p.goal !== null && <GoalPanel goal={p.goal} />}
              {actions}
              {p.weights.length > 0 && <WeightTable weights={p.weights} />}
              {/* No judged set, or only 0 kg ones: no estimate to speak of
                  (G-038) and no stair -- the section says so instead. */}
              <MaxSection exerciseId={id} record={p.pr_e1rm}
                weighted={p.table.some((row) => row.sets.some((set) => set.weight > 0))}
                sinceRecord={p.sessions_since_pr} stalled={p.state === 'stagniert'} trend={p.trend}
                stairs={p.stairs} pills={p.position_pills} selected={selected} onSelect={select}
                rowOf={rowOf} />
            </div>

            <div className="exdetail__log">
              <SessionLog table={p.table} isUnilateral={p.exercise.is_unilateral} />
              <ExerciseAbout exercise={p.exercise} about={p.about} />
            </div>
          </>
        ) : (
          // The drawing leads: with no history it is the one thing that
          // says what the exercise is.
          <div className="exnew">
            <section className="exnew__about" aria-label="Die Übung">
              <ExerciseArt exercise={p.exercise} about={p.about} />
            </section>
            {actions}
            {/* Says what fills the page, not just that it is empty -- and
                a lift logged today is not "no set": the page reads finished
                workouts. */}
            <p className="exnew__none">
              {p.running !== null && p.running.logged > 0
                ? 'Heute im laufenden Workout. Sobald es beendet ist, stehen hier '
                : 'Noch kein Satz. Sobald du sie loggst, stehen hier '}
              dein nächstes Ziel, deine Rekorde und jedes Workout.
            </p>
            <ExerciseVariants about={p.about} open />
          </div>
        )}

        <section className="sec sec--maint" aria-label="Deine Einstellungen">
          <button type="button" className="finished__correct"
            onClick={() => setEditing(true)}>
            <Icon name="edit" />
            Pause und Schritt einstellen
          </button>
        </section>
      </div>

      <EditSheet exercise={p.exercise} open={editing} onClose={() => setEditing(false)}
        onSaved={(exercise) => {
          setP((current) => ({ ...current, exercise }))
          // A new step moves the target's next weight: the rule sentence
          // must not say the old one. The rest of the page is unchanged.
          getJson<ExerciseDetailPayload>(`/gym/exercises/${id}/detail.json`)
            .then((fresh) => setP((current) => ({ ...current, goal: fresh.goal, exercise: fresh.exercise })))
            .catch(() => {})
        }} />
      {actions && (
        <RoutineSheet exercise={p.exercise} routines={p.routines} open={routing}
          onClose={() => setRouting(false)}
          onAdded={(routines) => setP((current) => ({ ...current, routines }))} />
      )}
    </>
  )
}
