import type { TickState } from '../types'

interface Props {
  states: TickState[]
  done: number
  total: number
}

/**
 * One tick per set in the whole workout, in order, so the strip reads as the
 * session filling up rather than as a chart.
 *
 * The server omits sets belonging to a skipped exercise, so this is shorter
 * than the sum of every exercise's sets -- do not zip it against them.
 *
 * role="img" with the count as its name: the ticks carry no text, and a screen
 * reader given twenty unlabelled spans learns nothing.
 */
export function TickStrip({ states, done, total }: Props) {
  return (
    <div className="ticks" role="img"
      aria-label={`${done} von ${total} Sätzen erledigt`}>
      {states.map((state, i) => (
        <span
          key={i}
          className={state === 'done' ? 'tick is-on' : state === 'now' ? 'tick is-hot' : 'tick'}
        />
      ))}
    </div>
  )
}
