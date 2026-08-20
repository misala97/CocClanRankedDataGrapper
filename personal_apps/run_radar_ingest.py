# personal_apps/run_radar_ingest.py
"""Radar ingest daemon.

Mirrors run_gym_notifier.py: an APScheduler process holding a Flask app context,
deployed as its own systemd unit and restarted by the VPS deploy script.

Cadence is chosen per cycle from the NYSE session rather than fixed, because
chatter volume follows the session and polling overnight at session rates is
wasted work. The state comes from the exchange calendar, never from local time
-- see the DST note in features/radar/market_calendar.py.
"""
import datetime as dt
import logging
import os

from apscheduler.schedulers.background import BackgroundScheduler

from app import app
from features.radar import ingest, market_calendar, retention
from features.radar.config import SUBREDDITS
from features.radar.sources import reddit

logger = logging.getLogger('radar.ingest')

INTERVALS = {
    'premarket': 180,
    'regular': 180,
    'afterhours': 600,
    'closed': 1800,
}
# An unrecognized state polls at the slowest rate. Failing towards fewer API
# calls is the safe direction when the alternative is hammering Reddit.
FALLBACK_INTERVAL = 1800


def interval_for(state):
    return INTERVALS.get(state, FALLBACK_INTERVAL)


def current_state(now_utc):
    return market_calendar.session_state(now_utc)


def build_fetcher(client):
    """Bind the Reddit client into the one-argument fetcher ingest expects."""
    def fetcher(since):
        return reddit.fetch(since, client, subreddits=SUBREDDITS)
    return fetcher


def build_client():
    return reddit.RedditClient(
        client_id=os.getenv('REDDIT_CLIENT_ID'),
        client_secret=os.getenv('REDDIT_CLIENT_SECRET'),
        username=os.getenv('REDDIT_USERNAME'),
        password=os.getenv('REDDIT_PASSWORD'),
        user_agent=os.getenv('REDDIT_USER_AGENT', reddit.USER_AGENT_DEFAULT),
    )


def tick(now_utc, fetcher):
    """One cycle, with failures contained.

    APScheduler drops a job whose function raises, so an unhandled error here
    would silently end ingest until the next restart -- losing far more than
    the cycle that failed.
    """
    try:
        summary = ingest.run_cycle(now_utc.replace(tzinfo=None), fetcher)
    except Exception:
        logger.exception('radar ingest cycle failed')
        return {'status': 'error', 'posts_seen': 0, 'posts_new': 0,
                'mentions': 0, 'buckets_written': 0, 'catchup_depth': 0}

    logger.info('radar cycle status=%s posts=%d new=%d mentions=%d '
                'buckets=%d catchup_depth=%d',
                summary['status'], summary['posts_seen'], summary['posts_new'],
                summary['mentions'], summary['buckets_written'],
                summary['catchup_depth'])
    return summary


def _scheduled_cycle(scheduler, fetcher):
    """Run a cycle, then reschedule at the interval the session now calls for."""
    now = dt.datetime.now(dt.timezone.utc)
    with app.app_context():
        tick(now, fetcher)

    state = current_state(now)
    scheduler.reschedule_job('radar_cycle', trigger='interval',
                             seconds=interval_for(state))


def _scheduled_prune():
    with app.app_context():
        deleted = retention.prune_posts(dt.datetime.utcnow())
        if deleted:
            logger.info('radar retention pruned %d posts', deleted)


def main():
    logging.basicConfig(level=logging.INFO)
    fetcher = build_fetcher(build_client())

    scheduler = BackgroundScheduler(timezone='UTC')
    scheduler.add_job(_scheduled_cycle, 'interval', seconds=180,
                      id='radar_cycle', args=[scheduler, fetcher],
                      max_instances=1, coalesce=True)
    scheduler.add_job(_scheduled_prune, 'cron', hour=4, minute=30,
                      id='radar_prune')
    scheduler.start()
    logger.info('radar ingest daemon started')

    try:
        while True:
            import time
            time.sleep(60)
    except (KeyboardInterrupt, SystemExit):
        scheduler.shutdown()


if __name__ == '__main__':
    main()
