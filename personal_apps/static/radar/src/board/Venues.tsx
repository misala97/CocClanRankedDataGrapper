import { sourceLabel } from '../format'

/** Which venues are talking about this ticker.
 *
 *  Fixed slots in the payload's source order, lit or dim -- not a count and
 *  not a list. A variable-length list cannot be read down a column, and the
 *  question here is WHICH venues agree, which a number cannot answer: one
 *  finance-native board and one general network saying the same thing is a
 *  very different reading from two crypto channels doing it.
 *
 *  Each slot carries its own label. The state is conveyed by colour alone,
 *  which is exactly the case that needs a text alternative.
 */
export function Venues({ all, lit }: { all: string[]; lit: string[] }) {
  return (
    <span className="venues">
      {all.map((source) => {
        const on = lit.includes(source)
        return (
          <i key={source} className={on ? 'venue on' : 'venue'} role="img"
             aria-label={`${sourceLabel(source)}: ${on ? 'talking' : 'quiet'}`} />
        )
      })}
    </span>
  )
}
