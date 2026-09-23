"""gym: one global exercise list -- every lifter's history moves onto list rows

Revision ID: e2c7a9f41b86
Revises: b7e3f9c1a2d4
Create Date: 2026-09-23 12:00:00.000000

Exercises were per user since c8e5f14a9b32 (2026-08-02). From here on
gym_exercises holds one row per features/gym/library.py entry, keyed by
library_key, and the four values a lifter may set for themselves live in
gym_exercise_settings (spec: docs/superpowers/specs/2026-09-23-gym-global-
exercise-list.md, G1/G2).

Each per-user row finds its list row through the owner-approved mapping of
the production names (PRODUCTION_2026_09, frozen here), else through an exact
match of its name against one entry's name or alias. A row neither finds is
not an error: it becomes a *retired* row (library_key NULL) that keeps its
name and history and is never offered again, because an exercise created in
production after the audit must not turn this deploy into a broken app.
Every personal value that differed from the list becomes that lifter's
setting; an old NULL meant "the default", which the list now is.

MySQL and MariaDB commit DDL implicitly, so this revision cannot be one
transaction. It is re-runnable instead: the additive DDL and the drops are
each skipped when already done, and all data work happens in one
transaction with no DDL inside it, ending in invariant checks that raise
(and roll the data back) rather than commit a half-moved history.

Downgrade is refused: merged rows cannot be split back into the old names.
The rollback is the nightly backup, or a dump taken before the upgrade.
"""
import json
import math
import sys
from pathlib import Path

import sqlalchemy as sa
from alembic import op

# The first revision to read app code: the list is library.py's data. Make
# personal_apps/ importable whatever directory alembic was started from.
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from features.gym import library  # noqa: E402

revision = 'e2c7a9f41b86'
down_revision = 'b7e3f9c1a2d4'
branch_labels = None
depends_on = None

# library_mapping.PRODUCTION_2026_09 as approved by the owner on 2026-09-23,
# frozen so this revision does not depend on a module that goes away.
PRODUCTION_2026_09 = {
    'Bench Press (Dumbbell)': 'dumbbell_bench_press',
    'Biceps Curl (Rotating)': 'dumbbell_curl',
    'Bizeps SZ Kabel': 'cable_curl',
    'Chest Fly (Machine)': 'machine_fly',
    'Chest Press (Machine, Lying)': 'plate_bench_press',
    'Front Raises': 'cable_front_raise_one_arm',
    'Hammer Curl (Dumbbell)': 'dumbbell_hammer_curl',
    'Hammer Curl (Kabel)': 'cable_hammer_curl',
    'Lat Pulldown (Single Arm, Hauptbahnhof)': 'plate_lat_pulldown',
    'Lat Pulldown Kabelzug': 'cable_lat_pulldown',
    'Later Raise Iso': 'plate_lateral_raise',
    'Lateral Raise (Machine, Good)': 'machine_lateral_raise',
    'Military Press': 'barbell_overhead_press',
    'Preacher Curl (Machine, Good)': 'plate_preacher_curl',
    'Preacher Curl Bilateral': 'machine_preacher_curl',
    'Reverse Fly (Machine)': 'machine_rear_delt_fly',
    'Seated Row (Machine, Good)': 'machine_row',
    'T Bar Row (Lying)': 'tbar_row_chest_supported',
    'T Bar Row (Standing)': 'tbar_row',
    'Triceps Extension (Cable, Overhead)': 'cable_overhead_extension',
    'Triceps Pushdown (Cable, EZ Bar)': 'cable_pushdown',
}
_MAPPED = {' '.join(name.split()): key for name, key in PRODUCTION_2026_09.items()}

PERSONAL = ('weight_increment', 'default_rest_seconds', 'stack_kg', 'bar_weight')
FACTS = ('name', 'muscle_group', 'secondary_muscle_groups', 'equipment', 'is_unilateral')
# stats.DEFAULT_INCREMENT when this was written; halved for one side.
DEFAULT_INCREMENT = 2.5

