import { Fragment } from 'react'
import type { ExerciseGoal, WeightReps } from '../types'
import { kgSetting, setsLine, whenSaid } from '../format'

/** Consecutive sets at one weight, as one line: 85 kg × 11 · 10 · 10. */
function runs(sets: WeightReps[]): { weight: number; reps: number[] }[] {
  const out: { weight: number; reps: number[] }[] = []
  for (const set of sets) {
    const last = out[out.length - 1]
    if (last !== undefined && last.weight === set.weight) last.reps.push(set.reps)
    else out.push({ weight: set.weight, reps: [set.reps] })
  }
  return out
}

/** "9, 10 und 10" */
function spokenList(values: number[]): string {
  return values.length > 1
    ? `${values.slice(0, -1).join(', ')} und ${values[values.length - 1]}`
    : String(values[0])
}

/** Where every set goes when it steps up: one weight for all of them, or
 *  each set's own ("42,5 · 37,5 · 37,5 kg"). */
function stepsTo(ups: number[]): string {
  return new Set(ups).size === 1
    ? `${kgSetting(ups[0]!)} kg`
    : `${ups.map(kgSetting).join(' · ')} kg`
}

/** How the target moves on (D2 P1, B5 stats.next_target): the range's top in
 *  every set, then each set one step up and back to the range's bottom. */
function Rule({ goal }: { goal: ExerciseGoal }) {
  const count = goal.sets.length
  const all = count === 1 ? 'im Satz' : `in allen ${count} Sätzen`
  if (goal.stepped) {
    return (
      <p className="exgoal__rule">
        Eine Stufe höher: bleib dabei, bis du <b>{goal.rep_max}</b> {all} schaffst.
      </p>
    )
  }
  const ups = goal.step_ups ?? []
  const steps = ups.filter((up): up is number => up !== null)
  if (steps.length === 0) {
    // Bodyweight, or the top stop of a known stack: the only way on is reps.
    return (
      <p className="exgoal__rule">
        Schaffst du <b>{goal.rep_max}</b> {all}, kommt {count === 1 ? 'im Satz' : 'in jedem Satz'} eine
        Wiederholung dazu.
      </p>
    )
  }
  if (steps.length < ups.length) {
    // Some sets can go up and some cannot (a 0 kg set, a stack's top stop):
    // next_target steps the ones that can and adds a rep to the rest.
    return (
      <p className="exgoal__rule">
        Schaffst du <b>{goal.rep_max}</b> {all}, gehen die Sätze mit einer nächsten Stufe hoch
        (<b>{stepsTo(steps)}</b>) und beginnen wieder bei <b>{goal.rep_min}</b> Wdh.; bei den anderen
        kommt eine Wiederholung dazu.
      </p>
    )
  }
  return (
    <p className="exgoal__rule">
      Schaffst du <b>{goal.rep_max}</b> {all}, geht {count === 1 ? 'der Satz' : 'jeder Satz'} eine
      Stufe hoch (<b>{stepsTo(steps)}</b>) und beginnt wieder bei <b>{goal.rep_min}</b> Wdh.
    </p>
  )
}

/**
 * "Nächstes Ziel" (D9 A): what to lift next time, set by set, and the
 * workout it builds on. The page's lead -- the question a lifter opens it
 * with is what to do next, not what they once did.
 *
 * One grid line per run of equal weights, so a heavy first set and its
 * back-off sets read as two lines (Michi, M2 09-24). The grid is drawn for
 * the eye and hidden from a screen reader, which gets the sentence instead.
 */
export function GoalPanel({ goal }: { goal: ExerciseGoal }) {
  const lines = runs(goal.sets)
  const spoken = lines.map((line) => {
    const n = line.reps.length
    return `${kgSetting(line.weight)} kg, ${n} ${n === 1 ? 'Satz' : 'Sätze'}: `
      + `${spokenList(line.reps)} Wiederholungen`
  }).join('; ')
  return (
    <section className="exgoal" aria-labelledby="goal-h">
      <h2 className="exgoal__h" id="goal-h">Nächstes Ziel</h2>
      <p className="exgoal__goal">
        <span className="sr-only">{spoken}</span>
        <span className="exgoal__grid" aria-hidden="true">
          {lines.map((line, i) => (
            <Fragment key={i}>
              <span className="exgoal__w">{kgSetting(line.weight)}<small>kg</small></span>
              <span className="exgoal__x">×</span>
              <span className="exgoal__r">
                {line.reps.map((reps, j) => (
                  <Fragment key={j}>{j > 0 && <i>·</i>}<span>{reps}</span></Fragment>
                ))}
              </span>
            </Fragment>
          ))}
        </span>
      </p>
      <p className="exgoal__last">
        <span className="exgoal__last-k">{`Letztes Mal · ${whenSaid(goal.last_at)}`}</span>
        <span className="exgoal__last-v">{setsLine(goal.last_sets)}</span>
      </p>
      <Rule goal={goal} />
    </section>
  )
}
