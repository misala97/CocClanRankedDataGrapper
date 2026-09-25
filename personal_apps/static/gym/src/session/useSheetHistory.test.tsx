import { act, render, screen } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { useSheets } from './stores'
import {
  LEAVE_FALLBACK_MS, leaveBySubmit, leavePage, useSheetHistory,
} from './useSheetHistory'

function Page() {
  useSheetHistory()
  return null
}

const open = (id: string) => act(() => { useSheets.getState().open(id) })
const openId = () => useSheets.getState().openId
const onSheetEntry = () => (history.state as { gymSheet?: boolean } | null)?.gymSheet === true

/** Settles once the next history step is taken and every listener ran. */
const step = () => new Promise<void>((resolve) => {
  window.addEventListener('popstate', () => resolve(), { once: true })
})

async function back() {
  const done = step()
  history.back()
  await act(() => done)
}

beforeEach(() => {
  useSheets.setState(useSheets.getInitialState(), true)
  history.replaceState(null, '')
})

describe('useSheetHistory: back closes the sheet, not the page (G-066)', () => {
  it('closes the open sheet on back', async () => {
    render(<Page />)
    open('sheet-a')
    expect(onSheetEntry()).toBe(true)
    await back()
    expect(openId()).toBeNull()
    expect(onSheetEntry()).toBe(false)
  })

  it('takes its entry back when the sheet closes another way', async () => {
    render(<Page />)
    open('sheet-a')
    const done = step()
    act(() => { useSheets.getState().close() })
    await act(() => done)
    // Back on the page's own entry: the next back leaves, as it should.
    expect(onSheetEntry()).toBe(false)
  })

  it('keeps one entry from one sheet to the next', async () => {
    render(<Page />)
    open('sheet-a')
    const length = history.length
    open('sheet-b')
    expect(history.length).toBe(length)
    await back()
    expect(openId()).toBeNull()
    expect(onSheetEntry()).toBe(false)
  })

  it('adds no second entry on a page reloaded on a sheet\'s', async () => {
    // A reload keeps the entry and its state: one back still closes.
    history.pushState({ gymSheet: true }, '')
    render(<Page />)
    const length = history.length
    open('sheet-a')
    expect(history.length).toBe(length)
    await back()
    expect(openId()).toBeNull()
  })

  it('keeps a sheet opened while its own step back is on its way', async () => {
    render(<Page />)
    open('sheet-a')
    const done = step()
    act(() => {
      useSheets.getState().close()
      useSheets.getState().open('sheet-b')
    })
    await act(() => done)
    expect(openId()).toBe('sheet-b')
    expect(onSheetEntry()).toBe(true)
    await back()
    expect(openId()).toBeNull()
  })

  it('steps back once for a sheet opened and closed while its step back is on its way', async () => {
    // A second step back for sheet b would take the page's own entry too.
    history.replaceState({ page: 'before' }, '')
    history.pushState({ page: 'workout' }, '')
    render(<Page />)
    open('sheet-a')
    const steps = vi.spyOn(history, 'back')
    const done = step()
    act(() => {
      useSheets.getState().close()
      useSheets.getState().open('sheet-b')
      useSheets.getState().close()
    })
    await act(() => done)
    await act(() => new Promise((resolve) => { setTimeout(resolve, 50) }))
    // Counted, too: jsdom aims each step when it is asked for, so two land
    // on the same entry there -- a browser takes the second from the first.
    expect(steps).toHaveBeenCalledTimes(1)
    expect(history.state).toEqual({ page: 'workout' })
    expect(openId()).toBeNull()
    steps.mockRestore()
  })

  it('leaves the history alone once the page is gone', () => {
    const { unmount } = render(<Page />)
    unmount()
    const push = vi.spyOn(history, 'pushState')
    open('sheet-a')
    window.dispatchEvent(new PageTransitionEvent('pageshow', { persisted: true }))
    expect(push).not.toHaveBeenCalled()
    push.mockRestore()
  })
})

