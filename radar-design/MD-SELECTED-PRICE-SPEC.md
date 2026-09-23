# Selected-instrument price charts — binding specification

2026-09-15. Assignment family MD-SELECTED-PRICE. Implements the owner-approved Research/shared Chatter chart improvement, MD-02/07 + first-adapter MD-10. MD-05 headline promotion stays deferred. Governing evidence: MD-SELECTED-PRICE-EVIDENCE-1-RULING.md; original research remains attributed and unchanged. HA1 is closed at daadf3868caedcb5db858378e919cba68b735f8a.

## 1. Product boundary

Improve **only** the selected stock's 1D/1W chart in the dark hub Research page and the shared research panel inside Human Chatter. Retain the current layout, cyan price line, sentiment-coloured chatter histogram, source selection, keyboard access, narrow-screen panning and longer-span controls. A newly loaded price chart must not replace the headline quote or change board scores. Analysis/HA1, legacy detail, German prices, 1M/6M/1Y/3Y, watch state, source ingestion and Finnhub polling keep their existing contracts.

Use one Yahoo chart source for native-USD mapped US-primary instruments. Do not assume the user's selected German listing is equivalent: use this path only when requested market is US and the resolved primary is eligible. Display the actual listing/venue and provider. No Nasdaq adapter, candles, volume indicator, return calculation, split-adjustment claim, recommendation, new classifier or polling study. No new external dependency or production schema migration.

Two flags, both default false: RADAR_SELECTED_PRICE_CHARTS_ENABLED enables the new hub chart contract; RADAR_SELECTED_PRICE_YAHOO_ENABLED additionally permits its outbound Yahoo acquisition. The second has no effect without the first. Local deterministic QA may enable charts with a fake transport; no production flag changes authorized by this packet. Chart flag off returns to the existing chart, rather than offering an empty new UI. The authenticated new route returns 404 with code feature_disabled when off. Supply the chart flag to the hub through its existing server bootstrap, never a browser-controlled provider switch.

This is a technical implementation scope. The usage-condition limitation in the ruling travels with the release carries; technical approval or existing Yahoo use does not establish provider permission. No further permission question is needed to implement and verify locally with fixtures. Live source activation/release is a separate owner-selected Deployer action, not this worker's task.

## 2. Window, time and identity

Compute windows using the existing America/New_York modeled US calendar without changing it. All wire instants are ISO UTC with Z. Display session dates in ET and hover times in the existing user-facing timezone, explicitly labelled. Hard lookup bound: 16 calendar days; fail with window_unavailable instead of inventing five sessions if the model cannot find them.

**1D:** if today is a modeled trading day and now is in [04:00 ET,20:00 ET), use today, from its extended open to now. Otherwise use the most recent trading day whose extended close is <= now, from its extended open to extended close. Price interval 60 seconds; includePrePost=true. At 04:00 the zero-length window is an explanatory waiting state, not division by zero. On early-close days respect the model's regular close and extended close; describe boundaries as modeled, not independently validated exchange facts.

**1W:** last five modeled trading sessions, including today only from its regular open onward. Before regular open, use five completed sessions. From = first session's regular open. To = now during the last session's regular session, otherwise that session's regular close. Regular-session prices only, 300-second bars. Chatter still covers the continuous from/to period, including intervening nights/weekends; closed bands describe price-market state, not chatter availability. Four completed sessions plus partial today is labelled '5 sessions · today partial'. Missing provider sessions do not redefine this expected window.

Build the exact upstream request from this computed from/to using existing period1/period2 transport, with end clipped to now. The research tested range=1d/5d; **do not claim equivalence**. Test emitted epoch parameters and normalization with recorded responses, and keep unexecuted live request-form compatibility explicit in the return. Do not silently substitute a shorter range when the service returns less data.

Resolve ticker to active company and exactly one current mapped US primary with nonempty provider symbol/MIC, USD currency, valid mapped_at and positive IDs. Use the existing eligibility rules by reference, without editing HA1. Return a fingerprint containing company ID, instrument ID, provider symbol, currency, MIC and mapped_at; revalidate against the current mapping on each response. The client discards responses for an old ticker, source selection, span or instrument fingerprint. Server takes no arbitrary upstream URL or browser-supplied symbol override.

Yahoo symbol conversion is adapter-local: ordinary symbols unchanged; a single class-share dot between alphanumeric components may map to a hyphen (BRK.B -> BRK-B), followed by full returned-symbol, currency and existing MIC/exchange allowlist validation. No speculative multi-symbol retries. Unknown forms refuse upstream and use stored data. Never mutate RadarInstrument.provider_symbol for this feature. XNMS is already in the current Yahoo allowlist; preserve it.

