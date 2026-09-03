import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it, vi } from 'vitest'

import { Controls } from './Controls'
import type { BoardPayload, Selection } from '../types'

const payload = (over: Partial<BoardPayload> = {}): BoardPayload => ({
  generated_at: '2026-08-22T19:00:00Z',
  market: 'us', display_timezone: 'Europe/Berlin',
  market_venue: 'US markets', next_boundary_label: 'closes',
  next_boundary_at: '2026-08-22T20:00:00Z',
  sources: ['bluesky', 'fourchan', 'reddit'],
  all_sources: ['bluesky', 'fourchan', 'reddit'],
  segments: [], session: 'regular', window_hours: 4,
  min_venues: 1, sort: null, dir: 'desc' as const, venue_counts: { any: 37, multi: 35 },
  segment_counts: { all: 37, discover: 9, large: 22, mid: 5, micro: 3,
                    recent_ipo: 1, unknown: 1, fund: 5 },
  triplet_hours: [1, 4, 24], series_hours: 24, lead_count: 3,
  rows: [], excluded: {},
  ...over,
})

const selection = (over: Partial<Selection> = {}): Selection => ({
  market: 'us', sources: ['bluesky', 'fourchan', 'reddit'], segments: [],
  window: 4, minVenues: 1, sort: null, dir: 'desc' as const, ...over,
})

function controls(sel: Selection = selection(), onChange = vi.fn()) {
  render(<Controls payload={payload()} selection={sel} busy={false}
                   onChange={onChange} />)
  return onChange
}

const tab = (name: RegExp) => screen.queryByRole('button', { name })

describe('the views row', () => {
  it('offers the five views and none of the raw sizes by default', () => {
    controls()

    for (const label of [/^All/, /^Discover/, /^Large/, /^IPO/, /^Funds/]) {
      expect(tab(label)).toBeInTheDocument()
    }
    for (const label of [/^Mid/, /^Micro/, /^Unknown/]) {
      expect(tab(label)).toBeNull()
    }
  })

  it('shows Discover\'s members only while Discover is in force', async () => {
    const onChange = controls(selection({ segments: ['discover'] }))

    for (const label of [/^Mid/, /^Micro/, /^Unknown/]) {
      expect(tab(label)).toBeInTheDocument()
    }
    /* A fresh listing is not obscure: IPO is a view of its own, never a
       member of Discover (types.ts). */
    expect(screen.getByText(/within Discover/)).not.toHaveTextContent(/IPO/)

    await userEvent.click(tab(/^Mid/)!)

    expect(onChange).toHaveBeenCalledWith(
      expect.objectContaining({ segments: ['mid'] }))
  })

  it('reads the members as covered, not pressed, when the server echoes the bundle expanded', async () => {
    /* The payload's `segments` comes back as the group AND its members --
       ['discover', 'mid', 'micro', 'unknown'] on the live board -- which is
       what lit four tabs at once on the old strip. While Discover is in
       force a member is covered by it, whatever else the list says. */
    const onChange = controls(
      selection({ segments: ['discover', 'mid', 'micro', 'unknown'] }))

    expect(tab(/^Discover/)).toHaveAttribute('aria-pressed', 'true')
    for (const label of [/^Mid/, /^Micro/, /^Unknown/]) {
      expect(tab(label)).toHaveAttribute('aria-pressed', 'false')
      expect(tab(label)!.className).toContain('covered')
    }

    await userEvent.click(tab(/^Micro/)!)

    expect(onChange).toHaveBeenCalledWith(
      expect.objectContaining({ segments: ['micro'] }))
  })

  it('keeps the members in view while one of them is the filter', () => {
    controls(selection({ segments: ['mid'] }))

    expect(tab(/^Mid/)).toHaveAttribute('aria-pressed', 'true')
    expect(tab(/^Discover/)).toHaveAttribute('aria-pressed', 'false')
    expect(tab(/^Micro/)).toBeInTheDocument()
  })

  it('keeps every view in its slot whatever the counts say', () => {
    render(<Controls payload={payload({ segment_counts: { all: 1, micro: 1 } })}
                     selection={selection()} busy={false} onChange={vi.fn()} />)

    for (const label of [/^All/, /^Discover/, /^Large/, /^IPO/, /^Funds/]) {
      expect(tab(label)).toBeInTheDocument()
    }
  })
})

describe('the summary line', () => {
  it('states the defaults as one sentence and keeps the filters folded', () => {
    controls()

    expect(screen.getByText((_, node) =>
      node?.classList.contains('summary') === true
        && node.textContent!.replace(/\s+/g, ' ').includes('4h · 3 sources · any venue')))
      .toBeInTheDocument()
    expect(tab(/Bluesky/)).toBeNull()
    expect(tab(/^12h/)).toBeNull()
  })

  it('names the sources when one is off, and the floor when it is raised', () => {
    controls(selection({ sources: ['bluesky', 'reddit'], minVenues: 2, sort: null, dir: 'desc' as const, window: 12 }))

    expect(screen.getByText((_, node) =>
      node?.classList.contains('summary') === true
        && node.textContent!.replace(/\s+/g, ' ').includes('12h · Bluesky, Reddit · 2+ venues')))
      .toBeInTheDocument()
  })

  it('unfolds the filters on request, with their behaviour intact', async () => {
    const onChange = controls()

    await userEvent.click(screen.getByRole('button', { name: /change/i }))

    expect(tab(/Bluesky/)).toBeInTheDocument()
    expect(tab(/^12h/)).toBeInTheDocument()
    await userEvent.click(tab(/4chan/)!)
    expect(onChange).toHaveBeenCalledWith(
      expect.objectContaining({ sources: ['bluesky', 'reddit'] }))
  })

  it('will still not let the last source be turned off once unfolded', async () => {
    /* Not `disabled`: that drops the button out of the tab order and its
       `title` is mouse-only, so a keyboard or screen-reader user got neither
       the control nor the reason (critique, 2026-09-01). The reason is
       written next to it instead. */
    const onChange = controls(selection({ sources: ['bluesky'] }))

    await userEvent.click(screen.getByRole('button', { name: /change/i }))

    expect(tab(/Bluesky/)).toHaveAttribute('aria-disabled', 'true')
    expect(tab(/Bluesky/)).not.toBeDisabled()
    expect(tab(/Bluesky/)).toHaveAccessibleDescription(/one source has to stay on/i)
    expect(screen.getByText(/one source has to stay on/i)).toBeVisible()
    await userEvent.click(tab(/Bluesky/)!)
    expect(onChange).not.toHaveBeenCalled()
  })

  it('names the venue floor, which its two tabs do not', async () => {
    /* `any 37 / 2+ 35` next to three source names read as more sources. */
    controls()

    await userEvent.click(screen.getByRole('button', { name: /change/i }))

    expect(screen.getByRole('group', { name: 'Venues' })).toHaveTextContent(/^venues/)
  })
})
