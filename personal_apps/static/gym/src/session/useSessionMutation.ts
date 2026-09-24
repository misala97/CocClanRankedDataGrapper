import { useId } from 'react'
import { useMutation, useQueryClient } from '@tanstack/react-query'
import type { SessionDetailPayload } from './types'
import { fetchSession, MutationFailed } from './api'
import { useSaveState } from './stores'

export const sessionKey = (sessionId: number) => ['session', sessionId] as const

/** How one kind of write's failures are told apart and offered again. */
export interface WriteOptions<Args extends unknown[]> {
  /** Which earlier failure a success answers (G-139). By default the row the
   *  write names first, for this hook alone. A write that states the whole of
   *  something -- the exercise order, the deload mark, a field of the workout
   *  -- names that, so its newest intent answers the older failure whose
   *  retry would put back what the lifter had already changed. A name is the
   *  workout's, not the hook's: every write naming 'set-4' answers it, and
   *  one naming 'set-4' answers 'set-4:done' too (stores.succeed). null:
   *  every call is new work -- an added set -- and answers only itself (B4
   *  review). */
  key?: (...args: Args) => string | null
  /** About this moment only, like the rest countdown: a failure is reported
   *  but never sent again -- a minute later "+15 s" moves a different rest. */
  ephemeral?: boolean
  /** false: sent twice, it is done twice -- an added set or exercise, a swap,
   *  the skip toggle. Its answer can be lost after it landed, so a failure
   *  is sent again only on the lifter's tap (Remedy 'manual'), never by the
   *  connection coming back or by finishing (B4 re-review). */
  idempotent?: boolean
}

let calls = 0

/**
 * Every write goes through here, so the optimistic path exists in exactly one
 * place.
 *
 * onMutate applies the change locally and returns the snapshot; onError puts
 * the snapshot back and raises the banner with a retry bound to the same
 * arguments. That pair is the whole reason TanStack Query is in the stack --
 * `performMutation` in the old screen hand-rolled the timeout, the in-flight
 * count and the retry, and rebuilding that by hand in React would repeat the
 * mistake this port exists to undo.
 *
 * `optimistic` is optional. A write whose local effect cannot be computed
 * honestly -- replacing an exercise, adding one -- simply does not supply it
 * and waits for the server. Guessing there would show a screen that is
 * briefly a lie, which is worse than one that is briefly slow.
 */
