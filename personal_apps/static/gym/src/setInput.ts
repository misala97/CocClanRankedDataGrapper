import { kg, roundTo } from './format'

/**
 * The largest numbers a set can carry -- routes/helpers.py MAX_SET_WEIGHT_KG
 * and MAX_SET_REPS, which refuse anything past them with a 400. A bound on
 * what someone can mean when they type it: a fat-fingered 9999 kg used to be
 * stored and stay the record for good (walkthrough G-070).
 */
export const MAX_WEIGHT_KG = 1000
export const MAX_REPS = 1000

/** helpers.py BODYWEIGHT_RANGE_KG, MAX_NOTE_CHARS and MAX_NAME_CHARS: the
 *  server refuses past these, so the fields stop there first (G-071, G-083 --
 *  a 230-character routine name was a 500 the app called a lost connection). */
export const BODYWEIGHT_MIN_KG = 20
export const BODYWEIGHT_MAX_KG = 400
export const MAX_NOTE_CHARS = 2000
export const MAX_NAME_CHARS = 150

/** A typed bodyweight, or null when it is blank or cannot be one. */
export function parseBodyweight(text: string): number | null {
  if (text.trim() === '') return null
  const kg = Number(text.replace(',', '.').trim())
  return Number.isFinite(kg) && kg >= BODYWEIGHT_MIN_KG && kg <= BODYWEIGHT_MAX_KG ? kg : null
}

/** What the field says when a typed number is refused. Short, because it
 *  replaces a label under a number on a 390px screen. A weight is kept to
 *  the hundredth (format.kg), so 11,125 is refused rather than shown as
 *  one number and stored as another (G-146). */
export const WEIGHT_HINT = `0 bis ${MAX_WEIGHT_KG} kg, auf 0,01 genau`
export const REPS_HINT = `1 bis ${MAX_REPS} Wdh.`

/** A typed weight, or null when it cannot be one. Comma-tolerant: a German
 *  keyboard types 62,5, and a number field that has degraded to text passes
 *  it through. */
export function parseWeight(text: string): number | null {
  if (text.trim() === '') return null
  const w = Number(text.replace(',', '.').trim())
  return Number.isFinite(w) && w >= 0 && w <= MAX_WEIGHT_KG && roundTo(w, 2) === w ? w : null
}

/** A typed rep count, or null when it cannot be one: a set of no reps is not
 *  a set, and 2.5 of them is not a count. */
export function parseReps(text: string): number | null {
  if (text.trim() === '') return null
  const r = Number(text.trim())
  return Number.isInteger(r) && r >= 1 && r <= MAX_REPS ? r : null
}

/**
 * A typed set, or null when the two fields cannot be one.
 *
 * The same rule gym_add_set and gym_update_set apply (routes/helpers.py
 * _to_weight/_to_reps), checked here first so the button can say no before a
 * round trip does. `Number('')` is 0, which is how an empty add row used to
 * log a completed 0 kg x 0 set. Zero kilograms stays valid -- a bodyweight
 * set is logged at 0 -- but a set of no reps is not a set.
 */
export function parseSetInput(
  weight: string, reps: string,
): { weight: number; reps: number } | null {
  const w = parseWeight(weight)
  const r = parseReps(reps)
  return w === null || r === null ? null : { weight: w, reps: r }
}

/** Why a typed set cannot be saved, for the line under the fields -- null
 *  while it can, or while a field is still empty (nothing typed is nothing
 *  wrong yet). */
export function setInputProblem(weight: string, reps: string): string | null {
  if (weight.trim() !== '' && parseWeight(weight) === null) return `Gewicht: ${WEIGHT_HINT}`
  if (reps.trim() !== '' && parseReps(reps) === null) return `Wiederholungen: ${REPS_HINT}`
  return null
}

/**
 * The question to ask before a set more than twice the lifter's best at the
 * exercise is saved -- its weight or its reps (Q5, G-070) -- or null. A slip
 * of the finger inside the bounds above still made a record that stayed.
 *
 * `best`: LiveExercise.best, null before the first set. The weight is only
 * judged once a best weighs something: at a bodyweight exercise's 0 kg,
 * every weight is more than twice it.
 */
export function unlikely(
  set: { weight: number; reps: number },
  best: { weight: number; reps: number } | null,
  unit = 'kg',
): string | null {
  if (best === null) return null
  if (best.weight > 0 && set.weight > 2 * best.weight) {
    return `Sicher? Bisher höchstens ${kg(best.weight)} ${unit}.`
  }
  if (best.reps > 0 && set.reps > 2 * best.reps) {
    return `Sicher? Bisher höchstens ${best.reps} Wdh.`
  }
  return null
}
