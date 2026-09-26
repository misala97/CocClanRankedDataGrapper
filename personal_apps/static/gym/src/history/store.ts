import { create } from 'zustand'

interface HistoryUi {
  query: string
  exporting: boolean
  /** "Nur Rekorde": only the workouts that set one, each record on its row. */
  onlyRecords: boolean
  /** Session ids picked for export. A Set would be tidier, but this is state a
   *  component re-renders from and an array compares by identity cleanly. */
  selected: number[]
  /** Also kept in the address (`?q=`, G-043): a reload, Back into the page
   *  or a shared link finds the same search -- replaced, not pushed. */
  setQuery(query: string): void
  /** Also says it in the address (`?rekorde`), so a reload or a shared link
   *  keeps it -- replaced, not pushed: a filter is no place to go back to. */
  setOnlyRecords(onlyRecords: boolean): void
  startExport(): void
  cancelExport(): void
  toggle(sessionId: number): void
  /** Presets REPLACE the selection rather than adding to it, and only ever
   *  from rows the search is currently showing -- "Alle" once meant all 178
   *  while 59 were on screen, then built the export URL from all 178. */
  replaceSelection(sessionIds: number[]): void
  isSelected(sessionId: number): boolean
}

/** Whether the address asks for "Nur Rekorde". */
export function recordsInAddress(search: string): boolean {
  return new URLSearchParams(search).has('rekorde')
}

/** The search the address asks for (`?q=`), or ''. */
export function queryInAddress(search: string): string {
  return new URLSearchParams(search).get('q') ?? ''
}

/** The address with `q` and `rekorde` as given, every other part kept: `q`
 *  dropped when blank, `rekorde` bare (URLSearchParams would write
 *  "rekorde="). */
function addressWith(search: string, change: { q?: string, records?: boolean }): string {
  const params = new URLSearchParams(search)
  const q = change.q ?? params.get('q') ?? ''
  const records = change.records ?? params.has('rekorde')
  params.delete('q')
  params.delete('rekorde')
  const query = [params.toString(), q.trim() ? `q=${encodeURIComponent(q)}` : '',
    records ? 'rekorde' : ''].filter(Boolean).join('&')
  return query ? `?${query}` : ''
}

/** The address with `?rekorde` set or dropped, every other part kept. */
export function withRecords(search: string, on: boolean): string {
  return addressWith(search, { records: on })
}

/** The address with `?q=` set to the search, or dropped when it is blank. */
export function withQuery(search: string, query: string): string {
  return addressWith(search, { q: query })
}

/** Replaces the address, the page's history entry kept as it is. */
function replaceAddress(search: string) {
  const { pathname, hash } = window.location
  try {
    window.history.replaceState(window.history.state, '', `${pathname}${search}${hash}`)
  } catch {
    // Safari refuses more than 100 replacements in 10 seconds: the address
    // keeps an older search until the next one lands; the page is unaffected.
  }
}

export const useHistoryUi = create<HistoryUi>((set, get) => ({
  query: typeof window !== 'undefined' ? queryInAddress(window.location.search) : '',
  exporting: false,
  onlyRecords: typeof window !== 'undefined' && recordsInAddress(window.location.search),
  selected: [],

  setQuery: (query) => {
    set({ query })
    replaceAddress(withQuery(window.location.search, query))
  },
  setOnlyRecords: (onlyRecords) => {
    set({ onlyRecords })
    replaceAddress(withRecords(window.location.search, onlyRecords))
  },
  startExport: () => set({ exporting: true }),
  // Leaving the mode drops the selection: keeping it would mean a later
  // "Exportieren" silently reopened with rows picked minutes ago.
  cancelExport: () => set({ exporting: false, selected: [] }),

  toggle: (sessionId) => set((state) => ({
    selected: state.selected.includes(sessionId)
      ? state.selected.filter((id) => id !== sessionId)
      : [...state.selected, sessionId],
  })),

  replaceSelection: (selected) => set({ selected }),
  isSelected: (sessionId) => get().selected.includes(sessionId),
}))
