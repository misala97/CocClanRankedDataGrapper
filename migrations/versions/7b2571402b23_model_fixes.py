"""model fixes

Revision ID: 7b2571402b23
Revises: 8b5d51eeb000
Create Date: 2026-06-03 14:53:43.880776

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import mysql

revision = '7b2571402b23'
down_revision = '8b5d51eeb000'
branch_labels = None
depends_on = None


def _col_exists(conn, table, col):
    row = conn.execute(sa.text(
        "SELECT COUNT(*) FROM INFORMATION_SCHEMA.COLUMNS "
        "WHERE TABLE_SCHEMA=DATABASE() AND TABLE_NAME=:t AND COLUMN_NAME=:c"
    ), {'t': table, 'c': col}).scalar()
    return row > 0

def _col_type(conn, table, col):
    row = conn.execute(sa.text(
        "SELECT DATA_TYPE FROM INFORMATION_SCHEMA.COLUMNS "
        "WHERE TABLE_SCHEMA=DATABASE() AND TABLE_NAME=:t AND COLUMN_NAME=:c"
    ), {'t': table, 'c': col}).first()
    return row[0] if row else None

def _fk_exists(conn, table, fk_name):
    row = conn.execute(sa.text(
        "SELECT COUNT(*) FROM INFORMATION_SCHEMA.TABLE_CONSTRAINTS "
        "WHERE TABLE_SCHEMA=DATABASE() AND TABLE_NAME=:t AND CONSTRAINT_NAME=:n"
    ), {'t': table, 'n': fk_name}).scalar()
    return row > 0

def _index_exists(conn, table, idx_name):
    row = conn.execute(sa.text(
        "SELECT COUNT(*) FROM INFORMATION_SCHEMA.STATISTICS "
        "WHERE TABLE_SCHEMA=DATABASE() AND TABLE_NAME=:t AND INDEX_NAME=:n"
    ), {'t': table, 'n': idx_name}).scalar()
    return row > 0

def _fk_name_for_column(conn, table, column):
    """Return the FK constraint name for a given column, or None if not found."""
    row = conn.execute(sa.text(
        "SELECT CONSTRAINT_NAME FROM INFORMATION_SCHEMA.KEY_COLUMN_USAGE "
        "WHERE TABLE_SCHEMA=DATABASE() AND TABLE_NAME=:t AND COLUMN_NAME=:c "
        "AND REFERENCED_TABLE_NAME IS NOT NULL LIMIT 1"
    ), {'t': table, 'c': column}).first()
    return row[0] if row else None


def upgrade():
    conn = op.get_bind()

    # ── fix #8: in_group_chat NOT NULL ────────────────────────────────────────
    op.execute(sa.text("UPDATE player SET in_group_chat = 0 WHERE in_group_chat IS NULL"))
    with op.batch_alter_table('player') as batch_op:
        batch_op.alter_column('in_group_chat',
            existing_type=mysql.TINYINT(display_width=1), nullable=False)

    # ── fix #1: opponent_th String → Integer ─────────────────────────────────
    if _col_type(conn, 'ranked_battle_log', 'opponent_th') in ('varchar', 'char'):
        with op.batch_alter_table('ranked_battle_log') as batch_op:
            batch_op.alter_column('opponent_th',
                existing_type=mysql.VARCHAR(length=100),
                type_=sa.Integer(), existing_nullable=True)

    # ── fix #6: duration String → Float ──────────────────────────────────────
    if _col_type(conn, 'uptime_tracker', 'duration') in ('varchar', 'char'):
        with op.batch_alter_table('uptime_tracker') as batch_op:
            batch_op.alter_column('duration',
                existing_type=mysql.VARCHAR(length=50),
                type_=sa.Float(), existing_nullable=True)

    # ── fix #9: add clan_tag to clan_war ─────────────────────────────────────
    if not _col_exists(conn, 'clan_war', 'clan_tag'):
        with op.batch_alter_table('clan_war') as batch_op:
            batch_op.add_column(sa.Column('clan_tag', sa.String(30), nullable=True))

    # ── fix #3: battle_log surrogate PK ──────────────────────────────────────
    if not _col_exists(conn, 'battle_log', 'id'):
        fk_bl = _fk_name_for_column(conn, 'battle_log', 'player_tag')
        if fk_bl:
            op.execute(sa.text(f"ALTER TABLE battle_log DROP FOREIGN KEY `{fk_bl}`"))
        op.execute(sa.text("ALTER TABLE battle_log ADD COLUMN id INT AUTO_INCREMENT UNIQUE FIRST"))
        op.execute(sa.text("ALTER TABLE battle_log DROP PRIMARY KEY"))
        op.execute(sa.text("ALTER TABLE battle_log ADD PRIMARY KEY (id)"))
        if not _index_exists(conn, 'battle_log', 'uq_battle_log'):
            op.execute(sa.text(
                "ALTER TABLE battle_log ADD UNIQUE KEY uq_battle_log "
                "(player_tag, opponent_tag, loot_gold, loot_elixir, loot_dark_elixir)"
            ))
        if not _fk_name_for_column(conn, 'battle_log', 'player_tag'):
            op.execute(sa.text(
                "ALTER TABLE battle_log ADD CONSTRAINT battle_log_ibfk_1 "
                "FOREIGN KEY (player_tag) REFERENCES player (tag)"
            ))

    # ── fix #4+#5: RaidWeekend — rename camelCase → snake_case ───────────────
    if _col_exists(conn, 'raid_weekend', 'startTime'):
        op.execute(sa.text("ALTER TABLE raid_weekend CHANGE COLUMN startTime start_time DATETIME NOT NULL"))
        op.execute(sa.text("ALTER TABLE raid_weekend CHANGE COLUMN endTime end_time DATETIME NOT NULL"))
        op.execute(sa.text("ALTER TABLE raid_weekend CHANGE COLUMN capitalTotalLoot capital_total_loot INT"))
        op.execute(sa.text("ALTER TABLE raid_weekend CHANGE COLUMN raidsCompleted raids_completed INT"))
        op.execute(sa.text("ALTER TABLE raid_weekend CHANGE COLUMN totalAttacks total_attacks INT"))
        op.execute(sa.text("ALTER TABLE raid_weekend CHANGE COLUMN enemyDistrictsDestroyed enemy_districts_destroyed INT"))
        op.execute(sa.text("ALTER TABLE raid_weekend CHANGE COLUMN offensiveReward offensive_reward INT"))
        op.execute(sa.text("ALTER TABLE raid_weekend CHANGE COLUMN defensiveReward defensive_reward INT"))
    if not _index_exists(conn, 'raid_weekend', 'uq_raid_weekend'):
        op.execute(sa.text(
            "ALTER TABLE raid_weekend ADD UNIQUE KEY uq_raid_weekend (start_time, end_time)"
        ))

    # ── fix #2+#5: RaidWeekendLog — rename camelCase → snake_case ────────────
    if _col_exists(conn, 'raid_weekend_log', 'defenderName'):
        op.execute(sa.text("ALTER TABLE raid_weekend_log CHANGE COLUMN defenderName defender_name VARCHAR(30)"))
        op.execute(sa.text("ALTER TABLE raid_weekend_log CHANGE COLUMN defenderTag defender_tag VARCHAR(30)"))
        op.execute(sa.text("ALTER TABLE raid_weekend_log CHANGE COLUMN districtName district_name VARCHAR(30)"))
        op.execute(sa.text("ALTER TABLE raid_weekend_log CHANGE COLUMN districLevel district_level INT"))
        op.execute(sa.text("ALTER TABLE raid_weekend_log CHANGE COLUMN totalLootAllAttacks total_loot_all_attacks INT"))
        op.execute(sa.text("ALTER TABLE raid_weekend_log CHANGE COLUMN percentageTotal percentage_total INT"))
        fk_rwl = _fk_name_for_column(conn, 'raid_weekend_log', 'playerTag')
        if fk_rwl:
            op.execute(sa.text(f"ALTER TABLE raid_weekend_log DROP FOREIGN KEY `{fk_rwl}`"))
        op.execute(sa.text("ALTER TABLE raid_weekend_log CHANGE COLUMN playerTag player_tag VARCHAR(50)"))
        if not _fk_name_for_column(conn, 'raid_weekend_log', 'player_tag'):
            op.execute(sa.text(
                "ALTER TABLE raid_weekend_log ADD CONSTRAINT raid_weekend_log_player_fk "
                "FOREIGN KEY (player_tag) REFERENCES player (tag)"
            ))


def downgrade():
    conn = op.get_bind()

    if _col_exists(conn, 'raid_weekend_log', 'player_tag'):
        if _fk_exists(conn, 'raid_weekend_log', 'raid_weekend_log_player_fk'):
            op.execute(sa.text("ALTER TABLE raid_weekend_log DROP FOREIGN KEY raid_weekend_log_player_fk"))
        op.execute(sa.text("ALTER TABLE raid_weekend_log CHANGE COLUMN player_tag playerTag VARCHAR(50)"))
        if not _fk_exists(conn, 'raid_weekend_log', 'raid_weekend_log_ibfk_1'):
            op.execute(sa.text(
                "ALTER TABLE raid_weekend_log ADD CONSTRAINT raid_weekend_log_ibfk_1 "
                "FOREIGN KEY (playerTag) REFERENCES player (tag)"
            ))
        op.execute(sa.text("ALTER TABLE raid_weekend_log CHANGE COLUMN percentage_total percentageTotal INT"))
        op.execute(sa.text("ALTER TABLE raid_weekend_log CHANGE COLUMN total_loot_all_attacks totalLootAllAttacks INT"))
        op.execute(sa.text("ALTER TABLE raid_weekend_log CHANGE COLUMN district_level districLevel INT"))
        op.execute(sa.text("ALTER TABLE raid_weekend_log CHANGE COLUMN district_name districtName VARCHAR(30)"))
        op.execute(sa.text("ALTER TABLE raid_weekend_log CHANGE COLUMN defender_tag defenderTag VARCHAR(30)"))
        op.execute(sa.text("ALTER TABLE raid_weekend_log CHANGE COLUMN defender_name defenderName VARCHAR(30)"))

    if _col_exists(conn, 'raid_weekend', 'start_time'):
        if _index_exists(conn, 'raid_weekend', 'uq_raid_weekend'):
            op.execute(sa.text("ALTER TABLE raid_weekend DROP INDEX uq_raid_weekend"))
        op.execute(sa.text("ALTER TABLE raid_weekend CHANGE COLUMN defensive_reward defensiveReward INT"))
        op.execute(sa.text("ALTER TABLE raid_weekend CHANGE COLUMN offensive_reward offensiveReward INT"))
        op.execute(sa.text("ALTER TABLE raid_weekend CHANGE COLUMN enemy_districts_destroyed enemyDistrictsDestroyed INT"))
        op.execute(sa.text("ALTER TABLE raid_weekend CHANGE COLUMN total_attacks totalAttacks INT"))
        op.execute(sa.text("ALTER TABLE raid_weekend CHANGE COLUMN raids_completed raidsCompleted INT"))
        op.execute(sa.text("ALTER TABLE raid_weekend CHANGE COLUMN capital_total_loot capitalTotalLoot INT"))
        op.execute(sa.text("ALTER TABLE raid_weekend CHANGE COLUMN end_time endTime DATETIME NOT NULL"))
        op.execute(sa.text("ALTER TABLE raid_weekend CHANGE COLUMN start_time startTime DATETIME NOT NULL"))

    if _col_exists(conn, 'battle_log', 'id'):
        if _fk_exists(conn, 'battle_log', 'battle_log_ibfk_1'):
            op.execute(sa.text("ALTER TABLE battle_log DROP FOREIGN KEY battle_log_ibfk_1"))
        if _index_exists(conn, 'battle_log', 'uq_battle_log'):
            op.execute(sa.text("ALTER TABLE battle_log DROP INDEX uq_battle_log"))
        op.execute(sa.text("ALTER TABLE battle_log DROP PRIMARY KEY"))
        op.execute(sa.text("ALTER TABLE battle_log DROP COLUMN id"))
        op.execute(sa.text(
            "ALTER TABLE battle_log ADD PRIMARY KEY "
            "(player_tag, opponent_tag, loot_gold, loot_elixir, loot_dark_elixir)"
        ))
        op.execute(sa.text(
            "ALTER TABLE battle_log ADD CONSTRAINT battle_log_ibfk_1 "
            "FOREIGN KEY (player_tag) REFERENCES player (tag)"
        ))

    if _col_exists(conn, 'clan_war', 'clan_tag'):
        with op.batch_alter_table('clan_war') as batch_op:
            batch_op.drop_column('clan_tag')

    with op.batch_alter_table('uptime_tracker') as batch_op:
        batch_op.alter_column('duration',
            existing_type=sa.Float(),
            type_=mysql.VARCHAR(length=50), existing_nullable=True)

    with op.batch_alter_table('ranked_battle_log') as batch_op:
        batch_op.alter_column('opponent_th',
            existing_type=sa.Integer(),
            type_=mysql.VARCHAR(length=100), existing_nullable=True)

    with op.batch_alter_table('player') as batch_op:
        batch_op.alter_column('in_group_chat',
            existing_type=mysql.TINYINT(display_width=1), nullable=True)
