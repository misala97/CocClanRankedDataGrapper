# Radar Yahoo Community Source Design

**Date:** 2026-09-01
**Status:** Approved design; binding implementation specification
**Scope:** Add Yahoo Finance Community as a directly active human-chatter
source for Radar
**Repository:** `personal_apps` on branch `dev_personal`

## 1. Decision

Radar will ingest public Yahoo Finance Community root posts for the 15 ticker
boards measured by the temporary VPS probe. Yahoo is active on the board from
the first production deployment; there is no shadow-only product stage.

The source is independently reversible. Setting
`RADAR_YAHOO_ENABLED=false` and restarting the web and ingest services removes
Yahoo from polling, scoring, default board selections, the source selector,
and accepted `sources=` query parameters. It does not delete Yahoo history and
does not alter Reddit, Bluesky, or 4chan behavior.

The release intentionally ingests root community posts only. The number of
comments attached to each root post is retained as engagement, but Yahoo
comment bodies are not fetched in this version. Root posts alone already
clear the value threshold; comment fetching is a separate source expansion
that first needs its own yield, pagination, identity, and rate-limit probe.

## 2. Evidence and product rationale

The source decision comes from the aggregate-only probe deployed at
`/opt/radar-chatter-probe` on the VPS. The probe stored no post text, author
identity, post identity, or permalink.

Across 10 collection rounds and 15 boards, Yahoo produced:

- 884 fresh root posts;
- 722 per-board author slots;
- 166 posts matching the narrow obvious-promotion pattern;
- 218 root posts with at least one comment and 370 attached comments;
- 91 of 150 board-round observations clearing the probe's Radar floor.

For the same five live market hours and the same 15 tickers, Yahoo produced
340 root posts, or 291 after the narrow promotion filter. Live Reddit produced
99 distinct comments and 101 ticker mentions for those tickers. Yahoo is
therefore approximately 3.4 times Reddit before the narrow filter and 2.9
times Reddit after it. The 291 filtered Yahoo posts are about 59% of the 493
distinct Reddit comments across Radar's entire ticker universe in those same
hours.

A separate pre-v2 sentiment-usability snapshot saw 159 fresh Yahoo posts, of
which 99 remained after the broader promotion and near-duplicate screen. Of
those 99, the old classifier called 54 directional and 35 unclear. Those are
not v2 relevance labels and are not treated as an activation gate. There are
no measured Yahoo sentiment-v2 judgments yet. Michi explicitly accepts that
remaining quality uncertainty in exchange for direct activation and fast,
reversible production evidence.

The measured live marginal rate was 61-78 new root posts per hour across the
15 boards once the initial backlog had cleared. Because Yahoo returns only 10
recent posts per board, that is a lower bound whenever a board reaches the
page cap.

## 3. Goals

The implementation must:

1. add Yahoo as a fourth root source and a normal source-selector option;
2. place accepted Yahoo chatter on the live board immediately;
3. preserve the Yahoo board symbol as trusted association metadata without
   inserting that symbol into the author's text;
4. route every stored Yahoo mention through the existing local sentiment and
   sentiment-v2 paths;
5. isolate Yahoo failures so they cannot cost another source its cycle;
6. maintain a cursor and coverage status independently for each ticker board;
7. remove obvious promotional posts before storage while still advancing the
   upstream cursor past them;
8. expose enough existing operational evidence in logs to judge yield,
   truncation, missing boards, newly stored posts, and extraction reasons;
9. make rollback one configuration change plus a service restart, without
   destructive cleanup; and
10. preserve the existing 30-day post/mention retention behavior.

## 4. Fixed first-release universe

The production constant is named `YAHOO_COMMUNITY_SYMBOLS` and contains, in
this exact order:

```python
YAHOO_COMMUNITY_SYMBOLS = (
    'AAPL', 'NVDA', 'TSLA', 'GME', 'PLTR', 'AMD', 'IREN', 'DJT', 'SMCI',
    'META', 'AMZN', 'MSFT', 'AVGO', 'MRNA', 'IOVA',
)
```

These are the boards for which yield and request behavior were measured.
Membership is code configuration, not an environment variable. Changing it
changes the counted population and therefore changes
`source_config_version()`.

