import type { ExerciseMeta } from '../types'
import { DialogSheet } from './DialogSheet'
import { SettingsBody } from '../settings/SettingsBody'

interface Props {
  exercise: ExerciseMeta
  open: boolean
  onClose(): void
  /** Each answer from the server, so the page shows what was saved. */
  onSaved(exercise: ExerciseMeta): void
}

/**
 * The lifter's own settings for one exercise, from its page: rest, step,
 * bar and, on a stack, its stops. Name, groups, equipment and one side
 * belong to the one list and are the page's header, not asked here.
 *
 * Every tap saves (settings/SettingsBody), so the sheet closes with
 * "Fertig" and nothing to lose. It used to be a form posted with a reload,
 * and closing it without "Speichern" dropped what was typed.
 */
export function EditSheet({ exercise, open, onClose, onSaved }: Props) {
  return (
    <DialogSheet id="sheet-edit" title="Deine Einstellungen" open={open} onClose={onClose}>
      <SettingsBody exercise={exercise} onSaved={onSaved} />
    </DialogSheet>
  )
}
