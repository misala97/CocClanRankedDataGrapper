import { useRef } from 'react'
import { CsrfField } from '../csrf'
import type { ExerciseDetailPayload } from '../types'
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
  const p = payload
  const id = p.exercise.id
  const count = p.table.length
  const editSheet = useRef<EditSheetHandle>(null)

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
                          comparison view needs to say so. */}
                      <a className={`pill${p.selected_position === null ? ' is-on' : ''}`}
                        href={`/gym/exercises/${id}?position=all`}>Alle</a>
                      {p.available_positions.map((pos) => (
                        <a key={pos}
                          className={`pill${p.selected_position === pos ? ' is-on' : ''}`}
                          href={`/gym/exercises/${id}?position=${pos}`}>Position {pos}</a>
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
            <form method="post" action={`/gym/exercises/${id}/delete`}
              onSubmit={(e) => { if (!confirm('Übung löschen?')) e.preventDefault() }}>
              <CsrfField />
              <button type="submit" className="quiet-acts__btn quiet-acts__btn--danger">
                Übung löschen
              </button>
            </form>
          )}
        </section>
      </div>

      <EditSheet ref={editSheet} exercise={p.exercise} muscleGroups={p.muscle_groups}
        equipmentLabels={p.equipment_labels} openOnMount={nameTaken} />
    </>
  )
}
