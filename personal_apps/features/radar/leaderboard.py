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
from . import history, journal
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
    quote: object
    baseline_days: float | None
    marks: list
    # Whether this row cleared the eligibility floor. Always True on a
    # ranked board -- the floor is applied before a Row exists -- and
    # False on a pinned (watched) row that would not have been listed.
    eligible: bool = True
    # Which gate it failed, when it did: one of _GATE_ORDER or
    # 'no_mentions' (no bucket in the window at all). phrasing.py turns
    # it into words.
    floor_reason: str | None = None


def _universe_rows(tickers):
    if not tickers:
        return {}
    rows = TickerUniverse.query.filter(
        TickerUniverse.symbol.in_(list(tickers))).all()
    return {row.symbol: row for row in rows}


# Daily sigma per (ticker, market, mic), for one calendar day. The closes it
# is computed from arrive once a day, and every build was re-reading
# HISTORY_DAYS of them per survivor -- 31k rows and 600ms on the 24h board
# (measured 2026-09-01) for a number that had not changed since the last
# build. Cleared when the day turns; a process sees a few hundred tickers.
sigma_cache: dict = {}


def _quote_sigmas(quote_views, today):
    """Volatility from the history belonging to each selected quote identity.

    A company-level cached US sigma is not evidence about its Xetra listing.
    Grouping preserves the batched read for normal US boards while allowing a
    Germany board's genuine and fallback rows to use their actual markets.
    """
    if any(key[3] != today for key in list(sigma_cache)):
        sigma_cache.clear()

    sigmas = {}
    by_identity = collections.defaultdict(list)
    for ticker, quote in quote_views.items():
        key = (ticker, quote.market, quote.mic, today)
        if key in sigma_cache:
            sigmas[ticker] = sigma_cache[key]
        else:
            by_identity[(quote.market, quote.mic)].append(ticker)

    for (market, mic), tickers in by_identity.items():
        if market == 'de':
            # A German identity seeds its volatility from whichever of the
            # ticker's listings actually has depth -- the Xetra sibling, or
            # the US primary converted into euros. Tradegate itself stores
            # about two days of closes, and a sigma from two closes is a
            # number with no information in it.
            #
            # Converted rather than raw dollars on purpose: the move this
            # sigma is compared against is measured in the quote's own
            # currency, so the volatility must be too.
            for ticker in tickers:
                basis = history.resolve_basis(
                    ticker, quote_views[ticker], history.HISTORY_DAYS, today)
                sigmas[ticker] = quotes_mod.daily_sigma(list(basis.closes))
                sigma_cache[(ticker, market, mic, today)] = sigmas[ticker]
            continue
        closes = history.closes_for(tickers, days=history.HISTORY_DAYS,
                                    today=today, market=market, mic=mic)
        for ticker in tickers:
            sigmas[ticker] = quotes_mod.daily_sigma(closes.get(ticker, []))
            sigma_cache[(ticker, market, mic, today)] = sigmas[ticker]
    return sigmas


def _aggregate(scored_sources, since, now, tickers=None):
    """One aggregated row per (ticker, source) over the window.

    Aggregated in SQL rather than in Python -- see _chatter_survivors for the
    measurement that decided it. `tickers` narrows the scan to named ones
    (the pinned path); None means every ticker with a scored bucket.
    """
    bucket = RadarBucketSource
    query = (db.session.query(
        bucket.ticker.label('ticker'),
        bucket.source.label('source'),
        sa.func.sum(bucket.mention_count).label('mentions'),
        sa.func.sum(sa.func.coalesce(bucket.expected, 0.0)).label('expected'),
        sa.func.sum(sa.func.coalesce(bucket.variance, 0.0)).label('variance'),
        sa.func.max(bucket.distinct_authors).label('authors'),
        sa.func.min(bucket.distinct_text_ratio).label('text_ratio'),
        # MIN over a nullable baseline_days skips NULLs, which is exactly
        # what the Python it replaces did. The columns that must not skip --
        # mention_count, distinct_authors, distinct_text_ratio, status -- are
        # all NOT NULL.
        sa.func.min(bucket.baseline_days).label('baseline_days'),
        sa.func.max(sa.case((bucket.status == 'truncated', 1), else_=0))
        .label('truncated'))
        .filter(bucket.source.in_(scored_sources),
                bucket.bucket_start >= since,
                bucket.bucket_start < now,
                bucket.mention_z.isnot(None)))
    if tickers is not None:
        query = query.filter(bucket.ticker.in_(list(tickers)))
    grouped = collections.defaultdict(list)
    for row in query.group_by(bucket.ticker, bucket.source).all():
        grouped[row.ticker].append(row)
    return grouped


