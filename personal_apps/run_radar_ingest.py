"""Radar ingest daemon.

Mirrors run_gym_notifier.py: an APScheduler process holding a Flask app
context, deployed as its own systemd unit and restarted by the VPS deploy
script.

Cadence is chosen per cycle from the NYSE session rather than fixed, because
chatter volume follows the session and polling overnight at session rates is
wasted work. The state comes from the exchange calendar, never from local time
-- see the DST note in features/radar/market_calendar.py.

Every source runs behind one contract. Nothing here branches on which source
is which beyond building its fetcher; a new one is a module in sources/ plus
an entry in config.SOURCES. StockTwits was one of these until 2026-08-26,
when Cloudflare bot management -- refusing every request, from launch --
made it not worth defeating a bot challenge to keep.
"""
import argparse
import datetime as dt
import logging
import sys
import time

import sqlalchemy as sa
from apscheduler.schedulers.background import BackgroundScheduler

from app import app
from extensions import db
from models import RadarInstrument, RadarPollState, RadarRedditCursor
from features.radar import (
    activity, history, ingest, journal, judge_config,
    judge_trial, llm_sentiment,
    market_calendar, observations, quotes, retention, scheduling, scoring,
    universe)
from features.radar.prices import finnhub as finnhub_provider
from features.radar.prices import twelvedata as twelvedata_provider
from features.radar.prices import normalize_snapshot
from features.radar.config import (
    ARCTIC_SHIFT_INTERVAL_SECONDS, CYCLE_SECONDS,
    MENTION_EVENT_RETENTION_HOURS,
    REDDIT_FETCHER, REDDIT_INTERVAL_SECONDS, REDDIT_MAX_POLL,
    REDDIT_MIN_POLL, REDDIT_SUBS, REDDIT_SUBS_PER_CYCLE, SOURCES,
    expand_sources, prefer_ipv4_if_configured, source_config_version)
from features.radar.sources import arctic_shift, bluesky, fourchan, reddit
from features.radar.sources import FetchResult

logger = logging.getLogger('radar.ingest')

# See the radar_scoring job in main() for why this is not fifteen.
SCORING_INTERVAL_MINUTES = 30

INTERVALS = {
    'premarket': 180,
    'regular': 180,
    'afterhours': 600,
    'closed': 1800,
}
# An unrecognized state polls at the slowest rate. Failing towards fewer
# requests is the safe direction when the alternative is hammering an API.
FALLBACK_INTERVAL = 1800

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


def _reddit_fetcher(client):
    """Reddit, a budgeted slice of subreddits per cycle.

    The feed holds 25 comments and has no cursor, so how often a subreddit is
    read IS its coverage -- r/wallstreetbets turns over in under two minutes.
    Reading all eighteen every cycle would be six requests a minute, which is
    well past what earned a sustained 429 during measurement, so they rotate
    through the poll scheduler's due-symbol ordering: most-overdue first, so
    a backlog larger than the budget rotates instead of starving the same subs
    forever.

    The observed rate comes back from the feed itself, which lets a quiet sub
    fall to a slow cadence and hand its share of the budget to a busy one.
    """
    def fetch(since):
        now = _utcnow()
        # Poll state stays keyed by the bare source name with the subreddit as
        # its symbol. Only what the POSTS carry is prefixed -- the scheduler's
        # unit is the subreddit either way, and re-keying it would retire every
        # learned observed_rate on deploy.
        scheduling.ensure_tracked('reddit', REDDIT_SUBS, now)
        # And drop the ones no longer configured. due_symbols filters by
        # SOURCE rather than by this list, so a removed subreddit would keep
        # its poll state and keep taking turns -- spending the very budget its
        # removal was meant to free, while still appearing in the logs as
        # though nothing had changed. Reddit can do this because REDDIT_SUBS
        # is the complete set; a source whose tracked set is a rolling window
        # must never call this, since a symbol falling out of it is temporary.
        retired = scheduling.retire_untracked('reddit', REDDIT_SUBS)
        if retired:
            logger.info('radar reddit retired %d subreddit(s) '
                        'no longer configured', retired)
        subs = scheduling.due_symbols('reddit', now, limit=REDDIT_SUBS_PER_CYCLE)
        if not subs:
            # Nothing due. Every subreddit was read inside its own interval,
            # so coverage IS current -- this is no work to do, not a failure.
            # `missing` here made six of eight cycles look like outages in the
            # log and hid the real ones among them.
            #
            # And an EXPLICITLY EMPTY per-source map, not the default None.
            # Reddit was not read at all this cycle, so it made no observation
            # -- there is nothing to record. None would fall through to
            # ingest's `{source: result.status}` fallback, stamp
            # `{'reddit': 'ok'}` onto the rollup and write a zero-count child
            # row named `reddit` into every bucket any OTHER source touched,
            # claiming coverage no fetch produced. This is the common path --
            # six of eight cycles have nothing due -- so that zero would be
            # the normal case rather than an edge one.
            return FetchResult(posts=[], status='ok', per_source_status={})

        # Each subreddit reads from when IT was last polled, never from a
        # cursor shared across the source. Shared, the busiest sub sets a
        # watermark that permanently excludes every quieter one.
        rows = {row.symbol: row.last_polled_at for row in
                RadarPollState.query.filter(
                    RadarPollState.source == 'reddit',
                    RadarPollState.symbol.in_(subs)).all()}
        since_by_sub = {sub: (rows.get(sub) or since) for sub in subs}

        result = reddit.fetch(since_by_sub, client)
        # Only what was actually attempted. A throttle stops the cycle, and
        # stamping the subreddits after it as polled would push them down the
        # queue for a request that was never made -- so they would lose their
        # turn to the ones that happened to be earlier in the batch.
        for sub, rate in (result.rates or {}).items():
            # This source's own bounds, not the scheduler's generic defaults:
            # a fifteen-minute floor would lose most of r/wallstreetbets --
            # whose feed holds 25 comments and turns over in under two
            # minutes.
            scheduling.record_poll('reddit', sub, now, rate,
                                   floor=REDDIT_MIN_POLL,
                                   ceiling=REDDIT_MAX_POLL,
                                   page_size=reddit.FEED_LIMIT)
        return result
    return fetch


