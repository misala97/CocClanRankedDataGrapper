import { useEffect, useRef, useState } from 'react'
import type { CatalogueExercise, LiveExercise } from '../types'
import { useSheets } from '../stores'
import { Sheet } from './Sheet'

interface Props {
  catalogue: CatalogueExercise[]
  /** The session's current contents, for the "schon drin" counts. Derived from
   *  the payload rather than tallied client-side, so the count is the real
   *  contents and cannot drift. */
  inSession: LiveExercise[]
  onAdd(exerciseId: number): void
  onCreate(name: string): void
  /** The row whose write is in flight -- an exercise id, or 'new' for the
   *  create row. Adding waits for the server (it recomputes which exercise is
   *  live, so there is no honest local guess) and this sheet stays open, so
   *  without a mark a slow add reads as a tap that did nothing and gets
   *  tapped again. */
  busyExerciseId?: number | 'new' | null
}

/** What an add is for: a catalogue row by id, or a name being created. */
interface Target {
  name: string
  exerciseId: number | null
}

/** An add in flight, with how many rows it had in the session when it was
 *  asked for -- it has landed once the payload holds one more. */
interface Pending extends Target {
  before: number
}

const fold = (name: string) => name.trim().toLowerCase()

/**
 * One field, two jobs.
 *
 * The sheet used to be two panes -- pick an existing lift, or switch modes and
 * invent one -- which meant a first-time user with an empty catalogue had to
 * understand the split before they could log anything. Here the create path is
 * simply what the list offers when the search matches nothing, so an empty
 * catalogue reaches it without choosing a mode at all.
 *
 * The sheet also stays open. It used to close and full-page-render on every
 * add, so building a six-exercise workout was six round trips.
 *
 * Staying open is only half of it: the query used to stay too, so after
 * "Anlegen: Bankdrücken" the one row left under the thumb was Bankdrücken
 * itself -- and tapping it, the natural way to say "that one", added a second
 * copy. The field now empties once the add has landed, and a row that is
 * already in the workout asks before it adds another.
 */
export function AddExerciseSheet({
  catalogue, inSession, onAdd, onCreate, busyExerciseId = null,
}: Props) {
  const query = useSheets((s) => s.addQuery)
  const setQuery = useSheets((s) => s.setAddQuery)
  const isOpen = useSheets((s) => s.openId === 'sheet-add-exercise')
  const field = useRef<HTMLInputElement>(null)
  const [pending, setPending] = useState<Pending | null>(null)
  const [added, setAdded] = useState<string | null>(null)
  const [armedId, setArmedId] = useState<number | null>(null)

  const countOf = (target: Target) => inSession.filter((se) => (
    target.exerciseId !== null
      ? se.exercise_id === target.exerciseId
      : fold(se.name) === fold(target.name))).length

  // Confirmed from the payload, not from the tap: an add has no optimistic
  // path, so the session holding one more of it is the only honest "done".
  // A write that fails never gets here, which leaves the query standing for a
  // retry -- the error banner says what went wrong.
  useEffect(() => {
    if (pending === null || countOf(pending) <= pending.before) return
    setPending(null)
    setAdded(pending.name)
    setQuery('')
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [inSession, pending])

  // The confirmation belongs to this visit to the sheet.
  useEffect(() => {
    if (!isOpen) {
      setAdded(null)
      setArmedId(null)
    }
  }, [isOpen])

  const ask = (target: Target, send: () => void) => {
    setPending({ ...target, before: countOf(target) })
    setAdded(null)
    setArmedId(null)
    send()
    // The tapped row or the create row may be about to vanish; the cursor
    // goes back where the next name is typed, which also keeps a phone's
    // keyboard up for it.
    field.current?.focus()
  }

  const needle = query.trim().toLowerCase()
  // Filtering is client-side over a list the server already sent: a lifter's
  // catalogue is tens of rows, not thousands, and a round trip per keystroke
  // on gym wifi would be worse than useless.
  const matches = catalogue.filter(
    (e) => needle === '' || e.name.toLowerCase().includes(needle))
  const exact = matches.some((e) => e.name.toLowerCase() === needle)

  const countIn = (exerciseId: number) =>
    inSession.filter((se) => se.exercise_id === exerciseId).length

  return (
    <Sheet id="sheet-add-exercise" title="Übung hinzufügen">
      {/* data-autofocus: typing is this sheet's only job, and showModal()
          otherwise hands focus to "Fertig", the first control in the dialog. */}
      <input
        type="search" id="exadd-search" className="input" autoComplete="off"
        placeholder="Übung suchen oder anlegen" ref={field} data-autofocus
        aria-label="Übung suchen oder anlegen" aria-controls="exadd-list"
        value={query} onChange={(e) => { setQuery(e.target.value); setArmedId(null) }}
      />
      {/* Rendered empty rather than not at all: a live region has to exist
          before its text changes for a screen reader to hear the change. */}
      <p className="exadd__status" role="status">
        {pending !== null && busyExerciseId !== null
          ? `${pending.name} wird hinzugefügt …`
          : added !== null ? `✓ ${added} ist drin.` : ''}
      </p>
      <div className="exadd" id="exadd-list">
        {matches.map((e) => {
          const already = countIn(e.id)
          const armed = armedId === e.id
          return (
            <button type="button" key={e.id}
              className={['exadd__row', busyExerciseId === e.id ? 'is-busy' : '',
                armed ? 'is-armed' : ''].filter(Boolean).join(' ')}
              disabled={busyExerciseId === e.id}
              onClick={() => {
                // Already in the workout: the first tap asks, the second adds.
                // Doing an exercise twice is legitimate; doing it twice by
                // accident was the easiest mistake on this sheet.
                if (already > 0 && !armed) {
                  setArmedId(e.id)
                  return
                }
                ask({ name: e.name, exerciseId: e.id }, () => onAdd(e.id))
              }}>
              <span className="exadd__name">{e.name}</span>
              {e.muscle_group !== null && !armed && (
                <span className="exadd__group">{e.muscle_group}</span>
              )}
              {armed ? (
                <span className="exadd__in">Nochmal hinzufügen?</span>
              ) : already > 0 && (
                <span className="exadd__in">{`${already}× drin`}</span>
              )}
            </button>
          )
        })}

        {/* The create path is what the list offers when nothing matches --
            never a mode to switch into. Hidden when the typed name already
            exists, because "Anlegen: Bankdrücken" under a Bankdrücken row is
            an offer to make a duplicate. */}
        {needle !== '' && !exact && (
          <button type="button" id="exadd-create"
            className={busyExerciseId === 'new'
              ? 'exadd__row exadd__row--new is-busy'
              : 'exadd__row exadd__row--new'}
            disabled={busyExerciseId === 'new'}
            onClick={() => {
              const name = query.trim()
              ask({ name, exerciseId: null }, () => onCreate(name))
            }}>
            <span className="exadd__name">Anlegen: <b>{query.trim()}</b></span>
            <span className="exadd__group">neue Übung</span>
          </button>
        )}

        {catalogue.length === 0 && (
          <p className="exadd__empty" id="exadd-empty">
            Tippe einen Namen — die Übung wird angelegt und bleibt in deiner Liste.
          </p>
        )}
      </div>
    </Sheet>
  )
}
