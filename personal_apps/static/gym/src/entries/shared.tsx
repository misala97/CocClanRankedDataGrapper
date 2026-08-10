import { createRoot } from 'react-dom/client'
import { SharedConfirmPage } from '../shared/SharedConfirmPage'
import type { SharedConfirmPayload } from '../shared/types'

const dataEl = document.getElementById('gym-data')
const rootEl = document.getElementById('gym-root')

if (dataEl && rootEl) {
  const payload: SharedConfirmPayload = JSON.parse(dataEl.textContent ?? '{}')
  createRoot(rootEl).render(<SharedConfirmPage payload={payload} />)
}