def _arctic_fetcher(client):
    """Reddit through Arctic Shift (features/radar/sources/arctic_shift.py).

    The per-sub cursors are loaded here, handed to the adapter, and the
    advanced ones are STAGED in the session -- not committed. run_cycle's
    single commit carries them with the posts they cover, so a cycle that
    fails after the fetch moves nothing and the next one asks again from
    the same place. `since` from the root cursor is ignored on purpose:
    one shared watermark starves the quiet subs (reddit.py:185-191).
    """
    def fetch(since):
        now = _utcnow()
        cursors = {(row.sub, row.kind): row.cursor_utc
                   for row in RadarRedditCursor.query.all()}
        result, advanced = arctic_shift.fetch(cursors, client, subs=REDDIT_SUBS, now=now)
        for (sub, kind), newest in advanced.items():
            row = db.session.get(RadarRedditCursor, (sub, kind))
            if row is None:
                db.session.add(RadarRedditCursor(sub=sub, kind=kind,
                                                 cursor_utc=newest, updated_at=now))
            elif newest > row.cursor_utc:
                row.cursor_utc = newest
                row.updated_at = now
        return result
    return fetch


def _reddit_job_seconds():
    """The radar_reddit job's interval follows the reader: the archive lags
    minutes, the feed turned over in under two."""
    return (ARCTIC_SHIFT_INTERVAL_SECONDS if REDDIT_FETCHER == 'arctic_shift'
            else REDDIT_INTERVAL_SECONDS)


def build_fetchers():
    """One callable per active source, each taking `since`."""
    fc_client = fourchan.FourChanClient()
    if REDDIT_FETCHER == 'arctic_shift':
        reddit_fetch = _arctic_fetcher(arctic_shift.ArcticShiftClient())
    else:
        reddit_fetch = _reddit_fetcher(reddit.RedditClient())
    return {
        'bluesky': lambda since: bluesky.fetch(since, bluesky.live_drain),
        'fourchan': lambda since: fourchan.fetch(
            since, fc_client, pause=fourchan.REQUEST_INTERVAL_SECONDS),
        'reddit': reddit_fetch,
    }


def _format_operational_map(values):
    """Stable one-line source report; None is visibly unknown, never zero."""
    if not values:
        return 'none'
    return ','.join(
        '%s=%s' % (source, 'unknown' if value is None else value)
        for source, value in sorted(values.items()))


# The main cycle and the Reddit cycle are separate JOBS on purpose -- a slow
# archive must not delay Bluesky and 4chan -- but they are not separate
# WRITERS: both rebuild the same radar_bucket_sources rows, and so do the
# scoring pass and the chatter-correction rebuild. What keeps them from
# deadlocking InnoDB is buckets.BUCKET_WRITE_LOCK, taken by each writer
# around its own flush. A lock HERE, around the whole cycle, was the first
# attempt (2026-09-03): it serialized the two cycles and missed the scoring
# pass, which then took a Reddit cycle down every thirty minutes.


