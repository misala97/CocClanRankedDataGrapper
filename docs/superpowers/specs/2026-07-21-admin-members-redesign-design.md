# Admin Members Rework — Structure Spec

**Date:** 2026-07-21
**Page:** `/admin/members`
**Type:** rework / rethink (not a reskin). No route or endpoint logic changes.
**Theme:** established "Night Ops Scope" system (PRODUCT.md / DESIGN.md), extended per the
Overview / Monitor / Roster / Insights precedent — **not re-litigated**. Structure contract:
sections, hierarchy, data mapping, behavior, responsive arrangement. Visual vocabulary belongs
to impeccable — see §8.

Supersedes §5.4 of `2026-07-21-admin-redesign-design.md`.

---

## 1. Problem

`/admin/members` is accordion-era: a collapsible "New Member Check" stacked over a flat
four-column table (Player / Group Chat / War Pref / Comment). It carries the patterns the
system now bans — side-stripe verdict cards (`border-left: 3px`), emoji as functional icons
(🆕 🏰 👤 ✓ ✗ ⚠), `dblclick`-only controls (no keyboard/touch path), and off-system fonts
(`DM Sans`). It also under-uses its own data: the editor shows only name + tag when town-hall,
league, join date, and vetted-status all sit free on the `Player` record.

## 2. Target shape

Two stacked sections, verdict-led / exceptions-first (the sibling-page language):

1. **New Member Check** — leads. A decision queue: evaluate recent joiners → verdict + evidence
   → clear. Collapses to an "all clear" hairline when nothing is unchecked.
2. **Member Roster** — the standing editor for all in-clan members, an enriched, searchable,
   quick-filterable table.

Rationale: the two jobs differ in nature (a transient, alert-driven, live-API decision queue vs.
a standing metadata editor over cheap server-rendered data). Keeping them as two sections lets
each be shaped for its job and keeps the heavy on-demand API data out of the always-rendered
roster. Confirmed with user 2026-07-21.

## 3. Backend / route changes

**None.** The route stays `players = Player.query.filter_by(in_clan=True).order_by(name)`. Every
enrichment this rework adds — town-hall, league (+ league-icon property), join date, and
`newbie_check` (vetted) status — is already on the `Player` record and reaches the template for
free. No new fields, no endpoint edits. (Named explicitly per the backend gate: nothing was
silently added or silently ruled out — no backend change is warranted here.)

**Unchanged endpoints** the page uses:
- `POST /admin/evaluate-new-members` → `{count, results[]}` (§4).
- `POST /admin/members/<tag>/update` — accepts `in_group_chat` (bool), `war_preference_custom`
  (`in`/`out`/null), `admin_comment` (text), `newbie_check` (bool).

## 4. Data brief

**Route (server):** `players` — in-clan `Player[]` by name. Per-player fields available:
`name, tag, current_th, league_tier` (+ league-icon property), `in_group_chat`,
`war_preference_in_game` (read-only API value), `war_preference_custom`, `admin_comment`,
`join_date`, `newbie_check`.

**`/admin/evaluate-new-members` (POST)** → `count` + `results[]`, sorted decline → consider →
accept. Each result: `name, tag, join_date, days_ago, th, ranked_league, league_icon,
hero_pct, heroes[{name, level, max_level}], checks[{status: pass|warn|fail, label, detail}]`
(five checks: Heroes, War Stars, Donations, Attack Wins, Ranked League), `verdict:
accept|consider|decline`; or `error` when the live fetch fails.

Everything both sections render already exists in these — no new data.

## 5. Per-section structure

Header (`_page_header.html` existing slots): title + accent span, one orientation line, a meta
figure for the active-member count; the **roster search** goes in the `page_controls` slot.
`_admin_tabs.html` below (Members tab already badges `newbie_check_count`). No new header slot.

### 5.1 New Member Check (leads)

- **Trigger:** a Run-check control. Evaluation stays **manual** (each candidate is a live CoC-API
  fetch — slow); the control names the unchecked count so the work is visible before the click.
