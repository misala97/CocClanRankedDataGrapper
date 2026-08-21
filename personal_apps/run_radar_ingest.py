"""Radar ingest daemon.

Mirrors run_gym_notifier.py: an APScheduler process holding a Flask app
context, deployed as its own systemd unit and restarted by the VPS deploy
script.

Cadence is chosen per cycle from the NYSE session rather than fixed, because
chatter volume follows the session and polling overnight at session rates is
wasted work. The state comes from the exchange calendar, never from local time
-- see the DST note in features/radar/market_calendar.py.

Three sources run behind one contract. Nothing here branches on which source is
which beyond building its fetcher; a fourth would be a module in sources/ plus
an entry in config.SOURCES.
"""
import datetime as dt
import logging
import time

import sqlalchemy as sa
from apscheduler.schedulers.background import BackgroundScheduler

from app import app
from extensions import db
from features.radar import (
    ingest, market_calendar, quotes, retention, scheduling, scoring)
from features.radar.prices import finnhub as finnhub_provider
from features.radar.config import (
    SOURCES, STOCKTWITS_REQUESTS_PER_HOUR, prefer_ipv4_if_configured)
from features.radar.sources import bluesky, fourchan, stocktwits
from features.radar.sources import FetchResult

logger = logging.getLogger('radar.ingest')

INTERVALS = {
    'premarket': 180,
    'regular': 180,
    'afterhours': 600,
    'closed': 1800,
}
# An unrecognized state polls at the slowest rate. Failing towards fewer
# requests is the safe direction when the alternative is hammering an API.
FALLBACK_INTERVAL = 1800

