import { create } from 'zustand'
import type { SortMode } from './types'

const STORE_KEY = 'gym.uebungen.open'

/**
 * Which groups are open, remembered across navigations within the tab.
 *
 * sessionStorage rather than local: "which bands I had open" is a property of
 * this visit, not a preference to carry for weeks. Wrapped in try/catch
 * because private mode throws on write, and a catalogue that cannot remember
 * its bands is fine while one that throws on every toggle is not.
 */
function readOpen(): string[] | null {
  try {
    const raw = sessionStorage.getItem(STORE_KEY)
    return raw === null ? null : JSON.parse(raw) as string[]
  } catch {
    return null
  }
}

function writeOpen(open: string[]): void {
  try {
    sessionStorage.setItem(STORE_KEY, JSON.stringify(open))
  } catch {
    /* private mode */
  }
}

const NIE_KEY = 'gym.uebungen.nie'

/** The open bands of "Noch nie gemacht", apart from yours: that part starts
 *  folded whatever its size -- it is the whole list -- and a band opened
 *  there says nothing about the same group's band of yours. */
function readNie(): string[] {
  try {
    const raw = sessionStorage.getItem(NIE_KEY)
    return raw === null ? [] : JSON.parse(raw) as string[]
  } catch {
    return []
  }
}

function writeNie(open: string[]): void {
  try {
    sessionStorage.setItem(NIE_KEY, JSON.stringify(open))
  } catch {
    /* private mode */
  }
}

const SORT_KEY = 'gym.uebungen.sort'

/** The sort IS a preference (a power user who lives in "Stagniert zuerst" re-tapped it
 *  every visit), so localStorage, not session. Unknown stored values fall
 *  back rather than crash a renamed mode. */
function readSort(): SortMode {
  try {
    const raw = localStorage.getItem(SORT_KEY)
    return raw === 'muscle' || raw === 'stall' || raw === 'recent' ? raw : 'muscle'
  } catch {
    return 'muscle'
  }
}

/** Whether a band of yours is open. A pure function of `open`, which a page
 *  selects itself: the store's own `isOpen` never changed identity, so a
 *  page that selected it was never told of a toggle and a tapped band
 *  stayed as it was until a reload (G-019). */
export function bandOpen(open: string[] | null, name: string, openByDefault: boolean): boolean {
  // Nothing remembered yet: fall back to what the catalogue's size implies.
  return open === null ? openByDefault : open.includes(name)
}

interface CatalogueUi {
  query: string
  sort: SortMode
  /** Group names, not indices: a slug keyed on position breaks the moment a
   *  group is added or the catalogue is re-ordered. */
  open: string[] | null
  setQuery(query: string): void
  setSort(sort: SortMode): void
  toggleGroup(name: string, openByDefault: boolean, allGroups: string[]): void
  /** The open bands of "Noch nie gemacht". */
  nieOpen: string[]
  toggleNie(name: string): void
  /** Opened, never closed: "Noch nichts für Beine" jumps to that band. */
  openNie(name: string): void
}

export const useCatalogueUi = create<CatalogueUi>((set) => ({
  query: '',
  sort: readSort(),
  open: readOpen(),
  nieOpen: readNie(),

  toggleNie: (name) => set((state) => {
    const next = state.nieOpen.includes(name)
      ? state.nieOpen.filter((g) => g !== name)
      : [...state.nieOpen, name]
    writeNie(next)
    return { nieOpen: next }
  }),
  openNie: (name) => set((state) => {
    if (state.nieOpen.includes(name)) return {}
    const next = [...state.nieOpen, name]
    writeNie(next)
    return { nieOpen: next }
  }),

  setQuery: (query) => set({ query }),
  setSort: (sort) => {
    try { localStorage.setItem(SORT_KEY, sort) } catch { /* private mode */ }
    set({ sort })
  },

  toggleGroup: (name, openByDefault, allGroups) => set((state) => {
    const current = state.open ?? (openByDefault ? allGroups : [])
    const next = current.includes(name)
      ? current.filter((g) => g !== name)
      : [...current, name]
    writeOpen(next)
    return { open: next }
  }),
}))
