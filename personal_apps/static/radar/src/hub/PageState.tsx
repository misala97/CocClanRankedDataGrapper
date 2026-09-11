// The states every hub page has to be able to be in.
//
// Named, because a page that only knows "data" and "no data" tells the reader
// the same thing when the sources were quiet, when the request failed, when
// the session expired, when nothing has loaded yet and when the board is
// still being built somewhere else. Those are different situations with
// different next actions.
//
// The one rule they share: a measured emptiness is a result, not a failure. A
// board with no rows says the floor excluded everything, not that something
// broke -- and a board nobody has built yet is neither: it says so, and never
// wears the empty board's words. A refresh that failed keeps the last good
// answer on screen with its age, because data that was true a minute ago
// beats a blank page.
import { useEffect, useState } from 'react'
import type { ReactNode } from 'react'

import { BoardUnavailable } from '../api'
import { humanAge } from '../format'
import { ageAt, pastFresh, refreshDue, untilExpired } from '../pending'
import type { BoardPayload } from '../types'

export function Loading({ label }: { label: string }) {
  return (
    <div className="rh-panel rh-pad" role="status" aria-live="polite">
      <p className="muted small">{label}</p>
      <div className="rh-skeleton half" style={{ marginTop: 14 }} />
      <div className="rh-skeleton large" />
      <div className="rh-skeleton" />
    </div>
  )
}

/** Measured, and empty. Never rendered for a request that did not answer, and
 *  never for a board that has not been built. */
export function Empty({ title, children }: { title: string; children: ReactNode }) {
  return (
    <div className="rh-empty">
      <h2>{title}</h2>
      <p>{children}</p>
    </div>
  )
}

/** The reader is signed out. Nothing else on the page can be trusted, and
 *  reloading is the fix -- which is exactly what forbidden is not. */
export function SignedOut() {
  return (
    <div className="rh-notice red" role="alert">
      <div>
        <strong>Session expired.</strong>
        <p>Reload the page to sign in again. Nothing here is up to date.</p>
      </div>
    </div>
  )
}

export function Forbidden({ what }: { what: string }) {
  return (
    <div className="rh-notice amber" role="alert">
      <div>
        <strong>{what} is for administrators.</strong>
        <p>You are signed in; this account is not allowed to read it.
           Reloading will not change that.</p>
      </div>
    </div>
  )
}

/** A refresh failed while data from a previous one is still on screen.
 *  The timestamp is not decoration: it is the difference between stale data
 *  and a lie.
 *
 *  Its Retry is the page's one while it is up -- the age line drops its own
 *  -- and it is the same guarded ask as every other: it joins a request
 *  already out. */
export function StaleNotice({ error, since, onRetry }: {
  error: unknown
  since: string | null
  onRetry?: () => void
}) {
  const reason = error instanceof BoardUnavailable ? error.message
    : 'The last refresh did not complete.'
  return (
    <div className="rh-notice amber" role="status">
      <div>
        <strong>Showing the last answer.</strong>
        <p>{reason}{since ? ` Loaded ${since}.` : ''}</p>
      </div>
      {onRetry ? <RetryButton onRetry={onRetry} /> : null}
    </div>
  )
}

/** Nothing loaded and nothing to fall back on. */
export function Unavailable({ error, retry }: { error: unknown; retry?: () => void }) {
  if (error instanceof BoardUnavailable && error.reason === 'session') {
    return <SignedOut />
  }
  const message = error instanceof Error ? error.message : 'Something went wrong.'
  return (
    <div className="rh-empty">
      <h2>This page could not be loaded.</h2>
      <p>{message}</p>
      {retry ? (
        <button type="button" className="rh-button" onClick={retry}>Try again</button>
      ) : null}
    </div>
  )
}

/** A hash nobody implemented. It says so and offers the way back, rather than
 *  silently redirecting somewhere the reader did not ask for. */
export function Missing({ onHome }: { onHome: () => void }) {
  return (
    <div className="rh-empty">
      <h2>There is nothing at this address.</h2>
      <p>
        The link may be from an older version of Radar, or point at a page
        that has not been built yet.
      </p>
      <button type="button" className="rh-button primary" onClick={onHome}>
        Go to the overview
      </button>
    </div>
  )
}

// --- a board somebody else is building -----------------------------------
//
// The words are the old board's (list/ListPane.tsx), so the two surfaces say
// one thing about one queue. Each stands where the page's rows would, under
// the page's own heading and controls: the reader who is tired of waiting can
// ask a different question, which is often one the store has already
// answered for somebody else.

function RetryButton({ onRetry }: { onRetry: () => void }) {
  return (
    <button type="button" className="rh-button rh-retry" onClick={onRetry}>
      Retry
    </button>
  )
}

/** No board yet: it is queued or being built.
 *
 *  `delayed` is the wait's own clock, kept by the page (queries.useBoard)
 *  and counted from when the wait for THIS selection began -- not from the
 *  last answer, which a poll answering "still pending" every few seconds
 *  would keep resetting. Past it the wait stops being a moment, and the
 *  reader deserves both an admission and a way out. */
