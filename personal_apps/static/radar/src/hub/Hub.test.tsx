import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import * as api from '../api'
import { BoardUnavailable } from '../api'
import { payload, row } from '../fixtures'
import { Hub } from './Hub'

const initial = payload()

function mount(props: Partial<Parameters<typeof Hub>[0]> = {}) {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  })
  return render(
    <QueryClientProvider client={client}>
      <Hub initial={initial} isAdmin={false} {...props} />
    </QueryClientProvider>,
  )
}

beforeEach(() => {
  window.history.replaceState(null, '', '/radar/hub/')
})

afterEach(() => {
  window.history.replaceState(null, '', '/radar/hub/')
})

describe('the shell', () => {
  it('opens on the overview', () => {
    mount()
    expect(screen.getByRole('main')).toHaveAccessibleName('Overview')
    expect(screen.getByRole('link', { name: 'Overview' }))
      .toHaveAttribute('aria-current', 'page')
  })

  it('offers only destinations this release renders', () => {
    mount()
    const nav = screen.getByRole('navigation', { name: 'Radar' })
    const labels = Array.from(nav.querySelectorAll('a')).map((a) => a.textContent)
    expect(labels).toEqual(['Overview', 'Human chatter', 'Watching', 'Activity'])
    // The prototype's other pages are roadmap, not disabled nav items.
    for (const absent of ['News', 'Portfolio', 'Analysis', 'Combined']) {
      expect(screen.queryByRole('link', { name: new RegExp(absent, 'i') }))
        .not.toBeInTheDocument()
    }
  })

  it('shows Administration to an admin and to nobody else', () => {
    const plain = mount()
    expect(screen.queryByRole('link', { name: 'Administration' }))
      .not.toBeInTheDocument()
    plain.unmount()

    mount({ isAdmin: true })
    expect(screen.getByRole('link', { name: 'Administration' })).toBeVisible()
  })

  it('opens the page named in the address bar', () => {
    window.history.replaceState(null, '', '/radar/hub/#watching')
    mount()
    expect(screen.getByRole('main')).toHaveAccessibleName('Watching')
  })

  it('opens a direct research link', () => {
    window.history.replaceState(null, '', '/radar/hub/#research/AAA')
    mount()
    expect(screen.getByRole('main')).toHaveAccessibleName('AAA')
  })

  it('offers a way back from an address that does not exist', async () => {
    window.history.replaceState(null, '', '/radar/hub/#portfolio')
    mount()
    expect(screen.getByText(/nothing at this address/i)).toBeVisible()

    await userEvent.click(screen.getByRole('button', { name: /overview/i }))
    expect(screen.getByRole('main')).toHaveAccessibleName('Overview')
  })

  it('restores the page on Back', async () => {
    mount()
    await userEvent.click(screen.getByRole('link', { name: 'Activity' }))
    expect(screen.getByRole('main')).toHaveAccessibleName('Activity')
    expect(window.location.hash).toBe('#activity')

    // jsdom dispatches popstate asynchronously, so this waits for the
    // listener under test rather than for a render.
    window.history.back()
    await waitFor(() => {
      expect(screen.getByRole('main')).toHaveAccessibleName('Overview')
    })
  })

  it('carries the reader’s filters through every link', () => {
    window.history.replaceState(null, '', '/radar/hub/?market=de&window=24#overview')
    mount()
    const link = screen.getByRole('link', { name: 'Human chatter' })
    expect(link.getAttribute('href')).toContain('market=de')
    expect(link.getAttribute('href')).toContain('window=24')
  })

  it('leaves a modified click to the browser', () => {
    mount()
    const link = screen.getByRole('link', { name: 'Activity' })
    // A ctrl-click is "open this in a new tab", which preventDefault would
    // silently break -- and these are real hrefs precisely so it works.
    // fireEvent, not userEvent: the modifier is the whole subject here, and
    // it has to arrive on the click event the handler reads.
    //
    // The document listener is what makes this test safe to run beside
    // others. It sees the event after the component's handler, so
    // defaultPrevented is the component's own answer -- and then it stops the
    // default itself, because letting a real href through makes jsdom attempt
    // a navigation it cannot perform. That throws asynchronously, on a timer,
    // long after this test has finished, and lands on whichever test happens
    // to be running: the suite failed roughly one run in six, on a different
    // test each time.
    const prevented: boolean[] = []
    const swallow = (event: MouseEvent) => {
      prevented.push(event.defaultPrevented)
      event.preventDefault()
    }
    document.addEventListener('click', swallow)
    try {
      fireEvent.click(link, { ctrlKey: true })
    } finally {
      document.removeEventListener('click', swallow)
    }
    expect(prevented).toEqual([false])
    expect(screen.getByRole('main')).toHaveAccessibleName('Overview')
  })

  it('has a labelled, keyboard-reachable menu toggle', async () => {
    const { container } = mount()
    // Found through the DOM rather than by role: the toggle is display:none
    // above 700px, this environment applies the stylesheet but not the media
    // query, and an element hidden that way has no accessible name to query
    // by. Its label and wiring are asserted directly instead; what is under
    // test is the control, not the breakpoint.
    const menu = container.querySelector<HTMLButtonElement>('.rh-menu')!
    expect(menu.getAttribute('aria-label')).toBe('Navigation')
    expect(menu).toHaveAttribute('aria-expanded', 'false')
    expect(menu).toHaveAttribute('aria-controls', 'rh-nav')
    expect(container.querySelector('#rh-nav')).not.toBeNull()

    menu.focus()
    await userEvent.keyboard('{Enter}')
    expect(menu).toHaveAttribute('aria-expanded', 'true')
    expect(container.querySelector('.rh-nav')).toHaveClass('open')
  })

  it('names the market context it is showing', () => {
    const { container } = mount()
    // In the top bar specifically: the page below it names the market too,
    // and this is about the shell's own standing context line.
    expect(container.querySelector('.rh-session')?.textContent)
      .toMatch(/US markets/)
  })

  it('offers a skip link that moves focus and keeps the page', async () => {
    mount()
    const skip = screen.getByRole('link', { name: /skip to the page/i })
    expect(skip).toHaveAttribute('href', '#rh-main')

    // Clicking it used to set the hash to an element id, which the router
    // read as a route name -- so the first control a keyboard reader met
    // replaced the page with "there is nothing at this address".
    await userEvent.click(skip)
    expect(screen.getByRole('main')).toHaveAccessibleName('Overview')
    expect(screen.queryByText(/nothing at this address/i)).not.toBeInTheDocument()
    expect(screen.getByRole('main')).toHaveFocus()
  })

  it('ignores an in-page anchor arriving as a hash change', () => {
    mount()
    window.location.hash = '#rh-main'
    window.dispatchEvent(new HashChangeEvent('hashchange'))
    expect(screen.getByRole('main')).toHaveAccessibleName('Overview')
  })

  it('refuses the admin page to a reader who is not one', () => {
    // The nav link is rendered for admins only, but a typed hash is not a
    // link. The API enforces this too; saying so is the difference between a
    // refusal and an empty page.
    window.history.replaceState(null, '', '/radar/hub/#admin')
    mount({ isAdmin: false })
    expect(screen.getByText(/is for administrators/i)).toBeVisible()
  })

  it('lets an admin open the admin page', async () => {
    vi.spyOn(api, 'fetchOps').mockResolvedValue({
      generated_at: '2026-09-09T10:00:00Z',
      spend: { today_usd: 0, month_usd: 1.25, unpriced_tokens: 0 },
      sentiment: { pending: 0, p95_age_minutes: null,
                   review: { demanded: 0, attempted: 0, served: 0, capped: 0,
                             over_ceiling: 0 } },
      market_data: {
        cycles: {}, mapping_generations: {}, quote_basis_24h: {},
        grouped_closes: { latest_accepted_date: null, retryable_gaps: [],
                          counts: null, error_code: null, http_status: null,
                          backoff_until: null },
        post_close_claims: {},
        de_download_budget_24h: { spent: 0, limit: 40, remaining: 40 },
      },
      capture: { latest_observed_at: null },
    })
    window.history.replaceState(null, '', '/radar/hub/#admin')
    mount({ isAdmin: true })
    // The page itself, not merely the absence of the refusal -- which is also
    // true while nothing has rendered.
    expect(await screen.findByText(/model API spend/i)).toBeVisible()
    expect(screen.queryByText(/is for administrators/i)).not.toBeInTheDocument()
  })

  it('writes one mark at a time, across pages as well as within one', async () => {
    // The guard lives in the shell precisely so leaving Watching mid-write and
    // pressing Watch on a company cannot put two writes in flight.
    const p = payload({ rows: [row({ ticker: 'AAA' })] })
    p.watching = ['AAA']
    p.watch_rows = [row({ ticker: 'AAA' })]
    const setWatch = vi.spyOn(api, 'setWatch')
      .mockReturnValue(new Promise(() => {}))

    window.history.replaceState(null, '', '/radar/hub/#watching')
    mount({ initial: p })

    await userEvent.click(screen.getByRole('button', { name: /stop watching AAA/i }))
    expect(setWatch).toHaveBeenCalledTimes(1)

    // Still in flight; the control is refused rather than queued.
    await userEvent.click(screen.getByRole('button', { name: /removing/i }))
    expect(setWatch).toHaveBeenCalledTimes(1)
  })

  it('never fetches a board of feeds the reader did not pick', async () => {
    // The level Codex named: Filters reports a selection, the shell turns it
    // into a request. With the defect, unchecking the only feed asked the
    // server for the OTHER two -- so this asserts on the request, not on the
    // callback.
    const onlyReddit = payload({ sources: ['reddit'] })
    const fetchBoard = vi.spyOn(api, 'fetchBoard').mockResolvedValue(onlyReddit)

    window.history.replaceState(null, '', '/radar/hub/#chatter')
    mount({ initial: onlyReddit })

    await userEvent.click(
      screen.getByRole('button', { name: /more filters/i }))
    await userEvent.click(screen.getByRole('checkbox', { name: /reddit/i }))

    for (const call of fetchBoard.mock.calls) {
      expect(call[0]!.sources).toEqual(['reddit'])
    }
    expect(window.location.search).not.toContain('bluesky')
    expect(window.location.search).not.toContain('fourchan')
  })

  it('does fetch when a feed selection really changes', async () => {
    // The positive control: without it the test above passes against a hub
    // whose checkboxes are wired to nothing at all.
    const both = payload({ sources: ['bluesky', 'reddit'] })
    const fetchBoard = vi.spyOn(api, 'fetchBoard')
      .mockResolvedValue(payload({ sources: ['bluesky'] }))

    window.history.replaceState(null, '', '/radar/hub/#chatter')
    mount({ initial: both })

    await userEvent.click(
      screen.getByRole('button', { name: /more filters/i }))
    await userEvent.click(screen.getByRole('checkbox', { name: /reddit/i }))
    await waitFor(() => expect(fetchBoard).toHaveBeenCalled())
    expect(fetchBoard.mock.calls[0]![0].sources).toEqual(['bluesky'])
  })

  it('does not carry a failed mark to the next page', async () => {
    const p = payload({ rows: [row({ ticker: 'AAA' })] })
    p.watching = ['AAA']
    p.watch_rows = [row({ ticker: 'AAA' })]
    vi.spyOn(api, 'setWatch').mockRejectedValue(new BoardUnavailable('server'))

    window.history.replaceState(null, '', '/radar/hub/#watching')
    mount({ initial: p })
    await userEvent.click(screen.getByRole('button', { name: /stop watching AAA/i }))
    expect(await screen.findByText(/could not be saved/i)).toBeVisible()

    await userEvent.click(screen.getByRole('link', { name: 'Human chatter' }))
    await waitFor(() => {
      expect(screen.queryByText(/could not be saved/i)).not.toBeInTheDocument()
    })
  })

  it('closes the menu on Escape and returns focus to its toggle', async () => {
    const { container } = mount()
    const menu = container.querySelector<HTMLButtonElement>('.rh-menu')!
    menu.focus()
    await userEvent.keyboard('{Enter}')
    expect(menu).toHaveAttribute('aria-expanded', 'true')

    await userEvent.keyboard('{Escape}')
    expect(menu).toHaveAttribute('aria-expanded', 'false')
    expect(menu).toHaveFocus()
  })
})
