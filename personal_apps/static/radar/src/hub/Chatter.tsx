// Human chatter: what people are actually discussing, in the server's order.
//
// The list answers one question -- which of these is worth my time -- and
// hands the second, is this real, to Research. That split is why the row shows
// its evidence rather than a score: how far above its own normal, how many
// voices, which platforms were talking, and every qualification the server
// attached. A single number would rank the same companies while telling the
// reader nothing about whether to believe it.
//
// Nothing here is a recommendation. The rank is unusual chatter with price
// context, and the copy says so.
//
// The row is deliberately COMPACT. The first version let two cells set the
// height: it printed every concrete feed name, so a ticker seen on thirty
// subreddits filled most of the table width with the word Reddit, and it
// stacked three tone counts vertically. Both facts are still here -- the
// concrete feed identifiers and the exact tone counts -- inside a detail the
// reader opens, rather than as prose every row has to carry.
import { useId, useMemo, useRef, useState } from 'react'

import type { BoardPayload, Row, Selection } from '../types'
import { sourcePresentation, tonePresentation } from './chatterPresentation'
import type { SourcePresentation, TonePresentation } from './chatterPresentation'
import { Filters } from './Filters'
import { Empty } from './PageState'

export function Chatter({ board, selection, onOpen, onSelect }: {
  board: BoardPayload
  selection: Selection
  onOpen: (ticker: string) => void
  onSelect?: (next: Selection) => void
}) {
  const [filter, setFilter] = useState('')
  const needle = filter.trim().toLowerCase()
  const rows = useMemo(() => (
    needle
      ? board.rows.filter((row) => matches(row, needle))
      : board.rows
  ), [board.rows, needle])

  const excluded = Object.values(board.excluded ?? {})
    .reduce((total, count) => total + count, 0)

  return (
    <>
      <div className="rh-heading">
        <div>
          <p className="rh-datestamp">{contextLine(board)}</p>
          <h1>Human chatter</h1>
          <p>Find unusual discussion, then inspect the evidence.</p>
        </div>
      </div>

      {onSelect ? (
        <Filters board={board} selection={selection} onChange={onSelect} />
      ) : null}

      {board.rows.length === 0
        ? <EmptyBoard excluded={excluded} />
        : (
          <Panel board={board} rows={rows} filter={filter}
                 onFilter={setFilter} onOpen={onOpen} />
        )}
    </>
  )
}

function EmptyBoard({ excluded }: { excluded: number }) {
  // A quiet market and a stopped ingest are different situations, and
  // `excluded` is what tells them apart.
  if (excluded > 0) {
    return (
      <Empty title="Nothing cleared the floor in this window.">
        {excluded} {excluded === 1 ? 'company was' : 'companies were'} left out
        by the eligibility floor and the breadth filter. That is a quiet
        window, not a missing one.
      </Empty>
    )
  }
  return (
    <Empty title="No company cleared this selection.">
      Nothing was recorded as excluded by the eligibility floor or the breadth
      filter — a segment filter does not report itself that way. Widen the
      window or the feeds, or check Activity for whether the fetch ran.
    </Empty>
  )
}

function Panel({ board, rows, filter, onFilter, onOpen }: {
  board: BoardPayload
  rows: Row[]
  filter: string
  onFilter: (next: string) => void
  onOpen: (ticker: string) => void
}) {
  const total = board.rows.length
  const shown = rows.length
  return (
    <section className="rh-panel rh-chatterpanel">
      <div className="rh-panelhead">
        <div className="rh-panelheadtext">
          <h2>Ranked companies</h2>
          <p className="small muted">
            Unusual attention, with voices and sources in view.
          </p>
        </div>
        <div className="rh-panelheadtools">
          <label className="rh-field rh-search">
            <span>Filter companies</span>
            <input
              type="search"
              value={filter}
              placeholder="Ticker or name"
              onChange={(event) => onFilter(event.target.value)}
            />
          </label>
          <p className="small muted rh-panelcount">
            {shown === total
              ? `${total} ${total === 1 ? 'company' : 'companies'}`
              : `${shown} of ${total} shown`}
          </p>
        </div>
      </div>

      {shown === 0 ? (
        <div className="rh-panelempty">
          <Empty title="No company here matches that.">
            The filter runs over the {total}{' '}
            {total === 1 ? 'company' : 'companies'} already listed. Clearing it
            brings them back.
          </Empty>
        </div>
      ) : (
        <Table rows={rows} onOpen={onOpen} />
      )}

      <Foot board={board} shown={shown} />
    </section>
  )
}

