# Radar Xetra History-Proxy Mapping Fix

**Date:** 2026-09-01  
**Status:** Approved in chat; awaiting repository review  
**Scope:** German market-data mapping generation, activation, and historical
backfill eligibility

## Problem

Radar correctly activates Tradegate BSX (`XGAT`) as the preferred German
price venue, but each mapping-generation decision currently retains only that
one preferred venue. The history reader requires a second, verified Xetra
(`XETR`) instrument with the same ISIN before it may compose older Xetra proxy
closes with newer native Tradegate closes.

Because generation activation does not persist that secondary Xetra identity,
the production German backfill found only 13 pre-existing Xetra rows even
though 2,517 German primary mappings were active. Live Tradegate prices work,
but most week, month, and year charts cannot acquire older history.

## Decision

The audited, hashed German mapping generation will own both identities needed
by the product:

- one preferred primary price identity, using the existing `XGAT`-then-`XETR`
  venue priority;
- for an `XGAT` primary only, an optional non-primary `XETR` history-proxy
  identity.

The proxy is valid only when OpenFIGI resolves the same US share class to one
supported Xetra candidate and the complete official Xetra reference catalog
confirms that candidate has the same ISIN as the selected Tradegate primary
and uses EUR. Missing, ambiguous, unsupported, currency-mismatched, or
ISIN-mismatched Xetra candidates produce no proxy. They do not invalidate an
otherwise valid Tradegate primary.

This keeps proxy identity inside the same generation hash and operator audit
boundary as the live mapping. Backfill-time discovery is rejected because it
would create unaudited mapping state that generation rollback could not
reproduce.

## Generation Contract

`MappingDecision` gains optional Xetra history-proxy fields. Existing payloads
without those fields remain byte-for-byte hash-verifiable and readable. The
canonical serializer omits absent optional proxy fields, while new payloads
include populated proxy fields in their SHA-256 identity.

For a mapped Xetra primary, the primary itself supplies German history and no
secondary proxy fields are stored. For an unavailable decision, all primary
and proxy identity fields are absent.

The existing identity audit continues to review the user-visible primary
mapping. Its generation hash binds the secondary proxy data as well, so any
proxy change invalidates an audit for the previous generation.

## Activation and Rollback

Generation activation remains one transaction. For every ticker governed by
the generation it first makes prior German venue rows non-authoritative, then:

1. applies the selected primary row as mapped and primary;
2. applies a verified Xetra history-proxy row as mapped and non-primary when
   present;
3. leaves every other German row for that ticker unavailable and non-primary.

This prevents a removed or changed proxy from remaining silently eligible for
history. Both primary and proxy rows carry the activated generation ID.

Rollback uses the same application path. Legacy generation payloads have no
proxy fields, so rolling back removes the new generation's proxy authority and
restores only the identities recorded by the legacy snapshot.

No schema migration is required: `radar_instruments` already supports one row
per `(ticker, market, mic)`, primary/non-primary state, mapping status, ISIN,
and generation ownership.

## Backfill and History Composition

The existing German backfill remains the only historical bootstrap writer. It
selects mapped Xetra instrument rows, validates Yahoo response metadata against
`XETR`, and writes EUR split-adjusted closes under the exact Xetra identity.

After a new proxy-aware generation is activated, rerunning
`backfill_radar_market_history --market de --apply` automatically includes the
new secondary rows. Existing successful history is idempotently retained.
The history reader's current exact-ISIN seam remains unchanged: Xetra may fill
only dates before the first native Tradegate date.

## Compatibility and Deployment

The currently active production generation remains usable after deploying the
code, but it will not gain proxy rows retroactively. The operator sequence is:

1. deploy the compatibility-safe code;
2. run the mapping refresh to create a new proxy-aware shadow generation;
3. run and review the German activation report and identity audit for that
   exact generation hash;
4. activate the new generation, retaining the current active generation as
   rollback evidence;
5. rerun the German history backfill in bounded batches;
6. verify Tradegate-primary week, month, year, and three-year charts plus an
   Xetra-primary example.

The daemon may continue collecting live prices from the old active generation
until step 4. No flag change or database migration is required for this fix.

## Failure Handling

- Incomplete official reference catalogs still refuse the entire generation.
- A missing or ambiguous Xetra proxy candidate omits only the proxy.
- Duplicate primary or proxy venue identities refuse generation activation
  before any database mutation.
- Any activation exception rolls back primary rows, proxy rows, and generation
  status together.
- Yahoo transport, metadata, or rate-limit failures remain no-write outcomes
  for the affected backfill instrument.

## Regression Proof

Tests must demonstrate the complete behavior, not only helper output:

- an XGAT primary with an exact same-ISIN XETR candidate serializes a proxy;
- ambiguity, currency mismatch, ISIN mismatch, and no candidate omit it;
- an XETR primary does not duplicate itself as a proxy;
- an old generation payload still verifies against its original hash;
- activation persists XGAT primary plus XETR non-primary atomically;
- activating a later generation without a proxy makes the old proxy
  unavailable;
- rollback of the legacy snapshot removes proxy authority;
- the German backfill discovers the activated secondary Xetra row;
- `history.series_for` still uses the exact-ISIN, pre-native-only seam.

Focused verification covers instrument mapping, mapping/report compatibility,
market-data activation, backfill, history, detail, and API behavior. Existing
unrelated dirty files are excluded from every commit.
