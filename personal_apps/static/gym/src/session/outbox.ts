import type { SessionDetailPayload } from './types'
import { MutationFailed } from './api'
import type { OutboxState, OutboxStatus, Remedy } from './stores'

/**
 * The live workout's outbox (walkthrough B6, D6-A: G-072, G-138, G-139).
 *
 * Every write the screen makes goes through here, one at a time, in the order
 * the lifter made them. What it shows is the server's last answer with every
 * write not answered yet drawn on top (`display`), so a set logged in a
 * basement with no signal stays logged: it waits on the phone, marked, and is
 * sent again and again until it lands -- after a reload, after the app was
 * closed. The 08-11 rule it replaces rolled a failed write back and waited for
 * an `online` event that a phone with dead wifi never fires.
 *
 * Durable writes are kept in localStorage, one key per write, synchronously,
 * so a set is on the phone before the tap handler returns. Writes with no
 * honest local effect (adding an exercise, a swap, the deload) are not kept:
 * they fail at once while the queue cannot get through, and say so.
 *
 * Nothing here knows React. The island wires the hooks (useOutbox.ts).
 */

export const OUTBOX_VERSION = 1

/** One write, as the phone keeps it until the server has answered it. */
export interface Entry {
  v: number
  id: string
  /** Its place among this workout's writes, across page loads and tabs: the
   *  time it was made, but never before the write made before it here. The
   *  phone's clock can step back, and a reload then replayed an un-log
   *  after the re-log that came after it (B6 review). */
  order: number
  /** When the lifter made it, by this phone's clock (epoch ms): the server
   *  stamps the set and runs the rest from here (helpers._write_time). */
  at: number
  kind: string
  args: unknown[]
}

export interface WriteSpec {
  /** Sends the write. The server answers with the whole screen after it. */
  send(args: unknown[], at: number): Promise<SessionDetailPayload>
  /** What the write does to the screen, drawn until the server has it. */
  apply?(payload: SessionDetailPayload, args: unknown[], at: number): SessionDetailPayload
  /** Kept on the phone and sent until it lands. Only a write that is safe to
   *  send twice may be: its answer can be lost after it landed. */
  durable: boolean
  /** Which failure on the banner its landing answers (stores.succeed). */
  key(args: unknown[]): string
  /** A write that is not kept, lost to the connection: sent again when it
   *  comes back ('auto'), only on the lifter's tap ('manual'), or never
   *  (null -- about this moment only, like "+15 s"). */
  resend?: Remedy | null
  /** Which argument names a set, for a set drawn before the server named it. */
  setArg?: number
  /** A write that makes a set: where its key and its temporary id are. */
  creates?: { key: number; temp: number }
}

/** Where the kept writes live. localShelf in the app, an object in tests.
 *  Every tab of the workout shares it. */
export interface Shelf {
  /** This workout's writes in order; `stale`: how many could not be read
   *  back -- another version of the app wrote them. Others' writes go. */
  read(): { entries: Entry[]; stale: number }
  /** False when the phone could not keep it. */
  put(entry: Entry): boolean
  drop(id: string): void
  /** The kept write as the phone has it now -- another tab may have named
   *  its set since -- or null once it is gone: another tab sent it.
   *  undefined when the phone cannot say. */
  get(id: string): Entry | null | undefined
  /** This workout's writes as the phone has them now, every tab's, in order;
   *  unlike `read`, removing nothing. undefined when the phone cannot say. */
  list(): Entry[] | undefined
  /** When the oldest write kept for the workout by any tab was made;
   *  undefined when the phone cannot say. */
  oldest(): number | null | undefined
  /** A set the server named: `temp` is the id the screen drew it with. For
   *  every tab: a write about the set made in one tab is sent from another,
   *  and the name lived only in the tab that saw it (B6 third review). */
  name(temp: number, real: number): void
  /** What a drawn set id became, as any tab of the workout saw it named;
   *  null while none has. undefined when the phone cannot say. */
  named(temp: number): number | null | undefined
}

