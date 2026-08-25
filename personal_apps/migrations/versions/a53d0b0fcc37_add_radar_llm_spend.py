"""add radar_llm_spend

What the model sentiment pass costs, accumulated from the `usage` every API
response already carries. There is no balance endpoint to ask instead:
Anthropic's Cost API reports spend rather than remaining credit, needs a
separate Admin API key, and is documented as unavailable for individual
accounts.

Money is INTEGER MICROS (1 USD = 1_000_000) rather than a float column, which
would accumulate rounding on every call and then report a total nobody can
reconcile against a statement.

Additive, and nothing reads the table until it has rows -- so this is safe to
apply ahead of the code that writes it.

Revision ID: a53d0b0fcc37
Revises: d5b81c30fa27
Create Date: 2026-08-25
"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'a53d0b0fcc37'
down_revision = 'd5b81c30fa27'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table('radar_llm_spend',
    sa.Column('day', sa.Date(), nullable=False),
    sa.Column('model', sa.String(length=40), nullable=False),
    sa.Column('calls', sa.Integer(), nullable=False),
    sa.Column('input_tokens', sa.BigInteger(), nullable=False),
    sa.Column('output_tokens', sa.BigInteger(), nullable=False),
    sa.Column('cost_micros', sa.BigInteger(), nullable=False),
    sa.PrimaryKeyConstraint('day', 'model'),
    mysql_charset='utf8mb4'
    )


def downgrade():
    # Drops the spend history with it. Nothing else reads the table, and the
    # figures are reconstructible only from Anthropic's own Console.
    op.drop_table('radar_llm_spend')
