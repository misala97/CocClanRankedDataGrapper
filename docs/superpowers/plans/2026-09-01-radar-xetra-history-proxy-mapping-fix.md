# Radar Xetra History-Proxy Mapping Fix Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Persist an audited exact-ISIN Xetra secondary mapping for each eligible Tradegate-primary German instrument so the existing backfill can populate historical charts.

**Architecture:** Extend each hashed German `MappingDecision` with optional flat history-proxy identity fields, preserving old payload hashes by omitting absent fields from canonical JSON. Generation activation atomically makes only the generation's primary and optional proxy rows authoritative; the unchanged backfill then discovers mapped Xetra secondary rows through `RadarInstrument`.

**Tech Stack:** Python 3, Flask, SQLAlchemy, MySQL/MariaDB, pytest, OpenFIGI mapping adapter, official Deutsche Börse reference catalogs, Yahoo chart history adapter

**Spec:** `docs/superpowers/specs/2026-09-01-radar-xetra-history-proxy-mapping-fix-design.md`

## Global Constraints

- No schema migration: `radar_instruments` already supports primary and non-primary MIC rows.
- A proxy is valid only for `XGAT` primary + one supported `XETR` candidate + complete official Xetra reference + EUR + the primary's exact ISIN.
- A missing, ambiguous, unsupported, currency-mismatched, or ISIN-mismatched proxy never invalidates an otherwise valid Tradegate primary.
- Existing generation payloads must retain their original SHA-256 verification behavior.
- Activation and rollback remain one database transaction; stale proxy authority cannot survive a generation switch.
- The existing history seam remains exact-ISIN and pre-native-only.
- Do not touch or commit the user's Telegram, candidate, scratchpad, or measurement WIP listed by `git status`.
- No provider payloads, cookies, API keys, or raw Deutsche Börse data enter Git.

---

### Task 1: Add proxy-aware mapping decisions without breaking old hashes

**Files:**
- Modify: `personal_apps/features/radar/instruments.py:65-330`
- Test: `personal_apps/tests/test_radar_openfigi.py`
- Test: `personal_apps/tests/test_radar_instruments.py`

**Interfaces:**
- Consumes: `OpenFigiProvider.us_share_classes(...)`, `OpenFigiProvider.venue_candidates(...)`, complete `ReferenceCatalog` values for `XGAT` and `XETR`.
- Produces: `MappingDecision(..., history_proxy_mic=None, history_proxy_symbol=None, history_proxy_isin=None, history_proxy_currency=None)` and backward-compatible `_canonical_payload(decisions) -> str`.

- [ ] **Step 1: Extend the OpenFIGI tests with the desired proxy behavior**

Add to `personal_apps/tests/test_radar_openfigi.py`:

```python
def test_tradegate_primary_keeps_same_isin_xetra_history_proxy():
    provider = FakeOpenFigi({
        ('TICKER', 'AAPL', 'US'): [us_result('AAPL', 'BBG001S5N8V8')],
        ('SHARE', 'BBG001S5N8V8', 'XGAT'): [de_result('APC', 'XGAT')],
        ('SHARE', 'BBG001S5N8V8', 'XETR'): [de_result('APC', 'XETR')],
    })

    decision = decide_mapping(instrument('AAPL'), provider,
                              BOTH_REFERENCES, {})

    assert (decision.mic, decision.symbol, decision.isin) == (
        'XGAT', 'APC', 'US0378331005')
    assert (decision.history_proxy_mic, decision.history_proxy_symbol,
            decision.history_proxy_isin,
            decision.history_proxy_currency) == (
                'XETR', 'APC', 'US0378331005', 'EUR')


@pytest.mark.parametrize('xetra_rows,xetra_references', [
    ([], [reference('APC', 'XETR', 'US0378331005')]),
    ([de_result('APC', 'XETR'), de_result('APC2', 'XETR')],
     [reference('APC', 'XETR', 'US0378331005'),
      reference('APC2', 'XETR', 'US0378331005')]),
    ([de_result('APC', 'XETR')],
     [reference('APC', 'XETR', 'DE0007164600')]),
    ([de_result('APC', 'XETR')],
     [reference('APC', 'XETR', 'US0378331005', currency='USD')]),
])
def test_invalid_xetra_history_candidate_does_not_invalidate_tradegate(
        xetra_rows, xetra_references):
    references = {
        'XGAT': BOTH_REFERENCES['XGAT'],
        'XETR': reference_catalog('XETR', xetra_references),
    }
    provider = FakeOpenFigi({
        ('TICKER', 'AAPL', 'US'): [us_result('AAPL', 'BBG001S5N8V8')],
        ('SHARE', 'BBG001S5N8V8', 'XGAT'): [de_result('APC', 'XGAT')],
        ('SHARE', 'BBG001S5N8V8', 'XETR'): xetra_rows,
    })

    decision = decide_mapping(instrument('AAPL'), provider, references, {})

    assert (decision.status, decision.mic) == ('mapped', 'XGAT')
    assert decision.history_proxy_mic is None


def test_xetra_primary_does_not_duplicate_itself_as_a_proxy():
    provider = FakeOpenFigi({
        ('TICKER', 'AAPL', 'US'): [us_result('AAPL', 'BBG001S5N8V8')],
        ('SHARE', 'BBG001S5N8V8', 'XETR'): [de_result('APC', 'XETR')],
    })

    decision = decide_mapping(instrument('AAPL'), provider,
                              BOTH_REFERENCES, {})

    assert decision.mic == 'XETR'
    assert decision.history_proxy_mic is None
```

