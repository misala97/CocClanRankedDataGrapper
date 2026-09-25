import { useEffect, useState } from 'react'
import { flushSync } from 'react-dom'
import type { ExerciseDetailPayload } from '../types'
import { getJson } from '../api'
import { shortDate } from '../format'
import { Icon } from '../components/Icon'
import { ExerciseHeader } from '../components/ExerciseHeader'
import { RecordsBand } from '../components/RecordsBand'
import { ExerciseChart } from '../components/ExerciseChart'
import { SessionLog } from '../components/SessionLog'
import { EditSheet } from '../components/EditSheet'

/** "Deine Pause" links an exception here: the page opens on the settings. */
const SETTINGS_HASH = '#einstellungen'

interface Props {
  payload: ExerciseDetailPayload
}

/**
 * Exercise detail (Puls): the single-exercise instrument.
 *
 * Order: what state it is in, the two records, the progression chart, every
 * session, and finally the lifter's own settings. Nothing here re-derives
 * anything -- every value comes from routes._exercise_detail_payload. The
 * exercise itself is the one list's: nobody renames or deletes it here.
 *
 * Position stays a SERIES, not just a filter: the same lift in slot 1 and slot
 * 3 is two different stories, and collapsing them would quietly drop that
 * dimension. The pills isolate one, and they are real links so deep links and
 * the back button keep working.
 */
