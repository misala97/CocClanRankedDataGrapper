import { useEffect, useState, type FormEvent } from 'react'
import type { HeutePayload, RoutineMemory, Stall } from './types'
import { postForm, MutationFailed } from '../api'
import { csrfToken, CsrfField } from '../csrf'
import { UndoToast, useUndo } from '../undo'
import { recency, sincePr } from '../catalogue/format'
import { useSheets, usePush } from '../session/stores'
import { Sheet } from '../session/components/Sheet'
import { Icon } from '../components/Icon'
import { kg1 } from '../format'
import { morphFrom } from '../vt'

const de = (value: number) => Math.round(value).toLocaleString('de-DE')
const local = (iso: string) => new Date(`${iso}Z`)
const pad = (n: number) => String(n).padStart(2, '0')
const dmy = (iso: string) => {
  const d = local(iso)
  return `${pad(d.getDate())}.${pad(d.getMonth() + 1)}.${d.getFullYear()}`
}
const dm = (iso: string) => {
  const d = local(iso)
  return `${pad(d.getDate())}.${pad(d.getMonth() + 1)}.`
}

/** Elapsed since the running workout started. hh:mm:ss, as GymClock rendered it. */
function useElapsed(startedAt: string): string {
  const [now, setNow] = useState(() => Date.now())
  useEffect(() => {
    const id = setInterval(() => setNow(Date.now()), 1000)
    return () => clearInterval(id)
  }, [])
  const total = Math.max(0, Math.floor((now - local(startedAt).getTime()) / 1000))
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
  const left = local(restEndsAt).getTime() - now
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
        <span className="row__meta">
          {`Als ${item.position}. Übung · ${kg1(item.stuck_at)} kg`}
        </span>
      </span>
      <span className="vtag vtag--stall">{sincePr(item.sessions_since_pr)}</span>
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
            aria-label={`Neuer Name für ${routine.name}`} required />
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

export function StartPage({ payload: initial }: { payload: HeutePayload }) {
  const openSheet = useSheets((s) => s.open)
  const subscribed = usePush((s) => s.subscribed)
  const setSubscribed = usePush((s) => s.setSubscribed)
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
   *  nothing has reached the server yet. */
  const deleteRoutine = (routine: RoutineMemory) => {
    const before = payload
    setPayload((current) => ({
      ...current,
      routines: current.routines.filter((r) => r.template_id !== routine.template_id),
      templates: current.templates.filter((r) => r.template_id !== routine.template_id),
    }))
    offerUndo({
      label: `Routine „${routine.name}“ gelöscht.`,
      undo: () => setPayload(before),
      commit: (keepalive) => {
        postForm<HeutePayload>(`/gym/templates/${routine.template_id}/delete`, {}, { keepalive })
          .then(setPayload)
          .catch((error) => setSaveError(error instanceof MutationFailed
            ? error.germanMessage
            : 'Löschen fehlgeschlagen.'))
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
      .then((sub) => setSubscribed(sub !== null))
      .catch(() => setSubscribed(false))
  }, [pushSupported, setSubscribed])

  // Anchored to the session's start, not the page render: `payload.now` here
  // was the bug that made the card read "00:00:01 läuft" twenty minutes in.
  const elapsed = useElapsed(payload.active_session_started_at ?? payload.now)
  const restLeft = useRestCountdown(payload.active_session_rest_ends_at)
  useReloadWhenStale()
  const lead = payload.routines[0]
  const rest = payload.routines.slice(canStart ? 1 : 0)
  const lastWeek = payload.tonnage[payload.tonnage.length - 1]
  const deloadWeeks = payload.tonnage.filter((w) => w.has_deload)

  return (
    <>
      <header className="start__head">
        <div className="start__row">
          <h1 className="start__h">Start</h1>
          <span className="start__sp" />
          <span className="start__date">{dmy(payload.now)}</span>
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
              <b>{kg1(payload.consistency.per_week)}</b> Workouts pro Woche
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
      {pushSupported && subscribed === false && (
        <section className="sec notify-prompt" id="notify-start">
          <button type="button" className="notify-prompt__btn"
            onClick={() => { void enablePush(payload.vapid_public_key, setSubscribed) }}>
            <Icon name="timer" />
            <span>
              <b>Pausen-Benachrichtigung aktivieren</b>
              <small>Auf diesem Gerät. Installiere die App zuerst über „Zum Home-Bildschirm“.</small>
            </span>
          </button>
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
              Noch keine Vorlagen. Speichere ein Workout als Vorlage, um es hier zu sehen.
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

      {/* The four reading sections, paired into two columns on desktop by
          KIND: what wants attention on the left, what is reference on the
          right. Not four sections auto-placed into a grid -- auto-placement
          locked section 3 to the tallest section in row 1 and left a 250px
          hole under "Steht still". */}
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
                      aria-label={`${week.is_current ? 'Diese Woche' : `Woche ab ${dm(week.week_start)}`}: ${de(week.volume)} kg${week.has_deload ? ', mit Deload-Einheit' : ''}`}
                      style={{ blockSize: `${Math.round((week.volume / payload.tonnage_peak) * 1000) / 10}%` }} />
                  ))}
                </div>
                <div className="vbars__axis" aria-hidden="true">
                  {payload.tonnage.map((week) => (
                    <span key={week.week_start}>
                      {week.is_current ? 'Jetzt' : dm(week.week_start)}
                    </span>
                  ))}
                </div>
                <p className="start__note">
                  {`${de(lastWeek?.volume ?? 0)} kg diese Woche bisher — läuft noch.`}
                  {deloadWeeks.length > 0 && ' Schraffiert: Woche mit Deload-Einheit.'}
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
                (local(s.finished_at).getTime() - local(s.started_at).getTime()) / 60000)
              return (
                <a className="row" href={`/gym/session/${s.session_id}`} key={s.session_id}
                  onClick={morphFrom('session')}>
                  <span className="row__main stack">
                    <span className="row__name row__name--strong">{s.name ?? 'Workout'}</span>
                    <span className="row__meta">
                      {/* Sub-minute sessions printed "0 min" -- same guard as
                          Verlauf's rows. */}
                      {`${dmy(s.started_at)} · ${minutes < 1 ? '< 1' : minutes} min${s.is_deload ? ' · Deload' : ''}`}
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

      <Sheet id="sheet-free" title="Freies Workout" closeLabel="Abbrechen">
        <form method="post" action="/gym/start">
          <CsrfField />
          <div className="field grow">
            <label className="label" htmlFor="start-name">Name (optional)</label>
            <input type="text" id="start-name" name="name" className="input"
              placeholder="z. B. Push Day" />
          </div>
          <div className="field grow">
            <label className="label" htmlFor="start-template">Vorlage</label>
            <select id="start-template" name="template_id" className="select">
              <option value="">— Ohne Vorlage —</option>
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
      {`${first.name} steht seit ${first.sessions_since_pr} ${first.sessions_since_pr === 1 ? 'Session' : 'Sessions'} bei ${kg1(first.stuck_at)} kg.`}
      {watch.length > 1 && ` · ${watch.length - 1} weitere`}
    </p>
  )
}

async function enablePush(
  vapidPublicKey: string | null,
  setSubscribed: (value: boolean) => void,
): Promise<void> {
  if (vapidPublicKey === null) return
  const registration = await navigator.serviceWorker.register('/sw.js', { scope: '/gym' })
  const permission = await Notification.requestPermission()
  if (permission !== 'granted') return
  const padding = '='.repeat((4 - (vapidPublicKey.length % 4)) % 4)
  const normalised = (vapidPublicKey + padding).replace(/-/g, '+').replace(/_/g, '/')
  const raw = atob(normalised)
  const bytes = new Uint8Array(new ArrayBuffer(raw.length))
  for (let i = 0; i < raw.length; i += 1) bytes[i] = raw.charCodeAt(i)
  const subscription = await registration.pushManager.subscribe({
    userVisibleOnly: true, applicationServerKey: bytes.buffer,
  })
  await fetch('/gym/push/subscribe', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', 'X-CSRF-Token': csrfToken() },
    body: JSON.stringify(subscription.toJSON()),
  })
  setSubscribed(true)
}
