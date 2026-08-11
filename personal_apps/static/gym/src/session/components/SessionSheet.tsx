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
      {/* Actions first: they are what a ⋯ is opened for mid-set. Each row is
          the app's own list grammar -- icon tile, strong name, quiet meta line
          answering the question the bare label always raised. */}
      <div className="sheet__group">
        {/* Ending a rest WITHOUT logging anything, after the last set of an
            exercise, so the notifier does not fire "Pause vorbei" for a rest
            you already walked away from. A workout-level action on a
            session-level timer, which is why it is here and not in the thumb
            zone. Rendered conditionally, which the Jinja version could not do:
            its sheets survived every refresh, so `{% if resting %}` froze at
            the last full page load. Nothing freezes now. */}
        {resting && (
          <button type="button" className="sheet-row" onClick={onSkipRest}>
            <span className="sheet-row__lead"><Icon name="timer" /></span>
            <span className="sheet-row__main">
              <span className="sheet-row__name">Pause beenden</span>
              <span className="sheet-row__meta">Ohne Satz — es kommt keine Benachrichtigung mehr.</span>
            </span>
          </button>
        )}

        <button type="button" className="sheet-row"
          onClick={() => { setReorder(!reorderUnlocked); close() }}>
          <span className="sheet-row__lead"><Icon name="swap" /></span>
          <span className="sheet-row__main">
            <span className="sheet-row__name">
              {reorderUnlocked ? 'Reihenfolge fertig' : 'Reihenfolge ändern'}
            </span>
            <span className="sheet-row__meta">Übungen per Ziehen sortieren.</span>
          </span>
        </button>

        <button type="button" className="sheet-row"
          onClick={() => openSheet('sheet-add-exercise')}>
          <span className="sheet-row__lead"><Icon name="plus" /></span>
          <span className="sheet-row__main">
            <span className="sheet-row__name">Übung hinzufügen</span>
            <span className="sheet-row__meta">Aus dem Katalog oder neu anlegen.</span>
          </span>
        </button>

        <button type="button" className="sheet-row"
          onClick={() => openSheet('sheet-deload')}>
          <span className="sheet-row__lead"><Icon name="deload" /></span>
          <span className="sheet-row__main">
            <span className="sheet-row__name">
              {session.is_deload ? 'Deload-Markierung ändern' : 'Als Deload markieren'}
            </span>
            <span className="sheet-row__meta">Bewusst leichter — zählt nicht gegen deinen Schnitt.</span>
          </span>
        </button>

        <button type="button" className="sheet-row"
          onClick={() => openSheet('sheet-template')}>
          <span className="sheet-row__lead"><Icon name="save" /></span>
          <span className="sheet-row__main">
            <span className="sheet-row__name">Als Vorlage speichern</span>
            <span className="sheet-row__meta">Diese Übungsliste als Routine für Start.</span>
          </span>
        </button>

        {/* Only the browser knows whether THIS device is subscribed. A
            subscription is a browser endpoint, one per device, so a
            server-side "has this user subscribed" hid the button on every
            other device the same person owns. `subscribed === null` is the
            one-time probe still running: the row stays out until it resolves
            rather than guessing. */}
        {pushSupported && subscribed === false && (
          <div id="notify-row">
            <button type="button" className="sheet-row" onClick={onEnablePush}>
              <span className="sheet-row__lead"><Icon name="bell" /></span>
              <span className="sheet-row__main">
                <span className="sheet-row__name">Pausen-Benachrichtigung</span>
                <span className="sheet-row__meta">Auf diesem Gerät, wenn die Pause endet.</span>
              </span>
            </button>
            <p className="sheet__note">Installiere die App zuerst über „Zum Home-Bildschirm“.</p>
          </div>
        )}
      </div>

      {/* Inside the sheet, never on the start path: the workout begins with
          one tap and that stays true. Both fields stay editable for as long
          as the session exists. */}
      <div className="sheet__group">
        <div className="sheet__group-head">
          <span className="label">Dieses Workout</span>
        </div>
        <div className="field">
          <label className="label" htmlFor="session-bodyweight">Körpergewicht (kg)</label>
          <input type="number" id="session-bodyweight" step="0.1" min="0"
            className="input input--num" placeholder="—"
            value={bodyweight} onChange={(e) => setBodyweight(e.target.value)} />
        </div>
        <div className="sheet__save-row">
          <div className="field">
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
        </div>
      </div>

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