- [ ] **Step 2: Run the mapping tests and verify RED**

Run:

```bash
cd personal_apps
python -m pytest tests/test_radar_openfigi.py -k "history_proxy or invalid_xetra_history or duplicate_itself" -v
```

Expected: FAIL because `MappingDecision` has no `history_proxy_*` attributes and `decide_mapping` returns immediately after selecting XGAT.

- [ ] **Step 3: Add backward-compatibility tests for canonical generation JSON**

Add to `personal_apps/tests/test_radar_instruments.py`:

```python
def test_absent_proxy_fields_preserve_the_old_generation_hash(
        generation_rows):
    import hashlib
    import json
    from features.radar import instruments as mod
    ticker = f'{PREFIX}OLD'
    old_payload = json.dumps({'decisions': [{
        'currency': 'EUR', 'isin': 'US0000000017',
        'mapping_source': 'openfigi', 'mic': 'XGAT', 'reason': None,
        'status': 'mapped', 'symbol': 'ZZOLD', 'ticker': ticker,
    }]}, sort_keys=True, separators=(',', ':'))

    decisions = [mod.MappingDecision(**item)
                 for item in json.loads(old_payload)['decisions']]

    assert mod._canonical_payload(decisions) == old_payload
    assert hashlib.sha256(mod._canonical_payload(decisions).encode()).hexdigest() == \
        hashlib.sha256(old_payload.encode()).hexdigest()


def test_proxy_identity_participates_in_the_generation_hash(generation_rows):
    from features.radar import instruments as mod
    ticker = f'{PREFIX}HASH'
    plain = _decision(ticker, symbol='ZZHASH', isin='US0000000017')
    proxied = dataclasses.replace(
        plain, history_proxy_mic='XETR', history_proxy_symbol='ZZHASHX',
        history_proxy_isin='US0000000017', history_proxy_currency='EUR')

    assert mod._canonical_payload([plain]) != mod._canonical_payload([proxied])
```

Add `import dataclasses` at the top of the test file.

- [ ] **Step 4: Run the compatibility tests and verify RED**

Run:

```bash
python -m pytest tests/test_radar_instruments.py -k "old_generation_hash or participates_in_the_generation_hash" -v
```

Expected: FAIL because `MappingDecision` does not accept proxy fields.

- [ ] **Step 5: Implement proxy resolution and compatible serialization**

In `personal_apps/features/radar/instruments.py`, append optional fields to `MappingDecision`:

```python
    history_proxy_mic: str | None = None
    history_proxy_symbol: str | None = None
    history_proxy_isin: str | None = None
    history_proxy_currency: str | None = None
```

Add a constant and serializer that omit absent fields:

```python
_HISTORY_PROXY_FIELDS = (
    'history_proxy_mic', 'history_proxy_symbol',
    'history_proxy_isin', 'history_proxy_currency',
)


def _decision_payload(decision):
    item = dataclasses.asdict(decision)
    for field in _HISTORY_PROXY_FIELDS:
        if item[field] is None:
            item.pop(field)
    return item


def _canonical_payload(decisions):
    ordered = sorted((_decision_payload(decision) for decision in decisions),
                     key=lambda item: item['ticker'])
    return json.dumps({'decisions': ordered}, sort_keys=True,
                      separators=(',', ':'))
```

