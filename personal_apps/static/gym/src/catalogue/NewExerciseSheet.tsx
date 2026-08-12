import { useState, type FormEvent } from 'react'
import { CsrfField } from '../csrf'
import { Sheet } from '../session/components/Sheet'

interface Props {
  muscleGroups: string[]
  equipmentLabels: Record<string, string>
  /** What a blank rest field actually stores. The placeholder said 90. */
  defaultRestSeconds: number
  /** POSTs the form over fetch; resolves true when the exercise was created
   *  (false on a name collision). The page swaps its payload either way --
   *  added_id highlights the new row, name_taken raises the banner. */
  onCreate: (fields: FormData) => Promise<boolean>
  /** Preselects the Muskelgruppe when an empty group band opened the sheet. */
  presetGroup?: string | null
}

/**
 * Creating an exercise from the catalogue.
 *
 * The submit goes over fetch and the page re-renders from the answered
 * payload -- the same added_id / name_taken the ?added= redirect used to
 * deliver, minus the reload. The raw FormData is what travels, because
 * secondary_muscle_groups is a multi-select and flattening it would drop
 * every value but one.
 */
export function NewExerciseSheet({
  muscleGroups, equipmentLabels, defaultRestSeconds, onCreate, presetGroup = null,
}: Props) {
  const submit = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault()
    const form = event.currentTarget
    void onCreate(new FormData(form)).then((created) => {
      // Only a success clears the fields: after a collision you reopen to
      // fix the name, not to retype everything.
      if (created) form.reset()
    })
  }
  // The stack-steps field only applies to a stack: on a dumbbell it is not an
  // empty answer, it is a meaningless question.
  const [equipment, setEquipment] = useState('stack')

  return (
    // keepMounted: a name collision CLOSES this sheet and the banner sends the
    // lifter back into it to fix the name -- everything already typed has to
    // still be there. Nothing in this form displays a stored value, so it has
    // none of the staleness that mounting on open exists to prevent.
    <Sheet id="sheet-new-exercise" title="Neue Übung" closeLabel="Abbrechen"
      keepMounted>
      <form method="post" action="/gym/exercises/add" onSubmit={submit}>
        <CsrfField />
        <div className="field grow">
          <label className="label" htmlFor="uebungen-add-name">Name</label>
          <input type="text" id="uebungen-add-name" name="name" className="input"
            placeholder="z.B. Kniebeuge" required />
        </div>

        <div className="field grow">
          <label className="label" htmlFor="uebungen-add-group">Muskelgruppe</label>
          {/* key remounts the uncontrolled select when an empty group band
              opened the sheet, so ITS group arrives preselected. */}
          <select id="uebungen-add-group" name="muscle_group" className="select"
            key={presetGroup ?? 'none'} defaultValue={presetGroup ?? ''}>
            <option value="">— optional —</option>
            {muscleGroups.map((mg) => <option value={mg} key={mg}>{mg}</option>)}
          </select>
        </div>

        <div className="field">
          <label className="label" htmlFor="uebungen-add-rest">Standard-Pause (Sek.)</label>
          <input type="number" id="uebungen-add-rest" name="default_rest_seconds"
            min="0" className="input input--num" placeholder={String(defaultRestSeconds)} />
        </div>

        <div className="field">
          <label className="label" htmlFor="uebungen-add-increment">Schrittweite (kg)</label>
          <input type="number" id="uebungen-add-increment" name="weight_increment"
            step="0.25" min="0" className="input input--num" placeholder="2,5" />
        </div>

        <div className="field grow">
          <label className="label" htmlFor="uebungen-add-equipment">Art</label>
          <select id="uebungen-add-equipment" name="equipment" className="select"
            value={equipment} onChange={(e) => setEquipment(e.target.value)}>
            {Object.entries(equipmentLabels).map(([value, label]) => (
              <option value={value} key={value}>{label}</option>
            ))}
          </select>
        </div>

        <div className="field">
          <label className="label" htmlFor="uebungen-add-bar">Stangengewicht (kg)</label>
          <input type="number" id="uebungen-add-bar" name="bar_weight" step="0.5"
            min="0" className="input input--num" placeholder="0" />
        </div>

        <div className="field grow" hidden={equipment !== 'stack'}>
          <label className="label" htmlFor="uebungen-add-stack">Stack-Stufen (kg, kommagetrennt)</label>
          <input type="text" id="uebungen-add-stack" name="stack_kg" className="input"
            placeholder="5, 13, 21, 29" />
        </div>

        <div className="field grow">
          <label className="label" htmlFor="uebungen-add-secondary">Sekundäre Muskelgruppen</label>
          <select id="uebungen-add-secondary" name="secondary_muscle_groups"
            className="select" multiple size={5}>
            {muscleGroups.map((mg) => <option value={mg} key={mg}>{mg}</option>)}
          </select>
        </div>

        <label className="sheet__row">
          <input type="checkbox" name="is_unilateral" className="check" />
          <span className="check__text">Einseitig (pro Seite)</span>
        </label>

        <button type="submit" className="btn btn--live btn--block">Hinzufügen</button>
      </form>
    </Sheet>
  )
}