def _fold(parts, authors, channels):
    """One ticker's per-source rows folded into the figures the floor and the
    row use. `authors` is the journal's true count or None (then the bucket
    maximum, which undercounts in the safe direction)."""
    # `parts` is one already-aggregated row per source, so these fold a
    # handful of numbers rather than a few hundred bucket objects.
    # Coerced here, once. SUM over an INTEGER column comes back as Decimal
    # from MySQL and MariaDB alike, and Decimal minus float raises -- so
    # the mention_z arithmetic in `_assemble` would have been the first
    # thing to break, in the middle of scoring rather than at the boundary.
    mentions = int(sum(part.mentions for part in parts))
    expected = float(sum(part.expected for part in parts))
    variance = float(sum(part.variance for part in parts))
    authors = authors if authors is not None else int(max(part.authors for part in parts))
    text_ratio = float(min(part.text_ratio for part in parts))

    # The gate is per kind: a forum's independent voices are its authors, a
    # broadcast network's are its channels. The pooled figures above still
    # describe the row -- they just no longer decide it.
    by_kind = collections.defaultdict(lambda: [0, 1.0])   # [mentions, lowest text ratio seen]
    for part in parts:
        totals = by_kind[source_kind(part.source)]
        totals[0] += int(part.mentions)
        totals[1] = min(totals[1], float(part.text_ratio))
    contributions = {
        kind: scoring.Contribution(
            mentions=totals[0],
            voices=(channels if kind == 'broadcast' else authors),
            text_ratio=totals[1])
        for kind, totals in by_kind.items()
    }
    return mentions, expected, variance, authors, text_ratio, contributions


def _chatter_survivors(sources, now, window_hours):
    """PASS ONE of build_rows, extracted whole: the chatter-only judgement.

    Returns (survivors, excluded, grouped, channel_counts). No market,
    quote, history, profile, or segment lookup happens here -- the grouped
    active-coverage denominator and the scheduler union consume EXACTLY
    this judgement, so one implementation owns it (plan Task 8 Step 7b).
    """
    since = now - dt.timedelta(hours=window_hours)
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
    scored_sources = expand_sources(sources)
    # How many venues the VIEWER switched on, rooted for the same reason the
    # contributing count is: picking `reddit` is picking one venue, however
    # many subreddits it expands to.
    selected_venues = len({source_root(name) for name in sources})
    grouped = _aggregate(scored_sources, since, now)

    # Eligibility needs these two and nothing else -- and only for tickers
    # that can still be eligible. Under MIN_MENTIONS no voice count changes
    # the verdict, and on the 24h board that is most of the ~4,000 tickers
    # with a scored bucket: asking for all of them, in two queries, was 3.3s
    # of an 8s build (measured 2026-09-01). The rest keep the bucket-maximum
    # fallback below, which is the same answer they would have got from an
    # aged-out journal.
    worth_asking = [
        ticker for ticker, parts in grouped.items()
        if sum(int(part.mentions) for part in parts) >= scoring.MIN_MENTIONS]
    voices = journal.distinct_voice_counts(worth_asking, sources, since, now)
    author_counts = {ticker: counts[0] for ticker, counts in voices.items()}
    channel_counts = {ticker: counts[1] for ticker, counts in voices.items()}

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
        mentions, expected, variance, authors, text_ratio, contributions = _fold(
            parts, author_counts.get(ticker), channel_counts.get(ticker, 0))

        # Below the floor there is nothing to rank. Showing it low would imply
        # it was measured and found wanting, when it was never measurable --
        # but dropping it silently is how a two-row board became
        # indistinguishable from a dead ingest, so the reason is counted.
        if not scoring.is_eligible(contributions):
            excluded[_rejection(contributions)] += 1
            continue

        survivors[ticker] = (mentions, expected, variance, authors, text_ratio)

    return survivors, excluded, grouped, channel_counts


def chatter_candidates(sources, now, window_hours):
    """Sorted tickers whose chatter clears the floor in one window."""
    survivors, _, _, _ = _chatter_survivors(sources, now, window_hours)
    return sorted(survivors)


def _assemble(ticker, folded, parts, profile, quote, moves, quote_sigmas,
              window_hours, selected_venues, today,
              eligible=True, floor_reason=None):
    """Everything that costs a lookup, for one ticker, into a Row.

    Shared by the ranked board and the pinned (watched) rows so the two can
    never disagree about what a row says.
    """
    mentions, expected, variance, authors, text_ratio = folded
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

    status = quote.tape_status
    move = (moves.get((ticker, quote.market))
            if quote.score_eligible else None)

    # A frozen tape reports no movement while mentions explode because it
    # froze. That is maximum divergence produced by an artifact, so the
    # row carries the mark and no score rather than a flattering number.
    # 'closed' lands here too and for the same reason -- but it earns no
    # mark, because the exchange being shut says nothing about the stock.
    value = None
    if quote.score_eligible and move is not None and mention_z is not None:
        sigma = quote_sigmas.get(ticker)
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

    segment = universe.segment_for(
        profile.market_cap if profile else None,
        profile.ipo_date if profile else None,
        quote.price, today,
        profile.name if profile else None,
        profile.is_etf if profile else None)

    return Row(
        ticker=ticker,
        name=profile.name if profile else None,
        segment=segment,
        divergence=value,
        mention_z=mention_z,
        mentions=mentions,
        expected=expected,
        authors=authors,
        text_ratio=text_ratio,
        sources=contributing,
        venues=venues,
        price=quote.price,
        price_move=move,
        direction=divergence_mod.direction(move),
        price_status=status,
        quote=quote,
        baseline_days=baseline_days,
        marks=marks,
        eligible=eligible,
        floor_reason=floor_reason,
    )