Refactor `decide_mapping` so it validates both venue candidates before choosing the existing priority. Store verified rows in `verified_by_mic`; choose XGAT when present, otherwise XETR. When XGAT is primary, populate proxy fields only when the verified Xetra row has the same ISIN:

```python
        primary = verified_by_mic.get('XGAT') or verified_by_mic.get('XETR')
        if primary is not None:
            proxy = verified_by_mic.get('XETR')
            if primary.mic != 'XGAT' or proxy is None or \
                    proxy.isin != primary.isin:
                proxy = None
            return MappingDecision(
                ticker=ticker, status='mapped', reason=None,
                mic=primary.mic, symbol=primary.symbol, isin=primary.isin,
                currency='EUR', mapping_source='openfigi',
                history_proxy_mic=proxy.mic if proxy else None,
                history_proxy_symbol=proxy.symbol if proxy else None,
                history_proxy_isin=proxy.isin if proxy else None,
                history_proxy_currency=proxy.currency if proxy else None)
```

Preserve every existing primary refusal reason and override behavior. Do not infer an override proxy when OpenFIGI did not independently verify one.

- [ ] **Step 6: Run Task 1 tests GREEN**

Run:

```bash
python -m pytest tests/test_radar_openfigi.py tests/test_radar_instruments.py -q
```

Expected: all tests pass.

- [ ] **Step 7: Commit Task 1**

```bash
git add personal_apps/features/radar/instruments.py \
  personal_apps/tests/test_radar_openfigi.py \
  personal_apps/tests/test_radar_instruments.py
git commit -m "fix(radar): retain audited Xetra history proxies"
```

---

### Task 2: Apply primary and proxy rows atomically across activation and rollback

**Files:**
- Modify: `personal_apps/features/radar/instruments.py:395-475`
- Test: `personal_apps/tests/test_radar_instruments.py`

**Interfaces:**
- Consumes: proxy-aware `MappingDecision` from Task 1.
- Produces: `activate_generation(generation_id, now) -> int` and `rollback_generation(generation_id, now) -> int` that leave only the selected primary and optional Xetra proxy mapped for governed tickers.

- [ ] **Step 1: Write failing activation and stale-proxy tests**

Extend the `_decision` test helper to accept proxy keyword arguments and pass them to `MappingDecision`. Add:

```python
def test_activation_persists_tradegate_primary_and_xetra_proxy(
        generation_rows):
    from features.radar import instruments as mod
    from models import RadarInstrument
    ticker = f'{PREFIX}PROXY'
    generation = mod.persist_generation([_decision(
        ticker, mic='XGAT', symbol='ZZTG', isin='US0000000017',
        history_proxy_mic='XETR', history_proxy_symbol='ZZXE',
        history_proxy_isin='US0000000017',
        history_proxy_currency='EUR')], NOW)

    mod.activate_generation(generation.id, NOW)

    rows = {row.mic: row for row in RadarInstrument.query.filter_by(
        ticker=ticker, market='de').all()}
    assert (rows['XGAT'].is_primary, rows['XGAT'].mapping_status) == \
        (True, 'mapped')
    assert (rows['XETR'].is_primary, rows['XETR'].mapping_status,
            rows['XETR'].provider_symbol, rows['XETR'].isin) == \
        (False, 'mapped', 'ZZXE', 'US0000000017')
    assert rows['XGAT'].mapping_generation_id == generation.id
    assert rows['XETR'].mapping_generation_id == generation.id


def test_later_generation_without_proxy_deactivates_the_old_proxy(
        generation_rows):
    from features.radar import instruments as mod
    from models import RadarInstrument
    ticker = f'{PREFIX}STALE'
    first = mod.persist_generation([_decision(
        ticker, mic='XGAT', symbol='ZZTG', isin='US0000000017',
        history_proxy_mic='XETR', history_proxy_symbol='ZZXE',
        history_proxy_isin='US0000000017',
        history_proxy_currency='EUR')], NOW)
    mod.activate_generation(first.id, NOW)
    second = mod.persist_generation([
        _decision(ticker, mic='XGAT', symbol='ZZTG2',
                  isin='US0000000017')], NOW + dt.timedelta(days=7))

    mod.activate_generation(second.id, NOW + dt.timedelta(days=7))

    proxy = RadarInstrument.query.filter_by(
        ticker=ticker, market='de', mic='XETR').one()
    assert proxy.is_primary is False
    assert proxy.mapping_status == 'unavailable'
    assert proxy.mapping_generation_id == second.id
```

