import { useState, type FormEvent } from 'react'
import { CsrfField } from '../csrf'
import type {
  FinishedExercise, FinishedPayload, RecordKind, SessionRecord,
} from './types'
import { postForm, MutationFailed } from '../api'
import { kg1, volume as de } from '../format'
import { UndoToast, useUndo } from '../undo'
import { useSheets } from '../session/stores'
import { Sheet } from '../session/components/Sheet'
import { Icon } from '../components/Icon'

const KINDS: Record<RecordKind, string> = {
  weight: 'Gewichts', e1rm: 'e1RM', volume: 'Volumen',
}

/** Local time, from a naive-UTC timestamp. */
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
const signed = (pct: number) => `${pct >= 0 ? '+' : '-'}${Math.abs(pct)}`

/** Floor-to-minutes alone prints "0 Minuten" for any real duration under a
 *  minute, and the wrong plural between 60 and 119 seconds. */
const minutes = (count: number) =>
  count < 1 ? 'unter 1 Minute' : `${count} ${count === 1 ? 'Minute' : 'Minuten'}`

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
      return <span className="vtag vtag--stall">{`${entry.sessions_since_pr} ohne PR`}</span>
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
          {`${KINDS[record.kind] ?? record.kind} · vorher ${kg1(record.previous)} kg`}
        </span>
      </span>
      <span className="row__trail">
        <span className="vol">{kg1(record.value)}<small>kg</small></span>
      </span>
    </a>
  )
}

