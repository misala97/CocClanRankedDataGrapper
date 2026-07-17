# Page Header Redesign — Design Spec

**Date:** 2026-07-17
**Component:** `coc_stats/templates/_page_header.html` (shared partial, ~18 pages)
**Type:** Shared-shell structural redesign (cross-page). Not a single route.

This is a *structure contract*. It defines the header's zones, template API,
layout arrangement, sticky behavior, and per-page migration — not its look.
Palette, type treatment, spacing, borders, and the actual CSS are `impeccable`'s
to decide (see "Open questions for impeccable").

---

## 1. Why

`_page_header.html` is included at the top of every content page except the
index (which has its own hero). It currently exposes four free-form slots
(`page_header_title`, `page_header_desc`, `page_header_right`, `page_controls`)
with no rules about how they relate. The result reads as chaotic for four
reasons the user confirmed:

1. **The controls pile.** `page_controls` is a single free-form HTML blob.
   Data pages cram it — `ranked_weeks` piles 7 controls (week dropdown, search,
   rank-zone filter, "Show left", "Reminder", "Week Analysis" link, "Show
   inactive") all as identical `.action-btn` pills, some with inline-styled
   one-off colors. No primacy, no grouping. Nothing stops the next page from
   doing the same.
2. **Loud chrome.** A 4px glowing gradient stripe sits left of every title
   (`.page-header h1::before`) and a radial-glow wash sits behind the whole
   header (`.page-header::before`). The stripe is a >1px colored accent stripe —
   **explicitly banned** by `DESIGN.md`'s Don'ts.
3. **Inconsistent titles.** Emoji on some pages (`🛡️ Equipment` — also banned:
   "no raw emoji as icon"), accent-word placement varies, and the desc line
   ranges from one plain sentence to a data-and-badge cram.
4. **Too heavy / space-hungry.** Giant title + subtitle + **two separately
   sticky bars** (`.page-header` and `.page-controls`, same `top`, both
   `z-index: 99`) take a big bite out of the viewport before any content shows.
   A prior fix already un-sticks everything below 640px because the header ate
   ~46% of the phone viewport.

The redesign fixes all four at the structural layer, so `impeccable` inherits
clean bones.

---

## 2. Header zones (final anatomy)

Top-to-bottom, all left-aligned (stacked-bands arrangement):

1. **Identity row** — the title, plus an optional right-aligned chip.
2. **Orientation** — an optional single plain-prose line.
3. **Meta strip** — an optional row of labeled dataset figures.
4. **Controls** — an optional primary selector followed by a secondary cluster.

Any zone except the title is optional; a page that sets none of them renders a
bare title (e.g. `admin_hub`, `raid_stats`).

---

## 3. Template API (slots)

| Slot | Status | Function | Rendered as |
|---|---|---|---|
| `page_header_title` | keep | Page title. Exactly one accent segment allowed (the existing `<span>`). **No emoji.** | The h1 |
| `page_header_desc` | keep | One plain orientation sentence. **No data facts, no badges, no counts.** | Sub-line under title |
| `page_header_meta` | **new** | Dataset facts. A list of `{value, label}` pairs. | Row of mono figures (value = Data role, label = Label role) |
| `page_header_right` | keep | Optional subject-identity block (e.g. player league + Town Hall chip). | Right-aligned on the identity row |
| `page_primary_control` | **new** | The single primary "what am I looking at" selector for the page. | First item in the controls bar, visually distinct, divider after it |
| `page_controls` | keep | The **secondary** control cluster only: search, filter dropdowns, view toggles, action/nav buttons. | Grouped cluster after the primary control |

**Meta slot shape.** `page_header_meta` is a Jinja list of dicts so the partial
can render figures uniformly:

```jinja
{% set page_header_meta = [
    {'value': total_wars,            'label': 'Wars'},
    {'value': first_war_date,        'label': 'Since'},
    {'value': 'All-time',            'label': 'Scope'},
] %}
```

The partial loops the list; the number of facts is page-driven (typically 2–3).
`value` may be a pre-formatted string (dates, league names) — formatting stays in
the template, as it does today.

**Primary vs. secondary control split.** The partial renders
`page_primary_control` first with a trailing divider, then `page_controls`.
Both are still HTML fragments set with `{% set %}...{% endset %}` — the split is
by slot, not by a new component vocabulary. This keeps migration mechanical:
move the page's main selector out of `page_controls` into
`page_primary_control`; everything else stays in `page_controls`.

---

## 4. Layout arrangement (chosen: stacked bands)

```
▍ BATTLE HISTORY                              [ right chip ]
  All-time attack performance
  ───────────────────────────────────────────
  26          12 JAN          MASTER II
  WARS        SINCE           LEAGUE
  ┌─────────────────────────────────────────────────────┐
  │ [ WEEK ▾ ]  │  search   zone▾   Show left   Analysis │
  └─────────────────────────────────────────────────────┘
     primary       secondary cluster
```

- Everything reads top-to-bottom, left-aligned.
- The optional `page_header_right` chip floats to the top-right of the identity
  row (the only zone that shares a horizontal line with the title).
- The meta strip is its own band under the desc, scaling to any number of
  facts without competing with the title.
- The controls bar is one band: primary control, a divider, then the secondary
  cluster.

Rejected: a "split top row" that right-aligns the meta beside the title — it
cramps at 3+ facts and collides with the right chip.

---

## 5. Sticky / scroll behavior

**Desktop (> 640px):** the title, desc, and meta strip **scroll away**
normally. Only the controls bar **detaches and pins** under the nav as a slim
sticky toolbar, so the primary selector and filters stay reachable deep in a
long table (`ranked_weeks`, `battle_history`) without scrolling to the top.

This replaces the current two-separately-sticky-bars arrangement (title bar +
controls bar both pinned) with one sticky element — the controls — and only
when a page has controls. A page with no controls has nothing sticky.

**Mobile (≤ 640px):** nothing is sticky. The whole header scrolls away,
preserving the existing fix that stopped the header eating ~46% of the phone
viewport. The controls do not pin on mobile.

---

## 6. Mobile / responsive pass (real, not just reflow)

- **Title** shrinks per the existing breakpoints (already handled).
- **Meta strip** stays as mono figures on mobile — it does **not** revert to a
  prose sentence. Figures sit in a tight wrapping row; if they exceed one line
  they wrap to two, never horizontal-scroll.
- **Controls** — the primary control goes full-width; the secondary cluster
  wraps beneath it. Nothing pins.
- No zone introduces horizontal overflow at 390px.

---

## 7. Out of scope structurally / removed

- **The 4px glowing accent stripe** (`.page-header h1::before`) — removed. It
  violates `DESIGN.md`'s ban on >1px colored accent stripes. How the title
  signals "page title" without it is a visual decision for `impeccable`, bound
  by the same ban.
- **The radial-glow wash** (`.page-header::before`) — removed as decorative
  noise. Any at-rest atmosphere is `impeccable`'s call within `DESIGN.md`.
- **Emoji in titles** — removed (`equipment.html`'s `🛡️`). Whether an icon
  replaces it (stroke SVG per `DESIGN.md`'s icon language) or nothing does is
  `impeccable`'s call.

---

## 8. Backend / route changes

**None.** Every fact the meta strip needs is already a template variable each
page passes today (it currently lives inside the prose `page_header_desc`
string): `war_stats` has `total_wars` / `first_war_date`; `cwl_stats` has
`total_seasons` / `first_season` / `latest_league`; `clan_overview` has the
member count and `period`; etc. The redesign only re-slots existing data. No
Python route handler changes.

---

## 9. Per-page migration

Title is unchanged on every page unless noted. Work per page:

**Split a primary control out of `page_controls` → `page_primary_control`:**
- `ranked/ranked_weeks.html` — Week dropdown → primary; search / rank filter /
  toggles / "Week Analysis" / "Reminder" stay secondary.
- `battles/battle_history.html` — week selector → primary.
- `player/clan_overview.html` — period selector → primary.
- `raid/raid_weekend.html` — its main selector → primary.
- `cwl/cwl.html` / `cwl/cwl_stats.html` — season/round selector → primary (if present).
- `player/player_profile.html` — Period toggle → primary.

**Move data-facts from `page_header_desc` → `page_header_meta`:**
- `war/war_stats.html` — wars recorded, since-date, scope.
- `cwl/cwl_stats.html` — seasons, since-season, current league (incl. the empty
  "No CWL data recorded yet" state → keep as desc, no meta).
- `player/clan_overview.html` — member count, period.
- `battles/battle_history.html` — week label, "Attacks only" scope.
- `admin/admin_members.html` — active-member count (+ keep the prose remainder
  as desc).
- Others keep a plain `page_header_desc` unchanged (`profile`, `admin_users`,
  `admin_hub`, `raid_stats`, `ranked_stats`, `ranked_analysis`, `compare`,
  `war/clanwar`, `battle_stats`, `equipment`, `ranked_weeks`).

**Emoji removal:**
- `tools/equipment.html` — drop `🛡️` from the title.

**Subject-identity special case:**
- `player/player_profile.html` is the one page whose header describes a
  *subject* (a player), not a dataset. Its facts — tag, In/Left Clan status,
  join date — are identity, not a dataset summary, so the "no badges / no facts
  in desc" rule does not force them into plain prose. Carry them as the meta
  strip (`{value, label}` figures, with In/Left Clan as a status figure) or a
  dedicated identity treatment alongside the existing right-side league/TH chip
  — which of those is an Open question for impeccable (§10.5). The rule's intent
  is to stop *dataset* pages cramming counts into a sentence, which this page
  isn't doing.

**Empty / idle states:** where a page's meta facts don't exist yet (e.g. no CWL
data), fall back to the plain desc line already written for that case — never a
dead placeholder figure.

---

## 10. Open questions for impeccable

These are look decisions, deliberately unresolved here:

1. How the title reads as the page title **without** the banned stripe/glow —
   weight, size, the accent-segment treatment, any left-edge signal that isn't a
   >1px colored stripe.
2. Meta-figure styling — do the figures use the `DESIGN.md` stat-cell / compact
   vocabulary, dividers between them, label placement above/below the value.
3. The visual distinction between `page_primary_control` and the secondary
   cluster — the divider, relative weight/size, whether the primary reads as a
   different element class or the same pill emphasized.
4. The detached sticky controls toolbar — its background, border, and whether it
   uses blur (note: `DESIGN.md` sanctions blur only for the nav, so likely a
   solid `--bg`).
5. Whether `page_header_right` (identity chip) and `page_header_meta` (dataset
   figures) should share a visual family, since both are "at-a-glance facts
   about the subject."
6. Whether `equipment`'s dropped emoji is replaced by a stroke-SVG icon or
   nothing.

---

## 11. Validation (before sign-off)

Playwright screenshots at **390×844**, **768×1024**, **1200×800** of at least:
- a controls-heavy page (`ranked_weeks`) — primary/secondary split, detached
  sticky toolbar on scroll (desktop), nothing sticky on mobile.
- a meta-strip page (`war_stats` or `cwl_stats`) — mono figures render, wrap
  cleanly on mobile.
- a bare page (`raid_stats` or `admin_hub`) — title-only, no empty zones.
- the right-chip page (`player_profile`) — chip + primary control coexist.

Check: mobile meta stays figures (not prose), no horizontal overflow at 390px,
no truncated control labels, empty CWL state falls back to plain desc.
Run `/impeccable critique` on the built header. Show all screenshots + critique
summary at the final gate.
