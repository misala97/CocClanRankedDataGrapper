import { useId, useState, type FormEvent, type ReactNode } from 'react'
import { CsrfField } from '../csrf'
import type {
  FinishedExercise, FinishedPayload, RecordKind, SessionRecord,
} from './types'
import { postForm, MutationFailed } from '../api'
import { dayMonth, instant, kg, kg1, localParts, shortDate, volume as de } from '../format'
import {
  BODYWEIGHT_MAX_KG, BODYWEIGHT_MIN_KG, MAX_NAME_CHARS, MAX_NOTE_CHARS, MAX_REPS, MAX_WEIGHT_KG,
  parseSetInput, unlikely,
} from '../setInput'
import { UndoToast, useUndo } from '../undo'
import { useSheets } from '../session/stores'
import type { LiveBest } from '../session/types'
import { leaveBySubmit, leavePage, useSheetHistory } from '../session/useSheetHistory'
import { Sheet } from '../session/components/Sheet'
import { Icon } from '../components/Icon'
import { sincePr } from '../catalogue/format'

/** A record is e1RM only (D3); the weight and volume kinds are gone. The
 *  flare names it in full, its first use on the page; the rows under it say
 *  1RM (D16). */
const KINDS: Record<RecordKind, { full: string; short: string }> = {
  e1rm: { full: 'geschätztes Maximum (1RM)', short: '1RM' },
}

const pad = (n: number) => String(n).padStart(2, '0')
const signed = (pct: number) => `${pct >= 0 ? '+' : '-'}${Math.abs(pct)}`

/** Floor-to-minutes alone prints "0 Minuten" for any real duration under a
 *  minute, and the wrong plural between 60 and 119 seconds. */
const minutes = (count: number) =>
  count < 1 ? 'unter 1 Minute' : `${count} ${count === 1 ? 'Minute' : 'Minuten'}`

/** 185 -> "3:05". */
const clock = (seconds: number) =>
  `${Math.floor(seconds / 60)}:${pad(seconds % 60)}`

/** A replaced original and its substitute share a slot, so the position alone
 *  gave React two children with one key -- which it may drop or double on the
 *  next render (B3 review). */
const entryKey = (entry: FinishedExercise) =>
  entry.session_exercise_id ?? `${entry.exercise_id}-${entry.position}`

/** The verdict. Every branch says something -- the zero-record case gets a real
 *  substitute rather than falling through to silence. The deload branch sits
 *  after the empty-session case (an empty session is empty whatever it is
 *  labelled) and before every volume branch: without it a deload that worked
 *  exactly as intended reads as a shortfall against its own average. */
function verdictLine(p: FinishedPayload): string {
  const { session, total_sets: sets, total_volume_delta_pct: delta } = p
  if (p.record_count > 0) {
    return `${p.record_count} ${p.record_count === 1 ? 'neuer Rekord' : 'neue Rekorde'}.`
  }
  if (sets === 0) return 'Kein Satz erfasst — dieses Workout zählt nicht in die Statistik.'
  if (session.is_deload && p.deload_applied) {
    return `Deload — ${session.deload_pct ?? p.deload_default_pct} %. Bewusst leichter.`
  }
  if (session.is_deload) return 'Als Deload markiert. Bewusst leichter.'
  // The dead band is ±15 %, not ±5 %: the baseline is a MEAN, so about half of
  // all sessions sit below it by construction, and at ±5 % an ordinary Tuesday
  // was headlined "Leichter als sonst" in 28px display type. The low branch is
  // descriptive rather than evaluative -- it states the comparison and leaves
  // the verdict to the reader.
  if (delta !== null && delta >= 15) return `${signed(delta)} % über deinem Schnitt.`
  if (delta !== null && delta <= -15) {
    return `${Math.abs(delta)} % unter deinem Schnitt für dieses Workout.`
  }
  if (delta !== null) return 'Im gewohnten Rahmen.'
  return `${sets} ${sets === 1 ? 'Satz' : 'Sätze'} erledigt.`
}

function Tag({ entry }: { entry: FinishedExercise }) {
  switch (entry.verdict) {
    case 'rekord':
      return <span className="vtag vtag--record">Rekord</span>
    case 'stagniert':
      return <span className="vtag vtag--stall">{sincePr(entry.sessions_since_pr, true)}</span>
    case 'steigend':
      return <span className="vtag vtag--up">{`+${entry.volume_delta_pct} % Vol.`}</span>
    case 'neu':
      return <span className="vtag vtag--neu">Erste Aufzeichnung</span>
    default:
      return null
  }
}

