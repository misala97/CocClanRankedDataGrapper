"""What turning bare tokens on for Bluesky actually did.

Run an hour or two after the change is live. The flag is one line; this is the
deliverable. /biz/ looked promising too and produced three scored mentions in
fourteen hours -- the difference between a good idea and a working one is this
report.

    cd personal_apps && PYTHONPATH=. python scripts/measure_bare_tokens.py

WHAT TO LOOK FOR
    Scored volume should rise, and the top twenty should read like equities.
    If IA, GOP, AP or similar are back among them, set
    BARE_TOKENS_ALLOWED['bluesky'] = False and the board is unharmed -- the
    junk was only ever stored, never counted.

    The promotion rate is the mechanism this rests on. If it is near zero,
    bare tokens are accumulating as `low` and contributing nothing, which
    means the change bought storage rather than signal.
"""
import datetime as dt

import sqlalchemy as sa

from app import app
from extensions import db
from models import RadarBucketSource, RadarMention, RadarPost

HOURS = 2


def main():
    with app.app_context():
        # Naive UTC, the convention every datetime here is stored in.
        # datetime.utcnow() is deprecated and was already removed from the
        # daemon once for printing a warning into the service log.
        now = dt.datetime.now(dt.timezone.utc).replace(tzinfo=None)
        since = now - dt.timedelta(hours=HOURS)

        by_conf = dict(db.session.query(
            RadarMention.confidence, sa.func.count())
            .join(RadarPost, RadarPost.id == RadarMention.post_id)
            .filter(RadarPost.source == 'bluesky',
                    RadarPost.created_utc >= since)
            .group_by(RadarMention.confidence).all())

        total = sum(by_conf.values())
        if not total:
            print(f'no bluesky mentions in the last {HOURS}h at all -- either '
                  f'ingest is down or the deploy has not happened yet')
            return

        scored = by_conf.get('high', 0) + by_conf.get('medium', 0)
        print(f'bluesky mentions in {HOURS}h: {by_conf}')
        print(f'  scored (high+medium): {scored}  ({scored / total:.0%} of extracted)')
        print(f'  low -> medium promotion rate: '
              f'{by_conf.get("medium", 0) / max(by_conf.get("low", 1), 1):.3f}')

        print('\ntop 20 by SCORED mentions -- these must look like equities:')
        rows = (db.session.query(RadarMention.ticker, sa.func.count())
                .join(RadarPost, RadarPost.id == RadarMention.post_id)
                .filter(RadarPost.source == 'bluesky',
                        RadarPost.created_utc >= since,
                        RadarMention.confidence.in_(('high', 'medium')))
                .group_by(RadarMention.ticker)
                .order_by(sa.func.count().desc()).limit(20).all())
        for ticker, count in rows:
            print(f'  {ticker:8s} {count}')

        ratio = (db.session.query(sa.func.avg(
            RadarBucketSource.distinct_text_ratio))
            .filter(RadarBucketSource.source == 'bluesky',
                    RadarBucketSource.bucket_start >= since).scalar())
        print(f'\nmean distinct_text_ratio: {float(ratio):.2f}' if ratio
              else '\nno buckets written yet')


if __name__ == '__main__':
    main()
