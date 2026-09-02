import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import { Search } from './Search'
import { row } from '../fixtures'
import type { SearchMatch } from '../types'

const matches: SearchMatch[] = [
  { ticker: 'NVDA', name: 'NVIDIA Corp', exchange: 'Q', segment: 'large', watching: false },
  { ticker: 'NVAX', name: 'Novavax', exchange: 'Q', segment: 'micro', watching: false },
]

function stubSearch(found = matches) {
  const spy = vi.fn(async (url: string) => ({
    ok: true, redirected: false, status: 200,
    json: async () => ({ matches: url.includes('q=nv') ? found : [] }),
  }))
  vi.stubGlobal('fetch', spy)
  return spy
}

beforeEach(() => vi.useFakeTimers({ shouldAdvanceTime: true }))
afterEach(() => { vi.useRealTimers(); vi.unstubAllGlobals() })

function search(props: Partial<Parameters<typeof Search>[0]> = {}) {
  const onPick = vi.fn(); const onToggleWatch = vi.fn()
  render(<Search rows={[row({ ticker: 'NVDA' })]} watching={['NVAX']} onPick={onPick}
                 onToggleWatch={onToggleWatch} {...props} />)
  return { onPick, onToggleWatch, input: screen.getByRole('combobox') }
}

describe('finding a stock', () => {
  it('fetches once the typing settles, and only for the last query', async () => {
    const spy = stubSearch()
    const { input } = search()
    const user = userEvent.setup({ advanceTimers: vi.advanceTimersByTime })

    await user.type(input, 'nv')
    await waitFor(() => expect(screen.getByRole('listbox')).toBeInTheDocument())

    expect(spy).toHaveBeenCalledTimes(1)
    expect(String(spy.mock.calls[0]![0])).toBe('/radar/api/search?q=nv')
    expect(screen.getAllByRole('option')).toHaveLength(2)
  })

  it('annotates each match from what the page already knows', async () => {
    stubSearch()
    const { input } = search()
    const user = userEvent.setup({ advanceTimers: vi.advanceTimersByTime })

    await user.type(input, 'nv')
    await screen.findByRole('listbox')

    expect(screen.getByRole('option', { name: /NVDA/ })).toHaveTextContent('on the board · +0.50')
    expect(screen.getByRole('option', { name: /NVAX/ })).toHaveTextContent('watching')
  })

  it('walks the list with the arrows and opens the panel with Enter', async () => {
    stubSearch()
    const { input, onPick } = search()
    const user = userEvent.setup({ advanceTimers: vi.advanceTimersByTime })

    await user.type(input, 'nv')
    await screen.findByRole('listbox')
    await user.keyboard('{ArrowDown}{Enter}')

    expect(onPick).toHaveBeenCalledWith('NVAX')
    expect(screen.queryByRole('listbox')).toBeNull()
    expect(input).toHaveValue('nv')
  })

  it('stars a match without opening it', async () => {
    stubSearch()
    const { input, onToggleWatch, onPick } = search()
    const user = userEvent.setup({ advanceTimers: vi.advanceTimersByTime })

    await user.type(input, 'nv')
    await screen.findByRole('listbox')
    await user.click(screen.getByRole('button', { name: 'Watch NVDA' }))

    expect(onToggleWatch).toHaveBeenCalledWith('NVDA')
    expect(onPick).not.toHaveBeenCalled()
  })

  it('is reached with / and left with Escape, in stages', async () => {
    stubSearch()
    const { input } = search()
    const user = userEvent.setup({ advanceTimers: vi.advanceTimersByTime })

    fireEvent.keyDown(window, { key: '/' })
    expect(document.activeElement).toBe(input)

    await user.type(input, 'nv')
    await screen.findByRole('listbox')
    await user.keyboard('{Escape}')
    expect(screen.queryByRole('listbox')).toBeNull()
    expect(input).toHaveValue('nv')
    await user.keyboard('{Escape}')
    expect(input).toHaveValue('')
  })

  it('says so when nothing matches', async () => {
    stubSearch([])
    const { input } = search()
    const user = userEvent.setup({ advanceTimers: vi.advanceTimersByTime })

    await user.type(input, 'nv')

    await waitFor(() => expect(screen.getByRole('listbox')).toHaveTextContent('Nothing matches'))
  })
})
