"""LOCAL-QA environment step: schema from candidate migrations + one local admin.

    py -3.12 ../radar-design/artifacts/ha1/local-qa/env_migrate.py   (cwd personal_apps)

Gated by scratchpad/ha1/local_runtime.gate()/bind() (RADAR_HA1_TARGET +
RADAR_HA1_REGISTRY + destructive_target.require) BEFORE any SQL. Runs
`flask db upgrade` (flask_migrate.upgrade) against the new disposable HA1
database only, then creates the environment-owned local admin account named in
RADAR_HA1_USER if absent. Prints no secret. Synthetic, local-only.
"""
import os
import sys
from pathlib import Path

PERSONAL = Path(__file__).resolve().parents[4] / 'personal_apps'
sys.path.insert(0, str(PERSONAL))
sys.path.insert(0, str(PERSONAL / 'scratchpad' / 'ha1'))
os.chdir(PERSONAL)

import local_runtime  # noqa: E402

host, port, database, target, registry = local_runtime.gate()
app = local_runtime.bind(host, port, database, target, registry)

from flask_migrate import upgrade  # noqa: E402
import sqlalchemy as sa  # noqa: E402
from werkzeug.security import generate_password_hash  # noqa: E402

from extensions import db  # noqa: E402
from models import AppUser  # noqa: E402

with app.app_context():
    upgrade(directory=str(PERSONAL / 'migrations'))
    head = db.session.execute(sa.text('SELECT version_num FROM alembic_version')).scalar()
    tables = sorted(sa.inspect(db.engine).get_table_names())
    username = os.environ['RADAR_HA1_USER']
    user = AppUser.query.filter_by(username=username).first()
    if user is None:
        user = AppUser(username=username, password_hash=generate_password_hash(os.environ['RADAR_HA1_PASSWORD']),
                       is_admin=True)
        db.session.add(user)
        db.session.commit()
        created = True
    else:
        created = False
    print(f'target={target} alembic_head={head} tables={len(tables)} '
          f'admin={username} id={user.id} created={created}')
