// The controls that change which board the server builds.
//
// The feed checkboxes carry the one rule with teeth: the selection can never
// become empty, because an empty source list is not a board the API can build.
// The first implementation "handled" that by selecting every OTHER feed, which
// answers a question the reader did not ask -- unchecking Reddit turned the
// board into Bluesky and 4chan. These tests assert what the selection IS after
// the click, not merely that it is non-empty, which is the assertion that let
// that through.
import { fireEvent, render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it, vi } from 'vitest'

import { payload } from '../fixtures'
import type { Selection } from '../types'
import { Filters, toggle } from './Filters'
import { selectionOf } from './queries'

const board = payload()
const base: Selection = selectionOf(board)

/** Renders the filters WITH the secondary disclosure already open.
 *
 *  Breadth and the feed checkboxes moved behind "More filters" in the VC1
 *  correction. They are hidden, not removed, so these tests open the
 *  disclosure and then assert exactly what they asserted before: every rule
 *  about the last remaining feed is unchanged. */
function show(sources: string[], onChange = vi.fn()) {
  render(<Filters board={board} selection={{ ...base, sources }}
                  onChange={onChange} />)
  fireEvent.click(screen.getByRole('button', { name: /more filters/i }))
  return onChange
}

const feed = (name: RegExp) => screen.getByRole('checkbox', { name })

describe('the feed checkboxes', () => {
  it('lights a feed its concrete venue belongs to', () => {
    // A link naming one subreddit keeps the Reddit chip lit rather than
    // lighting none.
    show(['reddit:wallstreetbets'])
    expect(feed(/reddit/i)).toBeChecked()
    expect(feed(/bluesky/i)).not.toBeChecked()
  })

  it('removes one feed and leaves the rest exactly as they were', async () => {
    const onChange = show(['bluesky', 'fourchan', 'reddit'])
    await userEvent.click(feed(/4chan/i))
    expect(onChange).toHaveBeenCalledWith(
      expect.objectContaining({ sources: ['bluesky', 'reddit'] }))
  })

  it('adds a feed without disturbing the others', async () => {
    const onChange = show(['bluesky'])
    await userEvent.click(feed(/reddit/i))
    expect(onChange).toHaveBeenCalledWith(
      expect.objectContaining({ sources: ['bluesky', 'reddit'] }))
  })

  it('drops every concrete venue under the feed being removed', async () => {
    const onChange = show(['bluesky', 'reddit:wallstreetbets', 'reddit:options'])
    await userEvent.click(feed(/reddit/i))
    expect(onChange).toHaveBeenCalledWith(
      expect.objectContaining({ sources: ['bluesky'] }))
  })
})

describe('the last remaining feed', () => {
  it('keeps the selection when its only feed is unchecked', async () => {
    // The failure this replaces: sources went from ['reddit'] to
    // ['bluesky','fourchan'] -- a board of two feeds the reader never picked,
    // fetched immediately, under controls that then showed Reddit unchecked.
    const onChange = show(['reddit'])
    await userEvent.click(feed(/reddit/i))

    // Nothing is asked for at all. This is what discriminates: with the
    // defect the click reported ['bluesky','fourchan'] and a board of two
    // feeds nobody picked was fetched immediately.
    expect(onChange).not.toHaveBeenCalled()
  })

  it('keeps a concrete venue selection when its only feed is unchecked', async () => {
    const onChange = show(['reddit:wallstreetbets'])
    await userEvent.click(feed(/reddit/i))

    expect(onChange).not.toHaveBeenCalled()
    expect(feed(/reddit/i)).toBeChecked()
  })

  it('says why it cannot be unchecked rather than ignoring the click', () => {
    // A control that silently does nothing is the same defect wearing a
    // different face. aria-disabled and not disabled, so the keyboard reader
    // this description exists for can still reach it -- the board's own
    // recorded decision, in board/Controls.tsx.
    show(['reddit'])
    const only = feed(/reddit/i)
    expect(only).toHaveAttribute('aria-disabled', 'true')
    expect(only).not.toBeDisabled()
    expect(only).toHaveAccessibleDescription(/one feed has to stay on/i)
  })

  it('says nothing about a floor nobody is standing on', () => {
    // The note used to render on every board, including the default with all
    // three feeds on and nothing locked.
    show(['bluesky', 'reddit'])
    expect(screen.queryByText(/one feed has to stay on/i))
      .not.toBeInTheDocument()
  })

  it('is unlocked again as soon as a second feed is on', () => {
    show(['bluesky', 'reddit'])
    expect(feed(/reddit/i)).not.toHaveAttribute('aria-disabled')
    expect(feed(/bluesky/i)).not.toHaveAttribute('aria-disabled')
  })

  it('counts concrete venues under one feed as one feed', () => {
    // Two subreddits are still only Reddit, so Reddit is still the last one.
    show(['reddit:wallstreetbets', 'reddit:options'])
    expect(feed(/reddit/i)).toHaveAttribute('aria-disabled', 'true')
  })
})

