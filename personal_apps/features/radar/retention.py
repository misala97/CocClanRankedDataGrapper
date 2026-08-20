"""Rolling deletion of raw text.

Buckets are never touched here. They are the queryable layer and are retained
forever; raw posts exist only long enough to be extracted from and read on a
detail page (spec 5).
"""
import datetime as dt
import time

from extensions import db
from models import RadarPost

from .config import POST_RETENTION_DAYS

# Breathing room between chunks so the daemon's next cycle is not queued behind
# a long delete on the same connection.
_CHUNK_PAUSE_SECONDS = 0.05


def prune_posts(now, chunk_size=5000, pause=_CHUNK_PAUSE_SECONDS):
    """Delete posts older than the retention window, in chunks.

    Mentions follow via ON DELETE CASCADE. Returns the number deleted.
    """
    cutoff = now - dt.timedelta(days=POST_RETENTION_DAYS)
    total = 0

    while True:
        ids = [
            row_id for (row_id,) in
            db.session.query(RadarPost.id)
            .filter(RadarPost.created_utc < cutoff)
            .order_by(RadarPost.created_utc)
            .limit(chunk_size).all()
        ]
        if not ids:
            break

        db.session.query(RadarPost).filter(RadarPost.id.in_(ids)).delete(
            synchronize_session=False)
        db.session.commit()
        total += len(ids)

        if len(ids) < chunk_size:
            break
        if pause:
            time.sleep(pause)

    return total
