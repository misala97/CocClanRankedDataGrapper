import { createRoot } from 'react-dom/client'

import { BoardPage } from '../board/BoardPage'
import { Boundary, Broken } from '../Broken'
import { loadPayload } from '../embedded'

// The first board is embedded in the document by features/radar/routes/views.py
// rather than fetched after mount: the server already had it, and a spinner on
// arrival for data that was in hand is a self-inflicted wait. Under the Vite
// dev harness (static/radar/dev.html) nothing is embedded and loadPayload
// fetches it instead; production never takes that path.
//
// It is checked before it is trusted -- see embedded.ts. An unreadable payload
// used to leave a blank white page, which is the one outcome worse than any
// error message.
const embedded = document.getElementById('radar-data') !== null
const rootEl = document.getElementById('radar-root')

if (rootEl) {
  const root = createRoot(rootEl)
  void loadPayload().then((payload) => {
    root.render(
      payload
        ? (
          // The outermost net. A throw anywhere the inner boundaries do not
          // cover still leaves a page with words on it.
          <Boundary label="The board">
            <BoardPage initial={payload} />
          </Boundary>
        )
        : (
          <Broken detail={embedded
            ? 'The board embedded in this page was unreadable.'
            : 'The board could not be fetched from /radar/api/board. '
              + 'Sign in to the Flask server first.'} />
        ),
    )
  })
}
