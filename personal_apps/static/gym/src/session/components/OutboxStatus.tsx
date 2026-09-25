import { useOutbox } from '../stores'

/**
 * What the phone still holds for the server, said calmly (B6, D6-A).
 *
 * A set logged with no signal is not lost any more: it stays on the card,
 * marked, kept on the phone, and is sent again and again until it lands. That
 * is not an alarm, so it is not the red banner, which is left for what did
 * NOT keep: a refused value, a lost swap, a login that ran out. Shown only
 * once a try has failed -- a write out for a moment is no news.
 *
 * In the flow under the header rather than docked over the thumb zone: the
 * banner and the undo toast already share the bottom edge.
 */
export function OutboxStatus({ onSendNow, onReload }: { onSendNow(): void; onReload(): void }) {
  const state = useOutbox((s) => s.state)
  const count = useOutbox((s) => s.count)
  const finishRefused = useOutbox((s) => s.finishRefused)
  if (count === 0 || (state !== 'waiting' && state !== 'blocked')) return null
  const changes = count === 1 ? '1 Änderung' : `${count} Änderungen`

  return (
    <div className="outbox" role="status">
      <p className="outbox__txt">
        {/* Blocked: only a fresh page sends them. */}
        <b>{state === 'blocked' ? 'Wartet auf Neuladen' : 'Wartet auf Verbindung'}</b>
        {` · ${changes} auf diesem Handy`}
        {finishRefused && (
          <span className="outbox__why">Beenden geht, sobald alles gespeichert ist.</span>
        )}
      </p>
      {state === 'waiting' && (
        <button type="button" className="outbox__send" onClick={onSendNow}>Jetzt senden</button>
      )}
      {/* Here as well as on the banner: hidden with "Ausblenden", the banner
          took the only way to the fresh page with it -- and the installed app
          has no reload of its own (B6 re-review). */}
      {state === 'blocked' && (
        <button type="button" className="outbox__send" onClick={onReload}>Neu laden</button>
      )}
    </div>
  )
}