## 3. HTTP and data contract

New authenticated GET /radar/api/ticker/<ticker>/price-chart?span=1D|1W&market=us plus sources=<comma-separated existing source selection>. Accept only span, market and sources; reject duplicates/unknown keys and invalid source values through the existing parser semantics. No arbitrary from/to or provider parameters. Auth behavior follows ticker_detail; validate before any acquisition. Unsupported eligibility: 422 unsupported_instrument; unknown ticker: 404; malformed request: 400; bounded store failure: 503 store_unavailable/read_limit. An upstream failure alone is a 200 explanatory payload, not a whole-panel error.

Version-1 response (all keys required unless marked optional):

```typescript
type PriceChartResponse = {
  version: 1;
  identity: { ticker: string; company_id: number; instrument_id: number;
    mic: string; venue: string; currency: 'USD'; provider_symbol: string;
    mapped_at: string; fingerprint: string };
  span: '1D' | '1W'; generated_at: string;
  window: { from: string; to: string; timezone: 'America/New_York';
    session_dates: string[]; partial: boolean; calendar_basis: 'modeled';
    bands: { from: string; to: string; state: 'regular'|'premarket'|'afterhours'|'closed' }[] };
  acquisition: { state: 'ready'|'pending'|'backoff'|'busy'|'disabled'|'unavailable';
    retry_after_seconds: number | null; reason: string | null };
  price: null | { source: string; kind: 'bar_close'|'stored_quote'|'daily_close';
    currency: 'USD'; mic: string; price_basis: string;
    adjustment_basis: string; regimes: { id: string; source: string; price_basis: string; adjustment_basis: string }[]; received_at: string | null;
    cache_age_seconds: number | null; latest_observation_at: string | null;
    stale: boolean; fallback: boolean; interval_seconds: number | null;
    points: { at: string; start: string; end: string; value: number | null;
      provisional: boolean; break_before: boolean; regime: string }[] };
  chatter: { step_minutes: 15|60; from: string; to: string;
    slots: { start: string; end: string; count: number | null;
      coverage: 'observed'|'partial'|'unknown'; config_transition: boolean;
      truncated: boolean; overlap_ambiguous: boolean }[];
    tone: { basis: 'recorded-judgments'; slots: (null | {
      bullish: number; bearish: number; neutral: number; unjudged: number;
      unavailable: number; status: 'complete'|'partial'|'unavailable' })[] };
    normal_per_slot: null };
  warnings: string[];
};
```

Use 15-minute chatter slots for 1D and 60-minute slots for 1W, anchored at window.from (09:30 on 1W). Read the actual underlying 15-minute bucket rows for exactly the window; final clipped bucket is partial. Retained bucket counts are not exact intra-bucket event counts; mark the final bucket partial without prorating it. Return start/end for each histogram slot so an incomplete last slot does not shift the entire axis. Both arrays share window bounds, never array index. Price points are not aligned or resampled to chatter slots.

No ordinary-detail rolling-window chatter or sentiment array may be pasted onto this response. Keep the old detail endpoint unchanged and still use it for headline, posts and summary. Source/window labels beside those other sections retain their own scope; the new chart's accessible text explicitly describes its own dates/counts. The new chart has no fabricated 'normal' line: normal_per_slot=null, with the existing relative-chatter summaries elsewhere unchanged.

## 4. Normalization and fallback

Normalize Yahoo close arrays only after validating envelope, returned identity, parallel lengths, finite positive values, monotonic timestamps and response limits. interval_seconds is 60 or 300; basis is provider_bar_close, adjustment_basis='unknown'. Never substitute unadjusted or split_adjusted without evidence. A bar timestamp is its start: completed bar at=end; unfinished bar at=min(now,end), provisional=true. Latest observation is the plotted bar boundary, not an exact trade time. Preserve source bar interval in hover text.

An off-grid trailing quote-like point is not a completed interval: omit it from the bar series and disclose omission in quality text when present; retain the last normal-grid provisional bar if valid. Do not turn that off-grid point into a headline observation. Null/nonpositive bars become explicit null points. Missing expected bars break the next segment; break at session/market-state boundaries and regime boundaries. Never interpolate or draw straight across a missing/null bar. One valid point is a visible dot with its timestamp, not an unavailable line. Provider coverage may be partial without triggering wholesale substitution; show the available range and gaps.

