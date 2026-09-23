import { useEffect, useState } from 'react'
import {
  QueryClient, QueryClientProvider, useQuery, useQueryClient,
} from '@tanstack/react-query'
import type { SessionDetailPayload } from './types'
import { api, fetchSession } from './api'
import { postNavigate } from '../api'
import { csrfToken } from '../csrf'
import { heartbeatSubscription } from '../push'
import { useUndo } from '../undo'
import { sessionKey, useSessionMutation } from './useSessionMutation'
import * as optimistic from './optimistic'
import { usePush, useSaveState, useSheets } from './stores'
import { useWakeLock } from './useWakeLock'
import { useFollowerSync } from './useFollowerSync'
import { SessionPage, type SessionActions } from './SessionPage'
import type { ExerciseSheetActions } from './components/ExerciseSheet'

const pushSupported = 'serviceWorker' in navigator && 'PushManager' in window

/** Resolves once no write to this workout is in flight or queued behind one.
 *  Mutations share a scope per session (useSessionMutation), so a queued write
 *  counts as pending until its own request has answered. */
export function writesSettled(client: QueryClient, key: readonly unknown[]): Promise<void> {
  return new Promise((resolve) => {
    const idle = () => client.isMutating({ mutationKey: key }) === 0
    if (idle()) { resolve(); return }
    const unsubscribe = client.getMutationCache().subscribe(() => {
      if (idle()) { unsubscribe(); resolve() }
    })
  })
}

/**
 * Wires the page's actions to the mutation layer.
 *
 * Everything the screen writes goes through useSessionMutation, so the
 * optimistic path, the rollback, the save counter and the error banner are
 * defined once rather than per call site -- which is the arrangement the old
 * screen never had and paid for in stale-state bugs.
 */
