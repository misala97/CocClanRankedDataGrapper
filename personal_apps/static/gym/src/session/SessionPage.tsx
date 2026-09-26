import { useEffect, useState } from 'react'
import type { SessionDetailPayload } from './types'
import type { SessionMetaPatch } from './api'
import type { PartnerSync } from './usePartnerSync'
import { useAnnouncer, useSheets } from './stores'
import { PARTNER_SHEET, PartnerLines } from '../partner/PartnerLine'
import { PartnerSheet } from '../partner/PartnerSheet'
import type { ShownLink } from '../partner/types'
import { useSheetHistory } from './useSheetHistory'
import { FinishSheet } from './components/FinishSheet'
import { SessionHeader } from './components/SessionHeader'
import { SaveErrorBanner } from './components/SaveErrorBanner'
import { SavingSweep } from './components/SavingSweep'
import { OutboxStatus } from './components/OutboxStatus'
import { ReorderBar } from './components/ReorderBar'
import { PartnerNotice } from './components/PartnerNotice'
import { LiveRegion } from './components/LiveRegion'
import { Rail } from './components/Rail'
import { LivePanel } from './components/LivePanel'
import { SessionTotals } from './components/SessionTotals'
import { TickStrip } from './components/TickStrip'
import { Queue } from './components/Queue'
import { SessionSheet } from './components/SessionSheet'
import { UndoToast } from '../undo'
import { DeloadSheet } from './components/DeloadSheet'
import { AddExerciseSheet } from './components/AddExerciseSheet'
import { TemplateSheet } from './components/TemplateSheet'
import { ExerciseSheet, type ExerciseSheetActions } from './components/ExerciseSheet'
import { LiveSettingsSheet } from './components/LiveSettingsSheet'

/** A row's routine and the plan it keeps, for its sheet: null when the
 *  routine does not hold the exercise, or there is no routine of yours. */
function routineOf(payload: SessionDetailPayload, seId: number) {
  const plan = payload.routine_plans[String(seId)]
  const name = payload.session.template_name
  return plan === undefined || name === null ? null : { name, plan }
}

/**
 * Every write the screen can perform. Supplied by the entry in 2c-iii, which
 * is where the optimistic path and the API client live -- this component knows
 * only that these exist, which is what keeps it renderable from a fixture.
 */
export interface SessionActions {
  /** `setId` is the open set the steppers are bound to; null appends one. */
  onConfirmSet(weight: number, reps: number, setId: number | null): void
  onToggleSet(setId: number, completed: boolean): void
  onFinish(): void
  /** "Jetzt senden": try the writes the phone is holding now (B6). */
  onSendNow(): void
  /** "Neu laden": the fresh page that sends what a lapsed login held. */
  onReload(): void
  /** Throw away a workout with nothing logged -- the finish sheet offers it
   *  only then, and the server refuses it otherwise. */
  onDiscard(): void
  onReorder(order: number[]): void
  onSessionMetaSave(meta: SessionMetaPatch): void
  onSkipRest(): void
  /** "−15" / "+15" on the running rest. */
  onShiftRest(seconds: number): void
  onInvite(partnerId: number): void
  onEnablePush(): void
  onToggleDeload(on: boolean, pct: number): void
  onAddExercise(exerciseId: number): void
  onSaveTemplate(name: string): void
  /** "Noch ein Satz" on the exercise the card just left (G-107): one set
   *  planned where its row stands. */
  onOneMore(sessionExerciseId: number, weight: number, reps: number): void
  exerciseActions(sessionExerciseId: number): ExerciseSheetActions
}

interface Props {
  payload: SessionDetailPayload
  actions: SessionActions
  pushSupported: boolean
  /** Finish or discard is waiting for writes still on their way. */
  finishing?: boolean
  /** Which add-exercise row is waiting on the server -- see AddExerciseSheet. */
  busyExerciseId?: number | null
  /** The training partners' lines (usePartnerSync); none when left out. */
  partners?: PartnerSync
}

