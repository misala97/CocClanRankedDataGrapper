import { createContext, useCallback, useContext, useRef, useState } from 'react'
import type { ReactNode } from 'react'

import { MARK_WHY } from '../format'
import type { Mark } from '../types'

// Trust marks are load-bearing (PRODUCT.md): a reader who cannot see that a
// divergence came from a frozen tape can act on a number the system already
// knows is meaningless. So the mark itself is always visible on the row, and
// only its explanation is behind a press.
//
// The explanation is a native popover rather than `title` or an absolutely
// positioned div, for two reasons this codebase has already been bitten by:
// `title` is mouse-only, so it does not exist on a phone or from the keyboard;
// and an in-flow tooltip is clipped by any scrolling ancestor, which the
// control strip and the mobile row layout both are.
//
// ONE popover for the whole page, not one per mark. There are four possible
// explanations and up to fifteen rows, so per-mark elements would put sixty
// duplicate nodes in the document to show at most one at a time. It also
// sidesteps CSS anchor positioning, which is not available everywhere yet.

interface Explainer {
  show: (mark: Mark) => void
}

const ExplainerContext = createContext<Explainer>({ show: () => {} })

export function MarkExplainer({ children }: { children: ReactNode }) {
  const [mark, setMark] = useState<Mark | null>(null)
  const ref = useRef<HTMLDivElement>(null)

  const show = useCallback((next: Mark) => {
    setMark(next)
    // showPopover() throws if it is already open, and re-showing is exactly
    // what happens when the reader taps a second mark while the first is up.
    const node = ref.current
    if (!node) return
    if (node.matches(':popover-open')) node.hidePopover()
    node.showPopover()
  }, [])

  return (
    <ExplainerContext.Provider value={{ show }}>
      {children}
      <div className="why" popover="auto" ref={ref} role="status">
        <b>{mark}</b>
        <p>{mark ? MARK_WHY[mark] : ''}</p>
      </div>
    </ExplainerContext.Provider>
  )
}

export function Marks({ marks }: { marks: Mark[] }) {
  const { show } = useContext(ExplainerContext)
  if (!marks.length) return null

  return (
    <>
      {marks.map((mark) => (
        <button
          key={mark}
          type="button"
          className={mark === 'no-print' ? 'mk hard' : 'mk'}
          onClick={() => show(mark)}
          aria-label={`${mark} — why this is marked`}
        >
          {mark}
        </button>
      ))}
    </>
  )
}