export interface OutboxHooks {
  specs: Record<string, WriteSpec>
  shelf: Shelf
  /** The screen now. */
  show(payload: SessionDetailPayload): void
  status(status: OutboxStatus): void
  /** The time of the oldest kept write, or null: the hold cookie. */
  hold(oldestAt: number | null): void
  /** One request out, and one back: the saving sweep. */
  begin(): void
  end(): void
  succeed(key: string): void
  fail(key: string, message: string, retry: (() => void) | null, remedy: Remedy): void
  /** The server's screen, asked when a write met a row that is not there. */
  fetchFresh(): Promise<SessionDetailPayload>
  /** The workout ended under this screen, or is gone. */
  finished(): void
  gone(): void
  /** A fresh page: the one way past a stale token or a lapsed login. */
  reload(): void
  /** Everything held back has landed: time to ask the server again. */
  drained(): void
  /** Which exercise is live, for a screen the server cannot answer. */
  relive(payload: SessionDetailPayload): SessionDetailPayload
  /** Runs one send with no other tab of the workout sending (exclusively). */
  exclusive(run: () => Promise<void>): Promise<void>
  now(): number
  /** Milliseconds on a clock that never steps back -- performance.now when
   *  not given: how long the server has been failing a write. By the wall
   *  clock, one stepped back by minutes held every later write that long
   *  (B6 third review). */
  elapsed?(): number
  newId(): string
}

/** Two seconds after the first failure, half a minute at most: a phone in a
 *  basement tries twice a minute, and a phone back in signal is caught by
 *  `online`, by coming back into view, or by the lifter's next tap. */
export const BACKOFF_MS = [2000, 5000, 10000, 20000, 30000]

/** Tries a write gets through server errors (api.ts 'server') before it is
 *  refused, and how long they must span: a passing one -- a database
 *  restarting for twenty seconds -- is caught, a broken one blocks the
 *  writes behind it for a minute, not for good (B6 re-review). */
export const SERVER_TRIES = 3
export const SERVER_SPAN_MS = 60_000

const STALE_MESSAGE = (count: number) => (count === 1
  ? 'Eine ältere Änderung konnte nach einem Update nicht gesendet werden.'
  : `${count} ältere Änderungen konnten nach einem Update nicht gesendet werden.`)

export class Outbox {
  private queue: Entry[]
  private base: SessionDetailPayload
  /** Bumped by every answer: a refetch that started before one is stale. */
  private version = 0
  /** The last write's `order`: the next one goes after it, whatever the
   *  clock says. */
  private order: number
  /** The writes of this queue the phone has: only these can be taken by
   *  another tab. One it could not keep (a private window, a full disk) is
   *  not on it, and is sent all the same. */
  private readonly onShelf = new Set<string>()
  private state: OutboxState = 'idle'
  private busy = false
  /** A write is out: sent, its answer not in yet. `busy` is also true while
   *  this tab only waits for its turn behind another tab's, or asks. */
  private out = false
  private failures = 0
  private timer: ReturnType<typeof setTimeout> | null = null
  private blockedBy: MutationFailed | null = null
  /** Server errors in a row for the write at the head, and when the first
   *  came (SERVER_TRIES, SERVER_SPAN_MS). */
  private strikes = { id: '', count: 0, since: 0 }
  /** Held back by a failure or a reload since the queue was last empty. */
  private recovering: boolean
  private readonly resolved = new Map<number, number>()
  private readonly waiters = new Map<string, {
    resolve(payload: SessionDetailPayload): void
    reject(error: unknown): void
  }>()
  private flushes: ((drained: boolean) => void)[] = []
  private stopped = false

  constructor(base: SessionDetailPayload, private readonly hooks: OutboxHooks) {
    const { entries, stale } = hooks.shelf.read()
    let unknown = 0
    this.queue = []
    for (const entry of entries) {
      if (hooks.specs[entry.kind] === undefined) {
        hooks.shelf.drop(entry.id)
        unknown += 1
      } else {
        this.queue.push(entry)
        this.onShelf.add(entry.id)
      }
    }
    this.order = Math.max(0, ...this.queue.map((e) => e.order))
    this.base = base
    this.recovering = this.queue.length > 0
    if (stale + unknown > 0) {
      hooks.fail('outbox-stale', STALE_MESSAGE(stale + unknown), null, 'auto')
    }
  }

  /** Publishes the screen and starts sending. Separate from the constructor
   *  so the island can draw its first frame from `display()` first. */
  start(): void {
    this.stopped = false
    this.publish()
    this.pump()
  }

  /** The screen is gone: no more tries from here. What is kept stays kept,
   *  for the next page; an answer on its way is still taken. */
  stop(): void {
    this.stopped = true
    if (this.timer !== null) clearTimeout(this.timer)
    this.timer = null
  }

