# HA1 US Daily Explore — binding specification

2026-09-14 · Assignment HA1-US-DAILY-EXPLORE-PLAN · Mastermind / Overview.
Packet v1, prepared for Mastermind acceptance; implementation has NOT been authorized or dispatched. Once accepted, this is the binding slice contract. The PLAN supplies tasks and the copy-ready Implementer prompt; the LEDGER owns execution status. Current rulings and this slice supersede older HA1 replay/mockup/range proposals for this increment only.

## 1. Outcome and boundaries

An authenticated **Analysis** destination, headed **Explore**, in the real dark Radar hub. Select a company and explicitly identify its current mapped native-USD US primary instrument; inspect retained daily closes and independently aggregated chatter mention counts for a bounded historical period. Useful even with no prices or no chatter. No new collection or schema prerequisite.

Default: the last seven **completed UTC calendar days**, not the last seven days with data. At a request on 2026-09-14 UTC this is September 7–13. Initial custom ranges contain 1–7 inclusive days and may end no later than yesterday UTC. Historical date windows are permitted but availability is measured only within the requested window, never promised by the selector. No 1M/1Y/3Y presets, range expansion, current partial day, or automatic search backwards for data. Wider support needs a separate bounded selected-instrument evidence/ruling step; not a broad research rerun.

This is a US-first feature, not a global USD policy. Preserve DE/international discovery and providers, legacy bookmarks, shared boards and Human Chatter's existing mention_z-before-top-N ranking. No replay, studies, returns/performance cards, predictive claims, correlation scores, daily z-score, durable tone, raw-post retrieval, OHLCV, intraday acquisition, provider selection, FX, capture activation, portfolio or news implementation.

Alternatives considered: reuse detail's slot chart (too much implicit coverage and basis selection); build a new archive/calendar prerequisite (unnecessary scope); **selected existing-store reader and independent series** (chosen). Retain the current framework, visual tokens and shell.

## 2. Evidence at verified base

Workspace: `C:/Users/michi/Desktop/CodingStuff/.worktrees/radar-hub-promotion`.
Branch: `codex/radar-hub-promotion`; HEAD and local `origin/main`: `1ac39fe4e1a5dd7d04830e96a96563183687b447`; no upstream. File references below are relative to this exact root; symbols are the durable locator if lines move. New interfaces in §4 are proposals, not existing endpoints.

| Current file / symbol | Inspection finding and design consequence |
| --- | --- |
| `personal_apps/models.py:497` TickerUniverse | Current catalogue ID, unique symbol, first_seen/delisted_at; not a versioned company-history registry |
| `personal_apps/models.py:546` RadarInstrument | ID plus ticker/market/MIC, venue, currency, provider_symbol, mapped_at, primary/mapping status; unique identity index and ticker/market/primary index |
| `personal_apps/models.py:944` RadarDailyClose | Date/close/fetched_at/source/price_basis/adjustment_basis/live-shadow; unique `(ticker,market,mic,close_date,is_shadow)`; rows can be replaced |
| `personal_apps/models.py:761` RadarBucketSource | PK `(ticker,bucket_start,source)`; mention_count/status/config stamp per source; no bucket revision/known-then timestamp |
| `personal_apps/features/radar/search.py:28` search_universe; `routes/api.py:668` search | Existing authenticated eight-hit identity search; currently returns ticker/name/exchange/segment, no company or instrument ID |
| `personal_apps/features/radar/routes/views.py` hub_page, _hub_args | Root/alias authenticated actual hub; embedded board remains existing shell cost |
| `personal_apps/static/radar/src/hub/navigation.ts` HubRoute/readRoute/readRootRoute/hashFor/urlFor | Hash destination, query filters, Back/refresh and old-root compatibility |
| `personal_apps/static/radar/src/hub/Hub.tsx` Hub/Page/openRoute/titleFor | Existing nav, search, focus, session handling; useBoard currently called for all pages |
| `personal_apps/static/radar/src/hub/Search.tsx` Search | 250ms debounce, combobox keyboard patterns; reusable search interaction |
| `personal_apps/static/radar/src/hub/queries.ts` useBoard/useSearch/detailKey | TanStack cache/key/failure conventions; independent Analysis key required |
| `personal_apps/static/radar/src/api.ts` BoardUnavailable/statusReason | Existing HTTP/session failure patterns; do not parse login HTML as data |
| `personal_apps/features/radar/history.py:292` resolve_basis | Chooses most-populated native/sibling/converted basis and discards one-close candidates; do NOT call for this pinned USD reader |
| `personal_apps/features/radar/detail.py:106` daily_counts; :139 first_watched_day; :159 chart_for; :349 intraday_chart_for | Count sums omit source-quality detail; first-watched inference and fixed slots unsuitable for HA1 |
| `personal_apps/features/radar/coverage.py` covered_bucket_starts/_scan | Cross-ticker source scan with growing cached range; not a selected-instrument completeness service |
| `personal_apps/features/radar/config.py:613` expand_sources_for_history | Preserves old bare Reddit for raw counts; current source expansion is not a historical configuration manifest |
| `personal_apps/features/radar/market_calendars/us.py` holidays/is_trading_day/session_bounds | Rule-based NYSE calendar; no evidenced authoritative historical exceptional-closure/MIC registry |
| `personal_apps/features/radar/board.py:502` sort_rows; :543 build | Preserve existing price-independent chatter selection and top-N semantics |
| `personal_apps/static/radar/src/hub/hub.css` .rh tokens | Navy canvas, orange action/chatter, cyan price, scoped CSS; keep mobile menu/focus conventions |
| `personal_apps/tests/conftest.py` client/plain DB fixtures; `personal_apps/destructive_target.py` require | Tests may use a real development DB; exact independent disposable-target gates must precede DB execution |

