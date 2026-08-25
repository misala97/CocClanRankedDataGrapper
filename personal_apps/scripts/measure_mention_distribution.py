"""How mentions spread across tickers, and what adjudicating them would cost.

The question this exists to answer: a model pass over "contested" mentions is
only affordable if the contested set is SMALL. Nobody knows whether it is.
3610 tickers a day, nearly all mentioned once, is a heavy tail -- and a heavy
tail cuts both ways. If the handful of tickers near the board carry most of
the volume, then filtering to "tickers worth adjudicating" removes almost
nothing and the bill is the full-firehose bill.

    cd personal_apps && PYTHONPATH=. python scripts/measure_mention_distribution.py
    cd personal_apps && PYTHONPATH=. python scripts/measure_mention_distribution.py --days 7

WHAT TO LOOK FOR
    The cumulative table is the deliverable. Read down it to the row where the
    cutoff is roughly the number of tickers the board could ever surface, and
    read the cost on that row. That number decides whether this is a $1/day
    feature or a $30/day one.

    If cost barely falls between `all` and `top 200`, volume-gating does not
    work and a different definition of "contested" is needed.

COST MODEL
    Deliberately crude, and stated in constants below rather than buried. It
    assumes one call-unit per MENTION, which over-counts: two tickers in one
    post can be judged by a single read. The measured mentions-per-post ratio
    is printed so the over-count is visible rather than assumed away.
"""
import argparse
import datetime as dt

import sqlalchemy as sa

from app import app
from extensions import db
from models import RadarBucketSource, RadarMention, RadarPost

# Haiku 4.5 list price, 2026-08. Sync API -- the Batch API is half this but
# turns around in up to 24h, which a live board cannot use.
INPUT_PER_MTOK = 1.00
OUTPUT_PER_MTOK = 5.00

# A Bluesky post is capped at 300 graphemes. 100 covers the text plus the
# per-item framing; the shared instructions amortize away across a batch.
INPUT_TOKENS_PER_MENTION = 100
# A terse structured verdict, e.g. {"t":"AAPL","ticker":true,"s":"bull"}.
OUTPUT_TOKENS_PER_MENTION = 15

CUTOFFS = (50, 100, 200, 500, 1000, 2000, None)


