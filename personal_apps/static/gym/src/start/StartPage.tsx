import { useEffect, useState, type FormEvent } from 'react'
import type { HeutePayload, Onboarding, RoutineMemory, Stall } from './types'
import { postForm, MutationFailed } from '../api'
import { CsrfField } from '../csrf'
import { enablePush, heartbeatSubscription } from '../push'
import { UndoToast, useUndo } from '../undo'
import { recency, sincePr } from '../catalogue/format'
import { MAX_NAME_CHARS } from '../setInput'
import { useSheets, usePush } from '../session/stores'
import { leaveBySubmit, useSheetHistory } from '../session/useSheetHistory'
import { Sheet } from '../session/components/Sheet'
import { Icon } from '../components/Icon'
import { dayMonth, instant, kg, kg1, shortDate, volume as de } from '../format'
import { morphFrom } from '../vt'

const pad = (n: number) => String(n).padStart(2, '0')

/** One routine back where it stood, into the list as it is now. */
function putBack(now: RoutineMemory[], was: RoutineMemory[], id: number): RoutineMemory[] {
  const at = was.findIndex((r) => r.template_id === id)
  if (at < 0 || now.some((r) => r.template_id === id)) return now
  return [...now.slice(0, at), was[at]!, ...now.slice(at)]
}

/** Elapsed since the running workout started. hh:mm:ss, as GymClock rendered it. */
function useElapsed(startedAt: string): string {
  const [now, setNow] = useState(() => Date.now())
  useEffect(() => {
    const id = setInterval(() => setNow(Date.now()), 1000)
    return () => clearInterval(id)
  }, [])
  const total = Math.max(0, Math.floor((now - instant(startedAt).getTime()) / 1000))
  return `${pad(Math.floor(total / 3600))}:${pad(Math.floor((total % 3600) / 60))}:${pad(total % 60)}`
}

/* A rest window is minutes, not hours: past this, a stale rest_ends_at is
 * treated as "no rest" -- the same ceiling the Jinja resume strip applies. */
const MAX_REST_MS = 900 * 1000

/* A PWA left open overnight re-surfaces showing yesterday's "Zuletzt vor N
 * Tagen" and tonnage. Everything here renders from a server-embedded payload,
 * so past this much time hidden the honest fix is a fresh page. */
const STALE_AFTER_MS = 30 * 60_000

function useReloadWhenStale() {
  useEffect(() => {
    let hiddenAt: number | null = null
    const onVisibility = () => {
      if (document.hidden) { hiddenAt = Date.now(); return }
      if (hiddenAt !== null && Date.now() - hiddenAt > STALE_AFTER_MS) {
        window.location.reload()
      }
      hiddenAt = null
    }
    document.addEventListener('visibilitychange', onVisibility)
    return () => document.removeEventListener('visibilitychange', onVisibility)
  }, [])
}

/** m:ss until the running rest ends, or null when there is none (or the
 *  stamp is stale/expired). Leaving the session mid-rest is exactly when the
 *  countdown matters most and exactly when the session screen is not on
 *  screen to show it. */
function useRestCountdown(restEndsAt: string | null): string | null {
  const [now, setNow] = useState(() => Date.now())
  useEffect(() => {
    if (restEndsAt === null) return
    const id = setInterval(() => setNow(Date.now()), 1000)
    return () => clearInterval(id)
  }, [restEndsAt])
  if (restEndsAt === null) return null
  const left = instant(restEndsAt).getTime() - now
  if (left <= 0 || left > MAX_REST_MS) return null
  const total = Math.ceil(left / 1000)
  return `${Math.floor(total / 60)}:${pad(total % 60)}`
}

function StallRow({ item }: { item: Stall }) {
  return (
    <a className="row row--top" href={`/gym/exercises/${item.exercise_id}`}
      onClick={morphFrom('ex')}>
      <span className="row__main stack">
        <span className="row__name row__name--wrap">{item.name}</span>
        {/* The count runs from the last record in any slot, so the weight
            is the newest attempt's, wherever it stood -- "meist" says the
            slot is the usual one, not the one the weight comes from. */}
        <span className="row__meta">
          {`Meist als ${item.position}. Übung · zuletzt ${kg(item.stuck_at)} kg`}
        </span>
      </span>
      <span className="vtag vtag--stall">{sincePr(item.sessions_since_pr, true)}</span>
    </a>
  )
}

