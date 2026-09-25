// Mirrors features/gym/schemas.py exactly. If a field is added there, add it
// here -- the Pydantic model uses extra='forbid', so drift fails loudly on the
// Python side first, which is the intended order.

/** The list's own values for the four personal settings -- what a blank field
 *  in the settings form stands for. */
export interface ListDefaults {
  default_rest_seconds: number | null
  weight_increment: number | null
  bar_weight: number | null
  stack_kg: number[] | null
}

/** The four settings a lifter can make their own. */
export type SettingField = keyof ListDefaults

/** The exercise as this lifter sees it. Name, groups, equipment and one side
 *  are the list's; rest, step, bar and stack are the lifter's effective
 *  values, over `list_defaults`. */
export interface ExerciseMeta {
  id: number
  name: string
  muscle_group: string | null
  is_unilateral: boolean
  default_rest_seconds: number | null
  weight_increment: number | null
  equipment: string | null
  bar_weight: number | null
  stack_kg: number[] | null
  secondary_muscle_groups: string[] | null
  list_defaults: ListDefaults
  /** The settings that are the lifter's own value -- for the rest an
   *  exception to `rest_for_all`, where they set one. */
  own: SettingField[]
  /** The lifter's rest for all their exercises ("Deine Pause"), or null: by
   *  kind of exercise, the list's rest. */
  rest_for_all: number | null
}

/** An exercise with a rest of its own, under "Deine Pause". */
export interface RestException {
  exercise_id: number
  name: string
  rest_seconds: number
}

/** "Deine Pause" (exercises.rest_overview). */
export interface RestOverview {
  /** Null: by kind of exercise, the list's rest for each. */
  rest_for_all: number | null
  exceptions: RestException[]
  /** Where "Eine für alle" starts from "Je nach Übungsart". */
  start_seconds: number
  /** The list's range, which "Je nach Übungsart" means. */
  list_min_seconds: number
  list_max_seconds: number
  /** The stepper's ends. */
  min_seconds: number
  max_seconds: number
}

/** One set as done or aimed at. */
export interface WeightReps {
  weight: number
  reps: number
}

/** One performed row of the exercise: a line of the Workouts log, and what
 *  the Rekordtreppe's readout names. */
export interface SessionRow {
  session_id: number
  started_at: string
  position: number
  is_deload: boolean
  /** This workout's best e1RM beat every workout before it (D3). History: a
   *  record later overtaken keeps the tag. */
  is_record: boolean
  /** The counted sets, as logged. */
  sets: WeightReps[]
  volume: number
  e1rm: number
}

/** "Nächstes Ziel" (D9 A; plan.exercise_target). */
export interface ExerciseGoal {
  sets: WeightReps[]
  /** "Letztes Mal": the newest non-deload workout's counted sets. */
  last_sets: WeightReps[]
  last_at: string
  rep_min: number
  rep_max: number
  /** This target already put a set's weight up (a set with no step goes on
   *  by a rep instead, and is no step). */
  stepped: boolean
  /** Not stepped: where each set goes once the range's top is reached in
   *  all -- null for a set with no step. Null when stepped. */
  step_ups: (number | null)[] | null
}

/** A line of "Wiederholungen je Gewicht" (stats.weight_ladder). */
export interface WeightRow {
  weight: number
  reps: number
  workouts: number
  first_at: string
}

/** stats.e1rm_trend: kg per 30 days over the newest `workouts`. */
export interface E1rmTrend {
  per_month: number
  workouts: number
}

/** One workout on the Rekordtreppe (stats.record_stair). */
export interface StairCol {
  session_id: number
  position: number
  started_at: string
  e1rm: number
  /** The best so far, this workout included: its tread. */
  best: number
  kind: 'workout' | 'record' | 'deload'
}

/** The Rekordtreppe for "Alle" (position null) or one slot. */
export interface Stair {
  position: number | null
  cols: StairCol[]
  lo: number
  hi: number
  ticks: number[]
  /** "N ohne Rekord" at the last tread: the lift's drought, "Alle" only. */
  since: number | null
  /** The drought is a stall: drawn in the stall hue. "Alle" only. */
  stalled: boolean
}

/** The exercise itself: its drawing and the other variants of its movement. */
export interface ExerciseAbout {
  picture: string | null
  movement: string | null
  variants: { id: number; label: string }[]
}

export interface E1rmPR {
  e1rm: number
  weight: number
  reps: number
  session_id: number
  started_at: string
  position: number
  /** False while the debut holds the best: a first workout beats nothing
   *  (D3), so the page says "Bestwert" and draws no gold. */
  is_record: boolean
}

/** The exercise page (D9, M2). Everything is the WHOLE exercise except the
 *  stair a pill picks. */
export interface ExerciseDetailPayload {
  exercise: ExerciseMeta
  /** Every row, newest first. */
  table: SessionRow[]
  goal: ExerciseGoal | null
  weights: WeightRow[]
  pr_e1rm: E1rmPR | null
  trend: E1rmTrend | null
  /** "Alle" first, then one per pill; empty with fewer than two workouts to
   *  draw. */
  stairs: Stair[]
  /** The slots an "Als N. Übung" pill offers. */
  position_pills: number[]
  /** The pill the page opens on; null is "Alle". */
  selected_position: number | null
  /** 'neu' | 'rekord' | 'stagniert' | 'steigend', or null for stable -- null is
   *  a real answer here, not an absence. */
  state: string | null
  sessions_since_pr: number | null
  chip_class: string | null
  chip_label: string | null
  about: ExerciseAbout
  /** Unread since the settings sheet stopped repeating the list's facts
   *  (V3); kept so this stays a true mirror of the schema. */
  equipment_labels: Record<string, string>
  /** On today's list. A retired row is offered no way on (M6). */
  on_list: boolean
  running: RunningWorkout | null
  /** The lifter's routines, A-Z. */
  routines: RoutineChoice[]
}

/** The workout running when the page was read (M6): "Zu „<name>“
 *  hinzufügen" instead of beginning one. */
export interface RunningWorkout {
  session_id: number
  /** null for a workout begun without one. */
  name: string | null
  /** Its visible rows of this exercise, as the add sheet counts them. */
  count: number
  /** Its sets of this exercise that count (done, one rep or more), on every
   *  row of it, a replaced original's too: lifted today, not yet on the
   *  page, which reads finished workouts -- and shows them so. */
  logged: number
}

/** A routine the exercise can go into ("Zur Routine"). */
export interface RoutineChoice {
  id: number
  name: string
  /** Its rows: "7 Übungen". */
  count: number
  /** It holds this exercise already: "drin", on a row that stays a button
   *  (aria-disabled), so the row just tapped keeps the focus. */
  has: boolean
}
