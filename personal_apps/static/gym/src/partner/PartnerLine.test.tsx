import { act, render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { PartnerLines } from './PartnerLine'
import type { PartnerLink } from './types'

/* The partner line (D14, M5 variant A): one per partner, under the header.
 * What it says per state is words.ts; these assert what reaches the screen
 * and the screen reader, and what the line does when touched. */

function link(over: Partial<PartnerLink> = {}): PartnerLink {
  return {
    id: 7, username: 'jglaser', viewer_leads: true, state: 'joined',
    // 09:26 UTC is 11:26 on Berlin's summer clock.
    since: '2026-09-25T09:26:00', finished_at: null,
    exercise: 'Bankdrücken', set_no: 2, done_in_exercise: 1, sets_in_exercise: 3,
    last_set: { weight: 60, reps: 8 }, rest_left: null, sets_done: 4, sets_total: 9, list_key: 1,
    ...over,
  }
}

function mount(links: PartnerLink[], receivedAt = Date.now()) {
  const onOpen = vi.fn()
  const onDismiss = vi.fn()
  const result = render(
    <PartnerLines links={links} receivedAt={receivedAt} onOpen={onOpen} onDismiss={onDismiss} />)
  return { ...result, onOpen, onDismiss }
}

const line = (container: HTMLElement) => container.querySelector('.partner')!

afterEach(() => { vi.useRealTimers() })

describe('PartnerLines', () => {
  it('says where a joined partner is, with their last set of that exercise', () => {
    const { container } = mount([link()])
    expect(line(container)).toHaveClass('is-joined')
    expect(line(container).querySelector('.partner__who'))
      .toHaveTextContent('jglaser · Satz 2 von 3')
    expect(line(container).querySelector('.partner__ex')).toHaveTextContent('Bankdrücken')
    expect(line(container).querySelector('.partner__set')).toHaveTextContent('60,0 × 8')
    // One button, said as a sentence: the chip's "×" and the tile's letter
    // are not read out.
    expect(screen.getByRole('button', {
      name: 'jglaser: Satz 2 von 3, Bankdrücken, zuletzt 60,0 kg mal 8. Liste ansehen',
    })).toHaveAttribute('aria-controls', 'sheet-partner')
    expect(line(container).querySelector('.partner__tile'))
      .toHaveAttribute('aria-hidden', 'true')
  })

  it('shows no chip before their first set of the exercise', () => {
    // The server sends only a set of the named exercise: a set from the one
    // before would read as done here.
    const { container } = mount([link({ set_no: 1, done_in_exercise: 0, last_set: null })])
    expect(line(container).querySelector('.partner__set')).toBeNull()
    expect(line(container)).toHaveTextContent('Satz 1 von 3')
  })

  it('says a rest by the sets done, and turns into the next set when it ends', () => {
    vi.useFakeTimers()
    vi.setSystemTime(new Date('2026-09-25T10:00:00Z'))
    const { container } = mount([link({ rest_left: 30 })])
    expect(line(container)).toHaveTextContent('Pause nach Satz 1 von 3')
    // No poll needed: the rest's own end re-renders the line.
    act(() => { vi.advanceTimersByTime(30_000) })
    expect(line(container)).toHaveTextContent('Satz 2 von 3')
    expect(line(container)).not.toHaveTextContent('Pause')
  })

  it('says a rest into a new exercise by the set ahead', () => {
    const { container } = mount([link({
      rest_left: 60, set_no: 1, done_in_exercise: 0, last_set: null,
    })])
    expect(line(container)).toHaveTextContent('Pause, dann Satz 1 von 3')
  })

  it('counts a rest already over as over', () => {
    // receivedAt is when the answer came: a rest that ended since is not
    // shown as running, however long the page slept.
    const { container } = mount([link({ rest_left: 30 })], Date.now() - 31_000)
    expect(line(container)).toHaveTextContent('Satz 2 von 3')
    expect(line(container)).not.toHaveTextContent('Pause')
  })

  it('says a partner with every set done who has not finished', () => {
    const { container } = mount([link({ set_no: null, done_in_exercise: 3 })])
    expect(line(container)).toHaveTextContent('alle Sätze geschafft')
  })

  it('says a partner with nothing open', () => {
    const { container } = mount([link({
      exercise: null, set_no: null, done_in_exercise: 0, sets_in_exercise: 0, last_set: null,
    })])
    expect(line(container)).toHaveTextContent('jglaser ist dabei')
    expect(line(container)).toHaveTextContent('Keine Übung offen')
    expect(line(container).querySelector('.partner__set')).toBeNull()
  })

  it('says an invite not yet answered, since when', () => {
    const { container } = mount([link({ state: 'invited', exercise: null, last_set: null })])
    expect(line(container)).toHaveClass('is-invited')
    expect(line(container)).toHaveTextContent('jglaser ist eingeladen')
    expect(line(container)).toHaveTextContent('Noch nicht dabei · seit 11:26')
    // The invite still opens: the sheet says what will show once they join.
    expect(screen.getByRole('button', {
      name: 'jglaser ist eingeladen, noch nicht dabei. Liste ansehen',
    })).toBeInTheDocument()
  })

  it('says when the partner finished, and with how much', () => {
    const { container, rerender } = mount([link({
      state: 'finished', finished_at: '2026-09-25T10:10:00', sets_done: 9, sets_total: 9,
    })])
    expect(line(container)).toHaveClass('is-finished')
    expect(line(container)).toHaveTextContent('jglaser ist fertig')
    expect(line(container)).toHaveTextContent('12:10 · alle 9 Sätze')
    const none = () => {}
    rerender(<PartnerLines links={[link({
      state: 'finished', finished_at: '2026-09-25T10:10:00', sets_done: 7, sets_total: 9,
    })]} receivedAt={0} onOpen={none} onDismiss={none} />)
    expect(line(container)).toHaveTextContent('12:10 · 7 von 9 Sätzen')
    rerender(<PartnerLines links={[link({
      state: 'finished', finished_at: '2026-09-25T10:10:00', sets_done: 1, sets_total: 1,
    })]} receivedAt={0} onOpen={none} onDismiss={none} />)
    expect(line(container)).toHaveTextContent('12:10 · 1 Satz')
  })

  it('tells a follower whose leader finished that the order is theirs now', () => {
    const { container } = mount([link({
      state: 'finished', viewer_leads: false, finished_at: '2026-09-25T10:10:00',
      sets_done: 9, sets_total: 9,
    })])
    expect(line(container)).toHaveTextContent('Ab jetzt bestimmst du die Reihenfolge.')
  })

  it('opens the list with the line it was opened from', async () => {
    const user = userEvent.setup()
    const joined = link()
    const { onOpen } = mount([joined])
    await user.click(screen.getByRole('button', { name: /Liste ansehen$/ }))
    expect(onOpen).toHaveBeenCalledWith(joined)
  })

  it('puts a declined invite away with OK, and offers no list', async () => {
    const user = userEvent.setup()
    const { container, onDismiss, onOpen } = mount([link({
      state: 'declined', exercise: null, last_set: null,
    })])
    expect(screen.getByRole('status')).toHaveTextContent('jglaser hat abgelehnt')
    expect(screen.getByRole('status')).toHaveTextContent('Du trainierst allein weiter.')
    expect(screen.queryByRole('button', { name: /Liste ansehen/ })).toBeNull()
    expect(line(container)).toHaveClass('is-declined')
    await user.click(screen.getByRole('button', { name: 'OK' }))
    expect(onDismiss).toHaveBeenCalledWith(7)
    expect(onOpen).not.toHaveBeenCalled()
  })

  it('stacks one line per partner, in the order given, and nothing for none', () => {
    const { container, rerender } = mount([
      link({ id: 3, username: 'anna' }),
      link({ id: 9, username: 'ben', state: 'invited', exercise: null, last_set: null }),
    ])
    const names = [...container.querySelectorAll('.partners > .partner .partner__who b')]
      .map((b) => b.textContent)
    expect(names).toEqual(['anna', 'ben'])
    const none = () => {}
    rerender(<PartnerLines links={[]} receivedAt={0} onOpen={none} onDismiss={none} />)
    expect(container.querySelector('.partners')).toBeNull()
  })

  it('shows a partner by their initial, uppercased', () => {
    const { container } = mount([link({ username: 'ölaf' })])
    expect(container.querySelector('.partner__tile')).toHaveTextContent('Ö')
  })
})