function RecordRow({ record }: { record: SessionRecord }) {
  return (
    <a className="row" href={`/gym/exercises/${record.exercise_id}`}>
      <span className="row__main stack">
        <span className="row__name row__name--strong">{record.name}</span>
        <span className="row__meta">
          {`${KINDS[record.kind]?.short ?? record.kind} · vorher ${kg1(record.previous)} kg`}
        </span>
      </span>
      <span className="row__trail">
        <span className="vol">{kg1(record.value)}<small>kg</small></span>
      </span>
    </a>
  )
}

export function FinishedPage({ payload: initial }: { payload: FinishedPayload }) {
  // Back closes an open sheet, not the debrief (G-066).
  useSheetHistory()
  const openSheet = useSheets((s) => s.open)
  // The server's answer to every save IS the next payload (_mutation_response
  // returns FinishedPayload for a finished session), so a correction re-renders
  // the whole debrief -- verdict, tags, sets_display -- without a reload, and
  // the sheet you saved from stays open.
  const [payload, setPayload] = useState(initial)
  const [saveError, setSaveError] = useState<string | null>(null)
  // What "Routine aktualisieren" would change; null: nothing, so no offer.
  const routineDiff = payload.session.template_id !== null && payload.total_sets > 0
    ? templateDiff(payload) : null
  const { session } = payload
  const offerUndo = useUndo((s) => s.offer)
  // Sets hidden while their delete waits out the undo window.
  const [hiddenSetIds, setHiddenSetIds] = useState<number[]>([])

  /** A set logged by mistake -- the double tap, the wrong exercise -- used to
   *  be permanent once the workout finished: this sheet could only retype
   *  numbers. Delayed commit like every other delete here. */
  const deleteSet = (setId: number, label: string) => {
    setHiddenSetIds((ids) => [...ids, setId])
    const unhide = () => setHiddenSetIds((ids) => ids.filter((id) => id !== setId))
    offerUndo({
      label: `${label} gelöscht.`,
      undo: unhide,
      commit: (keepalive) => {
        postForm<FinishedPayload>(`/gym/set/${setId}/delete`, {}, { keepalive })
          .then((fresh) => {
            setPayload((previous) => ({ ...fresh, just_finished: previous.just_finished }))
            setSaveError(null)
          })
          .catch((error: unknown) => {
            unhide()
            setSaveError(error instanceof MutationFailed
              ? error.germanMessage
              : 'Löschen fehlgeschlagen.')
          })
      },
    })
  }

  /** Submit this form's fields over fetch instead of navigating. just_finished
   *  is preserved from the mount: the flare celebrates the visit, not the
   *  data, and a POST carries no ?just_finished. */
  const saves = (url: string | ((fields: FormData) => string)) =>
    (event: FormEvent<HTMLFormElement>) => {
      event.preventDefault()
      const form = event.currentTarget
      const fields = new FormData(form)
      void (async () => {
        try {
          const target = typeof url === 'string' ? url : url(fields)
          const entries: Record<string, string> = {}
          fields.forEach((value, key) => { entries[key] = String(value) })
          const fresh = await postForm<FinishedPayload>(target, entries)
          setPayload((previous) => ({ ...fresh, just_finished: previous.just_finished }))
          setSaveError(null)
        } catch (error) {
          setSaveError(error instanceof MutationFailed
            ? error.germanMessage
            : 'Speichern fehlgeschlagen.')
        }
      })()
    }

  const elapsed = Math.floor(
    (instant(session.finished_at).getTime() - instant(session.started_at).getTime()) / 60000)
  const weekday = payload.weekday_short[localParts(session.started_at).weekday]

  // Counted from the ticks themselves: a gold tick is a record SET, one whose
  // own e1RM beat every earlier workout (D3), where record_count counts
  // exercises -- two gold sets on one lift are one record above.
  const tickRecords = payload.tick_states.filter((t) => t === 'record').length
  const lead = payload.records[0]

  return (
    <>
      <header className="session-top">
        <a href="/gym/verlauf" className="session-top__back" aria-label="Zurück zum Verlauf">
          <Icon name="back" />
        </a>
        {/* An <h1>: the page had no heading of any level. The date is printed
            once -- the name often already embeds one, and on older rows the two
            disagreed because the name was built from UTC. */}
        <span className="session-top__name stack">
          <h1 className="finished__name" style={{ viewTransitionName: 'session' }}>{session.name ?? 'Workout'}</h1>
          <span className="finished__when">
            {`${weekday} · ${shortDate(session.started_at)} · ${minutes(elapsed)}`}
          </span>
          {/* The app ended it (D5): the duration stops at the last set, and
              this says why nobody tapped "Beenden". */}
          {session.auto_finished && (
            <span className="finished__rest">Automatisch beendet — nach 3 Stunden ohne Satz.</span>
          )}
          {/* Measured, not planned. Absent for every session logged before
              completed_at existed, and silent rather than zero in that case.
              Pace, not "Pause": the gap between two logged sets includes the
              set itself, so "davon 50 Minuten Pause" in a 55-minute workout
              claimed almost all of it was spent resting. */}
          {payload.set_pace_seconds !== null && payload.set_pace_seconds > 0 && (
            <span className="finished__rest">
              {`Ø ${clock(payload.set_pace_seconds)} min je Satz (inkl. Pause)`}
            </span>
          )}
        </span>
        {session.is_deload && (
          <span className="session-top__deload">
            {payload.deload_applied
              ? `Deload ${session.deload_pct ?? payload.deload_default_pct} %`
              : 'Deload'}
          </span>
        )}
      </header>

      <p className={payload.record_count ? 'verdict verdict--record' : 'verdict'}>
        {verdictLine(payload)}
      </p>

      {payload.tick_states.length > 0 && (
        <div className="ticks" role="img"
          aria-label={`${payload.total_sets} Sätze erledigt${tickRecords ? `, davon ${tickRecords} mit Rekord` : ''}`}>
          {payload.tick_states.map((tick, i) => (
            <span key={i} className={tick === 'record' ? 'tick is-record' : 'tick is-on'} />
          ))}
        </div>
      )}

      {/* Suppressed entirely at zero sets: the verdict directly above says this
          workout does not count, and the page then scored it "-100 % ggü. Ø"
          over a band of three zeroes. */}
      {payload.total_sets > 0 && (
        <>
          <div className="grew">
            <span className="grew__num">{de(payload.total_volume)}</span>
            <span className="grew__unit">kg bewegt</span>
            <span className="grew__sp" />
            {/* Suppressed on a deload, where the pill in the header and the
                verdict have both already said it. The baseline is named in
                words: "ggü. Ø" is a double abbreviation with no antecedent,
                for a figure that is carefully scoped -- other finished sessions
                of this routine, deloads excluded. */}
            {payload.total_volume_delta_pct !== null && !session.is_deload && (
              <span className="grew__delta">
                {`${signed(payload.total_volume_delta_pct)} % zum Schnitt dieses Workouts`}
              </span>
            )}
          </div>

          {/* Last time, which is a fact, next to the mean, which is a
              judgement. The route loaded every cohort volume to compute that
              mean and kept none of them. */}
          {payload.previous_session !== null ? (
            <p className="finished__prev">
              Letztes Mal{' '}
              <a href={`/gym/session/${payload.previous_session.id}`}>
                <b>{`${de(payload.previous_session.volume)} kg`}</b>
                {` am ${dayMonth(payload.previous_session.started_at)}`}
              </a>
              {payload.avg_total_volume !== null && (
                <> · Schnitt <b>{`${de(payload.avg_total_volume)} kg`}</b></>
              )}
            </p>
          ) : payload.avg_total_volume !== null && (
            /* The route computed the mean and the page named it without ever
               showing it: "+34 % ggü. Ø" is a percentage of a number the
               reader cannot see. */
            <p className="finished__prev">
              Schnitt dieses Workouts <b>{`${de(payload.avg_total_volume)} kg`}</b>
            </p>
          )}

          <div className="band">
            <span className="band__cell">
              <span className="band__num">{payload.total_sets}</span>
              <span className="label">{payload.total_sets === 1 ? 'Satz' : 'Sätze'}</span>
            </span>
            <span className="band__cell">
              <span className="band__num">{payload.exercises.length}</span>
              <span className="label">
                {payload.exercises.length === 1 ? 'Übung' : 'Übungen'}
              </span>
            </span>
            <span className="band__cell">
              <span className={payload.record_count ? 'band__num is-record' : 'band__num'}>
                {payload.record_count}
              </span>
              <span className="label">
                {payload.record_count === 1 ? 'Rekord' : 'Rekorde'}
              </span>
            </span>
          </div>
        </>
      )}

      {/* ONE flare. It used to loop, so six records meant six identical
          full-bleed gold slabs. The rest become quiet rows, and every one of
          them is tagged Rekord again on its own row in the list below anyway.
          is-fresh only when you just finished: revisiting a three-week-old
          session from Verlauf is reading, not celebrating. */}
      {lead !== undefined && (
        <a className={payload.just_finished ? 'record-flare is-fresh' : 'record-flare'}
          href={`/gym/exercises/${lead.exercise_id}`}>
          <div className="record-flare__kind">
            {`Neuer Rekord · ${KINDS[lead.kind]?.full ?? lead.kind}`}
          </div>
          <div className="record-flare__name">{lead.name}</div>
          <div className="record-flare__row">
            <span className="record-flare__num">{kg1(lead.value)}</span>
            <span className="record-flare__unit">kg</span>
          </div>
          <div className="record-flare__prev">
            {`vorher ${kg1(lead.previous)} kg · ${shortDate(lead.previous_at)} · als ${lead.position}. Übung`}
          </div>
        </a>
      )}

      {payload.records.length > 1 && (
        <section className="sec" aria-labelledby="sec-records">
          <div className="sec__head">
            <h2 className="label" id="sec-records">Weitere Rekorde</h2>
          </div>
          {payload.records.slice(1).map((record) => (
            <RecordRow record={record} key={`${record.exercise_id}-${record.kind}`} />
          ))}
        </section>
      )}

      {/* Attention is cold and always carries the word. `advice` is only ever
          produced for a verdict of 'stagniert', and a deload keeps only
          'rekord' -- so a deload can never reach this. */}
      {payload.advice.length > 0 && (
        <section className="next-time" aria-labelledby="sec-next">
          <h2 className="next-time__lbl" id="sec-next">Nächstes Mal</h2>
          {payload.advice.map((item) => (
            <p className="next-time__body" key={item.exercise_id}>
              <b>{item.name}</b>
              {` steht seit ${item.sessions} ${item.sessions === 1 ? 'Workout' : 'Workouts'} auf ${kg(item.stuck_at)} kg — auf `}
              <b>{`${kg(item.suggested_weight)} kg`}</b>
              {' gehen, notfalls 2 Wdh. weniger.'}
            </p>
          ))}
        </section>
      )}

      <section className="sec" aria-labelledby="sec-byex">
        <div className="sec__head"><h2 className="label" id="sec-byex">Nach Übung</h2></div>
        {payload.exercises.length > 0 ? (
          <>
            {(() => {
              // A fresh lifter's every exercise records at once -- seven
              // identical gold chips is "rare by construction" failing
              // visibly. One gold sentence keeps the currency.
              const allRecords = payload.exercises.length >= 3
                && payload.exercises.every((entry) => entry.verdict === 'rekord')
              return (
                <>
                  {allRecords && (
                    <p className="finished__allpr">
                      {`Alle ${payload.exercises.length} Übungen mit Rekord.`}
                    </p>
                  )}
                  {payload.exercises.map((entry) => (
                    <div className="row row--top" key={entryKey(entry)}>
                      <span className="row__lead">{entry.position}</span>
                      <a className="row__main stack" href={`/gym/exercises/${entry.exercise_id}`}>
                        <span className="row__name row__name--wrap">{entry.name}</span>
                        <span className="row__meta">{entry.sets_display}</span>
                      </a>
                      {!allRecords && <span className="row__trail"><Tag entry={entry} /></span>}
                    </div>
                  ))}
                </>
              )
            })()}
            <button type="button" className="finished__correct"
              aria-haspopup="dialog" aria-controls="sheet-correct"
              onClick={() => openSheet('sheet-correct')}>
              <Icon name="edit" />
              Sätze &amp; Notizen
            </button>
          </>
        ) : (
          <p className="empty">Keine erledigten Sätze in diesem Workout.</p>
        )}
      </section>

      {/* "und", not "&", in German prose. The rendered diff replaces the old
          blind confirm(): the prompt now states exactly what the update would
          change, and disappears entirely when it would change nothing. */}
      {payload.just_finished && payload.total_sets > 0 && (
        session.template_id !== null ? (
          routineDiff !== null && (
            <section className="prompt">
              <RoutineUpdate payload={payload} diff={routineDiff} />
            </section>
          )
        ) : (
          /* A freeform session had nothing offered at the end, though every
             routine on Start comes from a template and this is the one moment
             you know what you actually did. */
          <section className="prompt">
            Dieses Workout als Routine speichern?
            <form method="post" action={`/gym/session/${session.id}/save_as_template`}>
              <CsrfField />
              {/* template_name, not name: that is what gym_save_as_template
                  reads. This said name= from the day the finished pages were
                  merged, so the route saw an empty string, skipped its `if`,
                  and redirected having created nothing -- and the redirect is
                  the same one a success produces. */}
              <input type="text" name="template_name" className="input"
                placeholder="Name der Routine" required maxLength={MAX_NAME_CHARS}
                aria-label="Name der neuen Routine" />
              <button type="submit" className="btn btn--ghost btn--block">
                Als Routine speichern
              </button>
            </form>
          </section>
        )
      )}

      <div className="outs">
        <a href="/gym/verlauf" className="btn btn--ghost">Verlauf</a>
        <a href="/gym" className="btn btn--live">Zum Start</a>
      </div>

      {/* Deleting a workout is a rare correction, not the way out of this
          screen. It used to be the largest, brightest, right-most element. */}
      {saveError !== null && (
        <p className="flash flash--error" role="alert">{saveError}</p>
      )}
      <div className="quiet-acts">
        <button type="button" className="quiet-acts__btn"
          onClick={() => openSheet('sheet-meta')}>
          Körpergewicht &amp; Notiz
        </button>
        <form method="post" action={`/gym/session/${session.id}/deload`}
          onSubmit={saves(`/gym/session/${session.id}/deload`)}>
          <CsrfField />
          <input type="hidden" name="on" value={session.is_deload ? '0' : '1'} />
          <input type="hidden" name="pct"
            value={String(session.deload_pct ?? payload.deload_default_pct)} />
          <button type="submit" className="quiet-acts__btn">
            {/* An action, both ways (G-078): "War ein Deload" read as a
                statement. Marking no longer touches records (D3). */}
            {session.is_deload ? 'Deload-Markierung entfernen' : 'Als Deload markieren'}
          </button>
        </form>
        {/* The offer above shows only on arrival; a workout opened again from
            Verlauf keeps it here (G-077, Q6). */}
        {!payload.just_finished && routineDiff !== null && (
          <button type="button" className="quiet-acts__btn"
            onClick={() => openSheet('sheet-routine')}>
            {`Routine „${session.template_name}“ aktualisieren …`}
          </button>
        )}
        {/* Delayed-commit undo instead of "unwiderruflich" + confirm(): five
            seconds to take it back, then the POST fires and the page moves on
            to Verlauf -- also when the window was closed by the app going to
            the background (G-062), since the page is still there when the
            lifter comes back. Replaced, not pushed: Back would land on a
            workout that no longer exists. */}
        <button type="button" className="quiet-acts__btn quiet-acts__btn--danger"
          onClick={() => useUndo.getState().offer({
            label: 'Workout gelöscht.',
            commit: (keepalive) => {
              postForm<{ deleted: boolean }>(
                `/gym/session/${session.id}/delete`, {}, { keepalive })
                .then(() => { leavePage(() => { window.location.replace('/gym/verlauf') }) })
                .catch((error) => setSaveError(error instanceof MutationFailed
                  ? error.germanMessage
                  : 'Löschen fehlgeschlagen.'))
            },
            undo: () => {},
          })}>
          Workout löschen
        </button>
      </div>

      {routineDiff !== null && (
        <Sheet id="sheet-routine" title="Routine aktualisieren" closeLabel="Abbrechen">
          <div className="sheet__group">
            <RoutineUpdate payload={payload} diff={routineDiff} />
          </div>
        </Sheet>
      )}

      {/* Bodyweight and the session note: editable "at any point during or
          after the workout" per spec, but this screen -- the ONLY one a
          finished session ever renders -- carried neither field. Same fields
          and same route as the live page's Workout-options sheet;
          owned_session() has no finished-check, so the route already accepted
          this, only the UI was missing. */}
      <Sheet id="sheet-meta" title="Workout">
        {saveError !== null && (
          <p className="flash flash--error" role="alert">{saveError}</p>
        )}
        <div className="sheet__group">
          <form method="post" action={`/gym/sessions/${session.id}/meta`}
            onSubmit={saves(`/gym/sessions/${session.id}/meta`)}>
            <CsrfField />
            <div className="sheet__row">
              <label className="label" htmlFor="finished-session-bodyweight">
                Körpergewicht (kg)
              </label>
              <input type="number" id="finished-session-bodyweight" name="bodyweight_kg"
                step="0.1" min={BODYWEIGHT_MIN_KG} max={BODYWEIGHT_MAX_KG}
                className="input input--num rest-form__input"
                defaultValue={session.bodyweight_kg ?? ''} placeholder="—" />
            </div>
            <div className="field grow">
              <label className="label" htmlFor="finished-session-notes">Notiz</label>
              <textarea id="finished-session-notes" name="notes" className="textarea" rows={3}
                maxLength={MAX_NOTE_CHARS}
                defaultValue={session.notes ?? ''} placeholder="z. B. nach 8h Schicht" />
            </div>
            <button type="submit" className="btn btn--ghost btn--sm">Speichern</button>
          </form>
          <p className="sheet__note">Gilt für dieses Workout.</p>
        </div>
      </Sheet>

      {/* Corrections live in a sheet: a typo is rare, and the editor is a dense
          grid of number fields that has no business sitting under the debrief
          every time. */}
      <Sheet id="sheet-correct" title="Sätze & Notizen">
        {saveError !== null && (
          <p className="flash flash--error" role="alert">{saveError}</p>
        )}
        {payload.exercises.map((entry) => (
          <div className="sheet__group" key={entryKey(entry)}>
            {/* .label is the meta treatment: uppercase, mono, letterspaced. 4.4
                is explicit that exercise names are sentence case in the body
                face, and calls it the most-violated rule in this project. */}
            <h3 className="correct__name">{entry.name}</h3>
            {entry.set_rows.filter((s) => !hiddenSetIds.includes(s.id)).map((s, i) => (
              // .sset, the live sheet's set grid: with a delete beside the save
              // the old flex row outgrew a phone and pushed the sheet sideways.
              <Sure key={s.id} was={s} best={entry.best} yes="Ja, speichern"
                onSubmit={saves(`/gym/set/${s.id}/update`)}>
                {(formId, ask) => (
                  <form method="post" action={`/gym/set/${s.id}/update`} className="sset"
                    id={formId} {...ask}>
                    <CsrfField />
                    <span className="label">{i + 1}</span>
                    {/* required + min: the browser refuses an empty or zero-rep
                        row before the submit handler ever runs. */}
                    <input type="number" name="weight" step="0.01" min="0" max={MAX_WEIGHT_KG}
                      required className="input input--num" defaultValue={s.weight}
                      aria-label={`${entry.name}, Satz ${i + 1}, Gewicht in kg`} />
                    <span className="sset__unit">kg</span><span className="sset__unit">×</span>
                    <input type="number" name="reps" min="1" max={MAX_REPS} required
                      className="input input--num" defaultValue={s.reps}
                      aria-label={`${entry.name}, Satz ${i + 1}, Wiederholungen`} />
                    <span className="sset__acts">
                      <button type="submit" className="icon-btn"
                        aria-label={`Satz ${i + 1} speichern`}>
                        <Icon name="save" />
                      </button>
                      <button type="button" className="icon-btn"
                        aria-label={`${entry.name}, Satz ${i + 1} löschen`}
                        onClick={() => deleteSet(s.id, `${entry.name}, Satz ${i + 1}`)}>✕</button>
                    </span>
                  </form>
                )}
              </Sure>
            ))}
            {entry.session_exercise_id !== null && (
              <AddSetForm key={`add-${entry.session_exercise_id}-${entry.set_rows.length}`}
                sessionExerciseId={entry.session_exercise_id} name={entry.name}
                seed={entry.set_rows[entry.set_rows.length - 1] ?? null} best={entry.best}
                onSubmit={saves(`/gym/session-exercise/${entry.session_exercise_id}/sets/add`)} />
            )}
            {/* The opposite lifetime to the sets above: a twinge and a note
                belong to this workout, not to the set values. */}
            {entry.session_exercise_id !== null && (
              <form method="post"
                action={`/gym/session-exercises/${entry.session_exercise_id}/meta`}
                onSubmit={saves(`/gym/session-exercises/${entry.session_exercise_id}/meta`)}>
                  <CsrfField />
                <label className="sheet__row">
                  <input type="checkbox" name="pain" className="check"
                    defaultChecked={entry.pain} />
                  <span className="check__text">Schmerz / Zwicken</span>
                </label>
                <div className="field grow">
                  <label className="label"
                    htmlFor={`finished-ex-notes-${entry.session_exercise_id}`}>Notiz</label>
                  <input type="text" className="input" name="notes" maxLength={MAX_NOTE_CHARS}
                    id={`finished-ex-notes-${entry.session_exercise_id}`}
                    defaultValue={entry.notes ?? ''} placeholder="—" />
                </div>
                <button type="submit" className="btn btn--ghost btn--sm">Speichern</button>
              </form>
            )}
          </div>
        ))}
        {/* Exercises of this workout with nothing logged are not in the
            debrief at all, so the set that did happen but never got its tap
            had nowhere to go. */}
        {payload.unlogged.map((entry) => (
          <div className="sheet__group" key={`unlogged-${entry.session_exercise_id}`}>
            <h3 className="correct__name">{entry.name}</h3>
            <p className="sheet__note">Nichts erfasst.</p>
            <AddSetForm key={`add-${entry.session_exercise_id}-0`}
              sessionExerciseId={entry.session_exercise_id} name={entry.name} seed={null}
              best={entry.best}
              onSubmit={saves(`/gym/session-exercise/${entry.session_exercise_id}/sets/add`)} />
          </div>
        ))}
      </Sheet>
      <UndoToast />
    </>
  )
}

