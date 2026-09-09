import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import * as api from '../api'
import type { SearchMatch } from '../types'
import { Search } from './Search'

function mount(onOpen = vi.fn()) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  render(
    <QueryClientProvider client={client}>
      <Search onOpen={onOpen} />
    </QueryClientProvider>,
  )
  return onOpen
}

const match = (ticker: string, name: string): SearchMatch => ({
  ticker, name, exchange: 'XNAS', segment: 'large', watching: false,
})

beforeEach(() => {
  vi.useFakeTimers({ shouldAdvanceTime: true })
})

afterEach(() => {
  vi.useRealTimers()
  vi.restoreAllMocks()
})

describe('finding a company', () => {
  it('waits for typing to settle before asking', async () => {
    const fetchSearch = vi.spyOn(api, 'fetchSearch')
      .mockResolvedValue([match('AAA', 'Alpha Inc')])
    mount()

    await userEvent.type(screen.getByRole('combobox'), 'alp')
    expect(fetchSearch).not.toHaveBeenCalled()

    await vi.advanceTimersByTimeAsync(260)
    await waitFor(() => expect(fetchSearch).toHaveBeenCalledTimes(1))
    expect(fetchSearch.mock.calls[0]![0]).toBe('alp')
  })

  it('searches the universe, not the board it was opened from', async () => {
    // A company nobody is discussing today is still a company.
    const fetchSearch = vi.spyOn(api, 'fetchSearch')
      .mockResolvedValue([match('ZZZ', 'Quiet Holdings')])
    mount()

    await userEvent.type(screen.getByRole('combobox'), 'quiet')
    await vi.advanceTimersByTimeAsync(260)

    expect(await screen.findByText('ZZZ')).toBeVisible()
    expect(fetchSearch).toHaveBeenCalledWith('quiet', expect.anything())
  })

  it('opens a match with Enter', async () => {
    vi.spyOn(api, 'fetchSearch').mockResolvedValue([
      match('AAA', 'Alpha Inc'), match('BBB', 'Beta Corp'),
    ])
    const onOpen = mount()

    const box = screen.getByRole('combobox')
    await userEvent.type(box, 'a')
    await vi.advanceTimersByTimeAsync(260)
    await screen.findByText('AAA')

    await userEvent.keyboard('{ArrowDown}')
    await userEvent.keyboard('{Enter}')
    expect(onOpen).toHaveBeenCalledWith('BBB')
  })

  it('dismisses with Escape in stages', async () => {
    vi.spyOn(api, 'fetchSearch').mockResolvedValue([match('AAA', 'Alpha Inc')])
    mount()

    const box = screen.getByRole('combobox')
    await userEvent.type(box, 'a')
    await vi.advanceTimersByTimeAsync(260)
    await screen.findByRole('listbox')

    await userEvent.keyboard('{Escape}')
    expect(screen.queryByRole('listbox')).not.toBeInTheDocument()
    // The words survive the first Escape: closing the list is not the same
    // request as abandoning the search.
    expect(box).toHaveValue('a')

    await userEvent.keyboard('{Escape}')
    expect(box).toHaveValue('')
  })

  it('says nothing matches rather than showing an empty list', async () => {
    vi.spyOn(api, 'fetchSearch').mockResolvedValue([])
    mount()

    await userEvent.type(screen.getByRole('combobox'), 'zzzz')
    await vi.advanceTimersByTimeAsync(260)

    expect(await screen.findByText(/nothing matches/i)).toBeVisible()
  })

  it('cannot be answered by a query the reader has moved on from', async () => {
    // The cache is keyed by the query string, so a slow answer for 'a' has
    // nowhere to land once the reader is looking at results for 'ab'.
    const fetchSearch = vi.spyOn(api, 'fetchSearch')
      .mockImplementation(async (q: string) => [match(q.toUpperCase(), `${q} Inc`)])
    mount()

    const box = screen.getByRole('combobox')
    await userEvent.type(box, 'ab')
    await vi.advanceTimersByTimeAsync(260)
    await screen.findByText('AB')

    expect(screen.queryByText('A')).not.toBeInTheDocument()
    expect(fetchSearch).toHaveBeenCalledTimes(1)
  })

  it('is a labelled combobox', () => {
    mount()
    const box = screen.getByRole('combobox')
    expect(box).toHaveAccessibleName('Find a company')
    expect(box).toHaveAttribute('aria-expanded', 'false')
  })
})
