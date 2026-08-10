import type { SessionDetailPayload } from './types'
import { useAnnouncer } from './stores'
import { SessionHeader } from './components/SessionHeader'
import { SaveErrorBanner } from './components/SaveErrorBanner'
import { ReorderBar } from './components/ReorderBar'
import { LiveRegion } from './components/LiveRegion'
import { Rail } from './components/Rail'
import { LivePanel } from './components/LivePanel'
import { SessionTotals } from './components/SessionTotals'
import { TickStrip } from './components/TickStrip'
import { Queue } from './components/Queue'
import { SessionSheet } from './components/SessionSheet'
import { DeloadSheet } from './components/DeloadSheet'
import { AddExerciseSheet } from './components/AddExerciseSheet'
import { TemplateSheet } from './components/TemplateSheet'
import { ExerciseSheet, type ExerciseSheetActions } from './components/ExerciseSheet'

/**
 * Every write the screen can perform. Supplied by the entry in 2c-iii, which
 * is where the optimistic path and the API client live -- this component knows
 * only that these exist, which is what keeps it renderable from a fixture.
 */
export interface SessionActions {
  onConfirmSet(weight: number, reps: number): void
  onToggleSet(setId: number, completed: boolean): void
  onFinish(): void
  onSessionMetaSave(meta: { bodyweightKg: number | null; notes: string }): void
  onSkipRest(): void
  onInvite(partnerId: number): void
  onEnablePush(): void
  onToggleDeload(on: boolean, pct: number): void
  onAddExercise(exerciseId: number): void
  onCreateExercise(name: string): void
  onSaveTemplate(name: string): void
  exerciseActions(sessionExerciseId: number): ExerciseSheetActions
}

interface Props {
  payload: SessionDetailPayload
  actions: SessionActions
  pushSupported: boolean
  busySetId?: number | null
}

/**
 * The live workout.
 *
 * Shape: a focus header, two rails, the one lifted panel for the exercise you
 * are on, what the session has become, and the queue. Every other control the
 * old screen kept permanently on the page now lives in a sheet, because that
 * layout spent its top third on chrome before showing a single set.
 *
 * Which exercise is live is decided by the server, not here: three surfaces
 * have to agree on it, and a rule expressed three times is a rule that drifts.
 */
export function SessionPage({ payload, actions, pushSupported, busySetId = null }: Props) {
  const announce = useAnnouncer((s) => s.announce)

  return (
    // No wrapper element: the mount node in session_detail.html already IS
    // .session-view, so adding one here would put an extra layer between
    // #gym-main and it -- which measurably changed the page height.
    <>
      <SessionHeader session={payload.session}
          deloadApplied={payload.deload_applied}
          deloadDefaultPct={payload.deload_default_pct} />

      <SaveErrorBanner />
      <ReorderBar />
      <LiveRegion />

      <Rail exercises={payload.visible_exercises} liveId={payload.live_id}
        liveIndex={payload.live_index}
        setsOpen={payload.sets_open} setsTotal={payload.sets_total} />

      <LivePanel payload={payload} busySetId={busySetId}
        onConfirm={actions.onConfirmSet}
        onToggleSet={actions.onToggleSet}
        onRestOver={() => announce('Pause vorbei.')} />

      <SessionTotals volume={payload.session_volume}
        setsDone={payload.sets_done}
        startedAt={payload.session.started_at} />

      <TickStrip states={payload.tick_states}
        done={payload.sets_done} total={payload.sets_total} />

      <Queue exercises={payload.visible_exercises} liveId={payload.live_id} />

      <div className="session-foot">
        <button type="button" className="btn btn--ghost btn--block"
          onClick={() => {
            if (confirm('Workout beenden?')) actions.onFinish()
          }}>Workout beenden</button>
      </div>
      {/* Inside .session-view now rather than beside it. A modal <dialog> is
          promoted to the top layer and is not laid out by its DOM ancestors,
          and a closed one is display:none -- so nesting them costs no layout
          and saves the wrapper that did. */}
      <SessionSheet session={payload.session} resting={payload.resting}
        partners={payload.partners} partnerStatus={payload.partner_status}
        pushSupported={pushSupported}
        onMetaSave={actions.onSessionMetaSave}
        onSkipRest={actions.onSkipRest}
        onInvite={actions.onInvite}
        onEnablePush={actions.onEnablePush} />

      <DeloadSheet session={payload.session}
        deloadApplied={payload.deload_applied}
        deloadPcts={payload.deload_pcts}
        deloadDefaultPct={payload.deload_default_pct}
        hasCompletedSet={payload.has_completed_set}
        onToggle={actions.onToggleDeload} />

      <AddExerciseSheet catalogue={payload.exercises}
        inSession={payload.visible_exercises}
        onAdd={actions.onAddExercise}
        onCreate={actions.onCreateExercise} />

      <TemplateSheet onSave={actions.onSaveTemplate} />

      {payload.visible_exercises.map((se) => (
        <ExerciseSheet key={se.id} exercise={se}
          catalogue={payload.exercises}
          suggestion={payload.suggestions[String(se.id)] ?? null}
          {...actions.exerciseActions(se.id)} />
      ))}
    </>
  )
}