def _recorder_now():
    """Actual wall time, not the cycle's `now`. A run that took four minutes
    must not be recorded as having finished when it started."""
    return dt.datetime.now(dt.timezone.utc).replace(tzinfo=None)


def tick(now_utc, fetchers):
    """One cycle across every source, with failures contained.

    APScheduler drops a job whose function raises, so an unhandled error here
    would silently end ingest until the next restart -- losing far more than
    the cycle that failed.

    The run marker is written BEFORE the cycle, so a process that dies inside
    run_cycle still leaves evidence that a cycle was attempted. The zeros in
    the error return below are the caller's stable shape and are deliberately
    not what gets recorded: `finish_run` stores a code and no counters.
    """
    run_id = activity.start_run(now_utc.replace(tzinfo=None))
    try:
        summary = ingest.run_cycle(now_utc.replace(tzinfo=None), fetchers)
    except Exception:
        logger.exception('radar ingest cycle failed')
        activity.finish_run(run_id, _recorder_now(),
                            summary=None, error_code='ingest_failed')
        return {'status': 'error', 'posts_seen': 0, 'posts_new': 0,
                'mentions': 0, 'buckets_written': 0, 'per_source': {},
                'aggregate_status': {}, 'catchup_depth': {}}

    activity.finish_run(run_id, _recorder_now(), summary=summary,
                        error_code=None)

    logger.info('radar cycle posts=%d new=%d mentions=%d buckets=%d sources=%s '
                'aggregate=%s catchup_depth=%s intake=%s',
                summary['posts_seen'], summary['posts_new'],
                summary['mentions'], summary['buckets_written'],
                summary['per_source'],
                _format_operational_map(summary['aggregate_status']),
                _format_operational_map(summary['catchup_depth']),
                summary.get('intake_reasons', {}))
    return summary


def _scheduled_cycle(scheduler, fetchers):
    """Run a cycle, then reschedule at the interval the session now calls for.

    Reddit is deliberately absent from `fetchers` here -- see
    `_scheduled_reddit`. Its cadence must not follow the market session.
    """
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
    for source in expand_sources(SOURCES):
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


def _market_instruments(tickers, market):
    """Primary, verified instruments for a bounded market poll."""
    return (RadarInstrument.query
            .filter(RadarInstrument.ticker.in_(tickers),
                    RadarInstrument.market == market,
                    RadarInstrument.is_primary.is_(True),
                    RadarInstrument.mapping_status == 'mapped')
            .order_by(RadarInstrument.ticker, RadarInstrument.mic).all())


def _poll_instruments(provider, instruments, now):
    """Fetch and normalize a market batch without inventing missing prices."""
    if not instruments:
        return 0
    if hasattr(provider, 'quotes_for_instruments'):
        raw_quotes = provider.quotes_for_instruments(instruments)
    else:
        raw_quotes = provider.quotes(
            [row.provider_symbol for row in instruments])
    normalized = {}
    for instrument in instruments:
        raw = raw_quotes.get(instrument.provider_symbol)
        if raw is None:
            continue
        try:
            quote = normalize_snapshot(instrument, raw)
        except Exception:
            logger.warning('radar quote rejected ticker=%s market=%s mic=%s',
                           instrument.ticker, instrument.market, instrument.mic)
            continue
        normalized[(quote.ticker, quote.market, quote.mic)] = quote
    return quotes.record_quotes(normalized, now.replace(tzinfo=None))


# --- market-data v2 orchestration (plan Task 9) -----------------------------

# How many due symbols one US quote cycle may attempt. Finnhub's 60/min
# budget leaves room beside the other jobs at 55 per five-minute cycle;
# the Yahoo fallback asks at most 100 per 15-minute cycle.
US_QUOTE_CAP = {'finnhub': 55, 'yahoo': 100}
US_QUOTE_MINUTES = {'finnhub': 5, 'yahoo': 15}  # [A2]

# The single post-close cycle is eligible only inside this window after the
# calendar's extended-session close [A3].
POST_CLOSE_WINDOW = dt.timedelta(minutes=60)


def _us_session_gate(now_aware):
    """'open', ('post_close', session_date), or 'closed'."""
    from features.radar.market_calendars import session_bounds, session_state
    if session_state('us', now_aware) != 'closed':
        return 'open', None
    for probe in (now_aware, now_aware - dt.timedelta(days=1)):
        try:
            bounds = session_bounds('us', probe)
        except Exception:
            continue
        if bounds.closes_at <= now_aware < bounds.closes_at + \
                POST_CLOSE_WINDOW:
            return 'post_close', bounds.closes_at.date()
    return 'closed', None


