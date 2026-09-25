import {
  Fragment, useId, useLayoutEffect, useRef, useState, type CSSProperties, type FormEvent,
  type ReactNode,
} from 'react'
import { CsrfField } from '../csrf'
import type { CorrectableSet, FinishedExercise, FinishedPayload, TargetSet } from './types'
import { postForm, MutationFailed } from '../api'
import { dayDate, instant, kg, kg1, localParts, shortDate, volume as de, weekdayDate } from '../format'
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
import { PARTNER_SHEET } from '../partner/PartnerLine'
import { MitPartner, PartnerSheet } from '../partner/PartnerSheet'
import type { PartnerRef } from '../partner/types'
import { sincePr } from '../catalogue/format'

/** A record is e1RM only (D3). The flare names it in full, its first use on
 *  the page; the rows under it say 1RM (D16). */
const E1RM_FULL = 'geschätztes Maximum (1RM)'

const pad = (n: number) => String(n).padStart(2, '0')

/** A sentence ending on a date: "24.07." is its own full stop, a year is not. */
const sentenceEnd = (date: string) => (date.endsWith('.') ? date : `${date}.`)

/** The comparison's sign: "+2", "−3" with a true minus, "±0". */
const signedPct = (pct: number) => (pct > 0 ? `+${pct}` : pct < 0 ? `−${-pct}` : '±0')

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

type Line = { weight: number; reps: number; is_record?: boolean }[]

/** Where a line of sets names its weight: the first set and every change,
 *  as setsLine and the exercise page's target line do. */
const heads = (sets: Line) =>
  sets.map((set, i) => i === 0 || set.weight !== sets[i - 1]!.weight)

/** Whether next time names its weights at the places this workout did --
 *  then the two lines stand set under set. */
function samePlaces(done: Line, next: Line): boolean {
  const said = heads(next)
  return heads(done).slice(0, said.length).every((head, i) => head === said[i])
}

/** A line of sets that runs on: the weight only where it changes, and a dot
 *  before every set but the first, so a wrapped line starts with one. */
function FlowLine({ sets, next = false }: { sets: Line; next?: boolean }) {
  const named = heads(sets)
  return (
    <>
      {sets.map((set, i) => (
        <Fragment key={i}>
          {i > 0 && <wbr />}
          <span className={`steps__set${next ? ' steps__set--next' : ''}${set.is_record ? ' is-record' : ''}`}>
            {i > 0 && <i>·</i>}
            {named[i] && <>{kg(set.weight)}<small>kg</small><i>×</i></>}
            <span className="steps__r">{set.reps}</span>
          </span>
        </Fragment>
      ))}
    </>
  )
}

/** The same line as grid cells -- dot, weight, ×, reps per set, each its own
 *  column -- so weights and reps line up down the two lines. */
function GridCells({ sets, next = false }: { sets: Line; next?: boolean }) {
  const named = heads(sets)
  const bold = next ? ' steps__c--next' : ''
  return (
    <>
      {sets.map((set, i) => (
        <Fragment key={i}>
          <span className="steps__c steps__c--sep">{i > 0 ? '·' : ''}</span>
          <span className={`steps__c steps__c--w${bold}`}>
            {named[i] && <>{kg(set.weight)}<small>kg</small></>}
          </span>
          <span className="steps__c steps__c--x">{named[i] ? '×' : ''}</span>
          <span className={`steps__c steps__c--r${bold}${set.is_record ? ' is-record' : ''}`}>
            <span className="steps__r">{set.reps}</span>
          </span>
        </Fragment>
      ))}
    </>
  )
}

/**
 * What was done and, while the plan still builds on it, next time (D10):
 * set under set, so 10 -> 11 reads straight down, where next time builds on
 * these very sets with the weights at the same places. A deload's plan comes
 * from the workout before it, so there each line runs on its own. A set that
 * beat the record has its reps washed gold, as its tick is.
 *
 * A grid cannot wrap: set under set wider than its row -- a pyramid's
 * weights, many sets on a phone -- pushed the page sideways, so there the
 * lines run on too. Measured, since the digits and the font decide; a row
 * wide enough again (the phone turned) stands them set under set.
 */
