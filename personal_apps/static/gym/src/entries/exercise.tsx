import { createRoot } from 'react-dom/client'
import { ExerciseDetailPage } from '../pages/ExerciseDetail'
import type { ExerciseDetailPayload } from '../types'

// The payload is embedded in the document by the Jinja shell rather than
// fetched, so the first render has everything and there is no waterfall on
// load. /gym/exercises/<id>/detail.json serves the same object for refetches.
const dataEl = document.getElementById('gym-data')
const rootEl = document.getElementById('gym-root')

if (dataEl && rootEl) {
  const payload: ExerciseDetailPayload = JSON.parse(dataEl.textContent ?? '{}')
  // ?name_taken is set by gym_update_exercise when a rename collided. It is a
  // query flag rather than payload state because it describes what just
  // happened to this request, not what the exercise is.
  const nameTaken = new URLSearchParams(window.location.search).has('name_taken')
  createRoot(rootEl).render(
    <ExerciseDetailPage payload={payload} nameTaken={nameTaken} />)
}
