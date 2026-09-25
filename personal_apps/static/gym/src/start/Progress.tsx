import { useRef, useState, type ReactNode, type RefObject } from 'react'
import type { DeloadSuggestion, Progress, ProgressLift, ProgressPoint, Stall } from './types'
import { sincePr } from '../catalogue/format'
import { Icon } from '../components/Icon'
import { dayDate, instant, kg, kg1, roundTo, signedKg1 } from '../format'
import { morphFrom } from '../vt'

/** Each list shows this many rows, the rest behind "Alle N zeigen" (D7). */
export const SHOWN = 5

const plural = (n: number, one: string, many: string) => (n === 1 ? one : many)

/**
 * A list cut to its first SHOWN rows, the rest brought in place on request.
 * The button goes with the click and focus lands on the first row it
 * brought, as the exercise page's Workouts log does.
 */
function ShortList<T>({ items, row }: {
  items: T[]
  row: (item: T, ref: RefObject<HTMLAnchorElement | null> | undefined) => ReactNode
}) {
  const [all, setAll] = useState(false)
  const firstMore = useRef<HTMLAnchorElement>(null)
  const shown = all ? items : items.slice(0, SHOWN)
  return (
    <>
      <div className="rlist">
        {shown.map((item, i) => row(item, i === SHOWN ? firstMore : undefined))}
      </div>
      {!all && items.length > SHOWN && (
        <button type="button" className="sec__more rlist__more"
          onClick={() => {
            setAll(true)
            requestAnimationFrame(() => firstMore.current?.focus())
          }}>
          {`Alle ${items.length} zeigen`}
          <Icon name="down" />
        </button>
      )}
    </>
  )
}

/** The workouts the pace was fitted through, spaced by date -- a break reads
 *  as a gap, and the last point is where the lift stands now. Top to bottom
 *  it spans at least a tenth of the lift's own level, so +0,5 kg a month
 *  does not draw as steep as +7,4. */
export function Spark({ points }: { points: ProgressPoint[] }) {
  const W = 56
  const H = 26
  const PAD = 3
  const at = points.map((p) => instant(p.started_at).getTime())
  const values = points.map((p) => p.e1rm)
  const first = at[0] ?? 0
  const span = (at[at.length - 1] ?? first) - first || 1
  const lo = Math.min(...values)
  const hi = Math.max(...values)
  const range = Math.max(hi - lo, 0.1 * hi) || 1
  const mid = (hi + lo) / 2
  const x = (i: number) => roundTo(PAD + ((at[i] ?? first) - first) / span * (W - 2 * PAD), 1)
  const y = (i: number) => roundTo(H / 2 - ((values[i] ?? mid) - mid) / range * (H - 2 * PAD), 1)
  const last = points.length - 1
  return (
    <svg className="prog__spark" viewBox={`0 0 ${W} ${H}`} aria-hidden="true" focusable="false">
      <polyline points={points.map((_, i) => `${x(i)},${y(i)}`).join(' ')} />
      <circle cx={x(last)} cy={y(last)} r="2.75" />
    </svg>
  )
}

function bestText(lift: ProgressLift): string {
  // "Bestwert" while the first workout holds the best: it beat nothing (D3).
  return `${lift.best.is_record ? 'Rekord' : 'Bestwert'} ${kg1(lift.best.e1rm)} kg am ${dayDate(lift.best.started_at)}`
}

function UpRow({ lift, rowRef }: { lift: ProgressLift; rowRef?: RefObject<HTMLAnchorElement | null> }) {
  return (
    <a ref={rowRef} className="row prog"
      href={`/gym/exercises/${lift.exercise_id}`} onClick={morphFrom('ex')}
      aria-label={`${lift.name}: Trend der letzten ${lift.workouts} Workouts ${signedKg1(lift.per_month)} kg im Monat, ${bestText(lift)}`}>
      <span className="row__main stack">
        <span className="row__name row__name--wrap">{lift.name}</span>
        <span className="row__meta">{bestText(lift)}</span>
      </span>
      <Spark points={lift.points} />
      <span className="prog__trend">
        <span className="prog__v">{signedKg1(lift.per_month)}<small>kg</small></span>
        <span className="row__k">im Monat</span>
      </span>
    </a>
  )
}

/** When the number last moved: the last record, or, for a lift that never
 *  set one, the first workout with a judged set -- that is where its count
 *  starts. "gewertet", because a lift done at 0 kg or for 13+ reps before
 *  then had earlier workouts that judged nothing (G-038). */
function stillSince(item: Stall): string {
  return item.last_record_at !== null
    ? `letzter am ${dayDate(item.last_record_at)}`
    : `erstes gewertetes Workout am ${dayDate(item.since)}`
}

