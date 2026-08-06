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
    # server_default on equipment: the column is NOT NULL and the table has
    # rows, which would otherwise fail the ALTER.
    op.add_column('gym_exercises',
                  sa.Column('equipment', sa.String(length=20), nullable=False,
                            server_default='stack'))
    op.add_column('gym_exercises', sa.Column('bar_weight', sa.Float(), nullable=True))
    op.add_column('gym_exercises', sa.Column('stack_kg', sa.JSON(), nullable=True))
    op.add_column('gym_exercises',
                  sa.Column('secondary_muscle_groups', sa.JSON(), nullable=True))

    bind = op.get_bind()
    for name, (equipment, bar_weight, secondary) in SEED.items():
        bind.execute(
            sa.text('UPDATE gym_exercises '
                    'SET equipment = :equipment, bar_weight = :bar_weight, '
                    '    secondary_muscle_groups = CAST(:secondary AS JSON) '
                    'WHERE name = :name'),
            {'equipment': equipment, 'bar_weight': bar_weight,
             'secondary': json.dumps(secondary), 'name': name},
        )


def downgrade():
    op.drop_column('gym_exercises', 'secondary_muscle_groups')
    op.drop_column('gym_exercises', 'stack_kg')
    op.drop_column('gym_exercises', 'bar_weight')
    op.drop_column('gym_exercises', 'equipment')
