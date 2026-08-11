import { useEffect, useRef, useState } from 'react'

interface Props {
  /** `kg`, `kg je Seite`, or `Wdh.` */
  label: string
  value: number
  /** The exercise's own loadable step, resolved server-side. */
  step: number
  decimals: number
  ariaLabel: string
  onChange(next: number): void
}

const de = (value: number, decimals: number) =>
  decimals ? value.toFixed(decimals).replace('.', ',') : String(Math.round(value))

/**
 * A number you change by tapping, not by typing.
 *
 * The value is state and the readout is text, which is the whole reason no
 * keyboard opens mid-workout. The readout is still a button: the steppers are
 * right when the prefilled number is already close, and wrong when it is not
 * -- an exercise with no history starts at a default, and stepping from there
 * to a real working weight is dozens of taps.
 */
export function Stepper({ label, value, step, decimals, ariaLabel, onChange }: Props) {
  const [editing, setEditing] = useState(false)
  const [draft, setDraft] = useState('')
  const input = useRef<HTMLInputElement>(null)
  // Closing the field blurs it synchronously, and that blur would otherwise
  // commit the very value an Escape just rejected. The original carried the
  // same flag for the same reason -- an isConnected check does not help,
  // because the blur fires before the node is detached.
  const settled = useRef(false)

  useEffect(() => {
    if (editing) {
      input.current?.focus()
      input.current?.select()
    }
  }, [editing])

  const bump = (direction: 1 | -1) => {
    // toFixed is a display concern only. Rounding the stored number here would
    // turn a 1.25 kg step into an effective 1.3 after a few taps.
    onChange(Math.max(0, value + direction * step))
  }

  const openEntry = () => {
    settled.current = false
    setDraft(de(value, decimals))
    setEditing(true)
  }

  const commit = (save: boolean) => {
    if (settled.current) return
    settled.current = true
    setEditing(false)
    if (!save) return
    // Both separators: the app renders commas, phone keypads vary on which
    // they offer, and rejecting either would be a silent no-op at the moment
    // the lifter is correcting a number.
    const parsed = Number.parseFloat(draft.replace(',', '.'))
    if (!Number.isFinite(parsed) || parsed < 0) return
    // Not snapped to the increment: the increment governs stepping, typing is
    // exact by intent.
    onChange(decimals ? parsed : Math.round(parsed))
  }

  return (
    <div className="field-num">
      {editing ? (
        <input
          ref={input}
          type="text"
          inputMode={decimals ? 'decimal' : 'numeric'}
          className="field-num__entry"
          aria-label={ariaLabel}
          value={draft}
          onChange={(e) => setDraft(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === 'Enter') { e.preventDefault(); commit(true) }
            else if (e.key === 'Escape') { e.preventDefault(); commit(false) }
          }}
          onBlur={() => commit(true)}
        />
      ) : (
        <button type="button" className="field-num__val"
          aria-label={ariaLabel} onClick={openEntry}>
          {de(value, decimals)}
        </button>
      )}
      <span className="field-num__lbl">{label}</span>
      <span className="field-num__keys">
        <button type="button" className="field-num__key"
          aria-label={`${label.startsWith('kg') ? 'Gewicht' : 'Wiederholungen'} verringern`}
          onClick={() => bump(-1)}>−</button>
        <button type="button" className="field-num__key"
          aria-label={`${label.startsWith('kg') ? 'Gewicht' : 'Wiederholungen'} erhöhen`}
          onClick={() => bump(1)}>+</button>
      </span>
    </div>
  )
}