  /** The screen: the server's last answer with every write it has not
   *  answered drawn on top, in order. While any write is unanswered, the
   *  live exercise is worked out here too: offline, the answer that moves
   *  it on is not coming; on a slow connection it comes late, and a second
   *  tap meanwhile appended a set to the exercise just finished (B6
   *  review); and while held writes land one by one, each answer knows
   *  only the writes before it -- the card would step back and forth. */
  display(): SessionDetailPayload {
    let shown = this.base
    for (const entry of this.queue) {
      const apply = this.hooks.specs[entry.kind]!.apply
      // A kept write that cannot be drawn is still sent -- the server's
      // answer is the judge. Thrown, it took the screen down on every load.
      try {
        if (apply !== undefined) shown = apply(shown, entry.args, entry.at)
      } catch { /* drawn by the answer */ }
    }
    if (this.queue.length > 0) shown = this.hooks.relive(shown)
    return shown
  }

  /** For a refetch: the version to hand back to `receive`. */
  stamp(): number {
    return this.version
  }

  /** A refetch's answer. It becomes the base unless an answer to a write
   *  came in while it was on its way -- then it is older than what the
   *  screen already has. Returns the screen. */
  receive(fresh: SessionDetailPayload, stamp: number): SessionDetailPayload {
    if (stamp === this.version) {
      this.base = fresh
      this.version += 1
    }
    return this.display()
  }

  /** Queues a write and draws it. Settles when the server has answered it:
   *  with the answer, or rejected when it was refused -- never for a lost
   *  connection, which only means later. */
  enqueue(kind: string, args: unknown[]): Promise<SessionDetailPayload> {
    const spec = this.hooks.specs[kind]
    if (spec === undefined) throw new Error(`no write called ${kind}`)
    const at = this.hooks.now()
    this.order = Math.max(at, this.order + 1)
    const entry: Entry = {
      v: OUTBOX_VERSION, id: this.hooks.newId(), order: this.order, at, kind,
      args: this.resolve(spec, args),
    }
    if (!spec.durable && (this.state === 'waiting' || this.state === 'blocked')) {
      // Behind writes that cannot get through it would wait with no end in
      // sight, and it is not kept: said now, with its own retry.
      const error = this.blockedBy ?? new MutationFailed('network')
      this.lose(entry, spec, error)
      return Promise.reject(error)
    }
    this.queue.push(entry)
    if (spec.durable) this.keep(entry)
    const answered = new Promise<SessionDetailPayload>((resolve, reject) => {
      this.waiters.set(entry.id, { resolve, reject })
    })
    this.publish()
    this.kick()
    return answered
  }

  /** Tries now: the connection may be back. */
  kick(): void {
    if (this.timer !== null) {
      clearTimeout(this.timer)
      this.timer = null
    }
    this.pump()
  }

  /** Before leaving: true once every write has landed, false as soon as one
   *  cannot -- the next try failed, or only a fresh page can send them.
   *  Another tab's kept writes count: finishing here went ahead without the
   *  sets a tab put away had not sent yet (B6 re-review). */
  flush(): Promise<boolean> {
    this.gather(this.out ? 1 : 0)
    if (this.queue.length === 0 && !this.busy) return Promise.resolve(true)
    if (this.state === 'blocked') return Promise.resolve(false)
    return new Promise((resolve) => {
      this.flushes.push(resolve)
      this.kick()
    })
  }

  /** The workout is being thrown away: its writes are moot. Resolves once no
   *  write is out, so the one in flight cannot land after the discard. A
   *  turn only waited for is not one, and another tab can hold the turn for
   *  as long as it likes; nor is a question to the server: it changes
   *  nothing there. Stopped: whatever comes back meanwhile -- that turn,
   *  that answer, the one waited out -- sends nothing more from here. It
   *  took in the writes another tab keeps, and one that landed first had
   *  the discard refused (B6 third review). Every caller leaves the page. */
  async clear(): Promise<void> {
    this.stopped = true
    if (this.timer !== null) clearTimeout(this.timer)
    this.timer = null
    for (const entry of this.queue) this.unkeep(entry)
    this.queue = []
    this.hooks.hold(null)
    // Nothing of it will land: a finish waiting on it goes nowhere.
    this.settleFlushes(false)
    while (this.out) await new Promise((resolve) => setTimeout(resolve, 50))
  }

