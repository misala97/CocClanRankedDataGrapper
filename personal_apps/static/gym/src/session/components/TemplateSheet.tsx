import { useState } from 'react'
import { Sheet } from './Sheet'

interface Props {
  onSave(name: string): void
}

/**
 * Saving the workout you are doing as a routine for next time.
 *
 * "Abbrechen" rather than "Fertig" on the dismiss control: this sheet is a
 * single decision with an obvious undo, not a workspace you finish with.
 */
export function TemplateSheet({ onSave }: Props) {
  const [name, setName] = useState('')

  return (
    <Sheet id="sheet-template" title="Als Vorlage speichern" closeLabel="Abbrechen">
      <form
        className="save-template"
        onSubmit={(e) => { e.preventDefault(); onSave(name) }}
      >
        <div className="field grow">
          <label className="label" htmlFor="template-name-input">Name der Vorlage</label>
          <input type="text" id="template-name-input" name="template_name"
            className="input" placeholder="z.B. Push Day" required
            value={name} onChange={(e) => setName(e.target.value)} />
        </div>
        <button type="submit" className="btn btn--live btn--block">Speichern</button>
      </form>
    </Sheet>
  )
}
