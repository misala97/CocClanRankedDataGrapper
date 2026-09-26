interface Props {
  /** The head's close label, word for word. */
  label: string
  onClose(): void
}

/**
 * The close at the bottom of a tall sheet (useSheetDialog's `tall`), under
 * the thumb. The head's close is the one a keyboard or a screen reader
 * meets: this one is out of the tab order and unheard, not a second close
 * to walk past on the way through the sheet.
 */
export function SheetFoot({ label, onClose }: Props) {
  return (
    <div className="sheet__foot" aria-hidden="true">
      <button type="button" className="btn btn--ghost btn--block sheet__done" tabIndex={-1}
        onClick={onClose}>
        {label}
      </button>
    </div>
  )
}
