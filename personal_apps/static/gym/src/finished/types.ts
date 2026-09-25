// Mirrors the finished-workout models in features/gym/schemas.py.

import type { LiveBest } from '../session/types'

export interface FinishedSession {
  id: number
  name: string | null
  started_at: string
  finished_at: string
  /** Ended by the app, at its last set, three hours on (D5). */
  auto_finished: boolean
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
  /** Its own e1RM beat every earlier workout's (D3): its reps wash gold. */
  is_record: boolean
}

/** One set of "Nächstes Mal" (stats.next_target). */
export interface TargetSet {
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
  /** This exercise's best e1RM here beat every earlier workout's (D3). */
  is_record: boolean
  /** What this row's best set beat, or null: no record here. */
  record: { value: number; previous: number } | null
  sessions_since_pr: number | null
  /** A deload keeps only 'rekord' and has no progress verdict otherwise. */
  verdict: 'rekord' | 'stagniert' | 'neu' | null
  /** What the next live card of this routine aims at, set by set -- null
   *  where this row is not what it builds on any more, or nothing is. */
  next_sets: TargetSet[] | null
  set_rows: CorrectableSet[]
  session_exercise_id: number | null
  notes: string | null
  pain: boolean
  /** What a correction or "Nachtragen" is judged against ("Sicher?", Q5), or
   *  null: no history. */
  best: LiveBest | null
}

/** A record is e1RM only (D3). */
export type RecordKind = 'e1rm'

export interface SessionRecord {
  kind: RecordKind
  name: string
  exercise_id: number
  position: number
  value: number
  /** The set that made it: "aus 80 kg × 12". */
  weight: number
  reps: number
  previous: number
  previous_at: string
}

/** Another workout the debrief points to. */
export interface WorkoutRef {
  id: number
  started_at: string
}

export interface FinishedPayload {
  session: FinishedSession
  exercises: FinishedExercise[]
  total_volume: number
  total_sets: number
  /** Ranked by relative gain: records[0] is the strongest claim. */
  records: SessionRecord[]
  record_count: number
  /** The one comparison (D10): whole percent against the mean of the two
   *  newest earlier full workouts of the routine, both named, newest first.
   *  null: no line (a deload, cut short, freeform, fewer than two). */
  comparison: { pct: number; against: (WorkoutRef & { volume: number })[] } | null
  /** The newest workout of the routine after this one (no deload), where
   *  the plan for next time is built now -- only a lift it left out still
   *  plans on its row here. */
  plan_moved_to: WorkoutRef | null
  /** A deload's one base workout for every "Nächstes Mal", or null. */
  plan_base: WorkoutRef | null
  is_deload: boolean
  deload_default_pct: number
  deload_applied: boolean
  tick_states: ('record' | 'done')[]
  /** Average seconds from one logged set to the next, the set itself
   *  included -- there is no stamp for when a set began, so this is pace,
   *  never "rest". null for fewer than two stamped sets, or for any session
   *  logged before completed_at existed: rendered as silence, never as zero. */
  set_pace_seconds: number | null
  /** Exercises of this workout with nothing logged, so the correction sheet
   *  can still add a set to them. */
  unlogged: { session_exercise_id: number; name: string; best: LiveBest | null }[]
  weekday_short: string[]
  just_finished: boolean
  /** The update prompt's diff, both halves: the template's current list, and
   *  what updating it would write (server-computed by the same function the
   *  route writes with). Both null for a freeform session. */
  template_exercises: string[] | null
  template_next_exercises: string[] | null
}
