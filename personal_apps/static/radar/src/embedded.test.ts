// Where the opening board comes from: embedded by Flask in production, fetched
// from the API under the Vite dev harness (static/radar/dev.html), which has
// no Jinja to embed it.

import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import { loadPayload, parsePayload } from './embedded'

const board = '{"rows":[],"market":"de"}'

function embed(text: string | null) {
  document.body.innerHTML = text === null
    ? '<div id="radar-root"></div>'
    : `<script type="application/json" id="radar-data">${text}</script><div id="radar-root"></div>`
}

beforeEach(() => {
  window.history.replaceState(null, '', '/static/radar/dev.html?market=de&window=12')
})
afterEach(() => {
  vi.unstubAllGlobals()
  document.body.innerHTML = ''
})

describe('the opening board', () => {
  it('is the embedded one when the document carries it, without a request', async () => {
    embed(board)
    const spy = vi.fn()
    vi.stubGlobal('fetch', spy)

    const payload = await loadPayload()

    expect(payload?.market).toBe('de')
    expect(spy).not.toHaveBeenCalled()
  })

  it('is fetched for the page\'s own query when nothing is embedded', async () => {
    embed(null)
    const spy = vi.fn(async (_url: string) => ({
      ok: true, redirected: false, text: async () => board,
    }))
    vi.stubGlobal('fetch', spy)

    const payload = await loadPayload()

    expect(payload?.market).toBe('de')
    expect(spy.mock.calls[0]?.[0]).toBe('/radar/api/board?market=de&window=12')
  })

  it('is null when the fetch lands on the login page', async () => {
    /* @login_required redirects rather than 401s, and fetch follows it
       transparently -- so a signed-out harness gets HTML with a 200. */
    embed(null)
    vi.stubGlobal('fetch', vi.fn(async () => ({
      ok: true, redirected: true, text: async () => '<!doctype html>',
    })))

    expect(await loadPayload()).toBeNull()
  })

  it('is null when the network fails, never a throw into React', async () => {
    embed(null)
    vi.stubGlobal('fetch', vi.fn(async () => { throw new Error('offline') }))

    expect(await loadPayload()).toBeNull()
  })
})

describe('a document that was served while the board was being built', () => {
  const shell = '{"rows":null,"pending":true,"busy":false,"market":"us"}'

  it('opens on the waiting shell rather than on nothing at all', () => {
    // `rows` is normally the check, because it is what the page IS. A null
    // one under `pending` is the store saying "there is no board yet" in as
    // many words -- an answer, with a selection to draw and a line to say --
    // and rejecting it would replace a page that says "calculating" with a
    // page that says nothing.
    expect(parsePayload(shell)?.pending).toBe(true)
    expect(parsePayload(shell)?.rows).toBeNull()
  })

  it('still refuses a null board that claims nobody is building one', () => {
    expect(parsePayload('{"rows":null,"market":"us"}')).toBeNull()
    expect(parsePayload('{"rows":null,"pending":false,"busy":false}')).toBeNull()
  })
})
