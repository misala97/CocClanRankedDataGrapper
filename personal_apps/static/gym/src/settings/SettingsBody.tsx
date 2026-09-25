import { useId, useRef, useState, type ReactNode } from 'react'
import type { ExerciseMeta, SettingField } from '../types'
import { saveSetting } from './api'
import { Choice } from './Choice'
import { useSaveQueue } from './useSaveQueue'
import {
  REST_MAX, REST_MIN, REST_NUDGE, barChoices, barLabel, clock, kg,
  parseStops, restChoices, stepChoices, stopsLine,
} from './values'

type Value = number | number[] | null

interface Props {
  /** As the server last said: the effective values, the list's, which of
   *  them are the lifter's own, and their rest for all. */
  exercise: ExerciseMeta
  /** Every answer, in order -- the page redraws what it shows from it. */
  onSaved(exercise: ExerciseMeta): void
}

/** What a field falls back to: for the rest the lifter's rest for all, where
 *  they set one, else the list's value (exercises.resolve). */
function fallback(meta: ExerciseMeta, field: SettingField): Value {
  if (field === 'default_rest_seconds' && meta.rest_for_all !== null) return meta.rest_for_all
  return meta.list_defaults[field]
}

const same = (a: Value, b: Value) => JSON.stringify(a) === JSON.stringify(b)

/** The answer before it comes: the value in force at once, and the field the
 *  lifter's own unless it equals what it falls back to -- which the server
 *  stores as nothing (exercises.to_store). */
function guess(meta: ExerciseMeta, field: SettingField, value: Value): ExerciseMeta {
  const back = fallback(meta, field)
  const own = meta.own.filter((f) => f !== field)
  return {
    ...meta,
    [field]: value ?? back,
    own: value === null || same(value, back) ? own : [...own, field].sort(),
  } as ExerciseMeta
}

/** On the wire: a number with a dot, stops joined by commas, blank for the
 *  value it falls back to. */
const wire = (value: Value) =>
  value === null ? '' : Array.isArray(value) ? value.join(', ') : String(value)

/**
 * "Deine Einstellungen" for one exercise: rest, step, bar and a stack's
 * stops, each a row of its usual values with the one it falls back to
 * marked. Every tap is saved -- the sheet has nothing to confirm, and closing
 * it loses nothing.
 *
 * The rows show the guess at once and the server's answer when it lands; a
 * failed write puts the last answer back and says why. The same body serves
 * the exercise page and the workout, which reach it by different sheets.
 */
export function SettingsBody({ exercise, onSaved }: Props) {
  const [meta, setMeta] = useState(exercise)
  const [error, setError] = useState<string | null>(null)
  const confirmed = useRef(exercise)
  const send = useSaveQueue<ExerciseMeta>({
    shown: (fresh) => { setMeta(fresh); setError(null) },
    saved: (fresh) => { confirmed.current = fresh; onSaved(fresh) },
    failed: (message) => { setMeta(confirmed.current); setError(message) },
  })

  const save = (field: SettingField, value: Value, leaving = false) => {
    setMeta((current) => guess(current, field, value))
    send((keepalive) => saveSetting(exercise.id, field, wire(value), keepalive), leaving)
  }

  const list = meta.list_defaults
  const mine = (field: SettingField) => meta.own.includes(field)
  const forAll = meta.rest_for_all
  const restBack = forAll ?? list.default_rest_seconds
  const restOwn = mine('default_rest_seconds')
  const restSource = restOwn
    ? (forAll !== null ? 'Ausnahme' : 'Deine')
    : (forAll !== null ? 'Wie deine Pause' : 'Standard')
  const source = (field: SettingField) => (mine(field) ? 'Deine' : 'Standard')

  return (
    <>
      <p className="sheet__note">
        {forAll !== null
          ? `Nur für dich. Ohne Ausnahme gilt deine Pause, ${clock(forAll)}.`
          : 'Nur für dich. Jeder Tipp ist sofort gespeichert.'}
      </p>
      {error !== null && <p className="setting__error" role="alert">{error}</p>}

      <Setting name="Pause nach jedem Satz" source={restSource} own={restOwn}>
        <Choice label="Pause nach jedem Satz" values={restChoices(restBack)}
          on={meta.default_rest_seconds} mark={restBack}
          markWord={forAll !== null ? 'Deine' : 'Standard'} format={clock}
          onPick={(value, leaving) => save('default_rest_seconds', value, leaving)}
          nudge={{
            step: REST_NUDGE, min: REST_MIN, max: REST_MAX,
            label: 'nach jedem Satz', keyNoun: '15 Sekunden',
          }} />
      </Setting>

      {/* Per side on a one-sided lift: + and − move one side's number. */}
      <Setting name={meta.is_unilateral ? 'Schritt je Seite (kg)' : 'Schritt bei + und − (kg)'}
        source={source('weight_increment')} own={mine('weight_increment')}>
        <Choice label="Schritt" values={stepChoices(meta.equipment, list.weight_increment)}
          on={meta.weight_increment} mark={list.weight_increment} markWord="Standard" format={kg}
          onPick={(value, leaving) => save('weight_increment', value, leaving)}
          nudge={{ step: 0.25, min: 0.25, max: 25, label: 'kg je Tipp', keyNoun: '0,25 kg' }} />
      </Setting>

      {/* Only where the list knows a bar: a stack or a dumbbell has none,
          and every plate-loaded entry states its own (library.py). A bar a
          lifter set before that stays reachable. */}
      {(list.bar_weight !== null || mine('bar_weight')) && (
        <Setting name="Stangengewicht (kg)" source={source('bar_weight')} own={mine('bar_weight')}>
          <Choice label="Stangengewicht" values={barChoices(list.bar_weight)}
            on={meta.bar_weight} mark={list.bar_weight} markWord="Standard" format={barLabel}
            onPick={(value, leaving) => save('bar_weight', value, leaving)}
            nudge={{ step: 0.5, min: 0, max: 50, label: 'kg Stange', keyNoun: '0,5 kg' }} />
        </Setting>
      )}

      {meta.equipment === 'stack' && (
        <Setting name="Gewichtsstufen" source={source('stack_kg')} own={mine('stack_kg')}>
          <StackStops meta={meta} own={mine('stack_kg')}
            onSave={(stops) => save('stack_kg', stops)} />
        </Setting>
      )}
    </>
  )
}

