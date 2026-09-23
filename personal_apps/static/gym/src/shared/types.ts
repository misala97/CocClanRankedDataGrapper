// Mirrors SharedConfirmPayload in features/gym/schemas.py.

/** One of the leader's exercises -- which, since the one list, the follower
 *  logs as it is. */
export interface SharedExercise {
  id: number
  name: string
}

export interface ConfirmTemplate {
  id: number
  name: string
  /** List exercise ids, compared against the workout's. */
  exercise_ids: number[]
}

export interface SharedConfirmPayload {
  shared_id: number
  leader_name: string
  /** The workout being joined: its name (null for a freeform one) and when
   *  the leader started it. */
  session_name: string | null
  started_at: string | null
  /** Why this invite cannot be accepted, or null. */
  refusal: string | null
  /** Accepting throws away the lifter's own running workout -- only ever an
   *  empty one; a logged set refuses the invite instead. */
  discards_active: boolean
  /** The leader's exercises in workout order, each once. */
  exercises: SharedExercise[]
  /** The follower's routines, for booking this workout under one of them. */
  templates: ConfirmTemplate[]
}
