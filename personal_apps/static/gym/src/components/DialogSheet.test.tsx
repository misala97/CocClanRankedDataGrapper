import { render } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { DialogSheet } from './DialogSheet'
import { SHEET_OPEN_GUARD_MS } from './useSheetDialog'

describe('DialogSheet', () => {
  afterEach(() => { vi.restoreAllMocks() })

  it('closes on a tap on the backdrop, as the live screen\'s sheets do (G-108)', async () => {
    // "Deine Einstellungen" closed so in a workout, and not on the exercise
    // page. jsdom lays nothing out: the sheet is given the lower half of a
    // phone, and the clock is put past the opening tap's bounce.
    const now = vi.spyOn(Date, 'now').mockReturnValue(1_000_000)
    const user = userEvent.setup()
    const onClose = vi.fn()
    render(<DialogSheet id="sheet-x" title="Deine Einstellungen" open onClose={onClose}>x</DialogSheet>)
    const node = document.querySelector('#sheet-x') as HTMLDialogElement
    node.getBoundingClientRect = () => DOMRect.fromRect({ x: 0, y: 400, width: 390, height: 444 })
    now.mockReturnValue(1_000_000 + SHEET_OPEN_GUARD_MS)

    await user.pointer({ keys: '[MouseLeft]', target: node, coords: { clientX: 200, clientY: 120 } })
    expect(onClose).toHaveBeenCalledTimes(1)
    expect(node.open).toBe(false)
  })

  it('has a close at the bottom when it stands tall', async () => {
    vi.spyOn(HTMLDialogElement.prototype, 'getBoundingClientRect')
      .mockReturnValue(DOMRect.fromRect({ x: 0, y: 30, width: 390, height: 738 }))
    const onClose = vi.fn()
    render(<DialogSheet id="sheet-x" title="Zur Routine" open onClose={onClose}>x</DialogSheet>)
    const foot = document.querySelector('.sheet__foot button')!
    expect(foot).toHaveTextContent('Fertig')
    await userEvent.click(foot)
    expect(onClose).toHaveBeenCalledTimes(1)
  })
})