def cost_per_day(mentions_per_day):
    """Dollars a day to read this many mentions at Haiku list price."""
    dollars_in = mentions_per_day * INPUT_TOKENS_PER_MENTION / 1e6 * INPUT_PER_MTOK
    dollars_out = mentions_per_day * OUTPUT_TOKENS_PER_MENTION / 1e6 * OUTPUT_PER_MTOK
    return dollars_in + dollars_out


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--days', type=float, default=1.0)
    parser.add_argument('--source', default=None,
                        help='restrict to one source; default pools all of them')
    args = parser.parse_args()

    with app.app_context():
        # Naive UTC computed in Python, never SQL NOW(): the VPS server clock
        # is CEST and bucket_start is naive UTC, so NOW() lands two hours off
        # and silently shortens the window.
        now = dt.datetime.now(dt.timezone.utc).replace(tzinfo=None)
        since = now - dt.timedelta(days=args.days)

        query = (db.session.query(
                    RadarBucketSource.ticker,
                    sa.func.sum(RadarBucketSource.mention_count),
                    sa.func.sum(RadarBucketSource.low_count),
                    sa.func.sum(RadarBucketSource.high_confidence_count))
                 .filter(RadarBucketSource.bucket_start >= since)
                 .group_by(RadarBucketSource.ticker))
        if args.source:
            query = query.filter(RadarBucketSource.source == args.source)

        # SUM() over an INTEGER column returns Decimal on MySQL and MariaDB,
        # and Decimal will not mix with the float arithmetic below.
        #
        # mention_count is high+medium; low_count is separate. So medium --
        # the bare tokens that a cashtag in the same bucket vouched for -- is
        # the difference, and it is worth naming because buckets._promote puts
        # no ceiling on it: one $ICE from one author promotes every bare "ICE
        # raids" mention in that quarter-hour.
        rows = [(ticker, int(scored or 0), int(low or 0), int(high or 0))
                for ticker, scored, low, high in query.all()]

        if not rows:
            print('no buckets in the last %g days -- ingest is down, or the '
                  'window predates the deploy' % args.days)
            return

        rows.sort(key=lambda row: -(row[1] + row[2]))
        total_scored = sum(row[1] for row in rows)
        total_low = sum(row[2] for row in rows)
        total_high = sum(row[3] for row in rows)
        total_medium = total_scored - total_high
        total = total_scored + total_low
        per_day = 1.0 / args.days

        label = args.source or 'all sources'
        print('%s, last %g days' % (label, args.days))
        print('  tickers seen      %10s' % format(len(rows), ','))
        print('  scored mentions   %10s   (%s/day)'
              % (format(total_scored, ','), format(round(total_scored * per_day), ',')))
        print('    of which high   %10s   (a cashtag, or a distinctive '
              'company word in the same post)' % format(total_high, ','))
        print('    of which medium %10s   (a bare token another author '
              'cashtagged in the same 15 min)' % format(total_medium, ','))
        print('  low  mentions     %10s   (%s/day)'
              % (format(total_low, ','), format(round(total_low * per_day), ',')))
        print('  total             %10s   (%s/day)'
              % (format(total, ','), format(round(total * per_day), ',')))
        print('  discard rate      %10.1f%%' % (100.0 * total_low / total))
        if total_scored:
            print('  medium share of scored %5.1f%%   <- buckets._promote puts '
                  'no ceiling on this' % (100.0 * total_medium / total_scored))

        print('\nHOW CONCENTRATED -- cumulative share of ALL mentions')
        print('  %10s  %12s  %7s  %10s  %8s  %9s'
              % ('cutoff', 'mentions', 'share', 'per day', '$/day', '$/month'))
        for cutoff in CUTOFFS:
            count = len(rows) if cutoff is None else min(cutoff, len(rows))
            running = sum(row[1] + row[2] for row in rows[:count])
            daily = running * per_day
            cost = cost_per_day(daily)
            name = 'all' if cutoff is None else 'top %d' % cutoff
            print('  %10s  %12s  %6.1f%%  %10s  %8.2f  %9.2f'
                  % (name, format(running, ','), 100.0 * running / total,
                     format(round(daily), ','), cost, cost * 30))
            if cutoff is not None and cutoff >= len(rows):
                break

        # The long tail is the cheap part to exclude. A ticker mentioned once
        # in a day cannot clear any eligibility floor whatever a model says
        # about it, so those mentions are never worth a call.
        singles = sum(1 for row in rows if row[1] + row[2] == 1)
        print('\n  tickers mentioned exactly once: %s (%.0f%% of tickers, '
              '%.1f%% of mentions)'
              % (format(singles, ','), 100.0 * singles / len(rows),
                 100.0 * singles / total))

        print('\nTOP 30 BY TOTAL MENTIONS -- scored + low, which is what a '
              'model pass would see')
        print('  %-8s %8s %8s %8s %8s %8s'
              % ('ticker', 'high', 'medium', 'scored', 'low', 'total'))
        for ticker, scored, low, high in rows[:30]:
            print('  %-8s %8s %8s %8s %8s %8s'
                  % (ticker, format(high, ','), format(scored - high, ','),
                     format(scored, ','), format(low, ','),
                     format(scored + low, ',')))

        # Mentions per post: how much the per-mention cost model over-counts,
        # since one read can judge every candidate in a post at once.
        # Measurable only over STORED posts, and a post is stored only when it
        # carries at least one `high` mention -- so this is a floor on the
        # real amortization rather than the number itself.
        posts, mentions = (db.session.query(
            sa.func.count(sa.distinct(RadarMention.post_id)),
            sa.func.count(RadarMention.id))
            .join(RadarPost, RadarPost.id == RadarMention.post_id)
            .filter(RadarPost.created_utc >= since).one())
        if posts:
            print('\n  mentions per stored post: %.2f -- divide the costs '
                  'above by this if one call judges a whole post (biased low: '
                  'only posts carrying a cashtag are stored)'
                  % (mentions / posts))

        # Single-letter cashtags. config.SINGLE_LETTER_CASHTAGS says these are
        # OFF for bluesky and fourchan, where `$M` is money shorthand and not
        # Macy's -- but ingest._extract_for never passes the flag, so
        # production runs with them ON for every source. Measure what that is
        # worth before anyone decides what to do about it.
        one_letter = [row for row in rows if len(row[0]) == 1]
        if one_letter:
            got = ', '.join('%s=%s' % (ticker, format(scored + low, ','))
                            for ticker, scored, low, _high in one_letter[:10])
            print('\n  single-letter symbols counted: %s' % got)
        else:
            print('\n  single-letter symbols counted: none')


if __name__ == '__main__':
    main()
