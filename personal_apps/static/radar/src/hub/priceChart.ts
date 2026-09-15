// Selected-instrument price chart (MD-SELECTED-PRICE): the version-1 wire
// types, their validation at the boundary, and the one request.
//
// Its own request beside the ticker detail, on purpose. The detail keeps the
// headline quote, the posts and the summary; this carries price, chatter
// counts and retained tone for ONE explicit window, so the three can never be
// drawn from different periods. Nothing here chooses a provider or a symbol:
// the request names the ticker, span, market and source selection, and the
// server resolves the rest.
import type { PanelSpan } from '../types'

export type ChartSpan = '1D' | '1W'
export const CHART_SPANS: readonly PanelSpan[] = ['1D', '1W']

export type BandState = 'regular' | 'premarket' | 'afterhours' | 'closed'
export type AcquisitionState =
  | 'ready' | 'pending' | 'backoff' | 'busy' | 'disabled' | 'unavailable'
export type ToneKey = 'bullish' | 'bearish' | 'neutral' | 'unjudged' | 'unavailable'
export const TONE_KEYS: readonly ToneKey[] =
  ['bullish', 'bearish', 'neutral', 'unjudged', 'unavailable']

export interface PriceChartIdentity {
  ticker: string
  company_id: number
  instrument_id: number
  mic: string
  venue: string
  currency: 'USD'
  provider_symbol: string
  mapped_at: string
  fingerprint: string
}

export interface PriceBand { from: string; to: string; state: BandState }

export interface PriceChartWindow {
  from: string
  to: string
  timezone: 'America/New_York'
  session_dates: string[]
  partial: boolean
  calendar_basis: 'modeled'
  bands: PriceBand[]
}

export interface Acquisition {
  state: AcquisitionState
  retry_after_seconds: number | null
  reason: string | null
}

/** One plotted observation. For a provider bar `start`/`end` are the bar and
 *  `at` is when its close was known -- the end, or the receipt instant for a
 *  bar still open then (`provisional`). A stored quote has start = end = at. */
export interface PricePoint {
  at: string
  start: string
  end: string
  value: number | null
  provisional: boolean
  break_before: boolean
  regime: string
}

export interface PriceRegime {
  id: string
  source: string
  price_basis: string
  adjustment_basis: string
}

export interface PriceSeries {
  source: string
  kind: 'bar_close' | 'stored_quote' | 'daily_close'
  currency: 'USD'
  mic: string
  price_basis: string
  adjustment_basis: string
  regimes: PriceRegime[]
  received_at: string | null
  cache_age_seconds: number | null
  latest_observation_at: string | null
  stale: boolean
  fallback: boolean
  interval_seconds: number | null
  points: PricePoint[]
}

export interface ChatterSlot {
  start: string
  end: string
  /** null is unknown -- nothing valid was recorded -- and never zero. */
  count: number | null
  coverage: 'observed' | 'partial' | 'unknown'
  config_transition: boolean
  truncated: boolean
  overlap_ambiguous: boolean
}

export type ToneSlot = null | ({ [K in ToneKey]: number } & {
  status: 'complete' | 'partial' | 'unavailable'
})

export interface PriceChartResponse {
  version: 1
  identity: PriceChartIdentity
  span: ChartSpan
  generated_at: string
  window: PriceChartWindow
  acquisition: Acquisition
  price: PriceSeries | null
  chatter: {
    step_minutes: 15 | 60
    from: string
    to: string
    slots: ChatterSlot[]
    tone: { basis: 'recorded-judgments'; slots: ToneSlot[] }
    normal_per_slot: null
  }
  warnings: string[]
}

/** Process-scoped acquisition health, from /radar/api/ops. */
export interface SelectedPriceOps {
  scope: 'process'
  pid: number
  /** When this process's acquisition coordinator was created: lazily, on the
   *  first provider-enabled chart request that reaches acquisition, whether or
   *  not it is then admitted. Not the OS process start; null: not started. */
  coordinator_started_at: string | null
  charts_enabled: boolean
  yahoo_enabled: boolean
  /** A positive explicit worker count from `configured_web_workers_source`,
   *  or null when none is configured there: unknown, never guessed. */
  configured_web_workers: number | null
  configured_web_workers_source: string
  note: string
  in_flight: boolean
  cache_keys: number
  cache_bytes: number
  rolling_starts_60s: number
  backoff_until: string | null
  quarantined: boolean
  counters: Record<string, number>
  latency: { count: number; sum_seconds: number; max_seconds: number }
  limits?: { starts_per_60s: number; deadline_seconds: number }
}

export type PriceChartReason =
  | 'session' | 'timeout' | 'network' | 'missing' | 'disabled' | 'unsupported'
  | 'invalid' | 'limit' | 'unavailable' | 'forbidden' | 'server' | 'mismatch'

