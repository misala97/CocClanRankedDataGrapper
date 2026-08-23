# Radar — reach the small stuff

## What this is for

Michi, correcting my framing: *"The main reason I do this is for penny stocks
and more unknown stocks and stuff. That people talk about Apple, Tesla etc is
no surprise."*

Three changes, all aimed at that. None of them adds a source — two attack
volume from the firehose already running, and the third aims the surface at
the segment the tool exists for.

## Context: why not a new source

Two candidates were investigated and both closed:

**Telegram** — the session works and 74 channels were profiled. Exactly one
uses cashtags meaningfully (`@intelligentsophieecommunity`, ~17 scored
mentions/day against Bluesky's ~1,300). Bare tokens can never be promoted on a
broadcast source, because promotion requires a *different author* cashtagging
the same ticker and a channel has one author by construction. One channel also
cannot clear the two-channel broadcast gate. Not wired in.

**InvestorsHub** — `robots.txt` permits the board paths, but the sitemap it
advertises returns a Cloudflare interstitial, and so do the ticker URLs. Active
bot detection. Not built: an ingest that works by looking enough like a browser
to pass a challenge is bot-detection evasion regardless of what robots.txt says.

That leaves the source already running. Bluesky's Jetstream sees every public
post, ~144k/hour, and the extractor throws away everything that is not a
cashtag.

---

## Part 1 — Distinctiveness counts issuers, not listings

### The bug

`universe.annotate_distinctive` marks a name token distinctive when it appears
in at most `MAX_NAME_TOKEN_DF = 3` names. Measured against the live 12,359-symbol
universe, this fails for the most-discussed tickers on the board:

| token | document frequency | why |
|---|---|---|
| `tesla` | 4 | Tesla Inc. plus three leveraged ETFs tracking it |
| `nvidia` | 4 | NVIDIA plus three ETFs |
| `alphabet` | 5 | five share classes of one issuer |
| `apple` | 4 | Apple, two ETFs, and Apple Hospitality REIT |

The rule cannot tell *"appears four times because three are its own
derivatives"* from *"appears four thousand times because it is boilerplate"*.

**This is live, not hypothetical.** A bare mention is promoted to `high` only
when a distinctive name token appears in the same post, so today a Bluesky post
reading "TSLA ripping, Tesla to the moon" scores `low` and is never counted.

### The fix

Count **issuers**, and exclude funds from the count:

- An issuer is the name up to its first comma or ` - `, so `Alphabet Inc. -
  Class A Common Stock` and `Alphabet Inc. - Class C Capital Stock` are one.
- Names matching a fund/derivative pattern (`ETF`, `ETN`, `Fund`, `Trust`,
  `Index`, `Inverse`, `Bull`, `Bear`, `2X`, `Daily Target`, `Warrant`,
  `Rights`, `Unit`, `Notes due`, `Preferred`, `Depositary`) do not contribute
  to any token's count. A derivative naming its underlying is not independent
  evidence that the name is common.

Both are needed: excluding funds alone leaves Alphabet's five share classes,
and issuer-deduping alone leaves Tesla's three ETFs.

The ceiling stays at 3. This is not a threshold change — raising it to 10 was
measured and admits `peace`, `golden`, `rock`, `standard`, `union`, which are
ordinary English words.

### What it actually buys, measured

**512 operating companies** gain a distinctive token they did not have. The
segment michi cares about is well represented:

```
SBFM   Sunshine Biopharma        GRML   Greenland Mines Ltd
HTOO   Fusion Fuel Green PLC     SACH   Sachem Capital Corp
LPAAU  Launch One Acquisition    IPEXU  Inflection Point Acquisition
```

Micro-cap biotechs, miners, and SPAC units — because a recent IPO lists as
Common Stock plus Units plus Warrants plus Rights, which is the small-cap
version of Tesla's ETF problem.

### The cost, stated plainly

`peace` goes 4 → 1 (from `Peace Acquisition Corp - Warrant`) and `golden`
4 → 2. Some ordinary words become distinctive.

This is narrower than it sounds: promotion still requires the **bare ticker in
the same post**, so it only misfires on a post containing both `PEACE` and the
word "peace". Accepted, and worth pinning with a test so the next person knows
it was a decision rather than an oversight.

### And the version stamp has to see it

`source_config_version` hashes the source list, the per-source policy, the
stopwords and the two regexes. It does **not** hash the distinctiveness
parameters — but this change promotes mentions that previously stayed `low`,
which changes what gets counted, which is exactly the discontinuity the stamp
exists to warm up from.

So `MAX_NAME_TOKEN_DF`, `MAX_NAME_TOKEN_RATIO`, `MIN_NAME_TOKEN_LEN` and the
fund pattern join the hash. The same omission bit this project on 2026-08-22,
when the stamp covered only the source list and three extraction fixes shipped
without invalidating the baselines built under the old rules.

---

## Part 2 — Bare tokens on Bluesky, measured before it stays

### Why this was off, and why that reasoning has expired

`BARE_TOKENS_ALLOWED['bluesky'] = False`, set after measuring that Bluesky's
top bare tokens were `IA` (Iowa), `GOP` and `AP`. Correct at the time.

Since then the confidence tiering changed what a bare token costs. An
uncorroborated bare token is stored as `low`, and **`low` is never scored**
(`buckets._SCORED = {'high', 'medium'}`). It becomes countable only by:

- a distinctive company-name token in the same post → `high`, or
- a *different author* cashtagging the same ticker in the same 15-minute
  bucket → `medium` at rollup.

Both were verified on real Telegram data: channels whose bare tokens were
`RSI`, `ROE`, `DMA` and `GROW` produced **zero** high-confidence hits.

The second path needs many independent authors, which Bluesky has and a
broadcast channel does not. This is the source where the mechanism can work.

### The change

`BARE_TOKENS_ALLOWED['bluesky'] = True`. One line.

It interacts with Part 1: with `tesla` distinctive again, "TSLA ripping, Tesla
to the moon" promotes immediately rather than waiting for a second author.

### Measure first, and be willing to revert

**This ships behind a measurement, not a decision.** Run it live, then after
one hour report, per source:

- scored mentions (`high` + `medium`) per hour, against the current baseline
- the twenty loudest tickers by scored mentions
- the `low`-to-`medium` promotion rate — the mechanism this rests on
- `distinct_text_ratio` across new buckets, as the spam check

**Keep it** if scored volume rises and the top tickers are recognisably
equities. **Revert** if `IA`, `GOP`, `AP` or similar appear in the top twenty.
The measurement is the deliverable; the flag is one line either way.

Note this changes `source_config_version`, so it resets baselines by design —
the same warm-up the extraction fix caused. Batch it with Part 1 so there is
one reset, not two.

---

## Part 3 — Default the board to what it is for

Today the board opens on **All**, so a matured board will read megacaps and
micro-caps in one list. The segment tabs exist and, since the profile job
shipped, finally have real market caps behind them.

Add a **`Small`** grouping — `micro` + `unknown` + `recent_ipo`, i.e. anything
not `large` or `mid` — and make it the default. `All` stays one click away.

**`Small` is a filter, not a segment value.** `universe.segment_for` keeps
returning exactly one of the five, and each row keeps reporting its own; the
filter accepts a SET of segments rather than one. Making it a sixth return
value would mean a micro-cap was no longer `micro`, and the segment counts
would stop summing to the total.

**`unknown` is an assumption and should be labelled as one.** It means no
market cap, not a small one. Folding it into `Small` asserts something not
known. It is defensible because a ticker no provider has profiled is
overwhelmingly a tiny one, and because the alternative — defaulting to `micro`
alone — hides most of the board while profiles fill in. If `unknown` ever
stops being dominated by small names, this is the assumption to revisit.

This does not touch scoring, only which rows are shown first.

### What this does NOT need

Nothing about megacap dominance needs fixing in the ranking. `mention_z`
already measures each ticker against **its own** baseline: SPY at fifty
mentions an hour is normal for SPY and produces no spike, while a micro-cap
going from zero to eight is enormous. The live board currently shows SPY, NVDA
and QQQ on top because every baseline is about two days old and every row reads
`provisional` — a ticker needs history before "unusual for it" means anything.
That resolves itself over roughly a fortnight with no code.

Resisting the urge to "fix" it in the ranking is the point. A size penalty
would be a second mechanism doing the same job as the z-score, and the two
would fight.

---

## Testing

- **Distinctiveness:** Tesla, NVIDIA, Alphabet and Apple gain a token;
  `common`, `stock` and `bancorp` do not. A SPAC listing as Common Stock plus
  Units plus Warrants counts once. **Teeth:** each assertion must fail under
  the old plain-count rule, or it is testing nothing.
- **The accepted cost:** a post containing both `PEACE` and "peace" promotes.
  Asserted deliberately, so the trade is recorded rather than discovered.
- **Bare tokens:** a Bluesky post with a bare ticker and no corroboration is
  stored `low`; the same post with a distinctive name token is `high`. Neither
  is new behaviour — the test is that the flag reaches the extractor.
- **Segment:** `Small` unions the three; `All` still returns everything; the
  segment counts still come from the unfiltered pass.

## Risks

- **Bare tokens could still flood Bluesky.** The whole of Part 2 is a
  measurement for this reason. Reverting is one line.
- **512 companies is 4% of the universe.** Real, and it lands on the segment
  that matters, but nobody should expect the board to transform.
- **None of this adds a venue.** After Telegram and InvestorsHub both closed,
  breadth stays at two sources. Discord remains the only untried volume
  candidate and its blocker is social — an admin has to admit a bot.
