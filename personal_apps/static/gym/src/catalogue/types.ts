// Mirrors the catalogue models in features/gym/schemas.py.
import type { ExerciseMeta, RestOverview } from '../types'

export type { ExerciseMeta, RestOverview }

export interface CatalogueEntry {
  exercise: ExerciseMeta
  /** The folded name and aliases the add sheet searches too (../search);
   *  the page adds the group's name. */
  search: string
  chip_class: string | null
  chip_label: string | null
  last_done: string | null
  best_weight: number | null
  /** What you would load TODAY, which is the question a catalogue is opened
   *  with. The row used to lead with the all-time best, unlabelled, so a
   *  personal record could not be told apart from a working weight. */
  last_weight: number | null
  days_ago: number | null
  sessions_since_pr: number | null
  /** The drawing's tile; null off the list (the dumbbell). */
  picture: string | null
  /** The running workout holds sets of it that count: with no finished one
   *  yet, "Heute im Workout" rather than "Noch kein Satz". */
  in_running: boolean
}

/** A muscle group and the lifter's exercises in it, in the list's order.
 *  An empty one is named, not banded: "Noch nichts für Beine". */
export interface CatalogueGroup {
  name: string
  entries: CatalogueEntry[]
}

/** A list entry the lifter has not had yet: "Noch nie gemacht" (M6). */
export interface LibraryEntry {
  id: number
  name: string
  /** "Bankdrücken" and "Kurzhantel" of "Bankdrücken (Kurzhantel)". */
  movement: string
  label: string
  /** Its band: its movement's group, as in the add sheet. */
  movement_group: string
  search: string
  picture: string | null
}

export interface CataloguePayload {
  groups: CatalogueGroup[]
  open_by_default: boolean
  /** "Deine Pause": the lifter's rest for all their exercises. */
  rest: RestOverview
  /** The rest of the list: every list exercise that is not the lifter's. */
  library: LibraryEntry[]
  /** The list's group order (library.LIST_GROUPS). */
  list_groups: string[]
}

export type SortMode = 'muscle' | 'stall' | 'recent'
