import { createRoot } from 'react-dom/client'
import { StartPage } from '../start/StartPage'
import type { HeutePayload } from '../start/types'
import { reloadWhenRestored } from '../fresh'

reloadWhenRestored()

const dataEl = document.getElementById('gym-data')
const rootEl = document.getElementById('gym-root')

if (dataEl && rootEl) {
  const payload: HeutePayload = JSON.parse(dataEl.textContent ?? '{}')
  createRoot(rootEl).render(<StartPage payload={payload} />)
}
