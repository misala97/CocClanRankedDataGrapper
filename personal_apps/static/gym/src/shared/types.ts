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

export interface SharedConfirmPayload {
  shared_id: number
  leader_name: string
  /** Why this invite cannot be accepted, or null. */
  refusal: string | null
  proposals: MatchProposal[]
}
