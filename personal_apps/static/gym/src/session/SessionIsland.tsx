import { useEffect } from 'react'
import { QueryClient, QueryClientProvider, useQuery } from '@tanstack/react-query'
import type { SessionDetailPayload } from './types'
import { api, fetchSession } from './api'
import { sessionKey, useSessionMutation } from './useSessionMutation'
import * as optimistic from './optimistic'
import { usePush, useSaveState, useSheets } from './stores'
import { useWakeLock } from './useWakeLock'
import { SessionPage, type SessionActions } from './SessionPage'
import type { ExerciseSheetActions } from './components/ExerciseSheet'

const pushSupported = 'serviceWorker' in navigator && 'PushManager' in window

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

  // The screen stays on for as long as the workout is live -- this island
  // only ever renders an unfinished session, so the flag is simply true.
  useWakeLock(true)

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

  // Only the browser knows whether THIS device is subscribed -- a subscription
  // is a browser endpoint, one per device, so a server-side answer hid the
  // button on every other device the same person owns. Probed once and cached,
  // never re-asked on every render.
  const setSubscribed = usePush((s) => s.setSubscribed)
  useEffect(() => {
    if (!pushSupported) { setSubscribed(false); return }
    navigator.serviceWorker.getRegistration('/gym')
      .then((registration) => registration?.pushManager.getSubscription() ?? null)
      .then((subscription) => setSubscribed(subscription !== null))
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

  // No optimistic entry: each of these moves which exercise is live, and that
  // decision belongs to the server.
  const addExercise = useSessionMutation(sessionId,
    (exerciseId: number) => api.addExercise(sessionId, exerciseId))
  const createExercise = useSessionMutation(sessionId,
    (name: string) => api.createExercise(sessionId, name))
  const removeExercise = useSessionMutation(sessionId,
    (seId: number) => api.removeExercise(seId))
  const replaceExercise = useSessionMutation(sessionId,
    (seId: number, exerciseId: number) => api.replaceExercise(seId, exerciseId))
  const replaceWithNew = useSessionMutation(sessionId,
    (seId: number, name: string) => api.replaceWithNew(seId, name))

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

  const live = data.visible_exercises.find((se) => se.id === data.live_id) ?? null
  const nextSet = live?.sets.find((s) => !s.completed) ?? null

  const actions: SessionActions = {
    onConfirmSet: (weight, reps) => {
      if (live === null) return
      // The pending set is confirmed; with nothing pending, gym_add_set
      // creates one already completed -- which is what "Satz geschafft" means
      // everywhere else on this screen. Only the endpoint differs.
      if (nextSet !== null) {
        toggleSet.mutate([nextSet.id, true, weight, reps])
      } else {
        // add cannot be made idempotent -- a second POST creates a second set
        // -- so the lock is what protects it from a double tap.
        const formId = `add-${live.id}`
        if (useSaveState.getState().isLocked(formId)) return
        lock(formId)
        addSet.mutateAsync([live.id, weight, reps]).finally(() => unlock(formId))
      }
    },
    onToggleSet: (setId, completed) => {
      const target = data.visible_exercises
        .flatMap((se) => se.sets).find((s) => s.id === setId)
      if (target === undefined) return
      toggleSet.mutate([setId, completed, target.weight, target.reps])
    },
    onFinish: () => { window.location.href = `/gym/session/${sessionId}/finish` },
    onSessionMetaSave: (meta) => { sessionMeta.mutate([meta]); close() },
    onSkipRest: () => { skipRest.mutate([]); close() },
    onInvite: (partnerId) => {
      // A navigation, not an in-place write: the invite has its own page.
      const form = document.createElement('form')
      form.method = 'post'
      form.action = `/gym/session/${sessionId}/invite`
      const field = document.createElement('input')
      field.name = 'partner_id'
      field.value = String(partnerId)
      form.append(field)
      document.body.append(form)
      form.submit()
    },
    onEnablePush: () => { void enablePush(data.vapid_public_key) },
    onToggleDeload: (on, pct) => { toggleDeload.mutate([on, pct]); close() },
    onAddExercise: (exerciseId) => addExercise.mutate([exerciseId]),
    onCreateExercise: (name) => createExercise.mutate([name]),
    onSaveTemplate: (name) => {
      const form = document.createElement('form')
      form.method = 'post'
      form.action = `/gym/session/${sessionId}/save_as_template`
      const field = document.createElement('input')
      field.name = 'template_name'
      field.value = name
      form.append(field)
      document.body.append(form)
      form.submit()
    },
    exerciseActions: (seId: number): ExerciseSheetActions => ({
      onRestChange: (seconds) => setRest.mutate([seId, seconds]),
      onIncrementChange: (kg) => setIncrement.mutate([seId, kg]),
      onMetaSave: (meta) => { exerciseMeta.mutate([seId, meta]); close() },
      onSetUpdate: (setId, weight, reps) => updateSet.mutate([setId, weight, reps]),
      onSetDelete: (setId) => deleteSet.mutate([setId]),
      onAddSet: (weight, reps) => addSet.mutate([seId, weight, reps]),
      onToggleSkip: () => { toggleSkip.mutate([seId]); close() },
      onReplace: (exerciseId) => { replaceExercise.mutate([seId, exerciseId]); close() },
      onReplaceWithNew: (name) => { replaceWithNew.mutate([seId, name]); close() },
      onRemove: () => { removeExercise.mutate([seId]); close() },
      onShowProgress: () => {
        const se = data.visible_exercises.find((row) => row.id === seId)
        if (se) window.location.href = `/gym/exercises/${se.exercise_id}`
      },
    }),
  }

  return (
    <SessionPage payload={data} actions={actions} pushSupported={pushSupported}
      busySetId={toggleSet.isPending ? (nextSet?.id ?? null) : null} />
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
    headers: { 'Content-Type': 'application/json' },
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
  const [client] = [new QueryClient({
    defaultOptions: { mutations: { retry: false }, queries: { retry: false } },
  })]

  return (
    <QueryClientProvider client={client}>
      <SessionIslandInner initial={initial} />
    </QueryClientProvider>
  )
}
