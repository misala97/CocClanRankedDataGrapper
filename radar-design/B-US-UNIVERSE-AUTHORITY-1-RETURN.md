# Researcher Return — `B-US-UNIVERSE-AUTHORITY-1`

Role: Radar Researcher. Public-source research only. No production host, database,
provider, or deployment access was used, requested, or obtained.

Date of work: 2026-09-18 (Europe/Berlin). Official retrievals ran
2026-09-17 22:23:39 UTC – 22:27:21 UTC.

**Headline: all eight directory codes and all eight MICs are CONFIRMED against
current primary sources. No remapping is required. What the authority check does
change is the *shape* of the C1 contract, the ruling basis for D1, and two
code-level inconsistencies that the confirmed vocabulary exposes.**

---

## 1. Start gate

### 1.1 Git evidence (observed, not asserted)

| Check | Observed |
|---|---|
| Workspace | `C:\Users\michi\Desktop\CodingStuff\.worktrees\radar-selected-price-charts` |
| Branch | `codex/radar-selected-price-charts` |
| `HEAD` | `0fdad7327292cd3cd0b62dbe3f6b460873263053` |
| `origin/main` | `0fdad7327292cd3cd0b62dbe3f6b460873263053` |
| Feature ref `codex/radar-selected-price-charts` | `0fdad7327292cd3cd0b62dbe3f6b460873263053` |
| Index | empty (`git diff --cached --stat` returns nothing) |

All three refs equal the expected hash. No Git repair was attempted and none was
needed.

### 1.2 Pre-existing dirt — preserved

Nine modified tracked files, every one a Mastermind-owned planning document:
`HANDOFF.md`, and under `radar-design/`: `A-US-USD-ONLY-LEDGER.md`,
`ASSIGNMENTS.md`, `HANDOFF.md`, `MARKET-DATA-ROADMAP.md`, `MASTERMIND-STATE.md`,
`MD-SELECTED-PRICE-LEDGER.md`, `ROADMAP.md`, `WORKFLOW.md`. Thirty-one
pre-existing untracked entries (the B/A/MD returns, rulings, prompts — including
this assignment's own `B-US-UNIVERSE-AUTHORITY-1-PROMPT.md` — and the
`radar-design/artifacts/*` evidence directories, plus one untracked spec under
`docs/superpowers/specs/`).

No tracked file was modified by this assignment. **No product code, test,
migration, or ledger is dirty** — the entire modified set is documentation. The
only paths this assignment created are:

- `radar-design/B-US-UNIVERSE-AUTHORITY-1-RETURN.md` (this file);
- `radar-design/artifacts/b-us-universe-authority-1/`.

### 1.3 Evidence‑2 is still the newest binding B assessment; B implementation has not begun

- `radar-design/B-US-UNIVERSE-LEDGER.md` lists `B-US-UNIVERSE-EVIDENCE-2` as
  **COMPLETE / ACCEPTED** and `B-US-UNIVERSE-AUTHORITY-1` as **OWNER APPROVED —
  PROMPT READY / NOT DISPATCHED**; "Workstream B implementation/deployment:
  **NOT STARTED / NOT AUTHORIZED**".
- `HANDOFF.md:1-3` — the newest `CURRENT` block is "B authority-check prompt
  ready; not dispatched (2026-09-18)". The Evidence‑2 block below it is the
  newest *ruling*-bearing block; no later B ruling exists.
- There is no `B-US-UNIVERSE-*-RULING.md` newer than
  `B-US-UNIVERSE-EVIDENCE-2-RULING.md` (dated 2026-09-18), and no B
  implementation artifact, branch, commit, or code change exists at `0fdad73`.

Release A remains **CLOSED**.

---

## 2. Sources

Primary only. Two authorities, six retrieved files, all hashed; see
`radar-design/artifacts/b-us-universe-authority-1/source-manifest.json` and
`.../commands.md`.

| ID | Authority | Document | Retrieved (UTC) | SHA-256 (first 16) |
|---|---|---|---|---|
| S1 | Nasdaq Trader | *Symbol Look-Up/Directory Data Fields & Definitions* — <https://www.nasdaqtrader.com/trader.aspx?id=symboldirdefs> | 2026-09-17T22:23:39Z | `1fc8feb7fd060e52` |
| S2 | ISO 20022 / ISO 10383 RA (SWIFT) | Market identifier codes landing page — <https://www.iso20022.org/market-identifier-codes> | 2026-09-17T22:24:58Z | `406cf0efbcda4f0b` |
| S3 | ISO 10383 RA (SWIFT) | `ISO10383_MIC.csv`, September 2026 publication — <https://www.iso20022.org/sites/default/files/ISO10383_MIC/ISO10383_MIC.csv> | 2026-09-17T22:25:02Z | `79de0f7704e260bd` |
| S4 | ISO 10383 RA (SWIFT) | *New MIC Data Set Structure and Format — Factsheet (Release 2.0 v2)* | 2026-09-17T22:27:21Z | `bde1621ff7252b52` |
| S5 | ISO 10383 RA (SWIFT) | `ISO10383_MIC_Annexes_September2026.pdf` | 2026-09-17T22:26:42Z | `6279b4a49a3d0e31` |
| S6 | ISO 10383 RA (SWIFT) | `ISO10383_MIC.xsd` | 2026-09-17T22:26:54Z | `addad3b712eeee35` |

**Register version.** S2 states the publication date **14 September 2026**, a
modification implementation date of **28 September 2026**, and the next
publication on **12 October 2026**; it also states the list is published on the
second Monday of each month and modifications take effect on the fourth Monday.
S3 as retrieved therefore is the 14 September 2026 publication, four days old at
retrieval, and its pending modifications become effective ten days after this
return. **Register row count: 2,883.**

**No secondary source supports any conclusion here.** No web search result,
vendor page, encyclopedia, or prior Radar document was used as authority. Where
I could not obtain an official statement, I say so rather than filling the gap
(§7).

**S5 was retrieved but not read.** The annexes PDF has no extractable text layer
in this environment. Nothing in this return depends on it; the code-list
definitions it would have carried were taken from S4, which is equally primary.

**Not fetched, by dispatch rule:** `nasdaqlisted.txt`, `otherlisted.txt`, and the
`dynamic/symdir/` listing. This return concerns definitions only.

---

## 3. Nasdaq directory fields — official findings

All of §3 is **official fact from S1** unless a line is marked *inference*.

### 3.1 `nasdaqlisted.txt`, field `Market Category`

The definition is that Nasdaq assigns the category from its listing
requirements. Values:

| Code | Official meaning |
|---|---|
| `Q` | Nasdaq Global Select Market℠ |
| `G` | Nasdaq Global Market℠ |
| `S` | Nasdaq Capital Market |

Three values, no others listed. These are exactly Radar's three.