/** One more set for an exercise of a finished workout. Keyed by the caller on
 *  the set count, so a successful add remounts it -- empty of what was just
 *  typed and seeded from the new last set. The server files it as logged
 *  without starting a rest: the workout is over. */
function AddSetForm({ sessionExerciseId, name, seed, best, onSubmit }: {
  sessionExerciseId: number
  name: string
  seed: { weight: number; reps: number } | null
  best: LiveBest | null
  onSubmit(event: FormEvent<HTMLFormElement>): void
}) {
  return (
    <Sure was={seed} best={best} yes="Ja, nachtragen" onSubmit={onSubmit}>
      {(formId, ask) => (
        <form method="post" action={`/gym/session-exercise/${sessionExerciseId}/sets/add`}
          className="sset" id={formId} {...ask}>
          <CsrfField />
          <span className="label" aria-hidden="true">+</span>
          <input type="number" name="weight" step="0.01" min="0" max={MAX_WEIGHT_KG} required
            className="input input--num" defaultValue={seed?.weight ?? ''}
            aria-label={`${name}, neuer Satz, Gewicht in kg`} />
          <span className="sset__unit">kg</span><span className="sset__unit">×</span>
          <input type="number" name="reps" min="1" max={MAX_REPS} required
            className="input input--num" defaultValue={seed?.reps ?? ''}
            aria-label={`${name}, neuer Satz, Wiederholungen`} />
          <span className="sset__acts">
            {/* Short visible text so the action track never wraps, like the
                live sheet's "Anhängen"; the accessible name carries the full
                phrase. */}
            <button type="submit" className="btn btn--ghost btn--sm"
              aria-label={`${name}, Satz nachtragen`}>Nachtragen</button>
          </span>
        </form>
      )}
    </Sure>
  )
}

