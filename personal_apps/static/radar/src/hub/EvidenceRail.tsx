// Evidence at a glance: the selected company's row on this board, restated.
//
// Every figure here comes from the SAME board row the candidate rail drew,
// for the same window and the same feed selection. That is the whole point of
// the rail -- it is the row's own evidence, enlarged, beside the chart. It is
// deliberately NOT the detail response's counts: those are built from the
// per-mention evidence, which has a shorter retention than the bucket totals,
// so the two legitimately differ. Showing one under a heading that names the
// other's window would be the same defect the tone column was corrected for.
//
// When there is no row -- a company reached by search, or one the current
// filters exclude -- this says so rather than substituting numbers from
// somewhere else.
import type { Detail, Row } from '../types'
import { sourcePresentation, tonePresentation } from './chatterPresentation'
import type { TonePresentation } from './chatterPresentation'
import { Disclosure } from './Disclosure'

const MARK_TEXT: Record<string, string> = {
  'no-print': 'No print',
  provisional: 'Provisional',
  'single-source': 'Single source',
  partial: 'Partial window',
  'warming-up': 'Warming up',
}

/** What each qualification is a caution about. The server decides WHICH marks
 *  a row carries; this only says what the mark means, and there is one
 *  sentence per mark rather than a warning invented for every ticker. */
const MARK_WHY: Record<string, string> = {
  'no-print': 'The exchange is open and this tape has not printed recently, '
    + 'so the price beside it is older than it looks.',
  provisional: 'Part of this window is still being counted, so the figures '
    + 'can still move.',
  'single-source': 'Everything counted here came from one feed. One feed is '
    + 'one audience, not corroboration.',
  partial: 'The window is not fully covered by the data behind it, so the '
    + 'counts are a floor rather than a total.',
  'warming-up': 'There is not enough history for this company to have a '
    + 'normal rate worth dividing by yet.',
}

export function EvidenceRail({ ticker, row, detail, windowHours, marketVenue,
                              isWatched, onToggleWatch, watchPending,
                              watchError }: {
  ticker: string
  /** The selected company's row on the current board, or null when this
   *  board has none for it. */
  row: Row | null
  /** The detail response, when it has arrived. Used only for the
   *  concentration facts, which are labelled as coming from the per-post
   *  evidence rather than from the row. */
  detail: Detail | null
  windowHours: number
  marketVenue: string
  isWatched: boolean
  onToggleWatch?: (ticker: string) => void
  watchPending: boolean
  watchError: unknown
}) {
  const tone = row ? tonePresentation(row.tone) : null
  const sources = row ? sourcePresentation(row.activity_sources) : null
  return (
    <aside className="rh-evidence" aria-labelledby="rh-evidence-head">
      <div className="rh-evidencehead">
        <h2 id="rh-evidence-head">Evidence at a glance</h2>
        <p className="small muted">
          Human chatter for {ticker} · {marketVenue} · last {windowHours}{' '}
          {windowHours === 1 ? 'hour' : 'hours'}
        </p>
      </div>

      {row && tone && sources ? (
        <>
          <div className="rh-evidencegrid">
            <Figure
              label="Attention"
              value={row.ratio === null ? 'New here' : `${row.ratio.toFixed(1)}×`}
              note={row.ratio === null
                ? `Too little history to divide by${
                    row.baseline_days !== null
                      ? ` · ${row.baseline_days}-day baseline` : ''}`
                : 'vs this company’s own normal rate'}
              quiet={row.ratio === null}
            />
            <Figure
              label="Voices"
              value={String(row.authors)}
              note={`distinct authors · ${row.mentions} ${
                row.mentions === 1 ? 'post' : 'posts'}`}
            />
            <Figure
              label="Active platforms"
              value={sources.kind === 'platforms'
                ? String(sources.platforms.length) : '—'}
              note={sources.kind === 'platforms' ? null : sources.label}
              quiet={sources.kind !== 'platforms'}
            >
              {sources.kind === 'platforms' ? (
                <Disclosure label={`Which feeds counted for ${ticker}`}
                            trigger={sources.summary ?? 'Which feeds'}>
                  <p className="rh-detailnote">
                    {sources.feedCount}{' '}
                    {sources.feedCount === 1 ? 'feed' : 'feeds'} counted at
                    least one post in this window, across{' '}
                    {sources.platforms.length}{' '}
                    {sources.platforms.length === 1 ? 'platform' : 'platforms'}.
                    Feeds on the same platform share a site and an audience, so
                    they do not corroborate one another — and neither do
                    distinct platforms repeating the same claim.
                  </p>
                  <ul className="rh-detaillist">
                    {sources.platforms.map((platform) => (
                      <li key={platform.root}>
                        <strong>{platform.label}</strong>
                        <span>{platform.feeds.join(', ')}</span>
                      </li>
                    ))}
                  </ul>
                </Disclosure>
              ) : null}
            </Figure>
            <ToneFigure ticker={ticker} tone={tone} />
          </div>

          <NeedsChecking row={row} detail={detail} />
        </>
      ) : (
        <p className="muted small rh-evidencenone">
          This board has no row for {ticker} in the current window and feed
          selection, so its attention, voices, platforms and tone are
          unknown here. The panels beside this one are the company’s own
          detail and are unaffected.
        </p>
      )}

      <div className="rh-evidenceact">
        {onToggleWatch ? (
          <button
            type="button"
            className={`rh-button rh-watchbutton${isWatched ? '' : ' primary'}`}
            aria-pressed={isWatched}
            // Disabled until the write lands, so a second click cannot race
            // the first and leave the mark in whichever state answered last.
            disabled={watchPending}
            onClick={() => onToggleWatch(ticker)}
          >
            {watchPending ? 'Saving…' : isWatched ? '✓ Watching' : `Watch ${ticker}`}
          </button>
        ) : null}
        {watchError ? (
          <p className="rh-notice red rh-watcherror" role="alert">
            <span>
              <strong>That mark could not be saved.</strong> Your marks are
              unchanged.
            </span>
          </p>
        ) : null}
        <p className="rh-caption">
          Whether a matching listing is available in any particular broker,
          including Scalable, has not been verified.
        </p>
      </div>
    </aside>
  )
}

