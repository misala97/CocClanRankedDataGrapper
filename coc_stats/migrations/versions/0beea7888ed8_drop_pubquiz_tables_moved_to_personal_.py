"""drop pubquiz tables (moved to personal_apps)

Revision ID: 0beea7888ed8
Revises: ed406b91c2dd
Create Date: 2026-06-17 17:40:24.068592

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import mysql

# revision identifiers, used by Alembic.
revision = '0beea7888ed8'
down_revision = 'ed406b91c2dd'
branch_labels = None
depends_on = None


def upgrade():
    op.drop_table('pubquiz_teams')
    op.drop_table('pubquiz_rounds')


def downgrade():
    op.create_table('pubquiz_rounds',
    sa.Column('id', mysql.INTEGER(), autoincrement=True, nullable=False),
    sa.Column('datum', mysql.DATETIME(), nullable=True),
    sa.Column('bilderrunde', mysql.VARCHAR(collation='utf8mb4_general_ci', length=100), nullable=True),
    sa.Column('quizmaster', mysql.VARCHAR(collation='utf8mb4_general_ci', length=100), nullable=True),
    sa.PrimaryKeyConstraint('id'),
    mysql_collate='utf8mb4_general_ci',
    mysql_default_charset='utf8mb4',
    mysql_engine='InnoDB'
    )
    op.create_table('pubquiz_teams',
    sa.Column('id', mysql.INTEGER(), autoincrement=True, nullable=False),
    sa.Column('name', mysql.VARCHAR(collation='utf8mb4_general_ci', length=100), nullable=True),
    sa.Column('round_id', mysql.INTEGER(), autoincrement=False, nullable=True),
    sa.Column('round1_points', mysql.FLOAT(), nullable=True),
    sa.Column('round2_points', mysql.FLOAT(), nullable=True),
    sa.Column('round3_points', mysql.FLOAT(), nullable=True),
    sa.Column('round1_size', mysql.INTEGER(), autoincrement=False, nullable=True),
    sa.Column('round2_size', mysql.INTEGER(), autoincrement=False, nullable=True),
    sa.Column('round3_size', mysql.INTEGER(), autoincrement=False, nullable=True),
    sa.Column('round4_points', mysql.FLOAT(), nullable=True),
    sa.Column('round4_size', mysql.INTEGER(), autoincrement=False, nullable=True),
    sa.ForeignKeyConstraint(['round_id'], ['pubquiz_rounds.id'], name=op.f('pubquiz_teams_ibfk_1')),
    sa.PrimaryKeyConstraint('id'),
    mysql_collate='utf8mb4_general_ci',
    mysql_default_charset='utf8mb4',
    mysql_engine='InnoDB'
    )
