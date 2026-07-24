# Admin-Editable War Combos Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Let an admin name a first-time war-attack combo (currently hardcoded in `WAR_COMBOS`, showing as a `?` badge) directly from the `/war` page, no code deploy needed.

**Architecture:** The hardcoded `WAR_COMBOS` dict in `features/war/war_combos.py` is replaced by a new `war_combo` DB table, seeded at migration time with the current 13 entries so behavior is unchanged the moment it ships. `get_war_verdict()` stays a pure function (no Flask/db import) — it now takes the loaded combos dict as an explicit third argument instead of reading a module global. A single Flask-`g`-cached accessor, `get_combos()` in `services/helpers.py`, is the only thing that knows how to load the table, and it's called at the two actual `get_war_verdict(...)` call sites (`war/routes.py`, and inside `_war_player_verdict` in `player/routes.py`) — no other function signature in either file's call chain changes. The `/war` page UI turns the `?` badge into a clickable button (admins only) that opens a small native-`popover` form; submitting POSTs to a new endpoint and reloads the page.

**Tech Stack:** Python 3, Flask, Flask-SQLAlchemy, Flask-Migrate (Alembic), MySQL, vanilla JS (no framework), Jinja2 templates.

## Global Constraints

- Spec: `docs/superpowers/specs/2026-07-24-war-combo-admin-design.md` — every task below implements one numbered section of it.
- **No automated test suite in this repo.** Verification is `app.test_client()` scripts and direct `app.app_context()` one-liners, run with `python`, not pytest. Do not add a test framework.
- Branch: `dev_coc`. This app deploys via git (not manual server commands) — commit after every task; no separate deploy step.
- Run all Python verification scripts with `sys.path.insert(0, r"C:\Users\michi\Desktop\CodingStuff\coc_stats")` then `from app import app` — this loads the Flask app without hitting the live Clash of Clans API (established local-run pattern for this project).
- Run `flask db upgrade`/`flask db migrate`-adjacent Alembic commands with cwd `coc_stats` (Flask autodetects `app.py` there).
- `war_combos.py` must stay Flask/db-free — `get_war_verdict(label_a, label_b, combos)` only ever reads the `combos` dict it's handed, never imports `flask` or `models`.
- Only the two real `get_war_verdict(...)` call sites change (`war/routes.py:132`, `player/routes.py:40` inside `_war_player_verdict`). Do not touch `_war_player_verdict`'s signature, `calculate_skill_score`, `calculate_scores_all_periods`, `_calculate_scores_bulk`, `_bulk_scores_cached`, `_clan_standing_all_periods`, `player_profile`, `clan_overview`, or anything in `features/admin/routes.py` — none of them need to know `combos` exists.
- `cwl/routes.py`'s `get_war_verdict` import is pre-existing dead code (it never calls the function) — leave it alone, not in scope.
- The combo-add endpoint is gated by `_can_edit_clan_war` (from `features/auth/routes.py`) — the same permission that already gates the war page's other admin edits (castle-empty, is-rushed, is-troll toggles). Not a stricter super-admin-only check.
- Non-admins must see byte-for-byte the same `?` badge markup as today — this feature is additive only for viewers who already have edit rights.

---

### Task 1: `WarCombo` model, table, and seed migration

**Files:**
- Modify: `coc_stats/models.py:311` (insert new class after `ClanWarAttack`)
- Create: `coc_stats/migrations/versions/a8e2f4c6b9d1_add_war_combo_table.py`

**Interfaces:**
- Produces: `models.WarCombo` (`label_a: str`, `label_b: str` — composite PK, sorted pair; `score: int`; `verdict_label: str`; `created_at: datetime`), and the `war_combo` table with 13 seeded rows. Consumed by Task 3 (`get_combos()`) and Task 5 (the add-combo endpoint).

- [ ] **Step 1: Add the model**

In `coc_stats/models.py`, insert directly after `ClanWarAttack` (currently ends at line 310 with `clan_war = db.relationship(...)`, blank line at 311, then the `# ── Clan War League ──` comment at 313):

```python
class WarCombo(db.Model):
    __tablename__ = 'war_combo'

    label_a       = db.Column(db.String(20), primary_key=True)
    label_b       = db.Column(db.String(20), primary_key=True)
    score         = db.Column(db.Integer, nullable=False)
    verdict_label = db.Column(db.String(60), nullable=False)
    created_at    = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))
```

Composite primary key on the sorted label pair, mirroring `war_combos.py`'s own `tuple(sorted(k))` normalization — a pair can never be stored twice under swapped keys. `datetime`/`timezone` are already imported at the top of `models.py` (`from datetime import datetime, timezone`), matching the same `default=lambda: datetime.now(timezone.utc)` pattern used by `AppUser.created_at` (`models.py:216`).

- [ ] **Step 2: Write the migration**

Create `coc_stats/migrations/versions/a8e2f4c6b9d1_add_war_combo_table.py`:

