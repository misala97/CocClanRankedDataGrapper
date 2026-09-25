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

export interface Stall {
  exercise_id: number
  name: string
  position: number
  stuck_at: number
  since: string
  /** "letzter am ..."; null when the lift never set a record -- `since` is
   *  its first workout then. */
  last_record_at: string | null
  sessions_since_pr: number
}

export interface ProgressPoint {
  started_at: string
  e1rm: number
}

/** The lift's best judged set: "Rekord", or "Bestwert" while its first
 *  workout holds it -- that beat nothing (D3). */
export interface ProgressBest {
  e1rm: number
  started_at: string
  is_record: boolean
}

/** A lift going up: its pace (kg per 30 days) above zero, not stalled. */
export interface ProgressLift {
  exercise_id: number
  name: string
  per_month: number
  workouts: number
  /** The workouts the pace was fitted through, oldest first. */
  points: ProgressPoint[]
  best: ProgressBest
}

/** "Fortschritt" (M3): the lifts going up; `stalls` is its other half. */
export interface Progress {
  up: ProgressLift[]
  /** Lifts with a pace at all, stalled ones aside: 0 means none has the
   *  workouts a pace needs yet. */
  with_trend: number
  min_workouts: number
  min_days: number
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

export interface OnboardingLast {
  session_id: number
  name: string | null
  started_at: string
  finished_at: string
  exercises: number
}

/** The first-run checklist. Null once a routine exists, or after enough
 *  freeform workouts that freeform is the habit. */
export interface Onboarding {
  workouts: number
  last: OnboardingLast | null
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
  progress: Progress
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
  onboarding: Onboarding | null
}
