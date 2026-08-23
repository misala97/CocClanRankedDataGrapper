# Radar — data source candidates

Addendum to §3 of `Radar — social-sentiment stock discovery dashboard`.
Section numbers (§) refer to that document.

**Current state:** Reddit is out. Bluesky and 4chan `/biz/` are in. X is out on
cost (§3.1). StockTwits is now uncertain — see below.

---

## 0. StockTwits status changed

Stocktwits' developer page currently states they are reviewing all their APIs,
documentation and terms, and are **not accepting new developer registrations**
until that review finishes. The keyed API in §3.3 is therefore unavailable, not
merely ToS-pending. Only the unauthenticated endpoints the web client uses are
reachable.

Two consequences:

- §12.1 is no longer a yes/no ToS question. Treat StockTwits as a gray-area
  source or drop it.
- §3.3 named StockTwits as **ground truth for calibrating the Reddit
  extractor**. That anchor is gone. The hand-labelled corpus in §12.1 is now the
  main path, not the fallback. See §4 below.

---

## 1. Two module types, not one

Everything on this list falls into one of two categories, and they must not
share a code path.

**Mention sources** feed `radar_post` / `radar_mention` and count toward
`mention_z`. Chatter venues only.

**Context feeds** annotate rows and never enter the score. Filings, press
releases, short volume, earnings dates. Counting them would let a single press
release manufacture a spike.

Add a `radar_event` table for the second category: ticker, event type,
timestamp, source, external id, link. Leaderboard rows and `radar_spike` rows
join against it to display a mark. Retention: keep, it's tiny.

---

## 2. Recommended, in priority order

### 2.1 SEC EDGAR — context feed

Free official API. Full-text search plus filing RSS. Rate limit is generous
(order of 10 req/sec) but requires a descriptive User-Agent header with contact
info — requests without one get blocked.

Filing types that matter here: **S-1, 424B5, S-3** (dilution — the single most
common explanation for a micro-cap chatter spike), **8-K** (material events),
**13D/G** (accumulation), **Form 4** (insider transactions).

Why it's first: it converts "loud and unmoved" from a mystery into a categorised
event. A 424B5 filed the same morning as a mention spike explains the spike, and
§7.4 can then slice hit rate by "had a filing" vs "didn't" — which is the
fastest way to learn whether the signal is anything more than a filings tracker.

### 2.2 Press release wires — context feed

GlobeNewswire, ACCESSWIRE, PRNewswire, Business Wire. Free RSS.

Micro-cap pumps almost always begin with a paid press release. Same argument as
EDGAR: this is the thing the chatter is downstream of. Match on company name
against `ticker_universe`, not on ticker — wires don't reliably tag symbols.

### 2.3 Telegram public channels — mention source

Free, official protocol. MTProto via Telethon; `api_id` and `api_hash` from
my.telegram.org. Reading public channel message history is the low-risk side of
Telegram automation — member-list extraction is the flagged spam vector that
gets accounts restricted. Stay entirely on the message-history side.

Content: small-cap alert channels, pump groups. The highest micro-cap signal
available for free, and the dirtiest — which suits a tool that ranks divergence
and displays source spread.

**Design implication (important):** channels are broadcast. One admin posts,
thousands read. The distinct-author eligibility gate in §6.1 is meaningless
here — every bucket has one author. Either Telegram never qualifies, or the gate
is bypassed and the spam defence is lost. See §4 below.

Handle `FloodWaitError` with backoff. Use `--` a dedicated account, not a
personal one.

### 2.4 Wikipedia Pageviews API — mention source (attention, not chatter)

Official, keyless, hourly granularity, no meaningful rate limit, no ToS risk.
Company-article pageviews as an attention proxy.

Best signal-per-effort item on the list: **zero ticker-extraction ambiguity**,
no bot noise, and it's genuinely independent of social chatter — which makes it
the only real corroboration source available. If mentions and pageviews spike
together, that's two independent measurements; if only mentions spike, that's a
bot or a brigade.

Symbol → article mapping comes from Wikidata (the ticker-symbol property), so
the mapping is automated, not hand-maintained. Refresh it on the existing weekly
`ticker_universe` job.

Gap: most micro-caps have no Wikipedia article. This source is strongest exactly
where the others are weakest (large/mid cap) and absent where they're
strongest — treat it as corroboration, not coverage.

### 2.5 InvestorsHub — mention source

Per-ticker penny-stock message boards. No API; HTML scraping. Structurally the
home of exactly what the Micro/Penny and Unknown tabs (§8.1) exist to surface.

Per-ticker boards mean tickers are unambiguous, so this can partly replace
StockTwits as an extraction calibration anchor (§4).

Check robots.txt and rate-limit conservatively.

