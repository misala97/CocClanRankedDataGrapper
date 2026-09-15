// Test fixtures for the selected-session chart. Synthetic: hand-written to
// exercise gaps, provisional bars, unknown versus zero counts and partial
// coverage, in the shape the server's contract emits.
import type { PriceChartResponse, PricePoint, PriceSeries } from './priceChart'

const DAY = '2026-09-15'

export function bar(hhmm: string, value: number | null,
                    { breakBefore = false, provisional = false, at }:
                    { breakBefore?: boolean; provisional?: boolean; at?: string } = {}): PricePoint {
  const start = `${DAY}T${hhmm}:00Z`
  const end = new Date(Date.parse(start) + 60_000).toISOString().replace('.000Z', 'Z')
  return { at: provisional && at ? `${DAY}T${at}Z` : end, start, end, value,
           provisional, break_before: breakBefore, regime: 'yahoo_chart:provider_bar_close:unknown' }
}

export function yahooPrice(over: Partial<PriceSeries> = {}): PriceSeries {
  return {
    source: 'yahoo_chart', kind: 'bar_close', currency: 'USD', mic: 'XNMS',
    price_basis: 'provider_bar_close', adjustment_basis: 'unknown',
    regimes: [{ id: 'yahoo_chart:provider_bar_close:unknown', source: 'yahoo_chart',
                price_basis: 'provider_bar_close', adjustment_basis: 'unknown' }],
    received_at: `${DAY}T09:06:30Z`, cache_age_seconds: 30,
    latest_observation_at: `${DAY}T09:06:30Z`, stale: false, fallback: false,
    interval_seconds: 60,
    points: [
      bar('08:00', 100), bar('08:01', 101), bar('08:02', null, { breakBefore: true }),
      bar('08:03', 102, { breakBefore: true }), bar('08:04', 101.5),
      bar('09:06', 103, { breakBefore: true, provisional: true, at: '09:06:30' }),
    ],
    ...over,
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
