import type { E1rmPR, SessionRow, WeightPR } from '../types'
import { kg1, shortDate } from '../format'

interface Props {
  prWeight: WeightPR | null
  prE1rm: E1rmPR | null
  state: string | null
  sessionsSincePr: number | null
  lastProgression: SessionRow | null
}

export function RecordsBand({
  prWeight, prE1rm, state, sessionsSincePr, lastProgression,
}: Props) {
  return (
    <>
      {prWeight !== null && prE1rm !== null ? (
        <div className="prs">
          <span className="pr">
            <span className="pr__val">{kg1(prWeight.weight)}<small>kg</small></span>
            <span className="label">Bestes Gewicht</span>
            {/* One string, not interpolated children -- see ExerciseHeader for
                why the raster depends on it. */}
            <span className="pr__sub">
              {`${prWeight.reps} Wdh. · Pos. ${prWeight.position} · ${shortDate(prWeight.started_at)}`}
            </span>
          </span>
          <span className="pr">
            <span className="pr__val">{kg1(prE1rm.e1rm)}<small>kg</small></span>
            <span className="label">Bestes e1RM</span>
            <span className="pr__sub">
              {`${kg1(prE1rm.weight)} kg × ${prE1rm.reps} · Pos. ${prE1rm.position} · ${shortDate(prE1rm.started_at)}`}
            </span>
          </span>
        </div>
      ) : (
        <p className="empty">Noch kein Rekord — bisher nur Deload-Sätze protokolliert.</p>
      )}

      {state === 'stagniert' && lastProgression !== null ? (
        <section className="next-time">
          <div className="next-time__lbl">Stagniert</div>
          <p className="next-time__body">
            Seit {sessionsSincePr} Workouts kein neuer e1RM-PR — mehr Gewicht
            oder mehr Wiederholungen versuchen, ausgehend von{' '}
            <b>{kg1(lastProgression.best_weight)} kg</b>.
          </p>
        </section>
      ) : sessionsSincePr !== null && sessionsSincePr > 0 ? (
        <p className="exdetail__since">
          {`Seit ${sessionsSincePr} ${sessionsSincePr === 1 ? 'Workout' : 'Workouts'} kein neuer e1RM-PR`}
        </p>
      ) : null}
    </>
  )
}