export function useSessionMutation<Args extends unknown[]>(
  sessionId: number,
  run: (...args: Args) => Promise<SessionDetailPayload>,
  optimistic?: (current: SessionDetailPayload, ...args: Args) => SessionDetailPayload,
  options: WriteOptions<Args> = {},
) {
  const client = useQueryClient()
  const key = sessionKey(sessionId)
  const begin = useSaveState((s) => s.begin)
  const end = useSaveState((s) => s.end)
  const succeed = useSaveState((s) => s.succeed)
  const fail = useSaveState((s) => s.fail)
  // Which write a failure belongs to: this hook (the kind of write) and what
  // it names (WriteOptions.key). A success answers only its own write's
  // failure -- ticking set 2 does not save the lost weight of set 1 (G-139).
  const writer = useId()
  const writeKey = (args: Args) => {
    if (options.key === undefined) return `${writer}:${JSON.stringify(args[0] ?? null)}`
    return options.key(...args) ?? `${writer}:call-${++calls}`
  }

  /** A 409 or a 404 to the live screen: it wrote to something the server
   *  no longer has. Which of three things happened, only the server knows,
   *  so ask it. The workout finished -- on the other phone, or by the
   *  three-hour rule: its page is the debrief now, a reload shows it. It is
   *  gone -- discarded: home. Still running: the write aimed at a row that
   *  is gone -- a resent delete that had landed after all, a set the
   *  partner's plan removed -- and is moot, not failed. Reloading for that
   *  threw away whatever the lifter was typing (B4 re-review). */
  const settleStale = async (failureKey: string) => {
    try {
      const fresh = await client.fetchQuery({
        queryKey: key, queryFn: () => fetchSession(sessionId), staleTime: 0,
      })
      if (fresh.session.finished_at !== null) window.location.reload()
      else succeed(failureKey)
    } catch (error) {
      if (error instanceof MutationFailed && error.reason === 'gone') window.location.assign('/gym')
      else window.location.reload()
    }
  }

  const mutation = useMutation<
    SessionDetailPayload, MutationFailed, Args,
    { previous?: SessionDetailPayload; failureKey: string }
  >({
    mutationFn: (args) => run(...args),

    // One write to a workout at a time, in the order they were made. Every
    // mutation on this session shares the scope, so TanStack queues them:
    // onMutate (the optimistic guess) still runs the moment the lifter acts,
    // and only the request waits its turn. Unscoped, two drops in quick
    // succession -- or the arrow-key path, a POST per key press -- reached the
    // server together; each read the same rows and wrote its own half, and the
    // queue came back as a blend of both orders. The server serialises now too
    // (features/gym/locking.py), but it cannot know which drop came second.
    mutationKey: key,
    scope: { id: `session-${sessionId}` },

    onMutate: async (args) => {
      begin()
      // Named once per call: a key that is new for every call has to be the
      // same one when its answer comes back.
      const failureKey = writeKey(args)
      // Stop an in-flight refetch from landing on top of the optimistic state
      // and undoing it a moment before the server answers.
      await client.cancelQueries({ queryKey: key })
      const previous = client.getQueryData<SessionDetailPayload>(key)
      if (optimistic && previous !== undefined) {
        client.setQueryData(key, optimistic(previous, ...args))
      }
      return { previous, failureKey }
    },

    onSuccess: (fresh, args, result) => {
      // The server recomputes which exercise is live on every write, so its
      // answer replaces the local guess wholesale rather than merging into it
      // -- unless a LATER write is already queued behind this one. That write
      // has drawn its guess on top of this one's, and this answer describes
      // the workout from before it: applied, it put the row the lifter had
      // just dropped back where it came from for a whole round trip, then
      // moved it again. The last write's answer carries everything, since the
      // server saw them in order. (This mutation still counts as in flight
      // here -- it settles after onSuccess -- hence more than ONE.)
      if (client.isMutating({ mutationKey: key }) <= 1) {
        client.setQueryData(key, fresh)
      }
      // Here, not in onSettled: onSettled also runs after a FAILURE, so
      // clearing there erased the banner the failure had just raised.
      succeed(result?.failureKey ?? writeKey(args))
    },

    onError: (error, args, context) => {
      const failureKey = context?.failureKey ?? writeKey(args)
      // The server no longer has what this screen wrote to: nothing to
      // retry, and whether anything is wrong at all is the server's to say.
      if (error.reason === 'finished' || error.reason === 'gone') {
        void settleStale(failureKey)
        return
      }
      if (context?.previous !== undefined) {
        client.setQueryData(key, context.previous)
      }
      // `previous` is the screen from before THIS write, which can still hold
      // an earlier write's guess whose answer was skipped above. Only the
      // server knows what is stored, so ask -- quietly; if the network is what
      // failed, the snapshot stays and the banner already says so.
      void client.invalidateQueries({ queryKey: key })
      // A stale CSRF token or a lapsed login cannot be retried into working
      // -- the only fix is a fresh page (a fresh token, or the login page), so
      // that is what the retry does for them. A refused value has no retry at
      // all: sending it again gets the same refusal.
      if (error.needsReload) {
        fail(failureKey, error.germanMessage, () => { window.location.reload() }, 'reload')
        return
      }
      const resend = error.retryable && !options.ephemeral
        ? () => { mutation.mutate(args) } : null
      fail(failureKey, error.germanMessage, resend,
        resend !== null && options.idempotent === false ? 'manual' : 'auto')
    },

    onSettled: () => { end() },
  })

  return mutation
}
