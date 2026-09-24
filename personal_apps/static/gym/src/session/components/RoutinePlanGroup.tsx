import { useEffect, useRef, useState } from 'react'
import type { RoutinePlan } from '../types'
import { Nudge } from '../../settings/Nudge'
import { NUDGE_SETTLE_MS } from '../../settings/Choice'

/** What the server keeps a plan within (stats.MAX_PLAN_SETS, MAX_PLAN_REPS). */
export const MAX_PLAN_SETS = 10
export const MAX_PLAN_REPS = 100

interface Props {
  routineName: string
  plan: RoutinePlan
  /** `leaving`: the page is going away, and the write has to outlive it. */
  onSave(plan: RoutinePlan, leaving: boolean): void
}

/**
 * What the routine keeps for this exercise (D2 P1): how many sets it plans
 * and the rep range its target aims at -- filled from history the first time
 * the routine was started, and changed only here.
 *
 * The rest nudge's manners: a run of taps is one write, sent once the taps
 * settle, or at once when the sheet closes or the page goes.
 */
export function RoutinePlanGroup({ routineName, plan, onSave }: Props) {
  const [draft, setDraft] = useState<RoutinePlan | null>(null)
  const timer = useRef<number | undefined>(undefined)
  // What the unmount and pagehide flushes read: the effect that registers
  // them runs once, and would otherwise see the first render's draft.
  const pending = useRef<{ plan: RoutinePlan; save: Props['onSave'] } | null>(null)

  const settle = (leaving: boolean) => {
    window.clearTimeout(timer.current)
    const next = pending.current
    pending.current = null
    setDraft(null)
    if (next !== null) next.save(next.plan, leaving)
  }

  useEffect(() => {
    const onHide = () => settle(true)
    window.addEventListener('pagehide', onHide)
    return () => {
      window.removeEventListener('pagehide', onHide)
      settle(false)
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  const shown = draft ?? plan
  const change = (next: RoutinePlan) => {
    setDraft(next)
    pending.current = { plan: next, save: onSave }
    window.clearTimeout(timer.current)
    timer.current = window.setTimeout(() => settle(false), NUDGE_SETTLE_MS)
  }

  return (
    <div className="sheet__group">
      <div className="sheet__group-head">
        <span className="label">{`Routine „${routineName}“`}</span>
      </div>
      <div className="plan-steps">
        <Nudge value={shown.sets} label="Sätze" step={1} min={1} max={MAX_PLAN_SETS}
          format={String} keyNoun="Ein Satz"
          onChange={(sets) => change({ ...shown, sets })} />
        <Nudge value={shown.rep_min} label="Wdh. ab" step={1} min={1} max={shown.rep_max}
          format={String} keyNoun="Ab: eine Wiederholung"
          onChange={(rep_min) => change({ ...shown, rep_min })} />
        <Nudge value={shown.rep_max} label="Wdh. bis" step={1} min={shown.rep_min}
          max={MAX_PLAN_REPS} format={String} keyNoun="Bis: eine Wiederholung"
          onChange={(rep_max) => change({ ...shown, rep_max })} />
      </div>
      {/* Two lifetimes, said once: the sets already planned today stay (the
          08-12 rule: nothing rescales mid-workout), the target reads the
          routine and follows at once. */}
      <p className="sheet__note">
        Ab dem nächsten Workout plant die Routine so. Das Ziel heute rechnet schon damit.
      </p>
    </div>
  )
}
