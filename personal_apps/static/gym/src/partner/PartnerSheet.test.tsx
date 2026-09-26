import { act, render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import {
  ASK_GUARD_MS, MitPartner, PartnerSheet, type PartnerFootActions, type PartnerTarget,
} from './PartnerSheet'
import { PARTNER_SHEET } from './PartnerLine'
import { useSheets } from '../session/stores'
import type { FootOutcome } from '../session/usePartnerSync'
import type { PartnerLink, PartnerList, PartnerListRow } from './types'
import { FOOT_FAILED } from './words'

/* The partner's list (D14, M5): read-only, loaded when the sheet opens,
 * fetched again whenever the line it was opened from moves. */

function link(over: Partial<PartnerLink> = {}): PartnerLink {
  return {
    id: 7, username: 'jglaser', viewer_leads: true, state: 'joined',
    since: '2026-09-25T09:26:00', finished_at: null,
    exercise: 'Rudern', set_no: 2, done_in_exercise: 1, sets_in_exercise: 3,
    last_set: { weight: 60, reps: 8 }, rest_left: null, sets_done: 4, sets_total: 12, list_key: 1,
    ...over,
  }
}

/** A row; its ticked count is its lifted sets unless said otherwise. */
function row(over: Partial<PartnerListRow> & Pick<PartnerListRow, 'id' | 'name' | 'state'>) {
  return {
    picture: null, sets: [], open: 0, set_no: null, done: over.sets?.length ?? 0, ...over,
  } satisfies PartnerListRow
}

function list(over: Partial<PartnerList> = {}): PartnerList {
  return {
    id: 7, username: 'jglaser', viewer_leads: true, link_live: true,
    since: '2026-09-25T09:26:00', started_at: '2026-09-25T09:20:00', finished_at: null,
    sets_done: 4, sets_total: 12, rest_left: null,
    rows: [
      row({ id: 1, name: 'Bankdrücken', state: 'done',
        sets: [{ weight: 60, reps: 8 }, { weight: 60, reps: 7 }, { weight: 62.5, reps: 6 }] }),
      // On set 3 of 4 after one lifted set: a tick without reps sits between.
      row({ id: 2, name: 'Rudern', state: 'now', sets: [{ weight: 60, reps: 8 }], done: 2,
        open: 2, set_no: 3 }),
      row({ id: 3, name: 'Schulterdrücken', state: 'open', open: 3 }),
      row({ id: 4, name: 'Dips', state: 'skipped' }),
    ],
    ...over,
  }
}

/** fetch, answering the list endpoint with whatever `answer` holds now. */
function server(answer: () => PartnerList | number) {
  return vi.fn(async (url: string) => {
    const body = answer()
    if (!String(url).endsWith('/gym/shared/7/list.json')) return new Response('{}', { status: 404 })
    return typeof body === 'number'
      ? new Response('{}', { status: body })
      : new Response(JSON.stringify(body), { headers: { 'Content-Type': 'application/json' } })
  })
}

function mount(target: PartnerTarget | null, dated = false) {
  const result = render(<PartnerSheet target={target} dated={dated} />)
  const open = () => act(() => { useSheets.getState().open(PARTNER_SHEET) })
  return { ...result, open }
}

const sheet = () => document.getElementById(PARTNER_SHEET)!
const rows = () => [...sheet().querySelectorAll('.psheet__row')] as HTMLElement[]

beforeEach(() => {
  useSheets.setState(useSheets.getInitialState(), true)
})
afterEach(() => { vi.unstubAllGlobals() })

describe('PartnerSheet', () => {
  it('names the partner beside their tile, as the dialog', () => {
    vi.stubGlobal('fetch', server(() => list()))
    const { open } = mount({ id: 7, username: 'jglaser', line: link() })
    open()
    expect(screen.getByRole('dialog', { name: 'jglaser' })).toBeInTheDocument()
    expect(sheet().querySelector('.sheet__who .partner__tile')).toHaveTextContent('J')
  })

  it('loads the list only when it opens', async () => {
    const fetchMock = server(() => list())
    vi.stubGlobal('fetch', fetchMock)
    const { open } = mount({ id: 7, username: 'jglaser', line: link() })
    expect(fetchMock).not.toHaveBeenCalled()
    open()
    expect(sheet()).toHaveTextContent('Lädt …')
    await waitFor(() => { expect(rows()).toHaveLength(4) })
    expect(fetchMock).toHaveBeenCalledTimes(1)
    expect(String(fetchMock.mock.calls[0]![0])).toBe('/gym/shared/7/list.json')
  })

  it('lists their workout in the queue grammar: done, now, open, not done', async () => {
    vi.stubGlobal('fetch', server(() => list()))
    const { open } = mount({ id: 7, username: 'jglaser', line: link() })
    open()
    await waitFor(() => { expect(rows()).toHaveLength(4) })
    const [done, now, ahead, skipped] = rows() as [HTMLElement, HTMLElement, HTMLElement, HTMLElement]
    expect(sheet().querySelector('.psheet__meta'))
      .toHaveTextContent('Zusammen seit 11:26 · 4 von 12 Sätzen')

    expect(done).toHaveClass('is-done')
    expect(done.querySelector('.queue__mark')).not.toBeNull()
    expect(done.querySelector('.row__meta')).toHaveTextContent('60,0 × 8 · 7 · 62,5 × 6')
    expect(done.querySelector('.row__trail')).toHaveTextContent('3/3')

    // Where they are: named for assistive tech too, never the live wash.
    expect(now).toHaveClass('is-cur')
    expect(now).toHaveAttribute('aria-current', 'step')
    // The set the line names too, and the count their own queue gives --
    // not the lifted ones plus one, beside "1/3".
    expect(now.querySelector('.row__meta')).toHaveTextContent('60,0 × 8 · jetzt Satz 3')
    expect(within(now.querySelector('.row__trail')!).getByText('2/4'))
      .toHaveAttribute('aria-hidden', 'true')
    expect(within(now.querySelector('.row__trail')!).getByText('2 von 4 Sätzen'))
      .toHaveClass('sr-only')

    // Not started: its count, never the weights planned for it (Michi).
    expect(ahead).toHaveClass('is-open')
    expect(ahead.querySelector('.row__meta')).toBeNull()
    expect(ahead.querySelector('.row__trail')).toHaveTextContent('0/3')

    expect(skipped).toHaveClass('is-skipped')
    expect(within(skipped.querySelector('.row__trail')!).getByText('–'))
      .toHaveAttribute('aria-hidden', 'true')
    expect(within(skipped).getByText('nicht gemacht')).toHaveClass('sr-only')

    expect(sheet().querySelector('.psheet__end'))
      .toHaveTextContent('Nur zum Ansehen: eintragen kann nur jglaser. jglaser folgt deiner Reihenfolge.')
    // Read-only: nothing in the list is a control.
    expect(within(sheet().querySelector('.psheet__list')! as HTMLElement)
      .queryAllByRole('button')).toHaveLength(0)
  })

  it('says a rest on the row they are at', async () => {
    vi.stubGlobal('fetch', server(() => list({ rest_left: 75 })))
    const { open } = mount({ id: 7, username: 'jglaser', line: link({ rest_left: 75 }) })
    open()
    await waitFor(() => { expect(rows()).toHaveLength(4) })
    expect(rows()[1]!.querySelector('.row__meta')).toHaveTextContent('60,0 × 8 · Pause')
  })

  it('says a row skipped after a set as their own queue does', async () => {
    // "–" and "nicht gemacht" hid a set they did; "1/1" called the row whole.
    vi.stubGlobal('fetch', server(() => list({ rows: [
      row({ id: 5, name: 'Curls', state: 'skipped', sets: [{ weight: 12, reps: 15 }] }),
    ] })))
    const { open } = mount({ id: 7, username: 'jglaser', line: link() })
    open()
    await waitFor(() => { expect(rows()).toHaveLength(1) })
    const [curls] = rows() as [HTMLElement]
    expect(curls).toHaveClass('is-skipped')
    expect(curls.querySelector('.queue__mark')).not.toBeNull()
    expect(curls.querySelector('.row__meta')).toHaveTextContent('12,0 × 15 · Rest übersprungen')
    const trail = within(curls.querySelector('.row__trail')!)
    expect(trail.getByText('1 Satz', { selector: '[aria-hidden]' })).toBeInTheDocument()
    expect(trail.getByText('1 Satz', { selector: '.sr-only' })).toBeInTheDocument()
  })

  it('tells a follower whose order it is', async () => {
    vi.stubGlobal('fetch', server(() => list({ viewer_leads: false })))
    const { open } = mount({ id: 7, username: 'jglaser', line: link({ viewer_leads: false }) })
    open()
    await waitFor(() => { expect(rows()).toHaveLength(4) })
    expect(sheet().querySelector('.psheet__end')).toHaveTextContent(
      'Nur zum Ansehen: eintragen kann nur jglaser. Die Reihenfolge gibt jglaser vor, '
      + 'solange ihr zusammen trainiert.')
  })

  it('keeps showing a partner who trains on after the link ended', async () => {
    vi.stubGlobal('fetch', server(() => list({ link_live: false })))
    const { open } = mount({ id: 7, username: 'jglaser' })
    open()
    await waitFor(() => { expect(rows()).toHaveLength(4) })
    expect(sheet().querySelector('.psheet__meta')).toHaveTextContent('Trainiert noch · 4 von 12 Sätzen')
    expect(sheet().querySelector('.psheet__end'))
      .toHaveTextContent(/^Nur zum Ansehen: eintragen kann nur jglaser\.$/)
  })

  it('shows a finished list as it ended, with its day when opened from the past', async () => {
    // As the server leaves one: the finish took the open sets.
    const finished = list({
      finished_at: '2026-09-25T10:10:00', sets_done: 4, sets_total: 6, link_live: false,
      rows: [
        row({ id: 1, name: 'Bankdrücken', state: 'done',
          sets: [{ weight: 60, reps: 8 }, { weight: 60, reps: 7 }, { weight: 62.5, reps: 6 }] }),
        row({ id: 2, name: 'Rudern', state: 'done', sets: [{ weight: 60, reps: 8 }] }),
        row({ id: 4, name: 'Dips', state: 'skipped' }),
      ],
    })
    vi.stubGlobal('fetch', server(() => finished))
    const { open, rerender } = mount({ id: 7, username: 'jglaser' }, true)
    open()
    await waitFor(() => { expect(rows()).toHaveLength(3) })
    expect(sheet().querySelector('.psheet__meta'))
      .toHaveTextContent(/^Fr 25\.09\.\S* · fertig um 12:10 · 4 von 6 Sätzen$/)
    expect(sheet().querySelector('.psheet__end'))
      .toHaveTextContent('So hat jglaser das Workout beendet. Nur zum Ansehen.')
    // Cut short, the rows count what was lifted: "1/1" under "4 von 6"
    // called Rudern whole.
    expect(rows().map((r) => r.querySelector('.row__trail [aria-hidden="true"]')!.textContent))
      .toEqual(['3', '1', '–'])
    expect(within(rows()[1]!).getByText('1 Satz')).toHaveClass('sr-only')

    rerender(<PartnerSheet target={{ id: 7, username: 'jglaser' }} />)
    expect(sheet().querySelector('.psheet__meta'))
      .toHaveTextContent('Fertig um 12:10 · 4 von 6 Sätzen')
  })

  it('keeps "3/3" on a list finished in full', async () => {
    vi.stubGlobal('fetch', server(() => list({
      finished_at: '2026-09-25T10:10:00', sets_done: 3, sets_total: 3, link_live: false,
      rows: [row({ id: 1, name: 'Bankdrücken', state: 'done',
        sets: [{ weight: 60, reps: 8 }, { weight: 60, reps: 7 }, { weight: 62.5, reps: 6 }] })],
    })))
    const { open } = mount({ id: 7, username: 'jglaser' }, true)
    open()
    await waitFor(() => { expect(rows()).toHaveLength(1) })
    expect(rows()[0]!.querySelector('.row__trail')).toHaveTextContent('3/3')
    expect(within(rows()[0]!).getByText('3 von 3 Sätzen')).toHaveClass('sr-only')
  })

  it('shows an invite from its line alone, with no fetch', () => {
    const fetchMock = server(() => list())
    vi.stubGlobal('fetch', fetchMock)
    const { open } = mount({
      id: 7, username: 'jglaser', line: link({ state: 'invited', exercise: null, last_set: null }),
    })
    open()
    expect(sheet()).toHaveTextContent('Eingeladen um 11:26 · noch keine Antwort')
    expect(sheet()).toHaveTextContent(
      'Sobald jglaser dabei ist, stehen hier die Übungen und Sätze, in deiner Reihenfolge.')
    expect(fetchMock).not.toHaveBeenCalled()
  })

  it('turns an open invite into its no, still asking the server nothing', () => {
    // It asked for a list nobody has, and said it could not be loaded.
    const fetchMock = server(() => 404)
    vi.stubGlobal('fetch', fetchMock)
    const invite = { exercise: null, last_set: null }
    const { open, rerender } = mount({
      id: 7, username: 'jglaser', line: link({ state: 'invited', ...invite }),
    })
    open()
    rerender(<PartnerSheet target={{
      id: 7, username: 'jglaser',
      line: link({ state: 'declined', since: '2026-09-25T09:30:00', ...invite }),
    }} />)
    expect(sheet().querySelector('.psheet__meta')).toHaveTextContent('Abgelehnt um 11:30')
    // Not "allein": a second partner may be in.
    expect(sheet().querySelector('.sheet__note')).toHaveTextContent('jglaser trainiert nicht mit.')
    expect(fetchMock).not.toHaveBeenCalled()
  })

  it('fetches again when the line moves, keeping the list shown until then', async () => {
    let answer = list()
    const fetchMock = server(() => answer)
    vi.stubGlobal('fetch', fetchMock)
    const { open, rerender } = mount({ id: 7, username: 'jglaser', line: link() })
    open()
    await waitFor(() => { expect(rows()).toHaveLength(4) })

    // The same line, answered again by a poll: nothing to fetch.
    rerender(<PartnerSheet target={{ id: 7, username: 'jglaser', line: link() }} />)
    expect(fetchMock).toHaveBeenCalledTimes(1)

    answer = list({ sets_done: 5 })
    rerender(<PartnerSheet target={{
      id: 7, username: 'jglaser',
      line: link({ sets_done: 5, set_no: 3, done_in_exercise: 2, list_key: 2 }),
    }} />)
    expect(sheet()).not.toHaveTextContent('Lädt …')
    expect(rows()).toHaveLength(4)
    await waitFor(() => {
      expect(sheet().querySelector('.psheet__meta')).toHaveTextContent('5 von 12 Sätzen')
    })
    expect(fetchMock).toHaveBeenCalledTimes(2)
  })

  it('fetches again when the list moves anywhere, and for a rest -- not its seconds', async () => {
    const fetchMock = server(() => list())
    vi.stubGlobal('fetch', fetchMock)
    const { open, rerender } = mount({ id: 7, username: 'jglaser', line: link() })
    open()
    await waitFor(() => { expect(rows()).toHaveLength(4) })
    const show = (over: Partial<PartnerLink>) => rerender(
      <PartnerSheet target={{ id: 7, username: 'jglaser', line: link(over) }} />)

    // Under the same set: a row further down swapped (only the list's key
    // says so), then a rest begun.
    show({ list_key: 2 })
    await waitFor(() => { expect(fetchMock).toHaveBeenCalledTimes(2) })
    show({ list_key: 2, rest_left: 90 })
    await waitFor(() => { expect(fetchMock).toHaveBeenCalledTimes(3) })
    // A rest's seconds move with every poll: the list counts them itself.
    show({ list_key: 2, rest_left: 80 })
    expect(fetchMock).toHaveBeenCalledTimes(3)
  })

  it('says when the list could not be loaded', async () => {
    vi.stubGlobal('fetch', server(() => 500))
    const { open } = mount({ id: 7, username: 'jglaser', line: link() })
    open()
    await waitFor(() => {
      expect(sheet()).toHaveTextContent('Die Liste ließ sich nicht laden.')
    })
  })
})

describe('PartnerSheet: ending it at the foot (B11)', () => {
  const DONE: FootOutcome = { done: true }
  const invite = { state: 'invited' as const, exercise: null, last_set: null }

  function actions(over: Partial<PartnerFootActions> = {}) {
    return {
      withdraw: vi.fn(async (_id: number) => DONE),
      end: vi.fn(async (_id: number) => DONE),
      ...over,
    }
  }

  function mountWith(target: PartnerTarget, acts: PartnerFootActions) {
    const result = render(<PartnerSheet target={target} actions={acts} />)
    act(() => { useSheets.getState().open(PARTNER_SHEET) })
    return result
  }

  const foot = () => sheet().querySelector<HTMLButtonElement>('.psheet__act')
  const isOpen = () => useSheets.getState().openId === PARTNER_SHEET

  // The clock alone, still unless moved on: a second tap sooner than
  // ASK_GUARD_MS after the one that asked is that one's bounce.
  beforeEach(() => { vi.useFakeTimers({ toFake: ['Date'] }) })
  afterEach(() => { vi.useRealTimers() })
  const later = () => { vi.advanceTimersByTime(ASK_GUARD_MS) }

  it('takes an invite back at one tap, and closes', async () => {
    const user = userEvent.setup()
    vi.stubGlobal('fetch', server(() => list()))
    const acts = actions()
    mountWith({ id: 7, username: 'jglaser', line: link(invite) }, acts)
    expect(foot()).toHaveClass('sheet-row', 'sheet-row--danger')
    expect(foot()!.querySelector('.sheet-row__name')).toHaveTextContent('Einladung zurückziehen')
    expect(foot()!.querySelector('.sheet-row__meta'))
      .toHaveTextContent('jglaser kann dann nicht mehr beitreten.')
    expect(foot()!.querySelector('.sheet-row__lead .icon-leave')).not.toBeNull()

    await user.click(foot()!)
    expect(acts.withdraw).toHaveBeenCalledTimes(1)
    expect(acts.withdraw).toHaveBeenCalledWith(7)
    expect(acts.end).not.toHaveBeenCalled()
    await waitFor(() => { expect(isOpen()).toBe(false) })
  })

  it('lets the leader end it at the second tap: the first asks, on the same row', async () => {
    const user = userEvent.setup()
    vi.stubGlobal('fetch', server(() => list()))
    const acts = actions()
    mountWith({ id: 7, username: 'jglaser', line: link() }, acts)
    await waitFor(() => { expect(rows()).toHaveLength(4) })
    // Under the note, at the sheet's end.
    expect(sheet().querySelector('.psheet__end .sheet__note + .psheet__act')).toBe(foot())
    expect(foot()!.querySelector('.sheet-row__name'))
      .toHaveTextContent('Gemeinsames Training beenden')
    expect(foot()!.querySelector('.sheet-row__meta'))
      .toHaveTextContent('jglaser trainiert allein weiter.')

    await user.click(foot()!)
    expect(acts.end).not.toHaveBeenCalled()
    expect(foot()!.querySelector('.sheet-row__meta')).toHaveTextContent('Wirklich beenden?')
    expect(foot()).toHaveClass('is-armed')
    expect(isOpen()).toBe(true)

    later()
    await user.click(foot()!)
    expect(acts.end).toHaveBeenCalledTimes(1)
    expect(acts.end).toHaveBeenCalledWith(7)
    expect(acts.withdraw).not.toHaveBeenCalled()
    await waitFor(() => { expect(isOpen()).toBe(false) })
  })

  it('lets the follower leave at the second tap', async () => {
    const user = userEvent.setup()
    vi.stubGlobal('fetch', server(() => list({ viewer_leads: false })))
    const acts = actions()
    mountWith({ id: 7, username: 'jglaser', line: link({ viewer_leads: false }) }, acts)
    expect(foot()!.querySelector('.sheet-row__name')).toHaveTextContent('Nicht mehr mitmachen')
    expect(foot()!.querySelector('.sheet-row__meta'))
      .toHaveTextContent('Dein Workout läuft weiter, die Reihenfolge bestimmst dann du.')
    await user.click(foot()!)
    expect(foot()!.querySelector('.sheet-row__meta'))
      .toHaveTextContent('Wirklich nicht mehr mitmachen?')
    // Over a hidden copy of the two-line meta, which holds the row at its
    // height: the one-line ask must not pull it down from under the thumb.
    expect(foot()!.querySelector('.psheet__say')).toHaveAttribute('data-room',
      'Dein Workout läuft weiter, die Reihenfolge bestimmst dann du.')
    expect(acts.end).not.toHaveBeenCalled()
    later()
    await user.click(foot()!)
    expect(acts.end).toHaveBeenCalledWith(7)
  })

  it("does not take the asking tap's bounce for the answer", async () => {
    // Ended, the two cannot be invited to this workout again.
    const user = userEvent.setup()
    vi.stubGlobal('fetch', server(() => list()))
    const acts = actions()
    mountWith({ id: 7, username: 'jglaser', line: link() }, acts)
    await user.click(foot()!)
    vi.advanceTimersByTime(ASK_GUARD_MS - 1)
    await user.click(foot()!)
    expect(acts.end).not.toHaveBeenCalled()
    expect(foot()).toHaveClass('is-armed')
    vi.advanceTimersByTime(1)
    await user.click(foot()!)
    expect(acts.end).toHaveBeenCalledTimes(1)
  })

  it('keeps asking when the list arrives between the two taps', async () => {
    const user = userEvent.setup()
    let deliver!: () => void
    vi.stubGlobal('fetch', vi.fn(() => new Promise<Response>((resolve) => {
      deliver = () => resolve(new Response(JSON.stringify(list()),
        { headers: { 'Content-Type': 'application/json' } }))
    })))
    const acts = actions()
    mountWith({ id: 7, username: 'jglaser', line: link() }, acts)
    expect(sheet()).toHaveTextContent('Lädt …')
    await user.click(foot()!)
    expect(foot()).toHaveClass('is-armed')
    await act(async () => { deliver() })
    await waitFor(() => { expect(rows()).toHaveLength(4) })
    expect(foot()).toHaveClass('is-armed')
    later()
    await user.click(foot()!)
    expect(acts.end).toHaveBeenCalledTimes(1)
  })

  it('asks again on the next visit to the sheet', async () => {
    const user = userEvent.setup()
    vi.stubGlobal('fetch', server(() => list()))
    const acts = actions()
    mountWith({ id: 7, username: 'jglaser', line: link() }, acts)
    await user.click(foot()!)
    expect(foot()).toHaveClass('is-armed')
    act(() => { useSheets.getState().close() })
    act(() => { useSheets.getState().open(PARTNER_SHEET) })
    expect(foot()).not.toHaveClass('is-armed')
    expect(foot()!.querySelector('.sheet-row__meta'))
      .toHaveTextContent('jglaser trainiert allein weiter.')
    await user.click(foot()!)
    expect(acts.end).not.toHaveBeenCalled()
  })

  it('does nothing more while the request is on its way', async () => {
    const user = userEvent.setup()
    vi.stubGlobal('fetch', server(() => list()))
    let answer!: (outcome: FootOutcome) => void
    const acts = actions({
      end: vi.fn(() => new Promise<FootOutcome>((resolve) => { answer = resolve })),
    })
    mountWith({ id: 7, username: 'jglaser', line: link() }, acts)
    await user.click(foot()!)
    later()
    await user.click(foot()!)
    expect(foot()).toHaveAttribute('aria-disabled', 'true')
    expect(foot()).toHaveClass('is-busy')
    await user.click(foot()!)
    expect(acts.end).toHaveBeenCalledTimes(1)
    // Not `disabled`: the focus stays on the row, inside the sheet.
    expect(foot()).not.toBeDisabled()
    await act(async () => { answer(DONE) })
    await waitFor(() => { expect(isOpen()).toBe(false) })
  })

  it('says a request that did not get through, and sends it again at the next tap', async () => {
    const user = userEvent.setup()
    vi.stubGlobal('fetch', server(() => list()))
    const acts = actions({
      end: vi.fn<(id: number) => Promise<FootOutcome>>()
        .mockResolvedValueOnce({ done: false, message: FOOT_FAILED })
        .mockResolvedValueOnce(DONE),
    })
    mountWith({ id: 7, username: 'jglaser', line: link() }, acts)
    await user.click(foot()!)
    later()
    await user.click(foot()!)
    await waitFor(() => {
      expect(foot()!.querySelector('.sheet-row__meta'))
        .toHaveTextContent('Ging nicht durch — nochmal tippen.')
    })
    expect(foot()).not.toHaveAttribute('aria-disabled')
    expect(isOpen()).toBe(true)
    await user.click(foot()!)
    expect(acts.end).toHaveBeenCalledTimes(2)
    await waitFor(() => { expect(isOpen()).toBe(false) })
  })

  it('starts over when the line changes under it', async () => {
    const user = userEvent.setup()
    vi.stubGlobal('fetch', server(() => list()))
    const acts = actions({
      withdraw: vi.fn(async (_id: number): Promise<FootOutcome> => (
        { done: false, message: FOOT_FAILED })),
    })
    const target = (over: Partial<PartnerLink> = {}): PartnerTarget => (
      { id: 7, username: 'jglaser', line: link({ ...invite, ...over }) })
    const { rerender } = mountWith(target(), acts)
    await user.click(foot()!)
    await waitFor(() => {
      expect(foot()!.querySelector('.sheet-row__meta')).toHaveTextContent(FOOT_FAILED)
    })
    // They said no meanwhile, and were asked again from the other phone:
    // the same row, an invite again, with nothing failed about it.
    rerender(<PartnerSheet target={target({ state: 'declined' })} actions={acts} />)
    expect(foot()).toBeNull()
    rerender(<PartnerSheet target={target()} actions={acts} />)
    expect(foot()!.querySelector('.sheet-row__meta'))
      .toHaveTextContent('jglaser kann dann nicht mehr beitreten.')
    expect(foot()).not.toHaveClass('is-armed')
  })

  it('leaves the screen alone when the answer comes after the sheet was closed', async () => {
    const user = userEvent.setup()
    vi.stubGlobal('fetch', server(() => list()))
    let answer!: (outcome: FootOutcome) => void
    const acts = actions({
      end: vi.fn(() => new Promise<FootOutcome>((resolve) => { answer = resolve })),
    })
    mountWith({ id: 7, username: 'jglaser', line: link() }, acts)
    await user.click(foot()!)
    later()
    await user.click(foot()!)
    expect(acts.end).toHaveBeenCalledTimes(1)
    // Closed while it was on its way, and another sheet open since.
    act(() => { useSheets.getState().open('sheet-menu') })
    await act(async () => { answer(DONE) })
    expect(useSheets.getState().openId).toBe('sheet-menu')
  })

  it('offers the way out even when the list would not load', async () => {
    vi.stubGlobal('fetch', server(() => 500))
    mountWith({ id: 7, username: 'jglaser', line: link() }, actions())
    await waitFor(() => {
      expect(sheet()).toHaveTextContent('Die Liste ließ sich nicht laden.')
    })
    expect(foot()!.querySelector('.sheet-row__name'))
      .toHaveTextContent('Gemeinsames Training beenden')
  })

  it('offers nothing once it ended, finished or vanished, for a no, or away from the live screen',
    async () => {
      vi.stubGlobal('fetch', server(() => list({ link_live: false })))
      const { rerender } = mountWith({ id: 7, username: 'jglaser', line: link() }, actions())
      expect(foot()).not.toBeNull()
      const acts = actions()
      for (const over of [
        { state: 'ended' as const }, { state: 'finished' as const },
        { state: 'declined' as const, exercise: null, last_set: null },
      ]) {
        rerender(<PartnerSheet target={{ id: 7, username: 'jglaser', line: link(over) }}
          actions={acts} />)
        expect(foot()).toBeNull()
      }
      rerender(<PartnerSheet target={{
        id: 7, username: 'jglaser', line: { ...link(), state: 'vanished' },
      }} actions={acts} />)
      expect(foot()).toBeNull()
      // The debrief's and Verlauf's sheets: no line, no actions.
      rerender(<PartnerSheet target={{ id: 7, username: 'jglaser' }} actions={acts} />)
      expect(foot()).toBeNull()
      rerender(<PartnerSheet target={{ id: 7, username: 'jglaser', line: link() }} />)
      expect(foot()).toBeNull()
    })
})

describe('MitPartner', () => {
  it('names whom the workout was done with, and opens their list', async () => {
    const user = userEvent.setup()
    const onOpen = vi.fn()
    const partner = { id: 7, username: 'jglaser' }
    const { container } = render(<MitPartner partner={partner} onOpen={onOpen} />)
    expect(container.querySelector('.mit__txt')).toHaveTextContent('mit jglaser')
    const button = screen.getByRole('button', { name: 'Zusammen mit jglaser. Liste von jglaser ansehen' })
    expect(button).toHaveAttribute('aria-controls', PARTNER_SHEET)
    await user.click(button)
    expect(onOpen).toHaveBeenCalledWith(partner)
  })
})