export function FinishedPage({ payload: initial }: { payload: FinishedPayload }) {
  const openSheet = useSheets((s) => s.open)
  // The server's answer to every save IS the next payload (_mutation_response
  // returns FinishedPayload for a finished session), so a correction re-renders
  // the whole debrief -- verdict, tags, sets_display -- without a reload, and
  // the sheet you saved from stays open.
  const [payload, setPayload] = useState(initial)
  const [saveError, setSaveError] = useState<string | null>(null)
  const { session } = payload

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
    (local(session.finished_at).getTime() - local(session.started_at).getTime()) / 60000)
  // Monday-first, matching WEEKDAY_SHORT. getDay() is Sunday-first.
  const started = local(session.started_at)
  const weekday = payload.weekday_short[(started.getDay() + 6) % 7]

  // Counted from the ticks themselves. Only a WEIGHT record earns a gold tick
  // (a set can honestly carry that and nothing else), but the label counted
  // every record kind -- 21 ticks with 1 gold announced "davon 3 mit Rekord".
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
            {`${weekday} · ${dmy(session.started_at)} · ${minutes(elapsed)}`}
          </span>
          {/* Measured, not planned. Absent for every session logged before
              completed_at existed, and silent rather than zero in that case. */}
          {payload.rest_taken_seconds !== null && payload.rest_taken_seconds > 0 && (
            <span className="finished__rest">
              {`davon ${minutes(Math.floor(payload.rest_taken_seconds / 60))} Pause`}
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
          aria-label={`${payload.total_sets} Sätze erledigt${tickRecords ? `, davon ${tickRecords} mit Gewichts-Rekord` : ''}`}>
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
                {` am ${dm(payload.previous_session.started_at)}`}
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
            {`Neuer ${KINDS[lead.kind] ?? lead.kind}-Rekord`}
          </div>
          <div className="record-flare__name">{lead.name}</div>
          <div className="record-flare__row">
            <span className="record-flare__num">{kg1(lead.value)}</span>
            <span className="record-flare__unit">kg</span>
          </div>
          <div className="record-flare__prev">
            {`vorher ${kg1(lead.previous)} kg · ${dmy(lead.previous_at)} · als ${lead.position}. Übung`}
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
          produced for a verdict of 'stagniert', and a deload sets every verdict
          to None -- so a deload can never reach this. */}
      {payload.advice.length > 0 && (
        <section className="next-time" aria-labelledby="sec-next">
          <h2 className="next-time__lbl" id="sec-next">Nächstes Mal</h2>
          {payload.advice.map((item) => (
            <p className="next-time__body" key={item.exercise_id}>
              <b>{item.name}</b>
              {` steht seit ${item.sessions} ${item.sessions === 1 ? 'Einheit' : 'Einheiten'} auf ${kg1(item.stuck_at)} kg — auf `}
              <b>{`${kg1(item.suggested_weight)} kg`}</b>
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
                    <div className="row row--top" key={entry.position}>
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
          templateDiff(payload) !== null && (
            <section className="prompt">
              Vorlage <b>{session.template_name}</b> mit dieser Übungsliste und Reihenfolge aktualisieren?
              <p className="prompt__diff">{templateDiff(payload)}</p>
              <form method="post" action={`/gym/session/${session.id}/update_template`}>
                <CsrfField />
                <button type="submit" className="btn btn--ghost btn--block">
                  Vorlage aktualisieren
                </button>
              </form>
            </section>
          )
        ) : (
          /* A freeform session had nothing offered at the end, though every
             routine on Start comes from a template and this is the one moment
             you know what you actually did. */
          <section className="prompt">
            Dieses Workout als Vorlage speichern?
            <form method="post" action={`/gym/session/${session.id}/save_as_template`}>
              <CsrfField />
              {/* template_name, not name: that is what gym_save_as_template
                  reads. This said name= from the day the finished pages were
                  merged, so the route saw an empty string, skipped its `if`,
                  and redirected having created nothing -- and the redirect is
                  the same one a success produces. */}
              <input type="text" name="template_name" className="input"
                placeholder="Name der Vorlage" required
                aria-label="Name der neuen Vorlage" />
              <button type="submit" className="btn btn--ghost btn--block">
                Als Vorlage speichern
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
            {session.is_deload ? 'Deload-Markierung entfernen' : 'War ein Deload'}
          </button>
        </form>
        {/* Delayed-commit undo instead of "unwiderruflich" + confirm(): five
            seconds to take it back, then the POST fires and the page moves on
            to Verlauf. */}
        <button type="button" className="quiet-acts__btn quiet-acts__btn--danger"
          onClick={() => useUndo.getState().offer({
            label: 'Workout gelöscht.',
            commit: (keepalive) => {
              postForm<{ deleted: boolean }>(
                `/gym/session/${session.id}/delete`, {}, { keepalive })
                .then(() => { if (!keepalive) window.location.assign('/gym/verlauf') })
                .catch((error) => setSaveError(error instanceof MutationFailed
                  ? error.germanMessage
                  : 'Löschen fehlgeschlagen.'))
            },
            undo: () => {},
          })}>
          Workout löschen
        </button>
      </div>

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
                step="0.1" min="0" className="input input--num rest-form__input"
                defaultValue={session.bodyweight_kg ?? ''} placeholder="—" />
            </div>
            <div className="field grow">
              <label className="label" htmlFor="finished-session-notes">Notiz</label>
              <input type="text" id="finished-session-notes" name="notes" className="input"
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
          <div className="sheet__group" key={entry.position}>
            {/* .label is the meta treatment: uppercase, mono, letterspaced. 4.4
                is explicit that exercise names are sentence case in the body
                face, and calls it the most-violated rule in this project. */}
            <h3 className="correct__name">{entry.name}</h3>
            {entry.set_rows.map((s, i) => (
              <form method="post" action={`/gym/set/${s.id}/update`} className="sheet__row"
                key={s.id} onSubmit={saves(`/gym/set/${s.id}/update`)}>
                <CsrfField />
                <span className="label">{i + 1}</span>
                <input type="number" name="weight" step="0.5" min="0"
                  className="input input--num" defaultValue={s.weight}
                  aria-label={`${entry.name}, Satz ${i + 1}, Gewicht in kg`} />
                <span className="load__unit">kg</span><span className="load__x">×</span>
                <input type="number" name="reps" min="0" className="input input--num"
                  defaultValue={s.reps}
                  aria-label={`${entry.name}, Satz ${i + 1}, Wiederholungen`} />
                <button type="submit" className="icon-btn"
                  aria-label={`Satz ${i + 1} speichern`}>
                  <Icon name="save" />
                </button>
              </form>
            ))}
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
                  <input type="text" className="input" name="notes"
                    id={`finished-ex-notes-${entry.session_exercise_id}`}
                    defaultValue={entry.notes ?? ''} placeholder="—" />
                </div>
                <button type="submit" className="btn btn--ghost btn--sm">Speichern</button>
              </form>
            )}
          </div>
        ))}
      </Sheet>
      <UndoToast />
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
  const reordered = added.length === 0 && removed.length === 0 &&
    current.join(' ') !== next.join(' ')

  if (added.length === 0 && removed.length === 0 && !reordered) return null
  const parts: string[] = []
  if (added.length > 0) parts.push(`Neu: ${added.join(', ')}.`)
  if (removed.length > 0) parts.push(`Entfällt: ${removed.join(', ')}.`)
  if (reordered) parts.push('Nur die Reihenfolge ändert sich.')
  return parts.join(' ')
}
