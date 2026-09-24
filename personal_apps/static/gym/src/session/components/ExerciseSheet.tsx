import { useState } from 'react'
import type { CatalogueExercise, LiveExercise, RoutinePlan, Suggestion } from '../types'
import { useUndo } from '../../undo'
import { useSaveState } from '../stores'
import {
  MAX_NOTE_CHARS, MAX_REPS, MAX_WEIGHT_KG, parseSetInput, setInputProblem,
} from '../../setInput'
import { Drawing, movementOf } from './Picture'
import { RoutinePlanGroup } from './RoutinePlanGroup'
import { Sheet } from './Sheet'
import { Icon } from '../../components/Icon'
import { Choice } from '../../settings/Choice'
import { REST_MAX, REST_MIN, REST_NUDGE, clock, kg, restChoices } from '../../settings/values'

export interface ExerciseSheetActions {
  /** "Pause heute". The setting's own value is sent as itself; the server
   *  stores it as nothing, so the row follows the setting again. */
  onRestChange(seconds: number): void
  /** One level down: "Deine Einstellungen", which hold for every workout. */
  onOpenSettings(): void
  onMetaSave(meta: { pain: boolean; notes: string }): void
  onSetUpdate(setId: number, weight: number, reps: number): void
  /** Settles once the server has answered; rejects when the delete failed. */
  onSetDelete(setId: number, keepalive: boolean): Promise<unknown>
  onAddSet(weight: number, reps: number): void
  onToggleSkip(): void
  onReplace(exerciseId: number): void
  onRemove(): void
  onShowProgress(): void
  /** Pull this exercise in front of the live one, so it is up next. */
  onMakeLive(): void
  /** The routine's plan for the exercise, once the steppers settle --
   *  `leaving` when the page is going away and the write must outlive it. */
  onRoutinePlanChange(plan: RoutinePlan, leaving: boolean): void
}

interface Props extends ExerciseSheetActions {
  exercise: LiveExercise
  /** The whole exercise list, which a replacement comes from. */
  catalogue: CatalogueExercise[]
  /** What the add-a-set row pre-fills with when the exercise has no set yet.
   *  Null for an exercise with no history to seed from. */
  suggestion: Suggestion | null
  /** Whether "Jetzt machen" is offered: not for the live exercise itself,
   *  a finished or skipped one, or a follower whose order is the leader's. */
  canMakeLive: boolean
  /** The workout's routine and what it keeps for this exercise; null when
   *  the routine does not hold it, or the workout has no routine of yours. */
  routine: { name: string; plan: RoutinePlan } | null
}

/**
 * One sheet per exercise: its sets, its rest time, and the three things you
 * can do to it. This replaced a menu on every row and an expanded panel per
 * exercise -- the row itself is the affordance.
 *
 * The groups are not cosmetic. "Pause heute" belongs to this workout, the
 * lifter's settings outlive it, and a twinge or a note belongs to today.
 * Side by side, two rest fields read as one; so today's rest is here, with
 * the setting's value marked in its row, and the settings are one level
 * down, in a sheet that says they hold for every workout.
 */
