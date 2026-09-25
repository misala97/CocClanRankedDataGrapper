// What the settings pills offer and how their values read. A rest reads
// m:ss, a weight with a comma -- the way the lifter would say it.

/** 150 -> "2:30". */
export function clock(seconds: number): string {
  const two = (n: number) => String(n).padStart(2, '0')
  // Past an hour only the rest band's "Pause vorbei" count-up gets here: a
  // lifter who walked away mid-workout.
  if (seconds >= 3600) {
    return `${Math.floor(seconds / 3600)}:${two(Math.floor(seconds / 60) % 60)}:${two(seconds % 60)}`
  }
  return `${Math.floor(seconds / 60)}:${two(seconds % 60)}`
}

/** 2.5 -> "2,5", 5 -> "5": a setting reads the way it is typed. */
export function kg(value: number): string {
  return String(Math.round(value * 100) / 100).replace('.', ',')
}

/** A bar of nothing is a real setting: the logged number is plates only. */
export function barLabel(value: number): string {
  return value === 0 ? 'Ohne' : kg(value)
}

/** A rest's ends, as the server keeps them (exercises.REST_MIN_SECONDS and
 *  REST_MAX_SECONDS), and what one nudge moves. */
export const REST_MIN = 15
export const REST_MAX = 600
export const REST_NUDGE = 15

/** Where the rest pills start when nothing marks a reference. */
const REST_AROUND = 120
const REST_GAP = 30
const REST_FLOOR = 30

/**
 * Five rests half a minute apart, the reference in the middle: one row for
 * "Pause heute" and the settings alike, each around the value it goes back
 * to (G-056; the settings put it second). The reference is always one of
 * them, so going back to it is one tap; fewer come before it rather than any
 * below half a minute, and fewer after it rather than any past REST_MAX --
 * a rest the server refuses.
 */
export function restChoices(reference: number | null): number[] {
  const centre = reference ?? REST_AROUND
  let first = centre
  for (let i = 0; i < 2 && first - REST_GAP >= REST_FLOOR; i += 1) first -= REST_GAP
  const last = () => first + 4 * REST_GAP
  while (last() > REST_MAX && last() - REST_GAP >= centre) first -= REST_GAP
  return [0, 1, 2, 3, 4].map((i) => first + i * REST_GAP)
}

/** Steps real gyms load in, by equipment: stacks in 2,5 to 10 (7 and 8 are
 *  the uneven machines lifters actually set), plates in pairs, dumbbells
 *  per hand. */
const STEPS: Record<string, number[]> = {
  stack: [2.5, 5, 7, 8, 10],
  plate_loaded: [1, 1.25, 2.5, 5, 10],
  dumbbell: [1, 1.25, 2, 2.5, 4],
}
const STEPS_OTHER = [1, 2, 2.5, 5, 10]
const BARS = [0, 10, 15, 20, 25]

/** `base`, with `reference` in it: it replaces the nearest value, so the
 *  row keeps its length and the list's own value is always one tap. */
function including(base: number[], reference: number | null): number[] {
  if (reference === null || base.includes(reference)) return base
  let nearest = 0
  base.forEach((value, i) => {
    if (Math.abs(value - reference) < Math.abs(base[nearest]! - reference)) nearest = i
  })
  return base.map((value, i) => (i === nearest ? reference : value)).sort((a, b) => a - b)
}

export function stepChoices(equipment: string | null, reference: number | null): number[] {
  return including(STEPS[equipment ?? ''] ?? STEPS_OTHER, reference)
}

export function barChoices(reference: number | null): number[] {
  return including(BARS, reference)
}

/** The first stops of a machine, as the stops row reads them: commas between
 *  whole kilograms, as they are typed, and dots between any with a decimal
 *  comma -- "2,5, 5, 7,5" reads as five numbers. */
export function stopsLine(stops: number[]): string {
  const first = stops.slice(0, 5)
  const shown = first.map(kg).join(first.every(Number.isInteger) ? ', ' : ' · ')
  return stops.length > 5 ? `${shown} …` : shown
}

/** Stops as typed: "5, 12; 19" -> [5, 12, 19], ascending, once each. Comma,
 *  semicolon or space between them, a decimal point as a dot -- stack pins
 *  are whole kilograms (routes._to_stack_steps, which is sent them joined by
 *  commas). Null unless at least two: one stop is not a machine. */
export function parseStops(text: string): number[] | null {
  const stops = [...new Set(text.split(/[;,\s]+/)
    .map((chunk) => Number.parseFloat(chunk))
    .filter((value) => Number.isFinite(value) && value > 0))].sort((a, b) => a - b)
  return stops.length >= 2 ? stops : null
}