/** The proportions the design contract sets at 1440, carried by a colgroup so
 *  the widest feed name can never decide them again. Percentages of the
 *  table's own content width; they add to 100. */
// A few points off the contract's 26/13/11/15/19/12/4, which it allows to
// avoid collisions: Sources takes two points from Attention and Voices so
// `Reddit · 4chan /biz/ · Bluesky` fits on one line at 1440, and Tone gives
// one back for the same reason.
const COLUMNS = ['26%', '12%', '10%', '18%', '18%', '12%', '4%']

function Table({ rows, onOpen }: {
  rows: Row[]; onOpen: (ticker: string) => void
}) {
  return (
    // Labelled and scrollable: the table may scroll inside this region, but
    // the document never scrolls sideways.
    <div className="rh-tablewrap" role="region" aria-label="Ranked companies"
         tabIndex={0}>
      <table role="table" className="rh-table rh-chatter">
        <colgroup>
          {COLUMNS.map((width, index) => (
            <col key={index} style={{ width }} />
          ))}
        </colgroup>
        <thead>
          <tr role="row">
            <th scope="col">Company</th>
            <th scope="col">Attention</th>
            <th scope="col">Voices</th>
            <th scope="col">Sources</th>
            <th scope="col">Tone</th>
            <th scope="col" className="right">Price · today</th>
            {/* The chevron's column. Named for a screen reader rather than
                left as an empty header, which reads as a missing one. */}
            <th scope="col"><span className="rh-visually-hidden">Open research</span></th>
          </tr>
        </thead>
        <tbody>
          {rows.map((row) => (
            <TickerRow key={row.ticker} row={row} onOpen={onOpen} />
          ))}
        </tbody>
      </table>
    </div>
  )
}

function TickerRow({ row, onOpen }: { row: Row; onOpen: (t: string) => void }) {
  const tone = tonePresentation(row.tone)
  const sources = sourcePresentation(row.activity_sources)
  return (
    <tr role="row">
      <th role="rowheader" scope="row" className="rh-company rh-col-company">
        <button type="button" className="rh-open" onClick={() => onOpen(row.ticker)}>
          <span className="rh-mark" aria-hidden="true">{row.ticker.slice(0, 2)}</span>
          <span className="rh-openname">
            <span className="rh-ticker" data-testid="rh-row-ticker">{row.ticker}</span>
            {/* Clamped to one line on the desk layout, never truncated in the
                accessible name: the text node is whole and `title` repeats
                it. A legal name is routinely longer than the column, and
                shortening the NAME rather than its display would be a lie
                about the company. */}
            <span className="rh-name" title={row.name ?? undefined}>
              {row.name ?? 'Name unknown'}
            </span>
          </span>
        </button>
        <Marks marks={row.marks} />
      </th>
      <Cell label="Attention" className="rh-col-attention">
        <Attention row={row} />
      </Cell>
      <Cell label="Voices" className="rh-col-voices">
        <strong className="num">{row.authors}</strong>
        {/* The backend's own meaning: distinct authors seen in the window, and
            the posts they wrote. Never "investors" and never "people" -- one
            person posting from three accounts is three authors here. */}
        <span className="rh-sub">
          {row.mentions} {row.mentions === 1 ? 'post' : 'posts'}
        </span>
      </Cell>
      <Cell label="Sources" className="rh-col-sources" testId="rh-row-sources">
        <Sources ticker={row.ticker} sources={sources} />
      </Cell>
      <Cell label="Tone" className="rh-col-tone">
        <ToneCell ticker={row.ticker} tone={tone} />
      </Cell>
      <Cell label="Price · today" className="right rh-col-price">
        <Price row={row} />
      </Cell>
      <Cell label="" className="rh-col-open">
        <button type="button" className="rh-chevron"
                onClick={() => onOpen(row.ticker)}>
          <span className="rh-visually-hidden">Open {row.ticker} research</span>
          <Chevron />
        </button>
      </Cell>
    </tr>
  )
}