_exercises = sa.table(
    'gym_exercises',
    sa.column('id', sa.Integer), sa.column('user_id', sa.Integer),
    sa.column('library_key', sa.String), sa.column('name', sa.String),
    sa.column('muscle_group', sa.String),
    sa.column('secondary_muscle_groups', sa.JSON(none_as_null=True)),
    sa.column('equipment', sa.String), sa.column('is_unilateral', sa.Boolean),
    sa.column('weight_increment', sa.Float), sa.column('default_rest_seconds', sa.Integer),
    sa.column('stack_kg', sa.JSON(none_as_null=True)), sa.column('bar_weight', sa.Float),
)
_settings = sa.table(
    'gym_exercise_settings',
    sa.column('user_id', sa.Integer), sa.column('exercise_id', sa.Integer),
    sa.column('weight_increment', sa.Float), sa.column('default_rest_seconds', sa.Integer),
    sa.column('stack_kg', sa.JSON(none_as_null=True)), sa.column('bar_weight', sa.Float),
)
_session_exercises = sa.table('gym_session_exercises', sa.column('id'), sa.column('exercise_id'))
_template_exercises = sa.table('gym_template_exercises', sa.column('id'), sa.column('exercise_id'))
_shared_map = sa.table('gym_shared_session_exercises', sa.column('id'),
                       sa.column('shared_session_id'), sa.column('leader_exercise_id'),
                       sa.column('follower_exercise_id'))


# -- pure helpers (tests/test_gym_global_migration_helpers.py) ---------------

def alias_index(entries):
    """Folded name or alias -> the keys it belongs to."""
    index = {}
    for entry in entries:
        for name in (entry.name, *entry.aka):
            index.setdefault(library.fold(name), set()).add(entry.key)
    return index


def resolve_key(name, index):
    """The list entry a per-user row becomes, or None."""
    key = _MAPPED.get(' '.join((name or '').split()))
    if key:
        return key
    keys = index.get(library.fold(name or ''), set())
    return next(iter(keys)) if len(keys) == 1 else None


def _close(a, b):
    if a is None or b is None:
        return a is None and b is None
    return math.isclose(float(a), float(b), rel_tol=1e-6)


def _stops(value):
    if isinstance(value, str):
        value = json.loads(value)
    if not value:
        return None
    return sorted(float(v) for v in value)


def is_even_grid(stops, step):
    """True when the stops are every `step` apart -- what the step already
    says, typed out (u1's Front Raises: 5, 10, ... 50 on a 5 kg stack)."""
    if not stops or not step or len(stops) < 2:
        return False
    return all(_close(b - a, step) for a, b in zip(stops, stops[1:]))


def _effective_step(row, target):
    step = row['weight_increment'] or target['weight_increment']
    if not step:
        step = DEFAULT_INCREMENT / 2 if target['is_unilateral'] else DEFAULT_INCREMENT
    return step


def carried(row, target):
    """The settings a per-user row leaves on its list row: each value it held
    that differs from the list's. An old NULL was "use the default" and a bar
    of 0 "nothing inside the number" -- neither is a setting."""
    out = {}
    if row['weight_increment'] is not None and not _close(row['weight_increment'], target['weight_increment']):
        out['weight_increment'] = float(row['weight_increment'])
    rest = row['default_rest_seconds']
    if rest is not None and rest != target['default_rest_seconds']:
        out['default_rest_seconds'] = int(rest)
    bar = row['bar_weight']
    if bar and not _close(bar, target['bar_weight'] or 0.0):
        out['bar_weight'] = float(bar)
    stops = _stops(row['stack_kg'])
    if (stops and target['equipment'] == 'stack'
            and not is_even_grid(stops, _effective_step(row, target))
            and stops != _stops(target['stack_kg'])):
        out['stack_kg'] = stops
    return out


def winner(rows):
    """The row whose values speak for a group: most session rows, then oldest."""
    return max(rows, key=lambda row: (row['n_se'], -row['id']))


def fact_changes(row, target):
    """The facts a row's history is read through that its list row states
    differently: one side or both (stats.set_volume doubles a one-sided
    number, so the whole history's volume doubles or halves) and the loading
    (the export's weight convention). Printed per row for the deploy log."""
    changes = []
    if bool(row['is_unilateral']) != bool(target['is_unilateral']):
        changes.append(f"is_unilateral {bool(row['is_unilateral'])} -> {bool(target['is_unilateral'])}")
    if row['equipment'] != target['equipment']:
        changes.append(f"equipment {row['equipment']} -> {target['equipment']}")
    return changes


