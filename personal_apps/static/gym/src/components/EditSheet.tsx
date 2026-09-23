import { forwardRef, useImperativeHandle, useRef } from 'react'
import { CsrfField } from '../csrf'
import type { ExerciseMeta } from '../types'

interface Props {
  exercise: ExerciseMeta
  equipmentLabels: Record<string, string>
}

export interface EditSheetHandle {
  open(): void
}

/** "2,5" for 2.5: a placeholder is read, not parsed. */
const de = (value: number) => String(value).replace('.', ',')

/**
 * The lifter's own settings for one exercise: step, rest, bar and, on a
 * stack, its stops. The rest of the exercise -- name, groups, equipment, one
 * side -- belongs to the one list, so it is shown, not asked.
 *
 * Each field starts at the value in use and stands for the list's value when
 * left blank, which is what its placeholder shows; a value equal to the
 * list's is stored as nothing (exercises.save_setup).
 *
 * Native <dialog>: the platform supplies the backdrop, Esc, and the focus
 * trap. The form is a native POST followed by a redirect, deliberately -- this
 * is a one-off edit, not a mid-workout mutation, and a full reload afterwards
 * is the honest signal that the page changed underneath.
 */
export const EditSheet = forwardRef<EditSheetHandle, Props>(function EditSheet(
  { exercise, equipmentLabels }, ref,
) {
  const dialog = useRef<HTMLDialogElement>(null)
  const list = exercise.list_defaults

  useImperativeHandle(ref, () => ({
    open: () => dialog.current?.showModal(),
  }), [])

  const num = (value: number | null) => (value === null ? '' : String(value))
  const facts = [
    exercise.name,
    exercise.muscle_group,
    exercise.equipment === null ? null : equipmentLabels[exercise.equipment] ?? exercise.equipment,
    exercise.is_unilateral ? 'einseitig (pro Seite)' : null,
  ].filter((fact) => fact !== null).join(' · ')

  return (
    <dialog className="sheet" id="sheet-edit" aria-labelledby="sheet-edit-title" ref={dialog}>
      <div className="sheet__head">
        <h2 className="sheet__title" id="sheet-edit-title">Deine Einstellungen</h2>
        <button type="button" className="sheet__close"
          onClick={() => dialog.current?.close()}>
          Abbrechen
        </button>
      </div>
      <div className="sheet__body">
        <p className="sheet__note">
          {facts}. Das legt die Übungsliste fest, für alle gleich. Die Werte hier
          gelten nur für dich — ein leeres Feld nimmt den Wert der Liste.
        </p>
        <form method="post" action={`/gym/exercises/${exercise.id}/update`}>
          <CsrfField />
          <div className="field">
            <label className="label" htmlFor="meta-increment">Schrittweite (kg)</label>
            <input type="number" id="meta-increment" name="weight_increment"
              step="0.25" min="0" className="input input--num"
              placeholder={list.weight_increment === null ? '' : de(list.weight_increment)}
              defaultValue={num(exercise.weight_increment)} />
          </div>

          <div className="field">
            <label className="label" htmlFor="meta-rest">Pause (Sek.)</label>
            <input type="number" id="meta-rest" name="default_rest_seconds" min="0"
              className="input input--num" placeholder={num(list.default_rest_seconds)}
              defaultValue={num(exercise.default_rest_seconds)} />
          </div>

          <div className="field">
            <label className="label" htmlFor="meta-bar">Stangengewicht (kg)</label>
            <input type="number" id="meta-bar" name="bar_weight" step="0.5" min="0"
              className="input input--num" placeholder={de(list.bar_weight ?? 0)}
              defaultValue={num(exercise.bar_weight)} />
          </div>

          {/* Only a stack has stops, and only an uneven one needs them: even
              ones are already described by Schrittweite above, and typing
              5,10,15,... would be the same fact twice. */}
          {exercise.equipment === 'stack' && (
            <div className="field grow">
              <label className="label" htmlFor="meta-stack">Stack-Stufen (kg, kommagetrennt)</label>
              <input type="text" id="meta-stack" name="stack_kg" className="input"
                placeholder={list.stack_kg === null ? 'gleichmäßig' : list.stack_kg.join(', ')}
                defaultValue={exercise.stack_kg === null ? '' : exercise.stack_kg.join(', ')} />
            </div>
          )}

          <button type="submit" className="btn btn--live btn--block">Speichern</button>
        </form>
      </div>
    </dialog>
  )
})
