/** A training partner, as the other one sees them (D14, M5). Mirrors of
 *  features/gym/schemas.py: PartnerLink, PartnerList, PartnerRef,
 *  SyncPayload. Read-only everywhere: nothing here is ever written back. */

/** One set a partner lifted. */
export interface PartnerSet {
  weight: number
  reps: number
}

/** One partner line on the live screen: the leader sees each link of their
 *  workout, a follower the one to their leader. */
export interface PartnerLink {
  /** The SharedSession: what the list and the OK ask for. */
  id: number
  username: string
  viewer_leads: boolean
  state: 'invited' | 'declined' | 'joined' | 'finished'
  /** invited: when it was sent; declined: when; joined, finished: accepted. */
  since: string
  /** The partner's own finish. */
  finished_at: string | null
  /** joined: the partner's live row, by the partner's own rule. */
  exercise: string | null
  /** The 1-based place of its first open set; null: every set is done. */
  set_no: number | null
  done_in_exercise: number
  sets_in_exercise: number
  /** Its newest counted set; null until the row has one -- a chip beside an
   *  exercise's name is a set OF that exercise. */
  last_set: PartnerSet | null
  /** Seconds of rest left when the server built this: an age, not a time,
   *  so a phone clock minutes off the server's cannot move the flip. */
  rest_left: number | null
  /** The partner's own tick strip. */
  sets_done: number
  sets_total: number
  /** joined: a fingerprint of their list -- an open sheet asks again when it
   *  moves. 0 in every other state. */
  list_key: number
}

export interface PartnerListRow {
  id: number
  name: string
  picture: string | null
  state: 'done' | 'now' | 'open' | 'skipped'
  /** What was lifted -- never what the open ones are planned at. */
  sets: PartnerSet[]
  /** Ticked sets, one without reps too: the count their own queue gives. */
  done: number
  open: number
  /** On the row they are at: the set they are on, as the line says it (a
   *  tick without reps keeps its place). null everywhere else. */
  set_no: number | null
}

/** The partner's workout behind a line or a "mit", to their own finish. */
export interface PartnerList {
  id: number
  username: string
  viewer_leads: boolean
  /** Still training together: the order is the leader's. */
  link_live: boolean
  since: string
  started_at: string
  finished_at: string | null
  sets_done: number
  sets_total: number
  rest_left: number | null
  rows: PartnerListRow[]
}

/** A finished workout's partner: "mit <Name>". */
export interface PartnerRef {
  id: number
  username: string
}

/** What the live screen polls. */
export interface SyncPayload {
  version: number
  partner_links: PartnerLink[]
}
