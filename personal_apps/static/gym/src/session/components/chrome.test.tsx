import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { SessionHeader } from './SessionHeader'
import { SaveErrorBanner } from './SaveErrorBanner'
import { ReorderBar } from './ReorderBar'
import { LiveRegion } from './LiveRegion'
import { useAnnouncer, useSaveState, useSheets, useWorkoutUi } from '../stores'
import { payload } from '../types.test-d'

beforeEach(() => {
  useSheets.setState(useSheets.getInitialState(), true)
  useWorkoutUi.setState(useWorkoutUi.getInitialState(), true)
  useSaveState.setState(useSaveState.getInitialState(), true)
  useAnnouncer.setState(useAnnouncer.getInitialState(), true)
  vi.useFakeTimers({ shouldAdvanceTime: true })
  vi.setSystemTime(new Date('2026-08-10T12:30:00Z'))
})

afterEach(() => { vi.useRealTimers() })

const session = payload.session

describe('SessionHeader', () => {
  it('names the workout as the page h1', () => {
    // It was a <span>, which left the whole document starting at h2 -- the
    // live exercise's name -- so heading navigation returned one exercise and
    // nothing about the workout it belongs to.
    render(<SessionHeader session={session} deloadApplied={false}
      deloadDefaultPct={70} />)
    expect(screen.getByRole('heading', { level: 1 }))
      .toHaveTextContent('Fixture Workout')
  })

  it('falls back to Workout when the session has no name', () => {
    render(<SessionHeader session={{ ...session, name: null }}
      deloadApplied={false} deloadDefaultPct={70} />)
    expect(screen.getByRole('heading', { level: 1 })).toHaveTextContent('Workout')
  })

  it('shows the elapsed clock counting from started_at', () => {
    // started_at is naive UTC; 30 minutes before the faked now.
    render(<SessionHeader session={{ ...session, started_at: '2026-08-10T12:00:00' }}
      deloadApplied={false} deloadDefaultPct={70} />)
    expect(screen.getByText('30:00')).toBeInTheDocument()
  })

  it('badges a deload, with the percentage only once it is applied', () => {
    const deload = { ...session, is_deload: true, deload_pct: 80 }
    const { rerender } = render(
      <SessionHeader session={deload} deloadApplied={false} deloadDefaultPct={70} />)
    expect(screen.getByText('Deload')).toBeInTheDocument()

    // A session flagged after a set was already logged keeps its full working
    // weights, so showing a percentage would describe nothing on screen.
    rerender(<SessionHeader session={deload} deloadApplied deloadDefaultPct={70} />)
    expect(screen.getByText(/Deload 80 %/)).toBeInTheDocument()
  })

  it('opens the workout sheet from the options button', async () => {
    const user = userEvent.setup({ advanceTimers: vi.advanceTimersByTime })
    render(<SessionHeader session={session} deloadApplied={false} deloadDefaultPct={70} />)
    await user.click(screen.getByLabelText('Workout-Optionen'))
    expect(useSheets.getState().openId).toBe('sheet-session')
  })
})

describe('SaveErrorBanner', () => {
  it('is absent until something fails', () => {
    render(<SaveErrorBanner />)
    expect(screen.queryByRole('alert')).not.toBeInTheDocument()
  })

  it('shows the message and runs the retry it was given', async () => {
    const user = userEvent.setup({ advanceTimers: vi.advanceTimersByTime })
    const retry = vi.fn()
    render(<SaveErrorBanner />)
    useSaveState.getState().fail('Keine Antwort vom Server', retry)

    expect(await screen.findByRole('alert')).toHaveTextContent('Keine Antwort vom Server')
    await user.click(screen.getByText('Erneut versuchen'))
    expect(retry).toHaveBeenCalledOnce()
  })

  it('dismisses', async () => {
    const user = userEvent.setup({ advanceTimers: vi.advanceTimersByTime })
    render(<SaveErrorBanner />)
    useSaveState.getState().fail('x', () => {})
    await user.click(await screen.findByText('Verwerfen'))
    expect(screen.queryByRole('alert')).not.toBeInTheDocument()
  })
})

describe('ReorderBar', () => {
  it('is absent outside reorder mode', () => {
    render(<ReorderBar />)
    expect(screen.queryByText('Fertig')).not.toBeInTheDocument()
  })

  it('names the mode and leaves it from where you are', async () => {
    // Before the bar existed the only exit was re-opening the options sheet.
    const user = userEvent.setup({ advanceTimers: vi.advanceTimersByTime })
    useWorkoutUi.getState().toggleReorder()
    render(<ReorderBar />)
    expect(screen.getByText(/Reihenfolge ändern/)).toBeInTheDocument()

    await user.click(screen.getByText('Fertig'))
    expect(useWorkoutUi.getState().reorderUnlocked).toBe(false)
  })
})

describe('LiveRegion', () => {
  it('is a polite live region that exists before it has anything to say', () => {
    // A live region has to persist to be announced. The original kept it
    // outside #session-body for exactly this reason -- a freshly inserted
    // region carrying pre-filled text does not reliably announce it.
    const { container } = render(<LiveRegion />)
    const region = container.querySelector('[aria-live]')!
    expect(region).toHaveAttribute('aria-live', 'polite')
    expect(region).toHaveTextContent('')
  })

  it('announces what the store is given', async () => {
    render(<LiveRegion />)
    useAnnouncer.getState().announce('Pause vorbei.')
    expect(await screen.findByText('Pause vorbei.')).toBeInTheDocument()
  })

  it('re-announces the same text when it happens again', async () => {
    // Two identical announcements in a row are two events. Writing the same
    // string back into a live region does not re-fire it, so the store
    // carries a nonce and the component keys on it.
    render(<LiveRegion />)
    useAnnouncer.getState().announce('3 Treffer.')
    const first = useAnnouncer.getState().nonce
    useAnnouncer.getState().announce('3 Treffer.')
    expect(useAnnouncer.getState().nonce).not.toBe(first)
  })
})