  // -------------------------------------------------------------------------

  private pump(): void {
    if (this.stopped || this.busy || this.timer !== null || this.state === 'blocked') return
    if (this.queue.length === 0) this.gather(0)
    const head = this.queue[0]
    if (head === undefined) {
      this.settleFlushes(true)
      return
    }
    this.busy = true
    if (this.state === 'idle') this.setState('sending')
    // One tab of the workout sends at a time, and its answer is taken
    // before the next can look: each tab restored the same kept writes, and
    // one sent again what the other had sent -- a set un-logged there was
    // logged again (B6 review). Never inside the tap that queued it.
    void Promise.resolve().then(() => this.hooks.exclusive(() => this.send(head)))
  }

  private async send(head: Entry): Promise<void> {
    // Another tab's writes made before this one go first: in the order the
    // lifter made them, whichever tab they were made in.
    this.gather(0)
    if (this.queue[0] !== head) { // cleared, or an older write came in
      this.busy = false
      this.pump()
      return
    }
    const spec = this.hooks.specs[head.kind]!
    if (this.onShelf.has(head.id)) {
      const now = this.hooks.shelf.get(head.id)
      if (now === null) return this.sentElsewhere(head, spec)
      // As the phone has it: another tab may have named its set.
      if (now !== undefined) head.args = now.args
    }
    // Made in another tab before the set was named, and named since by any.
    head.args = this.resolve(spec, head.args)
    this.hooks.begin()
    this.out = true
    let fresh: SessionDetailPayload
    try {
      fresh = await spec.send(head.args, head.at)
    } catch (error) {
      this.out = false
      this.hooks.end()
      // The network's failures all arrive as MutationFailed (../api.ts):
      // anything else is a write that cannot be sent at all -- refused, not
      // tried again forever.
      return this.failed(head, spec, error instanceof MutationFailed ? error : new MutationFailed('invalid'))
    }
    this.out = false
    this.hooks.end()
    this.landed(head, spec, fresh)
  }

  /** Another tab of the workout had it too, and sent it: it is off the
   *  phone. What it did is in the server's screen, asked for once the queue
   *  is empty -- unless it made a set: the screen names that set now, by its
   *  key. Asked only when a write queued here named it, a write about it
   *  queued later -- an un-log whose undo window was still open -- went out
   *  with the drawn id and was lost as moot (B6 re-review). */
  private sentElsewhere(head: Entry, spec: WriteSpec): Promise<void> | void {
    this.recovering = true
    if (spec.creates !== undefined) return this.askServer(head, spec, 'elsewhere')
    this.busy = false
    this.queue.shift()
    this.onShelf.delete(head.id)
    this.settle(head, this.base)
    this.afterAnswer()
  }

  private landed(head: Entry, spec: WriteSpec, fresh: SessionDetailPayload): void {
    this.busy = false
    this.failures = 0
    if (this.queue[0] !== head) { this.pump(); return } // cleared meanwhile
    this.queue.shift()
    this.unkeep(head)
    this.base = fresh
    this.version += 1
    if (spec.creates !== undefined) this.adopt(head, spec, fresh)
    this.hooks.succeed(spec.key(head.args))
    this.settle(head, fresh)
    this.afterAnswer()
  }

  private failed(head: Entry, spec: WriteSpec, error: MutationFailed): Promise<void> | void {
    this.busy = false
    if (this.queue[0] !== head) { this.pump(); return }
    if (error.reason === 'finished' || error.reason === 'gone') return this.askServer(head, spec, 'moot')
    if (error.needsReload) {
      // A stale token or a lapsed login fails every write alike: kept ones
      // wait for the fresh page, which sends them.
      this.blockedBy = error
      this.setState('blocked')
      this.shed(error)
      this.hooks.fail('outbox-blocked', error.germanMessage, this.hooks.reload, 'reload')
      this.publish()
      this.settleFlushes(false)
      return
    }
    if (error.retryable) {
      if (!spec.durable) {
        this.lose(this.queue.shift()!, spec, error)
        this.afterAnswer()
        return
      }
      if (error.reason === 'server') {
        // A server error may pass; one that does not held every later
        // write on the phone for good. Its own retry puts it back in line
        // as it was: made when it was made, with the writes about its set.
        // Queued anew, a set logged at 10:00 was stamped at the tap, and a
        // correction to it was gone (B6 re-review).
        const now = this.hooks.elapsed?.() ?? performance.now()
        const again = this.strikes.id === head.id
        this.strikes = again
          ? { ...this.strikes, count: this.strikes.count + 1 }
          : { id: head.id, count: 1, since: now }
        if (this.strikes.count >= SERVER_TRIES && now - this.strikes.since >= SERVER_SPAN_MS) {
          this.refuse(head, spec, error, 'manual', true)
          return
        }
      }
      this.failures += 1
      this.recovering = true
      this.setState('waiting')
      this.shed(error)
      const delay = BACKOFF_MS[Math.min(this.failures, BACKOFF_MS.length) - 1]!
      if (!this.stopped) this.timer = setTimeout(() => { this.timer = null; this.pump() }, delay)
      this.publish()
      this.settleFlushes(false)
      return
    }
    // Refused: the server says why, and sending it again gets the same.
    this.refuse(head, spec, error, 'auto', false)
  }