export function ExerciseSheet({
  exercise, catalogue, suggestion, canMakeLive, routine,
  onRestChange, onOpenSettings, onMetaSave, onSetUpdate, onSetDelete,
  onAddSet, onToggleSkip, onReplace, onRemove, onShowProgress,
  onMakeLive, onRoutinePlanChange,
}: Props) {
  const [pain, setPain] = useState(exercise.pain)
  const [notes, setNotes] = useState(exercise.notes ?? '')
  // The island locks the same key for the confirm button's add -- one append
  // per exercise in flight, whichever control asked for it.
  const adding = useSaveState((s) => s.locked[`add-${exercise.id}`] === true)
  const offerUndo = useUndo((s) => s.offer)
  // Sets hidden while their delete waits out the undo window. Ids, not
  // indices: the payload swap after the commit removes them for real.
  const [hiddenSetIds, setHiddenSetIds] = useState<number[]>([])

  const deleteSet = (setId: number, ordinal: number) => {
    setHiddenSetIds((ids) => [...ids, setId])
    offerUndo({
      label: `Satz ${ordinal} gelöscht.`,
      undo: () => setHiddenSetIds((ids) => ids.filter((id) => id !== setId)),
      // keepalive rides through to the fetch, so a delete flushed by leaving
      // the page leaves with it (G-062). A delete that fails brings its row
      // back: the payload rolls back to the set, but this list kept hiding
      // it, so a lost delete looked like a done one (G-147).
      commit: (keepalive) => {
        onSetDelete(setId, keepalive)
          .catch(() => setHiddenSetIds((ids) => ids.filter((id) => id !== setId)))
      },
    })
  }

  // The same muscle group first: a replacement is usually "the machine is
  // taken, same muscles another way". That can be empty -- an exercise with
  // no group, or one the list has no neighbour for -- and then the whole list
  // stands in, since nothing is created here any more.
  const others = catalogue.filter((e) => e.id !== exercise.exercise_id)
  const sameGroup = others.filter((e) => e.muscle_group === exercise.muscle_group)
  const swaps = sameGroup.length > 0 ? sameGroup : others
  const [replaceWith, setReplaceWith] = useState(swaps[0]?.id ?? 0)

  return (
    <Sheet id={`sheet-ex-${exercise.id}`} title={exercise.name}>
      {/* The drawing, whole (round 4): the live card's tile opens this sheet.
          Nothing in its place while there is none -- a plate with a dumbbell
          this size would only push the settings down. */}
      {exercise.picture !== null && (
        <div className="pic-full">
          <Drawing src={exercise.picture} alt={`Zeichnung: ${movementOf(exercise.name)}`} />
        </div>
      )}
      {/* Today's rest, from the one in force: the setting's value is marked
          ("deine" or "Liste") and one tap away, and every tap saves. */}
      <div className="sheet__group">
        <div className="sheet__group-head">
          <span className="label">Pause heute</span>
        </div>
        <Choice label="Pause heute" values={restChoices(exercise.rest_setting, 2)}
          on={exercise.rest_seconds ?? exercise.rest_setting} mark={exercise.rest_setting}
          markWord={exercise.rest_setting_mine ? 'deine' : 'Liste'} format={clock}
          onPick={(seconds) => onRestChange(seconds)}
          nudge={{
            step: REST_NUDGE, min: REST_MIN, max: REST_MAX,
            label: 'nach jedem Satz', keyNoun: '15 Sekunden',
          }} />
        <p className="sheet__note">Eine andere Zeit gilt nur für dieses Workout.</p>
        <button type="button" className="sheet-row" onClick={onOpenSettings}>
          <span className="sheet-row__lead"><Icon name="edit" /></span>
          <span className="sheet-row__main">
            <span className="sheet-row__name">Deine Einstellungen</span>
            <span className="sheet-row__meta">
              {(exercise.rest_setting === null ? '' : `Pause ${clock(exercise.rest_setting)} · `)
                + `Schritt ${kg(exercise.increment)} kg — gelten immer`}
            </span>
          </span>
          <span className="sheet-row__chev"><Icon name="forward" /></span>
        </button>
      </div>

      {/* A third lifetime, between the two: the routine's, from the next
          workout on (D2 P1). */}
      {routine !== null && (
        <RoutinePlanGroup routineName={routine.name} plan={routine.plan}
          onSave={onRoutinePlanChange} />
      )}

      {/* The opposite lifetime to the settings above: a twinge and a note
          belong to this workout, not to the machine.

          Both save by themselves, like the rest above. The flag used to
          wait for a Speichern button beside the note, so ticking it and
          closing the sheet kept the tick on screen and saved nothing. */}
      <div className="sheet__group">
        <div className="sheet__group-head">
          <span className="label">Heute</span>
        </div>
        <label className="sheet__row">
          <input type="checkbox" className="check" checked={pain}
            onChange={(e) => {
              setPain(e.target.checked)
              onMetaSave({ pain: e.target.checked, notes })
            }} />
          <span className="check__text">Schmerz / Zwicken</span>
        </label>
        <div className="field">
          <label className="label" htmlFor={`ex-notes-${exercise.id}`}>Notiz</label>
          <input type="text" id={`ex-notes-${exercise.id}`} className="input"
            placeholder="—" value={notes} maxLength={MAX_NOTE_CHARS}
            onChange={(e) => setNotes(e.target.value)}
            onKeyDown={(e) => { if (e.key === 'Enter') e.currentTarget.blur() }}
            onBlur={() => {
              if (notes !== (exercise.notes ?? '')) onMetaSave({ pain, notes })
            }} />
        </div>
      </div>

      <div className="sheet__group">
        <div className="sheet__group-head">
          <span className="label">Sätze</span>
        </div>
        {exercise.sets.filter((s) => !hiddenSetIds.includes(s.id)).map((s, i) => (
          // Keyed on the stored numbers, not on the id alone: an editor holds
          // its fields in local state, so a set rewritten while the sheet is
          // open -- by the partner's phone in a shared workout, or by the
          // deload toggle -- would otherwise keep showing the old value and
          // post it back on the next save. The key only moves when the SERVER
          // value moves; typing in the field does not touch it.
          <SetEditor set={s} ordinal={i + 1} key={`${s.id}-${s.weight}-${s.reps}`}
            onSave={onSetUpdate} onDelete={deleteSet} />
        ))}
        {/* Seeded from the last set, not only from the session's opening
            suggestion: appending is usually one more of what you just did.
            Keyed on that seed so a new last set re-seeds the row. */}
        <AddSetRow key={lastSetKey(exercise)} seed={addSeed(exercise, suggestion)}
          busy={adding} onAdd={onAddSet} />
      </div>

      <div className="sheet__group">
        {canMakeLive && (
          <button type="button" className="sheet-row" onClick={onMakeLive}>
            <span className="sheet-row__lead"><Icon name="check" /></span>
            <span className="sheet-row__main">
              <span className="sheet-row__name">Jetzt machen</span>
              <span className="sheet-row__meta">
                Kommt vor die aktuelle Übung — etwa wenn gerade dieses Gerät frei ist.
              </span>
            </span>
          </button>
        )}
        <button type="button" className="sheet-row" onClick={onShowProgress}>
          <span className="sheet-row__lead"><Icon name="chart" /></span>
          <span className="sheet-row__main">
            <span className="sheet-row__name">Fortschritt anzeigen</span>
            <span className="sheet-row__meta">Verlauf und Rekorde dieser Übung.</span>
          </span>
        </button>
        <button type="button" className="sheet-row" onClick={onToggleSkip}>
          <span className="sheet-row__lead"><Icon name="skip" /></span>
          <span className="sheet-row__main">
            <span className="sheet-row__name">
              {exercise.skipped ? 'Nicht mehr überspringen' : 'Übung überspringen'}
            </span>
            <span className="sheet-row__meta">
              {/* What the server does, which the old "Sätze bleiben" was not:
                  a skip drops every set still open, keeps the ones already
                  logged, and coming back plans the exercise afresh. */}
              {exercise.skipped
                ? 'Zählt wieder — offene Sätze werden neu geplant.'
                : 'Offene Sätze entfallen, erledigte bleiben.'}
            </span>
          </span>
        </button>

        {swaps.length > 0 && (
          <details>
            <summary className="sheet-row">
              <span className="sheet-row__lead"><Icon name="swap" /></span>
              <span className="sheet-row__main">
                <span className="sheet-row__name">Übung ersetzen</span>
                <span className="sheet-row__meta">Nur für heute — die Routine bleibt.</span>
              </span>
            </summary>

            <div className="sheet__pane">
              <div className="field grow">
                <label className="label" htmlFor={`replace-select-${exercise.id}`}>Ersatzübung</label>
                <select id={`replace-select-${exercise.id}`} className="select"
                  value={replaceWith}
                  onChange={(e) => setReplaceWith(Number(e.target.value))}>
                  {swaps.map((e) => <option value={e.id} key={e.id}>{e.name}</option>)}
                </select>
              </div>
              <button type="button" className="btn btn--live btn--sm"
                onClick={() => onReplace(replaceWith)}>Ersetzen</button>
            </div>
          </details>
        )}

        {/* A shared exercise is the leader's structure: a follower's remove
            was brought back by the leader's next change, so it is not offered
            (and the route refuses it). Skipping above is theirs, and sticks.
            An exercise they added themselves keeps its remove. */}
        {exercise.mirrored ? (
          <p className="sheet__note">
            Gehört zum gemeinsamen Plan — überspringen oder ersetzen geht, entfernen nicht.
          </p>
        ) : (
          <button type="button" className="sheet-row sheet-row--danger"
            onClick={() => offerUndo({
              label: `${exercise.name} wird entfernt.`,
              undo: () => {},
              commit: () => onRemove(),
            })}>
            <span className="sheet-row__lead"><Icon name="trash" /></span>
            <span className="sheet-row__main">
              <span className="sheet-row__name">Übung entfernen</span>
              <span className="sheet-row__meta">Aus diesem Workout, samt Sätzen.</span>
            </span>
          </button>
        )}
      </div>
    </Sheet>
  )
}

