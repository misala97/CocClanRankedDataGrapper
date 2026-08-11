import { useEffect, useState } from 'react'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import { fetchSync } from './api'
import { sessionKey } from './useSessionMutation'
import { useAnnouncer } from './stores'

/** How often the follower asks whether the plan moved. The leader's edit is
 *  already committed to the follower's own rows by then, so this is a cheap
 *  version check, not a data transfer. */
const POLL_MS = 5000

/**
 * The follower's page keeps up with the leader's structural changes.
 *
 * Only the FOLLOWER polls: `structure_version` is bumped by
 * reconcile_follower and only ever on the follower's session, so a leader
 * asking would burn a request every five seconds for a number that cannot
 * change. `session_is_shared` is already computed that way server-side.
 *
 * The Jinja version of this fetched a queue partial and swapped it into the
 * DOM, which is why it needed to re-arm drag handles, hunt for a missing
 * <dialog>, and reload the page when the open exercise vanished. None of that
 * survives here: a structural change invalidates the session query and the
 * whole island re-renders from one fresh payload -- an exercise that is gone
 * is simply not in it, and every sheet is rendered from that same list.
 *
 * It went missing entirely in the React port (the poll was deleted with the
 * 953 lines of imperative JS and never rebuilt), so between 2026-08-10 and
 * 2026-08-11 a follower saw the leader's changes only after a manual reload.
 */
export function useFollowerSync(sessionId: number, options: {
  enabled: boolean
  knownVersion: number
}) {
  const { enabled, knownVersion } = options
  const client = useQueryClient()
  const announce = useAnnouncer((s) => s.announce)
  // Sharing ends by stamping SharedSession.ended_at, which never touches
  // structure_version -- so "the link is over" has to be its own signal or
  // the page would poll forever after the leader finishes.
  const [linkLive, setLinkLive] = useState(true)

  const { data } = useQuery({
    queryKey: ['session-sync', sessionId] as const,
    queryFn: () => fetchSync(sessionId),
    enabled: enabled && linkLive,
    // refetchIntervalInBackground stays false (the default): a phone in a
    // pocket must not poll. TanStack resumes on focus by itself.
    refetchInterval: POLL_MS,
    gcTime: 0,
  })

  useEffect(() => {
    if (data === undefined) return
    if (!data.shared) { setLinkLive(false); return }
    if (data.version === knownVersion) return
    // The version is NOT recorded here -- `knownVersion` comes from the
    // session payload itself, so it advances only once the refetch below
    // actually lands. A locally-tracked "seen" version would mark the page
    // caught up even if this refetch then failed.
    void client.invalidateQueries({ queryKey: sessionKey(sessionId) })
    // The queue changing on its own is the one thing on this screen the
    // lifter did not cause, so it says so rather than moving silently.
    announce('Dein Partner hat den Plan geändert.')
  }, [data, knownVersion, client, sessionId, announce])
}
