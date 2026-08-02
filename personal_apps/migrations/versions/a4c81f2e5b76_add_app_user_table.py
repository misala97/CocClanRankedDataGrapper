"""add app_user table and seed the admin from the environment

Revision ID: a4c81f2e5b76
Revises: e9b4c2a71d63
Create Date: 2026-08-02 00:00:00.000000

"""
import os

from alembic import op
import sqlalchemy as sa
from werkzeug.security import generate_password_hash


# revision identifiers, used by Alembic.
revision = 'a4c81f2e5b76'
down_revision = 'e9b4c2a71d63'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        'app_user',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('username', sa.String(length=80), nullable=False),
        sa.Column('password_hash', sa.String(length=256), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('is_admin', sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('username'),
    )
    # Seed the author's account from the credentials the app authenticated
    # against until now, so the first login after deployment uses exactly the
    # username and password already in use. Task 2 then deletes the
    # environment code path entirely.
    username = os.getenv('PERSONAL_ADMIN_USER', '')
    password = os.getenv('PERSONAL_ADMIN_PASS', '')
    if not (username and password):
        raise RuntimeError(
            'PERSONAL_ADMIN_USER / PERSONAL_ADMIN_PASS must be set when running '
            'this migration -- they are the only source for the seeded admin account.')
    op.get_bind().execute(
        sa.text('INSERT INTO app_user (username, password_hash, created_at, is_admin) '
                'VALUES (:username, :password_hash, UTC_TIMESTAMP(), 1)'),
        {'username': username, 'password_hash': generate_password_hash(password)},
    )


def downgrade():
    op.drop_table('app_user')
