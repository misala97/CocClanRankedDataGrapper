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
import datetime as dt
import pathlib
import sys

import sqlalchemy as sa

HERE = pathlib.Path(__file__).resolve().parent
APP_DIR = HERE.parents[1]
for path in (str(APP_DIR), str(APP_DIR / 'scratchpad')):
    if path not in sys.path:
        sys.path.insert(0, path)

from werkzeug.security import generate_password_hash  # noqa: E402

import destructive_target  # noqa: E402
from app import app  # noqa: E402
from extensions import db  # noqa: E402
from models import (AppUser, RadarBucketSource, RadarMention,
                    RadarMentionEvent, RadarPost)  # noqa: E402

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


def preview_recorded_tone(seed_module):
    """Make this owned preview exercise the recorded-judgment renderer.

    The shared dev seeder intentionally makes independent bucket and post
    populations.  B1C's production reader must expose that mismatch as grey;
    this local wrapper additionally gives the visual review a small, truthful
    green/red/mixed sample without changing production code or the generic
    seeder.  The source totals are aligned only for the retained preview
    window, using the same eligible journal population the reader joins.
    """
    now = seed_module.NOW
    retained = now - dt.timedelta(hours=48)
    with app.app_context():
        mentions = (db.session.query(RadarMention)
                    .join(RadarPost, RadarPost.id == RadarMention.post_id)
                    .filter(RadarPost.created_utc >= retained).all())
        for mention in mentions:
            score = mention.lexicon_sentiment or 0.0
            mention.sentiment_relevance = 'relevant'
            mention.sentiment_content_origin = 'human_chatter'
            mention.sentiment_attitude = (
                'positive' if score > 0.15 else
                'negative' if score < -0.15 else 'mixed')
            mention.sentiment_confidence = 'high'
            mention.sentiment_model = 'b1c-preview-recorded'
            mention.sentiment_judged_at = now

        event_counts = (db.session.query(
            RadarMentionEvent.ticker,
            RadarMentionEvent.bucket_start,
            RadarMentionEvent.source,
            sa.func.count(RadarMentionEvent.id),
        ).filter(
            RadarMentionEvent.created_utc >= retained,
            sa.or_(RadarMentionEvent.confidence == 'high',
                   RadarMentionEvent.promoted.is_(True)),
            sa.or_(RadarMentionEvent.counts_as_human_chatter.is_(None),
                   RadarMentionEvent.counts_as_human_chatter.is_(True)),
        ).group_by(
            RadarMentionEvent.ticker,
            RadarMentionEvent.bucket_start,
            RadarMentionEvent.source,
        ).all())
        counts = {(ticker, bucket, source): count
                  for ticker, bucket, source, count in event_counts}
        rows = (RadarBucketSource.query
                .filter(RadarBucketSource.bucket_start >= retained).all())
        for row in rows:
            row.mention_count = counts.get(
                (row.ticker, row.bucket_start, row.source), 0)
        db.session.commit()
        print(f'preview recorded judgments={len(mentions)} '
              f'aligned source rows={len(rows)}')


def main():
    preflight()
    accounts()
    import seed_radar_dev
    seed_radar_dev.main()
    preview_recorded_tone(seed_radar_dev)


if __name__ == '__main__':
    main()