# -- phases -------------------------------------------------------------------

def _add_structures(bind):
    inspector = sa.inspect(bind)
    if not inspector.has_table('gym_exercise_settings'):
        op.create_table(
            'gym_exercise_settings',
            sa.Column('id', sa.Integer(), primary_key=True, autoincrement=True),
            sa.Column('user_id', sa.Integer(), nullable=False),
            sa.Column('exercise_id', sa.Integer(), nullable=False),
            sa.Column('weight_increment', sa.Float(), nullable=True),
            sa.Column('default_rest_seconds', sa.Integer(), nullable=True),
            sa.Column('stack_kg', sa.JSON(), nullable=True),
            sa.Column('bar_weight', sa.Float(), nullable=True),
            sa.ForeignKeyConstraint(['user_id'], ['app_user.id'],
                                    name='fk_gym_exercise_settings_user_id'),
            sa.ForeignKeyConstraint(['exercise_id'], ['gym_exercises.id'],
                                    name='fk_gym_exercise_settings_exercise_id',
                                    ondelete='CASCADE'),
            sa.UniqueConstraint('user_id', 'exercise_id',
                                name='uq_gym_exercise_settings_user_exercise'),
        )
    columns = {column['name'] for column in inspector.get_columns('gym_exercises')}
    if 'library_key' not in columns:
        op.add_column('gym_exercises', sa.Column('library_key', sa.String(64), nullable=True))
    if 'user_id' in columns:
        op.alter_column('gym_exercises', 'user_id', existing_type=sa.Integer(), nullable=True)
    return 'user_id' in columns


def _counts(bind):
    count = lambda table: bind.execute(sa.text(f'SELECT COUNT(*) FROM {table}')).scalar()
    return {table: count(table) for table in
            ('gym_session_exercises', 'gym_template_exercises', 'gym_session_sets',
             'gym_shared_session_exercises')}