- [ ] **Step 2: Run the activation tests and verify RED**

Run:

```bash
python -m pytest tests/test_radar_instruments.py -k "persists_tradegate_primary or deactivates_the_old_proxy" -v
```

Expected: FAIL because activation ignores proxy fields and leaves old non-primary rows mapped.

- [ ] **Step 3: Write failing rollback and duplicate-identity tests**

Add a rollback assertion to a new test: activate a proxy-aware generation over a legacy Xetra primary, locate the auto-snapshotted `source='legacy'` generation, roll it back, and assert the XGAT row is unavailable while the legacy XETR row is mapped and primary.

Add a generation with two tickers whose proxy identities are both `('XETR', 'US0000000017')`; assert `activate_generation` raises `ValueError` and writes no instrument rows for either ticker.

- [ ] **Step 4: Run the rollback/duplicate tests and verify RED**

Run:

```bash
python -m pytest tests/test_radar_instruments.py -k "rollback_removes_proxy_authority or duplicate_proxy_identity" -v
```

Expected: FAIL because `_apply_generation` validates only primary identities and rollback does not deactivate proxy authority.

- [ ] **Step 5: Implement authoritative generation application**

Add an upsert helper in `instruments.py`:

```python
def _upsert_mapped_row(decision, generation_id, now, *, mic, symbol,
                       isin, currency, is_primary):
    row = RadarInstrument.query.filter_by(
        ticker=decision.ticker, market='de', mic=mic).one_or_none()
    if row is None:
        row = RadarInstrument(
            ticker=decision.ticker, market='de', venue=VENUE_BY_MIC[mic],
            mic=mic, provider_symbol=symbol, currency=currency,
            is_primary=False, mapping_status='unavailable', mapped_at=now)
        db.session.add(row)
    row.venue = VENUE_BY_MIC[mic]
    row.provider_symbol = symbol
    row.currency = currency
    row.isin = isin
    row.is_primary = is_primary
    row.mapping_status = 'mapped'
    row.mapping_source = decision.mapping_source
    row.mapped_at = now
    row.mapping_generation_id = generation_id
    return 1
```

At the start of `_apply_decision`, update every German row for the ticker to `is_primary=False`, `mapping_status='unavailable'`, `mapped_at=now`, and `mapping_generation_id=generation_id`. For a mapped decision, upsert the primary and then the optional proxy with `is_primary=False`.

Extend `_apply_generation` identity validation to include both primary and proxy `(mic, isin)` pairs before calling `_apply_decision`. Reject a pair assigned to two different tickers.

- [ ] **Step 6: Run Task 2 tests GREEN**

Run:

```bash
python -m pytest tests/test_radar_instruments.py -q
```

Expected: all tests pass, including prior atomic-failure and rollback coverage.

- [ ] **Step 7: Commit Task 2**

```bash
git add personal_apps/features/radar/instruments.py \
  personal_apps/tests/test_radar_instruments.py
git commit -m "fix(radar): activate German proxy mappings atomically"
```

---

### Task 3: Prove the existing backfill and history seam consume activated proxies

**Files:**
- Test: `personal_apps/tests/test_radar_market_data.py`
- Test: `personal_apps/tests/test_radar_history.py`

**Interfaces:**
- Consumes: activated non-primary `RadarInstrument(market='de', mic='XETR', mapping_status='mapped')` from Task 2.
- Produces: regression proof that `_instrument_targets('de', now)` includes the proxy and `series_for(...)` still enforces exact-ISIN pre-native composition.

- [ ] **Step 1: Write the end-to-end backfill eligibility test**

Add to `personal_apps/tests/test_radar_market_data.py`:

```python
def test_de_backfill_discovers_an_activated_xetra_proxy(ctx):
    from features.radar import instruments
    from scripts import backfill_radar_market_history as cli
    ticker = f'{PREFIX}PX'
    decision = instruments.MappingDecision(
        ticker=ticker, status='mapped', reason=None, mic='XGAT',
        symbol='ZZTG', isin='DE000ZZTST01', currency='EUR',
        mapping_source='openfigi', history_proxy_mic='XETR',
        history_proxy_symbol='ZZXE',
        history_proxy_isin='DE000ZZTST01',
        history_proxy_currency='EUR')
    generation = instruments.persist_generation([decision], NOW)
    instruments.activate_generation(generation.id, NOW)

    targets = cli._instrument_targets('de', NOW)

    target = next(row for row in targets if row.ticker == ticker)
    assert (target.mic, target.provider_symbol, target.is_primary,
            target.isin) == ('XETR', 'ZZXE', False, 'DE000ZZTST01')
```