function Setting({ name, source, own, children }: {
  name: string
  /** Where the value comes from: "Deine", "Standard", ... */
  source: string
  own: boolean
  children: ReactNode
}) {
  return (
    <section className="setting">
      <div className="setting__head">
        <h3 className="setting__name">{name}</h3>
        <span className={own ? 'setting__src setting__src--own' : 'setting__src'}>{source}</span>
      </div>
      {children}
    </section>
  )
}

/**
 * A stack steps evenly by the step above unless the machine says otherwise:
 * then its stops, typed once. Typing is the one place here that is not a
 * tap, so it is behind a button and confirmed -- a half-typed list must not
 * be saved as the machine.
 */
function StackStops({ meta, own, onSave }: {
  meta: ExerciseMeta
  own: boolean
  onSave(stops: number[] | null): void
}) {
  const [editing, setEditing] = useState(false)
  const [text, setText] = useState('')
  const field = useId()
  const stops = meta.stack_kg
  const listStops = meta.list_defaults.stack_kg
  const parsed = parseStops(text)

  if (editing) {
    return (
      <div className="setting__edit">
        <label className="setting__line" htmlFor={field}>
          Jede Gewichtsstufe in kg, mit Komma getrennt — etwa 5, 12, 19, 26.
        </label>
        <input type="text" id={field} className="input" value={text} autoComplete="off"
          // The field appears on a tap inside a sheet already open, so it
          // takes the focus the tap asked for (unlike Sheet's opening focus).
          autoFocus
          onChange={(e) => setText(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === 'Enter' && parsed !== null) { onSave(parsed); setEditing(false) }
          }} />
        <div className="setting__acts">
          <button type="button" className="btn btn--live btn--sm" disabled={parsed === null}
            onClick={() => { if (parsed !== null) { onSave(parsed); setEditing(false) } }}>
            Übernehmen
          </button>
          <button type="button" className="btn btn--ghost btn--sm"
            onClick={() => setEditing(false)}>Abbrechen</button>
        </div>
      </div>
    )
  }

  const edit = () => {
    setText((stops ?? []).join(', '))
    setEditing(true)
  }
  const step = meta.weight_increment
  return (
    <>
      <p className="setting__line">
        {stops !== null
          ? stopsLine(stops)
          : step === null
            ? 'Gleichmäßig.'
            : `Gleichmäßig, in Schritten von ${kg(step)} kg.`}
      </p>
      {own ? (
        <div className="setting__acts">
          <button type="button" className="btn btn--ghost btn--sm" onClick={edit}>
            Gewichtsstufen ändern
          </button>
          <button type="button" className="btn btn--ghost btn--sm" onClick={() => onSave(null)}>
            {listStops === null ? 'Wieder gleichmäßig' : 'Zurück zum Standard'}
          </button>
        </div>
      ) : (
        <button type="button" className="btn btn--ghost btn--block" onClick={edit}>
          Das Gerät hat andere Gewichtsstufen
        </button>
      )}
    </>
  )
}