Yahoo has no global community firehose in the validated path. This release
does not rotate through the full security universe, follow a dynamically
changing loud-ticker set, or use an unmeasured trending endpoint. A later
release may expand the fixed list using production evidence. The first source
release must not silently broaden beyond the population that justified it.

## 5. Source names and activation

### 5.1 Root and durable names

The UI and query root is `yahoo`. Durable per-board names are
`yahoo:<SYMBOL>`, for example `yahoo:TSLA`.

Per-board names are required because coverage is per board. A full or broken
TSLA page must not mark AAPL missing or truncated, and an AAPL zero must not be
represented as a TSLA zero. `source_root('yahoo:TSLA')` already returns
`yahoo`; venue breadth therefore counts all Yahoo boards as one venue.

`expand_sources(('yahoo',))` expands to every configured durable board name.
A concrete `yahoo:TSLA` selection stays concrete. History expansion is the
same because there is no legacy root-level Yahoo population.

While Yahoo is enabled, a concrete `yahoo:<SYMBOL>` query is accepted only
when `<SYMBOL>` is in `YAHOO_COMMUNITY_SYMBOLS`. This tightens Yahoo's fixed
population without changing the existing compatibility behavior for concrete
Reddit names. An unknown concrete Yahoo board returns the existing
`unknown source` query error.

### 5.2 Source kind

Yahoo is `SOURCE_KIND['yahoo'] = 'forum'`. Each post has a human author and the
existing distinct-author gate is the appropriate independent-voice rule.
Yahoo is not a broadcast source and its board symbol is not a channel-level
voice.

### 5.3 Configuration contract

`RADAR_YAHOO_ENABLED` accepts exactly the case-insensitive strings `true` and
`false`; surrounding whitespace is ignored. It defaults to `true`. Any other
present value raises `RuntimeError` during application/daemon startup rather
than producing a half-configured process.

Configuration distinguishes:

```python
CONFIGURED_SOURCE_ROOTS = ('bluesky', 'fourchan', 'reddit', 'yahoo')
SOURCES = tuple(
    source for source in CONFIGURED_SOURCE_ROOTS
    if source != 'yahoo' or yahoo_enabled()
)
```

The exact implementation may avoid evaluating the environment twice, but the
two meanings are binding:

- `CONFIGURED_SOURCE_ROOTS` is the deployed counting-policy universe and is
  used in the source-configuration hash;
- `SOURCES` is the runtime-active set used by fetchers, scoring, API
  validation, defaults, and `all_sources` serialization.

The activation flag itself is not hashed. Turning Yahoo off stops new Yahoo
writes and excludes its durable names from every board read; turning it back
on resumes the identical counting policy and baseline generation.

`MAX_SOURCES` must remain a real upper bound after adding the 15 concrete
Yahoo names. A root selection normally carries one `yahoo` value, but an
explicit query may name concrete boards, and the validation bound must cover
every real configured root/concrete selection without becoming unbounded.

## 6. Public upstream client

### 6.1 Validated route

The adapter uses the route proven by
`scripts/measure_yahoo_finance_community.py`:

1. launch headless Chromium with Playwright;
2. load `https://finance.yahoo.com/quote/TSLA/community/`;
3. reject the consent prompt when it is present;
4. capture the page's own `GetContentByAssociatedContentId` GraphQL request
   body and browser cookie context;
5. request a crumb from Yahoo's public crumb endpoint;
6. resolve the 15 symbols to `messageBoardId` values in one batched quote
   request; and
7. issue one captured-template GraphQL request per board, replacing only the
   request's `contentId` variable.

The browser is closed in `finally` on every outcome. No browser, page, cookie,
crumb, board id, or captured query is shared across scheduled runs. This
avoids cross-thread Playwright ownership and keeps Yahoo's short-lived browser
state ephemeral. Browser memory exists only during the hourly job.

The implementation must not hard-code a reverse-engineered GraphQL query as a
supposed stable API. Capturing the public page's current request is the
compatibility mechanism validated by the probe.

### 6.2 Dependencies and request bounds

