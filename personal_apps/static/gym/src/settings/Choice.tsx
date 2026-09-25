import { useEffect, useRef, useState } from 'react'
import { Nudge } from './Nudge'

/** How long nudging rests before the value is sent: long enough that five
 *  quick taps are one save, short enough that closing right after still
 *  finds it sent. */
export const NUDGE_SETTLE_MS = 450

export interface NudgeSpec {
  step: number
  min: number
  max: number
  /** Under the number: "nach jedem Satz". */
  label: string
  /** What one tap moves: "15 Sekunden". */
  keyNoun: string
}

interface Props {
  /** The group's accessible name: "Pause", "Schritt". */
  label: string
  values: number[]
  /** The value in force. Its pill is on -- "Andere", showing it, when it is
   *  not one of `values`. Null: nothing is set to show. */
  on: number | null
  /** What the value falls back to, marked under its number so going back is
   *  one tap and never a hidden reset. */
  mark: number | null
  markWord: string
  format(value: number): string
  /** A pill, or the nudge once it settles. `leaving`: the page is going away,
   *  so the write has to outlive it. */
  onPick(value: number, leaving: boolean): void
  nudge: NudgeSpec
}

/**
 * One setting's usual values as pills, and "Andere" for the rest: a stepper
 * under the row, from the value in force. Every pick is the save -- there is
 * no button to forget.
 *
 * Nudging keeps its own draft until it settles, so a run of taps is one
 * write; the draft is sent at once when the row goes away (the sheet closed)
 * or the page does.
 */
export function Choice({ label, values, on, mark, markWord, format, onPick, nudge }: Props) {
  const [nudging, setNudging] = useState(false)
  const [draft, setDraft] = useState<number | null>(null)
  const timer = useRef<number | undefined>(undefined)
  // What the unmount and pagehide flushes read: the effect that registers
  // them runs once, and would otherwise see the first render's draft.
  const pending = useRef<{ value: number; pick: Props['onPick'] } | null>(null)

  const settle = (leaving: boolean) => {
    window.clearTimeout(timer.current)
    const next = pending.current
    pending.current = null
    setDraft(null)
    if (next !== null) next.pick(next.value, leaving)
  }

  useEffect(() => {
    const onHide = () => settle(true)
    window.addEventListener('pagehide', onHide)
    return () => {
      window.removeEventListener('pagehide', onHide)
      settle(false)
    }
  }, [])

  const shown = draft ?? on
  const offRow = shown !== null && !values.includes(shown)

  const pick = (value: number) => {
    window.clearTimeout(timer.current)
    pending.current = null
    setDraft(null)
    setNudging(false)
    onPick(value, false)
  }

  const nudgeTo = (value: number) => {
    setDraft(value)
    pending.current = { value, pick: onPick }
    window.clearTimeout(timer.current)
    timer.current = window.setTimeout(() => settle(false), NUDGE_SETTLE_MS)
  }

  return (
    <>
      <div className="pills pills--fit" role="group" aria-label={label}>
        {values.map((value) => (
          <button key={value} type="button"
            className={value === shown ? 'pill is-on' : 'pill'}
            aria-pressed={value === shown} onClick={() => pick(value)}>
            <span>{format(value)}</span>
            {value === mark && <small>{markWord}</small>}
          </button>
        ))}
        <button type="button" className={offRow ? 'pill is-on' : 'pill'}
          aria-pressed={offRow} aria-expanded={nudging}
          onClick={() => setNudging((open) => !open)}>
          {offRow && shown !== null ? (
            <><span>{format(shown)}</span><small>Andere</small></>
          ) : (
            <span>Andere</span>
          )}
        </button>
      </div>
      {nudging && (
        <Nudge value={shown ?? mark ?? values[0]!} label={nudge.label} step={nudge.step}
          min={nudge.min} max={nudge.max} format={format} keyNoun={nudge.keyNoun}
          onChange={nudgeTo} />
      )}
    </>
  )
}
