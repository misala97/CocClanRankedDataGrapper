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
    history, ingest, market_calendar, quotes, retention, scheduling, scoring,
    universe)
from features.radar.prices import finnhub as finnhub_provider
from features.radar.prices import twelvedata as twelvedata_provider
from features.radar.config import (
    REDDIT_SUBS, REDDIT_SUBS_PER_CYCLE, SOURCES, STOCKTWITS_REQUESTS_PER_HOUR,
    prefer_ipv4_if_configured)
from features.radar.sources import bluesky, fourchan, reddit, stocktwits
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

# Twelve Data allows 800 requests a day and volatility moves on the scale of
# weeks, so this is deliberately slow and small.
SIGMA_LIMIT = 60
SIGMA_INTERVAL_HOURS = 12

# Company profiles: market cap and IPO date, which are what the segment tabs
# are built from. There was no job for this until 2026-08-22, so market_cap
# was NULL for all 12,595 universe rows and every ticker fell through
# universe.segment_for() into Unknown -- the segment selector has never
# actually worked in production. universe.refresh_profiles() existed the whole
# time; nothing called it.
#
# Six-hourly rather than weekly because the board's tickers turn over daily and
# a new arrival should not sit in Unknown for a week. The staleness filter
# means a settled board asks for almost nothing.
PROFILE_LIMIT = 40
PROFILE_INTERVAL_HOURS = 6
PROFILE_MAX_AGE_DAYS = 7

# Daily closes for the chart's longer spans. The binding constraint is Twelve
# Data's EIGHT REQUESTS PER MINUTE, not its 800/day quota: 20 per five-minute
# cycle is four a minute, leaving room for the quote job alongside.
HISTORY_LIMIT = 20
HISTORY_INTERVAL_MINUTES = 5


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


def _reddit_fetcher(client):
    """Reddit, a budgeted slice of subreddits per cycle.

    The feed holds 25 comments and has no cursor, so how often a subreddit is
    read IS its coverage -- r/wallstreetbets turns over in under two minutes.
    Reading all eighteen every cycle would be six requests a minute, which is
    well past what earned a sustained 429 during measurement, so they rotate
    through the same scheduler StockTwits symbols use: most-overdue first, so
    a backlog larger than the budget rotates instead of starving the same subs
    forever.

    The observed rate comes back from the feed itself, which lets a quiet sub
    fall to a slow cadence and hand its share of the budget to a busy one.
    """
    def fetch(since):
        now = _utcnow()
        scheduling.ensure_tracked('reddit', REDDIT_SUBS, now)
        subs = scheduling.due_symbols('reddit', now, limit=REDDIT_SUBS_PER_CYCLE)
        if not subs:
            # Nothing due. Not a quiet period and not a failure -- there is
            # simply no observation to report, and `missing` is what keeps the
            # rollup from writing zero counts for it.
            return FetchResult(posts=[], status='missing')

        result = reddit.fetch(since, client, subs)
        for sub in subs:
            scheduling.record_poll('reddit', sub, now, result.rates.get(sub))
        return result
    return fetch