/**
 * "Sicher?" before a typed set is kept (Q5), as on the live screen:
 * "Nachtragen" and a correction count the moment they land, and a
 * fat-fingered 600 kg went straight into the records (B7 review). Only
 * numbers the lifter changed are asked about; typing again takes the question
 * away, and its "Ja" -- or the same numbers sent again -- sends the form as it
 * stands.
 */
function Sure({ was, best, yes, onSubmit, children }: {
  /** The numbers the row started from, which are not asked about. */
  was: { weight: number; reps: number } | null
  best: LiveBest | null
  yes: string
  onSubmit(event: FormEvent<HTMLFormElement>): void
  children(formId: string, ask: {
    onSubmit(event: FormEvent<HTMLFormElement>): void
    onInput(): void
  }): ReactNode
}) {
  const formId = useId()
  const [doubt, setDoubt] = useState<{ typed: string; text: string } | null>(null)
  const ask = {
    onSubmit: (event: FormEvent<HTMLFormElement>) => {
      const fields = new FormData(event.currentTarget)
      const parsed = parseSetInput(
        String(fields.get('weight') ?? ''), String(fields.get('reps') ?? ''))
      const changed = parsed !== null
        && (was === null || parsed.weight !== was.weight || parsed.reps !== was.reps)
      const text = changed ? unlikely(parsed, best) : null
      const typed = parsed === null ? '' : `${parsed.weight}|${parsed.reps}`
      if (text !== null && doubt?.typed !== typed) {
        event.preventDefault()
        setDoubt({ typed, text })
        return
      }
      setDoubt(null)
      onSubmit(event)
    },
    onInput: () => { setDoubt(null) },
  }
  return (
    <>
      {children(formId, ask)}
      <p className="sset__hint" aria-live="polite">
        {doubt?.text}
        {doubt !== null && (
          <button type="submit" form={formId} className="btn btn--ghost btn--sm sset__sure">
            {yes}
          </button>
        )}
      </p>
    </>
  )
}

