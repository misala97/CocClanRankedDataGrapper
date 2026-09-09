import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { createRoot } from 'react-dom/client'

import { Boundary, Broken } from '../Broken'
import { parsePayload } from '../embedded'
import { Hub } from '../hub/Hub'
import type { BoardPayload } from '../types'

// The opt-in hub at /radar/hub/. The board island at /radar/ is untouched and
// stays available: this route is here to be reviewed, and switching the root
// to it is a separate decision.
//
// The payload is embedded by the Flask view rather than fetched after mount --
// the server already had it, and a spinner for data in hand is a self-inflicted
// wait. It is checked before it is trusted: an unreadable payload used to leave
// a blank white page, which is the one outcome worse than an error message.

/** One client per page session. Not a module singleton shared across mounts:
 *  the cache holds board data scoped to the account that fetched it, and a
 *  second mount inheriting the first one's answers is how one reader sees
 *  another's marks. */
const client = new QueryClient({
  defaultOptions: {
    queries: {
      // Every hub query names its own refetch interval. What matters here is
      // that a tab the reader is not looking at does not poll.
      refetchOnWindowFocus: false,
      refetchIntervalInBackground: false,
    },
  },
})

const dataEl = document.getElementById('radar-hub-data')
const rootEl = document.getElementById('radar-hub-root')

if (rootEl) {
  const root = createRoot(rootEl)
  const parsed = readShell(dataEl?.textContent)
  root.render(
    parsed
      ? (
        <Boundary label="The hub">
          <QueryClientProvider client={client}>
            <Hub initial={parsed.board} isAdmin={parsed.isAdmin} />
          </QueryClientProvider>
        </Boundary>
      )
      : <Broken detail="The board embedded in this page was unreadable." />,
  )
}

/** The shell payload, validated at the boundary.
 *
 *  `is_admin` is a rendering hint and nothing more -- the admin API enforces
 *  authorization itself and does not trust this flag. A missing or non-boolean
 *  value therefore resolves to false rather than failing the page: the worst
 *  case is an admin who has to reload, not a stranger who gets a nav link.
 */
function readShell(text: string | null | undefined):
  { board: BoardPayload; isAdmin: boolean } | null {
  try {
    const raw = JSON.parse(text ?? '') as { board?: unknown; is_admin?: unknown }
    const board = parsePayload(JSON.stringify(raw?.board))
    if (!board) return null
    return { board, isAdmin: raw?.is_admin === true }
  } catch {
    return null
  }
}
