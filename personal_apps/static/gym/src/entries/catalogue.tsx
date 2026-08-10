import { createRoot } from 'react-dom/client'
import { CataloguePage } from '../catalogue/CataloguePage'
import type { CataloguePayload } from '../catalogue/types'

// The payload is embedded rather than fetched: the page's three sorts and its
// search are re-orderings of these same rows, so there is nothing to go back
// to the server for.
const dataEl = document.getElementById('gym-data')
const rootEl = document.getElementById('gym-root')

if (dataEl && rootEl) {
  const payload: CataloguePayload = JSON.parse(dataEl.textContent ?? '{}')
  createRoot(rootEl).render(<CataloguePage payload={payload} />)
}