`playwright` is added to the Python requirements, and the deployment requires
the matching Chromium bundle before the source can be enabled. Tests mock the
browser and HTTP boundary; the normal test suite performs no Yahoo requests.

Exact bounds:

- page navigation timeout: 60 seconds;
- quote/crumb/GraphQL request timeout: 30 seconds each;
- maximum boards per run: `len(YAHOO_COMMUNITY_SYMBOLS)` (15);
- maximum feed nodes consumed per board: 10;
- delay between board GraphQL requests: 0.2 seconds;
- scheduled run overlap: forbidden (`max_instances=1`, `coalesce=True`).

There is no API key, login, proxy rotation, challenge bypass, or retry storm.
One failed hourly run waits for the next scheduled run. If the public route
begins presenting a bot challenge or ceases to expose the request template,
Yahoo reports missing; the implementation does not attempt to defeat it.

### 6.3 Response parsing

The parser reads
`data.getContentByAssociatedContentId.newFeed.edges[].node`. Parsing separates
an upstream observation from a post eligible for emission. An
**identity-valid node** requires:

- a stable upstream content id;
- `publishedAt` or `createdAt` parseable as an aware timestamp;
- a timestamp no more than five minutes in the future relative to fetch time;
  and
- an external id within the model's 128-character limit after namespacing.

An identity-valid node is eligible for emission only when its timestamp is
strictly newer than the board's prior cursor, its authored body is non-empty
after whitespace normalization, and it does not match the Yahoo promotion
filter. Older/equal nodes still establish page coverage. Empty and promotional
nodes still advance the cursor when newer, but never become `RawPost` rows.
This distinction prevents a filtered-only page from repeating forever without
misrepresenting it as a missing observation.

Author username is nullable. Comment count is coerced to a non-negative
integer. Missing reaction fields do not fail a post; this release stores
`score=0`. The source URL is the public community page for the board. A
post-specific permalink may be used only when the node supplies a valid
absolute Yahoo URL; it is never guessed.

Malformed nodes are skipped and counted in the returned diagnostic summary.
If a syntactically successful board response has nodes but none is
identity-valid, that board is `missing`, not a measured zero. A response whose
nodes are identity-valid but all old, empty, or promotional is a valid
observation that may emit zero posts.

## 7. Polling, cursors, and coverage truth

### 7.1 Schedule

Yahoo runs on its own fixed 3,600-second interval around the clock. It is
excluded from the session-driven three-minute/overnight cycle in the same way
Reddit is excluded. The first Yahoo job runs immediately at daemon startup;
the existing scoring pass remains two minutes behind initial ingestion.

The cadence matches the measurement that justified the source. A faster
market-hours cadence and adaptive per-board polling are deliberately deferred
until production truncation rates show they are needed and tolerated.

### 7.2 Per-board cursors

`RadarSourceCursor` rows use the durable source name, for example
`yahoo:NVDA`. The initial cursor for a board is `now - 2 hours`; there is no
historical backfill beyond the newest page.

The common `FetchResult` contract gains:

```python
per_source_cursors: dict[str, dt.datetime] | None = None
```

Its three states mirror `per_source_status`:

- `None`: legacy behavior; ingest advances the fetcher's root cursor from
  returned posts;
- `{...}`: advance exactly these concrete cursors after posts and mentions
  have been stored successfully;
- `{}`: advance no cursor.

The daemon's Yahoo fetcher wrapper reads every configured concrete
`RadarSourceCursor` before calling the network client and passes a
`since_by_board` mapping keyed by symbol. A missing concrete row falls back to
the root `since` supplied by `run_cycle`, which is `now - 2 hours` on a cold
start. The client never queries the database. This is the same ownership split
used by Reddit's wrapper: scheduling/storage state belongs outside the source
HTTP adapter.

Cursor values follow the repository's naive-UTC database convention. Cursor
updates occur in the same database transaction as `RadarPost` and
`RadarMention` storage. A source adapter never commits cursor state. If that
storage transaction raises, it rolls back both the stored rows and cursor.
The existing store-then-roll-up transaction boundary remains unchanged: a
later rollup failure does not discard already-retained posts or rewind their
source cursor.