  /** Off the queue and the phone, with the writes about a set it made, and
   *  onto the banner -- `retry`: with a retry that puts them back. */
  private refuse(head: Entry, spec: WriteSpec, error: MutationFailed,
    remedy: Remedy, retry: boolean): void {
    this.queue.shift()
    this.unkeep(head)
    const dropped = this.dropDependents(head, spec)
    this.hooks.fail(spec.key(head.args), error.germanMessage,
      retry ? () => { this.requeue([head, ...dropped]) } : null, remedy)
    this.waiters.get(head.id)?.reject(error)
    this.waiters.delete(head.id)
    this.afterAnswer()
  }

  /** Writes back in line where they were made, and on the phone again. The
   *  write out keeps its turn: only a request in flight, not a turn waited
   *  for -- ahead of an older write, the retry went out after it (B6 third
   *  review). Tried again on the lifter's tap, a write gets its three tries
   *  again: its old ones refused it at its next server error. */
  private requeue(entries: Entry[]): void {
    this.strikes = { id: '', count: 0, since: 0 }
    for (const entry of entries) {
      this.insert(entry, this.out ? 1 : 0)
      if (this.hooks.specs[entry.kind]!.durable) this.keep(entry)
    }
    this.publish()
    this.kick()
  }

  /** Takes in the writes another tab of the workout keeps and this one has
   *  not: sent from here too, in their place. Finishing here went ahead
   *  without the sets a tab put away had not sent yet, and they were lost
   *  (B6 re-review). A write the other tab sends meanwhile is found gone
   *  under the lock, as a restored one is. Never before `from`: the write
   *  out keeps its turn. */
  private gather(from: number): void {
    const kept = this.hooks.shelf.list()
    if (kept === undefined) return
    const known = new Set(this.queue.map((entry) => entry.id))
    let took = false
    for (const entry of kept) {
      const spec = this.hooks.specs[entry.kind]
      if (known.has(entry.id) || spec === undefined) continue
      entry.args = this.resolve(spec, entry.args)
      this.insert(entry, from)
      this.onShelf.add(entry.id)
      took = true
    }
    if (!took) return
    this.recovering = true
    this.publish()
  }

  /** Into the queue by `order`, never before index `from`. */
  private insert(entry: Entry, from: number): void {
    let at = this.queue.length
    while (at > from && this.queue[at - 1]!.order > entry.order) at -= 1
    this.queue.splice(at, 0, entry)
    this.order = Math.max(this.order, entry.order)
  }

  /** A 409 or a 404 ('moot'): the write met something the server no longer
   *  has. Which of three things happened, only the server knows. The workout
   *  finished -- on the other phone, or by the three-hour rule: its page is
   *  the debrief now. It is gone -- discarded: home. Still running: the
   *  write aimed at a row that is gone -- a delete that had landed after
   *  all, a set the partner's plan removed -- and is moot, not failed.
   *  'elsewhere': another tab sent it, and the screen names the set it made. */
  private async askServer(head: Entry, spec: WriteSpec, why: 'moot' | 'elsewhere'): Promise<void> {
    this.busy = true
    let fresh: SessionDetailPayload
    try {
      fresh = await this.hooks.fetchFresh()
    } catch (error) {
      this.busy = false
      if (error instanceof MutationFailed && error.reason === 'gone') {
        await this.clear()
        this.hooks.gone()
        return
      }
      // A lapsed login answers the question as it answers a write. Anything
      // else: the question did not get through -- as for the write, later.
      await this.failed(head, spec, error instanceof MutationFailed && error.needsReload
        ? error : new MutationFailed('network'))
      return
    }
    this.busy = false
    if (fresh.session.finished_at !== null) {
      await this.clear()
      this.hooks.finished()
      return
    }
    if (this.queue[0] !== head) { this.pump(); return }
    this.queue.shift()
    this.unkeep(head)
    if (why === 'elsewhere') this.adopt(head, spec, fresh)
    else this.dropDependents(head, spec)
    this.base = fresh
    this.version += 1
    this.hooks.succeed(spec.key(head.args))
    this.settle(head, fresh)
    this.afterAnswer()
  }

