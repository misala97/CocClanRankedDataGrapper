import { act, fireEvent, render, screen } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { UndoToast, useUndo } from './undo'

beforeEach(() => {
  vi.useFakeTimers()
  useUndo.setState({ pending: null, timer: null })
})

afterEach(() => {
  vi.useRealTimers()
})

const offer = (over: Partial<Parameters<ReturnType<typeof useUndo.getState>['offer']>[0]> = {}) => {
  const commit = vi.fn()
  const undo = vi.fn()
  useUndo.getState().offer({ label: 'Satz 1 gelöscht.', commit, undo, ...over })
  return { commit, undo }
}

describe('useUndo', () => {
  it('commits after the window, untouched', () => {
    const { commit, undo } = offer()
    expect(commit).not.toHaveBeenCalled()
    vi.advanceTimersByTime(5000)
    expect(commit).toHaveBeenCalledWith(false)
    expect(undo).not.toHaveBeenCalled()
    expect(useUndo.getState().pending).toBeNull()
  })

  it('undo cancels the write entirely', () => {
    const { commit, undo } = offer()
    useUndo.getState().undoNow()
    vi.advanceTimersByTime(10000)
    expect(commit).not.toHaveBeenCalled()
    expect(undo).toHaveBeenCalled()
  })

  it('a second offer commits the first immediately', () => {
    // Two pending deletions behind one button is how the wrong one gets
    // kept -- the earlier write fires the moment a new one arrives.
    const first = offer()
    const second = offer({ label: 'Routine gelöscht.' })
    expect(first.commit).toHaveBeenCalledWith(false)
    expect(second.commit).not.toHaveBeenCalled()
  })
})

describe('UndoToast', () => {
  it('shows the label and undoes on tap', () => {
    render(<UndoToast />)
    let fns!: ReturnType<typeof offer>
    act(() => { fns = offer() })
    const { commit, undo } = fns
    expect(screen.getByRole('status')).toHaveTextContent('Satz 1 gelöscht.')
    fireEvent.click(screen.getByRole('button', { name: 'Rückgängig' }))
    expect(undo).toHaveBeenCalled()
    expect(commit).not.toHaveBeenCalled()
    expect(screen.queryByRole('status')).not.toBeInTheDocument()
  })

  it('dismiss commits right away instead of waiting the timer out', () => {
    render(<UndoToast />)
    let fns!: ReturnType<typeof offer>
    act(() => { fns = offer() })
    const { commit } = fns
    fireEvent.click(screen.getByRole('button', { name: 'Schließen' }))
    expect(commit).toHaveBeenCalledWith(false)
  })

  it('flushes the pending write with keepalive when the page hides', () => {
    render(<UndoToast />)
    let fns!: ReturnType<typeof offer>
    act(() => { fns = offer() })
    const { commit } = fns
    window.dispatchEvent(new Event('pagehide'))
    // keepalive=true: the request must outlive the document.
    expect(commit).toHaveBeenCalledWith(true)
  })

  it('renders nothing with nothing pending', () => {
    render(<UndoToast />)
    expect(screen.queryByRole('status')).not.toBeInTheDocument()
  })
})
