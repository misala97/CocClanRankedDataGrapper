"""Seed the B1C disposable database: the dev board plus two local accounts.

Runs `scratchpad/seed_radar_dev.py` -- which DELETES every radar table it
writes -- but only after the bound database has passed BOTH destructive gates
(`destructive_target.require`: the exact host:port/database opt-in and the
independently provisioned registry). The worktree `.env` names
`personal_apps_radar_b1c`; the gate is what proves that is what is bound, so
a stale `.env` cannot point this at TE1, B1, PERF3 or the dev database.

    cd personal_apps
    RADAR_DESTRUCTIVE_TEST_TARGET=localhost:3306/personal_apps_radar_b1c \
    RADAR_DESTRUCTIVE_TEST_REGISTRY=<abs path to registry json> \
    PYTHONPATH=. py -3.12 scratchpad/b1c/seed_b1c.py

The two accounts exist only in this database: `b1cadmin` (admin) and
`b1cplain`, password `b1c-local-only`. Nothing here is production tooling.
"""
import pathlib
import sys

HERE = pathlib.Path(__file__).resolve().parent
APP_DIR = HERE.parents[1]
for path in (str(APP_DIR), str(APP_DIR / 'scratchpad')):
    if path not in sys.path:
        sys.path.insert(0, path)

from werkzeug.security import generate_password_hash  # noqa: E402

import destructive_target  # noqa: E402
from app import app  # noqa: E402
from extensions import db  # noqa: E402
from models import AppUser  # noqa: E402

ACCOUNTS = (('b1cadmin', True), ('b1cplain', False))
PASSWORD = 'b1c-local-only'


def preflight():
    with app.app_context():
        target = destructive_target.require(db.engine.url)
    print(f'destructive gate passed for {target}')
    return target


def accounts():
    with app.app_context():
        for username, is_admin in ACCOUNTS:
            row = AppUser.query.filter_by(username=username).one_or_none()
            if row is None:
                row = AppUser(username=username,
                              password_hash=generate_password_hash(PASSWORD),
                              is_admin=is_admin)
                db.session.add(row)
            else:
                row.password_hash = generate_password_hash(PASSWORD)
                row.is_admin = is_admin
        db.session.commit()
        print('accounts:', [(u.username, u.is_admin)
                            for u in AppUser.query.order_by(AppUser.id).all()])


def main():
    preflight()
    accounts()
    import seed_radar_dev
    seed_radar_dev.main()


if __name__ == '__main__':
    main()
