import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { act, render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, describe, expect, it, vi } from 'vitest'

import { Analysis } from './Analysis'
import type { AnalysisRoute } from './Analysis'
import * as api from './analysisApi'
import { AnalysisUnavailable } from './analysisApi'
import { analysis, chatterDay, priceDay, resolved, sourceDay } from './analysisFixtures'
import { resolveKey } from './analysisQueries'
import type { AnalysisPayload, ResolvePayload } from './analysisTypes'

const NOW = () => new Date('2026-09-14T12:30:00Z')
const PINNED: AnalysisRoute = { page: 'analysis', ticker: 'AAA', companyId: 11, instrumentId: 7 }
const DEFAULT_WINDOW = { from: '2026-09-07', to: '2026-09-13' }

const newClient = () => new QueryClient({ defaultOptions: { queries: { retry: false } } })

/** A mapping from earlier: same symbol, different IDs. */
const staleMapping = () => resolved({
  company: { id: 99, ticker: 'AAA', name: 'Aaa Corp', first_seen: '2026-01-01T00:00:00Z' },
  instrument: { ...resolved().instrument, id: 98 },
})

function mount(route: AnalysisRoute, over: Partial<Parameters<typeof Analysis>[0]> = {},
               client = newClient()) {
  const onNavigate = vi.fn()
  const onSearch = vi.fn()
  const onSessionExpired = vi.fn()
  const tree = (current: AnalysisRoute) => (
    <QueryClientProvider client={client}>
      <Analysis route={current} rawRange={null} onNavigate={onNavigate} onSearch={onSearch}
                onSessionExpired={onSessionExpired} now={NOW} {...over} />
    </QueryClientProvider>
  )
  const view = render(tree(route))
  return { client, view, onNavigate, onSearch, onSessionExpired,
           rerender: (next: AnalysisRoute) => view.rerender(tree(next)) }
}

afterEach(() => vi.restoreAllMocks())

describe('choosing and resolving a company (C02/C12/C15)', () => {
  it('asks for a company when none is chosen, without fetching, and still names the scope', () => {
    const resolve = vi.spyOn(api, 'fetchAnalysisResolve')
    const read = vi.spyOn(api, 'fetchAnalysis')
    const { onSearch, view } = mount({ page: 'analysis' })
    expect(screen.getByRole('heading', { level: 1 })).toHaveTextContent('Explore')
    expect(screen.getByText(/Retrospective/)).toBeInTheDocument()
    expect(view.container.querySelector('.rh-an-scope')).toHaveTextContent('US primary · USD')
    screen.getByRole('button', { name: 'Find a company' }).click()
    expect(onSearch).toHaveBeenCalled()
    expect(resolve).not.toHaveBeenCalled()
    expect(read).not.toHaveBeenCalled()
  })

  it('resolves a ticker link and REPLACES it with the pinned canonical link and the default window', async () => {
    vi.spyOn(api, 'fetchAnalysisResolve').mockResolvedValue(resolved())
    const read = vi.spyOn(api, 'fetchAnalysis')
    const { onNavigate } = mount({ page: 'analysis', ticker: 'AAA' })
    expect(screen.getByText(/Resolving AAA/)).toBeInTheDocument()
    await waitFor(() => expect(onNavigate).toHaveBeenCalled())
    expect(onNavigate).toHaveBeenCalledWith(PINNED, DEFAULT_WINDOW, { replace: true })
    expect(read).not.toHaveBeenCalled()
  })

  it('carries a malformed address window through resolution unchanged and fetches nothing (P2-2)', async () => {
    vi.spyOn(api, 'fetchAnalysisResolve').mockResolvedValue(resolved())
    const read = vi.spyOn(api, 'fetchAnalysis')
    const { onNavigate } = mount({ page: 'analysis', ticker: 'AAA' },
                                 { rawRange: { from: '2026-13-07', to: '2026-09-13' } })
    await waitFor(() => expect(onNavigate).toHaveBeenCalled())
    // The raw strings, never the default a guessed range would be.
    expect(onNavigate).toHaveBeenCalledWith(PINNED, { from: '2026-13-07', to: '2026-09-13' },
                                            { replace: true })
    expect(onNavigate).not.toHaveBeenCalledWith(PINNED, DEFAULT_WINDOW, expect.anything())
    expect(read).not.toHaveBeenCalled()
  })

  it('refuses to pin a resolution for a different symbol', async () => {
    vi.spyOn(api, 'fetchAnalysisResolve').mockResolvedValue(
      resolved({ company: { id: 5, ticker: 'BBB', name: 'Other', first_seen: '2026-01-01T00:00:00Z' } }))
    const { onNavigate } = mount({ page: 'analysis', ticker: 'AAA' })
    await screen.findByText(/answered for a different symbol/)
    expect(onNavigate).not.toHaveBeenCalled()
  })

  it.each([
    ['missing', 'unknown_company', /No current company or instrument for AAA/],
    ['unsupported', 'ineligible_instrument', /no native-USD US primary/],
    ['conflict', 'ambiguous_primary', /no longer matches/],
  ] as const)('says why a %s resolution failed and offers search', async (reason, code, text) => {
    vi.spyOn(api, 'fetchAnalysisResolve').mockRejectedValue(new AnalysisUnavailable(reason, code, 'said so'))
    const { onSearch } = mount({ page: 'analysis', ticker: 'AAA' })
    await screen.findByText(text)
    expect(screen.getByText(new RegExp(code))).toBeInTheDocument()
    await userEvent.click(screen.getByRole('button', { name: 'Find a company' }))
    expect(onSearch).toHaveBeenCalled()
  })
})