```python
"""add war_combo table

Revision ID: a8e2f4c6b9d1
Revises: f7a3c9d1e2b4
Create Date: 2026-07-24

"""
import datetime

from alembic import op
import sqlalchemy as sa

revision = 'a8e2f4c6b9d1'
down_revision = 'f7a3c9d1e2b4'
branch_labels = None
depends_on = None

war_combo_table = sa.table(
    'war_combo',
    sa.column('label_a', sa.String),
    sa.column('label_b', sa.String),
    sa.column('score', sa.Integer),
    sa.column('verdict_label', sa.String),
    sa.column('created_at', sa.DateTime),
)

# Sorted-pair seed rows, mirroring the WAR_COMBOS dict being removed from
# features/war/war_combos.py in the same change — recomputed with
# tuple(sorted(...)) so byte-for-byte identical lookups survive the migration.
SEED_ROWS = [
    ('clear', 'clear', 100, 'Flawless'),
    ('clean_up', 'low_clear', 90, 'War Crimes'),
    ('clear', 'low_clear', 90, 'Scaredy Cat'),
    ('clean_up', 'clear', 90, 'Missing Confidence'),
    ('farm', 'low_clear', 75, 'Lazy Farmer'),
    ('clear', 'failed_clear', 50, 'Fumble'),
    ('farm', 'farm', 50, 'Farmer'),
    ('failed_clear', 'low_clear', 50, 'Fumble'),
    ('failed_farm', 'farm', 25, 'Inconsistent Farmer'),
    ('farm', 'wasted', 25, 'Inconsistent Farmer'),
    ('failed_clear', 'failed_clear', 15, 'Failure'),
    ('wasted', 'wasted', 15, 'Wasted'),
    ('no_attack', 'no_attack', 0, 'No Show'),
]


def upgrade():
    op.create_table(
        'war_combo',
        sa.Column('label_a',       sa.String(20), nullable=False),
        sa.Column('label_b',       sa.String(20), nullable=False),
        sa.Column('score',         sa.Integer(),  nullable=False),
        sa.Column('verdict_label', sa.String(60), nullable=False),
        sa.Column('created_at',    sa.DateTime(), nullable=True),
        sa.PrimaryKeyConstraint('label_a', 'label_b'),
    )
    now = datetime.datetime.utcnow()
    op.bulk_insert(war_combo_table, [
        {'label_a': a, 'label_b': b, 'score': s, 'verdict_label': l, 'created_at': now}
        for a, b, s, l in SEED_ROWS
    ])


def downgrade():
    op.drop_table('war_combo')
```

`f7a3c9d1e2b4` is the current Alembic head (`add_equip_last_seen_to_app_user`) — confirmed by walking every `revision`/`down_revision` pair in `migrations/versions/` and finding the one revision no other file declares as its `down_revision`.

- [ ] **Step 3: Apply the migration**

Run:
```bash
cd coc_stats && flask db upgrade
```
Expected: no errors; last line mentions upgrading to `a8e2f4c6b9d1`.

- [ ] **Step 4: Verify the table exists with exactly 13 seeded rows matching the old dict**

Run:
```bash
python -c "
import sys
sys.path.insert(0, r'C:\Users\michi\Desktop\CodingStuff\coc_stats')
from app import app
from models import WarCombo

with app.app_context():
    rows = WarCombo.query.order_by(WarCombo.label_a, WarCombo.label_b).all()
    assert len(rows) == 13, f'expected 13 rows, got {len(rows)}'
    by_key = {(r.label_a, r.label_b): (r.score, r.verdict_label) for r in rows}
    checks = [
        (('clear', 'clear'), (100, 'Flawless')),
        (('no_attack', 'no_attack'), (0, 'No Show')),
        (('failed_clear', 'low_clear'), (50, 'Fumble')),
        (('farm', 'wasted'), (25, 'Inconsistent Farmer')),
    ]
    for key, expected in checks:
        actual = by_key.get(key)
        status = 'OK' if actual == expected else 'MISMATCH'
        print(key, 'expected', expected, 'got', actual, status)
    print(f'row count OK: {len(rows)}')
"
```
Expected: four `OK` lines, then `row count OK: 13`.

- [ ] **Step 5: Commit**

```bash
git add coc_stats/models.py coc_stats/migrations/versions/a8e2f4c6b9d1_add_war_combo_table.py
git commit -m "$(cat <<'EOF'
feat(war): add war_combo table, seeded from the hardcoded WAR_COMBOS dict

First step toward letting admins name new war-attack combos from the
UI instead of a code deploy. This migration only adds the table and
seeds it with the current 13 entries — nothing reads from it yet.
EOF
)"
```

---

### Task 2: `war_combos.py` — remove the hardcoded dict, take `combos` explicitly

**Files:**
- Modify: `coc_stats/features/war/war_combos.py:41-101`

**Interfaces:**
- Consumes: nothing new (stays Flask/db-free).
- Produces: `get_war_verdict(label_a, label_b, combos) -> (score: int, label: str, badge: str)` — the `combos` param is `{(label_a, label_b) sorted tuple: (score, verdict_label)}`. This is a **breaking signature change** (was 2-arg) — consumed by Task 4 (`player/routes.py`) and Task 5 (`war/routes.py`), both edited in this same plan.

- [ ] **Step 1: Replace the `WAR_COMBOS` section and `get_war_verdict`**

In `coc_stats/features/war/war_combos.py`, replace everything from the `# ── Combination verdicts ──` comment block (line 41) through the end of `get_war_verdict` (line 101) — i.e. delete the whole hardcoded dict, its `tuple(sorted(k))` normalization line, and the old docstring-less lookup — with:

