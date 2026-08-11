// Mirrors the catalogue models in features/gym/schemas.py.
import type { ExerciseMeta } from '../types'

export type { ExerciseMeta }

export interface CatalogueEntry {
  exercise: ExerciseMeta
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
}

export interface CatalogueGroup {
  name: string
  entries: CatalogueEntry[]
}

export interface CataloguePayload {
  groups: CatalogueGroup[]
  muscle_groups: string[]
  equipment_labels: Record<string, string>
  open_by_default: boolean
  default_rest_seconds: number
  added_id: number | null
  name_taken: boolean
}

export type SortMode = 'muscle' | 'stall' | 'recent'