For Yahoo, each successful board returns the maximum valid upstream timestamp
strictly newer than its prior cursor, including nodes later removed as empty
or promotional. A successful page with no newer identity-valid node returns
no cursor entry. Failed boards return no cursor entry. Ingest may also advance the root
`yahoo` cursor to the maximum successful concrete cursor as an operational
cycle watermark, but fetch eligibility always reads the concrete cursor.

Advancing past filtered posts is mandatory: a page containing only promotion
is still an upstream observation and must not be fetched forever.

### 7.3 Page-cap status

For each board:

- `missing`: board id unavailable, request failed, response malformed, or no
  node carried a valid id/timestamp;
- `truncated`: 10 nodes were returned and the oldest identity-valid node is
  newer than the board's prior cursor, so an unseen gap may exist behind the
  page;
- `ok`: the response was valid and either fewer than 10 nodes were returned or
  the oldest identity-valid node reaches at least as far back as the prior
  cursor.

The adapter continues after one board fails. `per_source_status` contains one
entry for every attempted board. The root aggregate is:

- `missing` when no board succeeded;
- `truncated` when at least one board succeeded and at least one board was
  missing or truncated; and
- `ok` only when every board was `ok`.

No attempted board is converted to an `ok` zero after a failure. An empty
valid response, or an identity-valid response whose nodes are all old or
filtered, is a genuine `ok` zero.

## 8. Normalization and ticker association

### 8.1 `RawPost` mapping

Each accepted node becomes:

```python
RawPost(
    source=f'yahoo:{symbol}',
    external_id=f'yahoo:{symbol}:{content_id}',
    channel=symbol,
    author=username_or_none,
    created_utc=published_utc_naive,
    title=None,
    body=authored_body,
    score=0,
    num_comments=comment_count,
    url=validated_permalink_or_board_url,
    native_tickers=[symbol],
)
```

The external id is explicitly source- and board-namespaced even though the
database uniqueness constraint also includes `source`. Existing ingest looks
up refresh candidates by `external_id` before applying the database
constraint; a globally namespaced value prevents a Yahoo id colliding with a
Reddit or Bluesky id in that lookup.

An external id longer than the model's 128-character limit is rejected as a
malformed node. It is not silently truncated into a potentially colliding id.

### 8.2 Native association

`RawPost.native_tickers` is trusted source metadata, not authored text. The
extractor gains the provenance reason `native_symbol_scope`, ranked at high
confidence, and a scope flag `in_native_scope`. Existing reason precedence is
otherwise unchanged.

For a valid universe symbol in `native_tickers`, extraction emits:

```python
Match(
    ticker=symbol,
    confidence='high',
    reason='native_symbol_scope',
    in_author_text=False,
    in_thread_context=False,
    in_native_scope=True,
)
```

The native symbol is never prepended/appended to `title`, `body`, extraction
text, sentiment text, classifier text, or the LLM serialized item. The
author's words stay byte-for-byte semantically independent from association
metadata.

Native association is emitted only when authored body text is non-empty and
the symbol exists in the active universe lookup. The board association itself
bypasses the coin-collision drop: a post fetched from Yahoo's LINK equity
board is natively associated with the listed LINK security. Coin-shaped
symbols extracted from the post's prose remain subject to the normal collision
policy.

Text extraction still runs and may add explicitly mentioned other tickers.
For Yahoo v1:

- bare tokens are disabled;
- single-letter cashtags are disabled; and
- explicit multi-letter cashtags may add another ticker when the existing
  coin-collision policy permits it; and
- no bare-token or name-corroborated-bare path may add another ticker.

The strict policy is intentional. Yahoo's board metadata already supplies the
target ticker, while the probe did not measure the precision of unrelated bare
uppercase tokens inside Yahoo posts.

The compatibility wrapper `extract_tickers()` retains its existing signature
and return shape. `_extract_for()` remains a list of `(ticker, confidence)`
pairs. Native provenance travels through `_extract_matches()` and intake
diagnostics without changing those pinned public seams.

### 8.3 Promotion filter

Yahoo drops a node before `RawPost` creation when author plus body matches this
case-insensitive pattern:

