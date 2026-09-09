import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, describe, expect, it, vi } from 'vitest'

import * as api from '../api'
import { BoardUnavailable } from '../api'
import { detail, payload } from '../fixtures'
import type { Detail, PanelSpan, Selection } from '../types'
import { selectionOf } from './queries'
import { Research } from './Research'

const selection: Selection = selectionOf(payload())

function show(props: Partial<Parameters<typeof Research>[0]> = {},
              client = new QueryClient({
                defaultOptions: { queries: { retry: false } },
              })) {
  const result = render(
    <QueryClientProvider client={client}>
      <Research ticker="AAA" selection={selection} span="1D"
                onSpan={vi.fn()} onBack={vi.fn()} onSearch={vi.fn()}
                {...props} />
    </QueryClientProvider>,
  )
  return { ...result, client }
}

afterEach(() => { vi.restoreAllMocks() })

describe('finding the company', () => {
  it('carries the listing’s sources and window into the request', async () => {
    // The breakdown and the posts describe the same window the row's phrase
    // did. A panel scoped differently would quietly disagree with the row
    // that opened it.
    const fetchDetail = vi.spyOn(api, 'fetchDetail').mockResolvedValue(detail())
    show()
    await screen.findByText('Alpha Inc')

    expect(fetchDetail).toHaveBeenCalledWith('AAA', selection, '1D',
                                             expect.anything())
  })

  it('offers a way back and a way to search when the ticker is gone', async () => {
    vi.spyOn(api, 'fetchDetail').mockRejectedValue(new BoardUnavailable('missing'))
    const onBack = vi.fn()
    show({ onBack })

    expect(await screen.findByText(/nothing here for AAA/i)).toBeVisible()
    await userEvent.click(screen.getByRole('button', { name: /back to the list/i }))
    expect(onBack).toHaveBeenCalled()
    expect(screen.getByRole('button', { name: /search for a company/i }))
      .toBeVisible()
  })

  it('opens a company that is not on the current ranked board', async () => {
    // Search reaches the whole universe, so the panel must not assume the
    // ticker was among the rows that opened it.
    vi.spyOn(api, 'fetchDetail').mockResolvedValue(detail('ZZZ'))
    show({ ticker: 'ZZZ' })
    expect(await screen.findByText('Alpha Inc')).toBeVisible()
  })

  it('never shows the previous company under the new one’s heading', async () => {
    // The cache keeps the last panel so the layout does not collapse between
    // two fetches. Rendering it here would put one company's name, price and
    // evidence under another company's heading and URL.
    const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
    vi.spyOn(api, 'fetchDetail').mockResolvedValue(detail('AAA'))
    const first = show({}, client)
    await screen.findByText('Alpha Inc')
    first.unmount()

    let release: (value: Detail) => void = () => {}
    vi.spyOn(api, 'fetchDetail').mockReturnValue(
      new Promise((resolve) => { release = resolve }))
    show({ ticker: 'BBB' }, client)

    expect(screen.queryByText('Alpha Inc')).not.toBeInTheDocument()
    expect(screen.getByText(/loading BBB/i)).toBeVisible()

    release({ ...detail('BBB'), identity: { ...detail('BBB').identity,
                                            name: 'Beta Corp' } })
    expect(await screen.findByText('Beta Corp')).toBeVisible()
  })
})

