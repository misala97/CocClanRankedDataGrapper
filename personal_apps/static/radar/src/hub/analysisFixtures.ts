// Real-shaped Analysis payloads for the tests (HA1). The shapes mirror
// features/radar/analysis_contract.py exactly; the VALUES are synthetic
// local fixtures, never production evidence.
import type {
  AnalysisPayload, ChatterDay, PriceDay, ResolvePayload, SourceDay,
} from './analysisTypes'

export const DAYS = ['2026-09-07', '2026-09-08', '2026-09-09', '2026-09-10',
                     '2026-09-11', '2026-09-12', '2026-09-13'] as const

const CLOSED = new Set(['2026-09-05', '2026-09-06', '2026-09-07', '2026-09-12', '2026-09-13'])

export function priceDay(date: string, over: Partial<PriceDay> = {}): PriceDay {
  const observed = over.close !== undefined && over.close !== null
  return {
    date,
    close: null,
    state: observed ? 'observed' : 'missing',
    reason: null,
    source: observed ? 'massive_grouped' : null,
    price_basis: observed ? 'close' : null,
    adjustment_basis: observed ? 'split' : null,
    fetched_at: observed ? `${date}T23:00:00Z` : null,
    regime: observed ? 'us/XNYS/USD/massive_grouped/close/split' : null,
    calendar_hint: CLOSED.has(date) ? 'modeled_closed' : 'modeled_open',
    ...over,
  }
}

export function sourceDay(source: string, over: Partial<SourceDay> = {}): SourceDay {
  return {
    source, mentions: 0, ok_slots: 96, truncated_slots: 0, missing_slots: 0,
    absent_slots: 0, invalid_slots: 0, expected_slots: 96, excluded_rows: 0,
    config_versions: ['cfgA'], transition: false, coverage: 'observed_full_day',
    ...over,
  }
}

export function chatterDay(date: string, over: Partial<ChatterDay> = {}): ChatterDay {
  return {
    date, mentions: null, coverage: 'unavailable', configured_source_coverage: 'unknown',
    sources: [], config_transition: false, overlap_ambiguous: false,
    identity_excluded_slots: 0, excluded_rows: 0, ...over,
  }
}

export function resolved(over: Partial<ResolvePayload> = {}): ResolvePayload {
  return {
    company: { id: 11, ticker: 'AAA', name: 'Aaa Corp', first_seen: '2026-01-01T00:00:00Z' },
    instrument: { id: 7, ticker: 'AAA', market: 'us', mic: 'XNYS', venue: 'NYSE',
                  currency: 'USD', provider_symbol: 'AAA', mapped_at: '2026-08-01T00:00:00Z' },
    ...over,
  }
}

/** A typical week: closes Tue-Fri except a missing Wednesday, chatter full
 *  on three days, partial on one, unavailable on the weekend. */
export function analysis(over: Partial<AnalysisPayload> = {}): AnalysisPayload {
  const identity = resolved()
  return {
    schema_version: 1,
    mode: 'retrospective',
    company: identity.company,
    instrument: identity.instrument,
    identity_scope: 'current_mapping_retrospective',
    request: { from: '2026-09-07', to: '2026-09-13', chatter_timezone: 'UTC', max_days: 7 },
    read_started_at: '2026-09-14T12:30:00Z',
    read_finished_at: '2026-09-14T12:30:01Z',
    price: {
      resolution: 'daily_close',
      days: [
        priceDay('2026-09-07'),
        priceDay('2026-09-08', { close: 10.5 }),
        priceDay('2026-09-09'),
        priceDay('2026-09-10', { close: 11 }),
        priceDay('2026-09-11', { close: 10.8 }),
        priceDay('2026-09-12'),
        priceDay('2026-09-13'),
      ],
      usable_count: 3,
      first_usable: '2026-09-08',
      last_usable: '2026-09-11',
      official_completeness: 'unknown',
      interior_modeled_missing: ['2026-09-09'],
      regime_changed: false,
    },
    chatter: {
      resolution: 'daily_counts',
      input_minutes: 15,
      source_scope: 'all_retained_for_ticker',
      days: [
        chatterDay('2026-09-07'),
        chatterDay('2026-09-08', { mentions: 12, coverage: 'observed',
          sources: [sourceDay('bluesky', { mentions: 12 })] }),
        chatterDay('2026-09-09', { mentions: 0, coverage: 'observed',
          sources: [sourceDay('bluesky', { mentions: 0 })] }),
        chatterDay('2026-09-10', { mentions: 40, coverage: 'partial',
          sources: [sourceDay('bluesky', { mentions: 40, ok_slots: 40, absent_slots: 56,
                                          coverage: 'partial' })] }),
        chatterDay('2026-09-11', { mentions: 3, coverage: 'observed',
          sources: [sourceDay('bluesky', { mentions: 3 })] }),
        chatterDay('2026-09-12'),
        chatterDay('2026-09-13'),
      ],
      first_observed: '2026-09-08T00:00:00Z',
      last_observed: '2026-09-11T23:45:00Z',
    },
    warnings: [
      'identity: current mapping applied retrospectively; the company record is a conservative boundary, not a verified historical identity',
      'price: the split stamp is a declared basis, not a verified adjustment vintage; same-source closes may have been restated',
    ],
    ...over,
  }
}