```text
chat\.whatsapp|whatsapp|telegram|discord|t\.me/|bit\.ly|tinyurl|
join (?:my|our)|subscribe|free signal|premium|dm me|tp target|
take profit|signal service|signals_pro
```

The pattern lives in configuration and is included in
`source_config_version()`. It is applied only to Yahoo. The cursor still
advances past matches and the run logs the number filtered per board and in
aggregate.

Near-duplicate posts are not automatically deleted in v1. Existing simhash,
distinct-text eligibility, and sentiment-v2 origin judgment remain the safety
layers. The probe's near-duplicate heuristic is evidence for later tuning,
not authority to erase possibly genuine copy/meme chatter on day one.

## 9. Sentiment and immediate board behavior

Yahoo uses the ordinary pipeline:

1. deterministic source filtering;
2. high-confidence native mention storage;
3. local sentiment scoring from the author's body only;
4. normal high-confidence sentiment-v2 selection;
5. immediate unjudged participation under the existing NULL-safe eligibility
   rule; and
6. exclusion plus journal-backed bucket rebuild if the final judgment is
   `irrelevant` or `broadcast_or_automated`.

There is no Yahoo-specific sentiment prompt, model, default answer, daily cap,
or priority lane. Missing, malformed, or refused model answers remain unjudged
and retry exactly as they do for every other source.

Direct activation deliberately permits a newly ingested, not-yet-judged Yahoo
post to contribute briefly. That is Michi's chosen tradeoff. The deterministic
promotion filter limits the obvious failure class; sentiment v2 provides the
semantic correction and the existing append-only judgment history provides
evidence for later source tuning.

At the measured rate, Yahoo adds approximately 60-80 high-confidence mentions
per live market hour. This is far below the primary pass capacity of 400 every
10 minutes, but it will increase Claude usage. Existing spend and pending/p95
metrics remain the operational controls; the implementation must not hide
Yahoo work from them.

## 10. Board, detail, and UI behavior

When enabled:

- the default board includes Yahoo;
- `all_sources` includes `yahoo`;
- `sources=yahoo` is accepted and expands to the 15 durable names;
- a Yahoo-only selection works;
- source breadth roots every `yahoo:<SYMBOL>` contribution to one Yahoo
  venue;
- detail breakdown and post lists label durable names as `Yahoo`;
- Yahoo post links open the validated Yahoo URL; and
- the source selector renders `Yahoo`, not the lowercase fallback.

When disabled:

- the default board excludes Yahoo;
- `all_sources` excludes Yahoo;
- `sources=yahoo` and `sources=yahoo:TSLA` return the existing `unknown source`
  query error;
- historical Yahoo rows remain in the database but cannot enter board,
  detail, tone, distinct-voice, or scoring reads through an active root
  expansion; and
- no Yahoo scheduler job or client is constructed.

Frontend source controls remain data-driven. Adding the display label is the
only Yahoo-specific UI code.

## 11. Versioning, warm-up, and rollback

### 11.1 Activation version

The deployed policy root set, fixed Yahoo board membership, promotion pattern,
native-association generation, and Yahoo extraction settings are hash inputs.
The first deployment therefore changes `source_config_version()` and starts a
new baseline generation under the repository's existing global-version model.

This temporarily warms existing sources as well as Yahoo. That is honest and
visible: rows use the existing `warming-up`/`provisional` marks, old scored
rows with an incompatible version are not presented as current evidence, the
first ingest runs immediately, and scoring follows two minutes later. The
implementation must not copy old expected/variance values across the version
boundary to avoid the warm-up.

### 11.2 Kill-switch rollback

Runtime activation does not participate in the hash. Turning Yahoo off keeps
the post-deployment version for remaining sources, so rollback does not
resurrect the pre-Yahoo version or mix buckets across the release boundary.

Rollback is forward-only:

1. set `RADAR_YAHOO_ENABLED=false`;
2. restart both web and ingest processes so they agree on the active source
   set;
3. verify Yahoo is absent from `all_sources`, no Yahoo job exists, and a Yahoo
   query is rejected; and
4. retain all Yahoo rows for normal retention and diagnosis.

