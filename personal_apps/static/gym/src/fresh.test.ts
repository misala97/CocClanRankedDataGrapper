import { afterEach, describe, expect, it, vi } from 'vitest'
import { reloadWhenRestored } from './fresh'

/**
 * Back to a gym page restored from the back-forward cache is back to the page
 * as it was left -- before the delete, the finish, the new record (G-141).
 * Only the live workout used to notice; Start, Verlauf and Übungen showed the
 * old rows as if they were current.
 */
const restored = (persisted: boolean) =>
  Object.assign(new Event('pageshow'), { persisted })

afterEach(() => { vi.unstubAllGlobals() })

function stubReload() {
  const reload = vi.fn()
  vi.stubGlobal('location', { ...window.location, reload })
  return reload
}

describe('reloadWhenRestored', () => {
  it('reloads a page the browser restored from its cache', () => {
    const reload = stubReload()
    const stop = reloadWhenRestored()
    window.dispatchEvent(restored(true))
    stop()
    expect(reload).toHaveBeenCalledOnce()
  })

  it('leaves a page that was loaded fresh alone', () => {
    const reload = stubReload()
    const stop = reloadWhenRestored()
    window.dispatchEvent(restored(false))
    stop()
    expect(reload).not.toHaveBeenCalled()
  })
})

// Every page, not only the ones someone remembered: a new island is covered
// the day its entry exists.
const entries = import.meta.glob('./entries/*.tsx')

describe('every gym page', () => {
  it('has entries to check', () => {
    expect(Object.keys(entries).length).toBeGreaterThanOrEqual(8)
  })

  it.each(Object.keys(entries))('%s reloads when restored from the cache', async (path) => {
    const add = vi.spyOn(window, 'addEventListener')
    await entries[path]!()
    const onShow = add.mock.calls.find(([type]) => type === 'pageshow')?.[1]
    add.mockRestore()
    expect(onShow, 'no pageshow handler').toBeTypeOf('function')

    const reload = stubReload()
    ;(onShow as (event: Event) => void)(restored(true))
    expect(reload).toHaveBeenCalledOnce()
  })
})
