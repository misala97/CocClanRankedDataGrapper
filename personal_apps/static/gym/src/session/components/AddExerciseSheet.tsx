import { useEffect, useRef, useState } from 'react'
import type { CatalogueExercise, LiveExercise } from '../types'
import { useSheets } from '../stores'
import { matches } from '../../search'
import { Sheet } from './Sheet'

interface Props {
  /** The whole exercise list -- everyone picks from the same one. */
  catalogue: CatalogueExercise[]
  /** The session's current contents, for the "schon drin" counts. Derived from
   *  the payload rather than tallied client-side, so the count is the real
   *  contents and cannot drift. */
  inSession: LiveExercise[]
  onAdd(exerciseId: number): void
  /** The row whose write is in flight. Adding waits for the server (it
   *  recomputes which exercise is live, so there is no honest local guess)
   *  and this sheet stays open, so without a mark a slow add reads as a tap
   *  that did nothing and gets tapped again. */
  busyExerciseId?: number | null
}

/** An add in flight, with how many rows of it the session had when it was
 *  asked for -- it has landed once the payload holds one more. */
interface Pending {
  name: string
  exerciseId: number
  before: number
}

/**
 * One field over the one exercise list.
 *
 * The search keeps library.matches' contract: every word of the query has to
 * occur in the exercise's name or aliases, so "Bench Press" and "bankdruecken"
 * still find Bankdrücken (Langhantel) -- the names the lifters typed before the
 * list are its aliases. Nothing is created here: an exercise that is not on
 * the list is not in the app.
 *
 * The sheet stays open. It used to close and full-page-render on every add,
 * so building a six-exercise workout was six round trips.
 *
 * Staying open is only half of it: the query used to stay too, so after an
 * add the one row left under the thumb was that exercise itself -- and
 * tapping it, the natural way to say "that one", added a second copy. The
 * field now empties once the add has landed, and a row that is already in the
 * workout asks before it adds another.
 */
export function AddExerciseSheet({
  catalogue, inSession, onAdd, busyExerciseId = null,
}: Props) {
  const query = useSheets((s) => s.addQuery)
  const setQuery = useSheets((s) => s.setAddQuery)
  const isOpen = useSheets((s) => s.openId === 'sheet-add-exercise')
  const field = useRef<HTMLInputElement>(null)
  const [pending, setPending] = useState<Pending | null>(null)
  const [added, setAdded] = useState<string | null>(null)
  const [armedId, setArmedId] = useState<number | null>(null)

  const countIn = (exerciseId: number) =>
    inSession.filter((se) => se.exercise_id === exerciseId).length

  // Confirmed from the payload, not from the tap: an add has no optimistic
  // path, so the session holding one more of it is the only honest "done".
  // A write that fails never gets here, which leaves the query standing for a
  // retry -- the error banner says what went wrong.
  useEffect(() => {
    if (pending === null || countIn(pending.exerciseId) <= pending.before) return
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

  const add = (exercise: CatalogueExercise) => {
    setPending({ name: exercise.name, exerciseId: exercise.id, before: countIn(exercise.id) })
    setAdded(null)
    setArmedId(null)
    onAdd(exercise.id)
    // The tapped row may be about to vanish; the cursor goes back where the
    // next name is typed, which also keeps a phone's keyboard up for it.
    field.current?.focus()
  }

  // Filtering is client-side over a list the server already sent -- hundreds
  // of rows, not thousands -- and a round trip per keystroke on gym wifi would
  // be worse than useless.
  const hits = catalogue.filter((e) => matches(e.search, query))

  return (
    <Sheet id="sheet-add-exercise" title="Übung hinzufügen">
      {/* data-autofocus: typing is this sheet's only job, and showModal()
          otherwise hands focus to "Fertig", the first control in the dialog. */}
      <input
        type="search" id="exadd-search" className="input" autoComplete="off"
        placeholder="Übung suchen" ref={field} data-autofocus
        aria-label="Übung suchen" aria-controls="exadd-list"
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
        {hits.map((e) => {
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
                add(e)
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

        {hits.length === 0 && query.trim() !== '' && (
          <p className="exadd__empty" id="exadd-empty">
            {`Keine Übung in der Liste passt zu „${query.trim()}“.`}
          </p>
        )}
      </div>
    </Sheet>
  )
}
