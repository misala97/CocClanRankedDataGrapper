import { act, render, screen } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { SavingSweep } from './SavingSweep'
import { useSaveState } from '../stores'

beforeEach(() => {
  vi.useFakeTimers()
  useSaveState.setState({ pending: 0 })
})
afterEach(() => { vi.useRealTimers() })

const sweep = () => screen.queryByTestId('saving-sweep')

describe('SavingSweep', () => {
  it('says nothing about a save that lands quickly', () => {
    render(<SavingSweep />)
    act(() => { useSaveState.getState().begin() })
    act(() => { vi.advanceTimersByTime(280) })
    expect(sweep()).not.toBeInTheDocument()
    act(() => { useSaveState.getState().end() })
    act(() => { vi.advanceTimersByTime(1000) })
    expect(sweep()).not.toBeInTheDocument()
  })

  it('appears once a write is taking a moment', () => {
    render(<SavingSweep />)
    act(() => { useSaveState.getState().begin() })
    act(() => { vi.advanceTimersByTime(300) })
    expect(sweep()).toBeInTheDocument()
  })

  it('stays up until the LAST write answers', () => {
    // pending is counted rather than flagged for exactly this: two saves in
    // flight need two answers before the screen is idle again.
    render(<SavingSweep />)
    act(() => { useSaveState.getState().begin() })
    act(() => { useSaveState.getState().begin() })
    act(() => { vi.advanceTimersByTime(300) })
    act(() => { useSaveState.getState().end() })
    expect(sweep()).toBeInTheDocument()
    act(() => { useSaveState.getState().end() })
    expect(sweep()).not.toBeInTheDocument()
  })
})