export function ExerciseDetailPage({ payload }: Props) {
  // State, not the prop: the position pills swap the whole payload in place
  // (detail.json honours the filter exactly), so a pill tap is one fetch
  // instead of a full navigation.
  const [p, setP] = useState(payload)
  // A genuinely new server-rendered payload replaces any client-side swap.
  useEffect(() => { setP(payload) }, [payload])
  const id = p.exercise.id
  const count = p.table.length
  // One row per slot: an exercise done at two positions in one workout is
  // two rows here and still one workout (D16).
  const workouts = new Set(p.table.map((row) => row.session_id)).size
  const [editing, setEditing] = useState(false)

  // Arrived from an exception under "Deine Pause": open on the settings, and
  // drop the hash so a reload or the back button lands on the page itself.
  useEffect(() => {
    if (window.location.hash !== SETTINGS_HASH) return
    setEditing(true)
    history.replaceState(history.state, '', window.location.pathname + window.location.search)
  }, [])

  const fetchPosition = (positionParam: string) =>
    getJson<ExerciseDetailPayload>(
      `/gym/exercises/${id}/detail.json?position=${positionParam}`)

  // The swap is wrapped in a view transition where the platform has one --
  // the chart crossfades between filters instead of cutting. flushSync so the
  // new DOM exists inside the transition's capture window.
  const applyPayload = (fresh: ExerciseDetailPayload) => {
    if (document.startViewTransition !== undefined
      && !window.matchMedia('(prefers-reduced-motion: reduce)').matches) {
      document.startViewTransition(() => { flushSync(() => setP(fresh)) })
    } else {
      setP(fresh)
    }
  }

  const switchPosition = (positionParam: string) => {
    fetchPosition(positionParam)
      .then((fresh) => {
        applyPayload(fresh)
        // pushState, so every pill stays a back-button step, the way the
        // full navigations were.
        history.pushState(null, '', `/gym/exercises/${id}?position=${positionParam}`)
      })
      // The pills are real links underneath; a failed fetch falls back to
      // exactly the navigation the link always meant.
      .catch(() => {
        window.location.href = `/gym/exercises/${id}?position=${positionParam}`
      })
  }

  useEffect(() => {
    const onPop = () => {
      const positionParam = new URLSearchParams(window.location.search)
        .get('position') ?? 'all'
      fetchPosition(positionParam).then(applyPayload)
        .catch(() => { window.location.reload() })
    }
    window.addEventListener('popstate', onPop)
    return () => window.removeEventListener('popstate', onPop)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [id])

  const oldest = p.table[count - 1]
  const newest = p.table[0]

  return (
    <>
      <div className="exdetail">
        <ExerciseHeader exercise={p.exercise} lastOverall={p.last_overall}
          chipClass={p.chip_class} chipLabel={p.chip_label} />

        {count > 0 ? (
          <>
            {/* Two wrappers, so the desktop grid has two stable children to
                place. They are inert on phones -- plain blocks whose children
                still carry their own gutters -- and become the analysis column
                and the log column at 900px. */}
            <div className="exdetail__main">
              <RecordsBand prWeight={p.pr_weight} prE1rm={p.pr_e1rm} state={p.state}
                sessionsSincePr={p.sessions_since_pr}
                lastProgression={p.last_progression} />

              <section className="sec sec--chart" aria-labelledby="sec-chart">
                <div className="sec__head">
                  {/* The band's tile names the 1RM in full first (D16); with no
                      set of 1 to 12 reps there is no tile, and the chart below
                      still plots an estimate, so the heading names it. */}
                  <h2 className="label" id="sec-chart">
                    {p.pr_e1rm !== null ? 'Verlauf 1RM' : 'Verlauf des geschätzten Maximums (1RM)'}
                  </h2>
                  <span className="sec__sp" />
                  {/* The count is scoped, so it says what it is counting. It
                      read "10 Workouts" under a chart already filtered to one
                      slot. */}
                  <span className="label">
                    {(p.selected_position !== null ? `Pos. ${p.selected_position} · ` : '')
                      + `${workouts} ${workouts === 1 ? 'Workout' : 'Workouts'}`}
                  </span>
                </div>

                {p.available_positions.length > 1 && (
                  <>
                    <div className="pills">
                      {/* ?position=all, not a bare URL: a bare URL means
                          "decide for me" and lands on the default slot, so the
                          comparison view needs to say so. Still real links --
                          deep links, middle-click and no-JS keep working; a
                          plain click swaps in place. */}
                      <a className={`pill${p.selected_position === null ? ' is-on' : ''}`}
                        href={`/gym/exercises/${id}?position=all`}
                        onClick={(e) => { e.preventDefault(); switchPosition('all') }}>Alle</a>
                      {p.available_positions.map((pos) => (
                        <a key={pos}
                          className={`pill${p.selected_position === pos ? ' is-on' : ''}`}
                          href={`/gym/exercises/${id}?position=${pos}`}
                          onClick={(e) => { e.preventDefault(); switchPosition(String(pos)) }}>
                          Position {pos}</a>
                      ))}
                    </div>
                    {/* Arriving on a filtered page with a pill already lit
                        reads as a choice the reader made and forgot. It is the
                        page's choice, so the page says so and says on what
                        grounds -- otherwise the only way to learn the chart is
                        not the whole exercise is to notice the count disagree
                        with the record band. */}
                    {p.selected_position_is_default && (
                      <p className="exdetail__scope">
                        {`Zeigt Position ${p.selected_position} — ` +
                          (p.selected_position_reason === 'strongest'
                            ? 'die stärkste mit mindestens zwei Workouts'
                            : 'die einzige mit nennenswerter Historie') + '.'}
                      </p>
                    )}
                  </>
                )}

                {p.chart !== null && oldest !== undefined && newest !== undefined && (
                  <ExerciseChart chart={p.chart} sessionCount={workouts}
                    firstDate={shortDate(oldest.started_at)}
                    lastDate={shortDate(newest.started_at)} />
                )}
              </section>
            </div>

            <div className="exdetail__log">
              <SessionLog table={p.table} selectedPosition={p.selected_position}
                isUnilateral={p.exercise.is_unilateral} />
            </div>
          </>
        ) : (
          /* Says what fills the page, not just that it is empty. The old line
             was a dead end on a screen that has nothing else on it. */
          <p className="empty">
            Noch keine Sätze protokolliert. Sobald du diese Übung in einem
            Workout loggst, stehen hier Rekorde, der Verlauf deines geschätzten
            Maximums (1RM) und jedes einzelne Workout.
          </p>
        )}

        <section className="sec sec--maint" aria-label="Deine Einstellungen">
          <button type="button" className="finished__correct"
            onClick={() => setEditing(true)}>
            <Icon name="edit" />
            Pause und Schritt einstellen
          </button>
        </section>
      </div>

      <EditSheet exercise={p.exercise} open={editing} onClose={() => setEditing(false)}
        onSaved={(exercise) => setP((current) => ({ ...current, exercise }))} />
    </>
  )
}