function SessionIslandInner({ initial }: { initial: SessionDetailPayload }) {
  const sessionId = initial.session.id
  const client = useQueryClient()

  // The screen stays on for as long as the workout is live -- this island
  // only ever renders an unfinished session, so the flag is simply true.
  useWakeLock(true)

  // Back from the debrief, the browser restores this page from its cache,
  // still live and still accepting taps -- into a workout that has finished.
  // A restored page is a stale one; the server knows what it is now.
  useEffect(() => {
    const onShow = (event: PageTransitionEvent) => {
      if (event.persisted) window.location.reload()
    }
    window.addEventListener('pageshow', onShow)
    return () => window.removeEventListener('pageshow', onShow)
  }, [])

  const { data } = useQuery({
    queryKey: sessionKey(sessionId),
    queryFn: () => fetchSession(sessionId),
    initialData: initial,
    // The server is asked only when something changed it. Every mutation
    // returns the fresh payload, so polling for its own writes would be
    // asking a question it already has the answer to.
    staleTime: Infinity,
    refetchOnWindowFocus: false,
  })

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

  const toggleSet = useSessionMutation(sessionId,
    (setId: number, completed: boolean, weight: number, reps: number) =>
      api.toggleSet(setId, completed, weight, reps),
    optimistic.toggleSet)
  const addSet = useSessionMutation(sessionId,
    (seId: number, weight: number, reps: number) => api.addSet(seId, weight, reps))
  const updateSet = useSessionMutation(sessionId,
    (setId: number, weight: number, reps: number) => api.updateSet(setId, weight, reps),
    optimistic.updateSet)
  const deleteSet = useSessionMutation(sessionId,
    (setId: number) => api.deleteSet(setId), optimistic.deleteSet)
  const toggleSkip = useSessionMutation(sessionId,
    (seId: number) => api.toggleSkip(seId), optimistic.toggleSkip)
  const exerciseMeta = useSessionMutation(sessionId,
    (seId: number, meta: { pain: boolean; notes: string }) =>
      api.setExerciseMeta(seId, meta),
    optimistic.setExerciseMeta)

  // Reordering is optimistic for the row order alone -- that IS the user's
  // intent -- while live_id waits for the server like every other live-moving
  // write below.
  const reorder = useSessionMutation(sessionId,
    (order: number[]) => api.reorder(sessionId, order),
    optimistic.reorderExercises)

  // No optimistic entry: each of these moves which exercise is live, and that
  // decision belongs to the server.
  const addExercise = useSessionMutation(sessionId,
    (exerciseId: number) => api.addExercise(sessionId, exerciseId))
  const removeExercise = useSessionMutation(sessionId,
    (seId: number) => api.removeExercise(seId))
  const replaceExercise = useSessionMutation(sessionId,
    (seId: number, exerciseId: number) => api.replaceExercise(seId, exerciseId))

  const setRest = useSessionMutation(sessionId,
    (seId: number, seconds: number | null) => api.setRest(seId, seconds))
  const setIncrement = useSessionMutation(sessionId,
    (seId: number, kg: number | null) => api.setIncrement(seId, kg))
  const sessionMeta = useSessionMutation(sessionId,
    (meta: { bodyweightKg: number | null; notes: string }) =>
      api.setSessionMeta(sessionId, meta))
  const skipRest = useSessionMutation(sessionId, () => api.skipRest(sessionId))
  const toggleDeload = useSessionMutation(sessionId,
    (on: boolean, pct: number) => api.toggleDeload(sessionId, on, pct))

  const close = useSheets((s) => s.close)
  const lock = useSaveState((s) => s.lock)
  const unlock = useSaveState((s) => s.unlock)
  const offerUndo = useUndo((s) => s.offer)

  // Un-logging a chip waits out the undo window before it is sent, like every
  // other destructive tap here -- a sweaty thumb on a done chip used to undo
  // the set on the spot. Until then the screen shows it open, drawn over the
  // server's payload with the same guess the write itself would make.
  const [pendingUnlog, setPendingUnlog] = useState<number | null>(null)
  const unlogged = pendingUnlog === null
    ? undefined
    : data.visible_exercises.flatMap((se) => se.sets).find((s) => s.id === pendingUnlog)
  const view = unlogged === undefined
    ? data
    : optimistic.toggleSet(data, unlogged.id, false, unlogged.weight, unlogged.reps)

  const [finishing, setFinishing] = useState(false)

  const live = view.visible_exercises.find((se) => se.id === view.live_id) ?? null

  /** Leave for `url` once every write has landed. Finishing with a set still
   *  on its way used to navigate away from it: the form post won the race and
   *  the set never reached the workout. A pending undo is sent first, and a
   *  write that FAILS while waiting keeps the lifter here, with the banner. */
  const leaveAfterWrites = (url: string) => {
    setFinishing(true)
    const errorBefore = useSaveState.getState().error
    useUndo.getState().commitNow()
    void writesSettled(client, sessionKey(sessionId)).then(() => {
      const error = useSaveState.getState().error
      if (error !== null && error !== errorBefore) {
        setFinishing(false)
        close()
        return
      }
      postNavigate(url)
    })
  }

  const appendSet = (seId: number, weight: number, reps: number) => {
    // add cannot be made idempotent -- a second POST creates a second set --
    // so the lock is what protects it from a double tap. One key per
    // exercise, shared by the confirm button and the sheet's add row.
    const formId = `add-${seId}`
    if (useSaveState.getState().isLocked(formId)) return
    lock(formId)
    addSet.mutateAsync([seId, weight, reps])
      .catch(() => {}) // the banner already says so
      .finally(() => unlock(formId))
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
      if (setId === pendingUnlog) {
        // Re-logging the chip whose un-log is still in its undo window: send
        // the un-log now, so the numbers on the steppers are what lands.
        useUndo.getState().commitNow()
        setPendingUnlog(null)
      }
      toggleSet.mutate([setId, true, weight, reps])
    },
    onToggleSet: (setId, completed) => {
      const owner = data.visible_exercises.find((se) => se.sets.some((s) => s.id === setId))
      const target = owner?.sets.find((s) => s.id === setId)
      if (owner === undefined || target === undefined) return
      if (completed) {
        toggleSet.mutate([setId, true, target.weight, target.reps])
        return
      }
      setPendingUnlog(setId)
      offerUndo({
        label: `Satz ${owner.sets.indexOf(target) + 1} wieder offen.`,
        undo: () => setPendingUnlog(null),
        commit: () => {
          toggleSet.mutateAsync([setId, false, target.weight, target.reps])
            .catch(() => {}) // rolled back and bannered by the mutation layer
            // Cleared once the answer is in the payload, not before -- the
            // chip would flash back to done for the length of the request.
            .finally(() => setPendingUnlog((id) => (id === setId ? null : id)))
        },
      })
    },
    // A POST that redirects to the debrief. This was `window.location.href`
    // -- a GET to a POST-only route, a 405 for everyone -- until 2026-08-11.
    onFinish: () => leaveAfterWrites(`/gym/session/${sessionId}/finish`),
    onDiscard: () => leaveAfterWrites(`/gym/session/${sessionId}/discard`),
    onReorder: (order) => reorder.mutate([order]),
    onSessionMetaSave: (meta) => { sessionMeta.mutate([meta]); close() },
    onSkipRest: () => { skipRest.mutate([]); close() },
    // A navigation, not an in-place write: the invite has its own page.
    // postNavigate carries the csrf_token the hand-built form here forgot,
    // which the blueprint gate has 403'd since it closed.
    onInvite: (partnerId) => postNavigate(
      `/gym/session/${sessionId}/invite`, { partner_id: String(partnerId) }),
    onEnablePush: () => { void enablePush(data.vapid_public_key) },
    onToggleDeload: (on, pct) => { toggleDeload.mutate([on, pct]); close() },
    onAddExercise: (exerciseId) => addExercise.mutate([exerciseId]),
    onSaveTemplate: (name) => postNavigate(
      `/gym/session/${sessionId}/save_as_template`, { template_name: name }),
    exerciseActions: (seId: number): ExerciseSheetActions => ({
      onRestChange: (seconds) => setRest.mutate([seId, seconds]),
      onIncrementChange: (kg) => setIncrement.mutate([seId, kg]),
      // No close(): the flag saves on the tap and the note on blur, both
      // while the sheet stays open.
      onMetaSave: (meta) => exerciseMeta.mutate([seId, meta]),
      onSetUpdate: (setId, weight, reps) => updateSet.mutate([setId, weight, reps]),
      onSetDelete: (setId) => deleteSet.mutate([setId]),
      onAddSet: (weight, reps) => appendSet(seId, weight, reps),
      // In front of the live exercise, which is how the live rule reads a
      // step away from a busy machine (_live_context).
      onMakeLive: () => {
        const order = data.visible_exercises.map((se) => se.id).filter((id) => id !== seId)
        const at = data.live_id === null ? 0 : Math.max(0, order.indexOf(data.live_id))
        order.splice(at, 0, seId)
        reorder.mutate([order])
        close()
      },
      onToggleSkip: () => { toggleSkip.mutate([seId]); close() },
      onReplace: (exerciseId) => { replaceExercise.mutate([seId, exerciseId]); close() },
      onRemove: () => { removeExercise.mutate([seId]); close() },
      onShowProgress: () => {
        const se = data.visible_exercises.find((row) => row.id === seId)
        if (se) window.location.href = `/gym/exercises/${se.exercise_id}`
      },
    }),
  }

  return (
    <SessionPage payload={view} actions={actions} pushSupported={pushSupported}
      confirmBusy={toggleSet.isPending || addSet.isPending}
      finishing={finishing}
      // An add has no optimistic path, so the row is the only place that can
      // say the tap landed. `variables` is the argument tuple of the write
      // still in flight.
      busyExerciseId={addExercise.isPending ? addExercise.variables?.[0] ?? null : null} />
  )
}

