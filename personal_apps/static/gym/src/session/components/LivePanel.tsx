import { Fragment, useEffect, useLayoutEffect, useRef, useState } from 'react'
import type { SeedSource, SessionDetailPayload, VariantRef } from '../types'
import { useOutbox, useSheets } from '../stores'
import { clearDraft, readDraft, saveDraft } from '../drafts'
import { setName } from '../setName'
import { useRestTick } from '../useRestTick'
import { useRecordTakeover } from '../useRecordTakeover'
import { Icon } from '../../components/Icon'
import { kg, setsLine, shortDate, whenSaid } from '../../format'
import { MAX_REPS, MAX_WEIGHT_KG, REPS_HINT, WEIGHT_HINT, unlikely } from '../../setInput'
import { REST_MAX, REST_NUDGE, clock } from '../../settings/values'
import { Drawing, PictureTile } from './Picture'
import { RecordTakeover } from './RecordTakeover'
import { SetRow } from './SetRow'
import { Stepper, type StepperHandle } from './Stepper'

/** How long a freshly shown or moved rest band ignores taps: longer than the gap
 *  between a double tap's two presses, shorter than any deliberate reach. */
export const BAND_ARMS_MS = 600

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
          {` ${kg(ref.weight)} kg${ref.per_side ? ' je Seite' : ''} × ${ref.reps}`}
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
  /** "−15" / "+15" on the running rest. */
  onShiftRest(seconds: number): void
  /** End the running rest now. */
  onSkipRest(): void
}

/** How long "Satz geschafft" ignores a second tap after a set: the first
 *  tap bouncing, not a set -- the next chip is up at once, and a bounce
 *  logged it too. It used to wait for the server's answer instead, which
 *  offline never came (G-138). */
