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
  /** Null = not decided yet: an exercise with no history is planned with no
   *  numbers until the lifter types the first set. Never null on a completed
   *  set -- the server refuses to log one. */
  weight: number | null
  reps: number | null
  completed: boolean
  /** Non-null exactly when this set's weight is deload-scaled. `deload_applied`
   *  is derived from it -- the session's is_deload flag is not, because a
   *  session flagged after a set was logged keeps its full weights. */
  base_weight: number | null
  /** The live screen's own name for a set it added (SessionSet.client_key):
   *  how the outbox finds the real set behind the one it drew (B6). Null on
   *  every other set. */
  key: string | null
}

/** LiveBest, in schemas.py: each apart -- the most reps need not be at the
 *  heaviest weight. */
export interface LiveBest {
  weight: number
  reps: number
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
  /** True while this row is the leader's structure in a LIVE shared workout:
   *  the follower may skip or substitute it, never remove it. False for an
   *  exercise they added themselves, and for every row once the link ended. */
  mirrored: boolean
  is_unilateral: boolean
  /** This workout's own rest ("Pause heute"), or null: `rest_setting`. */
  rest_seconds: number | null
  /** The lifter's rest for the exercise, what always applies: its own, else
   *  their rest for all, else the list's. */
  rest_setting: number | null
  /** Whether `rest_setting` is the lifter's (own or for all) -- the mark
   *  under it says "deine" -- rather than the list's ("Liste"). */
  rest_setting_mine: boolean
  increment: number
  /** Where a blank kg stepper's "+" lands for this row: `live_floor` once
   *  it is live. The screen that moves on by itself offline needs it (B6). */
  floor: number
  notes: string | null
  /** A boolean flag ("this hurt"), not free text. NOT NULL with a false
   *  default, so never null -- typed as a string once and the endpoint
   *  rejected its own payload. */
  pain: boolean
  /** The heaviest weight and the most reps the lifter has done on the
   *  exercise, in any finished workout and in this one so far; null before
   *  the first. What a typed number is checked against ("Sicher?", G-070). */
  best: LiveBest | null
  /** Where the exercise's drawing loads from, or null while it has none
   *  (off the list, or not drawn yet): the page shows the placeholder. */
  picture: string | null
  /** The done sets (count, volume) of the hidden originals this row replaced:
   *  they count in place (Q1), so the retally adds them. Zero otherwise. */
  replaced_sets_done: number
  replaced_volume: number
  /** Stands in for a hidden original: removed, it brings the original back,
   *  a row this screen does not have to draw. */
  is_substitute: boolean
  sets: LiveSet[]
}

export interface CatalogueExercise {
  id: number
  name: string
  muscle_group: string | null
  /** The folded name and aliases (exercises.search_text) -- what the add
   *  sheet matches a query against, see ../search. */
  search: string
  /** The movement it is a variant of, and what sets it apart from the other
   *  variants: "Bankdrücken" and "Kurzhantel" of "Bankdrücken (Kurzhantel)". */
  movement: string
  label: string
  /** The section the add sheet lists the movement under -- the same for all
   *  of its variants, so one movement never splits across two sections. */
  movement_group: string
  /** This lifter's finished workouts with a completed set of it; 0 = never. */
  workouts: number
  /** Calendar days since the last of them; null = never. */
  days_ago: number | null
  /** 1 = what this lifter does most, recent weeks weighing more; null =
   *  never done. */
  rank: number | null
  /** Listed under "Deine" at the top of the add sheet. */
  common: boolean
}

/** What the steppers pre-fill with. Null for an exercise with no history to
 *  seed from, so the containing record's value is nullable. */
export interface Suggestion {
  weight: number
  reps: number
}

/** Which past workout a plan's numbers came from, and by which of seeding's
 *  rules. 'slot': the best fresh result at this slot or a later one.
 *  'earlier_slot': nothing fresh this late in a workout, so the best fresh
 *  result from an earlier, fresher slot -- may run heavy. 'layoff': nothing
 *  fresh at all, so the most recent workout rather than the best. */
export interface SeedSource {
  date: string
  /** The slot the exercise sat in during THAT workout. */
  position: number
  basis: 'slot' | 'earlier_slot' | 'layoff'
  /** That workout is also the newest one that counts (deloads left out), so
   *  the card may call it "Letztes Mal". */
  is_latest: boolean
  /** What was lifted that day, in order. */
  sets: Suggestion[]
}

/** What one just-logged set beat. A record is e1RM only (D3): `value` and
 *  `previous` are estimated one-rep-max kilograms, the same pair the debrief
 *  prints, so the live takeover and the debrief never name one set's record
 *  two different ways. */
export interface LiveRecord {
  kind: 'e1rm'
  value: number
  previous: number
  /** ISO. The start of the session that held the old best. */
  previous_at: string
}

/** One set of what to lift (D2 P1): display only, never seeded. */
export interface TargetSet {
  weight: number
  reps: number
}

/** What the workout's routine keeps for one exercise (D2 P1): the sets it
 *  plans and the rep range the target aims at. */
export interface RoutinePlan {
  sets: number
  rep_min: number
  rep_max: number
}

/** Another variant of a movement as the lifter last did it: the top set of
 *  the latest workout that had it, deloads aside. `label` is the variant part
 *  of the name ("Kurzhantel"), `per_side` says the weight is one side's. */
export interface VariantRef {
  label: string
  weight: number
  reps: number
  per_side: boolean
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
  /** Where the live kg stepper's "+" lands from a blank weight: the empty
   *  bar, the lightest stop of a known stack, else one step. Null when
   *  nothing is live. */
  live_floor: number | null

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
  /** Keyed the same way. Null for an exercise with no history at all. */
  seed_sources: Record<string, SeedSource | null>
  stagnation_counts: Record<string, number>
  /** Keyed like stagnation_counts: what to lift, set by set, for every
   *  exercise with a workout to build on. Empty in a deload. */
  next_targets: Record<string, TargetSet[]>
  /** Keyed the same way (D4): in a deload marked after the first set, the
   *  weight the deload would have planned for each exercise not started yet --
   *  nothing rescales mid-workout. Empty otherwise. */
  deload_hints: Record<string, number>
  /** Keyed the same way: the routine's plan for each exercise it holds, where
   *  the sheet's steppers start. Empty without a routine of your own. */
  routine_plans: Record<string, RoutinePlan>
  /** A set on the server, a list on the wire. */
  record_set_ids: number[]
  /** Keyed by Set.id, string-keyed like suggestions. One entry per id in
   *  record_set_ids and no others -- both are built from the same judgement
   *  in the same server loop. */
  record_details: Record<string, LiveRecord>
  /** Keyed by SessionExercise.id like suggestions: the exercises met for the
   *  first time -- no history, nothing logged in this workout yet. Each lists
   *  up to two of the lifter's other variants of the movement with their last
   *  numbers, most-done first. Information only: another variant's numbers
   *  are not this one's. Absent key = not a first time. */
  first_time: Record<string, VariantRef[]>

  /** The add sheet's list. Only the page and detail.json send it; a write's
   *  answer leaves it and list_groups out (SessionReply), and session/api.ts
   *  fills in the last one it saw, so past api.ts a payload always has it. */
  exercises: CatalogueExercise[]
  /** The add sheet's sections in the list's own order, Brust first. */
  list_groups: string[]
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

/** A write's answer: the payload without the add sheet's list, which never
 *  changes under a running workout (walkthrough G-140). */
export type SessionReply = Omit<SessionDetailPayload, 'exercises' | 'list_groups'>
  & Partial<Pick<SessionDetailPayload, 'exercises' | 'list_groups'>>
