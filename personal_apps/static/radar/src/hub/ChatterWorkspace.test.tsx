// The workspace, driven through the hub -- because most of what it promises
// is about the address bar, the history and the number of requests, and none
// of that exists in a component rendered on its own.
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import * as api from '../api'
import { BoardUnavailable } from '../api'
import { detail, payload, row } from '../fixtures'
import { Hub } from './Hub'

const board = payload({ rows: [
  row({ ticker: 'MID', name: 'Middle Co', authors: 5 }),
  row({ ticker: 'TOP', name: 'Top Co', authors: 10 }),
  row({ ticker: 'LOW', name: 'Low Co', authors: 2 }),
] })

function mount(initial = board, isAdmin = false) {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  })
  return render(
    <QueryClientProvider client={client}>
      <Hub initial={initial} isAdmin={isAdmin} />
    </QueryClientProvider>,
  )
}

const railTickers = () =>
  Array.from(document.querySelectorAll('.rh-candidate .rh-ticker'))
    .map((node) => node.textContent)

const selectedTicker = () =>
  document.querySelector('.rh-candidate.selected .rh-ticker')?.textContent

/** Which company the centre column is showing. Read from the heading's own
 *  ticker rather than the name: the detail fixture gives every ticker the
 *  same company name, and a test that cannot tell two companies apart is not
 *  testing that the right one is on screen. */
const centre = () =>
  document.querySelector('.rh-selectedticker')?.textContent

const showing = async (ticker: string) => {
  await waitFor(() => expect(centre()).toBe(ticker))
}

/** Clear the selection through the control that does it.
 *
 *  Fired at the element rather than found by role: the stylesheet IS loaded
 *  in this environment, and `Back to candidates` is `display: none` on the
 *  desk layout, where the candidate rail is sitting right there instead.
 *  Whether it is visible at a given width is the responsive rules' business;
 *  this is about what clearing does to the state. */
const clearSelection = () => {
  const back = document.querySelector<HTMLButtonElement>(
    '.rh-backtolist button')
  expect(back).not.toBeNull()
  fireEvent.click(back!)
}

/** jsdom has no `matchMedia`, so without this the width guard is skipped
 *  wholesale and every test runs the desk path -- the sequential-screen
 *  branch could have been deleted without a failure. */
function viewport(sideBySide: boolean) {
  vi.stubGlobal('matchMedia', (query: string) => ({
    matches: sideBySide,
    media: query,
    onchange: null,
    addEventListener: () => {},
    removeEventListener: () => {},
    addListener: () => {},
    removeListener: () => {},
    dispatchEvent: () => false,
  }))
}

beforeEach(() => {
  viewport(true)
  window.history.replaceState(null, '', '/radar/hub/#chatter')
  vi.spyOn(api, 'fetchBoard').mockResolvedValue(board)
  vi.spyOn(api, 'fetchDetail').mockImplementation(
    async (ticker: string) => detail(ticker))
})

afterEach(() => {
  vi.restoreAllMocks()
  window.history.replaceState(null, '', '/radar/hub/')
})

describe('opening the workspace', () => {
  it('opens on the first candidate without a history entry', async () => {
    // The length BEFORE, because jsdom's history is shared across the file.
    // This is the assertion that actually separates replace from push: under
    // a push, one Back would still land on `#chatter/MID`, so stepping back
    // proves nothing at all.
    const before = window.history.length
    mount()
    await waitFor(() => expect(window.location.hash).toBe('#chatter/MID'))
    expect(selectedTicker()).toBe('MID')
    expect(window.history.length).toBe(before)
  })

  it('leaves the list alone where the two columns do not fit', async () => {
    // Sequential screens: a reader who asked for the candidate list must not
    // be dropped into a company they did not choose.
    viewport(false)
    mount()
    expect(await screen.findByText(/Pick a candidate/i)).toBeVisible()
    await new Promise((resolve) => setTimeout(resolve, 50))
    expect(window.location.hash).toBe('#chatter')
    expect(api.fetchDetail).not.toHaveBeenCalled()
  })

  it('asks for one detail, not one per row', async () => {
    mount()
    await waitFor(() => expect(api.fetchDetail).toHaveBeenCalled())
    await showing('MID')
    const asked = (api.fetchDetail as ReturnType<typeof vi.fn>).mock.calls
      .map((call) => call[0])
    expect(new Set(asked)).toEqual(new Set(['MID']))
  })

  it('says so, and asks for nothing, when the board is empty', async () => {
    mount(payload({ rows: [], excluded: { floor: 4 } }))
    expect(await screen.findByText(/Pick a candidate/i)).toBeVisible()
    expect(window.location.hash).toBe('#chatter')
    expect(api.fetchDetail).not.toHaveBeenCalled()
  })
})

