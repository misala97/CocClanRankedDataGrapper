import type { LiveSet } from '../types'
import { kg1 } from '../../format'

interface Props {
  set: LiveSet
  /** 1-based position within its exercise, for the accessible name. */
  ordinal: number
  isRecord: boolean
  /** The one set the steppers are bound to. */
  isNext: boolean
  isUnilateral: boolean
  /** True while this set's write is in flight. */
  busy?: boolean
  onToggle(setId: number, completed: boolean): void
}

/**
 * One set chip: outline = offen, filled rose = erledigt, gold = ein Rekord,
 * outlined warm = the one you are about to do.
 *
 * Every chip with numbers shows the same weight-times-reps (a blank planned
 * set is named instead, see below). A filled chip is the result it
 * was logged at, an outlined chip is the plan it is prefilled for -- without
 * the plan the lifter at the machine had to remember last week's numbers just
 * to decide whether to add weight, which is the one thing a tracker exists to
 * do for them.
 */
export function SetRow({
  set, ordinal, isRecord, isNext, isUnilateral, busy = false, onToggle,
}: Props) {
  // A planned set still waiting for its numbers (an exercise with no history)
  // is named, not numbered: an invented "20,0 × 8" read as advice. Only ever
  // an open set -- a logged one always has both.
  if (set.weight === null || set.reps === null) {
    const missing = set.weight === null && set.reps === null
      ? 'Zahlen' : set.weight === null ? 'Gewicht' : 'Wdh.'
    return (
      <button type="button" className={`set is-blank${isNext ? ' is-now' : ''}`}
        aria-label={`Satz ${ordinal}, noch ohne ${missing} — antippen zum Auswählen`}
        disabled={busy} onClick={() => onToggle(set.id, true)}>
        {`Satz ${ordinal}`}
      </button>
    )
  }

  const weight = kg1(set.weight)
  const perSide = isUnilateral ? ' je Seite' : ''
  const amount = `${weight} kg${perSide} mal ${set.reps}`

  // The two fills are 1.03:1 apart in the dark theme, and this label used to
  // be byte-identical to a logged set's -- so the rarest state in the app did
  // not exist for a screen reader at all.
  const ariaLabel = isRecord
    ? `Satz ${ordinal} — Rekord, ${amount} — antippen zum Zurücksetzen`
    : set.completed
      ? `Satz ${ordinal} erledigt, ${amount} — antippen zum Zurücksetzen`
      : `Satz ${ordinal}, geplant ${weight} kg${perSide} mal ${set.reps} — antippen zum Auswählen`

  const className = isRecord
    ? 'set is-record'
    : set.completed
      ? 'set is-done'
      : isNext ? 'set is-now' : 'set'

  return (
    <button
      type="button"
      className={className}
      aria-label={ariaLabel}
      disabled={busy}
      // States the state it wants, not "flip me" -- see
      // gym_toggle_set_complete, which is idempotent precisely because the
      // client names its target rather than asking for an inversion. The
      // live panel reads `true` on an open chip as "pick this one" rather
      // than "log it": the steppers decide the numbers, not the plan.
      onClick={() => onToggle(set.id, !set.completed)}
    >
      {`${weight} × ${set.reps}`}
    </button>
  )
}