const NOTHING_TO_END = () => Promise.resolve({ done: true } as const)
const NO_PARTNERS: PartnerSync = {
  links: [], receivedAt: 0, dismiss: () => {}, withdraw: NOTHING_TO_END, end: NOTHING_TO_END,
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
export function SessionPage({
  payload, actions, pushSupported, finishing = false, busyExerciseId = null,
  partners = NO_PARTNERS,
}: Props) {
  // Back closes the open sheet instead of leaving the workout (G-066).
  useSheetHistory()
  const announce = useAnnouncer((s) => s.announce)
  const openSheet = useSheets((s) => s.open)
  // Whose list is open. The line itself is looked up on every render, so
  // an open list follows the poll, and it is remembered as last carried: a
  // line the poll drops (put away on the other phone, a partner gone) keeps
  // its sheet as it last was, rather than turning into a list nobody has.
  const [partnerShown, setPartnerShown] = useState<ShownLink | null>(null)
  const shownLine = partnerShown === null
    ? undefined : partners.links.find((link) => link.id === partnerShown.id)
  useEffect(() => { if (shownLine !== undefined) setPartnerShown(shownLine) }, [shownLine])
  const partnerTarget = partnerShown === null ? null : {
    id: partnerShown.id, username: partnerShown.username, line: shownLine ?? partnerShown,
  }
  const inWorkout = payload.visible_exercises.map((se) => se.exercise_id)

  return (
    // No wrapper element: the mount node in session_detail.html already IS
    // .session-view, so adding one here would put an extra layer between
    // #gym-main and it -- which measurably changed the page height.
    <>
      <SessionHeader session={payload.session}
          deloadApplied={payload.deload_applied}
          deloadDefaultPct={payload.deload_default_pct} />

      {/* Right under the header, one 52 px line per partner (D14, M5). */}
      <PartnerLines links={partners.links} receivedAt={partners.receivedAt}
        onOpen={(link) => {
          setPartnerShown(link)
          openSheet(PARTNER_SHEET)
        }}
        onDismiss={partners.dismiss} />

      <SaveErrorBanner />
      <OutboxStatus onSendNow={actions.onSendNow} onReload={actions.onReload} />
      <SavingSweep />
      <ReorderBar />
      <PartnerNotice />
      <LiveRegion />

      <Rail exercises={payload.visible_exercises} liveId={payload.live_id}
        liveIndex={payload.live_index}
        setsOpen={payload.sets_open} setsTotal={payload.sets_total} />

      <LivePanel payload={payload}
        onConfirm={actions.onConfirmSet}
        onToggleSet={actions.onToggleSet}
        onRestOver={() => announce('Pause vorbei.')}
        onShiftRest={actions.onShiftRest}
        onSkipRest={actions.onSkipRest}
        onOneMore={actions.onOneMore} />

      <SessionTotals volume={payload.session_volume}
        setsDone={payload.sets_done}
        startedAt={payload.session.started_at} />

      <TickStrip states={payload.tick_states}
        done={payload.sets_done} total={payload.sets_total} />

      <Queue exercises={payload.visible_exercises} liveId={payload.live_id}
        deloadHints={payload.deload_hints} onReorder={actions.onReorder} />

      <div className="session-foot">
        {/* Opens the finish sheet -- the pre-debrief beat -- instead of a
            native confirm() the design cannot style. */}
        <button type="button" className="btn btn--ghost btn--block"
          onClick={() => openSheet('sheet-finish')}>Workout beenden</button>
      </div>
      {/* Inside .session-view now rather than beside it. A modal <dialog> is
          promoted to the top layer and is not laid out by its DOM ancestors,
          and a closed one is display:none -- so nesting them costs no layout
          and saves the wrapper that did. */}
      <SessionSheet session={payload.session} resting={payload.resting}
        partners={payload.partners}
        following={payload.session_is_shared}
        pushSupported={pushSupported}
        onMetaSave={actions.onSessionMetaSave}
        onSkipRest={actions.onSkipRest}
        onInvite={actions.onInvite}
        onEnablePush={actions.onEnablePush} />

      <PartnerSheet target={partnerTarget} actions={partners} />

      <DeloadSheet session={payload.session}
        deloadApplied={payload.deload_applied}
        deloadPcts={payload.deload_pcts}
        deloadDefaultPct={payload.deload_default_pct}
        hasCompletedSet={payload.has_completed_set}
        onToggle={actions.onToggleDeload} />

      <AddExerciseSheet catalogue={payload.exercises} groups={payload.list_groups}
        inSession={payload.visible_exercises}
        busyExerciseId={busyExerciseId}
        onAdd={actions.onAddExercise} />

      <TemplateSheet onSave={actions.onSaveTemplate} />

      <FinishSheet volume={payload.session_volume}
        setsDone={payload.sets_done} setsTotal={payload.sets_total}
        startedAt={payload.session.started_at}
        finishing={finishing}
        onFinish={actions.onFinish}
        onDiscard={actions.onDiscard} />

      {payload.visible_exercises.map((se) => (
        <LiveSettingsSheet key={se.id} exercise={se} sessionId={payload.session.id} />
      ))}
      {payload.visible_exercises.map((se) => (
        <ExerciseSheet key={se.id} exercise={se}
          catalogue={payload.exercises} inWorkout={inWorkout}
          suggestion={payload.suggestions[String(se.id)] ?? null}
          routine={routineOf(payload, se.id)}
          // Moving a row is a reorder, which a follower's order refuses (it
          // is the leader's). A finished or skipped exercise has nothing to
          // do now, and the live one is already up.
          canMakeLive={!payload.session_is_shared
            && se.id !== payload.live_id
            && !se.skipped
            && !(se.sets.length > 0 && se.sets.every((s) => s.completed))}
          {...actions.exerciseActions(se.id)} />
      ))}
      <UndoToast />
    </>
  )
}