On cold/pending/unavailable acquisition, fallback preference is **one coherent dataset**, same current instrument/native currency/MIC: 1D retained valid event-time RadarQuote rows inside this window; if none, eligible stored daily closes inside the window. 1W eligible stored daily closes only. Do not call history.resolve_basis or borrow another venue/currency. No last-three-anchor invention or combination of stored quote and daily datasets. Preserve provenance per regime, breaking on source/price/adjustment change. If multiple incompatible quote regimes compete, choose the source regime with the latest valid event and label its incomplete coverage; do not interleave providers. Never use future-fetched, pre-mapping, nonpositive or shadow rows. Store overflow refuses the fallback rather than silently sampling it. No point inside the requested window means price=null, with a reason; do not reach outside the chart for a daily dot.

Cache staleness is age since receipt, not age of the last price. Serve a cached Yahoo series fresh for 60s, stale with visible receipt age until 15min; beyond that use stored fallback/null. A recent fetch of an old last session is not 'live'. Never keep yesterday's cached window as today's session. A provider identity failure invalidates its matching cached data, not merely the new response.

## 5. Aligned chatter and retained tone

Query selected concrete historical sources using existing selection expansion, capped at 64. Read only this ticker and bounded window. Treat configured-source completeness as unknown: observed coverage means represented source buckets, not all real-world discussion. Carry status/config metadata; never aggregate mention_z.

Deduplicate source/bucket keys; identical duplicate rows count once; conflicting duplicates make that source-slot unknown. Bare Reddit plus subreddit overlap in a constituent bucket makes its total unknown rather than double-counted. Unknown/malformed/negative counts are not zeros. Sum valid represented source counts; truncated or missing represented-source buckets make the interval partial. No valid observations -> count=null. Only recorded valid zero contributions can yield observed zero. Changes of config in/between constituent buckets are flagged. Earlier than company/mapping identity floor is unknown. Never infer a stock's zero count solely from another stock being watched.

Preserve current tone rules from chatter_tone.classify_recorded_tone/reconcile_slot, backed only by retained recorded judgments. The tone array must reconcile to the **new** slot totals. Reuse the event aggregation with an injectable bounded reader where useful; retain old caller behavior and tests. Do not newly classify posts. Limit events to the intersection of the chart window and existing MENTION_EVENT_RETENTION_HOURS. When evidence expired, conflicts, times out or overflows, colour the affected count as unavailable, never neutral. A bounded tone failure should not discard otherwise valid price/count data. No new normal-rate or historical sentiment claim.

## 6. Acquisition without blocking the web request

Do not perform Yahoo I/O on the Flask request thread. A lazy per-web-process coordinator owns at most **one** active acquisition supervisor and **one** child fetch process, created only after fork and only on a validated cache miss. No waiting queue. Same-key callers share in-flight state; different-key callers get busy plus fallback and can retry later. The route returns its local data immediately; it never waits for the provider result. No extra service or daemon deployment.

Use a short-lived Python multiprocessing spawn child, with no Flask context, DB handle, inherited requests session or credentials. Only pass validated public request parameters and a one-way result channel. It uses the existing Yahoo transport in a cache-disabled mode; keep existing callers' default behavior. Bound body while streaming to 512 KiB; bound result-channel bytes to 512 KiB and reject oversized normalized results. Supervisor concurrently drains the channel so a full pipe cannot deadlock completion. Fixed provider hostname; no redirects to alternate hosts, cookies/crumbs, automatic HTTP retries or alternate symbols.

Supervisor uses a monotonic **6s deadline from child start**, including startup/read/parse; on expiry terminate, then kill if necessary, and reap. Cleanup allowance 1s; if cleanup cannot be confirmed, quarantine acquisition for that parent process and expose cleanup_failed rather than spawn another child. These are supervisor deadlines, not a hard HTTP end-to-end guarantee or OS scheduling promise. Child connection/read socket timeouts are additionally capped at 2s/3s. Test a hanging child and oversized response without a real provider. Process creation itself must happen off the request thread. Shutdown cleans owned processes; never terminate anything discovered by broad name/port search.

Fresh cache lookup and enqueue use a short lock; no I/O while holding it. Coalescing/cache scope is explicitly per process. Cap each process to **10 acquisition starts in any rolling 60s**, with at least 60s between starts for the same key; no token-bucket burst ambiguity, no retry inside an acquisition. Process restart resets local counters; this is not a provider-wide limit. Report configured worker multiplier and note other existing ingest traffic separately. No claim of global cross-process deduplication. At two workers maximum concurrent children is two; neither occupies its Flask worker waiting for Yahoo.