/**
 * What updating the template would actually change, as one sentence -- or
 * null when it would change nothing, in which case the prompt has no reason
 * to exist. Both halves come from the server: the "after" list is NOT the
 * performed list (skipped and zero-set slots go into a template, substitutes
 * never do), so it is computed by the same function the route writes with.
 */
function templateDiff(payload: FinishedPayload): string | null {
  const current = payload.template_exercises ?? []
  const next = payload.template_next_exercises ?? []
  const added = next.filter((name) => !current.includes(name))
  const removed = current.filter((name) => !next.includes(name))
  // The order of the exercises that stay, said even beside a list change:
  // "Nur die Reihenfolge ändert sich" once stood where a removal and a
  // replacement had changed the list too (G-077).
  const moves = orderMoves(
    current.filter((name) => next.includes(name)),
    next.filter((name) => current.includes(name)))

  const parts: string[] = []
  if (added.length > 0) parts.push(`Neu: ${added.join(', ')}.`)
  if (removed.length > 0) parts.push(`Entfällt: ${removed.join(', ')}.`)
  if (moves !== null) {
    parts.push(moves.length <= 2
      ? `Reihenfolge: ${moves.join(', ')}.`
      : `Neue Reihenfolge: ${next.join(', ')}.`)
  }
  return parts.length === 0 ? null : parts.join(' ')
}

