import { useEffect, useRef, useState, type MouseEvent, type PointerEvent } from 'react'

/** A press on the backdrop this soon after the sheet opened is the opening
 *  tap's bounce. An opener above where a short sheet ends up -- a partner's
 *  line under the header -- put the second half of a double tap on the new
 *  backdrop, and the sheet closed as it opened (B10b review). */
export const SHEET_OPEN_GUARD_MS = 600

interface Options {
  open: boolean
  /** The close its own button makes. Left out, the dialog's own close(),
   *  whose close event then tells the page. */
  close?: () => void
  /** False for a sheet whose fields are a draft only its own buttons save:
   *  no backdrop close then, and no close at the bottom either. */
  backdrop: boolean
}

/**
 * What the two sheet components share: the native <dialog> shown and closed
 * with `open`, the backdrop's tap, and whether the sheet stands tall enough
 * to want a close at the bottom (`tall`, for SheetFoot).
 */
export function useSheetDialog({ open, close, backdrop }: Options) {
  const dialog = useRef<HTMLDialogElement>(null)
  const openedAt = useRef(0)
  const shut = close ?? (() => dialog.current?.close())

  useEffect(() => {
    const node = dialog.current
    if (node === null) return
    if (open && !node.open) {
      node.showModal()
      openedAt.current = Date.now()
      // showModal() focuses the first control, which is the dismiss button.
      // A sheet whose job is one field names it instead. An attribute rather
      // than React's autoFocus: that one focuses on mount, before showModal()
      // runs, and the dialog's own focusing step then takes it away again.
      node.querySelector<HTMLElement>('[data-autofocus]')?.focus()
    }
    if (!open && node.open) node.close()
  }, [open])

  // A sheet whose top stands in the upper third of the screen leaves only a
  // strip of backdrop, up there with its head's close and as far from the
  // thumb (G-108): it gets a close at the bottom as well. Measured again as
  // it grows or shrinks (search hits, a set added) and as the screen turns.
  // After the effect above, so the dialog is open and laid out.
  const [tall, setTall] = useState(false)
  useEffect(() => {
    const node = dialog.current
    if (!open || !backdrop || node === null) {
      setTall(false)
      return
    }
    const measure = () => {
      const box = node.getBoundingClientRect()
      setTall(box.height > 0 && box.top < window.innerHeight / 3)
    }
    measure()
    const observer = typeof ResizeObserver === 'undefined' ? null : new ResizeObserver(measure)
    observer?.observe(node)
    window.addEventListener('resize', measure)
    return () => {
      observer?.disconnect()
      window.removeEventListener('resize', measure)
    }
  }, [open, backdrop])

  // A tap on the backdrop closes the sheet as its button does -- the only
  // close sat at the top, out of a thumb's reach (G-108). The backdrop's
  // presses land on the <dialog> itself, outside its box. Both ends of the
  // press: one that starts inside -- a stepper held, a word selected -- and
  // is let go past the edge is not a tap on the backdrop.
  const pressedOutside = useRef(false)
  const outside = (e: MouseEvent<HTMLDialogElement>) => {
    if (e.target !== e.currentTarget) return false
    const box = e.currentTarget.getBoundingClientRect()
    return e.clientX < box.left || e.clientX > box.right
      || e.clientY < box.top || e.clientY > box.bottom
  }
  const backdropProps = backdrop ? {
    onPointerDown: (e: PointerEvent<HTMLDialogElement>) => {
      pressedOutside.current = Date.now() - openedAt.current >= SHEET_OPEN_GUARD_MS && outside(e)
    },
    onClick: (e: MouseEvent<HTMLDialogElement>) => {
      // Not while something typed in it waits for its own button: a sheet
      // that holds an open draft (`data-draft`) would throw it away.
      if (pressedOutside.current && outside(e)
        && e.currentTarget.querySelector('[data-draft]') === null) shut()
      pressedOutside.current = false
    },
  } : {}

  return { dialog, tall, shut, backdropProps }
}