function Chevron() {
  return (
    <svg className="rh-icon" viewBox="0 0 24 24" aria-hidden="true"
         focusable="false">
      <path d="m9 5 7 7-7 7" />
    </svg>
  )
}

/** How far above its own normal, when there is a normal worth dividing by.
 *  `ratio` null is phrasing.py's guard, decided once on the server -- the
 *  client never rebuilds it from mentions and expected. */
function Attention({ row }: { row: Row }) {
  if (row.ratio === null) {
    return (
      <>
        {/* The dash is decoration; "New here" beneath it is the reading, and
            it is what a screen reader gets. */}
        <strong aria-hidden="true">—</strong>
        <span className="rh-sub">
          New here{row.baseline_days !== null
            ? ` · ${row.baseline_days}-day baseline` : ''}
        </span>
      </>
    )
  }
  return (
    <>
      <strong className="num">{row.ratio.toFixed(1)}×</strong>
      <span className="rh-sub">its normal rate</span>
    </>
  )
}

/** The platforms that counted something, and every concrete feed behind them.
 *
 *  The compact form is a platform COUNT, not a list of labels: two subreddits
 *  are one platform, and printing `Reddit, Reddit` claimed a breadth that is
 *  not there while filling the column. The identifiers are not thrown away --
 *  they are one keystroke behind the summary. */
function Sources({ ticker, sources }: {
  ticker: string; sources: SourcePresentation
}) {
  if (sources.kind !== 'platforms') {
    return (
      <>
        <strong className="rh-tonequiet">{sources.label}</strong>
        {sources.summary ? <span className="rh-sub">{sources.summary}</span> : null}
      </>
    )
  }
  return (
    <>
      <strong className="num">{sources.label}</strong>
      {/* The summary IS the control. A separate "which feeds" link under it
          cost every row a line, which is how the row got tall in the first
          place -- and this correction exists because the rows were tall. */}
      <Detail label={`Which feeds counted for ${ticker}`}
              trigger={sources.summary ?? 'Which feeds'}>
        <p className="rh-detailnote">
          {sources.feedCount} {sources.feedCount === 1 ? 'feed' : 'feeds'}{' '}
          counted at least one post in this window, across{' '}
          {sources.platforms.length}{' '}
          {sources.platforms.length === 1 ? 'platform' : 'platforms'}. Feeds on
          the same platform share a site and an audience, so they do not
          corroborate one another.
        </p>
        <ul className="rh-detaillist">
          {sources.platforms.map((platform) => (
            <li key={platform.root}>
              <strong>{platform.label}</strong>
              <span>{platform.feeds.join(', ')}</span>
            </li>
          ))}
        </ul>
      </Detail>
    </>
  )
}

/** Tone as a share of the directional sample, with the sample size beside it.
 *
 *  The percentage and the bar have ONE denominator: the bullish and bearish
 *  signals. The residual is stated rather than folded in, because it holds
 *  balanced reads and unclassified ones together and neither is a vote for
 *  the middle. tonePresentation owns every rule; this only draws it. */
