// Analysis / Explore (HA1): one company, its current mapped US primary, and
// the last completed days of daily closes beside retained mention counts.
//
// Three route forms arrive here. No ticker: a prompt to find one. A ticker
// only: resolve it to today's company and instrument IDs, then REPLACE the
// address with the canonical pinned link -- carrying the address's dates
// exactly as written, valid or not. IDs: read the window, and refuse to draw
// anything whose identity is not exactly the one in the address.
//
// Everything on this page is retrospective and says so. Counts are stored
// mention observations, not people or posts; closes are stored trading
// dates; the calendar is a model; the mapping is today's. None of that is
// hidden in a tooltip.
import { useEffect, useMemo, useState } from 'react'
import type { FormEvent } from 'react'

import { AnalysisUnavailable } from './analysisApi'
import { AnalysisChart } from './AnalysisChart'
import { useAnalysis, useAnalysisResolve } from './analysisQueries'
import {
  RANGE_PROBLEM_TEXT, chatterLabel, dayLabel, defaultRange, formatClose,
  priceStateLabel, rangeProblem, stampUtc,
} from './analysisTypes'
import type { AnalysisPayload, ChatterDay, PriceDay, Range } from './analysisTypes'
import { Loading } from './PageState'
import type { AnalysisRange, HubRoute } from './navigation'
import './analysis.css'

export type AnalysisRoute = Extract<HubRoute, { page: 'analysis' }>

