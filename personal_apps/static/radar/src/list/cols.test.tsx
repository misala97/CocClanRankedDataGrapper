/** The column header stopped being decoration. */
import { cleanup, render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { expect, it, vi } from 'vitest'

import { SortCols } from './ListPane'
import type { Selection } from '../types'

const selection: Selection = {
  market: 'us', sources: ['bluesky'], segments: [], window: 4,
  minVenues: 1, sort: null, dir: 'desc',
}

function setup(over: Partial<Selection> = {}) {
  const onChange = vi.fn()
  render(<SortCols selection={{ ...selection, ...over }} onChange={onChange} />)
  return onChange
}

it('offers one control per sort key and nothing for price', () => {
  setup()
  for (const name of [/ticker/i, /mentions/i, /divergence/i, /ratio/i,
                      /price move/i, /lean/i]) {
    expect(screen.getByRole('button', { name })).toBeTruthy()
  }
  // "price" appears twice as a label and is a control neither time.
  expect(screen.queryByRole('button', { name: /^sort by price$/i })).toBeNull()
})

it('opens a number largest-first and a ticker A to Z', async () => {
  const onChange = setup()
  await userEvent.click(screen.getByRole('button', { name: /mentions/i }))
  expect(onChange).toHaveBeenCalledWith(
    expect.objectContaining({ sort: 'mentions', dir: 'desc' }))

  cleanup()            // two renders in one test would double every button
  const second = setup()
  await userEvent.click(screen.getByRole('button', { name: /ticker/i }))
  expect(second).toHaveBeenCalledWith(
    expect.objectContaining({ sort: 'ticker', dir: 'asc' }))
})

it('reverses on the second click and clears on the third', async () => {
  const onChange = setup({ sort: 'mentions', dir: 'desc' })
  await userEvent.click(screen.getByRole('button', { name: /mentions/i }))
  expect(onChange).toHaveBeenCalledWith(
    expect.objectContaining({ sort: 'mentions', dir: 'asc' }))

  cleanup()
  const cleared = setup({ sort: 'mentions', dir: 'asc' })
  await userEvent.click(screen.getByRole('button', { name: /mentions/i }))
  expect(cleared).toHaveBeenCalledWith(expect.objectContaining({ sort: null }))
})

it('names the action and marks the active column for assistive tech', () => {
  setup({ sort: 'mentions', dir: 'desc' })
  const talk = screen.getByRole('button', { name: /sort by mentions/i })
  expect(talk.closest('[aria-sort]')?.getAttribute('aria-sort'))
    .toBe('descending')
})

it('is not hidden from assistive tech', () => {
  const { container } = render(
    <SortCols selection={selection} onChange={vi.fn()} />)
  // A focusable button inside aria-hidden is an a11y violation, not a
  // cosmetic one: it is reachable by keyboard and absent from the tree.
  expect(container.querySelector('.cols')?.getAttribute('aria-hidden')).toBeNull()
})
