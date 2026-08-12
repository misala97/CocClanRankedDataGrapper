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
 */
export function AddExerciseSheet({
  catalogue, inSession, onAdd, onCreate, busyExerciseId = null,
}: Props) {
  const query = useSheets((s) => s.addQuery)
  const setQuery = useSheets((s) => s.setAddQuery)

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
      <input
        type="search" id="exadd-search" className="input" autoComplete="off"
        placeholder="Übung suchen oder anlegen"
        aria-label="Übung suchen oder anlegen" aria-controls="exadd-list"
        value={query} onChange={(e) => setQuery(e.target.value)}
      />
      <div className="exadd" id="exadd-list">
        {matches.map((e) => {
          const already = countIn(e.id)
          return (
            <button type="button" key={e.id}
              className={busyExerciseId === e.id ? 'exadd__row is-busy' : 'exadd__row'}
              disabled={busyExerciseId === e.id}
              onClick={() => onAdd(e.id)}>
              <span className="exadd__name">{e.name}</span>
              {e.muscle_group !== null && (
                <span className="exadd__group">{e.muscle_group}</span>
              )}
              {already > 0 && (
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
            onClick={() => onCreate(query.trim())}>
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
