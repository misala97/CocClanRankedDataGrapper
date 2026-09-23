// Watching renders; the hub writes.
//
// The mark mutation lives in the shell, not in this component, because one
// write at a time has to hold across a navigation too -- leaving this page
// mid-write and pressing Watch on a company would otherwise put two writes in
// flight, which is the out-of-order landing the discipline exists to prevent.
// Those tests are in Hub.test.tsx, where the guard is.
import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it, vi } from 'vitest'

import { BoardUnavailable } from '../api'
import { payload, row } from '../fixtures'
import type { BoardPayload, Row } from '../types'
import { Watching } from './Watching'

const payloadWithRows = (rows: Row[]) => payload({ rows })

function show(board: BoardPayload,
              props: Partial<Parameters<typeof Watching>[0]> = {}) {
  const onOpen = props.onOpen ?? vi.fn()
  render(<Watching board={board} onOpen={onOpen}
                   onToggleWatch={vi.fn()} {...props} />)
  return onOpen
}

function watched() {
  const p = payloadWithRows([])
  p.watching = ['AAA', 'BBB']
  p.watch_rows = [row({ ticker: 'AAA' }), row({ ticker: 'BBB', name: 'Beta Corp' })]
  return p
}

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

  it('draws the move it promises in the column heading', () => {
    const p = watched()
    p.watch_rows![0] = row({ ticker: 'AAA', price: 10, price_move: -0.021 })
    show(p)
    expect(screen.getByText('-2.1%')).toBeVisible()
  })

  it('keeps an unavailable quote unavailable', () => {
    const p = watched()
    p.watch_rows = [row({ ticker: 'AAA', price: null,
                          quote: { ...row().quote, price: null,
                                   quality: 'unavailable' } })]
    p.watching = ['AAA']
    show(p)
    expect(screen.getByText(/unavailable/i)).toBeVisible()
    expect(screen.queryByText('$0.00')).not.toBeInTheDocument()
  })
})

describe('what the page shows about a write', () => {
  it('adopts the list the server answered with, before the rows catch up', () => {
    // The endpoint answers the caller's ENTIRE list precisely so nothing is
    // merged client-side; a merge is where two truths start to diverge.
    show(watched(), { watching: ['BBB'] })
    expect(screen.queryByText('AAA')).not.toBeInTheDocument()
    expect(screen.getByText('BBB')).toBeVisible()
  })

  it('disables every mark while one is being written', () => {
    // Every control, not just the one clicked: two marks changing at once can
    // land out of order, and the later answer would restore a list that
    // predates the earlier one.
    show(watched(), { pending: 'AAA' })
    expect(screen.getByRole('button', { name: /removing/i })).toBeDisabled()
    expect(screen.getByRole('button', { name: /stop watching BBB/i }))
      .toBeDisabled()
  })

  it('leaves the marks alone and says what failed', () => {
    show(watched(), { watchError: new BoardUnavailable('server') })
    expect(screen.getByText(/could not be saved/i)).toBeVisible()
    expect(screen.getByText(/the board answered with an error/i)).toBeVisible()
    // Still watched, because the server never said otherwise.
    expect(screen.getByText('AAA')).toBeVisible()
    expect(screen.getByRole('button', { name: /stop watching AAA/i })).toBeEnabled()
  })

  it('does not claim the marks are unchanged when it cannot know', () => {
    // A request that timed out may well have been applied server-side.
    show(watched(), { watchError: new BoardUnavailable('timeout') })
    const text = document.body.textContent ?? ''
    expect(text).not.toMatch(/marks are unchanged/i)
    expect(text).toMatch(/last one the server confirmed/i)
  })

  it('renders no mark control at all when the caller cannot service one', () => {
    render(<Watching board={watched()} onOpen={vi.fn()} />)
    expect(screen.queryByRole('button', { name: /stop watching/i }))
      .not.toBeInTheDocument()
  })
})