MD-01C-RETURN and MD-01C-RULING are accepted **Researcher-reported** evidence, not rerun here. September 7–13: 12,599 current active/eligible US companies; 12,294 usable daily, 12,075 with >=2, 219 with one, 305 none. DE rescues zero absent-US cases in this window. 8,037 have buckets, 4,562 none, 2,146 positive mentions. Production changed between sequential SELECTs. These figures do not establish global coverage or long history. Q4's 195 instruments/225 gaps is provisional: the displayed outer join can count a synthetic NULL row; never use it as an oracle. Source/config distributions and complete executed strata were not preserved as a full raw transcript.

## 3. Product and URL contract

Add `#analysis` (empty selection) and `#analysis/<TICKER>` (current mapping resolution). Canonical selected URL uses `#analysis/<TICKER>/<company_id>/<instrument_id>` plus **analysis_from** and **analysis_to** query dates. Retain ordinary board query context separately so Back returns to the prior board selection. Analysis ignores board market/sources/window/span/sort; label **US primary · USD · all retained sources** explicitly, including when entering from a DE board. Range controls never send board filters to the Analysis API. No instrument switch by price availability.

Global Search on Analysis opens its ticker resolver; elsewhere preserve existing openRoute behavior. Resolve IDs once and replace (not push) the ticker-only URL with validated IDs and explicit dates. User changes of company/range push history; Back/forward/refresh restore the exact request. Invalid dates show an editable validation notice without fetching a guessed range; a bare Analysis URL alone gets the default. Stale canonical IDs fail visibly, never silently resolve to today's replacement. Selecting a search hit is the explicit way to resolve current mapping again.

Desktop: retain shell and horizontal nav; heading/retrospective subtitle, compact company/range controls, identity strip, independent price/chatter coverage summaries, two aligned daily panels (price above, counts below), selected-day detail and a compact provenance/coverage rail at >=1100px. Below 1100px stack rail after plots. At 390/320px order controls → identity → coverage → plots → day detail → provenance/table; no document horizontal overflow. Use existing .rh tokens and an Analysis-scoped CSS file, no redesign of other pages. No separate interactive prototype or redesigning-pages-from-data workflow.

All requested dates remain on the axis. Price uses close-date labels; chatter uses UTC midnight-to-midnight intervals. A shared calendar-date column is **not simultaneous measurement**: no fabricated close timestamp, 15-minute price slot or causal lead/lag claim. Text next to charts: “Daily closes use the stored trading date. Chatter days run midnight to midnight UTC.” Price dots are required; connect only neighboring dates with usable compatible observations, without crossing a missing/invalid date or regime boundary. A sole close is a dot/value, never a flat trend. A conservative broken line across a weekend is acceptable and explicit; no interpolation.

