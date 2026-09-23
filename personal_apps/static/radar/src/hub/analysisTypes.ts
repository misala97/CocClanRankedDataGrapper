// The Analysis / Explore payload (HA1), exactly as the server serialises it
// (features/radar/analysis_contract.py), plus the pure decisions the page
// makes about it: what a valid window is, which price points may be joined,
// and what a day's coverage is called.
//
// Nothing here fetches, aggregates across days, or infers. Every rule the
// chart draws by is a function on the payload the tests can call directly.

/** A validated YYYY-MM-DD, never a timestamp. */
export type Day = string

export interface AnalysisCompany {
  id: number
  ticker: string
  name: string | null
  first_seen: string
}

export interface AnalysisInstrument {
  id: number
  ticker: string
  market: 'us'
  mic: string
  venue: string
  currency: 'USD'
  provider_symbol: string
  mapped_at: string
}

export type PriceState = 'observed' | 'missing' | 'invalid' | 'identity_unverified'
export type CalendarHint = 'modeled_open' | 'modeled_closed' | 'unknown'

export interface PriceDay {
  date: Day
  close: number | null
  state: PriceState
  /** Why a row is invalid or unverified; null when observed or missing. */
  reason: string | null
  source: string | null
  price_basis: string | null
  adjustment_basis: string | null
  fetched_at: string | null
  regime: string | null
  calendar_hint: CalendarHint
}

export interface SourceDay {
  source: string
  mentions: number | null
  ok_slots: number
  truncated_slots: number
  missing_slots: number
  absent_slots: number
  invalid_slots: number
  expected_slots: 96
  /** Source-bucket ROWS outside the 96-slot partition (off the 15-minute
   *  grid, or repeating a slot's key). The *_slots fields sum to 96. */
  excluded_rows: number
  config_versions: (string | null)[]
  transition: boolean
  coverage: 'observed_full_day' | 'partial' | 'unavailable'
}

export type DayCoverage = 'observed' | 'partial' | 'unavailable'

export interface ChatterDay {
  date: Day
  mentions: number | null
  coverage: DayCoverage
  configured_source_coverage: 'unknown'
  sources: SourceDay[]
  config_transition: boolean
  overlap_ambiguous: boolean
  /** Source-bucket ROWS before the company record, excluded. The name is
   *  kept for compatibility; the unit is rows, not time slots. */
  identity_excluded_slots: number
  /** Source-bucket rows off the grid or repeated, excluded (all sources). */
  excluded_rows: number
}

export interface AnalysisPayload {
  schema_version: 1
  mode: 'retrospective'
  company: AnalysisCompany
  instrument: AnalysisInstrument
  identity_scope: 'current_mapping_retrospective'
  request: { from: Day; to: Day; chatter_timezone: 'UTC'; max_days: 7 }
  read_started_at: string
  read_finished_at: string
  price: {
    resolution: 'daily_close'
    days: PriceDay[]
    usable_count: number
    first_usable: Day | null
    last_usable: Day | null
    official_completeness: 'unknown'
    interior_modeled_missing: Day[] | null
    regime_changed: boolean
  }
  chatter: {
    resolution: 'daily_counts'
    input_minutes: 15
    source_scope: 'all_retained_for_ticker'
    days: ChatterDay[]
    first_observed: string | null
    last_observed: string | null
  }
  warnings: string[]
}

export interface ResolvePayload {
  company: AnalysisCompany
  instrument: AnalysisInstrument
}

/** The window the page asks for. Both ends inclusive, both completed UTC
 *  days, at most MAX_DAYS long. Same vocabulary as the server's. */
export interface Range { from: Day; to: Day }

export const MAX_DAYS = 7
export const SCHEMA_VERSION = 1

const ISO = /^\d{4}-\d{2}-\d{2}$/

/** Today's UTC calendar date. The server decides "completed" on UTC too, so
 *  a reader in Berlin at 01:00 asking for "yesterday" gets the day the
 *  server also calls yesterday. */
export function todayUtc(now: Date = new Date()): Day {
  return now.toISOString().slice(0, 10)
}

function parseDay(value: string): Date | null {
  if (!ISO.test(value)) return null
  const parsed = new Date(`${value}T00:00:00Z`)
  if (Number.isNaN(parsed.getTime())) return null
  // `2026-02-29` parses to March 1st; the round trip catches it.
  return parsed.toISOString().slice(0, 10) === value ? parsed : null
}

function addDays(day: Date, n: number): Day {
  return new Date(day.getTime() + n * 86_400_000).toISOString().slice(0, 10)
}

/** The last seven COMPLETED UTC days: yesterday and the six before it. */
export function defaultRange(now: Date = new Date()): Range {
  const today = parseDay(todayUtc(now)) as Date
  return { from: addDays(today, -MAX_DAYS), to: addDays(today, -1) }
}

