import { HistoryPage } from '../history/HistoryPage'
import type { HistoryPayload } from '../history/types'
import { mount } from '../mount'

// Embedded, not fetched: this page sees the whole history, and search and the
// export selection are client-side over the rows it already has.
mount<HistoryPayload>((payload) => <HistoryPage payload={payload} />)
