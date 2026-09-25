import { ExerciseDetailPage } from '../pages/ExerciseDetail'
import type { ExerciseDetailPayload } from '../types'
import { mount } from '../mount'

// The payload is embedded in the document by the Jinja shell rather than
// fetched, so the first render has everything and there is no waterfall on
// load. /gym/exercises/<id>/detail.json serves the same object for refetches.
mount<ExerciseDetailPayload>((payload) => <ExerciseDetailPage payload={payload} />)
