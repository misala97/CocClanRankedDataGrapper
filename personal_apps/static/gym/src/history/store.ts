import { create } from 'zustand'

interface HistoryUi {
  query: string
  exporting: boolean
  /** Session ids picked for export. A Set would be tidier, but this is state a
   *  component re-renders from and an array compares by identity cleanly. */
  selected: number[]
  setQuery(query: string): void
  startExport(): void
  cancelExport(): void
  toggle(sessionId: number): void
  /** Presets REPLACE the selection rather than adding to it, and only ever
   *  from rows the search is currently showing -- "Alle" once meant all 178
   *  while 59 were on screen, then built the export URL from all 178. */
  replaceSelection(sessionIds: number[]): void
  isSelected(sessionId: number): boolean
}

export const useHistoryUi = create<HistoryUi>((set, get) => ({
  query: '',
  exporting: false,
  selected: [],

  setQuery: (query) => set({ query }),
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