function SetEditor({ set, ordinal, onSave, onDelete }: {
  set: LiveExercise['sets'][number]
  ordinal: number
  onSave(setId: number, weight: number, reps: number): void
  onDelete(setId: number, ordinal: number): void
}) {
  // A blank planned set starts with empty fields, not the text "null".
  const [weight, setWeight] = useState(set.weight === null ? '' : String(set.weight))
  const [reps, setReps] = useState(set.reps === null ? '' : String(set.reps))
  // A cleared field used to save as 0 -- Number('') is 0 -- and overwrite the
  // real numbers. Invalid or unchanged, there is nothing to save.
  const parsed = parseSetInput(weight, reps)
  const changed = parsed !== null
    && (parsed.weight !== set.weight || parsed.reps !== set.reps)
  const problem = setInputProblem(weight, reps)

  return (
    <>
    <div className="sset">
      <span className="label">{ordinal}</span>
      <input type="number" step="0.5" min="0" max={MAX_WEIGHT_KG} className="input input--num"
        aria-label={`Satz ${ordinal}, Gewicht in kg`} value={weight}
        aria-invalid={problem?.startsWith('Gewicht') || undefined}
        onChange={(e) => setWeight(e.target.value)} />
      <span className="sset__unit">kg</span>
      <span className="sset__unit">×</span>
      <input type="number" min="1" max={MAX_REPS} className="input input--num"
        aria-label={`Satz ${ordinal}, Wiederholungen`} value={reps}
        aria-invalid={problem?.startsWith('Wiederholungen') || undefined}
        onChange={(e) => setReps(e.target.value)} />
      <span className="sset__acts">
        <button type="button" className="icon-btn"
          aria-label={`Satz ${ordinal} speichern`}
          disabled={!changed}
          onClick={() => { if (parsed !== null) onSave(set.id, parsed.weight, parsed.reps) }}>
          <Icon name="save" />
        </button>
        {/* The multiplication-sign delete stays a typographic mark on
            purpose -- see Icon.tsx's header. */}
        <button type="button" className="icon-btn"
          aria-label={`Satz ${ordinal} löschen`}
          onClick={() => onDelete(set.id, ordinal)}>✕</button>
      </span>
    </div>
    <SetInputHint problem={problem} />
    </>
  )
}

