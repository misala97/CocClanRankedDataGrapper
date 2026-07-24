# Admin-Editable War Combos

## Problem

`WAR_COMBOS` in `features/war/war_combos.py` is a hardcoded dict mapping pairs of
per-attack labels (e.g. `(CLEAR, CLEAR)`) to a `(score, verdict_label)` tuple. Any
combination not in the dict falls back to `(50, 'First Time Combination')` and
renders as a `?` badge (`badge-undefined`) on the war page. New combos currently
require a code edit + deploy.

Goal: let an admin (same permission as other war-page edits) name a new combo
directly from the `?` badge on `/war`, no deploy needed.

## Design

### 1. Data model (`models.py`)

```python
class WarCombo(db.Model):
    __tablename__ = 'war_combo'
    label_a       = db.Column(db.String(20), primary_key=True)
    label_b       = db.Column(db.String(20), primary_key=True)
    score         = db.Column(db.Integer, nullable=False)
    verdict_label = db.Column(db.String(60), nullable=False)
    created_at    = db.Column(db.DateTime, default=dt.datetime.utcnow)
```

Composite primary key on the sorted label pair — mirrors the existing
`tuple(sorted(k))` normalization so lookup order never matters and a pair can't
be stored twice under swapped keys.

### 2. `war_combos.py` — DB removed, stays a pure module

The hardcoded `WAR_COMBOS` dict, its sort-normalization line, and the now-stale
"Add entries here whenever you see a new 'Undefined' combination" comment block
are deleted. `get_war_verdict` changes from an implicit-global lookup to an
explicit-dict lookup:

```python
_DEFAULT_SCORE = 50
_DEFAULT_LABEL = 'First Time Combination'

def get_war_verdict(label_a, label_b, combos):
    """combos: {(label_a, label_b) sorted: (score, verdict_label)}, loaded by the caller."""
    key = tuple(sorted([label_a, label_b]))
    score, label = combos.get(key, (_DEFAULT_SCORE, _DEFAULT_LABEL))
    ...  # badge tiering unchanged
```

`war_combos.py` gains no Flask/db import — the caller always loads and passes
`combos`. `combos` defaulting to `{}` (e.g. via `combos=None` → `combos or {}`)
means every combo falls back to the default tuple, so a caller that forgets to
load it fails soft (shows `?` everywhere) rather than crashing.

### 3. Loader (`services/helpers.py`), request-cached via Flask `g`

`get_war_verdict` has only two call sites in the whole codebase
(`war/routes.py:132`, `player/routes.py:40`) — `cwl/routes.py` imports it but
never calls it (dead import, pre-existing, not touched by this change; it
only uses the unrelated `get_cwl_verdict`). But the `player/routes.py` call
site sits behind a single chokepoint, `_war_player_verdict`, itself reached
through **six nested functions** across three route handlers in **two
files** — `player_profile` and `clan_overview` in `player/routes.py`, and
`admin_war_roster` in `features/admin/routes.py` (via
`_player_war_stats` → `calculate_skill_score`).

Threading an explicit `combos` parameter through all six intermediate
functions (`_war_player_verdict`, `calculate_skill_score`,
`calculate_scores_all_periods`, `_calculate_scores_bulk`,
`_bulk_scores_cached`, `_clan_standing_all_periods`) would touch every one of
their signatures for a value none of them otherwise care about. Instead:

```python
# services/helpers.py
from flask import g
from models import WarCombo

def get_combos():
    if 'war_combos' not in g:
        g.war_combos = {(c.label_a, c.label_b): (c.score, c.verdict_label) for c in WarCombo.query.all()}
    return g.war_combos
```

Every one of the four `get_war_verdict(labels[0], labels[1])` call sites
(`war/routes.py:132`, `player/routes.py:40`, plus the two inside
`admin/routes.py`'s chain and `clan_overview`'s chain — all of which resolve
to the same `player/routes.py:40` line inside `_war_player_verdict`, so it's
really one call site reached five ways) becomes
`get_war_verdict(labels[0], labels[1], get_combos())`. `g` is per-request, so
the DB is queried once per request no matter how many times
`_war_player_verdict` loops inside it (bulk scoring iterates it once per war
per player). `war_combos.py` itself gains no Flask import — `get_war_verdict`
still just takes `combos` as a plain argument; only its Flask-bound callers
know how to fetch it.

### 4. Cache-busting

`player/routes.py` already has a 5-minute in-memory cache for clan-wide bulk
scoring, `_BULK_STANDING_CACHE` (module-level dict, key
`(period, hash(frozenset(in_clan_tags)))`, reached from `player_profile`'s
clan-standing widget via `_clan_standing_all_periods` →
`_bulk_scores_cached`). Its key has no dependency on combos, so a freshly
added `WarCombo` row would silently not show up there for up to 5 minutes.
Cheap fix: expose `clear_bulk_standing_cache()` from `player/routes.py`
(`_BULK_STANDING_CACHE.clear()`) and call it from the new combo-add endpoint
right after the DB commit, so the admin's own addition is visible everywhere
immediately, not just on the war page they added it from.

### 5. New endpoint (`war/routes.py`)

