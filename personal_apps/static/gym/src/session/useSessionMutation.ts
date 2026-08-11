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
  const fail = useSaveState((s) => s.fail)

  const mutation = useMutation<
    SessionDetailPayload, MutationFailed, Args, { previous?: SessionDetailPayload }
  >({
    mutationFn: (args) => run(...args),

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
      // answer replaces the local guess wholesale rather than merging into it.
      client.setQueryData(key, fresh)
    },

    onError: (error, args, context) => {
      if (context?.previous !== undefined) {
        client.setQueryData(key, context.previous)
      }
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