export function StallRow({ item, rowRef }: { item: Stall; rowRef?: RefObject<HTMLAnchorElement | null> }) {
  return (
    <a ref={rowRef} className="row row--top"
      href={`/gym/exercises/${item.exercise_id}`} onClick={morphFrom('ex')}
      aria-label={`${item.name}: ${sincePr(item.sessions_since_pr)}, ${stillSince(item)}, zuletzt ${kg(item.stuck_at)} kg`}>
      <span className="row__main stack">
        <span className="row__name row__name--wrap">{item.name}</span>
        {/* The count runs from the last record in any slot, deloads aside:
            the one count the exercise page and the live card say too. */}
        <span className="row__meta">
          <span className="stall-ink">{sincePr(item.sessions_since_pr, true)}</span>
          {` · ${stillSince(item)}`}
        </span>
      </span>
      {/* The newest attempt's top weight, wherever it stood. */}
      <span className="row__trail row__trail--stack">
        <span className="vol">{kg(item.stuck_at)}<small>kg</small></span>
        <span className="row__k">zuletzt</span>
      </span>
    </a>
  )
}

/** The answer first, as a sentence (D11): how many lifts go up and how many
 *  stand still -- or, before any lift has a pace, what one needs. */
function Lede({ progress, stalls }: { progress: Progress; stalls: number }) {
  const up = progress.up.length
  const measured = 'der Trend ihrer letzten Workouts, gemessen am geschätzten Maximum (1RM).'
  const still = stalls > 0
    ? <><b>{stalls}</b>{` ${plural(stalls, 'steht', 'stehen')} still`}</>
    : 'keine steht still'
  if (up > 0) {
    return (
      <p className="sec__lede">
        <b>{`${up} ${plural(up, 'Übung', 'Übungen')}`}</b>
        {` ${plural(up, 'legt', 'legen')} zu, `}{still}{`: ${measured}`}
      </p>
    )
  }
  if (progress.with_trend > 0) {
    return <p className="sec__lede">{'Keine Übung legt gerade zu, '}{still}{`: ${measured}`}</p>
  }
  const days = progress.min_days === 14 ? 'zwei Wochen' : `${progress.min_days} Tage`
  return (
    <p className="sec__lede">
      {stalls > 0 && (
        <><b>{`${stalls} ${plural(stalls, 'Übung', 'Übungen')}`}</b>
          {` ${plural(stalls, 'steht', 'stehen')} still. `}</>
      )}
      {'Einen Trend zeigt eine Übung ab '}<b>{`${progress.min_workouts} Workouts`}</b>
      {' über '}<b>{days}</b>{', gemessen am geschätzten Maximum (1RM).'}
    </p>
  )
}

/**
 * "Fortschritt" (M3, D7-C): Statistik's question -- komme ich voran? --
 * answered where the lifter lands. Two halves: the lifts going up, ranked
 * by the exercise page's pace (kg per month, D9) with the workouts it was
 * fitted through drawn beside it, then the lifts standing still. A lift sits
 * in one of them at most: the pace is silent while a lift is stalled.
 */
export function Fortschritt({ progress, stalls, deload }: {
  progress: Progress
  stalls: Stall[]
  deload: DeloadSuggestion | null
}) {
  return (
    <section className="sec sec--read" aria-labelledby="sec-fort">
      <h2 className="sec__title" id="sec-fort">Fortschritt</h2>
      <Lede progress={progress} stalls={stalls.length} />

      {progress.up.length > 0 && (
        <>
          <h3 className="sec__sub" id="sub-up">
            Legen zu <span className="sec__subn">{progress.up.length}</span>
          </h3>
          <ShortList items={progress.up}
            row={(lift, ref) => <UpRow lift={lift} rowRef={ref} key={lift.exercise_id} />} />
        </>
      )}

      {stalls.length > 0 && (
        <>
          <h3 className="sec__sub" id="sub-still">
            Steht still <span className="sec__subn">{stalls.length}</span>
          </h3>
          {/* "davon aktiv trainiert": the deload signal counts only lifts
              trained inside the rolling window, while the roster below is
              unfiltered. Unscoped, the note said "4 Übungen stehen still"
              directly above six rows. */}
          {deload !== null && (
            <p className="stall-note">
              <b>{`${deload.count} davon aktiv trainiert`}</b>
              {' — ein Deload könnte fällig sein.'}
            </p>
          )}
          {/* Bounded by count: stall_report is unbounded, and after a layoff
              essentially the whole catalogue qualifies. */}
          <ShortList items={stalls}
            row={(item, ref) => <StallRow item={item} rowRef={ref} key={item.exercise_id} />} />
        </>
      )}
    </section>
  )
}
