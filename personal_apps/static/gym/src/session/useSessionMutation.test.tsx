import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { act, render, screen, waitFor } from '@testing-library/react'
import type { ReactNode } from 'react'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { MutationFailed } from './api'
import { useSaveState } from './stores'
import { useSessionMutation, sessionKey, type WriteOptions } from './useSessionMutation'
import { SaveErrorBanner } from './components/SaveErrorBanner'
import { payload } from './types.test-d'

/**
 * The banner and the mutation are tested together on purpose: the bug this
 * pins was not in either of them but in the ORDER their callbacks run.
 * onSettled fires immediately after onError, so a store that cleared the
 * error there removed the banner in the same tick it was raised -- a lost
 * write reverted the screen and said nothing.
 */
beforeEach(() => {
  useSaveState.setState(useSaveState.getInitialState(), true)
})

/** What the refetch after a refused write finds: the workout, or a status. */
function serverHas(answer: typeof payload | number) {
  vi.stubGlobal('fetch', vi.fn(async () => (typeof answer === 'number'
    ? new Response('', { status: answer })
    : new Response(JSON.stringify(answer), {
      status: 200, headers: { 'Content-Type': 'application/json' },
    }))))
}

function harness(run: () => Promise<typeof payload>) {
  const client = new QueryClient({
    defaultOptions: { mutations: { retry: false }, queries: { retry: false } },
  })
  client.setQueryData(sessionKey(payload.session.id), payload)

  let mutate: () => void = () => {}
  function Probe() {
    const mutation = useSessionMutation(payload.session.id, run)
    mutate = () => mutation.mutate([])
    return <SaveErrorBanner />
  }
  const wrapper = ({ children }: { children: ReactNode }) => (
    <QueryClientProvider client={client}>{children}</QueryClientProvider>
  )
  render(<Probe />, { wrapper })
  return { fire: () => act(() => { mutate() }) }
}