### 3.2 `otherlisted.txt`, field `Exchange`

The field is defined as "The listing stock exchange or market of a security."
and the enumeration is introduced by "Allowed values are:".

| Code | Official meaning |
|---|---|
| `A` | NYSE MKT |
| `N` | New York Stock Exchange (NYSE) |
| `P` | NYSE ARCA |
| `Z` | BATS Global Markets (BATS) |
| `V` | Investors' Exchange, LLC (IEXG) |

Five values, no others listed. These are exactly Radar's five. Note that `V`'s
label carries the ISO MIC **`IEXG`** in the official Nasdaq text itself — the
only place on the page where a MIC appears.

### 3.3 Are these still the complete valid sets?

**Yes, as published.** S1 is the only official Nasdaq statement of these
enumerations, it presents both as closed lists ("Values:" / "Allowed values
are:"), and it names no sixth exchange code and no fourth market category.

**But S1 is undated and two of its labels are retired trade names.** The page
carries no version, no effective date, and no change history. It still calls `A`
"NYSE MKT" while the ISO register names that venue **NYSE AMERICAN LLC**, and
still calls `Z` "BATS Global Markets" while the register names it **CBOE BZX
U.S. EQUITIES EXCHANGE**. *Researcher assessment:* the page is authoritative for
the **codes** and stale for the **labels**. Radar's own venue strings
(`a4c8e2f19b70:41` "NYSE American", `:42` "Cboe BZX") are **more current than
Nasdaq's page**, and should not be "corrected" backwards to match it.

### 3.4 Missing, new, renamed, or retired listing venues

S1 documents no code for any US venue beyond those eight. The ISO register (S3)
does show US venues with no Nasdaq directory code, all `ACTIVE`:

| MIC | Official name | Type / operating MIC | Category | Last update |
|---|---|---|---|---|
| `LTSE` | LONG-TERM STOCK EXCHANGE, INC. | OPRT / `LTSE` | NSPD | 2019-12-23 |
| `XMEM` / `MEMX` | MEMX LLC / MEMX LLC EQUITIES | OPRT / SGMT of `XMEM` | RMKT / OTHR | 2026-03-23 |
| `EPRL` | MIAX PEARL EQUITIES | SGMT of `MIHI` | RMKT | 2023-08-28 |
| `TXSE` | TEXAS STOCK EXCHANGE | OPRT / `TXSE` | RMKT | 2025-11-24 |
| `24EQ` | 24X NATIONAL EXCHANGE LLC | OPRT / `24EQ` | RMKT | 2025-04-28 |
| `XMXT` | MX2 LLC | OPRT / `XMXT` | RMKT | 2026-03-23 |

Two renames inside groups Radar already touches, neither affecting a Radar code:
`XCHI` is now **NYSE TEXAS, INC.** (segment of `XNYS`) and `XBOS` is now
**NASDAQ TEXAS** (segment of `XNAS`). Neither MIC is in the C1 table and neither
corresponds to a directory code.

**Critical limit, stated plainly:** the ISO register records that a market
exists, who operates it, and its category. **It does not state whether a venue
accepts primary listings.** So ISO cannot tell us whether any of the six above
lists securities. The only authoritative statement on that question is S1's
allowed-value list, and it names none of them.

*Researcher inference, clearly separated:* if one of these venues begins primary
listings, Nasdaq would have to introduce a new `Exchange` letter, and that letter
would arrive in `otherlisted.txt` with no entry in Radar's table. Under the
current deployed code that letter reaches `radar_ticker_universe.exchange`
unvalidated and no instrument is created (there is no live mapping writer —
Evidence‑2, §6.2). Under the historical migration's `CASE` it would have become
`'XXXX'` / `'unverified'` (`a4c8e2f19b70:32`, `:47-51`). Under C1's quarantine
rule it gets no row. **C1's rule is the correct one and this survey is the reason
to keep it.**

**Verdict on ADD: nothing to add.** No official source authorizes a ninth code
today.

### 3.5 The same letter means different things in different columns — officially

This is not hypothetical and it is not cross-file only. Inside
`nasdaqlisted.txt` itself, the `Financial Status` field reuses two of the three
Market Category letters:

| Letter | `Market Category` (same file) | `Financial Status` (same file) |
|---|---|---|
| `Q` | Nasdaq Global Select Market℠ | Bankrupt: Issuer Has Filed for Bankruptcy |
| `G` | Nasdaq Global Market℠ | Deficient and Bankrupt |
| `N` | — (not a Market Category value) | Normal (Default) |

Across files, `N`, `A`, `P`, `S` and `V` are also reused by `Test Issue`,
`MP Type` and the mutual-fund `Category` field with unrelated meanings.

**Consequence for C1.** The two listing-code namespaces Radar uses are disjoint
(`{Q,G,S}` ∩ `{N,A,P,Z,V}` = ∅), so the migration's single flat `CASE` over
`u.exchange` (`a4c8e2f19b70:23-33`) produced correct results for the data it saw.
It is nonetheless **file-and-column-blind**, and one column away from silently
mis-assigning a venue. Evidence‑1's C1 already specifies per-file
interpretation; **S1 now supplies the official justification for that rule, and
it is stronger than expected** — the collision exists within a single file.

**Live parser risk, exact.** `personal_apps/scripts/seed_radar_universe.py:32`
resolves the exchange letter from the first non-empty of
`('Exchange', 'Listing Exchange', 'Market Category', 'exchange')`. Today that is
safe: `nasdaqlisted.txt` has no `Exchange` column so `Market Category` wins, and
`otherlisted.txt` has `Exchange`. But `Listing Exchange` is a column **S1 does
not document at all** — it belongs to `nasdaqtraded.txt`, for which Nasdaq
publishes no field definitions on this page (its tab list covers Nasdaq-Listed,
Other-Exchange Listed, Market Participants, Mutual Funds, PBOT Futures, the
options files, Nasdaq, Nasdaq Texas (NTX), and PSX Adds and Deletes — no
`nasdaqtraded`). **There is therefore no authoritative meaning available for the
letters in the column that alias would read.** See §7 G3.

---

## 4. ISO 10383 MIC dispositions

All of §4 is **official fact from S3**, with field semantics from S4 and S6,
unless marked *inference*. Extracted rows:
`radar-design/artifacts/b-us-universe-authority-1/iso10383-radar-mics.csv`
(10 rows, SHA-256 `16bb93a6…`).

Official field semantics (S4): *Operating MIC* is the entity operating an
exchange/market/trade reporting facility in a specific market/country;
`OPRT`/`SGMT` indicates whether the MIC is an operating MIC or a market segment
MIC; a *Segment MIC* is a "section of an exchange/market/trade reporting facility
that specialises in one or more specific instruments or that is regulated
differently"; *Status* is active, updated (since last publication), or expired
(= deactivated). Market category codes: `RMKT` = Regulated Market, `NSPD` = Not
Specified. S6 confirms `OPRT`/`SGMT` is a closed two-value enumeration in the
official schema.

### 4.1 The eight Radar MICs

| MIC | Official market name | Type | Operating MIC | Legal entity | Country / city | Category | Status | Created | Last update | Last validation | Expiry |
|---|---|---|---|---|---|---|---|---|---|---|---|
| `XNGS` | NASDAQ GLOBAL SELECT MARKET | SGMT | `XNAS` | NASDAQ, INC. | US / New York | RMKT | **ACTIVE** | 2006-07-24 | 2026-04-27 | 2026-04-27 | — |
| `XNMS` | NASDAQ GLOBAL MARKET | SGMT | `XNAS` | NASDAQ, INC. | US / New York | RMKT | **ACTIVE** | 2005-06-27 | 2026-04-27 | 2026-04-27 | — |
| `XNCM` | NASDAQ CAPITAL MARKET | SGMT | `XNAS` | NASDAQ, INC. | US / New York | RMKT | **ACTIVE** | 2008-02-25 | 2026-04-27 | 2026-04-27 | — |
| `XNYS` | NEW YORK STOCK EXCHANGE, INC. | **OPRT** | `XNYS` | INTERCONTINENTAL EXCHANGE, INC. | US / New York | NSPD | **ACTIVE** | 2005-05-23 | 2025-04-28 | 2025-04-28 | — |
| `XASE` | NYSE AMERICAN LLC | SGMT | `XNYS` | INTERCONTINENTAL EXCHANGE, INC. | US / New York | RMKT | **ACTIVE** | 2009-05-25 | 2025-04-28 | 2025-04-28 | — |
| `ARCX` | NYSE ARCA | SGMT | `XNYS` | INTERCONTINENTAL EXCHANGE, INC. | US / New York | RMKT | **ACTIVE** | 2006-09-25 | 2025-04-28 | 2025-04-28 | — |
| `BATS` | CBOE BZX U.S. EQUITIES EXCHANGE | SGMT | `XCBO` | *(empty in register)* | US / Chicago | NSPD | **ACTIVE** | 2008-11-24 | 2018-06-25 | *(none)* | — |
| `IEXG` | INVESTORS EXCHANGE | **OPRT** | `IEXG` | INVESTORS EXCHANGE LLC | US / New York | NSPD | **ACTIVE** | 2013-10-28 | 2022-10-24 | *(none)* | — |

Context row, not a C1 value: `XNAS` = NASDAQ - ALL MARKETS, OPRT, operating MIC
`XNAS`, NASDAQ, INC., US, RMKT, ACTIVE, created 2005-06-27, last updated and
validated 2026-04-27.

`XNCM` carries a register comment that it was previously (2005) named Nasdaq
SmallCap Market — useful confirmation that this is the tier Nasdaq's `S` means.

**Every one of the eight exists, is ACTIVE, is US, and carries no expiry date.**

**Freshness is uneven, and that is an official observation worth recording.** The
Nasdaq group rows were last validated 2026-04-27 and the NYSE group 2025-04-28.
The Cboe group, including `BATS`, was last updated 2018-06-25 with **no last
validation date and an empty legal entity name**; `IEXG` was last updated
2022-10-24 with **no last validation date**. Neither is marked expired or
deactivated, so both remain valid register entries — but they are the two least
recently maintained rows in Radar's set.

### 4.2 Is each MIC appropriate for the listing segment its directory code represents?

| Directory code | Listing segment it names | MIC | Appropriate? |
|---|---|---|---|
| `Q` | Nasdaq Global Select Market | `XNGS` | **Yes** — the register's name is the identical tier, as a segment of Nasdaq. |
| `G` | Nasdaq Global Market | `XNMS` | **Yes** — identical tier. |
| `S` | Nasdaq Capital Market | `XNCM` | **Yes** — identical tier, with the SmallCap lineage noted in the register. |
| `N` | New York Stock Exchange | `XNYS` | **Yes** — and it must be the operating MIC, because the register contains **no segment MIC for NYSE's own equities market**. The 13 rows in the `XNYS` group are `ARCX`, `XASE`, `XCIS` (NYSE National), `XCHI` (NYSE Texas), `NYSD` (NYSE Dark), `XNYB` (NYSE Bonds), `ARCD`, `CISD`, `AMXO`, `ARCO`, the expired `ALDP`/`XNLI`, and `XNYS` itself. |
| `A` | NYSE American (the page's "NYSE MKT") | `XASE` | **Yes** — the register's NYSE AMERICAN LLC. |
| `P` | NYSE Arca | `ARCX` | **Yes** — the register's NYSE ARCA. |
| `Z` | Cboe BZX (the page's "BATS Global Markets") | `BATS` | **Yes** — see §4.4. |
| `V` | Investors' Exchange | `IEXG` | **Yes** — see §4.5. |

*Researcher note on the OPRT/SGMT asymmetry:* three of Radar's MICs are operating
MICs (`XNYS`, `IEXG`) or segments of a third-party operating MIC (`BATS` under
`XCBO`), while five are segments. **This asymmetry is correct, not a defect.** The
register offers no narrower code for NYSE equities or for IEX equities, and
offers exactly the right narrower code for each Nasdaq tier and each NYSE
sibling market. C1 must record the type and the operating MIC per row so the
asymmetry is visible instead of looking like an inconsistency.

### 4.3 Ruling: Nasdaq tier MICs stay segment MICs — do **not** normalize to `XNAS`

**Recommendation: keep `XNGS` / `XNMS` / `XNCM`. Do not collapse to `XNAS`.**

Grounds, in order of weight:

1. **The source supplies the tier; normalizing throws it away.** `Market
   Category` is *defined* (S1) as the tier assigned from listing requirements.
   `XNAS` is officially named "NASDAQ - ALL MARKETS". Mapping Q/G/S to `XNAS`
   discards the one distinction the directory field exists to carry, and it is
   irreversible.
2. **The rollup is free in the other direction.** Every register row carries its
   `OPERATING MIC`, so `XNGS → XNAS` is a lookup any consumer can do. There is no
   reverse lookup.
3. **The register's own model prefers the segment.** S4 defines a segment MIC as
   a section of a market that specialises or is regulated differently — exactly
   what a Nasdaq listing tier is.
4. **Changing the basis would rewrite stored history.** `mic` participates in
   `uq_radar_quote_market` and `uq_radar_daily_close_market`, and every reader
   filters on it (Evidence‑2 §5.2). A normalization pass is a mass rewrite of
   12,599 mapped rows plus their quote and close history — the largest possible
   change, for a strict information loss.
5. **`XNAS` is already the wrong-value sentinel in this codebase.** The legacy
   fallbacks at `personal_apps/features/radar/quotes.py:97` and
   `personal_apps/features/radar/prices/__init__.py:85` default to `'XNAS'`;
   Evidence‑2 measured zero such rows and named it latent finding F2/D8. Making
   `XNAS` a *legitimate* value would erase the distinction between a correct
   Nasdaq row and a fallback row and make F2 permanently undetectable.

*Consequence for C1:* store the operating MIC as a **separate recorded field**
(or derive it from a pinned table), never as a replacement for the segment MIC.

### 4.4 Ruling: `BATS` is the correct current MIC for `Z`

**CONFIRMED.** The register's `BATS` row is `ACTIVE`, US, a segment of operating
MIC `XCBO` (CBOE GLOBAL MARKETS INC.), and officially named **CBOE BZX U.S.
EQUITIES EXCHANGE**. The four-letter code did not change when the venue's trade
name did; the register carries the new name under the old code. Nasdaq's `Z`
label ("BATS Global Markets") is the dated artifact, not the mapping.

Within the `XCBO` group the register distinguishes `BATS` (BZX equities) from
`BATY` (BYX equities), `BZXD` (BZX dark), `BATO` (BZX options), `EDGA`, `EDGX`,
`EDGD`, `EDDP`, `EDGO`. `BATS` is the only one of these that names the BZX
**equities** market, so it is the correct single choice for a `Z` listing.

Two honest caveats: the row's category is `NSPD` rather than `RMKT`, its legal
entity name is empty, and it has **no last validation date** (last update
2018-06-25). *Researcher assessment:* this is register maintenance lag across the
whole Cboe group — 13 of the 17 `XCBO` rows share the 2018-06-25 stamp — not a
signal that `BATS` is wrong or deprecated. Nothing marks it expired.

### 4.5 Ruling: `IEXG` is the correct current MIC for `V`, and the mapping should be kept

**CONFIRMED, and this is the strongest-cited row in the table** — because the
Nasdaq page itself writes the MIC: "V = Investors' Exchange, LLC (IEXG)". Both
authorities agree in one step, with no interpretation.

The register's `IEXG` row is `ACTIVE`, US, an operating MIC in its own right,
legal entity INVESTORS EXCHANGE LLC, no expiry. Its group holds `IEXD`
(IEX dark), `IEXC` (DAX facility) and `IEXO` (IEX Options, updated 2026-07-27);
`IEXG` itself is the right code for a listing.

**Evidence‑2's zero-row finding does not contradict this.** Evidence‑2 measured
zero `IEXG` instrument rows across all 12,599 mapped rows and zero `V` codes in
all three cohorts. *Researcher reading, separated from fact:* zero rows is
consistent with no security in the 2026-09-16 snapshot carrying `V`. It is
evidence about **Radar's data**, not about the **mapping's correctness**. The two
questions are independent, and the correct posture for an untested-but-confirmed
mapping is to **keep it**: if a `V` row ever arrives, mapping it to `IEXG` is
right, and quarantining it instead would create a mapping gap for a code the
official source explicitly allows.

**But the confirmed mapping exposes an inconsistency in Radar.**
`personal_apps/features/radar/analysis_contract.py:42` defines
`KNOWN_US_MICS = frozenset({'ARCX', 'XNMS', 'XNYS', 'XNCM', 'BATS', 'XNGS', 'XASE'})`
— **seven of the eight; `IEXG` is absent.** At
`personal_apps/features/radar/analysis.py:423` a MIC outside that set adds the
warning "no modeled calendar for MIC …; trading-day hints are unknown", and
`analysis_contract.py:224-232` returns the `unknown` hint function. So the first
`IEXG` instrument Radar ever maps would silently lose modeled trading-day hints.
This **fails soft and degrades honestly** — it is not a crash and not a data
corruption — but it is a real inconsistency between the confirmed C1 vocabulary
and a downstream consumer. See §6, C1-D.

For completeness, the other MIC-vocabulary consumer,
`personal_apps/features/radar/prices/yahoo.py:24-34`, does list all eight plus
`XNAS`; that path is dormant (Yahoo is OFF since release A).

### 4.6 Ruling: cross-venue and tier changes need **three** treatments, not two

The register's operating-MIC and legal-entity columns split Evidence‑2's seven
drift rows more finely than "tier vs cross-venue":

| Class | Rows | What the register says changed | Proposed treatment |
|---|---|---|---|
| **T1 — tier move inside Nasdaq** | `EPRX` (S→Q, `XNCM`→`XNGS`), `FSHP`, `FSHPR`, `FSHPU` (G→S, `XNMS`→`XNCM`) — **4** | Segment MIC changes; operating MIC stays `XNAS`; legal entity stays NASDAQ, INC. | Same venue, different listing tier. A tier field or a new effective-dated mapping row; **no history break**, because the operating MIC is unchanged. |
| **T2 — move inside the NYSE group** | `MVPA` (P→N, `ARCX`→`XNYS`) — **1** | Segment → its own operating MIC; operating MIC stays `XNYS`; legal entity stays INTERCONTINENTAL EXCHANGE, INC. | Same operator, genuinely different market. Review, but the continuity argument is stronger than for T3. |
| **T3 — operating MIC changes** | `KHC` (Q→N, `XNAS`→`XNYS`), `OPAD` (N→S, `XNYS`→`XNAS`) — **2** | Operating MIC **and** legal entity change (NASDAQ, INC. ↔ INTERCONTINENTAL EXCHANGE, INC.) | A true venue transfer. Needs the explicit history-continuity ruling C2 already demands before any primary switch. |

This is a new, official-source-derived refinement of D1. Evidence‑2 reported
"4 tier + 3 cross-venue"; the register says the `MVPA` case is materially
different from `KHC`/`OPAD` and should not be ruled with them.

**All fourteen MIC values involved (both sides of all seven rows) are ACTIVE in
the register.** Neither the stored MIC nor the directory-implied MIC is invalid.
D1 is therefore purely a history-continuity policy question — **not a correctness
repair**. That is the single most useful thing this authority check can tell the
owner about those seven rows.

---

## 5. C1 contract disposition table

One row per directory source/code. Citations: **S1** = Nasdaq definitions page
(§3.1/§3.2 of the extract artifact); **S3** = ISO 10383 register, 14 September
2026 publication, row extracted to `iso10383-radar-mics.csv`.

| Source file · field | Code | Official directory meaning (S1) | Proposed MIC | MIC type · operating MIC (S3) | Official status (S3) | Verdict | Citation | Implication for the 114 safe candidates and the 7 drift rows |
|---|---|---|---|---|---|---|---|---|
| `nasdaqlisted.txt` · `Market Category` | `Q` | Nasdaq Global Select Market℠ | `XNGS` | SGMT · `XNAS` | ACTIVE, US, RMKT, val. 2026-04-27 | **CONFIRMED** | S1 §*nasdaqlisted*/`Market Category`; S3 row `XNGS` | 0 of the 114 (the 2 `XNGS` rows in the 146 fall in the 26 + 6 review groups). Drift: `EPRX` target and `KHC` origin. |
| `nasdaqlisted.txt` · `Market Category` | `G` | Nasdaq Global Market℠ | `XNMS` | SGMT · `XNAS` | ACTIVE, US, RMKT, val. 2026-04-27 | **CONFIRMED** | S1; S3 row `XNMS` | **26** of the 114 unchanged. Drift: `FSHP`/`FSHPR`/`FSHPU` origin. |
| `nasdaqlisted.txt` · `Market Category` | `S` | Nasdaq Capital Market | `XNCM` | SGMT · `XNAS` | ACTIVE, US, RMKT, val. 2026-04-27 | **CONFIRMED** | S1; S3 row `XNCM` (comment: previously Nasdaq SmallCap Market) | **15** of the 114 unchanged. Drift: `FSHP`×3 target, `OPAD` target, `EPRX` origin. |
| `otherlisted.txt` · `Exchange` | `N` | New York Stock Exchange (NYSE) | `XNYS` | **OPRT** · `XNYS` | ACTIVE, US, NSPD, val. 2025-04-28 | **CONFIRMED** | S1 §*otherlisted*/`Exchange`; S3 row `XNYS` | **5** of the 114 unchanged. Drift: `KHC` and `MVPA` target, `OPAD` origin. |
| `otherlisted.txt` · `Exchange` | `A` | NYSE MKT *(retired trade name; register: NYSE AMERICAN LLC)* | `XASE` | SGMT · `XNYS` | ACTIVE, US, RMKT, val. 2025-04-28 | **CONFIRMED** *(label dated at source, code correct)* | S1; S3 row `XASE` | **4** of the 114 unchanged. No drift row. |
| `otherlisted.txt` · `Exchange` | `P` | NYSE ARCA | `ARCX` | SGMT · `XNYS` | ACTIVE, US, RMKT, val. 2025-04-28 | **CONFIRMED** | S1; S3 row `ARCX` | **36** of the 114 unchanged — the largest single block. Drift: `MVPA` origin. |
| `otherlisted.txt` · `Exchange` | `Z` | BATS Global Markets (BATS) *(retired trade name; register: CBOE BZX U.S. EQUITIES EXCHANGE)* | `BATS` | SGMT · `XCBO` | ACTIVE, US, NSPD, upd. 2018-06-25, **no validation date** | **CONFIRMED** *(label dated at source; register row stale but active)* | S1; S3 row `BATS` | **28** of the 114 unchanged. No drift row. |
| `otherlisted.txt` · `Exchange` | `V` | Investors' Exchange, LLC (IEXG) | `IEXG` | **OPRT** · `IEXG` | ACTIVE, US, NSPD, upd. 2022-10-24, **no validation date** | **CONFIRMED** *(keep despite zero observed rows)* | S1 — the MIC is stated in the Nasdaq text; S3 row `IEXG` | 0 of the 114, 0 of the 146, 0 of 12,599 mapped rows, 0 drift rows. Keep the mapping; add `IEXG` to `KNOWN_US_MICS` or document the degradation. |

**No `REMOVE`. No `ADD`. No `CORRECT_WITH_CHANGE` at the code→MIC level.**
Eight of eight confirmed.

### 5.1 Exact impact on the 114 and the 7

- **114 safe insert-only candidates: entirely unaffected.** Their MIC
  distribution (Evidence‑2 §5.1: `ARCX` 36, `BATS` 28, `XNMS` 26, `XNCM` 15,
  `XNYS` 5, `XASE` 4 = 114) uses six MICs, and all six are officially ACTIVE with
  the meanings C1 assumed. **Zero rows change MIC, zero rows move classification,
  and the cohort does not resize.** The first B1 apply remains exactly 114
  insert-only rows.
- **The full 146 are equally covered** (adds `XNGS` 2; `VENUE_UNKNOWN` stays 0),
  so the 26 D3 rows and 6 corporate-action rows keep their proposed MICs for
  whenever the owner rules D3.
- **7 MIC-drift rows: no value changes.** What changes is the ruling basis —
  D1 should be ruled as T1 (4 rows) / T2 (1 row) / T3 (2 rows) per §4.6, and the
  owner should know that both sides of every drift row are valid ACTIVE MICs, so
  no repair is owed on correctness grounds.
- **Nothing in Evidence‑2's accepted counts is invalidated by this return.**

---

## 6. Required C1 corrections

None is a remapping. All six are structural or code-consistency items.

- **C1-A — record MIC type and operating MIC per row (required).** C1 currently
  carries code → MIC → venue label. Add `mic_type` (`OPRT`/`SGMT`) and
  `operating_mic` from the register: `XNGS`/`XNMS`/`XNCM` → `XNAS`;
  `XASE`/`ARCX` → `XNYS`; `BATS` → `XCBO`; `XNYS` and `IEXG` are themselves
  operating MICs. This is what makes §4.6's T1/T2/T3 rule computable and what
  makes the OPRT/SGMT asymmetry legible instead of looking like a bug.
- **C1-B — keep per-file, per-column interpretation, now officially grounded
  (confirmed).** S1 shows `Q` and `G` reused with unrelated meanings *inside*
  `nasdaqlisted.txt`. The migration's flat `CASE` over `u.exchange`
  (`a4c8e2f19b70:23-33`) is correct only by the accident that the two listing
  namespaces are disjoint. C1's rule — a code in the wrong file gets no row —
  stands and should be stated as officially motivated.
- **C1-C — keep Radar's venue labels; do not sync them to S1 (confirmed).**
  `a4c8e2f19b70:41` "NYSE American" and `:42` "Cboe BZX" match the register and
  are ahead of Nasdaq's page. Record in C1 that the Nasdaq labels for `A` and `Z`
  are retired trade names so nobody "fixes" them backwards later.
- **C1-D — `IEXG` is confirmed but absent from `KNOWN_US_MICS` (correction
  owed).** `analysis_contract.py:42` lists seven of the eight. Either add `IEXG`
  (the US calendar is a rule-based NYSE-holiday model and would apply as
  correctly to IEX as to the other seven — *inference*, since no official source
  covers trading calendars) or record explicitly that a `V` listing will produce
  `unknown` trading-day hints. Do not leave it implicit. Zero rows today, so this
  is a pre-emptive fix, not an outage.
- **C1-E — the `XXXX` / `XNAS` fallbacks are outside the confirmed vocabulary
  (already D8/F2; now officially reinforced).** `a4c8e2f19b70:32` writes
  `ELSE 'XXXX'` and `:47-51` marks such rows `unverified`; `quotes.py:97` and
  `prices/__init__.py:85` default to `'XNAS'`. `XXXX` is not a US listing MIC and
  `XNAS` is the Nasdaq **operating** MIC, so a fallback row is indistinguishable
  from a legitimately-Nasdaq row. §4.3 raises the cost of ever legitimizing
  `XNAS`. C1's quarantine rule supersedes both fallbacks.
- **C1-F — pin the parser to the two documented files (correction owed).**
  `seed_radar_universe.py:32` accepts a `Listing Exchange` alias for which S1
  publishes no definition (§3.5). Either drop the alias or bind each input path
  to its documented file and column, so an undocumented column can never supply
  a listing letter.

---

## 7. Gaps, ambiguities and dated sources — stated, not filled

- **G1 — S1 is undated.** No version, no effective date, no change history. It
  is authoritative for the codes and cannot be pinned to a revision. Any future
  re-check must re-hash the page and diff it; there is no version number to
  compare.
- **G2 — S1 carries two retired trade names** (`A` = "NYSE MKT", `Z` = "BATS
  Global Markets"). Resolved against S3 for the venue identity; recorded rather
  than silently corrected.
- **G3 — no official definition exists for `nasdaqtraded.txt`.** S1's tab list
  does not include it, so the `Listing Exchange` column Radar's parser aliases
  has **no authoritative meaning available**. I did not infer one, and I did not
  fetch that file (dispatch rule). If the daily-maintenance design ever wants
  that file, obtaining its official field definitions is a prerequisite.
- **G4 — ISO does not say who accepts listings.** The register states existence,
  operator, category and status only. The "is a new US listing venue missing"
  question is therefore answered **only** by S1's allowed-value list. The six
  active US venues in §3.4 with no directory code are an alert to re-check, not a
  finding that Radar is missing a mapping.
- **G5 — two Radar MIC rows are stale in the register.** `BATS` (last update
  2018-06-25) and `IEXG` (2022-10-24) both lack a last validation date, and
  `BATS` has an empty legal entity name. Both are `ACTIVE` with no expiry, so
  they are valid; their maintenance lag is recorded, not resolved.
- **G6 — `XNYS` and `BATS` are categorised `NSPD` (Not Specified), not `RMKT`.**
  The Nasdaq tier MICs and `XASE`/`ARCX` are `RMKT`. I have no official
  explanation for why NYSE's own operating row is `NSPD` while its segments are
  `RMKT`; S4's factsheet notes that additional US market types "will be
  introduced to the list of codes", which is the closest official statement. Do
  not use `MARKET CATEGORY CODE` as a filter for "is this a listing venue".
- **G7 — S5 (annexes PDF) retrieved but unreadable here.** No conclusion depends
  on it. Its code-list content was taken from S4 instead.
- **G8 — the register moves.** The retrieved publication is 14 September 2026;
  its pending modifications take effect 28 September 2026 and the next
  publication is 12 October 2026. **This return is a dated snapshot.** A daily
  maintenance design that pins MICs should re-validate against the register on a
  cadence, not treat this table as permanent.
- **G9 — not verified here, by scope:** no directory data was fetched, so this
  return says nothing about whether current `nasdaqlisted.txt`/`otherlisted.txt`
  contents still contain only these eight letters. Evidence‑2 measured that for
  the 2026-09-16 snapshot (`VENUE_UNKNOWN` = 0).

---

## 8. Official fact vs Researcher inference — the separation, explicitly

**Official fact (S1/S3/S4/S6):** every code meaning in §3.1–3.2 and §3.5; the
completeness of both enumerations as published; every MIC attribute in §4.1
(name, type, operating MIC, legal entity, country, city, category, status,
creation, last update, last validation, expiry); the definitions of operating
MIC, segment MIC, status and the `RMKT`/`NSPD` category codes; the register's
publication dates and row count; the existence and status of the US venues in
§3.4; the group membership listings in §4.2 and §4.4.

**Researcher inference, and it is mine, not the sources':** that S1 is
authoritative for codes and stale for labels; that the OPRT/SGMT asymmetry is
correct rather than a defect; the `XNAS` normalization recommendation (§4.3) and
its five grounds; the three-way T1/T2/T3 split of the drift rows (derived from
official columns, but the *treatment* proposal is mine); the reading that
`IEXG`'s zero rows say nothing about the mapping's correctness; that
`KNOWN_US_MICS` would apply correctly to `IEXG`; the assessment that the Cboe
group's 2018 stamps are register maintenance lag; and every C1 correction in §6.

**Repository fact (read at `0fdad73`):** the C1 table's origin at
`personal_apps/migrations/versions/a4c8e2f19b70_add_radar_market_instruments.py:23-51`;
consumers at `personal_apps/features/radar/analysis_contract.py:42,224`,
`personal_apps/features/radar/analysis.py:423`,
`personal_apps/features/radar/prices/yahoo.py:24-34`,
`personal_apps/features/radar/quotes.py:97`,
`personal_apps/features/radar/prices/__init__.py:85`; the parser at
`personal_apps/scripts/seed_radar_universe.py:28-35,69,80`.

**Prior-report fact, attributed and not re-measured:** every cohort count,
MIC distribution, drift row and zero-residue measurement is Evidence‑2's, under
`B-US-UNIVERSE-EVIDENCE-2-RULING.md`. I read them; I did not and could not
re-verify them without host or database access, which this dispatch forbids.

---

## 9. Recommended owner decisions

- **D1 (MIC policy) — ready to rule.** Recommended: keep segment MICs, never
  normalize to `XNAS` (§4.3); record `mic_type` and `operating_mic` (C1-A); treat
  drift as T1/T2/T3 (§4.6); no correctness repair is owed on the seven rows
  because both sides are ACTIVE MICs; C2's "never rewrite a MIC in place" stands.
- **D2 (first-token changes) — untouched by this assignment.** Nothing in the
  official sources bears on Evidence‑2's N2 rebrand finding.
- **D3 (26 non-common listings) — unblocked on the venue question.** All 26
  resolve to confirmed ACTIVE MICs, so D3 is purely a security-type policy
  choice (warrants/units/rights/notes/preferreds), not a mapping-validity one.
- **D8 (the `XNAS`/`XXXX` fallback) — recommendation strengthened: fix it.**
  §4.3 ground 5 makes the fallback actively harmful to the tier decision, not
  merely untidy. Measured extent is still zero rows.
- **New, small:** rule C1-D (`IEXG` in `KNOWN_US_MICS`) and C1-F (drop the
  undocumented `Listing Exchange` alias) alongside D1. Both are one-line changes
  belonging to the B1 slice, not to this assignment.

---

## 10. Actions taken and protected state

**Done:** read the required repository documents and code read-only; retrieved
six official documents over HTTPS with `curl` (no credentials, no cookies
retained); extracted 10 + 74 register rows and the two Nasdaq field blocks;
wrote this return and
`radar-design/artifacts/b-us-universe-authority-1/` (six files:
`source-manifest.json`, `commands.md`,
`nasdaq-symbol-directory-definitions.md`, `extract_authority_rows.py`, and the
two generated CSVs).

**Not done, at all:** no production host, SSH, database, `.env`, service, job,
timer or configuration access; no `nasdaqlisted.txt`/`otherlisted.txt` or
symbol-directory data fetch; no importer, mapping write, delisting, migration or
product/test code change; no provider, Alpaca, trading, account, order or paid
API call; no user-data or credential access; no commit, stage, push, clean,
reset, discard, merge, deployment or release-A action; no subagents.

**Protected state verified after the work:** `HEAD`, `origin/main` and the
feature ref all still `0fdad7327292cd3cd0b62dbe3f6b460873263053`; index still
empty; the nine modified tracked planning documents and all 31 pre-existing
untracked entries untouched; the B ledger, brief, rulings, handoffs, roadmaps and
the Evidence‑1/Evidence‑2 artifact directories unmodified. The only additions to
the worktree are the two untracked paths this assignment owns.

**Raw downloads live only in this session's scratchpad**, not in the repository;
their hashes are in `source-manifest.json` so any reviewer can re-fetch and
compare.

---

## 11. Artifact index

| Path | What |
|---|---|
| `radar-design/B-US-UNIVERSE-AUTHORITY-1-RETURN.md` | this return |
| `radar-design/artifacts/b-us-universe-authority-1/source-manifest.json` | the six official sources: URL, title, retrieval time, bytes, SHA-256, version/effective dates, what each supported |
| `.../nasdaq-symbol-directory-definitions.md` | the extracted `nasdaqlisted`/`otherlisted` field definitions and code lists, plus what the page does not document |
| `.../iso10383-radar-mics.csv` | the 10 register rows (8 Radar MICs + `XNAS` + `XCBO`), full official columns — SHA-256 `16bb93a67f0af51b62e65faf273f76df6c9804b2b1fc7efc31381408147cd3b8` |
| `.../iso10383-us-listing-context.csv` | 74 US rows across the 10 relevant operating groups, the evidence for the missing-venue survey — SHA-256 `2062c369684c7afe45acc3efdba74e6e4dd8f4c123e1175cc632588289462856` |
| `.../extract_authority_rows.py` | the reproducible extractor; reads a register copy, writes only the two CSVs |
| `.../commands.md` | every command, hash and cited line number, plus the before/after Git checks |

---

## 12. Mastermind return prompt

```text
You are Radar's Mastermind / Overview. Resume from repository evidence, not chat memory.

Assignment completed: B-US-UNIVERSE-AUTHORITY-1
Workspace: C:\Users\michi\Desktop\CodingStuff\.worktrees\radar-selected-price-charts
Branch: codex/radar-selected-price-charts
Observed HEAD / origin/main / feature ref: 0fdad7327292cd3cd0b62dbe3f6b460873263053 / 0fdad7327292cd3cd0b62dbe3f6b460873263053 / 0fdad7327292cd3cd0b62dbe3f6b460873263053
Observed index and worktree dirt: index empty. 9 modified tracked Mastermind-owned planning documents (HANDOFF.md; radar-design/A-US-USD-ONLY-LEDGER, ASSIGNMENTS, HANDOFF, MARKET-DATA-ROADMAP, MASTERMIND-STATE, MD-SELECTED-PRICE-LEDGER, ROADMAP, WORKFLOW .md) plus 31 pre-existing untracked entries, all untouched; no product code, test or migration is dirty. The Researcher added only untracked radar-design/B-US-UNIVERSE-AUTHORITY-1-RETURN.md and radar-design/artifacts/b-us-universe-authority-1/. Nothing staged, committed or pushed; the B ledger, brief, rulings, handoffs and the Evidence-1/Evidence-2 artifacts were NOT edited.

Read completely:
1. HANDOFF.md
2. radar-design/B-US-UNIVERSE-BRIEF.md
3. radar-design/B-US-UNIVERSE-LEDGER.md
4. radar-design/B-US-UNIVERSE-EVIDENCE-2-RULING.md
5. radar-design/B-US-UNIVERSE-AUTHORITY-1-RETURN.md
6. radar-design/artifacts/b-us-universe-authority-1/source-manifest.json, commands.md, nasdaq-symbol-directory-definitions.md, iso10383-radar-mics.csv, iso10383-us-listing-context.csv, extract_authority_rows.py

Authority result:
- Nasdaq Q/G/S: CONFIRMED against Nasdaq Trader's Symbol Look-Up/Directory Data Fields & Definitions (retrieved 2026-09-17 22:23:39 UTC, page SHA-256 1fc8feb7fd060e52...). Market Category values are exactly Q = Nasdaq Global Select Market, G = Nasdaq Global Market, S = Nasdaq Capital Market; three values, no others published. The page carries no version or effective date.
- Other-listed N/A/P/Z/V: CONFIRMED. The Exchange field is defined as the listing stock exchange or market, with allowed values A = NYSE MKT, N = New York Stock Exchange (NYSE), P = NYSE ARCA, Z = BATS Global Markets (BATS), V = Investors' Exchange, LLC (IEXG); five values, no others published. Two labels are retired trade names (A is today NYSE American, Z is today Cboe BZX); the codes are correct and Radar's own venue strings in migration a4c8e2f19b70:41-42 are already more current than Nasdaq's page. V's label states the MIC IEXG in the official Nasdaq text itself.
- ISO MIC dispositions: all eight exist, are ACTIVE, are US, and carry no expiry in the 14 September 2026 register publication (2,883 rows, SHA-256 79de0f7704e260bd...). XNGS NASDAQ GLOBAL SELECT MARKET / SGMT / op XNAS / RMKT / validated 2026-04-27; XNMS NASDAQ GLOBAL MARKET / SGMT / op XNAS / RMKT / 2026-04-27; XNCM NASDAQ CAPITAL MARKET / SGMT / op XNAS / RMKT / 2026-04-27; XNYS NEW YORK STOCK EXCHANGE, INC. / OPRT / op XNYS / NSPD / 2025-04-28; XASE NYSE AMERICAN LLC / SGMT / op XNYS / RMKT / 2025-04-28; ARCX NYSE ARCA / SGMT / op XNYS / RMKT / 2025-04-28; BATS CBOE BZX U.S. EQUITIES EXCHANGE / SGMT / op XCBO / NSPD / last update 2018-06-25 with no validation date and an empty legal entity name; IEXG INVESTORS EXCHANGE / OPRT / op IEXG / NSPD / last update 2022-10-24 with no validation date. Three MICs are operating MICs or segments of a third-party operator while five are segments; that asymmetry is correct because the register holds no narrower code for NYSE equities or IEX equities.
- Missing/new listing venue codes: NOTHING TO ADD on official evidence. Nasdaq publishes no code for any US venue beyond those eight. The register does list active US venues with no directory code (LTSE, XMEM/MEMX, EPRL MIAX Pearl Equities, TXSE, 24EQ, XMXT) and two in-group renames that do not touch Radar (XCHI is now NYSE Texas, XBOS is now Nasdaq Texas), but ISO never states which venues accept primary listings, so Nasdaq's allowed-value list is the only authority on that question and it names none of them. If one of them starts listing, the new letter arrives with no C1 entry, which is exactly why C1's quarantine rule must stay.
- XNAS normalization ruling: DO NOT NORMALIZE. Keep XNGS/XNMS/XNCM as segment MICs. The directory field exists to carry the tier and XNAS is officially "NASDAQ - ALL MARKETS", so collapsing loses information irreversibly while the segment-to-operating rollup is free from the register's OPERATING MIC column; ISO's own definition of a segment MIC is a section of a market regulated differently, which is what a Nasdaq tier is; mic participates in uq_radar_quote_market and uq_radar_daily_close_market so a basis change rewrites 12,599 mappings plus history; and XNAS is already this codebase's fallback sentinel (quotes.py:97, prices/__init__.py:85), so legitimizing it would make finding F2 permanently undetectable. Instead record mic_type and operating_mic as separate fields.
- BATS and IEXG ruling: BOTH CONFIRMED AND KEPT. BATS is ACTIVE, is the only XCBO-group MIC naming the BZX equities market (distinct from BATY, BZXD, BATO, EDGA, EDGX), and carries the current Cboe name under the unchanged code; its stale 2018 stamp is group-wide register maintenance lag, not deprecation. IEXG is confirmed twice over, since the Nasdaq page itself writes "(IEXG)" for V, and is ACTIVE with no expiry. Evidence-2's zero IEXG rows is a fact about Radar's data, not about the mapping; keep the mapping so a future V row maps correctly instead of being quarantined. BUT: analysis_contract.py:42 KNOWN_US_MICS lists only seven of the eight and omits IEXG, so a first IEXG instrument would silently fall to "unknown" trading-day hints via analysis.py:423 — a fail-soft inconsistency that should be fixed with the B1 slice.
- Required C1 corrections: no remapping; eight of eight codes CONFIRMED, zero REMOVE, zero ADD, zero CORRECT_WITH_CHANGE at the code-to-MIC level. Six structural corrections: (A) record mic_type and operating_mic per row; (B) keep per-file/per-column interpretation — now officially justified because Nasdaq reuses Q and G with unrelated meanings in nasdaqlisted.txt's own Financial Status column, so the migration's flat CASE over u.exchange is correct only by namespace accident; (C) keep Radar's venue labels and record that Nasdaq's A and Z labels are retired names, so nobody syncs them backwards; (D) add IEXG to KNOWN_US_MICS or document the degradation; (E) the ELSE 'XXXX' at a4c8e2f19b70:32 and the 'XNAS' defaults are outside the confirmed vocabulary and C1's quarantine rule supersedes them (D8/F2); (F) drop or pin seed_radar_universe.py:32's undocumented 'Listing Exchange' alias, because Nasdaq publishes no field definitions for nasdaqtraded.txt at all.
- Impact on 114 safe candidates and seven drift rows: the 114 are ENTIRELY UNAFFECTED — their six MICs (ARCX 36, BATS 28, XNMS 26, XNCM 15, XNYS 5, XASE 4) are all officially ACTIVE with the meanings C1 assumed, so zero rows change MIC, zero change classification, and the first B1 apply remains exactly 114 insert-only rows. The full 146 are equally covered (adds XNGS 2, VENUE_UNKNOWN stays 0). The seven drift rows change no MIC value; what changes is the ruling basis — the register splits them three ways instead of two: T1 tier move inside Nasdaq (EPRX, FSHP, FSHPR, FSHPU — segment changes, operating MIC stays XNAS, legal entity stays Nasdaq, Inc.), T2 move inside the NYSE group (MVPA ARCX to XNYS — operating MIC stays XNYS, legal entity stays Intercontinental Exchange, Inc.), T3 operating-MIC change (KHC XNAS to XNYS, OPAD XNYS to XNAS — operator and legal entity both change). All fourteen MIC values on both sides of all seven rows are ACTIVE, so D1 is a history-continuity policy question, not a correctness repair.
- Remaining authoritative gaps: the Nasdaq definitions page is undated and unversioned, so a future re-check must diff its hash; Nasdaq publishes no field definitions for nasdaqtraded.txt, so the 'Listing Exchange' column Radar aliases has no authoritative meaning available; ISO never states which venues accept listings, so the missing-venue question rests solely on Nasdaq's allowed-value list; BATS and IEXG both lack a last validation date and BATS has an empty legal entity name (active, but the least maintained rows in the set); XNYS and BATS are categorised NSPD rather than RMKT with no official explanation, so MARKET CATEGORY CODE must not be used as a "is this a listing venue" filter; the annexes PDF was retrieved but has no extractable text layer here, so the category-code definitions came from the official Release 2.0 factsheet instead; and the register is a moving target — this publication is 14 September 2026, its modifications take effect 28 September 2026, and the next publication is 12 October 2026, so a maintenance design must re-validate on a cadence rather than treating this table as permanent. No directory data was fetched, so this return says nothing about current file contents.
- Recommended owner decisions D1/D2/D3/D8: D1 is READY TO RULE — keep segment MICs, add mic_type/operating_mic, adopt the T1/T2/T3 treatment, and note that no correctness repair is owed on the seven rows. D2 is UNTOUCHED by this assignment; nothing official bears on the rebrand-versus-reassignment question. D3 is UNBLOCKED on the venue question — all 26 non-common rows resolve to confirmed ACTIVE MICs, so D3 is purely a security-type policy choice. D8 is STRENGTHENED — fix the XNAS/XXXX fallback, because legitimizing XNAS would destroy the tier distinction the D1 ruling depends on; measured extent is still zero rows. Two new one-line items, C1-D (IEXG in KNOWN_US_MICS) and C1-F (the Listing Exchange alias), belong to the B1 slice.
- Smallest safe next assignment: none for the Researcher — the authoritative-definition carry is closed. The owner should now rule D1, D2, D3 and D8 on this return plus Evidence-2, after which the correct next assignment is the already-recommended B1 implementation slice for ONE Implementer: strict per-file parser/validator, dry-run reconciler, insert-only US primary mapper sized at exactly 114 rows, the F2/D8 fallback fix, and the two C1-D/C1-F one-liners — with no migration and no scheduler.

Release A remains CLOSED. Do not implement, mutate production, or dispatch another worker until the Mastermind reconciles this return into the B ledger and the owner approves the next step.
```