interface RoutineEditProps {
  routine: RoutineMemory
  /** POSTs over fetch and hands back the fresh HeutePayload the route
   *  answers with; the page re-renders from it, no reload. */
  onSave: (url: string, fields: Record<string, string>) => Promise<void>
  /** Hides the routine now, deletes it when the undo window closes. */
  onDelete: (routine: RoutineMemory) => void
}

function RoutineEdit({ routine, onSave, onDelete }: RoutineEditProps) {
  const submit = (url: string) =>
    (event: FormEvent<HTMLFormElement>) => {
      event.preventDefault()
      const form = event.currentTarget
      const fields: Record<string, string> = {}
      new FormData(form).forEach((value, key) => { fields[key] = String(value) })
      void onSave(url, fields).then(() => {
        // The panel is done: the row it edits re-renders around it.
        form.closest('details')?.removeAttribute('open')
      })
    }

  const remove = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault()
    event.currentTarget.closest('details')?.removeAttribute('open')
    onDelete(routine)
  }

  return (
    <details className="lead__edit">
      <summary className="lead__edit-toggle" aria-label={`${routine.name} bearbeiten`}>
        <Icon name="edit" />
      </summary>
      <div className="lead__edit-body">
        <form method="post" action={`/gym/templates/${routine.template_id}/rename`}
          className="lead__edit-form"
          onSubmit={submit(`/gym/templates/${routine.template_id}/rename`)}>
          <CsrfField />
          <input type="text" name="name" defaultValue={routine.name} className="input"
            aria-label={`Neuer Name für ${routine.name}`} required maxLength={MAX_NAME_CHARS} />
          <button type="submit" className="btn btn--ghost btn--sm">Speichern</button>
        </form>
        <form method="post" action={`/gym/templates/${routine.template_id}/delete`}
          onSubmit={remove}>
          <CsrfField />
          <button type="submit" className="btn btn--quiet-danger btn--sm btn--block">
            Löschen
          </button>
        </form>
      </div>
    </details>
  )
}

type PushState = 'on' | 'off' | 'unsupported' | 'unknown'

interface FirstRunProps {
  onboarding: Onboarding
  daysSinceLast: number | null
  push: PushState
  /** Why the last tap did not turn push on. */
  pushError: string | null
  onEnablePush: () => void
  onStartFree: () => void
}

/**
 * An empty account used to land on four empty sections, a setup prompt on
 * top and the only way in as a small text link. This is a real sequence --
 * the order is the content, which is what earns the numbers: train once,
 * keep it as a routine (the one-tap start the rest of the page is built
 * around), then let the phone call the end of a rest. One step at a time
 * wears the lifted plane and the live button.
 */
