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