- **Per candidate — verdict-led row:** the verdict (`accept` / `consider` / `decline`) leads,
  in the established judgment-badge vocabulary; identity (town-hall, name → player page, tag,
  "joined Nd ago"); a hero-development meter (`hero_pct`); the five `checks` as pass/warn/fail
  chips (each carries its `detail`); and one primary action — **Mark checked** (`newbie_check:
  true`, removes the row and decrements the count). API-error candidates render a clear error row
  with the same Mark-checked action.
- **Detail on demand:** a real disclosure per candidate → per-hero level/max bars, the checks
  with full detail text, and the external-profile links (player page + clashspot). Disclosure is
  keyboard/touch-native (not `title`/hover, not `dblclick`).
- **Empty / all-clear:** when `count == 0`, the section collapses to an "all clear" hairline
  (the Overview pattern) — not a dead empty box.

### 5.2 Member Roster (the editor)

- **Search** (header controls slot) filters the roster by name/tag.
- **Quick-filter chips** (client-side, over the already-loaded roster): **Not in chat**,
  **War override** (has a custom war-pref), **Has note**, **Unvetted** (`newbie_check == false`).
  Each chip shows its count and toggles a filter; the intent is to surface admin gaps without
  leaving the single scannable table.
- **Enriched roster table**, one row per member:
  - *Identity:* name (→ player page) + tag + **town-hall** + **league** (+ icon). This is the
    context the old page dropped.
  - *Group chat:* a single-click toggle (in / not-in), keyboard-operable, with a real pressed
    state.
  - *War preference:* the **read-only in-game API value** shown alongside the **editable custom
    override** (single-click cycle in / out / none, keyboard-operable). Two distinct controls —
    the API value is never editable; the override is.
  - *Admin comment:* an inline text field with save-on-blur/enter + a save affordance.
  - *(Vetted status* surfaces via the Unvetted filter/state, tying the roster to §5.1.)
- All edits → `POST /admin/members/<tag>/update` (existing; already accepts these fields). No
  `dblclick`; single-click + keyboard throughout.

## 6. Responsive strategy

- **Both** the roster table (with its inline toggle / war-pref / comment controls) and the
  vetting rows drop to the established **divided roster-row pattern** on phone width — identity
  line on top, the controls wrapping below. **Never** per-entity cards (DESIGN.md standing ban).
- **Quick-filter chips** wrap; the search control goes full-width (header toolbar behavior).
- **Vetting check-chips** and the hero meter wrap within each row.
- Validation viewports: **390×844**, **768×1024**, **1200×800**.

## 7. Reuse (don't reinvent)

- **Page header** — existing slots (title + accent, desc, one meta figure, `page_controls`
  search). No new slot.
- **`_admin_tabs.html`** — unchanged (Members tab + `newbie_check_count` badge already exist).
- **Judgment / verdict badges** — established vocabulary; reuse for the accept/consider/decline
  verdicts and the pass/warn/fail check chips (map to the existing semantic tiers).
- **Divided roster-row** mobile pattern, **real `aria-expanded` disclosure**, **single-click +
  keyboard toggle** with `aria-pressed`, **in-surface toast** for save feedback — all established
  on the Roster page this cycle; reuse, don't reinvent.
- **Scope-console command-deck aesthetic** from the sibling admin pages — extend, don't restyle.

## 8. Open questions for impeccable

- **Verdict-row treatment:** how a candidate row reads at a glance — weight of the verdict badge
  vs. the check chips, how the hero-% meter renders, how decline/consider/accept differentiate
  without a side-stripe.
- **Quick-filter chips:** active/inactive state, how the counts read, multi-select vs. single.
- **War-preference dual control:** how the read-only API value and the editable custom override
  sit together so it's obvious which is which and which is editable.
- **Group-chat toggle & comment field:** the affordances in the roster row (and how they wrap on
  mobile without becoming cards).
- **External-profile links** in the vetting detail: treatment as reference tools.
- **All-clear collapse** for the vetting section.
- **Motion:** vetting-row reveal after Run-check, Mark-checked exit, filter-chip feedback, save
  toast — defer to a final `/impeccable animate` pass.