### 2.6 FINRA daily short sale volume — context feed

Free daily files, per ticker. Feeds the squeeze case directly and gives §7.4 a
slice worth having: does divergence work better on heavily shorted names?

Daily grain only — it annotates, it doesn't drive intraday scoring.

### 2.7 Discord trading servers — mention source

A bot in the server plus the Message Content privileged intent. Technically
straightforward; the gate is social — an admin has to let the bot in.

**Do not use a user account / self-bot.** That is a ToS violation and a ban
vector.

Same broadcast caveat as Telegram for announcement channels; general chat
channels do have real distinct authors.

---

## 3. Considered and rejected

Recorded so these don't get re-litigated later.

| Source | Why not |
|---|---|
| **Threads** | Keyword search exists and is free, but requires Meta App Review approval for the `threads_keyword_search` permission before public posts are searchable at all — without it, search only covers the authenticated user's own posts. Reported quota is around 500 requests per 7 days. Dead at a 3-minute cadence. |
| **Google Trends** | The official API announced 24 July 2025 is still an application-gated alpha with most applicants never admitted; `pytrends` was archived April 2025. Good signal, unusable access. Revisit if it opens up. |
| **Lemmy / Mastodon** | Free APIs, Reddit-shaped data, but finance volume is negligible. Cost of a module exceeds the signal. |
| **TradingView ideas** | Has native bull/bear tags per symbol, which is attractive. No public API and the ToS forbids scraping. |
| **X / Twitter** | Unchanged from §3.1 — cost. |
| **ApeWisdom** | Free keyless API covering ~15 subreddits plus a 4chan beta, refreshed roughly twice hourly. Would restore the Reddit dimension, but returns *aggregated mention counts* from someone else's extractor — the §4.2 confidence model doesn't apply, the refresh is coarser than our cadence, and a dependency on a third party's ranking defeats the point of computing our own baselines. Fallback only. |

---

## 4. Design changes these force

Four things break or need extending. Do these before adding sources, not after.

### 4.1 Per-source-type eligibility gates (§6.1)

`distinct_authors` is the only anti-spam defence and it does not exist on
broadcast sources. Replace the single gate with a per-source-type rule:

| Source type | Eligibility signal |
|---|---|
| Forum / social (Bluesky, 4chan, iHub, Discord chat) | distinct authors |
| Broadcast channel (Telegram, Discord announcements) | forwards / views / subscriber count |
| Attention (Wikipedia) | absolute pageview floor |
| Context feed | none — never scored |

Store the source's type on the source module, not per bucket.

### 4.2 Context feeds must not touch `mention_z` (§6)

Enforce structurally: `radar_event` is a separate table and the scoring module
never reads it. A test should assert that `scoring.py` imports nothing from the
event layer.

### 4.3 Extraction calibration has no anchor (§4.2, §12.1)

StockTwits was the ground truth. Replacement options, in order of preference:

1. **InvestorsHub** — per-ticker boards give unambiguous symbol labels for free.
2. **Hand-labelled corpus** — a few hundred posts across Bluesky and `/biz/`,
   both directions, committed to the repo as the golden corpus in §10.

Do not calibrate against `/biz/`. See below.

### 4.4 4chan `/biz/` is mostly crypto and will poison extraction

`/biz/` is overwhelmingly crypto, and crypto tickers collide with live equity
symbols — **SOL, LINK, ADA and APE are all real listed tickers**. Under the §4.2
matching rules, a `/biz/` thread about Solana produces medium-confidence
mentions of an unrelated equity, and those become a fake spike.

Required before `/biz/` counts toward anything:

- A crypto-symbol blacklist applied to `/biz/` specifically, seeded from a
  top-500 coin list and refreshed with the universe job.
- `/biz/` mentions capped at medium confidence unless the post also contains the
  company name.
- Consider excluding `/biz/` from the equity radar entirely and treating it as a
  separate crypto surface later.

---

## 5. Bluesky — already in, one improvement

If ingest is currently polling search endpoints, switch to the **Jetstream
firehose**: full public stream, free, no auth, websocket JSON. It matches the
`fetch(since)` shape in §4.1 far better than periodic queries and removes the
truncation risk that polling has during high-volume periods (the same failure
described for Reddit in the change list).

---

## 6. Verify at implementation time

Same status as §12 open items — assumed correct here, confirm before building:

1. SEC EDGAR current rate limit and User-Agent requirements.
2. FINRA short volume file location and format.
3. Wikidata property id for ticker symbol, and coverage across the universe.
4. Whether InvestorsHub robots.txt permits this.
5. Discord Message Content intent requirements at current bot scale.
6. Bluesky Jetstream endpoint and whether it exposes everything the current
   ingest uses.
