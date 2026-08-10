import { createRoot } from 'react-dom/client'
import { StatistikPage } from '../statistik/StatistikPage'
import type { StatistikPayload } from '../statistik/types'

const dataEl = document.getElementById('gym-data')
const rootEl = document.getElementById('gym-root')

if (dataEl && rootEl) {
  const payload: StatistikPayload = JSON.parse(dataEl.textContent ?? '{}')
  createRoot(rootEl).render(<StatistikPage payload={payload} />)
}
