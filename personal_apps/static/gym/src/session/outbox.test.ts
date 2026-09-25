import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { MutationFailed } from './api'
import {
  BACKOFF_MS, OUTBOX_VERSION, Outbox, SERVER_SPAN_MS, exclusively, localShelf, newId, writeHold,
  type Entry, type OutboxHooks, type WriteSpec,
} from './outbox'
import * as optimistic from './optimistic'
import type { OutboxStatus, Remedy } from './stores'
import type { SessionDetailPayload } from './types'
import { payload } from './types.test-d'

/**
 * The outbox (B6, D6-A) against a pretend server: every write is drawn at
 * once, kept on the phone, and sent in order until it lands -- whatever the
 * connection does.
 *
 * The fixture's live exercise is 10: set 100 done, 101 and 102 open.
 */

type Outcome = 'ok' | 'hang' | MutationFailed | Promise<void>

/** Holds its own copy of the workout and changes it as the routes would --
 *  the optimistic functions stand in -- then answers with the whole screen,
 *  unless the test scripted another outcome for that request. */
class Server {
  state: SessionDetailPayload = payload
  calls: { kind: string; args: unknown[]; at: number }[] = []
  outcomes: Outcome[] = []
  nextId = 500

  answer(kind: string, args: unknown[], at: number): Promise<SessionDetailPayload> {
    this.calls.push({ kind, args, at })
    const outcome = this.outcomes.shift() ?? 'ok'
    if (outcome === 'hang') return new Promise(() => {})
    if (outcome instanceof MutationFailed) return Promise.reject(outcome)
    const land = () => { this.state = this.apply(kind, args, at); return this.state }
    return outcome instanceof Promise ? outcome.then(land) : Promise.resolve(land())
  }

  private apply(kind: string, args: unknown[], at: number): SessionDetailPayload {
    if (kind === 'tick') {
      return optimistic.toggleSet(this.state, args[0] as number, args[1] as boolean, 60, 8, at)
    }
    if (kind === 'add') {
      // A copy finds the set the first made (the client key).
      return optimistic.addSet(this.state, args[0] as number, 60, 8, args[1] as string,
        this.nextId++, at)
    }
    if (kind === 'note') return optimistic.setSessionMeta(this.state, { notes: args[0] as string })
    return this.state
  }
}

function specsFor(server: Server): Record<string, WriteSpec> {
  const send = (kind: string) => (args: unknown[], at: number) => server.answer(kind, args, at)
  return {
    tick: {
      send: send('tick'),
      apply: (p, args, at) => optimistic.toggleSet(p, args[0] as number, args[1] as boolean, 60, 8, at),
      durable: true, key: (args) => `set-${String(args[0])}:done`, setArg: 0,
    },
    add: {
      send: send('add'),
      apply: (p, args, at) => optimistic.addSet(p, args[0] as number, 60, 8, args[1] as string,
        args[2] as number, at),
      durable: true, key: (args) => `add-${String(args[1])}`, creates: { key: 1, temp: 2 },
    },
    note: {
      send: send('note'),
      apply: (p, args) => optimistic.setSessionMeta(p, { notes: args[0] as string }),
      durable: true, key: () => 'note',
    },
    swap: { send: send('swap'), durable: false, key: (args) => `swap-${String(args[0])}`, resend: 'manual' },
    nudge: { send: send('nudge'), durable: false, key: () => 'rest', resend: null },
    broken: {
      send: () => { throw new TypeError('args from another shape') },
      durable: true, key: () => 'broken',
    },
    undrawable: {
      send: send('note'),
      apply: () => { throw new TypeError('args from another shape') },
      durable: true, key: () => 'undrawable',
    },
  }
}

/** The phone's storage, as JSON like the real one. `full`: nothing can be
 *  kept -- a private window, a full disk. */
function memoryShelf(start: Entry[] = [], stale = 0, full = false) {
  const kept = new Map<string, Entry>()
  const names = new Map<number, number>()
  const copy = (entry: Entry) => JSON.parse(JSON.stringify(entry)) as Entry
  for (const entry of start) kept.set(entry.id, copy(entry))
  return {
    kept,
    names,
    shelf: {
      name: (temp: number, real: number) => { if (!full) names.set(temp, real) },
      named: (temp: number) => names.get(temp) ?? null,
      read: () => ({
        entries: [...kept.values()].map(copy).sort((a, b) => a.order - b.order),
        stale,
      }),
      put: (entry: Entry) => {
        if (full) return false
        kept.set(entry.id, copy(entry))
        return true
      },
      drop: (id: string) => { kept.delete(id) },
      get: (id: string) => {
        const entry = kept.get(id)
        return entry === undefined ? null : copy(entry)
      },
      oldest: () => (kept.size === 0 ? null : Math.min(...[...kept.values()].map((e) => e.at))),
      list: () => [...kept.values()].map(copy).sort((a, b) => a.order - b.order),
    },
  }
}

/** navigator.locks as two tabs of one browser share it: one holder at a time. */
function sharedLock(): OutboxHooks['exclusive'] {
  let tail = Promise.resolve()
  return (run) => {
    const turn = tail.then(run)
    tail = turn.catch(() => {})
    return turn
  }
}

interface Failure { key: string; message: string; retry: (() => void) | null; remedy: Remedy }

const FIRST_AT = 1_001_000

/** One tab. Two tabs of one workout share `server`, the shelf and a lock. */
function harness(stored = memoryShelf(), tab: {
  server?: Server
  exclusive?: OutboxHooks['exclusive']
  now?: () => number
  /** The clock that never steps back; `now` unless given. */
  elapsed?: () => number
  /** Its writes' id prefix: two tabs never make the same id. */
  name?: string
} = {}) {
  const server = tab.server ?? new Server()
  const seen = {
    shown: null as SessionDetailPayload | null,
    status: { state: 'idle', count: 0, setIds: [] } as OutboxStatus,
    hold: null as number | null,
    failures: [] as Failure[],
    succeeded: [] as string[],
    finished: 0, gone: 0, reloads: 0, drained: 0,
  }
  let clock = FIRST_AT - 1000
  let ids = 0
  const now = tab.now ?? (() => (clock += 1000))
  const hooks: OutboxHooks = {
    specs: specsFor(server),
    shelf: stored.shelf,
    show: (p) => { seen.shown = p },
    status: (s) => { seen.status = s },
    hold: (at) => { seen.hold = at },
    begin: () => {},
    end: () => {},
    succeed: (key) => { seen.succeeded.push(key) },
    fail: (key, message, retry, remedy) => { seen.failures.push({ key, message, retry, remedy }) },
    fetchFresh: () => Promise.resolve(server.state),
    finished: () => { seen.finished += 1 },
    gone: () => { seen.gone += 1 },
    reload: () => { seen.reloads += 1 },
    drained: () => { seen.drained += 1 },
    // A stand-in for optimistic.relive, which has its own tests: here it
    // only has to show WHEN it is applied.
    relive: (p) => ({ ...p, live_index: 99 }),
    exclusive: tab.exclusive ?? ((run) => run()),
    now,
    elapsed: tab.elapsed ?? now,
    newId: () => `${tab.name ?? 'w'}${++ids}`,
  }
  const outbox = new Outbox(payload, hooks)
  return { outbox, server, hooks, kept: stored.kept, seen }
}

const settle = () => vi.advanceTimersByTimeAsync(0)
const offline = () => new MutationFailed('network')
const gate = () => {
  let open!: () => void
  const closed = new Promise<void>((resolve) => { open = resolve })
  return { closed, open }
}
const setOf = (p: SessionDetailPayload, id: number) =>
  p.visible_exercises.flatMap((se) => se.sets).find((s) => s.id === id)
