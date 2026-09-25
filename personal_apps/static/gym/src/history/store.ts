import { create } from 'zustand'

interface HistoryUi {
  query: string
  exporting: boolean
  /** "Nur Rekorde": only the workouts that set one, each record on its row. */
  onlyRecords: boolean
  /** Session ids picked for export. A Set would be tidier, but this is state a
   *  component re-renders from and an array compares by identity cleanly. */
  selected: number[]
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

/** The address with `?rekorde` set or dropped, every other part kept. */
export function withRecords(search: string, on: boolean): string {
  const params = new URLSearchParams(search)
  params.delete('rekorde')
  const rest = params.toString()
  const query = [rest, on ? 'rekorde' : ''].filter(Boolean).join('&')
  return query ? `?${query}` : ''
}

export const useHistoryUi = create<HistoryUi>((set, get) => ({
  query: '',
  exporting: false,
  onlyRecords: typeof window !== 'undefined' && recordsInAddress(window.location.search),
  selected: [],

  setQuery: (query) => set({ query }),
  setOnlyRecords: (onlyRecords) => {
    set({ onlyRecords })
    const { pathname, search, hash } = window.location
    window.history.replaceState(window.history.state, '',
      `${pathname}${withRecords(search, onlyRecords)}${hash}`)
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