export function Analysis({ route, rawRange, onNavigate, onSearch, onSessionExpired,
                           now = () => new Date() }: {
  route: AnalysisRoute
  /** The analysis dates as written in the address, or null for the default. */
  rawRange: AnalysisRange | null
  onNavigate: (route: AnalysisRoute, range: Range | null,
               options?: { replace?: boolean; keepFocus?: boolean }) => void
  onSearch: () => void
  onSessionExpired: () => void
  now?: () => Date
}) {
  const ticker = route.ticker ?? null
  const pinned = route.companyId !== undefined && route.instrumentId !== undefined
  const fallback = useMemo(() => defaultRange(now()), [now])
  const problem = rawRange === null ? null : rangeProblem(rawRange, now())
  const range: Range | null = rawRange === null ? fallback : problem === null ? rawRange : null
  // What the canonical link carries: the address's own strings when it had
  // any -- a malformed date stays malformed and visible -- else the default.
  const pinRange: Range = rawRange ?? fallback

  // --- resolve a ticker-only link to today's IDs -----------------------------
  const resolve = useAnalysisResolve(ticker !== null && !pinned ? ticker : null)
  // Only an answer fetched since this resolution began may pin. A cached
  // mapping from minutes ago is exactly what "search again" is meant to
  // replace; the server still revalidates whatever is pinned.
  const fresh = resolve.isSuccess && resolve.isFetchedAfterMount && !resolve.isFetching
    ? resolve.data : undefined
  useEffect(() => {
    if (pinned || ticker === null || !fresh) return
    const { company, instrument } = fresh
    if (company.ticker !== ticker) return
    onNavigate({ page: 'analysis', ticker, companyId: company.id, instrumentId: instrument.id },
               pinRange, { replace: true })
  }, [pinned, ticker, fresh, onNavigate, pinRange])

  const query = useAnalysis(pinned ? route.companyId! : null, pinned ? route.instrumentId! : null,
                            ticker, pinned ? range : null)

  const sessionError = [resolve.error, query.error].find(
    (error) => error instanceof AnalysisUnavailable && error.reason === 'session')
  useEffect(() => {
    if (sessionError) onSessionExpired()
  }, [sessionError, onSessionExpired])

  if (ticker === null) return <ChooseCompany onSearch={onSearch} />

  const rangeForm = (
    <RangeForm key={`${rawRange?.from ?? fallback.from}/${rawRange?.to ?? fallback.to}`}
               initial={rawRange ?? fallback} problem={problem} now={now}
               onApply={(next) => onNavigate(route, next, { keepFocus: true })} />
  )

  if (!pinned) {
    if (resolve.error && !resolve.isFetching
        && !(resolve.error instanceof AnalysisUnavailable && resolve.error.reason === 'session')) {
      return (
        <>
          <Heading ticker={ticker} />
          <Refused ticker={ticker} error={resolve.error} onSearch={onSearch}
                   onRetry={() => void resolve.refetch()} />
        </>
      )
    }
    if (fresh && fresh.company.ticker !== ticker) {
      return (
        <>
          <Heading ticker={ticker} />
          <div className="rh-notice red" role="alert">
            <div>
              <strong>The current catalogue answered for a different symbol.</strong>
              <p>Asked for {ticker}, resolved {fresh.company.ticker}. Nothing is shown
                 under a label it does not belong to. Search for the company again.</p>
            </div>
          </div>
        </>
      )
    }
    return (
      <>
        <Heading ticker={ticker} />
        <Loading label={`Resolving ${ticker} to its current company and US primary…`} />
      </>
    )
  }

  const data = query.data
  const mismatch = data !== undefined && (
    data.company.id !== route.companyId || data.instrument.id !== route.instrumentId
    || data.company.ticker !== ticker)

  return (
    <>
      <Heading ticker={ticker} name={data && !mismatch ? data.company.name : null} />
      <section className="rh-panel rh-pad rh-an-controls" aria-label="Company and window">
        <div className="rh-an-company">
          <span className="rh-mark" aria-hidden="true">{ticker.slice(0, 2)}</span>
          <div>
            <p className="rh-an-companyname">{data && !mismatch ? (data.company.name ?? ticker) : ticker}</p>
            <p className="muted small">
              Pinned by ID: company {route.companyId} · instrument {route.instrumentId}
            </p>
          </div>
          <button type="button" className="rh-button" onClick={onSearch}>
            Find another company
          </button>
        </div>
        {rangeForm}
      </section>

      {range === null ? (
        <div className="rh-empty rh-an-empty">
          <h2>No window to show.</h2>
          <p>The dates in the address are not a window this page can ask for.
             Correct them above; nothing was fetched for a guessed range.</p>
        </div>
      ) : mismatch ? (
        <div className="rh-notice red" role="alert">
          <div>
            <strong>The answer did not match this link.</strong>
            <p>The store answered for a different company or instrument than the
               address pins. Nothing is shown. Search for the company again to
               resolve today's mapping.</p>
          </div>
        </div>
      ) : data === undefined ? (
        query.isError
          ? <Refused ticker={ticker} error={query.error} onSearch={onSearch}
                     onRetry={() => void query.refetch()} />
          : <Loading label={`Reading ${ticker}, ${dayLabel(range.from)} to ${dayLabel(range.to)}…`} />
      ) : (
        <Body payload={data} stale={query.isError ? query.error : null}
              fetching={query.isFetching}
              onRetry={() => void query.refetch()} />
      )}
    </>
  )
}

function Heading({ ticker, name = null }: { ticker?: string; name?: string | null }) {
  return (
    <div className="rh-heading rh-an-heading">
      <div>
        <h1>Explore{ticker ? ` · ${ticker}` : ''}</h1>
        {/* The scope stays on the page at every width: the top bar drops its
            venue half on a phone. */}
        <p className="rh-an-scope">US primary · USD</p>
        <p>
          <strong className="rh-an-retro">Retrospective</strong> — current retained
          records may include later corrections.
          {name ? ` ${name}.` : ''}
        </p>
      </div>
    </div>
  )
}

function ChooseCompany({ onSearch }: { onSearch: () => void }) {
  return (
    <>
      <Heading />
      <div className="rh-empty rh-an-empty">
        <h2>Choose a company to explore.</h2>
        <p>
          Explore shows a company's current native-USD US primary instrument:
          daily closes and independently counted retained mentions for up to
          seven completed UTC days. It works with no prices or no chatter — it
          says which is missing rather than inventing a zero.
        </p>
        <button type="button" className="rh-button primary" onClick={onSearch}>
          Find a company
        </button>
      </div>
    </>
  )
}

