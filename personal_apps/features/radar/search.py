"""Find a stock by symbol or name, anywhere in the universe.

Identity only. Whether a match is on today's board, and its score, the
island knows from the rows it already holds; building a board to say so
here would cost more than the whole search.
"""
import dataclasses

import sqlalchemy as sa

from models import TickerUniverse

from . import universe

LIMIT = 8
MAX_QUERY = 40


@dataclasses.dataclass
class Match:
    ticker: str
    name: str | None
    exchange: str | None
    segment: str


def search_universe(q, today, limit=LIMIT):
    """Matches for `q`: exact symbol, then symbols starting with it, then
    names containing it -- each group alphabetical, `limit` in all.

    Symbols are utf8mb4_bin, so the symbol side compares the uppercased
    query; names compare case-insensitively. Delisted symbols never match:
    a symbol reassigned to another company is a different stock.
    """
    q = (q or '').strip()[:MAX_QUERY]
    if not q:
        return []
    upper = q.upper()
    contains = f'%{q}%'
    rank = sa.case(
        (TickerUniverse.symbol == upper, 0),
        (TickerUniverse.symbol.like(f'{upper}%'), 1),
        else_=2)
    rows = (TickerUniverse.query
            .filter(TickerUniverse.delisted_at.is_(None))
            .filter(sa.or_(TickerUniverse.symbol.like(f'{upper}%'),
                           TickerUniverse.name.ilike(contains)))
            .order_by(rank, TickerUniverse.symbol)
            .limit(limit).all())
    return [Match(
        ticker=row.symbol,
        name=row.name,
        exchange=row.exchange,
        # No price at hand, and none needed: the segment is a size, and
        # the penny-price override only matters on a board row.
        segment=universe.segment_for(row.market_cap, row.ipo_date, None,
                                     today, row.name, row.is_etf),
    ) for row in rows]
