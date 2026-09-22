/**
 * A typed set, or null when the two fields cannot be one.
 *
 * The same rule gym_add_set and gym_update_set apply (routes/helpers.py
 * _to_weight/_to_reps), checked here first so the button can say no before a
 * round trip does. `Number('')` is 0, which is how an empty add row used to
 * log a completed 0 kg x 0 set. Zero kilograms stays valid -- a bodyweight
 * set is logged at 0 -- but a set of no reps is not a set.
 *
 * Comma-tolerant: a German keyboard types 62,5, and a number field that has
 * degraded to text passes it through.
 */
export function parseSetInput(
  weight: string, reps: string,
): { weight: number; reps: number } | null {
  const w = weight.trim() === '' ? NaN : Number(weight.replace(',', '.').trim())
  const r = reps.trim() === '' ? NaN : Number(reps.trim())
  if (!Number.isFinite(w) || w < 0) return null
  if (!Number.isInteger(r) || r < 1) return null
  return { weight: w, reps: r }
}