function Refused({ ticker, error, onSearch, onRetry }: {
  ticker: string
  error: unknown
  onSearch: () => void
  onRetry: () => void
}) {
  const known = error instanceof AnalysisUnavailable ? error : null
  const title = known?.reason === 'missing' ? `No current company or instrument for ${ticker}.`
    : known?.reason === 'conflict' ? `This link no longer matches today's mapping for ${ticker}.`
    : known?.reason === 'unsupported' ? `${ticker} has no native-USD US primary this page can show.`
    : known?.reason === 'timeout' ? 'The analysis did not answer in time.'
    : known?.reason === 'limit' ? 'The read exceeded its bounds.'
    : 'This analysis could not be loaded.'
  const message = known?.message ?? 'Something went wrong.'
  // The title already says it for a timeout or a limit; do not say it twice.
  const detail = message === title ? null : message
  const stale = known?.reason === 'conflict' || known?.reason === 'missing'
  return (
    <div className="rh-empty rh-an-empty" role="alert">
      <h2>{title}</h2>
      <p>{detail}{known?.code ? ` (${known.code})` : ''}</p>
      {stale ? (
        <p>An old link is not silently retargeted to whatever the symbol means
           today. Selecting the company from search resolves its current mapping again.</p>
      ) : null}
      <div className="rh-empty-actions">
        {!stale ? <button type="button" className="rh-button" onClick={onRetry}>Retry</button> : null}
        <button type="button" className="rh-button primary" onClick={onSearch}>Find a company</button>
      </div>
    </div>
  )
}

const quoted = (value: string) => (value === '' ? '(empty)' : `“${value}”`)

function RangeForm({ initial, problem, onApply, now }: {
  initial: { from: string; to: string }
  problem: string | null
  onApply: (range: Range) => void
  now: () => Date
}) {
  const [from, setFrom] = useState(initial.from)
  const [to, setTo] = useState(initial.to)
  // The problem the reader is looking at and the values it is about: the
  // address's own strings until the reader submits something else.
  const [local, setLocal] = useState<{ problem: string; from: string; to: string } | null>(null)
  const shown = local ?? (problem ? { problem, from: initial.from, to: initial.to } : null)
  const submit = (event: FormEvent) => {
    event.preventDefault()
    const found = rangeProblem({ from, to }, now())
    if (found) { setLocal({ problem: found, from, to }); return }
    setLocal(null)
    onApply({ from, to })
  }
  // Text, not type="date": a browser empties a date input whose value is not
  // a real date, and then the reader cannot see or correct what was wrong.
  const field = (label: string, name: string, value: string, set: (value: string) => void) => (
    <label className="rh-field">
      {label}
      <input type="text" name={name} value={value} inputMode="numeric"
             placeholder="YYYY-MM-DD" autoComplete="off" spellCheck={false} maxLength={32}
             aria-invalid={shown ? true : undefined}
             aria-describedby={shown ? 'rh-an-rangeproblem' : 'rh-an-rangehint'}
             onChange={(event) => set(event.target.value)} />
    </label>
  )
  return (
    <form className="rh-an-range" onSubmit={submit} noValidate>
      {field('From (UTC day)', 'analysis_from', from, setFrom)}
      {field('To (UTC day)', 'analysis_to', to, setTo)}
      <button type="submit" className="rh-button primary">Show these days</button>
      {shown ? (
        <p id="rh-an-rangeproblem" className="rh-an-rangeproblem warning" role="alert">
          {RANGE_PROBLEM_TEXT[shown.problem as keyof typeof RANGE_PROBLEM_TEXT] ?? shown.problem}
          {` Asked for ${quoted(shown.from)} to ${quoted(shown.to)}.`}
        </p>
      ) : (
        <p id="rh-an-rangehint" className="muted small rh-an-rangehint">
          1 to 7 completed UTC days, written YYYY-MM-DD; the default is the last seven.
        </p>
      )}
    </form>
  )
}

