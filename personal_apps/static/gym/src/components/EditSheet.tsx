import { forwardRef, useEffect, useImperativeHandle, useRef, useState } from 'react'
import { CsrfField } from '../csrf'
import type { ExerciseMeta } from '../types'

interface Props {
  exercise: ExerciseMeta
  muscleGroups: string[]
  equipmentLabels: Record<string, string>
  /** The rename was rejected, so reopen the editor rather than making the
   *  reader find the sheet again. */
  openOnMount: boolean
}

export interface EditSheetHandle {
  open(): void
}

/**
 * Native <dialog>: the platform supplies the backdrop, Esc, and the focus
 * trap. The form is a native POST followed by a redirect, deliberately -- this
 * is a one-off edit, not a mid-workout mutation, and a full reload afterwards
 * is the honest signal that the page changed underneath.
 */
export const EditSheet = forwardRef<EditSheetHandle, Props>(function EditSheet(
  { exercise, muscleGroups, equipmentLabels, openOnMount }, ref,
) {
  const dialog = useRef<HTMLDialogElement>(null)
  // Replaces the old document-level 'change' listener. The stack-steps field
  // only applies to a stack: on a dumbbell it is not an empty answer, it is a
  // meaningless question.
  const [equipment, setEquipment] = useState(exercise.equipment ?? '')

  useImperativeHandle(ref, () => ({
    open: () => dialog.current?.showModal(),
  }), [])

  useEffect(() => {
    if (openOnMount) dialog.current?.showModal()
  }, [openOnMount])

  const num = (value: number | null) => (value === null ? '' : String(value))

  return (
    <dialog className="sheet" id="sheet-edit" aria-labelledby="sheet-edit-title" ref={dialog}>
      <div className="sheet__head">
        <h2 className="sheet__title" id="sheet-edit-title">Übung bearbeiten</h2>
        <button type="button" className="sheet__close"
          onClick={() => dialog.current?.close()}>
          Abbrechen
        </button>
      </div>
      <div className="sheet__body">
        <form method="post" action={`/gym/exercises/${exercise.id}/update`}>
          <CsrfField />
          <div className="field grow">
            <label className="label" htmlFor="meta-name">Name</label>
            <input type="text" id="meta-name" name="name" className="input"
              defaultValue={exercise.name} required />
          </div>

          <div className="field grow">
            <label className="label" htmlFor="meta-group">Muskelgruppe</label>
            <select id="meta-group" name="muscle_group" className="select"
              defaultValue={exercise.muscle_group ?? ''}>
              <option value="">— keine —</option>
              {muscleGroups.map((mg) => <option value={mg} key={mg}>{mg}</option>)}
              {exercise.muscle_group !== null
                && !muscleGroups.includes(exercise.muscle_group) && (
                <option value={exercise.muscle_group}>{exercise.muscle_group} (alt)</option>
              )}
            </select>
          </div>

          <div className="field">
            <label className="label" htmlFor="meta-rest">Standard-Pause (Sek.)</label>
            <input type="number" id="meta-rest" name="default_rest_seconds" min="0"
              className="input input--num" placeholder="90"
              defaultValue={num(exercise.default_rest_seconds)} />
          </div>

          <div className="field">
            <label className="label" htmlFor="meta-increment">Schrittweite (kg)</label>
            <input type="number" id="meta-increment" name="weight_increment"
              step="0.25" min="0" className="input input--num" placeholder="2,5"
              defaultValue={num(exercise.weight_increment)} />
          </div>

          <div className="field grow">
            <label className="label" htmlFor="meta-equipment">Art</label>
            <select id="meta-equipment" name="equipment" className="select"
              value={equipment} onChange={(e) => setEquipment(e.target.value)}>
              {Object.entries(equipmentLabels).map(([value, label]) => (
                <option value={value} key={value}>{label}</option>
              ))}
            </select>
          </div>

          <div className="field">
            <label className="label" htmlFor="meta-bar">Stangengewicht (kg)</label>
            <input type="number" id="meta-bar" name="bar_weight" step="0.5" min="0"
              className="input input--num" placeholder="0"
              defaultValue={num(exercise.bar_weight)} />
          </div>

          {/* Only meaningful on an uneven stack. Even ones are already
              described by Schrittweite above, and typing 5,10,15,... would be
              the same fact twice. */}
          <div className="field grow" hidden={equipment !== 'stack'}>
            <label className="label" htmlFor="meta-stack">Stack-Stufen (kg, kommagetrennt)</label>
            <input type="text" id="meta-stack" name="stack_kg" className="input"
              placeholder="5, 13, 21, 29"
              defaultValue={exercise.stack_kg !== null ? exercise.stack_kg.join(', ') : ''} />
          </div>

          <div className="field grow">
            <label className="label" htmlFor="meta-secondary">Sekundäre Muskelgruppen</label>
            <select id="meta-secondary" name="secondary_muscle_groups" className="select"
              multiple size={5}
              defaultValue={exercise.secondary_muscle_groups ?? []}>
              {muscleGroups.map((mg) => <option value={mg} key={mg}>{mg}</option>)}
            </select>
          </div>

          <label className="sheet__row">
            <input type="checkbox" name="is_unilateral" className="check"
              defaultChecked={exercise.is_unilateral} />
            <span className="label">Einseitig (pro Seite)</span>
          </label>

          <button type="submit" className="btn btn--live btn--block">Speichern</button>
        </form>
      </div>
    </dialog>
  )
})