describe('choosing a company', () => {
  it('pushes history, and Back and Forward restore the choice', async () => {
    mount()
    await waitFor(() => expect(window.location.hash).toBe('#chatter/MID'))

    await userEvent.click(screen.getByRole('link', { name: /TOP Top Co/ }))
    await waitFor(() => expect(window.location.hash).toBe('#chatter/TOP'))
    await showing('TOP')

    window.history.back()
    await waitFor(() => expect(window.location.hash).toBe('#chatter/MID'))
    await waitFor(() => expect(selectedTicker()).toBe('MID'))

    window.history.forward()
    await waitFor(() => expect(window.location.hash).toBe('#chatter/TOP'))
    await waitFor(() => expect(selectedTicker()).toBe('TOP'))
  })

  it('marks the chosen candidate for a screen reader, not only in colour',
    async () => {
      mount()
      await waitFor(() => expect(window.location.hash).toBe('#chatter/MID'))
      await userEvent.click(screen.getByRole('link', { name: /TOP Top Co/ }))
      await waitFor(() => {
        expect(screen.getByRole('link', { name: /TOP Top Co/ }))
          .toHaveAttribute('aria-current', 'true')
      })
      expect(screen.getByRole('link', { name: /MID Middle Co/ }))
        .not.toHaveAttribute('aria-current')
    })

  it('never shows the previous company under the new one’s heading',
    async () => {
      const gate: { open?: () => void } = {}
      const held = new Promise<void>((resolve) => { gate.open = resolve })
      vi.spyOn(api, 'fetchDetail').mockImplementation(
        async (ticker: string) => {
          if (ticker === 'TOP') await held
          return detail(ticker)
        })

      mount()
      await showing('MID')
      await userEvent.click(screen.getByRole('link', { name: /TOP Top Co/ }))

      // The reply for TOP has not landed. MID's panel must not be sitting
      // under TOP's heading and address in the meantime.
      await screen.findByText(/Loading TOP/i)
      expect(centre()).toBeUndefined()
      gate.open?.()
      await showing('TOP')
    })

  it('keeps the selection when a new board arrives in a new order', async () => {
    mount()
    await waitFor(() => expect(window.location.hash).toBe('#chatter/MID'))
    await userEvent.click(screen.getByRole('link', { name: /LOW Low Co/ }))
    await waitFor(() => expect(window.location.hash).toBe('#chatter/LOW'))

    // A refresh that reorders the list must not move the reader onto
    // whatever is now first.
    ;(api.fetchBoard as ReturnType<typeof vi.fn>).mockResolvedValue(
      payload({ rows: [
        row({ ticker: 'TOP', name: 'Top Co', authors: 10 }),
        row({ ticker: 'MID', name: 'Middle Co', authors: 5 }),
        row({ ticker: 'LOW', name: 'Low Co', authors: 2 }),
      ] }))
    await userEvent.click(screen.getByRole('button', { name: /^Filters/ }))
    await userEvent.selectOptions(screen.getByLabelText(/window/i), '1')

    await waitFor(() => expect(railTickers()).toEqual(['TOP', 'MID', 'LOW']))
    expect(window.location.hash).toBe('#chatter/LOW')
    expect(selectedTicker()).toBe('LOW')
  })
})