/** Why the row's button is off: a disabled save with no reason looked like a
 *  broken button (walkthrough G-070). */
function SetInputHint({ problem }: { problem: string | null }) {
  return (
    <p className="sset__hint" aria-live="polite">{problem}</p>
  )
}

/** What the add row starts from: the last set of this exercise that has its
 *  numbers (a blank plan has none yet), else the session's suggestion, else
 *  nothing. */
function addSeed(exercise: LiveExercise, suggestion: Suggestion | null) {
  for (let i = exercise.sets.length - 1; i >= 0; i -= 1) {
    const { weight, reps } = exercise.sets[i]!
    if (weight !== null && reps !== null) return { weight, reps }
  }
  return suggestion
}

function lastSetKey(exercise: LiveExercise): string {
  const last = exercise.sets[exercise.sets.length - 1]
  return last === undefined ? 'none' : `${last.id}-${last.weight}-${last.reps}`
}

function AddSetRow({ seed, busy, onAdd }: {
  seed: { weight: number; reps: number } | null
  /** An append for this exercise is still on its way to the server. */
  busy: boolean
  onAdd(weight: number, reps: number): void
}) {
  const [weight, setWeight] = useState(seed ? String(seed.weight) : '')
  const [reps, setReps] = useState(seed ? String(seed.reps) : '')
  const parsed = parseSetInput(weight, reps)
  const problem = setInputProblem(weight, reps)

  return (
    <>
    <div className="sset">
      <span className="label" aria-hidden="true">+</span>
      <input type="number" step="0.5" min="0" max={MAX_WEIGHT_KG} className="input input--num" required
        aria-label="Neuer Satz, Gewicht in kg" value={weight}
        aria-invalid={problem?.startsWith('Gewicht') || undefined}
        onChange={(e) => setWeight(e.target.value)} />
      <span className="sset__unit">kg</span>
      <span className="sset__unit">×</span>
      <input type="number" min="1" max={MAX_REPS} className="input input--num" required
        aria-label="Neuer Satz, Wiederholungen" value={reps}
        aria-invalid={problem?.startsWith('Wiederholungen') || undefined}
        onChange={(e) => setReps(e.target.value)} />
      <span className="sset__acts">
        {/* Visible text short so the action slot never wraps; the accessible
            name stays the full phrase. Disabled while the fields cannot make a
            set -- an empty row used to log 0 kg x 0 as done -- and while an
            append is in flight, since a second tap would be a second set. */}
        <button type="button" className="btn btn--ghost btn--sm" aria-label="Satz anhängen"
          disabled={parsed === null || busy}
          onClick={() => { if (parsed !== null) onAdd(parsed.weight, parsed.reps) }}>
          Anhängen
        </button>
      </span>
    </div>
    <SetInputHint problem={problem} />
    </>
  )
}
