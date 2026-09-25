import { SessionIsland } from '../session/SessionIsland'
import type { SessionDetailPayload } from '../session/types'
import { mount } from '../mount'

// The payload is embedded in the document rather than fetched, so the first
// render has everything and there is no waterfall on load. It is the same
// object /gym/session/<id>/detail.json serves, built once by
// routes.workout._live_data -- so the page and any refetch cannot disagree
// about which exercise is live.
mount<SessionDetailPayload>((payload) => <SessionIsland initial={payload} />)
