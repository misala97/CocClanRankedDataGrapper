// One company, in depth: who it is, what it costs, and what was actually said.
//
// The list answered "which of these deserves my time". This answers "is it
// real", and it does that by showing evidence rather than a verdict. The chart
// puts price and chatter on one time axis so their relationship is the
// reader's to judge; the breakdown says how concentrated the discussion is;
// the posts are the source text itself.
//
// The summary column deliberately is not a thesis. It restates the server's
// own clauses, names the concentration figures, and says what is unverified --
// most of all that a social ticker is not a tradable listing and that broker
// availability is unknown. A generated recommendation here would be the one
// thing this surface must never produce.
import { Breakdown } from '../detail/Breakdown'
import { Posts } from '../detail/Posts'
import { ChartBasisNote, PriceChart } from '../detail/PriceChart'
import { exchangeLabel, segmentLabel } from '../format'
import type { Detail, PanelSpan, Selection } from '../types'
import { Loading, Unavailable } from './PageState'
import { useDetail } from './queries'
import { BoardUnavailable } from '../api'

const SPANS: PanelSpan[] = ['1D', '1W', '1M', '6M', '1Y', '3Y']

/** What the two lanes are made of, which differs by span. Copied in meaning
 *  from the board panel, because a caption claiming intraday resolution the
 *  line does not have is worse than no caption. */
const CAPTIONS: Record<PanelSpan, string> = {
  '1D': 'intraday quotes · mentions per 15 min',
  '1W': 'intraday quotes · mentions per hour',
  '1M': 'daily closes · mentions per day',
  '6M': 'daily closes · mentions per day',
  '1Y': 'daily closes · mentions per day',
  '3Y': 'daily closes · mentions per day',
}

export function Research({ ticker, selection, span, onSpan, onBack, onSearch,
                           watching, onToggleWatch, visible = true }: {
  ticker: string
  selection: Selection
  span: PanelSpan
  onSpan: (span: PanelSpan) => void
  onBack: () => void
  onSearch: () => void
  watching?: string[]
  onToggleWatch?: (ticker: string) => void
  visible?: boolean
}) {
  const { data, error, isLoading, refetch } = useDetail(ticker, selection, span,
                                                        visible)

  if (isLoading && !data) return <Loading label={`Loading ${ticker}…`} />
  if (!data) return <NotHere ticker={ticker} error={error} onBack={onBack}
                             onSearch={onSearch} retry={() => void refetch()} />

  const { identity, chart, breakdown } = data
  const isWatched = watching?.includes(identity.ticker) ?? false

  return (
    <>
      <p className="rh-crumb">
        <button type="button" className="rh-textbutton" onClick={onBack}>
          ← Back to the list
        </button>
      </p>

      <div className="rh-researchhead">
        <div className="rh-identity">
          <span className="rh-mark large" aria-hidden="true">
            {identity.ticker.slice(0, 2)}
          </span>
          <div>
            <h1>{identity.name ?? identity.ticker}</h1>
            <p className="muted small">
              {[identity.ticker, segmentLabel(identity.segment),
                exchangeLabel(identity.exchange)].filter(Boolean).join(' · ')}
            </p>
          </div>
        </div>
        {onToggleWatch ? (
          <button
            type="button"
            className={`rh-button${isWatched ? '' : ' primary'}`}
            aria-pressed={isWatched}
            onClick={() => onToggleWatch(identity.ticker)}
          >
            {isWatched ? '✓ Watching' : 'Watch'}
          </button>
        ) : null}
      </div>

      <div className="rh-researchcols">
        <div className="rh-stack">
          <Quote detail={data} />

          <section className="rh-panel rh-pad" aria-labelledby="rh-chart-head">
            <div className="rh-sectionhead">
              <div>
                <h2 id="rh-chart-head">Price and chatter</h2>
                <p className="muted small">{CAPTIONS[chart.span]}</p>
              </div>
              <div className="rh-spans" role="group" aria-label="Chart span">
                {SPANS.map((option) => (
                  <button
                    key={option}
                    type="button"
                    aria-pressed={option === span}
                    onClick={() => onSpan(option)}
                  >
                    {option}
                  </button>
                ))}
              </div>
            </div>
            <ChartBasisNote chart={chart} quoteVenue={identity.quote.venue} />
            {/* Its own scroller: below the desk widths the chart pans rather
                than being scaled until its axis is unreadable. The document
                itself never scrolls sideways. */}
            <div className="rh-chartwrap" role="region"
                 aria-label={`Price and chatter for ${identity.ticker}`}
                 tabIndex={0}>
              <PriceChart chart={chart} />
            </div>
            <p className="rh-caption">
              Swipe or scroll sideways for earlier history. The chart has a
              text equivalent under every figure it draws: the price and the
              window are stated above, and the counts are in the breakdown.
            </p>
          </section>

          {/* Both components bring their own heading and their own caption,
              and both captions name the window -- wrapping them in a second
              heading said the same thing twice. */}
          <section className="rh-panel rh-pad">
            <Breakdown breakdown={breakdown} windowHours={selection.window} />
          </section>

          <section className="rh-panel rh-pad">
            <Posts posts={data.posts} total={data.post_total} retentionNote />
          </section>
        </div>

        <Summary detail={data} />
      </div>
    </>
  )
}

/** Identity and provenance together, because a price without the venue,
 *  currency and time it was taken at is a number, not a fact. */
