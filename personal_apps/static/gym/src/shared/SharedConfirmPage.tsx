import { useState, type ReactNode } from 'react'
import type { SharedConfirmPayload } from './types'
import { CsrfField } from '../csrf'

/** "trainiert seit 12 min", said once at render -- the card is read in the
 *  seconds before a tap, not watched. */
function runningFor(leader: string, startedAt: string | null): string {
  if (startedAt === null) return `${leader} trainiert gerade`
  const minutes = Math.floor((Date.now() - new Date(`${startedAt}Z`).getTime()) / 60000)
  if (minutes < 1) return `${leader} hat gerade angefangen`
  if (minutes < 60) return `${leader} trainiert seit ${minutes} min`
  return `${leader} trainiert seit ${Math.floor(minutes / 60)} h ${minutes % 60} min`
}

/**
 * The invite is the page: one lifted card, like the one on Start that led
 * here, naming who is training what and ending in Mitmachen. Both partners
 * log the one exercise list, so there is nothing to match; the one choice
 * left -- which of your routines the workout counts as -- is preselected
 * when one clearly fits and otherwise one tap away.
 */
export function SharedConfirmPage({ payload }: { payload: SharedConfirmPayload }) {
  // null means "the reader has not touched it", which keeps the
  // preselection in charge until they do.
  const [routine, setRoutine] = useState<string | null>(null)
  const [open, setOpen] = useState(false)

  const total = payload.exercises.length
  const inWorkout = new Set(payload.exercises.map((exercise) => exercise.id))
  const ranked = payload.templates
    .map((template) => ({
      ...template,
      covered: template.exercise_ids.filter((id) => inWorkout.has(id)).length,
    }))
    .filter((template) => template.covered > 0)
    .sort((a, b) => b.covered - a.covered || a.name.localeCompare(b.name, 'de'))

  // The best-covering routine is preselected when it clearly leads: at least
  // half the workout, and no other routine level with it. A tie is the
  // reader's call -- picking by name would be a guess.
  const best = ranked[0]
  const clearLead = best !== undefined
    && best.covered * 2 >= total
    && (ranked[1] === undefined || ranked[1].covered < best.covered)
  const routineValue = routine ?? (clearLead ? String(best.id) : '')
  const routineName = ranked.find((template) => String(template.id) === routineValue)?.name
  const acceptForm = `confirm-accept-${payload.shared_id}`

  const card = (children: ReactNode) => (
    <div className="lead confirm">
      <span className="lead__due">{runningFor(payload.leader_name, payload.started_at)}</span>
      <span className="lead__name">{payload.session_name ?? 'Workout'}</span>
      {children}
    </div>
  )

  return (
    <section className="sec confirm-sec" aria-labelledby="sec-confirm">
      <h1 className="sr-only" id="sec-confirm">{`Mit ${payload.leader_name} trainieren`}</h1>

      {payload.refusal !== null ? (
        card(
          <>
            <p className="confirm__refusal">{payload.refusal}</p>
            <a className="btn btn--ghost btn--block confirm__back" href="/gym">Zurück</a>
          </>,
        )
      ) : (
        <>
          <form method="post" action={`/gym/shared/${payload.shared_id}/accept`} id={acceptForm}>
            <CsrfField />
            {card(
              <>
                <p className="lead__list">
                  {total > 0
                    ? payload.exercises.map((exercise) => exercise.name).join(' · ')
                    : `Noch keine Übungen — sie kommen dazu, sobald ${payload.leader_name} welche hinzufügt.`}
                </p>
                {routineName !== undefined && (
                  <p className="confirm__ok">Zählt als <b>{routineName}</b>.</p>
                )}
                {/* Said before the button, not after: the server drops it on
                    accept, and it is the one thing on this page that goes away. */}
                {payload.discards_active && (
                  <p className="confirm__note">
                    Dein laufendes Workout ist noch leer — es wird verworfen.
                  </p>
                )}
                <button type="submit" className="lead__go">Mitmachen</button>
              </>,
            )}
          </form>

          <div className="confirm__foot">
            {/* Absent rather than empty: a disclosure that opens onto nothing
                is worse than silence. */}
            {ranked.length > 0 ? (
              <button type="button" className="confirm__more" aria-expanded={open}
                aria-controls="confirm-more" onClick={() => setOpen((value) => !value)}>
                {routineName !== undefined ? 'Routine ändern' : 'Routine wählen'}
                <svg className="confirm__chev" viewBox="0 0 16 16" width="16" height="16"
                  fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round"
                  strokeLinejoin="round" aria-hidden="true">
                  <path d="M6 3.5l4.5 4.5L6 12.5" />
                </svg>
              </button>
            ) : <span />}
            <form method="post" action={`/gym/shared/${payload.shared_id}/decline`}>
              <CsrfField />
              <button type="submit" className="btn btn--ghost btn--sm">Ablehnen</button>
            </form>
          </div>

          {/* Closed, not unmounted: the routine posts with the accept form
              (via `form=`) whether or not the reader ever opens this. */}
          {ranked.length > 0 && (
            <div className="confirm__panel" id="confirm-more" hidden={!open}>
              <div className="field">
                <label className="label" htmlFor="confirm-routine">Zählt bei dir als</label>
                <select className="select" id="confirm-routine" name="template_id"
                  form={acceptForm} value={routineValue}
                  onChange={(e) => setRoutine(e.target.value)}>
                  <option value="">Keine Routine</option>
                  {ranked.map((template) => (
                    <option value={template.id} key={template.id}>
                      {`${template.name} — ${template.covered} von ${total} Übungen`}
                    </option>
                  ))}
                </select>
                <p className="sheet__note">
                  Das Workout erscheint auf deinem Start als Durchgang dieser Routine.
                </p>
              </div>
            </div>
          )}
        </>
      )}
    </section>
  )
}