Select a day by pointer or keyboard-accessible date buttons; show the close or its reason, retained count or unavailable, source/config breakdown and statuses. Include an accessible daily table with equivalent information; no tooltip-only facts. Focus visible, controls >=44px on mobile, loading/status announcements, errors with retry, contrast >=4.5:1 for ordinary text and >=3:1 for meaningful graphics. Missing uses text/patterns as well as color. Respect reduced motion. Use natural retained-evidence copy, not technical policy prose as the main workflow.

Always visible: **Retrospective — current retained records may include later corrections.** Details: counts are mention observations, not unique people/posts or sentiment; original posts/judgments may have expired and are not queried here. No promise that today's mapping, name, config or close was known on that date. No known-then/replay/study tabs or fake performance placeholders.

## 4. Proposed backend and transport contract

New route module `personal_apps/features/radar/routes/analysis.py`, registered in `routes/__init__.py`, delegates to new `features/radar/analysis.py`. All routes use existing login_required; this is ordinary authenticated access, not admin-only. No account/watch data in responses. Keep search API unchanged by resolving its ticker result:

1. `GET /radar/api/analysis/resolve?ticker=AAPL`: bounded exact active TickerUniverse lookup; select eligible US primary candidates with ticker index and LIMIT 2. Zero -> 422 `ineligible_instrument`; >1 -> 409 `ambiguous_primary`; unknown/delisted -> 404. Return company and instrument objects below. Nonempty trimmed MIC/provider symbol/venue, mapped status, primary, USD, mapped_at <= request read-start are required. Do not use `.first()` to hide ambiguity.
2. `GET /radar/api/analysis/company/<int:company_id>?instrument_id=<id>&from=YYYY-MM-DD&to=YYYY-MM-DD`: all three query fields required, unique, strictly valid and bounded. Reject unsupported query keys, duplicate keys, zero/negative IDs, reversed/>7-day ranges, today/future dates with 400 and stable `code`. Endpoints accept no client `as_of`.

Revalidate current company/selected instrument on every data request: exact IDs, ticker relationship, active company and current eligibility. Missing ID ->404; remapped/nonprimary/mismatched identity ->409 `identity_changed`; unsupported selection ->422. Do not retarget an old bookmark. A current catalogue/mapping has no complete identity lineage: rows before company.first_seen are excluded with `identity_unverified`; first_seen is only a conservative boundary, NOT proof of historical legal identity. Do not clamp to mapped_at (backfilled prices predate mapping). Echo `identity_scope: current_mapping_retrospective` and boundary/caveat. Never reinterpret missing lineage as a validated corporate-action history.

Successful response (JSON numbers finite; dates ISO, timestamps UTC Z; empty arrays and null have explicit meaning):

```typescript
type Day = string // validated YYYY-MM-DD, not a timestamp
type Company = { id: number; ticker: string; name: string | null; first_seen: string }
type Instrument = { id: number; ticker: string; market: 'us'; mic: string;
  venue: string; currency: 'USD'; provider_symbol: string; mapped_at: string }
type PriceDay = { date: Day; close: number | null;
  state: 'observed' | 'missing' | 'invalid' | 'identity_unverified';
  source: string | null; price_basis: string | null; adjustment_basis: string | null;
  fetched_at: string | null; regime: string | null;
  calendar_hint: 'modeled_open' | 'modeled_closed' | 'unknown' }
type SourceDay = { source: string; mentions: number | null;
  ok_slots: number; truncated_slots: number; missing_slots: number;
  absent_slots: number; invalid_slots: number; expected_slots: 96;
  config_versions: (string | null)[]; transition: boolean;
  coverage: 'observed_full_day' | 'partial' | 'unavailable' }
type ChatterDay = { date: Day; mentions: number | null;
  coverage: 'observed' | 'partial' | 'unavailable';
  configured_source_coverage: 'unknown'; sources: SourceDay[];
  config_transition: boolean; overlap_ambiguous: boolean }
type AnalysisPayload = { schema_version: 1; mode: 'retrospective';
  company: Company; instrument: Instrument;
  identity_scope: 'current_mapping_retrospective';
  request: { from: Day; to: Day; chatter_timezone: 'UTC'; max_days: 7 };
  read_started_at: string; read_finished_at: string;
  price: { resolution: 'daily_close'; days: PriceDay[];
    usable_count: number; first_usable: Day | null; last_usable: Day | null;
    official_completeness: 'unknown'; interior_modeled_missing: Day[] | null;
    regime_changed: boolean };
  chatter: { resolution: 'daily_counts'; input_minutes: 15;
    source_scope: 'all_retained_for_ticker'; days: ChatterDay[];
    first_observed: string | null; last_observed: string | null };
  warnings: string[] }
```

