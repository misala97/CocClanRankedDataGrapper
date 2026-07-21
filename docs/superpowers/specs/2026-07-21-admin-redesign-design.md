# Admin Surface Redesign — Structure Spec

**Date:** 2026-07-21
**Page(s):** the entire admin surface — currently `/admin` (hub), `/admin/users`, `/admin/members`, `/debug`
**Type:** rethink / re-architecture (not a reskin). All existing functionality is preserved; nothing is dropped.
**Theme:** established "Night Ops Scope" system (PRODUCT.md / DESIGN.md) — **extended, not re-litigated**. This spec is a *structure contract*: sections, hierarchy, data mapping, behavior, responsive arrangement. No visual vocabulary — colour/type/spacing/signature belong to impeccable (see Open Questions).

---

## 1. Problem

The admin surface is a junk drawer. Eight unrelated capabilities are spread across three pages plus an unprotected debug route:

- `/admin` is a stack of **6 equal collapsible accordions** (Task Uptime Monitor, Member Administration, War Roster Recommendation, CWL Bonus, Ranked×Raid Skill Correlation, New Member Check) with no hierarchy — you hunt-and-expand.
- `/admin/users` and `/admin/members` are **orphans** — reachable only by direct URL, never linked in nav.
- `/admin/members` is a **strict subset duplicate** of the hub's inline Member Administration section (same group-chat + comment editing, minus war-pref).
- `/debug` has **no `@require_super_admin`** — anyone with the URL sees all player data and battle logs.

This directly violates PRODUCT.md's principle *"one command center, not stitched-together pages."*

## 2. Target shape

A dashboard **Overview** plus four focused sub-pages, tied together by a new admin sub-nav (tabs). Orphans are folded in; the duplicate is eliminated; debug is locked down and linked.

| Destination | Route | Holds |
|---|---|---|
| **Overview** | `/admin` | Command deck: system-pulse line, attention tiles, tool jump-cards, quick task-run. |
| **Monitor** | `/admin/monitor` (new) | Task Uptime Monitor (health cards, timeline, per-task charts, gaps, Run-Now) + link to Debug. |
| **Roster** | `/admin/roster` (new) | War Roster Recommendation + CWL Bonus + Skill Correlation. |
| **Members** | `/admin/members` (upgraded) | New Member Check evaluator + the canonical per-player editor (group chat · war-pref · comment). |
| **Users** | `/admin/users` (redesigned) | Account access control (approve / super / perms / link-player / delete). |

Grouping rationale: by **who uses it and when** — Overview for the daily glance, Monitor for "is the machine alive," Roster for periodic war/CWL calls, Members for ongoing people-data, Users for access.

## 3. Backend / route changes (all approved 2026-07-21)

1. **Split the hub route.**
   - `admin_hub` (`/admin`) is repurposed as **Overview**; it drops the timeline/`by_function`/`function_stats` computation and instead assembles the alert data in §5.1.
   - New `/admin/monitor` route receives the moved uptime computation **verbatim** (`by_function`, `function_stats`, `selected_days`).
   - New `/admin/roster` route is a thin shell (renders the tool controls; the tools themselves are existing AJAX endpoints).
