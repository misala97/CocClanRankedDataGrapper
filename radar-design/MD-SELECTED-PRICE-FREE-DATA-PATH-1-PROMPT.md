# Copy/paste prompt — MD-SELECTED-PRICE-FREE-DATA-PATH-1

```text
You are Radar's Researcher. Return your result to the Mastermind.

Assignment ID: MD-SELECTED-PRICE-FREE-DATA-PATH-1

Objective:
Resolve the one remaining material blocker for priority C: select a genuinely usable EUR0 selected-instrument data path for Radar's 1D chart, or prove that no candidate currently meets the owner's constraints. This is a narrow decision assignment, not another broad provider survey and not implementation.

Workspace:
C:/Users/michi/Desktop/CodingStuff/.worktrees/radar-selected-price-charts

Branch / verified base and expected current HEAD:
codex/radar-selected-price-charts
f632e5db5dd92e27480cbfccdf7b0638b26533ed

Before acting:
- Verify branch, HEAD, origin/main, status, diff and recent log with per-command safe.directory.
- Preserve every dirty/untracked file. Current continuity/research/preview/release artifacts are intentionally local and uncommitted.
- Do not modify another worktree, production, databases, services, provider flags, Remote Control sessions or saved credentials.

Read fully, in this order:
1. C:/Users/michi/Desktop/CodingStuff/.worktrees/radar-selected-price-charts/radar-design/WORKFLOW.md
2. .../radar-design/MD-SELECTED-PRICE-AREA-DATA-PLAN.md
3. .../radar-design/MD-SELECTED-PRICE-RELEASE-CLOSURE.md
4. .../radar-design/MD-SELECTED-PRICE-EVIDENCE-1-RETURN.md
5. .../radar-design/MD-SELECTED-PRICE-EVIDENCE-1-RULING.md
6. .../radar-design/artifacts/md-selected-price-release-preflight/yahoo-usage-conditions.md
7. .../radar-design/artifacts/md-selected-price-personal-preview/DIAGNOSIS.md
8. .../radar-design/US-USD-ONLY-DECISION.md
9. Existing provider adapters: personal_apps/features/radar/prices/finnhub.py, twelvedata.py, massive.py, yahoo.py; and personal_apps/features/radar/price_chart_fetch.py plus price_chart_acquisition.py.

Current facts and decisions:
- Owner order is C -> A -> B. This assignment is C0 only.
- 1D is the priority. Accepted renderer: compact continuous area chart connecting actual reported prices within a session, subtle fill, no broken line/dot at every missing minute. That renderer is not yet implemented.
- Preview chatter is synthetic. Production already has real aligned Radar chatter/tone through the deployed selected-price endpoint.
- FT does not need 390 synthetic values: Yahoo and Nasdaq both produced the same 64 regular-session FT time/price observations; AAPL Yahoo produced 390/390. Connections are visual guides, not observations.
- Charts are live; new Yahoo acquisition is OFF. The earlier charts-only release and HA1 are closed and must not be reopened.
- Yahoo and Nasdaq are technically demonstrated but current reviewed terms do not establish permission for unattended automated capture. Do not repeat their broad technical probes. Finnhub's existing path proves /quote, while repository evidence says its free tier returned 403 for /stock/candle. Twelve Data currently serves daily data; Massive serves grouped daily data. Intraday entitlement for the existing Twelve Data/Massive credentials is unproved.
- Radar is private/personal, budget EUR0, no paid subscription or purchase. Do not create an account, accept new terms, buy anything or activate any provider. If a new free account is the only viable route, return that as a specific owner decision.
- C is US-primary/native-USD only. Do not investigate German/EUR support.

Mandatory pass criteria for a source:
1. EUR0; no paid subscription or purchase. State separately whether a new free account/key would be required.
2. Current official documentation/applicable terms support automated private/personal use for this integration. HTTP success is not permission.
3. US equity identity/currency coverage with a liquid common share, ETF, small/less-liquid listing and class-share symbol behavior.
4. Timestamped actual observations for the current or most recent regular 1D session, suitable for a connected reported-price line. Full 390-minute coverage is not required; unavailable must differ from zero.
5. Sustainable on-open use at <= one visible-chart refresh per minute with a documented quota or a conservative enforceable budget.
6. 1W intraday is desirable, not mandatory. If absent, Radar can retain its stored daily-close 1W fallback.

Research bounds:
- Start with existing configured providers: Finnhub, Twelve Data, Massive. Inspect whether relevant credential names are configured without printing or copying secret values.
- A current repository-proven 403, plan exclusion or official entitlement table may close a candidate without another live call.
- Screen at most three additional documented EUR0 candidates. Prefer official APIs or downloads; do not propose page scraping.
- Use primary/current provider documentation and terms. Cite URLs and access dates. Clearly separate source fact, observed result and inference.
- Live probes are optional and allowed only after a candidate passes the documentation/permission screen. Maximum 12 provider requests total, sequential, one attempt per request shape/instrument, <=15 s timeout, fixed ordinary headers, no proxy/cookie/session workaround, no retry. Stop all probes on 401/403/429 and record the result. Do not discover rate limits by load.
- Do not use production, Radar's DB, or provider acquisition flags. Do not print response headers/bodies that contain credentials or account identifiers. Save only sanitized small artifacts.
- No subagents. No application/test/config/schema edits, account creation, provider activation, commit, push or deployment.

Required deliverables:
1. A candidate matrix with PASS/FAIL for every mandatory criterion and the evidence for each cell.
2. A concise disposition of Yahoo, Nasdaq, Finnhub, Twelve Data and Massive that reuses existing evidence and does not repeat closed work.
3. For each candidate that passes documentation first: exact endpoint/request shape, timestamp/bar semantics, currency/listing identity, regular-session bounds, null/empty/error behavior, representative sample result, quota and terms/entitlement.
4. The smallest integration recommendation against the existing normalized child boundary: identify exact files/interfaces likely to change, but do not edit them.
5. One final recommendation only:
   - IMPLEMENT <named source and exact role>, or
   - STORED-ONLY RENDERER because no source passes, or
   - OWNER DECISION REQUIRED for <named free-account or exact constraint change>.
   Never recommend implementation with unresolved permission, entitlement or identity.
6. Create:
   - radar-design/MD-SELECTED-PRICE-FREE-DATA-PATH-1-RETURN.md
   - radar-design/artifacts/md-selected-price-free-data-path-1/README.md
   - sanitized request/summary artifacts only if probes actually run
   Update only the current notices in radar-design/MD-SELECTED-PRICE-LEDGER.md and root HANDOFF.md. Preserve historical text.

Evidence and stop condition:
Finish when the Mastermind can either name one usable source with its exact permitted role, account state, 1D/1W capability, identity checks, traffic budget and limitations, or can state precisely why none passes. Do not broaden into whole-universe polling, headlines, scoring, German data, candles, provider activation or UI work.

Your final response must end with this complete copy/paste return prompt, filled with actual facts:

You are Radar's Mastermind / Overview. Assess the Researcher return for assignment MD-SELECTED-PRICE-FREE-DATA-PATH-1.

Workspace: C:/Users/michi/Desktop/CodingStuff/.worktrees/radar-selected-price-charts
Branch / base / current HEAD: [exact verified values]
Working tree: [all dirty/untracked paths and ownership; committed/pushed status]
Binding artifacts: [absolute plan, return, ledger and evidence paths]

Objective and authorized scope: Select or rule out a EUR0, automation-permitted, US/USD selected-instrument 1D data path under the bounded research rules; no implementation or activation.
Completed work: [candidate screening, documentation, any bounded probes, integration trace]
Evidence: [primary-source URLs/access dates; exact sanitized commands/request count/results; saved artifacts]
Evidence attribution: [fresh worker execution vs repository reports vs inference]
Candidate decision matrix: [PASS/FAIL for each mandatory criterion]
Findings and limitations: [coverage, session, identity, terms/entitlement, quotas, untested behavior]
Recommendation: [exactly IMPLEMENT named source / STORED-ONLY RENDERER / OWNER DECISION REQUIRED]
Actions taken: [files created/updated; explicitly no account/provider/config/DB/production/commit/deploy action]
Protected state: [preserved worktrees, services, databases, credentials and dirty files]
Subagents: none
Updated artifacts: [absolute local/uncommitted paths]
Requested Mastermind decision: [accept source and prepare C1 implementer packet, accept stored-only path, or rule on exact owner decision]
Next bounded action recommendation: [one action; do not redispatch completed research]

Read the current handoff and ledger, verify Git/artifact evidence, make the product ruling and update planning continuity. Do not implement, deploy, activate a provider or dispatch workers automatically.
```