Each series returns one entry per requested date, independently. first/last metadata describes **this window only**, never all-time min/max. Data errors return 503 `analysis_unavailable`; bounded read/resource failure ->503 `analysis_limit`. No internal SQL/credentials. A query error is not 200 with an empty series. Snapshot isolation is not claimed: bounded sequential reads and read-start/end disclose current-state timing; fetched_at <= read-start filters prices only, not later bucket revisions.

## 5. Price eligibility, regimes and gaps

Query only selected ticker/market/MIC, live lane, inclusive dates and fetched_at <= read-start. Accept finite positive close, USD, nonempty source, price_basis='close', adjustment_basis='split'. Unusable retained rows are `invalid`, not zero or absent; preserve safe provenance. Missing required metadata stays null. Neither legacy null-MIC rows nor other venues/currencies/shadow observations fill gaps.

Regime is the tuple `(market,mic,currency,source,price_basis,adjustment_basis)`. Break connection at changes, retaining each observed value and its provenance; A→B→A produces three runs. Do not calculate percent return, split adjustment, normalization or performance. The store's `split` stamp is a declared basis, not a verified adjustment vintage or complete corporate-action feed. Even same-source observations may have been restated differently; disclose this limit. Do not invent split/halts from jumps or imply dividends/total-return adjustment.

No authoritative calendar or peer-date service is added. The existing rule-based NYSE calendar may supply **modeled** hints only for known US MICs evidenced here: ARCX, XNMS, XNYS, XNCM, BATS, XNGS, XASE. Other MIC -> unknown. Holidays/weekends without a close are not automatically gaps. An observation on a modeled-closed day remains observed plus discrepancy warning. Unexpected closures, listing-specific halts and historical calendar limits remain unknown; never display “complete official sessions.”

`interior_modeled_missing`: null with <2 usable dates or unknown calendar; otherwise dates strictly between first/last usable where the local model says open and no usable close exists. End missing dates are coverage edges, not interior gaps. Invalid data can be a missing usable observation but keeps its invalid reason. Adjacent two closes with no interior expected dates -> empty list, not one gap. Should later peer evidence be provided, its distinct, non-null dates must belong to the same eligible market/MIC; missing count is `sum(peer_date is not null and selected_close is null)`. Peer-based completeness cannot detect a market/provider-wide outage. HA1 does not execute MD-01C Q4 or expose its provisional aggregate.

## 6. Daily chatter contract

Read only selected ticker's RadarBucketSource rows in `[from 00:00Z, (to+1 day) 00:00Z)`. Include every stored concrete source (also retired names and bare Reddit), NOT today's expanded config and NOT both parent RadarBucket totals and child sums. No raw posts/events/judgments joins, no z/expected/variance arithmetic. No global coverage probe to manufacture absent ticker slots as zero.

For each source observed anywhere in the requested range, construct 96 quarter-hour slots per requested UTC day. A valid slot is aligned, count is an integer >=0, and status is recognized. Each PK row contributes once. ok counts and truncated counts are retained observations; missing rows/status and invalid counts provide no numeric contribution. An ok explicit zero is observed zero. A source with no usable slots has mentions=null; otherwise mentions=sum(valid ok/truncated counts), accompanied by coverage. No extrapolation for absent slots or truncated intake. A partial day with sum zero says **“0 in observed buckets — coverage incomplete”**, never “no chatter.”