describe('a cached resolution never pins (P2-7)', () => {
  it('waits for the fresh answer when an older mapping is still cached', async () => {
    let release: (value: ResolvePayload) => void = () => undefined
    const spy = vi.spyOn(api, 'fetchAnalysisResolve').mockImplementation(
      () => new Promise<ResolvePayload>((resolve) => { release = resolve }))
    const client = newClient()
    client.setQueryData(resolveKey('AAA'), staleMapping())
    const { onNavigate } = mount({ page: 'analysis', ticker: 'AAA' }, {}, client)
    await waitFor(() => expect(spy).toHaveBeenCalledTimes(1))
    expect(screen.getByText(/Resolving AAA/)).toBeInTheDocument()
    expect(onNavigate).not.toHaveBeenCalled()
    await act(async () => { release(resolved()) })
    await waitFor(() => expect(onNavigate).toHaveBeenCalledTimes(1))
    expect(onNavigate).toHaveBeenCalledWith(PINNED, DEFAULT_WINDOW, { replace: true })
  })

  it('reselecting after a stale pinned link resolves again instead of reusing the old IDs', async () => {
    vi.spyOn(api, 'fetchAnalysis').mockRejectedValue(
      new AnalysisUnavailable('conflict', 'identity_changed', 'the mapped primary changed'))
    let release: (value: ResolvePayload) => void = () => undefined
    const spy = vi.spyOn(api, 'fetchAnalysisResolve').mockImplementation(
      () => new Promise<ResolvePayload>((resolve) => { release = resolve }))
    const client = newClient()
    client.setQueryData(resolveKey('AAA'), staleMapping())
    const stalePin: AnalysisRoute = { page: 'analysis', ticker: 'AAA', companyId: 99, instrumentId: 98 }
    const { onNavigate, rerender } = mount(stalePin, {}, client)
    await screen.findByText(/no longer matches today's mapping/)
    // The reader picks AAA from search again: the ticker-only form.
    rerender({ page: 'analysis', ticker: 'AAA' })
    await waitFor(() => expect(spy).toHaveBeenCalledTimes(1))
    expect(onNavigate).not.toHaveBeenCalled()
    // Remapped: today's IDs differ from the cached ones.
    await act(async () => { release(resolved()) })
    await waitFor(() => expect(onNavigate).toHaveBeenCalledTimes(1))
    expect(onNavigate).toHaveBeenCalledWith(PINNED, DEFAULT_WINDOW, { replace: true })
    expect(onNavigate).not.toHaveBeenCalledWith(expect.objectContaining({ companyId: 99 }),
                                                expect.anything(), expect.anything())
  })

  it('pins only the answer for the ticker now in the address when replies race', async () => {
    const pending = new Map<string, (value: ResolvePayload) => void>()
    vi.spyOn(api, 'fetchAnalysisResolve').mockImplementation(
      (ticker) => new Promise<ResolvePayload>((resolve) => { pending.set(ticker, resolve) }))
    const { onNavigate, rerender } = mount({ page: 'analysis', ticker: 'AAA' })
    await waitFor(() => expect(pending.has('AAA')).toBe(true))
    rerender({ page: 'analysis', ticker: 'BBB' })
    await waitFor(() => expect(pending.has('BBB')).toBe(true))
    await act(async () => { pending.get('AAA')!(resolved()) })
    expect(onNavigate).not.toHaveBeenCalled()
    const bbb = resolved({
      company: { id: 5, ticker: 'BBB', name: 'Bbb', first_seen: '2026-01-01T00:00:00Z' },
      instrument: { ...resolved().instrument, id: 6, ticker: 'BBB', provider_symbol: 'BBB' },
    })
    await act(async () => { pending.get('BBB')!(bbb) })
    await waitFor(() => expect(onNavigate).toHaveBeenCalledTimes(1))
    expect(onNavigate).toHaveBeenCalledWith(
      { page: 'analysis', ticker: 'BBB', companyId: 5, instrumentId: 6 }, DEFAULT_WINDOW, { replace: true })
  })
})

describe('the pinned read (C03-C09/C12/C16)', () => {
  it('renders identity, coverage, chart, day detail and the table from one answer', async () => {
    vi.spyOn(api, 'fetchAnalysis').mockResolvedValue(analysis())
    mount(PINNED)
    await screen.findByRole('group', { name: 'Select a day' })
    expect(screen.getByRole('heading', { level: 1 })).toHaveTextContent('Explore · AAA')
    expect(screen.getByText(/US primary · USD · all retained sources/)).toBeInTheDocument()
    expect(screen.getByText(/today's mapping, applied retrospectively/)).toBeInTheDocument()
    expect(screen.getByText('NYSE (XNYS) · AAA')).toBeInTheDocument()
    expect(screen.getByLabelText('Price coverage')).toHaveTextContent('3 of 7 days observed')
    expect(screen.getByLabelText('Price coverage')).toHaveTextContent('Missing on 1 modeled-open day(s): Wed 9 Sep')
    expect(screen.getByLabelText('Price coverage')).toHaveTextContent('Official session completeness: unknown')
    expect(screen.getByLabelText('Chatter coverage')).toHaveTextContent('3 observed · 1 partial · 3 unavailable')
    expect(screen.getByLabelText('Chatter coverage')).toHaveTextContent('historical source set not verified')
    // The selected day defaults to the last usable close (Fri 11) and shows its facts.
    const detail = screen.getByLabelText(/Selected day, Fri 11 Sep 2026/)
    expect(detail).toHaveTextContent('10.80 USD')
    expect(detail).toHaveTextContent('massive_grouped · close · split')
    expect(detail).toHaveTextContent('3 observed')
    // The accessible table carries every day and the same facts.
    const table = within(screen.getByLabelText('Daily table')).getByRole('table')
    const rows = within(table).getAllByRole('row').slice(1)
    expect(rows).toHaveLength(7)
    expect(rows[2]).toHaveTextContent('no close retained (modeled open day)')
    expect(rows[2]).toHaveTextContent('0 observed')
    expect(rows[3]).toHaveTextContent('40 in observed buckets — coverage incomplete')
    expect(rows[5]).toHaveTextContent('no close (modeled closed day)')
    expect(rows[5]).toHaveTextContent('no retained buckets')
    // Once as a standing limit in the rail, once as this read's own note.
    expect(screen.getAllByText(/split stamp is a declared basis/)).toHaveLength(2)
    expect(screen.getByText(/not unique people or posts/)).toBeInTheDocument()
    // No return figure, score or tone anywhere; the rail says so in words.
    expect(screen.queryByText(/[+\-−]\d+(\.\d+)?\s?%/)).not.toBeInTheDocument()
    expect(screen.queryByText(/bullish|bearish|score|mention_z/i)).not.toBeInTheDocument()
    expect(screen.getByText(/No return is calculated/)).toBeInTheDocument()
  })

  it('changes the selected day from the table and the buttons', async () => {
    vi.spyOn(api, 'fetchAnalysis').mockResolvedValue(analysis())
    mount(PINNED)
    const group = await screen.findByRole('group', { name: 'Select a day' })
    await userEvent.click(within(group).getAllByRole('button')[2]!)
    expect(screen.getByLabelText(/Selected day, Wed 9 Sep 2026/)).toHaveTextContent('no close retained (modeled open day)')
    const table = within(screen.getByLabelText('Daily table')).getByRole('table')
    await userEvent.click(within(table).getByRole('button', { name: 'Thu 10 Sep' }))
    const detail = screen.getByLabelText(/Selected day, Thu 10 Sep 2026/)
    expect(detail).toHaveTextContent('40 in observed buckets — coverage incomplete')
    expect(within(detail).getByRole('table')).toHaveTextContent('bluesky')
    expect(within(detail).getByRole('table')).toHaveTextContent('partial')
  })

  it('names exclusions in source-bucket rows, never time slots (P2-4/P3)', async () => {
    const base = analysis()
    const payload: AnalysisPayload = analysis({
      chatter: { ...base.chatter, days: base.chatter.days.map((d) => (d.date === '2026-09-11'
        ? chatterDay(d.date, { mentions: null, coverage: 'partial', overlap_ambiguous: true, config_transition: true,
                               identity_excluded_slots: 144, excluded_rows: 2,
                               sources: [sourceDay('reddit', { mentions: 1, config_versions: ['a', 'b'], transition: true,
                                                               coverage: 'partial', excluded_rows: 2 }),
                                         sourceDay('reddit:wsb', { mentions: 2 })] })
        : d)) },
    })
    vi.spyOn(api, 'fetchAnalysis').mockResolvedValue(payload)
    mount(PINNED)
    const detail = await screen.findByLabelText(/Selected day, Fri 11 Sep 2026/)
    expect(detail).toHaveTextContent('source overlap — pooled count withheld')
    expect(detail).toHaveTextContent('config changed')
    expect(detail).toHaveTextContent('144 source-bucket rows before the company record excluded')
    expect(detail).toHaveTextContent('2 source-bucket rows off the 15-minute grid or repeated, excluded')
    expect(detail).not.toHaveTextContent(/\bslots? before/)
    const sources = within(detail).getByRole('table')
    expect(sources).toHaveTextContent('a → b (changed)')
    expect(within(sources).getByRole('columnheader', { name: 'excluded rows' })).toBeInTheDocument()
  })

  it('names the scrollable tables, marks the selected row without aria-selected and announces briefly', async () => {
    vi.spyOn(api, 'fetchAnalysis').mockResolvedValue(analysis())
    mount(PINNED)
    await screen.findByRole('group', { name: 'Select a day' })
    expect(screen.getByRole('region', { name: 'Daily table (scrollable)' })).toHaveAttribute('tabindex', '0')
    expect(screen.getByRole('region', { name: 'Per-source buckets (scrollable)' })).toHaveAttribute('tabindex', '0')
    const table = within(screen.getByLabelText('Daily table')).getByRole('table')
    for (const row of within(table).getAllByRole('row')) expect(row).not.toHaveAttribute('aria-selected')
    expect(within(table).getByRole('button', { name: 'Fri 11 Sep' })).toHaveAttribute('aria-current', 'true')
    // The detail itself is not live: selecting a day must not re-read its tables.
    expect(screen.getByLabelText(/Selected day/)).not.toHaveAttribute('aria-live')
    await userEvent.click(within(table).getByRole('button', { name: 'Wed 9 Sep' }))
    const status = screen.getAllByRole('status').find((el) => el.textContent?.includes('Wed 9 Sep 2026'))
    expect(status).toHaveTextContent('Wed 9 Sep 2026: no close retained (modeled open day); 0 observed.')
    expect(within(table).getByRole('button', { name: 'Wed 9 Sep' })).toHaveAttribute('aria-current', 'true')
    expect(within(table).getByRole('button', { name: 'Fri 11 Sep' })).not.toHaveAttribute('aria-current')
  })

  it('refuses an answer whose identity is not the one in the address', async () => {
    vi.spyOn(api, 'fetchAnalysis').mockResolvedValue(analysis({
      company: { id: 12, ticker: 'AAA', name: 'Aaa Corp', first_seen: '2026-01-01T00:00:00Z' },
    }))
    mount(PINNED)
    await screen.findByText(/did not match this link/)
    expect(screen.queryByRole('group', { name: 'Select a day' })).not.toBeInTheDocument()
  })

  it('shows a failed read with Retry, then the data', async () => {
    vi.spyOn(api, 'fetchAnalysis')
      .mockRejectedValueOnce(new AnalysisUnavailable('timeout'))
      .mockResolvedValueOnce(analysis())
    mount(PINNED)
    await screen.findByText('The analysis did not answer in time.')
    await userEvent.click(screen.getByRole('button', { name: 'Retry' }))
    await screen.findByRole('group', { name: 'Select a day' })
  })

  it('keeps the last answer on a failed refresh and says when it was read', async () => {
    vi.spyOn(api, 'fetchAnalysis')
      .mockResolvedValueOnce(analysis())
      .mockRejectedValueOnce(new AnalysisUnavailable('unavailable', 'analysis_unavailable', 'store down'))
    const { client } = mount(PINNED)
    await screen.findByRole('group', { name: 'Select a day' })
    await act(async () => { await client.refetchQueries() })
    await screen.findByText(/Showing the answer read 2026-09-14 12:30 UTC/)
    expect(screen.getByText(/store down/)).toBeInTheDocument()
    expect(screen.getByRole('group', { name: 'Select a day' })).toBeInTheDocument()
  })

  it('reports an expired session upward', async () => {
    vi.spyOn(api, 'fetchAnalysis').mockRejectedValue(new AnalysisUnavailable('session'))
    const { onSessionExpired } = mount(PINNED)
    await waitFor(() => expect(onSessionExpired).toHaveBeenCalled())
  })

  it('a stale pinned link says so and does not retarget', async () => {
    vi.spyOn(api, 'fetchAnalysis').mockRejectedValue(
      new AnalysisUnavailable('conflict', 'identity_changed', 'the mapped primary changed'))
    mount(PINNED)
    await screen.findByText(/no longer matches today's mapping/)
    expect(screen.getByText(/not silently retargeted/)).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Retry' })).not.toBeInTheDocument()
  })
})

describe('the window controls (C01/C15)', () => {
  it('shows an invalid address window as typed and fetches nothing', () => {
    const read = vi.spyOn(api, 'fetchAnalysis')
    mount(PINNED, { rawRange: { from: '2026-09-13', to: '2026-09-07' } })
    expect(screen.getByRole('alert')).toHaveTextContent('The start must not be after the end.')
    expect(screen.getByRole('alert')).toHaveTextContent('Asked for “2026-09-13” to “2026-09-07”.')
    expect(screen.getByLabelText(/From \(UTC day\)/)).toHaveValue('2026-09-13')
    expect(screen.getByText('No window to show.')).toBeInTheDocument()
    expect(read).not.toHaveBeenCalled()
  })

  it('keeps a malformed address date visible and editable as text, and fetches nothing (P2-6)', () => {
    const read = vi.spyOn(api, 'fetchAnalysis')
    mount(PINNED, { rawRange: { from: '2026-13-07', to: '' } })
    const from = screen.getByLabelText(/From \(UTC day\)/)
    // A native date input would sanitize this to an empty value in a real browser.
    expect(from).toHaveAttribute('type', 'text')
    expect(from).toHaveValue('2026-13-07')
    expect(from).toHaveAttribute('aria-invalid', 'true')
    expect(screen.getByRole('alert')).toHaveTextContent('Dates must be written YYYY-MM-DD')
    expect(screen.getByRole('alert')).toHaveTextContent('Asked for “2026-13-07” to (empty).')
    expect(read).not.toHaveBeenCalled()
  })

  it('echoes a malformed typed window instead of letting the browser swallow it', async () => {
    vi.spyOn(api, 'fetchAnalysis').mockResolvedValue(analysis())
    const { onNavigate } = mount(PINNED)
    await screen.findByRole('group', { name: 'Select a day' })
    const from = screen.getByLabelText(/From \(UTC day\)/)
    await userEvent.clear(from)
    await userEvent.type(from, '9/7/2026')
    await userEvent.click(screen.getByRole('button', { name: 'Show these days' }))
    expect(screen.getByRole('alert')).toHaveTextContent('Asked for “9/7/2026” to “2026-09-13”.')
    expect(onNavigate).not.toHaveBeenCalled()
  })

  it('applies a valid explicit window as a pushed navigation that keeps focus', async () => {
    vi.spyOn(api, 'fetchAnalysis').mockResolvedValue(analysis())
    const { onNavigate } = mount(PINNED)
    await screen.findByRole('group', { name: 'Select a day' })
    const from = screen.getByLabelText(/From \(UTC day\)/)
    const to = screen.getByLabelText(/To \(UTC day\)/)
    await userEvent.clear(from)
    await userEvent.type(from, '2026-09-10')
    await userEvent.clear(to)
    await userEvent.type(to, '2026-09-12')
    await userEvent.click(screen.getByRole('button', { name: 'Show these days' }))
    expect(onNavigate).toHaveBeenCalledWith(PINNED, { from: '2026-09-10', to: '2026-09-12' },
                                            { keepFocus: true })
  })

  it('refuses a typed 8-day or today window before sending it', async () => {
    vi.spyOn(api, 'fetchAnalysis').mockResolvedValue(analysis())
    const { onNavigate } = mount(PINNED)
    await screen.findByRole('group', { name: 'Select a day' })
    const from = screen.getByLabelText(/From \(UTC day\)/)
    await userEvent.clear(from)
    await userEvent.type(from, '2026-09-06')
    await userEvent.click(screen.getByRole('button', { name: 'Show these days' }))
    expect(screen.getByRole('alert')).toHaveTextContent('At most 7 days')
    expect(onNavigate).not.toHaveBeenCalled()
  })

  it('shows a one-close window as a value and a no-chatter window as unavailable', async () => {
    const base = analysis()
    vi.spyOn(api, 'fetchAnalysis').mockResolvedValue(analysis({
      request: { ...base.request, from: '2026-09-10', to: '2026-09-10' },
      price: { ...base.price, days: [priceDay('2026-09-10', { close: 11 })], usable_count: 1,
        first_usable: '2026-09-10', last_usable: '2026-09-10', interior_modeled_missing: null },
      chatter: { ...base.chatter, days: [chatterDay('2026-09-10')], first_observed: null, last_observed: null },
    }))
    mount(PINNED, { rawRange: { from: '2026-09-10', to: '2026-09-10' } })
    await screen.findByRole('group', { name: 'Select a day' })
    expect(screen.getByLabelText('Price coverage')).toHaveTextContent('1 of 1 days observed')
    expect(screen.getByLabelText('Price coverage')).toHaveTextContent('Interior gaps not assessable')
    expect(screen.getByLabelText('Chatter coverage')).toHaveTextContent('No retained bucket in this window')
    expect(screen.getByLabelText(/Selected day, Thu 10 Sep 2026/)).toHaveTextContent('no retained buckets')
  })
})
