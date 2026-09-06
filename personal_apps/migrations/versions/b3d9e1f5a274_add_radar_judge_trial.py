"""add radar_judge_trial

The durable record of one encoder trial. It exists because switching a
removing judge off is not a rollback: by then its relevance verdicts have
already taken mentions out of bucket counts and journal eligibility, and
undoing that needs the journal, which keeps 48 hours. This row pins that
evidence and holds the stop switch, so neither depends on an environment
file surviving a restart.

Singleton by construction: id is not auto-increment and a CHECK pins it to
1. Arming refuses to overwrite an existing row -- two trials sharing one
record could not both be recovered.

One atomic DDL statement per direction, the house rule for radar
migrations: MariaDB commits DDL even when a later statement in the same
migration fails.

Revision ID: b3d9e1f5a274
Revises: a1c4f7b2e6d8
Create Date: 2026-09-06
"""
from alembic import op
import sqlalchemy as sa


revision = 'b3d9e1f5a274'
down_revision = 'a1c4f7b2e6d8'
branch_labels = None
depends_on = None


def upgrade():
    op.execute(
        'CREATE TABLE radar_judge_trial ('
        ' id INT NOT NULL,'
        ' model_id VARCHAR(40) NOT NULL,'
        ' prompt_version VARCHAR(64) NOT NULL,'
        ' artifact_sha256 VARCHAR(64) NOT NULL,'
        ' status VARCHAR(10) NOT NULL,'
        ' armed_at DATETIME(6) NOT NULL,'
        ' retain_from DATETIME(6) NOT NULL,'
        ' first_judged_at DATETIME(6) NULL,'
        ' audit_evaluated_at DATETIME(6) NULL,'
        ' audit_passed TINYINT(1) NULL,'
        ' audit_report_sha256 VARCHAR(64) NULL,'
        ' recipe JSON NOT NULL,'
        ' stop_reason TEXT NULL,'
        ' PRIMARY KEY (id),'
        " CONSTRAINT ck_radar_judge_trial_status CHECK"
        " (status IN ('armed','running','recovering','recovered')),"
        ' CONSTRAINT ck_radar_judge_trial_singleton CHECK (id = 1)'
        ') DEFAULT CHARSET=utf8mb4')


def downgrade():
    op.execute('DROP TABLE radar_judge_trial')
