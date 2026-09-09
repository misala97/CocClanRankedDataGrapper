// Shared server state for the hub.
//
// One cache for the whole page, so Overview, Human chatter and Watching read
// the same board rather than each fetching one -- three views of one answer,
// which is also why they can never disagree with each other on screen.
//
// The keys are the load-bearing part. A key that held only the market would
// serve a reader the board built for a different window, sort or source set:
// silently, and only sometimes. Every dimension the server filters on is in
// the key, and the panel's key carries the listing context that opened it,
// because its breakdown and posts describe the same window the row's phrase
// did.
import { keepPreviousData, useQuery } from '@tanstack/react-query'

import { fetchBoard, fetchDetail, fetchSearch, queryFor } from '../api'
import type { BoardPayload, PanelSpan, Selection } from '../types'

/** Every hub key starts here, so the hub and the old board island can share a
 *  browser tab without sharing a cache entry. */
const ROOT = 'radar-hub'

/** Boards and panels are refreshed while their page is on screen, and only
 *  then. A hidden tab polling a dashboard nobody is reading is a request the
 *  reader did not ask for. */
export const REFRESH_MS = 60_000

export const boardKey = (s: Selection) => [ROOT, 'board', queryFor(s)] as const

export const detailKey = (ticker: string, s: Selection, span: PanelSpan) =>
  [ROOT, 'detail', ticker, s.market, s.sources.join(','), s.window, span] as const

export const searchKey = (q: string) => [ROOT, 'search', q.trim()] as const

/** The Selection a board payload was built for, from the server's own echo.
 *
 *  Read from the echo rather than from the URL: the server has already parsed
 *  and validated it, and a second parser would be free to disagree.
 */
export function selectionOf(payload: BoardPayload): Selection {
  return {
    market: payload.market,
    sources: payload.sources,
    segments: payload.segments,
    minVenues: payload.min_venues,
    window: payload.window_hours,
    sort: payload.sort,
    dir: payload.dir,
  }
}

/** Permanent for this attempt: retrying spends the reader's time on the same
 *  answer. A forbidden endpoint will not become allowed, an expired session
 *  will not revive, and a ticker the server does not have will not appear. */
const PERMANENT = new Set(['session', 'forbidden', 'missing'])

function retry(count: number, error: unknown): boolean {
  const reason = (error as { reason?: string })?.reason
  if (reason !== undefined && PERMANENT.has(reason)) return false
  return count < 2
}

export function useBoard(selection: Selection, initial?: BoardPayload,
                         visible = true) {
  // The embedded board seeds only the key it was actually built for. Handing
  // it to another key would present a board built under one filter as the
  // answer to a different one -- as real data, with a fresh timestamp, once,
  // on arrival, and then silently replaced a minute later. Enforced here
  // rather than asked of every caller.
  const seed = initial && queryFor(selectionOf(initial)) === queryFor(selection)
    ? initial : undefined
  return useQuery({
    queryKey: boardKey(selection),
    queryFn: ({ signal }) => fetchBoard(selection, signal),
    initialData: seed,
    // The embedded board is fresh when the document is. Without this the
    // seeded page immediately refetches the board the server just rendered
    // into it, which is the self-inflicted wait the embed exists to avoid.
    staleTime: REFRESH_MS,
    refetchInterval: visible ? REFRESH_MS : false,
    refetchIntervalInBackground: false,
    // Governs a KEY CHANGE: the previous board stays on screen while the one
    // for a new filter loads. Surviving a failed REFRESH is separate, and is
    // react-query keeping `data` while `status` turns to error -- which is
    // what StaleNotice renders beside.
    placeholderData: keepPreviousData,
    retry,
  })
}

export function useDetail(ticker: string | null, selection: Selection,
                          span: PanelSpan, visible = true) {
  return useQuery({
    queryKey: detailKey(ticker ?? '', selection, span),
    queryFn: ({ signal }) => fetchDetail(ticker as string, selection, span, signal),
    enabled: Boolean(ticker),
    refetchInterval: visible ? REFRESH_MS : false,
    refetchIntervalInBackground: false,
    placeholderData: keepPreviousData,
    retry,
  })
}

/** The universe, not the current board: a reader searching for a company that
 *  nobody is discussing today still expects to find it. */
export function useSearch(query: string) {
  const trimmed = query.trim()
  return useQuery({
    queryKey: searchKey(trimmed),
    queryFn: ({ signal }) => fetchSearch(trimmed, signal),
    enabled: trimmed.length > 0,
    // A universe match does not go stale in the seconds a reader spends
    // choosing one, and re-asking on every keystroke's remount would.
    staleTime: 30_000,
    placeholderData: keepPreviousData,
    retry,
  })
}