function FirstRun({
  onboarding, daysSinceLast, push, pushError, onEnablePush, onStartFree,
}: FirstRunProps) {
  const { workouts, last } = onboarding
  const trained = workouts > 0
  const done = (trained ? 1 : 0) + (push === 'on' ? 1 : 0)

  let receipt = ''
  if (last !== null) {
    const when = recency(daysSinceLast)
    const minutes = Math.floor(
      (instant(last.finished_at).getTime() - instant(last.started_at).getTime()) / 60000)
    // Mid-sentence only the adverbs go lower case: "zuletzt gestern", but
    // "zuletzt vor 3 Tagen" -- a whole-string toLowerCase wrote "tagen".
    receipt = workouts > 1
      ? `${workouts} Workouts · zuletzt ${when.replace(/^(Heute|Gestern)/, (word) => word.toLowerCase())}`
      : `${when.charAt(0).toUpperCase()}${when.slice(1)} · ${last.exercises} ${last.exercises === 1 ? 'Übung' : 'Übungen'} · ${minutes < 1 ? '< 1' : minutes} min`
  }

  const dot = (n: number, isDone: boolean) => (
    <span className="onb__dot" aria-hidden="true">{isDone ? <Icon name="check" /> : n}</span>
  )

  return (
    <section className="sec onb-sec" aria-labelledby="sec-onb">
      <div className="sec__head">
        <h2 className="label" id="sec-onb">So fängst du an</h2>
        <span className="sec__sp" />
        <span className="label onb__count">{`${done} von 3`}</span>
      </div>
      <ol className="onb">
        <li className={`onb__step ${trained ? 'is-done' : 'is-now'}`}
          aria-current={trained ? undefined : 'step'}>
          {dot(1, trained)}
          <div className="onb__body">
            <span className="onb__t">
              {trained && <span className="sr-only">Erledigt: </span>}
              Erstes Workout
            </span>
            {trained ? (
              <p className="onb__d">{receipt}</p>
            ) : (
              <>
                <p className="onb__d">Leer starten, Übungen aus der Liste hinzufügen, während du sie machst.</p>
                <form method="post" action="/gym/start">
                  <CsrfField />
                  <button type="submit" className="lead__go">
                    <Icon name="skip" />
                    Workout starten
                  </button>
                </form>
              </>
            )}
          </div>
        </li>

        <li className={`onb__step${trained ? ' is-now' : ''}`}
          aria-current={trained ? 'step' : undefined}>
          {dot(2, false)}
          <div className="onb__body">
            <span className="onb__t">Als Routine speichern</span>
            {trained && last !== null ? (
              <>
                <p className="onb__d">
                  Dann startest du es hier mit einem Tipp — samt Gewichten vom letzten Mal.
                </p>
                <form method="post" action={`/gym/session/${last.session_id}/save_as_template`}
                  className="onb__save">
                  <CsrfField />
                  <input type="hidden" name="next" value="start" />
                  <div className="field grow">
                    <label className="label" htmlFor="onb-name">Name der Routine</label>
                    <input type="text" id="onb-name" name="template_name" className="input"
                      defaultValue={last.name ?? ''} placeholder="z. B. Oberkörper" required
                      maxLength={MAX_NAME_CHARS} />
                  </div>
                  <button type="submit" className="lead__go">Als Routine speichern</button>
                </form>
              </>
            ) : (
              <p className="onb__d">
                Am Ende des Workouts. Danach startest du es hier mit einem Tipp — samt
                Gewichten vom letzten Mal.
              </p>
            )}
          </div>
        </li>

        <li className={`onb__step${push === 'on' ? ' is-done' : ''}`}>
          {dot(3, push === 'on')}
          <div className="onb__body">
            <span className="onb__t">
              {push === 'on' && <span className="sr-only">Erledigt: </span>}
              Pausen-Timer aufs Handy
            </span>
            {push === 'on' ? (
              <p className="onb__d">Auf diesem Gerät aktiv.</p>
            ) : push === 'unsupported' ? (
              <p className="onb__d">
                Füge die App über „Zum Home-Bildschirm“ hinzu und öffne sie von dort — dann
                meldet sich das Handy, wenn die Pause um ist.
              </p>
            ) : (
              <>
                <p className="onb__d">
                  Zum Home-Bildschirm hinzufügen — dann meldet sich das Handy, wenn die Pause
                  um ist.
                </p>
                {push === 'off' && (
                  <button type="button" className="btn btn--ghost btn--sm" onClick={onEnablePush}>
                    Benachrichtigung aktivieren
                  </button>
                )}
                {push === 'off' && pushError !== null && (
                  <p className="flash flash--error" role="alert">{pushError}</p>
                )}
              </>
            )}
          </div>
        </li>
      </ol>

      {/* Step 1 IS the start button until it is done. After it, the checklist
          asks for a save, and the next workout still needs a way in. */}
      {trained && (
        <button type="button" className="start__free" onClick={onStartFree}>
          <Icon name="plus" />
          Freies Workout starten
        </button>
      )}
    </section>
  )
}

