# personal_apps/features/radar/leaderboard.py
"""One ranked row per ticker.

Reads scored buckets, quotes and universe rows; decides nothing about
appearance. What it does decide is what is worth showing at all -- the
eligibility floor -- and that matters more on a thin board than a busy one,
because the temptation to pad is greatest when there is little to show.
"""
import collections
import dataclasses
import datetime as dt

import sqlalchemy as sa

from extensions import db
from models import RadarBucketSource, TickerUniverse

from . import divergence as divergence_mod
from . import journal
from . import market_calendar
from . import quotes as quotes_mod
from . import scoring, universe
from .config import (PROVISIONAL_BASELINE_DAYS, VARIANCE_FLOOR,
                     expand_sources, segments_in, source_kind, source_root)


@dataclasses.dataclass
class Ranking:
    """Rows worth showing, and an account of what was left out.

    The account is not decoration. The eligibility floor is the single largest
    reason this board is short, and until now it dropped tickers with no trace
    -- so a quiet market and a stopped daemon rendered identically, and the
    reader had no way to tell which they were looking at.
    """
    rows: list
    # reason -> how many tickers it rejected. See _rejection for the vocabulary.
    excluded: dict


@dataclasses.dataclass
class Row:
    ticker: str
    name: str | None
    segment: str
    divergence: float | None
    mention_z: float | None
    mentions: int
    expected: float
    authors: int
    text_ratio: float
    # Concrete stored names that contributed -- `reddit:pennystocks`, not
    # `reddit`. This is the breakdown, and it must stay concrete.
    sources: list
    # How many INDEPENDENT venues those names represent, which is the count of
    # their roots. Two subreddits are two entries in `sources` and one venue:
    # they share a platform, a user population and a rate-limit budget, so the
    # corroboration the breadth filter and the `single-source` mark claim is
    # not there. Carried as its own field rather than recomputed by every
    # reader, so the two can never drift apart.
    venues: int
    price: object
    price_move: object
    direction: str
    price_status: str
    baseline_days: float | None
    marks: list


def _distinct_authors(tickers, sources, since, now):
    """True distinct authors per ticker across the whole window.

    Read from the mention journal rather than from radar_mentions. That table
    never holds `medium` -- promotion is decided at rollup over the whole
    bucket and written back onto the journal -- and a post whose tickers were
    all `low` is never stored there at all, so the count it gave was smaller
    than the mention count the floor was gating.

    Falls back to nothing: a ticker whose events have aged out of the journal
    is absent from the result and the caller uses the bucket maximum, which
    undercounts in the safe direction.
    """
    return journal.distinct_voices(tickers, sources, since, now, 'author')


def _distinct_channels(tickers, sources, since, now):
    """The broadcast analogue. See _distinct_authors."""
    return journal.distinct_voices(tickers, sources, since, now, 'channel')


def _universe_rows(tickers):
    if not tickers:
        return {}
    rows = TickerUniverse.query.filter(
        TickerUniverse.symbol.in_(list(tickers))).all()
    return {row.symbol: row for row in rows}


