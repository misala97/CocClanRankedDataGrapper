import { useEffect, useRef, useState } from 'react'
import {
  QueryClient, QueryClientProvider, useQuery, useQueryClient,
} from '@tanstack/react-query'
import type { SessionDetailPayload } from './types'
import { fetchSession, MutationFailed, sessionKey } from './api'
import { postNavigate } from '../api'
import { enablePush, heartbeatSubscription } from '../push'
import { useUndo } from '../undo'
import * as optimistic from './optimistic'
import { setName } from './setName'
import { Outbox, exclusively, localShelf, newId, writeHold } from './outbox'
import { writeSpecs, type WriteArgs, type WriteKind } from './writes'
import { clearDraft, sweepDrafts } from './drafts'
import { failureCheckpoint, useOutbox, usePush, useSaveState, useSheets } from './stores'
import { useWakeLock } from './useWakeLock'
import { useFollowerSync } from './useFollowerSync'
import { SessionPage, type SessionActions } from './SessionPage'
import type { ExerciseSheetActions } from './components/ExerciseSheet'

const pushSupported = 'serviceWorker' in navigator && 'PushManager' in window

/** A second add for the same exercise this soon is the first tap bouncing,
 *  not a set: round 4's band guard, for "Satz geschafft" and the sheet's add
 *  row alike. The client key makes a resend safe; this stops a double tap. */
export const APPEND_GUARD_MS = 600

/** Hidden this long, the page asks the server again on its way back: the
 *  three-hour rule may have ended the workout meanwhile (every GET settles
 *  it), and a screen left open overnight should say so, not take sets. */
export const STALE_AFTER_HIDDEN_MS = 30 * 60 * 1000

let lastTempId = 0

/** A set's id until the server names it: negative, so never a real one, and
 *  from the clock, so a new page never repeats one an old page left in the
 *  outbox. */
function tempId(): number {
  lastTempId = Math.min(lastTempId - 1, -Date.now())
  return lastTempId
}

/**
 * Wires the page's actions to the outbox.
 *
 * Everything the screen writes goes through one queue (./outbox.ts), so the
 * optimistic path, the order, the retry and the banner are defined once
 * rather than per call site -- and a set logged with no signal stays logged,
 * kept on the phone until it lands (B6, D6-A).
 */
