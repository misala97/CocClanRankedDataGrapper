# Yahoo usage conditions — official sources read 2026-09-15

Technical access and permission are different questions. This note records what the official documents say; it is not a legal conclusion.

## Sources (fetched 2026-09-15 via WebFetch, summarised; short quotes)

1. **Yahoo Terms of Service** (legal.yahoo.com/us/en/yahoo/terms/otos/, "Last Updated May 6, 2025", US version dated May 15, 2025)
   - §2.4(i) Member Conduct: you may not "access or collect data, or attempt to access or collect data, from our Services using any automated means … for any purpose without our express, prior permission."
   - §2.5: "you may not access or reuse the Services, or any portion thereof, for any commercial purpose."
   - §2.4(j): no use of content "to create any database, archive, mobile application, data feed, widget or any other aggregated data source that competes with or constitutes a material substitute for the Services".
   - §2.8: no reproduction/derivative works of "the Services (including content, advertisements, APIs, and software)" for commercial purposes.
2. **Yahoo Developer API Terms of Use** (legal.yahoo.com/us/en/yahoo/terms/product-atos/apiforydn/, revised 3-2022): a registered API key "must accompany all web services requests"; no selling/deriving income from the APIs without written permission. The `/v8/finance/chart` endpoint the candidate (and the existing ingest) uses is not one of the keyed developer APIs; these terms do not name a Finance chart API.
3. **Yahoo Finance help, "Finance for web" data page** (help.yahoo.com/kb/finance-for-web/SLN2310.html): "You must not redistribute information displayed on or provided by Yahoo Finance." and "All data provided on Yahoo Finance is provided for informational purposes only, and is not intended for trading or investing purposes." No programmatic-access permission is described.

## Reading against this application's use

- The candidate's acquisition is automated collection of chart data by a program (one bounded request per chart, per process, ≤10/min). §2.4(i) makes that conditional on "express, prior permission", which this project does not hold. Radar is a private single-owner tool, not a commercial or redistributing service, which bears on §2.5/§2.4(j)/help-page redistribution but not on §2.4(i).
- Technical access exists today: run_radar_ingest.py already instantiates `YahooProvider(YahooHttp())` (three call sites) against the same public chart endpoint. Per SPEC §1, existing use does not establish permission.
- **Decision taken in this preflight:** the documented conditions are not consistent with unattended automated requests without permission, so the optional up-to-four live requests were **not made** (provider request count: 0). The exact request form was instead exercised against a loopback server on the host (see linux-subprocess-harness.out.json: `/v8/finance/chart/AAPL?interval=5m&period1=1788960600&period2=1789502400&includePrePost=false`, headers Accept / Accept-Encoding / Connection / Host / User-Agent, no cookie).
- Consequently: live epoch-form compatibility, closed-session/holiday behaviour and throttling behaviour remain **unverified**, and `RADAR_SELECTED_PRICE_YAHOO_ENABLED` activation stays an unresolved owner ruling on usage conditions, not a technical gate.
