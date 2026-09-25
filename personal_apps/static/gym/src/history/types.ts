// Mirrors the history models in features/gym/schemas.py.

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
  /** The same exercises the volume beside it was computed from -- swapped-out
   *  ones excluded, so the roster and the total agree. */
  exercises: string[]
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

export interface HistoryPayload {
  months: HistoryMonth[]
  total: number
  gap_threshold: number
  weekday_short: string[]
  /** Each listed exercise's search text by name: the add sheet's, aliases
   *  and all -- once per exercise, not per row. */
  exercise_search: Record<string, string>
}