describe('the centre and the rail fail separately', () => {
  it('keeps the evidence rail while the centre is loading', async () => {
    const gate: { open?: () => void } = {}
    const held = new Promise<void>((resolve) => { gate.open = resolve })
    ;(api.fetchDetail as ReturnType<typeof vi.fn>).mockImplementation(
      async (ticker: string) => {
        if (ticker === 'TOP') await held
        return detail(ticker)
      })

    mount()
    await showing('MID')
    await userEvent.click(screen.getByRole('link', { name: /TOP Top Co/ }))
    await screen.findByText(/Loading TOP/i)

    // Every figure in the rail came from the board row, which was in hand
    // before the detail request was made. Blanking it would throw away
    // evidence that never depended on the thing still loading -- and take
    // the Watch control, the page's only write, with it.
    const rail = screen.getByRole('complementary',
                                 { name: /evidence at a glance/i })
    expect(within(rail).getByText(/Human chatter for TOP/)).toBeVisible()
    expect(within(rail).getByText('10')).toBeVisible()
    expect(within(rail).getByRole('button', { name: /watch TOP/i })).toBeVisible()
    gate.open?.()
    await showing('TOP')
  })

  it('keeps the evidence rail when the centre fails outright', async () => {
    ;(api.fetchDetail as ReturnType<typeof vi.fn>).mockRejectedValue(
      new BoardUnavailable('missing'))
    window.history.replaceState(null, '', '/radar/hub/#chatter/TOP')
    mount()

    expect(await screen.findByText(/No panel for TOP/i)).toBeVisible()
    const rail = screen.getByRole('complementary',
                                 { name: /evidence at a glance/i })
    expect(within(rail).getByText(/Human chatter for TOP/)).toBeVisible()
    expect(within(rail).getByRole('button', { name: /watch TOP/i })).toBeVisible()
  })
})

describe('a selection the list does not hold', () => {
  it('keeps the company and says it is outside the candidates', async () => {
    mount()
    await waitFor(() => expect(window.location.hash).toBe('#chatter/MID'))
    await userEvent.click(screen.getByRole('link', { name: /TOP Top Co/ }))
    await showing('TOP')

    await userEvent.type(screen.getByLabelText(/filter companies/i), 'LOW')

    expect(await screen.findByText(/Outside this candidate list/i)).toBeVisible()
    // Still the company that was chosen, not a substitute.
    expect(centre()).toBe('TOP')
    expect(railTickers()).toEqual(['LOW'])

    await userEvent.click(
      screen.getByRole('button', { name: /open the first candidate instead/i }))
    await waitFor(() => expect(window.location.hash).toBe('#chatter/LOW'))
  })

  it('blames the filter only when the filter is the reason', async () => {
    // A company the text filter hides is on this board and one keystroke
    // away. A company that never ranked here is a different absence, and
    // sending the reader to clear a filter that is not the cause is the
    // wrong instruction.
    mount()
    await waitFor(() => expect(window.location.hash).toBe('#chatter/MID'))
    await userEvent.type(screen.getByLabelText(/filter companies/i), 'LOW')
    expect(await screen.findByText(/is on this board, but the filter/i))
      .toBeVisible()
  })

  it('says a company that never ranked here did not rank here', async () => {
    window.history.replaceState(null, '', '/radar/hub/#chatter/ELSE')
    mount()
    await showing('ELSE')
    expect(await screen.findByText(/did not rank on this board at all/i))
      .toBeVisible()
  })

  it('reports a deep link the server has no panel for', async () => {
    ;(api.fetchDetail as ReturnType<typeof vi.fn>).mockRejectedValue(
      new BoardUnavailable('missing'))
    window.history.replaceState(null, '', '/radar/hub/#chatter/NOPE')
    mount()

    expect(await screen.findByText(/No panel for NOPE/i)).toBeVisible()
    // No substitution: the candidate list is still there and still usable.
    expect(railTickers()).toEqual(['MID', 'TOP', 'LOW'])
  })

  it('scopes a failed detail to the centre, leaving the list usable',
    async () => {
      ;(api.fetchDetail as ReturnType<typeof vi.fn>).mockRejectedValue(
        new BoardUnavailable('server'))
      window.history.replaceState(null, '', '/radar/hub/#chatter/TOP')
      mount()

      // A server failure is retried twice inside the query before it is
      // reported, which is longer than the default assertion window.
      expect(await screen.findByRole('button', { name: /try again/i },
                                     { timeout: 5000 })).toBeVisible()
      expect(railTickers()).toEqual(['MID', 'TOP', 'LOW'])

      ;(api.fetchDetail as ReturnType<typeof vi.fn>)
        .mockResolvedValue(detail('TOP'))
      await userEvent.click(screen.getByRole('button', { name: /try again/i }))
      await showing('TOP')
    })

  it('treats a malformed company in the address as the bare list', async () => {
    window.history.replaceState(null, '', '/radar/hub/#chatter/%E0%A4%A')
    mount()
    // A broken escape is not a company and not a missing page: it is the
    // list, which then opens on its own first candidate.
    await waitFor(() => expect(window.location.hash).toBe('#chatter/MID'))
  })
})