const REASON_TEXT: Record<PriceChartReason, string> = {
  session: 'Session expired — reload to sign in again.',
  timeout: 'The chart did not answer in time.',
  network: 'Could not reach the chart.',
  missing: 'No current company for that ticker.',
  disabled: 'The selected-session chart is switched off.',
  unsupported: 'No US primary listing in US dollars can be charted for this company.',
  invalid: 'The chart answer could not be read.',
  limit: 'The chart read exceeded its bounds.',
  unavailable: 'The chart data could not be read.',
  forbidden: 'This account is not allowed to read that.',
  server: 'The chart answered with an error.',
  mismatch: 'That answer was for a different chart, and was not shown.',
}

export class PriceChartUnavailable extends Error {
  constructor(readonly reason: PriceChartReason, readonly code: string | null = null) {
    super(REASON_TEXT[reason])
  }
}

/** Nothing retries these: another attempt gets the same refusal. */
export const PERMANENT_CHART_REASONS: ReadonlySet<PriceChartReason> = new Set([
  'session', 'forbidden', 'missing', 'disabled', 'unsupported', 'invalid', 'mismatch',
])

const TIMEOUT_MS = 8000
const MAX_POINTS = 2000
const MAX_SLOTS = 400
const ISO_Z = /^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$/
const DATE = /^\d{4}-\d{2}-\d{2}$/
const BAND_STATES = new Set(['regular', 'premarket', 'afterhours', 'closed'])
const STATES = new Set(['ready', 'pending', 'backoff', 'busy', 'disabled', 'unavailable'])

type Obj = Record<string, unknown>
const isObj = (value: unknown): value is Obj =>
  typeof value === 'object' && value !== null && !Array.isArray(value)
const isIso = (value: unknown): value is string =>
  typeof value === 'string' && ISO_Z.test(value) && Number.isFinite(Date.parse(value))
const isCount = (value: unknown): value is number =>
  typeof value === 'number' && Number.isInteger(value) && value >= 0
const isNullableNumber = (value: unknown) =>
  value === null || (typeof value === 'number' && Number.isFinite(value) && value >= 0)
const isStr = (value: unknown): value is string => typeof value === 'string'

function invalid(): never {
  throw new PriceChartUnavailable('invalid')
}

function check(condition: boolean): void {
  if (!condition) invalid()
}

function validPoint(point: unknown): void {
  check(isObj(point))
  const p = point as Obj
  check(isIso(p.at) && isIso(p.start) && isIso(p.end) && isStr(p.regime))
  check(p.value === null || (typeof p.value === 'number' && Number.isFinite(p.value) && p.value > 0))
  check(typeof p.provisional === 'boolean' && typeof p.break_before === 'boolean')
}

function validPrice(price: unknown): void {
  if (price === null) return
  check(isObj(price))
  const p = price as Obj
  check(isStr(p.source) && ['bar_close', 'stored_quote', 'daily_close'].includes(p.kind as string))
  check(p.currency === 'USD' && isStr(p.mic) && isStr(p.price_basis) && isStr(p.adjustment_basis))
  check(Array.isArray(p.regimes) && (p.regimes as unknown[]).every((r) => isObj(r)
    && isStr(r.id) && isStr(r.source) && isStr(r.price_basis) && isStr(r.adjustment_basis)))
  check((p.received_at === null || isIso(p.received_at))
    && (p.latest_observation_at === null || isIso(p.latest_observation_at)))
  check(isNullableNumber(p.cache_age_seconds) && isNullableNumber(p.interval_seconds))
  check(typeof p.stale === 'boolean' && typeof p.fallback === 'boolean')
  check(Array.isArray(p.points) && (p.points as unknown[]).length <= MAX_POINTS)
  ;(p.points as unknown[]).forEach(validPoint)
}

function validTone(slot: unknown, count: number | null): void {
  if (slot === null) {
    check(count === null)
    return
  }
  check(isObj(slot) && count !== null)
  const t = slot as Obj
  check(TONE_KEYS.every((key) => isCount(t[key])))
  check(['complete', 'partial', 'unavailable'].includes(t.status as string))
  check(TONE_KEYS.reduce((sum, key) => sum + (t[key] as number), 0) === count)
}

/** The response, or a thrown PriceChartUnavailable. `expected` is what this
 *  page asked for: an answer about another ticker or span is a late reply to
 *  an old question and is refused rather than drawn. */
