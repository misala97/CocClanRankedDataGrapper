/**
 * The eleven pieces of state the live workout screen owns and the server
 * cannot know.
 *
 * This file deliberately imports nothing from `./types`. Client state deriving
 * from the server payload is the exact defect this port exists to remove: the
 * old screen kept reorder mode, the open sheet, the search query and the save
 * status in the DOM, `refreshBody` replaced that DOM wholesale on every
 * mutation, and syncSheets / syncAfterSwap / applyReorderUI / applyNotifyState
 * existed only to rebuild them by hand. A missing import enforces the
 * separation better than a comment does.
 *
 * Scroll position is not here, and that is not an oversight. It was state only
 * because the swap destroyed it; React reconciles in place, so there is
 * nothing to save and restore.
 */
import { create } from 'zustand'

// ---------------------------------------------------------------------------
// Sheets: which one is open, which pane it is showing, and the add-list query.
// ---------------------------------------------------------------------------

interface SheetState {
  openId: string | null
  panes: Record<string, string>
  addQuery: string
  open(id: string): void
  close(): void
  showPane(sheetId: string, pane: string): void
  paneOf(sheetId: string): string | null
  setAddQuery(query: string): void
}

export const useSheets = create<SheetState>((set, get) => ({
  openId: null,
  panes: {},
  addQuery: '',

  /** Opening a sheet closes any other and resets this one to its first pane.
   *  A sheet on top of a sheet is not a state this design has -- the old code
   *  called current.close() before showModal() for the same reason. */
  open: (id) => set((state) => {
    const panes = { ...state.panes }
    delete panes[id]
    return { openId: id, panes }
  }),

  close: () => set({ openId: null }),

  showPane: (sheetId, pane) =>
    set((state) => ({ panes: { ...state.panes, [sheetId]: pane } })),

  paneOf: (sheetId) => get().panes[sheetId] ?? null,

  /** Survives a close and reopen, matching the old screen: refreshBody
   *  replaced #exadd-list but never #exadd-search, and closing a <dialog>
   *  does not clear its inputs. */
  setAddQuery: (addQuery) => set({ addQuery }),
}))

// ---------------------------------------------------------------------------
// Reorder mode: a mode with a visible banner, not a lock icon to decode.
// ---------------------------------------------------------------------------

interface WorkoutUiState {
  reorderUnlocked: boolean
  toggleReorder(): void
  setReorder(on: boolean): void
}

export const useWorkoutUi = create<WorkoutUiState>((set) => ({
  reorderUnlocked: false,
  toggleReorder: () => set((state) => ({ reorderUnlocked: !state.reorderUnlocked })),
  setReorder: (reorderUnlocked) => set({ reorderUnlocked }),
}))

// ---------------------------------------------------------------------------
// Save status: how many writes are in flight, which forms are locked, and the
// one visible answer to "did that save?".
// ---------------------------------------------------------------------------

export interface SaveError {
  message: string
  retry(): void
}

interface SaveStateStore {
  pending: number
  error: SaveError | null
  locked: Record<string, true>
  begin(): void
  end(): void
  succeed(): void
  fail(message: string, retry: () => void): void
  dismissError(): void
  lock(formId: string): void
  unlock(formId: string): void
  isLocked(formId: string): boolean
}

export const useSaveState = create<SaveStateStore>((set, get) => ({
  pending: 0,
  error: null,
  locked: {},

  /** Counted, not flagged. Two concurrent saves need two ends -- a boolean
   *  would clear the sweep on the first while a second write was still out. */
  begin: () => set((state) => ({ pending: state.pending + 1 })),

  /** Settle only. This runs from onSettled, which fires straight after
   *  onError -- clearing the error here took the banner down in the same tick
   *  it went up, so every lost write reverted the screen in silence. A write
   *  that FINISHED is not a write that WORKED. */
  end: () => set((state) => ({ pending: Math.max(0, state.pending - 1) })),

  /** A real answer from the server: the last failure is no longer the current
   *  truth, so the banner goes with it. */
  succeed: () => set({ error: null }),

  fail: (message, retry) => set({ error: { message, retry } }),
  dismissError: () => set({ error: null }),

  /** One write per form at a time. The confirm button is in the thumb zone
   *  and its answer arrives a round trip later, so a second tap before the
   *  first resolves is what a sweaty hand does, not an edge case. Keyed per
   *  form because two different sets landing together is legitimate; the same
   *  one twice is not. */
  lock: (formId) => set((state) => ({ locked: { ...state.locked, [formId]: true } })),

  unlock: (formId) => set((state) => {
    const locked = { ...state.locked }
    delete locked[formId]
    return { locked }
  }),

  isLocked: (formId) => get().locked[formId] === true,
}))

// ---------------------------------------------------------------------------
// Push: a fact about this device, not about the account.
// ---------------------------------------------------------------------------

interface PushState {
  /** null while the one-time probe is in flight. The row stays at its default
   *  until it resolves; treating null as false would offer to enable push on a
   *  device that already has it. */
  subscribed: boolean | null
  setSubscribed(value: boolean): void
}

export const usePush = create<PushState>((set) => ({
  subscribed: null,
  setSubscribed: (subscribed) => set({ subscribed }),
}))


// ---------------------------------------------------------------------------
// The screen's live region.
//
// A live region has to persist to be announced -- the original kept #rest-announce
// outside #session-body for exactly that reason, because a freshly inserted
// region carrying pre-filled text does not reliably announce it. React keeps
// it mounted, so what is left is the other half of the problem: writing the
// same string into a live region does not re-fire it, and two identical
// announcements in a row are two events. Hence the nonce.
// ---------------------------------------------------------------------------

interface AnnouncerState {
  message: string
  nonce: number
  announce(message: string): void
}

export const useAnnouncer = create<AnnouncerState>((set) => ({
  message: '',
  nonce: 0,
  announce: (message) => set((state) => ({ message, nonce: state.nonce + 1 })),
}))
