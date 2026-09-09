# Radar interactive review 02

Open http://127.0.0.1:5187/#overview while the preview server is running.
Restart from this folder with `node serve.cjs`. It serves only this design folder on localhost, port 5187. No build or dependency installation is needed.

## Pages

Overview, Human chatter, News & professional, Combined radar, Stock research, Watchlists & alerts, Portfolio & trades, Analysis, Activity, Administration, and Record/correct trade.

## Try these connected flows

1. Overview → Understand the signal → Counter-evidence → Source posts → Watch stock.
2. Stock research → Record a trade → fill actual price/quantity → Save → Transactions → Positions.
3. Portfolio → Record sell → enter more than the available shares to see the validation → correct to a partial close → inspect remaining quantity.
4. Watchlists → New alert → save a local rule → mute/resume or mark a sample change seen.
5. Analysis → move through the saved example snapshots → write and save a review note.
6. Chatter → search or filter → Verified on Scalable → inspect how unknown availability is handled.
7. Portfolio → Hypothetical → create an entry without changing the sample actual-trade ledger.

The bottom Page state selector exposes first-use/empty, delayed coverage, connection error and loading examples. Not every state has a unique page-specific design yet. Reset demo restores only this prototype's local sample data.

## What this prototype is

A locally interactive design artifact. All companies, prices, stories, trades, source posts, recommendations and operational figures are fictional. There are no application/backend/broker calls. Demo transactions, alerts, watchlists and notes are saved only under `radar-design-v2` in this browser's local storage.

The actual-trades label describes the proposed account type, not imported real transactions. The ledger supports average-cost calculations, partial sells, entry fees, corrections and separate hypothetical trades. Its limited accounting model is not a production portfolio implementation. This prototype uses USD sample listings and USD reporting; currency/FX selection, transfers, corporate actions and tax accounting are not implemented.

Research horizon changes assessment copy and the initial chart range. The underlying chatter fixtures are shared rather than a full long-term dataset. Chart series are illustrative. The chart inspector demonstrates accessible value inspection, not a complete market-chart interaction system. Historical replay is a scripted set of sample snapshots, not an evaluation engine. Signal outcomes are explicitly a fictional study. Alerts save rules but never monitor or send notifications. Admin status is display-only.

## Verification

`check_preview.py` runs browser verification at 1440×1000, 768×1024 and 390×844, captures desktop/phone screenshots, and checks navigation, search, evidence tabs, filtering, watch persistence, oversell validation, partial sale, alert creation and scenario switching. Results are in QA.json. It resets only the demo local-storage key through the prototype and uses its own fresh browser context.

Screenshots are under screenshots/. These checks verify the preview artifact, not production readiness or predictive accuracy.

## Next design review

Review the overview and research first: visual identity, usable density, clear hierarchy and whether the handoff between them feels natural. Then review the supporting pages, recommendation language and portfolio workflow. Still open: EUR/listing/FX flows, evidence-history details, deeper long-term mode, complete alert editing and dedicated mobile prioritization. No app implementation should begin from this prototype without another explicit instruction.
