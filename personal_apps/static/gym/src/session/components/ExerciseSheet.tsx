import { useState } from 'react'
import type { CatalogueExercise, LiveExercise, Suggestion } from '../types'
import { useUndo } from '../../undo'
import { useSaveState } from '../stores'
import { parseSetInput } from '../../setInput'
import { Sheet } from './Sheet'
import { Icon } from '../../components/Icon'

export interface ExerciseSheetActions {
  onRestChange(seconds: number | null): void
  onIncrementChange(kg: number | null): void
  onMetaSave(meta: { pain: boolean; notes: string }): void
  onSetUpdate(setId: number, weight: number, reps: number): void
  onSetDelete(setId: number): void
  onAddSet(weight: number, reps: number): void
  onToggleSkip(): void
  onReplace(exerciseId: number): void
  onRemove(): void
  onShowProgress(): void
  /** Pull this exercise in front of the live one, so it is up next. */
  onMakeLive(): void
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
}

/**
 * One sheet per exercise: its sets, its rest time, and the three things you
 * can do to it. This replaced a menu on every row and an expanded panel per
 * exercise -- the row itself is the affordance.
 *
 * The groups are not cosmetic. Rest belongs to this session, the increment
 * belongs to the exercise and outlives the workout, and a twinge or a note
 * belongs to today. Identical styling with no caption would make those
 * opposite lifetimes invisible, which is why each carries its own note.
 */
export function ExerciseSheet({
  exercise, catalogue, suggestion, canMakeLive,
  onRestChange, onIncrementChange, onMetaSave, onSetUpdate, onSetDelete,
  onAddSet, onToggleSkip, onReplace, onRemove, onShowProgress,
  onMakeLive,
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
      // The keepalive flag stops here: the write goes through the session
      // mutation layer, which owns its own fetch. A pagehide flush mid-window
      // therefore races the navigation -- acceptable for a 5s window on a
      // screen you leave by finishing the workout.
      commit: () => onSetDelete(setId),
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
      {/* One group, one caption naming both lifetimes: the rest is this
          session's, the increment is the exercise's and outlives the workout.
          Both save on blur, as before. */}
      <div className="sheet__group">
        <div className="sheet__group-head">
          <span className="label">Einstellungen</span>
        </div>
        <div className="sheet__save-row">
          <div className="field">
            <label className="label" htmlFor={`rest-${exercise.id}`}>Pause (Sekunden)</label>
            <input type="number" id={`rest-${exercise.id}`} min="0"
              className="input input--num"
              defaultValue={exercise.rest_seconds ?? ''}
              onBlur={(e) => onRestChange(
                e.target.value === '' ? null : Number(e.target.value))} />
          </div>
          <div className="field">
            <label className="label" htmlFor={`increment-${exercise.id}`}>Schrittweite (kg)</label>
            <input type="number" id={`increment-${exercise.id}`} step="0.25" min="0"
              className="input input--num" placeholder="2,5"
              defaultValue={exercise.increment}
              onBlur={(e) => onIncrementChange(
                e.target.value === '' ? null : Number(e.target.value))} />
          </div>
        </div>
        <p className="sheet__note">Pause gilt für dieses Workout, Schrittweite für die Übung.</p>
      </div>

      {/* The opposite lifetime to the increment above: a twinge and a note
          belong to this workout, not to the machine.

          Both save by themselves, like the settings above. The flag used to
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
            placeholder="—" value={notes}
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
  const [weight, setWeight] = useState(String(set.weight))
  const [reps, setReps] = useState(String(set.reps))
  // A cleared field used to save as 0 -- Number('') is 0 -- and overwrite the
  // real numbers. Invalid or unchanged, there is nothing to save.
  const parsed = parseSetInput(weight, reps)
  const changed = parsed !== null
    && (parsed.weight !== set.weight || parsed.reps !== set.reps)

  return (
    <div className="sset">
      <span className="label">{ordinal}</span>
      <input type="number" step="0.5" min="0" className="input input--num"
        aria-label={`Satz ${ordinal}, Gewicht in kg`} value={weight}
        onChange={(e) => setWeight(e.target.value)} />
      <span className="sset__unit">kg</span>
      <span className="sset__unit">×</span>
      <input type="number" min="1" className="input input--num"
        aria-label={`Satz ${ordinal}, Wiederholungen`} value={reps}
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
  )
}

/** What the add row starts from: the last set of this exercise, else the
 *  session's suggestion, else nothing. */
function addSeed(exercise: LiveExercise, suggestion: Suggestion | null) {
  const last = exercise.sets[exercise.sets.length - 1]
  if (last !== undefined) return { weight: last.weight, reps: last.reps }
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

  return (
    <div className="sset">
      <span className="label" aria-hidden="true">+</span>
      <input type="number" step="0.5" min="0" className="input input--num" required
        aria-label="Neuer Satz, Gewicht in kg" value={weight}
        onChange={(e) => setWeight(e.target.value)} />
      <span className="sset__unit">kg</span>
      <span className="sset__unit">×</span>
      <input type="number" min="1" className="input input--num" required
        aria-label="Neuer Satz, Wiederholungen" value={reps}
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
  )
}
