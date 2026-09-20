import { useMutation, useQueryClient } from '@tanstack/react-query'
import type { SessionDetailPayload } from './types'
import { MutationFailed } from './api'
import { useSaveState } from './stores'

export const sessionKey = (sessionId: number) => ['session', sessionId] as const

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
) {
  const client = useQueryClient()
  const key = sessionKey(sessionId)
  const begin = useSaveState((s) => s.begin)
  const end = useSaveState((s) => s.end)
  const succeed = useSaveState((s) => s.succeed)
  const fail = useSaveState((s) => s.fail)

  const mutation = useMutation<
    SessionDetailPayload, MutationFailed, Args, { previous?: SessionDetailPayload }
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
      // Stop an in-flight refetch from landing on top of the optimistic state
      // and undoing it a moment before the server answers.
      await client.cancelQueries({ queryKey: key })
      const previous = client.getQueryData<SessionDetailPayload>(key)
      if (optimistic && previous !== undefined) {
        client.setQueryData(key, optimistic(previous, ...args))
      }
      return { previous }
    },

    onSuccess: (fresh) => {
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
      succeed()
    },

    onError: (error, args, context) => {
      if (context?.previous !== undefined) {
        client.setQueryData(key, context.previous)
      }
      // `previous` is the screen from before THIS write, which can still hold
      // an earlier write's guess whose answer was skipped above. Only the
      // server knows what is stored, so ask -- quietly; if the network is what
      // failed, the snapshot stays and the banner already says so.
      void client.invalidateQueries({ queryKey: key })
      // A stale CSRF token cannot be retried into working -- the only fix is
      // a fresh page (which mints a fresh token), so that is what the retry
      // does for it.
      fail(error.germanMessage, error.reason === 'forbidden'
        ? () => { window.location.reload() }
        : () => { mutation.mutate(args) })
    },

    onSettled: () => { end() },
  })

  return mutation
}