```python
# ── Combination verdicts ─────────────────────────────────────────────────────
# Named combos live in the war_combo DB table (models.WarCombo), added from the
# '?' badge on /war when an admin sees a first-time combination. This module
# stays Flask/db-free — get_war_verdict() takes the loaded table as `combos`,
# supplied by the caller via services.helpers.get_combos().

_DEFAULT_SCORE = 50
_DEFAULT_LABEL = 'First Time Combination'


def get_war_verdict(label_a, label_b, combos):
    """Look up the combined verdict for two attack labels.

    combos: {(label_a, label_b) sorted: (score, verdict_label)}, loaded by the
    caller (see services.helpers.get_combos()) — this function never touches
    the database itself. Returns (score, label, badge).
    """
    key = tuple(sorted([label_a, label_b]))
    score, label = (combos or {}).get(key, (_DEFAULT_SCORE, _DEFAULT_LABEL))

    if label == _DEFAULT_LABEL:
        badge = 'badge-undefined'
    elif score >= 80:
        badge = 'badge-godlike'
    elif score >= 65:
        badge = 'badge-dominant'
    elif score >= 50:
        badge = 'badge-wow'
    elif score >= 30:
        badge = 'badge-good'
    elif score >= 10:
        badge = 'badge-warning'
    else:
        badge = 'badge-suck'

    return score, label, badge
```

`get_attack_context` and `get_cwl_verdict` below this block are untouched.

- [ ] **Step 2: Verify the new signature behaves identically to the old hardcoded lookup, given an equivalent dict**

Run:
```bash
python -c "
import sys
sys.path.insert(0, r'C:\Users\michi\Desktop\CodingStuff\coc_stats')
from features.war.war_combos import get_war_verdict, CLEAR, FAILED_CLEAR, NO_ATTACK

combos = {
    ('clear', 'clear'): (100, 'Flawless'),
    ('failed_clear', 'failed_clear'): (15, 'Failure'),
    ('no_attack', 'no_attack'): (0, 'No Show'),
}

checks = [
    ((CLEAR, CLEAR), (100, 'Flawless', 'badge-godlike')),
    ((FAILED_CLEAR, FAILED_CLEAR), (15, 'Failure', 'badge-warning')),
    ((NO_ATTACK, NO_ATTACK), (0, 'No Show', 'badge-suck')),
    (('made_up_label', CLEAR), (50, 'First Time Combination', 'badge-undefined')),
]
for (a, b), expected in checks:
    actual = get_war_verdict(a, b, combos)
    status = 'OK' if actual == expected else 'MISMATCH'
    print(a, b, 'expected', expected, 'got', actual, status)

# combos=None must fail soft, not crash
actual = get_war_verdict(CLEAR, CLEAR, None)
print('combos=None ->', actual, 'OK' if actual == (50, 'First Time Combination', 'badge-undefined') else 'MISMATCH')
"
```
Expected: five `OK` lines, no traceback.

- [ ] **Step 3: Commit**

```bash
git add coc_stats/features/war/war_combos.py
git commit -m "$(cat <<'EOF'
refactor(war): get_war_verdict takes combos explicitly, drop hardcoded dict

WAR_COMBOS is gone — named combos now live in the war_combo table
(previous commit). war_combos.py stays Flask/db-free: get_war_verdict
just takes the loaded combos dict as a third argument instead of
reading a module-level global. Callers are updated in the next two
commits; this one is intentionally a breaking signature change.
EOF
)"
```

---

### Task 3: `get_combos()` — request-cached loader

**Files:**
- Modify: `coc_stats/services/helpers.py:1-19`

**Interfaces:**
- Consumes: `models.WarCombo` (Task 1).
- Produces: `get_combos() -> dict` (`{(label_a, label_b): (score, verdict_label)}`), request-scoped via Flask `g`. Consumed by Task 4 and Task 5.

- [ ] **Step 1: Add the imports and the function**

In `coc_stats/services/helpers.py`, add `from flask import g` and `from models import WarCombo` to the import block at the top (currently lines 1-8), and add `get_combos()` right after the existing module-level constants (currently ending at line 18 with `RAID_CAPITAL_PEAK_MEDALS = {...}`), before `_is_attack`:

```python
import datetime as dt
import logging
import os
import re
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from dotenv import load_dotenv
from flask import g

from models import WarCombo

load_dotenv(override=True)
LOCAL_TZ = ZoneInfo(os.getenv("TIMEZONE", "Europe/Berlin"))

CLEANUP_THRESHOLD = 35
SKIP_LEAGUES      = {'Unranked', 'Unknown League', None, ''}
IMPORT_WINDOW     = timedelta(minutes=2)

RAID_DISTRICT_MEDALS     = {1: 135, 2: 225, 3: 350, 4: 405, 5: 460}
RAID_CAPITAL_PEAK_MEDALS = {2: 180, 3: 360, 4: 585, 5: 810, 6: 1115, 7: 1240, 8: 1260, 9: 1375, 10: 1450}


def get_combos():
    """Load the war_combo table once per request, cached on Flask's g.
    Returns {(label_a, label_b): (score, verdict_label)} for get_war_verdict()."""
    if 'war_combos' not in g:
        g.war_combos = {(c.label_a, c.label_b): (c.score, c.verdict_label) for c in WarCombo.query.all()}
    return g.war_combos


def _is_attack(log):
    return log.attack is True or log.attack == 1
```

- [ ] **Step 2: Verify it loads the 13 seeded rows and caches on `g` within one request context**

Run:
```bash
python -c "
import sys
sys.path.insert(0, r'C:\Users\michi\Desktop\CodingStuff\coc_stats')
from app import app
from services.helpers import get_combos

with app.test_request_context('/'):
    combos = get_combos()
    assert len(combos) == 13, f'expected 13, got {len(combos)}'
    assert combos[('clear', 'clear')] == (100, 'Flawless'), combos.get(('clear', 'clear'))
    combos2 = get_combos()
    assert combos2 is combos, 'second call within the same request should return the cached dict object, not requery'
    print('OK: 13 combos loaded, cached on g within one request')
"
```
Expected: `OK: 13 combos loaded, cached on g within one request`.