function Quote({ detail }: { detail: Detail }) {
  const { identity } = detail
  const { quote } = identity
  const unavailable = quote.quality === 'unavailable' || identity.price === null
  return (
    <section className="rh-panel rh-pad" aria-labelledby="rh-quote-head">
      <h2 id="rh-quote-head" className="rh-visually-hidden">Price</h2>
      {unavailable ? (
        <>
          <p className="rh-bigprice">Price unavailable</p>
          <p className="muted small">
            No quote was available for this listing. The chatter figures below
            are unaffected — they do not depend on a price.
          </p>
        </>
      ) : (
        <>
          <p className="rh-bigprice num">
            {formatPrice(identity.price as number, quote.currency)}
            <span className={`rh-move ${moveClass(identity.price_move)}`}>
              {identity.price_move === null
                ? ' move unknown'
                : ` ${identity.price_move > 0 ? '+' : ''}${(identity.price_move * 100).toFixed(1)}% today`}
            </span>
          </p>
          <p className="muted small">
            {[quote.venue, quote.currency, quote.mic].filter(Boolean).join(' · ')}
            {quote.quoted_at ? ` · quoted ${berlinTime(quote.quoted_at)} Berlin` : ''}
            {' · '}{quote.quality}
            {quote.is_fallback ? ' · fallback listing' : ''}
          </p>
        </>
      )}
      <dl className="rh-facts">
        <div>
          <dt>Session</dt>
          <dd>{identity.session}</dd>
        </div>
        <div>
          <dt>Market cap</dt>
          <dd>{identity.market_cap === null ? 'Not measured' : cap(identity.market_cap)}</dd>
        </div>
        <div>
          <dt>Basis</dt>
          <dd>{quote.price_basis ?? 'unknown'}</dd>
        </div>
      </dl>
      {/* A quote timestamp is not the observation time of the chatter. Two
          different clocks, and conflating them is how a stale price gets read
          as a stale conversation. */}
      <p className="rh-caption">
        The quote time above is when the price was taken. It is not when the
        discussion happened.
      </p>
    </section>
  )
}

/** What is known, and what is explicitly not. Never a trade thesis. */
function Summary({ detail }: { detail: Detail }) {
  const { breakdown, read } = detail
  const concentrated = breakdown.top_author_share !== null
    && breakdown.top_author_share >= 0.5
  return (
    <aside className="rh-summary" aria-labelledby="rh-summary-head">
      <h2 id="rh-summary-head">What the figures say</h2>

      {read.length ? (
        <p className="rh-read">
          {read.map((clause, index) => (
            <span key={index} className={`rh-clause ${clause.kind}`}>
              {clause.text}{' '}
            </span>
          ))}
        </p>
      ) : (
        <p className="muted small">
          No phrase was produced for this company in this window.
        </p>
      )}

      <h3>How concentrated it is</h3>
      <ul className="rh-facts-list">
        <li>
          <strong className="num">{breakdown.voices}</strong> independent
          {breakdown.voices === 1 ? ' voice' : ' voices'} across
          {' '}<strong className="num">{breakdown.mentions}</strong>
          {breakdown.mentions === 1 ? ' post' : ' posts'}
        </li>
        <li>
          <strong className="num">{breakdown.venues.length}</strong>
          {breakdown.venues.length === 1 ? ' venue' : ' venues'}:
          {' '}{breakdown.venues.map((venue) => venue.source).join(', ') || '—'}
        </li>
        <li className={concentrated ? 'warning' : undefined}>
          {breakdown.top_author_share === null
            ? 'Author concentration not measured'
            : `Loudest account is ${(breakdown.top_author_share * 100).toFixed(0)}% of the posts`}
        </li>
        {breakdown.disagreements > 0 ? (
          <li>
            <strong className="num">{breakdown.disagreements}</strong> posts
            where the wording score and the model read the tone differently
          </li>
        ) : null}
      </ul>

      <h3>What this is not</h3>
      <p className="muted small">
        A rank here is unusual discussion with price context. It is not a view
        on the company, a probability, or a recommendation to buy or sell.
      </p>
      <p className="muted small">
        The ticker above identifies the company Radar tracked in social posts.
        Whether a matching listing is available in any particular broker,
        including Scalable, has not been verified.
      </p>
    </aside>
  )
}

function NotHere({ ticker, error, onBack, onSearch, retry }: {
  ticker: string; error: unknown; onBack: () => void; onSearch: () => void
  retry: () => void
}) {
  const missing = error instanceof BoardUnavailable && error.reason === 'missing'
  if (!missing) return <Unavailable error={error} retry={retry} />
  return (
    <div className="rh-empty">
      <h2>Nothing here for {ticker}.</h2>
      <p>
        Radar has no panel for that ticker in the current window and market.
        It may have dropped off the board, or the symbol may be spelled
        differently in this market.
      </p>
      <p className="rh-empty-actions">
        <button type="button" className="rh-button primary" onClick={onBack}>
          Back to the list
        </button>
        <button type="button" className="rh-button" onClick={onSearch}>
          Search for a company
        </button>
      </p>
    </div>
  )
}

function moveClass(move: number | null): string {
  if (move === null || move === 0) return ''
  return move > 0 ? 'positive' : 'negative'
}

function formatPrice(value: number, currency: string | null): string {
  const symbol = currency === 'EUR' ? '€' : currency === 'USD' ? '$' : ''
  const text = value.toLocaleString('en-US',
    { minimumFractionDigits: 2, maximumFractionDigits: 2 })
  return symbol ? `${symbol}${text}` : `${text} ${currency ?? ''}`.trim()
}

function berlinTime(iso: string): string {
  return new Date(iso).toLocaleTimeString('en-GB',
    { hour: '2-digit', minute: '2-digit', timeZone: 'Europe/Berlin' })
}

function cap(value: number): string {
  if (value >= 1e12) return `$${(value / 1e12).toFixed(1)}T`
  if (value >= 1e9) return `$${(value / 1e9).toFixed(1)}B`
  if (value >= 1e6) return `$${(value / 1e6).toFixed(0)}M`
  return `$${value.toLocaleString('en-US')}`
}
