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
  createRoot(rootEl).render(<ExerciseDetailPage payload={payload} />)
}
