import { useEffect, useRef, useState } from 'react'
import { flushSync } from 'react-dom'
import type { ExerciseDetailPayload } from '../types'
import { getJson, postForm } from '../api'
import { UndoToast, useUndo } from '../undo'
import { shortDate } from '../format'
import { Icon } from '../components/Icon'
import { ExerciseHeader } from '../components/ExerciseHeader'
import { RecordsBand } from '../components/RecordsBand'
import { ExerciseChart } from '../components/ExerciseChart'
import { SessionLog } from '../components/SessionLog'
import { EditSheet, type EditSheetHandle } from '../components/EditSheet'

interface Props {
  payload: ExerciseDetailPayload
  nameTaken: boolean
}

/**
 * Exercise detail (Puls): the single-exercise instrument.
 *
 * Order: what state it is in, the two records, the progression chart, every
 * session, and finally maintenance. Nothing here re-derives anything -- every
 * value comes from routes._exercise_detail_payload.
 *
 * Position stays a SERIES, not just a filter: the same lift in slot 1 and slot
 * 3 is two different stories, and collapsing them would quietly drop that
 * dimension. The pills isolate one, and they are real links so deep links and
 * the back button keep working.
 */
export function ExerciseDetailPage({ payload, nameTaken }: Props) {
  // State, not the prop: the position pills swap the whole payload in place
  // (detail.json honours the filter exactly), so a pill tap is one fetch
  // instead of a full navigation.
  const [p, setP] = useState(payload)
  // A genuinely new server-rendered payload replaces any client-side swap.
  useEffect(() => { setP(payload) }, [payload])
  const id = p.exercise.id
  const count = p.table.length
  const editSheet = useRef<EditSheetHandle>(null)

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

        {nameTaken && (
          <section className="next-time">
            <div className="next-time__lbl">Name nicht geändert</div>
            <p className="next-time__body">Eine Übung mit diesem Namen gibt es schon.</p>
          </section>
        )}

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
                  <h2 className="label" id="sec-chart">Verlauf e1RM</h2>
                  <span className="sec__sp" />
                  {/* The count is scoped, so it says what it is counting. It
                      read "10 Einheiten" under a chart already filtered to one
                      slot. */}
                  <span className="label">
                    {(p.selected_position !== null ? `Pos. ${p.selected_position} · ` : '')
                      + `${count} ${count === 1 ? 'Einheit' : 'Einheiten'}`}
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
                            ? 'die stärkste mit mindestens zwei Einheiten'
                            : 'die einzige mit nennenswerter Historie') + '.'}
                      </p>
                    )}
                  </>
                )}

                {p.chart !== null && oldest !== undefined && newest !== undefined && (
                  <ExerciseChart chart={p.chart} sessionCount={count}
                    firstDate={shortDate(oldest.started_at)}
                    lastDate={shortDate(newest.started_at)} />
                )}
              </section>
            </div>

            <div className="exdetail__log">
              <SessionLog table={p.table} selectedPosition={p.selected_position}
                isUnilateral={p.exercise.is_unilateral}
                prWeight={p.pr_weight} prE1rm={p.pr_e1rm} />
            </div>
          </>
        ) : (
          /* Says what fills the page, not just that it is empty. The old line
             was a dead end on a screen that has nothing else on it. */
          <p className="empty">
            Noch keine Sätze protokolliert. Sobald du diese Übung in einem
            Workout loggst, stehen hier Rekorde, der e1RM-Verlauf und jede
            einzelne Einheit.
          </p>
        )}

        <section className="sec sec--maint" aria-label="Übung verwalten">
          <button type="button" className="finished__correct"
            onClick={() => editSheet.current?.open()}>
            <Icon name="edit" />
            Name, Muskelgruppe, Standard-Pause bearbeiten
          </button>
          {p.can_delete && (
            /* Delayed-commit undo instead of confirm(): the toast reports it,
               five seconds to take it back, then the POST fires and the page
               moves on to the catalogue. */
            <button type="button" className="quiet-acts__btn quiet-acts__btn--danger"
              onClick={() => useUndo.getState().offer({
                label: `Übung „${p.exercise.name}“ gelöscht.`,
                commit: (keepalive) => {
                  postForm<{ deleted: boolean }>(
                    `/gym/exercises/${id}/delete`, {}, { keepalive })
                    .then(() => { if (!keepalive) window.location.assign('/gym/uebungen') })
                    // A failed delete leaves the exercise standing -- staying
                    // on its page is the honest outcome.
                    .catch(() => {})
                },
                undo: () => {},
              })}>
              Übung löschen
            </button>
          )}
        </section>
      </div>

      <EditSheet ref={editSheet} exercise={p.exercise} muscleGroups={p.muscle_groups}
        equipmentLabels={p.equipment_labels} openOnMount={nameTaken} />
      <UndoToast />
    </>
  )
}
