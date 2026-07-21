# Admin Users Rework — Structure Spec

**Date:** 2026-07-21
**Page:** `/admin/users`
**Type:** rework / rethink (not a reskin). One route change (§3); no endpoint logic changes.
**Theme:** established "Night Ops Scope" system (PRODUCT.md / DESIGN.md), extended per the
Overview / Monitor / Roster / Insights / Members precedent — **not re-litigated**. Structure
contract: sections, hierarchy, data mapping, behavior, responsive arrangement. Visual vocabulary
belongs to impeccable — see §9.

Supersedes §5.5 of `2026-07-21-admin-redesign-design.md`. Last of the six admin sub-pages.

---

## 1. Problem

`/admin/users` is a two-table dump: "Pending Approval" (username / registered / approve+delete)
over "Active Users" (username / registered / super toggle / permission checkboxes / link select /
revoke+delete). Every column is a raw column of the `AppUser` record; nothing on the page is
computed, judged, or ranked. It carries the banned patterns — emoji as functional icons
(⭐ ☆ ✓ ✕), off-system `DM Sans` / `Rajdhani` faces, full-page form POST per edit — and, more
importantly, it hides real state:

1. **Silent-unlink fault.** The route passes `players = Player.query.filter_by(in_clan=True)`.
   An account linked to a player who has since left the clan matches no `<option>`, so the select
   renders "— None —"; submitting that row wipes a link the admin never intended to touch. The
   `AppUser.linked_player` relationship already holds the truth and is unused.
2. **Effective ≠ stored permission.** `_is_super_admin()` short-circuits both
   `_can_create_reminder_ranked()` and `_can_edit_clan_war()`
   (`features/auth/routes.py:38-48`), so a super admin holds every grant regardless of the
   checkboxes. The page hides the checkboxes for super admins entirely, so their stored values are
   invisible — and reappear, unchanged and unexplained, the moment super admin is removed.
3. **The link matters more than the page implies.** `linked_player_tag` drives "me" highlighting
   on eight pages and gates the ranked-reminder routes (`features/ranked/routes.py:594,618,656`).
   An approved account with no link gets a quietly degraded site and nothing surfaces it.
4. **Duplicate links are undetectable.** Two accounts may hold the same `linked_player_tag`.
5. **Self-lockout is unguarded.** A super admin can strip their own super-admin flag with one
   click and lose the admin surface.
6. **The env-credential admin is invisible.** `ADMIN_USER` / `ADMIN_PASS` authenticates a session
   with full super-admin power (`features/auth/routes.py:23-30`) and appears in no list, so the
   roster silently implies a completeness it does not have.

## 2. Target shape

Two stacked bands, verdict-led / exceptions-first (the sibling-page language):

1. **Needs Attention** — leads. Every account state that requires a decision or a repair, in one
   severity-ordered list, each entry carrying its own action. Collapses to an all-clear hairline
   when empty.
2. **Accounts** — the standing access registry: one row per approved account, read-only and
   scannable, with a per-account disclosure holding the editor.

Rationale: the page's two jobs are *dispatch* (something is wrong or waiting) and *registry*
(who holds what power). The old split — pending vs. approved — only modelled the first bit of
`is_approved` and left every other exception buried in a column. Pending and revoked accounts
appear **only** in the attention band, never duplicated into the roster: they have no access to
describe. Confirmed with user 2026-07-21 (arrangement 1 of three wireframed).

## 3. Backend / route change

**One, approved 2026-07-21:** `admin_users()` additionally passes the players that accounts are
currently linked to but who are no longer in the clan, so the link control can render a departed
link truthfully instead of silently unlinking it (§1.1).

```
users            = AppUser.query.order_by(AppUser.is_approved, AppUser.created_at.desc()).all()
players          = Player.query.filter_by(in_clan=True).order_by(Player.name).all()
departed_linked  = the Players whose tag is linked by some user but is not in `players`
```

Passed as a **separate** list, not merged, so the control can group them distinctly and the
template can tell "linked to a current member" from "linked to someone who left".

**Explicitly considered and declined** (per the backend gate — neither silently added nor
silently ruled out):

- `AppUser.last_login_at` — would unlock dormancy verdicts ("never logged in since registering",
  "dormant 90d"). Declined by user; the page therefore makes **no** dormancy claims.
