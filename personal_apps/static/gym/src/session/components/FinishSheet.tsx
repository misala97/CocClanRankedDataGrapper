import { Sheet } from './Sheet'
import { useSheets } from '../stores'

interface Props {
  volume: number
  setsDone: number
  setsTotal: number
  startedAt: string
  onFinish(): void
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
 * told it will not count -- honestly, not alarmingly -- and its confirm is a
 * ghost: quiet-danger, the word carries the weight.
 */
export function FinishSheet({ volume, setsDone, setsTotal, startedAt, onFinish }: Props) {
  // Subscribed so the minutes are computed when the sheet OPENS, not when the
  // page first rendered.
  const isOpen = useSheets((s) => s.openId === 'sheet-finish')
  const open = setsTotal - setsDone
  const empty = setsDone === 0
  const minutes = isOpen
    ? Math.max(0, Math.floor((Date.now() - new Date(`${startedAt}Z`).getTime()) / 60000))
    : 0

  return (
    <Sheet id="sheet-finish" title="Workout beenden" closeLabel="Abbrechen">
      <div className="finish-sum">
        {empty ? (
          <p className="finish-sum__none">Kein Satz erfasst — das Workout zählt nicht.</p>
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
                {open === 1 ? 'Ein Satz noch offen.' : `${open} Sätze noch offen.`}
              </p>
            )}
          </>
        )}
      </div>
      <button type="button"
        className={`btn ${empty ? 'btn--ghost' : 'btn--live'} btn--block`}
        onClick={onFinish}>
        {empty ? 'Trotzdem beenden' : 'Beenden'}
      </button>
    </Sheet>
  )
}
