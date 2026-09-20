import { act, render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { PartnerNotice } from './PartnerNotice'
import { usePartnerNotice } from '../stores'

beforeEach(() => {
  usePartnerNotice.setState(usePartnerNotice.getInitialState(), true)
})
afterEach(() => { vi.useRealTimers() })

describe('PartnerNotice', () => {
  it('is not there until the partner changes something', () => {
    render(<PartnerNotice />)
    expect(screen.queryByText(/Dein Partner hat den Plan geändert/)).toBeNull()
  })

  it('says in plain sight that the plan moved, and can be waved away', async () => {
    // The only notice used to be sr-only text, so for anyone looking at the
    // screen the queue rearranged itself -- and once, the exercise under the
    // confirm button changed -- without a word.
    const user = userEvent.setup()
    render(<PartnerNotice />)
    act(() => { usePartnerNotice.getState().show() })
    expect(screen.getByText(/Dein Partner hat den Plan geändert/)).toBeVisible()

    await user.click(screen.getByRole('button', { name: 'OK' }))
    expect(screen.queryByText(/Dein Partner hat den Plan geändert/)).toBeNull()
  })

  it('leaves by itself, and a second change restarts the clock', () => {
    vi.useFakeTimers()
    render(<PartnerNotice />)
    act(() => { usePartnerNotice.getState().show() })
    act(() => { vi.advanceTimersByTime(6000) })
    act(() => { usePartnerNotice.getState().show() })
    act(() => { vi.advanceTimersByTime(6000) })
    expect(screen.getByText(/Dein Partner hat den Plan geändert/)).toBeInTheDocument()

    act(() => { vi.advanceTimersByTime(3000) })
    expect(screen.queryByText(/Dein Partner hat den Plan geändert/)).toBeNull()
  })
})
