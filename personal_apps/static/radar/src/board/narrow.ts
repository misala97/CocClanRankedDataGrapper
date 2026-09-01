import { useEffect, useState } from 'react'

/** The width below which the page stacks -- the same figure as radar.css's
 *  `@media (max-width: 900px)`. The two must agree, because the account block
 *  is placed by this and styled by that. */
const STACKED = '(max-width: 900px)'

function stackedNow(): boolean {
  return typeof window !== 'undefined'
    && typeof window.matchMedia === 'function'
    && window.matchMedia(STACKED).matches
}

/** Whether the page is currently stacked (list over panel) rather than two
 *  panes side by side.
 *
 *  Asked of the browser rather than inferred from a resize listener: CSS
 *  decides the layout and this only follows it. False wherever matchMedia is
 *  absent (jsdom), which is the desk layout every existing test renders. */
export function useNarrow(): boolean {
  const [narrow, setNarrow] = useState(stackedNow)
  useEffect(() => {
    if (typeof window.matchMedia !== 'function') return
    const list = window.matchMedia(STACKED)
    const update = () => setNarrow(list.matches)
    update()
    list.addEventListener('change', update)
    return () => list.removeEventListener('change', update)
  }, [])
  return narrow
}
