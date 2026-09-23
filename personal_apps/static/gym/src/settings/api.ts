// The settings writes: one field of one exercise, and the rest for all.
// Both answer with what the sheet redraws from.

import { getJson, postForm } from '../api'
import type { ExerciseMeta, RestOverview, SettingField } from '../types'

/** One setting, as the server reads it: a number (a dot for decimals), stops
 *  comma-separated, or blank for the list's value. A value equal to what the
 *  field falls back to is stored as nothing (exercises.to_store). */
export function saveSetting(exerciseId: number, field: SettingField, value: string,
  keepalive = false): Promise<ExerciseMeta> {
  return postForm<ExerciseMeta>(`/gym/exercises/${exerciseId}/update`, { [field]: value },
    { keepalive })
}

export function fetchSettings(exerciseId: number): Promise<ExerciseMeta> {
  return getJson<ExerciseMeta>(`/gym/exercises/${exerciseId}/settings.json`)
}

/** Null: "Je nach Übungsart". */
export function saveRestForAll(seconds: number | null, keepalive = false): Promise<RestOverview> {
  return postForm<RestOverview>('/gym/rest', { rest_seconds: seconds === null ? '' : seconds },
    { keepalive })
}
