"""add user_id to the three gym root tables

Revision ID: b7d93a5c1e40
Revises: a4c81f2e5b76
Create Date: 2026-08-02 00:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'b7d93a5c1e40'
down_revision = 'a4c81f2e5b76'
branch_labels = None
depends_on = None

_TABLES = ('gym_workout_sessions', 'gym_workout_templates', 'gym_push_subscriptions')


def upgrade():
    connection = op.get_bind()
    admin_id = connection.execute(sa.text(
        'SELECT id FROM app_user WHERE is_admin = 1 ORDER BY id LIMIT 1')).scalar()
    if admin_id is None:
        raise RuntimeError(
            'no admin account to backfill ownership to -- run the a4c81f2e5b76 '
            'migration first, which seeds it.')

    # Added nullable, backfilled, then tightened. Doing it in one step would
    # fail against a non-empty table, and doing it without the backfill would
    # leave every existing row violating the constraint.
    for table in _TABLES:
        with op.batch_alter_table(table, schema=None) as batch_op:
            batch_op.add_column(sa.Column('user_id', sa.Integer(), nullable=True))

    for table in _TABLES:
        connection.execute(
            sa.text(f'UPDATE {table} SET user_id = :admin_id WHERE user_id IS NULL'),
            {'admin_id': admin_id},
        )

    for table in _TABLES:
        with op.batch_alter_table(table, schema=None) as batch_op:
            batch_op.alter_column('user_id', existing_type=sa.Integer(), nullable=False)
            batch_op.create_index(f'ix_{table}_user_id', ['user_id'])
            batch_op.create_foreign_key(f'fk_{table}_user_id', 'app_user', ['user_id'], ['id'])


def downgrade():
    for table in _TABLES:
        with op.batch_alter_table(table, schema=None) as batch_op:
            batch_op.drop_constraint(f'fk_{table}_user_id', type_='foreignkey')
            batch_op.drop_index(f'ix_{table}_user_id')
            batch_op.drop_column('user_id')
