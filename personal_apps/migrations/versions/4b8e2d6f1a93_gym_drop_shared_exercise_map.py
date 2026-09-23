"""gym: drop the shared-session exercise map -- both partners log one list

Revision ID: 4b8e2d6f1a93
Revises: e2c7a9f41b86
Create Date: 2026-09-23 18:00:00.000000

gym_shared_session_exercises translated a leader's exercise ids into the
follower's per-user catalogue. Since e2c7a9f41b86 both partners log the same
list rows: a follower's row names the leader's exercise, so the map has nothing
left to say -- its rows map a lift to itself or belong to spent links (G3,
docs/superpowers/plans/2026-09-23-gym-first-run-workflows.md).

Guarded both ways, so a re-run is a no-op. Downgrade recreates the table empty,
as it stood after d98add219b32; the code before this revision writes its map
rows as a link needs them.
"""
import sqlalchemy as sa
from alembic import op

revision = '4b8e2d6f1a93'
down_revision = 'e2c7a9f41b86'
branch_labels = None
depends_on = None

TABLE = 'gym_shared_session_exercises'


def upgrade():
    if sa.inspect(op.get_bind()).has_table(TABLE):
        op.drop_table(TABLE)


def downgrade():
    if sa.inspect(op.get_bind()).has_table(TABLE):
        return
    op.create_table(
        TABLE,
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('shared_session_id', sa.Integer(), nullable=False),
        sa.Column('leader_exercise_id', sa.Integer(), nullable=False),
        sa.Column('follower_exercise_id', sa.Integer(), nullable=False),
        sa.PrimaryKeyConstraint('id'),
        sa.ForeignKeyConstraint(['shared_session_id'], ['gym_shared_sessions.id'],
                                name='fk_gym_shared_session_exercises_link'),
        sa.ForeignKeyConstraint(['leader_exercise_id'], ['gym_exercises.id'],
                                name='fk_gym_shared_session_exercises_leader_exercise',
                                ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['follower_exercise_id'], ['gym_exercises.id'],
                                name='fk_gym_shared_session_exercises_follower_exercise',
                                ondelete='CASCADE'),
        sa.UniqueConstraint('shared_session_id', 'leader_exercise_id',
                            name='uq_gym_shared_session_exercises_link_leader'),
    )
    op.create_index('ix_gym_shared_session_exercises_shared_session_id', TABLE,
                    ['shared_session_id'])
