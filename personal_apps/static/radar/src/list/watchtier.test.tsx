import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it, vi } from 'vitest'

import { ListPane } from './ListPane'
import { payload as basePayload, row } from '../fixtures'
import type { BoardPayload, Row, Selection } from '../types'

const r = (ticker: string, over: Partial<Row> = {}): Row => row({ ticker, name: ticker, ...over })

const quiet = (ticker: string): Row => r(ticker, {
  eligible: false, divergence: null, mention_z: null, mentions: 2, expected: 0,
  ratio: null, normal_per_hour: null,
  // Zeros counted, nothing observed: the chart must draw no body from these.
  series: Array.from({ length: 25 }, (_, i) => ({ hour: `h${i}`, count: 0 })),
  clauses: [{ kind: 'warn', text: '2 mentions in 4h, under the floor' }],
})

const selection: Selection = {
  market: 'us', sources: ['bluesky', 'fourchan', 'reddit'], segments: [], window: 4, minVenues: 1,
}

const payload = (over: Partial<BoardPayload> = {}): BoardPayload => basePayload({
  rows: [r('A'), r('B'), r('C')], segment_counts: { all: 3, large: 3 }, ...over,
})

function sequence(container: HTMLElement): string[] {
  return Array.from(container.querySelectorAll('.tier, .row')).map((node) =>
    node.classList.contains('tier')
      ? `tier:${node.textContent!.replace(/\s+/g, ' ').trim().split(' ·')[0]}`
      : `row:${node.querySelector('.tk')!.textContent}${node.classList.contains('quiet') ? '(quiet)' : ''}`)
}

function list(over: Partial<BoardPayload> = {}, onToggleWatch = vi.fn()) {
  const utils = render(
    <ListPane payload={payload(over)} selection={selection} selected={null}
              busy={false} onSelect={() => {}} onChange={() => {}}
              watching={over.watching ?? []} onToggleWatch={onToggleWatch} />)
  return { ...utils, onToggleWatch }
}

describe('the Watching tier', () => {
  it('sits above the scored tier and takes its rows out of the ranked ones', () => {
    const { container } = list({ watching: ['B', 'Q'], watch_rows: [r('B'), quiet('Q')] })

    expect(sequence(container)).toEqual([
      'tier:Watching', 'row:B', 'row:Q(quiet)',
      'tier:Scored against price', 'row:A', 'row:C',
    ])
    expect(screen.getByText(/Scored against price/).closest('.tier')).toHaveTextContent(/\b2\b/)
  })

  it('is absent when nothing is watched', () => {
    list()
    expect(screen.queryByText(/^Watching/)).toBeNull()
  })

  it('shows a freshly starred board row at once, before the refetch brings its watch row', () => {
    /* The star is optimistic; the tier must not wait for the server. */
    const { container } = list({ watching: ['C'], watch_rows: [] })

    expect(sequence(container)).toEqual([
      'tier:Watching', 'row:C', 'tier:Scored against price', 'row:A', 'row:B',
    ])
  })

  it('renders a quiet row with no score and the floor\'s reason', () => {
    const { container } = list({ watching: ['Q'], watch_rows: [quiet('Q')] })

    const q = container.querySelector('.row.quiet')!
    expect(q.querySelector('.score')).toHaveTextContent('—')
    expect(q.querySelector('.sub.warn')).toHaveTextContent('2 mentions in 4h, under the floor')
    expect(q.querySelector('.chart path')).toBeNull()
  })

  it('puts a star beside every row, named for its action', async () => {
    const { onToggleWatch } = list({ watching: ['B'], watch_rows: [r('B')] })

    expect(screen.getByRole('button', { name: 'Stop watching B' })).toHaveAttribute('aria-pressed', 'true')
    await userEvent.click(screen.getByRole('button', { name: 'Watch A' }))

    expect(onToggleWatch).toHaveBeenCalledWith('A')
    // The star is a sibling of the link, never inside it.
    expect(screen.getByRole('button', { name: 'Watch A' }).closest('a')).toBeNull()
    expect(screen.getByRole('link', { name: /^A/ })).toHaveAttribute('id', 'radar-row-A')
  })
})
