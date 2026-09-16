// Test fixtures for the selected-session chart. Synthetic: hand-written to
// exercise gaps, provisional bars, unknown versus zero counts and partial
// coverage, in the shape the server's contract emits.
import type { PriceChartResponse, PricePoint, PriceSeries } from './priceChart'

const DAY = '2026-09-15'
const YAHOO_REGIME = 'yahoo_chart:provider_bar_close:unknown'
/** The hard segment these fixture bars sit in: the window is entirely
 *  pre-market, so every bar shares one market state and one regime. */
export const PREMARKET = `premarket:${DAY}|${YAHOO_REGIME}`

export function bar(hhmm: string, value: number | null,
                    { breakBefore = false, provisional = false, at, segment = PREMARKET,
                      regime = YAHOO_REGIME }:
                    { breakBefore?: boolean; provisional?: boolean; at?: string
                      segment?: string; regime?: string } = {}): PricePoint {
  const start = `${DAY}T${hhmm}:00Z`
  const end = new Date(Date.parse(start) + 60_000).toISOString().replace('.000Z', 'Z')
  return { at: provisional && at ? `${DAY}T${at}Z` : end, start, end, value,
           provisional, break_before: breakBefore, regime, segment }
}

export const counted = (points: PricePoint[]) => points.filter((p) => p.value !== null).length

export function yahooPrice(over: Partial<PriceSeries> = {}): PriceSeries {
  const points = over.points ?? [
    bar('08:00', 100), bar('08:01', 101), bar('08:02', null, { breakBefore: true }),
    bar('08:03', 102, { breakBefore: true }), bar('08:04', 101.5),
    bar('09:06', 103, { breakBefore: true, provisional: true, at: '09:06:30' }),
  ]
  return {
    source: 'yahoo_chart', kind: 'bar_close', currency: 'USD', mic: 'XNMS',
    price_basis: 'provider_bar_close', adjustment_basis: 'unknown',
    regimes: [{ id: YAHOO_REGIME, source: 'yahoo_chart',
                price_basis: 'provider_bar_close', adjustment_basis: 'unknown' }],
    received_at: `${DAY}T09:06:30Z`, cache_age_seconds: 30,
    latest_observation_at: `${DAY}T09:06:30Z`, stale: false, fallback: false,
    interval_seconds: 60, observations: counted(points), expected_intervals: 67,
    ...over,
    points,
  }
}

const ALPACA_REGIME = 'alpaca_sip:provider_bar_close:raw'

/** A delayed consolidated-SIP series: raw closes, one hard segment, gaps left
 *  as gaps. `minutes` are offsets from 08:00Z, so a caller can make the
 *  sparse FT-like shape or a dense one. */
export function alpacaPrice(minutes: number[], over: Partial<PriceSeries> = {}): PriceSeries {
  const clock = (minute: number) =>
    `${String(8 + Math.floor(minute / 60)).padStart(2, '0')}:${String(minute % 60).padStart(2, '0')}`
  const points = minutes.map((minute, index) => bar(clock(minute), 7.4 + (index % 7) * 0.01, {
    breakBefore: index > 0 && minute - minutes[index - 1]! !== 1,
    segment: `premarket:${DAY}|${ALPACA_REGIME}`, regime: ALPACA_REGIME,
  }))
  return {
    source: 'alpaca_sip', kind: 'bar_close', currency: 'USD', mic: 'XNMS',
    price_basis: 'provider_bar_close', adjustment_basis: 'raw',
    regimes: [{ id: ALPACA_REGIME, source: 'alpaca_sip',
                price_basis: 'provider_bar_close', adjustment_basis: 'raw' }],
    received_at: `${DAY}T09:07:00Z`, cache_age_seconds: 12,
    latest_observation_at: points[points.length - 1]?.at ?? null, stale: false, fallback: false,
    interval_seconds: 60, observations: counted(points), expected_intervals: 67,
    ...over,
    points,
  }
}

export function priceChartResponse(over: Partial<PriceChartResponse> = {},
                                   ticker = 'AAA'): PriceChartResponse {
  const from = `${DAY}T08:00:00Z`
  const to = `${DAY}T09:07:00Z`
  const slot = (start: string, end: string, count: number | null,
                coverage: 'observed' | 'partial' | 'unknown') => ({
    start: `${DAY}T${start}:00Z`, end: `${DAY}T${end}:00Z`, count, coverage,
    config_transition: false, truncated: false, overlap_ambiguous: false,
  })
  return {
    version: 1,
    identity: { ticker, company_id: 11, instrument_id: 7, mic: 'XNMS', venue: 'NASDAQ',
                currency: 'USD', provider_symbol: ticker, mapped_at: '2026-08-01T00:00:00Z',
                fingerprint: `${ticker.toLowerCase()}`.padEnd(32, '0') },
    span: '1D',
    generated_at: to,
    window: { from, to, timezone: 'America/New_York', session_dates: [DAY], partial: true,
              calendar_basis: 'modeled', bands: [{ from, to, state: 'premarket' }] },
    acquisition: { state: 'ready', retry_after_seconds: null, reason: null },
    price: yahooPrice(),
    chatter: {
      step_minutes: 15, from, to,
      slots: [slot('08:00', '08:15', 3, 'observed'), slot('08:15', '08:30', 0, 'observed'),
              slot('08:30', '08:45', null, 'unknown'), slot('08:45', '09:00', 2, 'partial'),
              slot('09:00', '09:07', 1, 'partial')],
      tone: {
        basis: 'recorded-judgments',
        slots: [
          { bullish: 2, bearish: 1, neutral: 0, unjudged: 0, unavailable: 0, status: 'complete' },
          { bullish: 0, bearish: 0, neutral: 0, unjudged: 0, unavailable: 0, status: 'complete' },
          null,
          { bullish: 0, bearish: 0, neutral: 1, unjudged: 0, unavailable: 1, status: 'partial' },
          { bullish: 0, bearish: 0, neutral: 0, unjudged: 0, unavailable: 1, status: 'unavailable' },
        ],
      },
      normal_per_slot: null,
    },
    warnings: ['price: 1 provider bar(s) had no valid close and are shown as gaps'],
    ...over,
  }
}
