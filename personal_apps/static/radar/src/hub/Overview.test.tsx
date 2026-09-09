import { render, screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it, vi } from 'vitest'

import { payload, row } from '../fixtures'
import type { BoardPayload } from '../types'
import { Overview } from './Overview'

function show(board: BoardPayload, handlers: {
  onOpen?: (t: string) => void; onGo?: (page: string) => void
} = {}) {
  const onOpen = handlers.onOpen ?? vi.fn()
  const onGo = handlers.onGo ?? vi.fn()
  render(<Overview board={board} onOpen={onOpen} onGo={onGo} />)
  return { onOpen, onGo }
}

describe('the overview', () => {
  it('leads with the market context and when the board was built', () => {
    show(payload())
    expect(screen.getByText(/US markets/)).toBeVisible()
    // The stamp is not decoration: it is what makes the numbers under it
    // readable as of a moment rather than as of now.
    // Exact, and in Berlin. An alternation that also accepted the raw UTC
    // hour would pass with the conversion broken.
    expect(screen.getByText(/built 21:00 Berlin/)).toBeVisible()
  })

  it('greets nobody and narrates nothing', () => {
    show(payload())
    const text = document.body.textContent ?? ''
    for (const invented of [/good (morning|afternoon|evening)/i,
                            /since your last visit/i, /welcome back/i,
                            /today's story/i, /we recommend/i]) {
      expect(text).not.toMatch(invented)
    }
  })

  it('shows the first three candidates in the server’s order', () => {
    show(payload({
      rows: [row({ ticker: 'CCC' }), row({ ticker: 'AAA' }),
             row({ ticker: 'BBB' }), row({ ticker: 'DDD' })],
    }))
    const list = screen.getByRole('list', { name: /current chatter/i })
    const names = within(list).getAllByTestId('rh-candidate')
      .map((el) => el.textContent)
    expect(names).toHaveLength(3)
    expect(names[0]).toContain('CCC')
    expect(names[1]).toContain('AAA')
    expect(names[2]).toContain('BBB')
  })

  it('names the window those candidates are ranked over', () => {
    show(payload({ window_hours: 24 }))
    expect(screen.getByText(/last 24 hours/i)).toBeVisible()
  })

  it('shows the first five watched companies', () => {
    const p = payload({ rows: [] })
    p.watching = ['A1', 'A2', 'A3', 'A4', 'A5', 'A6']
    p.watch_rows = p.watching.map((ticker) => row({ ticker }))
    show(p)
    const list = screen.getByRole('list', { name: /watching/i })
    expect(within(list).getAllByTestId('rh-watchrow')).toHaveLength(5)
    expect(within(list).queryByText('A6')).not.toBeInTheDocument()
    expect(screen.getByRole('button', { name: /all 6 marked/i })).toBeVisible()
  })

  it('opens research from a candidate', async () => {
    const { onOpen } = show(payload({ rows: [row({ ticker: 'AAA' })] }))
    await userEvent.click(screen.getAllByTestId('rh-candidate')[0]!
      .querySelector('button')!)
    expect(onOpen).toHaveBeenCalledWith('AAA')
  })

  it('links to the full lists rather than ending there', async () => {
    const { onGo } = show(payload())
    await userEvent.click(screen.getByRole('button', { name: /all chatter/i }))
    expect(onGo).toHaveBeenCalledWith('chatter')
  })

  it('never totals authors or mentions across companies', () => {
    // Two companies discussed by the same person are not two people, and the
    // board carries no way to know. A "47 people talking today" line would be
    // an invented system total.
    show(payload({
      rows: [row({ ticker: 'AAA', authors: 9, mentions: 20 }),
             row({ ticker: 'BBB', authors: 7, mentions: 30 })],
    }))
    // Every number on the page has to be one the rows themselves carry. A
    // sum, a mean, or a count of companies would all fail this; greping for
    // one literal total would only ever have caught the sum.
    const allowed = new Set([
      '9', '7', '20', '30',            // the rows' own authors and mentions
      '10.00', '1.2', '3.3',           // one row's price, move and ratio
      '21', '00',                      // the build stamp
      '4',                             // the window, in hours
      '3', '2',                        // inside the server's own phrase
    ])
    for (const found of (document.body.textContent ?? '')
      .match(/\d+(?:[.,]\d+)?/g) ?? []) {
      expect(allowed.has(found.replace(',', '')),
             `unexpected number on the page: ${found}`).toBe(true)
    }
  })

  it('says so when the board is empty and marks are not', () => {
    const p = payload({ rows: [], excluded: { floor: 3 } })
    p.watching = ['AAA']
    p.watch_rows = [row({ ticker: 'AAA', eligible: false })]
    show(p)
    expect(screen.getByText(/nothing cleared the floor/i)).toBeVisible()
    expect(screen.getByText('AAA')).toBeVisible()
  })

  it('says so when marks are empty and the board is not', () => {
    const p = payload({ rows: [row({ ticker: 'AAA' })] })
    p.watching = []
    p.watch_rows = []
    show(p)
    expect(screen.getByText(/nothing marked yet/i)).toBeVisible()
    expect(screen.getAllByTestId('rh-candidate')).toHaveLength(1)
  })

  it('keeps an unavailable quote unavailable', () => {
    show(payload({
      rows: [row({ price: null, quote: { ...row().quote, price: null,
                                         quality: 'unavailable' } })],
    }))
    expect(screen.getByText(/unavailable/i)).toBeVisible()
    expect(screen.queryByText('$0.00')).not.toBeInTheDocument()
  })
})
