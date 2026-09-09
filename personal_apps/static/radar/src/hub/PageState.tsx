// The states every hub page has to be able to be in.
//
// Five of them, named, because a page that only knows "data" and "no data"
// tells the reader the same thing when the sources were quiet, when the
// request failed, when the session expired and when nothing has loaded yet.
// Those are four different situations with four different next actions.
//
// The one rule they share: a measured emptiness is a result, not a failure. A
// board with no rows says the floor excluded everything, not that something
// broke -- and a refresh that failed keeps the last good answer on screen with
// its timestamp, because data that was true a minute ago beats a blank page.
import type { ReactNode } from 'react'

import { BoardUnavailable } from '../api'

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

/** Measured, and empty. Never rendered for a request that did not answer. */
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
 *  and a lie. */
export function StaleNotice({ error, since }: { error: unknown; since: string | null }) {
  const reason = error instanceof BoardUnavailable ? error.message
    : 'The last refresh did not complete.'
  return (
    <div className="rh-notice amber" role="status">
      <div>
        <strong>Showing the last answer.</strong>
        <p>{reason}{since ? ` Loaded ${since}.` : ''}</p>
      </div>
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
