"""add linked_player_tag to app_user

Revision ID: 2f372debbd6b
Revises: 7b2571402b23
Create Date: 2026-06-04 17:49:50.497803

"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = '2f372debbd6b'
down_revision = '7b2571402b23'
branch_labels = None
depends_on = None


def upgrade():
    # Column must use utf8mb4_general_ci to match player.tag collation for FK to work.
    # Use ADD COLUMN for fresh databases; local dev had the column pre-created so was stamped directly.
    op.execute(
        "ALTER TABLE app_user "
        "ADD COLUMN linked_player_tag VARCHAR(50) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci NULL, "
        "ADD CONSTRAINT app_user_ibfk_1 FOREIGN KEY (linked_player_tag) REFERENCES player (tag)"
    )


def downgrade():
    op.execute(
        "ALTER TABLE app_user "
        "DROP FOREIGN KEY app_user_ibfk_1, "
        "DROP COLUMN linked_player_tag"
    )
