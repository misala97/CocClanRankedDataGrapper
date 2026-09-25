import type { WeightRow } from '../types'
import { dayDate, kgSetting } from '../format'

/**
 * "Wiederholungen je Gewicht" (D9 A): the heaviest weights lifted, how far
 * each one went, in how many workouts, and since when. A real table: it is
 * read down its columns -- the ladder of weights and the reps each reached.
 */
export function WeightTable({ weights }: { weights: WeightRow[] }) {
  return (
    <section className="exsec" aria-labelledby="sec-reps">
      <h2 className="exsec__h" id="sec-reps">Wiederholungen je Gewicht</h2>
      <table className="exweights">
        <thead>
          <tr>
            <th scope="col">Gewicht</th>
            <th scope="col">Meiste Wdh.</th>
            <th scope="col">Workouts</th>
            <th scope="col">Zuerst</th>
          </tr>
        </thead>
        <tbody>
          {weights.map((row) => (
            <tr key={row.weight}>
              <th scope="row">{`${kgSetting(row.weight)} kg`}</th>
              <td className="exweights__best">{row.reps}</td>
              <td>{row.workouts}</td>
              <td>{dayDate(row.first_at)}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </section>
  )
}
