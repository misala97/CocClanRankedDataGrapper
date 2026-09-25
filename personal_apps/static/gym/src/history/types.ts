// Mirrors the history models in features/gym/schemas.py.

import type { PartnerRef } from '../partner/types'

/** A record the workout set: the set that made it and the best it beat. */
export interface HistoryRecord {
  exercise_id: number
  name: string
  weight: number
  reps: number
  e1rm: number
  previous: number
}

export interface HistoryEntry {
  session_id: number
  name: string | null
  started_at: string
  finished_at: string | null
  is_deload: boolean
  /** Ended by the app three hours after its last set (D5). */
  auto_finished: boolean
  volume: number
  record_count: number
  /** One per exercise, in the order the workout ran: "Nur Rekorde" shows
   *  them in place of the exercise line, with no fetch. */
  records: HistoryRecord[]
  /** The same exercises the volume beside it was computed from -- swapped-out
   *  ones excluded, so the roster and the total agree. */
  exercises: string[]
  /** Whom it was done with ("mit <Name>"): a partner who joined and lifted. */
  partners: PartnerRef[]
  /** The name and the date words ("31.07.2026 juli 2026"), folded on the
   *  server (../search); the exercises' texts are the payload's
   *  exercise_search. */
  search: string
  /** Days since the session AFTER this one in time. history is newest-first,
   *  so the gap belongs to the row below the break. Null on the newest row. */
  gap_days: number | null
}

export interface HistoryMonth {
  label: string
  slug: string
  entries: HistoryEntry[]
  volume: number
  records: number
}

/** The lede: the whole history in a sentence. */
export interface HistorySummary {
  workouts: number
  first_at: string
  tonnage: number
  /** Days, the break still running included. */
  longest_gap: number
}

export interface HistoryWeeks {
  weeks_trained: number
  weeks_total: number
  longest_streak: number
}

/** A month of the index -- every month since the first workout, one without
 *  a workout included: the index is a calendar. */
export interface HistoryIndexMonth {
  year: number
  month: number
  label: string
  short: string
  slug: string
  volume: number
  deload_volume: number
  records: number
  is_gap: boolean
  /** Still filling: drawn as an outline. */
  is_current: boolean
}

export interface HistoryPayload {
  months: HistoryMonth[]
  total: number
  /** Null while there is no workout. */
  summary: HistorySummary | null
  /** Null under four weeks: a share of three says nothing. */
  weeks: HistoryWeeks | null
  index: HistoryIndexMonth[]
  /** "Größtes Workout"; null under two workouts. */
  biggest_session_id: number | null
  gap_threshold: number
  weekday_short: string[]
  /** Each listed exercise's search text by name: the add sheet's, aliases
   *  and all -- once per exercise, not per row. */
  exercise_search: Record<string, string>
}
