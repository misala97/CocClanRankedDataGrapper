// Cache identity and lifecycle for the Analysis page (HA1).
//
// Its own keys, its own lifetimes, and no polling: a retrospective window of
// completed days does not change while the reader looks at it, and nothing
// here asks again on its own. The key names everything the answer depends
// on -- both IDs, the ticker they were resolved from, both dates and the
// schema version -- so an answer for one identity can never stand under
// another's heading, and a stale link's old IDs never share a cache entry
// with today's.
import { useQuery } from '@tanstack/react-query'

import { fetchAnalysis, fetchAnalysisResolve } from './analysisApi'
import type { Range } from './analysisTypes'
import { SCHEMA_VERSION } from './analysisTypes'

const ROOT = 'radar-hub'

/** A minute: the same figure the board uses for "current enough". Past it a
 *  remount asks again; before it, Back and forward render from the cache. */
export const ANALYSIS_STALE_MS = 60_000
/** Five minutes: how long an answer nobody is looking at is kept. */
export const ANALYSIS_GC_MS = 5 * 60_000

export const analysisKey = (companyId: number, instrumentId: number, ticker: string,
                            range: Range) =>
  [ROOT, 'analysis', `v${SCHEMA_VERSION}`, companyId, instrumentId, ticker,
    range.from, range.to] as const

export const resolveKey = (ticker: string) =>
  [ROOT, 'analysis-resolve', `v${SCHEMA_VERSION}`, ticker] as const

/** A resolution nobody is looking at is dropped at once: it is only ever
 *  the input to one pin, and a kept one is a stale mapping in waiting. */
export const ANALYSIS_RESOLVE_GC_MS = 0

/** Resolve a ticker to the current company/instrument IDs. Short-lived on
 *  purpose: it is what "look this up again" means. The page pins only an
 *  answer fetched after it asked (isFetchedAfterMount), never a cached one. */
export function useAnalysisResolve(ticker: string | null) {
  return useQuery({
    queryKey: resolveKey(ticker ?? ''),
    queryFn: ({ signal }) => fetchAnalysisResolve(ticker as string, signal),
    enabled: ticker !== null,
    staleTime: 0,
    gcTime: ANALYSIS_RESOLVE_GC_MS,
    retry: false,
    refetchOnWindowFocus: false,
    refetchOnReconnect: false,
    refetchInterval: false,
  })
}

/** The daily series for a pinned identity and window.
 *
 *  No placeholder data: the previous window's or previous company's series
 *  under this one's labels is exactly what the identity contract forbids.
 *  No retry: a refused identity will not become accepted, and a timed-out
 *  read is the reader's to send again. */
export function useAnalysis(companyId: number | null, instrumentId: number | null,
                            ticker: string | null, range: Range | null) {
  const ready = companyId !== null && instrumentId !== null && ticker !== null
    && range !== null
  return useQuery({
    queryKey: analysisKey(companyId ?? 0, instrumentId ?? 0, ticker ?? '',
                          range ?? { from: '', to: '' }),
    queryFn: ({ signal }) => fetchAnalysis(
      companyId as number, instrumentId as number, range as Range, signal),
    enabled: ready,
    staleTime: ANALYSIS_STALE_MS,
    gcTime: ANALYSIS_GC_MS,
    retry: false,
    refetchOnWindowFocus: false,
    refetchOnReconnect: false,
    refetchInterval: false,
  })
}
