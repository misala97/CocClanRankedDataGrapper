"""add user_id to gym_exercises, swap the unique constraint to (user_id, name)

Revision ID: c8e5f14a9b32
Revises: b7d93a5c1e40
Create Date: 2026-08-02 00:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'c8e5f14a9b32'
down_revision = 'b7d93a5c1e40'
branch_labels = None
depends_on = None

# Every row referencing an exercise must belong to the same user as the
# exercise. Run before any DDL: if it is already violated, the state this
# migration assumes does not hold and continuing would bake the violation in.
_CROSS_OWNER_CHECK = sa.text("""
    SELECT COUNT(*) FROM (
        SELECT te.id
          FROM gym_template_exercises te
          JOIN gym_workout_templates t ON t.id = te.template_id
          JOIN gym_exercises e ON e.id = te.exercise_id
         WHERE t.user_id <> :owner
        UNION ALL
        SELECT se.id
          FROM gym_session_exercises se
          JOIN gym_workout_sessions s ON s.id = se.session_id
          JOIN gym_exercises e ON e.id = se.exercise_id
         WHERE s.user_id <> :owner
    ) AS offenders
""")


def upgrade():
    connection = op.get_bind()
    owner = connection.execute(sa.text(
        'SELECT id FROM app_user WHERE is_admin = 1 ORDER BY id LIMIT 1')).scalar()
    if owner is None:
        raise RuntimeError('no admin account to own the existing exercises')

    # The intended state is a single-user database: the second account is
    # deleted before this runs, precisely so no exercise has to be duplicated
    # and no live foreign key repointed inside a migration. If that did not
    # happen, stop -- the alternative is silently leaving one user's templates
    # pointing at another user's lifts.
    offenders = connection.execute(_CROSS_OWNER_CHECK, {'owner': owner}).scalar()
    if offenders:
        raise RuntimeError(
            f'{offenders} template/session row(s) reference an exercise belonging to '
            f'another user. Delete those accounts first (scripts/delete_user.py), or '
            f'fork their exercises by hand before migrating.')

    with op.batch_alter_table('gym_exercises', schema=None) as batch_op:
        batch_op.add_column(sa.Column('user_id', sa.Integer(), nullable=True))

    connection.execute(
        sa.text('UPDATE gym_exercises SET user_id = :owner WHERE user_id IS NULL'),
        {'owner': owner},
    )

    with op.batch_alter_table('gym_exercises', schema=None) as batch_op:
        batch_op.alter_column('user_id', existing_type=sa.Integer(), nullable=False)
        batch_op.create_index('ix_gym_exercises_user_id', ['user_id'])
        batch_op.create_foreign_key('fk_gym_exercises_user_id', 'app_user', ['user_id'], ['id'])
        # MySQL named the original constraint after its column.
        batch_op.drop_constraint('name', type_='unique')
        batch_op.create_unique_constraint('uq_gym_exercises_user_id_name', ['user_id', 'name'])


def downgrade():
    connection = op.get_bind()
    # Lossy and it says so: restoring a global unique on `name` cannot succeed
    # while two users hold the same name, and choosing which row survives (and
    # whose weight_increment with it) has no correct answer. Restore from
    # backup instead.
    duplicates = connection.execute(sa.text(
        'SELECT COUNT(*) FROM (SELECT name FROM gym_exercises '
        'GROUP BY name HAVING COUNT(*) > 1) AS d')).scalar()
    if duplicates:
        raise RuntimeError(
            f'{duplicates} exercise name(s) are held by more than one user. Downgrading '
            f'would have to merge them and pick a surviving weight_increment, which this '
            f'migration will not guess. Restore from backup.')

    with op.batch_alter_table('gym_exercises', schema=None) as batch_op:
        batch_op.drop_constraint('uq_gym_exercises_user_id_name', type_='unique')
        batch_op.create_unique_constraint('name', ['name'])
        batch_op.drop_constraint('fk_gym_exercises_user_id', type_='foreignkey')
        batch_op.drop_index('ix_gym_exercises_user_id')
        batch_op.drop_column('user_id')