Do not delete Yahoo data, revert the configuration hash to its historical
value, or restore old expected/variance fields. If Yahoo is permanently
removed in a later code release, that release increments an explicit source
membership generation while retaining a tombstone for the old configured
root; it must not reproduce the pre-Yahoo hash.

## 12. Failure containment and observability

All Yahoo network, browser, consent, crumb, board-id, GraphQL, and parse errors
are contained at the Yahoo adapter/fetcher boundary. They never raise through
`tick()` in a way that loses another source's data or removes the scheduler
job.

The normal one-line ingest report already carries root aggregate status,
durable per-source status, catch-up depth, new posts, mentions, and intake
reasons. Yahoo adds one bounded source log per hourly run containing only:

- boards attempted / ok / missing / truncated;
- nodes received / valid / new-by-cursor;
- promotions filtered;
- posts emitted;
- malformed nodes;
- elapsed milliseconds; and
- the root aggregate status.

It never logs body text, usernames, content ids, cookies, crumbs, captured
GraphQL bodies, or full URLs. Per-board errors may log the public ticker symbol
and a stable local reason code such as `missing_board_id`, `http_status`,
`template_missing`, `bad_payload`, or `timeout`.

The source does not add a database health table or a new board-request query.
Logs plus existing cursor, bucket status, sentiment backlog, and spend evidence
are sufficient for the first release.

## 13. Privacy, safety, and retention

Production stores only the fields already allowed by `RadarPost`: authored
body, nullable public username, public source URL, public timestamp, ticker
board, score zero, and comment count. It does not store browser cookies,
request templates, profile metadata, avatars, emails, or hidden identifiers.

The temporary aggregate-only probe remains separate and is not imported by
production. Its artifacts are not migrated into Radar tables. The production
source starts from its two-hour/page-limited cold cursor.

Yahoo posts and mentions use the existing 30-day rolling retention. Judgment
history and mention-journal behavior remain governed by their existing
sentiment-v2 policies.

## 14. Required tests

All network tests use captured minimal fixtures with synthetic text and ids.
No test calls Yahoo.

### 14.1 Configuration and expansion

1. default-unset activation includes Yahoo;
2. case-insensitive `true`/`false` parsing with surrounding whitespace;
3. invalid activation refuses startup;
4. disabled activation removes Yahoo from `SOURCES` but leaves
   `source_config_version()` identical to enabled activation;
5. the post-release version differs from a pinned pre-Yahoo payload;
6. root expansion produces exactly the 15 durable names in configured order;
7. concrete expansion stays concrete;
8. Yahoo is a forum root;
9. an enabled configured concrete Yahoo board is accepted while an unknown
   concrete Yahoo board is rejected;
10. source query limits include the concrete Yahoo population; and
11. changing board membership or the promotion pattern changes the version.

The flag/version test is absence-shaped and must first demonstrate that the
broken implementation hashing runtime `SOURCES` produces different hashes for
enabled and disabled states.

### 14.2 Parser and client

1. consent present and absent;
2. current request template captured and only `contentId` replaced;
3. missing template fails closed;
4. board ids resolved in one batch;
5. one board failure does not stop later boards;
6. browser closes after success and every failure path;
7. id, timestamp, body, author, comment-count, and URL normalization;
8. future, missing-id, missing-time, and overlong-id rejection;
9. no identity-valid nodes from a non-empty malformed response is `missing`;
10. page-cap `ok` versus `truncated` boundary;
11. root aggregate status over mixed board outcomes;
12. empty-body and promotional nodes emit no post but advance the cursor;
13. nodes at or behind the prior cursor emit no post and do not move it;
14. promotion filtering and aggregate counts; and
15. emitted fixtures contain no captured cookie, crumb, or query body.

The browser-close test must first run a broken fake that omits `close()` and
prove the fixture detects the leaked resource. The per-board-continuation test
must first run a broken fail-fast loop and prove the later board was not
called.

### 14.3 Native association and ingest

1. a Yahoo post whose body never spells its board symbol still stores one
   high-confidence native mention;
2. native association never changes authored extraction or sentiment text;
3. native reason/scope survives `_extract_matches()` while `_extract_for()`
   remains pair-shaped;
