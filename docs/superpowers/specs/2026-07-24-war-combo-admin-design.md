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

### 3. Loader helper (`services/helpers.py`)

```python
def load_war_combos():
    return {(c.label_a, c.label_b): (c.score, c.verdict_label) for c in WarCombo.query.all()}
```

Called once per request at each of the three existing `get_war_verdict` call
sites (`war/routes.py`, `player/routes.py`, `cwl/routes.py`) — one query per
request instead of one per attack pair. Because all three share this loader, a
combo named once on `/war` is immediately recognized on player profiles and CWL
pages too, not just on the war page it was added from.

### 4. New endpoint (`war/routes.py`)

`POST /war/api/combo/add`, gated by `_can_edit_clan_war` (same permission that
already gates other war-page edits — stars/castle — not a stricter
super-admin-only check).

Body: `label_a`, `label_b`, `score` (int, 0–100), `verdict_label` (non-empty,
trimmed, ≤60 chars). Normalizes to the sorted pair and inserts. Duplicate PK
(combo already named, e.g. a double-submit race) → 409, does not overwrite.
Returns `{ok: true}` on success.

### 5. UI (`templates/war/clanwar.html`)

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

### 6. Migration

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
- `war/routes.py`, `player/routes.py`, `cwl/routes.py`: each gains one
  `load_war_combos()` call per request handler that reaches `get_war_verdict`.
- New table `war_combo`, seeded not empty.
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
6. Visit a player profile or CWL page containing that same label pair, confirm
   it also shows the new verdict, not `?` — proves the shared loader/lookup
   works across all three call sites.
7. Try submitting the same combo twice (double-click or resubmit) — confirm
   the second attempt fails cleanly (409, inline error) rather than silently
   overwriting or crashing.

## Rollout

Code + migration on `dev_coc`. This app deploys via git (not manual server
commands) — commit and push once verified; run the migration as part of the
normal deploy flow.
