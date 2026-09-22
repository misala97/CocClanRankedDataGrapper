import { act, render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { FinishSheet } from './FinishSheet'
import { useSheets } from '../stores'

beforeEach(() => {
  useSheets.setState(useSheets.getInitialState(), true)
})

const mount = (over: Partial<Parameters<typeof FinishSheet>[0]> = {}) => {
  const props = {
    volume: 1200, setsDone: 3, setsTotal: 4, startedAt: '2026-09-23T10:00:00',
    onFinish: vi.fn(), onDiscard: vi.fn(), ...over,
  }
  render(<FinishSheet {...props} />)
  act(() => { useSheets.getState().open('sheet-finish') })
  return props
}

describe('FinishSheet', () => {
  it('finishes a workout with sets in it, and offers no discard', async () => {
    const user = userEvent.setup()
    const props = mount()
    expect(screen.queryByText('Workout verwerfen')).toBeNull()
    await user.click(screen.getByText('Beenden'))
    expect(props.onFinish).toHaveBeenCalled()
  })

  it('offers to throw away a workout with nothing logged', async () => {
    // The wrong routine tapped on the way in could only be finished -- an
    // empty entry in the history -- and then deleted from the debrief.
    const user = userEvent.setup()
    const props = mount({ setsDone: 0, volume: 0 })
    await user.click(screen.getByText('Workout verwerfen'))
    expect(props.onDiscard).toHaveBeenCalled()
    expect(props.onFinish).not.toHaveBeenCalled()
    expect(screen.getByText('Trotzdem beenden')).toBeInTheDocument()
  })

  it('says it is still saving instead of leaving', () => {
    mount({ finishing: true })
    const button = screen.getByText('Speichert noch…')
    expect(button).toBeDisabled()
    expect(screen.queryByText('Beenden')).toBeNull()
  })
})
