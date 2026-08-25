"""What each subreddit is worth per request, which is the only budget there is.

Reddit's anonymous feed budget is roughly one request per 90-120 seconds --
about 30 an hour, TOTAL, for every subreddit combined. So the question is not
"is this subreddit interesting" but "does it earn its share of thirty".

    cd personal_apps && PYTHONPATH=. python scripts/measure_subreddit_value.py
    cd personal_apps && PYTHONPATH=. python scripts/measure_subreddit_value.py --hours 24

THE COLUMNS THAT DECIDE IT are `mentions/hr` and `per feed`, and they answer
different halves.

`mentions/hr` is what a subreddit actually delivered. Undistorted.

`per feed` is what it delivered per request it ASKED FOR, which is the cost
side -- but it is understated for any sub the budget cannot satisfy. Demand
runs to 67 feeds an hour against a budget of 30, so a sub pinned at the floor
gets roughly half what it asks and its per-feed reads roughly half of the
truth. r/wallstreetbets is the worst affected, being the only sub at the
floor. Rows marked `starved` are the ones to read with that in mind.

THE OTHER TEST is the top-ticker column, from the source-list spec: "if it's
all mega-caps, the sub is a news reposter and adds nothing to a discovery
radar". A subreddit can be busy, cost a lot, and still contribute only names
the board would have found anyway.

WHAT THIS CANNOT TELL YOU. Posts are pruned at 30 days and only stored when
they carry a `high` mention, so counts here are mentions rather than traffic.
A subreddit can be talkative and score zero; that is exactly the case worth
cutting, and it shows up as a low mentions/feed with a real observed rate.
"""
import argparse
import collections
import datetime as dt

import sqlalchemy as sa

from app import app
from extensions import db
from features.radar.config import (REDDIT_MAX_POLL, REDDIT_MIN_POLL,
                                   REDDIT_SUBS)
from features.radar.scheduling import interval_for_rate
from models import RadarMention, RadarPollState, RadarPost

# Feeds per hour the whole source gets. Measured against the live endpoint
# 2026-08-25: successes at t=0, 78 and 198 seconds, refusals between.
BUDGET_PER_HOUR = 30.0