Per-source `observed_full_day` requires 96 valid ok slots, no missing/absent/truncated/invalid slots, one known non-null config stamp; it means full retained bucket coverage for that represented source only, not all real-world content. Otherwise partial if any usable slot, unavailable if none. Unknown config does not erase valid observed counts, but prevents a full-coverage claim. Config changes are preserved per source/day and across adjacent days; show source/config periods and boundary warnings, not a homogeneous activity trend. Sum actual mentions across nonoverlapping slots/configs; never sum/average mention_z.

Overall configured-source coverage is always unknown: no historical enabled-source manifest exists. A day with all represented sources full may use `coverage=observed`, explicitly labeled “Observed counts; historical source set not verified.” Other days partial if any usable data, unavailable if none. A source absent for the entire window is unknowable; no 100% all-source badge. Before/after/between retained buckets remain absent; first observed is not capture start and gaps are not proof of retention deletion.

At a slot where bare `reddit` and `reddit:*` both have usable observations, retain separate source counts but do not pool overlapping families: the day's pooled `mentions=null`, `overlap_ambiguous=true`, coverage partial; source breakdown remains usable. No heuristic preference/double counting. Identical text across distinct ordinary sources is not deduplicated by this archive, so pooled counts mean stored source mention observations, never unique posts/people. Cross-day counts across changed configs are descriptive, not directly comparable unusual-activity scores.

## 7. Bounded query and failure budget

Resolver <=2 statements; data reader <=4 data SELECTs (company, selected instrument, daily rows, source buckets), excluding normal auth. Daily read <=7 live identity rows (LIMIT 8 sentinel); bucket read ordered by PK and LIMIT 43009 (7*96*64 +1 sentinel), select only needed columns, max 64 distinct sources. Sentinel/excess sources -> honest 503 analysis_limit, never truncated-success. UTC predicates are index-sargable; no DATE(column) in WHERE, universe joins, peer calendar scans, all-time availability scans or per-source/day N+1 queries. Aggregate bounded fetched rows in memory. Existing indexes are sufficient candidates; no migration precondition or forced optimizer hint without selected-query evidence.

Use a statement-scoped MariaDB SELECT timeout of 2 seconds (including identity reads) with a 5-second total reader deadline; abort remaining work after failure. Verify timeout cancellation and pooled-connection hygiene on isolated MariaDB. On another supported test engine use its appropriate test timeout; never send MariaDB syntax blindly. Browser fetch timeout 8 seconds with AbortSignal, no automatic retry or background polling; manual Retry only. TanStack query keys include IDs, ticker, dates and schema version; 60-second stale time, five-minute cache lifetime, no previous-selection placeholder, refetch-on-focus off. Clear Analysis cache on session failure through existing hub session handling. Do not serve cached data as freshly read after a failed refresh: mark last answer/read time, same key only.

Suppress recurring board requests while Analysis is active through useBoard's enable/visibility path, preserve other-page behavior and initial shell bootstrap. Analysis body and errors do not depend on board readiness. Existing hub_page still embeds its board: disclose/measure that separate cold-shell cost; do not redesign PERF3 in this slice. No provider request, collector scheduling or new adapter cache is involved.

Local acceptance budgets, not claims of production performance: <=4 data SELECTs, <=43008 input bucket rows, <=1MiB response, <=32MiB incremental reader allocation; warm isolated MariaDB full data request p95 <=1 second over 20 runs of the max-row selected fixture, and no request survives the enforced deadline. Record median/p95, hardware/engine, EXPLAIN and bytes. If unmet, query-local correction or return the measured limitation to Mastermind; no silent target waiver, cache daemon or schema expansion.

## 8. Acceptance and next scope

PLAN's matrix must pass on a safely isolated candidate, with any unavailable environment gate explicitly open. One owner-selected Implementer then independent Reviewer with QA combined. No workers dispatched by this packet; Deployer only on later owner authorization. Review is not a deployment approval.

OpenTerminal continuation is **next enabling packet MD-02/07 + MD-05 + MD-10**, ahead of portfolio/full news: independently timestamped selected-instrument history/intraday, evidence-based provider priority, and first-adapter cache/coalescing/timeouts/backoff/health. Broad MD-03/08 discovery/venue experiments remain separate. This daily contract does not freeze future price cadence or invent OHLCV; MD-06 contextual earnings/news remains later. No material product decision blocks completing this plan; Mastermind acceptance of v1 is next. Runtime/QA environment availability is unverified, not a research failure.
