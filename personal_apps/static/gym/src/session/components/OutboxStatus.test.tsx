import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { OutboxStatus } from './OutboxStatus'
import { useOutbox, type OutboxState } from '../stores'

beforeEach(() => {
  useOutbox.setState(useOutbox.getInitialState(), true)
})

const holding = (state: OutboxState, count: number) =>
  useOutbox.getState().publish({ state, count, setIds: [] })

describe('OutboxStatus', () => {
  it('says nothing while writes simply go out -- a write out for a moment is no news', () => {
    for (const state of ['idle', 'sending'] as const) {
      holding(state, 2)
      const { container, unmount } = render(<OutboxStatus onSendNow={vi.fn()} onReload={vi.fn()} />)
      expect(container).toBeEmptyDOMElement()
      unmount()
    }
  })

  it('says what waits on the phone once a try failed, and sends on a tap', async () => {
    const user = userEvent.setup()
    const onSendNow = vi.fn()
    holding('waiting', 1)
    const { rerender } = render(<OutboxStatus onSendNow={onSendNow} onReload={vi.fn()} />)
    expect(screen.getByRole('status'))
      .toHaveTextContent('Wartet auf Verbindung · 1 Änderung auf diesem Handy')
    await user.click(screen.getByRole('button', { name: 'Jetzt senden' }))
    expect(onSendNow).toHaveBeenCalledOnce()

    holding('waiting', 3)
    rerender(<OutboxStatus onSendNow={onSendNow} onReload={vi.fn()} />)
    expect(screen.getByRole('status')).toHaveTextContent('3 Änderungen auf diesem Handy')
  })

  it('waits for a fresh page, not the connection, after a lapsed login -- and offers it', async () => {
    // The banner's "Neu laden" goes with "Ausblenden", and the installed
    // app has no reload of its own (B6 re-review).
    const user = userEvent.setup()
    const onSendNow = vi.fn()
    const onReload = vi.fn()
    holding('blocked', 2)
    render(<OutboxStatus onSendNow={onSendNow} onReload={onReload} />)
    expect(screen.getByRole('status')).toHaveTextContent('Wartet auf Neuladen · 2 Änderungen')
    expect(screen.queryByRole('button', { name: 'Jetzt senden' })).toBeNull()
    await user.click(screen.getByRole('button', { name: 'Neu laden' }))
    expect(onReload).toHaveBeenCalledOnce()
    expect(onSendNow).not.toHaveBeenCalled()
  })

  it('says why a finish stayed, until nothing is held', () => {
    holding('waiting', 1)
    useOutbox.getState().refuseFinish()
    const { rerender } = render(<OutboxStatus onSendNow={vi.fn()} onReload={vi.fn()} />)
    expect(screen.getByText('Beenden geht, sobald alles gespeichert ist.')).toBeInTheDocument()
    holding('idle', 0)
    holding('waiting', 1)
    rerender(<OutboxStatus onSendNow={vi.fn()} onReload={vi.fn()} />)
    expect(screen.queryByText('Beenden geht, sobald alles gespeichert ist.')).toBeNull()
  })
})
