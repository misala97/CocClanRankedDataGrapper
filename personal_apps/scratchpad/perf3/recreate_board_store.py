"""Recreate only PERF3's disposable cache tables for a revised migration.

Run through ``scale_env.py``. Its exact target plus registry guard executes
before Flask-Migrate can issue either DROP or CREATE.
"""
import scale_env

app = scale_env.bind()

from flask_migrate import downgrade, upgrade  # noqa: E402


with app.app_context():
    downgrade(revision='a7c31f0b52d4')
    upgrade()
print('PERF3 board store recreated on the registered scale database')