describe('what the panel is allowed to say', () => {
  it('labels a 1D chart drawn from daily closes as daily closes', async () => {
    // 1D prices from quote snapshots when there are enough and from stored
    // closes when there are not. A constant caption would claim a resolution
    // the line does not have.
    const daily = detail()
    daily.chart = { ...daily.chart, span: '1D' as PanelSpan, priced_from: 'daily' }
    vi.spyOn(api, 'fetchDetail').mockResolvedValue(daily)
    show()

    expect(await screen.findByText(/daily closes · mentions per 15 min/i))
      .toBeVisible()
    expect(screen.queryByText(/intraday quotes/i)).not.toBeInTheDocument()
  })

  it('labels a 1D chart drawn from snapshots as intraday', async () => {
    const intraday = detail()
    intraday.chart = { ...intraday.chart, span: '1D' as PanelSpan,
                       priced_from: 'intraday' }
    vi.spyOn(api, 'fetchDetail').mockResolvedValue(intraday)
    show()
    expect(await screen.findByText(/intraday quotes · mentions per 15 min/i))
      .toBeVisible()
  })

  it('does not report absent evidence as zero', async () => {
    // The bucket totals the clauses are counted from outlive the individual
    // mentions behind them, so an older window has totals and no rows. "0
    // independent voices across 0 posts" next to a clause saying 80 mentions
    // reports an absence as a measurement.
    const empty = detail()
    empty.breakdown = { ...empty.breakdown, venues: [], mentions: 0, voices: 0,
                        top_author_share: null }
    empty.read = [{ kind: 'plain', text: '80 mentions in this window.' }]
    vi.spyOn(api, 'fetchDetail').mockResolvedValue(empty)
    show()

    expect(await screen.findByText(/no per-post evidence is held/i)).toBeVisible()
    expect(screen.queryByText(/0 independent/i)).not.toBeInTheDocument()
    expect(screen.queryByText(/across 0 posts/i)).not.toBeInTheDocument()
  })

  it('still reports a real measurement', async () => {
    vi.spyOn(api, 'fetchDetail').mockResolvedValue(detail())
    show()
    expect(await screen.findByText(/independent/)).toBeVisible()
    expect(screen.queryByText(/no per-post evidence/i)).not.toBeInTheDocument()
  })

  it('keeps a null price unavailable', async () => {
    const unpriced = detail()
    unpriced.identity = {
      ...unpriced.identity, price: null, price_move: null,
      quote: { ...unpriced.identity.quote, price: null, quality: 'unavailable' },
    }
    vi.spyOn(api, 'fetchDetail').mockResolvedValue(unpriced)
    show()

    expect(await screen.findByText(/price unavailable/i)).toBeVisible()
    expect(screen.queryByText('$0.00')).not.toBeInTheDocument()
  })

  it('states the venue, currency and when the quote was taken', async () => {
    vi.spyOn(api, 'fetchDetail').mockResolvedValue(detail())
    show()
    await screen.findByText('Alpha Inc')
    const provenance = screen.getByTestId('rh-quote-provenance').textContent ?? ''
    expect(provenance).toMatch(/Nasdaq/)
    expect(provenance).toMatch(/USD/)
    // With a date, not a bare time of day: an "eod" or "stale" quote showing
    // only a clock time reads as today.
    expect(provenance).toMatch(/\d{1,2} \w{3} 2026/)
  })

  it('renders a source body as text, never as markup', async () => {
    const withHtml = detail()
    withHtml.posts = [{
      source: 'bluesky', author: 'someone', channel: '',
      created: '2026-08-22T19:00:00Z', title: null,
      body: '<img src=x onerror="alert(1)">short squeeze<script>bad()</script>',
      url: 'https://example.test/post', tone: 'neutral',
      judged_by: null, judged_label: null,
    }]
    withHtml.post_total = 1
    vi.spyOn(api, 'fetchDetail').mockResolvedValue(withHtml)
    const { container } = show()

    await screen.findByText(/short squeeze/)
    expect(container.querySelector('img')).toBeNull()
    expect(container.querySelector('script')).toBeNull()
  })

  it('says nothing about a broker it has not verified', async () => {
    vi.spyOn(api, 'fetchDetail').mockResolvedValue(detail())
    show()
    await screen.findByText('Alpha Inc')
    expect(screen.getByText(/has not been verified/i)).toBeVisible()
    const text = document.body.textContent ?? ''
    expect(text).not.toMatch(/available on scalable|verified on scalable/i)
    // The prototype's generated verdict, and the shapes a thesis takes. The
    // page's own disclaimer contains the words "buy or sell", so the check
    // has to be for a recommendation rather than for those words.
    expect(text).not.toMatch(/consider entry|price target|strong (buy|sell)/i)
    expect(text).not.toMatch(/we (expect|recommend)|our view/i)
  })

  it('survives a chart with nothing in it', async () => {
    const bare = detail()
    bare.chart = { ...bare.chart, closes: [], chatter: [], sessions: [] }
    vi.spyOn(api, 'fetchDetail').mockResolvedValue(bare)
    show()
    // Renders, and does not throw: an absent chart is a gap in one zone, not
    // a broken page.
    expect(await screen.findByText('Alpha Inc')).toBeVisible()
  })
})

describe('the watch control', () => {
  it('is absent until the caller can service it', async () => {
    vi.spyOn(api, 'fetchDetail').mockResolvedValue(detail())
    show()
    await screen.findByText('Alpha Inc')
    expect(screen.queryByRole('button', { name: /^watch$/i })).not.toBeInTheDocument()
  })

  it('shows the mark this account already made', async () => {
    vi.spyOn(api, 'fetchDetail').mockResolvedValue(detail())
    show({ watching: ['AAA'], onToggleWatch: vi.fn() })
    const button = await screen.findByRole('button', { name: /watching/i })
    expect(button).toHaveAttribute('aria-pressed', 'true')
  })

  it('cannot be clicked twice while a write is in flight', async () => {
    vi.spyOn(api, 'fetchDetail').mockResolvedValue(detail())
    const onToggleWatch = vi.fn()
    show({ watching: [], onToggleWatch, watchPending: true })
    const button = await screen.findByRole('button', { name: /saving/i })
    expect(button).toBeDisabled()
    await userEvent.click(button)
    expect(onToggleWatch).not.toHaveBeenCalled()
  })

  it('says so when a mark was refused', async () => {
    vi.spyOn(api, 'fetchDetail').mockResolvedValue(detail())
    show({ watching: [], onToggleWatch: vi.fn(),
           watchError: new BoardUnavailable('server') })
    await waitFor(() => {
      expect(screen.getByText(/could not be saved/i)).toBeVisible()
    })
  })
})
