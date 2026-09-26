import { act, fireEvent, render, screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import type { ReactElement } from 'react'
import { afterEach, beforeEach, describe, expect, it, type MockInstance, vi } from 'vitest'
import { SHEET_OPEN_GUARD_MS } from '../../components/useSheetDialog'
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

  describe('a tap on the backdrop (G-108)', () => {
    // jsdom lays nothing out, so the sheet is given its box: the lower half
    // of a 390 x 844 phone. The backdrop's presses land on the <dialog>. The
    // clock is then put past the opening tap's bounce (SHEET_OPEN_GUARD_MS).
    let now: MockInstance<() => number>
    beforeEach(() => { now = vi.spyOn(Date, 'now').mockReturnValue(1_000_000) })
    afterEach(() => { vi.restoreAllMocks() })
    const opened = (ui: ReactElement = <Fixture />, id = 'sheet-a') => {
      render(ui)
      act(() => { useSheets.getState().open(id) })
      const node = document.querySelector(`#${id}`) as HTMLDialogElement
      node.getBoundingClientRect = () => DOMRect.fromRect({ x: 0, y: 400, width: 390, height: 444 })
      now.mockReturnValue(1_000_000 + SHEET_OPEN_GUARD_MS)
      return node
    }
    const at = (target: Element, clientX: number, clientY: number) =>
      ({ target, coords: { clientX, clientY } })

    it('closes the sheet, as its button does', async () => {
      const user = userEvent.setup()
      const node = opened()
      await user.pointer({ keys: '[MouseLeft]', ...at(node, 200, 120) })
      expect(useSheets.getState().openId).toBeNull()
    })

    it('leaves it open for a press on it: its ground, or its contents even past its edge', async () => {
      const user = userEvent.setup()
      const node = opened()
      await user.pointer({ keys: '[MouseLeft]', ...at(node, 200, 600) })
      await user.pointer({ keys: '[MouseLeft]', ...at(screen.getByText('a-body'), 200, 600) })
      // Its own contents count wherever they are drawn: a menu reaching up
      // past the sheet's top is still the sheet.
      await user.pointer({ keys: '[MouseLeft]', ...at(screen.getByText('a-body'), 200, 120) })
      expect(useSheets.getState().openId).toBe('sheet-a')
    })

    it('leaves it open for a press that starts inside and is let go outside', async () => {
      // A stepper held, a word selected, and the thumb slides past the edge.
      const user = userEvent.setup()
      const node = opened()
      await user.pointer([
        { keys: '[MouseLeft>]', ...at(screen.getByText('a-body'), 200, 600) },
        { keys: '[/MouseLeft]', ...at(node, 200, 120) },
      ])
      expect(useSheets.getState().openId).toBe('sheet-a')
    })

    it('takes no press in the moment it opens: that is the opening tap\'s bounce', async () => {
      // A double tap on an opener above where a short sheet ends up -- a
      // partner's line under the header -- put its second half on the new
      // backdrop, and the sheet closed as it opened. Counted from each
      // opening, not from the page's first render.
      const user = userEvent.setup()
      render(<Fixture />)
      const node = document.querySelector('#sheet-a') as HTMLDialogElement
      node.getBoundingClientRect = () => DOMRect.fromRect({ x: 0, y: 400, width: 390, height: 444 })
      for (const openAt of [1_005_000, 1_015_000]) {
        now.mockReturnValue(openAt)
        act(() => { useSheets.getState().open('sheet-a') })
        now.mockReturnValue(openAt + SHEET_OPEN_GUARD_MS - 1)
        await user.pointer({ keys: '[MouseLeft]', ...at(node, 200, 120) })
        expect(useSheets.getState().openId).toBe('sheet-a')

        now.mockReturnValue(openAt + SHEET_OPEN_GUARD_MS)
        await user.pointer({ keys: '[MouseLeft]', ...at(node, 200, 120) })
        expect(useSheets.getState().openId).toBeNull()
      }
    })

    it('leaves a draft open: only its own buttons save it', async () => {
      // The debrief's typed note, lost to a tap meant to put the keyboard away.
      const user = userEvent.setup()
      const node = opened(<Sheet id="sheet-d" title="Workout" draft>d-body</Sheet>, 'sheet-d')
      await user.pointer({ keys: '[MouseLeft]', ...at(node, 200, 120) })
      expect(useSheets.getState().openId).toBe('sheet-d')
    })

    it('leaves it open while a draft is in it: a machine\'s stops being typed', async () => {
      const user = userEvent.setup()
      const node = opened(<Sheet id="sheet-e" title="Latzug"><div data-draft>e-body</div></Sheet>, 'sheet-e')
      await user.pointer({ keys: '[MouseLeft]', ...at(node, 200, 120) })
      expect(useSheets.getState().openId).toBe('sheet-e')
    })
  })

  describe('a close at the bottom of a tall sheet (G-108)', () => {
    // Its top in the upper third of the screen (jsdom's is 768 high), the
    // backdrop is a strip up there, as far from the thumb as the head's close.
    let top = 30
    beforeEach(() => {
      top = 30
      vi.spyOn(HTMLDialogElement.prototype, 'getBoundingClientRect')
        .mockImplementation(() => DOMRect.fromRect({ x: 0, y: top, width: 390, height: 768 - top }))
    })
    afterEach(() => { vi.restoreAllMocks(); vi.unstubAllGlobals() })
    const open = (ui: ReactElement = <Fixture />, id = 'sheet-a') => {
      render(ui)
      act(() => { useSheets.getState().open(id) })
      return document.querySelector(`#${id}`) as HTMLDialogElement
    }
    const foot = () => document.querySelector('.sheet__foot button')

    it('closes the sheet, as its head\'s button does, and says so in its words', async () => {
      open(<Sheet id="sheet-c" title="Freies Workout" closeLabel="Abbrechen">c-body</Sheet>, 'sheet-c')
      expect(foot()).toHaveTextContent('Abbrechen')
      await userEvent.click(foot()!)
      expect(useSheets.getState().openId).toBeNull()
    })

    it('leaves a keyboard and a screen reader the one close, the head\'s', () => {
      const node = open()
      expect(foot()).toHaveAttribute('tabindex', '-1')
      expect(within(node).getAllByRole('button', { name: 'Fertig' })).toHaveLength(1)
    })

    it('is not on a short sheet, nor on a draft', () => {
      top = 400
      open()
      expect(foot()).toBeNull()
      top = 30
      open(<Sheet id="sheet-d" title="Workout" draft>d-body</Sheet>, 'sheet-d')
      expect(foot()).toBeNull()
    })

    it('comes as the sheet grows past the third, and as the screen turns', () => {
      // A sheet's contents change while it is open: search hits, a set added.
      let grew = () => {}
      vi.stubGlobal('ResizeObserver', class {
        constructor(private measure: () => void) {}
        observe() { grew = this.measure }
        disconnect() {}
      })
      top = 400
      open()
      expect(foot()).toBeNull()
      top = 30
      act(() => { grew() })
      expect(foot()).not.toBeNull()

      top = 400
      act(() => { fireEvent(window, new Event('resize')) })
      expect(foot()).toBeNull()
    })
  })

  it('puts the store back in step when the platform closes it', () => {
    // Esc closes a native <dialog> without going through the store. Without
    // this, openId would keep naming a sheet nobody can see, and reopening it
    // would appear to do nothing.
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

  it('binds a lead to its title, and names itself by the title alone', () => {
    // A training partner's tile before their name (D14): one unit in the
    // head, while the dialog is still called by the name.
    render(<Sheet id="sheet-p" title="jglaser" lead={<span className="tile">J</span>}>p</Sheet>)
    act(() => { useSheets.getState().open('sheet-p') })
    const who = document.querySelector('#sheet-p .sheet__who')!
    expect([...who.children].map((child) => child.className)).toEqual(['tile', 'sheet__title'])
    expect(screen.getByRole('dialog', { name: 'jglaser' })).toBeInTheDocument()
    // Without one the title stands alone, as every other sheet has it.
    render(<Fixture />)
    expect(document.querySelector('#sheet-a .sheet__who')).toBeNull()
  })
})
