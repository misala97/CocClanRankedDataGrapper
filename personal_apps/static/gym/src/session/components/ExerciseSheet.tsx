import { useState } from 'react'
import type { CatalogueExercise, LiveExercise, Suggestion } from '../types'
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
  onReplaceWithNew(name: string): void
  onRemove(): void
  onShowProgress(): void
}

interface Props extends ExerciseSheetActions {
  exercise: LiveExercise
  catalogue: CatalogueExercise[]
  /** What the add-a-set row pre-fills with. Null for an exercise with no
   *  history to seed from. */
  suggestion: Suggestion | null
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
  exercise, catalogue, suggestion,
  onRestChange, onIncrementChange, onMetaSave, onSetUpdate, onSetDelete,
  onAddSet, onToggleSkip, onReplace, onReplaceWithNew, onRemove, onShowProgress,
}: Props) {
  const [pain, setPain] = useState(exercise.pain)
  const [notes, setNotes] = useState(exercise.notes ?? '')
  const [newName, setNewName] = useState('')

  // Filtered to the same muscle group, so it can be legitimately empty even
  // for a full catalogue -- which is why the pane choice keys off this list
  // rather than off the catalogue as a whole.
  const swaps = catalogue.filter(
    (e) => e.muscle_group === exercise.muscle_group && e.id !== exercise.exercise_id)
  const [replacePane, setReplacePane] = useState<'pick' | 'new'>(
    swaps.length > 0 ? 'pick' : 'new')
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
          belong to this workout, not to the machine. */}
      <div className="sheet__group">
        <div className="sheet__group-head">
          <span className="label">Heute</span>
        </div>
        <label className="sheet__row">
          <input type="checkbox" className="check" checked={pain}
            onChange={(e) => setPain(e.target.checked)} />
          <span className="check__text">Schmerz / Zwicken</span>
        </label>
        <div className="sheet__save-row">
          <div className="field">
            <label className="label" htmlFor={`ex-notes-${exercise.id}`}>Notiz</label>
            <input type="text" id={`ex-notes-${exercise.id}`} className="input"
              placeholder="—" value={notes}
              onChange={(e) => setNotes(e.target.value)} />
          </div>
          <button type="button" className="btn btn--ghost btn--sm"
            onClick={() => onMetaSave({ pain, notes })}>Speichern</button>
        </div>
      </div>

      <div className="sheet__group">
        <div className="sheet__group-head">
          <span className="label">Sätze</span>
        </div>
        {exercise.sets.map((s, i) => (
          <SetEditor set={s} ordinal={i + 1} key={s.id}
            onSave={onSetUpdate} onDelete={onSetDelete} />
        ))}
        <AddSetRow suggestion={suggestion} onAdd={onAddSet} />
      </div>

      <div className="sheet__group">
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
              {exercise.skipped
                ? 'Zählt wieder ganz normal.'
                : 'Sätze bleiben, zählen aber nicht.'}
            </span>
          </span>
        </button>

        <details>
          <summary className="sheet-row">
            <span className="sheet-row__lead"><Icon name="swap" /></span>
            <span className="sheet-row__main">
              <span className="sheet-row__name">Übung ersetzen</span>
              <span className="sheet-row__meta">Nur für heute — die Vorlage bleibt.</span>
            </span>
          </summary>

          {replacePane === 'pick' && swaps.length > 0 && (
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
              <button type="button" className="sheet__switch"
                onClick={() => setReplacePane('new')}>+ Neue Übung anlegen</button>
            </div>
          )}

          {(replacePane === 'new' || swaps.length === 0) && (
            <div className="sheet__pane">
              {swaps.length > 0
                ? (
                  <button type="button" className="sheet__back"
                    onClick={() => setReplacePane('pick')}>← Vorhandene wählen</button>
                )
                : (
                  <p className="sheet__hint">
                    {`Keine andere Übung für ${exercise.muscle_group ?? 'diese Gruppe'} in deiner Liste. Leg eine neue an.`}
                  </p>
                )}
              <div className="field grow">
                <label className="label" htmlFor={`replace-name-${exercise.id}`}>Name</label>
                <input type="text" id={`replace-name-${exercise.id}`} className="input"
                  placeholder="z.B. Kabelzug" value={newName}
                  onChange={(e) => setNewName(e.target.value)} />
              </div>
              <button type="button" className="btn btn--live btn--sm"
                onClick={() => onReplaceWithNew(newName)}>Anlegen und ersetzen</button>
            </div>
          )}
        </details>

        <button type="button" className="sheet-row sheet-row--danger"
          onClick={() => {
            if (confirm('Übung aus Workout entfernen?')) onRemove()
          }}>
          <span className="sheet-row__lead"><Icon name="trash" /></span>
          <span className="sheet-row__main">
            <span className="sheet-row__name">Übung entfernen</span>
            <span className="sheet-row__meta">Aus diesem Workout, samt Sätzen.</span>
          </span>
        </button>
      </div>
    </Sheet>
  )
}

function SetEditor({ set, ordinal, onSave, onDelete }: {
  set: LiveExercise['sets'][number]
  ordinal: number
  onSave(setId: number, weight: number, reps: number): void
  onDelete(setId: number): void
}) {
  const [weight, setWeight] = useState(String(set.weight))
  const [reps, setReps] = useState(String(set.reps))

  return (
    <div className="sset">
      <span className="label">{ordinal}</span>
      <input type="number" step="0.5" min="0" className="input input--num"
        aria-label={`Satz ${ordinal}, Gewicht in kg`} value={weight}
        onChange={(e) => setWeight(e.target.value)} />
      <span className="sset__unit">kg</span>
      <span className="sset__unit">×</span>
      <input type="number" min="0" className="input input--num"
        aria-label={`Satz ${ordinal}, Wiederholungen`} value={reps}
        onChange={(e) => setReps(e.target.value)} />
      <span className="sset__acts">
        <button type="button" className="icon-btn"
          aria-label={`Satz ${ordinal} speichern`}
          onClick={() => onSave(set.id, Number(weight), Number(reps))}>
          <Icon name="save" />
        </button>
        {/* The multiplication-sign delete stays a typographic mark on
            purpose -- see Icon.tsx's header. */}
        <button type="button" className="icon-btn"
          aria-label={`Satz ${ordinal} löschen`}
          onClick={() => onDelete(set.id)}>✕</button>
      </span>
    </div>
  )
}

function AddSetRow({ suggestion, onAdd }: {
  suggestion: Suggestion | null
  onAdd(weight: number, reps: number): void
}) {
  const [weight, setWeight] = useState(suggestion ? String(suggestion.weight) : '')
  const [reps, setReps] = useState(suggestion ? String(suggestion.reps) : '')

  return (
    <div className="sset">
      <span className="label" aria-hidden="true">+</span>
      <input type="number" step="0.5" min="0" className="input input--num" required
        aria-label="Neuer Satz, Gewicht in kg" value={weight}
        onChange={(e) => setWeight(e.target.value)} />
      <span className="sset__unit">kg</span>
      <span className="sset__unit">×</span>
      <input type="number" min="0" className="input input--num" required
        aria-label="Neuer Satz, Wiederholungen" value={reps}
        onChange={(e) => setReps(e.target.value)} />
      <span className="sset__acts">
        {/* Visible text short so the action slot never wraps; the accessible
            name stays the full phrase. */}
        <button type="button" className="btn btn--ghost btn--sm" aria-label="Satz anhängen"
          onClick={() => onAdd(Number(weight), Number(reps))}>Anhängen</button>
      </span>
    </div>
  )
}
