import { useEffect, useRef, type ReactNode } from 'react'

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
 * native <dialog> as session/components/Sheet, opened by a prop.
 *
 * The body is mounted only while open, for that sheet's reason: an editor
 * seeded at page load and never re-read shows values that are no longer
 * true, and posts them back.
 */
export function DialogSheet({ id, title, open, onClose, children }: Props) {
  const dialog = useRef<HTMLDialogElement>(null)

  useEffect(() => {
    const node = dialog.current
    if (node === null) return
    if (open && !node.open) node.showModal()
    if (!open && node.open) node.close()
  }, [open])

  return (
    <dialog className="sheet" id={id} aria-labelledby={`${id}-title`} ref={dialog}
      onClose={onClose}>
      <div className="sheet__head">
        <h2 className="sheet__title" id={`${id}-title`}>{title}</h2>
        <button type="button" className="sheet__close"
          onClick={() => dialog.current?.close()}>Fertig</button>
      </div>
      <div className="sheet__body">{open && children}</div>
    </dialog>
  )
}