function Steps({ done, next, paired }: {
  done: CorrectableSet[]
  next: TargetSet[] | null
  paired: boolean
}) {
  const box = useRef<HTMLSpanElement>(null)
  // The width set under set needs, once it did not fit; null while it does.
  const [need, setNeed] = useState<number | null>(null)

  useLayoutEffect(() => {
    const node = box.current
    if (node === null || !paired) return
    const measure = () => {
      if (need === null) {
        if (node.scrollWidth > node.clientWidth + 1) setNeed(node.scrollWidth)
      } else if (node.clientWidth >= need) {
        setNeed(null)
      }
    }
    measure()
    // The web font lands after the first paint, and widens the figures.
    let live = true
    document.fonts?.ready.then(() => { if (live) measure() })
    if (typeof ResizeObserver === 'undefined') return () => { live = false }
    const observer = new ResizeObserver(measure)
    observer.observe(node)
    return () => { live = false; observer.disconnect() }
  }, [paired, need, done, next])

  if (next === null) {
    return <span className="steps__done"><FlowLine sets={done} /></span>
  }
  if (paired && need === null) {
    const columns = { '--n': Math.max(done.length, next.length) } as CSSProperties
    return (
      <span className="steps" style={columns} ref={box}>
        <span className="steps__k">Geschafft</span>
        <GridCells sets={done} />
        <span className="steps__k">Nächstes Mal</span>
        <GridCells sets={next} next />
      </span>
    )
  }
  return (
    <span className="steps steps--flow" ref={box}>
      <span className="steps__k">Geschafft</span>
      <span className="steps__line"><FlowLine sets={done} /></span>
      <span className="steps__k">Nächstes Mal</span>
      <span className="steps__line"><FlowLine sets={next} next /></span>
    </span>
  )
}

/** One exercise: its name leads, the figures under it, then what it beat or
 *  how long it has stood still. The whole block opens the exercise page. The
 *  one chip left is "Rekord" (D10). */
function ExerciseRow({ entry, isDeload, chip }: {
  entry: FinishedExercise
  isDeload: boolean
  chip: boolean
}) {
  const next = entry.next_sets
  const paired = !isDeload && next !== null && samePlaces(entry.set_rows, next)
  return (
    <div className="row exrow">
      <a className="row__main exrow__main" href={`/gym/exercises/${entry.exercise_id}`}>
        <span className="row__name">{entry.name}</span>
        <Steps done={entry.set_rows} next={next} paired={paired} />
        {entry.record !== null && (
          <span className="exrow__rec">
            {'Rekord: 1RM '}
            <b>{`${kg1(entry.record.value)} kg`}</b>
            {`, vorher ${kg1(entry.record.previous)} kg`}
          </span>
        )}
        {entry.verdict === 'stagniert' && (
          <span className="exrow__stall">{sincePr(entry.sessions_since_pr, true)}</span>
        )}
        {entry.verdict === 'neu' && <span className="exrow__first">Zum ersten Mal</span>}
      </a>
      {chip && entry.record !== null && (
        <span className="row__trail"><span className="vtag vtag--record">Rekord</span></span>
      )}
    </div>
  )
}

