import { createRoot } from 'react-dom/client'
import { FinishedPage } from '../finished/FinishedPage'
import type { FinishedPayload } from '../finished/types'

const dataEl = document.getElementById('gym-data')
const rootEl = document.getElementById('gym-root')

if (dataEl && rootEl) {
  const payload: FinishedPayload = JSON.parse(dataEl.textContent ?? '{}')
  createRoot(rootEl).render(<FinishedPage payload={payload} />)
}
