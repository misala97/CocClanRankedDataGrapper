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

export const searchKey = (q: string) => [ROOT, 'search', q] as const

/** An expired session and a forbidden endpoint are both permanent for this
 *  attempt: retrying either just spends the reader's time on the same answer.
 *  Everything else gets the default retries. */
function retry(count: number, error: unknown): boolean {
  const reason = (error as { reason?: string })?.reason
  if (reason === 'session' || reason === 'forbidden') return false
  return count < 2
}

export function useBoard(selection: Selection, initial?: BoardPayload,
                         visible = true) {
  return useQuery({
    queryKey: boardKey(selection),
    queryFn: ({ signal }) => fetchBoard(selection, signal),
    // The embedded board seeds only the selection it was built for. Handing it
    // to a different key would show the reader a board under a filter they
    // never chose.
    initialData: initial,
    refetchInterval: visible ? REFRESH_MS : false,
    refetchIntervalInBackground: false,
    // The previous board stays on screen through a failed refresh. Data that
    // was true a minute ago is worth more than an empty page, as long as the
    // surface says when it was true and that the refresh failed.
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
  return useQuery({
    queryKey: searchKey(query),
    queryFn: ({ signal }) => fetchSearch(query, signal),
    enabled: query.trim().length > 0,
    // A universe match does not go stale in the seconds a reader spends
    // choosing one, and re-asking on every keystroke's remount would.
    staleTime: 30_000,
    placeholderData: keepPreviousData,
    retry,
  })
}