function Body({ payload, stale, fetching, onRetry }: {
  payload: AnalysisPayload
  stale: unknown
  fetching: boolean
  onRetry: () => void
}) {
  const price = payload.price
  const chatter = payload.chatter
  const [picked, setPicked] = useState<string | null>(null)
  // A short status for a screen reader when the reader picks a day; the
  // detail region itself is not live, so its tables are not re-read.
  const [announcement, setAnnouncement] = useState('')
  // The selection belongs to one answer: a new window starts on its last
  // usable close, or its last day.
  const selected = picked !== null && price.days.some((d) => d.date === picked)
    ? picked : (price.last_usable ?? price.days[price.days.length - 1]?.date ?? null)
  const priceDay = price.days.find((d) => d.date === selected) ?? null
  const chatterDay = chatter.days.find((d) => d.date === selected) ?? null
  const observedDays = chatter.days.filter((d) => d.coverage === 'observed').length
  const partialDays = chatter.days.filter((d) => d.coverage === 'partial').length
  const unavailableDays = chatter.days.filter((d) => d.coverage === 'unavailable').length

  const select = (day: string) => {
    setPicked(day)
    const close = price.days.find((d) => d.date === day)
    const count = chatter.days.find((d) => d.date === day)
    if (!close || !count) return
    const closeText = close.state === 'observed' && close.close !== null
      ? `close ${formatClose(close.close)} USD` : priceStateLabel(close)
    setAnnouncement(`${dayLabel(day, true)}: ${closeText}; ${chatterLabel(count)}.`)
  }

  return (
    <div className="rh-an-body">
      {stale ? (
        <div className="rh-notice amber" role="status">
          <div>
            <strong>Showing the answer read {stampUtc(payload.read_started_at)}.</strong>
            <p>{stale instanceof Error ? stale.message : 'The refresh did not complete.'} This
               is the last successful read, not a fresh one.</p>
          </div>
          <button type="button" className="rh-button rh-retry" onClick={onRetry} disabled={fetching}>
            Retry
          </button>
        </div>
      ) : null}
      <p className="rh-visually-hidden" role="status" aria-live="polite">{announcement}</p>

      <section className="rh-panel rh-an-identity" aria-label="Instrument identity">
        <dl>
          <div><dt>Scope</dt><dd>US primary · USD · all retained sources</dd></div>
          <div><dt>Instrument</dt><dd>{payload.instrument.venue} ({payload.instrument.mic}) · {payload.instrument.provider_symbol}</dd></div>
          <div><dt>Mapped</dt><dd>{stampUtc(payload.instrument.mapped_at)}</dd></div>
          <div><dt>Company record since</dt><dd>{stampUtc(payload.company.first_seen)}</dd></div>
          <div><dt>Identity</dt><dd>today's mapping, applied retrospectively</dd></div>
          <div><dt>Read</dt><dd>{stampUtc(payload.read_started_at)}</dd></div>
        </dl>
      </section>

      <div className="rh-an-columns">
        <div className="rh-an-mainstack">
          <div className="rh-an-coverage">
            <section className="rh-panel rh-pad" aria-label="Price coverage">
              <h2 className="rh-an-h2 price">Daily closes</h2>
              <p className="rh-an-figure">
                <b className="num">{price.usable_count}</b> of {price.days.length} days observed
              </p>
              <p className="muted small">
                {price.first_usable
                  ? `${dayLabel(price.first_usable)} to ${dayLabel(price.last_usable as string)} in this window.`
                  : 'No usable close in this window.'}
                {price.interior_modeled_missing === null
                  ? ' Interior gaps not assessable.'
                  : price.interior_modeled_missing.length === 0
                    ? ' No interior modeled-open day is missing.'
                    : ` Missing on ${price.interior_modeled_missing.length} modeled-open day(s): ${price.interior_modeled_missing.map((d) => dayLabel(d)).join(', ')}.`}
                {price.regime_changed ? ' Source or basis changed inside the window.' : ''}
                {' Official session completeness: unknown.'}
              </p>
            </section>
            <section className="rh-panel rh-pad" aria-label="Chatter coverage">
              <h2 className="rh-an-h2 chatter">Retained mentions</h2>
              <p className="rh-an-figure">
                <b className="num">{observedDays}</b> observed · <b className="num">{partialDays}</b> partial · <b className="num">{unavailableDays}</b> unavailable
              </p>
              <p className="muted small">
                Observed counts; historical source set not verified.
                {chatter.first_observed
                  ? ` Buckets from ${stampUtc(chatter.first_observed)} to ${stampUtc(chatter.last_observed)}.`
                  : ' No retained bucket in this window.'}
              </p>
            </section>
          </div>

          <section className="rh-panel rh-pad" aria-label="Daily closes and retained mention counts">
            <AnalysisChart payload={payload} selected={selected} onSelect={select} />
          </section>

          {priceDay && chatterDay ? <DayDetail price={priceDay} chatter={chatterDay} /> : null}

          <DailyTable payload={payload} selected={selected} onSelect={select} />
        </div>

        <aside className="rh-an-rail" aria-label="Provenance and limits">
          <section className="rh-panel rh-pad">
            <h2 className="rh-an-h2">What these are</h2>
            <ul className="rh-an-list">
              <li>Counts are stored mention observations across every retained
                  source for this ticker — not unique people or posts, and not
                  sentiment. Original posts and judgments may have expired and
                  are not read here.</li>
              <li>Closes are the stored daily close for this instrument in USD.
                  The split stamp is a declared basis, not a verified adjustment
                  vintage. No return is calculated.</li>
              <li>Trading-day hints come from a modeled NYSE calendar for known
                  US MICs; unscheduled closures and halts are unknown.</li>
              <li>No promise that today's mapping, name, source set or close was
                  known on that date.</li>
            </ul>
          </section>
          <section className="rh-panel rh-pad">
            <h2 className="rh-an-h2">Notes from this read</h2>
            {payload.warnings.length ? (
              <ul className="rh-an-list">
                {payload.warnings.map((warning) => <li key={warning}>{warning}</li>)}
              </ul>
            ) : <p className="muted small">None.</p>}
          </section>
        </aside>
      </div>
    </div>
  )
}

