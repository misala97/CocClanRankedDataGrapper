import { createRoot } from 'react-dom/client'
import { SessionIsland } from '../session/SessionIsland'
import type { SessionDetailPayload } from '../session/types'

// The payload is embedded in the document rather than fetched, so the first
// render has everything and there is no waterfall on load. It is the same
// object /gym/session/<id>/detail.json serves, built once by
// routes.workout._live_data -- so the page and any refetch cannot disagree
// about which exercise is live.
const dataEl = document.getElementById('gym-data')
const rootEl = document.getElementById('gym-root')

if (dataEl && rootEl) {
  const payload: SessionDetailPayload = JSON.parse(dataEl.textContent ?? '{}')
  createRoot(rootEl).render(<SessionIsland initial={payload} />)
}
