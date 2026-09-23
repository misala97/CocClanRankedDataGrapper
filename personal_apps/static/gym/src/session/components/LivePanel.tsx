import { Fragment, useEffect, useRef, useState } from 'react'
import type { SeedSource, SessionDetailPayload, VariantRef } from '../types'
import { useSheets } from '../stores'
import { useRestTick } from '../useRestTick'
import { useRecordTakeover } from '../useRecordTakeover'
import { Icon } from '../../components/Icon'
import { kg1, shortDate } from '../../format'
import { RecordTakeover } from './RecordTakeover'
import { SetRow } from './SetRow'
import { Stepper, type StepperHandle } from './Stepper'

/** The sentence after "Vorgabe". Day and month only: every basis but the
 *  layoff is inside seeding's four-week window, where a year is noise. No
 *  number of weeks in the layoff copy -- the window is a server constant
 *  (stats.ROLLING_WINDOW_DAYS) and a figure here would drift from it.
 *
 *  "Position", not "Slot": the queue, the rail and the reorder announcements
 *  all say Position, and a second word for the same number read as a second
 *  concept. */
function seedSourceText(source: SeedSource, position: number): string {
  const day = shortDate(source.date).slice(0, 6)
  if (source.basis === 'layoff') {
    return `vom ${day} — schon länger her, daher dein letztes Workout statt des besten.`
  }
  if (source.basis === 'earlier_slot') {
    return `vom ${day}, damals an Position ${source.position} — so spät im Workout gibt es noch nichts, daher dein bestes Ergebnis von früher.`
  }
  if (source.position > position) {
    return `vom ${day}, damals später im Workout (Position ${source.position}).`
  }
  return `vom ${day}, gleiche Position im Workout.`
}

/** "Kurzhantel 26,0 kg je Seite × 10 · Maschine, Scheiben 27,5 kg × 10" --
 *  the lifter's other variants of a movement met for the first time. */
function VariantRefs({ refs }: { refs: VariantRef[] }) {
  return (
    <span className="live__refs">
      {'Deine anderen Varianten, zuletzt: '}
      {refs.map((ref, i) => (
        <Fragment key={ref.label}>
          {i > 0 && ' · '}
          <b>{ref.label}</b>
          {` ${kg1(ref.weight)} kg${ref.per_side ? ' je Seite' : ''} × ${ref.reps}`}
        </Fragment>
      ))}
    </span>
  )
}

/** Length of the go-ready keyframes in gym.css. The class comes off after it,
 *  so the ring is an event and not a state the button gets stuck in. */
const READY_RING_MS = 320

interface Props {
  payload: SessionDetailPayload
  /** Confirms `setId`, the open set the steppers are bound to, or appends one
   *  when it is null -- gym_add_set creates it already completed, which is
   *  what "Satz geschafft" means everywhere else on this screen. */
  onConfirm(weight: number, reps: number, setId: number | null): void
  /** A logged chip was tapped: put it back to open. */
  onToggleSet(setId: number, completed: boolean): void
  onRestOver(): void
  /** A set write is still on its way. The confirm button waits for it. */
  confirmBusy?: boolean
}

/**
 * The one lifted panel for the exercise you are on.
 *
 * Three shapes, one workspace. An exercise added mid-workout arrives with no
 * sets at all and is then picked as live and never completes, blocking
 * everything after it -- so an empty exercise gets the same two steppers and
 * the same confirm button; only the endpoint differs. The steppers and the
 * button render in every state including "everything is logged", because the
 * state needed the control, not new machinery.
 */
