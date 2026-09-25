import { useEffect, useRef, useState } from 'react'
import type {
  CatalogueExercise, LiveBest, LiveExercise, LiveSet, RoutinePlan, Suggestion,
} from '../types'
import { useUndo } from '../../undo'
import { useDeleting, useOutbox, useSheets, useWaitingFor } from '../stores'
import { setName } from '../setName'
import {
  MAX_NOTE_CHARS, MAX_REPS, MAX_WEIGHT_KG, parseSetInput, setInputProblem, unlikely,
} from '../../setInput'
import { Drawing, movementOf } from './Picture'
import { RoutinePlanGroup } from './RoutinePlanGroup'
import { Sheet } from './Sheet'
import { Icon } from '../../components/Icon'
import { Choice } from '../../settings/Choice'
import { REST_MAX, REST_MIN, REST_NUDGE, clock, kg, restChoices } from '../../settings/values'

/** How long a row says "Gespeichert" after it saved itself (G-058). */
export const SAVED_MS = 2000

export interface ExerciseSheetActions {
  /** "Pause heute". The setting's own value is sent as itself; the server
   *  stores it as nothing, so the row follows the setting again. */
  onRestChange(seconds: number): void
  /** One level down: "Deine Einstellungen", which hold for every workout. */
  onOpenSettings(): void
  onMetaSave(meta: { pain: boolean; notes: string }): void
  onSetUpdate(setId: number, weight: number, reps: number): void
  /** Settles once the server has answered; rejects when it refused the
   *  delete. A lost connection is neither: the delete waits on the phone. */
  onSetDelete(setId: number): Promise<unknown>
  /** "Anhängen": one more set, planned open behind the others (Q2). */
  onAddSet(weight: number, reps: number): void
  onToggleSkip(): void
  onReplace(exerciseId: number): void
  /** At the tap: the island hides the row and offers the undo (G-067). */
  onRemove(): void
  onShowProgress(): void
  /** Pull this exercise in front of the live one, so it is up next. */
  onMakeLive(): void
  /** The routine's plan for the exercise, once the steppers settle. */
  onRoutinePlanChange(plan: RoutinePlan): void
}

interface Props extends ExerciseSheetActions {
  exercise: LiveExercise
  /** The whole exercise list, which a replacement comes from. */
  catalogue: CatalogueExercise[]
  /** The exercises this workout already holds, marked in the replace list. */
  inWorkout: number[]
  /** What the add-a-set row pre-fills with when the exercise has no set yet.
   *  Null for an exercise with no history to seed from. */
  suggestion: Suggestion | null
  /** Whether "Jetzt machen" is offered: not for the live exercise itself,
   *  a finished or skipped one, or a follower whose order is the leader's. */
  canMakeLive: boolean
  /** The workout's routine and what it keeps for this exercise; null when
   *  the routine does not hold it, or the workout has no routine of yours. */
  routine: { name: string; plan: RoutinePlan } | null
}

/**
 * One sheet per exercise: its sets, its rest time, and the three things you
 * can do to it. This replaced a menu on every row and an expanded panel per
 * exercise -- the row itself is the affordance.
 *
 * The groups are not cosmetic. "Pause heute" belongs to this workout, the
 * lifter's settings outlive it, and a twinge or a note belongs to today.
 * Side by side, two rest fields read as one; so today's rest is here, with
 * the setting's value marked in its row, and the settings are one level
 * down, in a sheet that says they hold for every workout.
 */
