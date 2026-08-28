import { createRoot } from 'react-dom/client'

import { BoardPage } from '../board/BoardPage'
import { Boundary, Broken } from '../Broken'
import { parsePayload } from '../embedded'

// The first board is embedded in the document by features/radar/routes/views.py
// rather than fetched after mount: the server already had it, and a spinner on
// arrival for data that was in hand is a self-inflicted wait.
//
// It is checked before it is trusted -- see embedded.ts. An unreadable payload
// used to leave a blank white page, which is the one outcome worse than any
// error message.
const dataEl = document.getElementById('radar-data')
const rootEl = document.getElementById('radar-root')

if (rootEl) {
  const payload = parsePayload(dataEl?.textContent)
  createRoot(rootEl).render(
    payload
      ? (
        // The outermost net. A throw anywhere the inner boundaries do not
        // cover still leaves a page with words on it.
        <Boundary label="The board">
          <BoardPage initial={payload} />
        </Boundary>
      )
      : <Broken detail="The board embedded in this page was unreadable." />,
  )
}