- [ ] **Step 2: Run the test and verify it passes only after Tasks 1–2**

Run:

```bash
python -m pytest tests/test_radar_market_data.py::test_de_backfill_discovers_an_activated_xetra_proxy -v
```

Expected: PASS with Tasks 1–2 present. To prove the test has teeth, temporarily remove the proxy upsert call, rerun and observe failure at `next(...)`, then restore production code and rerun PASS.

- [ ] **Step 3: Strengthen the existing history seam test**

In `test_series_for_composes_one_xetra_proxy_seam`, set the XGAT and XETR rows' `mapping_generation_id` to the same generated ID and retain assertions that:

```python
assert series.history_proxy is True
assert (series.proxy_mic, series.native_mic) == ('XETR', 'XGAT')
assert series.native_from == DAY - dt.timedelta(days=2)
assert dict(series.closes)[DAY - dt.timedelta(days=3)] == \
    decimal.Decimal('10.0000')
assert dict(series.closes)[DAY - dt.timedelta(days=2)] == \
    decimal.Decimal('11.0000')
```

Keep the existing negative checks for mismatched ISIN and currency.

- [ ] **Step 4: Run backfill/history/detail integration tests**

Run:

```bash
python -m pytest tests/test_radar_market_data.py \
  tests/test_radar_history.py tests/test_radar_detail.py -q
```

Expected: all tests pass.

- [ ] **Step 5: Commit Task 3**

```bash
git add personal_apps/tests/test_radar_market_data.py \
  personal_apps/tests/test_radar_history.py
git commit -m "test(radar): prove Xetra proxy backfill path"
```

---

### Task 4: Verify compatibility, record deployment state, and stop

**Files:**
- Modify: `docs/superpowers/plans/2026-08-31-radar-market-data-v2-ledger.md`
- Modify: `HANDOFF.md`

**Interfaces:**
- Consumes: completed Tasks 1–3 and fresh test output.
- Produces: exact deployment and operator continuation instructions; no automatic deploy or production mutation.

- [ ] **Step 1: Run the focused mapping and market-data gate**

Run:

```bash
cd personal_apps
python -m pytest tests/test_radar_openfigi.py \
  tests/test_radar_instruments.py tests/test_radar_reference_universe.py \
  tests/test_radar_market_data.py tests/test_radar_market_data_report.py \
  tests/test_radar_history.py tests/test_radar_detail.py \
  tests/test_radar_api.py tests/test_radar_daemon.py -q
```

Expected: zero failures.

- [ ] **Step 2: Run adjacent backend regression and static diff checks**

Run:

```bash
python -m pytest tests/test_radar_quotes.py tests/test_radar_board.py \
  tests/test_radar_leaderboard.py tests/test_radar_migration.py -q
cd ..
git diff --check
git status --short
```

Expected: zero test failures; `git diff --check` exits 0; status lists only this fix plus the protected pre-existing user files.

- [ ] **Step 3: Update the ledger and handoff with exact evidence**

Append a dated section to the ledger recording:

- the production symptom: active generation 1, 2,517 German primaries, but only 13 pre-existing Xetra backfill targets;
- design and implementation commit IDs;
- exact focused test counts and commands;
- current production generation 1 and rollback generation 2 as operator-observed state, not local DB state;
- no migration and no automatic deployment;
- next operator steps: deploy, refresh mappings, audit the new exact hash, activate it, run bounded `--market de --apply` batches, and verify XGAT/XETR charts.

Update `HANDOFF.md` to point at the current `dev_personal` workspace/HEAD, retain the protected dirty-file list, and make the proxy rollout the immediate next action. Do not mark the production fix active before Michi performs those steps.

- [ ] **Step 4: Commit verification records only**

```bash
git add docs/superpowers/plans/2026-08-31-radar-market-data-v2-ledger.md \
  HANDOFF.md
git commit -m "docs(radar): hand off Xetra proxy rollout"
```

- [ ] **Step 5: Final repository verification**

Run:

```bash
git log -6 --oneline
git status --short
git diff HEAD~4..HEAD --check
```

Expected: the fix commits are present; no fix-owned changes remain uncommitted; protected user files remain unchanged and uncommitted.

Stop before pushing, deploying, refreshing production mappings, activating a generation, or running the production backfill. Those are operator-controlled actions.
