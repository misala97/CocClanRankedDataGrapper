import { createRoot } from 'react-dom/client'

import { BoardPage } from '../board/BoardPage'
import type { BoardPayload } from '../types'

// The first board is embedded in the document by features/radar/routes/views.py
// rather than fetched after mount: the server already had it, and a spinner on
// arrival for data that was in hand is a self-inflicted wait.
const dataEl = document.getElementById('radar-data')
const rootEl = document.getElementById('radar-root')

if (dataEl && rootEl) {
  const payload: BoardPayload = JSON.parse(dataEl.textContent ?? '{}')
  createRoot(rootEl).render(<BoardPage initial={payload} />)
}