describe('the server-side filters', () => {
  it('asks for All with an empty segment rather than omitting it', async () => {
    const onChange = vi.fn()
    render(<Filters board={board} selection={{ ...base, segments: ['large'] }}
                    onChange={onChange} />)
    await userEvent.selectOptions(screen.getByLabelText(/size/i), 'all')
    expect(onChange).toHaveBeenCalledWith(
      expect.objectContaining({ segments: [] }))
  })

  it('offers only the windows and breadths the API accepts', () => {
    show(['bluesky', 'reddit'])
    const windows = Array.from(
      screen.getByLabelText(/window/i).querySelectorAll('option'))
      .map((option) => option.value)
    expect(windows).toEqual(['1', '4', '12', '24'])

    const venues = Array.from(
      screen.getByLabelText(/breadth/i).querySelectorAll('option'))
      .map((option) => option.value)
    expect(venues).toEqual(['1', '2'])
  })
})

// The disabled checkbox is an affordance; this is the invariant. Tested
// directly, because a test that only clicks a disabled input passes whether
// the reducer refuses or not.
describe('the reducer behind the checkboxes', () => {
  it('refuses to empty the selection', () => {
    expect(toggle(['reddit'], 'reddit')).toEqual(['reddit'])
    expect(toggle(['reddit:wallstreetbets'], 'reddit'))
      .toEqual(['reddit:wallstreetbets'])
    expect(toggle(['reddit:options', 'reddit:wallstreetbets'], 'reddit'))
      .toEqual(['reddit:options', 'reddit:wallstreetbets'])
  })

  it('never answers with a feed the reader did not select', () => {
    // The defect: unchecking the only feed returned every OTHER feed.
    const after = toggle(['reddit'], 'reddit')
    expect(after).not.toContain('bluesky')
    expect(after).not.toContain('fourchan')
  })

  it('removes a feed and its venues when another one remains', () => {
    expect(toggle(['bluesky', 'reddit'], 'reddit')).toEqual(['bluesky'])
    expect(toggle(['bluesky', 'reddit:options'], 'reddit')).toEqual(['bluesky'])
  })

  it('adds a feed that is off', () => {
    expect(toggle(['bluesky'], 'reddit')).toEqual(['bluesky', 'reddit'])
  })

  it('signals a refusal by identity, so a caller can tell it apart', () => {
    // The component reads this to decide whether to report anything at all;
    // reporting an unchanged selection would push a dead history entry.
    const only = ['reddit']
    expect(toggle(only, 'reddit')).toBe(only)
    expect(toggle(['bluesky', 'reddit'], 'reddit')).not.toBe(only)
  })

  it('roots the source it was given, not only the ones it holds', () => {
    // Exported, so it can be called with a concrete venue. Rooting one side
    // only made this a remove that silently appended a duplicate.
    expect(toggle(['reddit:options'], 'reddit:options'))
      .toEqual(['reddit:options'])
    expect(toggle(['bluesky', 'reddit:options'], 'reddit:options'))
      .toEqual(['bluesky'])
  })
})
