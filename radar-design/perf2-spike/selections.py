"""The selections the spike measures, and the warm set of Part I.6.

ONE DELIBERATE SUBSTITUTION, and it is the reason PERF1 had to retract a whole
round of evidence. The plan's warm set spells its source selection
`('bluesky', 'fourchan', 'reddit')` -- every root. On the FIXTURE the root
`reddit` expands through `config.REDDIT_SUBS` to thirty-five real subreddit
names, of which the fixture holds three: it stores `reddit:sub03`..`sub32` as
placeholders. Asking for the root there would aggregate a fraction of the rows
and every timing under it would be an artifact.

So "every root" is spelled here as the fixture's own DISTINCT source list,
which covers 100% of its rows and roots to exactly `['bluesky', 'fourchan',
'reddit']` in the payload -- the same board, the same payload shape, the same
work. `perf1-bench/acceptance.py` did the same thing for the same reason.
"""
import datetime as dt

# Part I.6: two markets x two segment selections x four windows.
WARM_MARKETS = ('us', 'de')
WARM_SEGMENTS = ((), ('discover', 'mid', 'micro', 'unknown'))
WARM_WINDOWS = (1, 4, 12, 24)
WARM_LIMIT = 50
WARM_VENUES = 1


def warm_set(query_cls, sources):
    """The sixteen warm keys, as `Query` objects."""
    out = []
    for market in WARM_MARKETS:
        for segments in WARM_SEGMENTS:
            for window in WARM_WINDOWS:
                out.append(query_cls(sources=list(sources),
                                     segments=list(segments), window=window,
                                     limit=WARM_LIMIT, min_venues=WARM_VENUES,
                                     market=market, sort=None,
                                     direction='desc'))
    return out


def label(query):
    segs = ','.join(query.segments) if query.segments else 'all'
    tail = ''
    if query.sort:
        tail = ' sort=%s/%s' % (query.sort, query.direction)
    if query.limit != WARM_LIMIT:
        tail += ' limit=%d' % query.limit
    if query.min_venues != WARM_VENUES:
        tail += ' venues=%d' % query.min_venues
    if len(query.sources) < 4:
        tail += ' src=%s' % ','.join(query.sources)
    return '%2dh %-28s %s%s' % (query.window, segs, query.market.upper(), tail)


def fixed_now():
    """One instant for every comparison in a run.

    A moving `now` makes parity untestable: `board.build` uses
    `now - timedelta(hours=window)` unfloored, so two builds a second apart
    read two different windows.
    """
    return dt.datetime(2026, 9, 10, 12, 0, 0)