- `AppUser.approved_at` — would let the queue distinguish a fresh registration from a revoked
  account. Declined by user; §5.1 states the resulting limitation on the page rather than
  guessing from `created_at`.

**Unchanged endpoints** the page uses (all existing, all form-encoded POST + redirect):
`/admin/users/<id>/approve`, `/reject`, `/delete`, `/toggle-super`, `/perms`, `/link-player`.

## 4. Data brief

**Route (server):**

- `users` — all `AppUser[]`, `is_approved` ascending then `created_at` descending. Per account:
  `id, username, created_at, is_approved, is_super_admin, perm_create_reminder_ranked,
  perm_clan_war_edits, linked_player_tag`, plus the eager-joined `linked_player` relationship
  (`name, tag, current_th, in_clan`).
- `players` — in-clan `Player[]` by name (`name, tag, current_th`).
- `departed_linked` — `Player[]` linked by some account but no longer in clan (§3).

**Derived on the page, not stored** (this is the material the old page never computed):

| Derived value | From |
|---|---|
| Effective access tier | `is_approved`, `is_super_admin`, the two `perm_*` flags, read the way `auth/routes.py` reads them |
| Grants held | super admin ⇒ both, implied; otherwise the two `perm_*` flags |
| Stored-but-overridden grants | `perm_*` values on an account where `is_super_admin` is true |
| Link state | `linked_player_tag` + whether that player is in `players`, in `departed_linked`, or absent |
| Duplicate link | two accounts sharing one `linked_player_tag` |
| Is this me | `current_user.id == u.id` (self-demotion guard) |

No other data is needed and none is invented.

## 5. Per-section structure

**Header** — `_page_header.html` existing slots only, no new slot: title + accent span, one
orientation line, meta figures for total accounts / super admins / awaiting decision, and a
roster **search** (username or linked player name) in the `page_controls` slot.
`_admin_tabs.html` below, unchanged — its Users tab already badges `pending_approvals`.

### 5.1 Needs Attention (leads)

One severity-ordered list. Each entry names the account, states the condition in plain words, and
carries the action that resolves it:

| Order | Condition | Entry states | Action |
|---|---|---|---|
| 1 | `is_approved == false` | username, registered date | Approve · Delete |
| 2 | linked tag is in `departed_linked` | username → player name, "left the clan" | Open editor (relink or clear) |
| 3 | two or more accounts share one `linked_player_tag` | **one** entry per shared tag, naming every account on it → the shared player | Open editor for any of them |
| 4 | approved, `linked_player_tag` is null | username, what the missing link costs | Open editor (link) |

Tiers 1–3 are faults or decisions; tier 4 is a standing note and reads as the quieter tier.

**Stated limitation, on the page:** without `approved_at` (§3), a revoked account is
indistinguishable from a new registration — both are simply `is_approved == false`. Tier 1 says
"awaiting decision", not "new registration", and the section does not claim otherwise.

**Empty / all-clear:** when no entries qualify, the band collapses to an all-clear hairline (the
Overview pattern) — not a dead empty box.

### 5.2 Accounts (the registry)

One row per **approved** account. The row is read-only and scannable; nothing in it can be
changed by a stray click:

- *Identity:* username, registered date.
- *Effective access tier:* `Super admin` / `Standard + N grants` / `Standard` — computed as
  `auth/routes.py` computes it, so the row states what the account **can actually do**.
- *Grants:* the two grants shown as held / not held. For a super admin, both read as held **by
  virtue of super admin**, with the account's *stored* checkbox values still visible and clearly
  subordinate — this is the fix for §1.2 and must survive into the built page.
- *Linked player:* player name + town hall, or *left the clan*, or *not linked*.
- *Disclosure* (one per account, `aria-expanded`, keyboard/touch-native) opens the editor.

**Editor (inside the disclosure):**

- **Super admin** toggle. Granting confirms; removing confirms. **Removing it from your own
  account is blocked**, with the reason stated — the §1.5 guard.
- **Grants** — the two permission checkboxes. When the account is a super admin they are shown
  but non-effective, labelled as overridden rather than hidden.
- **Linked player** — a select over `players`, with `departed_linked` entries presented as a
  distinct group so a departed link renders as itself, plus a clear-link option.
- **Revoke access** — sets `is_approved = false`; the row leaves the registry and reappears in
  the attention band. The control says so.
- **Delete account** — destructive, confirmed, states that it is permanent.

