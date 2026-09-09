# Radar design progress

## Completed
- Discovery: user goals, independence, markets, horizons, manual trades and scope confirmed in conversation.
- Read current Radar product context and representative data contracts. Old product exclusions explicitly superseded in future brief.
- Drafted BRIEF.md covering hub architecture, flows, page contracts, mobile, states and future capabilities.

## Completed for review 01
- Three generated visual direction probes saved and visually inspected: probes/a-daily-brief.png, probes/b-research-desk.png, probes/c-discovery-atlas.png.
- These are static direction tests, not interactive or numerically validated screens. All content is fictional.

## Current stage
- Owner liked the prototype and chose Codex planning / Claude implementation. Direction: A overview + B research workflow, light/green. C rejected.
- IMPLEMENTATION-SPEC.md, two dated implementation plans, FOUNDATIONS-LEDGER.md, HUB-LEDGER.md and CLAUDE-START.md now form the execution package. All implementation tasks remain open.

## Roadmap review
- Owner praised first interactive mockup and requested a roadmap from present capabilities to future hub.
- ROADMAP.md written from local backend/API/model/configuration inspection at dev_personal HEAD 7a9ffe445076e57d02fea5627e8cd185ec9cb39f.
- Proposed sequence: baseline + historical capture; real-data research hub; manual portfolio/alerts; news; analysis; qualified combined recommendations. Long-term/broker expansion is a separate lane.
- Repository existence distinguished from live readiness. No production queries or test-suite runs performed for this roadmap. Newest v3 retrain record supersedes older “no judge” notes.
- No application implementation started. Release 0/1 plans are written; Claude starts with the workspace/baseline gate.

## Completed for review 02
- Standalone interactive prototype: index.html, preview.css, preview.js; local server serve.cjs.
- 11 views: overview, chatter, news/professional, combined, research, watchlists/alerts, portfolio, analysis, activity, admin, manual entry/correction.
- Connected watch, evidence, search/filter, trade/partial-sale, alert, journal and replay interactions; local-only fictional data.
- Browser check completed after final visual fixes: 33 route/viewport combinations (1440, 768, 390 widths), zero document overflow, zero page errors.
- Seven interaction checks passed: watch persistence, evidence tabs, filters, oversell + partial sale, alert creation, scenarios, search/dismissal.
- Viewed desktop overview/research/portfolio/chatter/news/combined/analysis/activity/admin and phone research screenshots. Fixed concatenated company labels and mobile chart label scaling.
- Numeric sample portfolio: $2,210 holdings, $182 unrealized, $10.40 realized under prototype average-cost method including fees.
- REVIEW.md documents simulation boundaries, review flows and outstanding design work. DESIGN.md records selected identity.
- Preview running at http://127.0.0.1:5187; exec session 73154. Restart with node serve.cjs from this folder if unavailable. Codex browser open request returned queued.

## Probe review notes to carry forward
- A: approachable home and clear story hierarchy; remove generated slogans, stock photos and unnecessary card borders; group flat navigation. Generated profile identity is fictional, not owner data.
- B: strong research relationship between candidates, chart and thesis; remove duplicated navigation, repeated watch controls and excessive pills; no implication of a measured investment edge.
- C: useful optional comparison mode; generated axis is mathematically inconsistent (negative ratio values), selected price deltas disagree and several points do not match their rows. Do not copy these values or semantics into an interactive prototype. Specify either a signed change measure or a nonnegative relative-rate measure, keep timestamps aligned, and synchronize chart/list/detail from one fixture.
- Dates, source counts, news and returns in all probes are illustrative and not factual. Final mockups need coherent shared fixtures, explicit units/time windows and realistic sample sizes.

## Open
- User feedback on the rendered hub; no claim of final design approval.
- Deeper EUR/listing/FX mockups, long-term datasets, complete alert editing, complete per-page state coverage and mobile prioritization.
- Future page details beyond the first-release spec remain open; ROADMAP.md is complete.

Codex performed planning only. Claude is the selected implementer; deployment is outside this package. Do not mark the full design complete after the first direction review.