const entry = (over: Partial<Entry>): Entry => ({
  v: OUTBOX_VERSION, id: 'e', order: over.at ?? 1000, at: 1000, kind: 'note', args: ['x'], ...over,
})

beforeEach(() => { vi.useFakeTimers() })
afterEach(() => { vi.useRealTimers() })

describe('Outbox', () => {
  it('draws a write at once and keeps it on the phone before anything is sent', async () => {
    const { outbox, server, kept, seen } = harness()
    outbox.start()
    void outbox.enqueue('tick', [101, true])

    expect(setOf(seen.shown!, 101)?.completed).toBe(true)
    expect([...kept.values()]).toEqual([
      { v: OUTBOX_VERSION, id: 'w1', order: FIRST_AT, at: FIRST_AT, kind: 'tick', args: [101, true] }])
    expect(server.calls).toHaveLength(0)

    await settle()
    expect(server.calls).toEqual([{ kind: 'tick', args: [101, true], at: FIRST_AT }])
    expect(kept.size).toBe(0)
    expect(seen.succeeded).toEqual(['set-101:done'])
  })

  it('sends one write at a time, in the order they were made', async () => {
    const { outbox, server } = harness()
    const first = gate()
    server.outcomes = [first.closed]
    void outbox.enqueue('tick', [101, true])
    void outbox.enqueue('note', ['Knie'])
    void outbox.enqueue('tick', [102, true])
    await settle()
    expect(server.calls.map((c) => c.args)).toEqual([[101, true]])

    first.open()
    await settle()
    expect(server.calls.map((c) => c.args)).toEqual([[101, true], ['Knie'], [102, true]])
  })

  it('draws the writes not answered yet over the newest answer', async () => {
    // The answer to the first write knows nothing of the second: shown as it
    // came, the note typed after the set vanished for a round trip.
    const { outbox, server } = harness()
    const second = gate()
    server.outcomes = ['ok', second.closed]
    void outbox.enqueue('tick', [101, true])
    void outbox.enqueue('note', ['Knie'])
    await settle()

    expect(server.state.session.notes).not.toBe('Knie')
    expect(setOf(outbox.display(), 101)?.completed).toBe(true)
    expect(outbox.display().session.notes).toBe('Knie')
  })

  it('keeps a write through a lost connection and tries again, no rollback (G-138, G-139)', async () => {
    const { outbox, server, seen } = harness()
    outbox.start()
    server.outcomes = [offline(), offline(), offline()]
    void outbox.enqueue('tick', [101, true])
    await settle()

    expect(seen.status).toEqual({ state: 'waiting', count: 1, setIds: [101] })
    expect(setOf(seen.shown!, 101)?.completed).toBe(true)
    // Calm: the red banner is for what did not keep.
    expect(seen.failures).toEqual([])

    await vi.advanceTimersByTimeAsync(BACKOFF_MS[0]! - 1)
    expect(server.calls).toHaveLength(1)
    await vi.advanceTimersByTimeAsync(1)
    expect(server.calls).toHaveLength(2)
    await vi.advanceTimersByTimeAsync(BACKOFF_MS[1]!)
    expect(server.calls).toHaveLength(3)
    await vi.advanceTimersByTimeAsync(BACKOFF_MS[2]!)
    expect(server.calls).toHaveLength(4)
    expect(seen.status).toEqual({ state: 'idle', count: 0, setIds: [] })
  })

  it('pauses half a minute at most between tries', async () => {
    const { outbox, server } = harness()
    server.outcomes = Array.from({ length: 8 }, offline)
    void outbox.enqueue('tick', [101, true])
    await settle()
    for (const pause of [...BACKOFF_MS, 30_000, 30_000]) {
      const before = server.calls.length
      await vi.advanceTimersByTimeAsync(pause)
      expect(server.calls).toHaveLength(before + 1)
    }
    expect(BACKOFF_MS.at(-1)).toBe(30_000)
  })

  it('tries at once when kicked -- the connection back, the app in front, a new write', async () => {
    const { outbox, server, seen } = harness()
    server.outcomes = [offline(), offline()]
    void outbox.enqueue('tick', [101, true])
    await settle()
    outbox.kick()
    await settle()
    expect(server.calls).toHaveLength(2)

    void outbox.enqueue('tick', [102, true])
    await settle()
    expect(server.calls.map((c) => c.args)).toEqual([[101, true], [101, true], [101, true], [102, true]])
    expect(seen.status.state).toBe('idle')
  })

  it('restores what the phone kept, in the order it was made, and sends it with its time', async () => {
    // Every tab's writes, and the time orders them.
    const stored = memoryShelf([
      entry({ id: 'b', at: 2000, kind: 'note', args: ['zwei'] }),
      entry({ id: 'a', at: 1000, kind: 'tick', args: [101, true] }),
    ])
    const { outbox, server } = harness(stored)
    expect(setOf(outbox.display(), 101)?.completed).toBe(true)
    expect(outbox.display().session.notes).toBe('zwei')

    outbox.start()
    await settle()
    expect(server.calls).toEqual([
      { kind: 'tick', args: [101, true], at: 1000 },
      { kind: 'note', args: ['zwei'], at: 2000 }])
    expect(stored.kept.size).toBe(0)
  })

  it('places new writes after the ones it restored, whatever the clock says', () => {
    const stored = memoryShelf([entry({ id: 'a', order: 5_000_000 })])
    const { outbox, kept } = harness(stored)
    void outbox.enqueue('note', ['y'])
    expect(kept.get('w1')).toMatchObject({ order: 5_000_001, at: FIRST_AT })
  })

  it('keeps the order the lifter made them in when the clock steps back (B6 review)', async () => {
    // Un-logged at 10:00:05, the clock stepped back ten seconds, logged again
    // at 09:59:58: after a reload, sorted by time, the un-log came last and
    // the set ended open although the lifter's last word was "done".
    const times = [36_005_000, 35_998_000]
    const stored = memoryShelf()
    const first = harness(stored, { now: () => times.shift()! })
    first.server.outcomes = ['hang'] // no signal: neither gets through
    void first.outbox.enqueue('tick', [100, false])
    void first.outbox.enqueue('tick', [100, true])
    await settle()

    const reloaded = harness(stored)
    expect(setOf(reloaded.outbox.display(), 100)?.completed).toBe(true)
    reloaded.outbox.start()
    await settle()
    // Each is still sent with the time it was made.
    expect(reloaded.server.calls).toEqual([
      { kind: 'tick', args: [100, false], at: 36_005_000 },
      { kind: 'tick', args: [100, true], at: 35_998_000 }])
  })

  it('asks the server again once the writes it held back are in -- and only then', async () => {
    const { outbox, server, seen } = harness()
    outbox.start()
    void outbox.enqueue('tick', [101, true])
    await settle()
    expect(seen.drained).toBe(0)

    server.outcomes = [offline()]
    void outbox.enqueue('tick', [102, true])
    void outbox.enqueue('note', ['x'])
    await settle()
    expect(seen.drained).toBe(0)
    outbox.kick()
    await settle()
    expect(seen.drained).toBe(1)
  })

  it('asks again after sending what a reload restored', async () => {
    const { outbox, seen } = harness(memoryShelf([entry({})]))
    outbox.start()
    await settle()
    expect(seen.drained).toBe(1)
  })

  it('holds the three-hour rule from the oldest kept write, and lets go once all are in', async () => {
    const { outbox, server, seen } = harness()
    server.outcomes = [offline()]
    void outbox.enqueue('tick', [101, true])
    void outbox.enqueue('note', ['x'])
    void outbox.enqueue('swap', [11]).catch(() => {})
    await settle()
    expect(seen.hold).toBe(FIRST_AT)

    outbox.kick()
    await settle()
    expect(seen.hold).toBeNull()
  })

  it('works the live exercise out itself while any write is not answered yet', async () => {
    // Only from the first failure, it left the card on an exercise just
    // finished for as long as a slow answer took: a second tap appended a
    // set to it (B6 review). The old screen held the button instead.
    const { outbox, server } = harness()
    void outbox.enqueue('tick', [101, true])
    expect(outbox.display().live_index).toBe(99)
    await settle()
    expect(outbox.display().live_index).toBe(payload.live_index)

    server.outcomes = [offline()]
    void outbox.enqueue('tick', [102, true])
    await settle()
    expect(outbox.display().live_index).toBe(99)

    outbox.kick()
    await settle()
    expect(outbox.display().live_index).toBe(payload.live_index)
  })

  it('drops a refused write, says why, and draws it no more', async () => {
    const { outbox, server, kept, seen } = harness()
    server.outcomes = [new MutationFailed('invalid', 'Gewicht zu hoch.')]
    const answered = outbox.enqueue('tick', [101, true]).catch((error: unknown) => error)
    await settle()

    expect(await answered).toBeInstanceOf(MutationFailed)
    expect(seen.failures).toEqual([
      { key: 'set-101:done', message: 'Gewicht zu hoch.', retry: null, remedy: 'auto' }])
    expect(setOf(outbox.display(), 101)?.completed).toBe(false)
    expect(kept.size).toBe(0)
    expect(seen.status.state).toBe('idle')
  })

  it('refuses a write that cannot even be sent, rather than trying it forever', async () => {
    const { outbox, kept, seen } = harness()
    const answered = outbox.enqueue('broken', []).catch((error: unknown) => error)
    await settle()
    expect(await answered).toBeInstanceOf(MutationFailed)
    expect(seen.failures.map((f) => f.key)).toEqual(['broken'])
    expect(kept.size).toBe(0)
  })

  it('still sends a kept write it cannot draw, and the screen stays up', async () => {
    const { outbox, server } = harness()
    void outbox.enqueue('undrawable', ['x'])
    expect(() => outbox.display()).not.toThrow()
    await settle()
    expect(server.calls).toHaveLength(1)
  })

  it('names the set the server made in every write after it, on the phone too', async () => {
    const { outbox, server, kept, seen } = harness()
    server.outcomes = ['ok', offline()]
    void outbox.enqueue('add', [10, 'k1', -5])
    void outbox.enqueue('tick', [-5, false])
    await settle()

    // The add is in, as set 500; the un-log waits, and names 500 now.
    expect([...kept.values()].map((e) => e.args)).toEqual([[500, false]])
    expect(seen.status.setIds).toEqual([500])
    // A write made later with the id the screen had captured names it too.
    void outbox.enqueue('tick', [-5, true])
    expect([...kept.values()].at(-1)!.args).toEqual([500, true])
    await settle()
    expect(server.calls.map((c) => c.args)).toEqual([
      [10, 'k1', -5], [500, false], [500, false], [500, true]])
  })

  it('drops the writes about a set the server refused to make', async () => {
    const { outbox, server, kept } = harness()
    server.outcomes = [new MutationFailed('invalid', 'Nein.')]
    void outbox.enqueue('add', [10, 'k1', -5]).catch(() => {})
    const unlog = outbox.enqueue('tick', [-5, false])
    await settle()
    await expect(unlog).resolves.toBeDefined()
    expect(server.calls.map((c) => c.kind)).toEqual(['add'])
    expect(kept.size).toBe(0)
  })

  it('gives up on a write the server fails every time, and lets the rest through (B6 review)', async () => {
    // A server bug on one write used to hold every later set on the phone,
    // "Wartet auf Verbindung" on a working connection, for good.
    let now = 1000
    const { outbox, server, kept, seen } = harness(undefined, { now: () => now })
    const broken = () => new MutationFailed('server')
    server.outcomes = [broken(), broken(), broken()]
    const refused = outbox.enqueue('tick', [101, true])
    refused.catch(() => {})
    void outbox.enqueue('note', ['Knie'])
    await vi.advanceTimersByTimeAsync(BACKOFF_MS[0]!)
    now += SERVER_SPAN_MS
    await vi.advanceTimersByTimeAsync(BACKOFF_MS[1]!)

    await expect(refused).rejects.toMatchObject({ reason: 'server' })
    expect(server.calls.map((c) => c.kind)).toEqual(['tick', 'tick', 'tick', 'note'])
    expect(kept.size).toBe(0)
    expect(seen.status.state).toBe('idle')
    expect(seen.failures).toMatchObject([{ key: 'set-101:done', remedy: 'manual' }])
    // Its own retry puts it back in line.
    seen.failures[0]!.retry!()
    await settle()
    expect(server.calls.at(-1)).toMatchObject({ kind: 'tick', args: [101, true] })
  })

  it('keeps trying through server errors for a minute before it gives up (B6 re-review)', async () => {
    // Three tries fitted in seven seconds of backoff: a database restarting
    // for twenty seconds had a set refused and taken off the phone.
    let now = 1000
    const { outbox, server, kept, seen } = harness(undefined, { now: () => now })
    server.outcomes = Array.from({ length: 5 }, () => new MutationFailed('server'))
    const landed = outbox.enqueue('tick', [101, true])
    await vi.advanceTimersByTimeAsync(BACKOFF_MS[0]! + BACKOFF_MS[1]! + BACKOFF_MS[2]!)
    expect(server.calls).toHaveLength(4)
    expect(seen.failures).toEqual([])
    expect(kept.size).toBe(1)
    now += SERVER_SPAN_MS - 1
    await vi.advanceTimersByTimeAsync(BACKOFF_MS[3]! + BACKOFF_MS[4]!)
    await landed
    expect(server.calls).toHaveLength(6)
    expect(seen.failures).toEqual([])
  })

  it('puts a refused set back as it was made, with the writes about it (B6 re-review)', async () => {
    // Queued anew, the retry stamped a set logged at 10:00 with the time of
    // the tap, and a correction made to it meanwhile was gone.
    let now = 1000
    const { outbox, server, kept, seen } = harness(undefined, { now: () => now })
    const broken = () => new MutationFailed('server')
    server.outcomes = [broken(), broken(), broken()]
    void outbox.enqueue('add', [10, 'k1', -5]).catch(() => {})
    now = 1500
    void outbox.enqueue('tick', [-5, false])
    await vi.advanceTimersByTimeAsync(BACKOFF_MS[0]!)
    now = 2000 + SERVER_SPAN_MS
    await vi.advanceTimersByTimeAsync(BACKOFF_MS[1]!)
    expect(seen.failures).toMatchObject([{ key: 'add-k1', remedy: 'manual' }])
    expect(kept.size).toBe(0)

    now = 400_000
    seen.failures[0]!.retry!()
    expect(kept.size).toBe(2)
    await settle()
    expect(server.calls.slice(-2)).toEqual([
      { kind: 'add', args: [10, 'k1', -5], at: 1000 },
      { kind: 'tick', args: [500, false], at: 1500 },
    ])
    expect(kept.size).toBe(0)
  })

  it('gives up on a server error only after three tries, however long they took (B6 re-review)', async () => {
    // A phone asleep between two tries: a minute gone is not three strikes.
    let now = 1000
    const { outbox, server, seen } = harness(undefined, { now: () => now })
    server.outcomes = [new MutationFailed('server'), new MutationFailed('server')]
    const landed = outbox.enqueue('tick', [101, true])
    await settle()
    now += 10 * SERVER_SPAN_MS
    await vi.advanceTimersByTimeAsync(BACKOFF_MS[0]!)
    expect(seen.failures).toEqual([])
    await vi.advanceTimersByTimeAsync(BACKOFF_MS[1]!)
    await landed
    expect(server.calls).toHaveLength(3)
    expect(seen.failures).toEqual([])
  })

  it('puts a refused write back behind the one out (B6 re-review)', async () => {
    let now = 1000
    const { outbox, server, seen } = harness(undefined, { now: () => now })
    const broken = () => new MutationFailed('server')
    server.outcomes = [broken(), broken(), broken()]
    void outbox.enqueue('add', [10, 'k1', -5]).catch(() => {})
    await settle()
    await vi.advanceTimersByTimeAsync(BACKOFF_MS[0]!)
    now = 1000 + SERVER_SPAN_MS
    await vi.advanceTimersByTimeAsync(BACKOFF_MS[1]!)
    expect(seen.failures).toMatchObject([{ key: 'add-k1', remedy: 'manual' }])

    const out = gate()
    server.outcomes = [out.closed]
    now = 400_000
    void outbox.enqueue('note', ['Knie'])
    await settle()
    seen.failures[0]!.retry!()
    out.open()
    await settle()
    expect(server.calls.slice(3).map((c) => c.kind)).toEqual(['note', 'add'])
  })

  it('gives up after a minute of server errors when the phone\'s clock steps back (B6 third review)', async () => {
    // By the wall clock, ten minutes back held the writes behind it ten
    // minutes longer.
    let wall = 1000
    let steady = 0
    const { outbox, server, seen } = harness(undefined, { now: () => wall, elapsed: () => steady })
    const broken = () => new MutationFailed('server')
    server.outcomes = [broken(), broken(), broken()]
    const refused = outbox.enqueue('tick', [101, true])
    refused.catch(() => {})
    await settle()
    await vi.advanceTimersByTimeAsync(BACKOFF_MS[0]!)
    wall -= 10 * 60_000
    steady += SERVER_SPAN_MS
    await vi.advanceTimersByTimeAsync(BACKOFF_MS[1]!)

    await expect(refused).rejects.toMatchObject({ reason: 'server' })
    expect(seen.failures).toMatchObject([{ key: 'set-101:done', remedy: 'manual' }])
  })

  it('gives a write tried again on the lifter\'s tap its three tries again (B6 third review)', async () => {
    // Its old tries counted on: refused again at its next server error.
    let now = 1000
    const { outbox, server, seen } = harness(undefined, { now: () => now })
    const broken = () => new MutationFailed('server')
    server.outcomes = [broken(), broken(), broken()]
    void outbox.enqueue('tick', [101, true]).catch(() => {})
    await settle()
    await vi.advanceTimersByTimeAsync(BACKOFF_MS[0]!)
    now += SERVER_SPAN_MS
    await vi.advanceTimersByTimeAsync(BACKOFF_MS[1]!)
    expect(seen.failures).toHaveLength(1)

    server.outcomes = [broken()]
    seen.failures[0]!.retry!()
    await settle()
    await vi.advanceTimersByTimeAsync(Math.max(...BACKOFF_MS))
    expect(seen.failures).toHaveLength(1)
    expect(setOf(server.state, 101)?.completed).toBe(true)
  })

  it('puts a refused write back ahead of a later one only waiting for its turn (B6 third review)', async () => {
    // Waiting for the lock is no write out: the retry went in behind the
    // un-log tapped after it, and the set ended logged.
    let now = 1000
    const lock = sharedLock()
    const { outbox, server, seen } = harness(undefined, { now: () => now, exclusive: lock })
    const broken = () => new MutationFailed('server')
    server.outcomes = [broken(), broken(), broken()]
    void outbox.enqueue('tick', [101, true]).catch(() => {})
    await settle()
    await vi.advanceTimersByTimeAsync(BACKOFF_MS[0]!)
    now += SERVER_SPAN_MS
    await vi.advanceTimersByTimeAsync(BACKOFF_MS[1]!)
    expect(seen.failures).toHaveLength(1)

    let release!: () => void
    void lock(() => new Promise<void>((resolve) => { release = resolve }))
    now = 400_000
    void outbox.enqueue('tick', [101, false])
    await settle()
    seen.failures[0]!.retry!()
    release()
    await settle()
    expect(server.calls.slice(3).map((c) => c.args)).toEqual([[101, true], [101, false]])
    expect(setOf(server.state, 101)?.completed).toBe(false)
  })

  it('keeps trying a write through a server error that passes', async () => {
    const { outbox, server, seen } = harness()
    server.outcomes = [new MutationFailed('server'), new MutationFailed('server')]
    const landed = outbox.enqueue('tick', [101, true])
    await vi.advanceTimersByTimeAsync(BACKOFF_MS[0]! + BACKOFF_MS[1]!)
    await landed
    expect(server.calls).toHaveLength(3)
    expect(seen.failures).toEqual([])
  })

  it('marks the set it drew while the add waits', async () => {
    const { outbox, server, seen } = harness()
    server.outcomes = [offline()]
    void outbox.enqueue('add', [10, 'k1', -5])
    await settle()
    expect(seen.status.setIds).toEqual([-5])
    expect(setOf(seen.shown!, -5)).toMatchObject({ completed: true, key: 'k1' })
  })

  it('marks nothing while writes simply go out -- a write out for a moment is no news', async () => {
    const { outbox, server, seen } = harness()
    server.outcomes = ['hang']
    void outbox.enqueue('tick', [101, true])
    void outbox.enqueue('add', [10, 'k1', -5])
    await settle()
    expect(seen.status).toEqual({ state: 'sending', count: 2, setIds: [] })
  })

  it('drops a write that met a row the workout no longer has, quietly', async () => {
    // A delete that had landed with its answer lost; a set the partner's
    // plan removed. The workout is running: nothing failed.
    const { outbox, server, kept, seen } = harness()
    server.outcomes = [new MutationFailed('gone')]
    const answered = outbox.enqueue('tick', [101, true])
    await settle()
    await expect(answered).resolves.toBeDefined()
    expect(seen.failures).toEqual([])
    expect(seen.finished + seen.gone).toBe(0)
    expect(kept.size).toBe(0)
  })

  it('drops everything when the workout finished under it, and says so', async () => {
    const { outbox, server, hooks, kept, seen } = harness()
    hooks.fetchFresh = () => Promise.resolve(
      { ...payload, session: { ...payload.session, finished_at: '2026-09-25T10:00:00' } })
    server.outcomes = [new MutationFailed('finished')]
    void outbox.enqueue('tick', [101, true])
    void outbox.enqueue('note', ['x'])
    await settle()
    expect(seen.finished).toBe(1)
    expect(kept.size).toBe(0)
    expect(server.calls).toHaveLength(1)
  })

  it('goes home when the workout is gone', async () => {
    const { outbox, server, hooks, kept, seen } = harness()
    hooks.fetchFresh = () => Promise.reject(new MutationFailed('gone'))
    server.outcomes = [new MutationFailed('gone')]
    void outbox.enqueue('tick', [101, true])
    await settle()
    expect(seen.gone).toBe(1)
    expect(kept.size).toBe(0)
  })

  it('waits when it cannot even ask what a 409 meant', async () => {
    const { outbox, server, hooks, kept, seen } = harness()
    hooks.fetchFresh = () => Promise.reject(new MutationFailed('network'))
    server.outcomes = [new MutationFailed('finished')]
    void outbox.enqueue('tick', [101, true])
    await settle()
    expect(seen.status.state).toBe('waiting')
    expect(kept.size).toBe(1)
  })

  it('keeps every write for a fresh page after a stale token or a lapsed login', async () => {
    const { outbox, server, kept, seen } = harness()
    server.outcomes = [new MutationFailed('forbidden')]
    void outbox.enqueue('tick', [101, true])
    await settle()
    expect(seen.status.state).toBe('blocked')
    expect(seen.failures).toMatchObject([{ key: 'outbox-blocked', remedy: 'reload' }])
    seen.failures[0]!.retry!()
    expect(seen.reloads).toBe(1)

    // Sending again cannot work: nothing more goes out, and nothing is lost.
    void outbox.enqueue('note', ['x'])
    outbox.kick()
    await vi.advanceTimersByTimeAsync(120_000)
    expect(server.calls).toHaveLength(1)
    expect(kept.size).toBe(2)
    expect(await outbox.flush()).toBe(false)
  })

  it('fails a write it does not keep at once while the queue waits, with its own retry', async () => {
    const { outbox, server, kept, seen } = harness()
    server.outcomes = [offline()]
    void outbox.enqueue('tick', [101, true])
    await settle()

    const lost = outbox.enqueue('swap', [11]).catch((error: unknown) => error)
    expect(await lost).toBeInstanceOf(MutationFailed)
    expect(server.calls).toHaveLength(1)
    expect(seen.failures).toMatchObject([{ key: 'swap-11', remedy: 'manual' }])
    expect(kept.size).toBe(1)

    outbox.kick()
    await settle()
    seen.failures[0]!.retry!()
    await settle()
    expect(server.calls.map((c) => c.kind)).toEqual(['tick', 'tick', 'swap'])
  })

  it('says at once that a write it does not keep is lost behind one that stopped getting through', async () => {
    const { outbox, server, seen } = harness()
    server.outcomes = [offline()]
    void outbox.enqueue('tick', [101, true])
    const lost = outbox.enqueue('swap', [11]).catch((error: unknown) => error)
    await settle()
    expect(await lost).toBeInstanceOf(MutationFailed)
    expect(seen.failures.map((f) => f.key)).toEqual(['swap-11'])

    outbox.kick()
    await settle()
    expect(server.calls.map((c) => c.kind)).toEqual(['tick', 'tick'])
  })

  it('reports a lost "+15 s" and never sends it again', async () => {
    const { outbox, server, seen } = harness()
    server.outcomes = [offline()]
    const lost = outbox.enqueue('nudge', [15]).catch((error: unknown) => error)
    await settle()
    expect(await lost).toBeInstanceOf(MutationFailed)
    expect(seen.failures).toMatchObject([{ key: 'rest', retry: null }])
    expect(seen.status.state).toBe('idle')
    await vi.advanceTimersByTimeAsync(60_000)
    expect(server.calls).toHaveLength(1)
  })

  it('takes no refetch that set out before an answer came in', async () => {
    const { outbox, server } = harness()
    const answer = gate()
    server.outcomes = [answer.closed]
    const stamp = outbox.stamp()
    void outbox.enqueue('tick', [101, true])
    await settle()
    answer.open()
    await settle()

    // Older than the answer that is the base now: 101 stays done.
    expect(setOf(outbox.receive(payload, stamp), 101)?.completed).toBe(true)
    const noted = { ...payload, session: { ...payload.session, notes: 'neu' } }
    expect(outbox.receive(noted, outbox.stamp()).session.notes).toBe('neu')
  })

  it('lets a finish go once everything is in, and stops it the moment a write cannot get through', async () => {
    const { outbox, server } = harness()
    expect(await outbox.flush()).toBe(true)

    const answer = gate()
    server.outcomes = [answer.closed]
    void outbox.enqueue('tick', [101, true])
    const landed = outbox.flush()
    answer.open()
    await settle()
    expect(await landed).toBe(true)

    server.outcomes = [offline(), offline()]
    void outbox.enqueue('tick', [102, true])
    await settle()
    const refused = outbox.flush()
    await settle()
    expect(await refused).toBe(false)
    expect(server.calls).toHaveLength(3)
  })

  it('throws every write away with the workout, and waits out the one on its way', async () => {
    const { outbox, server, kept, seen } = harness()
    const answer = gate()
    server.outcomes = [answer.closed]
    void outbox.enqueue('tick', [101, true])
    void outbox.enqueue('note', ['x'])
    await settle()

    let cleared = false
    void outbox.clear().then(() => { cleared = true })
    await vi.advanceTimersByTimeAsync(200)
    expect(cleared).toBe(false)
    expect(kept.size).toBe(0)
    expect(seen.hold).toBeNull()

    answer.open()
    await vi.advanceTimersByTimeAsync(100)
    expect(cleared).toBe(true)
    expect(server.calls).toHaveLength(1)
  })

  it('tries no more once its screen is gone, and keeps what it holds for the next', async () => {
    const { outbox, server, kept } = harness()
    server.outcomes = [offline()]
    void outbox.enqueue('tick', [101, true])
    await settle()
    outbox.stop()
    await vi.advanceTimersByTimeAsync(120_000)
    void outbox.enqueue('note', ['x'])
    await vi.advanceTimersByTimeAsync(120_000)
    expect(server.calls).toHaveLength(1)
    expect(kept.size).toBe(2)

    outbox.start()
    await settle()
    expect(server.calls).toHaveLength(3)
  })

  it('says so when the phone held writes this version cannot read', () => {
    const stored = memoryShelf([entry({ id: 'x', kind: 'a-kind-since-removed' })], 2)
    const { kept, seen } = harness(stored)
    expect(seen.failures).toMatchObject([{
      key: 'outbox-stale',
      message: '3 ältere Änderungen konnten nach einem Update nicht gesendet werden.',
      retry: null,
    }])
    expect(kept.size).toBe(0)
  })

  it('says so for a write this version no longer knows, with nothing else unreadable', () => {
    const { kept, seen } = harness(memoryShelf([entry({ id: 'x', kind: 'a-kind-since-removed' })]))
    expect(seen.failures).toMatchObject([{
      key: 'outbox-stale',
      message: 'Eine ältere Änderung konnte nach einem Update nicht gesendet werden.',
    }])
    expect(kept.size).toBe(0)
  })
})

