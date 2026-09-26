import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import { fetchSync, sessionKey } from './api'
import { useAnnouncer, usePartnerNotice } from './stores'
import { MutationFailed } from '../api'
import { dismissPartner, endPartner, withdrawInvite } from '../partner/api'
import type { PartnerLink, ShownLink, SyncPayload } from '../partner/types'
import { FOOT_FAILED, lineWords } from '../partner/words'

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

/** Whether a return to the tab, or to the network, asks after these lines:
 *  what a poll asks after, and an ended line too -- it turns finished when
 *  the partner finishes, or goes with their workout thrown away: too seldom
 *  to poll for, not never (B11). */
function worthAsking(links: PartnerLink[]): boolean {
  return links.some((link) => moving(link) || link.state === 'ended')
}

/** What became of a request from the partner sheet's foot: done (the server
 *  did it, or answered that it can't any more -- the line now says what is
 *  so), or not through, with what to say. */
export type FootOutcome = { done: true } | { done: false; message: string }

export interface PartnerSync {
  links: ShownLink[]
  /** When these arrived (Date.now()): each rest_left counts down from here. */
  receivedAt: number
  /** The leader's OK on a declined line: gone at once, the row with it. */
  dismiss(id: number): void
  /** "Einladung zurückziehen": the line goes at once (B11). */
  withdraw(id: number): Promise<FootOutcome>
  /** "Gemeinsames Training beenden" / "Nicht mehr mitmachen" (B11). */
  end(id: number): Promise<FootOutcome>
}

/** The lines the partner was training in whose link went between two
 *  answers, as vanished. */
function wentFrom(before: PartnerLink[], now: PartnerLink[]): ShownLink[] {
  return before
    .filter((line) => (line.state === 'joined' || line.state === 'ended')
      && !now.some((l) => l.id === line.id))
    .map((line): ShownLink => ({ ...line, state: 'vanished' }))
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
  // A return to the tab, or to the network, asks after every line that can
  // still change (worthAsking): a workout without one asks nobody anything.
  const asks = (query: { state: { data?: SyncPayload } }) =>
    worthAsking(query.state.data?.partner_links ?? [])

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

  // The sheet's foot (B11). Its answer is waited for: the line changes when
  // sync.json says so, asked at once. A 404 or a 409 is an answer too -- it
  // ended or went already, they joined after all -- and the line then says
  // what is so. Only a request that did not get through is the sheet's to
  // say, and to send again.
  const outcomeOf = useCallback(async (send: Promise<unknown>): Promise<FootOutcome> => {
    try {
      await send
    } catch (error: unknown) {
      if (!(error instanceof MutationFailed)
          || (error.reason !== 'gone' && error.reason !== 'finished')) {
        return {
          done: false,
          message: error instanceof MutationFailed && error.needsReload
            ? error.germanMessage : FOOT_FAILED,
        }
      }
    }
    void client.invalidateQueries({ queryKey: ['session-sync', sessionId] })
    return { done: true }
  }, [client, sessionId])

  // A withdrawn invite goes at once, as an OK'd one does -- as an invite
  // only: a line put away with its OK may come back as one, asked again
  // from the other phone. It comes back if the request did not get through.
  const [withdrawn, setWithdrawn] = useState<number[]>([])
  const withdraw = useCallback(async (id: number) => {
    setWithdrawn((ids) => [...ids, id])
    const outcome = await outcomeOf(withdrawInvite(id))
    if (!outcome.done) setWithdrawn((ids) => ids.filter((x) => x !== id))
    return outcome
  }, [outcomeOf])

  const end = useCallback((id: number) => outcomeOf(endPartner(id)), [outcomeOf])

  // A line the partner was training in whose link went -- a workout thrown
  // away deletes it -- stays, said as vanished, for the rest of the page:
  // the follower's order turned theirs, and a line gone without a word
  // would not say why. Kept while rendering, not after: a line gone for one
  // frame would move everything under it by its 52 px. It goes for good
  // once its partner is back on a line of their own -- asked again from the
  // other phone: a new link, a newer id -- whatever becomes of that one; not
  // for a line of theirs older than it (one that finished before they were
  // asked back). A partner is on one joined or ended line at a time, so two
  // of their lines never vanish together.
  const [trail, setTrail] = useState(() => ({
    links: data.partner_links, vanished: [] as ShownLink[],
  }))
  let { vanished } = trail
  if (trail.links !== data.partner_links) {
    const now = data.partner_links
    vanished = [...vanished, ...wentFrom(trail.links, now)].filter((line) =>
      !now.some((link) => link.username === line.username && link.id >= line.id))
    setTrail({ links: now, vanished })
  }

  // And a line that stops being joined is said aloud: for a follower the
  // order turned theirs under their thumb.
  const seen = useRef(data.partner_links)
  useEffect(() => {
    const before = seen.current
    const now = data.partner_links
    if (before === now) return
    seen.current = now
    const over = now.filter((line) => (line.state === 'ended' || line.state === 'finished')
      && before.some((b) => b.id === line.id && b.state === 'joined'))
    const said = [...over, ...wentFrom(before, now)]
      .map((line) => `${lineWords(line, false).spoken}.`)
    if (said.length > 0) announce(said.join(' '))
  }, [data.partner_links, announce])

  const links = useMemo(() => [
    ...data.partner_links.filter((link) => !(link.state === 'declined' && gone.includes(link.id))
      && !(link.state === 'invited' && withdrawn.includes(link.id))),
    ...vanished,
  ].sort((a, b) => a.id - b.id), [data.partner_links, gone, withdrawn, vanished])

  return { links, receivedAt: dataUpdatedAt, dismiss, withdraw, end }
}
