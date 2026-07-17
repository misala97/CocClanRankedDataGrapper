# Sitewide nav redesign — design spec

## Scope

Structure and behavior only, for `coc_stats/templates/_nav.html`, included on
every page via `inject_auth()` (`coc_stats/app.py:131-142`). Visual treatment
(palette, type, component styling) is out of scope — hands off to
`impeccable craft` after this spec is signed off. `_nav.html` already carries
this session's OKLCH token migration and motion system; this cycle changes
its *structure*, not its established look.

## Data source

Everything below comes from `inject_auth()` (`app.py:131-142`) plus
`request.path` for active-link state. No template variable is treated as a
given — each is named here because the context processor actually produces
it, sitewide, on every page.

- **Identity**: `clan_badge_url` (crest image, falls back to inline SVG)
- **Auth state**: `current_user` (`.username`, `.linked_player`), `is_env_admin`
- **Permissions**: `is_super_admin` (gates the Admin link), `newbie_check_count` (Admin badge count)
- **Sync health**: `nav_task_status` — list of 6 `{label, status, time_str}` for Ranked/Battles/Raids/War/CWL/Members, `status` ∈ `good`/`warn`/`bad`/`none`, computed by `_nav_task_status()` (`app.py:92-116`)
- **Route table** (fixed, not data-driven): Home `/`, Ranked `/ranked` (+ `/ranked/stats`), Battles `/battles` (+ `/battles/stats`), Raids `/raid` (+ `/raid/stats`), War `/war` (+ `/war/stats`), CWL `/cwl` (+ `/cwl/stats`), Tools `/tools/equipment`, Clan `/clan`, Admin `/admin` (conditional)

## Structure

Three real IA directions were mocked up and shown to the user (flat comparison,
not this page's final look — CDS neutral placeholder styling, structure only).
**Chosen: two-row, status-on-demand.**

```
Row 1 (always):  [crest] Home  Ranked  Battles  Raids  War  CWL  Tools  Clan  [Admin] ...... [user chip ▾ / Login]
Row 2 (on demand): collapses to a ~4px hairline when nav_task_status has no warn/bad entries.
                   Expands to a slim strip listing only the non-good entries when any exist,
                   e.g. "⚠ War synced 74m ago" — good entries are omitted, not listed as "OK".
```

### Why this direction over the other two mocked options
- **Grouped Modes dropdown** (single `Modes▾` mega-menu) was rejected — it hides
  5 of 8 destinations behind a hover, adding a click for the primary nav action.
- **Flat + inline status pips** (dot on every link label) was rejected in favor
  of the two-row split — pips on healthy links are visual noise 95% of the time;
  Option 3's collapse-when-healthy behavior gets the same "don't clutter for no
  reason" outcome without permanently modifying every link's shape.

### Dropdowns are eliminated entirely
All 8 top-level items become **flat links**, including Ranked/Battles/Raids/War/CWL
(previously hover-dropdowns with a "Current"/"Stats" pair) and Tools (previously
a redundant single-item dropdown). This is a structural fix for the DESIGN.md
Do's-and-Don'ts flag *"the nav's mode dropdowns are hover-only, no keyboard
equivalent"* — removing the dropdown removes the violation, rather than
patching keyboard support onto a pattern being retired.

### Long Term Stats moves in-page
Each mode link now points at its "current" route only. `/ranked/stats`,
`/battles/stats`, `/raid/stats`, `/war/stats`, `/cwl/stats` remain reachable —
via a small Current/Stats toggle living on that mode's own page header, not
in the nav. Routes are unchanged; only the nav's entry point into them
changes. (Implementing the toggle itself is out of scope for this cycle —
each mode page is its own future redesign cycle.)

### Status strip behavior
- Expand condition: any of the 6 `nav_task_status` entries is `warn` or `bad`.
  `none` (no data yet) does **not** trigger expansion — it isn't a fault.
- When expanded, list only the non-good entries (label + time_str + severity
  color), not all 6 — a leader glancing at the bar sees exactly what needs
  attention, nothing else.
- Full 6-of-6 status detail (including all-good) is out of scope for the nav
  itself in this direction — DESIGN.md already documents a footer
  "operational" status dot as the sitewide full-health indicator; the nav
  strip's job is narrower: interrupt only when something needs a look.
- Each expanded entry stays keyboard-focusable with the existing spoken
  `aria-label` pattern ("War sync: Error, 74m ago") — carried over from the
  current implementation, not reinvented.

### Admin, user chip, login
Unchanged in structure — Admin stays a flat link with its existing red count
badge (super-admin only); the user chip/dropdown (linked-profile, sign out)
and the logged-out Login link are not part of the flagged issues and aren't
being restructured this cycle.

## Mobile (re-examined, not just reflow)

Burger panel, now genuinely simpler than today's build because there's no
nesting left to collapse:
- Single flat list: Home, Ranked, Battles, Raids, War, CWL, Tools, Clan, Admin
  — no expand/collapse per item, since Stats sub-links moved in-page.
- Status section: same on-demand rule as desktop — omitted entirely when all
  6 are good, shown as a short list of only the non-good entries when any
  exist. No permanent "System Status" block for the common case.
- **Fixes the DESIGN.md-flagged bug**: active-link state uses a background
  tint (matching the desktop `nl-active` treatment), not a `border-left`
  stripe — closes the one standing violation of the sitewide no-stripe rule.

## Out of scope / future opportunities (not this cycle)

- Per-mode-page Current/Stats toggle UI (needed by the "stats moves in-page"
  decision above, but belongs to that mode page's own redesign cycle).
- Footer "operational" status dot — already exists per DESIGN.md; not touched here.
- Exact mobile breakpoint (currently 900px) — flat links take less horizontal
  space than the old dropdown-caret links; final breakpoint is an
  implementation-time check, not a spec-locked number.