export function ExerciseSheet({
  exercise, catalogue, inWorkout, suggestion, canMakeLive, routine,
  onRestChange, onOpenSettings, onMetaSave, onSetUpdate, onSetDelete,
  onAddSet, onToggleSkip, onReplace, onRemove, onShowProgress,
  onMakeLive, onRoutinePlanChange,
}: Props) {
  const [pain, setPain] = useState(exercise.pain)
  const [notes, setNotes] = useState(exercise.notes ?? '')
  // The sets whose write the phone is holding (B6), marked as on the card.
  const waitingIds = useOutbox((s) => s.setIds)
  const offerUndo = useUndo((s) => s.offer)
  const closeSheet = useSheets((s) => s.close)
  // Sets whose delete waits out the undo window, gone from the whole screen
  // meanwhile -- the totals too (G-061). By name: see useDeleting.
  const deleting = useDeleting((s) => s.names)
  const hideSet = useDeleting((s) => s.hide)
  const unhideSet = useDeleting((s) => s.unhide)
  const unit = exercise.is_unilateral ? 'kg je Seite' : 'kg'

  const deleteSet = (set: LiveSet, ordinal: number) => {
    const name = setName(set)
    hideSet(name)
    offerUndo({
      label: `Satz ${ordinal} gelöscht.`,
      undo: () => unhideSet(name),
      // Queued on the phone the moment it commits -- a flush on the way out
      // of the page included (G-062) -- and drawn gone by the outbox from
      // then on, until it lands; one the server refuses comes back with its
      // row (G-147). A drawn id the server has named since is sent as the
      // real one.
      commit: () => {
        onSetDelete(set.id).catch(() => {})
        unhideSet(name)
      },
    })
  }

  // "Gespeichert" under the row that saved itself, by the set's name: the
  // row is drawn anew with the numbers it saved.
  const [saved, setSaved] = useState<string | null>(null)
  const savedTimer = useRef<ReturnType<typeof setTimeout> | null>(null)
  useEffect(() => () => {
    if (savedTimer.current !== null) clearTimeout(savedTimer.current)
  }, [])
  const saveSet = (set: LiveSet, weight: number, reps: number) => {
    onSetUpdate(set.id, weight, reps)
    const name = setName(set)
    setSaved(name)
    if (savedTimer.current !== null) clearTimeout(savedTimer.current)
    savedTimer.current = setTimeout(() => {
      setSaved((shown) => (shown === name ? null : shown))
    }, SAVED_MS)
  }

  // The same muscle group first: a replacement is usually "the machine is
  // taken, same muscles another way". That can be empty -- an exercise with
  // no group, or one the list has no neighbour for -- and then the whole list
  // stands in, since nothing is created here any more. Within it, the ones
  // the lifter does first (G-068), in the order they do them most.
  const others = catalogue.filter((e) => e.id !== exercise.exercise_id)
  const sameGroup = others.filter((e) => e.muscle_group === exercise.muscle_group)
  const swaps = sameGroup.length > 0 ? sameGroup : others
  const theirs = swaps.filter((e) => e.common)
    .sort((a, b) => (a.rank ?? Infinity) - (b.rank ?? Infinity))
  const rest = swaps.filter((e) => !e.common)
  // Nothing chosen until the lifter chooses: the first of the list stood
  // preselected, and one tap swapped in an exercise nobody picked (G-068).
  const [replaceWith, setReplaceWith] = useState<number | null>(null)
  const option = (e: CatalogueExercise) => (
    <option value={e.id} key={e.id}>
      {inWorkout.includes(e.id) ? `${e.name} — schon im Workout` : e.name}
    </option>
  )

  return (
    <Sheet id={`sheet-ex-${exercise.id}`} title={exercise.name}>
      {/* The drawing, whole (round 4): the live card's tile opens this sheet.
          Nothing in its place while there is none -- a plate with a dumbbell
          this size would only push the settings down. */}
      {exercise.picture !== null && (
        <div className="pic-full">
          <Drawing src={exercise.picture} alt={`Zeichnung: ${movementOf(exercise.name)}`} />
        </div>
      )}
      {/* Today's rest, from the one in force: the setting's value is marked
          ("deine" or "Liste") and one tap away, and every tap saves. */}
      <div className="sheet__group">
        <div className="sheet__group-head">
          <span className="label">Pause heute</span>
        </div>
        <Choice label="Pause heute" values={restChoices(exercise.rest_setting, 2)}
          on={exercise.rest_seconds ?? exercise.rest_setting} mark={exercise.rest_setting}
          markWord={exercise.rest_setting_mine ? 'deine' : 'Liste'} format={clock}
          onPick={(seconds) => onRestChange(seconds)}
          nudge={{
            step: REST_NUDGE, min: REST_MIN, max: REST_MAX,
            label: 'nach jedem Satz', keyNoun: '15 Sekunden',
          }} />
        <p className="sheet__note">Eine andere Zeit gilt nur für dieses Workout.</p>
        <button type="button" className="sheet-row" onClick={onOpenSettings}>
          <span className="sheet-row__lead"><Icon name="edit" /></span>
          <span className="sheet-row__main">
            <span className="sheet-row__name">Deine Einstellungen</span>
            <span className="sheet-row__meta">
              {(exercise.rest_setting === null ? '' : `Pause ${clock(exercise.rest_setting)} · `)
                + `Schritt ${kg(exercise.increment)} kg — gelten immer`}
            </span>
          </span>
          <span className="sheet-row__chev"><Icon name="forward" /></span>
        </button>
      </div>

      {/* A third lifetime, between the two: the routine's, from the next
          workout on (D2 P1). */}
      {routine !== null && (
        <RoutinePlanGroup routineName={routine.name} plan={routine.plan}
          onSave={onRoutinePlanChange} />
      )}

      {/* The opposite lifetime to the settings above: a twinge and a note
          belong to this workout, not to the machine.

          Both save by themselves, like the rest above. The flag used to
          wait for a Speichern button beside the note, so ticking it and
          closing the sheet kept the tick on screen and saved nothing. */}
      <div className="sheet__group">
        <div className="sheet__group-head">
          <span className="label">Heute</span>
        </div>
        <label className="sheet__row">
          <input type="checkbox" className="check" checked={pain}
            onChange={(e) => {
              setPain(e.target.checked)
              onMetaSave({ pain: e.target.checked, notes })
            }} />
          <span className="check__text">Schmerz / Zwicken</span>
        </label>
        <div className="field">
          <label className="label" htmlFor={`ex-notes-${exercise.id}`}>Notiz</label>
          <input type="text" id={`ex-notes-${exercise.id}`} className="input"
            placeholder="—" value={notes} maxLength={MAX_NOTE_CHARS}
            onChange={(e) => setNotes(e.target.value)}
            onKeyDown={(e) => { if (e.key === 'Enter') e.currentTarget.blur() }}
            onBlur={() => {
              if (notes !== (exercise.notes ?? '')) onMetaSave({ pain, notes })
            }} />
        </div>
      </div>

      <div className="sheet__group">
        <div className="sheet__group-head">
          <span className="label">Sätze</span>
        </div>
        {exercise.sets.filter((s) => !deleting.includes(setName(s))).map((s, i) => (
          // Keyed on the stored numbers, not on the id alone: an editor holds
          // its fields in local state, so a set rewritten while the sheet is
          // open -- by the partner's phone in a shared workout, or by the
          // deload toggle -- would otherwise keep showing the old value and
          // post it back on the next save. The key only moves when the SERVER
          // value moves; typing in the field does not touch it.
          <SetEditor set={s} ordinal={i + 1} key={`${s.key ?? s.id}-${s.weight}-${s.reps}`}
            idBase={`sset-${exercise.id}-${i + 1}`} unit={unit} best={exercise.best}
            waiting={waitingIds.includes(s.id)} saved={saved === setName(s)}
            onSave={saveSet} onDelete={deleteSet} />
        ))}
        {/* Seeded from the last set, not only from the session's opening
            suggestion: appending is usually one more of what you just did.
            Keyed on that seed so a new last set re-seeds the row. A skipped
            exercise plans nothing: its open sets went with the skip, and one
            planned now would wait for a card that never shows it. */}
        {exercise.skipped
          ? <p className="sheet__note">Übersprungen — neue Sätze erst nach „Nicht mehr überspringen“.</p>
          : (
            <AddSetRow key={lastSetKey(exercise)} seed={addSeed(exercise, suggestion)}
              unit={unit} best={exercise.best} onAdd={onAddSet} />
          )}
      </div>

      <div className="sheet__group">
        {canMakeLive && (
          <button type="button" className="sheet-row" onClick={onMakeLive}>
            <span className="sheet-row__lead"><Icon name="check" /></span>
            <span className="sheet-row__main">
              <span className="sheet-row__name">Jetzt machen</span>
              <span className="sheet-row__meta">
                Kommt vor die aktuelle Übung — etwa wenn gerade dieses Gerät frei ist.
              </span>
            </span>
          </button>
        )}
        <button type="button" className="sheet-row" onClick={onShowProgress}>
          <span className="sheet-row__lead"><Icon name="chart" /></span>
          <span className="sheet-row__main">
            <span className="sheet-row__name">Fortschritt anzeigen</span>
            <span className="sheet-row__meta">Verlauf und Rekorde dieser Übung.</span>
          </span>
        </button>
        <button type="button" className="sheet-row" onClick={onToggleSkip}>
          <span className="sheet-row__lead"><Icon name="skip" /></span>
          <span className="sheet-row__main">
            <span className="sheet-row__name">
              {exercise.skipped ? 'Nicht mehr überspringen' : 'Übung überspringen'}
            </span>
            <span className="sheet-row__meta">
              {/* What the server does, which the old "Sätze bleiben" was not:
                  a skip drops every set still open, keeps the ones already
                  logged, and coming back plans the exercise afresh. */}
              {exercise.skipped
                ? 'Zählt wieder — offene Sätze werden neu geplant.'
                : 'Offene Sätze entfallen, erledigte bleiben.'}
            </span>
          </span>
        </button>

        {swaps.length > 0 && (
          <details>
            <summary className="sheet-row">
              <span className="sheet-row__lead"><Icon name="swap" /></span>
              <span className="sheet-row__main">
                <span className="sheet-row__name">Übung ersetzen</span>
                <span className="sheet-row__meta">Nur für heute — die Routine bleibt.</span>
              </span>
            </summary>

            {/* The button beside the list, where the choice is made: under
                it, it sat below the fold (G-068). */}
            <div className="sheet__save-row">
              <div className="field">
                <label className="label" htmlFor={`replace-select-${exercise.id}`}>Ersatzübung</label>
                <select id={`replace-select-${exercise.id}`} className="select"
                  value={replaceWith ?? ''}
                  onChange={(e) => setReplaceWith(e.target.value === '' ? null : Number(e.target.value))}>
                  <option value="" disabled>Übung wählen …</option>
                  {theirs.length > 0
                    ? (
                      <>
                        <optgroup label="Deine">{theirs.map(option)}</optgroup>
                        {rest.length > 0 && <optgroup label="Weitere">{rest.map(option)}</optgroup>}
                      </>
                    )
                    : rest.map(option)}
                </select>
              </div>
              <button type="button" className="btn btn--live btn--sm"
                disabled={replaceWith === null}
                onClick={() => { if (replaceWith !== null) onReplace(replaceWith) }}>Ersetzen</button>
            </div>
          </details>
        )}

        {/* A shared exercise is the leader's structure: a follower's remove
            was brought back by the leader's next change, so it is not offered
            (and the route refuses it). Skipping above is theirs, and sticks.
            An exercise they added themselves keeps its remove. */}
        {exercise.mirrored ? (
          <p className="sheet__note">
            Gehört zum gemeinsamen Plan — überspringen oder ersetzen geht, entfernen nicht.
          </p>
        ) : (
          <button type="button" className="sheet-row sheet-row--danger"
            onClick={() => {
              // Closed at the tap, the undo on the toast (G-067): open, it
              // stayed editable for the whole window, on an exercise about
              // to go. The island hides the row and keeps the undo.
              closeSheet()
              onRemove()
            }}>
            <span className="sheet-row__lead"><Icon name="trash" /></span>
            <span className="sheet-row__main">
              <span className="sheet-row__name">Übung entfernen</span>
              <span className="sheet-row__meta">Aus diesem Workout, samt Sätzen.</span>
            </span>
          </button>
        )}
      </div>
    </Sheet>
  )
}

