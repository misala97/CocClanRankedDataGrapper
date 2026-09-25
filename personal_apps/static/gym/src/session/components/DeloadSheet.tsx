import type { SessionMeta } from '../types'
import { Sheet } from './Sheet'

interface Props {
  session: SessionMeta
  /** Whether the percentage was actually applied to the weights. Not the same
   *  question as is_deload: a session flagged after a set was already logged
   *  keeps its full working weights. */
  deloadApplied: boolean
  deloadPcts: number[]
  deloadDefaultPct: number
  /** Any set completed yet. The depth picker disappears once one has been,
   *  because changing the percentage then would rewrite nothing. */
  hasCompletedSet: boolean
  onToggle(on: boolean, pct: number): void
}

/**
 * A deliberately light session. It gets no colour of its own; a record it
 * sets still counts (D3), but it never counts against progress -- its purpose
 * is that the statistics do not read a planned light week as a plateau.
 */
export function DeloadSheet({
  session, deloadApplied, deloadPcts, deloadDefaultPct, hasCompletedSet, onToggle,
}: Props) {
  const pct = session.deload_pct ?? deloadDefaultPct

  return (
    <Sheet id="sheet-deload" title="Deload">
      <p className="sheet__note">
        Eine bewusst leichte Einheit. Sie bekommt keine eigene Farbe und zählt
        nicht gegen die Stagnation — ihr Zweck ist, dass die Statistik eine
        geplante leichte Woche nicht als Plateau liest. Ein Rekord bleibt ein
        Rekord.
      </p>

      {session.is_deload && !hasCompletedSet && (
        <div className="sheet__group">
          <div className="sheet__picks" role="group" aria-label="Deload-Tiefe">
            {deloadPcts.map((option) => (
              <button
                key={option}
                type="button"
                className={option === session.deload_pct
                  ? 'sheet__pick is-active' : 'sheet__pick'}
                {...(option === session.deload_pct
                  ? { 'aria-current': 'true' as const } : {})}
                onClick={() => onToggle(true, option)}
              >{`${option} %`}</button>
            ))}
          </div>
        </div>
      )}

      {session.is_deload && hasCompletedSet && (
        <p className="sheet__note">
          {deloadApplied
            ? `${pct} % vom Arbeitsgewicht.`
            : 'Nur markiert — die Gewichte bleiben unverändert, weil schon ein Satz erledigt ist.'}
        </p>
      )}

      {/* The sheet's one decision, drawn as a button: as a bare text row it
          read as a line of prose (G-075). Marking is the sheet's purpose;
          ending one is the quiet way back. */}
      <div className="sheet__group">
        <button
          type="button"
          className={session.is_deload ? 'btn btn--ghost btn--block' : 'btn btn--live btn--block'}
          onClick={() => onToggle(!session.is_deload, pct)}
        >
          {session.is_deload ? 'Deload beenden' : 'Als Deload markieren'}
        </button>
      </div>
    </Sheet>
  )
}
