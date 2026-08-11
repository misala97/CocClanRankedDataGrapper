// Shared-element view transitions, the list side.
//
// The DETAIL side of a morph names its element statically -- one page, one
// heading, no ambiguity. The LIST side cannot: naming every row would put
// hundreds of identical view-transition-names on one page, and duplicate
// names make the browser skip the transition entirely. So the tapped row is
// named at tap time, just before navigation snapshots the old page.
//
// Clearing every previously-named element first is not defensive fluff: a
// back-navigation restores the page from the bfcache WITH the mutated DOM,
// so the row tapped last time is still named -- tap a second row and the
// page has two, which skips the morph exactly when it is expected most.

import type { MouseEvent } from 'react'

/** selector picks the text element inside the tapped row; null means the
 *  tapped element IS the text (e.g. Statistik's progression links). */
export function morphFrom(name: string, selector: string | null = '.row__name') {
  return (event: MouseEvent<HTMLElement>) => {
    for (const el of document.querySelectorAll<HTMLElement>('[data-vt]')) {
      el.style.removeProperty('view-transition-name')
      delete el.dataset['vt']
    }
    const target = (selector === null ? null
      : event.currentTarget.querySelector<HTMLElement>(selector)) ?? event.currentTarget
    target.style.setProperty('view-transition-name', name)
    target.dataset['vt'] = name
  }
}
