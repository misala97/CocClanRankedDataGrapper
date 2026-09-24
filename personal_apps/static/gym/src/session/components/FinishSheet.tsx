import { Sheet } from './Sheet'
import { useSheets } from '../stores'

interface Props {
  volume: number
  setsDone: number
  setsTotal: number
  startedAt: string
  /** Waiting for writes still on their way before leaving -- see the
   *  island's onFinish. */
  finishing?: boolean
  onFinish(): void
  onDiscard(): void
}

/**
 * The pre-debrief beat: what the session became, then one decision.
 *
 * This replaces a native confirm() -- the app's most emotionally loaded
 * transition rendered in browser chrome the design cannot style, with the two
 * most consequential buttons at an unpredictable position. The native
 * <dialog> underneath keeps everything the confirm() did right for assistive
 * tech: platform focus trap, Esc, backdrop.
 *
 * "Abbrechen" dismisses; the primary states the decision. An empty workout is
 * told it will not be kept -- honestly, not alarmingly -- and "verwerfen" is
 * the only way out: a workout with nothing lifted is never filed (D5, G-023;
 * the server refuses to finish one). Open sets are named with what finishing
 * does to them, deletes them (D5, G-010), and "Zurück zum Workout" is the
 * other answer, spelled out beside it rather than left to the header's
 * "Abbrechen".
 */
export function FinishSheet({
  volume, setsDone, setsTotal, startedAt, finishing = false, onFinish, onDiscard,
}: Props) {
  // Subscribed so the minutes are computed when the sheet OPENS, not when the
  // page first rendered.
  const isOpen = useSheets((s) => s.openId === 'sheet-finish')
  const close = useSheets((s) => s.close)
  const open = setsTotal - setsDone
  // sets_done is counts(), the rule gym_discard_session refuses by -- done
  // sets on a skipped or replaced exercise included -- so this never offers
  // a discard the server would refuse (G-131).
  const empty = setsDone === 0
  const minutes = isOpen
    ? Math.max(0, Math.floor((Date.now() - new Date(`${startedAt}Z`).getTime()) / 60000))
    : 0

  return (
    <Sheet id="sheet-finish" title="Workout beenden" closeLabel="Abbrechen">
      <div className="finish-sum">
        {empty ? (
          <p className="finish-sum__none">
            Kein Satz erfasst — ein leeres Workout wird nicht gespeichert.
          </p>
        ) : (
          <>
            <span className="finish-sum__vol">
              {Math.round(volume).toLocaleString('de-DE')}
              <small>kg bewegt</small>
            </span>
            <span className="finish-sum__meta">
              {`${setsDone} von ${setsTotal} Sätzen erledigt · ${minutes < 1 ? '< 1' : minutes} min`}
            </span>
            {open > 0 && (
              <p className="finish-sum__open">
                {open === 1 ? 'Ein offener Satz wird gelöscht.' : `${open} offene Sätze werden gelöscht.`}
              </p>
            )}
          </>
        )}
      </div>
      {finishing ? (
        // A set write was still on its way. Leaving now lost it, so the sheet
        // waits for the answer and says so.
        <button type="button" className="btn btn--live btn--block" disabled>
          Speichert noch…
        </button>
      ) : (
        <>
          {empty ? (
            <button type="button" className="btn btn--live btn--block" onClick={onDiscard}>
              Workout verwerfen
            </button>
          ) : (
            <button type="button" className="btn btn--live btn--block" onClick={onFinish}>
              Beenden
            </button>
          )}
          {(empty || open > 0) && (
            <button type="button" className="btn btn--ghost btn--block" onClick={close}>
              Zurück zum Workout
            </button>
          )}
        </>
      )}
    </Sheet>
  )
}