def _run_us_price_cycle(provider_name, now_aware):
    from features.radar import market_data, scheduling
    from features.radar.prices import yahoo as yahoo_provider

    now = now_aware.replace(tzinfo=None)
    gate, session_date = _us_session_gate(now_aware)
    if gate == 'closed':
        # A structured no-op, not an error: nights and weekends are most of
        # the clock [A3].
        return {'skipped': 'market_closed', 'stored': 0, 'error': False}
    poll_source = f'price:{provider_name}'
    if gate == 'post_close':
        # Resolve candidates BEFORE claiming; an empty cycle must not burn
        # the one durable post-close slot.
        candidates = market_data.active_price_tickers(now)
        if not candidates:
            return {'skipped': 'no_candidates', 'stored': 0, 'error': False}
        claimed = market_data.claim_post_close(
            poll_source, 'us', now, session_date)
        if claimed is None:
            return {'skipped': 'post_close_claimed', 'stored': 0,
                    'error': False}
    else:
        candidates = market_data.active_price_tickers(now)
        if not candidates:
            return {'skipped': 'no_candidates', 'stored': 0, 'error': False}

    scheduling.ensure_tracked(poll_source, candidates, now)
    cap = US_QUOTE_CAP[provider_name]
    due = scheduling.due_symbols_from(poll_source, candidates, now, cap)
    if not due:
        return {'skipped': 'nothing_due', 'stored': 0, 'error': False}

    interval = dt.timedelta(minutes=US_QUOTE_MINUTES[provider_name])
    instruments_rows = _market_instruments(due, 'us')
    if not instruments_rows:
        # D8: nothing due has a mapped US primary, so nothing due has a venue
        # anyone verified. No provider is asked and no quote is stored -- a
        # structured no-op, not an error. The attempts are still stamped, as
        # an unmapped symbol in a mixed batch is: left due, an unmapped batch
        # would head every following cycle and starve the mapped symbols.
        for symbol in due:
            scheduling.record_fixed_poll(poll_source, symbol, now, interval)
        return {'skipped': 'no_mapped_instruments', 'stored': 0,
                'error': False}

    if provider_name == 'finnhub':
        provider = finnhub_provider.FinnhubProvider(
            finnhub_provider.FinnhubHttp())
    else:
        provider = yahoo_provider.YahooProvider(yahoo_provider.YahooHttp())

    try:
        stored = _poll_instruments(provider, instruments_rows, now_aware)
        error = False
    except Exception:
        logger.exception('radar US quote cycle failed')
        stored = 0
        error = True
    for symbol in due:
        scheduling.record_fixed_poll(poll_source, symbol, now, interval)
    return {'skipped': None, 'stored': stored, 'error': error,
            'attempted': len(due)}


def _scheduled_us_quotes():
    from features.radar.config import price_provider_config
    provider_name, _ = price_provider_config()
    now_aware = dt.datetime.now(dt.timezone.utc)
    with app.app_context():
        result = _run_us_price_cycle(provider_name, now_aware)
    logger.info('radar us quotes provider=%s stored=%s skipped=%s error=%s',
                provider_name, result.get('stored'), result.get('skipped'),
                result.get('error'))
    return result