`POST /war/api/combo/add`, gated by `_can_edit_clan_war` (same permission that
already gates other war-page edits — stars/castle — not a stricter
super-admin-only check).

Body: `label_a`, `label_b`, `score` (int, 0–100), `verdict_label` (non-empty,
trimmed, ≤60 chars). Normalizes to the sorted pair and inserts. Duplicate PK
(combo already named, e.g. a double-submit race) → 409, does not overwrite.
Returns `{ok: true}` on success.

### 6. UI (`templates/war/clanwar.html`)

In `buildWarVerdictTable`, a row whose `v.badge === 'badge-undefined'` renders
the `?` as a `<span>` today regardless of viewer. Change: when the viewer can
edit (existing `can_edit_clan_war` Jinja var, exposed as a small JS const
alongside `WAR_VERDICTS`), that span becomes a `<button>` with the same visual
classes plus a pointer cursor. Non-admins see the identical static `?` span —
no change for them.

Click opens one shared `<dialog>` popover (native, matches the project's
existing a11y disclosure pattern) with two inputs — score (number, 0–100) and
verdict label (text) — and a Save button. The two attack labels come from
`v.atk_labels`, already present in the `WAR_VERDICTS` JS payload (no extra
fetch needed to know what's being named).

Submit → `fetch POST` to `/war/api/combo/add` → on success, `location.reload()`
(full reload, not a targeted DOM patch — this is a rare admin action, not a hot
path, and a reload re-derives every badge on the page correctly for free). On
failure (e.g. 409), show an inline error in the dialog and don't reload.

### 7. Migration

One Alembic revision: `create_table('war_combo', ...)` followed by
`op.bulk_insert(...)` seeding the current 12 hardcoded entries, so scoring
behavior is byte-for-byte identical the moment this deploys — nothing reverts
to "First Time Combination" that wasn't already undefined before. Follows the
existing `clan_config` migration's shape (`migrations/versions/b3e7c1a9f042_add_clan_config_table.py`).

## Explicitly out of scope

Decided during brainstorming:
- No standalone management page (list/edit/delete existing combos). If a named
  combo ever needs correcting, that's a direct DB edit — expected to be rare
  enough not to justify UI.
- No audit trail (who added a combo, from which war) — not requested.
- The CWL page's own verdict table markup is a separate copy in `cwl.html`
  (not the shared `_war_detail_unit.html` partial) and is untouched — the add
  UI only ships on `/war`, per your call. CWL pages still *benefit* from newly
  named combos via the shared `get_war_verdict`/DB lookup, they just don't get
  their own add button.

## Blast radius

- `war_combos.py`: `WAR_COMBOS` dict removed; `get_war_verdict` signature
  changes (new required `combos` param) — every call site must be updated in
  the same change, not left calling the old 2-arg signature.
- `services/helpers.py`: gains `get_combos()`.
- `war/routes.py:132` and `player/routes.py:40` (inside `_war_player_verdict`):
  each `get_war_verdict(...)` call gains `get_combos()` as a third argument.
  No other function signature in the call chain changes — `_war_player_verdict`,
  `calculate_skill_score`, `calculate_scores_all_periods`,
  `_calculate_scores_bulk`, `_bulk_scores_cached`, `_clan_standing_all_periods`,
  `player_profile`, `clan_overview`, and `admin/routes.py`'s
  `admin_war_roster`/`_player_war_stats` are all untouched.
- `player/routes.py`: gains `clear_bulk_standing_cache()`, called by the new
  endpoint after a successful insert.
- New table `war_combo`, seeded not empty.
- `cwl/routes.py`'s `get_war_verdict` import stays dead (pre-existing, unrelated
  to this change — not removed here to keep the diff focused).
- No change to `classify_attack`, `get_cwl_verdict`, or badge tiering
  thresholds.

## Verification plan

No test suite in this project (manual verification, per project convention).

1. Run the migration locally, confirm `war_combo` has exactly 12 rows matching
   the current hardcoded dict (`SELECT * FROM war_combo`).
2. Load `/war` on a war with at least one already-known combo (e.g. two
   `CLEAR` attacks) — confirm score/label/badge unchanged from before the
   change.
3. Manufacture or find a genuinely undefined combo on a real war, confirm it
   renders as a clickable `?` for an editor account and a plain `?` for a
   non-editor account.
4. As an editor, submit a score + label via the dialog, confirm the page
   reloads and that row now shows the real badge/label/score.
5. Reload `/war` again (fresh request) — confirm the named combo persists
   (came from DB, not just client state).
6. Visit a player profile containing that same label pair (including the
   clan-standing widget, which goes through `_BULK_STANDING_CACHE`), confirm
   it also shows the new verdict immediately, not `?` and not a stale cached
   value — proves both the shared `get_combos()` lookup and the cache-bust
   work.
7. Try submitting the same combo twice (double-click or resubmit) — confirm
   the second attempt fails cleanly (409, inline error) rather than silently
   overwriting or crashing.

## Rollout

Code + migration on `dev_coc`. This app deploys via git (not manual server
commands) — commit and push once verified; run the migration as part of the
normal deploy flow.
