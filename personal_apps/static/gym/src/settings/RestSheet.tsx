import { useEffect, useRef, useState } from 'react'
import type { RestOverview } from '../types'
import { DialogSheet } from '../components/DialogSheet'
import { Icon } from '../components/Icon'
import { saveRestForAll } from './api'
import { NUDGE_SETTLE_MS } from './Choice'
import { Nudge } from './Nudge'
import { useSaveQueue } from './useSaveQueue'
import { REST_NUDGE, clock } from './values'

interface Props {
  overview: RestOverview
  open: boolean
  onClose(): void
  /** Each answer from the server, so the row under "Übungen" shows it. */
  onSaved(overview: RestOverview): void
}

/** "3 Ausnahmen", "1 Ausnahme". */
export function exceptionCount(overview: RestOverview): string {
  const n = overview.exceptions.length
  if (overview.rest_for_all === null) return `${n} eigene`
  return `${n} ${n === 1 ? 'Ausnahme' : 'Ausnahmen'}`
}

/** The list's range, which "Je nach Übungsart" means: "1:00–3:00". */
export const listRange = (overview: RestOverview) =>
  `${clock(overview.list_min_seconds)}–${clock(overview.list_max_seconds)}`

/**
 * "Deine Pause": one rest after every set of every exercise, or the list's
 * by kind of exercise -- the change lifters make most is the same rest
 * everywhere, and that used to be one field per exercise.
 *
 * An exercise's own rest stays an exception to it, listed here and changed
 * on the exercise. Switching on takes in the ones already equal to it; the
 * rest stay exceptions (exercises.set_rest_for_all).
 */
export function RestSheet({ overview, open, onClose, onSaved }: Props) {
  return (
    <DialogSheet id="sheet-rest" title="Deine Pause" open={open} onClose={onClose}>
      <RestBody overview={overview} onSaved={onSaved} />
    </DialogSheet>
  )
}

function RestBody({ overview, onSaved }: { overview: RestOverview; onSaved: Props['onSaved'] }) {
  const [shown, setShown] = useState(overview)
  const [error, setError] = useState<string | null>(null)
  const confirmed = useRef(overview)
  const send = useSaveQueue<RestOverview>({
    shown: (fresh) => { setShown(fresh); setError(null) },
    saved: (fresh) => { confirmed.current = fresh; onSaved(fresh) },
    failed: (message) => { setShown(confirmed.current); setError(message) },
  })
  const save = (seconds: number | null, leaving = false) =>
    send((keepalive) => saveRestForAll(seconds, keepalive), leaving)

  // The stepper sends once it settles, or at once when the sheet closes or
  // the page goes -- an exception's link is a navigation.
  const timer = useRef<number | undefined>(undefined)
  const pending = useRef<number | null>(null)
  const settle = (leaving: boolean) => {
    window.clearTimeout(timer.current)
    const seconds = pending.current
    pending.current = null
    if (seconds !== null) save(seconds, leaving)
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

  const forAll = shown.rest_for_all
  const choose = (on: boolean) => {
    if (on === (forAll !== null)) return
    window.clearTimeout(timer.current)
    pending.current = null
    const seconds = on ? shown.start_seconds : null
    setShown((current) => ({ ...current, rest_for_all: seconds }))
    save(seconds)
  }
  const nudge = (seconds: number) => {
    setShown((current) => ({ ...current, rest_for_all: seconds }))
    pending.current = seconds
    window.clearTimeout(timer.current)
    timer.current = window.setTimeout(() => settle(false), NUDGE_SETTLE_MS)
  }

  return (
    <>
      <p className="sheet__note">Nach jedem Satz, für alle deine Übungen.</p>
      {error !== null && <p className="setting__error" role="alert">{error}</p>}

      <div className="sorts sorts--sheet" role="group" aria-label="Pause">
        <button type="button" className={forAll !== null ? 'sort is-on' : 'sort'}
          aria-pressed={forAll !== null} onClick={() => choose(true)}>Eine für alle</button>
        <button type="button" className={forAll === null ? 'sort is-on' : 'sort'}
          aria-pressed={forAll === null} onClick={() => choose(false)}>Je nach Übungsart</button>
      </div>

      {forAll !== null && (
        <Nudge value={forAll} label="nach jedem Satz" step={REST_NUDGE}
          min={shown.min_seconds} max={shown.max_seconds} format={clock}
          keyNoun="15 Sekunden" onChange={nudge} />
      )}
      <p className="sheet__note">
        {`${forAll !== null ? 'Je nach Übungsart wären es' : 'Die Liste nimmt je nach Übung'} `
          + `${clock(shown.list_min_seconds)} bis ${clock(shown.list_max_seconds)} — `
          + 'Kreuzheben mehr, Curls weniger.'}
      </p>

      <div className="sheet__group">
        <div className="sheet__group-head">
          <span className="label">{forAll !== null ? 'Ausnahmen' : 'Eigene Pausen'}</span>
        </div>
        {shown.exceptions.length === 0 ? (
          <p className="sheet__note">
            {forAll !== null
              ? `Keine — jede deiner Übungen pausiert ${clock(forAll)}.`
              : 'Keine. Eine eigene Pause stellst du bei der Übung ein.'}
          </p>
        ) : shown.exceptions.map((exception) => (
          <a key={exception.exercise_id} className="sheet-row"
            href={`/gym/exercises/${exception.exercise_id}#einstellungen`}>
            <span className="sheet-row__main">
              <span className="sheet-row__name">{exception.name}</span>
              <span className="sheet-row__meta">Eigene Pause bei der Übung</span>
            </span>
            <span className="sheet-row__val">{clock(exception.rest_seconds)}</span>
            <span className="sheet-row__chev"><Icon name="forward" /></span>
          </a>
        ))}
      </div>
    </>
  )
}