describe('the two readings of the list', () => {
  it('carries the filter and the ordering across the toggle', async () => {
    mount()
    await waitFor(() => expect(window.location.hash).toBe('#chatter/MID'))

    await userEvent.type(screen.getByLabelText(/filter companies/i), 'o')
    await userEvent.selectOptions(screen.getByLabelText(/sort by/i), 'voices')
    await waitFor(() => expect(railTickers()).toEqual(['TOP', 'MID', 'LOW']))

    await userEvent.click(screen.getByRole('button', { name: 'Table' }))
    const listed = screen.getAllByTestId('rh-row-ticker').map((n) => n.textContent)
    expect(listed).toEqual(['TOP', 'MID', 'LOW'])
    expect(screen.getByLabelText(/filter companies/i)).toHaveValue('o')

    await userEvent.click(screen.getByRole('button', { name: 'Research' }))
    await waitFor(() => expect(railTickers()).toEqual(['TOP', 'MID', 'LOW']))
    expect(screen.getByLabelText(/filter companies/i)).toHaveValue('o')
  })

  it('does not put a company back after the reader cleared one', async () => {
    // The workspace unmounts on every toggle. When the opening selection was
    // remembered inside it, coming back from the table re-selected the first
    // row -- with replaceState, which destroyed the `#chatter` entry the
    // reader was standing on and took their Back with it.
    mount()
    await waitFor(() => expect(window.location.hash).toBe('#chatter/MID'))
    clearSelection()
    await waitFor(() => expect(window.location.hash).toBe('#chatter'))

    await userEvent.click(screen.getByRole('button', { name: 'Table' }))
    await userEvent.click(screen.getByRole('button', { name: 'Research' }))

    await screen.findByText(/Pick a candidate/i)
    expect(window.location.hash).toBe('#chatter')
  })

  it('stays cleared after a deep link the reader backed out of', async () => {
    // The other way to reach a cleared list: arrive ON a company, so the
    // opening-selection effect never runs, then press back to the
    // candidates. Without clearing being treated as the decision it is, the
    // effect fires for the first time right then and replaces the entry the
    // reader just asked for.
    window.history.replaceState(null, '', '/radar/hub/#chatter/TOP')
    mount()
    await showing('TOP')
    clearSelection()

    await screen.findByText(/Pick a candidate/i)
    await new Promise((resolve) => setTimeout(resolve, 60))
    expect(window.location.hash).toBe('#chatter')
  })

  it('opens on a candidate again on a fresh visit to the list', async () => {
    // Leaving Human chatter ends the visit; returning is a new one, and a
    // new one opens on a candidate the way the first did.
    mount()
    await waitFor(() => expect(window.location.hash).toBe('#chatter/MID'))
    clearSelection()
    await waitFor(() => expect(window.location.hash).toBe('#chatter'))

    await userEvent.click(screen.getByRole('link', { name: 'Overview' }))
    await waitFor(() => expect(window.location.hash).toBe('#overview'))
    await userEvent.click(screen.getByRole('link', { name: 'Human chatter' }))

    await waitFor(() => expect(window.location.hash).toBe('#chatter/MID'))
  })

  it('opens a company from the table into the workspace', async () => {
    mount()
    await waitFor(() => expect(window.location.hash).toBe('#chatter/MID'))
    await userEvent.click(screen.getByRole('button', { name: 'Table' }))

    await userEvent.click(screen.getByRole('button', { name: /^LOW Low Co/ }))
    await waitFor(() => expect(window.location.hash).toBe('#chatter/LOW'))
    // The table cannot show a company; asking for one moves to the reading
    // that can.
    await showing('LOW')
    expect(selectedTicker()).toBe('LOW')
  })
})