- [ ] **Step 3: Commit**

```bash
git add coc_stats/services/helpers.py
git commit -m "$(cat <<'EOF'
feat(war): add get_combos() request-cached loader for war_combo table

Single per-request accessor for the newly-added war_combo table,
cached on Flask g so it's queried once no matter how many times the
scoring call chain loops through get_war_verdict inside a request.
Not wired into any caller yet.
EOF
)"
```

---

### Task 4: `player/routes.py` — wire the lookup, add cache-busting

**Files:**
- Modify: `coc_stats/features/player/routes.py:10-14` (imports), `:40` (the `get_war_verdict` call inside `_war_player_verdict`), `:1263-1264` (near `_BULK_STANDING_CACHE`)

**Interfaces:**
- Consumes: `get_combos()` (Task 3).
- Produces: `clear_bulk_standing_cache() -> None`. Consumed by Task 5's endpoint (imported there as `from features.player.routes import clear_bulk_standing_cache`).

- [ ] **Step 1: Import `get_combos` and use it in `_war_player_verdict`**

In `coc_stats/features/player/routes.py`, extend the existing `from services.helpers import (...)` block (currently lines 10-14):

```python
from services.helpers import (
    _ranked_verdict, _calc_ranked_score,
    _district_stats, _raid_verdict, LOCAL_TZ,
    _is_attack, week_cutoff, filter_import_window,
    get_combos,
)
```

Then replace line 40 (inside `_war_player_verdict`):

```python
    score, verdict_label, badge = get_war_verdict(labels[0], labels[1])
```

with:

```python
    score, verdict_label, badge = get_war_verdict(labels[0], labels[1], get_combos())
```

Nothing else in `_war_player_verdict` or any of its callers changes — `get_combos()` is called fresh each time `_war_player_verdict` runs, but since it's `g`-cached, every call within the same request after the first is a dict lookup, not a query.

- [ ] **Step 2: Add `clear_bulk_standing_cache()`**

In `coc_stats/features/player/routes.py`, directly after the existing cache declaration (currently lines 1263-1264):

```python
_BULK_STANDING_CACHE = {}          # (period, roster_hash) -> (expires_at, results)
_BULK_STANDING_TTL   = 300         # seconds


def clear_bulk_standing_cache():
    """Called after a WarCombo is added so the admin's own addition is
    visible on /player/<tag>'s clan-standing widget immediately, instead of
    waiting out the up-to-5-minute TTL above."""
    _BULK_STANDING_CACHE.clear()
```

- [ ] **Step 3: Verify `/player/<tag>` still renders and the cache-clear function works**

Run (uses any real in-clan player tag from the dev DB — replace `SOME_PLAYER_TAG` with one confirmed to exist, e.g. via `Player.query.filter_by(in_clan=True).first().tag`):
```bash
python -c "
import sys
sys.path.insert(0, r'C:\Users\michi\Desktop\CodingStuff\coc_stats')
from app import app
from models import Player
from features.player.routes import clear_bulk_standing_cache, _BULK_STANDING_CACHE

with app.app_context():
    p = Player.query.filter_by(in_clan=True).first()
    assert p is not None, 'no in-clan player found in dev DB — cannot verify /player/<tag>'
    tag = p.tag

with app.test_client() as c:
    r = c.get('/player/' + tag.replace('#', ''))
    assert r.status_code == 200, ('GET /player/<tag>', r.status_code)
    print('GET /player/' + tag + ' ->', r.status_code)

    r = c.get('/clan')
    assert r.status_code == 200, ('GET /clan', r.status_code)
    print('GET /clan ->', r.status_code)

_BULK_STANDING_CACHE[('month', 12345)] = (9999999999.0, {'fake': 'entry'})
assert len(_BULK_STANDING_CACHE) >= 1
clear_bulk_standing_cache()
assert len(_BULK_STANDING_CACHE) == 0, 'cache not cleared'
print('OK: clear_bulk_standing_cache() empties _BULK_STANDING_CACHE')
"
```
Expected: `GET /player/<tag> -> 200`, `GET /clan -> 200`, `OK: clear_bulk_standing_cache() empties _BULK_STANDING_CACHE`.

- [ ] **Step 4: Commit**

```bash
git add coc_stats/features/player/routes.py
git commit -m "$(cat <<'EOF'
feat(war): wire get_combos() into player scoring, add cache-bust hook

_war_player_verdict now passes the loaded combos table into
get_war_verdict, same as the /war route. clear_bulk_standing_cache()
lets the new combo-add endpoint (previous commit) invalidate the
5-minute clan-standing cache so a freshly named combo doesn't look
stale on /player/<tag>.
EOF
)"
```

---

### Task 5: `war/routes.py` — wire the lookup, add the combo-add endpoint

**Files:**
- Modify: `coc_stats/features/war/routes.py:1-11` (imports), `:132` (the `get_war_verdict` call), end of file (new route)

**Interfaces:**
- Consumes: `get_war_verdict(label_a, label_b, combos)` (Task 2), `get_combos()` (Task 3), `models.WarCombo` (Task 1), `features.player.routes.clear_bulk_standing_cache` (Task 4 — already exists by this point).
- Produces: `POST /war/api/combo/add` — body `{label_a, label_b, score, verdict_label}`, returns `{ok: true}` (200) or `{error: str}` (400/403/409). Consumed by Task 6's UI.

- [ ] **Step 1: Update imports and the existing `get_war_verdict` call**

