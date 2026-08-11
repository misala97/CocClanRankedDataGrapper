"""cascade delete shared session exercise fks

Revision ID: d98add219b32
Revises: e4a91c7d20f8
Create Date: 2026-08-03 07:58:32.657834

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'd98add219b32'
down_revision = 'e4a91c7d20f8'
branch_labels = None
depends_on = None


def upgrade():
    # A spent gym_shared_session_exercises row is not a reason to keep a
    # catalogue Exercise alive -- see the SharedSessionExercise docstring in
    # models.py. Without ondelete='CASCADE' here, an exercise referenced only
    # by this map (the exercise-map-with-no-SessionExercise case) could never
    # be deleted: gym_delete_exercise's in-use check knows nothing about this
    # table, so the delete would hit an unhandled IntegrityError instead of
    # the route's existing friendly refusal.
    op.drop_constraint('fk_gym_shared_session_exercises_leader_exercise',
                       'gym_shared_session_exercises', type_='foreignkey')
    op.drop_constraint('fk_gym_shared_session_exercises_follower_exercise',
                       'gym_shared_session_exercises', type_='foreignkey')
    op.create_foreign_key('fk_gym_shared_session_exercises_leader_exercise',
                          'gym_shared_session_exercises', 'gym_exercises',
                          ['leader_exercise_id'], ['id'], ondelete='CASCADE')
    op.create_foreign_key('fk_gym_shared_session_exercises_follower_exercise',
                          'gym_shared_session_exercises', 'gym_exercises',
                          ['follower_exercise_id'], ['id'], ondelete='CASCADE')


def downgrade():
    op.drop_constraint('fk_gym_shared_session_exercises_leader_exercise',
                       'gym_shared_session_exercises', type_='foreignkey')
    op.drop_constraint('fk_gym_shared_session_exercises_follower_exercise',
                       'gym_shared_session_exercises', type_='foreignkey')
    op.create_foreign_key('fk_gym_shared_session_exercises_leader_exercise',
                          'gym_shared_session_exercises', 'gym_exercises',
                          ['leader_exercise_id'], ['id'])
    op.create_foreign_key('fk_gym_shared_session_exercises_follower_exercise',
                          'gym_shared_session_exercises', 'gym_exercises',
                          ['follower_exercise_id'], ['id'])
