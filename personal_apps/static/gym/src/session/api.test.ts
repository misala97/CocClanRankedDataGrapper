import { afterEach, describe, expect, it, vi } from 'vitest'
import fixture from './__fixtures__/session-payload.json'
import { api, fetchSession, rememberCatalogue } from './api'
import type { SessionDetailPayload } from './types'

const page = fixture as unknown as SessionDetailPayload

/** What a write answers since G-140: the payload without the add sheet's list. */
function withoutList(payload: SessionDetailPayload) {
  const { exercises: _exercises, list_groups: _groups, ...reply } = payload
  return reply
}

function answering(body: unknown) {
  vi.stubGlobal('fetch', vi.fn(async () => new Response(JSON.stringify(body), {
    status: 200, headers: { 'Content-Type': 'application/json' },
  })))
}

describe('a write answer and the add sheet list (G-140)', () => {
  afterEach(() => { vi.unstubAllGlobals() })

  it('gets the list the page came with', async () => {
    rememberCatalogue(page)
    answering(withoutList(page))

    const answer = await api.skipRest(page.session.id)

    expect(answer.exercises).toBe(page.exercises)
    expect(answer.list_groups).toBe(page.list_groups)
    expect(answer.sets_done).toBe(page.sets_done)
  })

  it('asks for the answer without the list', async () => {
    // Only a write that asks gets it without: a page from before G-140,
    // still open across the deploy, reads the list off every answer.
    answering(withoutList(page))
    await api.skipRest(page.session.id)
    const [, init] = (fetch as ReturnType<typeof vi.fn>).mock.calls[0] as [string, RequestInit]
    expect(new Headers(init.headers).get('X-Gym-Catalogue')).toBe('kept')
  })

  it('gets the list the last read brought, not the page one', async () => {
    rememberCatalogue(page)
    const fresher = { ...page, exercises: page.exercises.slice(0, 1), list_groups: ['Brust'] }
    answering(fresher)
    await fetchSession(page.session.id)
    answering(withoutList(page))

    const answer = await api.skipRest(page.session.id)

    expect(answer.exercises).toEqual(fresher.exercises)
    expect(answer.list_groups).toEqual(['Brust'])
  })

  it('keeps a list an answer does carry', async () => {
    rememberCatalogue(page)
    const own = { ...page, exercises: [], list_groups: ['Beine'] }
    answering(own)

    const answer = await api.skipRest(page.session.id)

    expect(answer.exercises).toEqual([])
    expect(answer.list_groups).toEqual(['Beine'])
  })
})