FEED_LIMIT = 25


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--hours', type=float, default=6.0)
    args = parser.parse_args()

    with app.app_context():
        # Naive UTC in Python, never SQL NOW(): the VPS clock is CEST and
        # created_utc is naive UTC, so NOW() silently shortens the window.
        now = dt.datetime.now(dt.timezone.utc).replace(tzinfo=None)
        since = now - dt.timedelta(hours=args.hours)

        rows = (db.session.query(RadarPost.channel,
                                 sa.func.count(sa.distinct(RadarPost.id)),
                                 sa.func.count(RadarMention.id),
                                 sa.func.count(sa.distinct(RadarMention.ticker)),
                                 sa.func.count(sa.distinct(RadarPost.author)))
                .outerjoin(RadarMention, RadarMention.post_id == RadarPost.id)
                .filter(RadarPost.source == 'reddit',
                        RadarPost.created_utc >= since)
                .group_by(RadarPost.channel).all())

        stats = {channel: (int(posts), int(mentions), int(tickers), int(authors))
                 for channel, posts, mentions, tickers, authors in rows}

        state = {row.symbol: row for row in RadarPollState.query.filter_by(
            source='reddit').all()}

        report = []
        for sub in REDDIT_SUBS:
            posts, mentions, tickers, authors = stats.get(sub, (0, 0, 0, 0))
            poll = state.get(sub)
            rate = poll.observed_rate if poll is not None else None
            # A rate of None means the scheduler has never measured this sub,
            # and interval_for_rate answers "poll soon and find out" -- the
            # floor. That is right for the scheduler and wrong here: reporting
            # an unmeasured sub as WANTING forty feeds an hour would put a
            # number nobody measured into a budget table, and the whole point
            # of this report is deciding what to cut on evidence.
            if rate is None:
                report.append({
                    'sub': sub, 'rate': None, 'feeds_hr': None, 'feeds': 0.0,
                    'posts': posts, 'mentions': mentions, 'tickers': tickers,
                    'authors': authors, 'per_feed': None,
                })
                continue

            interval = interval_for_rate(rate, floor=REDDIT_MIN_POLL,
                                         ceiling=REDDIT_MAX_POLL,
                                         page_size=FEED_LIMIT)
            feeds_per_hour = 3600.0 / interval.total_seconds()
            feeds = feeds_per_hour * args.hours
            report.append({
                'sub': sub,
                'rate': rate,
                'feeds_hr': feeds_per_hour,
                'feeds': feeds,
                'posts': posts,
                'mentions': mentions,
                'tickers': tickers,
                'authors': authors,
                'per_feed': (mentions / feeds) if feeds else 0.0,
                'per_hour': mentions / args.hours,
                # At the floor means it wants the fastest cadence there is, so
                # it is first in line for the shortfall when demand exceeds
                # the budget -- and its per-feed is understated most.
                'starved': interval <= REDDIT_MIN_POLL,
            })

        # Unmeasured last, and never ranked among the measured ones.
        report.sort(key=lambda entry: (entry['per_feed'] is None,
                                       -(entry['per_hour'] or 0.0)))
        measured = [e for e in report if e['feeds_hr'] is not None]
        unmeasured = [e for e in report if e['feeds_hr'] is None]

        print('reddit, last %g hours. Budget is ~%g feeds/hour for ALL '
              'subreddits combined.' % (args.hours, BUDGET_PER_HOUR))
        print()
        print('  %-22s %8s %8s %8s %8s %10s %10s %s'
              % ('subreddit', 'rate/hr', 'feeds/hr', 'mentions', 'tickers',
                 'mentions/hr', 'per feed', ''))
        for entry in measured:
            print('  %-22s %8.2f %8.2f %8d %8d %10.1f %10.2f %s'
                  % (entry['sub'], entry['rate'], entry['feeds_hr'],
                     entry['mentions'], entry['tickers'], entry['per_hour'],
                     entry['per_feed'], 'starved' if entry['starved'] else ''))
        for entry in unmeasured:
            print('  %-22s %8s %8s %8d %8d %10s %10s'
                  % (entry['sub'], 'never', 'never', entry['mentions'],
                     entry['tickers'], '-', '-'))
        if unmeasured:
            print('\n  %d subreddit(s) have never been polled successfully. '
                  'Not ranked, and left out of the budget below -- they have '
                  'no measured cost to weigh.' % len(unmeasured))

        spent = sum(entry['feeds_hr'] for entry in measured)
        earned = sum(entry['mentions'] for entry in report)
        print()
        print('  requested %.1f feeds/hour against a budget of %.0f'
              % (spent, BUDGET_PER_HOUR))
        if spent > BUDGET_PER_HOUR:
            print('  OVERSUBSCRIBED by %.1f/hour -- the scheduler serves the '
                  'most overdue, so the shortfall lands on whoever wants the '
                  'fastest cadence' % (spent - BUDGET_PER_HOUR))
        print('  %d mentions total, %.1f per hour' % (earned, earned / args.hours))

        # What cutting the bottom of the list would hand back. The subs at the
        # ceiling cost little each; the mid-tier is where the budget actually
        # goes, and that is the uncomfortable part of the decision.
        print('\nWHAT CUTTING WOULD FREE, cheapest contributors first')
        print('  (WSB turns its 25-entry feed over every 1.8 min, so that is '
              'the number to beat)')
        print('  %-22s %10s %12s %14s'
              % ('cut through here', 'frees/hr', 'loses mentions', 'WSB poll'))
        freed = 0.0
        lost = 0
        wsb = next((e for e in measured if e['sub'] == 'wallstreetbets'), None)
        wsb_hr = (wsb['feeds_hr'] if wsb else 0.0)

        def wsb_interval(demand):
            """Minutes between WSB polls at a given total demand.

            The scheduler serves whoever is most overdue, which over any
            stretch approximates a proportional share: every sub gets the same
            fraction of what it asked for. So WSB's actual cadence is its
            request scaled by budget/demand, and it cannot go below the floor
            however much is freed.

            The first version of this printed the same number on every row,
            because it added the freed budget to WSB's REQUEST and then capped
            at the budget -- WSB already requests more than the budget, so the
            cap bound immediately and the column said nothing.
            """
            if demand <= 0:
                return None
            got = min(wsb_hr * BUDGET_PER_HOUR / demand, wsb_hr)
            return 60.0 / got if got else None

        demand = spent
        for entry in reversed(measured):
            if entry['sub'] == 'wallstreetbets':
                continue
            freed += entry['feeds_hr']
            lost += entry['mentions']
            demand -= entry['feeds_hr']
            share = wsb_interval(demand)
            print('  %-22s %10.2f %12d %14s'
                  % (entry['sub'], freed, lost,
                     'every %.1f min' % share if share else '-'))

        print('\nTOP TICKERS PER SUBREDDIT -- all mega-caps means a news '
              'reposter, which a discovery radar does not need')
        per_sub = collections.defaultdict(collections.Counter)
        pairs = (db.session.query(RadarPost.channel, RadarMention.ticker)
                 .join(RadarMention, RadarMention.post_id == RadarPost.id)
                 .filter(RadarPost.source == 'reddit',
                         RadarPost.created_utc >= since).all())
        for channel, ticker in pairs:
            per_sub[channel][ticker] += 1
        for entry in report:
            top = per_sub[entry['sub']].most_common(8)
            if top:
                print('  %-22s %s' % (entry['sub'], ', '.join(
                    '%s=%d' % (ticker, count) for ticker, count in top)))
            else:
                print('  %-22s (nothing)' % entry['sub'])


if __name__ == '__main__':
    main()