  private afterAnswer(): void {
    if (this.queue.length === 0) {
      if (this.state !== 'blocked') this.setState('idle')
      this.publish()
      this.settleFlushes(true)
      if (this.recovering) {
        this.recovering = false
        this.hooks.drained()
      }
      return
    }
    if (this.state === 'waiting') this.setState('sending')
    this.publish()
    this.pump()
  }

  private settle(head: Entry, fresh: SessionDetailPayload): void {
    this.waiters.get(head.id)?.resolve(fresh)
    this.waiters.delete(head.id)
  }

  /** No write that is not kept waits behind ones that cannot get through:
   *  each is said now, with its own retry. The one out keeps its turn. */
  private shed(error: MutationFailed): void {
    this.queue = this.queue.filter((entry, i) => {
      const spec = this.hooks.specs[entry.kind]!
      if (spec.durable || (i === 0 && this.busy)) return true
      this.lose(entry, spec, error)
      return false
    })
  }

  /** A lost write that is not kept: off the queue, onto the banner. */
  private lose(entry: Entry, spec: WriteSpec, error: MutationFailed): void {
    const resend = spec.resend === null || !error.retryable
      ? null
      : () => { this.enqueue(entry.kind, entry.args).catch(() => {}) }
    this.hooks.fail(spec.key(entry.args), error.germanMessage, resend, spec.resend ?? 'auto')
    this.waiters.get(entry.id)?.reject(error)
    this.waiters.delete(entry.id)
  }

  /** A set the server has now named: every later write naming the drawn one
   *  names the real one, on the phone too. No set with its key in the
   *  answer means the server did not make it -- the writes about it go. */
  private adopt(head: Entry, spec: WriteSpec, fresh: SessionDetailPayload): void {
    const key = head.args[spec.creates!.key] as string
    const temp = head.args[spec.creates!.temp] as number
    const made = fresh.visible_exercises.flatMap((se) => se.sets).find((s) => s.key === key)
    if (made === undefined) {
      this.dropDependents(head, spec)
      return
    }
    this.resolved.set(temp, made.id)
    this.hooks.shelf.name(temp, made.id)
    for (const entry of this.queue) {
      const at = this.hooks.specs[entry.kind]!.setArg
      if (at === undefined || entry.args[at] !== temp) continue
      entry.args = entry.args.map((arg, i) => (i === at ? made.id : arg))
      if (!this.hooks.specs[entry.kind]!.durable) continue
      // Not one another tab has sent: put back, it was sent twice.
      if (!this.onShelf.has(entry.id) || this.hooks.shelf.get(entry.id) !== null) this.keep(entry)
    }
  }

  /** Drops the writes about the set `head` would have made; returns them. */
  private dropDependents(head: Entry, spec: WriteSpec): Entry[] {
    if (spec.creates === undefined) return []
    const temp = head.args[spec.creates.temp]
    const dropped: Entry[] = []
    this.queue = this.queue.filter((entry) => {
      const at = this.hooks.specs[entry.kind]!.setArg
      if (at === undefined || entry.args[at] !== temp) return true
      this.unkeep(entry)
      this.waiters.get(entry.id)?.resolve(this.base)
      this.waiters.delete(entry.id)
      dropped.push(entry)
      return false
    })
    return dropped
  }