In `coc_stats/features/war/routes.py`, replace the import block (lines 1-11):

```python
import datetime as dt

from flask import Blueprint, render_template, request, jsonify
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import selectinload

from extensions import db
from models import ClanWar, ClanWarMember, WarCombo
from features.auth.routes import _can_edit_clan_war
from services.helpers import avg_league_name, league_rank, SKIP_LEAGUES, get_combos
from features.war.war_combos import classify_attack, get_war_verdict, get_attack_context
from features.player.routes import clear_bulk_standing_cache

war_bp = Blueprint('war', __name__)
```

`player/routes.py` does not import anything from `war/routes.py` (confirmed — only `app.py` imports `war_bp`), so this is a one-directional dependency, not a cycle. `clear_bulk_standing_cache` already exists in `player/routes.py` as of Task 4, so this import resolves cleanly.

Then replace line 132 (inside `clan_war_page`, the `# ── War verdicts ──` loop):

```python
            score, verdict_label, badge = get_war_verdict(labels[0], labels[1])
```

with:

```python
            score, verdict_label, badge = get_war_verdict(labels[0], labels[1], get_combos())
```

- [ ] **Step 2: Add the combo-add endpoint**

Append to the end of `coc_stats/features/war/routes.py` (after `war_toggle_member_troll`):

```python


@war_bp.route('/war/api/combo/add', methods=['POST'])
def war_add_combo():
    if not _can_edit_clan_war():
        return jsonify(error='Forbidden'), 403

    data = request.get_json(silent=True) or {}
    label_a = str(data.get('label_a') or '').strip()
    label_b = str(data.get('label_b') or '').strip()
    verdict_label = str(data.get('verdict_label') or '').strip()

    if not label_a or not label_b:
        return jsonify(error='Missing attack labels'), 400
    try:
        score = int(data.get('score'))
    except (TypeError, ValueError):
        return jsonify(error='Score must be a number'), 400
    if not (0 <= score <= 100):
        return jsonify(error='Score must be between 0 and 100'), 400
    if not verdict_label or len(verdict_label) > 60:
        return jsonify(error='Verdict label must be 1-60 characters'), 400

    a, b = sorted([label_a, label_b])
    db.session.add(WarCombo(label_a=a, label_b=b, score=score, verdict_label=verdict_label))
    try:
        db.session.commit()
    except IntegrityError:
        db.session.rollback()
        return jsonify(error='Combo already named'), 409

    clear_bulk_standing_cache()
    return jsonify(ok=True)
```

- [ ] **Step 3: Verify the read path still works and the new endpoint round-trips**

Run (this both confirms `/war` still renders after the `get_combos()` wiring, and exercises the add endpoint end to end — permission denial, a real insert, and the duplicate-409 path):
```bash
python -c "
import sys
sys.path.insert(0, r'C:\Users\michi\Desktop\CodingStuff\coc_stats')
from app import app
from models import WarCombo
from extensions import db

with app.app_context():
    # clean up any leftover row from a prior failed run of this exact script
    existing = db.session.get(WarCombo, ('__test_a__', '__test_b__'))
    if existing:
        db.session.delete(existing)
        db.session.commit()

with app.test_client() as c:
    r = c.get('/war')
    assert r.status_code == 200, ('GET /war', r.status_code)
    print('GET /war ->', r.status_code)

    # anonymous: forbidden
    r = c.post('/war/api/combo/add', json={'label_a': '__test_a__', 'label_b': '__test_b__', 'score': 42, 'verdict_label': 'Test Combo'})
    assert r.status_code == 403, ('anonymous add', r.status_code, r.get_json())
    print('anonymous POST ->', r.status_code, r.get_json())

    with c.session_transaction() as sess:
        sess['env_admin_logged_in'] = True

    # admin: succeeds
    r = c.post('/war/api/combo/add', json={'label_a': '__test_a__', 'label_b': '__test_b__', 'score': 42, 'verdict_label': 'Test Combo'})
    assert r.status_code == 200 and r.get_json().get('ok') is True, ('admin add', r.status_code, r.get_json())
    print('admin POST (new) ->', r.status_code, r.get_json())

    # duplicate: 409, does not overwrite
    r = c.post('/war/api/combo/add', json={'label_a': '__test_b__', 'label_b': '__test_a__', 'score': 99, 'verdict_label': 'Overwrite Attempt'})
    assert r.status_code == 409, ('duplicate add', r.status_code, r.get_json())
    print('admin POST (duplicate, swapped order) ->', r.status_code, r.get_json())

    # bad score: 400
    r = c.post('/war/api/combo/add', json={'label_a': '__test_c__', 'label_b': '__test_d__', 'score': 500, 'verdict_label': 'Too High'})
    assert r.status_code == 400, ('bad score', r.status_code, r.get_json())
    print('admin POST (score=500) ->', r.status_code, r.get_json())

with app.app_context():
    row = db.session.get(WarCombo, ('__test_a__', '__test_b__'))
    assert row is not None and row.score == 42 and row.verdict_label == 'Test Combo', 'inserted row not found or wrong values'
    print('DB row confirmed:', row.label_a, row.label_b, row.score, row.verdict_label)
    db.session.delete(row)
    db.session.commit()
    print('test row cleaned up')
"
```
Expected: `GET /war -> 200`, `anonymous POST -> 403 ...`, `admin POST (new) -> 200 {'ok': True}`, `admin POST (duplicate, swapped order) -> 409 ...`, `admin POST (score=500) -> 400 ...`, `DB row confirmed: __test_a__ __test_b__ 42 Test Combo`, `test row cleaned up`. This test writes and then deletes its own `__test_a__`/`__test_b__` rows — it does not touch any of the 13 seeded real combos.