2. **Fold orphans in.** `/admin/members` is upgraded to the fuller editor (adds the war-pref column that today lives only in the hub's inline copy); the old `admin_members.html` content is replaced by this single canonical page. `/admin/users` logic is unchanged, only redesigned and linked.
3. **Two new Overview data pieces** (§5.1): `pending_approvals` count and a `cwl_bonus_available` helper extracted from `admin_cwl_bonus_suggest`.
4. **New shared partial** `templates/admin/_admin_tabs.html` — the 5-tab sub-nav, active-by-path, admin-scoped (does not touch global `_nav`).
5. **Security fix** — add `@require_super_admin` to `/debug`; keep it a page, link it from Monitor (not inlined).

Unchanged AJAX endpoints (called from the new pages, no edits): `/admin/trigger-task`, `/admin/war-roster`, `/admin/cwl-bonus[/suggest|/apply|/toggle]`, `/admin/skill-correlation`, `/admin/evaluate-new-members`, `/admin/members/<tag>/update`, and the `/admin/users/<id>/*` POST actions.

## 4. Shared admin sub-nav (`_admin_tabs.html`)

- Five links: Overview → `/admin`, Monitor → `/admin/monitor`, Roster → `/admin/roster`, Members → `/admin/members`, Users → `/admin/users`.
- Active state derived from `request.path` (exact for `/admin`, `startswith` for the rest). Active-state visual **must** obey DESIGN.md: tint-only, never a side-stripe.
- Count badges on tabs that carry pending work: **Members** shows `newbie_check_count` (mirrors the global nav badge), **Users** shows `pending_approvals`. Badge hidden at zero.
- Included on every admin page, immediately below the page header. Exact placement/stickiness is an Open Question.

## 5. Per-page structure

### 5.1 Overview (`/admin`) — layout A, "grouped bands"

Four stacked bands:

1. **Needs Attention** — up to three action tiles, each a count + one-line label + link:
   - *N new members to check* → Members. Data: `newbie_check_count` (context processor, free).
   - *N pending approval* → Users. Data: **new** `pending_approvals = AppUser.query.filter_by(is_approved=False).count()`.
   - *N CWL bonuses available* → Roster. Data: **new** `cwl_bonus_available` — a helper extracted from `admin_cwl_bonus_suggest` returning `{count, season_label}` for the active season, or `None` when no active CWL season.
   - The whole band **collapses to an "all clear" hairline** when all three counts are 0. A tile with a 0 count is individually omitted (not shown as "0").
2. **System Pulse** — one compact line: `nav_health.down`/6 operational + freshest-sync age (`nav_health.age_str`); names any down/delayed task from `nav_task_status`. Links to Monitor. All data free from the context processor.
3. **Jump To** — four entry cards (Monitor / Roster / Members / Users), each carrying a live status/count: Monitor = `X/6 up`; Roster = static label ("war · cwl · skill"); Members = active-member count (**new** `Player.query.filter_by(in_clan=True).count()`); Users = active + pending counts.
4. **Quick Run** — the six triggerable background tasks as buttons that POST to `/admin/trigger-task` (existing behavior, existing per-button run/busy/done states).

Empty/idle: if nothing is pending, band 1 collapses to the "all clear" hairline; bands 2–4 always render (they are navigational/operational, not alerts).

### 5.2 Monitor (`/admin/monitor`)

De-accordioned; the current uptime section rendered as a full page.
- **Header controls:** the period selector (24h / 7d / 14d / 30d) moves into the page-header controls slot; reloads via `?days=`.
- **Task status grid:** the 6 task health cards (icon · status badge · last-run · run stats · gap warning · **Run Now** button → `/admin/trigger-task`). Whether these stay a uniform 6-grid or adopt two-tier hierarchy is an Open Question (they are genuinely equivalent monitored tasks).
- **Activity timeline:** the scatter chart (`by_function`, existing Chart.js).
- **Per-task detail:** duration sparkline cards + detected-gap list per task.
- **Debug link:** a link/entry to `/debug` (now protected).
- **Empty state:** keep the existing "no uptime data for the last N days" panel.

Data: `by_function`, `function_stats`, `selected_days` (moved from the old hub route unchanged).

### 5.3 Roster (`/admin/roster`)

Three tool sections **stacked and visible** (not accordions). Each is a control header + an on-demand result area (all compute on button press, so at rest the page is short):
1. **War Roster Recommendation** — Auto/Manual mode, war-size + fill-ups inputs, Generate → roster + bench tables. AJAX `/admin/war-roster`.
2. **CWL Bonus** — Suggest / Apply / Toggle over the month grid. AJAX `/admin/cwl-bonus[/suggest|/apply|/toggle]`.
3. **Skill Correlation** — Run Analysis → scatter + per-player table + Pearson r. AJAX `/admin/skill-correlation`.

Order = most→least operational (roster and bonus are decision tools; correlation is analysis). Shell route needs only `current_month` (for the bonus tool's default).

### 5.4 Members (`/admin/members`)

Two sections:
1. **New Member Check** (top — it's the alert-driven, time-sensitive one) — Run Evaluation → verdict cards for recent joiners. AJAX `/admin/evaluate-new-members`.
2. **Member editor** — the canonical per-player table: identity, group-chat toggle, war-pref (in-game API value **read-only** + custom override editable), admin comment. Search lives in the page-header controls slot. Edits → `/admin/members/<tag>/update` (existing; already accepts `in_group_chat`, `war_preference_custom`, `admin_comment`).

This section **absorbs** the hub's old inline Member Administration (the fuller version with war-pref); the previous bare `/admin/members` duplicate is retired.

Data: `players` (in-clan, already provided).

### 5.5 Users (`/admin/users`)

Redesigned, same content: **Pending Approval** table (approve / delete) + **Active Users** table (super-admin toggle, permission checkboxes, link-player select, revoke / delete). Data: `users`, `players` (unchanged).

## 6. Responsive strategy

- **Dense editable tables** (Members editor, Users tables, Roster/bench result tables) drop to the established **divided roster-row pattern** on phone width — one entity per row, identity line on top, the inline controls (toggles / inputs / selects / verdict) wrapping below. **Never** a stack of per-entity cards (DESIGN.md standing ban). Confirmed with user 2026-07-21.
- **Overview bands** reflow: attention tiles and jump cards go from a row to a single column; the pulse line and quick-run row wrap.
- **Admin tabs** collapse to a horizontally-scrollable strip or a compact control on narrow widths (impeccable's call).
- **Monitor charts** keep their existing responsive Chart.js config.
- Three validation viewports: **390×844**, **768×1024**, **1200×800**.

## 7. Reuse (don't reinvent)

- **Page header:** every admin page uses `_page_header.html`'s existing slots (title + accent span, desc, optional meta figures, `page_controls` for period selector / search). No new header slot is needed — the admin tabs are a *separate* partial, not a header slot.
- **Divided roster-row** mobile table pattern — established (battles/raid/clan). Reuse; the only new wrinkle is that admin rows carry editable controls, which wrap inline.
- **Verdict/judgment badge** vocabulary and **status badge** styles — established; reuse for task health, new-member verdicts, war-pref states.
- **Two-tier hierarchy** (featured + compact-row) — apply wherever a section would otherwise become a flat repeated grid.

## 8. Build sequence

The spec covers the whole surface, but implementation runs page-by-page as mini-cycles:
1. **Overview first** — it establishes the `_admin_tabs` partial and the command-deck language the other pages inherit. Includes the backend split (Overview route + the two new data pieces) and the tabs partial.
2. **Monitor** — move the uptime computation to its route; de-accordion.
3. **Roster** — shell route + stack the three existing tools.
4. **Members** — upgrade route/page, absorb the hub's war-pref editing, retire the duplicate.
5. **Users** — redesign in place.
6. `/debug` lockdown + Monitor link (can ride along with Monitor).

Each page hands off to `/impeccable craft` (Overview) / `/impeccable` extension passes (later pages) for visual execution; motion via a final `/impeccable animate` pass.

## 9. Open questions for impeccable

- **Overview visual treatment:** how the four bands read as a command deck — do the attention tiles / jump cards use the category hues, how the "all clear" hairline looks, how the pulse line renders. The whole look of the invented page.
- **Monitor task grid:** should the 6 equivalent task-health cards stay a uniform grid, or is a monitoring grid an acceptable exception to the "6+ identical cards" ban (analogous to the 4 featured live-mode tiles)? impeccable decides, respecting the ban's intent.
- **Admin tabs strip:** exact placement (directly under global nav vs. under the page-header headings), sticky vs. static, and the active-state visual (tint-only, no side-stripe).
- **Motion:** attention-tile entrance, count-ups on the tiles/pulse, task-run button feedback — defer to `/impeccable animate`.
- **Chart theming:** align the Monitor charts to design tokens (resolve to computed `rgb()` — Chart.js can't read CSS vars).
