import { useState } from 'react'
import { Sheet } from '../session/components/Sheet'

interface Props {
  muscleGroups: string[]
  equipmentLabels: Record<string, string>
  /** What a blank rest field actually stores. The placeholder said 90. */
  defaultRestSeconds: number
}

/**
 * Creating an exercise from the catalogue.
 *
 * A native POST followed by a redirect, deliberately: the route answers with
 * ?added=<id> so the new row can arrive highlighted, and ?name_taken=1 when it
 * collides -- both of which the page reads on the way back in. Turning this
 * into a fetch would mean reimplementing that round trip for no gain.
 */
export function NewExerciseSheet({
  muscleGroups, equipmentLabels, defaultRestSeconds,
}: Props) {
  // The stack-steps field only applies to a stack: on a dumbbell it is not an
  // empty answer, it is a meaningless question.
  const [equipment, setEquipment] = useState('stack')

  return (
    <Sheet id="sheet-new-exercise" title="Neue Übung" closeLabel="Abbrechen">
      <form method="post" action="/gym/exercises/add">
        <div className="field grow">
          <label className="label" htmlFor="uebungen-add-name">Name</label>
          <input type="text" id="uebungen-add-name" name="name" className="input"
            placeholder="z.B. Kniebeuge" required />
        </div>

        <div className="field grow">
          <label className="label" htmlFor="uebungen-add-group">Muskelgruppe</label>
          <select id="uebungen-add-group" name="muscle_group" className="select">
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
