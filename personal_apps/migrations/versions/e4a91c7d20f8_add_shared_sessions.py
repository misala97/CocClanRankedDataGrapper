"""add shared sessions

Revision ID: e4a91c7d20f8
Revises: d1f6b83c25e9
Create Date: 2026-08-03 00:00:00.000000

"""
from alembic import op
import sqlalchemy as sa

revision = 'e4a91c7d20f8'
down_revision = 'd1f6b83c25e9'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        'gym_shared_sessions',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('leader_session_id', sa.Integer(), nullable=False),
        sa.Column('follower_session_id', sa.Integer(), nullable=True),
        sa.Column('leader_user_id', sa.Integer(), nullable=False),
        sa.Column('follower_user_id', sa.Integer(), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('accepted_at', sa.DateTime(), nullable=True),
        sa.Column('ended_at', sa.DateTime(), nullable=True),
        sa.PrimaryKeyConstraint('id'),
        sa.ForeignKeyConstraint(['leader_session_id'], ['gym_workout_sessions.id'],
                                name='fk_gym_shared_sessions_leader_session'),
        sa.ForeignKeyConstraint(['follower_session_id'], ['gym_workout_sessions.id'],
                                name='fk_gym_shared_sessions_follower_session'),
        sa.ForeignKeyConstraint(['leader_user_id'], ['app_user.id'],
                                name='fk_gym_shared_sessions_leader_user'),
        sa.ForeignKeyConstraint(['follower_user_id'], ['app_user.id'],
                                name='fk_gym_shared_sessions_follower_user'),
        sa.UniqueConstraint('leader_session_id', 'follower_user_id',
                            name='uq_gym_shared_sessions_leader_session_follower'),
    )
    op.create_index('ix_gym_shared_sessions_leader_session_id',
                    'gym_shared_sessions', ['leader_session_id'])
    op.create_index('ix_gym_shared_sessions_follower_user_id',
                    'gym_shared_sessions', ['follower_user_id'])

    op.create_table(
        'gym_shared_session_exercises',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('shared_session_id', sa.Integer(), nullable=False),
        sa.Column('leader_exercise_id', sa.Integer(), nullable=False),
        sa.Column('follower_exercise_id', sa.Integer(), nullable=False),
        sa.PrimaryKeyConstraint('id'),
        sa.ForeignKeyConstraint(['shared_session_id'], ['gym_shared_sessions.id'],
                                name='fk_gym_shared_session_exercises_link'),
        sa.ForeignKeyConstraint(['leader_exercise_id'], ['gym_exercises.id'],
                                name='fk_gym_shared_session_exercises_leader_exercise'),
        sa.ForeignKeyConstraint(['follower_exercise_id'], ['gym_exercises.id'],
                                name='fk_gym_shared_session_exercises_follower_exercise'),
        sa.UniqueConstraint('shared_session_id', 'leader_exercise_id',
                            name='uq_gym_shared_session_exercises_link_leader'),
    )
    op.create_index('ix_gym_shared_session_exercises_shared_session_id',
                    'gym_shared_session_exercises', ['shared_session_id'])

    op.add_column('gym_session_exercises',
                  sa.Column('mirrors_id', sa.Integer(), nullable=True))
    op.create_foreign_key('fk_gym_session_exercises_mirrors',
                          'gym_session_exercises', 'gym_session_exercises',
                          ['mirrors_id'], ['id'], ondelete='SET NULL')

    op.add_column('gym_workout_sessions',
                  sa.Column('structure_version', sa.Integer(), nullable=False,
                            server_default='0'))


def downgrade():
    op.drop_column('gym_workout_sessions', 'structure_version')
    op.drop_constraint('fk_gym_session_exercises_mirrors',
                       'gym_session_exercises', type_='foreignkey')
    op.drop_column('gym_session_exercises', 'mirrors_id')
    # No explicit drop_index calls here: on MySQL/InnoDB, an index backing a
    # still-live FK constraint on the same table cannot be dropped on its own
    # (error 1553) -- it has to go together with the constraint. drop_table
    # removes the table's indexes and FK constraints in one shot, so letting
    # it do that is both simpler and the only ordering that actually works.
    op.drop_table('gym_shared_session_exercises')
    op.drop_table('gym_shared_sessions')
