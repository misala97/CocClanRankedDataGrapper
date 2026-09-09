import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, beforeEach, describe, expect, it } from 'vitest'

import { payload } from '../fixtures'
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
    fireEvent.click(link, { ctrlKey: true })
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

  it('lets an admin open the admin page', () => {
    window.history.replaceState(null, '', '/radar/hub/#admin')
    mount({ isAdmin: true })
    expect(screen.queryByText(/is for administrators/i)).not.toBeInTheDocument()
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