/**
 * How the exercises in `before` moved to stand as in `after` (the same names),
 * one phrase per exercise that moved: "Hammercurls jetzt vor Bizepscurls".
 * Null when none did.
 *
 * What stayed is the longest run still in its old order, so one exercise
 * pulled forward names that one, not every exercise it passed. Each moved
 * one is placed against a neighbour that stayed: no such run holds a gap it
 * could have stayed in, so it is before the next one now and was after it,
 * or the other way round. Between equals, the run keeps the earlier
 * exercises, so a pull forward reads as one.
 */
function orderMoves(before: string[], after: string[]): string[] | null {
  const was = after.map((name) => before.indexOf(name))
  const length = was.map(() => 1)
  const previous = was.map(() => -1)
  let end = -1
  was.forEach((index, i) => {
    for (let j = 0; j < i; j += 1) {
      if (was[j]! >= index) continue
      const longer = length[j]! + 1 > length[i]!
      const earlier = length[j]! + 1 === length[i]! && was[j]! < was[previous[i]!]!
      if (longer || earlier) { length[i] = length[j]! + 1; previous[i] = j }
    }
    if (end === -1 || length[i]! > length[end]!
      || (length[i] === length[end] && index < was[end]!)) end = i
  })
  const stayed = new Set<number>()
  for (let i = end; i !== -1; i = previous[i]!) stayed.add(i)
  if (stayed.size === after.length) return null

  return after.flatMap((name, i) => {
    if (stayed.has(i)) return []
    const behind = after.findIndex((_, k) => k > i && stayed.has(k))
    if (behind !== -1 && was[behind]! < was[i]!) return [`${name} jetzt vor ${after[behind]}`]
    let ahead = i - 1
    while (ahead >= 0 && !stayed.has(ahead)) ahead -= 1
    if (ahead >= 0) return [`${name} jetzt nach ${after[ahead]}`]
    // Only with a name twice in the list, which no run can place.
    return behind === -1 ? [] : [`${name} jetzt vor ${after[behind]}`]
  })
}

/** "Routine aktualisieren", with what it would change: offered on arrival
 *  and kept in the workout's menu (G-077). */
function RoutineUpdate({ payload, diff }: { payload: FinishedPayload; diff: string }) {
  const { session } = payload
  return (
    <>
      Routine <b>{session.template_name}</b> mit dieser Übungsliste und Reihenfolge aktualisieren?
      <p className="prompt__diff">{diff}</p>
      <form method="post" action={`/gym/session/${session.id}/update_template`}
        onSubmit={leaveBySubmit}>
        <CsrfField />
        <button type="submit" className="btn btn--ghost btn--block">
          Routine aktualisieren
        </button>
      </form>
    </>
  )
}