describe('reaching it from the keyboard', () => {
  it('moves between the evidence tabs with the arrow keys', async () => {
    mount()
    await showing('MID')
    const evidence = screen.getByRole('tab', { name: 'Evidence' })
    const posts = screen.getByRole('tab', { name: /Source posts/ })
    // One tab stop for the set, arrows to move within it.
    expect(evidence).toHaveAttribute('tabindex', '0')
    expect(posts).toHaveAttribute('tabindex', '-1')

    evidence.focus()
    await userEvent.keyboard('{ArrowRight}')
    expect(posts).toHaveAttribute('aria-selected', 'true')
    expect(posts).toHaveFocus()
    // And it wraps, rather than stopping at the end of the set.
    await userEvent.keyboard('{ArrowRight}')
    expect(evidence).toHaveAttribute('aria-selected', 'true')
  })

  it('closes a rail disclosure on Escape without losing the company',
    async () => {
      mount()
      await showing('MID')
      const toggle = document.querySelector<HTMLButtonElement>(
        '.rh-evidence .rh-detailtoggle')!
      await userEvent.click(toggle)
      expect(toggle).toHaveAttribute('aria-expanded', 'true')

      await userEvent.keyboard('{Escape}')
      expect(toggle).toHaveAttribute('aria-expanded', 'false')
      expect(toggle).toHaveFocus()
      // Escape closes the disclosure it was opened from. It does not travel
      // on to anything else that listens for it, and above all it does not
      // reset the selected company.
      expect(window.location.hash).toBe('#chatter/MID')
      expect(selectedTicker()).toBe('MID')
    })
})

describe('the evidence rail', () => {
  it('reads the selected company’s own board row', async () => {
    mount()
    await showing('MID')
    const rail = screen.getByRole('complementary', { name: /evidence at a glance/i })
    expect(within(rail).getByText(/Human chatter for MID/)).toBeVisible()
    expect(within(rail).getByText('Voices')).toBeVisible()
    expect(within(rail).getByText('5')).toBeVisible()
  })

  it('says the figures are unknown for a company with no row here', async () => {
    window.history.replaceState(null, '', '/radar/hub/#chatter/ELSE')
    mount()
    await showing('ELSE')
    const rail = screen.getByRole('complementary', { name: /evidence at a glance/i })
    expect(within(rail).getByText(/has no row for ELSE/i)).toBeVisible()
  })

  it('marks a company through the one authenticated write', async () => {
    const marked = payload({ rows: board.rows, watching: ['MID'] })
    const setWatch = vi.spyOn(api, 'setWatch').mockResolvedValue(['MID'])
    ;(api.fetchBoard as ReturnType<typeof vi.fn>).mockResolvedValue(marked)

    mount(payload({ rows: board.rows, watching: [] }))
    await showing('MID')
    await userEvent.click(screen.getByRole('button', { name: /watch MID/i }))

    expect(setWatch).toHaveBeenCalledWith('MID', true)
    await waitFor(() => {
      expect(screen.getByRole('button', { name: /watching/i }))
        .toHaveAttribute('aria-pressed', 'true')
    })
  })

  it('refuses a second press while the first write is in flight', async () => {
    const gate: { open?: (v: string[]) => void } = {}
    vi.spyOn(api, 'setWatch').mockImplementation(
      () => new Promise((resolve) => { gate.open = resolve }))

    mount(payload({ rows: board.rows, watching: [] }))
    await showing('MID')
    const watch = screen.getByRole('button', { name: /watch MID/i })
    await userEvent.click(watch)

    // Disabled until the answer lands, so two presses cannot land out of
    // order and leave the mark in whichever state replied last.
    await waitFor(() => expect(watch).toBeDisabled())
    expect(watch).toHaveTextContent(/saving/i)
    gate.open?.(['MID'])
    await waitFor(() => expect(watch).not.toBeDisabled())
  })

  it('says a refused mark was refused and leaves the marks alone', async () => {
    vi.spyOn(api, 'setWatch').mockRejectedValue(new BoardUnavailable('server'))
    mount(payload({ rows: board.rows, watching: [] }))
    await showing('MID')
    await userEvent.click(screen.getByRole('button', { name: /watch MID/i }))

    expect(await screen.findByText(/could not be saved/i)).toBeVisible()
    expect(screen.getByRole('button', { name: /watch MID/i }))
      .toHaveAttribute('aria-pressed', 'false')
  })
})
