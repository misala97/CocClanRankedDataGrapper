import { useState } from 'react'
import type { Partner, PartnerStatus, SessionMeta } from '../types'
import { usePush, useSheets, useWorkoutUi } from '../stores'
import { Sheet } from './Sheet'
import { Icon } from '../../components/Icon'

interface Props {
  session: SessionMeta
  /** Whether a rest is running right now. Rendered live rather than frozen --
   *  see the note on the skip-rest control below. */
  resting: boolean
  partners: Partner[]
  partnerStatus: PartnerStatus[]
  pushSupported: boolean
  onMetaSave(meta: { bodyweightKg: number | null; notes: string }): void
  onSkipRest(): void
  onInvite(partnerId: number): void
  onEnablePush(): void
}

/**
 * Workout-level options. Everything the old screen kept permanently on the
 * page -- deload picks, the reorder lock, add-exercise, save-as-template --
 * lives here, because that layout spent its top third on chrome before showing
 * a single set.
 */
export function SessionSheet({
  session, resting, partners, partnerStatus, pushSupported,
  onMetaSave, onSkipRest, onInvite, onEnablePush,
}: Props) {
  const openSheet = useSheets((s) => s.open)
  const reorderUnlocked = useWorkoutUi((s) => s.reorderUnlocked)
  const setReorder = useWorkoutUi((s) => s.setReorder)
  const close = useSheets((s) => s.close)
  const subscribed = usePush((s) => s.subscribed)

  const [bodyweight, setBodyweight] = useState(
    session.bodyweight_kg === null ? '' : String(session.bodyweight_kg))
  const [notes, setNotes] = useState(session.notes ?? '')
  const [partnerId, setPartnerId] = useState(partners[0]?.id ?? 0)

  return (
    <Sheet id="sheet-session" title="Workout">
      {/* Inside the sheet, never on the start path: the workout begins with
          one tap and that stays true. Both fields stay editable for as long
          as the session exists. */}
      <div className="sheet__group">
        <div className="sheet__row">
          <label className="label" htmlFor="session-bodyweight">Körpergewicht (kg)</label>
          <input type="number" id="session-bodyweight" step="0.1" min="0"
            className="input input--num rest-form__input" placeholder="—"
            value={bodyweight} onChange={(e) => setBodyweight(e.target.value)} />
        </div>
        <div className="field grow">
          <label className="label" htmlFor="session-notes">Notiz</label>
          <input type="text" id="session-notes" className="input"
            placeholder="z. B. nach 8h Schicht"
            value={notes} onChange={(e) => setNotes(e.target.value)} />
        </div>
        <button type="button" className="btn btn--ghost btn--sm"
          onClick={() => onMetaSave({
            bodyweightKg: bodyweight === '' ? null : Number(bodyweight),
            notes,
          })}>Speichern</button>
        <p className="sheet__note">Gilt für dieses Workout.</p>
      </div>

      {/* Ending a rest WITHOUT logging anything, after the last set of an
          exercise, so the notifier does not fire "Pause vorbei" for a rest you
          already walked away from. A workout-level action on a session-level
          timer, which is why it is here and not in the thumb zone.

          Rendered conditionally, which the Jinja version could not do: the
          sheets sat outside #session-body and survived every refresh, so a
          `{% if resting %}` would have frozen at whatever was true on the last
          full page load -- almost always wrong, since rests start and end
          entirely through refreshes. Nothing freezes now. */}
      {resting && (
        <button type="button" className="sheet__act" onClick={onSkipRest}>
          <Icon name="timer" />
          Pause beenden
        </button>
      )}

      <button type="button" className="sheet__act"
        onClick={() => openSheet('sheet-deload')}>
        <Icon name="timer" />
        {session.is_deload ? 'Deload-Markierung ändern' : 'Als Deload markieren'}
      </button>

      <button type="button" className="sheet__act"
        onClick={() => { setReorder(!reorderUnlocked); close() }}>
        <Icon name="swap" />
        <span>{reorderUnlocked ? 'Reihenfolge fertig' : 'Reihenfolge ändern'}</span>
      </button>

      <button type="button" className="sheet__act"
        onClick={() => openSheet('sheet-add-exercise')}>
        <Icon name="plus" />
        Übung hinzufügen
      </button>

      <button type="button" className="sheet__act"
        onClick={() => openSheet('sheet-template')}>
        <Icon name="save" />
        Als Vorlage speichern
      </button>

      {/* Only the browser knows whether THIS device is subscribed. A
          subscription is a browser endpoint, one per device, so a server-side
          "has this user subscribed" hid the button on every other device the
          same person owns and a second phone could never subscribe at all.
          `subscribed === null` is the one-time probe still running: the row
          stays out until it resolves rather than guessing. */}
      {pushSupported && subscribed === false && (
        <div id="notify-row">
          <button type="button" className="sheet__act" onClick={onEnablePush}>
            <Icon name="timer" />
            Pausen-Benachrichtigung auf diesem Gerät aktivieren
          </button>
          <p className="sheet__note">Installiere die App zuerst über „Zum Home-Bildschirm“.</p>
        </div>
      )}

      {/* Three people use this app, so the picker IS the feature. The leader's
          session is never blocked on an answer: it started already, and the
          partner's is seeded from whatever the structure looks like when they
          say yes. */}
      {partners.length > 0 && (
        <div className="field">
          <label className="label" htmlFor="invite-partner">Trainingspartner einladen</label>
          <select className="select" id="invite-partner" value={partnerId}
            onChange={(e) => setPartnerId(Number(e.target.value))}>
            {partners.map((p) => <option value={p.id} key={p.id}>{p.username}</option>)}
          </select>
          <button type="button" className="btn btn--ghost"
            onClick={() => onInvite(partnerId)}>Einladen</button>
        </div>
      )}

      {partnerStatus.map((status) => (
        <p className="shared-status" key={status.username}>
          {`${status.username} ${status.accepted ? 'ist dabei' : 'wurde eingeladen'}`}
        </p>
      ))}
    </Sheet>
  )
}