- [ ] **Step 4: Commit**

```bash
git add coc_stats/features/war/routes.py
git commit -m "$(cat <<'EOF'
feat(war): wire get_combos() into /war, add combo-add endpoint

POST /war/api/combo/add lets an editor (same permission as the other
war-page toggles) name a first-time combo. Gated by _can_edit_clan_war,
race-safe on the composite PK via IntegrityError -> 409, and busts the
clan-standing bulk-scoring cache so the admin's own addition is
visible immediately elsewhere too.
EOF
)"
```

---

### Task 6: `/war` UI — clickable `?` badge, popover, submit

**Files:**
- Modify: `coc_stats/templates/war/clanwar.html:24` (CSS insertion point), `:475-476` (JS const), `:596-606` (badge cell), `:653-654` (new JS functions)

**Interfaces:**
- Consumes: `POST /war/api/combo/add` (Task 5), the `can_edit_clan_war` Jinja global (already injected into every template by the sitewide context processor in `app.py:171` — no route change needed), `v.atk_labels` and `v.player_tag` (already present in the `WAR_VERDICTS` JS payload, unchanged by this plan).
- Produces: no new interface for later tasks — this is the last code task.

- [ ] **Step 1: Add the CSS**

In `coc_stats/templates/war/clanwar.html`, insert directly after the existing `.selector:focus { ... }` rule (line 24) and before `{% include "war/_war_unit_style.html" %}` (line 26):

```css
        .selector:focus { box-shadow: 0 0 0 3px color-mix(in oklch, var(--accent) 14%, transparent); }

        /* ── COMBO-ADD POPOVER (admin-only; mirrors player_profile.html's .detail-pop) ── */
        .judgment-add-btn { appearance: none; -webkit-appearance: none; cursor: pointer; }
        .judgment-add-btn:hover, .judgment-add-btn:focus-visible { outline: 2px solid var(--accent); outline-offset: 2px; }
        .combo-pop {
            position: fixed; margin: 0; inset: auto; background: var(--surf2); border: 1px solid var(--border);
            border-radius: 8px; padding: 12px 14px; width: 240px; box-shadow: 0 8px 24px rgba(0,0,0,.5);
            color: var(--text); font-family: 'Manrope', sans-serif; z-index: 9999;
        }
        .combo-pop h5 { font-family: 'JetBrains Mono', monospace; font-size: 12px; font-weight: 700; text-transform: uppercase; letter-spacing: .6px; margin-bottom: 10px; }
        .cp-row + .cp-row { margin-top: 8px; }
        .cp-row label { display: block; font-size: 10px; font-weight: 700; letter-spacing: .6px; text-transform: uppercase; color: var(--muted); margin-bottom: 3px; }
        .cp-row input { width: 100%; box-sizing: border-box; background: var(--surface); border: 1px solid var(--border); border-radius: 6px; padding: 6px 8px; color: var(--text); font-family: 'Manrope', sans-serif; font-size: 13px; }
        .cp-error { margin-top: 8px; font-size: 11px; color: var(--red); }
        .cp-actions { display: flex; justify-content: flex-end; gap: 8px; margin-top: 12px; }

        {% include "war/_war_unit_style.html" %}
```

- [ ] **Step 2: Add the `CAN_EDIT_COMBOS` JS const**

Directly after `const WAR_VERDICTS = {{ war_verdicts | tojson | safe }};` (line 475):

```javascript
const WAR_VERDICTS = {{ war_verdicts | tojson | safe }};
const CAN_EDIT_COMBOS = {{ can_edit_clan_war | tojson }};
let wvSort = { col: 'score', dir: 'desc' };
```

- [ ] **Step 3: Make the badge clickable for editors**

In `buildWarVerdictTable` (currently lines 596-606), replace:

```javascript
        row.innerHTML = `
            <td style="text-align:center;font-family:'Rajdhani',sans-serif;font-weight:700;color:var(--muted);font-size:13px;">#${v.map_pos}</td>
            <td>
                <div style="font-weight:600;font-size:13.5px;"><a href="/player/${encodeURIComponent((v.player_tag||'').replace('#',''))}" class="player-link" onclick="event.stopPropagation();">${escapeHTML(v.player_name)} <span class="player-link-arrow">↗</span></a></div>
                <div style="font-size:11px;color:var(--muted);margin-top:1px;">TH${v.player_th}</div>
            </td>
            <td style="font-size:11px;color:var(--muted);white-space:nowrap;overflow:hidden;text-overflow:ellipsis;">${v.league ? escapeHTML(v.league) : '—'}</td>
            <td style="text-align:center;font-family:'Rajdhani',sans-serif;font-size:16px;font-weight:700;">${v.attacks_used}<span style="font-size:12px;color:var(--muted);font-weight:400;">/2</span></td>
            <td style="text-align:center;"><span class="judgment ${v.badge}" title="${v.badge === 'badge-undefined' ? v.label : ''}">${v.badge === 'badge-undefined' ? '?' : v.label}${v.score > 0 ? ` <span style="opacity:0.6;font-size:0.9em;">·</span> ${v.score}` : ''}</span></td>
            <td><button type="button" class="action-btn details-toggle" onclick="event.stopPropagation(); toggleWarVerdictDetails(this)">Details</button></td>
        `;
```

with:

```javascript
        const badgeContent = (v.badge === 'badge-undefined' ? '?' : v.label) + (v.score > 0 ? ` <span style="opacity:0.6;font-size:0.9em;">·</span> ${v.score}` : '');
        const badgeTitle = v.badge === 'badge-undefined' ? v.label : '';
        const badgeCell = (v.badge === 'badge-undefined' && CAN_EDIT_COMBOS)
            ? `<button type="button" class="judgment ${v.badge} judgment-add-btn" title="${badgeTitle} — click to name it" onclick="event.stopPropagation(); openComboAdd(this, '${v.player_tag}')">${badgeContent}</button>`
            : `<span class="judgment ${v.badge}" title="${badgeTitle}">${badgeContent}</span>`;

        row.innerHTML = `
            <td style="text-align:center;font-family:'Rajdhani',sans-serif;font-weight:700;color:var(--muted);font-size:13px;">#${v.map_pos}</td>
            <td>
                <div style="font-weight:600;font-size:13.5px;"><a href="/player/${encodeURIComponent((v.player_tag||'').replace('#',''))}" class="player-link" onclick="event.stopPropagation();">${escapeHTML(v.player_name)} <span class="player-link-arrow">↗</span></a></div>
                <div style="font-size:11px;color:var(--muted);margin-top:1px;">TH${v.player_th}</div>
            </td>
            <td style="font-size:11px;color:var(--muted);white-space:nowrap;overflow:hidden;text-overflow:ellipsis;">${v.league ? escapeHTML(v.league) : '—'}</td>
            <td style="text-align:center;font-family:'Rajdhani',sans-serif;font-size:16px;font-weight:700;">${v.attacks_used}<span style="font-size:12px;color:var(--muted);font-weight:400;">/2</span></td>
            <td style="text-align:center;">${badgeCell}</td>
            <td><button type="button" class="action-btn details-toggle" onclick="event.stopPropagation(); toggleWarVerdictDetails(this)">Details</button></td>
        `;
```

Player tags (`v.player_tag`) are Clash of Clans tags — always `#` plus uppercase alphanumerics, never containing a quote character, so interpolating one into a single-quoted JS string inside this HTML attribute is safe without extra escaping (same trust level as `v.player_name` being escaped via `escapeHTML` a few lines above, which handles the one field here that genuinely is free-text).

- [ ] **Step 4: Add the popover JS**

Directly before the `{% endif %}` that closes the `{% if war_verdicts %}` block (currently line 654, right after `toggleWarVerdicts`'s closing `}`):

```javascript
function toggleWarVerdicts() {
    const body    = document.getElementById('warVerdictBody');
    const chevron = document.getElementById('warVerdictChevron');
    const opening = body.style.display === 'none' || body.style.display === '';
    body.style.display = opening ? 'block' : 'none';
    chevron.classList.toggle('open', opening);
    if (opening && !document.getElementById('warVerdictTbody').children.length) buildWarVerdictTable();
}

// ── Combo-add popover (admin-only; keyboard + touch reachable, escapes table clip) ──
let comboPop, _comboLabels = null;
function ensureComboPop() {
    if (!comboPop) {
        comboPop = document.createElement('div');
        comboPop.className = 'combo-pop';
        comboPop.setAttribute('popover', 'auto');
        comboPop.setAttribute('role', 'dialog');
        comboPop.setAttribute('aria-label', 'Name this combo');
        comboPop.innerHTML = `
            <h5>Name this combo</h5>
            <div class="cp-row"><label for="cpScore">Score (0–100)</label><input id="cpScore" type="number" min="0" max="100" step="1"></div>
            <div class="cp-row"><label for="cpLabel">Verdict label</label><input id="cpLabel" type="text" maxlength="60"></div>
            <div class="cp-error" id="cpError" style="display:none;"></div>
            <div class="cp-actions">
                <button type="button" class="action-btn" onclick="comboPop.hidePopover()">Cancel</button>
                <button type="button" class="action-btn" onclick="submitComboAdd()">Save</button>
            </div>`;
        document.body.appendChild(comboPop);
    }
    return comboPop;
}
function openComboAdd(btn, playerTag) {
    const v = WAR_VERDICTS.find(x => x.player_tag === playerTag);
    if (!v) return;
    _comboLabels = v.atk_labels;
    const p = ensureComboPop();
    p.querySelector('#cpError').style.display = 'none';
    p.querySelector('#cpScore').value = '';
    p.querySelector('#cpLabel').value = '';
    p.showPopover();
    const r = btn.getBoundingClientRect();
    const w = 240;
    p.style.left = Math.max(12, Math.min(window.innerWidth - w - 12, r.right - w)) + 'px';
    p.style.top = (r.bottom + 6) + 'px';
    p.querySelector('#cpScore').focus();
}
function submitComboAdd() {
    const p = comboPop;
    const scoreEl = p.querySelector('#cpScore');
    const labelEl = p.querySelector('#cpLabel');
    const errEl = p.querySelector('#cpError');
    const score = parseInt(scoreEl.value, 10);
    const label = labelEl.value.trim();
    if (isNaN(score) || score < 0 || score > 100) {
        errEl.textContent = 'Score must be 0-100.';
        errEl.style.display = 'block';
        return;
    }
    if (!label) {
        errEl.textContent = 'Verdict label is required.';
        errEl.style.display = 'block';
        return;
    }
    fetch('/war/api/combo/add', {
        method: 'POST',
        headers: {'Content-Type': 'application/json', 'X-Requested-With': 'XMLHttpRequest'},
        body: JSON.stringify({label_a: _comboLabels[0], label_b: _comboLabels[1], score: score, verdict_label: label})
    })
    .then(r => r.json().then(data => ({status: r.status, data})))
    .then(({status, data}) => {
        if (status === 200 && data.ok) {
            location.reload();
        } else {
            errEl.textContent = data.error || 'Could not save — try again.';
            errEl.style.display = 'block';
        }
    })
    .catch(() => {
        errEl.textContent = 'Network error — try again.';
        errEl.style.display = 'block';
    });
}
window.addEventListener('scroll', () => {
    if (comboPop && comboPop.matches(':popover-open')) comboPop.hidePopover();
}, { passive: true });
{% endif %}
```

- [ ] **Step 5: Verify the markup renders correctly for both a can-edit and a non-edit session**

Run:
```bash
python -c "
import sys
sys.path.insert(0, r'C:\Users\michi\Desktop\CodingStuff\coc_stats')
from app import app

with app.test_client() as c:
    html = c.get('/war').get_data(as_text=True)
    assert 'CAN_EDIT_COMBOS = false' in html, 'anonymous session should see CAN_EDIT_COMBOS = false'
    assert 'openComboAdd' in html, 'popover JS missing'
    assert 'judgment-add-btn' in html, 'add-btn CSS class missing'
    print('anonymous: CAN_EDIT_COMBOS = false, OK')

    with c.session_transaction() as sess:
        sess['env_admin_logged_in'] = True
    html = c.get('/war').get_data(as_text=True)
    assert 'CAN_EDIT_COMBOS = true' in html, 'admin session should see CAN_EDIT_COMBOS = true'
    print('admin: CAN_EDIT_COMBOS = true, OK')
print('ROUTE OK')
"
```
Expected: `anonymous: CAN_EDIT_COMBOS = false, OK`, `admin: CAN_EDIT_COMBOS = true, OK`, `ROUTE OK`. (This only proves the flag renders correctly for both sessions — it does not prove a `?` badge is actually present, since that depends on whether the currently-loaded war has any undefined combo. Task 7 confirms the interactive click-path against a real war in the browser.)

- [ ] **Step 6: Commit**

```bash
git add coc_stats/templates/war/clanwar.html
git commit -m "$(cat <<'EOF'
feat(war): clickable ? badge opens combo-add popover for editors

Admins (same permission as the war page's other edit toggles) can now
name a first-time combo directly from the ? badge instead of needing
a code deploy. Native popover, matches player_profile.html's existing
detail-pop pattern. Non-editors see the identical static badge as
before.
EOF
)"
```

---

### Task 7: End-to-end browser verification

**Files:** none (verification-only task)

**Interfaces:**
- Consumes: everything from Tasks 1-6, running together against the real dev server.
- Produces: nothing further — this task exists to prove the whole feature works interactively, not just through `test_client` assertions.

- [ ] **Step 1: Start the dev server and open `/war`**

Use the Browser pane's `preview_start {name: "coc_stats"}` (per this project's existing `.claude/launch.json` entry), then navigate to `/war`. Log in as an admin (or rely on the env-admin credentials already configured for this dev environment, per `ADMIN_USER`/`ADMIN_PASS`).

