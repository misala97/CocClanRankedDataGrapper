// Mirrors SharedConfirmPayload in features/gym/schemas.py.

export interface MatchProposal {
  /** The leader's name for it, verbatim. */
  name: string
  leader_exercise_id: number
  /** A normalised-equal match, which needs no question. */
  exact_id: number | null
  /** [id, name], best-first, always the full catalogue. */
  candidates: [number, string][]
}

export interface ConfirmTemplate {
  id: number
  name: string
  /** The FOLLOWER's own exercise ids -- compared against the selected
   *  matches, which resolve to the same catalogue. */
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
  proposals: MatchProposal[]
  /** The follower's routines, for booking this workout under one of them. */
  templates: ConfirmTemplate[]
}
