import type { LiveSet } from '../types'
import { Icon } from '../../components/Icon'
import { kg } from '../../format'
import { useWaitingFor } from '../stores'

interface Props {
  set: LiveSet
  /** 1-based position within its exercise, for the accessible name. */
  ordinal: number
  isRecord: boolean
  /** The one set the steppers are bound to. */
  isNext: boolean
  /** The steppers' numbers, for the open chip they are bound to: what
   *  "Satz geschafft" will log, shown in the plan's place (G-054). */
  now?: { weight: number | null; reps: number | null }
  isUnilateral: boolean
  /** Its write is kept on the phone until the connection is back (B6). A
   *  mark, never a lock: the chip stays tappable, and what it does next is
   *  queued behind. */
  waiting?: boolean
  onToggle(setId: number, completed: boolean): void
}

/**
 * One set chip: plain = offen, tinted with a tick = erledigt, gold = ein Rekord,
 * outlined warm = the one you are about to do.
 *
 * Every chip with numbers shows the same weight-times-reps (a blank planned
 * set is named instead, see below). A filled chip is the result it
 * was logged at, an outlined chip is the plan it is prefilled for -- without
 * the plan the lifter at the machine had to remember last week's numbers just
 * to decide whether to add weight, which is the one thing a tracker exists to
 * do for them. The ringed chip, the one the steppers are bound to, shows the
 * steppers: what the tap on "Satz geschafft" will log (G-054).
 */
export function SetRow({
  set: stored, ordinal, isRecord, isNext, now, isUnilateral, waiting = false, onToggle,
}: Props) {
  const waitingFor = useWaitingFor()
  const mark = waiting ? ' is-waiting' : ''
  const said = waiting ? ` — ${waitingFor}` : ''
  const set = isNext && !stored.completed && now !== undefined ? { ...stored, ...now } : stored
  // A planned set still waiting for its numbers (an exercise with no history)
  // is named, not numbered: an invented "20,0 × 8" read as advice. Only ever
  // an open set -- a logged one always has both.
  if (set.weight === null || set.reps === null) {
    const missing = set.weight === null && set.reps === null
      ? 'Zahlen' : set.weight === null ? 'Gewicht' : 'Wdh.'
    return (
      <button type="button" className={`set is-blank${isNext ? ' is-now' : ''}${mark}`}
        aria-label={`Satz ${ordinal}, noch ohne ${missing}${said} — antippen zum Auswählen`}
        onClick={() => onToggle(set.id, true)}>
        {`Satz ${ordinal}`}
      </button>
    )
  }

  const weight = kg(set.weight)
  const perSide = isUnilateral ? ' je Seite' : ''
  const amount = `${weight} kg${perSide} mal ${set.reps}`

  // The two fills are 1.03:1 apart in the dark theme, and this label used to
  // be byte-identical to a logged set's -- so the rarest state in the app did
  // not exist for a screen reader at all.
  const ariaLabel = isRecord
    ? `Satz ${ordinal} — Rekord, ${amount}${said} — antippen zum Zurücksetzen`
    : set.completed
      ? `Satz ${ordinal} erledigt, ${amount}${said} — antippen zum Zurücksetzen`
      : `Satz ${ordinal}, geplant ${weight} kg${perSide} mal ${set.reps}${said} — antippen zum Auswählen`

  const className = isRecord
    ? 'set is-record'
    : set.completed
      ? 'set is-done'
      : isNext ? 'set is-now' : 'set'

  return (
    <button
      type="button"
      className={`${className}${mark}`}
      aria-label={ariaLabel}
      // States the state it wants, not "flip me" -- see
      // gym_toggle_set_complete, which is idempotent precisely because the
      // client names its target rather than asking for an inversion. The
      // live panel reads `true` on an open chip as "pick this one" rather
      // than "log it": the steppers decide the numbers, not the plan.
      onClick={() => onToggle(set.id, !set.completed)}
    >
      {/* A logged set is a settled fact: a tint and a tick, not the solid
          fill that outweighed the next set -- in dark the brightest thing on
          the card (G-112). The next set's ring leads the row now. */}
      {className === 'set is-done' && <Icon name="check" />}
      {`${weight} × ${set.reps}`}
    </button>
  )
}
