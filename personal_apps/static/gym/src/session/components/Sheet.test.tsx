import { act, render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, describe, expect, it } from 'vitest'
import { Sheet } from './Sheet'
import { useSheets } from '../stores'

beforeEach(() => {
  useSheets.setState(useSheets.getInitialState(), true)
})

const Fixture = () => (
  <>
    <Sheet id="sheet-a" title="Erste">a-body</Sheet>
    <Sheet id="sheet-b" title="Zweite">b-body</Sheet>
  </>
)

describe('Sheet', () => {
  it('is closed until the store says otherwise', () => {
    render(<Fixture />)
    expect(document.querySelector('#sheet-a')).not.toHaveAttribute('open')
  })

  it('does not render its contents while it is closed', () => {
    // A closed <dialog> still renders its children, which froze every editor
    // inside a sheet at the values of the last full page load: the set editors
    // on the live screen then showed -- and posted back -- numbers that had
    // since been overwritten. Contents exist only while the sheet is open, so
    // they mount from current state every time it opens.
    render(<Fixture />)
    expect(screen.queryByText('a-body')).not.toBeInTheDocument()
    act(() => { useSheets.getState().open('sheet-a') })
    expect(screen.getByText('a-body')).toBeInTheDocument()
    act(() => { useSheets.getState().close() })
    expect(screen.queryByText('a-body')).not.toBeInTheDocument()
  })

  it('opens the one the store names', () => {
    render(<Fixture />)
    act(() => { useSheets.getState().open('sheet-a') })
    expect(document.querySelector('#sheet-a')).toHaveAttribute('open')
    expect(document.querySelector('#sheet-b')).not.toHaveAttribute('open')
  })

  it('never has two open at once', () => {
    // A sheet on top of a sheet is not a state this design has.
    render(<Fixture />)
    act(() => { useSheets.getState().open('sheet-a') })
    act(() => { useSheets.getState().open('sheet-b') })
    expect(document.querySelector('#sheet-a')).not.toHaveAttribute('open')
    expect(document.querySelector('#sheet-b')).toHaveAttribute('open')
  })

  it('closes from its own dismiss control', async () => {
    const user = userEvent.setup()
    render(<Fixture />)
    act(() => { useSheets.getState().open('sheet-a') })
    await user.click(screen.getAllByText('Fertig')[0]!)
    expect(useSheets.getState().openId).toBeNull()
  })

  it('puts the store back in step when the platform closes it', () => {
    // Esc and a backdrop click close a native <dialog> without going through
    // the store. Without this, openId would keep naming a sheet nobody can
    // see, and reopening it would appear to do nothing.
    render(<Fixture />)
    act(() => { useSheets.getState().open('sheet-a') })
    const node = document.querySelector('#sheet-a') as HTMLDialogElement
    act(() => { node.close() })
    expect(useSheets.getState().openId).toBeNull()
  })

  it('names itself for assistive tech', () => {
    render(<Fixture />)
    act(() => { useSheets.getState().open('sheet-a') })
    const node = document.querySelector('#sheet-a')!
    expect(node).toHaveAttribute('aria-labelledby', 'sheet-a-title')
    expect(document.querySelector('#sheet-a-title')).toHaveTextContent('Erste')
  })
})