export type RangeProblem =
  | 'invalid_date' | 'reversed_range' | 'range_too_long' | 'range_not_completed'

/** Why a window cannot be asked for, or null. Mirrors parse_range on the
 *  server so the page never sends a request it knows will be refused, and
 *  never quietly repairs one -- the notice shows the values as typed. */
export function rangeProblem(range: { from: string; to: string },
                             now: Date = new Date()): RangeProblem | null {
  const from = parseDay(range.from)
  const to = parseDay(range.to)
  if (!from || !to) return 'invalid_date'
  if (to < from) return 'reversed_range'
  const days = Math.round((to.getTime() - from.getTime()) / 86_400_000) + 1
  if (days > MAX_DAYS) return 'range_too_long'
  const yesterday = parseDay(addDays(parseDay(todayUtc(now)) as Date, -1)) as Date
  if (to > yesterday) return 'range_not_completed'
  return null
}

export const RANGE_PROBLEM_TEXT: Record<RangeProblem, string> = {
  invalid_date: 'Dates must be written YYYY-MM-DD and be real calendar days.',
  reversed_range: 'The start must not be after the end.',
  range_too_long: `At most ${MAX_DAYS} days can be shown at once.`,
  range_not_completed: 'Only completed UTC days can be shown: the end must be yesterday or earlier.',
}

/** Which observed price points the line may join, as runs of indexes into
 *  `days`.
 *
 *  Only ADJACENT calendar dates that are both observed and share one regime
 *  (market, MIC, currency, source, basis) are joined. Any date between two
 *  observations -- missing, invalid, unverified, and a modeled-closed
 *  weekend or holiday too -- breaks the line (SPEC section 3: a conservative
 *  broken line across a weekend is acceptable; nothing is bridged). A sole
 *  observation is a dot. Nothing is interpolated. The server's
 *  analysis_contract.regime_runs draws the same runs. */
export function priceRuns(days: PriceDay[]): number[][] {
  const runs: number[][] = []
  let current: number[] = []
  days.forEach((day, index) => {
    if (day.state !== 'observed') {
      if (current.length) runs.push(current)
      current = []
      return
    }
    const previous = current.length ? days[current[current.length - 1]!]! : null
    if (previous !== null && previous.regime !== day.regime) {
      runs.push(current)
      current = []
    }
    current.push(index)
  })
  if (current.length) runs.push(current)
  return runs
}

/** Human words for a price day's state. */
export function priceStateLabel(day: PriceDay): string {
  switch (day.state) {
    case 'observed': return 'close'
    case 'missing':
      return day.calendar_hint === 'modeled_closed' ? 'no close (modeled closed day)'
        : day.calendar_hint === 'modeled_open' ? 'no close retained (modeled open day)'
        : 'no close retained'
    case 'invalid': return 'retained row unusable'
    case 'identity_unverified': return 'before the company record'
  }
}

/** Human words for a chatter day, honest about partial zeros. */
export function chatterLabel(day: ChatterDay): string {
  if (day.overlap_ambiguous) return 'source overlap — pooled count withheld'
  if (day.mentions === null) return 'no retained buckets'
  if (day.coverage === 'partial') {
    return day.mentions === 0
      ? '0 in observed buckets — coverage incomplete'
      : `${day.mentions} in observed buckets — coverage incomplete`
  }
  return `${day.mentions} observed`
}

/** Cents for anything a dollar or more; three significant figures under
 *  it, where a penny stock's third decimal is the whole move. */
export function formatClose(value: number): string {
  return value >= 1 ? value.toFixed(2) : value.toPrecision(3)
}

const WEEKDAYS = ['Sun', 'Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat']
const MONTHS = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct',
                'Nov', 'Dec']

/** `2026-09-08` as `Tue 8 Sep`, without inventing a timezone. Spelled here
 *  rather than by the locale: ICU's en-GB writes `Sept`, en-US reorders,
 *  and a label that differs by machine is not a label. */
export function dayLabel(day: Day, long = false): string {
  const parsed = parseDay(day)
  if (!parsed) return day
  const text = `${WEEKDAYS[parsed.getUTCDay()]} ${parsed.getUTCDate()} ${MONTHS[parsed.getUTCMonth()]}`
  return long ? `${text} ${parsed.getUTCFullYear()}` : text
}

export function stampUtc(iso: string | null): string {
  if (!iso) return 'unknown'
  const parsed = new Date(iso)
  if (Number.isNaN(parsed.getTime())) return iso
  return `${parsed.toISOString().slice(0, 16).replace('T', ' ')} UTC`
}
