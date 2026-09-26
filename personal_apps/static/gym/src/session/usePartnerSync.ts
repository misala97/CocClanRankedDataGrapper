import { useCallback, useEffect, useState } from 'react'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import { fetchSync, sessionKey } from './api'
import { useAnnouncer, usePartnerNotice } from './stores'
import { MutationFailed } from '../api'
import { dismissPartner } from '../partner/api'
import type { PartnerLink, SyncPayload } from '../partner/types'

/** How often the leader asks after a partner line that can still change
 *  (D14: about every ten seconds). */
export const LEADER_POLL_MS = 10_000
/** How often the follower asks: the leader's plan changes land in their own
 *  rows, and the screen has to catch up fast -- as it did before the line. */
export const FOLLOWER_POLL_MS = 5_000

/** A line that can change by itself: an invite may be answered, a partner
 *  is lifting. A declined one waits on the viewer's OK, a finished one on
 *  nothing -- so a screen with only those asks nobody anything. */
function moving(link: PartnerLink): boolean {
  return link.state === 'invited' || link.state === 'joined'
}

/** The poll's interval for these lines, or false: no poll. */
export function pollEvery(links: PartnerLink[], follower: boolean): number | false {
  if (!links.some(moving)) return false
  return follower ? FOLLOWER_POLL_MS : LEADER_POLL_MS
}

export interface PartnerSync {
  links: PartnerLink[]
  /** When these arrived (Date.now()): each rest_left counts down from here. */
  receivedAt: number
  /** The leader's OK on a declined line: gone at once, the row with it. */
  dismiss(id: number): void
}

/**
 * The live screen's partner lines, and the follower's catch-up with the
 * leader's plan -- one poll of sync.json for both.
 *
 * The page's own payload seeds it; after that only sync.json speaks for the
 * lines. A write's answer leaves them out on purpose (routes/workout.py
 * _live_data), so an answer that set off before a poll cannot land after it
 * and put back an older partner.
 *
 * The follower half keeps what useFollowerSync did since 2026-08-11: the
 * leader's structural edits are writes into the follower's own rows, so the
 * page only has to notice the version moved -- then it refetches itself and
 * says so. Only the follower's version ever moves.
 */
export function usePartnerSync(sessionId: number, options: {
  initial: PartnerLink[]
  /** The follower half of a live link (session_is_shared). */
  follower: boolean
  knownVersion: number
}): PartnerSync {
  const { initial, follower, knownVersion } = options
  const client = useQueryClient()
  const announce = useAnnouncer((s) => s.announce)
  const showNotice = usePartnerNotice((s) => s.show)
  const [seededAt] = useState(() => Date.now())
  // A return to the tab, or to the network, asks only what a poll would:
  // a workout without a line that can still change asks nobody anything.
  const asks = (query: { state: { data?: SyncPayload } }) =>
    pollEvery(query.state.data?.partner_links ?? [], follower) !== false

  const { data, dataUpdatedAt } = useQuery({
    queryKey: ['session-sync', sessionId] as const,
    queryFn: () => fetchSync(sessionId),
    initialData: (): SyncPayload => ({
      version: knownVersion, partner_links: initial,
    }),
    // The page's lines are as fresh as the page: the first question waits a
    // full interval, and a return to the tab asks at once only after one.
    initialDataUpdatedAt: seededAt,
    staleTime: FOLLOWER_POLL_MS,
    // refetchIntervalInBackground stays false (the default): a phone in a
    // pocket must not poll. TanStack resumes on focus by itself.
    refetchInterval: (query) => pollEvery(query.state.data?.partner_links ?? [], follower),
    refetchOnWindowFocus: asks,
    refetchOnReconnect: asks,
    gcTime: 0,
  })

  // The leader finished, or the link ended: the line says "Ab jetzt
  // bestimmst du die Reihenfolge", so the page stops following too -- its
  // order, its live row. The session payload says whether it follows
  // (session_is_shared), so it is asked again, once: `follower` turns false
  // when the answer lands, and this with it.
  const following = data.partner_links.some((link) => !link.viewer_leads && link.state === 'joined')
  useEffect(() => {
    if (follower && !following) void client.invalidateQueries({ queryKey: sessionKey(sessionId) })
  }, [follower, following, client, sessionId])

  useEffect(() => {
    if (!follower || data.version === knownVersion) return
    // The version is NOT recorded here -- `knownVersion` comes from the
    // session payload itself, so it advances only once the refetch below
    // actually lands. A locally-tracked "seen" version would mark the page
    // caught up even if this refetch then failed.
    void client.invalidateQueries({ queryKey: sessionKey(sessionId) })
    // The queue changing on its own is the one thing on this screen the
    // lifter did not cause, so it says so rather than moving silently -- to a
    // screen reader through the live region, and to everyone else through the
    // bar PartnerNotice renders (the live region is sr-only text).
    announce('Dein Partner hat den Plan geändert.')
    showNotice()
  }, [data.version, knownVersion, follower, client, sessionId, announce, showNotice])

  // Put away here, not in the cache: a poll already on its way would bring
  // the line back until the next one. An OK that did not arrive brings it
  // back at once, as does one refused because they joined after all (409);
  // one the server has no declined invite for (404: put away already, on the
  // other phone) stays done. Either way sync.json is asked what the line is
  // now -- no poll runs on a screen whose lines are settled -- and a line
  // stays put away only while it still reads declined: asked again from
  // the other phone, the same row comes back as an invite.
  const [gone, setGone] = useState<number[]>([])
  const dismiss = useCallback((id: number) => {
    setGone((ids) => [...ids, id])
    dismissPartner(id).catch((error: unknown) => {
      void client.invalidateQueries({ queryKey: ['session-sync', sessionId] })
      if (error instanceof MutationFailed && error.reason === 'gone') return
      setGone((ids) => ids.filter((x) => x !== id))
    })
  }, [client, sessionId])

  return {
    links: data.partner_links.filter(
      (link) => !(link.state === 'declined' && gone.includes(link.id))),
    receivedAt: dataUpdatedAt,
    dismiss,
  }
}