export function StartPage({ payload: initial }: { payload: HeutePayload }) {
  // Back closes an open sheet, not the page (G-066).
  useSheetHistory()
  const openSheet = useSheets((s) => s.open)
  const subscribed = usePush((s) => s.subscribed)
  const setSubscribed = usePush((s) => s.setSubscribed)
  const pushError = usePush((s) => s.error)
  // Renaming or deleting a routine answers with the fresh HeutePayload, and
  // the page re-renders from it -- the row changing is the feedback.
  const [payload, setPayload] = useState(initial)
  const [saveError, setSaveError] = useState<string | null>(null)

  const saveRoutine = async (url: string, fields: Record<string, string>) => {
    try {
      setPayload(await postForm<HeutePayload>(url, fields))
      setSaveError(null)
    } catch (error) {
      setSaveError(error instanceof MutationFailed
        ? error.germanMessage
        : 'Speichern fehlgeschlagen.')
    }
  }

  const offerUndo = useUndo((s) => s.offer)
  /** confirm() replaced by delayed commit: the row vanishes now, the DELETE
   *  fires when the undo window closes, Rückgängig just puts the row back --
   *  nothing has reached the server yet. A delete that fails puts it back
   *  too: the routine still exists (G-147). */
  const deleteRoutine = (routine: RoutineMemory) => {
    const before = payload
    const id = routine.template_id
    setPayload((current) => ({
      ...current,
      routines: current.routines.filter((r) => r.template_id !== id),
      templates: current.templates.filter((r) => r.template_id !== id),
    }))
    // Into the page as it is by then, not the page from before the tap: a
    // rename saved inside the window stays saved.
    const restore = () => setPayload((current) => ({
      ...current,
      routines: putBack(current.routines, before.routines, id),
      templates: putBack(current.templates, before.templates, id),
    }))
    offerUndo({
      label: `Routine „${routine.name}“ gelöscht.`,
      undo: restore,
      commit: (keepalive) => {
        postForm<HeutePayload>(`/gym/templates/${id}/delete`, {}, { keepalive })
          .then(setPayload)
          .catch((error) => {
            restore()
            setSaveError(error instanceof MutationFailed
              ? error.germanMessage
              : 'Löschen fehlgeschlagen.')
          })
      },
    })
  }

  const running = payload.active_session_id !== null
  // Nothing on this page can start a workout while one is running: gym_start
  // redirects to the live session, so every "Starten" resolved to "Weiter" --
  // landing you in a DIFFERENT workout than the one you tapped, with no
  // message. The routines stay as reading material; they stop pretending to
  // be actionable.
  const canStart = !running

  const pushSupported = 'serviceWorker' in navigator && 'PushManager' in window
  useEffect(() => {
    if (!pushSupported) { setSubscribed(false); return }
    navigator.serviceWorker.getRegistration('/gym')
      .then((reg) => reg?.pushManager.getSubscription() ?? null)
      .then((sub) => {
        setSubscribed(sub !== null)
        heartbeatSubscription(sub)
      })
      .catch(() => setSubscribed(false))
  }, [pushSupported, setSubscribed])

  // Anchored to the session's start, not the page render: `payload.now` here
  // was the bug that made the card read "00:00:01 läuft" twenty minutes in.
  const elapsed = useElapsed(payload.active_session_started_at ?? payload.now)
  const restLeft = useRestCountdown(payload.active_session_rest_ends_at)
  useReloadWhenStale()
  const lead = payload.routines[0]
  const rest = payload.routines.slice(canStart ? 1 : 0)
  // The checklist is what to do next, and while a workout runs the answer is
  // the running card. Nothing on an account's first run has data yet, so the
  // reading sections wait for the first finished workout instead of
  // announcing four times that they are empty.
  const firstRun = payload.onboarding
  const showChecklist = firstRun !== null && !running
  const nothingToRead = firstRun !== null && firstRun.workouts === 0
  const pushState: PushState = !pushSupported ? 'unsupported'
    : subscribed === null ? 'unknown' : subscribed ? 'on' : 'off'
  const lastWeek = payload.tonnage[payload.tonnage.length - 1]
  const deloadWeeks = payload.tonnage.filter((w) => w.has_deload)

  return (
    <>
      <header className="start__head">
        <div className="start__row">
          <h1 className="start__h">Start</h1>
          <span className="start__sp" />
          <span className="start__date">{shortDate(payload.now)}</span>
        </div>
        <p className="start__pulse">
          {payload.consistency.days_since_last !== null ? (
            <>
              {payload.consistency.days_since_last === 0
                ? <>Zuletzt <b>heute</b></>
                : payload.consistency.days_since_last === 1
                  ? <>Zuletzt <b>gestern</b></>
                  : <>Zuletzt vor <b>{payload.consistency.days_since_last}</b> Tagen</>}
              {' · '}
              {/* The window is said: a rate over the last four weeks read as a
                  lifetime average, and after a break it disagreed with the
                  "Zuletzt vor 20 Tagen" right beside it. */}
              <b>{kg1(payload.consistency.per_week)}</b> Workouts pro Woche
              {` (letzte ${Math.round(payload.consistency.window_days / 7)} Wochen)`}
            </>
          ) : 'Noch keine Workouts protokolliert'}
        </p>
      </header>

      {running && (
        // A workout is already running: nothing else on this page competes
        // with getting back into it.
        <section className="sec" aria-labelledby="sec-laeuft">
          <div className="sec__head"><h2 className="label" id="sec-laeuft">Läuft gerade</h2></div>
          <div className="lead">
            <span className="lead__main stack">
              <span className="lead__name">{payload.active_session_name ?? 'Workout'}</span>
              {payload.active_session_exercise !== null && (
                <span className="lead__ex">{payload.active_session_exercise}</span>
              )}
              <span className="lead__due">
                <b id="heute-elapsed">{elapsed}</b> läuft
                {restLeft !== null && <>{' · Pause '}<b>{restLeft}</b></>}
              </span>
            </span>
            <a href={`/gym/session/${payload.active_session_id}`} className="lead__go">
              <Icon name="skip" />
              Weiter
            </a>
          </div>
        </section>
      )}

      {/* Enabling rest-timer notifications lived only in the options sheet
          during a live workout -- a menu that does not exist until you are
          mid-set, which is neither where you look nor when you would think of
          it. Shown once on a device without a subscription, gone for good
          after the tap. BELOW the running card: a one-time setup prompt must
          not outrank the workout that is happening right now. */}
      {pushSupported && subscribed === false && !showChecklist && (
        <section className="sec notify-prompt" id="notify-start">
          <button type="button" className="notify-prompt__btn"
            onClick={() => { void enablePush(payload.vapid_public_key) }}>
            <Icon name="timer" />
            <span>
              <b>Pausen-Benachrichtigung aktivieren</b>
              <small>Auf diesem Gerät. Installiere die App zuerst über „Zum Home-Bildschirm“.</small>
            </span>
          </button>
          {pushError !== null && (
            <p className="flash flash--error" role="alert">{pushError}</p>
          )}
        </section>
      )}

      {/* Someone is training right now and asked for you. Above the routines
          because it expires: the workout it belongs to is already running. */}
      {payload.pending_invites.map((invite) => (
        <section className="sec" key={invite.shared_id}>
          <div className="invite-card">
            <span className="invite-card__main stack">
              <span className="invite-card__who">{`${invite.leader_name} trainiert`}</span>
              <span className="invite-card__what">{invite.session_name}</span>
            </span>
            <a href={`/gym/shared/${invite.shared_id}/confirm`} className="lead__go">
              Mitmachen
            </a>
          </div>
        </section>
      ))}

      {showChecklist && (
        <FirstRun onboarding={firstRun} daysSinceLast={payload.consistency.days_since_last}
          push={pushState}
          pushError={pushError}
          onEnablePush={() => { void enablePush(payload.vapid_public_key) }}
          onStartFree={() => openSheet('sheet-free')} />
      )}

      {firstRun === null && (
        <section className="sec" aria-labelledby="sec-routinen">
          {saveError !== null && (
            <p className="flash flash--error" role="alert">{saveError}</p>
          )}
          {payload.routines.length > 0 ? (
            <>
              <div className="sec__head">
                <h2 className="label" id="sec-routinen">
                  {canStart ? 'Am längsten her' : 'Routinen'}
                </h2>
              </div>

              {canStart && lead !== undefined ? (
                <div className="lead">
                  <div className="lead__top">
                    <span className="lead__main stack">
                      <span className="lead__due">{recency(lead.days_ago, true)}</span>
                      <span className="lead__name">{lead.name}</span>
                    </span>
                    <RoutineEdit routine={lead} onSave={saveRoutine} onDelete={deleteRoutine} />
                  </div>
                  <p className="lead__list">
                    {lead.exercises.length > 0 ? lead.exercises.join(' · ') : 'Keine Übungen'}
                  </p>
                  {/* The stalls section further down covers every exercise you
                      own. This is the one to watch in the routine you are about
                      to tap, and it is silent when there is none -- which is
                      what makes it worth reading when it appears. */}
                  <LeadWatch lead={lead} stalls={payload.stalls} />
                  <form method="post" action="/gym/start">
                    <CsrfField />
                    <input type="hidden" name="template_id" value={lead.template_id} />
                    <button type="submit" className="lead__go">
                      <Icon name="skip" />
                      Starten
                    </button>
                  </form>
                </div>
              ) : (
                <p className="start__blocked">
                  Ein Workout läuft schon. Beende es, um ein neues zu starten.
                </p>
              )}

              {/* The rest are quiet rows, never a second card. */}
              {rest.map((routine) => (
                <div className="row" key={routine.template_id}>
                  <span className="row__main stack">
                    <span className="row__name row__name--strong">{routine.name}</span>
                    <span className="row__meta row__meta--clip">
                      {recency(routine.days_ago)}
                      {routine.exercises.length > 0 && ` · ${routine.exercises.join(' · ')}`}
                    </span>
                  </span>
                  <span className="row__trail">
                    <RoutineEdit routine={routine} onSave={saveRoutine} onDelete={deleteRoutine} />
                    {canStart && (
                      <form method="post" action="/gym/start">
                        <CsrfField />
                        <input type="hidden" name="template_id" value={routine.template_id} />
                        <button type="submit" className="row__go">Starten</button>
                      </form>
                    )}
                  </span>
                </div>
              ))}
            </>
          ) : (
            <>
              <div className="sec__head"><h2 className="label" id="sec-routinen">Routinen</h2></div>
              <p className="empty">
                Noch keine Routinen. Speichere ein Workout als Routine, um es hier zu sehen.
              </p>
            </>
          )}

          {/* Starting without a template is a real path, but the secondary one. */}
          {canStart && (
            <button type="button" className="start__free"
              onClick={() => openSheet('sheet-free')}>
              <Icon name="plus" />
              Freies Workout starten
            </button>
          )}
        </section>
      )}

      {/* The four reading sections, paired into two columns on desktop by
          KIND: what wants attention on the left, what is reference on the
          right. Not four sections auto-placed into a grid -- auto-placement
          locked section 3 to the tallest section in row 1 and left a 250px
          hole under "Steht still". */}
      {!nothingToRead && (
        <div className="start__read">
          <div className="start__col">
            {payload.stalls.length > 0 && (
              <section className="sec" aria-labelledby="sec-still">
                <div className="sec__head">
                  <h2 className="label" id="sec-still">Steht still</h2>
                  <span className="sec__sp" />
                  <span className="label">
                    {`${payload.stalls.length} ${payload.stalls.length === 1 ? 'Übung' : 'Übungen'}`}
                  </span>
                </div>
                {/* "davon aktiv trainiert": the deload signal counts only lifts
                    trained inside the rolling window, while the roster below is
                    unfiltered. Unscoped, the note said "4 Übungen stehen still"
                    directly above six rows. */}
                {payload.deload_suggestion !== null && (
                  <p className="stall-note">
                    <b>{`${payload.deload_suggestion.count} davon aktiv trainiert`}</b>
                    {' — ein Deload könnte fällig sein.'}
                  </p>
                )}
                {/* Bounded by count: stall_report is unbounded, and after a
                    layoff essentially the whole catalogue qualifies. */}
                {payload.stalls.slice(0, 5).map((item) => (
                  <StallRow item={item} key={item.exercise_id} />
                ))}
                {payload.stalls.length > 5 && (
                  <details className="year">
                    <summary className="year__head">
                      <svg className="group__chev" viewBox="0 0 24 24" fill="none"
                        stroke="currentColor" strokeWidth="3" strokeLinecap="round"
                        strokeLinejoin="round" aria-hidden="true">
                        <path d="M9 5l7 7-7 7" />
                      </svg>
                      <span className="label">{`${payload.stalls.length - 5} weitere`}</span>
                    </summary>
                    {payload.stalls.slice(5).map((item) => (
                      <StallRow item={item} key={item.exercise_id} />
                    ))}
                  </details>
                )}
              </section>
            )}

            <section className="sec" aria-labelledby="sec-tonnage">
              <div className="sec__head">
                <h2 className="label" id="sec-tonnage">Tonnage pro Woche</h2>
                <span className="sec__sp" />
                <span className="label">8 Wochen</span>
              </div>
              {payload.tonnage_peak > 0 ? (
                <>
                  {/* Every bar states its value. The chart carried no numbers at
                      all -- no scale, no per-bar figure, no accessible text --
                      so its whole magnitude dimension existed only as relative
                      height. The peak is named so the heights have something to
                      be read against. */}
                  <p className="vbars__peak">
                    <span className="label">Höchste Woche</span>{' '}
                    <b>{de(payload.tonnage_peak)}</b> kg
                  </p>
                  <div className="vbars" role="list">
                    {payload.tonnage.map((week) => (
                      <span key={week.week_start}
                        className={`vbar${week.is_current ? ' is-live' : ''}${week.has_deload ? ' vbar--deload' : ''}`}
                        role="listitem"
                        aria-label={`${week.is_current ? 'Diese Woche' : `Woche ab ${dayMonth(week.week_start)}`}: ${de(week.volume)} kg${week.has_deload ? ', mit Deload-Workout' : ''}`}
                        style={{ blockSize: `${Math.round((week.volume / payload.tonnage_peak) * 1000) / 10}%` }} />
                    ))}
                  </div>
                  <div className="vbars__axis" aria-hidden="true">
                    {payload.tonnage.map((week) => (
                      <span key={week.week_start}>
                        {week.is_current ? 'Jetzt' : dayMonth(week.week_start)}
                      </span>
                    ))}
                  </div>
                  <p className="start__note">
                    {`${de(lastWeek?.volume ?? 0)} kg diese Woche bisher — läuft noch.`}
                    {deloadWeeks.length > 0 && ' Schraffiert: Woche mit Deload-Workout.'}
                  </p>
                </>
              ) : (
                <p className="empty">Noch keine Sätze in den letzten 8 Wochen.</p>
              )}
            </section>
          </div>

          <div className="start__col">
            <section className="sec" aria-labelledby="sec-balance">
              <div className="sec__head">
                <h2 className="label" id="sec-balance">Sätze pro Muskelgruppe</h2>
                <span className="sec__sp" />
                <span className="label">Letzte 4 Wochen</span>
              </div>
              {payload.balance.length > 0 ? (() => {
                // Six identical "0 · zu wenig" rows drowned the one
                // under-trained group that mattered -- and "Ohne Muskelgruppe ·
                // zu wenig" attached advice to a data-hygiene artifact. Trained
                // groups keep their bars; the untouched ones collapse into one
                // stated line.
                const NO_GROUP = 'Ohne Muskelgruppe'
                const trained = payload.balance.filter((bucket) => bucket.sets > 0)
                // An untouched no-group bucket is a catalogue artifact, not a
                // training gap -- it appears nowhere rather than in the line.
                const zero = payload.balance.filter(
                  (bucket) => bucket.sets === 0 && bucket.group !== NO_GROUP)
                return (
                  <>
                    {trained.map((bucket) => (
                      <div className="hbar" key={bucket.group}>
                        <span className="hbar__name">{bucket.group}</span>
                        <span className="hbar__track">
                          <span className={bucket.under_trained ? 'hbar__fill is-stall' : 'hbar__fill'}
                            style={{ inlineSize: `${Math.round(bucket.share * 1000) / 10}%` }} />
                        </span>
                        <span className="hbar__val">
                          {bucket.sets}
                          {bucket.under_trained && <small>zu wenig</small>}
                        </span>
                      </div>
                    ))}
                    {zero.length > 0 && (
                      <p className="start__note">
                        {`Ohne Sätze: ${zero.map((bucket) => bucket.group).join(', ')}.`}
                      </p>
                    )}
                  </>
                )
              })() : (
                <p className="empty">Noch keine Übungen im Katalog.</p>
              )}
            </section>

            <section className="sec" aria-labelledby="sec-letzte">
              <div className="sec__head">
                <h2 className="label" id="sec-letzte">Letzte Workouts</h2>
                <span className="sec__sp" />
                <a className="sec__more" href="/gym/verlauf">Verlauf ›</a>
              </div>
              {payload.recent_sessions.length > 0 ? payload.recent_sessions.map((s) => {
                const minutes = Math.floor(
                  (instant(s.finished_at).getTime() - instant(s.started_at).getTime()) / 60000)
                return (
                  <a className="row" href={`/gym/session/${s.session_id}`} key={s.session_id}
                    onClick={morphFrom('session')}>
                    <span className="row__main stack">
                      <span className="row__name row__name--strong">{s.name ?? 'Workout'}</span>
                      <span className="row__meta">
                        {/* Sub-minute sessions printed "0 min" -- same guard as
                            Verlauf's rows. */}
                        {`${shortDate(s.started_at)} · ${minutes < 1 ? '< 1' : minutes} min${s.is_deload ? ' · Deload' : ''}`}
                      </span>
                    </span>
                    <span className="row__trail row__trail--stack">
                      <span className="vol">{de(s.volume)}<small>kg</small></span>
                      {s.records > 0 && (
                        <span className="vtag vtag--record">
                          {`${s.records} ${s.records === 1 ? 'Rekord' : 'Rekorde'}`}
                        </span>
                      )}
                    </span>
                  </a>
                )
              }) : (
                <p className="empty">Noch keine abgeschlossenen Workouts.</p>
              )}
            </section>
          </div>
        </div>
      )}

      <Sheet id="sheet-free" title="Freies Workout" closeLabel="Abbrechen">
        <form method="post" action="/gym/start" onSubmit={leaveBySubmit}>
          <CsrfField />
          <div className="field grow">
            <label className="label" htmlFor="start-name">Name (optional)</label>
            <input type="text" id="start-name" name="name" className="input"
              placeholder="z. B. Push Day" maxLength={MAX_NAME_CHARS} />
          </div>
          <div className="field grow">
            <label className="label" htmlFor="start-template">Routine</label>
            <select id="start-template" name="template_id" className="select">
              <option value="">— Ohne Routine —</option>
              {payload.templates.map((t) => (
                <option value={t.template_id} key={t.template_id}>{t.name}</option>
              ))}
            </select>
          </div>
          <button type="submit" className="btn btn--live btn--block">Workout starten</button>
        </form>
      </Sheet>
      <UndoToast />
    </>
  )
}

function LeadWatch({ lead, stalls }: { lead: RoutineMemory; stalls: Stall[] }) {
  // stall_report returns worst-first, so the first survivor is the one.
  const watch = stalls.filter((s) => lead.exercise_ids.includes(s.exercise_id))
  if (watch.length === 0) return null
  const first = watch[0]!
  return (
    <p className="lead__watch">
      {`${first.name} steht seit ${first.sessions_since_pr} ${first.sessions_since_pr === 1 ? 'Workout' : 'Workouts'} bei ${kg(first.stuck_at)} kg.`}
      {watch.length > 1 && ` · ${watch.length - 1} weitere`}
    </p>
  )
}