def build_fetchers():
    """One callable per active source, each taking `since`."""
    st_client = stocktwits.StockTwitsClient()
    fc_client = fourchan.FourChanClient()
    rd_client = reddit.RedditClient()

    return {
        'stocktwits': _stocktwits_fetcher(st_client),
        'bluesky': lambda since: bluesky.fetch(since, bluesky.live_drain),
        'fourchan': lambda since: fourchan.fetch(
            since, fc_client, pause=fourchan.REQUEST_INTERVAL_SECONDS),
        'reddit': _reddit_fetcher(rd_client),
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


def refresh_volatility(now_utc, limit=SIGMA_LIMIT):
    """Recompute daily sigma for the tickers on the board.

    No provider argument: sigma comes from the closes the history job already
    stored (features/radar/history.py). Divergence needs a sigma for every row
    of every page load, so it stays cached -- this fills the cache from the
    table rather than from the network.
    """
    tickers = _loud_tickers(now_utc, limit)
    if not tickers:
        return 0
    try:
        return quotes.refresh_sigma(tickers, now_utc.replace(tzinfo=None))
    except Exception:
        logger.exception('radar volatility refresh failed')
        return 0


def _profiles_due(now, limit):
    """Board tickers whose profile is missing or has gone stale, loudest first.

    Drawn from a wider slice of the board than `limit`, then filtered by age,
    so a settled board spends its calls on the arrivals that need them rather
    than re-asking about the same forty rows every six hours.

    The ordering is the whole job. `_loud_tickers` ranks the pool by mention_z
    and this used to throw that away: the eligible rows came back from a
    `WHERE symbol IN (...)` with no ORDER BY, so the scan order decided who got
    a profile. In practice that is symbol order, and with more eligible
    tickers than `limit` the tail of the alphabet starved outright -- in
    production on 2026-08-24 there were 167 eligible against a limit of 40, and
    SPY, QQQ and TSLA had been losing the cut for three days while new arrivals
    between A and N jumped the queue. Every one of them rendered as segment
    Unknown the whole time, which is what put Tesla under the Small tab.

    So the eligibility test stays in SQL and the ranking stays in Python, where
    it cannot be dropped by a query planner.
    """
    from models import TickerUniverse
    candidates = _loud_tickers(now, limit * 5)
    if not candidates:
        return []

    cutoff = now.replace(tzinfo=None) - dt.timedelta(days=PROFILE_MAX_AGE_DAYS)
    eligible = {symbol for (symbol,) in db.session.query(TickerUniverse.symbol)
                .filter(TickerUniverse.symbol.in_(candidates),
                        # A fund has no profile to fetch. Finnhub answers an
                        # empty payload for every one of them, so each costs a
                        # slot to learn nothing -- and 5,636 of the 12,599
                        # rows in the live universe are funds. Skipped where
                        # the directory SAID so; NULL still gets asked, since
                        # not knowing is not the same as knowing it is a fund.
                        sa.or_(TickerUniverse.is_etf.is_(None),
                               TickerUniverse.is_etf.is_(False)),
                        sa.or_(TickerUniverse.profile_refreshed_at.is_(None),
                               TickerUniverse.profile_refreshed_at < cutoff))}
    return [symbol for symbol in candidates if symbol in eligible][:limit]


def refresh_profiles(now_utc, provider, limit=PROFILE_LIMIT):
    """Fetch market cap and IPO date for the tickers that need them.

    Returns how many rows were updated. A provider that answers nothing leaves
    the existing row alone -- erasing a cap we already had would drop the
    ticker into Unknown until the next pass, which is worse than a stale one.
    """
    symbols = _profiles_due(now_utc, limit)
    if not symbols:
        return 0
    try:
        return universe.refresh_profiles(provider, symbols,
                                         now_utc.replace(tzinfo=None))
    except Exception:
        logger.exception('radar profile refresh failed')
        return 0


def _scheduled_profiles():
    now = dt.datetime.now(dt.timezone.utc)
    provider = finnhub_provider.FinnhubProvider(finnhub_provider.FinnhubHttp())
    with app.app_context():
        updated = refresh_profiles(now, provider)
    logger.info('radar profiles refreshed %d tickers', updated)


def refresh_history(now_utc, provider, limit=HISTORY_LIMIT):
    """Fetch a year of daily closes for board tickers that need them.

    Returns how many tickers came back with data. Ordering is the history
    module's decision -- missing before stale -- because a ticker the board
    cannot draw at all is worth more than a fresher copy of one it can.
    """
    candidates = _loud_tickers(now_utc, limit * 5)
    if not candidates:
        return 0

    naive = now_utc.replace(tzinfo=None)
    try:
        due = history.tickers_needing_history(candidates, naive.date())[:limit]
        if not due:
            return 0
        return history.fetch_into_store(provider, due, naive)
    except Exception:
        logger.exception('radar history refresh failed')
        return 0


def _scheduled_history():
    now = dt.datetime.now(dt.timezone.utc)
    provider = twelvedata_provider.TwelveDataProvider(
        twelvedata_provider.TwelveDataHttp())
    with app.app_context():
        stored = refresh_history(now, provider)
    logger.info('radar history stored %d tickers', stored)


def _scheduled_volatility():
    now = dt.datetime.now(dt.timezone.utc)
    with app.app_context():
        updated = refresh_volatility(now)
    logger.info('radar volatility refreshed %d tickers', updated)


def _scheduled_prune():
    with app.app_context():
        now = _utcnow()
        deleted = retention.prune_posts(now)
        if deleted:
            logger.info('radar retention pruned %d posts', deleted)
        # Quotes were never pruned at all, and since the board began reading
        # them on every load (2026-08-24) that table is the one most likely to
        # slowly undo the work that made it fast.
        quotes = retention.prune_quotes(now)
        if quotes:
            logger.info('radar retention pruned %d quotes', quotes)


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
    scheduler.add_job(_scheduled_volatility, 'interval',
                      hours=SIGMA_INTERVAL_HOURS, id='radar_volatility',
                      max_instances=1, coalesce=True,
                      next_run_time=dt.datetime.now(dt.timezone.utc)
                      + dt.timedelta(minutes=5))
    # Three minutes in, ahead of volatility, because until a profile exists
    # every row on the board reads as segment Unknown -- and unlike a missing
    # sigma, that is visible on the very first page load.
    scheduler.add_job(_scheduled_profiles, 'interval',
                      hours=PROFILE_INTERVAL_HOURS, id='radar_profiles',
                      max_instances=1, coalesce=True,
                      next_run_time=dt.datetime.now(dt.timezone.utc)
                      + dt.timedelta(minutes=3))
    # One minute in, ahead of everything else that costs requests: a ticker
    # with no stored history is the only one the chart literally cannot draw.
    scheduler.add_job(_scheduled_history, 'interval',
                      minutes=HISTORY_INTERVAL_MINUTES, id='radar_history',
                      max_instances=1, coalesce=True,
                      next_run_time=dt.datetime.now(dt.timezone.utc)
                      + dt.timedelta(minutes=1))
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
