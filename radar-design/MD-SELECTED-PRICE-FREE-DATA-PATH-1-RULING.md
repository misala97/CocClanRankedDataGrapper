# MD-SELECTED-PRICE-FREE-DATA-PATH-1 — Mastermind ruling

2026-09-16. Planning/evidence assessment only. No implementation, account creation, credential handling, provider activation, API probe, database, production, service, commit, push or deployment action.

## Owner disposition — 2026-09-16

The owner confirms Radar is owner-only and a consolidated SIP delay of at least 15 minutes is acceptable. The owner selects the Alpaca path. Binding record: `radar-design/MD-SELECTED-PRICE-ALPACA-OWNER-DECISION.md`. Stored-only remains fallback rather than the primary C1 choice. Next is owner account/key setup, then the prepared bounded validation prompt `radar-design/MD-SELECTED-PRICE-ALPACA-VALIDATE-1-PROMPT.md`. C1 remains blocked until validation passes.

## Decision

Accept the Researcher return as a sufficient bounded provider screen. It closes Yahoo, Nasdaq, Finnhub candles, Twelve Data Basic, Massive Basic, Tiingo Starter and Alpha Vantage free for the stated on-open 1D role under the owner's current constraints. Do not repeat that survey.

The return's final recommendation is accepted with one correction:

- **Alpaca Market Data Basic passes the documentation/permission screen, not final gate C0.** Official documentation supports a free Basic plan for personal trading applications, US stocks/ETFs, IEX real time, SIP historical data ending at least 15 minutes before now and 200 historical requests/minute. The terms allow personal, non-commercial use and require advance notice if the content is made available to others.
- **The source is not yet implementable.** Radar has no Alpaca account or credential, and the return explicitly leaves actual response behavior, representative symbol coverage, class-share spelling, identity validation, empty/error envelopes and the exact delayed-SIP boundary unverified. Mandatory criteria C3/C4 and the plan's "without inference" acceptance condition therefore remain open.
- A free **Paper Only** account is a plausible path: Alpaca currently says anyone globally can create one, and its Basic plan is the default for Paper and Live accounts. Creating the account and accepting its agreements are owner actions and are not authorized by this ruling.

## Product fork requiring the owner

1. **Owner says yes to a free Alpaca Paper Only account.** The owner creates the account and supplies the credentials through the project's normal secret mechanism. Then run one narrow `MD-SELECTED-PRICE-ALPACA-VALIDATE-1` verification assignment before C1. It may only prove the already documented path with bounded calls: plan/account identity, AAPL, SPY, FT, one small listing, BRK.B/BRK-B behavior, nonexistent/empty behavior, current-session delayed SIP bars, one IEX comparison, quota/error semantics and sanitized evidence. No adapter or UI implementation, provider activation or production access. Only after that evidence passes C0 may the Mastermind write the Alpaca C1 implementation packet.
2. **Owner says no.** Select `STORED-ONLY RENDERER` and write C1 for the accepted continuous area chart over the already deployed `stored_quote` 1D and `daily_close` 1W paths, with explicit sparse/stored provenance. No more provider research.

Do not combine SIP and IEX into one continuous price regime. If Alpaca later passes, the consolidated SIP line ends at least 15 minutes before now; any IEX-only live tail is a separately labelled partial-tape regime and may be omitted from the first implementation.

## Evidence assessment

- Git is verified at branch `codex/radar-selected-price-charts`, HEAD `f632e5db5dd92e27480cbfccdf7b0638b26533ed`, equal to `origin/main`; no commits were added.
- The Researcher made zero provider API calls and preserved the dirty worktree. Its owned return/evidence files exist.
- Current official Alpaca documentation independently rechecked by the Mastermind on 2026-09-16 describes the Basic plan as free, covering US stocks/ETFs, IEX real time, historical data excluding the latest 15 minutes and 200 historical calls/minute. The FAQ says historical SIP queries require an `end` at least 15 minutes old. The Terms and Conditions permit personal/non-commercial use and require 30 days' notice before making a user application available to others.
- The return's provider matrix is accepted as documentation/repository evidence, not live provider proof. Its legal/permission classifications remain engineering gates, not legal conclusions.

## Current state and next action

C0 research is complete; C0 source acceptance is waiting on one owner decision. No worker is running and none is prepared or dispatched by this ruling. Charts remain ON, new Yahoo acquisition remains OFF, and the closed selected-price/HA1 releases stay closed.

**Question to owner:** Do you want to create a free Alpaca Paper Only account for Radar's private selected-price chart, accepting a consolidated SIP line delayed by at least 15 minutes and keeping the data owner-only unless Alpaca's notice/permission requirements are satisfied? If no, Radar proceeds with the stored-only area renderer.
