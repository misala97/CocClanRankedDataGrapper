import type { ComponentProps } from 'react'
import { act, render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { SessionSheet } from './SessionSheet'
import { usePush, useSheets, useWorkoutUi } from '../stores'
import { payload } from '../types.test-d'

beforeEach(() => {
  useSheets.setState(useSheets.getInitialState(), true)
  useWorkoutUi.setState(useWorkoutUi.getInitialState(), true)
  usePush.setState(usePush.getInitialState(), true)
})

// Typed explicitly: an empty literal infers as never[], so any test passing a
// populated partnerStatus would fail to compile while the suite stayed green.
const base: ComponentProps<typeof SessionSheet> = {
  session: payload.session,
  resting: false,
  partners: [{ id: 7, username: 'Anna' }],
  partnerStatus: [],
  pushSupported: true,
  onMetaSave: vi.fn(), onSkipRest: vi.fn(), onInvite: vi.fn(), onEnablePush: vi.fn(),
}

function open(props: Partial<typeof base> = {}) {
  const merged = { ...base, ...props, onMetaSave: vi.fn(), onSkipRest: vi.fn(),
    onInvite: vi.fn(), onEnablePush: vi.fn(), ...props }
  const result = render(<SessionSheet {...merged} />)
  act(() => { useSheets.getState().open('sheet-session') })
  return { ...result, props: merged }
}

describe('SessionSheet', () => {
  it('saves bodyweight and note together, and says what they apply to', async () => {
    const user = userEvent.setup()
    const { props } = open()
    await user.type(screen.getByLabelText('Körpergewicht (kg)'), '82.4')
    await user.type(screen.getByLabelText('Notiz'), 'nach Schicht')
    await user.click(screen.getByText('Speichern'))

    expect(props.onMetaSave).toHaveBeenCalledWith({
      bodyweightKg: 82.4, notes: 'nach Schicht',
    })
    // The caption is the group's head now, not a floating footnote.
    expect(screen.getByText('Dieses Workout')).toBeInTheDocument()
  })

  it('offers to end a rest only while one is running', () => {
    // The Jinja version had to render this always and hide it, because the
    // sheets survived every refresh and a `{% if %}` would have frozen at
    // whatever was true on the last full page load. Nothing freezes now.
    const { rerender } = open({ resting: false })
    expect(screen.queryByText('Pause beenden')).not.toBeInTheDocument()

    rerender(<SessionSheet {...base} resting />)
    expect(screen.getByText('Pause beenden')).toBeInTheDocument()
  })

  it('names the deload action for the state it is in', () => {
    const { rerender } = open()
    expect(screen.getByText('Als Deload markieren')).toBeInTheDocument()

    rerender(<SessionSheet {...base}
      session={{ ...base.session, is_deload: true }} />)
    expect(screen.getByText('Deload-Markierung ändern')).toBeInTheDocument()
  })

  it('hands off to the other sheets', async () => {
    const user = userEvent.setup()
    open()
    await user.click(screen.getByText('Übung hinzufügen'))
    expect(useSheets.getState().openId).toBe('sheet-add-exercise')
  })

  it('enters reorder mode and gets out of the way', async () => {
    // The bar is the mode's own exit; leaving the sheet open over it would
    // hide the thing being reordered.
    const user = userEvent.setup()
    open()
    await user.click(screen.getByText('Reihenfolge ändern'))
    expect(useWorkoutUi.getState().reorderUnlocked).toBe(true)
    expect(useSheets.getState().openId).toBeNull()
  })

  it('offers push only once the probe says this device is not subscribed', () => {
    // A subscription is a browser endpoint, one per device. null is the
    // one-time probe still running, and guessing would offer to enable push
    // on a phone that already has it.
    const { rerender } = open()
    expect(screen.queryByText(/Pausen-Benachrichtigung/)).not.toBeInTheDocument()

    act(() => { usePush.getState().setSubscribed(true) })
    expect(screen.queryByText(/Pausen-Benachrichtigung/)).not.toBeInTheDocument()

    act(() => { usePush.getState().setSubscribed(false) })
    expect(screen.getByText(/Pausen-Benachrichtigung/)).toBeInTheDocument()

    rerender(<SessionSheet {...base} pushSupported={false} />)
    expect(screen.queryByText(/Pausen-Benachrichtigung/)).not.toBeInTheDocument()
  })

  it('invites the chosen partner', async () => {
    const user = userEvent.setup()
    const { props } = open()
    await user.click(screen.getByText('Einladen'))
    expect(props.onInvite).toHaveBeenCalledWith(7)
  })

  it('omits the picker when there is nobody to invite', () => {
    open({ partners: [] })
    expect(screen.queryByLabelText('Trainingspartner einladen')).not.toBeInTheDocument()
  })

  it('reports who is in and who was asked', () => {
    open({ partnerStatus: [
      { username: 'Anna', accepted: true },
      { username: 'Ben', accepted: false },
    ] })
    expect(screen.getByText('Anna ist dabei')).toBeInTheDocument()
    expect(screen.getByText('Ben wurde eingeladen')).toBeInTheDocument()
  })
})