4. unknown native symbols are ignored;
5. empty authored text does not create a new native mention;
6. native board symbol bypasses coin collision, prose-extracted symbols do
   not;
7. Yahoo bare tokens are not extracted;
8. explicit safe cashtags for another ticker still extract;
9. globally namespaced external ids do not collide with another source;
10. a promotion produces no post/mention but advances its concrete cursor;
11. a failed board advances no cursor;
12. concrete cursor advancement commits with stored posts;
13. forced storage failure rolls back both the post and cursor;
14. repeated external ids remain idempotent and do not double-count the
    journal; and
15. intake diagnostics count `native_symbol_scope` once per unique post.

The cursor/filter test must first use the broken variant deriving the cursor
only from emitted posts and prove that a promotion-only page repeats.

### 14.4 Scheduling and failure isolation

1. enabled `build_fetchers()` covers every active root including Yahoo;
2. disabled `build_fetchers()` does not construct a Yahoo client;
3. Yahoo is absent from the session-driven fetcher map;
4. the hourly job is immediate, non-overlapping, and coalescing;
5. one Yahoo exception leaves Reddit/Bluesky/4chan cycle behavior unchanged;
6. scoring expands the Yahoo root to all durable board names; and
7. the daemon's startup source log agrees with the web process active set.

The disabled-construction test must use a factory that raises if touched; a
passing no-call assertion alone is not sufficient.

### 14.5 Board, sentiment, and frontend

1. enabled default and `all_sources` include Yahoo;
2. disabled default and `all_sources` exclude Yahoo;
3. disabled root and concrete Yahoo query parameters are rejected;
4. Yahoo-only board/detail queries use all durable names;
5. all durable names count as one venue;
6. an unjudged Yahoo mention remains included by existing NULL-safe logic;
7. a final irrelevant or broadcast judgment removes it and rebuilds the
   affected window;
8. missing/malformed/refused judgment remains unjudged and retries;
9. sentiment serialization contains authored body only and no injected board
   symbol;
10. spend and pending counters include Yahoo attempts;
11. `sourceLabel('yahoo')` and `sourceLabel('yahoo:TSLA')` render `Yahoo`; and
12. the source control can toggle Yahoo without allowing the final active
    source to be disabled.

The NULL-safety test must exercise `True`, `False`, and `NULL` relevance and
origin combinations. The authored-text test must compare exact serialized
text, not substring absence.

## 15. Acceptance and deployment checks

Implementation is accepted when:

1. all focused backend and frontend tests pass;
2. the complete backend suite passes against the real dev MySQL database;
3. `npm test` and `npm run build` pass;
4. no normal test performs a network request;
5. a manual dev probe against Yahoo emits only aggregate operational logs and
   stores no cookie/query material;
6. production dependencies and the matching Chromium bundle are present
   before the daemon restart;
7. the first production Yahoo job attempts exactly 15 boards;
8. scoring runs after initial ingest and the board visibly labels any thin
   baseline as warming/provisional;
9. Yahoo appears in the default source selector and a Yahoo-only query works;
10. Reddit, Bluesky, and 4chan continue producing independent statuses during
    a forced Yahoo failure; and
11. the kill-switch rollback is rehearsed in dev: Yahoo disappears everywhere
    described in §10, no Yahoo client is constructed, existing sources keep
    the same post-release configuration version, and no data is deleted.

## 16. Non-goals

This release does not:

- ingest Yahoo comment bodies;
- poll more than the 15 measured boards;
- use Yahoo trending, screener, quote, news, analyst, or official-company
  content as chatter;
- add Yahoo market prices or reuse the market-data Yahoo provider;
- scrape a global search result to invent a community firehose;
- dynamically rotate boards based on current Radar rankings;
- run a shadow-only board mode;
- add a Yahoo-specific LLM prompt or classifier;
- automatically mute authors or tickers;
- drop near-duplicate human posts beyond the existing eligibility and
  sentiment layers;
- backfill beyond the two-hour/page-limited cold start;
- delete Yahoo data on rollback; or
- bypass bot challenges, authentication, consent, or upstream controls.