function ToneCell({ ticker, tone }: { ticker: string; tone: TonePresentation }) {
  const proportional = tone.bull !== null && tone.bear !== null
  return (
    <>
      <strong className={tone.kind === 'directional' ? 'num' : 'rh-tonequiet'}>
        {tone.label}
      </strong>
      {/* Drawn for every sampled row, empty track included, so the column does
          not jump between rows that have a reading and rows that do not.
          Colour never carries the meaning alone: the percentage above it is
          the reading, and this is its proportion. */}
      {tone.kind !== 'unavailable' ? (
        <span className="rh-tonebar" aria-hidden="true">
          {proportional && tone.bull! > 0
            ? <span className="bull" style={{ flexGrow: tone.bull! }} /> : null}
          {proportional && tone.bear! > 0
            ? <span className="bear" style={{ flexGrow: tone.bear! }} /> : null}
          {!proportional ? <span className="flat" style={{ flexGrow: 1 }} /> : null}
        </span>
      ) : null}
      {/* Same economy as the source cell: the sample line IS the control, so
          the exact counts cost the row no height at all.
          ------------------------------------------------------------------
          And no control at all when there is no sample line to hang it on. A
          row with nothing to count has nothing to break down, and giving it
          its own "how this is counted" link cost a line on every row of a
          board where no tone has been read yet -- which is exactly the board
          the local development copy produces. The footer's "How to read
          this" still explains the column. */}
      {tone.sample ? (
        <Detail label={`How ${ticker}’s tone is counted`} trigger={tone.sample}>
          <p className="rh-detailnote">{tone.detail}</p>
        </Detail>
      ) : null}
    </>
  )
}

/** A disclosure that opens in place.
 *
 *  In place rather than floating: the table scrolls inside its own region, and
 *  anything absolutely positioned in a cell would be clipped by that scroll
 *  box. A row that grows while it is open is at least honest about what it is
 *  showing.
 *
 *  Escape closes it and returns focus to the control that opened it. A reader
 *  who opened it from the keyboard otherwise has nowhere obvious to go back
 *  to. Rendered always and hidden with the attribute rather than unmounted,
 *  so `aria-controls` points at something that exists. */
function Detail({ label, trigger, children }: {
  label: string; trigger: string; children: React.ReactNode
}) {
  const [open, setOpen] = useState(false)
  const id = useId()
  const button = useRef<HTMLButtonElement>(null)
  return (
    <span
      className="rh-detail"
      onKeyDown={(event) => {
        if (event.key !== 'Escape' || !open) return
        // Stopped here so Escape closes THIS and does not travel on to
        // whatever else on the page listens for it.
        event.stopPropagation()
        setOpen(false)
        button.current?.focus()
      }}
    >
      <button
        type="button"
        ref={button}
        className="rh-detailtoggle"
        aria-expanded={open}
        aria-controls={id}
        // The visible text is the figure, which is not a name for a control.
        // The label says what opening it does.
        aria-label={label}
        onClick={() => setOpen((was) => !was)}
      >
        <span className="rh-sub">{trigger}</span>
      </button>
      <span className="rh-detailbody" id={id} role="group" aria-label={label}
            hidden={!open}>
        {children}
      </span>
    </span>
  )
}