Key = version, provider, identity fingerprint, span, interval, pre/post policy and included session dates. Moving now/period2 is not part of the stable key. Clip cached output to response.window.to. Cache max 128 keys, 8 MiB serialized total, 256 KiB normalized price per key; LRU eviction under lock, no unbounded second transport cache. If one result exceeds its bound, reject instead of truncating. Provider-wide per-process 401/403/429 backoff uses existing 60/120/240/480/960/1800s ladder; honour longer valid Retry-After, saturating at one day and then requiring another eligible request after expiry. A capped value must be disclosed; never retry sooner than the supplied Retry-After (if longer than one day, mark administratively unavailable until the full supplied time). 5xx/timeout/invalid-body/empty: 60s cooldown, no retry. Classify 404 as unsupported for that key for 15min. Never log exception URLs containing secrets.

## 7. Local reader, errors and health

New reader owns bounded SQL; reuse HA1's SqlStore statement-deadline technique without editing HA1. Identity is checked before cache reuse; shared price cache contains no user/source-filtered data. A 30s process-local chart-data cache keyed by identity/window/source selection can avoid repeating count/tone/fallback queries during pending polls. Cap 64 entries/16 MiB; do not cache store failures as empty success. Mapping/source changes invalidate key reuse. Max 16 calendar days, 64 concrete sources, 98,304 source rows plus one sentinel, 20,000 quote rows plus sentinel, 32 daily rows plus sentinel; max normalized price 2,000 points. Reject overflow explicitly. Tone grouped source/bucket results have the same source-row bound.

Each local SQL statement gets <=1s server statement limit within a 3s monotonic reader budget; check after materialization and reduction. Identity, buckets, fallback and optional tone together <=8 SELECT statements on a cold request. Count/tone use projections/aggregates, no raw post bodies. Optional tone uses remaining budget and degrades to unavailable. Distinguish these application/statement limits from pool/network cancellation guarantees; verify on a fixture DB if one can be created safely. No claims of production latency from fake-store tests.

Add selected_price_ops to the existing admin-only /api/ops response, never trigger provider I/O from ops. Include process ID/start time, scope='process', enabled flags, in-flight/key count/bytes, rolling starts, backoff-until, success/empty/invalid/identity_mismatch/timeout/throttle/unsupported/served_stale/fallback/busy/cleanup_failed counters, and latency count/sum/max. Do not add per-ticker unbounded logs or a new monitoring service. Show a compact section in Admin with process-scope/reset wording; no new dashboard redesign. Browser errors expose stable codes and human text, never internal paths, raw responses or SQL.

## 8. Frontend behavior

Add one typed usePriceChart query shared by ChartSection's two consumers. Query key includes ticker, selected market/sources, span and feature mode; returned fingerprint is validated. No keepPreviousData across identity/span/selection. Active only for eligible US mode, flag enabled and 1D/1W. On pending, poll at 2s for at most five polls per acquisition attempt; then normal 60s refresh while visible. Respect retry_after_seconds; disabled/unsupported stop fast polls. No hidden-tab/unmounted polling, focus retry storms or board refresh caused by chart state. Cancel obsolete fetches; late replies never overwrite the current stock.

Use a dedicated SelectedPriceChart renderer and geometry helpers, sharing existing visual primitives when compatible. Avoid changing the old DetailChart/PriceChart meaning for other consumers. ChartSection chooses the new payload atomically (price + aligned chatter/tone + window). While first payload loads, show chart-local loading; do not overlay new price onto old counts. On endpoint failure retain a previous response only for the exact same identity/window/selection with visible age/error; otherwise show a retryable chart-local message. Feature-disabled or ineligible market uses the original chart component.

Preserve sentiment colours and unavailable category with recorded-evidence meaning. Hover and keyboard focus report actual price interval, provisional status, count interval, coverage and provenance. Use the actual last-session end label rather than 'now' on closed charts. Use discontinuous line segments; a price absent interval remains visible against session bands. Unknown adjustment is a short visible basis note. No directional return percentage is computed from this series. Chart counts are labelled by their own interval; other section totals may cover a different window and are not claimed as its text equivalent. Provide a concise chart-local accessible summary and keyboard-accessible observations.

## 9. Acceptance and delivery boundary

One implementation worker delivers the code plus focused deterministic tests, local synthetic reader/route checks and built-hub browser evidence. One independent focused Reviewer/QA follows. Do not repeat MD research, HA1 review, whole-universe measurements or unrelated tests. Acceptance cases and execution order are in MD-SELECTED-PRICE-PLAN.md. No live provider data is needed to implement. Exact period request behavior and source activation remain explicitly unverified until an authorized live run; do not disguise fixture responses as live evidence.

All application work happens in the new candidate worktree named in the plan. Protected source workspace, all unrelated dirty files, prior environments and production stay untouched. No commit/push/deployment by Implementer. The owner dispatches by pasting the prompt; a prepared prompt is not a running worker.