function SetEditor({ set, ordinal, idBase, unit, best, waiting, saved, onSave, onDelete }: {
  set: LiveSet
  ordinal: number
  /** Unique on the page: the sheet's exercise and the row. */
  idBase: string
  /** "kg", or "kg je Seite" for a one-sided exercise, as on the card (G-057). */
  unit: string
  best: LiveBest | null
  /** Its write is kept on the phone until the connection is back (B6). */
  waiting: boolean
  /** It just saved itself. */
  saved: boolean
  onSave(set: LiveSet, weight: number, reps: number): void
  onDelete(set: LiveSet, ordinal: number): void
}) {
  // A blank planned set starts with empty fields, not the text "null".
  const [weight, setWeight] = useState(set.weight === null ? '' : String(set.weight))
  const [reps, setReps] = useState(set.reps === null ? '' : String(set.reps))
  // The numbers the lifter said "Ja" to, past twice their best (Q5).
  const [sureOf, setSureOf] = useState<string | null>(null)
  // A cleared field used to save as 0 -- Number('') is 0 -- and overwrite the
  // real numbers. Invalid or unchanged, there is nothing to save.
  const parsed = parseSetInput(weight, reps)
  const changed = parsed !== null
    && (parsed.weight !== set.weight || parsed.reps !== set.reps)
  const problem = setInputProblem(weight, reps)
  const typed = `${weight}|${reps}`
  const doubt = changed && sureOf !== typed ? unlikely(parsed, best, unit) : null
  const waitingFor = useWaitingFor()

  // The row saves itself (G-058): as focus leaves it, on Enter, and as it
  // goes -- the sheet closing, or the row drawn anew. Edits were thrown away
  // unless the small icon was tapped. What it saves is what is on screen at
  // that moment, and never the same numbers twice: the row saved, the set
  // took them, and the row drawn anew for them would have sent them again.
  const now = useRef({ parsed, changed, doubt })
  now.current = { parsed, changed, doubt }
  const sent = useRef<string | null>(null)
  const save = (sure = false) => {
    const { parsed: numbers, changed: moved, doubt: asking } = now.current
    if (numbers === null || !moved || (asking !== null && !sure)) return
    const said = `${numbers.weight}|${numbers.reps}`
    if (sent.current === said) return
    sent.current = said
    onSave(set, numbers.weight, numbers.reps)
  }
  const saveOnUnmount = useRef(save)
  saveOnUnmount.current = save
  useEffect(() => () => { saveOnUnmount.current() }, [])

  const state = `${set.completed ? 'erledigt' : 'offen'}${waiting ? `, ${waitingFor}` : ''}`
  const hint = problem ?? doubt ?? (saved ? 'Gespeichert' : null)

  return (
    <>
    <div className="sset"
      onBlur={(e) => { if (!e.currentTarget.contains(e.relatedTarget as Node | null)) save() }}>
      {/* Done or still open, as the card's chips say it (G-059): the tick,
          or the number in a ring. Said to a screen reader on both fields. */}
      <span className={`label sset__ord${set.completed ? ' is-done' : ''}${waiting ? ' is-waiting' : ''}`}>
        <span aria-hidden="true">{set.completed ? <Icon name="check" /> : ordinal}</span>
        <span className="sr-only" id={`${idBase}-state`}>{state}</span>
      </span>
      <input type="number" step="0.5" min="0" max={MAX_WEIGHT_KG} className="input input--num"
        aria-label={`Satz ${ordinal}, Gewicht in ${unit}`} value={weight}
        aria-describedby={`${idBase}-state`}
        aria-invalid={problem?.startsWith('Gewicht') || undefined}
        onChange={(e) => setWeight(e.target.value)}
        onKeyDown={(e) => { if (e.key === 'Enter') e.currentTarget.blur() }} />
      <Unit unit={unit} />
      <span className="sset__unit">×</span>
      <input type="number" min="1" max={MAX_REPS} className="input input--num"
        aria-label={`Satz ${ordinal}, Wiederholungen`} value={reps}
        aria-describedby={`${idBase}-state`}
        aria-invalid={problem?.startsWith('Wiederholungen') || undefined}
        onChange={(e) => setReps(e.target.value)}
        onKeyDown={(e) => { if (e.key === 'Enter') e.currentTarget.blur() }} />
      <span className="sset__acts">
        <button type="button" className="icon-btn"
          aria-label={`Satz ${ordinal} speichern`}
          disabled={!changed || doubt !== null}
          onClick={() => save()}>
          <Icon name="save" />
        </button>
        {/* The multiplication-sign delete stays a typographic mark on
            purpose -- see Icon.tsx's header. */}
        <button type="button" className="icon-btn"
          aria-label={`Satz ${ordinal} löschen`}
          onClick={() => onDelete(set, ordinal)}>✕</button>
      </span>
    </div>
    <SetInputHint text={hint} ok={problem === null && doubt === null}
      sure={problem === null && doubt !== null ? {
        label: 'Ja, speichern',
        onSure: () => { setSureOf(typed); save(true) },
      } : null} />
    </>
  )
}

