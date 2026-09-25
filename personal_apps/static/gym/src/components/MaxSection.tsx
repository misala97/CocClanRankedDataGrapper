import type { MouseEvent } from 'react'
import type { E1rmPR, E1rmTrend, SessionRow, Stair, StairCol } from '../types'
import { dayDate, kg1, kgSetting, signedKg1 } from '../format'
import { RecordStair } from './RecordStair'

interface Props {
  exerciseId: number
  /** Null: no set of 1 to 12 reps above 0 kg to estimate from (G-038). */
  record: E1rmPR | null
  /** Some set had a weight, so a missing record means high reps only. */
  weighted: boolean
  sinceRecord: number | null
  stalled: boolean
  trend: E1rmTrend | null
  stairs: Stair[]
  pills: number[]
  /** The pill shown; null is "Alle". */
  selected: number | null
  onSelect: (position: number | null) => void
  rowOf: (col: StairCol) => SessionRow | undefined
}

/** "Seit 3 Workouts ohne Rekord." and the trend -- or, while the lift is
 *  stalled, the count alone (D9 round 1): a rising trend beside a stall
 *  reads as a contradiction, and the count is what matters then. */
function Drift({ since, stalled, trend }: { since: number | null; stalled: boolean; trend: E1rmTrend | null }) {
  const drought = since !== null && since >= 1
    ? `Seit ${since} ${since === 1 ? 'Workout' : 'Workouts'} ohne Rekord.` : null
  if (stalled && drought !== null) {
    return <p className="exdrift"><span className="is-stall">{drought}</span></p>
  }
  const pace = !stalled && trend !== null ? trend : null
  if (drought === null && pace === null) return null
  return (
    <p className="exdrift">
      {drought}
      {drought !== null && pace !== null && ' '}
      {pace !== null && (
        <>
          {`Trend der letzten ${pace.workouts} Workouts: `}
          <b>{`${signedKg1(pace.per_month)} kg im Monat`}</b>.
        </>
      )}
    </p>
  )
}

/**
 * "Geschätztes Maximum (1RM)" (D9): the record and the drought in words,
 * then the Rekordtreppe. The pills lens the stair alone -- every stair came
 * with the page, so a pill is a swap, not a fetch -- and they stay links, so
 * a pill opens in a new tab or without JavaScript as what it says. Default
 * "Alle"; a slot with fewer than three workouts gets no pill (G-036).
 *
 * With no record the section still stands, saying why: it is where the page
 * names the 1RM in full before the log says "1RM" (D16).
 */
export function MaxSection(props: Props) {
  const { exerciseId, record, stairs, pills, selected, onSelect } = props
  const stair = stairs.find((s) => s.position === selected) ?? stairs[0]
  const pick = (position: number | null) => (event: MouseEvent<HTMLAnchorElement>) => {
    // A modified click is the link's: a new tab or window, as it says.
    if (event.button !== 0 || event.metaKey || event.ctrlKey || event.shiftKey || event.altKey) return
    event.preventDefault()
    onSelect(position)
  }
  return (
    <section className="exsec" aria-labelledby="sec-1rm">
      <h2 className="exsec__h" id="sec-1rm">Geschätztes Maximum (1RM)</h2>
      <p className="exsec__in">
        Wie viel du für eine Wiederholung schaffen würdest, geschätzt aus dem besten Satz jedes
        Workouts.
      </p>
      {record !== null ? (
        <p className="exrec">
          {/* Gold only for a record: while the debut holds the best, it
              beat nothing (D3) and is the best so far, no more. */}
          {record.is_record && <span className="exrec__dot" aria-hidden="true" />}
          <span>
            {record.is_record ? 'Rekord ' : 'Bestwert '}<b>{`${kg1(record.e1rm)} kg`}</b>
            {`, aus ${kgSetting(record.weight)} kg × ${record.reps} am ${dayDate(record.started_at)}`}
          </span>
        </p>
      ) : (
        <p className="exrec">
          {props.weighted
            ? 'Noch kein Rekord: geschätzt wird nur aus Sätzen mit 1 bis 12 Wiederholungen.'
            : 'Noch kein Rekord — bisher nur Sätze ohne Gewicht.'}
        </p>
      )}
      <Drift since={props.sinceRecord} stalled={props.stalled} trend={props.trend} />
      {pills.length > 0 && (
        <nav className="pills expills" aria-label="Nach Reihenfolge im Workout">
          <a className={`pill${selected === null ? ' is-on' : ''}`} href={`/gym/exercises/${exerciseId}`}
            aria-current={selected === null ? 'true' : undefined} onClick={pick(null)}>Alle</a>
          {pills.map((position) => (
            <a key={position} className={`pill${selected === position ? ' is-on' : ''}`}
              href={`/gym/exercises/${exerciseId}?position=${position}`}
              aria-current={selected === position ? 'true' : undefined} onClick={pick(position)}>
              {`Als ${position}. Übung`}
            </a>
          ))}
        </nav>
      )}
      {stair !== undefined && (
        <RecordStair key={stair.position ?? 'alle'} stair={stair} rowOf={props.rowOf} />
      )}
    </section>
  )
}
