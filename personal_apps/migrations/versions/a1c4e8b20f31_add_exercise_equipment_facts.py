"""add equipment facts to gym exercises

Revision ID: a1c4e8b20f31
Revises: d98add219b32
Create Date: 2026-08-06

Adds how an exercise is loaded, the dead weight inside its logged number,
uneven stack stops, and secondary muscles -- then seeds the values for the
exercises actually in this gym, matched by name across every user's
catalogue (same machines, same hall, so a per-user answer is the same
answer three times).

is_unilateral is deliberately untouched: production already holds the
correct flags, and rewriting one would silently halve or double that
exercise's entire history in every statistic.
"""
import json

from alembic import op
import sqlalchemy as sa

revision = 'a1c4e8b20f31'
down_revision = 'd98add219b32'
branch_labels = None
depends_on = None


# name -> (equipment, bar_weight, secondary muscle groups)
SEED = {
    'Bench Press (Dumbbell)':                   ('dumbbell',     None, ['Trizeps', 'Schultern']),
    'Biceps Curl (Rotating)':                   ('dumbbell',     None, []),
    'Hammer Curl (Dumbbell)':                   ('dumbbell',     None, []),
    'Chest Press (Machine, Lying)':             ('plate_loaded', None, ['Trizeps', 'Schultern']),
    'Preacher Curl (Machine, Good)':            ('plate_loaded', None, []),
    'Lat Pulldown (Single Arm, Hauptbahnhof)':  ('plate_loaded', None, ['Bizeps']),
    'Military Press':                           ('plate_loaded', 20,   ['Trizeps']),
    'T Bar Row (Standing)':                     ('plate_loaded', None, ['Bizeps']),
    'T Bar Row (Lying)':                        ('plate_loaded', None, ['Bizeps']),
    'Chest Fly (Machine)':                      ('stack',        None, []),
    'Lateral Raise (Machine, Good)':            ('stack',        None, []),
    'Triceps Pushdown (Cable, EZ Bar)':         ('stack',        None, []),
    'Triceps Extension (Cable, Overhead)':      ('stack',        None, []),
    'Seated Row (Machine, Good)':               ('stack',        None, ['Bizeps']),
    'Lat Pulldown Kabelzug':                    ('stack',        None, ['Bizeps']),
    'Reverse Fly (Machine)':                    ('stack',        None, []),
    'Preacher Curl Bilateral':                  ('stack',        None, []),
}


def upgrade():
    bind = op.get_bind()
    # Adding a column is DDL, and MySQL/MariaDB commit DDL immediately without
    # rolling it back when the rest of the migration fails. The first run of
    # this migration against production added all four columns and then died on
    # the seed below, leaving the columns in place and alembic_version behind --
    # so re-running it must not try to add them a second time.
    existing = {column['name'] for column in
                sa.inspect(bind).get_columns('gym_exercises')}

    # server_default on equipment: the column is NOT NULL and the table has
    # rows, which would otherwise fail the ALTER.
    if 'equipment' not in existing:
        op.add_column('gym_exercises',
                      sa.Column('equipment', sa.String(length=20), nullable=False,
                                server_default='stack'))
    if 'bar_weight' not in existing:
        op.add_column('gym_exercises', sa.Column('bar_weight', sa.Float(), nullable=True))
    if 'stack_kg' not in existing:
        op.add_column('gym_exercises', sa.Column('stack_kg', sa.JSON(), nullable=True))
    if 'secondary_muscle_groups' not in existing:
        op.add_column('gym_exercises',
                      sa.Column('secondary_muscle_groups', sa.JSON(), nullable=True))

    for name, (equipment, bar_weight, secondary) in SEED.items():
        bind.execute(
            # No CAST(... AS JSON) here: production is MariaDB, where JSON is an
            # alias for LONGTEXT and that syntax is a parse error. Both engines
            # accept a JSON string assigned straight to the column -- MySQL 8
            # converts it on the way in, MariaDB stores the text as given.
            sa.text('UPDATE gym_exercises '
                    'SET equipment = :equipment, bar_weight = :bar_weight, '
                    '    secondary_muscle_groups = :secondary '
                    'WHERE name = :name'),
            {'equipment': equipment, 'bar_weight': bar_weight,
             'secondary': json.dumps(secondary), 'name': name},
        )


def downgrade():
    op.drop_column('gym_exercises', 'secondary_muscle_groups')
    op.drop_column('gym_exercises', 'stack_kg')
    op.drop_column('gym_exercises', 'bar_weight')
    op.drop_column('gym_exercises', 'equipment')