def build_rows(sources, now, window_hours=4, segments=(), limit=50,
               session=None, min_venues=1):
    """Ranked leaderboard rows for the selected sources.

    `sources` is the viewer's SELECTION, root-level or concrete, not an
    expanded list. The bucket query below is a SCORED read, so it expands
    strictly: the pre-split root `reddit` rows carry a different
    source_config_version and their z belongs to a different baseline
    population (see config.expand_sources). The voice counts are raw and
    expand for history.

    The source list is a read-time filter: it re-pools components that were
    stored per source, and never touches how anything was scored (spec 8.6).

    `session` is the exchange state. With the market shut no row gets a
    divergence, because there is no price movement to be surprised by -- so
    the sort falls through to mention_z and the board ranks on chatter alone.
    That is the useful answer at 23:00 on a Sunday (what is worth looking at
    on Monday), and it is only honest if the surface says which of the two
    rankings the reader is looking at. Computed once here rather than per
    ticker; the caller may pass it in to avoid computing it twice.
    """
    since = now - dt.timedelta(hours=window_hours)
    # A selection may name groups ('small'), single segments, or several of
    # either. Resolved to a flat union.
    # once rather than per row; empty means everything.
    allowed = segments_in(segments)
    if session is None:
        session = market_calendar.session_state(
            now.replace(tzinfo=dt.timezone.utc))

    # Aggregated in SQL rather than in Python, and this is the difference
    # between a page and a wait. Every figure the loop below needs is a SUM, a
    # MAX or a MIN over a ticker's buckets, and fetching the buckets themselves
    # meant materialising a mapped object per bucket per source per quarter
    # hour: measured on the live board 2026-08-24, 17,508 rows to rank four
    # tickers on the 4h board and 99,776 to rank forty-one on the 24h one --
    # 707ms of SQL and 1.8s of object construction, for figures the database
    # can produce in one pass.
    #
    # Grouped by SOURCE as well as ticker, not folded to kind here: which kind
    # a source belongs to is `source_kind`'s judgement and it stays in Python.
    # Sources are a handful, so this is ~3 rows per ticker rather than ~96.
    #
    # MIN over a nullable baseline_days skips NULLs, which is exactly what the
    # Python it replaces did. The columns that must not skip -- mention_count,
    # distinct_authors, distinct_text_ratio, status -- are all NOT NULL.
    scored_sources = expand_sources(sources)
    # How many venues the VIEWER switched on, rooted for the same reason the
    # contributing count is: picking `reddit` is picking one venue, however
    # many subreddits it expands to.
    selected_venues = len({source_root(name) for name in sources})
    bucket = RadarBucketSource
    per_source = (db.session.query(
        bucket.ticker.label('ticker'),
        bucket.source.label('source'),
        sa.func.sum(bucket.mention_count).label('mentions'),
        sa.func.sum(sa.func.coalesce(bucket.expected, 0.0)).label('expected'),
        sa.func.sum(sa.func.coalesce(bucket.variance, 0.0)).label('variance'),
        sa.func.max(bucket.distinct_authors).label('authors'),
        sa.func.min(bucket.distinct_text_ratio).label('text_ratio'),
        sa.func.min(bucket.baseline_days).label('baseline_days'),
        sa.func.max(sa.case((bucket.status == 'truncated', 1), else_=0))
        .label('truncated'))
        .filter(bucket.source.in_(scored_sources),
                bucket.bucket_start >= since,
                bucket.bucket_start < now,
                bucket.mention_z.isnot(None))
        .group_by(bucket.ticker, bucket.source)
        .all())

    grouped = collections.defaultdict(list)
    for row in per_source:
        grouped[row.ticker].append(row)

    # Eligibility needs these two and nothing else, so they are the only
    # lookups that have to cover every ticker with a scored bucket.
    author_counts = _distinct_authors(grouped.keys(), sources, since, now)
    channel_counts = _distinct_channels(grouped.keys(), sources, since, now)

    # PASS ONE: fold the aggregates and apply the floor.
    #
    # Split from pass two because of the ratio between them. Measured on the
    # live board 2026-08-24: 3,497 tickers have a scored bucket in a 24h
    # window and 41 clear the floor. Fetching universe rows, quote statuses
    # and price moves before this point meant doing all three for 3,497
    # tickers and discarding 3,456 of them -- 14,029 quote rows to end up
    # using about 170, and a mapped TickerUniverse object per rejected ticker.
    survivors = {}
    excluded = collections.Counter()

    for ticker, parts in grouped.items():
        # `parts` is one already-aggregated row per source, so these fold a
        # handful of numbers rather than a few hundred bucket objects.
        # Coerced here, once. SUM over an INTEGER column comes back as Decimal
        # from MySQL and MariaDB alike, and Decimal minus float raises -- so
        # the mention_z line below would have been the first thing to break,
        # in the middle of scoring rather than at the boundary.
        mentions = int(sum(part.mentions for part in parts))
        expected = float(sum(part.expected for part in parts))
        variance = float(sum(part.variance for part in parts))
        # True count where the posts are still retained; the bucket maximum
        # only as a fallback once they have aged out. The fallback undercounts,
        # which is the safe direction -- it can hide a ticker but never invent
        # breadth that was not there.
        authors = author_counts.get(
            ticker, int(max(part.authors for part in parts)))
        text_ratio = float(min(part.text_ratio for part in parts))

        # The gate is per kind: a forum's independent voices are its authors, a
        # broadcast network's are its channels. The pooled figures above still
        # describe the row -- they just no longer decide it.
        by_kind = collections.defaultdict(
            lambda: [0, 1.0])          # [mentions, lowest text ratio seen]
        for part in parts:
            totals = by_kind[source_kind(part.source)]
            totals[0] += int(part.mentions)
            totals[1] = min(totals[1], float(part.text_ratio))

        contributions = {
            kind: scoring.Contribution(
                mentions=totals[0],
                voices=(channel_counts.get(ticker, 0) if kind == 'broadcast'
                        else authors),
                text_ratio=totals[1])
            for kind, totals in by_kind.items()
        }

        # Below the floor there is nothing to rank. Showing it low would imply
        # it was measured and found wanting, when it was never measurable --
        # but dropping it silently is how a two-row board became
        # indistinguishable from a dead ingest, so the reason is counted.
        if not scoring.is_eligible(contributions):
            excluded[_rejection(contributions)] += 1
            continue

        survivors[ticker] = (mentions, expected, variance, authors, text_ratio)

    # PASS TWO: everything that costs a lookup, for the rows that survived.
    profiles = _universe_rows(survivors.keys())
    # The quote lookups were an N+1 here until 2026-08-24 -- a status, a move
    # and a latest snapshot per ticker, ~1200 round trips and 1.58s of TTFB
    # against 30ms for the detail panel doing the same three for one ticker.
    statuses = quotes_mod.statuses_for(survivors.keys(), now, session=session)
    moves = quotes_mod.moves_for(survivors.keys(), window_hours, now)
    today = now.date()
    rows = []

    for ticker, (mentions, expected, variance, authors,
                 text_ratio) in survivors.items():
        parts = grouped[ticker]
        mention_z = ((mentions - expected)
                     / max(variance, VARIANCE_FLOOR) ** 0.5) if variance else None

        contributing = sorted({part.source for part in parts})
        # One venue per ROOT, not per stored name -- see Row.venues.
        venues = len({source_root(name) for name in contributing})
        # MIN already skipped NULLs per source; this skips the sources that
        # had nothing but NULLs, so a row with no usable baseline anywhere
        # still reports None rather than raising. Coerced like the aggregates
        # above for the same reason, even though MIN/MAX over a Float column
        # (unlike SUM over an Integer one) do not promote to Decimal on
        # MySQL/MariaDB -- matching the sibling pattern removes the ambiguity
        # for a future reader rather than relying on that distinction silently.
        baseline_days = min((float(part.baseline_days) for part in parts
                             if part.baseline_days is not None), default=None)

        profile = profiles.get(ticker)
        status, latest = statuses[ticker]
        move = moves[ticker]
        if status == 'unknown':
            # Kept explicit rather than relying on the batch: 'unknown' means
            # never quoted, so there is no snapshot to carry even though the
            # mapping always has an entry for every ticker asked about.
            latest = None

        # A frozen tape reports no movement while mentions explode because it
        # froze. That is maximum divergence produced by an artifact, so the
        # row carries the mark and no score rather than a flattering number.
        # 'closed' lands here too and for the same reason -- but it earns no
        # mark, because the exchange being shut says nothing about the stock.
        value = None
        if status == 'ok' and move is not None and mention_z is not None:
            sigma = profile.daily_sigma if profile else None
            move_z = divergence_mod.price_move_z(
                move, quotes_mod.scale_sigma(sigma, window_hours))
            if move_z is not None:
                value = divergence_mod.divergence(mention_z, move_z)

        marks = []
        if status == 'stale':
            marks.append('no-print')
        if venues == 1 and selected_venues > 1:
            marks.append('single-source')
        if baseline_days is not None and baseline_days < PROVISIONAL_BASELINE_DAYS:
            # Two different facts wear this badge, and only one is about the
            # ticker. A NEW ticker has thin history of its own; every ticker on
            # the board has thin history when the extraction rules changed
            # recently, because baselines are built per config version. Saying
            # `provisional` for both made it fire on all of them.
            marks.append('provisional' if baseline_days >= 1.0 else 'warming-up')
        if any(part.truncated for part in parts):
            marks.append('partial')

        row_segment = universe.segment_for(
            profile.market_cap if profile else None,
            profile.ipo_date if profile else None,
            latest.price if latest else None,
            today, profile.name if profile else None,
            profile.is_etf if profile else None)
        if allowed and row_segment not in allowed:
            continue
        # Breadth as a filter, not as a score. `contributing` is the list of
        # sources that actually said something, so this asks how many venues
        # are talking rather than how many the viewer has switched on.
        #
        # Counted apart from the floor: this is the reader's own filter doing
        # what they asked, not the data being too thin to measure. Merging the
        # two would tell them the data was worse than it is.
        if venues < min_venues:
            excluded['one_venue'] += 1
            continue

        rows.append(Row(
            ticker=ticker,
            name=profile.name if profile else None,
            segment=row_segment,
            divergence=value,
            mention_z=mention_z,
            mentions=mentions,
            expected=expected,
            authors=authors,
            text_ratio=text_ratio,
            sources=contributing,
            venues=venues,
            price=latest.price if latest else None,
            price_move=move,
            direction=divergence_mod.direction(move),
            price_status=status,
            baseline_days=baseline_days,
            marks=marks,
        ))

    # Divergence first where it exists, then mention_z. A ticker with no price
    # is not evidence of anything about its price, so it sorts below one that
    # has been measured -- but it is not dropped.
    rows.sort(key=lambda r: (r.divergence is not None,
                             r.divergence if r.divergence is not None else 0,
                             r.mention_z or 0), reverse=True)
    return Ranking(rows=rows[:limit] if limit else rows,
                   excluded=dict(excluded))


# Ordered by how far a ticker got before failing. A later gate means every
# earlier one passed, so the furthest failure is the most informative
# description of why a ticker is not on the board.
_GATE_ORDER = ('too_few_mentions', 'too_few_voices', 'repeated_text')


def _rejection(contributions):
    """Which gate a ticker failed, or None if it passed.

    Reported against the ticker's BEST kind rather than every kind it touched.
    A ticker carried by three Bluesky authors and glanced at by one Telegram
    channel is not "too few voices" merely because the broadcast side was
    thin -- it failed on the forum side or not at all.
    """
    best = None
    for kind, part in contributions.items():
        if part.mentions < scoring.MIN_MENTIONS:
            reason = 'too_few_mentions'
        elif part.voices < scoring._VOICE_FLOOR.get(
                kind, scoring.MIN_DISTINCT_AUTHORS):
            reason = 'too_few_voices'
        elif part.text_ratio < scoring.MIN_DISTINCT_TEXT_RATIO:
            reason = 'repeated_text'
        else:
            return None
        if best is None or _GATE_ORDER.index(reason) > _GATE_ORDER.index(best):
            best = reason
    return best
