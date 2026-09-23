import { useQuery, useQueryClient } from '@tanstack/react-query'
import type { LiveExercise } from '../types'
import { fetchSettings } from '../../settings/api'
import { SettingsBody } from '../../settings/SettingsBody'
import { useSheets } from '../stores'
import { sessionKey } from '../useSessionMutation'
import { Sheet } from './Sheet'

interface Props {
  exercise: LiveExercise
  sessionId: number
}

/**
 * "Deine Einstellungen" from the workout: one level below the exercise's
 * sheet, which it goes back to. The same rows as on the exercise's page --
 * what is set here holds for every workout, which is why it is a step away
 * from "Pause heute" rather than beside it.
 */
export function LiveSettingsSheet({ exercise, sessionId }: Props) {
  const open = useSheets((s) => s.open)
  return (
    <Sheet id={`sheet-settings-${exercise.id}`} title="Deine Einstellungen"
      onBack={() => open(`sheet-ex-${exercise.id}`)}>
      <LiveSettings exerciseId={exercise.exercise_id} sessionId={sessionId} />
    </Sheet>
  )
}

function LiveSettings({ exerciseId, sessionId }: { exerciseId: number; sessionId: number }) {
  const client = useQueryClient()
  // Read on every open and never kept: the rows seed from it once, so a
  // cached copy would show whatever was true the last time.
  const { data, isError, refetch } = useQuery({
    queryKey: ['exercise-settings', exerciseId],
    queryFn: () => fetchSettings(exerciseId),
    staleTime: 0,
    gcTime: 0,
    retry: false,
    refetchOnWindowFocus: false,
  })

  if (isError) {
    return (
      <p className="setting__error" role="alert">
        Einstellungen nicht geladen.{' '}
        <button type="button" className="linklike" onClick={() => { void refetch() }}>
          Nochmal
        </button>
      </p>
    )
  }
  if (data === undefined) return <p className="sheet__note">Lädt …</p>

  // The workout reads the rest and the step from the settings -- "Pause
  // heute" marks the one in force, the kg stepper moves by the step -- so
  // each answer has the screen asked again.
  return (
    <SettingsBody exercise={data}
      onSaved={() => { void client.invalidateQueries({ queryKey: sessionKey(sessionId) }) }} />
  )
}
