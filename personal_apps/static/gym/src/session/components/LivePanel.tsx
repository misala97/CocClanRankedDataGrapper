import { useEffect, useState } from 'react'
import type { SessionDetailPayload } from '../types'
import { useSheets } from '../stores'
import { useRestTick } from '../useRestTick'
import { Icon } from '../../components/Icon'
import { SetRow } from './SetRow'
import { Stepper } from './Stepper'

interface Props {
  payload: SessionDetailPayload
  /** Confirms the pending set, or appends one when nothing is pending --
   *  gym_add_set creates it already completed, which is what "Satz geschafft"
   *  means everywhere else on this screen. */
  onConfirm(weight: number, reps: number): void
  onToggleSet(setId: number, completed: boolean): void
  onRestOver(): void
  busySetId?: number | null
}

/**
 * The one lifted panel for the exercise you are on.
 *
 * Three shapes, one workspace. An exercise added mid-workout arrives with no
 * sets at all and is then picked as live and never completes, blocking
 * everything after it -- so an empty exercise gets the same two steppers and
 * the same confirm button; only the endpoint differs. The steppers and the
 * button render in every state including "everything is logged", because the
 * state needed the control, not new machinery.
 */
export function LivePanel({
  payload, onConfirm, onToggleSet, onRestOver, busySetId = null,
}: Props) {
  const openSheet = useSheets((s) => s.open)
  const live = payload.visible_exercises.find((se) => se.id === payload.live_id) ?? null
  const nextSet = live?.sets.find((s) => !s.completed) ?? null

  // Appending after everything is logged starts from the set you just did, not
  // from the session's opening suggestion: the reason you are adding one is
  // that the last one went well enough to want another.
  const lastDone = live && live.sets.length > 0 ? live.sets[live.sets.length - 1]! : null
  const suggestion = live ? payload.suggestions[String(live.id)] ?? null : null
  const seedWeight = nextSet?.weight ?? lastDone?.weight
    ?? suggestion?.weight ?? payload.default_plan_weight
  const seedReps = nextSet?.reps ?? lastDone?.reps
    ?? suggestion?.reps ?? payload.default_plan_reps

  const [weight, setWeight] = useState(seedWeight)
  const [reps, setReps] = useState(seedReps)

  // The server is authoritative about what comes next; re-seed whenever it
  // says the pending set changed.
  useEffect(() => {
    setWeight(seedWeight)
    setReps(seedReps)
  }, [seedWeight, seedReps])

  const rest = useRestTick(
    payload.resting ? payload.session.rest_ends_at : null,
    payload.rest_total_seconds,
    { onOver: onRestOver })

  if (live === null) {
    return (
      /* A workout started without a template has no exercises at all, and the
         only route to one was the sheet in the top corner. The panel is the
         one place on this screen guaranteed to be looked at, so the first
         action belongs in it -- as the same solid control every other state
         puts in this slot, not as a link in the copy.

         Not .live__kick: that carries the hot NOW dot, and nothing is
         happening now. The panel is lifted because it holds the only action. */
      <section className="live">
        <h2 className="live__name">Noch keine Übung</h2>
        <p className="live__empty">
          Füge die erste Übung hinzu — oder starte das nächste Mal aus einer Vorlage.
        </p>
        <button type="button" className="go"
          onClick={() => openSheet('sheet-add-exercise')}>
          <Icon name="plus" />
          Übung hinzufügen
        </button>
      </section>
    )
  }

  const stall = payload.stagnation_counts[String(live.id)]
  const ready = payload.ready_for_more
  const perSide = live.is_unilateral ? ' je Seite' : ''
  const records = live.sets.filter(
    (s) => s.completed && payload.record_set_ids.includes(s.id))

  return (
    <section className="live" data-se-id={live.id}>
      <div className="live__head">
        <span className="live__kick">Jetzt</span>
        <button type="button" className="live__more"
          aria-label={`${live.name} — Optionen`}
          onClick={() => openSheet(`sheet-ex-${live.id}`)}>
          <Icon name="more" />
        </button>
      </div>
      <h2 className="live__name">{live.name}</h2>

      {/* Above the workspace, not below it. This is advice about the numbers
          you are about to set, and it used to render under the 64px confirm
          button -- after the control you would act on it with, and off-screen
          on a phone by the time you had scrolled to the queue. */}
      {stall !== undefined && (
        <p className="live__stall">
          <span className="live__stall-lbl">Stagniert</span>
          {` ${stall} Workouts ohne neuen e1RM-PR — mehr Gewicht oder Wdh. versuchen.`}
        </p>
      )}

      {/* Same slot and the same reason. The two never contradict each other --
          stagnation counts sessions without a PR, this reads the last
          session's reps -- but if both fire, both are worth saying. */}
      {ready !== null && (
        <p className="live__ready">
          <span className="live__ready-lbl">Bereit</span>
          {` ${ready.is_latest ? 'Letztes Mal' : 'Zuletzt in diesem Slot'} ${ready.sets} Sätze auf ${ready.weight.toFixed(1).replace('.', ',')} kg${perSide} mit ${payload.min_full_reps}+ Wdh.`}
        </p>
      )}

      {live.sets.length > 0 && (
        <div className="sets">
          {live.sets.map((s, i) => (
            <SetRow key={s.id} set={s} ordinal={i + 1}
              isRecord={payload.record_set_ids.includes(s.id)}
              isNext={nextSet !== null && s.id === nextSet.id}
              isUnilateral={live.is_unilateral}
              busy={busySetId === s.id}
              onToggle={onToggleSet} />
          ))}
        </div>
      )}

      {records.length > 0 && (
        <p className="live__record">
          <span className="live__record-lbl">Rekord</span>
          {/* "Bestwert", not "schwerer": is_new_best counts an e1RM record too,
              so a set can land here at a lighter weight and more reps. */}
          {records.length === 1
            ? ` Satz ${live.sets.indexOf(records[0]!) + 1} ist ein neuer Bestwert in dieser Übung.`
            : ` ${records.length} Sätze über deinem bisherigen Bestwert.`}
        </p>
      )}

      {live.sets.length === 0 && (
        <p className="live__empty">
          {`Noch keine Sätze. Der erste wird angelegt, sobald du ihn bestätigst${suggestion ? ` — zuletzt ${suggestion.weight.toFixed(1).replace('.', ',')} kg × ${suggestion.reps}` : ''}.`}
        </p>
      )}
      {live.sets.length > 0 && nextSet === null && (
        <p className="live__alldone">
          Alle Sätze erledigt. Unten beenden — oder hier noch einen anhängen.
        </p>
      )}

      <div className="pair">
        <Stepper label={`kg${perSide}`} value={weight} step={payload.live_increment}
          decimals={1} ariaLabel="Gewicht eingeben" onChange={setWeight} />
        <Stepper label="Wdh." value={reps} step={1} decimals={0}
          ariaLabel="Wiederholungen eingeben" onChange={setReps} />
      </div>

      {/* The rest does not take this slot -- it runs THROUGH it. The button is
          present and pressable for the whole countdown; the band charges
          underneath. aria-hidden on the clock keeps the accessible name stable
          at "Satz geschafft": a name that rewrote itself every second would be
          worse than no countdown, and the announcement lives in the live
          region, which speaks twice per rest rather than ninety times. */}
      <button type="button" className={rest.running ? 'go is-resting' : 'go'}
        id="set-confirm" onClick={() => onConfirm(weight, reps)}>
        <span className="go__lbl">
          <Icon name="check" />
          Satz geschafft
        </span>
        {rest.running && (
          <>
            <span className="go__clock" aria-hidden="true">
              {`${Math.floor(rest.remaining / 60)}:${String(rest.remaining % 60).padStart(2, '0')}`}
            </span>
            <span className="go__band" aria-hidden="true">
              <span className="go__charge"
                style={{ transform: `scaleX(${rest.progress})` }} />
            </span>
          </>
        )}
      </button>
    </section>
  )
}