- [ ] **Step 2: Find or manufacture an undefined combo**

Pick a war with at least one member showing a `?` badge in the verdict table (scroll/expand the "War Verdicts" section if collapsed). If none exists in the current data, that's fine — Task 5 Step 3's `test_client` script already round-tripped the endpoint with synthetic labels; this step is about the *interactive click path*, not manufacturing new real data. If no `?` is visible, skip to Step 6 having confirmed via `read_page` that a normal `.judgment` badge row renders correctly and unchanged.

- [ ] **Step 3: Click the `?` badge, confirm the popover opens**

Use `computer` to click the badge. Use `read_page` to confirm a dialog with "Name this combo", a Score input, a Verdict label input, and Cancel/Save buttons is now visible and positioned near the clicked badge (not off-screen).

- [ ] **Step 4: Submit a score and label, confirm the page reloads with the real verdict**

Type a score (e.g. `72`) and a label (e.g. `Test Verdict`) via `computer`/`form_input`, click Save. Confirm (via `read_page` or `get_page_text` after the reload) that the same row's badge no longer shows `?` — it now shows the submitted label and score.

- [ ] **Step 5: Confirm persistence and cross-page visibility**

Reload `/war` again (fresh navigation) — confirm the named combo still shows the real verdict, not `?` (proves it came from the DB, not just client-side state). If the same label pair appears on a player profile page (`/player/<tag>`) for a member who had that combo, confirm it shows there too, not `?`.

- [ ] **Step 6: Clean up the test data**

If Step 4 created a real `Test Verdict` row in the `war_combo` table (rather than being skipped per Step 2), remove it so it doesn't linger as junk data for the actual clan:
```bash
python -c "
import sys
sys.path.insert(0, r'C:\Users\michi\Desktop\CodingStuff\coc_stats')
from app import app
from models import WarCombo
from extensions import db

with app.app_context():
    row = WarCombo.query.filter_by(verdict_label='Test Verdict').first()
    if row:
        print('deleting test row:', row.label_a, row.label_b, row.score, row.verdict_label)
        db.session.delete(row)
        db.session.commit()
    else:
        print('no test row found, nothing to clean up')
"
```

- [ ] **Step 7: Confirm with the user**

Report what was actually observed in the browser (screenshot or `read_page` excerpt) — not just that the scripts passed — and hand off for final review. No further commit is needed; Tasks 1-6 already committed all the code.
