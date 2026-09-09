import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, describe, expect, it, vi } from 'vitest'

import * as api from '../api'
import { BoardUnavailable } from '../api'
import { payload, row } from '../fixtures'
import type { BoardPayload, Row } from '../types'
import { Watching } from './Watching'

const payloadWithRows = (rows: Row[]) => payload({ rows })

function show(board: BoardPayload, onOpen = vi.fn()) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  render(
    <QueryClientProvider client={client}>
      <Watching board={board} onOpen={onOpen} />
    </QueryClientProvider>,
  )
  return onOpen
}

afterEach(() => { vi.restoreAllMocks() })

describe('the caller’s marks', () => {
  it('keeps quiet watched companies visible', () => {
    // watch_rows is the caller's list whatever the floor said. Filtering the
    // ranked rows instead would drop exactly the companies that went quiet --
    // which is the reason someone marked them.
    const p = payloadWithRows([])
    p.watching = ['AAA']
    p.watch_rows = [row({ ticker: 'AAA', eligible: false })]
    show(p)
    expect(screen.getByText('AAA')).toBeVisible()
  })

  it('says why a watched company is quiet rather than hiding it', () => {
    const p = payloadWithRows([])
    p.watching = ['AAA']
    p.watch_rows = [row({ ticker: 'AAA', eligible: false, mentions: 0 })]
    show(p)
    expect(screen.getByText(/below the floor/i)).toBeVisible()
  })

  it('distinguishes an older payload from an empty list', () => {
    // watch_rows absent means the server did not send it; watch_rows empty
    // means this account watches nothing. Rendering both as "nothing here"
    // would tell a reader with marks that they have none.
    const older = payloadWithRows([])
    older.watching = ['AAA']
    delete older.watch_rows
    show(older)
    expect(screen.getByText(/not included in this board/i)).toBeVisible()

    expect(screen.queryByText(/nothing marked yet/i)).not.toBeInTheDocument()
  })

  it('offers a first step when nothing is marked', () => {
    const empty = payloadWithRows([row()])
    empty.watching = []
    empty.watch_rows = []
    show(empty)
    expect(screen.getByText(/nothing marked yet/i)).toBeVisible()
  })

  it('opens research from a watched row', async () => {
    const p = payloadWithRows([])
    p.watching = ['AAA']
    p.watch_rows = [row({ ticker: 'AAA' })]
    const onOpen = show(p)
    await userEvent.click(screen.getByRole('button', { name: /Alpha Inc/ }))
    expect(onOpen).toHaveBeenCalledWith('AAA')
  })
})

describe('unmarking', () => {
  function watched() {
    const p = payloadWithRows([])
    p.watching = ['AAA', 'BBB']
    p.watch_rows = [row({ ticker: 'AAA' }), row({ ticker: 'BBB' })]
    return p
  }

  it('adopts the whole list the server answers with', async () => {
    // The endpoint answers the caller's entire list precisely so nothing is
    // merged client-side; a merge is where two truths start to diverge.
    const setWatch = vi.spyOn(api, 'setWatch').mockResolvedValue(['BBB'])
    show(watched())

    await userEvent.click(screen.getByRole('button', { name: /stop watching AAA/i }))
    await waitFor(() => {
      expect(screen.queryByText('AAA')).not.toBeInTheDocument()
    })
    expect(setWatch).toHaveBeenCalledWith('AAA', false)
    expect(screen.getByText('BBB')).toBeVisible()
  })

  it('disables the control until the write completes', async () => {
    let release: (value: string[]) => void = () => {}
    vi.spyOn(api, 'setWatch').mockReturnValue(
      new Promise((resolve) => { release = resolve }))
    show(watched())

    const button = screen.getByRole('button', { name: /stop watching AAA/i })
    await userEvent.click(button)
    expect(button).toBeDisabled()

    release(['BBB'])
    await waitFor(() => expect(screen.queryByText('AAA')).not.toBeInTheDocument())
  })

  it('cannot be raced by repeated clicks', async () => {
    const setWatch = vi.spyOn(api, 'setWatch')
      .mockReturnValue(new Promise(() => {}))
    show(watched())

    const button = screen.getByRole('button', { name: /stop watching AAA/i })
    await userEvent.click(button)
    await userEvent.click(button)
    await userEvent.click(button)
    expect(setWatch).toHaveBeenCalledTimes(1)
  })

  it('leaves the previous state alone when the write is refused', async () => {
    vi.spyOn(api, 'setWatch').mockRejectedValue(new BoardUnavailable('server'))
    show(watched())

    await userEvent.click(screen.getByRole('button', { name: /stop watching AAA/i }))
    await waitFor(() => {
      expect(screen.getByText(/could not be saved/i)).toBeVisible()
    })
    // Still watched, because the server never said otherwise.
    expect(screen.getByText('AAA')).toBeVisible()
    expect(screen.getByRole('button', { name: /stop watching AAA/i })).toBeEnabled()
  })

  it('says plainly when a write was refused rather than failing quietly', async () => {
    vi.spyOn(api, 'setWatch').mockRejectedValue(new BoardUnavailable('forbidden'))
    show(watched())
    await userEvent.click(screen.getByRole('button', { name: /stop watching AAA/i }))
    expect(await screen.findByText(/not allowed/i)).toBeVisible()
  })
})