describe('two tabs of one workout (B6 review)', () => {
  // Each tab restores the same kept writes from the one storage they share.
  const restoredTick = () => memoryShelf([entry({ id: 'a', kind: 'tick', args: [101, true] })])

  it('sends no write another tab has sent: a set un-logged there stays open', async () => {
    const stored = restoredTick()
    const server = new Server()
    const lock = sharedLock()
    const background = harness(stored, { server, exclusive: lock })
    const front = harness(stored, { server, exclusive: lock })
    front.outbox.start()
    await settle()
    void front.outbox.enqueue('tick', [101, false])
    await settle()

    background.outbox.start()
    await settle()
    expect(server.calls.map((c) => c.args)).toEqual([[101, true], [101, false]])
    expect(setOf(server.state, 101)?.completed).toBe(false)
    expect(background.seen.status).toEqual({ state: 'idle', count: 0, setIds: [] })
    // What the other tab did is on the server: this one asks for it.
    expect(background.seen.drained).toBe(1)
  })

  it('lets one tab send at a time, and takes its answer before the other looks', async () => {
    const stored = restoredTick()
    const server = new Server()
    const lock = sharedLock()
    const one = harness(stored, { server, exclusive: lock })
    const other = harness(stored, { server, exclusive: lock })
    const out = gate()
    server.outcomes = [out.closed]
    one.outbox.start()
    other.outbox.start()
    await settle()
    expect(server.calls).toHaveLength(1)

    out.open()
    await settle()
    expect(server.calls).toHaveLength(1)
    expect(other.seen.status.count).toBe(0)
  })

  it('sends a kept write as the phone has it now: another tab named its set', async () => {
    const stored = memoryShelf([entry({ id: 'b', kind: 'tick', args: [-5, true] })])
    const tab = harness(stored)
    stored.kept.set('b', entry({ id: 'b', kind: 'tick', args: [500, true] }))
    tab.outbox.start()
    await settle()
    expect(tab.server.calls.map((c) => c.args)).toEqual([[500, true]])
  })

  it('asks the server which set another tab made, for the writes here about it', async () => {
    const stored = memoryShelf([entry({ id: 'a', kind: 'add', args: [10, 'k1', -5] })])
    const server = new Server()
    const lock = sharedLock()
    const here = harness(stored, { server, exclusive: lock })
    const there = harness(stored, { server, exclusive: lock })
    there.outbox.start()
    await settle()
    // Logged here, on the set as this tab drew it.
    void here.outbox.enqueue('tick', [-5, true])
    await settle()

    expect(server.calls.map((c) => [c.kind, c.args])).toEqual([
      ['add', [10, 'k1', -5]], ['tick', [500, true]]])
    expect(setOf(server.state, 500)?.completed).toBe(true)
    expect(stored.kept.size).toBe(0)
  })

  it('puts back no write another tab has sent when it names a set', async () => {
    const tab = harness()
    const out = gate()
    tab.server.outcomes = [out.closed]
    void tab.outbox.enqueue('add', [10, 'k1', -5])
    void tab.outbox.enqueue('tick', [-5, true])
    await settle()
    tab.kept.delete('w2') // sent by another tab meanwhile
    out.open()
    await settle()

    expect(tab.kept.has('w2')).toBe(false)
    expect(tab.server.calls.map((c) => c.kind)).toEqual(['add'])
  })

  it('asks the server what another tab sent of its own writes', async () => {
    // With no lock to share (plain http), the tabs interleave freely: the
    // screen here never saw the answer to what the other sent for it.
    const stored = memoryShelf()
    const server = new Server()
    const maker = harness(stored, { server })
    const out = gate()
    server.outcomes = [out.closed]
    void maker.outbox.enqueue('tick', [101, true])
    void maker.outbox.enqueue('note', ['Knie'])
    await settle()
    const opened = harness(stored, { server })
    opened.outbox.start()
    await settle()
    out.open()
    await settle()

    expect(server.calls.map((c) => c.kind)).toEqual(['tick', 'tick', 'note'])
    expect(maker.seen.drained).toBe(1)
  })

  it('holds the workout open for the writes another tab keeps', () => {
    // A tab with nothing to send deleted the cookie the other's writes needed.
    const stored = memoryShelf()
    const idle = harness(stored)
    stored.kept.set('x', entry({ id: 'x', at: 4000 }))
    idle.outbox.start()
    expect(idle.seen.hold).toBe(4000)
  })

  it('sends a write the phone could not keep, and holds the workout for it', async () => {
    // Not on the phone is not "sent by another tab".
    const tab = harness(memoryShelf([], 0, true))
    tab.server.outcomes = [offline()]
    void tab.outbox.enqueue('tick', [101, true])
    await settle()
    expect(tab.seen.hold).toBe(FIRST_AT)

    await vi.advanceTimersByTimeAsync(BACKOFF_MS[0]!)
    expect(tab.server.calls).toHaveLength(2)
    expect(tab.seen.status.state).toBe('idle')
  })

  it('finishes only once the writes another tab keeps are in (B6 re-review)', async () => {
    // A tab put away with a set it could not send: finishing in this one
    // went ahead without it, and the set was lost.
    const stored = memoryShelf()
    const server = new Server()
    const lock = sharedLock()
    const front = harness(stored, { server, exclusive: lock, name: 'f' })
    front.outbox.start()
    await settle()
    const away = harness(stored, { server, exclusive: lock, name: 'a' })
    away.outbox.start()
    server.outcomes = [offline()]
    void away.outbox.enqueue('tick', [101, true])
    await settle()
    away.outbox.stop()
    expect(stored.kept.size).toBe(1)

    const drained = front.outbox.flush()
    await settle()
    expect(await drained).toBe(true)
    expect(server.calls.map((c) => c.args)).toEqual([[101, true], [101, true]])
    expect(setOf(server.state, 101)?.completed).toBe(true)
    expect(stored.kept.size).toBe(0)
    // Writes another page made, as restored ones: then the whole screen.
    expect(front.seen.drained).toBe(1)
  })

  it('sends the writes another tab keeps when it has none of its own (B6 re-review)', async () => {
    // The connection back, a tab with nothing to send left the sets a tab
    // put away had kept waiting on the phone.
    const stored = memoryShelf()
    const server = new Server()
    const lock = sharedLock()
    const here = harness(stored, { server, exclusive: lock, name: 'h' })
    here.outbox.start()
    await settle()
    const away = harness(stored, { server, exclusive: lock, name: 'a' })
    away.outbox.start()
    server.outcomes = [offline()]
    void away.outbox.enqueue('tick', [101, true])
    await settle()
    away.outbox.stop()

    here.outbox.kick()
    await settle()
    expect(server.calls.map((c) => c.args)).toEqual([[101, true], [101, true]])
    expect(stored.kept.size).toBe(0)
  })

  it('sends nothing another tab sent while it waited its turn (B6 re-review)', async () => {
    // Taken in from the phone, then sent by the tab that made it before this
    // one's turn came: it went out twice.
    const stored = memoryShelf()
    const server = new Server()
    const lock = sharedLock()
    const there = harness(stored, { server, exclusive: lock, name: 't' })
    const here = harness(stored, { server, exclusive: lock, name: 'h' })
    there.outbox.start()
    here.outbox.start()
    await settle()
    const out = gate()
    server.outcomes = [out.closed]
    void there.outbox.enqueue('tick', [101, true])
    await settle()
    const drained = here.outbox.flush()
    out.open()
    await settle()
    expect(await drained).toBe(true)
    expect(server.calls.map((c) => c.args)).toEqual([[101, true]])
  })

  it('leaves a write of a kind it does not know to the tab that made it (B6 re-review)', async () => {
    // A tab on another build of the page: taken in here, it stuck the queue.
    const tab = harness()
    tab.kept.set('x', entry({ id: 'x', kind: 'fromAnotherBuild', args: [] }))
    let done: boolean | null = null
    void tab.outbox.flush().then((ok) => { done = ok })
    await settle()
    expect(done).toBe(true)
    expect(tab.server.calls).toEqual([])
    expect(tab.kept.has('x')).toBe(true)
  })

  it('shows the writes it takes in from another tab at once (B6 re-review)', async () => {
    const tab = harness()
    tab.server.outcomes = [new MutationFailed('unauthorized')]
    void tab.outbox.enqueue('tick', [101, true])
    await settle()
    expect(tab.seen.status).toMatchObject({ state: 'blocked', count: 1 })
    tab.kept.set('x', entry({ id: 'x' }))
    expect(await tab.outbox.flush()).toBe(false)
    expect(tab.seen.status).toMatchObject({ state: 'blocked', count: 2 })
  })

  it('sends a write another tab made before its own first (B6 re-review)', async () => {
    // In the order the lifter made them: the older log sent after the
    // newer un-log left the set logged.
    const stored = memoryShelf()
    const server = new Server()
    const lock = sharedLock()
    const here = harness(stored, { server, exclusive: lock, name: 'h', now: () => 2000 })
    const there = harness(stored, { server, exclusive: lock, name: 't', now: () => 1000 })
    here.outbox.start()
    there.outbox.start()
    await settle()
    server.outcomes = [offline()]
    void there.outbox.enqueue('tick', [101, true])
    await settle()
    there.outbox.stop()

    void here.outbox.enqueue('tick', [101, false])
    await settle()
    expect(server.calls.map((c) => c.args)).toEqual([[101, true], [101, true], [101, false]])
    expect(setOf(server.state, 101)?.completed).toBe(false)
  })

  it('learns the set another tab made, for a write about it queued later (B6 re-review)', async () => {
    // Nothing here named the drawn set yet when the add was found sent, so
    // the un-log that came after went out with the drawn id -- a 404,
    // dropped as moot, and the set stayed logged.
    const stored = memoryShelf([entry({ id: 'add', kind: 'add', args: [10, 'k1', -5] })])
    const server = new Server()
    const lock = sharedLock()
    const there = harness(stored, { server, exclusive: lock, name: 't' })
    const here = harness(stored, { server, exclusive: lock, name: 'h' })
    there.outbox.start()
    await settle()
    here.outbox.start()
    await settle()

    void here.outbox.enqueue('tick', [-5, false])
    await settle()
    expect(server.calls.at(-1)).toMatchObject({ kind: 'tick', args: [500, false] })
  })

  it('keeps the turn of the write out when it takes in an older one (B6 re-review)', async () => {
    // Put in front of the write in flight, the older one took its place:
    // the answer was not taken as the write's own, and it went out twice.
    const tab = harness()
    const out = gate()
    tab.server.outcomes = [out.closed]
    void tab.outbox.enqueue('note', ['Knie'])
    await settle()
    tab.kept.set('x', entry({ id: 'x', kind: 'tick', args: [101, true] })) // another tab's, older
    const drained = tab.outbox.flush()
    out.open()
    await settle()
    expect(await drained).toBe(true)
    expect(tab.server.calls.map((c) => c.kind)).toEqual(['note', 'tick'])
  })

  it('throws the workout away without waiting for another tab\'s turn (B6 re-review)', async () => {
    // Only waiting for the lock is no request out: the discard waited for
    // as long as the other tab held it.
    const lock = sharedLock()
    let release!: () => void
    void lock(() => new Promise<void>((resolve) => { release = resolve }))
    const { outbox, server } = harness(memoryShelf(), { exclusive: lock })
    void outbox.enqueue('note', ['x']).catch(() => {})
    await settle()
    let cleared = false
    void outbox.clear().then(() => { cleared = true })
    await vi.advanceTimersByTimeAsync(200)
    expect(cleared).toBe(true)

    release()
    await settle()
    expect(server.calls).toEqual([])
  })

  it('sends nothing more once the workout is thrown away, another tab\'s writes neither (B6 third review)', async () => {
    // The answer it waited out pumped again and took in what another tab
    // kept: a set that landed first had the discard refused.
    const tab = harness()
    const out = gate()
    tab.server.outcomes = [out.closed]
    void tab.outbox.enqueue('note', ['x']).catch(() => {})
    await settle()
    tab.kept.set('x', entry({ id: 'x', kind: 'tick', args: [101, true] }))
    let cleared = false
    void tab.outbox.clear().then(() => { cleared = true })
    out.open()
    await vi.advanceTimersByTimeAsync(200)
    expect(cleared).toBe(true)
    expect(tab.server.calls.map((c) => c.kind)).toEqual(['note'])
    expect(tab.kept.has('x')).toBe(true)
  })

  it('sends another tab\'s older write ahead of one only waiting for its turn (B6 third review)', async () => {
    // Waiting for the lock is no write out: filed behind the un-log tapped
    // last, the older log went to the server after it.
    const lock = sharedLock()
    let release!: () => void
    void lock(() => new Promise<void>((resolve) => { release = resolve }))
    const tab = harness(memoryShelf(), { exclusive: lock, now: () => 5000 })
    void tab.outbox.enqueue('tick', [101, false])
    await settle()
    tab.kept.set('x', entry({ id: 'x', kind: 'tick', args: [101, true], order: 1000, at: 1000 }))
    const drained = tab.outbox.flush()
    release()
    await settle()
    expect(await drained).toBe(true)
    expect(tab.server.calls.map((c) => c.args)).toEqual([[101, true], [101, false]])
    expect(setOf(tab.server.state, 101)?.completed).toBe(false)
  })

  it('sends a write another tab made about a set by the name it learnt here (B6 third review)', async () => {
    // Made there while the set was drawn, after it landed from here: sent
    // with the drawn id, it met no set -- a 404, dropped as moot -- and the
    // set stayed logged.
    const stored = memoryShelf()
    const server = new Server()
    const here = harness(stored, { server, name: 'h' })
    here.outbox.start()
    void here.outbox.enqueue('add', [10, 'k1', -5])
    await settle()
    stored.kept.set('t1', entry({ id: 't1', kind: 'tick', args: [-5, false], order: 9_000_000 }))
    here.outbox.kick()
    await settle()
    expect(server.calls.at(-1)).toMatchObject({ kind: 'tick', args: [500, false] })
    expect(setOf(server.state, 500)?.completed).toBe(false)
  })

  it('draws a write it takes in from another tab on the set it names now (B6 third review)', async () => {
    const stored = memoryShelf()
    const server = new Server()
    const here = harness(stored, { server })
    here.outbox.start()
    void here.outbox.enqueue('add', [10, 'k1', -5])
    await settle()
    server.outcomes = [new MutationFailed('unauthorized')]
    void here.outbox.enqueue('note', ['x'])
    await settle()
    stored.kept.set('t1', entry({ id: 't1', kind: 'tick', args: [-5, false], order: 9_000_000 }))

    expect(await here.outbox.flush()).toBe(false)
    expect(setOf(here.seen.shown!, 500)?.completed).toBe(false)
  })

  it('knows the name after a reload too: every tab of the workout keeps it (B6 third review)', async () => {
    const stored = memoryShelf()
    const server = new Server()
    const first = harness(stored, { server })
    first.outbox.start()
    void first.outbox.enqueue('add', [10, 'k1', -5])
    await settle()
    first.outbox.stop()
    expect(stored.names.get(-5)).toBe(500)
    stored.kept.set('t1', entry({ id: 't1', kind: 'tick', args: [-5, false], order: 9_000_000 }))

    const reloaded = harness(stored, { server })
    reloaded.outbox.start()
    await settle()
    expect(server.calls.at(-1)).toMatchObject({ kind: 'tick', args: [500, false] })
  })
})