  /** A set id captured by the screen before its set was named: the real one,
   *  once this tab or any other has seen it named. Sent drawn, it met no
   *  set -- a 404, dropped as moot, and the un-log was lost (B6 third
   *  review). */
  private resolve(spec: WriteSpec, args: unknown[]): unknown[] {
    if (spec.setArg === undefined) return args
    const id = args[spec.setArg]
    if (typeof id !== 'number' || id >= 0) return args
    const real = this.resolved.get(id) ?? this.hooks.shelf.named(id) ?? undefined
    return real === undefined ? args : args.map((arg, i) => (i === spec.setArg ? real : arg))
  }

  /** Said at once; the screen is redrawn by the next publish, if at all. */
  private setState(state: OutboxState): void {
    if (this.state === state) return
    this.state = state
    this.hooks.status(this.status())
  }

  private kept(): Entry[] {
    return this.queue.filter((entry) => this.hooks.specs[entry.kind]!.durable)
  }

  private status(): OutboxStatus {
    const kept = this.kept()
    const setIds: number[] = []
    const stuck = this.state === 'waiting' || this.state === 'blocked'
    for (const entry of stuck ? kept : []) {
      const spec = this.hooks.specs[entry.kind]!
      if (spec.creates !== undefined) setIds.push(entry.args[spec.creates.temp] as number)
      else if (spec.setArg !== undefined) setIds.push(entry.args[spec.setArg] as number)
    }
    return { state: this.state, count: kept.length, setIds }
  }

  private settleFlushes(drained: boolean): void {
    const waiting = this.flushes
    this.flushes = []
    for (const resolve of waiting) resolve(drained)
  }

  private publish(): void {
    this.hooks.show(this.display())
    this.hooks.status(this.status())
    this.hooks.hold(this.oldest())
  }

  /** The hold cookie: the oldest write any tab of the workout keeps. From
   *  this tab's own queue only, a tab with nothing to send deleted the
   *  cookie another tab's writes still needed (B6 review). */
  private oldest(): number | null {
    const times = this.kept().map((entry) => entry.at)
    const onPhone = this.hooks.shelf.oldest()
    if (typeof onPhone === 'number') times.push(onPhone)
    return times.length === 0 ? null : Math.min(...times)
  }

  private keep(entry: Entry): void {
    if (this.hooks.shelf.put(entry)) this.onShelf.add(entry.id)
  }

  private unkeep(entry: Entry): void {
    this.hooks.shelf.drop(entry.id)
    this.onShelf.delete(entry.id)
  }
}

/** One send at a time across the tabs of a workout: the Web Locks API, where
 *  there is one. A phone on the local network during development is not a
 *  secure context and has none -- its one tab sends as before. */
export function exclusively(name: string): OutboxHooks['exclusive'] {
  return async (run) => {
    const locks = typeof navigator === 'undefined' ? undefined : navigator.locks
    if (locks === undefined) return run()
    let ran = false
    try {
      await locks.request(name, async () => { ran = true; await run() })
    } catch (error) {
      // The lock itself failed: sent without it, rather than never.
      if (!ran) return run()
      throw error
    }
  }
}

// ---------------------------------------------------------------------------
// The phone's side: localStorage, the hold cookie, ids.
// ---------------------------------------------------------------------------

const PREFIX = 'gym-outbox:'
/** The sets named so far, `{drawn: real}`, under the workout's own prefix:
 *  swept with its writes. Never a write's id, which is a uuid. */
const NAMES = 'names'

/** One key per write -- `gym-outbox:v1:<session>:<id>` -- so two tabs never
 *  overwrite each other's list. localStorage can throw (a private window, a
 *  full disk): the screen then works as a screen with no memory. */
