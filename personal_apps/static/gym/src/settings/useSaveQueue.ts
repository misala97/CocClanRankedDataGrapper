import { useEffect, useRef } from 'react'
import { MutationFailed } from '../api'

interface Handlers<T> {
  /** The last write's answer only: a run of taps does not flicker back
   *  through the ones before it. */
  shown(fresh: T): void
  /** Every answer, in the order the writes were made. */
  saved?(fresh: T): void
  /** The last write failed, with the banner's German reason. */
  failed(message: string): void
}

/**
 * Settings writes, one after another in the order they were made. Two at
 * once could both find no settings row yet and both insert one; one at a
 * time, each answer is also the newest state when it lands.
 *
 * `write` is handed whether it must outlive the page. A write made as the
 * page goes away is sent at once -- queued behind another, it would start
 * after the document is gone.
 */
export function useSaveQueue<T>(handlers: Handlers<T>) {
  const chain = useRef<Promise<unknown>>(Promise.resolve())
  const latest = useRef(0)
  const on = useRef(handlers)
  useEffect(() => { on.current = handlers })

  return (write: (keepalive: boolean) => Promise<T>, leaving = false) => {
    latest.current += 1
    const mine = latest.current
    const run = leaving ? write(true) : chain.current.then(() => write(false))
    chain.current = run.catch(() => undefined)
    run.then(
      (fresh) => {
        on.current.saved?.(fresh)
        if (mine === latest.current) on.current.shown(fresh)
      },
      (failure: unknown) => {
        if (mine !== latest.current) return
        on.current.failed(failure instanceof MutationFailed
          ? failure.germanMessage
          : 'Nicht gespeichert — bitte noch einmal.')
      })
  }
}