describe('exclusively', () => {
  afterEach(() => { Reflect.deleteProperty(navigator, 'locks') })
  const lockApi = (request: (name: string, run: () => Promise<void>) => Promise<void>) => {
    Object.defineProperty(navigator, 'locks', { value: { request }, configurable: true })
  }

  it('sends under the workout\'s lock', async () => {
    const names: string[] = []
    lockApi((name, run) => { names.push(name); return run() })
    const run = vi.fn(() => Promise.resolve())
    await exclusively('gym-outbox-7')(run)
    expect(names).toEqual(['gym-outbox-7'])
    expect(run).toHaveBeenCalledOnce()
  })

  it('sends without one where the browser has none, or it cannot be had', async () => {
    const run = vi.fn(() => Promise.resolve())
    await exclusively('gym-outbox-7')(run)
    lockApi(() => Promise.reject(new DOMException('denied', 'SecurityError')))
    await exclusively('gym-outbox-7')(run)
    expect(run).toHaveBeenCalledTimes(2)
  })
})

describe('localShelf', () => {
  it('keeps one key per write, and reads back this workout\'s in the order they were made', () => {
    const shelf = localShelf(7, localStorage)
    shelf.put(entry({ id: 'b', at: 50 }))
    shelf.put(entry({ id: 'a', at: 10 }))
    expect(localStorage.getItem(`gym-outbox:v${OUTBOX_VERSION}:7:a`)).not.toBeNull()
    expect(shelf.read()).toEqual({
      entries: [entry({ id: 'a', at: 10 }), entry({ id: 'b', at: 50 })], stale: 0 })
    shelf.drop('a')
    expect(localStorage.getItem(`gym-outbox:v${OUTBOX_VERSION}:7:a`)).toBeNull()
  })

  it('reads them back in the order they were made, not by the clock (B6 review)', () => {
    const shelf = localShelf(7, localStorage)
    shelf.put(entry({ id: 'relog', order: 20, at: 5 }))
    shelf.put(entry({ id: 'unlog', order: 10, at: 50 }))
    expect(shelf.read().entries.map((e) => e.id)).toEqual(['unlog', 'relog'])
  })

  it('sweeps other workouts\' writes, and counts this one\'s it cannot read', () => {
    localStorage.setItem(`gym-outbox:v${OUTBOX_VERSION}:6:x`, JSON.stringify(entry({})))
    localStorage.setItem('gym-outbox:v0:7:y', '{}')
    localStorage.setItem(`gym-outbox:v${OUTBOX_VERSION}:7:z`, 'not json')
    localStorage.setItem(`gym-outbox:v${OUTBOX_VERSION}:7:w`, JSON.stringify({ ...entry({}), v: 99 }))
    localStorage.setItem(`gym-outbox:v${OUTBOX_VERSION}:7:u`, JSON.stringify({ ...entry({}), order: 'x' }))
    localStorage.setItem('gym-draft:7', 'kept')

    expect(localShelf(7, localStorage).read()).toEqual({ entries: [], stale: 4 })
    expect(Object.keys(localStorage)).toEqual(['gym-draft:7'])
  })

  it('works as a screen with no memory when storage throws', () => {
    const denied = new Proxy({}, { get() { throw new DOMException('denied', 'SecurityError') } })
    const shelf = localShelf(7, denied as Storage)
    expect(shelf.read()).toEqual({ entries: [], stale: 0 })
    expect(shelf.put(entry({}))).toBe(false)
    expect(() => { shelf.drop('e') }).not.toThrow()
    // Cannot say -- which is not "gone".
    expect(shelf.get('e')).toBeUndefined()
    expect(shelf.oldest()).toBeUndefined()
    expect(shelf.list()).toBeUndefined()
  })

  it('lists this workout\'s writes in order and leaves the rest be (B6 re-review)', () => {
    // A tab takes in what another keeps: never another workout's, and it
    // sweeps nothing -- those writes are still the other tab's to send.
    const shelf = localShelf(7, localStorage)
    shelf.put(entry({ id: 'relog', order: 20 }))
    shelf.put(entry({ id: 'unlog', order: 10 }))
    localStorage.setItem(`gym-outbox:v${OUTBOX_VERSION}:6:x`, JSON.stringify(entry({ id: 'x' })))
    localStorage.setItem(`gym-outbox:v${OUTBOX_VERSION}:7:z`, 'not json')
    expect(shelf.list()!.map((e) => e.id)).toEqual(['unlog', 'relog'])
    expect(localStorage.getItem(`gym-outbox:v${OUTBOX_VERSION}:6:x`)).not.toBeNull()
    expect(localStorage.getItem(`gym-outbox:v${OUTBOX_VERSION}:7:z`)).not.toBeNull()
  })

  it('keeps the sets named for the workout, swept with its writes (B6 third review)', () => {
    const shelf = localShelf(7, localStorage)
    expect(shelf.named(-5)).toBeNull()
    shelf.name(-5, 500)
    shelf.name(-6, 501)
    shelf.put(entry({ id: 'a' }))
    expect([shelf.named(-5), shelf.named(-6)]).toEqual([500, 501])
    // No write, and nothing it cannot read.
    expect(shelf.read()).toEqual({ entries: [entry({ id: 'a' })], stale: 0 })
    expect(shelf.list()!.map((e) => e.id)).toEqual(['a'])
    expect(localShelf(7, localStorage).named(-5)).toBe(500)

    localShelf(8, localStorage).read()
    expect(localShelf(7, localStorage).named(-5)).toBeNull()
  })

  it('names afresh over a value it cannot read, and cannot say when storage throws', () => {
    localStorage.setItem(`gym-outbox:v${OUTBOX_VERSION}:7:names`, 'not json')
    const shelf = localShelf(7, localStorage)
    expect(shelf.named(-5)).toBeNull()
    shelf.name(-5, 500)
    expect(shelf.named(-5)).toBe(500)

    const denied = new Proxy({}, { get() { throw new DOMException('denied', 'SecurityError') } })
    const none = localShelf(7, denied as Storage)
    expect(() => { none.name(-5, 500) }).not.toThrow()
    expect(none.named(-5)).toBeUndefined()
  })

  it('says what it has of one write, and when the oldest of the workout\'s was made', () => {
    const shelf = localShelf(7, localStorage)
    expect(shelf.oldest()).toBeNull()
    expect(shelf.put(entry({ id: 'b', at: 50 }))).toBe(true)
    shelf.put(entry({ id: 'a', at: 10 }))
    localStorage.setItem(`gym-outbox:v${OUTBOX_VERSION}:6:x`, JSON.stringify(entry({ at: 1 })))
    expect(shelf.get('b')).toEqual(entry({ id: 'b', at: 50 }))
    expect(shelf.get('c')).toBeNull()
    expect(shelf.oldest()).toBe(10)
  })
})

describe('writeHold', () => {
  it('names the workout and its oldest write, and ends the hold when nothing is held', () => {
    const cookies: string[] = []
    const set = vi.spyOn(Document.prototype, 'cookie', 'set')
      .mockImplementation((value: string) => { cookies.push(value) })
    writeHold(7, 1234.4)
    writeHold(7, null)
    set.mockRestore()
    expect(cookies[0]).toBe('gym_outbox=7:1234; Path=/gym; Max-Age=604800; SameSite=Lax')
    expect(cookies[1]).toBe('gym_outbox=; Path=/gym; Max-Age=0; SameSite=Lax')
  })
})

describe('newId', () => {
  const UUID = /^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/

  it('is a key the server takes (SessionSet.client_key)', () => {
    expect(newId()).toMatch(UUID)
  })

  it('makes one without randomUUID, which a phone on plain http lacks', () => {
    const getRandomValues = crypto.getRandomValues.bind(crypto)
    vi.stubGlobal('crypto', { getRandomValues })
    try {
      const ids = new Set(Array.from({ length: 50 }, newId))
      expect(ids.size).toBe(50)
      for (const id of ids) expect(id).toMatch(UUID)
    } finally {
      vi.unstubAllGlobals()
    }
  })
})
