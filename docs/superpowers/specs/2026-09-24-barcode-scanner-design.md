# Barcode Scanner (personal_apps) — design

Date: 2026-09-24. Status: approved in chat ("Build + ship").

## Goal

A page at `/barcode/` in personal_apps: point the phone camera at a product
barcode, get product info. German products first. Admin-only, German UI.

Info the user asked for (all four offered blocks):

1. Nährwerte & Makros — per 100 g and per portion.
2. Zutaten & Allergene — ingredients, allergens + traces, vegan/vegetarian/palm
   oil, Pfand if the product is tagged with it.
3. Scores — Nutri-Score, NOVA, Eco-Score.
4. Non-food — cosmetics, pet food, other products, books.

Out of scope: prices (no free German source), PZN/medicines, server-side scan
history, editing upstream data.

## Approach

Flask lookup route + plain Jinja page with one static JS and one CSS file (the
Showoff shape; no Vite entry). Rejected: browser calling the APIs directly (no
User-Agent, DNB is not browser-callable, raw payload parsing in JS) and a React
island (one screen, no client state worth a build).

## Units

`features/barcode/`

- `codes.py` — pure: `normalize(raw) -> str` (digits only; 8/12/13 digits; a
  12-digit UPC-A becomes 13 with a leading 0; raises `InvalidCode`),
  `checksum_ok(code)`, `classify(code) -> 'book' | 'instore' | 'product'`,
  `gs1_label(code) -> str | None` (GS1 prefix table, German country names;
  978/979 ISBN, 977 ISSN, 20–29 and EAN-8 `2…` in-store, 98/99 coupons).
- `sources.py` — HTTP + normalizers.
  - `fetch_off(code)`: `https://world.openfoodfacts.org/api/v2/product/<code>.json?product_type=all&fields=…`.
    OFF answers a non-food code with a 302 to the right sister DB (beauty, pet
    food, products) — verified 2026-09-24 — so one call covers all four.
    Returns `None` for not found (`status` 0), raises `UpstreamError` on
    timeout / 5xx / non-JSON.
  - `normalize_off(product, flavor_host)` → dict: `type`, `name` (German
    `product_name_de` first), `brand`, `quantity`, `image` (https only, OFF
    image hosts only), `scores` (unknown / not-applicable dropped),
    `nutrition` (rows: kcal, fat, saturated fat, carbs, sugars, fibre, protein,
    salt; per 100 g and per serving; `serving_size`), `ingredients` (German
    text first, `lang: other` when only another language exists),
    `allergens` + `traces` (14 EU allergens → German names; unknown tags
    humanised), `diet` (vegan / vegetarian / palm oil from
    `ingredients_analysis_tags`), `deposit` (label containing `pfand`/`deposit`),
    `url` (product page on the flavor's own site).
  - `fetch_dnb(isbn)`: DNB SRU, `recordSchema=oai_dc`, `maximumRecords=1`.
    `normalize_dnb(xml)` → `title`, `authors` ("Schlink, Bernhard
    [Verfasser]" → "Bernhard Schlink"), `publisher`, `year`, `pages`,
    `price_de` (from the ISBN identifier's `EUR … (DE)`, price at
    registration), `subject`, `url` (d-nb.info link when present).
  - `lookup(code)`: book → DNB, falling through to OFF when DNB has no record;
    everything else → OFF. Always attaches `gs1`, `kind`, `found`.
- `routes.py` — blueprint `barcode` at `/barcode`, both routes
  `@admin_required`:
  - `GET /barcode/` → `templates/barcode/index.html`.
  - `GET /barcode/api/<raw>` → JSON. 400 invalid code / bad checksum, 502
    upstream unreachable (`error` text in German), 200 otherwise (including
    not found: `found: false`).

User-Agent on every upstream call: `PersonalApps-Barcode/1.0` (OFF asks for an
identifying app name; no personal contact data is sent). Timeout 8 s.

## Page (`templates/barcode/index.html`, `static/barcode/barcode.{js,css}`)

- Hub tokens from `overview.html` (dark, Inter / Space Grotesk). Mobile-first,
  390 px reference width.
- Scanner: rear camera (`facingMode: environment`), EAN-13 / EAN-8 / UPC-A.
  Native `BarcodeDetector` when it supports `ean_13`; otherwise the
  `barcode-detector` polyfill (zxing-wasm) imported on demand from jsDelivr.
  Camera auto-starts when permission is already granted, else a start button.
  Hit = valid checksum → vibrate, stop camera, look up. Torch button only when
  the track reports `torch` capability.
- Manual digit input always present (desktop, camera denied, damaged code).
- Result card rendered with DOM APIs only (`textContent`), never `innerHTML`
  with upstream data.
- Recent scans: last 10 `{code, name}` in `localStorage` (try/catch), tap to
  reopen.

## Access

`admin_required` on both routes; blueprint stays out of `_MEMBER_BLUEPRINTS`.
Hub card `Barcode Scanner` in `APPS`; members' hub filter unchanged, so they
do not see it.

## Errors

| Case | Response | Page |
|---|---|---|
| bad digits / checksum | 400 | "Ungültiger Code" |
| not found | 200 `found:false` + gs1 | explanation + OFF "eintragen" link |
| in-store code not found | 200 `found:false`, `kind: instore` | "Handelsinterne Nummer …" |
| timeout / 5xx | 502 | "nicht erreichbar — nochmal versuchen" |
| camera denied / no camera | — | message, manual input stays |

## Tests

`tests/test_barcode.py`, DB-free (monkeypatched `auth.current_user`, as
`test_showoff.py` does):

- codes: checksum, normalize (12 → 13, rejects), classify, gs1 boundaries.
- normalizers against recorded fixtures in `tests/fixtures/barcode/`
  (OFF food, OFF beauty via redirect, DNB XML) — no network.
- route: 400 / 200 / 502 with `sources` HTTP monkeypatched.
- access: anonymous → login, member → 403, admin → 200; hub card admin-only.

Browser check: python-playwright at 390×844 — manual lookup render, plus a
fake-camera run (`--use-file-for-fake-video-capture` with a generated EAN-13
video) to prove the polyfill scan path end to end.
