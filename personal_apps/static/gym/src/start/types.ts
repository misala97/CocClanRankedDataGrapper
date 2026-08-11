// Mirrors the Start-page models in features/gym/schemas.py.

export interface Consistency {
  sessions: number
  per_week: number
  days_since_last: number | null
  window_days: number
}

export interface RoutineMemory {
  template_id: number
  name: string
  exercises: string[]
  /** Parallel to `exercises`. The briefing intersects by id, not by name. */
  exercise_ids: number[]
  last_done: string | null
  days_ago: number | null
}

export interface RecentSession {
  session_id: number
  name: string | null
  started_at: string
  finished_at: string
  is_deload: boolean
  volume: number
  records: number
}

export interface Stall {
  exercise_id: number
  name: string
  position: number
  stuck_at: number
  since: string
  sessions_since_pr: number
}

export interface DeloadSuggestion {
  count: number
  stalls: Stall[]
}

export interface MuscleBalance {
  group: string
  sets: number
  volume: number
  share: number
  under_trained: boolean
}

export interface TonnageWeek {
  week_start: string
  volume: number
  is_current: boolean
  has_deload: boolean
}

export interface PendingInvite {
  shared_id: number
  leader_name: string
  session_name: string
}

export interface HeutePayload {
  now: string
  active_session_id: number | null
  active_session_name: string | null
  /** The clock's anchor: session start, not page render. */
  active_session_started_at: string | null
  /** The resume heuristic's "what was I on", for the card's second line. */
  active_session_exercise: string | null
  /** Display target for the rest countdown; stale values past the cap are
   *  ignored client-side, same as the Jinja resume strip. */
  active_session_rest_ends_at: string | null
  vapid_public_key: string | null
  consistency: Consistency
  routines: RoutineMemory[]
  recent_sessions: RecentSession[]
  stalls: Stall[]
  deload_suggestion: DeloadSuggestion | null
  balance: MuscleBalance[]
  tonnage: TonnageWeek[]
  /** The scale the bars are drawn against, and the empty-state gate: 0 means
   *  there is nothing to chart, and the section says so instead of drawing
   *  eight stubs and asserting a running week over them. */
  tonnage_peak: number
  templates: RoutineMemory[]
  pending_invites: PendingInvite[]
}
