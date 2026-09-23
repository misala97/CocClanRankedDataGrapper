"""gym: one rest for all of a lifter's exercises ("Deine Pause")

Revision ID: fc72f159a49f
Revises: c5a1d8e3f207
Create Date: 2026-09-23 23:30:00.000000

V3 of the first-run work (docs/superpowers/plans/2026-09-23-gym-first-run-workflows.md),
lane C "Einmal für alle": a lifter sets the rest after each set once, for all
their exercises, and an exercise keeps a rest of its own only as an exception.
gym_lifter_settings holds the one value per lifter; no row means "by kind of
exercise", the list's rest for each -- which is what everybody has today, so
upgrading moves no data and changes no rest in force.

Downgrade keeps every rest in force for what the lifter trains: before the
table goes, each exercise a lifter with a rest for all has logged, keeps in a
routine or set up gets that rest as its own -- unless it has its own already,
or the list's rest is the same anyway. Only an exercise they never touched
falls back to the list.
"""
import sqlalchemy as sa
from alembic import op

revision = 'fc72f159a49f'
down_revision = 'c5a1d8e3f207'
branch_labels = None
depends_on = None

TABLE = 'gym_lifter_settings'


def upgrade():
    op.create_table(
        TABLE,
        sa.Column('user_id', sa.Integer(), sa.ForeignKey('app_user.id'), primary_key=True,
                  autoincrement=False),
        sa.Column('rest_seconds', sa.Integer(), nullable=True),
    )


# gym_exercises.default_rest_seconds is the list's rest (Exercise.list_rest_seconds).
TOUCHED = sa.text("""
    SELECT e.id, e.default_rest_seconds FROM gym_exercises e
    WHERE e.id IN (
        SELECT se.exercise_id FROM gym_session_exercises se
        JOIN gym_workout_sessions s ON s.id = se.session_id WHERE s.user_id = :user_id
        UNION
        SELECT te.exercise_id FROM gym_template_exercises te
        JOIN gym_workout_templates t ON t.id = te.template_id WHERE t.user_id = :user_id
        UNION
        SELECT es.exercise_id FROM gym_exercise_settings es WHERE es.user_id = :user_id)
""")


def downgrade():
    bind = op.get_bind()
    lifters = bind.execute(sa.text(
        f'SELECT user_id, rest_seconds FROM {TABLE} WHERE rest_seconds IS NOT NULL')).all()
    for user_id, seconds in lifters:
        for exercise_id, list_rest in bind.execute(TOUCHED, {'user_id': user_id}).all():
            if list_rest == seconds:
                continue
            row = bind.execute(sa.text(
                'SELECT id, default_rest_seconds FROM gym_exercise_settings '
                'WHERE user_id = :user_id AND exercise_id = :exercise_id'),
                {'user_id': user_id, 'exercise_id': exercise_id}).first()
            if row is None:
                bind.execute(sa.text(
                    'INSERT INTO gym_exercise_settings (user_id, exercise_id, default_rest_seconds) '
                    'VALUES (:user_id, :exercise_id, :seconds)'),
                    {'user_id': user_id, 'exercise_id': exercise_id, 'seconds': seconds})
            elif row.default_rest_seconds is None:
                bind.execute(sa.text(
                    'UPDATE gym_exercise_settings SET default_rest_seconds = :seconds '
                    'WHERE id = :id'), {'seconds': seconds, 'id': row.id})
    op.drop_table(TABLE)