function Price({ row }: { row: Row }) {
  const { quote } = row
  if (quote.quality === 'unavailable' || row.price === null) {
    return (
      <>
        <strong aria-hidden="true">—</strong>
        <span className="rh-sub">Price unavailable</span>
      </>
    )
  }
  const move = row.price_move
  return (
    <>
      <strong className="num">
        {formatPrice(row.price, quote.currency)}
      </strong>
      <span className={`rh-sub num ${moveClass(move)}`}>
        {move === null ? 'Move unknown' : `${move > 0 ? '+' : ''}${(move * 100).toFixed(1)}%`}
      </span>
    </>
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

/** What the numbers above mean, once, under the table.
 *
 *  Once is the point. The rejected version repeated its warnings in every
 *  cell, which is how a caveat stops being read. */
function Foot({ board, shown }: { board: BoardPayload; shown: number }) {
  return (
    <div className="rh-tablefoot">
      <p className="small muted rh-footline">
        <span>
          <strong>{shown}</strong>{' '}
          {shown === 1 ? 'company' : 'companies'} in view
        </span>
        <span>prices from {board.market_venue}</span>
        <span>
          attention compares equivalent hourly windows against each company’s
          own baseline
        </span>
      </p>
      <Detail label="How to read this table" trigger="How to read this">
        <dl className="rh-glossary">
          <dt>Attention</dt>
          <dd>
            How many times its own normal rate the discussion is running at,
            over equivalent windows. A company with too little history to have
            a normal shows an em dash and says so, rather than a ratio.
          </dd>
          <dt>Voices</dt>
          <dd>
            Distinct authors seen in the window, and the posts they wrote. One
            person posting from three accounts counts as three authors; this is
            not a count of investors.
          </dd>
          <dt>Sources</dt>
          <dd>
            Platforms with at least one counted post in this window. Feeds on
            the same platform — several subreddits, say — are one platform and
            do not corroborate each other. This display count is not what the
            breadth filter uses: that filter follows the scoring breadth, which
            counts every feed that was read, including the quiet ones.
          </dd>
          <dt>Tone</dt>
          <dd>
            Share of directional signals that are bullish. Signals may come
            from model judgments or keyword rules. The rest of the sample is
            unread or non-directional and is excluded from the percentage — it
            is not agreement that the outlook is neutral.
          </dd>
          <dt>Price · today</dt>
          <dd>
            The latest price this board has for the selected market, and the
            move across the window. An unavailable quote stays unavailable
            rather than rendering as a zero.
          </dd>
        </dl>
      </Detail>
    </div>
  )
}

const MARK_TEXT: Record<string, string> = {
  'no-print': 'No print',
  provisional: 'Provisional',
  'single-source': 'Single source',
  partial: 'Partial window',
  'warming-up': 'Warming up',
}

/** Rendered, never behind a hover. A qualification the reader has to discover
 *  is a qualification that did not happen -- so this is the one thing on the
 *  row allowed to make it taller. */
function Marks({ marks }: { marks: Row['marks'] }) {
  if (!marks.length) return null
  return (
    <p className="rh-marks">
      {marks.map((mark) => (
        <span key={mark} className="rh-badge amber">{MARK_TEXT[mark] ?? mark}</span>
      ))}
    </p>
  )
}

function matches(row: Row, needle: string): boolean {
  return row.ticker.toLowerCase().includes(needle)
    || (row.name ?? '').toLowerCase().includes(needle)
}

/** Both halves from the payload's own echo. Taking the venue from the board
 *  and the window from the request meant that, while a new window loaded, the
 *  previous window's rows sat under a heading naming the new one. */
function contextLine(board: BoardPayload): string {
  const hours = board.window_hours
  return `${board.market_venue} · last ${hours} ${hours === 1 ? 'hour' : 'hours'}`
    + ` · built ${stamp(board.generated_at)}`
}

/** The board's own build time, in the timezone the reader lives in. A board
 *  with no visible age is one nobody can tell is stale. */
function stamp(iso: string): string {
  try {
    return `${new Date(iso).toLocaleTimeString('en-GB',
      { hour: '2-digit', minute: '2-digit', timeZone: 'Europe/Berlin' })} Berlin`
  } catch {
    return 'time unknown'
  }
}

function Cell({ label, className, testId, children }: {
  label: string
  className?: string
  testId?: string
  children: React.ReactNode
}) {
  // An explicit role, because `display: block` in the stacked mobile layout
  // drops the implicit one; and a real element for the label rather than
  // generated content, because ::before is not part of a cell's accessible
  // name and cannot carry the header association a stacked table loses.
  //
  // Not aria-hidden. On the desk layout the column header supplies the
  // association and this repeats it, which costs a word; below 700px the
  // header row is gone and this is the only thing naming the figure.
  return (
    <td role="cell" className={className} data-testid={testId}>
      {label
        ? <span className="rh-cell-label rh-visually-hidden">{label}</span>
        : null}
      {children}
    </td>
  )
}