/** The unit beside a weight: "je Seite" under "kg", where one line would
 *  push the row past a phone's width. */
function Unit({ unit }: { unit: string }) {
  if (unit === 'kg') return <span className="sset__unit">kg</span>
  return <span className="sset__unit sset__unit--side">kg<br />je Seite</span>
}

/** Why the row's button is off -- a disabled save with no reason looked like
 *  a broken button (walkthrough G-070) -- or the "Sicher?" with its "Ja", or
 *  that the row saved itself. */
function SetInputHint({ text, ok, sure }: {
  text: string | null
  /** A confirmation, not a problem. */
  ok: boolean
  sure: { label: string; onSure(): void } | null
}) {
  return (
    <p className={`sset__hint${ok ? ' sset__hint--ok' : ''}`} aria-live="polite">
      {text}
      {sure !== null && (
        <button type="button" className="btn btn--ghost btn--sm sset__sure"
          onClick={sure.onSure}>{sure.label}</button>
      )}
    </p>
  )
}

/** What the add row starts from: the last set of this exercise that has its
 *  numbers (a blank plan has none yet), else the session's suggestion, else
 *  nothing. */
function addSeed(exercise: LiveExercise, suggestion: Suggestion | null) {
  for (let i = exercise.sets.length - 1; i >= 0; i -= 1) {
    const { weight, reps } = exercise.sets[i]!
    if (weight !== null && reps !== null) return { weight, reps }
  }
  return suggestion
}