def _move_rows(bind):
    before = _counts(bind)

    have = {row.library_key for row in bind.execute(
        sa.select(_exercises.c.library_key).where(_exercises.c.user_id.is_(None),
                                                  _exercises.c.library_key.isnot(None)))}
    missing = [{
        'library_key': entry.key, 'name': entry.name, 'muscle_group': entry.group,
        'secondary_muscle_groups': list(entry.secondary), 'equipment': entry.equipment,
        'is_unilateral': entry.unilateral, 'weight_increment': entry.increment,
        'default_rest_seconds': entry.rest, 'stack_kg': None, 'bar_weight': entry.bar,
        'user_id': None,
    } for entry in library.LIBRARY if entry.key not in have]
    if missing:
        bind.execute(_exercises.insert(), missing)
    list_rows = {row.library_key: dict(row._mapping) for row in bind.execute(
        sa.select(_exercises).where(_exercises.c.user_id.is_(None),
                                    _exercises.c.library_key.isnot(None)))}

    n_se = dict(bind.execute(sa.text(
        'SELECT exercise_id, COUNT(*) FROM gym_session_exercises GROUP BY exercise_id')).all())
    old_rows = [{**row._mapping, 'n_se': n_se.get(row.id, 0)} for row in bind.execute(
        sa.select(_exercises).where(_exercises.c.user_id.isnot(None)).order_by(_exercises.c.id))]

    index = alias_index(library.LIBRARY)
    target_of, unmapped, how = {}, {}, {'mapping': 0, 'name': 0, 'retired': 0}
    for row in old_rows:
        key = resolve_key(row['name'], index)
        if key:
            target_of[row['id']] = list_rows[key]
            how['mapping' if ' '.join(row['name'].split()) in _MAPPED else 'name'] += 1
        else:
            unmapped.setdefault(library.fold(row['name']), []).append(row)
    for rows in unmapped.values():
        source = winner(rows)
        values = {column: source[column] for column in FACTS + PERSONAL}
        new_id = bind.execute(_exercises.insert().values(
            library_key=None, user_id=None, **values)).lastrowid
        retired = {**values, 'id': new_id, 'library_key': None}
        for row in rows:
            target_of[row['id']] = retired
        how['retired'] += len(rows)
        print(f'  retired: {source["name"]!r} ({len(rows)} row(s)) -> #{new_id}')

    # Old id -> new id for every row, into the deploy log: exports made
    # before this carry the old ids and names, and after it the only other
    # record of the mapping is the backup.
    for row in old_rows:
        target = target_of[row['id']]
        changes = fact_changes(row, target)
        print(f'  #{row["id"]} user {row["user_id"]} {row["name"]!r} ({row["n_se"]} logged)'
              f' -> #{target["id"]} {target["library_key"] or "retired"}'
              + (f'; {", ".join(changes)}' if changes else ''))

    by_owner = {}
    for row in old_rows:
        by_owner.setdefault((row['user_id'], target_of[row['id']]['id']), []).append(row)
    settings_rows = []
    for (user_id, target_id), rows in by_owner.items():
        row = winner(rows)
        values = carried(row, target_of[row['id']])
        if values:
            settings_rows.append({'user_id': user_id, 'exercise_id': target_id,
                                  **{field: values.get(field) for field in PERSONAL}})
    if settings_rows:
        bind.execute(_settings.insert(), settings_rows)

    for old_id, target in target_of.items():
        for table in (_session_exercises, _template_exercises):
            bind.execute(table.update().where(table.c.exercise_id == old_id)
                         .values(exercise_id=target['id']))
    seen, dropped = set(), []
    for link in bind.execute(sa.select(_shared_map).order_by(_shared_map.c.id)).all():
        leader = target_of[link.leader_exercise_id]['id']
        follower = target_of[link.follower_exercise_id]['id']
        if (link.shared_session_id, leader) in seen:
            dropped.append(link.id)
            continue
        seen.add((link.shared_session_id, leader))
        bind.execute(_shared_map.update().where(_shared_map.c.id == link.id)
                     .values(leader_exercise_id=leader, follower_exercise_id=follower))
    if dropped:
        bind.execute(_shared_map.delete().where(_shared_map.c.id.in_(dropped)))

    bind.execute(_exercises.delete().where(_exercises.c.user_id.isnot(None)))

    after = _counts(bind)
    expected = {**before, 'gym_shared_session_exercises':
                before['gym_shared_session_exercises'] - len(dropped)}
    left = bind.execute(sa.text(
        'SELECT COUNT(*) FROM gym_exercises WHERE user_id IS NOT NULL')).scalar()
    if after != expected or left:
        raise RuntimeError(f'exercise move does not add up: before {before}, after {after}, '
                           f'{len(dropped)} map row(s) dropped, {left} per-user row(s) left')
    print(f'  {len(old_rows)} per-user rows -> {how}; {len(settings_rows)} settings rows; '
          f'{len(missing)} list rows inserted')


def _drop_per_user_structures(bind):
    inspector = sa.inspect(bind)
    columns = {column['name'] for column in inspector.get_columns('gym_exercises')}
    if 'user_id' in columns:
        for fk in inspector.get_foreign_keys('gym_exercises'):
            if fk['constrained_columns'] == ['user_id']:
                op.drop_constraint(fk['name'], 'gym_exercises', type_='foreignkey')
        for index in sa.inspect(bind).get_indexes('gym_exercises'):
            if 'user_id' in index['column_names']:
                op.drop_index(index['name'], table_name='gym_exercises')
        op.drop_column('gym_exercises', 'user_id')
    if 'previous_name' in columns:
        op.drop_column('gym_exercises', 'previous_name')
    if not any(index['name'] == 'uq_gym_exercises_library_key'
               for index in sa.inspect(bind).get_indexes('gym_exercises')):
        op.create_unique_constraint('uq_gym_exercises_library_key', 'gym_exercises',
                                    ['library_key'])


def upgrade():
    bind = op.get_bind()
    if _add_structures(bind):
        per_user = bind.execute(sa.text(
            'SELECT COUNT(*) FROM gym_exercises WHERE user_id IS NOT NULL')).scalar()
        if per_user:
            _move_rows(bind)
    _drop_per_user_structures(bind)


def downgrade():
    raise RuntimeError(
        'e2c7a9f41b86 merged every lifter\'s exercises into one list; the old per-user rows '
        'and their names cannot be rebuilt. Restore from backup.')