export const CONFIRM_GUARD_MS = 600

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
  payload, onConfirm, onToggleSet, onRestOver, onShiftRest, onSkipRest,
}: Props) {
  const openSheet = useSheets((s) => s.open)
  const sessionId = payload.session.id
  // The chips whose write the phone is holding (B6): marked, never locked.
  const waitingIds = useOutbox((s) => s.setIds)
  const live = payload.visible_exercises.find((se) => se.id === payload.live_id) ?? null

  // Tapping an open chip picks it: the steppers bind to it and "Satz
  // geschafft" logs it. It used to log the chip on the spot with its PLANNED
  // numbers, whatever the steppers said -- a tap to look became a set logged
  // at the wrong weight. The pick lapses by itself once that set is done or
  // the live exercise changes, because it is looked up, never stored as a set.
  // By name: a set just added changes id when it lands (B6 re-review).
  const [pickedName, setPickedName] = useState<string | null>(null)
  const picked = live?.sets.find((s) => setName(s) === pickedName && !s.completed) ?? null
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

  // Which set the steppers are for -- see the re-seed below. A set this
  // screen added is named by its key: its id changes when the server names
  // it (B6), and the numbers dialled for it, or after it, are still for the
  // same set -- a reopened one was re-seeded as it landed (B6 re-review).
  const boundTo = `${live?.id ?? 'none'}:${nextSet !== null
    ? setName(nextSet) : `after-${lastDone === null ? 'none' : setName(lastDone)}`}`
  // A draft left by the page before a reload, drawn from the first frame.
  const [restored] = useState(() => readDraft(sessionId, boundTo))
  const [weight, setWeight] = useState<number | null>(restored?.weight ?? seedWeight)
  const [reps, setReps] = useState<number | null>(restored?.reps ?? seedReps)
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
  // What was last put on the steppers from outside, so the effect below runs
  // once per change -- not twice under StrictMode, which would throw the
  // draft it just restored away.
  const seeded = useRef<string | null>(null)
  useEffect(() => {
    const seed = `${boundTo}|${seedWeight}|${seedReps}`
    if (seeded.current === seed) return
    const first = seeded.current === null
    seeded.current = seed
    // A reload drops component state, and with it the numbers the lifter
    // had dialled in (G-009): the first seed after a mount takes their
    // draft for the same set over the plan. Any later seed is the server
    // saying the set, or its plan, changed -- the draft is over.
    const draft = first ? readDraft(sessionId, boundTo) : null
    if (draft !== null) {
      setWeight(draft.weight)
      setReps(draft.reps)
      return
    }
    if (!first) clearDraft(sessionId)
    setWeight(seedWeight)
    setReps(seedReps)
    setAskedAbout(null)
  }, [boundTo, seedWeight, seedReps, sessionId])
  // The numbers "Sicher?" was asked about (Q5, G-070): the next tap on the
  // button logs them. Other numbers ask again.
  const [askedAbout, setAskedAbout] = useState<string | null>(null)
  // Kept as it is set, for the set it is set for.
  const dial = (next: { weight: number | null; reps: number | null }) => {
    setWeight(next.weight)
    setReps(next.reps)
    setAskedAbout(null)
    saveDraft(sessionId, { bound: boundTo, ...next })
  }
  const lastConfirm = useRef(-Infinity)

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

  // Which exercise's Vorgabe rule is spelled out. Kept per exercise rather
  // than as a flag, so the next exercise going live starts on the one line.
  const [sourceOpenFor, setSourceOpenFor] = useState<number | null>(null)

  // The last rest's end, while no set has been logged since (a new set
  // replaces it; reopening or deleting its set, or the finish, clears it):
  // the band counts down to it, then up from it (round 4).
  const rest = useRestTick(
    payload.session.resting_set_id !== null ? payload.session.rest_ends_at : null,
    payload.rest_total_seconds,
    { stopped: !payload.resting, onOver: () => { setRinging(true); onRestOver() } })

  // A band that has only just appeared pushed the confirm button down under
  // a thumb already on its way: a double tap on "Satz geschafft" landed its
  // second tap on "−15" (I1 review). Staying until the next set (round 4),
  // the band can also be pushed down by the card above it -- the next
  // exercise's name, a line that comes -- onto where the button was
  // (fix-round review). Either way its keys wait BAND_ARMS_MS. A band that
  // moves UP leaves that spot to what is below the button, so it stays armed:
  // closing the Vorgabe and reaching for "+15" is no double tap. Measured in
  // the commit that moved it, before the next paint or tap; against the
  // page, so scrolling is no move.
  const band = rest.running || rest.over
  const bandRef = useRef<HTMLDivElement>(null)
  const bandArm = useRef({ since: 0, top: Number.NaN })
  useLayoutEffect(() => {
    if (bandRef.current === null) {
      bandArm.current.top = Number.NaN
      return
    }
    const top = bandRef.current.getBoundingClientRect().top + window.scrollY
    const last = bandArm.current.top
    if (Number.isNaN(last) || top - last >= 1) bandArm.current = { since: Date.now(), top }
    else bandArm.current.top = top
  })
  const armed = (act: () => void) => () => {
    if (Date.now() - bandArm.current.since >= BAND_ARMS_MS) act()
  }

  // The countdown follows the lifter into another tab: leaving mid-rest is
  // exactly when this screen is not on screen to show it. The phone has the
  // wake lock and the push notification; the tab title covers the desk.
  useEffect(() => {
    if (!rest.running) return
    const base = document.title
    document.title =
      `${clock(rest.remaining)} Pause · ${base}`
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
  const target = payload.next_targets[String(live.id)]
  const deloadHint = payload.deload_hints[String(live.id)]
  const deloadPct = payload.session.deload_pct
  const source = payload.seed_sources[String(live.id)] ?? null
  const firstTime = payload.first_time[String(live.id)]
  const perSide = live.is_unilateral ? ' je Seite' : ''
  const records = live.sets.filter(
    (s) => s.completed && payload.record_set_ids.includes(s.id))
  // More than twice the best at the exercise: asked once before it is
  // logged -- a slip of the thumb made a record that stayed (Q5, G-070).
  const doubt = weight === null || reps === null
    ? null : unlikely({ weight, reps }, live.best, `kg${perSide}`)
  const asking = doubt !== null && askedAbout === `${weight}|${reps}`

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
      {/* The drawing beside the name (round 4), a tap from the sheet that
          shows it whole. Not drawn yet: the dumbbell, keeping the name where
          it always is, and no second way into the sheet that has no picture. */}
      <div className="live__title">
        {live.picture !== null
          ? (
            <button type="button" className="pic pic--live"
              aria-label={`${live.name} — Bild`}
              onClick={() => openSheet(`sheet-ex-${live.id}`)}>
              <Drawing src={live.picture} />
            </button>
          )
          : <PictureTile src={null} size="live" />}
        <h2 className="live__name">{live.name}</h2>
      </div>
      {/* Today's twinge and note, where the lifter looks before the set
          (G-073): saved in the sheet, they showed nowhere else. */}
      {(live.pain || Boolean(live.notes)) && (
        <p className="live__meta">
          {live.pain && <span className="chip chip--pain">Zwicken</span>}
          {Boolean(live.notes) && <span className="live__note">{live.notes}</span>}
        </p>
      )}

      {/* Above the workspace, not below it. This is advice about the numbers
          you are about to set, and it used to render under the 64px confirm
          button -- after the control you would act on it with, and off-screen
          on a phone by the time you had scrolled to the queue. */}
      {/* The fact only: what to lift is the target's to say (D2 P1). The
          stall line used to name a weight of its own, and "Bereit" a third
          -- two answers that could disagree with the one below. */}
      {stall !== undefined && (
        <p className="live__stall">
          <span className="live__stall-lbl">Stagniert</span>
          {` ${stall} Workouts ohne neuen Rekord.`}
        </p>
      )}

      {/* What to lift today, set by set (D2 P1, G-035): double progression
          from the workout the line under it names, in that line's notation.
          Said, never seeded: the steppers keep last time's numbers, and
          going up is the lifter's call. First, as on the exercise page
          (M2): the aim, then where the plan came from. */}
      {target !== undefined && (
        <p className="targetline">
          <span className="targetline__lbl">Ziel</span>
          {' '}
          <span className="targetline__val">{setsLine(target)}</span>
        </p>
      )}
      {/* D4: a deload marked after the first set rescales nothing (the 08-12
          rule), so an exercise not started yet says what the deload would
          have planned -- in its target's place, as a deload aims at nothing. */}
      {deloadHint !== undefined && (
        <p className="targetline targetline--deload">
          <span className="targetline__lbl">{`Deload${deloadPct !== null ? ` ${deloadPct} %` : ''}`}</span>
          {' '}
          <span className="targetline__val">{`≈ ${kg(deloadHint)} kg${perSide}`}</span>
        </p>
      )}

      {/* Where the numbers below come from, said rather than left to guess.
          One line now (G-053, D8): what was lifted and when, which is what a
          lifter reads it for. The rule behind it is one tap away -- seeding
          reads the slot as a fatigue proxy, so moving an exercise can change
          its plan or, this late in a workout, visibly NOT change it, and the
          owner kept that fallback on the condition that the screen says so.
          "Letztes Mal" only when it was: the best result lately can be ten
          days old with a lighter workout since. */}
      {source !== null && (
        <>
          <button type="button" className="seedline"
            aria-expanded={sourceOpenFor === live.id} aria-controls={`seed-rule-${live.id}`}
            onClick={() => setSourceOpenFor(sourceOpenFor === live.id ? null : live.id)}>
            <span className="seedline__lbl">
              {`${source.is_latest ? 'Letztes Mal' : 'Stärkstes Workout'} ${whenSaid(source.date)}`}
            </span>
            {' '}
            <span className="seedline__val">{setsLine(source.sets)}</span>
            <Icon name="forward" />
          </button>
          {sourceOpenFor === live.id && (
            <p className="live__seed" id={`seed-rule-${live.id}`}>
              <span className="live__seed-lbl">Vorgabe</span>
              {` ${seedSourceText(source, live.position)}`}
            </p>
          )}
        </>
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
            // Keyed by name: as a set just added lands, its chip -- and the
            // keyboard focus on it -- stays.
            <div className="set-form" key={setName(s)}>
              <SetRow set={s} ordinal={i + 1}
                // Only a done set is gold: an un-log waiting out its undo
                // keeps the record the server named (SessionIsland).
                isRecord={s.completed && payload.record_set_ids.includes(s.id)}
                isNext={nextSet !== null && s.id === nextSet.id}
                // What "Satz geschafft" will log, on the chip it logs (G-054):
                // the plan stayed on it while the steppers said otherwise.
                now={nextSet !== null && s.id === nextSet.id ? { weight, reps } : undefined}
                isUnilateral={live.is_unilateral}
                waiting={waitingIds.includes(s.id)}
                onToggle={(setId, completed) => {
                  if (completed) setPickedName(setName(s))
                  else onToggleSet(setId, false)
                }} />
            </div>
          ))}
        </div>
      )}

      {records.length > 0 && (
        <p className="live__record">
          <span className="live__record-lbl">Rekord</span>
          {/* "Bestwert", not "schwerer": a record is e1RM only (D3), so a set
              can land here at a lighter weight and more reps. */}
          {records.length === 1
            ? ` Satz ${live.sets.indexOf(records[0]!) + 1} ist ein neuer Bestwert in dieser Übung.`
            : ` ${records.length} Sätze über deinem bisherigen Bestwert.`}
        </p>
      )}

      {live.sets.length === 0 && (
        <p className="live__empty">
          {`Noch keine Sätze. Der erste wird angelegt, sobald du ihn bestätigst${suggestion ? ` — zuletzt ${kg(suggestion.weight)} kg × ${suggestion.reps}` : ''}.`}
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
          step={payload.live_increment} decimals={2}
          floor={payload.live_floor ?? payload.live_increment}
          max={MAX_WEIGHT_KG} refusedHint={WEIGHT_HINT}
          ariaLabel="Gewicht eingeben"
          enterHint={reps === null ? 'next' : 'done'}
          onEnter={reps === null ? () => repsField.current?.open() : undefined}
          onDraft={setDraftWeight} onChange={(value) => dial({ weight: value, reps })} />
        <Stepper ref={repsField} label="Wdh." value={reps} step={1} decimals={0} min={1}
          max={MAX_REPS} refusedHint={REPS_HINT}
          ariaLabel="Wiederholungen eingeben"
          enterHint={weight === null ? 'next' : 'done'}
          onEnter={weight === null ? () => kgField.current?.open() : undefined}
          onDraft={setDraftReps} onChange={(value) => dial({ weight, reps: value })} />
      </div>

      {/* The rest gets a band of its own above the button (D8, variant B):
          "Pause 2:25" at 13px on the button's edge could not be read from
          the bench, ending a rest early sat behind ⋮, and there was no ±15
          (G-055). The card stays -- the next set's numbers are what the rest
          is for. The time is a timer, silent by role; the end is announced
          once, by the live region.
          It stays once the countdown is done, counting up, until the next set
          (round 4): gone, it took the button 112px up while the phone rang. */}
      {band && (
        <div ref={bandRef} className={`restband${rest.over ? ' is-over' : ''}`} role="group" aria-label="Pause">
          {/* The label on a line of its own, the band's full width: beside
              the keys it wrapped on a 360px phone, and the band changed
              height when the keys went. */}
          <span className="restband__lbl">
            {rest.running ? `Pause · von ${clock(payload.rest_total_seconds)}` : 'Pause vorbei'}
          </span>
          <div className="restband__row">
            <div className="restband__time">
              <span className={`restband__num${rest.running && rest.remaining >= 600 ? ' is-long' : ''}`}
                role="timer">
                {rest.running ? clock(rest.remaining) : `+${clock(rest.sinceEnd)}`}
              </span>
            </div>
            {rest.running && (
              <div className="restband__keys">
                <button type="button" className="restband__key" aria-label="−15 Sekunden"
                  onClick={armed(() => onShiftRest(-REST_NUDGE))}>−15</button>
                {/* The server stops a rest at the longest one there is; at
                    that point the key has nothing left to do. */}
                <button type="button" className="restband__key" aria-label="+15 Sekunden"
                  disabled={payload.rest_total_seconds >= REST_MAX}
                  onClick={armed(() => onShiftRest(REST_NUDGE))}>+15</button>
                <button type="button" className="restband__key" aria-label="Pause beenden"
                  onClick={armed(onSkipRest)}><Icon name="skip" /></button>
              </div>
            )}
          </div>
        </div>
      )}

      {/* The button stays present and pressable for the whole countdown, and
          its name stays "Satz geschafft": the band charges underneath it. */}
      {/* A sweaty double-tap on a 64px thumb target is normal use: the second
          press lands on the NEXT set, up the moment the first is drawn done
          -- or, after an exercise's last set, down the append path, a set
          nobody did. So a second tap inside CONFIRM_GUARD_MS is dropped. It
          was disabled for the round trip instead, and offline the round trip
          never ended: no set could be logged at all (G-138). No visual
          treatment: the window is shorter than a look. */}
      {/* While a number is missing the button asks for it rather than
          logging: it opens the entry, keypad up, and says which number it
          wants -- a draft being typed counts, so the label has moved on by
          the time the thumb does. A tap cannot log a set without both. */}
      {/* The question beside the button that answers it; in the tree while
          empty, so it is heard the moment it asks. */}
      <p className="live__doubt" role="status">{asking ? doubt : null}</p>
      <button type="button"
        className={`go${rest.running ? ' is-resting' : ''}${ringing ? ' is-ready' : ''}`}
        id="set-confirm"
        onClick={() => {
          if (weight === null) kgField.current?.open()
          else if (reps === null) repsField.current?.open()
          else {
            const now = Date.now()
            if (now - lastConfirm.current < CONFIRM_GUARD_MS) return
            lastConfirm.current = now
            // The first tap asks; a bounce inside the guard cannot answer.
            if (doubt !== null && !asking) {
              setAskedAbout(`${weight}|${reps}`)
              return
            }
            setAskedAbout(null)
            clearDraft(sessionId)
            onConfirm(weight, reps, nextSet?.id ?? null)
          }
        }}>
        <span className="go__lbl">
          {weight === null && draftWeight === null
            ? 'Gewicht eintippen'
            : reps === null && draftReps === null
              ? 'Wdh. eintippen'
              : <><Icon name="check" />{asking ? 'Ja, eintragen' : 'Satz geschafft'}</>}
        </span>
        {rest.running && (
          <span className="go__band" aria-hidden="true">
            <span className="go__charge"
              style={{ transform: `scaleX(${rest.progress})` }} />
          </span>
        )}
      </button>
    </section>
  )
}