export function localShelf(sessionId: number, storage: Storage = window.localStorage): Shelf {
  const mine = `${PREFIX}v${OUTBOX_VERSION}:${sessionId}:`
  const namesKey = `${mine}${NAMES}`
  // Storage that throws throws on; a value that cannot be read is named
  // afresh.
  const names = (): Record<string, unknown> => {
    const raw = storage.getItem(namesKey)
    try {
      const parsed: unknown = JSON.parse(raw ?? '{}')
      return typeof parsed === 'object' && parsed !== null ? parsed as Record<string, unknown> : {}
    } catch {
      return {}
    }
  }
  return {
    read() {
      const entries: Entry[] = []
      let stale = 0
      try {
        const keys: string[] = []
        for (let i = 0; i < storage.length; i += 1) {
          const key = storage.key(i)
          if (key !== null && key.startsWith(PREFIX)) keys.push(key)
        }
        for (const key of keys) {
          if (!key.startsWith(mine)) {
            // Another workout's: only one runs at a time, and Start leads to
            // it, so this one is over -- finished or thrown away elsewhere.
            // Another version's, for this workout: it cannot be read back.
            if (key.startsWith(`${PREFIX}v`) && key.split(':')[2] === String(sessionId)) {
              stale += 1
            }
            storage.removeItem(key)
            continue
          }
          if (key === namesKey) continue
          const entry = parseEntry(storage.getItem(key))
          if (entry === null) {
            stale += 1
            storage.removeItem(key)
          } else {
            entries.push(entry)
          }
        }
      } catch {
        return { entries: [], stale: 0 }
      }
      // The order they were made in, by every tab of the workout.
      entries.sort((a, b) => a.order - b.order)
      return { entries, stale }
    },
    put(entry) {
      try {
        storage.setItem(`${mine}${entry.id}`, JSON.stringify(entry))
        return true
      } catch {
        return false
      }
    },
    drop(id) {
      try { storage.removeItem(`${mine}${id}`) } catch { /* no memory */ }
    },
    get(id) {
      try {
        const raw = storage.getItem(`${mine}${id}`)
        return raw === null ? null : parseEntry(raw) ?? undefined
      } catch {
        return undefined
      }
    },
    list() {
      try {
        const entries: Entry[] = []
        for (let i = 0; i < storage.length; i += 1) {
          const key = storage.key(i)
          if (key === null || !key.startsWith(mine)) continue
          const entry = parseEntry(storage.getItem(key))
          if (entry !== null) entries.push(entry)
        }
        return entries.sort((a, b) => a.order - b.order)
      } catch {
        return undefined
      }
    },
    oldest() {
      try {
        let oldest: number | null = null
        for (let i = 0; i < storage.length; i += 1) {
          const key = storage.key(i)
          if (key === null || !key.startsWith(mine)) continue
          const entry = parseEntry(storage.getItem(key))
          if (entry !== null && (oldest === null || entry.at < oldest)) oldest = entry.at
        }
        return oldest
      } catch {
        return undefined
      }
    },
    name(temp, real) {
      try {
        storage.setItem(namesKey, JSON.stringify({ ...names(), [temp]: real }))
      } catch { /* no memory: this tab's own still holds */ }
    },
    named(temp) {
      try {
        const real = names()[String(temp)]
        return typeof real === 'number' ? real : null
      } catch {
        return undefined
      }
    },
  }
}

function parseEntry(raw: string | null): Entry | null {
  try {
    const entry = JSON.parse(raw ?? '') as Partial<Entry>
    if (entry.v !== OUTBOX_VERSION || typeof entry.id !== 'string' || typeof entry.order !== 'number'
      || typeof entry.at !== 'number' || typeof entry.kind !== 'string'
      || !Array.isArray(entry.args)) return null
    return entry as Entry
  } catch {
    return null
  }
}

export const HOLD_COOKIE = 'gym_outbox'
const HOLD_SECONDS = 7 * 24 * 3600

/** While the phone holds writes for the workout, the server does not end it
 *  by the three-hour rule before they are in (helpers._outbox_hold). */
export function writeHold(sessionId: number, oldestAt: number | null): void {
  const secure = window.location.protocol === 'https:' ? '; Secure' : ''
  document.cookie = oldestAt === null
    ? `${HOLD_COOKIE}=; Path=/gym; Max-Age=0; SameSite=Lax${secure}`
    : `${HOLD_COOKIE}=${sessionId}:${Math.round(oldestAt)}; Path=/gym; Max-Age=${HOLD_SECONDS}; SameSite=Lax${secure}`
}

/** A write's id. randomUUID exists only in a secure context, and the phone
 *  on the local network during development is not one. */
export function newId(): string {
  if (typeof crypto.randomUUID === 'function') return crypto.randomUUID()
  const bytes = crypto.getRandomValues(new Uint8Array(16))
  bytes[6] = (bytes[6]! & 0x0f) | 0x40
  bytes[8] = (bytes[8]! & 0x3f) | 0x80
  const hex = [...bytes].map((b) => b.toString(16).padStart(2, '0')).join('')
  return `${hex.slice(0, 8)}-${hex.slice(8, 12)}-${hex.slice(12, 16)}-${hex.slice(16, 20)}-${hex.slice(20)}`
}
