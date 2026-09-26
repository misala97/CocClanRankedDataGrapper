import type { ReactNode } from 'react'
import { SheetFoot } from './SheetFoot'
import { useSheetDialog } from './useSheetDialog'

interface Props {
  id: string
  title: string
  open: boolean
  /** Every way it closes -- "Fertig", Esc, the backdrop -- ends here. */
  onClose(): void
  children: ReactNode
}

/**
 * A bottom sheet on a page without the live workout's sheet store: the same
 * native <dialog> as session/components/Sheet, opened by a prop, and closed
 * the same ways -- the backdrop too, so "Deine Einstellungen" closes on the
 * exercise page as it does in a workout.
 *
 * The body is mounted only while open, for that sheet's reason: an editor
 * seeded at page load and never re-read shows values that are no longer
 * true, and posts them back.
 */
export function DialogSheet({ id, title, open, onClose, children }: Props) {
  // Every close goes through the dialog's own, whose close event is onClose.
  const { dialog, tall, shut, backdropProps } = useSheetDialog({ open, backdrop: true })

  return (
    <dialog className="sheet" id={id} aria-labelledby={`${id}-title`} ref={dialog}
      onClose={onClose} {...backdropProps}>
      <div className="sheet__head">
        <h2 className="sheet__title" id={`${id}-title`}>{title}</h2>
        <button type="button" className="sheet__close" onClick={shut}>Fertig</button>
      </div>
      <div className="sheet__body">{open && children}</div>
      {tall && <SheetFoot label="Fertig" onClose={shut} />}
    </dialog>
  )
}