def build_rows(sources, now, window_hours=4, segments=(), limit=50,
               min_venues=1, market='us'):
    """Ranked leaderboard rows for the selected sources.

    `sources` is the viewer's SELECTION, root-level or concrete, not an
    expanded list. The bucket query below is a SCORED read, so it expands
    strictly: the pre-split root `reddit` rows carry a different
    source_config_version and their z belongs to a different baseline
    population (see config.expand_sources). The voice counts are raw and
    expand for history.

    The source list is a read-time filter: it re-pools components that were
    stored per source, and never touches how anything was scored (spec 8.6).

    Quote selection supplies its own market/session/tape state per row.  A
    Germany board can therefore rank a marked US fallback on its US session
    without treating every row as if it shared the aggregate board session.
    """
    survivors, excluded, grouped, channel_counts = _chatter_survivors(
        sources, now, window_hours)
    # A selection may name groups ('discover'), single segments, or several
    # of either, resolved once rather than per row; empty means everything.
    allowed = segments_in(segments)
    # One venue per ROOT: picking `reddit` is picking one venue, however
    # many subreddits it expands to.
    selected_venues = len({source_root(name) for name in sources})

    # PASS TWO: everything that costs a lookup, for the rows that survived.
    profiles = _universe_rows(survivors.keys())
    # The quote lookups were an N+1 here until 2026-08-24 -- a status, a move
    # and a latest snapshot per ticker, ~1200 round trips and 1.58s of TTFB
    # against 30ms for the detail panel doing the same three for one ticker.
    quote_views = quotes_mod.quote_views_for(survivors.keys(), market, now)
    moves = quotes_mod.moves_for(
        [(ticker, view.market, view.mic) for ticker, view in quote_views.items()
         if view.price is not None], window_hours, now)
    today = now.date()
    quote_sigmas = _quote_sigmas(quote_views, today)
    rows = []

    for ticker, (mentions, expected, variance, authors,
                 text_ratio) in survivors.items():
        row = _assemble(ticker, (mentions, expected, variance, authors, text_ratio),
                        grouped[ticker], profiles.get(ticker), quote_views[ticker],
                        moves, quote_sigmas, window_hours, selected_venues, today)
        if allowed and row.segment not in allowed:
            continue
        # Breadth as a filter, not as a score. `contributing` is the list of
        # sources that actually said something, so this asks how many venues
        # are talking rather than how many the viewer has switched on.
        #
        # Counted apart from the floor: this is the reader's own filter doing
        # what they asked, not the data being too thin to measure. Merging the
        # two would tell them the data was worse than it is.
        if row.venues < min_venues:
            excluded['one_venue'] += 1
            continue
        rows.append(row)

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


def build_pinned(tickers, sources, now, window_hours=4, market='us'):
    """Rows for named tickers regardless of the eligibility floor.

    The floor decides ranking, not existence: a watched stock the reader
    marked deserves a row saying what was measured and why it was not
    ranked. Same aggregate, same lookups, same Row as the board -- with
    `eligible` False and `floor_reason` set where the floor would have
    dropped it, and every derived figure None where nothing was measured.
    """
    tickers = list(dict.fromkeys(t.upper() for t in tickers))
    if not tickers:
        return []
    since = now - dt.timedelta(hours=window_hours)
    scored_sources = expand_sources(sources)
    selected_venues = len({source_root(name) for name in sources})

    grouped = _aggregate(scored_sources, since, now, tickers=tickers)
    voices = journal.distinct_voice_counts(tickers, sources, since, now)
    profiles = _universe_rows(tickers)
    quote_views = quotes_mod.quote_views_for(tickers, market, now)
    moves = quotes_mod.moves_for(
        [(ticker, view.market, view.mic) for ticker, view in quote_views.items()
         if view.price is not None], window_hours, now)
    today = now.date()
    quote_sigmas = _quote_sigmas(quote_views, today)

    rows = []
    for ticker in tickers:
        parts = grouped.get(ticker, [])
        if parts:
            authors_seen, channels_seen = voices.get(ticker, (None, 0))
            mentions, expected, variance, authors, text_ratio, contributions = _fold(
                parts, authors_seen, channels_seen)
            eligible = scoring.is_eligible(contributions)
            reason = None if eligible else _rejection(contributions)
        else:
            # No bucket in the window: nothing measured, and the fold would
            # divide by nothing. Zeros here are counts of nothing observed,
            # not measurements; the derived figures come out None.
            mentions, expected, variance, authors, text_ratio = 0, 0.0, 0.0, 0, 1.0
            eligible, reason = False, 'no_mentions'
        rows.append(_assemble(
            ticker, (mentions, expected, variance, authors, text_ratio), parts,
            profiles.get(ticker), quote_views[ticker], moves, quote_sigmas,
            window_hours, selected_venues, today,
            eligible=eligible, floor_reason=reason))
    return rows