export function validatePriceChart(raw: unknown,
                                   expected: { ticker: string; span: ChartSpan }):
  PriceChartResponse {
  check(isObj(raw))
  const r = raw as Obj
  check(r.version === 1)
  check(isObj(r.identity))
  const id = r.identity as Obj
  check(isStr(id.ticker) && isStr(id.mic) && isStr(id.venue) && isStr(id.provider_symbol)
    && isStr(id.fingerprint) && id.currency === 'USD' && isIso(id.mapped_at))
  check(typeof id.company_id === 'number' && id.company_id > 0
    && typeof id.instrument_id === 'number' && id.instrument_id > 0)
  if (id.ticker !== expected.ticker.toUpperCase() || r.span !== expected.span) {
    throw new PriceChartUnavailable('mismatch')
  }
  check(isIso(r.generated_at) && isObj(r.window) && isObj(r.acquisition) && isObj(r.chatter))
  const w = r.window as Obj
  check(isIso(w.from) && isIso(w.to) && Date.parse(w.to as string) >= Date.parse(w.from as string))
  check(w.timezone === 'America/New_York' && w.calendar_basis === 'modeled'
    && typeof w.partial === 'boolean')
  check(Array.isArray(w.session_dates) && (w.session_dates as unknown[]).length >= 1
    && (w.session_dates as unknown[]).every((d) => isStr(d) && DATE.test(d)))
  check(Array.isArray(w.bands) && (w.bands as unknown[]).every((b) => isObj(b)
    && isIso(b.from) && isIso(b.to) && BAND_STATES.has(b.state as string)))
  const a = r.acquisition as Obj
  check(STATES.has(a.state as string) && isNullableNumber(a.retry_after_seconds)
    && (a.reason === null || isStr(a.reason)))
  validPrice(r.price)
  const c = r.chatter as Obj
  // Shared bounds, never a shared array index.
  check(c.from === w.from && c.to === w.to && (c.step_minutes === 15 || c.step_minutes === 60))
  check(c.normal_per_slot === null && Array.isArray(c.slots)
    && (c.slots as unknown[]).length <= MAX_SLOTS && isObj(c.tone))
  const slots = c.slots as unknown[]
  const tone = c.tone as Obj
  check(tone.basis === 'recorded-judgments' && Array.isArray(tone.slots)
    && (tone.slots as unknown[]).length === slots.length)
  slots.forEach((slot, index) => {
    check(isObj(slot))
    const s = slot as Obj
    check(isIso(s.start) && isIso(s.end) && (s.count === null || isCount(s.count)))
    check(['observed', 'partial', 'unknown'].includes(s.coverage as string))
    check(typeof s.config_transition === 'boolean' && typeof s.truncated === 'boolean'
      && typeof s.overlap_ambiguous === 'boolean')
    check((s.count === null) === (s.coverage === 'unknown'))
    validTone((tone.slots as unknown[])[index], s.count as number | null)
  })
  check(Array.isArray(r.warnings) && (r.warnings as unknown[]).every(isStr))
  return raw as unknown as PriceChartResponse
}

function reasonFor(status: number, code: string | null): PriceChartReason {
  if (status === 401) return 'session'
  if (status === 403) return 'forbidden'
  if (status === 404) return code === 'feature_disabled' ? 'disabled' : 'missing'
  if (status === 422) return 'unsupported'
  if (status === 400) return 'invalid'
  if (status === 503) return code === 'read_limit' ? 'limit' : 'unavailable'
  if (status >= 500) return 'server'
  return 'network'
}

/** The chart for one company, span and source selection. Only three query
 *  keys exist on the server and only these three are sent. */
export async function fetchPriceChart(ticker: string, sources: string[], span: ChartSpan,
                                      signal?: AbortSignal): Promise<PriceChartResponse> {
  const params = new URLSearchParams()
  params.set('span', span)
  params.set('market', 'us')
  params.set('sources', sources.join(','))
  const controller = new AbortController()
  const timer = setTimeout(() => controller.abort(), TIMEOUT_MS)
  if (signal?.aborted) controller.abort()
  const relay = () => controller.abort()
  signal?.addEventListener('abort', relay, { once: true })
  let body: unknown
  try {
    const response = await fetch(
      `/radar/api/ticker/${encodeURIComponent(ticker)}/price-chart?${params}`,
      { headers: { Accept: 'application/json' }, credentials: 'same-origin',
        signal: controller.signal })
    if (response.redirected) throw new PriceChartUnavailable('session')
    if (!response.ok) {
      let code: string | null = null
      try {
        const refusal = await response.json() as { code?: unknown }
        code = typeof refusal?.code === 'string' ? refusal.code : null
      } catch {
        code = null
      }
      throw new PriceChartUnavailable(reasonFor(response.status, code), code)
    }
    try {
      body = await response.json()
    } catch {
      throw new PriceChartUnavailable('invalid')
    }
  } catch (error) {
    if (error instanceof PriceChartUnavailable) throw error
    throw new PriceChartUnavailable(
      (error as Error)?.name === 'AbortError' ? 'timeout' : 'network')
  } finally {
    clearTimeout(timer)
    signal?.removeEventListener('abort', relay)
  }
  return validatePriceChart(body, { ticker, span })
}