# Cycles per hour at the fastest cadence, used to divide the hourly budget.
_CYCLES_PER_HOUR = 20
SYMBOL_BUDGET_PER_CYCLE = max(1, STOCKTWITS_REQUESTS_PER_HOUR // _CYCLES_PER_HOUR)

# Finnhub's free tier is 60 calls a minute. Quotes go to the tickers actually
# on the board, not to all 12,000 in the universe -- a quote for a ticker
# nobody is discussing answers a question nobody asked.
QUOTE_LIMIT = 50
QUOTE_INTERVAL_MINUTES = 5


def _utcnow():
    """Naive UTC, the convention every datetime in this codebase is stored in.

    datetime.utcnow() is deprecated and slated for removal, and it printed a
    warning into the service log on every cycle.
    """
    return dt.datetime.now(dt.timezone.utc).replace(tzinfo=None)

def interval_for(state):
    return INTERVALS.get(state, FALLBACK_INTERVAL)


def current_state(now_utc):
    return market_calendar.session_state(now_utc)


def _stocktwits_fetcher(client):
    """Trending is both the discovery surface and how the polled set grows.

    Symbols accumulate: every symbol that has ever trended stays tracked, so
    the standing set builds itself rather than waiting on a market-cap source
    the free tier does not provide.
    """
    def fetch(since):
        now = _utcnow()
        discovery_failed = False
        try:
            hot = stocktwits.trending(client)
            scheduling.ensure_tracked('stocktwits', hot, now)
        except stocktwits.StockTwitsUnavailable as exc:
            # One bad trending call must not cost the cycle its polled set.
            # The reason is logged: "unavailable" alone is not diagnosable, and
            # a blocked IP looks identical to a rate limit without it.
            discovery_failed = True
            logger.warning('stocktwits trending unavailable this cycle: %s', exc)

        symbols = scheduling.due_symbols('stocktwits', now,
                                         limit=SYMBOL_BUDGET_PER_CYCLE)

        if discovery_failed and not symbols:
            # Nothing reached us and nothing was left to try, so this source
            # saw nothing -- which is `missing`, not a quiet period. Reporting
            # `ok` here wrote zero-count buckets for a source that was 403 on
            # every request, and thirty days of those would make any later
            # StockTwits data read as an enormous spike.
            return FetchResult(posts=[], status='missing')

        result = stocktwits.fetch(since, client, symbols)
        for symbol in symbols:
            scheduling.record_poll('stocktwits', symbol, now,
                                   result.rates.get(symbol))
        return result
    return fetch


def build_fetchers():
    """One callable per active source, each taking `since`."""
    st_client = stocktwits.StockTwitsClient()
    fc_client = fourchan.FourChanClient()

    return {
        'stocktwits': _stocktwits_fetcher(st_client),
        'bluesky': lambda since: bluesky.fetch(since, bluesky.live_drain),
        'fourchan': lambda since: fourchan.fetch(
            since, fc_client, pause=fourchan.REQUEST_INTERVAL_SECONDS),
    }


def tick(now_utc, fetchers):
    """One cycle across every source, with failures contained.

    APScheduler drops a job whose function raises, so an unhandled error here
    would silently end ingest until the next restart -- losing far more than
    the cycle that failed.
    """
    try:
        summary = ingest.run_cycle(now_utc.replace(tzinfo=None), fetchers)
    except Exception:
        logger.exception('radar ingest cycle failed')
        return {'status': 'error', 'posts_seen': 0, 'posts_new': 0,
                'mentions': 0, 'buckets_written': 0, 'per_source': {}}

    logger.info('radar cycle posts=%d new=%d mentions=%d buckets=%d sources=%s',
                summary['posts_seen'], summary['posts_new'],
                summary['mentions'], summary['buckets_written'],
                summary['per_source'])
    return summary


def _scheduled_cycle(scheduler, fetchers):
    """Run a cycle, then reschedule at the interval the session now calls for."""
    now = dt.datetime.now(dt.timezone.utc)
    with app.app_context():
        tick(now, fetchers)

    scheduler.reschedule_job('radar_cycle', trigger='interval',
                             seconds=interval_for(current_state(now)))


def score_all(now_utc):
    """Rescore every source. Returns rows written per source.

    Separate from ingest and slower -- it walks thirty days of buckets per
    ticker, so it runs on its own schedule rather than inside a three-minute
    cycle.

    Failures are isolated per source for the same reason ingest isolates them:
    one source's baseline going wrong is not a reason to leave the rest
    unscored.
    """
    written = {}
    for source in SOURCES:
        try:
            written[source] = scoring.score_source(
                source, now_utc.replace(tzinfo=None))
        except Exception:
            logger.exception('radar scoring failed for %s', source)
            written[source] = 0
    return written


def _scheduled_scoring():
    now = dt.datetime.now(dt.timezone.utc)
    with app.app_context():
        written = score_all(now)
    logger.info('radar scoring wrote %s', written)


def _loud_tickers(now, limit):
    """Tickers worth spending a quote on: the loudest recently scored."""
    from models import RadarBucketSource
    since = now.replace(tzinfo=None) - dt.timedelta(hours=4)
    rows = (db.session.query(RadarBucketSource.ticker,
                             sa.func.max(RadarBucketSource.mention_z))
            .filter(RadarBucketSource.bucket_start >= since,
                    RadarBucketSource.mention_z.isnot(None))
            .group_by(RadarBucketSource.ticker)
            .order_by(sa.func.max(RadarBucketSource.mention_z).desc())
            .limit(limit).all())
    return [ticker for ticker, _ in rows]


def poll_quotes(now_utc, provider, limit=QUOTE_LIMIT):
    """Fetch and store quotes for the loudest tickers."""
    symbols = _loud_tickers(now_utc, limit)
    if not symbols:
        # No board, so no reason to spend rate limit on an empty request.
        return {'requested': 0, 'stored': 0, 'error': False}

    try:
        found = provider.quotes(symbols)
        stored = quotes.record_quotes(found, now_utc.replace(tzinfo=None))
    except Exception:
        logger.exception('radar quote poll failed')
        return {'requested': len(symbols), 'stored': 0, 'error': True}

    return {'requested': len(symbols), 'stored': stored, 'error': False}


def _scheduled_quotes():
    now = dt.datetime.now(dt.timezone.utc)
    provider = finnhub_provider.FinnhubProvider(finnhub_provider.FinnhubHttp())
    with app.app_context():
        result = poll_quotes(now, provider)
    logger.info('radar quotes requested=%d stored=%d error=%s',
                result['requested'], result['stored'], result['error'])


def _scheduled_prune():
    with app.app_context():
        deleted = retention.prune_posts(_utcnow())
        if deleted:
            logger.info('radar retention pruned %d posts', deleted)


def main():
    logging.basicConfig(level=logging.INFO)
    if prefer_ipv4_if_configured():
        logger.info('RADAR_FORCE_IPV4 set -- outbound HTTP will skip AAAA records')
    fetchers = build_fetchers()

    scheduler = BackgroundScheduler(timezone='UTC')
    # next_run_time is not a nicety. An interval trigger otherwise fires only
    # after the first interval has elapsed, so starting the service overnight
    # means thirty minutes of silence before any evidence it works -- and the
    # same wait after every deploy restart. Catch-up is cursor-driven, so an
    # immediate first cycle costs nothing and collects the gap.
    scheduler.add_job(_scheduled_cycle, 'interval', seconds=180,
                      id='radar_cycle', args=[scheduler, fetchers],
                      max_instances=1, coalesce=True,
                      next_run_time=dt.datetime.now(dt.timezone.utc))
    # Two minutes behind the first cycle, so there are buckets to read before
    # the first scoring pass goes looking for them.
    scheduler.add_job(_scheduled_scoring, 'interval', minutes=15,
                      id='radar_scoring', max_instances=1, coalesce=True,
                      next_run_time=dt.datetime.now(dt.timezone.utc)
                      + dt.timedelta(minutes=2))
    scheduler.add_job(_scheduled_quotes, 'interval',
                      minutes=QUOTE_INTERVAL_MINUTES, id='radar_quotes',
                      max_instances=1, coalesce=True)
    scheduler.add_job(_scheduled_prune, 'cron', hour=4, minute=30,
                      id='radar_prune')
    scheduler.start()
    logger.info('radar ingest daemon started, sources=%s', ','.join(SOURCES))

    try:
        while True:
            time.sleep(60)
    except (KeyboardInterrupt, SystemExit):
        scheduler.shutdown()


if __name__ == '__main__':
    main()
