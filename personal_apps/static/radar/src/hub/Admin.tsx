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
import type { SelectedPriceOps } from './priceChart'
import { REFRESH_MS } from './queries'
import { sourceWord } from './selectedPriceGeometry'

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
          <Fact label="Held back by the gate">
            {ops.sentiment.gated_pending ?? 0}
          </Fact>
          {/* Unjudged mentions the pass can never reach. Without it, two
              zeroes above read as an empty backlog while a real tail sits
              behind them. */}
          <Fact label="Unreachable">{ops.sentiment.pinned_pending ?? 0}</Fact>
          <Fact label="Oldest unjudged (p95)">
            {ops.sentiment.p95_age_minutes === null
              ? 'Not measured'
              : `${Math.round(ops.sentiment.p95_age_minutes)} min`}
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
          <Fact label="Quote basis, 24h">
            {Object.entries(ops.market_data.quote_basis_24h)
              .map(([basis, count]) => `${basis} ${count.toLocaleString('en-US')}`)
              .join(' · ') || 'No quotes stored'}
          </Fact>
        </Panel>

        {ops.selected_price_ops ? <SelectedPricePanel ops={ops.selected_price_ops} /> : null}
      </div>
    </>
  )
}

/** Whether the source is actually acquiring, in words. "The charts are on" is
 *  a different claim from "the source is acquiring", and so is "the key
 *  variables hold something". */
const SOURCE_STATE_WORD: Record<string, string> = {
  active: 'acquiring',
  disabled: 'switched off',
  charts_off: 'selected charts switched off',
  credentials_missing: 'credentials not configured',
  yahoo: 'the historical Yahoo source is active instead',
}

/** One web process's selected-price acquisition, and it says so: every figure
 *  resets when that process restarts, and each web worker keeps its own. */
function SelectedPricePanel({ ops }: { ops: SelectedPriceOps }) {
  const outcomes = Object.entries(ops.counters)
    .filter(([, value]) => value > 0)
    .map(([name, value]) => `${name.replace(/_/g, ' ')} ${value}`)
    .join(' · ')
  const average = ops.latency.count ? ops.latency.sum_seconds / ops.latency.count : null
  // The server names where the worker count comes from; an older server that
  // does not is the same environment variable.
  const workersSource = ops.configured_web_workers_source || 'WEB_CONCURRENCY'
  return (
    <Panel title="Selected price charts">
      <Fact label="Scope">{`This web process (pid ${ops.pid})`}</Fact>
      <Fact label="Acquisition coordinator started">
        {ops.coordinator_started_at ? dayStamp(ops.coordinator_started_at) : 'not started in this process'}
      </Fact>
      <Fact label="Configured web workers">
        {typeof ops.configured_web_workers === 'number' && ops.configured_web_workers > 0
          ? `${ops.configured_web_workers} (from ${workersSource})`
          : `Unknown — ${workersSource} is not set to a positive number; each worker keeps its own limits`}
      </Fact>
      <Fact label="Chart / Alpaca switch">
        {`${ops.charts_enabled ? 'on' : 'off'} / ${ops.alpaca_enabled ? 'on' : 'off'}`}
      </Fact>
      <Fact label="Source">
        {`${ops.source ? sourceWord(ops.source) : 'None selected'} — `
          + `${SOURCE_STATE_WORD[ops.source_state ?? ''] ?? 'unknown'}`}
      </Fact>
      <Fact label="Credentials configured">{ops.credentials_present ? 'yes' : 'no'}</Fact>
      <Fact label="Acquiring now">{ops.in_flight ? 'yes' : 'no'}</Fact>
      <Fact label="Starts, last 60 s">
        {`${ops.rolling_starts_60s} of ${ops.limits?.starts_per_60s ?? 10}`}
      </Fact>
      <Fact label="Cached charts">
        {`${ops.cache_keys} · ${(ops.cache_bytes / 1024).toFixed(0)} KiB`}
      </Fact>
      <Fact label="Provider backoff until">
        {ops.backoff_until === null ? 'none' : stamp(ops.backoff_until)}
      </Fact>
      {ops.quarantined ? (
        <Fact label="Stopped">a fetch child could not be confirmed stopped</Fact>
      ) : null}
      <Fact label="Outcomes">{outcomes || 'none yet'}</Fact>
      <Fact label="Acquisition time">
        {average === null ? 'none yet'
          : `avg ${average.toFixed(2)} s · max ${ops.latency.max_seconds.toFixed(2)} s`}
      </Fact>
      <p className="rh-caption">{ops.note}</p>
    </Panel>
  )
}

const MONTHS = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec']

/** Day and time in Berlin, e.g. "15 Sep, 10:00 Berlin". A coordinator can be
 *  days old, so a bare clock time would read as today. Built from numeric
 *  parts: ICU spells en-GB September "Sept" in some builds. */
function dayStamp(iso: string): string {
  const when = new Date(iso)
  if (Number.isNaN(when.getTime())) return 'an unknown time'
  const parts = Object.fromEntries(new Intl.DateTimeFormat('en-GB', {
    day: 'numeric', month: 'numeric', hour: '2-digit', minute: '2-digit', hourCycle: 'h23',
    timeZone: 'Europe/Berlin',
  }).formatToParts(when).map((part) => [part.type, part.value]))
  return `${Number(parts.day)} ${MONTHS[Number(parts.month) - 1]}, ${parts.hour}:${parts.minute} Berlin`
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
  // Sub-cent spend is not zero, and this is the one tile whose caption is
  // about not misreading a zero.
  if (value > 0 && value < 0.01) return 'under $0.01'
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
