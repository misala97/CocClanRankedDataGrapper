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
      <div className="sheet__group">
        <div className="sheet__row rest-form">
          <label className="label" htmlFor={`rest-${exercise.id}`}>Pause (Sekunden)</label>
          <input type="number" id={`rest-${exercise.id}`} min="0"
            className="input input--num rest-form__input"
            defaultValue={exercise.rest_seconds ?? ''}
            onBlur={(e) => onRestChange(
              e.target.value === '' ? null : Number(e.target.value))} />
        </div>
      </div>

      {/* Its own group, with the note, because the two fields have opposite
          lifetimes: the rest above is this session's, this one is the
          exercise's and outlives the workout. */}
      <div className="sheet__group">
        <div className="sheet__row rest-form">
          <label className="label" htmlFor={`increment-${exercise.id}`}>Schrittweite (kg)</label>
          <input type="number" id={`increment-${exercise.id}`} step="0.25" min="0"
            className="input input--num rest-form__input" placeholder="2,5"
            defaultValue={exercise.increment}
            onBlur={(e) => onIncrementChange(
              e.target.value === '' ? null : Number(e.target.value))} />
        </div>
        <p className="sheet__note">Gilt für die Übung, nicht nur heute.</p>
      </div>

      {/* The opposite lifetime to the increment above: a twinge and a note
          belong to this workout, not to the machine. */}
      <div className="sheet__group">
        <label className="sheet__row">
          <input type="checkbox" className="check" checked={pain}
            onChange={(e) => setPain(e.target.checked)} />
          <span className="check__text">Schmerz / Zwicken</span>
        </label>
        <div className="field grow">
          <label className="label" htmlFor={`ex-notes-${exercise.id}`}>Notiz</label>
          <input type="text" id={`ex-notes-${exercise.id}`} className="input"
            placeholder="—" value={notes}
            onChange={(e) => setNotes(e.target.value)} />
        </div>
        <button type="button" className="btn btn--ghost btn--sm"
          onClick={() => onMetaSave({ pain, notes })}>Speichern</button>
        <p className="sheet__note">Gilt nur für heute.</p>
      </div>

      {exercise.sets.length > 0 && (
        <div className="sheet__group">
          <span className="label">Sätze</span>
          {exercise.sets.map((s, i) => (
            <div className="sheet__row" key={s.id}>
              <span className="label">{i + 1}</span>
              <SetEditor set={s} ordinal={i + 1} onSave={onSetUpdate} />
              <button type="button" className="icon-btn"
                aria-label={`Satz ${i + 1} löschen`}
                onClick={() => onSetDelete(s.id)}>✕</button>
            </div>
          ))}
        </div>
      )}

      <AddSetRow suggestion={suggestion} onAdd={onAddSet} />

      <div className="sheet__group">
        <button type="button" className="sheet__act" onClick={onShowProgress}>
          <Icon name="chart" />
          Fortschritt anzeigen
        </button>
        <button type="button" className="sheet__act" onClick={onToggleSkip}>
          <Icon name="skip" />
          {exercise.skipped ? 'Nicht mehr überspringen' : 'Übung überspringen'}
        </button>

        <details>
          <summary className="sheet__act">
            <Icon name="swap" />
            Übung ersetzen
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

        <button type="button" className="sheet__act sheet__act--danger"
          onClick={() => {
            if (confirm('Übung aus Workout entfernen?')) onRemove()
          }}>Übung entfernen</button>
      </div>
    </Sheet>
  )
}

function SetEditor({ set, ordinal, onSave }: {
  set: LiveExercise['sets'][number]
  ordinal: number
  onSave(setId: number, weight: number, reps: number): void
}) {
  const [weight, setWeight] = useState(String(set.weight))
  const [reps, setReps] = useState(String(set.reps))

  return (
    <div className="sheet__row" style={{ flex: 1 }}>
      <input type="number" step="0.5" min="0" className="input input--num"
        aria-label="Gewicht in kg" value={weight}
        onChange={(e) => setWeight(e.target.value)} />
      <span className="load__unit">kg</span><span className="load__x">×</span>
      <input type="number" min="0" className="input input--num"
        aria-label="Wiederholungen" value={reps}
        onChange={(e) => setReps(e.target.value)} />
      <button type="button" className="icon-btn"
        aria-label={`Satz ${ordinal} speichern`}
        onClick={() => onSave(set.id, Number(weight), Number(reps))}>
        <Icon name="save" />
      </button>
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
    <div className="sheet__group">
      <div className="sheet__row">
        <input type="number" step="0.5" min="0" className="input input--num" required
          aria-label="Gewicht in kg" value={weight}
          onChange={(e) => setWeight(e.target.value)} />
        <span className="load__unit">kg</span><span className="load__x">×</span>
        <input type="number" min="0" className="input input--num" required
          aria-label="Wiederholungen" value={reps}
          onChange={(e) => setReps(e.target.value)} />
        <button type="button" className="btn btn--ghost btn--sm"
          onClick={() => onAdd(Number(weight), Number(reps))}>Satz anhängen</button>
      </div>
    </div>
  )
}
