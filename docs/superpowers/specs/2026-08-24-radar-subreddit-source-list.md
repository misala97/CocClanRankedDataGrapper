# Radar — subreddit source list

**Status:** Michi's list, written before Reddit was written off as a source and
restored to the repo 2026-08-24, when measurement showed Reddit's published
Atom feeds are still open even though the JSON API returns 403 and app
registration is closed.

Seed list for the Reddit source module (§3.2). Configuration, not code.

**Rollout:** Tier 1 first. Measure for a few weeks, then add Tier 2 **in one
batch** — each change to this list bumps `source_config_version` and starts a
baseline warm-up (change list item 5), so batching costs one warm-up instead of
nine.

**Subscriber figures are indicative only.** They come from public listings and
what matters is messages per day and ticker density, both of which the ingest
measures for free in the first week. Treat anything below as a starting point,
not a fact.

---

## Tier 1 — core volume

| Subreddit | Approx. size | Notes |
|---|---|---|
| `wallstreetbets` | ~20M | Primary source. Heavy sarcasm and inverted positions — this is the case §6.5's Haiku re-read exists for. |
| `stocks` | ~9.3M | High volume, mega-cap skew, slower turnover. |
| `Daytrading` | ~4.9M | More process and psychology than named tickers. Volume ≠ mentions here. |
| `StockMarket` | ~4.1M | Broad, news-driven. |
| `pennystocks` | ~2.1M | Core for the Micro/Penny segment. |
| `options` | — | Tickers named constantly; skews liquid. |
| `smallstreetbets` | — | Further down the cap curve than WSB. |
| `shortsqueeze` | — | Directly feeds the squeeze case. High pump density — that's the point, not a defect. |
| `SPACs` | — | Far quieter than 2021, but the only place SPAC chatter concentrates. Keep for the Recent IPO tab. |

## Tier 2 — narrower, add after Tier 1 is calibrated

| Subreddit | Notes |
|---|---|
| `RobinHoodPennyStocks` | Micro-cap, low quality, high pump density. |
| `wallstreetbetsOGs` | WSB offshoot — check author overlap before counting as an independent source. |
| `Wallstreetbetsnew` | Same caveat. |
| `thetagang` | Options sellers. Liquid names, little micro-cap value, but real tickers. |
| `swingtrading` | Multi-day horizon, names specific setups. |
| `Vitards` | Steel and commodities. Small, genuinely high-quality DD. |
| `Biotechplays` | Catalyst-driven micro-caps and FDA dates. Fills a gap the generalists miss. |
| `weedstocks` | Sector, micro-cap heavy. |
| `UraniumSqueeze` | Thin, spikes hard when the sector moves. |

---

## Config

```json
{
  "reddit": {
    "tier_1": [
      "wallstreetbets", "stocks", "Daytrading", "StockMarket",
      "pennystocks", "options", "smallstreetbets", "shortsqueeze", "SPACs"
    ],
    "tier_2": [
      "RobinHoodPennyStocks", "wallstreetbetsOGs", "Wallstreetbetsnew",
      "thetagang", "swingtrading", "Vitards", "Biotechplays",
      "weedstocks", "UraniumSqueeze"
    ],
    "correlated_clusters": [
      ["wallstreetbets", "smallstreetbets", "wallstreetbetsOGs",
       "Wallstreetbetsnew"],
      ["pennystocks", "RobinHoodPennyStocks"]
    ]
  }
}
```

---

## Do not add

| Excluded | Why |
|---|---|
| `Superstonk`, `GME`, `amcstock` | Single-ticker subs with enormous volume. One ticker gets a permanently inflated baseline and nothing else is contributed. Actively harmful, not merely useless. |
| `investing`, `ValueInvesting`, `SecurityAnalysis`, `Bogleheads`, `dividends` | Long horizon, mega-cap and ETFs. No signal at a day-trading cadence. |
| `algotrading` | Discusses methods, not tickers. |
| `IndianStockMarket`, `CanadianInvestor`, `ASX_Bets`, `UKInvesting` | Wrong exchange. NSE and TSX-V symbols collide with the US universe the same way crypto tickers do — same corruption vector as `/biz/`. |
| `CryptoCurrency`, `SatoshiStreetBets` | Wrong asset class. |

If a new subreddit is proposed later, it has to clear all four: US equities,
names tickers in text, active daily, and not a single-ticker community.

---

## Three design consequences

### 1. Source granularity is the subreddit, not "reddit"

Change list item 4 specifies per-source baselines. Apply that per **subreddit**,
not per platform. With 20M-member and 40k-member communities pooled into one
count, WSB is the only thing that ever moves the number and a real spike in
`Vitards` or `Biotechplays` is arithmetically invisible.

### 2. Megathreads need their own ingest path

In WSB a large share of ticker mentions live in one or two pinned daily
discussion threads carrying thousands of comments. Paginating by post will
systematically miss them.

Use the subreddit-level new-comments endpoint rather than walking per-post
comment trees, and treat pinned megathreads as continuous streams with their own
catch-up state. This interacts with change list item 8: the megathreads are
exactly where the page cap gets hit during a spike.

### 3. Cross-sub author overlap is not corroboration

The source-spread column treats three subreddits mentioning a ticker as
independent confirmation. The clusters listed in the config above share a
substantial user base, so that reading is too generous.

Compute pairwise author overlap from the 30-day `radar_post` store — it costs
nothing extra — and down-weight source spread within a correlated cluster.
Same problem and same fix as the Telegram operator-network check.

---

## First-week checks

Once ingest is live, confirm per subreddit before trusting any of the above:

- messages per day
- share of posts and comments containing ≥1 universe hit
- top 10 tickers — if it's all mega-caps, the sub is a news reposter and adds
  nothing to a discovery radar
- pairwise author overlap, to validate or correct `correlated_clusters`

Drop anything that fails, and record why in this file.

---

## What measurement has already settled (2026-08-24)

Added when the list came back into play. These are measured, not assumed.

- **The feeds are open.** `/r/<sub>/comments/.rss` returns 200 with no auth;
  `/r/<sub>/new.json` returns 403. App registration at `reddit.com/prefs/apps`
  no longer works, so OAuth is not available and anonymous feeds are the route.
- **§2 above is confirmed by the transport.** `/r/<sub>/comments/.rss` IS the
  subreddit-level new-comments endpoint, so megathread comments arrive without
  walking post trees. There is nothing extra to build for that case.
- **Rate limiting is the binding constraint, not volume.** Sixteen requests in
  thirty seconds earned a sustained 429 on a residential IP. Feeds hold only
  25 entries, so poll cadence must be derived per subreddit from how fast that
  window turns over, and the request budget is what limits how many subreddits
  can be carried at once.
- **Measured turnover, first pass:** `wallstreetbets` 818 comments/hour (feed
  turns over every 1.8 min), `stocks` 67/hour, `pennystocks` 27/hour,
  `smallstreetbets` 14/hour. Comment volume is not mention volume — see
  `scripts/discover_reddit_sources.py`, which scores each candidate with the
  real extractor and reports equity mentions per hour instead.