export function FinishedPage({ payload: initial }: { payload: FinishedPayload }) {
  // Back closes an open sheet, not the debrief (G-066).
  useSheetHistory()
  const openSheet = useSheets((s) => s.open)
  // The server's answer to every save IS the next payload (_mutation_response
  // returns FinishedPayload for a finished session), so a correction re-renders
  // the whole debrief -- the counts, the comparison, the rows and their plan
  // for next time -- without a reload, and the sheet you saved from stays open.
  const [payload, setPayload] = useState(initial)
  const [saveError, setSaveError] = useState<string | null>(null)
  // The partner whose list is open ("mit <Name>").
  const [partnerShown, setPartnerShown] = useState<PartnerRef | null>(null)
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
  const { comparison, plan_moved_to: moved } = payload
  // A fresh lifter's every exercise records at once -- seven identical gold
  // chips is "rare by construction" failing visibly. One gold sentence keeps
  // the currency, and each row still says what it beat.
  const allRecords = payload.exercises.length >= 3
    && payload.exercises.every((entry) => entry.record !== null)
  const planned = payload.exercises.some((entry) => entry.next_sets !== null)

  return (
    <>
      <header className="session-top">
        <a href="/gym/verlauf" className="session-top__back" aria-label="Zurück zum Verlauf">
          <Icon name="back" />
        </a>
        {/* An <h1>, the page's title: the workout's name. The date is printed
            once -- the name often already embeds one, and on older rows the two
            disagreed because the name was built from UTC. */}
        <span className="session-top__name stack">
          <h1 className="finished__name" style={{ viewTransitionName: 'session' }}>{session.name ?? 'Workout'}</h1>
          <span className="finished__when">
            {`${weekday} ${shortDate(session.started_at)} · ${minutes(elapsed)}`}
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
          {/* Whom it was done with, and their list as it ended (D14). */}
          {payload.partners.map((partner) => (
            <MitPartner key={partner.id} partner={partner} onOpen={(p) => {
              setPartnerShown(p)
              openSheet(PARTNER_SHEET)
            }} />
          ))}
        </span>
        {/* A label, not a state (4.2): the word in an outline, at the 13px
            floor where the header's caps pill was 11px. */}
        {session.is_deload && (
          <span className="vtag vtag--deload finished__deload">
            {payload.deload_applied
              ? `Deload ${session.deload_pct ?? payload.deload_default_pct} %`
              : 'Deload'}
          </span>
        )}
      </header>

      {/* What was done, first: the live screen's readout, closed. The counts
          sit beside it, not in tiles of their own (G-011, G-121). */}
      {payload.total_sets > 0 ? (
        <div className="grew">
          <span className="grew__num">{de(payload.total_volume)}</span>
          <span className="grew__unit">kg bewegt</span>
          <span className="grew__sp" />
          <span className="grew__side">
            <b>{payload.total_sets}</b>{payload.total_sets === 1 ? ' Satz' : ' Sätze'}
            <br />
            <b>{payload.exercises.length}</b>
            {payload.exercises.length === 1 ? ' Übung' : ' Übungen'}
          </span>
        </div>
      ) : (
        <p className="finished__cmp">Kein Satz erfasst — dieses Workout zählt nicht mit.</p>
      )}

      {/* The one comparison (D10): against the two newest earlier workouts
          of the routine done in full, both named and a tap away. Neutral ink
          either way -- a minus is a fact, not a warning (G-079) -- and no line
          at all where the comparison would mislead (G-087). */}
      {comparison !== null ? (
        <p className="finished__cmp">
          <b>{`${signedPct(comparison.pct)} %`}</b>
          {' zum Schnitt von '}
          {comparison.against.map((other, i) => (
            <Fragment key={other.id}>
              {i > 0 && ' und '}
              <a href={`/gym/session/${other.id}`}>{weekdayDate(other.started_at)}</a>
            </Fragment>
          ))}
        </p>
      ) : session.is_deload && payload.total_sets > 0 && (
        <p className="finished__cmp">Deload: bewusst leichter, darum ohne Vergleich.</p>
      )}

      {payload.tick_states.length > 0 && (
        <div className="ticks" role="img"
          aria-label={`${payload.total_sets} ${payload.total_sets === 1 ? 'Satz' : 'Sätze'} erledigt${tickRecords ? `, davon ${tickRecords} mit Rekord` : ''}`}>
          {payload.tick_states.map((tick, i) => (
            <span key={i} className={tick === 'record' ? 'tick is-record' : 'tick is-on'} />
          ))}
        </div>
      )}

      {/* ONE flare, and the set that made it. is-fresh only when you just
          finished: revisiting a three-week-old session from Verlauf is
          reading, not celebrating. Every other record says itself on its own
          row below. */}
      {lead !== undefined && (
        <a className={payload.just_finished ? 'record-flare is-fresh' : 'record-flare'}
          href={`/gym/exercises/${lead.exercise_id}`}>
          <div className="record-flare__kind">Neuer Rekord</div>
          <div className="record-flare__name">{lead.name}</div>
          <div className="record-flare__row">
            <span className="record-flare__num">{kg1(lead.value)}</span>
            <span className="record-flare__unit">kg</span>
          </div>
          <div className="record-flare__prev">
            {`${E1RM_FULL}, aus ${kg(lead.weight)} kg × ${lead.reps} · vorher ${kg1(lead.previous)} kg am ${dayDate(lead.previous_at)}`}
          </div>
        </a>
      )}

      {(payload.exercises.length > 0 || payload.unlogged.length > 0) && (
        <section className="finished__sec" aria-labelledby="sec-uebungen">
          <h2 className="finished__h" id="sec-uebungen">Übungen</h2>
          {/* Its "next time" has happened: a newer workout of the routine
              came after this one, and the plan is built there now -- all
              but a lift that workout left out, which still plans here. */}
          {moved !== null && (
            <a className="finished__moved" href={`/gym/session/${moved.id}`}>
              <span>
                {planned ? 'Der Plan für die übrigen Übungen steht jetzt beim Workout vom '
                  : 'Der Plan fürs nächste Mal steht jetzt beim Workout vom '}
                <b>{weekdayDate(moved.started_at)}</b>
              </span>
              <Icon name="forward" />
            </a>
          )}
          {session.is_deload && planned && (
            /* A deload is no base: next time builds on what came before it --
               under the pointer too, for a lift the newer workout left out. */
            <p className="finished__note">
              {`Nächstes Mal wieder mit deinen Arbeitsgewichten, aufgebaut auf ${
                payload.plan_base !== null
                  ? sentenceEnd(weekdayDate(payload.plan_base.started_at))
                  : 'dem jeweils letzten Workout davor.'}`}
            </p>
          )}
          {allRecords && (
            <p className="finished__allpr">{`Alle ${payload.exercises.length} Übungen mit Rekord.`}</p>
          )}
          {payload.exercises.map((entry) => (
            <ExerciseRow entry={entry} isDeload={session.is_deload} chip={!allRecords}
              key={entryKey(entry)} />
          ))}
          {/* Also for a workout with nothing logged: its sheet is where a set
              that never got its tap can still be entered. */}
          <button type="button" className="finished__correct"
            aria-haspopup="dialog" aria-controls="sheet-correct"
            onClick={() => openSheet('sheet-correct')}>
            <Icon name="edit" />
            Sätze &amp; Notizen
          </button>
        </section>
      )}

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

      {/* One way on (G-045): to Start after finishing, back to Verlauf when
          the workout was opened again from there. */}
      <div className="outs">
        {payload.just_finished
          ? <a href="/gym" className="btn btn--live">Zum Start</a>
          : <a href="/gym/verlauf" className="btn btn--live">Zurück zum Verlauf</a>}
      </div>

      {/* Deleting a workout is a rare correction, not the way out of this
          screen. It used to be the largest, brightest, right-most element. */}
      {saveError !== null && (
        <p className="flash flash--error" role="alert">{saveError}</p>
      )}
      <div className="quiet-acts">
        {/* The offer above shows only on arrival; a workout opened again from
            Verlauf keeps it here, first (G-077, Q6). */}
        {!payload.just_finished && routineDiff !== null && (
          <button type="button" className="quiet-acts__btn"
            onClick={() => openSheet('sheet-routine')}>
            {`Routine „${session.template_name}“ aktualisieren …`}
          </button>
        )}
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

      {payload.partners.length > 0 && <PartnerSheet target={partnerShown} dated />}

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