describe('leavePage: no dead step left behind (B7 review)', () => {
  // Left from a sheet, the page kept the sheet's entry: back from the next
  // page landed on it, and the next back on this page again.
  it("takes the sheet's entry back first, then leaves", async () => {
    history.replaceState({ page: 'workout' }, '')
    render(<Page />)
    open('sheet-a')
    const states: unknown[] = []
    const go = vi.fn(() => { states.push(history.state) })
    const done = step()
    leavePage(go)
    expect(go).not.toHaveBeenCalled()
    await act(() => done)
    expect(go).toHaveBeenCalledOnce()
    expect(states).toEqual([{ page: 'workout' }])
  })

  it('keeps the sheet up while it leaves (B7 re-review)', async () => {
    // Closed by the step, it left the page under it live for the whole
    // round trip of a finish.
    history.replaceState({ page: 'workout' }, '')
    render(<Page />)
    open('sheet-a')
    const sheets: unknown[] = []
    const done = step()
    leavePage(() => { sheets.push(openId()) })
    await act(() => done)
    expect(sheets).toEqual(['sheet-a'])
    expect(openId()).toBe('sheet-a')
  })

  it('gives the sheet its entry again when the page comes back whole (B7 re-review)', async () => {
    // Back from the next page, the bfcache shows the page as it was left:
    // the sheet up, its entry gone. Back then left the page past the sheet.
    history.replaceState({ page: 'workout' }, '')
    render(<Page />)
    open('sheet-a')
    const done = step()
    leavePage(() => {})
    await act(() => done)
    expect(onSheetEntry()).toBe(false)

    const shown = (persisted: boolean) => {
      window.dispatchEvent(new PageTransitionEvent('pageshow', { persisted }))
    }
    shown(false)
    expect(onSheetEntry()).toBe(false)
    shown(true)
    expect(onSheetEntry()).toBe(true)
    // One entry, however often the page comes back.
    const entries = history.length
    shown(true)
    expect(history.length).toBe(entries)
    await back()
    expect(openId()).toBeNull()
    // No sheet up: nothing to give back.
    shown(true)
    expect(onSheetEntry()).toBe(false)
  })

  it('sends a form that leaves the page once the step is done (B7 re-review)', async () => {
    // A plain POST from a sheet left the sheet's entry behind it too.
    history.replaceState({ page: 'workout' }, '')
    const states: unknown[] = []
    const submit = vi.spyOn(HTMLFormElement.prototype, 'submit')
      .mockImplementation(() => { states.push(history.state) })
    render(<><Page /><form onSubmit={leaveBySubmit}><button>Los</button></form></>)
    open('sheet-a')
    // The form's own POST held back: it went at once, past the entry.
    const held: boolean[] = []
    const hold = (event: Event) => { held.push(event.defaultPrevented) }
    window.addEventListener('submit', hold)
    const done = step()
    act(() => { screen.getByRole('button', { name: 'Los' }).click() })
    window.removeEventListener('submit', hold)
    expect(held).toEqual([true])
    expect(submit).not.toHaveBeenCalled()
    await act(() => done)
    expect(submit).toHaveBeenCalledOnce()
    expect(states).toEqual([{ page: 'workout' }])
    submit.mockRestore()
  })

  it('leaves at once when no sheet holds an entry', () => {
    const steps = vi.spyOn(history, 'back')
    const go = vi.fn()
    leavePage(go)
    expect(go).toHaveBeenCalledOnce()
    expect(steps).not.toHaveBeenCalled()
    steps.mockRestore()
  })

  it('steps back once for a second tap while its step is on its way', async () => {
    // A second step back would leave the page by history, not by `go`.
    history.replaceState({ page: 'workout' }, '')
    render(<Page />)
    open('sheet-a')
    const steps = vi.spyOn(history, 'back')
    const go = vi.fn()
    const done = step()
    leavePage(go)
    leavePage(go)
    await act(() => done)
    await act(() => new Promise((resolve) => { setTimeout(resolve, 50) }))
    expect(steps).toHaveBeenCalledTimes(1)
    expect(go).toHaveBeenCalledOnce()
    steps.mockRestore()
  })

  it('leaves anyway when the step back never lands, once', () => {
    // A view that will not walk its history kept the lifter on the page.
    vi.useFakeTimers()
    history.replaceState({ gymSheet: true }, '')
    const steps = vi.spyOn(history, 'back').mockImplementation(() => {})
    const go = vi.fn()
    leavePage(go)
    vi.advanceTimersByTime(LEAVE_FALLBACK_MS - 1)
    expect(go).not.toHaveBeenCalled()
    vi.advanceTimersByTime(1)
    expect(go).toHaveBeenCalledOnce()
    // A step landing late leaves no second time.
    window.dispatchEvent(new PopStateEvent('popstate'))
    expect(go).toHaveBeenCalledOnce()

    // Done leaving: the next tap is not ignored.
    leavePage(go)
    vi.advanceTimersByTime(LEAVE_FALLBACK_MS)
    expect(steps).toHaveBeenCalledTimes(2)
    expect(go).toHaveBeenCalledTimes(2)
    steps.mockRestore()
    vi.useRealTimers()
  })

  it('leaves no second time at the fallback once the step has landed', () => {
    vi.useFakeTimers()
    history.replaceState({ gymSheet: true }, '')
    const steps = vi.spyOn(history, 'back').mockImplementation(() => {
      window.dispatchEvent(new PopStateEvent('popstate'))
    })
    const go = vi.fn()
    leavePage(go)
    expect(go).toHaveBeenCalledOnce()
    vi.advanceTimersByTime(LEAVE_FALLBACK_MS)
    expect(go).toHaveBeenCalledOnce()
    steps.mockRestore()
    vi.useRealTimers()
  })
})
