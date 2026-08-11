import { createRoot } from 'react-dom/client'
import { HistoryPage } from '../history/HistoryPage'
import type { HistoryPayload } from '../history/types'

// Embedded, not fetched: this page sees the whole history, and search and the
// export selection are client-side over the rows it already has.
const dataEl = document.getElementById('gym-data')
const rootEl = document.getElementById('gym-root')

if (dataEl && rootEl) {
  const payload: HistoryPayload = JSON.parse(dataEl.textContent ?? '{}')
  createRoot(rootEl).render(<HistoryPage payload={payload} />)
}
