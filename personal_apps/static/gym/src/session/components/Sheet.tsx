import { useEffect, useRef, type ReactNode } from 'react'
import { useSheets } from '../stores'

interface Props {
  id: string
  title: string
  /** Label on the dismiss control. "Fertig" for sheets you act inside,
   *  "Abbrechen" for ones that are a single decision. */
  closeLabel?: string
  /** Keeps the body mounted while the sheet is closed. Only for a sheet whose
   *  contents are a DRAFT the lifter must get back -- the new-exercise form is
   *  closed by a name collision and reopened to fix the name. Never for one
   *  that displays stored values: those must re-read them on open. */
  keepMounted?: boolean
  children: ReactNode
}

/**
 * A bottom sheet, as a native <dialog>.
 *
 * The platform supplies the backdrop, Esc and the focus trap -- none of that
 * is reimplemented here, and that was already true before the port.
 *
 * What the port changes is when a sheet exists. The old ones were rendered
 * always and toggled with `hidden`, because they sat outside #session-body
 * specifically to survive refreshBody, and a `{% if %}` would have frozen at
 * whatever was true on the last full page load -- wrong for anything that
 * changes through a refresh, which is most of this screen. Nothing swaps the
 * DOM any more, so a sheet can simply not be open, and its contents render
 * from current state whenever it is.
 *
 * That last sentence is why the body is mounted only while `isOpen`. A closed
 * <dialog> still renders its children, so every editor inside a sheet seeded
 * its state at page load and then never moved: the per-exercise sheet showed
 * the numbers a set had when the workout opened, and saving posted them back
 * over whatever had been logged since. Mounting on open is what makes "from
 * current state" true rather than merely intended.
 */
export function Sheet({
  id, title, closeLabel = 'Fertig', keepMounted = false, children,
}: Props) {
  const dialog = useRef<HTMLDialogElement>(null)
  const openId = useSheets((s) => s.openId)
  const close = useSheets((s) => s.close)
  const isOpen = openId === id

  useEffect(() => {
    const node = dialog.current
    if (node === null) return
    if (isOpen && !node.open) node.showModal()
    if (!isOpen && node.open) node.close()
  }, [isOpen])

  return (
    <dialog
      className="sheet"
      id={id}
      aria-labelledby={`${id}-title`}
      ref={dialog}
      // Esc and the backdrop close the dialog without going through the
      // store, which would leave openId pointing at a sheet nobody can see.
      onClose={() => { if (useSheets.getState().openId === id) close() }}
    >
      <div className="sheet__head">
        <h2 className="sheet__title" id={`${id}-title`}>{title}</h2>
        <button type="button" className="sheet__close" onClick={close}>
          {closeLabel}
        </button>
      </div>
      <div className="sheet__body">{(isOpen || keepMounted) && children}</div>
    </dialog>
  )
}
