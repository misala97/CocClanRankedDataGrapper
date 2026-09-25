import { act, render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { Crash, mount } from './mount'

afterEach(() => {
  vi.unstubAllGlobals()
  vi.restoreAllMocks()
  document.body.innerHTML = ''
})

function Boom(): never {
  throw new Error('drawn wrong')
}

describe('mount (G-150)', () => {
  it('draws the page from the payload the document carries', async () => {
    document.body.innerHTML = '<script type="application/json" id="gym-data">{"name":"Push"}</script>'
      + '<main id="gym-root"></main>'
    await act(async () => { mount<{ name: string }>((payload) => <h1>{payload.name}</h1>) })
    expect(screen.getByRole('heading', { name: 'Push' })).toBeInTheDocument()
  })

  it('says a page could not draw itself, and offers the reload', async () => {
    vi.spyOn(console, 'error').mockImplementation(() => {})
    const reload = vi.fn()
    vi.stubGlobal('location', { ...window.location, reload })
    document.body.innerHTML = '<script type="application/json" id="gym-data">{}</script>'
      + '<main id="gym-root"></main>'
    await act(async () => { mount(() => <Boom />) })

    expect(screen.getByRole('alert')).toHaveTextContent('Die Seite konnte nicht angezeigt werden.')
    await userEvent.click(screen.getByRole('button', { name: 'Neu laden' }))
    expect(reload).toHaveBeenCalledOnce()
  })

  it('draws the page itself while nothing fails', () => {
    render(<Crash><p>fine</p></Crash>)
    expect(screen.getByText('fine')).toBeInTheDocument()
    expect(screen.queryByRole('alert')).toBeNull()
  })
})
