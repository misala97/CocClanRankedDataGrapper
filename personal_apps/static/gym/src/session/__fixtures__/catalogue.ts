import { fold } from '../../search'
import type { CatalogueExercise } from '../types'

/**
 * One add-sheet row as the server sends it, built from a list name
 * ("Bewegung (Gerät, Variante)"): never done unless `over` says otherwise.
 * For tests that need a handful of rows with known usage -- the generated
 * session-payload.json carries the real list with one real history.
 */
export function listed(id: number, name: string,
  over: Partial<CatalogueExercise> = {}): CatalogueExercise {
  const match = /^(.+) \((.+)\)$/.exec(name)
  return {
    id, name, muscle_group: 'Brust', search: fold(name),
    movement: match?.[1] ?? name, label: match?.[2] ?? name,
    movement_group: over.muscle_group ?? 'Brust',
    workouts: 0, days_ago: null, rank: null, common: false,
    ...over,
  }
}
