import { useEffect, useLayoutEffect, useMemo, useRef, useState, type ReactNode } from 'react'
import type { CatalogueExercise, LiveExercise } from '../types'
import { useSheets } from '../stores'
import { recency } from '../../catalogue/format'
import { Icon } from '../../components/Icon'
import { NearMisses } from '../../components/NearMisses'
import { isQuery } from '../../search'
import { found, mine, movementMeta, sections, workouts, yoursFirst } from '../picker'
import { Sheet } from './Sheet'

interface Props {
  /** The whole exercise list -- everyone picks from the same one. */
  catalogue: CatalogueExercise[]
  /** The list's muscle groups in its own order: the full list's sections. */
  groups: string[]
  /** The session's current contents, for the "drin" marks. Derived from the
   *  payload rather than tallied client-side, so the mark is the real
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

const ID = 'sheet-add-exercise'

/**
 * The one exercise list, yours first (owner, V1: "my common ones first and
 * the rest in a properly ordered list by movement").
 *
 * Three views in one sheet. Opened, it leads with "Deine" -- what you do
 * often, one movement's variants as a block, the one you mainly do on top --
 * and below it every movement once, by muscle, A-Z. A movement with several
 * Geräte opens them one level deeper, yours first. Typing turns the sheet
 * into search results, exact exercises, yours first. The ordering itself is
 * ../picker.
 *
 * Nothing takes focus on open: the common case is one tap on something you
 * always do, and a keyboard that jumps up over the list hides it.
 *
 * The search keeps library.find's contract: every word of the query has to
 * occur in the exercise's name or aliases, so "Bench Press" and "bankdruecken"
 * still find Bankdrücken (Langhantel) -- the whole query as one run first, a
 * typo only when nothing else matches, and then it says so. Nothing is
 * created here: an exercise that is not on the list is not in the app.
 *
 * The sheet stays open after an add, so building a workout is not a round
 * trip per exercise. A search empties once its add has landed -- otherwise
 * the one row left under the thumb was that exercise itself, and tapping it,
 * the natural way to say "that one", added a second copy -- and a row already
 * in the workout asks before it adds another.
 */
export function AddExerciseSheet({
  catalogue, groups, inSession, onAdd, busyExerciseId = null,
}: Props) {
  const query = useSheets((s) => s.addQuery)
  const setQuery = useSheets((s) => s.setAddQuery)
  const isOpen = useSheets((s) => s.openId === ID)
  const field = useRef<HTMLInputElement>(null)
  const [pending, setPending] = useState<Pending | null>(null)
  const [added, setAdded] = useState<string | null>(null)
  const [armedId, setArmedId] = useState<number | null>(null)
  // One level deeper: the movement whose Geräte are showing, and where the
  // list was scrolled when it opened, so Zurück lands back on the same row.
  const [movement, setMovement] = useState<string | null>(null)
  const listScroll = useRef(0)
  const cameFrom = useRef<string | null>(null)

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
  }, [inSession, pending])

  // The confirmation and the level belong to this visit to the sheet.
  useEffect(() => {
    if (!isOpen) {
      setAdded(null)
      setArmedId(null)
      setMovement(null)
      cameFrom.current = null
    }
  }, [isOpen])

  // A change of level moves the reader with it: deeper starts at the top with
  // focus on Zurück, and the way back restores the scroll and the focus to
  // the movement it came from -- a screen reader would otherwise be left on a
  // control that no longer exists.
  useLayoutEffect(() => {
    const dialog = document.getElementById(ID)
    if (dialog === null) return
    if (movement !== null) {
      dialog.scrollTop = 0
      document.getElementById(`${ID}-back`)?.focus()
    } else if (cameFrom.current !== null) {
      dialog.scrollTop = listScroll.current
      const rows = dialog.querySelectorAll<HTMLElement>('[data-movement]')
      Array.from(rows).find((row) => row.dataset.movement === cameFrom.current)?.focus()
      cameFrom.current = null
    }
  }, [movement])

  const openMovement = (name: string) => {
    listScroll.current = document.getElementById(ID)?.scrollTop ?? 0
    cameFrom.current = name
    setArmedId(null)
    setMovement(name)
  }

  const add = (exercise: CatalogueExercise) => {
    setPending({ name: exercise.name, exerciseId: exercise.id, before: countIn(exercise.id) })
    setAdded(null)
    setArmedId(null)
    onAdd(exercise.id)
    // A search is typed: its row is about to vanish, and the cursor goes back
    // where the next name goes. A tap from the list keeps the keyboard down.
    if (isQuery(query)) field.current?.focus()
  }

  const searching = isQuery(query)
  // Client-side over the list the server already sent -- 158 rows -- because
  // a round trip per keystroke on gym wifi would be worse than useless.
  const search = useMemo(() => (searching ? found(catalogue, query) : null),
    [catalogue, query, searching])
  const hits = search?.clusters ?? []
  const common = useMemo(() => mine(catalogue), [catalogue])
  const listed = useMemo(() => sections(catalogue, groups), [catalogue, groups])

  /** A row that adds: one tap, or two when the exercise is already in. */
  const row = (exercise: CatalogueExercise, name: ReactNode, meta: string | null,
    trail: ReactNode) => {
    const already = countIn(exercise.id)
    const armed = armedId === exercise.id
    const busy = busyExerciseId === exercise.id
    return (
      <button type="button" key={exercise.id}
        className={['sheet-row', 'exadd__row', busy ? 'is-busy' : '', armed ? 'is-armed' : '']
          .filter(Boolean).join(' ')}
        // Not `disabled`: that blurs the row just tapped and drops focus onto
        // the page behind the sheet, and a list tap no longer refocuses the
        // field -- a screen reader would lose its place on every add.
        aria-disabled={busy || undefined}
        onClick={() => {
          if (busy) return
          // Already in the workout: the first tap asks, the second adds.
          // Doing an exercise twice is legitimate; doing it twice by accident
          // was the easiest mistake on this sheet.
          if (already > 0 && !armed) {
            setArmedId(exercise.id)
            return
          }
          add(exercise)
        }}>
        <span className="sheet-row__main">
          <span className="sheet-row__name">
            {name}
            {already > 0 && (
              <span className="exadd__in">{already === 1 ? 'drin' : `${already}× drin`}</span>
            )}
          </span>
          {armed ? (
            <span className="sheet-row__meta exadd__ask">Nochmal hinzufügen?</span>
          ) : meta !== null && (
            <span className="sheet-row__meta exadd__meta">{meta}</span>
          )}
        </span>
        {trail}
      </button>
    )
  }

  const times = (exercise: CatalogueExercise) =>
    exercise.workouts > 0 ? <span className="exadd__n">{`${exercise.workouts}×`}</span> : null
  const plus = <span className="exadd__plus"><Icon name="plus" /></span>
  /** "Deine": when last and how often. */
  const yours = (exercise: CatalogueExercise) =>
    row(exercise, exercise.name, recency(exercise.days_ago), times(exercise))
  /** A search hit is a row of a movement's own list: when last (or never),
   *  and the "+". It was the name alone, and never-done ones quieter: bare
   *  grey text left it open that a tap adds (G-007). */
  const result = (exercise: CatalogueExercise) => row(exercise, exercise.name,
    exercise.rank !== null
      ? `${recency(exercise.days_ago)} · ${workouts(exercise.workouts)}`
      : recency(null),
    plus)

  let body: ReactNode
  if (movement !== null) {
    const rows = yoursFirst(catalogue.filter((exercise) => exercise.movement === movement))
    const done = rows.filter((exercise) => exercise.rank !== null)
    const rest = rows.filter((exercise) => exercise.rank === null)
    body = (
      <>
        {done.length > 0 && <GroupHead label="Deine" />}
        {done.map((exercise, i) => row(exercise,
          <>
            {exercise.label}
            {/* Only a real choice has a "mainly": one variant is trivially it. */}
            {i === 0 && done.length > 1 && <span className="chip exadd__most">meistens</span>}
          </>,
          `${recency(exercise.days_ago)} · ${workouts(exercise.workouts)}`, plus))}
        {rest.length > 0 && <GroupHead label={done.length > 0 ? 'Weitere Geräte' : 'Geräte'} />}
        {rest.map((exercise) => row(exercise, exercise.label, recency(null), plus))}
      </>
    )
  } else if (searching) {
    body = (
      <>
        {hits.length > 0 && search?.tier === 'typos' && <NearMisses query={query} />}
        {hits.map((cluster) => (
          <div className="exadd__cluster" key={cluster.movement}>{cluster.rows.map(result)}</div>
        ))}
        {hits.length === 0 && (
          <p className="exadd__empty" id="exadd-empty">
            {`Keine Übung in der Liste passt zu „${query.trim()}“.`}
          </p>
        )}
      </>
    )
  } else {
    const deep = common.length > 0
    body = (
      <>
        {deep ? (
          <section className="exadd__group" aria-labelledby="exadd-mine">
            <GroupHead id="exadd-mine" label="Deine"
              count={`${common.reduce((n, cluster) => n + cluster.rows.length, 0)} Übungen, häufigste oben`} />
            {common.map((cluster) => (
              <div className="exadd__cluster" key={cluster.movement}>{cluster.rows.map(yours)}</div>
            ))}
          </section>
        ) : (
          <p className="exadd__intro">Was du oft machst, rückt hier nach oben.</p>
        )}
        {deep && <h3 className="exadd__all">Alle Übungen <span>nach Muskel, A–Z</span></h3>}
        {listed.map((section, i) => (
          <section className="exadd__group" key={section.group} aria-labelledby={`exadd-g${i}`}>
            <GroupHead id={`exadd-g${i}`} label={section.group} level={deep ? 4 : 3}
              count={`${section.movements.length} Bewegungen`} />
            {section.movements.map(({ movement: name, rows }) => (rows.length === 1
              ? row(rows[0]!, name, movementMeta(rows), plus)
              : (
                <button type="button" key={name} className="sheet-row exadd__move"
                  data-movement={name} onClick={() => openMovement(name)}>
                  <span className="sheet-row__main">
                    <span className="sheet-row__name">{name}</span>
                    <span className="sheet-row__meta exadd__meta">{movementMeta(rows)}</span>
                  </span>
                  <span className="exadd__trail">
                    <span className="exadd__trail-n">
                      {rows.length}<span className="sr-only"> Geräte</span>
                    </span>
                    <Icon name="forward" />
                  </span>
                </button>
              )))}
          </section>
        ))}
      </>
    )
  }

  return (
    <Sheet id={ID} title={movement ?? 'Übung hinzufügen'}
      onBack={movement !== null ? () => { setArmedId(null); setMovement(null) } : undefined}>
      {movement === null && (
        <div className="exadd__field">
          <Icon name="search" />
          <input
            type="search" id="exadd-search" className="input" autoComplete="off"
            placeholder="Übung oder Gerät suchen" ref={field}
            aria-label="Übung suchen" aria-controls="exadd-list"
            value={query} onChange={(e) => { setQuery(e.target.value); setArmedId(null) }}
          />
        </div>
      )}
      {/* Rendered empty rather than not at all: a live region has to exist
          before its text changes for a screen reader to hear the change. */}
      <p className="exadd__status" role="status">
        {pending !== null && busyExerciseId !== null
          ? `${pending.name} wird hinzugefügt …`
          : added !== null ? `✓ ${added} ist drin.` : ''}
      </p>
      <div className="exadd" id="exadd-list">{body}</div>
    </Sheet>
  )
}

/** A group's caption. It stays under the title bar while its rows scroll by,
 *  so deep in the list you still know which muscle you are in. */
function GroupHead({ id, label, count, level = 3 }: {
  id?: string, label: string, count?: string, level?: 3 | 4
}) {
  const Tag = level === 4 ? 'h4' : 'h3'
  return (
    <Tag className="sheet__group-head exadd__head" id={id}>
      <span className="label">{label}</span>
      {count !== undefined && <>{' '}<span className="exadd__count">{count}</span></>}
    </Tag>
  )
}