const rows = (n: number) => `${n} source-bucket row${n === 1 ? '' : 's'}`

function DayDetail({ price, chatter }: { price: PriceDay; chatter: ChatterDay }) {
  return (
    <section className="rh-panel rh-pad rh-an-detail" aria-label={`Selected day, ${dayLabel(price.date, true)}`}>
      <h2 className="rh-an-h2">{dayLabel(price.date, true)}</h2>
      <div className="rh-an-detailcols">
        <dl>
          <div><dt>Close</dt>
            <dd>{price.state === 'observed' && price.close !== null
              ? `${formatClose(price.close)} USD` : priceStateLabel(price)}</dd></div>
          {price.reason ? <div><dt>Why</dt><dd>{price.reason}</dd></div> : null}
          <div><dt>Source · basis</dt>
            <dd>{price.source ? `${price.source} · ${price.price_basis ?? '?'} · ${price.adjustment_basis ?? '?'}` : 'no retained row'}</dd></div>
          <div><dt>Fetched</dt><dd>{stampUtc(price.fetched_at)}</dd></div>
          <div><dt>Calendar</dt><dd>{price.calendar_hint.replace('_', ' ')}</dd></div>
        </dl>
        <dl>
          <div><dt>Retained mentions</dt><dd>{chatterLabel(chatter)}</dd></div>
          <div><dt>Coverage</dt>
            <dd>{chatter.coverage}{chatter.config_transition ? ' · config changed' : ''}
              {chatter.identity_excluded_slots ? ` · ${rows(chatter.identity_excluded_slots)} before the company record excluded` : ''}
              {chatter.excluded_rows ? ` · ${rows(chatter.excluded_rows)} off the 15-minute grid or repeated, excluded` : ''}</dd></div>
          <div><dt>Source set</dt><dd>historical completeness unknown</dd></div>
        </dl>
      </div>
      {chatter.sources.length ? (
        <div className="rh-tablewrap rh-an-sources" tabIndex={0} role="region"
             aria-label="Per-source buckets (scrollable)">
          <table className="rh-table">
            <caption className="rh-visually-hidden">
              Per-source buckets for {dayLabel(chatter.date, true)}: the slot columns
              divide the day's 96 quarter-hours; excluded rows sit outside them
            </caption>
            <thead>
              <tr>
                <th scope="col">Source</th>
                <th scope="col" className="right">Mentions</th>
                <th scope="col" className="right">ok</th>
                <th scope="col" className="right">truncated</th>
                <th scope="col" className="right">missing</th>
                <th scope="col" className="right">absent</th>
                <th scope="col" className="right">invalid</th>
                <th scope="col" className="right">excluded rows</th>
                <th scope="col">Config</th>
                <th scope="col">Coverage</th>
              </tr>
            </thead>
            <tbody>
              {chatter.sources.map((source) => (
                <tr key={source.source}>
                  <th scope="row">{source.source}</th>
                  <td className="right num">{source.mentions ?? '—'}</td>
                  <td className="right num">{source.ok_slots}</td>
                  <td className="right num">{source.truncated_slots}</td>
                  <td className="right num">{source.missing_slots}</td>
                  <td className="right num">{source.absent_slots}</td>
                  <td className="right num">{source.invalid_slots}</td>
                  <td className="right num">{source.excluded_rows ?? 0}</td>
                  <td>{source.config_versions.map((c) => c ?? 'unknown').join(' → ')}{source.transition ? ' (changed)' : ''}</td>
                  <td>{source.coverage.replace(/_/g, ' ')}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      ) : <p className="muted small">No retained source buckets on this day.</p>}
    </section>
  )
}

function DailyTable({ payload, selected, onSelect }: {
  payload: AnalysisPayload
  selected: string | null
  onSelect: (day: string) => void
}) {
  return (
    <section className="rh-panel rh-an-tablepanel" aria-label="Daily table">
      <div className="rh-tablewrap" tabIndex={0} role="region" aria-label="Daily table (scrollable)">
        <table className="rh-table rh-an-table">
          <caption className="rh-visually-hidden">Every requested day with its close and retained mention count</caption>
          <thead>
            <tr>
              <th scope="col">Day (UTC)</th>
              <th scope="col" className="right">Close USD</th>
              <th scope="col">Price state</th>
              <th scope="col" className="right">Mentions</th>
              <th scope="col">Chatter coverage</th>
              <th scope="col">Sources</th>
            </tr>
          </thead>
          <tbody>
            {payload.price.days.map((day, index) => {
              const chatter = payload.chatter.days[index]!
              const isSelected = selected === day.date
              return (
                <tr key={day.date} className={isSelected ? 'selected' : undefined}>
                  <th scope="row">
                    <button type="button" className="rh-textbutton" onClick={() => onSelect(day.date)}
                            aria-current={isSelected ? 'true' : undefined}>
                      {dayLabel(day.date)}
                    </button>
                  </th>
                  <td className="right num">{day.state === 'observed' && day.close !== null ? formatClose(day.close) : '—'}</td>
                  <td>{priceStateLabel(day)}{day.state === 'observed' && day.source ? ` · ${day.source}` : ''}</td>
                  <td className="right num">{chatter.mentions === null || chatter.overlap_ambiguous ? '—' : chatter.mentions}</td>
                  <td>{chatterLabel(chatter)}</td>
                  <td>{chatter.sources.filter((s) => s.mentions !== null).length} of {chatter.sources.length} with data</td>
                </tr>
              )
            })}
          </tbody>
        </table>
      </div>
    </section>
  )
}
