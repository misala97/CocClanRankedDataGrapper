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
// Save status: how many writes are in flight, and the one visible answer to
// "did that save?" -- for every write the outbox cannot keep trying.
// ---------------------------------------------------------------------------

/** What mends a failure. 'auto': sending the same write again, which the
 *  connection coming back or finishing does by itself. 'manual': sending it
 *  again, but only on the lifter's tap -- a write that is new work each
 *  time (an added set) may have landed with only its answer lost, and sent
 *  again by itself it lands twice (B4 re-review). 'reload': a fresh page --
 *  a stale token or a lapsed login fails every write alike. */
export type Remedy = 'auto' | 'manual' | 'reload'

export interface SaveError {
  /** Which write failed -- the same write landing later answers it. */
  key: string
  /** New for every failure, so "did anything fail since?" can be asked. */
  id: number
  message: string
  /** Null when sending the same write again cannot work -- a value the
   *  server refused says so, and the banner offers no retry for it. For
   *  'reload', the reload. */
  retry: (() => void) | null
  remedy: Remedy
}

interface SaveStateStore {
  pending: number
  /** Every write that failed and has not landed since, oldest first. One
   *  slot kept only the newest, and any later success emptied it: earlier
   *  writes, already rolled back, vanished with no banner (G-139). */
  errors: SaveError[]
  begin(): void
  end(): void
  succeed(key: string): void
  fail(key: string, message: string, retry: (() => void) | null, remedy?: Remedy): void
  /** Takes every failure that sending again mends by itself ('auto') off the
   *  list and sends it; one that fails again comes back as a new entry. The
   *  rest stay: the refused ones, the ones for the lifter to resend, and the
   *  ones only a fresh page mends -- the connection coming back must not
   *  reload the page under the lifter (B4 review). */
  resendAll(): void
  /** "Erneut versuchen", the lifter's tap: every failure with a retry,
   *  'manual' ones included -- and a fresh page last when any failure needs
   *  one. The outbox sends nothing then, so the retries only put their
   *  writes back on the phone for that page; before the outbox, resending
   *  them raced the reload (B4 review). */
  retryAll(): void
  dismissErrors(): void
}

let lastErrorId = 0

export const useSaveState = create<SaveStateStore>((set, get) => ({
  pending: 0,
  errors: [],

  /** Counted, not flagged. Two concurrent saves need two ends -- a boolean
   *  would clear the sweep on the first while a second write was still out. */
  begin: () => set((state) => ({ pending: state.pending + 1 })),

  /** Settle only. This runs from onSettled, which fires straight after
   *  onError -- clearing the error here took the banner down in the same tick
   *  it went up, so every lost write reverted the screen in silence. A write
   *  that FINISHED is not a write that WORKED. */
  end: () => set((state) => ({ pending: Math.max(0, state.pending - 1) })),

  /** A real answer from the server for THIS write: its earlier failure is
   *  no longer the truth, and neither is one about a part of what it names
   *  -- a deleted set answers its lost tick ('set-4' answers 'set-4:done').
   *  Any other write's failure still is. */
  succeed: (key) => set((state) => ({
    errors: state.errors.filter((e) => e.key !== key && !e.key.startsWith(`${key}:`)),
  })),

  /** The newest failure of a write replaces its older one -- it carries the
   *  lifter's latest intent, and one write needs one retry. */
  fail: (key, message, retry, remedy = 'auto') => set((state) => ({
    errors: [...state.errors.filter((e) => e.key !== key),
      { key, id: ++lastErrorId, message, retry, remedy }],
  })),

  resendAll: () => {
    const resends = get().errors.flatMap((e) => (
      e.retry !== null && e.remedy === 'auto' ? [e.retry] : []))
    set((state) => ({
      errors: state.errors.filter((e) => e.retry === null || e.remedy !== 'auto'),
    }))
    for (const resend of resends) resend()
  },

  retryAll: () => {
    const errors = get().errors
    const reload = errors.find((e) => e.remedy === 'reload' && e.retry !== null)
    const resends = errors.flatMap((e) => (e.retry !== null && e !== reload ? [e.retry] : []))
    if (reload !== undefined) {
      // The rest first, which only puts them back on the phone: while only
      // a fresh page can send, the outbox sends nothing and keeps them for
      // it. The reload alone lost a refused set that was already off the
      // phone (B6 third review).
      for (const resend of resends) resend()
      reload.retry!()
      return
    }
    set((state) => ({ errors: state.errors.filter((e) => e.retry === null) }))
    for (const resend of resends) resend()
  },

  dismissErrors: () => set({ errors: [] }),
}))