export function Pending({ delayed, onRetry }: {
  delayed: boolean
  onRetry?: () => void
}) {
  return (
    <div className="rh-notice rh-wait" role="status">
      <div>
        <strong>{delayed ? 'Still calculating…' : 'Calculating this board…'}</strong>
        {delayed ? (
          <p>
            A board nobody has asked for recently is built from scratch.
            Change the window or the feeds to ask for one that may already be
            built.
          </p>
        ) : null}
      </div>
      {delayed && onRetry ? <RetryButton onRetry={onRetry} /> : null}
    </div>
  )
}

/** The generation is refusing work. Busy is not a queue: there is no
 *  position to be near the front of and nothing to be patient about, so it
 *  says why at once and offers the way out at once. */
export function Busy({ onRetry }: { onRetry?: () => void }) {
  return (
    <div className="rh-notice rh-wait busy" role="status">
      <div>
        <strong>The board is busy with other selections.</strong>
        <p>
          It is building boards other readers asked for first. Change the
          window or the feeds to ask for one that may already be built.
        </p>
      </div>
      {onRetry ? <RetryButton onRetry={onRetry} /> : null}
    </div>
  )
}

/** The builds for this selection are failing, not merely slow, and there is
 *  no earlier board to show instead. Red and an alert rather than the calm
 *  waiting line, because "this is taking a while" would be the wrong thing to
 *  keep saying. */
export function FailedNotice({ onRetry }: { onRetry?: () => void }) {
  return (
    <div className="rh-notice red rh-wait" role="alert">
      <div>
        <strong>This board could not be built.</strong>
        <p>Radar is still retrying.</p>
      </div>
      {onRetry ? <RetryButton onRetry={onRetry} /> : null}
    </div>
  )
}

/** An age at the resolution the state it describes actually moves at:
 *  seconds below a minute, because the line ticks every second; minutes below
 *  ninety; then humanAge's hours and days. The old board's line prints the
 *  same units (list/ListPane.tsx), so the two surfaces never state one age
 *  two ways. */
export function boardAge(seconds: number): string {
  if (seconds < 60) return `${Math.max(0, Math.floor(seconds))}s`
  const minutes = Math.floor(seconds / 60)
  return minutes < 90 ? `${minutes}m` : humanAge(seconds)
}

/** When this board was calculated -- always, in as many words, and what is
 *  being done about it once that stops being recent.
 *
 *  Read through the same functions the page acts on (../pending.ts), so the
 *  line can neither claim a refresh the page is not waiting on nor deny one
 *  it is. Every board past its fresh bound is marked stale here, whoever
 *  built it (ruling §5); the word after the age says which of three things
 *  follows. Nothing at all for a board nobody has built: inventing an age for
 *  a waiting shell would be the freshness stamp's one unforgivable lie.
 */
export function AgeLine({ board, received, stalled = false, onRetry }: {
  board: BoardPayload
  /** When this page received the board. */
  received: number
  /** Nothing is fetching a replacement: the last request failed and no wait
   *  is running. Only an expired board has anything to say about it. */
  stalled?: boolean
  /** Offered beside a board nothing else is going to ask about. Omitted
   *  while the page's failure notice is up with a Retry of its own. */
  onRetry?: () => void
}) {
  // The page has no other reason to redraw while it sits untouched, which is
  // precisely the situation this describes.
  const [, tick] = useState(0)
  useEffect(() => {
    const timer = setInterval(() => tick((n) => n + 1), 1000)
    return () => clearInterval(timer)
  }, [])

  const now = Date.now()
  const age = ageAt(board, received, now)
  if (age === null) return null
  const retry = onRetry
    ? <button type="button" onClick={onRetry}>Retry</button> : null
  // Past the hard expiry the age has stopped being worth printing: the rows
  // describe a rolling window that has moved on.
  const expiry = untilExpired(board, received, now)
  if (expiry !== null && expiry < 0) {
    return (
      <span className="rh-age expired">
        {stalled
          // The ask for a replacement failed and nothing else is asking.
          // Promising a recalculation then is the line describing work the
          // page is not doing.
          ? <><b>Expired</b>{retry}</>
          : <b>Expired, recalculating</b>}
      </span>
    )
  }
  const stale = board.stale || pastFresh(board, received, now)
  return (
    <span className={stale ? 'rh-age stale' : 'rh-age'}>
      Calculated {boardAge(age)} ago
      {board.failed
        // A verdict on the queue, not on these rows: they are the last board
        // that built. In place of "refreshing", never beside it -- a refresh
        // that is failing is not one that is happening.
        ? <> · <b>Last refresh failed</b></>
        : !stale ? null
        // A refresh the page is waiting on. Its own quiet class: a queued
        // refresh is not a caution on rows that are still the last real ones.
        : refreshDue(board, received, now)
          ? <> · <b className="queued">refreshing</b></>
        // Built by a worker for itself: nothing is queued behind it, and the
        // ask it would take -- a synchronous build -- is the reader's.
        : <> · <b>not refreshed</b>{retry}</>}
    </span>
  )
}
