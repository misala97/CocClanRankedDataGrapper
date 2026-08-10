// Mirrors the session models in features/gym/schemas.py, checked against a
// payload captured from the real endpoint (scripts/make_session_fixture.py).
// The Pydantic models use extra='forbid', so drift fails on the Python side
// first -- which is the intended order.

export interface SessionMeta {
  id: number
  name: string | null
  started_at: string
  /** Always null here: a finished session renders a different page. */
  finished_at: string | null
  is_deload: boolean
  deload_pct: number | null
  rest_ends_at: string | null
  resting_set_id: number | null
  template_id: number | null
  template_name: string | null
  bodyweight_kg: number | null
  notes: string | null
  /** What the follower's poll compares. Only ever bumped on the FOLLOWER's
   *  session, which is why a leader polling sync.json would burn a request
   *  every 5s for a version that can never change. */
  structure_version: number
}

export interface LiveSet {
  id: number
  weight: number
  reps: number
  completed: boolean
  /** Non-null exactly when this set's weight is deload-scaled. `deload_applied`
   *  is derived from it -- the session's is_deload flag is not, because a
   *  session flagged after a set was logged keeps its full weights. */
  base_weight: number | null
}

export interface LiveExercise {
  /** The SessionExercise. `suggestions` and `stagnation_counts` are keyed by
   *  this; history and records go by `exercise_id`. */
  id: number
  exercise_id: number
  name: string
  muscle_group: string | null
  position: number
  skipped: boolean
  is_unilateral: boolean
  rest_seconds: number | null
  increment: number
  notes: string | null
  /** A boolean flag ("this hurt"), not free text. NOT NULL with a false
   *  default, so never null -- typed as a string once and the endpoint
   *  rejected its own payload. */
  pain: boolean
  sets: LiveSet[]
}

export interface CatalogueExercise {
  id: number
  name: string
  muscle_group: string | null
}

/** What the steppers pre-fill with. Null for an exercise with no history to
 *  seed from, so the containing record's value is nullable. */
export interface Suggestion {
  weight: number
  reps: number
}

/** "That weight went easy" -- only ever computed for the live exercise, and
 *  never during a deload. Null or a verdict; never an empty object. */
export interface ReadyForMore {
  sets: number
  weight: number
  is_latest: boolean
}

export interface Partner {
  id: number
  username: string
}

export interface PartnerStatus {
  username: string
  accepted: boolean
}

/** One tick per set in the whole workout, in order. Sets belonging to a
 *  skipped exercise are omitted entirely, so this is shorter than the sum of
 *  every exercise's sets. */
export type TickState = 'done' | 'now' | 'open'

export interface SessionDetailPayload {
  session: SessionMeta
  visible_exercises: LiveExercise[]
  /** The live SessionExercise, or null when the session has no visible
   *  exercises at all. */
  live_id: number | null
  /** 1-based position of the live exercise; 0 when there is none. */
  live_index: number
  live_increment: number

  tick_states: TickState[]
  sets_done: number
  sets_total: number
  sets_open: number
  session_volume: number

  resting: boolean
  /** 0 when nothing is resting, never null -- the progress bar divides by it.
   *  Comes from the exercise that OWNS the resting set, not the live one. */
  rest_total_seconds: number

  /** Both keyed by SessionExercise.id. JSON object keys are always strings, so
   *  these read '10', never 10. Pinned server-side by
   *  test_int_keyed_dicts_serialize_as_string_keys. */
  suggestions: Record<string, Suggestion | null>
  stagnation_counts: Record<string, number>
  /** A set on the server, a list on the wire. */
  record_set_ids: number[]
  ready_for_more: ReadyForMore | null

  min_full_reps: number
  default_plan_weight: number
  default_plan_reps: number

  exercises: CatalogueExercise[]
  muscle_groups: string[]
  /** Null whenever VAPID_PUBLIC_KEY is unset in .env. */
  vapid_public_key: string | null
  has_completed_set: boolean

  deload_applied: boolean
  deload_pcts: number[]
  deload_default_pct: number

  partners: Partner[]
  partner_status: PartnerStatus[]
  session_is_shared: boolean
}