/** Takes a checkpoint; the function it returns says whether any write has
 *  failed since. A write that failed before and fails AGAIN counts: its entry
 *  is new, even though the list is no longer. */
export function failureCheckpoint(): () => boolean {
  const before = new Set(useSaveState.getState().errors.map((e) => e.id))
  return () => useSaveState.getState().errors.some((e) => !before.has(e.id))
}

// ---------------------------------------------------------------------------
// The outbox (./outbox.ts): what the phone still holds for the server.
// ---------------------------------------------------------------------------

/** 'sending': a write is out, or next. 'waiting': the last try found no
 *  connection, and the next comes by itself. 'blocked': only a fresh page
 *  can send -- a stale token or a lapsed login. */
export type OutboxState = 'idle' | 'sending' | 'waiting' | 'blocked'

export interface OutboxStatus {
  state: OutboxState
  /** Writes kept on the phone and not answered yet. */
  count: number
  /** While waiting or blocked: the sets whose own write is among them, so
   *  their chips can say so. Empty otherwise -- a write out for a moment is
   *  no news. */
  setIds: number[]
}

interface OutboxStore extends OutboxStatus {
  /** "Beenden" was tapped while the writes could not get through: the
   *  status line says why nothing happened, until they are in. */
  finishRefused: boolean
  publish(status: OutboxStatus): void
  refuseFinish(): void
}

export const useOutbox = create<OutboxStore>((set) => ({
  state: 'idle',
  count: 0,
  setIds: [],
  finishRefused: false,
  publish: (status) => set((state) => ({
    ...status,
    // Everything in: the reason finishing waited is gone with them.
    finishRefused: state.finishRefused && status.count > 0,
  })),
  refuseFinish: () => set({ finishRefused: true }),
}))

/** What a set whose write the phone holds is waiting for, said on its chip:
 *  the status line's words. "Verbindung" while only a fresh page can send
 *  contradicted it (B6 review). */
export function useWaitingFor(): string {
  return useOutbox((s) => (s.state === 'blocked' ? 'wartet auf Neuladen' : 'wartet auf Verbindung'))
}

// ---------------------------------------------------------------------------
// Push: a fact about this device, not about the account.
// ---------------------------------------------------------------------------

interface PushState {
  /** null while the one-time probe is in flight. The row stays at its default
   *  until it resolves; treating null as false would offer to enable push on a
   *  device that already has it. */
  subscribed: boolean | null
  /** Why the last tap on "aktivieren" did not turn push on, shown beside the
   *  button that was tapped; null when there is nothing to say. */
  error: string | null
  setSubscribed(value: boolean): void
  setError(message: string | null): void
}

export const usePush = create<PushState>((set) => ({
  subscribed: null,
  error: null,
  setSubscribed: (subscribed) => set({ subscribed }),
  setError: (error) => set({ error }),
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

// ---------------------------------------------------------------------------
// "Your partner changed the plan" -- for eyes, not only for a screen reader.
//
// The announcer below is sr-only text. For everyone else the follower's queue
// used to rearrange itself in silence, which is the one change on this screen
// the lifter did not cause. The nonce is what lets a second change restart the
// notice's clock while the first is still showing.
// ---------------------------------------------------------------------------

interface PartnerNoticeState {
  visible: boolean
  nonce: number
  show(): void
  dismiss(): void
}

export const usePartnerNotice = create<PartnerNoticeState>((set) => ({
  visible: false,
  nonce: 0,
  show: () => set((state) => ({ visible: true, nonce: state.nonce + 1 })),
  dismiss: () => set({ visible: false }),
}))

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
