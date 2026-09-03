"""Where the Arctic Shift reader is, per subreddit and kind."""
import datetime as dt

import pytest

from app import app as flask_app
from extensions import db
from models import RadarRedditCursor


@pytest.fixture()
def clean():
    with flask_app.app_context():
        RadarRedditCursor.query.filter(RadarRedditCursor.sub.like('zzarc%')).delete(
            synchronize_session=False)
        db.session.commit()
        yield
        RadarRedditCursor.query.filter(RadarRedditCursor.sub.like('zzarc%')).delete(
            synchronize_session=False)
        db.session.commit()


def test_one_cursor_per_sub_and_kind(clean):
    now = dt.datetime(2027, 1, 1, 12, 0, 0)
    with flask_app.app_context():
        db.session.add(RadarRedditCursor(sub='zzarc', kind='comments', cursor_utc=now, updated_at=now))
        db.session.add(RadarRedditCursor(sub='zzarc', kind='posts',
                                         cursor_utc=now - dt.timedelta(hours=1), updated_at=now))
        db.session.commit()

        rows = {(r.sub, r.kind): r.cursor_utc for r in
                RadarRedditCursor.query.filter_by(sub='zzarc').all()}

        assert rows == {('zzarc', 'comments'): now,
                        ('zzarc', 'posts'): now - dt.timedelta(hours=1)}
        assert db.session.get(RadarRedditCursor, ('zzarc', 'comments')).cursor_utc == now
