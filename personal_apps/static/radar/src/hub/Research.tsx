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
//
// This is the STANDALONE reading of a company: reached from a search on
// another page, from a watch list, or from an old bookmark. The chatter
// workspace renders the same pieces (hub/ResearchContent.tsx) beside its
// candidate rail. Both own exactly one `useDetail` for the company they have
// open.
import { exchangeLabel, segmentLabel } from '../format'
import type { PanelSpan, Selection } from '../types'
import { Loading } from './PageState'
import {
  ChartSection, EvidencePanel, NotHere, PostsPanel, Quote, Summary,
} from './ResearchContent'
import { useDetail } from './queries'
import { BoardUnavailable } from '../api'

export function Research({ ticker, selection, span, onSpan, onBack, onSearch,
                           watching, onToggleWatch, watchPending = false,
                           watchError, visible = true }: {
  ticker: string
  selection: Selection
  span: PanelSpan
  onSpan: (span: PanelSpan) => void
  onBack: () => void
  onSearch: () => void
  watching?: string[]
  onToggleWatch?: (ticker: string) => void
  watchPending?: boolean
  watchError?: unknown
  visible?: boolean
}) {
  const { data, error, isPlaceholderData, refetch } = useDetail(
    ticker, selection, span, visible)

  // Placeholder data is the PREVIOUS company's panel, kept so the layout does
  // not collapse between two fetches. Rendering it here would put one
  // company's name, price, chart and evidence under another company's
  // heading and URL -- which is the reader-facing half of "old replies may
  // not replace the current ticker".
  if (!data || isPlaceholderData) {
    if (error && !isPlaceholderData) {
      return <NotHere ticker={ticker} error={error} onBack={onBack}
                      onSearch={onSearch} retry={() => void refetch()} />
    }
    return <Loading label={`Loading ${ticker}…`} />
  }
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
            // Disabled until the write lands, so a second click cannot race
            // the first and leave the mark in whichever state answered last.
            disabled={watchPending}
            onClick={() => onToggleWatch(identity.ticker)}
          >
            {watchPending ? 'Saving…' : isWatched ? '✓ Watching' : 'Watch'}
          </button>
        ) : null}
      </div>

      {watchError ? (
        <div className="rh-notice red" role="alert">
          <div>
            <strong>That mark could not be saved.</strong>
            <p>
              {watchError instanceof BoardUnavailable ? watchError.message
                : 'The change was refused.'} Your marks are unchanged.
            </p>
          </div>
        </div>
      ) : null}

      <div className="rh-researchcols">
        <div className="rh-stack">
          <Quote detail={data} />
          <ChartSection chart={chart} quoteVenue={identity.quote.venue}
                        ticker={identity.ticker} span={span} onSpan={onSpan} />
          <EvidencePanel breakdown={breakdown} windowHours={selection.window} />
          <PostsPanel detail={data} />
        </div>

        <Summary detail={data} />
      </div>
    </>
  )
}