function lastSetKey(exercise: LiveExercise): string {
  const last = exercise.sets[exercise.sets.length - 1]
  return last === undefined ? 'none' : `${last.key ?? last.id}-${last.weight}-${last.reps}`
}

function AddSetRow({ seed, unit, best, onAdd }: {
  seed: { weight: number; reps: number } | null
  unit: string
  best: LiveBest | null
  onAdd(weight: number, reps: number): void
}) {
  const [weight, setWeight] = useState(seed ? String(seed.weight) : '')
  const [reps, setReps] = useState(seed ? String(seed.reps) : '')
  const parsed = parseSetInput(weight, reps)
  const problem = setInputProblem(weight, reps)
  // Only numbers the lifter typed are asked about. The row starts from the
  // last set's, and after "Ja, anhängen" it starts from the very numbers just
  // said yes to: asked again, a second "Ja" planned the set twice (B7 review).
  const typed = parsed !== null
    && (seed === null || parsed.weight !== seed.weight || parsed.reps !== seed.reps)
  const doubt = typed ? unlikely(parsed, best, unit) : null

  return (
    <>
    <div className="sset">
      <span className="label" aria-hidden="true">+</span>
      <input type="number" step="0.5" min="0" max={MAX_WEIGHT_KG} className="input input--num" required
        aria-label={`Neuer Satz, Gewicht in ${unit}`} value={weight}
        aria-invalid={problem?.startsWith('Gewicht') || undefined}
        onChange={(e) => setWeight(e.target.value)} />
      <Unit unit={unit} />
      <span className="sset__unit">×</span>
      <input type="number" min="1" max={MAX_REPS} className="input input--num" required
        aria-label="Neuer Satz, Wiederholungen" value={reps}
        aria-invalid={problem?.startsWith('Wiederholungen') || undefined}
        onChange={(e) => setReps(e.target.value)} />
      <span className="sset__acts">
        {/* Visible text short so the action slot never wraps; the accessible
            name stays the full phrase. Disabled while the fields cannot make a
            set -- an empty row used to log 0 kg x 0 as done -- or while the
            "Sicher?" under it waits for its "Ja". A double tap is the island's
            to drop (APPEND_GUARD_MS): waiting for the answer instead held the
            button for as long as the wifi was gone. */}
        <button type="button" className="btn btn--ghost btn--sm" aria-label="Satz anhängen"
          disabled={parsed === null || doubt !== null}
          onClick={() => { if (parsed !== null) onAdd(parsed.weight, parsed.reps) }}>
          Anhängen
        </button>
      </span>
    </div>
    <SetInputHint text={problem ?? doubt} ok={false}
      sure={problem === null && doubt !== null && parsed !== null ? {
        label: 'Ja, anhängen',
        onSure: () => onAdd(parsed.weight, parsed.reps),
      } : null} />
    </>
  )
}