def _scheduled_us_grouped_closes():
    """[A1] The daily grouped-close ingestion; a no-op under legacy."""
    from features.radar import market_data
    from features.radar.config import price_provider_config
    from features.radar.market_calendars import session_state
    from features.radar.prices import massive as massive_provider
    _, close_source = price_provider_config()
    if close_source == 'legacy':
        return {'skipped': 'legacy'}
    now_aware = dt.datetime.now(dt.timezone.utc)
    now = now_aware.replace(tzinfo=None)
    with app.app_context():
        from models import RadarGroupedCloseDay
        is_shadow = close_source == 'shadow'
        accepted = {
            state.close_date for state in RadarGroupedCloseDay.query
            .filter_by(source='massive_grouped', is_shadow=is_shadow,
                       status='accepted')}
        days = []
        probe = now_aware.date() - dt.timedelta(days=1)
        while len(days) < 7 and probe > now_aware.date() - dt.timedelta(
                days=14):
            stamp = dt.datetime.combine(probe, dt.time(16),
                                        tzinfo=dt.timezone.utc)
            if session_state('us', stamp) != 'closed' and \
                    probe not in accepted:
                days.append(probe)
            probe -= dt.timedelta(days=1)
        provider = massive_provider.MassiveProvider(
            massive_provider.MassiveHttp())
        results = []
        for day in sorted(days):
            try:
                result = market_data.ingest_grouped_day(provider, day, now)
            except Exception:
                logger.exception('radar grouped ingest failed for %s', day)
                continue
            results.append((day, result.status))
            logger.info('radar grouped closes %s status=%s written=%d '
                        'unmatched_provider=%d unmatched_universe=%d',
                        day, result.status, result.written,
                        result.unmatched_provider, result.unmatched_universe)
    return {'attempted': len(results), 'results': results}


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

    Returns ``(stored, empty)``. Ordering is the history
    module's decision -- missing before stale -- because a ticker the board
    cannot draw at all is worth more than a fresher copy of one it can.
    """
    candidates = _loud_tickers(now_utc, limit * 5)
    if not candidates:
        return 0, 0

    naive = now_utc.replace(tzinfo=None)
    try:
        primary = _market_instruments(candidates, 'us')
        if not primary:
            # Mixed-version compatibility before instrument seeding lands.
            due = history.tickers_needing_history(
                candidates, naive.date())[:limit]
            if not due:
                return 0, 0
            return history.fetch_into_store(provider, due, naive)

        stored = 0
        empty = 0
        remaining = limit
        by_mic = {}
        for instrument in primary:
            by_mic.setdefault(instrument.mic, []).append(instrument)
        for mic, rows in by_mic.items():
            if remaining <= 0:
                break
            tickers = [row.ticker for row in rows]
            due = history.tickers_needing_history(
                tickers, naive.date(), market='us', mic=mic)[:remaining]
            if not due:
                continue
            symbols = {row.ticker: row.provider_symbol for row in rows
                       if row.ticker in due}
            batch_stored, batch_empty = history.fetch_into_store(
                provider, due, naive, market='us', mic=mic, currency='USD',
                provider_symbols=symbols)
            stored += batch_stored
            empty += batch_empty
            remaining -= len(due)
        return stored, empty
    except Exception:
        logger.exception('radar history refresh failed')
        return 0, 0


def _yahoo_deep_tail(now_aware, limit=2):
    """[A1] At most two newly active, 3Y-incomplete tickers per cycle.

    Fair deterministic retries via poll source ``history:yahoo-tail``; a
    ticker that reaches the floor leaves the queue and is not called again.
    """
    from features.radar import market_data, scheduling
    from features.radar.prices import yahoo as yahoo_provider

    now = now_aware.replace(tzinfo=None)
    active = market_data.active_price_tickers(now)
    if not active:
        return 0
    floor = int(history.HISTORY_DAYS * history.MIN_STORED_RATIO)
    stored_depth = history.closes_for(active, today=now_aware.date())
    incomplete = [ticker for ticker in active
                  if len(stored_depth.get(ticker, [])) < floor]
    if not incomplete:
        return 0
    scheduling.ensure_tracked('history:yahoo-tail', incomplete, now)
    due = scheduling.due_symbols_from('history:yahoo-tail', incomplete, now,
                                      limit)
    if not due:
        return 0
    provider = yahoo_provider.YahooProvider(yahoo_provider.YahooHttp())
    rows = {row.ticker: row for row in _market_instruments(due, 'us')}
    stored = 0
    for ticker in due:
        instrument = rows.get(ticker)
        if instrument is None:
            # History without a mapped MIC cannot be identity-validated.
            scheduling.record_fixed_poll('history:yahoo-tail', ticker, now,
                                         dt.timedelta(hours=6))
            continue
        symbol = instrument.provider_symbol
        closes = provider.daily_closes(
            symbol, history.HISTORY_DAYS, mic_code=instrument.mic)
        if closes:
            history.record_closes(
                ticker, closes, now, market='us',
                mic=instrument.mic,
                currency='USD', source='yahoo_chart',
                adjustment_basis='split')
            stored += 1
        # A day's failed retry re-queues fairly rather than immediately.
        scheduling.record_fixed_poll('history:yahoo-tail', ticker, now,
                                     dt.timedelta(hours=6))
    return stored


def _scheduled_history():
    from features.radar.config import price_provider_config
    _, close_source = price_provider_config()
    now = dt.datetime.now(dt.timezone.utc)
    with app.app_context():
        stored = 0
        empty = 0
        if close_source in ('legacy', 'shadow'):
            # The incumbent live writer keeps running through shadow so the
            # agreement gate has an independent series to compare against.
            provider = twelvedata_provider.TwelveDataProvider(
                twelvedata_provider.TwelveDataHttp())
            stored, empty = refresh_history(now, provider)
        tail = 0
        if close_source in ('shadow', 'massive'):
            tail = _yahoo_deep_tail(now)
    logger.info('radar history us=%d us_empty=%d yahoo_tail=%d',
                stored, empty, tail)


def _scheduled_volatility():
    now = dt.datetime.now(dt.timezone.utc)
    with app.app_context():
        updated = refresh_volatility(now)
    logger.info('radar volatility refreshed %d tickers', updated)


def _scheduled_reddit(fetcher):
    """Reddit, on a fixed interval of its own.

    Everything else here follows the NYSE session, because the chatter those
    sources carry does. Reddit does not stop at the closing bell -- and more
    to the point, its feed holds 25 comments with no cursor, so a slow poll
    does not arrive late, it never arrives at all.

    Under REDDIT_FETCHER='arctic_shift' the same job runs the archive reader
    every ARCTIC_SHIFT_INTERVAL_SECONDS; it stays a job of its own so a slow
    archive never delays Bluesky and 4chan.

    Riding the session cycle, four subs per 1800-second overnight cycle meant
    a full rotation of eighteen took over two hours against a feed that turns
    over in under two minutes. Six hours of that produced one scorable
    mention.

    Its own `run_cycle` rather than a shared one -- but since roll_up now
    rebuilds a touched RadarBucket from the whole journal rather than from
    whichever cycle's rows are in memory (2026-08-26), the parent it writes is
    the same cross-source union any other cycle would produce for that window,
    not a Reddit-only total. Nothing reads that table anyway -- every consumer
    goes through RadarBucketSource, which stays correctly scoped because
    roll_up only writes a child row for the sources named in THIS cycle's
    statuses, 'reddit' alone here.
    """
    def run():
        now = dt.datetime.now(dt.timezone.utc)
        with app.app_context():
            tick(now, {'reddit': fetcher})
    return run


def _next_quarter_hour(now):
    """The next :00, :15, :30 or :45 strictly after `now`."""
    floor = now.replace(minute=(now.minute // 15) * 15, second=0, microsecond=0)
    return floor + dt.timedelta(minutes=15)


def _scheduled_observations():
    """Archive the fixed board pair for this quarter-hour.

    Its own job, never folded into tick or the scoring pass: a capture is a
    read of the board and must not be able to delay, block or fail ingest. It
    calls no quote provider -- everything it stores comes from the board the
    API would have served anyway.

    A failure here logs and leaves a gap, which is the honest outcome. The
    archive is allowed to be incomplete; it is not allowed to be wrong.
    """
    if not observations.capture_enabled():
        return
    with app.app_context():
        try:
            observations.capture(
                _utcnow(), producer_revision=observations.producer_revision())
        except Exception:
            logger.exception('radar board observation capture failed')


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
        events = retention.prune_mention_events(now)
        if events:
            logger.info('radar retention pruned %d mention events', events)
        closes = retention.prune_closes(now)
        if closes:
            logger.info('radar retention pruned %d daily closes', closes)


def _scheduled_sentiment():
    """The model re-read of tone, spec 6.11.

    Its own job rather than part of a cycle, and deliberately: ingest must
    never wait on an external API, and a source that failed must never be able
    to fail because sentiment did. Nothing downstream blocks on this -- a
    mention with no verdict simply keeps answering on its lexicon score.
    """
    with app.app_context():
        try:
            judged = llm_sentiment.run_pass()
        except Exception:
            # Broad on purpose, same as the source isolation above. A missing
            # API key raises at client construction, and taking the whole
            # daemon down over an optional enrichment would cost the ingest
            # this exists to decorate.
            logger.exception('radar sentiment pass failed')
            return
        if judged:
            # live_pending_count, not pending_count: the bare call applies
            # neither the gate nor the trial's retention pin, and reported
            # 37,017 waiting on 2026-09-08 while the pass could select 146.
            logger.info('radar sentiment judged %d mentions, %d still waiting '
                        '(%d behind the retention pin, unreachable)',
                        judged, llm_sentiment.live_pending_count(),
                        llm_sentiment.unreachable_count())
        try:
            reviewed = llm_sentiment.run_review_pass()
        except Exception:
            # Same isolation as the primary: the review tier is optional on
            # top of an optional enrichment, and it must never cost the
            # primary pass its turn.
            logger.exception('radar review pass failed')
            return
        if reviewed:
            logger.info('radar review judged %d mentions', reviewed)


def _prepare_rollup_generation(now):
    """Recover retained evidence and clear incompatible scores, once, before
    any fetcher or scheduler exists.

    Two things happen here and neither can wait for the first ingest cycle:

    Bootstrap first. The mention journal is empty immediately after migration
    (Task 1), so if the first cycle rebuilt an already-open quarter-hour
    straight from its own cursor slice, that would repeat the exact overwrite
    this generation exists to fix -- once, on the one window unlucky enough to
    still be open at deploy time. journal.bootstrap_from_mentions replays the
    retained radar_posts x radar_mentions evidence back through record() so
    that window rebuilds complete instead.

    Then the zero-recovery check. A fresh or genuinely quiet database recovers
    zero events because there is nothing to recover, and must be allowed to
    start. A migrated database whose retained evidence failed to bootstrap for
    some other reason ALSO recovers zero events, and the two are
    indistinguishable from the count alone -- an absence is never a zero. A
    legacy RadarBucketSource already showing real high_confidence_count in the
    same overlap window is what tells them apart: it is proof the evidence
    existed, so recovering none of it means bootstrap is broken, not that the
    world was quiet. Continuing anyway would serve relabelled scores over
    evidence that never actually made it into the journal, so this raises
    instead and lets the caller's lack of a try/except abort startup.

    Finally, incompatible scores in the same window are cleared so nothing
    still shows a generation-1 z-score under the generation-2 stamp before the
    first cycle even runs. score_source repeats a narrower version of this
    check every fifteen minutes as a backstop; this is the one-time pass for
    the migration boundary itself.
    """
    from models import RadarBucketSource

    with app.app_context():
        since = now.replace(tzinfo=None) - dt.timedelta(
            hours=MENTION_EVENT_RETENTION_HOURS)
        recovered = journal.bootstrap_from_mentions(since)
        if recovered == 0:
            legacy = (RadarBucketSource.query
                     .filter(RadarBucketSource.bucket_start >= since,
                             RadarBucketSource.high_confidence_count > 0)
                     .first())
            if legacy is not None:
                raise RuntimeError(
                    'radar rollup bootstrap recovered zero mention events, '
                    'but a legacy bucket in the same overlap window '
                    '(ticker=%s source=%s bucket_start=%s) already carries '
                    'high_confidence_count > 0 -- refusing to start ingest '
                    'against evidence that failed to bootstrap' %
                    (legacy.ticker, legacy.source, legacy.bucket_start))

        # A bucket write like any other: a recovery may be running from the
        # CLI at this moment, and it takes the same database-wide guard.
        from features.radar import buckets
        with buckets.bucket_write_guard():
            invalidated = scoring.invalidate_incompatible_scores(
                source_config_version(), since)
            db.session.commit()
        return recovered, invalidated


def main(argv=None):
    parser = argparse.ArgumentParser(description='Radar ingest daemon')
    # Direct callers (including daemon lifecycle tests) retain the old no-arg
    # contract. The executable entry point below explicitly supplies CLI args.
    parser.parse_args([] if argv is None else argv)
    logging.basicConfig(level=logging.INFO)
    if prefer_ipv4_if_configured():
        logger.info('RADAR_FORCE_IPV4 set -- outbound HTTP will skip AAAA records')

    # Ahead of build_fetchers and the scheduler, deliberately -- no cycle may
    # run against a mixed-generation database, and the zero-recovery check
    # above needs to see the pre-startup state before anything else touches
    # it. Uncaught on purpose: a bootstrap or invalidation failure must abort
    # the daemon rather than start ingest over evidence it could not recover.
    recovered, invalidated = _prepare_rollup_generation(
        dt.datetime.now(dt.timezone.utc))
    logger.info('radar rollup generation prepared: recovered=%d invalidated=%d',
               recovered, invalidated)

    # The judge is resolved and constructed HERE: before any fetcher, before
    # the scheduler, and outside _scheduled_sentiment's exception handler.
    # That handler exists so a failing optional enrichment cannot take the
    # daemon down with it -- which is exactly why a MISCONFIGURED judge must
    # not be discovered inside it, where it would be caught and logged every
    # ten minutes into a warning nobody reads twice. Uncaught on purpose.
    settings = judge_config.resolve_settings()
    with app.app_context():
        # The trial's own deadline is checked at startup as well as by its
        # timer: the timer cannot promise execution while the host is down,
        # and a trial must not resume judging across a gap that outlived
        # it. Before initialize_judges, so an expired trial is already
        # recovering when the encoder asks whether it may run.
        expiry = judge_trial.tick(dt.datetime.utcnow())
        if expiry.get('action') not in (None, 'none'):
            logger.warning('radar encoder trial at startup: %s', expiry)
        judge_config.initialize_judges(settings)

    fetchers = build_fetchers()

    if REDDIT_FETCHER == 'arctic_shift':
        # A misspelled subreddit answers 200 and an empty list forever; say
        # so once at start rather than build a baseline out of nothing.
        try:
            silent = arctic_shift.probe_subs(arctic_shift.ArcticShiftClient(), REDDIT_SUBS)
        except Exception:      # the probe must never keep the daemon from starting
            silent = []
        if silent:
            logger.warning('radar reddit: the archive has nothing for %s',
                           ', '.join(silent))

    scheduler = BackgroundScheduler(timezone='UTC')
    # next_run_time is not a nicety. An interval trigger otherwise fires only
    # after the first interval has elapsed, so starting the service overnight
    # means thirty minutes of silence before any evidence it works -- and the
    # same wait after every deploy restart. Catch-up is cursor-driven, so an
    # immediate first cycle costs nothing and collects the gap.
    # Reddit is pulled out of the session-driven cycle: it needs a fixed
    # cadence of its own, and the reason is in _scheduled_reddit.
    session_fetchers = {name: f for name, f in fetchers.items()
                        if name != 'reddit'}
    scheduler.add_job(_scheduled_cycle, 'interval', seconds=CYCLE_SECONDS,
                      id='radar_cycle', args=[scheduler, session_fetchers],
                      max_instances=1, coalesce=True,
                      next_run_time=dt.datetime.now(dt.timezone.utc))
    if 'reddit' in fetchers:
        # RSS: REDDIT_INTERVAL_SECONDS; Arctic Shift: ARCTIC_SHIFT_INTERVAL_SECONDS
        scheduler.add_job(_scheduled_reddit(fetchers['reddit']), 'interval',
                          seconds=_reddit_job_seconds(), id='radar_reddit',
                          max_instances=1, coalesce=True,
                          next_run_time=dt.datetime.now(dt.timezone.utc)
                          + dt.timedelta(seconds=30))
    # Two minutes behind the first cycle, so there are buckets to read before
    # the first scoring pass goes looking for them.
    #
    # Thirty minutes, not fifteen: a pass measured 27m52s on 2026-09-03,
    # against 42s before the Arctic Shift backfill filled every source's
    # 30-day window. At fifteen the scheduler simply skipped every second
    # firing (max_instances=1) and said so only in a warning -- an interval
    # the work cannot fit is a worse lie than a slower one that can.
    scheduler.add_job(_scheduled_scoring, 'interval', minutes=SCORING_INTERVAL_MINUTES,
                      id='radar_scoring', max_instances=1, coalesce=True,
                      next_run_time=dt.datetime.now(dt.timezone.utc)
                      + dt.timedelta(minutes=2))
    # Market-data v2 [A1][A2][A3]: independent US jobs behind
    # startup-validated flags. The old combined `radar_quotes` job is gone.
    from features.radar.config import price_provider_config
    us_provider, _ = price_provider_config()
    scheduler.add_job(_scheduled_us_quotes, 'interval',
                      minutes=US_QUOTE_MINUTES[us_provider],
                      id='radar_us_quotes', max_instances=1, coalesce=True)
    # 23:30 UTC is after the US close in both DST states [A1].
    scheduler.add_job(_scheduled_us_grouped_closes, 'cron', hour=23,
                      minute=30, id='radar_us_grouped_closes',
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
    # Registered whether or not capture is switched on, so turning it on is an
    # environment change and a restart rather than a code change. The job
    # itself reads the flag and returns; see _scheduled_observations.
    #
    # Started on the next quarter-hour boundary rather than fifteen minutes
    # after this process happened to start. Which part of a slot gets sampled
    # is then a property of the design instead of the last restart, and two
    # firings cannot land in one slot -- the second would be refused as
    # already recorded and its neighbour would read as an outage.
    scheduler.add_job(_scheduled_observations, 'interval', minutes=15,
                      id='radar_board_observations', max_instances=1,
                      coalesce=True,
                      next_run_time=_next_quarter_hour(
                          dt.datetime.now(dt.timezone.utc)))
    if not observations.capture_enabled():
        logger.info('radar board observation capture is disabled '
                    '(RADAR_OBSERVATION_CAPTURE_ENABLED)')
    # Ten minutes, and PASS_LIMIT caps each run, so a day of normal volume is
    # covered many times over and an abnormal one cannot run up a bill
    # unattended. Offset past the first cycle so there are mentions to read.
    scheduler.add_job(_scheduled_sentiment, 'interval', minutes=10,
                      id='radar_sentiment', max_instances=1, coalesce=True,
                      next_run_time=dt.datetime.now(dt.timezone.utc)
                      + dt.timedelta(minutes=4))
    scheduler.start()
    logger.info('radar ingest daemon started, sources=%s', ','.join(SOURCES))

    try:
        while True:
            time.sleep(60)
    except (KeyboardInterrupt, SystemExit):
        scheduler.shutdown()


if __name__ == '__main__':
    main(sys.argv[1:])
