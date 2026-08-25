"""What each subreddit is worth per request, which is the only budget there is.

Reddit's anonymous feed budget is roughly one request per 90-120 seconds --
about 30 an hour, TOTAL, for every subreddit combined. So the question is not
"is this subreddit interesting" but "does it earn its share of thirty".

    cd personal_apps && PYTHONPATH=. python scripts/measure_subreddit_value.py
    cd personal_apps && PYTHONPATH=. python scripts/measure_subreddit_value.py --hours 24

THE COLUMN THAT DECIDES IT is `mentions/feed`. A subreddit polled every six
hours that yields nothing is not merely quiet -- it is spending requests that
r/wallstreetbets needs, and WSB turns its 25-entry feed over every 1.8 minutes
against a budget that cannot poll it faster than every 5.7. Everything cut
here goes straight to the subs that overflow.

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
            })

        # Unmeasured last, and never ranked among the measured ones.
        report.sort(key=lambda entry: (entry['per_feed'] is None,
                                       -(entry['per_feed'] or 0.0)))
        measured = [e for e in report if e['feeds_hr'] is not None]
        unmeasured = [e for e in report if e['feeds_hr'] is None]

        print('reddit, last %g hours. Budget is ~%g feeds/hour for ALL '
              'subreddits combined.' % (args.hours, BUDGET_PER_HOUR))
        print()
        print('  %-22s %8s %8s %8s %8s %8s %10s'
              % ('subreddit', 'rate/hr', 'feeds/hr', 'posts', 'mentions',
                 'tickers', 'per feed'))
        for entry in measured:
            print('  %-22s %8.2f %8.2f %8d %8d %8d %10.2f'
                  % (entry['sub'], entry['rate'], entry['feeds_hr'],
                     entry['posts'], entry['mentions'], entry['tickers'],
                     entry['per_feed']))
        for entry in unmeasured:
            print('  %-22s %8s %8s %8d %8d %8d %10s'
                  % (entry['sub'], 'never', 'never', entry['posts'],
                     entry['mentions'], entry['tickers'], '-'))
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
        print('  %-22s %10s %12s %14s'
              % ('cut through here', 'frees/hr', 'loses mentions', 'WSB poll'))
        freed = 0.0
        lost = 0
        wsb = next((e for e in measured if e['sub'] == 'wallstreetbets'), None)
        wsb_hr = (wsb['feeds_hr'] if wsb else 0.0)
        # Only what the budget is actually oversubscribed BY can be handed
        # back; freeing more than that just leaves the budget unspent.
        headroom = max(spent - BUDGET_PER_HOUR, 0.0)
        for entry in reversed(measured):
            if entry['sub'] == 'wallstreetbets':
                continue
            freed += entry['feeds_hr']
            lost += entry['mentions']
            # Everything freed goes to whoever wants the fastest cadence,
            # which is always WSB -- it is pinned at the floor and starved.
            share = min(wsb_hr + min(freed, headroom), BUDGET_PER_HOUR)
            print('  %-22s %10.2f %12d %14s'
                  % (entry['sub'], freed, lost,
                     'every %.1f min' % (60.0 / share) if share else '-'))

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
