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
  it('says the volume as the debrief will: whole kilos, half to even (G-146)', () => {
    mount({ volume: 1234.5 })
    // Its own rounding said 1.235 here and the debrief 1.234.
    expect(document.querySelector('.finish-sum__vol')?.firstChild?.textContent).toBe('1.234')
  })

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
  })

  it('never files an empty workout: discard or go back (D5)', async () => {
    const user = userEvent.setup()
    const props = mount({ setsDone: 0, setsTotal: 6, volume: 0 })
    expect(screen.getByText(/Kein Satz erfasst — ein leeres Workout wird nicht gespeichert\./))
      .toBeInTheDocument()
    expect(screen.queryByText('Trotzdem beenden')).toBeNull()
    expect(screen.queryByText('Beenden')).toBeNull()
    await user.click(screen.getByText('Zurück zum Workout'))
    expect(useSheets.getState().openId).toBeNull()
    expect(props.onFinish).not.toHaveBeenCalled()
    expect(props.onDiscard).not.toHaveBeenCalled()
  })

  it('says what happens to the open sets, and offers the way back (G-010)', async () => {
    const user = userEvent.setup()
    const props = mount({ setsDone: 3, setsTotal: 5 })
    expect(screen.getByText('2 offene Sätze werden gelöscht.')).toBeInTheDocument()
    await user.click(screen.getByText('Zurück zum Workout'))
    expect(useSheets.getState().openId).toBeNull()
    expect(props.onFinish).not.toHaveBeenCalled()
  })

  it('names a single open set in the singular', () => {
    mount({ setsDone: 3, setsTotal: 4 })
    expect(screen.getByText('Ein offener Satz wird gelöscht.')).toBeInTheDocument()
  })

  it('has nothing to warn about when every set is done', () => {
    mount({ setsDone: 4, setsTotal: 4 })
    expect(screen.queryByText(/gelöscht/)).toBeNull()
    expect(screen.queryByText('Zurück zum Workout')).toBeNull()
  })

  it('says it is still saving instead of leaving', () => {
    mount({ finishing: true })
    const button = screen.getByText('Speichert noch…')
    expect(button).toBeDisabled()
    expect(screen.queryByText('Beenden')).toBeNull()
  })
})
