// Operations, read-only.
//
// Everything here is a summary the application already computes for its own
// use. Nothing on this page fetches from a provider, and nothing on it can
// start, stop, retry or retrain anything: a page that can act is a page that
// can be made to act by accident, and none of these pipelines has an undo.
//
// The spend figure is what the model API was billed, and it says so. The judge
// runs locally and is priced at zero by that meter -- reading the number as
// "no cost" would be a claim about infrastructure it knows nothing about.
import { useQuery } from '@tanstack/react-query'

import { BoardUnavailable, fetchOps } from '../api'
import { Forbidden, Loading, Unavailable } from './PageState'
import { REFRESH_MS } from './queries'

export function Admin() {
  const query = useQuery({
    queryKey: ['radar-hub', 'ops'],
    queryFn: ({ signal }) => fetchOps(signal),
    staleTime: REFRESH_MS,
    retry: (count, error) => {
      const reason = (error as { reason?: string })?.reason
      return reason !== 'session' && reason !== 'forbidden' && count < 2
    },
  })

  if (query.error && !query.data) {
    if (query.error instanceof BoardUnavailable
        && query.error.reason === 'forbidden') {
      return <Forbidden what="Administration" />
    }
    return <Unavailable error={query.error} retry={() => void query.refetch()} />
  }
  if (!query.data) return <Loading label="Loading operations…" />

  const ops = query.data
  return (
    <>
      <div className="rh-heading">
        <div>
          <h1>Administration</h1>
          <p>
            What the pipelines are doing, as of {stamp(ops.generated_at)}.
            Read-only: there is nothing here to start, stop or retry.
          </p>
        </div>
      </div>

      <div className="rh-opsgrid">
        <Panel title="Ingestion and capture">
          <Fact label="Board archive">
            {ops.capture.latest_observed_at === null
              ? 'Nothing captured yet'
              : `Newest ${stamp(ops.capture.latest_observed_at)}`}
          </Fact>
          <p className="rh-caption">
            The archive keeps two fixed board selections per quarter-hour. It
            is off until it is switched on, and a gap in it is a capture that
            failed rather than a quiet market.
          </p>
        </Panel>

        <Panel title="Judgment pipeline">
          <Fact label="Waiting to be judged">{ops.sentiment.pending}</Fact>
          {ops.sentiment.gated_pending !== undefined ? (
            <Fact label="Held back by the gate">{ops.sentiment.gated_pending}</Fact>
          ) : null}
          <Fact label="Oldest unjudged (p95)">
            {ops.sentiment.p95_age_minutes === null
              ? 'Not measured'
              : `${ops.sentiment.p95_age_minutes} min`}
          </Fact>
          <Fact label="Review tier">
            {`${ops.sentiment.review.served} served of ${ops.sentiment.review.demanded} demanded`}
            {ops.sentiment.review.capped
              ? ` · ${ops.sentiment.review.capped} capped` : ''}
          </Fact>
        </Panel>

        <Panel title="Model API spend">
          <Fact label="Today">{money(ops.spend.today_usd)}</Fact>
          <Fact label="This month">{money(ops.spend.month_usd)}</Fact>
          <Fact label="Unpriced tokens">
            {ops.spend.unpriced_tokens.toLocaleString('en-US')}
          </Fact>
          <p className="rh-caption">
            Spend, never a balance, and model API only — it is not the cost of
            running Radar. Work done by a local model is priced at zero here
            and is not free.
          </p>
        </Panel>

        <Panel title="Market data">
          <Fact label="Newest grouped close">
            {ops.market_data.grouped_closes.latest_accepted_date ?? 'None accepted'}
          </Fact>
          <Fact label="Gaps awaiting retry">
            {ops.market_data.grouped_closes.retryable_gaps.length}
          </Fact>
          {ops.market_data.grouped_closes.error_code ? (
            <Fact label="Last error">
              {ops.market_data.grouped_closes.error_code}
              {ops.market_data.grouped_closes.http_status
                ? ` (${ops.market_data.grouped_closes.http_status})` : ''}
            </Fact>
          ) : null}
          <Fact label="German download budget">
            {`${ops.market_data.de_download_budget_24h.spent} of `
             + `${ops.market_data.de_download_budget_24h.limit} used`}
          </Fact>
          <Fact label="Quote basis, 24h">
            {Object.entries(ops.market_data.quote_basis_24h)
              .map(([basis, count]) => `${basis} ${count.toLocaleString('en-US')}`)
              .join(' · ') || 'No quotes stored'}
          </Fact>
        </Panel>

        <Panel title="Collection cycles">
          {Object.keys(ops.market_data.cycles).length === 0
            ? <p className="muted small">No cycle has been recorded.</p>
            : (
              <ul className="rh-facts-list">
                {Object.entries(ops.market_data.cycles).map(([key, cycle]) => (
                  <li key={key}>
                    <strong>{key}</strong> — {cycle.status}
                    {cycle.error_code ? ` (${cycle.error_code})` : ''},
                    {' '}{cycle.files_accepted} of {cycle.files_seen} files,
                    {' '}{cycle.selected.toLocaleString('en-US')} selected
                  </li>
                ))}
              </ul>
            )}
        </Panel>
      </div>
    </>
  )
}

function Panel({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <section className="rh-panel rh-pad">
      <h2>{title}</h2>
      <div className="rh-facts-rows">{children}</div>
    </section>
  )
}

function Fact({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div className="rh-factrow">
      <span className="muted">{label}</span>
      <strong className="num">{children}</strong>
    </div>
  )
}

function money(value: number): string {
  return `$${value.toFixed(2)}`
}

function stamp(iso: string): string {
  try {
    return `${new Date(iso).toLocaleTimeString('en-GB',
      { hour: '2-digit', minute: '2-digit', timeZone: 'Europe/Berlin' })} Berlin`
  } catch {
    return 'an unknown time'
  }
}