/** The key comes from the payload, not a second DOM node: it is already a
 *  field the server serves, and a separate element would be a second place for
 *  it to go missing. Null whenever VAPID is unset in .env. */
async function enablePush(vapidPublicKey: string | null) {
  if (vapidPublicKey === null) return
  const registration = await navigator.serviceWorker.register('/sw.js', { scope: '/gym' })
  const permission = await Notification.requestPermission()
  if (permission !== 'granted') return
  const subscription = await registration.pushManager.subscribe({
    userVisibleOnly: true,
    applicationServerKey: urlBase64ToBytes(vapidPublicKey),
  })
  await fetch('/gym/push/subscribe', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', 'X-CSRF-Token': csrfToken() },
    body: JSON.stringify(subscription.toJSON()),
  })
  usePush.getState().setSubscribed(true)
}

/** The VAPID key is base64url; PushManager wants raw bytes.
 *
 *  Returns ArrayBuffer rather than Uint8Array: applicationServerKey is typed
 *  BufferSource, and a Uint8Array's backing buffer is ArrayBufferLike, which
 *  admits SharedArrayBuffer and so does not satisfy it. */
function urlBase64ToBytes(base64: string): ArrayBuffer {
  const padding = '='.repeat((4 - (base64.length % 4)) % 4)
  const normalised = (base64 + padding).replace(/-/g, '+').replace(/_/g, '/')
  const raw = atob(normalised)
  const bytes = new Uint8Array(new ArrayBuffer(raw.length))
  for (let i = 0; i < raw.length; i += 1) bytes[i] = raw.charCodeAt(i)
  return bytes.buffer
}

export function SessionIsland({ initial }: { initial: SessionDetailPayload }) {
  // One client per island. Retries are off: every one of these writes is a
  // user action with a visible banner and an explicit retry button, and a
  // silent second attempt would be a second POST to routes that are not all
  // idempotent.
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
