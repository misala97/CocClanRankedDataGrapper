import { forwardRef, useImperativeHandle, useLayoutEffect, useRef, useState } from 'react'
import { kg, roundTo } from '../../format'

/** What the live panel can ask of a stepper beyond its props. */
export interface StepperHandle {
  /** Open the typed entry with the keypad up -- the go button does this while
   *  the number is still missing. */
  open(): void
}

interface Props {
  /** `kg`, `kg je Seite`, or `Wdh.` */
  label: string
  /** Null = blank: nothing decided yet (an exercise with no history). */
  value: number | null
  /** The exercise's own loadable step, resolved server-side. */
  step: number
  /** The most decimals a typed number may have: 2 for a weight (a
   *  quarter-kilo step is real), 0 for reps. */
  decimals: number
  /** The lowest number the field takes. Reps start at 1 -- the server does
   *  not take a set of none. */
  min?: number
  /** The highest number the field takes; the server refuses anything past
   *  it (setInput.ts MAX_WEIGHT_KG / MAX_REPS). */
  max?: number
  /** What the label says instead while a typed number is refused, e.g.
   *  "0 bis 1000 kg". */
  refusedHint?: string
  /** Where "+" lands from a blank; "−" has nowhere to go from one. */
  floor?: number
  ariaLabel: string
  /** The keypad's Enter key: "next" while the other number is still blank. */
  enterHint?: 'next' | 'done'
  /** Called after Enter commits a typed number, to move on. */
  onEnter?(): void
  /** The number being typed, or null when there is none or it is not one --
   *  so the go button can name the next step before the entry closes. */
  onDraft?(value: number | null): void
  onChange(next: number): void
}

// The readout and the entry say the number the way every other screen does,
// to the hundredth. toFixed(1) here used to open 11,25 as "11,3" and write
// that back on close -- a set logged heavier than lifted (walkthrough G-146).
const de = (value: number, decimals: number) =>
  decimals ? kg(value) : String(Math.round(value))

/**
 * A number you change by tapping, not by typing.
 *
 * The value is state and the readout is text, which is the whole reason no
 * keyboard opens mid-workout. The readout is still a button: the steppers are
 * right when the prefilled number is already close, and wrong when it is not.
 * An exercise with no history has no number at all -- the readout is an empty
 * slot, and typing is the way in (the go button opens the entry itself).
 */
export const Stepper = forwardRef<StepperHandle, Props>(function Stepper({
  label, value, step, decimals, min = 0, max = Infinity, floor = min, ariaLabel,
  refusedHint, enterHint = 'done', onEnter, onDraft, onChange,
}, ref) {
  const [editing, setEditing] = useState(false)
  const [draft, setDraft] = useState('')
  // A typed number the field would not take. It used to snap back to the old
  // value without a word -- -10 kg, 0 reps -- so the lifter could not tell a
  // refusal from a missed tap (walkthrough G-070).
  const [refused, setRefused] = useState(false)
  const input = useRef<HTMLInputElement>(null)
  // Closing the field blurs it synchronously, and that blur would otherwise
  // commit the very value an Escape just rejected. The original carried the
  // same flag for the same reason -- an isConnected check does not help,
  // because the blur fires before the node is detached.
  const settled = useRef(false)

  // A layout effect, not a passive one: the focus has to land inside the tap
  // that opened the entry, or iOS keeps the keypad down.
  useLayoutEffect(() => {
    if (editing) {
      input.current?.focus()
      input.current?.select()
    }
  }, [editing])

  // Both separators: the app renders commas, phone keypads vary on which they
  // offer, and rejecting either would be a silent no-op at the moment the
  // lifter is correcting a number. Not snapped to the increment: the increment
  // governs stepping, typing is exact by intent -- which is also why 2.5 reps
  // is refused rather than rounded into a count nobody typed.
  const parse = (text: string): number | null => {
    const parsed = Number.parseFloat(text.replace(',', '.'))
    if (!Number.isFinite(parsed)) return null
    if (roundTo(parsed, decimals) !== parsed) return null
    return parsed < min || parsed > max ? null : parsed
  }

  const bump = (direction: 1 | -1) => {
    setRefused(false)
    if (value === null) {
      if (direction === 1) onChange(floor)
      return
    }
    // toFixed is a display concern only. Rounding the stored number here would
    // turn a 1.25 kg step into an effective 1.3 after a few taps.
    onChange(Math.min(max, Math.max(min, value + direction * step)))
  }

  const openEntry = () => {
    settled.current = false
    setRefused(false)
    const text = value === null ? '' : de(value, decimals)
    setDraft(text)
    onDraft?.(value)
    setEditing(true)
  }

  useImperativeHandle(ref, () => ({ open: openEntry }))

  const commit = (save: boolean) => {
    if (settled.current) return false
    settled.current = true
    setEditing(false)
    onDraft?.(null)
    if (!save) return false
    const next = parse(draft)
    if (next === null) {
      // A cleared field is no answer rather than a wrong one: the old value
      // stands without comment. Anything typed gets the reason.
      setRefused(draft.trim() !== '')
      return false
    }
    onChange(next)
    return true
  }

  const noun = label.startsWith('kg') ? 'Gewicht' : 'Wiederholungen'
  return (
    <div className={`field-num${editing ? ' is-editing' : ''}${value === null ? ' is-blank' : ''}`}>
      {editing ? (
        <input
          ref={input}
          type="text"
          inputMode={decimals ? 'decimal' : 'numeric'}
          enterKeyHint={enterHint}
          className="field-num__entry"
          aria-label={ariaLabel}
          value={draft}
          onChange={(e) => {
            setDraft(e.target.value)
            onDraft?.(parse(e.target.value))
          }}
          onKeyDown={(e) => {
            if (e.key === 'Enter') {
              e.preventDefault()
              if (commit(true)) onEnter?.()
            } else if (e.key === 'Escape') { e.preventDefault(); commit(false) }
          }}
          onBlur={() => commit(true)}
        />
      ) : (
        <button type="button" className="field-num__val"
          aria-label={ariaLabel} onClick={openEntry}>
          {value === null ? null : de(value, decimals)}
        </button>
      )}
      {/* The label turns into the reason while a typed number is refused --
          under the number that was refused, and read out once. */}
      <span className={`field-num__lbl${refused ? ' is-refused' : ''}`} aria-live="polite">
        {refused && refusedHint ? refusedHint : label}
      </span>
      <span className="field-num__keys">
        <button type="button" className="field-num__key"
          aria-label={`${noun} verringern`} disabled={value === null}
          onClick={() => bump(-1)}>−</button>
        <button type="button" className="field-num__key"
          aria-label={`${noun} erhöhen`}
          onClick={() => bump(1)}>+</button>
      </span>
    </div>
  )
})
