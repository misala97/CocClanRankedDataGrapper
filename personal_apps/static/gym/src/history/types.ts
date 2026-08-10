// Mirrors the history models in features/gym/schemas.py.

export interface HistoryEntry {
  session_id: number
  name: string | null
  started_at: string
  finished_at: string | null
  is_deload: boolean
  volume: number
  record_count: number
  /** The same exercises the volume beside it was computed from -- swapped-out
   *  ones excluded, so the roster and the total agree. */
  exercises: string[]
  /** Searchable date text, so "31.07" or "juli" works. */
  search_date: string
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
}
