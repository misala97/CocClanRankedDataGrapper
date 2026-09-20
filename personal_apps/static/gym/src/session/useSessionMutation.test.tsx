import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { act, render, screen, waitFor } from '@testing-library/react'
import type { ReactNode } from 'react'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { MutationFailed } from './api'
import { useSaveState } from './stores'
import { useSessionMutation, sessionKey } from './useSessionMutation'
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
  useSaveState.setState({ pending: 0, error: null, locked: {} })
})

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
    expect(useSaveState.getState().error?.message)
      .toBe(new MutationFailed('network').germanMessage)
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

  it('takes the banner down once a write actually lands', async () => {
    useSaveState.getState().fail('alte Meldung', vi.fn())
    const { fire } = harness(() => Promise.resolve(payload))
    expect(screen.getByText('Nicht gespeichert')).toBeInTheDocument()

    fire()
    await waitFor(() => {
      expect(screen.queryByText('Nicht gespeichert')).not.toBeInTheDocument()
    })
  })
})