describe('useSessionMutation', () => {
  it('leaves the banner up after a write fails', async () => {
    const { fire } = harness(() => Promise.reject(new MutationFailed('network')))
    fire()

    await waitFor(() => {
      expect(screen.getByText('Nicht gespeichert')).toBeInTheDocument()
    })
    // Past the point where onSettled has run and the write is no longer
    // in flight -- the banner is still the current truth.
    await waitFor(() => expect(useSaveState.getState().pending).toBe(0))
    expect(screen.getByText('Nicht gespeichert')).toBeInTheDocument()
    expect(useSaveState.getState().errors.map((e) => e.message))
      .toEqual([new MutationFailed('network').germanMessage])
  })

  it('says why a refused value was refused, and offers no retry for it', async () => {
    const { fire } = harness(() => Promise.reject(
      new MutationFailed('invalid', 'Wiederholungen: bitte eine ganze Zahl von 1 bis 1000.')))
    fire()

    await waitFor(() => {
      expect(screen.getByRole('alert'))
        .toHaveTextContent('Wiederholungen: bitte eine ganze Zahl von 1 bis 1000.')
    })
    expect(useSaveState.getState().errors[0]?.retry).toBeNull()
  })

  /** Two writes, each with an optimistic guess, answered by hand. */
  function twoWrites() {
    const client = new QueryClient({
      defaultOptions: { mutations: { retry: false }, queries: { retry: false } },
    })
    const key = sessionKey(payload.session.id)
    client.setQueryData(key, payload)

    const started: string[] = []
    const answer: Record<string, (value: typeof payload) => void> = {}
    const refuse: Record<string, (error: MutationFailed) => void> = {}
    const run = (name: string) => {
      started.push(name)
      return new Promise<typeof payload>((resolve, reject) => {
        answer[name] = resolve
        refuse[name] = reject
      })
    }
    const named = (name: string) => ({ ...payload, session: { ...payload.session, name } })

    let mutate: (name: string) => void = () => {}
    function Probe() {
      const mutation = useSessionMutation(payload.session.id, run,
        (current, name: string) => ({
          ...current, session: { ...current.session, name: `guess ${name}` },
        }))
      mutate = (name) => mutation.mutate([name])
      return null
    }
    render(
      <QueryClientProvider client={client}><Probe /></QueryClientProvider>)
    const shown = () => client.getQueryData<typeof payload>(key)!.session.name
    return { client, key, started, answer, refuse, named, shown,
      fire: (name: string) => act(() => { mutate(name) }) }
  }

  it('sends one write at a time, in the order they were made', async () => {
    // Two drops in quick succession, or the arrow-key path (a POST per key
    // press), used to put two reorders on the server at once -- each read the
    // same rows and wrote its own half, and the queue came back as a blend.
    const { started, answer, named, fire } = twoWrites()
    fire('first')
    fire('second')

    await waitFor(() => expect(started).toEqual(['first']))
    await act(async () => { answer.first!(named('first')) })
    await waitFor(() => expect(started).toEqual(['first', 'second']))
    await act(async () => { answer.second!(named('second')) })
  })

  it('does not let an older answer undo a newer guess', async () => {
    // The first answer describes the screen BEFORE the second write. Applying
    // it wholesale put the row the lifter had just dropped back where it came
    // from for as long as the second request took -- over a second on gym
    // wifi -- and then moved it again.
    const { answer, named, shown, fire } = twoWrites()
    fire('first')
    fire('second')
    await waitFor(() => expect(shown()).toBe('guess second'))

    await act(async () => { answer.first!(named('first')) })
    expect(shown()).toBe('guess second')

    await waitFor(() => expect(answer.second).toBeDefined())
    await act(async () => { answer.second!(named('second')) })
    await waitFor(() => expect(shown()).toBe('second'))
  })

  it('asks the server again after a failed write', async () => {
    // Rolling back restores the screen from before THIS write, which may still
    // hold an earlier write's guess whose answer was skipped above. Only the
    // server knows what is actually stored.
    const { client, key, refuse, fire } = twoWrites()
    fire('first')
    await waitFor(() => expect(refuse.first).toBeDefined())
    await act(async () => { refuse.first!(new MutationFailed('network')) })

    await waitFor(() => expect(client.getQueryState(key)?.isInvalidated).toBe(true))
  })

  it('reloads instead of bannering a write to a workout that has finished', async () => {
    // The page for a finished workout is the debrief, and the reload is what
    // shows it. A retry could never land.
    const reload = vi.fn()
    vi.stubGlobal('location', { ...window.location, reload })
    serverHas({ ...payload, session: { ...payload.session, finished_at: '2026-09-24T09:00:00' } })
    const { fire } = harness(() => Promise.reject(new MutationFailed('finished')))
    fire()
    await waitFor(() => expect(reload).toHaveBeenCalled())
    expect(screen.queryByText('Nicht gespeichert')).not.toBeInTheDocument()
    vi.unstubAllGlobals()
  })

  /** Two different writes to the same row: which write it was, not which row,
   *  decides whether a success answers a failure. */
  function twoWriters(failing: (id: number) => Promise<typeof payload>) {
    const client = new QueryClient({
      defaultOptions: { mutations: { retry: false }, queries: { retry: false } },
    })
    client.setQueryData(sessionKey(payload.session.id), payload)
    const fire: Record<'a' | 'b', (id: number) => void> = { a: () => {}, b: () => {} }
    function Probe() {
      const a = useSessionMutation(payload.session.id, failing)
      const b = useSessionMutation(payload.session.id,
        (_id: number) => Promise.resolve(payload))
      fire.a = (id) => a.mutate([id])
      fire.b = (id) => b.mutate([id])
      return <SaveErrorBanner />
    }
    render(<QueryClientProvider client={client}><Probe /></QueryClientProvider>)
    return { fire: (which: 'a' | 'b', id: number) => act(() => { fire[which](id) }) }
  }

  it('takes the banner down once the failed write lands', async () => {
    const { fire } = twoWriters(vi.fn()
      .mockRejectedValueOnce(new MutationFailed('network'))
      .mockResolvedValueOnce(payload))
    fire('a', 7)
    await waitFor(() => expect(screen.getByText('Nicht gespeichert')).toBeInTheDocument())

    fire('a', 7)
    await waitFor(() => {
      expect(screen.queryByText('Nicht gespeichert')).not.toBeInTheDocument()
    })
  })

  it('keeps a lost write on the banner while other writes land (G-139)', async () => {
    // It was rolled back; a later success elsewhere does not save it. Not a
    // different row (8), and not a different write to the SAME row (b, 7).
    const { fire } = twoWriters(vi.fn()
      .mockRejectedValueOnce(new MutationFailed('network'))
      .mockResolvedValue(payload))
    fire('a', 7)
    await waitFor(() => expect(screen.getByText('Nicht gespeichert')).toBeInTheDocument())

    fire('a', 8)
    fire('b', 7)
    await waitFor(() => expect(useSaveState.getState().pending).toBe(0))
    expect(screen.getByText('Nicht gespeichert')).toBeInTheDocument()
    expect(useSaveState.getState().errors).toHaveLength(1)
  })

  /** One write with options, fired with any number. */
  function writer(run: (value: number) => Promise<typeof payload>,
    options: WriteOptions<[number]>) {
    const client = new QueryClient({
      defaultOptions: { mutations: { retry: false }, queries: { retry: false } },
    })
    client.setQueryData(sessionKey(payload.session.id), payload)
    let mutate: (value: number) => void = () => {}
    function Probe() {
      const mutation = useSessionMutation(payload.session.id, run, undefined, options)
      mutate = (value) => mutation.mutate([value])
      return <SaveErrorBanner />
    }
    render(<QueryClientProvider client={client}><Probe /></QueryClientProvider>)
    return { fire: (value: number) => act(() => { mutate(value) }) }
  }

  it('lets a write that states the whole of something answer its earlier failure (B4 review)', async () => {
    // The newest order is the lifter's intent. Kept, the failed older one
    // was a retry that put back an order they had already changed.
    const { fire } = writer(vi.fn()
      .mockRejectedValueOnce(new MutationFailed('network'))
      .mockResolvedValue(payload), { key: () => 'order' })
    fire(1)
    await waitFor(() => expect(screen.getByText('Nicht gespeichert')).toBeInTheDocument())

    fire(2)
    await waitFor(() => {
      expect(screen.queryByText('Nicht gespeichert')).not.toBeInTheDocument()
    })
  })

  it('keeps a failed add on the banner when the next add lands (B4 review)', async () => {
    // Every add is new work: the second set does not save the first.
    const { fire } = writer(vi.fn()
      .mockRejectedValueOnce(new MutationFailed('network'))
      .mockResolvedValue(payload), { key: () => null })
    fire(7)
    await waitFor(() => expect(screen.getByText('Nicht gespeichert')).toBeInTheDocument())

    fire(7)
    await waitFor(() => expect(useSaveState.getState().pending).toBe(0))
    expect(useSaveState.getState().errors).toHaveLength(1)
  })

  it('offers no retry for a write about this moment only (B4 review)', async () => {
    // Sent again a minute later, "+15 s" would move a different rest.
    const { fire } = writer(() => Promise.reject(new MutationFailed('network')),
      { ephemeral: true })
    fire(15)
    await waitFor(() => expect(useSaveState.getState().errors).toHaveLength(1))
    expect(useSaveState.getState().errors[0]?.retry).toBeNull()
  })

  it('marks a failure only a fresh page can fix (B4 review)', async () => {
    const { fire } = writer(() => Promise.reject(new MutationFailed('forbidden')), {})
    fire(1)
    await waitFor(() => expect(useSaveState.getState().errors).toHaveLength(1))
    expect(useSaveState.getState().errors[0]?.remedy).toBe('reload')
  })

  it('marks a lost write that is new work each time for the lifter to resend (B4 re-review)', async () => {
    const { fire } = writer(() => Promise.reject(new MutationFailed('network')),
      { idempotent: false })
    fire(1)
    await waitFor(() => expect(useSaveState.getState().errors).toHaveLength(1))
    expect(useSaveState.getState().errors[0]?.remedy).toBe('manual')
  })

  it('lets another kind of write to the same set answer its failure (B4 re-review)', async () => {
    // Each hook named its failures for itself: a set deleted after its tick
    // was lost left the tick on the banner, and its resend hit a set that
    // was gone.
    const tick = writer(() => Promise.reject(new MutationFailed('network')),
      { key: (id) => `set-${id}:done` })
    const remove = writer(() => Promise.resolve(payload), { key: (id) => `set-${id}` })
    tick.fire(7)
    await waitFor(() => expect(useSaveState.getState().errors).toHaveLength(1))

    remove.fire(7)
    await waitFor(() => expect(useSaveState.getState().errors).toHaveLength(0))
  })

  it('drops a refused write whose workout is still running (B4 re-review)', async () => {
    // A resent delete that had landed after all: the set is gone, the
    // workout is not. It reloaded the page under the lifter.
    const reload = vi.fn()
    vi.stubGlobal('location', { ...window.location, reload })
    serverHas(payload)
    const { fire } = writer(vi.fn()
      .mockRejectedValueOnce(new MutationFailed('network'))
      .mockRejectedValueOnce(new MutationFailed('finished')), { key: (id) => `set-${id}` })
    fire(7)
    await waitFor(() => expect(useSaveState.getState().errors).toHaveLength(1))

    fire(7)
    await waitFor(() => expect(useSaveState.getState().errors).toHaveLength(0))
    await waitFor(() => expect(useSaveState.getState().pending).toBe(0))
    expect(reload).not.toHaveBeenCalled()
  })

  it('goes home when a refused write\'s workout is gone (B4 re-review)', async () => {
    // Discarded on the other phone, or by the three-hour rule: there is no
    // page for it to reload into.
    const reload = vi.fn()
    const assign = vi.fn()
    vi.stubGlobal('location', { ...window.location, reload, assign })
    serverHas(404)
    const { fire } = writer(() => Promise.reject(new MutationFailed('finished')), {})
    fire(1)
    await waitFor(() => expect(assign).toHaveBeenCalledWith('/gym'))
    expect(reload).not.toHaveBeenCalled()
  })
})