export function LivePanel({
  payload, onConfirm, onToggleSet, onRestOver, confirmBusy = false,
}: Props) {
  const openSheet = useSheets((s) => s.open)
  const live = payload.visible_exercises.find((se) => se.id === payload.live_id) ?? null

  // Tapping an open chip picks it: the steppers bind to it and "Satz
  // geschafft" logs it. It used to log the chip on the spot with its PLANNED
  // numbers, whatever the steppers said -- a tap to look became a set logged
  // at the wrong weight. The pick lapses by itself once that set is done or
  // the live exercise changes, because it is looked up, never stored as a set.
  const [pickedId, setPickedId] = useState<number | null>(null)
  const picked = live?.sets.find((s) => s.id === pickedId && !s.completed) ?? null
  const nextSet = picked ?? live?.sets.find((s) => !s.completed) ?? null

  // Appending after everything is logged starts from the set you just did, not
  // from the session's opening suggestion: the reason you are adding one is
  // that the last one went well enough to want another.
  //
  // An open set binds to exactly what it holds. A blank one (an exercise with
  // no history) stays blank -- borrowing a number from elsewhere would be the
  // invented prefill the blank plan exists to end.
  const lastDone = live && live.sets.length > 0 ? live.sets[live.sets.length - 1]! : null
  const suggestion = live ? payload.suggestions[String(live.id)] ?? null : null
  const seedWeight = nextSet !== null
    ? nextSet.weight
    : lastDone?.weight ?? suggestion?.weight ?? null
  const seedReps = nextSet !== null
    ? nextSet.reps
    : lastDone?.reps ?? suggestion?.reps ?? null

  const [weight, setWeight] = useState<number | null>(seedWeight)
  const [reps, setReps] = useState<number | null>(seedReps)
  // What is being typed right now, before the entry closes: the go button
  // names the next step from it ("Wdh. eintippen" while the kg is typed).
  const [draftWeight, setDraftWeight] = useState<number | null>(null)
  const [draftReps, setDraftReps] = useState<number | null>(null)
  const kgField = useRef<StepperHandle>(null)
  const repsField = useRef<StepperHandle>(null)

  // The server is authoritative about what comes next; re-seed whenever it
  // says the pending set changed. WHICH set is up decides that, not only what
  // it holds: keyed on the numbers alone, two equal seeds in a row read as
  // "nothing changed", so a bump made for one set carried into the next -- or
  // into the next EXERCISE -- but only when the numbers happened to match, and
  // snapped back when they did not. No carry-forward is the owner's ruling (it
  // would override drop sets and ramp-ups), so the coincidence was the bug.
  // The numbers stay in the list for the other direction: a plan re-seeded in
  // place (a reorder, a partner's reorder) keeps its set ids and changes only
  // what they hold.
  const boundTo = `${live?.id ?? 'none'}:${nextSet?.id ?? `after-${lastDone?.id ?? 'none'}`}`
  useEffect(() => {
    setWeight(seedWeight)
    setReps(seedReps)
  }, [boundTo, seedWeight, seedReps])

  // One ring when the countdown lands, then settle. The rest hitting zero is
  // the cue to start the next set and it arrives with the phone face-down on a
  // bench, so the control announces itself rather than quietly stopping.
  // .go.is-ready has existed in the stylesheet since the Jinja screen; nothing
  // in the port applied it, so the end of a rest was visually silent.
  const [ringing, setRinging] = useState(false)
  useEffect(() => {
    if (!ringing) return
    const timer = setTimeout(() => setRinging(false), READY_RING_MS)
    return () => clearTimeout(timer)
  }, [ringing])

  // Above the `live === null` return, with every other hook, and in THIS
  // component rather than in the island: LivePanel is rendered without a key,
  // so the instance survives a change of live exercise. A hook mounted per
  // exercise would reseed its seen-set to empty on every switch and then
  // celebrate every record already in the payload.
  const { celebration, dismiss } = useRecordTakeover(payload)

  const rest = useRestTick(
    payload.resting ? payload.session.rest_ends_at : null,
    payload.rest_total_seconds,
    { onOver: () => { setRinging(true); onRestOver() } })

  // The countdown follows the lifter into another tab: leaving mid-rest is
  // exactly when this screen is not on screen to show it. The phone has the
  // wake lock and the push notification; the tab title covers the desk.
  useEffect(() => {
    if (!rest.running) return
    const base = document.title
    document.title =
      `${Math.floor(rest.remaining / 60)}:${String(rest.remaining % 60).padStart(2, '0')} Pause · ${base}`
    return () => { document.title = base }
  }, [rest.running, rest.remaining])

  if (live === null && payload.visible_exercises.length > 0) {
    // Every exercise skipped. The server used to call the last skipped one
    // live and put it here under "Jetzt"; now nothing is live, and saying so
    // beats the no-exercises copy below, which would be wrong.
    return (
      <section className="live">
        <h2 className="live__name">Alles übersprungen</h2>
        <p className="live__empty">
          Hol eine Übung über ihr Menü in der Liste zurück — oder füge eine neue hinzu.
        </p>
        <button type="button" className="go"
          onClick={() => openSheet('sheet-add-exercise')}>
          <Icon name="plus" />
          Übung hinzufügen
        </button>
      </section>
    )
  }

  if (live === null) {
    return (
      /* A workout started without a template has no exercises at all, and the
         only route to one was the sheet in the top corner. The panel is the
         one place on this screen guaranteed to be looked at, so the first
         action belongs in it -- as the same solid control every other state
         puts in this slot, not as a link in the copy.

         Not .live__kick: that carries the hot NOW dot, and nothing is
         happening now. The panel is lifted because it holds the only action. */
      <section className="live">
        <h2 className="live__name">Noch keine Übung</h2>
        <p className="live__empty">
          Füge die erste Übung hinzu — sie bleibt danach in deiner Liste.
        </p>
        <button type="button" className="go"
          onClick={() => openSheet('sheet-add-exercise')}>
          <Icon name="plus" />
          Übung hinzufügen
        </button>
      </section>
    )
  }

  const stall = payload.stagnation_counts[String(live.id)]
  const stallNext = payload.stall_next_weight[String(live.id)]
  const source = payload.seed_sources[String(live.id)] ?? null
  const firstTime = payload.first_time[String(live.id)]
  const ready = payload.ready_for_more
  const perSide = live.is_unilateral ? ' je Seite' : ''
  const records = live.sets.filter(
    (s) => s.completed && payload.record_set_ids.includes(s.id))

  return (
    <section className="live" data-se-id={live.id}>
      {celebration !== null && (
        <RecordTakeover celebration={celebration} onDismiss={dismiss} />
      )}
      <div className="live__head">
        <span className="live__kick">Jetzt</span>
        <button type="button" className="live__more"
          aria-label={`${live.name} — Optionen`}
          onClick={() => openSheet(`sheet-ex-${live.id}`)}>
          <Icon name="more" />
        </button>
      </div>
      <h2 className="live__name">{live.name}</h2>

      {/* Above the workspace, not below it. This is advice about the numbers
          you are about to set, and it used to render under the 64px confirm
          button -- after the control you would act on it with, and off-screen
          on a phone by the time you had scrolled to the queue. */}
      {stall !== undefined && (
        <p className="live__stall">
          <span className="live__stall-lbl">Stagniert</span>
          {/* The prescription is said, never seeded -- the steppers stay on
              the proven weight, and going up is the lifter's call. Same
              number and same copy as the debrief's Nächstes-Mal advice. */}
          {stallNext !== undefined
            ? ` ${stall} Workouts ohne neuen e1RM-PR — auf ${kg1(stallNext)} kg gehen, notfalls 2 Wdh. weniger.`
            : ` ${stall} Workouts ohne neuen e1RM-PR — mehr Gewicht oder Wdh. versuchen.`}
        </p>
      )}

      {/* Same slot and the same reason. The two never contradict each other --
          stagnation counts sessions without a PR, this reads the last
          session's reps -- but if both fire, both are worth saying. */}
      {/* Names the step as well as the evidence for it, with the same step-up
          the stall line uses. Said, not seeded, like that one. A stack that
          is topped out has no next weight and keeps the evidence alone. */}
      {ready !== null && (
        <p className="live__ready">
          <span className="live__ready-lbl">Bereit</span>
          {` ${ready.is_latest ? 'Letztes Mal' : 'Zuletzt an dieser Position'} ${ready.sets} Sätze auf ${kg1(ready.weight)} kg${perSide} mit ${payload.min_full_reps}+ Wdh.`}
          {ready.next_weight !== null && ` Zeit für ${kg1(ready.next_weight)} kg${perSide}.`}
        </p>
      )}

      {/* Where the numbers below come from, said rather than left to guess.
          Seeding reads the slot as a fatigue proxy, so moving an exercise can
          change its plan -- or, this late in a workout, visibly NOT change it,
          because nothing was ever lifted that late and the best earlier result
          stands in. The owner kept that fallback on the condition that the
          screen says so. Quiet: same note anatomy, no ink of its own. */}
      {source !== null && (
        <p className="live__seed">
          <span className="live__seed-lbl">Vorgabe</span>
          {` ${seedSourceText(source, live.position)}`}
        </p>
      )}
      {/* The other half of the same slot: no history, so no Vorgabe -- the
          plan is blank and the lifter types the first set. The other
          variants' numbers are a reference, never a prefill: a dumbbell's
          kilos are not a barbell's. */}
      {firstTime !== undefined && (
        <p className="live__seed">
          <span className="live__seed-lbl">Erstes Mal</span>
          {' Tipp ein, womit du anfängst — die nächsten Sätze übernehmen es.'}
          {firstTime.length > 0 && <VariantRefs refs={firstTime} />}
        </p>
      )}

      {live.sets.length > 0 && (
        <div className="sets">
          {live.sets.map((s, i) => (
            // .set-form is what gives the chips their `flex: 1 1 5.5rem`, so
            // they share a row instead of stacking. It was a <form> before the
            // port and is a plain wrapper now -- the class is load-bearing for
            // layout, not for semantics.
            <div className="set-form" key={s.id}>
              <SetRow set={s} ordinal={i + 1}
                isRecord={payload.record_set_ids.includes(s.id)}
                isNext={nextSet !== null && s.id === nextSet.id}
                isUnilateral={live.is_unilateral}
                onToggle={(setId, completed) => {
                  if (completed) setPickedId(setId)
                  else onToggleSet(setId, false)
                }} />
            </div>
          ))}
        </div>
      )}

      {records.length > 0 && (
        <p className="live__record">
          <span className="live__record-lbl">Rekord</span>
          {/* "Bestwert", not "schwerer": is_new_best counts an e1RM record too,
              so a set can land here at a lighter weight and more reps. */}
          {records.length === 1
            ? ` Satz ${live.sets.indexOf(records[0]!) + 1} ist ein neuer Bestwert in dieser Übung.`
            : ` ${records.length} Sätze über deinem bisherigen Bestwert.`}
        </p>
      )}

      {live.sets.length === 0 && (
        <p className="live__empty">
          {`Noch keine Sätze. Der erste wird angelegt, sobald du ihn bestätigst${suggestion ? ` — zuletzt ${kg1(suggestion.weight)} kg × ${suggestion.reps}` : ''}.`}
        </p>
      )}
      {live.sets.length > 0 && nextSet === null && (
        <p className="live__alldone">
          Alle Sätze erledigt. Unten beenden — oder hier noch einen anhängen.
        </p>
      )}

      <div className="pair">
        {/* "Weiter" on the keypad walks from a typed kg straight into the
            reps while those are still blank -- the whole first set without
            reaching for the screen between the two numbers. */}
        <Stepper ref={kgField} label={`kg${perSide}`} value={weight}
          step={payload.live_increment} decimals={1}
          floor={payload.live_floor ?? payload.live_increment}
          ariaLabel="Gewicht eingeben"
          enterHint={reps === null ? 'next' : 'done'}
          onEnter={reps === null ? () => repsField.current?.open() : undefined}
          onDraft={setDraftWeight} onChange={setWeight} />
        <Stepper ref={repsField} label="Wdh." value={reps} step={1} decimals={0} min={1}
          ariaLabel="Wiederholungen eingeben"
          enterHint={weight === null ? 'next' : 'done'}
          onEnter={weight === null ? () => kgField.current?.open() : undefined}
          onDraft={setDraftReps} onChange={setReps} />
      </div>

      {/* The rest does not take this slot -- it runs THROUGH it. The button is
          present and pressable for the whole countdown; the band charges
          underneath. aria-hidden on the clock keeps the accessible name stable
          at "Satz geschafft": a name that rewrote itself every second would be
          worse than no countdown, and the announcement lives in the live
          region, which speaks twice per rest rather than ninety times. */}
      {/* Disabled for the length of the round trip: a sweaty double-tap on a
          64px thumb target is normal use, and the second press must not race
          the first one's answer. It keyed on the NEXT set's id, which is null
          the moment the last set is optimistically done -- so the second tap
          on an exercise's last set went down the append path and logged a set
          nobody did. Any set write in flight holds it now. No visual disabled
          treatment: the window is a few hundred ms, and styling a flash would
          be noise. */}
      {/* While a number is missing the button asks for it rather than
          logging: it opens the entry, keypad up, and says which number it
          wants -- a draft being typed counts, so the label has moved on by
          the time the thumb does. A tap cannot log a set without both. */}
      <button type="button"
        className={`go${rest.running ? ' is-resting' : ''}${ringing ? ' is-ready' : ''}`}
        id="set-confirm" disabled={confirmBusy}
        onClick={() => {
          if (weight === null) kgField.current?.open()
          else if (reps === null) repsField.current?.open()
          else onConfirm(weight, reps, nextSet?.id ?? null)
        }}>
        <span className="go__lbl">
          {weight === null && draftWeight === null
            ? 'Gewicht eintippen'
            : reps === null && draftReps === null
              ? 'Wdh. eintippen'
              : <><Icon name="check" />Satz geschafft</>}
        </span>
        {rest.running && (
          <>
            {/* "Pause" is said: a bare 2:59 inside a button labelled "Satz
                geschafft" read as anything but the rest. Stacked above the
                time (gym.css), so it costs no width beside the label. */}
            <span className="go__clock" aria-hidden="true">
              <span className="go__clock-lbl">Pause</span>
              {`${Math.floor(rest.remaining / 60)}:${String(rest.remaining % 60).padStart(2, '0')}`}
            </span>
            <span className="go__band" aria-hidden="true">
              <span className="go__charge"
                style={{ transform: `scaleX(${rest.progress})` }} />
            </span>
          </>
        )}
      </button>
    </section>
  )
}