function Figure({ label, value, note, quiet, children }: {
  label: string
  value: string
  note?: string | null
  quiet?: boolean
  children?: React.ReactNode
}) {
  return (
    <div className="rh-figure">
      <p className="rh-figurelabel">{label}</p>
      <p className={`rh-figurevalue${quiet ? ' quiet' : ' num'}`}>{value}</p>
      {note ? <p className="rh-sub">{note}</p> : null}
      {children}
    </div>
  )
}

/** Tone keeps its two-segment directional contract: one denominator, the
 *  residual stated rather than folded in, and the bar never the only thing
 *  carrying the reading. */
function ToneFigure({ ticker, tone }: { ticker: string; tone: TonePresentation }) {
  const proportional = tone.bull !== null && tone.bear !== null
  return (
    <div className="rh-figure">
      <p className="rh-figurelabel">Tone</p>
      <p className={`rh-figurevalue${
        tone.kind === 'directional' ? ' num' : ' quiet'}`}>
        {tone.label}
      </p>
      {tone.kind !== 'unavailable' ? (
        <span className="rh-tonebar wide" aria-hidden="true">
          {proportional && tone.bull! > 0
            ? <span className="bull" style={{ flexGrow: tone.bull! }} /> : null}
          {proportional && tone.bear! > 0
            ? <span className="bear" style={{ flexGrow: tone.bear! }} /> : null}
          {!proportional ? <span className="flat" style={{ flexGrow: 1 }} /> : null}
        </span>
      ) : null}
      {tone.sample ? (
        <Disclosure label={`How ${ticker}’s tone is counted`}
                    trigger={tone.sample}>
          <p className="rh-detailnote">{tone.detail}</p>
        </Disclosure>
      ) : null}
    </div>
  )
}

/** The qualifications the server actually attached, and the concentration
 *  figures when the detail has arrived. Nothing is invented to fill the
 *  section: a company with no marks and no measured concentration says so. */
function NeedsChecking({ row, detail }: { row: Row; detail: Detail | null }) {
  const share = detail?.breakdown.top_author_share ?? null
  const twoShare = detail?.breakdown.top_two_share ?? null
  const hasConcentration = share !== null
  return (
    <section className="rh-checking" aria-labelledby="rh-checking-head">
      <h3 id="rh-checking-head">What needs checking</h3>
      {row.marks.length === 0 && !hasConcentration ? (
        <p className="muted small">
          The server attached no qualification to this row, and no author
          concentration has been measured for this window. That is an absence
          of flags, not a clean bill of health.
        </p>
      ) : (
        <ul className="rh-checklist">
          {row.marks.map((mark) => (
            <li key={mark}>
              <strong className="warning">{MARK_TEXT[mark] ?? mark}</strong>
              <span>{MARK_WHY[mark] ?? 'The server attached this qualification to the row.'}</span>
            </li>
          ))}
          {hasConcentration ? (
            <li>
              <strong className={share >= 0.5 ? 'warning' : undefined}>
                Loudest account is {(share * 100).toFixed(0)}% of the posts
              </strong>
              <span>
                {twoShare !== null
                  ? `The two loudest are ${(twoShare * 100).toFixed(0)}%. `
                  : ''}
                Counted from the per-post evidence behind this window, which is
                held for a shorter time than the totals above.
              </span>
            </li>
          ) : null}
        </ul>
      )}
    </section>
  )
}
