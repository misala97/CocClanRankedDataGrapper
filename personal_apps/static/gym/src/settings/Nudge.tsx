interface Props {
  value: number
  /** Under the number: "nach jedem Satz", "kg je Tipp". */
  label: string
  step: number
  min: number
  max: number
  format(value: number): string
  /** What one tap moves, for the keys' names: "15 Sekunden", "0,25 kg". */
  keyNoun: string
  onChange(next: number): void
}

/**
 * A setting you nudge: the live kg stepper's look (.field-num), without its
 * typed entry -- a rest or a step is a few taps from where it stands, and
 * the pills above already hold the usual values.
 */
export function Nudge({ value, label, step, min, max, format, keyNoun, onChange }: Props) {
  // Quarters and seconds are exact in binary, but a sum of them read back
  // from JSON need not be; two places is finer than any step here.
  const to = (next: number) => onChange(Math.round(Math.min(max, Math.max(min, next)) * 100) / 100)
  return (
    <div className="field-num nudge">
      <output className="field-num__val" aria-live="polite">{format(value)}</output>
      <span className="field-num__lbl">{label}</span>
      <span className="field-num__keys">
        <button type="button" className="field-num__key" aria-label={`${keyNoun} weniger`}
          disabled={value - step < min} onClick={() => to(value - step)}>−</button>
        <button type="button" className="field-num__key" aria-label={`${keyNoun} mehr`}
          disabled={value + step > max} onClick={() => to(value + step)}>+</button>
      </span>
    </div>
  )
}
