// Mirrors the Statistik models in features/gym/schemas.py, which in turn
// mirror analytics.py's return values.

export interface BestSession {
  session_id: number
  started_at: string
  volume: number
}

export interface Totals {
  tonnage: number
  sets: number
  reps: number
  sessions: number
  /** All three are null before the first logged set. */
  first_session: string | null
  days_training: number | null
  best_session: BestSession | null
}

export interface TonnageMonth {
  year: number
  month: number
  volume: number
  /** A month with no training at all, drawn as a break rather than a zero. */
  is_gap: boolean
  has_deload: boolean
  has_record: boolean
}

export interface ProgressionRow {
  exercise_id: number
  name: string
  sessions: number
  first_e1rm: number
  current_e1rm: number
  change_pct: number
  best_weight: number
  points: number[]
  /** SVG polyline points, computed server-side. */
  spark: string
  /** Half-width of the diverging bar, scaled against the page's widest move. */
  bar_pct: number
  is_up: boolean
}

export interface RepBucket {
  label: string
  sets: number
  share: number
}

export interface RepRange {
  buckets: RepBucket[]
  sample: number
  dominant: RepBucket | null
  statable: boolean
  skipped: number
}

export interface Fatigue {
  sample: number
  statable: boolean
  weight_change_pct: number | null
  first_reps: number | null
  last_reps: number | null
}

export interface DaypartBucket {
  /** 'morning' | 'evening' | 'other', keyed into daypart_names. */
  label: string
  sessions: number
  volume: number
  avg_volume: number
}

export interface Daypart {
  parts: DaypartBucket[]
  statable: boolean
}

export interface WeekdayBucket {
  /** Monday-first, matching weekday_names. */
  weekday: number
  sessions: number
  share: number
  /** Per session, so the most-trained day cannot win by arithmetic. */
  avg_volume: number
}

export interface Weekday {
  days: WeekdayBucket[]
  sample: number
  statable: boolean
}

export interface RestGapBucket {
  label: string
  sessions: number
  avg_volume: number
  /** Enough workouts behind it to be drawn at all. */
  shown: boolean
}

export interface RestGap {
  buckets: RestGapBucket[]
  /** Populated but not yet drawable -- named in the caption, not dropped. */
  thin: RestGapBucket[]
  statable: boolean
}

export interface EffortSlice {
  label: string
  volume: number
  sets: number
  share: number
}

export interface Effort {
  groups: EffortSlice[]
  exercises: EffortSlice[]
  total_volume: number
}

export interface SessionLength {
  /** Timed sessions only. */
  sample: number
  /** Sessions with no usable finish stamp -- not zero-minute workouts. */
  untimed: number
  statable: boolean
  median_minutes: number | null
  volume_per_minute: number | null
}

export interface Consistency {
  weeks_trained: number
  weeks_total: number
  share: number
  current_streak: number
  longest_streak: number
  statable: boolean
}

export interface DriftGroup {
  label: string | null
  recent_share: number
  earlier_share: number
  delta: number
}

export interface BalanceDrift {
  window_days: number
  groups: DriftGroup[]
  recent_sessions: number
  earlier_sessions: number
  statable: boolean
}

export interface LadderRung {
  exercise_id: number
  name: string
  notches: number
  from_weight: number
  to_weight: number
  sessions: number
}

export interface IncrementLadder {
  exercises: LadderRung[]
  total_notches: number
  statable: boolean
}

export interface DroughtRow {
  exercise_id: number
  name: string
  sessions: number
  sessions_since: number
  /** null when the lift has never beaten its own debut. */
  last_record_at: string | null
}

export interface RecordDrought {
  exercises: DroughtRow[]
  statable: boolean
}

export interface RecordMove {
  value: number
  previous: number
}

export interface TimelineRecord {
  started_at: string
  session_id: number
  exercise_id: number
  name: string
  /** A row is here because it set at least one of the two. */
  weight: RecordMove | null
  e1rm: RecordMove | null
}

export interface RecordYear {
  year: number
  records: TimelineRecord[]
}

export interface StatistikPayload {
  totals: Totals
  longest_gap: number
  months: TonnageMonth[]
  progression: ProgressionRow[]
  rep_range: RepRange
  min_sets_for_rep_range: number
  fatigue: Fatigue
  daypart: Daypart
  weekday: Weekday
  rest_gap: RestGap
  session_length: SessionLength
  consistency: Consistency
  balance_drift: BalanceDrift
  increment_ladder: IncrementLadder
  record_drought: RecordDrought
  effort: Effort
  /** [planned, actual] medians in seconds, or null when there is nothing to
   *  report -- so the section says so instead of a confident 0:00. */
  rest_habit: [number, number] | null
  records_total: number
  recent_records: TimelineRecord[]
  record_years: RecordYear[]
  month_names: string[]
  weekday_names: string[]
  daypart_names: Record<string, string>
}
