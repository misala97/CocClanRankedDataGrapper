import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { act, render, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { LiveSettingsSheet } from './LiveSettingsSheet'
import { useSheets } from '../stores'
import { payload } from '../types.test-d'
import { sessionKey } from '../api'
import type { ExerciseMeta } from '../../types'

const se = payload.visible_exercises[0]!
const settings: ExerciseMeta = {
  id: se.exercise_id, name: se.name, muscle_group: se.muscle_group, is_unilateral: false,
  default_rest_seconds: 150, weight_increment: 2, equipment: 'dumbbell', bar_weight: null,
  stack_kg: null, secondary_muscle_groups: null,
  list_defaults: { default_rest_seconds: 90, weight_increment: 2, bar_weight: null, stack_kg: null },
  own: ['default_rest_seconds'], rest_for_all: null,
}

beforeEach(() => { useSheets.setState(useSheets.getInitialState(), true) })
afterEach(() => { vi.unstubAllGlobals() })

function mount(reply: (url: string) => unknown = () => settings) {
  const fetchMock = vi.fn(async (url: string) =>
    ({ ok: true, status: 200, json: async () => reply(url) } as Response))
  vi.stubGlobal('fetch', fetchMock)
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  const invalidate = vi.spyOn(client, 'invalidateQueries')
  render(
    <QueryClientProvider client={client}>
      <LiveSettingsSheet exercise={se} sessionId={payload.session.id} />
    </QueryClientProvider>)
  act(() => { useSheets.getState().open(`sheet-settings-${se.id}`) })
  return { fetchMock, invalidate, sheet: within(document.getElementById(`sheet-settings-${se.id}`)!) }
}

describe('LiveSettingsSheet', () => {
  it("reads the lifter's settings when it opens, not the workout's copy", async () => {
    const { fetchMock, sheet } = mount()
    expect(sheet.getByText('Lädt …')).toBeInTheDocument()
    expect(await sheet.findByRole('heading', { name: 'Pause nach jedem Satz' })).toBeInTheDocument()
    expect(fetchMock.mock.calls[0]![0]).toBe(`/gym/exercises/${se.exercise_id}/settings.json`)
  })

  it('has the workout read again after each save', async () => {
    // "Pause heute" marks the rest in force and the kg stepper moves by the
    // step: both come from these settings.
    const user = userEvent.setup()
    const { invalidate, sheet } = mount()
    await user.click(await sheet.findByRole('button', { name: '3:00' }))
    await waitFor(() => expect(invalidate)
      .toHaveBeenCalledWith({ queryKey: sessionKey(payload.session.id) }))
  })

  it("goes back to the exercise's sheet", async () => {
    const user = userEvent.setup()
    const { sheet } = mount()
    await user.click(sheet.getByRole('button', { name: 'Zurück' }))
    expect(useSheets.getState().openId).toBe(`sheet-ex-${se.id}`)
  })
})
