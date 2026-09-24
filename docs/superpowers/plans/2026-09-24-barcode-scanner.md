# Barcode Scanner Implementation Plan

> **For agentic workers:** executed inline in the authoring session (superpowers:executing-plans), per Michi's standing rule for small plans. Steps use checkbox (`- [ ]`) syntax.

**Goal:** `/barcode/` in personal_apps — scan a product barcode with the phone camera, show food / non-food / book info.

**Architecture:** Flask blueprint `features/barcode/` with a pure code module, an upstream-sources module and two routes; a standalone Jinja page with one static JS and one CSS file (Showoff shape, no Vite).

**Tech Stack:** Flask, requests, xml.etree, vanilla JS (`BarcodeDetector`, `barcode-detector` polyfill from jsDelivr), pytest, python-playwright.

**Spec:** `docs/superpowers/specs/2026-09-24-barcode-scanner-design.md`

## Global Constraints

- Admin-only: `@admin_required` on every route; blueprint NOT added to `_MEMBER_BLUEPRINTS`.
- German UI copy.
- Upstream calls: `User-Agent: PersonalApps-Barcode/1.0`, timeout 8 s. No personal data in requests.
- Upstream data reaches the DOM through `textContent` / attributes only — never `innerHTML`.
- Tests DB-free (monkeypatch `auth.current_user`); run ONLY named test files, never a wide `tests/` selector (suite binds the local dev DB).
- Commits on `dev_personal`, `git checkout dev_personal` in the same command as each commit; add only this plan's files (tree has unrelated dirty files).

---

### Task 1: `features/barcode/codes.py`

**Files:** Create `personal_apps/features/barcode/__init__.py`, `personal_apps/features/barcode/codes.py`; Test `personal_apps/tests/test_barcode.py`

**Produces:** `InvalidCode(ValueError)`; `checksum_ok(code: str) -> bool`; `normalize(raw: str) -> str` (8/13 digits, 12 → '0'+12, raises `InvalidCode`); `classify(code) -> 'book'|'instore'|'product'`; `gs1_label(code) -> str|None`.

- [ ] Tests: valid EAN-13 `4001686301265`, EAN-8 `40111445`-style valid code, UPC-A 12 → 13; rejects wrong check digit, letters, length 10, unicode digits; classify 978/979 → book, `2…` EAN-13 / `02…`/`04…` / EAN-8 `0…`/`2…` → instore, `400…` → product; gs1 boundaries 400 & 440 → Deutschland, 441 → not Deutschland, 977 → ISSN, 978 → ISBN, unassigned 140 → None.
- [ ] Run `python -m pytest tests/test_barcode.py -q` → FAIL (module missing).
- [ ] Implement.
- [ ] Run → PASS. Commit `feat(barcode): code validation, classification, GS1 prefixes`.

### Task 2: `features/barcode/sources.py`

**Files:** Create `personal_apps/features/barcode/sources.py`, fixtures `personal_apps/tests/fixtures/barcode/{off_haribo.json,off_clubmate.json,obf_nivea.json,dnb_schulze.xml,dnb_empty.xml}` (recorded live once); extend `tests/test_barcode.py`.

**Consumes:** `classify`, `gs1_label`. **Produces:** `UpstreamError`; `fetch_off(code) -> (product: dict, host: str) | None`; `normalize_off(product, host) -> dict`; `fetch_dnb(isbn) -> dict|None`; `normalize_dnb(xml: bytes) -> dict|None`; `lookup(code) -> dict` with keys `code, kind, gs1, found, product, book, add_url`.

- [ ] Record fixtures with a scratch script (real responses, trimmed to requested fields).
- [ ] Tests: German name preferred; brand/quantity; image kept only for https OFF hosts; unknown Nutri-Score dropped; nutrition rows per 100 g + per serving with basis `100 ml` for ml products; kcal falls back from kJ; allergens → German (`en:nuts` → Schalenfrüchte, `en:soybeans` → Soja), unknown tag humanised (`en:kiwi` → Kiwi); diet vegan/vegetarian/palm-oil; deposit from a `pfand` label; ingredients `lang: other` fallback; beauty via host → type beauty + Open Beauty Facts link; DNB title/author flip/publisher/year/pages/price_de/url; empty DNB → None; lookup: book → DNB, book miss → OFF, product miss → `found: False` + `add_url`; requests timeout → `UpstreamError`; 429/5xx → `UpstreamError`.
- [ ] Run → FAIL. Implement. Run → PASS. Commit `feat(barcode): Open Food Facts family + DNB lookups`.

### Task 3: routes, registration, hub card

**Files:** Create `personal_apps/features/barcode/routes.py`, `personal_apps/templates/barcode/index.html` (shell); Modify `personal_apps/app.py` (import + register + `APPS` entry); extend `tests/test_barcode.py`.

**Produces:** blueprint `barcode` at `/barcode`; `GET /barcode/` (page), `GET /barcode/api/<raw>` (JSON: 200 / 400 `{error}` / 502 `{error, code}`).

- [ ] Tests: api 400 on bad checksum; 200 with monkeypatched `sources.lookup`; 502 on `UpstreamError`; access matrix on `localhost` and `FULL_ACCESS_HOST` — anonymous → 302 `/login`, member → 403, admin → 200; hub lists `/barcode/` for admin, not for member.
- [ ] Run → FAIL. Implement. Run `python -m pytest tests/test_barcode.py tests/test_showoff.py -q` → PASS. Commit `feat(barcode): admin-only routes and hub card`.

### Task 4: the page

**Files:** `personal_apps/templates/barcode/index.html`, `personal_apps/static/barcode/barcode.js`, `personal_apps/static/barcode/barcode.css`.

- [ ] Verify polyfill entry path on jsDelivr (`barcode-detector@3` package exports).
- [ ] Build: viewfinder + start/next button + torch; native detector or polyfill; two identical reads confirm a hit; manual input; result cards (product / book / not found / error); recent list (localStorage, try/catch).
- [ ] Playwright (scratch script, in-process server, admin monkeypatched, 390×844): (a) fake camera fed a generated EAN-13 `.y4m` → card appears (proves the polyfill scan path); (b) manual `9783423282390` → book card; (c) `4005808890507` → beauty card; (d) invalid code → error. Read each PNG. Fix, re-run.
- [ ] Commit `feat(barcode): scanner page`.

### Task 5: ship

- [ ] `python -m pytest tests/test_barcode.py tests/test_showoff.py tests/test_auth.py -q` → PASS.
- [ ] `git checkout main && git merge dev_personal --no-edit && git push origin main && git checkout dev_personal && git push origin dev_personal` (approved in chat: "Build + ship").
