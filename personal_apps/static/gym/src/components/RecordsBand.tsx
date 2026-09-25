import type { E1rmPR, SessionRow, WeightPR } from '../types'
import { kg, kg1, shortDate } from '../format'

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
      {/* Each figure stands on its own. The heaviest set is a fact, not a
          record -- a record is an e1RM (D3) -- and either can be missing: no
          set above 0 kg, or none of 1 to 12 reps to estimate from. */}
      {prWeight !== null || prE1rm !== null ? (
        <div className="prs">
          {prWeight !== null && (
            <span className="pr">
              <span className="pr__val">{kg(prWeight.weight)}<small>kg</small></span>
              <span className="label">Schwerster Satz</span>
              {/* One string, not interpolated children -- see ExerciseHeader for
                  why the raster depends on it. */}
              <span className="pr__sub">
                {`${prWeight.reps} Wdh. · Pos. ${prWeight.position} · ${shortDate(prWeight.started_at)}`}
              </span>
            </span>
          )}
          {prE1rm !== null && (
            <span className="pr">
              <span className="pr__val">{kg1(prE1rm.e1rm)}<small>kg</small></span>
              <span className="label">Bestes geschätztes Maximum (1RM)</span>
              <span className="pr__sub">
                {`${kg(prE1rm.weight)} kg × ${prE1rm.reps} · Pos. ${prE1rm.position} · ${shortDate(prE1rm.started_at)}`}
              </span>
            </span>
          )}
        </div>
      ) : (
        <p className="empty">Noch kein Bestwert — bisher nur Sätze ohne Gewicht.</p>
      )}

      {state === 'stagniert' && lastProgression !== null ? (
        <section className="next-time">
          <div className="next-time__lbl">Stagniert</div>
          <p className="next-time__body">
            Seit {sessionsSincePr} Workouts kein neuer Rekord — mehr Gewicht
            oder mehr Wiederholungen versuchen, ausgehend von{' '}
            <b>{kg(lastProgression.best_weight)} kg</b>.
          </p>
        </section>
      ) : sessionsSincePr !== null && sessionsSincePr > 0 ? (
        <p className="exdetail__since">
          {`Seit ${sessionsSincePr} ${sessionsSincePr === 1 ? 'Workout' : 'Workouts'} kein neuer Rekord`}
        </p>
      ) : null}
    </>
  )
}
