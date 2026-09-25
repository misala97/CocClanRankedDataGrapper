/**
 * How the add sheet orders the one exercise list (owner: "we have 2 preacher
 * curls and we only do one mainly" -- one movement's variants together, the
 * one you mainly do first).
 *
 * Pure functions over the payload's rows, so the ordering is testable without
 * rendering a sheet. "What you mainly do" is the server's `rank` (1 = most,
 * recent weeks weighing more -- exercises.usage), and which rows are yours
 * often enough to lead the sheet is its `common`.
 */
import type { CatalogueExercise } from './types'
import { find, type Tier } from '../search'

/** What the list's order needs of a row: the add sheet's rows, and
 *  Übungen's "Noch nie gemacht" (M6), whose rows have no rank -- never
 *  done, so A-Z. */
export interface Listed {
  movement: string
  label: string
  movement_group: string
  rank?: number | null
}

/** One movement and its rows, in the order the sheet shows them. */
export interface Cluster<T extends Listed = CatalogueExercise> {
  movement: string
  rows: T[]
}

/** One muscle group of the full list: every movement listed under it, A-Z. */
export interface Section<T extends Listed = CatalogueExercise> {
  group: string
  movements: Cluster<T>[]
}

const collator = new Intl.Collator('de')
const rankOf = (row: Listed) => row.rank ?? Number.POSITIVE_INFINITY

/** Yours first, the one you do most on top; the rest A-Z. Two never-done
 *  rows compare Infinity - Infinity = NaN, which falls through to the name. */
export function yoursFirst<T extends Listed>(rows: T[]): T[] {
  return [...rows].sort((a, b) => rankOf(a) - rankOf(b) || collator.compare(a.label, b.label))
}

function byMovement<T extends Listed>(rows: T[]): Cluster<T>[] {
  const grouped = new Map<string, T[]>()
  for (const row of rows) {
    const list = grouped.get(row.movement)
    if (list) list.push(row)
    else grouped.set(row.movement, [row])
  }
  return [...grouped].map(([movement, list]) => ({ movement, rows: yoursFirst(list) }))
}

/** Rows grouped by movement: the movement whose best row you do most comes
 *  first, movements you never did follow A-Z. */
export function clusters(rows: CatalogueExercise[]): Cluster[] {
  return byMovement(rows).sort((a, b) =>
    rankOf(a.rows[0]!) - rankOf(b.rows[0]!) || collator.compare(a.movement, b.movement))
}

/** "Deine": the exercises you do often, one movement's variants as a block. */
export function mine(catalogue: CatalogueExercise[]): Cluster[] {
  return clusters(catalogue.filter((row) => row.common))
}

/** The full list: every movement once, under its section, A-Z. Sections come
 *  in the list's own order; a group the server did not name goes last. */
export function sections<T extends Listed>(catalogue: T[], groups: string[]): Section<T>[] {
  const grouped = new Map<string, T[]>()
  for (const row of catalogue) {
    const list = grouped.get(row.movement_group)
    if (list) list.push(row)
    else grouped.set(row.movement_group, [row])
  }
  const unnamed = [...grouped.keys()].filter((group) => !groups.includes(group))
  return [...groups, ...unnamed.sort(collator.compare)]
    .filter((group) => grouped.has(group))
    .map((group) => ({
      group,
      movements: byMovement(grouped.get(group)!)
        .sort((a, b) => collator.compare(a.movement, b.movement)),
    }))
}

/** A search's hits, clustered the same way: what you do first. `tier` says
 *  how search.find found them -- 'typos', and the sheet says they are a
 *  typo away. */
export function found(catalogue: CatalogueExercise[], query: string):
  { clusters: Cluster[]; tier: Tier } {
  const { hits, tier } = find(catalogue, query, (row) => row.search)
  return { clusters: clusters(hits), tier }
}

const unique = (values: string[]) => [...new Set(values)]

/** A full-list movement row's second line: the variants you do, with how
 *  often, or else what it is done on. `rows` in yoursFirst order. */
export function movementMeta(rows: CatalogueExercise[]): string {
  const done = rows.filter((row) => row.rank !== null)
  if (done.length > 0) return done.slice(0, 2).map((row) => `${row.label} ${row.workouts}×`).join(' · ')
  if (rows.length === 1) return rows[0]!.label
  const geraete = unique(rows.map((row) => row.label.split(', ')[0]!))
  if (geraete.length > 1) return geraete.join(' · ')
  // All on one Gerät, and "Maschine" alone says nothing when all three are
  // machines: name what tells them apart.
  return unique([geraete[0]!, ...rows.flatMap((row) => row.label.split(', ').slice(1))]).join(' · ')
}

/** "1 Workout", "12 Workouts". */
export function workouts(count: number): string {
  return `${count} ${count === 1 ? 'Workout' : 'Workouts'}`
}
