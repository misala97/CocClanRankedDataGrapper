"""add CWL tables

Revision ID: a1b2c3d4e5f6
Revises: f1a2b3c4d5e6
Branch_labels = None
Depends_on = None

Create Date: 2026-06-02 00:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


revision = 'a1b2c3d4e5f6'
down_revision = 'f1a2b3c4d5e6'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        'cwl_season',
        sa.Column('id',           sa.Integer(),    nullable=False, autoincrement=True),
        sa.Column('season',       sa.String(10),   nullable=False),
        sa.Column('state',        sa.String(20),   nullable=True),
        sa.Column('league_name',  sa.String(50),   nullable=True),
        sa.Column('last_updated', sa.DateTime(),   nullable=True),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('season'),
    )
    op.create_table(
        'cwl_clan',
        sa.Column('id',        sa.Integer(),    nullable=False, autoincrement=True),
        sa.Column('season_id', sa.Integer(),    nullable=False),
        sa.Column('tag',       sa.String(30),   nullable=False),
        sa.Column('name',      sa.String(100),  nullable=True),
        sa.Column('badge_url', sa.String(200),  nullable=True),
        sa.ForeignKeyConstraint(['season_id'], ['cwl_season.id']),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_table(
        'cwl_clan_member',
        sa.Column('id',              sa.Integer(),  nullable=False, autoincrement=True),
        sa.Column('clan_id',         sa.Integer(),  nullable=False),
        sa.Column('player_tag',      sa.String(30), nullable=True),
        sa.Column('player_name',     sa.String(100),nullable=True),
        sa.Column('town_hall_level', sa.Integer(),  nullable=True),
        sa.Column('ranked_league',   sa.String(50), nullable=True),
        sa.Column('is_rushed',       sa.Boolean(),  nullable=False, server_default=sa.false()),
        sa.Column('is_troll',        sa.Boolean(),  nullable=False, server_default=sa.false()),
        sa.ForeignKeyConstraint(['clan_id'], ['cwl_clan.id']),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_table(
        'cwl_war',
        sa.Column('id',                   sa.Integer(),  nullable=False, autoincrement=True),
        sa.Column('season_id',            sa.Integer(),  nullable=False),
        sa.Column('round_number',         sa.Integer(),  nullable=False),
        sa.Column('war_tag',              sa.String(50), nullable=False),
        sa.Column('state',                sa.String(20), nullable=True),
        sa.Column('start_time',           sa.DateTime(), nullable=True),
        sa.Column('end_time',             sa.DateTime(), nullable=True),
        sa.Column('team_size',            sa.Integer(),  nullable=True),
        sa.Column('clan_tag',             sa.String(30), nullable=True),
        sa.Column('clan_name',            sa.String(100),nullable=True),
        sa.Column('clan_badge',           sa.String(200),nullable=True),
        sa.Column('clan_stars',           sa.Integer(),  nullable=True),
        sa.Column('clan_attacks',         sa.Integer(),  nullable=True),
        sa.Column('clan_destruction_pct', sa.Float(),    nullable=True),
        sa.Column('opp_tag',              sa.String(30), nullable=True),
        sa.Column('opp_name',             sa.String(100),nullable=True),
        sa.Column('opp_badge',            sa.String(200),nullable=True),
        sa.Column('opp_stars',            sa.Integer(),  nullable=True),
        sa.Column('opp_attacks',          sa.Integer(),  nullable=True),
        sa.Column('opp_destruction_pct',  sa.Float(),    nullable=True),
        sa.ForeignKeyConstraint(['season_id'], ['cwl_season.id']),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_table(
        'cwl_member',
        sa.Column('id',               sa.Integer(),  nullable=False, autoincrement=True),
        sa.Column('war_id',           sa.Integer(),  nullable=False),
        sa.Column('clan_tag',         sa.String(30), nullable=True),
        sa.Column('player_tag',       sa.String(30), nullable=True),
        sa.Column('player_name',      sa.String(100),nullable=True),
        sa.Column('town_hall_level',  sa.Integer(),  nullable=True),
        sa.Column('map_position',     sa.Integer(),  nullable=True),
        sa.Column('is_opponent',      sa.Boolean(),  nullable=True),
        sa.Column('ranked_league',    sa.String(50), nullable=True),
        sa.Column('opponent_attacks', sa.Integer(),  nullable=True, server_default='0'),
        sa.Column('is_rushed',        sa.Boolean(),  nullable=False, server_default=sa.false()),
        sa.Column('is_troll',         sa.Boolean(),  nullable=False, server_default=sa.false()),
        sa.ForeignKeyConstraint(['war_id'], ['cwl_war.id']),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_table(
        'cwl_attack',
        sa.Column('id',              sa.Integer(), nullable=False, autoincrement=True),
        sa.Column('war_id',          sa.Integer(), nullable=False),
        sa.Column('attacker_tag',    sa.String(30),nullable=True),
        sa.Column('defender_tag',    sa.String(30),nullable=True),
        sa.Column('stars',           sa.Integer(), nullable=True),
        sa.Column('destruction_pct', sa.Float(),   nullable=True),
        sa.Column('attack_order',    sa.Integer(), nullable=True),
        sa.Column('duration',        sa.Integer(), nullable=True),
        sa.ForeignKeyConstraint(['war_id'], ['cwl_war.id']),
        sa.PrimaryKeyConstraint('id'),
    )


def downgrade():
    op.drop_table('cwl_attack',       if_exists=True)
    op.drop_table('cwl_member',       if_exists=True)
    op.drop_table('cwl_war',          if_exists=True)
    op.drop_table('cwl_clan_member',  if_exists=True)
    op.drop_table('cwl_clan',         if_exists=True)
    op.drop_table('cwl_season',       if_exists=True)