function SessionIslandInner({ initial }: { initial: SessionDetailPayload }) {
  const sessionId = initial.session.id
  const client = useQueryClient()

  // The screen stays on for as long as the workout is live -- this island
  // only ever renders an unfinished session, so the flag is simply true.
  useWakeLock(true)

  // Back from the debrief, a page restored from the browser's cache would
  // still be live and accepting taps into a finished workout: the entry
  // reloads it, as every gym page's does (../fresh.ts).

  const [outbox] = useState(() => {
    sweepDrafts(sessionId)
    const saves = useSaveState.getState()
    return new Outbox(initial, {
      specs: writeSpecs(sessionId),
      shelf: localShelf(sessionId),
      show: (payload) => { client.setQueryData(sessionKey(sessionId), payload) },
      status: (status) => { useOutbox.getState().publish(status) },
      hold: (oldestAt) => { writeHold(sessionId, oldestAt) },
      begin: saves.begin,
      end: saves.end,
      succeed: saves.succeed,
      fail: saves.fail,
      fetchFresh: () => fetchSession(sessionId),
      finished: () => { window.location.reload() },
      gone: () => { window.location.assign('/gym') },
      reload: () => { window.location.reload() },
      // Everything held back is in: ask again, with the hold cookie gone.
      // Past the three-hour rule by now, the GET ends the workout at its
      // real last set -- the replayed ones included -- and the effect below
      // shows its debrief.
      drained: () => { void client.invalidateQueries({ queryKey: sessionKey(sessionId) }) },
      relive: optimistic.relive,
      exclusive: exclusively(`gym-outbox-${sessionId}`),
      now: () => Date.now(),
      newId,
    })
  })

  const { data, error } = useQuery({
    queryKey: sessionKey(sessionId),
    // Through the outbox: an answer to a write that lands while this is on
    // its way is newer than it, and the writes not answered yet go on top.
    queryFn: async () => {
      const stamp = outbox.stamp()
      return outbox.receive(await fetchSession(sessionId), stamp)
    },
    initialData: () => outbox.display(),
    // The server is asked only when something changed it. Every write
    // returns the fresh payload, so polling for its own writes would be
    // asking a question it already has the answer to.
    staleTime: Infinity,
    refetchOnWindowFocus: false,
  })

  // Sends what the phone kept -- from before a reload, from yesterday --
  // and tries again the moment there may be a way through: the connection
  // back, the app back in front. A phone with dead wifi never fires
  // `online`; the backoff and the next tap cover it.
  useEffect(() => {
    outbox.start()
    let hiddenAt: number | null = null
    const kick = () => { outbox.kick() }
    const onVisibility = () => {
      if (document.visibilityState === 'hidden') { hiddenAt = Date.now(); return }
      outbox.kick()
      const away = hiddenAt === null ? 0 : Date.now() - hiddenAt
      hiddenAt = null
      // With writes held, the drain asks by itself once they are in.
      if (away >= STALE_AFTER_HIDDEN_MS && useOutbox.getState().count === 0) {
        void client.invalidateQueries({ queryKey: sessionKey(sessionId) })
      }
    }
    window.addEventListener('online', kick)
    window.addEventListener('pageshow', kick)
    document.addEventListener('visibilitychange', onVisibility)
    return () => {
      outbox.stop()
      window.removeEventListener('online', kick)
      window.removeEventListener('pageshow', kick)
      document.removeEventListener('visibilitychange', onVisibility)
    }
  }, [outbox, client, sessionId])

  // Finished under this screen -- on the other phone, or by the three-hour
  // rule: a refetch says so, and the page for the workout now is its
  // debrief. The screen kept taking sets for it (B4 review).
  useEffect(() => {
    if (data.session.finished_at !== null) {
      clearDraft(sessionId)
      window.location.reload()
    }
  }, [data.session.finished_at, sessionId])
  // Thrown away under this screen -- on the other phone, or by the three-hour
  // rule with nothing in it: there is no page for it any more. A refetch
  // read that as a lost connection (B4 re-review).
  useEffect(() => {
    if (error instanceof MutationFailed && error.reason === 'gone') window.location.assign('/gym')
  }, [error])

  // Training with a partner: the leader's structural edits land in these rows
  // as writes, so the page only has to notice they happened. Server-gated to
  // the follower half of a live link.
  useFollowerSync(sessionId, {
    enabled: data.session_is_shared,
    knownVersion: data.session.structure_version,
  })

  // Only the browser knows whether THIS device is subscribed -- a subscription
  // is a browser endpoint, one per device, so a server-side answer hid the
  // button on every other device the same person owns. Probed once and cached,
  // never re-asked on every render.
  const setSubscribed = usePush((s) => s.setSubscribed)
  useEffect(() => {
    if (!pushSupported) { setSubscribed(false); return }
    navigator.serviceWorker.getRegistration('/gym')
      .then((registration) => registration?.pushManager.getSubscription() ?? null)
      .then((subscription) => {
        setSubscribed(subscription !== null)
        // The same probe doubles as the heartbeat: this device is the only
        // thing that can say its endpoint is still the current one.
        heartbeatSubscription(subscription)
      })
      .catch(() => setSubscribed(false))
  }, [setSubscribed])

  /** Queues a write. The promise settles once the server has answered it --
   *  never for a lost connection, which only means later -- and rejects when
   *  it was refused or could not be kept, which the banner already says. */
  const write = <K extends WriteKind>(kind: K, ...args: WriteArgs[K]) =>
    outbox.enqueue(kind, args)
  const send = <K extends WriteKind>(kind: K, ...args: WriteArgs[K]) => {
    write(kind, ...args).catch(() => {})
  }

  const close = useSheets((s) => s.close)
  const openSheet = useSheets((s) => s.open)
  const offerUndo = useUndo((s) => s.offer)

  // Un-logging a chip waits out the undo window before it is sent, like every
  // other destructive tap here -- a sweaty thumb on a done chip used to undo
  // the set on the spot. Until then the screen shows it open, drawn over the
  // payload with the same guess the write itself makes.
  // By its name, not its id: a set just added changes id when it lands.
  const [pendingUnlog, setPendingUnlog] = useState<string | null>(null)
  const unlogged = pendingUnlog === null
    ? undefined
    : data.visible_exercises.flatMap((se) => se.sets).find((s) => setName(s) === pendingUnlog)
  const view = unlogged === undefined
    ? data
    : optimistic.toggleSet(data, unlogged.id, false, unlogged.weight, unlogged.reps)

  const [finishing, setFinishing] = useState(false)
  // An add has no optimistic path, so its row is the only place that can say
  // the tap landed.
  const [addingExerciseId, setAddingExerciseId] = useState<number | null>(null)

  const live = view.visible_exercises.find((se) => se.id === view.live_id) ?? null

  /** Leave for `url` once every write has landed. Finishing with a set still
   *  on its way used to navigate away from it: the form post won the race and
   *  the set never reached the workout. A pending undo goes into the queue
   *  first, and so does every lost write that mends by itself -- finishing
   *  past one filed the workout without it (B4 review). Writes that cannot
   *  get through keep the lifter here, and the status line says why; so does
   *  a write that fails on the way, one only the lifter may send again, or
   *  one only a fresh page mends.
   *
   *  `discarding`: the workout is thrown away, and whatever was not sent goes
   *  with it. Sent first, a lost set landed and the discard refused a
   *  workout that now had one (B4 re-review). */
  const leaveAfterWrites = async (url: string, discarding = false) => {
    setFinishing(true)
    if (discarding) {
      useSaveState.getState().dismissErrors()
      useUndo.getState().commitNow()
      await outbox.clear()
      clearDraft(sessionId)
      postNavigate(url)
      return
    }
    const failedSince = failureCheckpoint()
    useSaveState.getState().resendAll()
    useUndo.getState().commitNow()
    const drained = await outbox.flush()
    if (!drained || failedSince()
      || useSaveState.getState().errors.some((e) => e.remedy !== 'auto')) {
      setFinishing(false)
      if (!drained) useOutbox.getState().refuseFinish()
      close()
      return
    }
    clearDraft(sessionId)
    postNavigate(url)
  }

  // Per exercise: when its last add went out (APPEND_GUARD_MS).
  const lastAppend = useRef(new Map<number, number>())
  const appendSet = (seId: number, weight: number, reps: number) => {
    const now = Date.now()
    if (now - (lastAppend.current.get(seId) ?? -Infinity) < APPEND_GUARD_MS) return
    lastAppend.current.set(seId, now)
    send('addSet', seId, weight, reps, newId(), tempId())
  }

  const actions: SessionActions = {
    onConfirmSet: (weight, reps, setId) => {
      if (live === null) return
      // The set the steppers are bound to is confirmed; with nothing open,
      // gym_add_set creates one already completed -- which is what "Satz
      // geschafft" means everywhere else on this screen.
      if (setId === null) {
        appendSet(live.id, weight, reps)
        return
      }
      if (unlogged !== undefined && unlogged.id === setId) {
        // Re-logging the chip whose un-log is still in its undo window: queue
        // the un-log now, so the numbers on the steppers are what lands.
        useUndo.getState().commitNow()
        setPendingUnlog(null)
      }
      send('toggleSet', setId, true, weight, reps)
    },
    onToggleSet: (setId, completed) => {
      const owner = data.visible_exercises.find((se) => se.sets.some((s) => s.id === setId))
      const target = owner?.sets.find((s) => s.id === setId)
      if (owner === undefined || target === undefined) return
      if (completed) {
        send('toggleSet', setId, true, target.weight, target.reps)
        return
      }
      const name = setName(target)
      setPendingUnlog(name)
      offerUndo({
        label: `Satz ${owner.sets.indexOf(target) + 1} wieder offen.`,
        undo: () => setPendingUnlog(null),
        // On the phone the moment it is queued -- a flush on the way out of
        // the page included -- and drawn open by the outbox from then on.
        // A drawn id the server has named since is sent as the real one.
        commit: () => {
          send('toggleSet', setId, false, target.weight, target.reps)
          setPendingUnlog((pending) => (pending === name ? null : pending))
        },
      })
    },
    // A POST that redirects to the debrief. This was `window.location.href`
    // -- a GET to a POST-only route, a 405 for everyone -- until 2026-08-11.
    onFinish: () => { void leaveAfterWrites(`/gym/session/${sessionId}/finish`) },
    onDiscard: () => { void leaveAfterWrites(`/gym/session/${sessionId}/discard`, true) },
    onSendNow: () => { outbox.kick() },
    onReload: () => { window.location.reload() },
    onReorder: (order) => send('reorder', order),
    // Saved per field as it is left, so the sheet stays open: leaving the
    // bodyweight for the note must not close it under the lifter.
    onSessionMetaSave: (meta) => send('sessionMeta', meta),
    onSkipRest: () => { send('skipRest'); close() },
    // Each tap is its own write, and each moves the countdown on the spot.
    onShiftRest: (seconds) => send('shiftRest', seconds),
    // A navigation, not an in-place write: the invite has its own page.
    // postNavigate carries the csrf_token the hand-built form here forgot,
    // which the blueprint gate has 403'd since it closed.
    onInvite: (partnerId) => postNavigate(
      `/gym/session/${sessionId}/invite`, { partner_id: String(partnerId) }),
    onEnablePush: () => { void enablePush(data.vapid_public_key) },
    onToggleDeload: (on, pct) => { send('toggleDeload', on, pct); close() },
    onAddExercise: (exerciseId) => {
      setAddingExerciseId(exerciseId)
      write('addExercise', exerciseId)
        .catch(() => {})
        .finally(() => setAddingExerciseId((id) => (id === exerciseId ? null : id)))
    },
    onSaveTemplate: (name) => postNavigate(
      `/gym/session/${sessionId}/save_as_template`, { template_name: name }),
    exerciseActions: (seId: number): ExerciseSheetActions => ({
      onRestChange: (seconds) => send('setRest', seId, seconds),
      onRoutinePlanChange: (plan) => send('routinePlan', seId, plan),
      onOpenSettings: () => openSheet(`sheet-settings-${seId}`),
      // No close(): the flag saves on the tap and the note on blur, both
      // while the sheet stays open.
      onMetaSave: (meta) => send('exerciseMeta', seId, meta),
      onSetUpdate: (setId, weight, reps) => send('updateSet', setId, weight, reps),
      // The promise, so the sheet can bring the row back if it is refused.
      onSetDelete: (setId) => write('deleteSet', setId),
      onAddSet: (weight, reps) => appendSet(seId, weight, reps),
      // In front of the live exercise, which is how the live rule reads a
      // step away from a busy machine (_live_context).
      onMakeLive: () => {
        const order = data.visible_exercises.map((se) => se.id).filter((id) => id !== seId)
        const at = data.live_id === null ? 0 : Math.max(0, order.indexOf(data.live_id))
        order.splice(at, 0, seId)
        send('reorder', order)
        close()
      },
      // The state wanted, not a flip: sent twice, a flip undid itself.
      onToggleSkip: () => {
        const se = data.visible_exercises.find((row) => row.id === seId)
        if (se !== undefined) send('toggleSkip', seId, !se.skipped)
        close()
      },
      onReplace: (exerciseId) => { send('replaceExercise', seId, exerciseId); close() },
      onRemove: () => { send('removeExercise', seId); close() },
      onShowProgress: () => {
        const se = data.visible_exercises.find((row) => row.id === seId)
        if (se) window.location.href = `/gym/exercises/${se.exercise_id}`
      },
    }),
  }

  return (
    <SessionPage payload={view} actions={actions} pushSupported={pushSupported}
      finishing={finishing} busyExerciseId={addingExerciseId} />
  )
}

export function SessionIsland({ initial }: { initial: SessionDetailPayload }) {
  // One client per island. Retries are off: the outbox owns every write and
  // its retries, and a query that fails says so (a workout gone, a login
  // lapsed) rather than asking again behind the lifter's back.
  //
  // useState's initialiser, not a bare `new` in the body: that built a fresh
  // client -- and an empty cache -- on every render of this component.
  const [client] = useState(() => new QueryClient({
    defaultOptions: { mutations: { retry: false }, queries: { retry: false } },
  }))

  return (
    <QueryClientProvider client={client}>
      <SessionIslandInner initial={initial} />
    </QueryClientProvider>
  )
}
