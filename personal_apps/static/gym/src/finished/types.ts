// Mirrors the finished-workout models in features/gym/schemas.py.

export interface FinishedSession {
  id: number
  name: string | null
  started_at: string
  finished_at: string
  is_deload: boolean
  deload_pct: number | null
  bodyweight_kg: number | null
  notes: string | null
  template_id: number | null
  template_name: string | null
}

export interface CorrectableSet {
  id: number
  weight: number
  reps: number
}

export interface FinishedExercise {
  exercise_id: number
  name: string
  position: number
  sets: [number, number][]
  sets_display: string
  volume: number
  best_weight: number
  e1rm: number
  has_history: boolean
  avg_volume: number | null
  volume_delta_pct: number | null
  is_weight_pr: boolean
  is_volume_pr: boolean
  is_e1rm_pr: boolean
  sessions_since_pr: number | null
  /** A deload sets every verdict to null, which is why the tag can be absent. */
  verdict: 'rekord' | 'stagniert' | 'steigend' | 'neu' | null
  set_rows: CorrectableSet[]
  session_exercise_id: number | null
  notes: string | null
  pain: boolean
}

export type RecordKind = 'weight' | 'e1rm' | 'volume'

export interface SessionRecord {
  kind: RecordKind
  name: string
  exercise_id: number
  position: number
  value: number
  previous: number
  previous_at: string
}

export interface SessionAdvice {
  exercise_id: number
  name: string
  stuck_at: number
  sessions: number
  suggested_weight: number
}

export interface PreviousSession {
  id: number
  started_at: string
  volume: number
}

export interface FinishedPayload {
  session: FinishedSession
  exercises: FinishedExercise[]
  total_volume: number
  total_sets: number
  avg_total_volume: number | null
  total_volume_delta_pct: number | null
  /** Ranked by kind then relative gain: records[0] is the strongest claim. */
  records: SessionRecord[]
  record_count: number
  advice: SessionAdvice[]
  is_deload: boolean
  deload_default_pct: number
  deload_applied: boolean
  previous_session: PreviousSession | null
  tick_states: ('record' | 'done')[]
  /** null for any session logged before completed_at existed -- rendered as
   *  silence, never as zero. */
  rest_taken_seconds: number | null
  weekday_short: string[]
  just_finished: boolean
  /** The update prompt's diff, both halves: the template's current list, and
   *  what updating it would write (server-computed by the same function the
   *  route writes with). Both null for a freeform session. */
  template_exercises: string[] | null
  template_next_exercises: string[] | null
}
