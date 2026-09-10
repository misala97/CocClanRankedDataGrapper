"""Two spike accounts with different watch lists.

The fixture ships one account (`perf1admin`) and no watches at all, so the
per-account half of the read path -- `watch.tickers_for` and
`board.build_pinned_rows` -- would otherwise never run and S2's warm number
would be missing the only per-request database work there is.

Writes to `app_user` and `radar_watch` on the DISPOSABLE fixture only.
`teardown` removes exactly what `setup` made.
"""
import datetime as dt

import sqlalchemy as sa

USERS = ('perf2_a', 'perf2_b')


def _user_id(db, username):
    return db.session.execute(sa.text(
        'SELECT id FROM app_user WHERE username = :u'), {'u': username}
    ).scalar()


def setup(db, watch_lists, now=None):
    """(id_a, id_b) for two accounts holding `watch_lists[0]` / `[1]`."""
    now = now or dt.datetime(2026, 9, 1, 0, 0, 0)
    ids = []
    for username, tickers in zip(USERS, watch_lists):
        user_id = _user_id(db, username)
        if user_id is None:
            db.session.execute(sa.text(
                'INSERT INTO app_user (username, password_hash, created_at,'
                ' is_admin) VALUES (:u, :p, :c, 0)'),
                {'u': username, 'p': 'spike-not-a-login', 'c': now})
            db.session.commit()
            user_id = _user_id(db, username)
        db.session.execute(sa.text(
            'DELETE FROM radar_watch WHERE user_id = :u'), {'u': user_id})
        for i, ticker in enumerate(tickers):
            db.session.execute(sa.text(
                'INSERT INTO radar_watch (user_id, ticker, created_at)'
                ' VALUES (:u, :t, :c)'),
                {'u': user_id, 't': ticker,
                 'c': now + dt.timedelta(seconds=i)})
        db.session.commit()
        ids.append(user_id)
    return tuple(ids)


def teardown(db):
    for username in USERS:
        user_id = _user_id(db, username)
        if user_id is None:
            continue
        db.session.execute(sa.text(
            'DELETE FROM radar_watch WHERE user_id = :u'), {'u': user_id})
        db.session.execute(sa.text(
            'DELETE FROM app_user WHERE id = :u'), {'u': user_id})
    db.session.commit()
