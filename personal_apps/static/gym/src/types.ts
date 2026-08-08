// Mirrors features/gym/schemas.py exactly. If a field is added there, add it
// here -- the Pydantic model uses extra='forbid', so drift fails loudly on the
// Python side first, which is the intended order.

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
}

export interface SessionRow {
  session_id: number
  started_at: string
  position: number
  is_deload: boolean
  sets_display: string
  best_weight: number
  volume: number
  e1rm: number
}

/** session_id is load-bearing: the log matches the record row on it, never on
 *  the date -- two sessions on one day both matched a date test and both went
 *  gold. */
export interface WeightPR {
  weight: number
  reps: number
  session_id: number
  started_at: string
  position: number
}

export interface E1rmPR {
  e1rm: number
  weight: number
  reps: number
  session_id: number
  started_at: string
  position: number
}

/** x/y are SVG coordinates. e1rm and started_at ride along because
 *  _chart_geometry computes is_best from them after laying the points out. */
export interface ChartPoint {
  x: number
  y: number
  e1rm: number
  started_at: string
  is_best: boolean
  is_deload: boolean
}

export interface ChartTick {
  y_pct: number
  text: string
}

/** One position slot. Series separate by weight rather than hue: the palette is
 *  fixed at three semantic hues and a slot number is not a state, so the slot
 *  with the most sessions draws solid (is_main) and occasional ones recede. */
export interface ChartSeries {
  position: number
  points: ChartPoint[]
  opacity: number
  width: number
  is_main: boolean
  label_x: number
  label_y: number
  /** Only ever 'end' (label flipped left of a point near the right edge) or
   *  'start'. Narrow rather than string, so SVG's textAnchor accepts it and a
   *  third value added on the Python side fails here. */
  label_anchor: 'start' | 'end'
}

/** lo/hi are the DATA range, which is what the accessible description quotes.
 *  axis_lo/axis_hi are the padded drawing range -- widened to a floor so a lift
 *  that drifted 0,7 kg over a year does not render as a cliff. */
export interface ChartGeometry {
  series: ChartSeries[]
  lo: number
  hi: number
  axis_lo: number
  axis_hi: number
  ticks: ChartTick[]
  /** One or three entries: deduped, so an exercise whose whole history is one
   *  day renders a single mark instead of the same date three times. */
  dates: string[]
  width: number
  height: number
  has_deload: boolean
  has_record: boolean
}

export interface ExerciseDetailPayload {
  exercise: ExerciseMeta
  table: SessionRow[]
  /** Present in the payload but unread here: the page draws from `chart`, which
   *  is this same data already turned into SVG coordinates. Typed loosely on
   *  purpose rather than omitted, so this stays a true mirror of the schema. */
  series: unknown[]
  available_positions: number[]
  selected_position: number | null
  selected_position_is_default: boolean
  selected_position_reason: string | null
  last_overall: { started_at: string; position: number } | null
  pr_weight: WeightPR | null
  pr_e1rm: E1rmPR | null
  last_progression: SessionRow | null
  /** 'neu' | 'rekord' | 'stagniert' | 'steigend', or null for stable -- null is
   *  a real answer here, not an absence. */
  state: string | null
  sessions_since_pr: number | null
  chart: ChartGeometry | null
  chip_class: string | null
  chip_label: string | null
  can_delete: boolean
  muscle_groups: string[]
  equipment_labels: Record<string, string>
}