**Footnote under the registry:** the `ADMIN_USER` env-credential login is a full super admin that
exists outside this table (§1.6). One quiet line, so the count is never read as complete.

### 5.3 Behavior

- All six actions submit to their **existing** endpoints via `fetch` (form-encoded), then update
  the row, the attention band, and the header figures in place, with an in-surface toast — the
  Roster/Members save behavior. No page reload, no lost scroll, no closed disclosure.
- The underlying `<form method="POST" action=…>` markup is kept intact as the no-JS fallback;
  the endpoints already redirect back to the page.
- Single click + keyboard throughout. No `dblclick`. Toggles carry `aria-pressed`; the disclosure
  carries `aria-expanded`.
- Destructive actions (delete, revoke, super-admin change) confirm before firing.

## 6. Responsive strategy

- The registry table and the attention entries both drop to the established **divided roster-row
  pattern** on phone width — identity line on top, state wrapping below, the disclosure holding
  the editor. **Never** per-account cards (DESIGN.md standing ban).
- The editor stays inside the row's disclosure at every width; grant checkboxes, link select and
  the destructive controls wrap within it.
- Search is full-width in the header toolbar on mobile (existing toolbar behavior).
- Validation viewports: **390×844**, **768×1024**, **1200×800**.

## 7. What must not be lost

Everything the old page could express stays expressible: approve, revoke, delete, toggle super
admin, set both permissions, link/unlink a player, and see each account's registration date and
pending/approved state. The rework adds computed state (effective tier, link faults, duplicates,
overridden grants); it removes no capability and no field.

## 8. Reuse (don't reinvent)

- **Page header** — existing slots (title + accent, desc, meta figures, `page_controls` search).
  No new slot needed.
- **`_admin_tabs.html`** — unchanged; the Users tab's `pending_approvals` badge already tracks
  tier 1 of the attention band and must stay in sync after a fetch-driven approve.
- **All-clear hairline** collapse — Overview pattern.
- **Divided roster-row** mobile pattern, **`aria-expanded` disclosure**, **`aria-pressed` toggle**,
  **in-surface toast** — established on Roster and Members this cycle.
- **Judgment / verdict badge** vocabulary — reuse for the attention tiers and the access tier;
  map to the existing semantic tiers rather than inventing a scale.
- **Scope-console command-deck aesthetic** from the sibling admin pages — extend, don't restyle.

## 8a. Deltas found during build (not in the original contract)

Three things the implementation adds, each because building or critiquing it surfaced a
state the spec hadn't accounted for:

- **Pending accounts can already carry `is_super_admin`.** Real data has one. The flag does
  nothing while `is_approved` is false and everything the moment it flips, so the tier-1
  entry warns before the click. (`supers` is counted among **approved** accounts only — an
  unapproved super admin holds no power and must not inflate the figure.)
- **A fifth link state: tag stored, `Player` row gone entirely.** Neither "linked" nor
  "departed" — `linked_player` is null while `linked_player_tag` is set, so the account would
  have read as "Not linked" and escaped the unlinked tier too. Now its own fault entry.
- **The self-lockout guard is enforced server-side, not only in the template.** §1.5 named
  self-demotion; revoking or deleting your own account is the same hazard and strictly worse.
  `admin_user_reject`, `admin_user_delete` and `admin_user_toggle_super` each `abort(400)` on
  self, so a stale page or a direct POST can't route around the disabled control.

## 9. Open questions for impeccable

- **Access tier badge:** how `Super admin` / `Standard + N grants` / `Standard` differentiate at a
  glance without a side-stripe, and how much weight the tier carries against the username.
- **Overridden grants:** how a super admin's stored-but-inert checkbox values read as present yet
  subordinate — the single most delicate piece of hierarchy on the page.
- **Attention entry treatment:** how a decision (approve) and a fault (broken link) sit in one
  list without the quieter tier-4 notes drowning the tier-1 decisions.
- **Link state:** how *linked* / *left the clan* / *not linked* differentiate, and how the
  departed group appears inside the select.
- **Editor panel inside the disclosure:** how six controls of three different risk levels
  (routine / confirm / destructive) sit together, and how that holds at 390px.
- **Env-admin footnote:** treatment of a caveat that is neither a row nor an error.
- **All-clear collapse** for the attention band.
- **Motion:** attention-entry exit on resolve, row update after save, disclosure open/close, toast
  — defer to a final `/impeccable animate` pass.
